import hashlib
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch


MODULE = Path(__file__).parents[1] / "scripts" / "officecli_bridge.py"
spec = importlib.util.spec_from_file_location("officecli_bridge", MODULE)
bridge = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = bridge
spec.loader.exec_module(bridge)

REPAIR_MODULE = Path(__file__).parents[1] / "scripts" / "repair_officecli.py"
repair_spec = importlib.util.spec_from_file_location("repair_officecli", REPAIR_MODULE)
repair = importlib.util.module_from_spec(repair_spec)
assert repair_spec.loader is not None
sys.modules[repair_spec.name] = repair
repair_spec.loader.exec_module(repair)


class OfficeCliBridgeTests(unittest.TestCase):
    def test_sha256_is_stable(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "sample.pptx"
            source.write_bytes(b"officecli-test")
            expected = hashlib.sha256(b"officecli-test").hexdigest().upper()
            self.assertEqual(bridge.sha256(source), expected)

    def test_native_requires_explicit_allow_flag(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "sample.pptx"
            source.write_bytes(b"officecli-test")
            with patch.object(bridge, "run_process") as run_process:
                with self.assertRaisesRegex(bridge.BridgeError, "--allow-native"):
                    bridge.run_view(Path("officecli.exe"), source, ["screenshot", "--render", "native"])
            run_process.assert_not_called()

    def test_existing_output_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "render.png"
            output.write_bytes(b"existing")
            with self.assertRaisesRegex(bridge.BridgeError, "overwrite"):
                bridge.ensure_new_output(str(output))

    def test_screenshot_requires_explicit_render_mode(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "sample.pptx"
            source.write_bytes(b"officecli-test")
            with patch.object(bridge, "run_process") as run_process:
                with self.assertRaisesRegex(bridge.BridgeError, "explicit render mode"):
                    bridge.run_view(Path("officecli.exe"), source, ["screenshot"])
            run_process.assert_not_called()

    def test_html_screenshot_requires_non_fidelity_preview_flag(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "sample.pptx"
            source.write_bytes(b"officecli-test")
            with patch.object(bridge, "run_process") as run_process:
                with self.assertRaisesRegex(bridge.BridgeError, "non-fidelity preview"):
                    bridge.run_view(
                        Path("officecli.exe"),
                        source,
                        ["screenshot", "--render", "html"],
                    )
            run_process.assert_not_called()

    def test_html_screenshot_is_explicit_diagnostic_preview(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "sample.pptx"
            output = Path(temp_dir) / "render.png"
            source.write_bytes(b"officecli-test")

            def fake_run(command):
                if command[1] == "close":
                    return subprocess.CompletedProcess(command, 0, "", "")
                output_index = command.index("--out") + 1
                Path(command[output_index]).write_bytes(b"non-fidelity-preview")
                return subprocess.CompletedProcess(command, 0, "", "")

            stderr = io.StringIO()
            with patch.object(bridge, "run_process", side_effect=fake_run) as run_process:
                with redirect_stderr(stderr):
                    self.assertEqual(
                        bridge.run_view(
                            Path("officecli.exe"),
                            source,
                            [
                                "screenshot",
                                "--render",
                                "html",
                                "--non-fidelity-preview",
                                "--out",
                                str(output),
                            ],
                        ),
                        0,
                    )

            self.assertEqual(output.read_bytes(), b"non-fidelity-preview")
            self.assertIn("non-fidelity diagnostic preview", stderr.getvalue())
            view_command = next(
                call.args[0] for call in run_process.call_args_list if call.args[0][2] == "view"
            )
            self.assertIn("--render", view_command)
            self.assertIn("html", view_command)
            self.assertNotIn("--non-fidelity-preview", view_command)

    def test_html_and_svg_require_non_fidelity_preview_flag(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "sample.pptx"
            source.write_bytes(b"officecli-test")
            for mode in ("html", "svg"):
                with self.subTest(mode=mode):
                    with patch.object(bridge, "run_process") as run_process:
                        with self.assertRaisesRegex(bridge.BridgeError, "non-fidelity preview"):
                            bridge.run_view(Path("officecli.exe"), source, [mode])
                    run_process.assert_not_called()

    def test_pdf_export_is_rejected_before_officecli_call(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "sample.pptx"
            source.write_bytes(b"officecli-test")
            with patch.object(bridge, "run_process") as run_process:
                with self.assertRaisesRegex(bridge.BridgeError, "exporter plugin"):
                    bridge.run_view(Path("officecli.exe"), source, ["pdf", "--out", str(Path(temp_dir) / "out.pdf")])
            run_process.assert_not_called()

    def test_xlsx_validation_is_rejected_before_officecli_call(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "sample.xlsx"
            source.write_bytes(b"officecli-test")
            with patch.object(bridge, "run_process") as run_process:
                with self.assertRaisesRegex(bridge.BridgeError, "verify_xlsx.py"):
                    bridge.run_read(Path("officecli.exe"), "validate", source, [])
            run_process.assert_not_called()

    def test_auto_render_is_prohibited(self):
        with self.assertRaisesRegex(bridge.BridgeError, "auto is prohibited"):
            bridge.resolve_render_mode("screenshot", ["screenshot", "--render", "auto"])

    def test_json_escaped_paths_are_rewritten(self):
        result = subprocess.CompletedProcess(
            ["officecli"],
            0,
            '{"data":"C:\\\\temp\\\\internal.png"}',
            "",
        )
        with patch("sys.stdout") as stdout:
            bridge.emit_result(result, {r"C:\temp\internal.png": r"D:\out\final.png"})
            emitted = "".join(call.args[0] for call in stdout.write.call_args_list)
        self.assertIn(r"D:\\out\\final.png", emitted)

    def test_nested_json_paths_are_rewritten(self):
        result = subprocess.CompletedProcess(
            ["officecli"],
            0,
            '{"data":{"path":"C:\\\\temp\\\\internal.png"}}',
            "",
        )
        with patch("sys.stdout") as stdout:
            bridge.emit_result(result, {r"C:\temp\internal.png": r"D:\out\final.png"})
            emitted = "".join(call.args[0] for call in stdout.write.call_args_list)
        self.assertIn(r"D:\\out\\final.png", emitted)

    def test_native_is_rejected_when_powerpoint_is_running(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "sample.pptx"
            output_parent = Path(temp_dir) / "native-output"
            output = output_parent / "render.png"
            source.write_bytes(b"officecli-test")
            with patch.object(bridge, "process_exists", return_value=True):
                with patch.object(bridge, "run_process") as run_process:
                    with self.assertRaisesRegex(bridge.BridgeError, "POWERPNT.EXE"):
                        bridge.run_view(
                            Path("officecli.exe"),
                            source,
                            ["screenshot", "--render", "native", "--allow-native", "--out", str(output)],
                        )
            run_process.assert_not_called()
            self.assertFalse(output_parent.exists())

    def test_native_xlsx_render_is_rejected_before_officecli_call(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "sample.xlsx"
            output = Path(temp_dir) / "render.png"
            source.write_bytes(b"officecli-test")
            with patch.object(bridge, "run_process") as run_process:
                with self.assertRaisesRegex(bridge.BridgeError, "unsupported for this extension"):
                    bridge.run_view(
                        Path("officecli.exe"),
                        source,
                        ["screenshot", "--render", "native", "--allow-native", "--out", str(output)],
                    )
            run_process.assert_not_called()

    def test_native_officecli_failure_is_diagnostic_not_app_availability_evidence(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "sample.pptx"
            output = Path(temp_dir) / "render.png"
            source.write_bytes(b"officecli-test")

            def fake_run(command):
                if command[1] == "close":
                    return subprocess.CompletedProcess(command, 0, "", "")
                return subprocess.CompletedProcess(
                    command,
                    23,
                    "",
                    "--render native requires Windows with Microsoft PowerPoint installed\n",
                )

            stderr = io.StringIO()
            with patch.object(bridge, "process_exists", return_value=False):
                with patch.object(bridge, "run_process", side_effect=fake_run):
                    with redirect_stderr(stderr):
                        exit_code = bridge.run_view(
                            Path("officecli.exe"),
                            source,
                            ["screenshot", "--render", "native", "--allow-native", "--out", str(output)],
                        )

            self.assertEqual(exit_code, 23)
            diagnostic = json.loads(stderr.getvalue().splitlines()[-1])
            self.assertEqual(diagnostic["status"], "officecli_native_diagnostic_failed")
            self.assertEqual(diagnostic["exit_code"], 23)
            self.assertEqual(diagnostic["input_format"], "pptx")
            self.assertEqual(diagnostic["office_application_state"], "not_inferred")
            self.assertIn("Microsoft PowerPoint installed", diagnostic["stderr"])
            self.assertNotEqual(diagnostic["status"], "APP_UNAVAILABLE")
            self.assertFalse(output.exists())

    def test_screenshot_requires_new_output_path(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "sample.pptx"
            source.write_bytes(b"officecli-test")
            with self.assertRaisesRegex(bridge.BridgeError, "requires --out"):
                bridge.run_view(
                    Path("officecli.exe"),
                    source,
                    ["screenshot", "--render", "html", "--non-fidelity-preview"],
                )

    def test_mutation_copies_source_to_new_output(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "source.pptx"
            output = Path(temp_dir) / "draft.pptx"
            source.write_bytes(b"source-bytes")

            def fake_run(command):
                if command[1] == "close":
                    return subprocess.CompletedProcess(command, 0, "", "")
                Path(command[3]).write_bytes(b"changed-copy")
                return subprocess.CompletedProcess(command, 0, "{}", "")

            with patch.object(bridge, "run_process", side_effect=fake_run):
                self.assertEqual(bridge.run_mutation(Path("officecli.exe"), source, str(output), "batch", []), 0)
            self.assertEqual(source.read_bytes(), b"source-bytes")
            self.assertEqual(output.read_bytes(), b"changed-copy")

    def test_default_missing_reports_repair_without_execution(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            missing = Path(temp_dir) / "officecli.exe"
            with patch.dict(os.environ, {}, clear=True):
                with patch.object(bridge, "DEFAULT_EXE", missing):
                    with patch.object(bridge, "run_process") as run_process:
                        with self.assertRaisesRegex(bridge.BridgeError, "default path") as context:
                            bridge.resolve_exe()
            self.assertIn("repair_officecli.py", str(context.exception))
            run_process.assert_not_called()

    def test_hash_mismatch_stops_before_version_check(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            candidate = Path(temp_dir) / "officecli.exe"
            candidate.write_bytes(b"unexpected-binary")
            with patch.dict(os.environ, {}, clear=True):
                with patch.object(bridge, "DEFAULT_EXE", candidate):
                    with patch.object(bridge, "run_process") as run_process:
                        with self.assertRaisesRegex(bridge.BridgeError, "hash mismatch"):
                            bridge.resolve_exe()
            run_process.assert_not_called()

    def test_version_check_follows_matching_hash(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            candidate = Path(temp_dir) / "officecli.exe"
            candidate.write_bytes(b"verified-binary")
            expected_hash = bridge.sha256(candidate)
            version_result = subprocess.CompletedProcess([str(candidate), "--version"], 0, "1.0.144\n", "")
            with patch.dict(os.environ, {}, clear=True):
                with patch.object(bridge, "DEFAULT_EXE", candidate):
                    with patch.object(bridge, "OFFICECLI_SHA256", expected_hash):
                        with patch.object(bridge, "run_process", return_value=version_result) as run_process:
                            resolved = bridge.resolve_exe()
            self.assertEqual(resolved.path, candidate)
            self.assertEqual(resolved.sha256, expected_hash)
            self.assertFalse(resolved.is_override)
            run_process.assert_called_once_with([str(candidate), "--version"])

    def test_version_mismatch_is_rejected_after_hash_check(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            candidate = Path(temp_dir) / "officecli.exe"
            candidate.write_bytes(b"verified-binary")
            version_result = subprocess.CompletedProcess([str(candidate), "--version"], 0, "1.0.143\n", "")
            with patch.dict(os.environ, {}, clear=True):
                with patch.object(bridge, "DEFAULT_EXE", candidate):
                    with patch.object(bridge, "OFFICECLI_SHA256", bridge.sha256(candidate)):
                        with patch.object(bridge, "run_process", return_value=version_result) as run_process:
                            with self.assertRaisesRegex(bridge.BridgeError, "version mismatch"):
                                bridge.resolve_exe()
            run_process.assert_called_once_with([str(candidate), "--version"])

    def test_override_failure_never_falls_back_to_default(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            override = Path(temp_dir) / "missing-override.exe"
            with patch.dict(os.environ, {"OFFICECLI_EXE": str(override)}, clear=True):
                with patch.object(bridge, "run_process") as run_process:
                    with self.assertRaisesRegex(bridge.BridgeError, "override path") as context:
                        bridge.resolve_exe()
            self.assertIn("unset OFFICECLI_EXE", str(context.exception))
            run_process.assert_not_called()

    def test_valid_override_uses_same_integrity_checks(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            override = Path(temp_dir) / "override.exe"
            override.write_bytes(b"verified-override")
            result = subprocess.CompletedProcess([str(override), "--version"], 0, "1.0.144\n", "")
            with patch.dict(os.environ, {"OFFICECLI_EXE": str(override)}, clear=True):
                with patch.object(bridge, "OFFICECLI_SHA256", bridge.sha256(override)):
                    with patch.object(bridge, "run_process", return_value=result) as run_process:
                        resolved = bridge.resolve_exe()
            self.assertTrue(resolved.is_override)
            self.assertEqual(resolved.path, override)
            run_process.assert_called_once_with([str(override), "--version"])

    def test_status_uses_verified_result_without_restarting_officecli(self):
        resolved = bridge.ResolvedOfficeCli(
            Path("officecli.exe"), bridge.OFFICECLI_SHA256, bridge.OFFICECLI_VERSION, False
        )
        with patch.object(bridge, "run_process") as run_process:
            self.assertEqual(bridge.run_status(resolved), 0)
        run_process.assert_not_called()

    def test_repair_requires_explicit_flag(self):
        stderr = io.StringIO()
        with patch.object(repair, "repair") as repair_call:
            with redirect_stderr(stderr):
                self.assertEqual(repair.main([]), 2)
        repair_call.assert_not_called()
        self.assertIn("--repair", stderr.getvalue())

    def test_repair_valid_target_is_a_noop(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "officecli.exe"
            target.write_bytes(b"verified-asset")
            expected_hash = repair.sha256(target)
            with patch.object(repair, "EXPECTED_ASSET_SHA256", expected_hash):
                with patch.object(repair, "download") as download:
                    result = repair.repair(target)
            self.assertEqual(result["status"], "already_valid")
            self.assertEqual(target.read_bytes(), b"verified-asset")
            download.assert_not_called()

    def test_repair_download_failure_preserves_bad_target(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "officecli.exe"
            target.write_bytes(b"bad-target")
            with patch.object(repair, "download", side_effect=repair.RepairError("download failed")):
                with self.assertRaisesRegex(repair.RepairError, "download failed"):
                    repair.repair(target)
            self.assertEqual(target.read_bytes(), b"bad-target")

    def test_repair_invalid_sums_preserves_bad_target(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "officecli.exe"
            target.write_bytes(b"bad-target")

            def write_invalid_sums(_url, destination):
                destination.write_bytes(b"not a checksum file\n")

            with patch.object(repair, "download", side_effect=write_invalid_sums):
                with self.assertRaisesRegex(repair.RepairError, "SHA256SUMS hash mismatch"):
                    repair.repair(target)
            self.assertEqual(target.read_bytes(), b"bad-target")

    def test_repair_backs_up_bad_target_before_atomic_replacement(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "officecli.exe"
            target.write_bytes(b"bad-target")
            verified_asset = b"verified-asset"
            expected_asset_hash = hashlib.sha256(verified_asset).hexdigest().upper()
            sums_payload = f"{expected_asset_hash.lower()}  {repair.ASSET_NAME}\n".encode("ascii")
            expected_sums_hash = hashlib.sha256(sums_payload).hexdigest().upper()

            def fake_download(url, destination):
                destination.write_bytes(sums_payload if url == repair.SUMS_URL else verified_asset)

            with patch.object(repair, "EXPECTED_ASSET_SHA256", expected_asset_hash):
                with patch.object(repair, "EXPECTED_SUMS_SHA256", expected_sums_hash):
                    with patch.object(repair, "download", side_effect=fake_download):
                        result = repair.repair(target)
            self.assertEqual(result["status"], "repaired")
            self.assertEqual(target.read_bytes(), verified_asset)
            backup = Path(result["backup"])
            self.assertTrue(backup.is_file())
            self.assertEqual(backup.read_bytes(), b"bad-target")

    def test_repair_lock_times_out_without_touching_target(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "officecli.exe"
            target.write_bytes(b"bad-target")
            with patch.object(repair, "LOCK_TIMEOUT_SECONDS", 0):
                with patch.object(repair, "lock_file", side_effect=OSError("locked")):
                    with self.assertRaisesRegex(repair.RepairError, "already running"):
                        with repair.repair_lock(target):
                            pass
            self.assertEqual(target.read_bytes(), b"bad-target")

    def test_runtime_copies_are_identical(self):
        canonical = MODULE.read_bytes()
        skills_root = MODULE.parents[2]
        for skill in ("docx", "xlsx", "pdf"):
            candidate = skills_root / skill / "scripts" / "officecli_bridge.py"
            self.assertEqual(candidate.read_bytes(), canonical, candidate)

    def test_repair_runtime_copies_are_identical(self):
        canonical = REPAIR_MODULE.read_bytes()
        skills_root = MODULE.parents[2]
        for skill in ("docx", "xlsx", "pdf"):
            candidate = skills_root / skill / "scripts" / "repair_officecli.py"
            self.assertEqual(candidate.read_bytes(), canonical, candidate)

    def test_native_gate_runtime_copies_are_identical(self):
        canonical = (MODULE.parent / "office_native_gate.py").read_bytes()
        skills_root = MODULE.parents[2]
        for skill in ("docx", "xlsx", "pdf"):
            candidate = skills_root / skill / "scripts" / "office_native_gate.py"
            self.assertEqual(candidate.read_bytes(), canonical, candidate)


if __name__ == "__main__":
    unittest.main()
