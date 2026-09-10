"""Offline regression coverage for explicitly launched, task-owned PowerPoint."""

from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from test_office_native_gate import FakeComRuntime, FakePowerPoint, FakePresentation, native_gate as gate


class DisconnectedError(RuntimeError):
    hresult = -2147417848


def disconnected_failure() -> Exception:
    underlying = DisconnectedError("RPC_E_DISCONNECTED")
    wrapped = RuntimeError("intermediate COM wrapper")
    wrapped.__cause__ = underlying
    failure = gate.OwnershipFailure("collection unavailable")
    failure.__cause__ = wrapped
    return failure


class DirectPowerPointTests(unittest.TestCase):
    def test_unique_original_process_is_required(self):
        child = Mock(pid=123)
        child.poll.return_value = None
        for output, accepted in (
            (b'"POWERPNT.EXE","123","Console","1","100 K"', True),
            (b'"POWERPNT.EXE","124","Console","1","100 K"', False),
            (b'"POWERPNT.EXE","123"\n"POWERPNT.EXE","124"', False),
            (b'INFO: No tasks are running', False),
        ):
            with self.subTest(output=output), patch.object(gate.subprocess, "run", return_value=Mock(returncode=0, stdout=output)):
                if accepted:
                    gate._require_unique_powerpoint_process(child)
                else:
                    with self.assertRaises(gate.OwnershipFailure):
                        gate._require_unique_powerpoint_process(child)

    def test_exited_child_or_failed_enumeration_cannot_bind(self):
        for exit_code, returncode in ((0, 0), (None, 1)):
            child = Mock(pid=123)
            child.poll.return_value = exit_code
            with patch.object(gate.subprocess, "run", return_value=Mock(returncode=returncode, stdout=b'"POWERPNT.EXE","123"')):
                with self.assertRaises(gate.OwnershipFailure):
                    gate._require_unique_powerpoint_process(child)

    def owner(self, *, exit_code=0, identity=True, completed=True, process=True):
        child = Mock()
        child.wait.return_value = exit_code
        app = FakePowerPoint()
        owner = gate.OwnedApplication(
            app,
            "Presentations",
            exclusive_at_start=True,
            process=child if process else None,
            identity_verified=identity,
            operation_completed=completed,
        )
        return owner, child, app

    def test_completed_bound_process_exits_cleanly_after_disconnect(self):
        owner, child, app = self.owner()
        with patch.object(gate, "_collection_count", side_effect=disconnected_failure()):
            gate.quit_owned_application(owner)
        child.wait.assert_called_once_with(timeout=3)
        self.assertEqual(owner.metadata["cleanup"], "self_exited")
        self.assertFalse(owner.created_by_task)
        self.assertFalse(owner.quit_performed)
        self.assertEqual(app.quit_calls, 0)

    def test_alive_process_after_disconnect_is_not_success(self):
        owner, child, app = self.owner()
        child.wait.side_effect = subprocess.TimeoutExpired("POWERPNT.EXE", 3)
        with patch.object(gate, "_collection_count", side_effect=disconnected_failure()):
            with self.assertRaises(gate.OwnershipFailure):
                gate.quit_owned_application(owner)
        self.assertNotEqual(owner.metadata.get("cleanup"), "self_exited")
        self.assertTrue(owner.created_by_task)
        self.assertEqual(app.quit_calls, 0)

    def test_abnormal_exit_after_disconnect_is_not_success(self):
        for code in (1, -1, 3221225477):
            with self.subTest(exit_code=code):
                owner, child, app = self.owner(exit_code=code)
                with patch.object(gate, "_collection_count", side_effect=disconnected_failure()):
                    with self.assertRaises(gate.OwnershipFailure):
                        gate.quit_owned_application(owner)
                self.assertNotEqual(owner.metadata.get("cleanup"), "self_exited")
                self.assertEqual(app.quit_calls, 0)

    def test_unknown_exit_state_is_not_success(self):
        owner, child, app = self.owner()
        child.wait.side_effect = OSError("process handle unavailable")
        with patch.object(gate, "_collection_count", side_effect=disconnected_failure()):
            with self.assertRaises(gate.OwnershipFailure):
                gate.quit_owned_application(owner)
        self.assertNotEqual(owner.metadata.get("cleanup"), "self_exited")
        self.assertEqual(app.quit_calls, 0)

    def test_unbound_or_incomplete_operation_cannot_use_exit_exception(self):
        for kwargs in ({"identity": False}, {"completed": False}, {"process": False}):
            with self.subTest(kwargs=kwargs):
                owner, child, app = self.owner(**kwargs)
                with patch.object(gate, "_collection_count", side_effect=disconnected_failure()):
                    with self.assertRaises(gate.OwnershipFailure):
                        gate.quit_owned_application(owner)
                child.wait.assert_not_called()
                self.assertEqual(app.quit_calls, 0)

    def test_unowned_or_initially_nonexclusive_instance_is_never_quit(self):
        for field in ("created_by_task", "exclusive_at_start"):
            with self.subTest(field=field):
                owner, child, app = self.owner()
                setattr(owner, field, False)
                with self.assertRaises(gate.OwnershipFailure):
                    gate.quit_owned_application(owner)
                child.wait.assert_not_called()
                self.assertEqual(app.quit_calls, 0)

    def test_other_com_failure_does_not_use_process_exit_exception(self):
        owner, child, app = self.owner()
        failure = gate.OwnershipFailure("permission denied")
        failure.__cause__ = OSError("unrelated failure")
        with patch.object(gate, "_collection_count", side_effect=failure):
            with self.assertRaises(gate.OwnershipFailure):
                gate.quit_owned_application(owner)
        child.wait.assert_not_called()
        self.assertEqual(app.quit_calls, 0)

    def test_empty_connected_instance_uses_normal_quit(self):
        owner, child, app = self.owner()
        gate.quit_owned_application(owner)
        self.assertEqual(app.quit_calls, 1)
        self.assertTrue(owner.quit_performed)
        child.wait.assert_not_called()

    def test_document_remaining_refuses_quit(self):
        owner, child, app = self.owner()
        app.Presentations.items.append(object())
        with self.assertRaises(gate.OwnershipFailure):
            gate.quit_owned_application(owner)
        self.assertEqual(app.quit_calls, 0)
        child.wait.assert_not_called()

    def test_cleanup_failure_still_uninitializes_com(self):
        app = FakePowerPoint()
        app.Quit = Mock(side_effect=RuntimeError("Quit failed"))
        runtime = FakeComRuntime()
        with self.assertRaises(gate.OwnershipFailure):
            with gate.owned_application(
                gate.FORMAT_SPECS["pptx"],
                dispatch_ex=lambda _: app,
                com_runtime=runtime,
            ):
                pass
        self.assertEqual(runtime.initialize_calls, 1)
        self.assertEqual(runtime.uninitialize_calls, 1)

    def test_explicit_executable_uses_launcher_and_keeps_bound_process(self):
        app = FakePowerPoint()
        app.Path = "C:/verified/Microsoft Office"
        app.Version = "16.0"
        child = Mock()
        runtime = FakeComRuntime()
        dispatch = Mock(side_effect=AssertionError("default activation forbidden"))
        exe = Path("C:/verified/Microsoft Office/POWERPNT.EXE")
        with patch.object(gate, "launch_microsoft_powerpoint", return_value=(app, child)) as launch:
            with gate.owned_application(
                gate.FORMAT_SPECS["pptx"],
                dispatch_ex=dispatch,
                com_runtime=runtime,
                powerpoint_executable=exe,
            ) as (actual, owner):
                self.assertIs(actual, app)
                self.assertIs(owner.process, child)
                self.assertTrue(owner.identity_verified)
                self.assertFalse(owner.operation_completed)
            launch.assert_called_once_with(exe)
        dispatch.assert_not_called()
        self.assertEqual(app.quit_calls, 1)
        self.assertEqual(runtime.uninitialize_calls, 1)

    def test_default_powerpoint_activation_does_not_use_direct_launcher(self):
        app = FakePowerPoint()
        runtime = FakeComRuntime()
        with patch.object(gate, "launch_microsoft_powerpoint") as launch:
            with gate.owned_application(
                gate.FORMAT_SPECS["pptx"],
                dispatch_ex=lambda _: app,
                com_runtime=runtime,
            ) as (_, owner):
                self.assertIsNone(owner.process)
                self.assertFalse(owner.identity_verified)
            launch.assert_not_called()

    def test_explicit_executable_is_rejected_for_word_and_excel_before_activation(self):
        for format_name in ("docx", "xlsx"):
            with self.subTest(format=format_name), tempfile.TemporaryDirectory() as directory:
                source = Path(directory) / f"sample.{format_name}"
                source.write_bytes(b"unchanged original")
                probe = Mock(side_effect=AssertionError("preflight must reject before process probe"))
                runtime = FakeComRuntime()
                with patch.object(gate, "launch_microsoft_powerpoint") as launch:
                    result = gate.check_file(
                        source, format_name, allow_office_com=True,
                        process_probe=probe, com_runtime=runtime,
                        powerpoint_executable=Path("C:/verified/POWERPNT.EXE"),
                    )
                self.assertFalse(result["ok"])
                self.assertEqual(result["status"], "UNVERIFIED")
                self.assertEqual(result["phase"], "preflight")
                self.assertIn("PPTX-only", result["error"])
                self.assertEqual(result["source_sha256_before"], result["source_sha256_after"])
                self.assertEqual(runtime.initialize_calls, 0)
                probe.assert_not_called()
                launch.assert_not_called()

    def test_explicit_executable_and_dispatch_injection_are_mutually_exclusive(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "sample.pptx"
            source.write_bytes(b"unchanged original")
            probe = Mock(side_effect=AssertionError("preflight must reject before process probe"))
            dispatch = Mock(side_effect=AssertionError("must not dispatch"))
            runtime = FakeComRuntime()
            with patch.object(gate, "launch_microsoft_powerpoint") as launch:
                result = gate.check_file(
                    source, "pptx", allow_office_com=True,
                    process_probe=probe, dispatch_ex=dispatch, com_runtime=runtime,
                    powerpoint_executable=Path("C:/verified/POWERPNT.EXE"),
                )
            self.assertFalse(result["ok"])
            self.assertEqual(result["status"], "UNVERIFIED")
            self.assertEqual(result["phase"], "preflight")
            self.assertIn("cannot be combined", result["error"])
            self.assertEqual(result["source_sha256_before"], result["source_sha256_after"])
            self.assertEqual(runtime.initialize_calls, 0)
            probe.assert_not_called()
            dispatch.assert_not_called()
            launch.assert_not_called()

    def test_check_file_preserves_render_evidence_when_cleanup_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "sample.pptx"
            source.write_bytes(b"unchanged original")
            app = FakePowerPoint(slide_count=2)
            app.Quit = Mock(side_effect=RuntimeError("Quit failed"))
            runtime = FakeComRuntime()
            result = gate.check_file(
                source, "pptx", allow_office_com=True, require_render=True,
                process_probe=lambda _: False, dispatch_ex=lambda _: app,
                com_runtime=runtime,
            )
            self.assertFalse(result["ok"])
            self.assertEqual(result["status"], "UNVERIFIED")
            self.assertEqual(result["phase"], "cleanup")
            self.assertTrue(result["details"]["native_open"])
            self.assertEqual(result["details"]["native_render"]["files"], 2)
            self.assertEqual(result["source_sha256_before"], result["source_sha256_after"])
            self.assertEqual(source.read_bytes(), b"unchanged original")
            self.assertEqual(runtime.uninitialize_calls, 1)

    def test_check_file_only_marks_completed_after_successful_open_render_and_close(self):
        for options, status in (
            ({}, "PASS"),
            ({"open_error": OSError("open failed")}, "FAIL_OPEN"),
            ({"export_error": OSError("export failed")}, "FAIL_RENDER"),
        ):
            with self.subTest(options=options), tempfile.TemporaryDirectory() as directory:
                source = Path(directory) / "sample.pptx"
                source.write_bytes(b"unchanged original")
                app = FakePowerPoint(**options)
                owners = []
                original_quit = gate.quit_owned_application

                def capture(owner):
                    owners.append(owner.operation_completed)
                    original_quit(owner)

                with patch.object(gate, "quit_owned_application", side_effect=capture):
                    result = gate.check_file(
                        source, "pptx", allow_office_com=True, require_render=True,
                        process_probe=lambda _: False, dispatch_ex=lambda _: app,
                        com_runtime=FakeComRuntime(),
                    )
                self.assertEqual(result["status"], status)
                self.assertEqual(owners, [status == "PASS"])

    def test_failed_document_close_cannot_mark_operation_completed(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "sample.pptx"
            source.write_bytes(b"unchanged original")
            app = FakePowerPoint()
            completed = []
            original_quit = gate.quit_owned_application

            def capture(owner):
                completed.append(owner.operation_completed)
                original_quit(owner)

            with patch.object(FakePresentation, "Close", side_effect=RuntimeError("Close failed")):
                with patch.object(gate, "quit_owned_application", side_effect=capture):
                    result = gate.check_file(
                        source, "pptx", allow_office_com=True, require_render=True,
                        process_probe=lambda _: False, dispatch_ex=lambda _: app,
                        com_runtime=FakeComRuntime(),
                    )
            self.assertEqual(result["status"], "UNVERIFIED")
            self.assertEqual(result["phase"], "cleanup")
            self.assertEqual(completed, [False])
            self.assertEqual(app.quit_calls, 0)


if __name__ == "__main__":
    unittest.main()
