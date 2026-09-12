"""Configuration and output tests without Office, environment writes or sessions."""
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import runtime_config as config


class RuntimeConfigTests(unittest.TestCase):
    def test_project_relative_paths_env_priority_and_no_parent_search(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {}, clear=True):
            root = Path(directory)
            (root / "项目").mkdir()
            first, second = root / "工具一.exe", root / "工具二.exe"
            first.touch()
            second.touch()
            config.atomic_write_json(root / "lab-report.local.json", {"soffice": first.name, "work_root": "过程文件"})
            found = config.load_config(discovery_dir=root)
            self.assertEqual(found["values"]["soffice"], str(first))
            self.assertEqual(found["sources"]["soffice"], "project config")
            self.assertFalse((root / "过程文件").exists())
            with patch.dict(os.environ, {"LAB_REPORT_SOFFICE": str(second)}):
                found = config.load_config(discovery_dir=root)
                self.assertEqual(found["values"]["soffice"], str(second))
                self.assertEqual(found["persistence"]["soffice"]["project"], str(first))
            self.assertIsNone(config.load_config(discovery_dir=root / "项目")["path"])

    def test_invalid_explicit_config_and_override_do_not_fall_back(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {}, clear=True):
            root = Path(directory)
            with self.assertRaises(config.ConfigError):
                config.load_config(root / "missing.json")
            executable = root / "tool.exe"
            executable.touch()
            config.atomic_write_json(root / "lab-report.local.json", {"soffice": str(executable)})
            with patch.dict(os.environ, {"LAB_REPORT_SOFFICE": str(root / "missing.exe")}):
                with self.assertRaises(config.ConfigError):
                    config.load_config(discovery_dir=root)
            for bad in ([], {"unknown": "x"}, {"soffice": 5}, {"soffice": ""}, {"work_root": str(executable)}):
                config.atomic_write_json(root / "lab-report.local.json", bad)
                with self.assertRaises(config.ConfigError):
                    config.load_config(discovery_dir=root)

    def test_registry_denied_distinct_from_absent_and_session(self):
        registry = types.SimpleNamespace(HKEY_CURRENT_USER=0, OpenKey=lambda *a: (_ for _ in ()).throw(PermissionError("denied")))
        with patch.dict(sys.modules, {"winreg": registry}):
            status = config.user_environment("LAB_REPORT_SOFFICE")
        self.assertEqual(status["user_status"], "unavailable")
        self.assertIn("denied", status["user_error"])

    def test_emit_json_uses_utf8_bytes_in_gbk_stream(self):
        raw = io.BytesIO()
        stream = io.TextIOWrapper(raw, encoding="gbk")
        config.emit_json({"路径": "中文与🙂"}, stream)
        self.assertEqual(json.loads(raw.getvalue().decode("utf-8")), {"路径": "中文与🙂"})
        stream.detach()
        text = io.StringIO()
        config.emit_json({"中文": True}, text)
        self.assertEqual(json.loads(text.getvalue()), {"中文": True})

    def test_atomic_replace_and_serialization_failure_preserve_previous(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "状态.json"
            config.atomic_write_json(path, {"old": 1})
            original = path.read_bytes()
            with patch.object(config.os, "replace", side_effect=PermissionError("denied")):
                with self.assertRaises(PermissionError):
                    config.atomic_write_json(path, {"new": 2})
            self.assertEqual(path.read_bytes(), original)
            with self.assertRaises(TypeError):
                config.atomic_write_json(path, {"bad": object()})
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(list(Path(directory).iterdir()), [path])
            config.atomic_write_json(path, {"new": "中文"})
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {"new": "中文"})

    def test_fsync_failure_leaves_no_first_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            with patch.object(config.os, "fsync", side_effect=OSError("disk failed")):
                with self.assertRaises(OSError):
                    config.atomic_write_json(path, {"test": True})
            self.assertFalse(path.exists())

    def test_dependency_cli_unicode_error_is_valid_utf8_under_gbk(self):
        script = Path(__file__).resolve().parents[1] / "scripts" / "check_dependencies.py"
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run([sys.executable, str(script), "--config", str(Path(directory) / "中文🙂缺失.json")],
                                    capture_output=True, env={**os.environ, "PYTHONIOENCODING": "gbk"})
        self.assertEqual(result.returncode, 1)
        payload = json.loads(result.stdout.decode("utf-8"))
        self.assertIn("中文🙂", payload["error"])
        self.assertEqual(result.stderr, b"")


if __name__ == "__main__":
    unittest.main()
