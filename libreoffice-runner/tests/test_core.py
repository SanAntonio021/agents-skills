from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch

from _support import PYTHON, RUNNER_CLI, WindowsOnlyTestCase
from libreoffice_runner.core import RunRequest, _conversion_command, _prepare, run


class _Lease:
    def __enter__(self) -> "_Lease":
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        return None


class CoreTests(WindowsOnlyTestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(prefix="lo-runner-core-")
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
