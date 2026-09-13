"""Shared process safety checks; every external Office dependency is injected."""
from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch


SKILLS_ROOT = Path(__file__).resolve().parents[2]
GATES = {}
for skill in ("xlsx", "pdf"):
    spec = importlib.util.spec_from_file_location(
        f"shared_native_safety_{skill}", SKILLS_ROOT / skill / "scripts" / "office_native_gate.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    GATES[skill] = module


class FakeExcel:
    def __init__(self, *, quit_fails=False):
        self.Workbooks = SimpleNamespace(Count=0, Open=self.open)
        self.workbook = SimpleNamespace(Worksheets=SimpleNamespace(Count=1), Close=self.close)
        self.open_calls = []
        self.close_calls = []
        self.quit_calls = 0
        self.quit_fails = quit_fails

    def open(self, path, update_links, read_only):
        self.open_calls.append((Path(path), update_links, read_only))
        self.Workbooks.Count = 1
        return self.workbook

    def close(self, save_changes):
        self.close_calls.append(save_changes)
        self.Workbooks.Count = 0

    def Quit(self):
        self.quit_calls += 1
        if self.quit_fails:
            raise RuntimeError("injected Quit failure")


class SharedNativeSafetyTests(unittest.TestCase):
    def exercise(self, gate, timeline, verify, *, quit_fails=False, cleanup_fails=False):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source.xlsx"
            original = b"injected native gate input"
            source.write_bytes(original)
            workspace = root / "owned-workspace"
            workspace.mkdir()
            excel = FakeExcel(quit_fails=quit_fails)
            dispatch = Mock(return_value=excel)
            runtime = SimpleNamespace(CoInitialize=Mock(), CoUninitialize=Mock())
            probe = Mock(side_effect=timeline)
            real_rmtree = gate.shutil.rmtree

            def remove(path, *args, **kwargs):
                if cleanup_fails and Path(path) == workspace:
                    raise OSError("injected workspace cleanup failure")
                return real_rmtree(path, *args, **kwargs)

            with (
                patch.object(gate.tempfile, "mkdtemp", return_value=str(workspace)),
                patch.object(gate.shutil, "rmtree", side_effect=remove) as cleanup,
                patch.object(gate.subprocess, "run", side_effect=AssertionError("real process launch prohibited")),
                patch.object(gate, "default_dispatch_ex", side_effect=AssertionError("real COM prohibited")),
                patch.object(gate, "default_com_runtime", side_effect=AssertionError("real COM runtime prohibited")),
            ):
                result = gate.check_file(
                    source, "xlsx", allow_office_com=True, process_ids=probe,
                    dispatch_ex=dispatch, com_runtime=runtime,
                    pid_observation_timeout_seconds=0, process_exit_timeout_seconds=0,
                )
                self.assertEqual(source.read_bytes(), original)
                self.assertEqual(result["source_sha256_before"], result["source_sha256_after"])
                verify(result, excel, dispatch, runtime, workspace, cleanup)

    def test_preexisting_or_unknown_process_never_activates(self):
        for skill, gate in GATES.items():
            for timeline in ([ [99] ], [RuntimeError("probe failed")], [[], [99]], [[], RuntimeError("probe failed")]):
                with self.subTest(skill=skill, timeline=timeline):
                    def verify(result, excel, dispatch, runtime, workspace, cleanup):
                        self.assertFalse(result["ok"])
                        self.assertIn(result["status"], {"UNSAFE_PROCESS", "UNVERIFIED"})
                        dispatch.assert_not_called()
                        self.assertEqual(excel.quit_calls, 0)
                        self.assertEqual(excel.open_calls, [])
                    self.exercise(gate, timeline, verify)

    def test_missing_new_pid_never_opens_or_quits_and_retains_workspace(self):
        for skill, gate in GATES.items():
            with self.subTest(skill=skill):
                def verify(result, excel, dispatch, runtime, workspace, cleanup):
                    self.assertEqual(result["status"], "UNVERIFIED")
                    self.assertEqual(result["phase"], "cleanup")
                    self.assertEqual(excel.quit_calls, 0)
                    self.assertEqual(excel.open_calls, [])
                    self.assertTrue(workspace.exists())
                    self.assertEqual(result["details"]["retained_workspace"], str(workspace))
                    cleanup.assert_not_called()
                    runtime.CoUninitialize.assert_called_once_with()
                self.exercise(gate, [[], [], []], verify)

    def test_exit_uncertainty_never_passes_or_deletes_workspace(self):
        for skill, gate in GATES.items():
            for final_probe, quit_fails in (([42], False), (RuntimeError("exit probe failed"), False), ([], True)):
                with self.subTest(skill=skill, final_probe=final_probe, quit_fails=quit_fails):
                    def verify(result, excel, dispatch, runtime, workspace, cleanup):
                        self.assertFalse(result["ok"])
                        self.assertEqual(result["status"], "UNVERIFIED")
                        self.assertEqual(result["phase"], "cleanup")
                        self.assertTrue(workspace.exists())
                        cleanup.assert_not_called()
                        self.assertEqual(excel.quit_calls, 1)
                        runtime.CoUninitialize.assert_called_once_with()
                    self.exercise(gate, [[], [], [42], final_probe], verify, quit_fails=quit_fails)

    def test_workspace_cleanup_failure_downgrades_pass(self):
        for skill, gate in GATES.items():
            with self.subTest(skill=skill):
                def verify(result, excel, dispatch, runtime, workspace, cleanup):
                    self.assertFalse(result["ok"])
                    self.assertEqual(result["status"], "UNVERIFIED")
                    self.assertEqual(result["phase"], "cleanup")
                    self.assertEqual(result["details"]["prior_result"]["status"], "PASS")
                    self.assertEqual(result["details"]["cleanup_uncertainties"][0]["kind"], "temporary_workspace")
                    self.assertTrue(workspace.exists())
                self.exercise(gate, [[], [], [42], []], verify, cleanup_fails=True)

    def test_owned_read_only_copy_passes_after_proven_exit(self):
        for skill, gate in GATES.items():
            with self.subTest(skill=skill):
                def verify(result, excel, dispatch, runtime, workspace, cleanup):
                    self.assertTrue(result["ok"])
                    self.assertEqual(result["status"], "PASS")
                    self.assertEqual(result["ownership"]["cleanup"]["status"], "CLEAN")
                    self.assertEqual(excel.open_calls, [(workspace / "source.xlsx", 0, True)])
                    self.assertEqual(excel.close_calls, [False])
                    self.assertEqual(excel.quit_calls, 1)
                    self.assertFalse(workspace.exists())
                    runtime.CoInitialize.assert_called_once_with()
                    runtime.CoUninitialize.assert_called_once_with()
                    cleanup.assert_called_once_with(workspace)
                self.exercise(gate, [[], [], [42], []], verify)


if __name__ == "__main__":
    unittest.main()
