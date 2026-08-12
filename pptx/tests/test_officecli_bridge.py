import hashlib
import importlib.util
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


MODULE = Path(__file__).parents[1] / "scripts" / "officecli_bridge.py"
spec = importlib.util.spec_from_file_location("officecli_bridge", MODULE)
bridge = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(bridge)


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

    def test_screenshot_defaults_to_html_without_office_auto_mode(self):
        clean_args, is_native = bridge.resolve_render_mode("screenshot", ["screenshot"])
        self.assertEqual(clean_args, ["screenshot", "--render", "html"])
        self.assertFalse(is_native)

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
            output = Path(temp_dir) / "render.png"
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

    def test_screenshot_requires_new_output_path(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "sample.pptx"
            source.write_bytes(b"officecli-test")
            with self.assertRaisesRegex(bridge.BridgeError, "requires --out"):
                bridge.run_view(Path("officecli.exe"), source, ["screenshot"])

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

    def test_runtime_copies_are_identical(self):
        canonical = MODULE.read_bytes()
        skills_root = MODULE.parents[2]
        for skill in ("docx", "xlsx", "pdf"):
            candidate = skills_root / skill / "scripts" / "officecli_bridge.py"
            self.assertEqual(candidate.read_bytes(), canonical, candidate)


if __name__ == "__main__":
    unittest.main()
