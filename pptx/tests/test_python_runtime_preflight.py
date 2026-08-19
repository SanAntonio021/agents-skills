from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


MODULE = Path(__file__).parents[1] / "scripts" / "python_runtime_preflight.py"
spec = importlib.util.spec_from_file_location("pptx_python_runtime_preflight", MODULE)
preflight = importlib.util.module_from_spec(spec)
assert spec is not None and spec.loader is not None
sys.modules[spec.name] = preflight
spec.loader.exec_module(preflight)


def passing_probe(candidate: preflight.Candidate, **_kwargs: object) -> dict:
    dependencies = {
        distribution: {
            "module": module,
            "ok": True,
            "version": "test",
            "error": None,
        }
        for distribution, module in preflight.REQUIRED_IMPORTS
    }
    return {
        "source": candidate.source,
        "command": list(candidate.command),
        "label": candidate.label,
        "executable": candidate.command[0],
        "status": "PASS",
        "ok": True,
        "python_version": "3.13.0",
        "dependencies": dependencies,
        "returncode": 0,
        "error": None,
        "stderr": None,
    }


def failing_probe(candidate: preflight.Candidate, **_kwargs: object) -> dict:
    dependencies = {
        distribution: {
            "module": module,
            "ok": False,
            "version": None,
            "error": "ModuleNotFoundError: missing in test",
        }
        for distribution, module in preflight.REQUIRED_IMPORTS
    }
    return {
        "source": candidate.source,
        "command": list(candidate.command),
        "label": candidate.label,
        "executable": candidate.command[0],
        "status": "FAIL",
        "ok": False,
        "python_version": "3.13.0",
        "dependencies": dependencies,
        "returncode": 1,
        "error": "one or more required imports failed",
        "stderr": None,
    }


class PythonRuntimePreflightTests(unittest.TestCase):
    def test_current_interpreter_is_checked_first_and_selected_when_complete(self) -> None:
        candidates = preflight.build_candidates(
            current_executable="C:/bundled/python.exe",
            explicit_candidates=["C:/system/python.exe"],
            which=lambda name: {"py": "C:/Windows/py.exe", "python": "C:/path/python.exe"}.get(name),
            system_paths=[],
        )
        self.assertEqual(candidates[0].source, "current_interpreter")

        with patch.object(preflight, "probe_candidate", side_effect=passing_probe) as probe:
            report = preflight.run_preflight(
                current_executable="C:/bundled/python.exe",
                explicit_candidates=["C:/system/python.exe"],
                which=lambda _name: None,
                system_paths=[],
            )
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["selected_executable"], "C:/bundled/python.exe")
        self.assertEqual(probe.call_count, 1)
        self.assertEqual(report["selected_dependencies"]["python-pptx"]["ok"], True)

    def test_missing_current_runtime_falls_back_to_verified_candidate(self) -> None:
        def probe(candidate: preflight.Candidate, **kwargs: object) -> dict:
            return failing_probe(candidate, **kwargs) if candidate.source == "current_interpreter" else passing_probe(candidate, **kwargs)

        with patch.object(preflight, "probe_candidate", side_effect=probe) as mocked:
            report = preflight.run_preflight(
                current_executable="C:/bundled/python.exe",
                explicit_candidates=["C:/Python313/python.exe"],
                which=lambda _name: None,
                system_paths=[],
            )
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["selected_executable"], "C:/Python313/python.exe")
        self.assertEqual([call.args[0].source for call in mocked.call_args_list], [
            "current_interpreter",
            "explicit_candidate",
        ])

    def test_missing_current_runtime_can_fall_back_to_py_launcher(self) -> None:
        def probe(candidate: preflight.Candidate, **kwargs: object) -> dict:
            return failing_probe(candidate, **kwargs) if candidate.source == "current_interpreter" else passing_probe(candidate, **kwargs)

        with patch.object(preflight, "probe_candidate", side_effect=probe) as mocked:
            report = preflight.run_preflight(
                current_executable="C:/bundled/python.exe",
                which=lambda name: "C:/Windows/py.exe" if name == "py" else None,
                system_paths=[],
            )
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["selected_source"], "py_launcher")
        self.assertEqual([call.args[0].source for call in mocked.call_args_list], [
            "current_interpreter",
            "py_launcher",
        ])

    def test_no_candidate_returns_failure_and_never_installs(self) -> None:
        with patch.object(preflight, "probe_candidate", side_effect=failing_probe):
            report = preflight.run_preflight(
                current_executable="C:/bundled/python.exe",
                explicit_candidates=["C:/missing/python.exe"],
                which=lambda _name: None,
                system_paths=[],
            )
        self.assertEqual(report["status"], "FAIL")
        self.assertIsNone(report["selected_executable"])
        self.assertIn("no candidate interpreter", report["failure_reason"])
        source = MODULE.read_text(encoding="utf-8").lower()
        self.assertNotIn("pip install", source)

    def test_real_cli_reports_selected_path_and_dependency_results(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            report_path = Path(temp_dir) / "preflight.json"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(MODULE),
                    "--json-out",
                    str(report_path),
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            report = json.loads(completed.stdout)
            self.assertEqual(report["status"], "PASS")
            self.assertTrue(report["selected_executable"])
            self.assertEqual(
                set(report["selected_dependencies"]),
                {"defusedxml", "lxml", "python-pptx"},
            )
            self.assertEqual(json.loads(report_path.read_text(encoding="utf-8")), report)

    def test_report_writer_rejects_runtime_directories_and_missing_parents(self) -> None:
        report = {"status": "PASS"}
        with tempfile.TemporaryDirectory() as temp_dir:
            parent = Path(temp_dir)
            with self.assertRaises(FileNotFoundError):
                preflight._write_json(parent / "missing" / "report.json", report)
            with self.assertRaises(ValueError):
                preflight._write_json(parent / ".codex" / "report.json", report)

    def test_skill_documents_preflight_and_acceptance_boundaries(self) -> None:
        skill_text = (MODULE.parents[1] / "SKILL.md").read_text(encoding="utf-8")
        for label in (
            "STATIC_PASS",
            "LO_RENDER_PASS",
            "NATIVE_OPEN_PASS",
            "NATIVE_RENDER_PASS",
        ):
            self.assertIn(label, skill_text)
        self.assertIn("python_runtime_preflight.py", skill_text)
        self.assertIn("OfficeCLI", skill_text)
        self.assertIn("POWERPNT.EXE", skill_text)
        self.assertIn("UNVERIFIED", skill_text)


if __name__ == "__main__":
    unittest.main()
