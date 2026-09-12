from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch

from _support import PYTHON, RUNNER_CLI, WindowsOnlyTestCase
from libreoffice_runner.core import RunRequest, _conversion_command, _prepare, _read_capture, convert, main, run


class _Lease:
    def __enter__(self) -> "_Lease":
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        return None


class CoreTests(WindowsOnlyTestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(prefix="r")
        self.root = Path(self.temp_dir.name)
        self.source = self.root / "input.docx"
        self.source.write_bytes(b"not-opened-in-these-tests")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_existing_output_returns_before_capacity_acquisition(self) -> None:
        output = self.root / "output.pdf"
        output.write_bytes(b"already exists")
        request = RunRequest("pdf", self.source, output, soffice=PYTHON)
        with patch("libreoffice_runner.core.CapacitySlots.acquire", side_effect=AssertionError("must not queue")):
            report = run(request)
        self.assertFalse(report.ok)
        self.assertEqual(report.error, "output_exists")

    def test_second_output_check_prevents_launch_after_queue_wait(self) -> None:
        output = self.root / "output.pdf"
        request = RunRequest("pdf", self.source, output, soffice=PYTHON)

        def acquire(_self: object, _timeout: float) -> _Lease:
            output.write_bytes(b"created by earlier waiter")
            return _Lease()

        with patch("libreoffice_runner.core.CapacitySlots.acquire", new=acquire):
            report = run(request)
        self.assertFalse(report.ok)
        self.assertEqual(report.error, "output_exists")

    def test_command_uses_uri_and_never_nolockcheck(self) -> None:
        long_parent = self.root / ("中文 空格-" * 20)
        long_parent.mkdir()
        source = long_parent / "输入.xlsx"
        source.write_bytes(b"placeholder")
        output = long_parent / "输出.xlsx"
        prepared = _prepare(RunRequest("recalc", source, output))
        command = _conversion_command(prepared, PYTHON, long_parent / "profile", source, long_parent / "generated")
        profile_argument = next(item for item in command if item.startswith("-env:UserInstallation="))
        self.assertIn("file:///", profile_argument)
        self.assertNotIn("--nolockcheck", command)

    def test_cli_emits_parseable_json_for_failure(self) -> None:
        result = subprocess.run(
            [str(PYTHON), str(RUNNER_CLI), "pdf", str(self.root / "missing.docx"), str(self.root / "out.pdf")],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        payload = json.loads(result.stdout)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"], "input_not_found")

    def test_cli_emits_utf8_json_when_console_encoding_is_gbk(self) -> None:
        environment = os.environ.copy()
        environment["PYTHONUTF8"] = "0"
        environment["PYTHONIOENCODING"] = "gbk"
        missing = self.root / "missing-a\u032b.docx"
        result = subprocess.run(
            [str(PYTHON), str(RUNNER_CLI), "pdf", str(missing), str(self.root / "out.pdf")],
            capture_output=True,
            env=environment,
            timeout=10,
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout.count(b"\n"), 1)
        payload = json.loads(result.stdout.decode("utf-8"))
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"], "input_not_found")
        self.assertIn("\u032b", payload["message"])

    def test_child_capture_decodes_utf8_and_native_windows_codepage(self) -> None:
        capture = self.root / "stdout.txt"
        capture.write_bytes("中文结果".encode("utf-8"))
        self.assertEqual(_read_capture(capture), "中文结果")
        capture.write_bytes("中文结果".encode("mbcs", errors="replace"))
        self.assertEqual(_read_capture(capture), "中文结果".encode("mbcs", errors="replace").decode("mbcs"))

    def test_nonzero_child_exit_keeps_command_and_diagnostics(self) -> None:
        output = self.root / "output.pdf"
        state_root = self.root / "runner-state"
        with (
            patch("libreoffice_runner.win32_sync.default_state_root", return_value=state_root),
            patch("libreoffice_runner.core.default_state_root", return_value=state_root),
        ):
            report = run(RunRequest("pdf", self.source, output, soffice=PYTHON, queue_timeout=2, run_timeout=5))
        self.assertFalse(report.ok)
        self.assertEqual(report.error, "nonzero_exit")
        self.assertEqual(report.root_pid is not None, True)
        self.assertTrue(report.command)
        self.assertTrue(report.stderr or report.stdout)
        self.assertTrue(report.diagnostics)
        self.assertTrue(Path(str(report.diagnostics)).is_file())

    def test_capacity_denied_saves_diagnostics_without_task_or_launch(self) -> None:
        request = RunRequest("pdf", self.source, self.root / "out.pdf", soffice=PYTHON,
                             work_root=self.root / "work", diagnostics_root=self.root / "诊断")
        with (
            patch("libreoffice_runner.core.CapacitySlots", side_effect=PermissionError("shared slots denied")),
            patch("libreoffice_runner.core._run_owned") as launch,
        ):
            report = run(request)
        self.assertEqual(report.error, "capacity_acquire_failed")
        launch.assert_not_called()
        self.assertFalse(request.work_root.exists())
        saved = json.loads(Path(report.diagnostics).read_text(encoding="utf-8"))
        self.assertEqual(saved["error"], "capacity_acquire_failed")

    def test_work_directory_failure_does_not_launch_and_keeps_primary_error(self) -> None:
        blocked = self.root / "not-directory"
        blocked.write_text("file", encoding="utf-8")
        with (
            patch("libreoffice_runner.core.CapacitySlots.acquire", return_value=_Lease()),
            patch("libreoffice_runner.core.launch_suspended_in_job") as launch,
        ):
            report = run(RunRequest("pdf", self.source, self.root / "out.pdf", soffice=PYTHON,
                                    work_root=blocked, diagnostics_root=blocked))
        self.assertEqual(report.error, "job_setup_failed")
        self.assertIn("not-directory", report.message)
        self.assertTrue(report.diagnostics_error)
        self.assertIsNone(report.diagnostics)
        launch.assert_not_called()

    def test_deep_work_root_fails_before_launch_with_actionable_diagnostics(self) -> None:
        with (
            patch("libreoffice_runner.core.CapacitySlots.acquire", return_value=_Lease()),
            patch("libreoffice_runner.core.launch_suspended_in_job") as launch,
        ):
            report = run(RunRequest("pdf", self.source, self.root / "out.pdf", soffice=PYTHON,
                                    work_root=self.root / ("long" * 30), diagnostics_root=self.root / "diag"))
        self.assertEqual(report.error, "work_root_too_long")
        self.assertIn("--work-root", report.message)
        self.assertTrue(Path(report.diagnostics).is_file())
        launch.assert_not_called()

    def test_custom_root_profile_and_temp_are_owned_and_cleanup_preserves_parent(self) -> None:
        work = self.root / "中文 工作"
        work.mkdir()
        sentinel = work / "keep.txt"
        sentinel.write_text("keep", encoding="utf-8")
        with patch("libreoffice_runner.core.CapacitySlots.acquire", return_value=_Lease()):
            report = run(RunRequest("pdf", self.source, self.root / "out.pdf", soffice=PYTHON,
                                    work_root=work, diagnostics_root=self.root / "diagnostics"))
        self.assertEqual(report.error, "nonzero_exit")
        profile = next(item for item in report.command if item.startswith("-env:UserInstallation="))
        self.assertTrue(profile.startswith("-env:UserInstallation=" + work.as_uri()))
        self.assertEqual(list(work.iterdir()), [sentinel])
        self.assertTrue(Path(report.diagnostics).is_file())

    def test_owner_or_diagnostics_write_failure_does_not_mask_child_failure(self) -> None:
        from libreoffice_runner import core
        original = core._write_json
        def write(path: Path, value: object) -> None:
            if isinstance(value, dict) and (value.get("state") == "failed" or "ok" in value):
                raise PermissionError("diagnostic denied")
            original(path, value)
        with (
            patch("libreoffice_runner.core.CapacitySlots.acquire", return_value=_Lease()),
            patch("libreoffice_runner.core._write_json", side_effect=write),
        ):
            report = run(RunRequest("pdf", self.source, self.root / "out.pdf", soffice=PYTHON,
                                    work_root=self.root / "work", diagnostics_root=self.root / "diag"))
        self.assertEqual(report.error, "nonzero_exit")
        self.assertTrue(report.command)
        self.assertTrue(report.stderr)
        self.assertTrue(report.diagnostics_error)
        self.assertTrue(report.cleanup_error)
        self.assertEqual(list((self.root / "work").iterdir()), [])

    def test_distinct_work_roots_share_capacity_and_do_not_launch_when_full(self) -> None:
        from libreoffice_runner.win32_sync import CapacitySlots
        shared = self.root / "state"
        with patch("libreoffice_runner.win32_sync.default_state_root", return_value=shared):
            first = CapacitySlots().acquire(1)
            second = CapacitySlots().acquire(1)
            try:
                with patch("libreoffice_runner.core._run_owned") as launch:
                    reports = [run(RunRequest("pdf", self.source, self.root / f"out{i}.pdf", soffice=PYTHON,
                                              queue_timeout=0.05, work_root=self.root / f"work{i}",
                                              diagnostics_root=self.root / "diag")) for i in range(2)]
                self.assertEqual([item.error for item in reports], ["queue_timeout", "queue_timeout"])
                launch.assert_not_called()
            finally:
                first.release()
                second.release()

    def test_cleanup_cli_passes_explicit_work_root_and_compatibility_defaults(self) -> None:
        work = self.root / "work"
        with patch("libreoffice_runner.core.cleanup_abandoned", return_value={"ok": True}) as cleanup, \
             patch("libreoffice_runner.core._emit_json"):
            self.assertEqual(main(["cleanup", "--work-root", str(work)]), 0)
        self.assertEqual(cleanup.call_args.kwargs["temp_root"], work)
        request = RunRequest("pdf", self.source, self.root / "out.pdf")
        self.assertIsNone(request.work_root)
        self.assertIsNone(request.diagnostics_root)
        with self.assertRaises(FileNotFoundError):
            convert("pdf", self.root / "missing.docx", self.root / "out.pdf")
