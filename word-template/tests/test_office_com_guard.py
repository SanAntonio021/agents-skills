from __future__ import annotations

import argparse
import re
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = SKILL_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from office_com_guard import (  # noqa: E402
    OfficeComPermissionError,
    OfficeComSafetyError,
    OwnedWordApplication,
    add_office_com_argument,
    quit_owned_word_application,
    word_application,
    word_process_present,
)
import word_constants  # noqa: E402


class FakeComRuntime:
    def __init__(self) -> None:
        self.initialize_calls = 0
        self.uninitialize_calls = 0

    def CoInitialize(self) -> None:
        self.initialize_calls += 1

    def CoUninitialize(self) -> None:
        self.uninitialize_calls += 1


class FakeDocuments:
    def __init__(self, count: int) -> None:
        self.Count = count


class FakeWordApplication:
    def __init__(self, document_count: int = 0) -> None:
        self.Documents = FakeDocuments(document_count)
        self.Visible = True
        self.DisplayAlerts = 1
        self.ScreenUpdating = True
        self.quit_calls: list[tuple[object, ...]] = []
        self.quit_error: Exception | None = None

    def Quit(self, *args: object) -> None:
        self.quit_calls.append(args)
        if self.quit_error is not None:
            raise self.quit_error


class GuardTests(unittest.TestCase):
    def test_no_permission_rejects_before_probe_or_com(self) -> None:
        calls = {"probe": 0, "dispatch": 0}
        runtime = FakeComRuntime()

        def probe() -> bool:
            calls["probe"] += 1
            return False

        def dispatch(_: str) -> FakeWordApplication:
            calls["dispatch"] += 1
            return FakeWordApplication()

        with self.assertRaises(OfficeComPermissionError):
            with word_application(
                allow_office_com=False,
                process_probe=probe,
                com_runtime=runtime,
                dispatch_ex=dispatch,
            ):
                self.fail("The context must not be entered")

        self.assertEqual(calls, {"probe": 0, "dispatch": 0})
        self.assertEqual(runtime.initialize_calls, 0)

    def test_existing_word_rejects_before_com(self) -> None:
        runtime = FakeComRuntime()
        dispatch_calls = 0

        def dispatch(_: str) -> FakeWordApplication:
            nonlocal dispatch_calls
            dispatch_calls += 1
            return FakeWordApplication()

        with self.assertRaisesRegex(OfficeComSafetyError, "already running"):
            with word_application(
                allow_office_com=True,
                process_probe=lambda: True,
                com_runtime=runtime,
                dispatch_ex=dispatch,
            ):
                self.fail("The context must not be entered")

        self.assertEqual(dispatch_calls, 0)
        self.assertEqual(runtime.initialize_calls, 0)

    def test_process_probe_failure_rejects_before_com(self) -> None:
        runtime = FakeComRuntime()

        def failed_probe() -> bool:
            raise OSError("probe failed")

        with self.assertRaisesRegex(OfficeComSafetyError, "Unable to verify"):
            with word_application(
                allow_office_com=True,
                process_probe=failed_probe,
                com_runtime=runtime,
                dispatch_ex=lambda _: self.fail("Dispatch must not run"),
            ):
                self.fail("The context must not be entered")

        self.assertEqual(runtime.initialize_calls, 0)

    def test_dispatch_ex_owned_empty_instance_quits_once(self) -> None:
        runtime = FakeComRuntime()
        application = FakeWordApplication()
        dispatch_names: list[str] = []

        def dispatch(name: str) -> FakeWordApplication:
            dispatch_names.append(name)
            return application

        with word_application(
            allow_office_com=True,
            process_probe=lambda: False,
            com_runtime=runtime,
            dispatch_ex=dispatch,
        ) as active_application:
            self.assertIs(active_application, application)
            self.assertFalse(active_application.Visible)

        self.assertEqual(dispatch_names, ["Word.Application"])
        self.assertEqual(application.quit_calls, [(False,)])
        self.assertEqual(runtime.initialize_calls, 1)
        self.assertEqual(runtime.uninitialize_calls, 1)

    def test_initial_documents_prevent_entry_and_quit(self) -> None:
        runtime = FakeComRuntime()
        application = FakeWordApplication(document_count=1)

        with self.assertRaisesRegex(OfficeComSafetyError, "exclusive ownership"):
            with word_application(
                allow_office_com=True,
                process_probe=lambda: False,
                com_runtime=runtime,
                dispatch_ex=lambda _: application,
            ):
                self.fail("The context must not be entered")

        self.assertEqual(application.quit_calls, [])
        self.assertEqual(runtime.uninitialize_calls, 1)

    def test_remaining_documents_prevent_quit(self) -> None:
        runtime = FakeComRuntime()
        application = FakeWordApplication()

        with self.assertRaisesRegex(OfficeComSafetyError, "still has open documents"):
            with word_application(
                allow_office_com=True,
                process_probe=lambda: False,
                com_runtime=runtime,
                dispatch_ex=lambda _: application,
            ) as active_application:
                active_application.Documents.Count = 1

        self.assertEqual(application.quit_calls, [])
        self.assertEqual(runtime.uninitialize_calls, 1)

    def test_cleanup_error_does_not_replace_primary_error(self) -> None:
        runtime = FakeComRuntime()
        application = FakeWordApplication()

        with self.assertRaisesRegex(RuntimeError, "primary failure") as captured:
            with word_application(
                allow_office_com=True,
                process_probe=lambda: False,
                com_runtime=runtime,
                dispatch_ex=lambda _: application,
            ) as active_application:
                active_application.Documents.Count = 1
                raise RuntimeError("primary failure")

        notes = getattr(captured.exception, "__notes__", [])
        self.assertTrue(any("cleanup also failed" in note for note in notes))
        self.assertEqual(application.quit_calls, [])

    def test_dispatch_failure_still_uninitializes_com(self) -> None:
        runtime = FakeComRuntime()

        def failed_dispatch(_: str) -> FakeWordApplication:
            raise RuntimeError("fake dispatch failure")

        with self.assertRaisesRegex(RuntimeError, "fake dispatch failure"):
            with word_application(
                allow_office_com=True,
                process_probe=lambda: False,
                com_runtime=runtime,
                dispatch_ex=failed_dispatch,
            ):
                self.fail("The context must not be entered")

        self.assertEqual(runtime.initialize_calls, 1)
        self.assertEqual(runtime.uninitialize_calls, 1)

    def test_quit_failure_does_not_replace_primary_error(self) -> None:
        runtime = FakeComRuntime()
        application = FakeWordApplication()
        application.quit_error = RuntimeError("fake quit failure")

        with self.assertRaisesRegex(RuntimeError, "primary failure") as captured:
            with word_application(
                allow_office_com=True,
                process_probe=lambda: False,
                com_runtime=runtime,
                dispatch_ex=lambda _: application,
            ):
                raise RuntimeError("primary failure")

        notes = getattr(captured.exception, "__notes__", [])
        self.assertTrue(any("Application.Quit() failed" in note for note in notes))
        self.assertEqual(application.quit_calls, [(False,)])
        self.assertTrue(application.Visible)

    def test_unowned_application_cannot_be_quit(self) -> None:
        application = FakeWordApplication()
        owner = OwnedWordApplication(
            application=application,
            created_by_this_task=False,
            exclusive_at_start=True,
        )

        with self.assertRaisesRegex(OfficeComSafetyError, "ownership is not proven"):
            quit_owned_word_application(owner)
        self.assertEqual(application.quit_calls, [])

    def test_cli_flag_is_opt_in(self) -> None:
        parser = argparse.ArgumentParser()
        add_office_com_argument(parser)
        self.assertFalse(parser.parse_args([]).allow_office_com)
        self.assertTrue(parser.parse_args(["--allow-office-com"]).allow_office_com)

    @patch("office_com_guard.subprocess.run")
    def test_process_probe_parses_tasklist_without_com(self, run_mock) -> None:
        run_mock.return_value = SimpleNamespace(
            returncode=0,
            stdout='"WINWORD.EXE","1234","Console","1","50,000 K"\n',
        )
        self.assertTrue(word_process_present())

        run_mock.return_value = SimpleNamespace(
            returncode=0,
            stdout="INFO: No tasks are running which match the specified criteria.\n",
        )
        self.assertFalse(word_process_present())


class EntrypointContractTests(unittest.TestCase):
    PYTHON_ENTRYPOINTS = (
        "word_template_formatter.py",
        "build_master_template.py",
        "validate_master_default.py",
        "install_normal_template.py",
    )

    def test_unsafe_python_com_apis_are_absent(self) -> None:
        for name in self.PYTHON_ENTRYPOINTS:
            source = (SCRIPTS_DIR / name).read_text(encoding="utf-8")
            self.assertNotIn("EnsureDispatch(", source, name)
            self.assertNotIn("GetActiveObject(", source, name)
            self.assertNotIn(".Quit(", source, name)

    def test_each_python_entrypoint_exposes_permission_flag(self) -> None:
        for name in self.PYTHON_ENTRYPOINTS:
            source = (SCRIPTS_DIR / name).read_text(encoding="utf-8")
            self.assertIn("add_office_com_argument", source, name)
            self.assertIn("allow_office_com", source, name)

    def test_word_constants_do_not_depend_on_gen_py_cache(self) -> None:
        expected = {
            "wdAlignParagraphLeft": 0,
            "wdAlignParagraphCenter": 1,
            "wdAlignParagraphJustify": 3,
            "wdLineSpaceExactly": 4,
            "wdPageBreak": 7,
            "wdFormatXMLDocument": 12,
            "wdFormatXMLTemplateMacroEnabled": 15,
            "wdListNoNumbering": 0,
            "wdStyleNormal": -1,
            "wdStyleHeading1": -2,
            "wdStyleHeading2": -3,
            "wdStyleHeading3": -4,
            "wdStyleTOC1": -20,
            "wdStyleTOC2": -21,
            "wdStyleTOC3": -22,
            "wdStyleCaption": -35,
            "wdStyleTitle": -63,
            "wdStyleBodyText": -67,
        }
        for name, value in expected.items():
            self.assertEqual(getattr(word_constants, name), value, name)

        for entrypoint in self.PYTHON_ENTRYPOINTS:
            source = (SCRIPTS_DIR / entrypoint).read_text(encoding="utf-8")
            self.assertNotIn("win32com.client.constants", source, entrypoint)

    def test_validator_forwards_permission_to_formatter(self) -> None:
        source = (SCRIPTS_DIR / "validate_master_default.py").read_text(
            encoding="utf-8"
        )
        self.assertRegex(
            source,
            re.compile(r"command\.append\(\"--allow-office-com\"\)"),
        )

    def test_powershell_entrypoint_has_no_direct_quit(self) -> None:
        source = (SCRIPTS_DIR / "export_markdown_to_word.ps1").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("$word.Quit", source)
        self.assertNotRegex(source, r"New-Object\s+-ComObject")
        self.assertIn("apply-native-template", source)
        self.assertIn("-AllowOfficeCom", source)


if __name__ == "__main__":
    unittest.main()
