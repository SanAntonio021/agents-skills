"""Preflight tests use mocks only; no Office or real sessions are accessed."""

import contextlib
import importlib.util
import io
import json
import tempfile
from pathlib import Path
import unittest
from unittest.mock import Mock, patch


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_dependencies.py"
SPEC = importlib.util.spec_from_file_location("check_dependencies", SCRIPT)
deps = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(deps)


class DependencyTests(unittest.TestCase):
    def simulated_environment(self, *, exists=True):
        stack = contextlib.ExitStack()
        stack.enter_context(patch.dict(deps.os.environ, {}, clear=True))
        stack.enter_context(patch.object(deps.platform, "system", return_value="Windows"))
        stack.enter_context(patch.object(deps.sys, "version_info", (3, 10, 0)))
        stack.enter_context(patch.object(deps.importlib, "import_module", return_value=Mock()))
        stack.enter_context(patch.object(deps.shutil, "which", side_effect=lambda name: "/tools/" + name))
        stack.enter_context(patch.object(deps.Path, "is_file", return_value=exists))
        return stack

    def test_complete_environment_is_ok(self):
        with self.simulated_environment():
            result = deps.check_dependencies()
        self.assertTrue(result["ok"])
        self.assertEqual(result["missing"], [])
        self.assertIn("not end-to-end", result["notes"][0])

    def test_missing_tools_are_named_and_fail(self):
        with self.simulated_environment(exists=False):
            result = deps.check_dependencies()
        self.assertFalse(result["ok"])
        self.assertEqual(set(result["missing"]), {"libreoffice_runner", "pdftoppm", "libreoffice"})

    def test_explicit_paths_override_discovery(self):
        overrides = {
            "LAB_REPORT_LO_RUNNER": "C:/custom/runner.py",
            "LAB_REPORT_PDFTOPPM": "C:/custom/pdftoppm.exe",
            "LAB_REPORT_SOFFICE": "C:/custom/soffice.exe",
        }
        with self.simulated_environment(), patch.dict(deps.os.environ, overrides):
            with patch.object(deps.shutil, "which") as which:
                result = deps.check_dependencies()
                which.assert_not_called()
        for name, variable in (("libreoffice_runner", "LAB_REPORT_LO_RUNNER"),
                               ("pdftoppm", "LAB_REPORT_PDFTOPPM"),
                               ("libreoffice", "LAB_REPORT_SOFFICE")):
            self.assertEqual(result["required"][name]["source"], variable)
            self.assertEqual(result["required"][name]["path"], str(Path(overrides[variable])))

    def test_invalid_override_does_not_fall_back(self):
        with patch.dict(deps.os.environ, {"LAB_REPORT_SOFFICE": "C:/missing.exe"}, clear=True):
            with patch.object(deps.Path, "is_file", return_value=False), patch.object(deps.shutil, "which") as which:
                status = deps.executable_status("LAB_REPORT_SOFFICE", ("soffice",))
                which.assert_not_called()
        self.assertFalse(status["present"])
        self.assertEqual(status["source"], "LAB_REPORT_SOFFICE")

    def test_program_files_discovery(self):
        expected = Path("C:/Programs") / "LibreOffice/program/soffice.exe"
        with self.simulated_environment(), patch.dict(deps.os.environ, {"ProgramFiles": "C:/Programs"}):
            with patch.object(deps.shutil, "which", return_value=None), patch.object(deps.Path, "is_file", new=lambda path: path == expected):
                result = deps.check_dependencies()
        self.assertEqual(result["required"]["libreoffice"]["path"], str(expected))
        self.assertTrue(result["required"]["libreoffice"]["present"])

    def test_old_python_and_wrong_platform_fail(self):
        with self.simulated_environment(), patch.object(deps.sys, "version_info", (3, 9, 9)), patch.object(deps.platform, "system", return_value="Linux"):
            result = deps.check_dependencies()
        self.assertEqual(set(result["missing"]), {"python", "windows"})

    def test_import_error_and_missing_timezone_are_reported(self):
        with patch.object(deps.importlib, "import_module", side_effect=ImportError("missing module")):
            self.assertFalse(deps.module_status("pptx")["present"])
        zoneinfo = Mock()
        zoneinfo.ZoneInfo.side_effect = KeyError("Asia/Shanghai")
        with patch.object(deps.importlib, "import_module", return_value=zoneinfo):
            status = deps.timezone_status()
        self.assertFalse(status["present"])
        self.assertIn("tzdata", status["hint"])

    def test_main_emits_json_and_returns_failure(self):
        result = {"ok": False, "required": {}, "missing": ["python"]}
        output = io.StringIO()
        with patch.object(deps, "check_dependencies", return_value=result), contextlib.redirect_stdout(output):
            code = deps.main([])
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(output.getvalue()), result)

    def test_project_config_reports_effective_and_persistent_separately(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "lab-report.local.json"
            path.write_text(json.dumps({"soffice": "中文程序.exe", "work_root": "过程文件"}), encoding="utf-8")
            with self.simulated_environment():
                with patch.dict(deps.load_config.__globals__, {"user_environment": lambda name: {"user": None, "user_status": "unavailable", "user_error": "denied"}}):
                    result = deps.check_dependencies(path)
        self.assertTrue(result["ok"])
        config = result["configuration"]
        self.assertEqual(config["persistence"]["soffice"]["source"], "project config")
        self.assertEqual(config["persistence"]["soffice"]["effective"], str(Path(directory) / "中文程序.exe"))
        self.assertEqual(config["persistence"]["soffice"]["user_status"], "unavailable")
        self.assertIsNone(config["persistence"]["soffice"]["session"])
        self.assertEqual(config["persistence"]["work_root"]["source"], "project config")
        self.assertTrue(result["interpreter"])


if __name__ == "__main__":
    unittest.main()
