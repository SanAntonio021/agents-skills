from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


MODULE = Path(__file__).parents[1] / "scripts" / "office_native_gate.py"
spec = importlib.util.spec_from_file_location("office_native_gate", MODULE)
native_gate = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = native_gate
spec.loader.exec_module(native_gate)


class FakeComRuntime:
    def __init__(self) -> None:
        self.initialize_calls = 0
        self.uninitialize_calls = 0

    def CoInitialize(self) -> None:
        self.initialize_calls += 1

    def CoUninitialize(self) -> None:
        self.uninitialize_calls += 1


class FakeCollection:
    def __init__(self) -> None:
        self.items: list[object] = []

    @property
    def Count(self) -> int:
        return len(self.items)


class FakeSlides:
    def __init__(self, presentation: "FakePresentation") -> None:
        self.presentation = presentation

    @property
    def Count(self) -> int:
        return len(self.presentation.slides)

    def __call__(self, index: int) -> "FakeSlide":
        return self.presentation.slides[index - 1]


class FakeSlide:
    def __init__(self, *, export_error: Exception | None = None) -> None:
        self.export_error = export_error

    def Export(self, path: str, _format: str, *_scale: int) -> None:
        if self.export_error is not None:
            raise self.export_error
        Path(path).write_bytes(b"PNG")


class FakePresentation:
    def __init__(self, app: "FakePowerPoint", *, slide_count: int = 2, export_error: Exception | None = None) -> None:
        self.app = app
        self.slides = [FakeSlide(export_error=export_error) for _ in range(slide_count)]
        self.Slides = FakeSlides(self)

    def Close(self) -> None:
        self.app.Presentations.items.remove(self)


class FakePresentations(FakeCollection):
    def __init__(self, app: "FakePowerPoint", **open_options: object) -> None:
        super().__init__()
        self.app = app
        self.open_options = open_options

    def Open(self, _path: str, *_args: object) -> FakePresentation:
        error = self.open_options.get("open_error")
        if error is not None:
            raise error
        presentation = FakePresentation(
            self.app,
            slide_count=int(self.open_options.get("slide_count", 2)),
            export_error=self.open_options.get("export_error"),
        )
        self.items.append(presentation)
        return presentation


class FakePowerPoint:
    def __init__(self, **open_options: object) -> None:
        self.Presentations = FakePresentations(self, **open_options)
        self.Visible = True
        self.DisplayAlerts = 1
        self.quit_calls = 0

    def Quit(self) -> None:
        self.quit_calls += 1


class FakeDocument:
    def __init__(self, app: "FakeWord", *, page_count: int = 2, export_error: Exception | None = None) -> None:
        self.app = app
        self.page_count = page_count
        self.export_error = export_error

    def Repaginate(self) -> None:
        return None

    def ComputeStatistics(self, _statistic: int) -> int:
        return self.page_count

    def ExportAsFixedFormat(self, path: str, _format: int) -> None:
        if self.export_error is not None:
            raise self.export_error
        Path(path).write_bytes(b"PDF")

    def Close(self, _save_changes: bool = False) -> None:
        self.app.Documents.items.remove(self)


class FakeDocuments(FakeCollection):
    def __init__(self, app: "FakeWord", **open_options: object) -> None:
        super().__init__()
        self.app = app
        self.open_options = open_options

    def Open(self, _path: str, *_args: object) -> FakeDocument:
        error = self.open_options.get("open_error")
        if error is not None:
            raise error
        document = FakeDocument(
            self.app,
            page_count=int(self.open_options.get("page_count", 2)),
            export_error=self.open_options.get("export_error"),
        )
        self.items.append(document)
        return document


class FakeWord:
    def __init__(self, **open_options: object) -> None:
        self.Documents = FakeDocuments(self, **open_options)
        self.Visible = True
        self.DisplayAlerts = 1
        self.ScreenUpdating = True
        self.quit_calls = 0

    def Quit(self) -> None:
        self.quit_calls += 1


class FakeWorksheets(FakeCollection):
    pass


class FakeWorkbook:
    def __init__(self, app: "FakeExcel", sheet_count: int = 2) -> None:
        self.app = app
        self.Worksheets = FakeWorksheets()
        self.Worksheets.items.extend(object() for _ in range(sheet_count))

    def Close(self, _save_changes: bool = False) -> None:
        self.app.Workbooks.items.remove(self)


class FakeWorkbooks(FakeCollection):
    def __init__(self, app: "FakeExcel", **open_options: object) -> None:
        super().__init__()
        self.app = app
        self.open_options = open_options

    def Open(self, _path: str, *_args: object) -> FakeWorkbook:
        error = self.open_options.get("open_error")
        if error is not None:
            raise error
        workbook = FakeWorkbook(self.app, int(self.open_options.get("sheet_count", 2)))
        self.items.append(workbook)
        return workbook


class FakeExcel:
    def __init__(self, **open_options: object) -> None:
        self.Workbooks = FakeWorkbooks(self, **open_options)
        self.Visible = True
        self.DisplayAlerts = 1
        self.quit_calls = 0

    def Quit(self) -> None:
        self.quit_calls += 1


def dispatch_for(application: object):
    def dispatch(progid: str) -> object:
        return application

    return dispatch


def no_process(_image_name: str) -> bool:
    return False


class ClassNotRegisteredError(RuntimeError):
    hresult = 0x80040154


class NativeGateTests(unittest.TestCase):
    def _source(self, directory: str, extension: str) -> Path:
        path = Path(directory) / f"source{extension}"
        path.write_bytes(b"valid-office-package")
        return path

    def _check(self, source: Path, format_name: str, application: object, **kwargs: object) -> dict:
        runtime = FakeComRuntime()
        return native_gate.check_file(
            source,
            format_name,
            allow_office_com=True,
            process_probe=no_process,
            dispatch_ex=dispatch_for(application),
            com_runtime=runtime,
            **kwargs,
        )

    def test_permission_is_required_before_process_probe_or_com(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = self._source(temp_dir, ".pptx")
            calls = {"probe": 0, "dispatch": 0}

            def probe(_image_name: str) -> bool:
                calls["probe"] += 1
                return False

            def dispatch(_progid: str) -> object:
                calls["dispatch"] += 1
                return FakePowerPoint()

            result = native_gate.check_file(
                source,
                "pptx",
                allow_office_com=False,
                process_probe=probe,
                dispatch_ex=dispatch,
            )
            self.assertEqual(result["status"], "UNVERIFIED")
            self.assertEqual(calls, {"probe": 0, "dispatch": 0})

    def test_existing_office_process_is_unsafe_and_never_dispatches(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = self._source(temp_dir, ".pptx")
            dispatch = unittest.mock.Mock()
            result = native_gate.check_file(
                source,
                "pptx",
                allow_office_com=True,
                process_probe=lambda _name: True,
                dispatch_ex=dispatch,
            )
            self.assertEqual(result["status"], "UNSAFE_PROCESS")
            dispatch.assert_not_called()

    def test_pptx_open_and_native_export_pass(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = self._source(temp_dir, ".pptx")
            app = FakePowerPoint(slide_count=2)
            result = self._check(source, "pptx", app, require_render=True)
            self.assertEqual(result["status"], "PASS")
            self.assertEqual(result["details"]["native_render"]["files"], 2)
            self.assertEqual(app.quit_calls, 1)
            self.assertEqual(source.read_bytes(), b"valid-office-package")

    def test_corrupt_pptx_is_fail_open_not_app_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = self._source(temp_dir, ".pptx")
            app = FakePowerPoint(open_error=OSError("0x80070570: file or directory is corrupted"))
            result = self._check(source, "pptx", app)
            self.assertEqual(result["status"], "FAIL_OPEN")
            self.assertEqual(result["phase"], "open")
            self.assertIn("0x80070570", result["error"])

    def test_docx_export_failure_is_fail_render(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = self._source(temp_dir, ".docx")
            app = FakeWord(export_error=OSError("Word export failed"))
            result = self._check(source, "docx", app, require_render=True)
            self.assertEqual(result["status"], "FAIL_RENDER")
            self.assertEqual(result["phase"], "office_export")
            self.assertIn("Word export failed", result["error"])

    def test_docx_native_pdf_and_rasterization_pass(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = self._source(temp_dir, ".docx")
            app = FakeWord(page_count=2)

            def fake_rasterizer(pdf: Path, output_dir: Path, expected: int) -> dict:
                self.assertTrue(pdf.is_file())
                for index in range(1, expected + 1):
                    (output_dir / f"page-stem-{index}.png").write_bytes(b"PNG")
                return {"rasterizer": "fake", "expected": expected, "files": expected}

            result = self._check(source, "docx", app, require_render=True, rasterizer=fake_rasterizer)
            self.assertEqual(result["status"], "PASS")
            self.assertEqual(result["details"]["rasterization"]["files"], 2)

    def test_xlsx_open_only_passes_and_does_not_render(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = self._source(temp_dir, ".xlsx")
            result = self._check(source, "xlsx", FakeExcel(sheet_count=3))
            self.assertEqual(result["status"], "PASS")
            self.assertEqual(result["details"]["worksheets"], 3)
            self.assertFalse(result["details"]["native_render"])

    def test_xlsx_render_request_is_rejected_before_dispatch(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = self._source(temp_dir, ".xlsx")
            dispatch = unittest.mock.Mock()
            result = native_gate.check_file(
                source,
                "xlsx",
                allow_office_com=True,
                process_probe=no_process,
                dispatch_ex=dispatch,
                require_render=True,
            )
            self.assertEqual(result["status"], "UNVERIFIED")
            self.assertEqual(result["phase"], "preflight")
            dispatch.assert_not_called()

    def test_class_not_registered_is_app_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = self._source(temp_dir, ".pptx")
            result = native_gate.check_file(
                source,
                "pptx",
                allow_office_com=True,
                process_probe=no_process,
                dispatch_ex=lambda _name: (_ for _ in ()).throw(ClassNotRegisteredError("class not registered")),
                com_runtime=FakeComRuntime(),
            )
            self.assertEqual(result["status"], "APP_UNAVAILABLE")
            self.assertEqual(result["phase"], "activate")

    def test_generic_activation_failure_is_unverified(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = self._source(temp_dir, ".pptx")
            result = native_gate.check_file(
                source,
                "pptx",
                allow_office_com=True,
                process_probe=no_process,
                dispatch_ex=lambda _name: (_ for _ in ()).throw(OSError("0x80070570")),
                com_runtime=FakeComRuntime(),
            )
            self.assertEqual(result["status"], "UNVERIFIED")
            self.assertNotEqual(result["status"], "APP_UNAVAILABLE")

    def test_source_change_downgrades_result_to_unverified(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = self._source(temp_dir, ".pptx")
            original_open = FakePresentations.Open

            def mutate_source(collection, path, *args):
                Path(source).write_bytes(b"changed-by-external-editor")
                return original_open(collection, path, *args)

            app = FakePowerPoint(slide_count=1)
            with patch.object(FakePresentations, "Open", mutate_source):
                result = self._check(source, "pptx", app)
            self.assertEqual(result["status"], "UNVERIFIED")
            self.assertEqual(result["phase"], "integrity")

    def test_existing_native_output_directory_is_not_reused(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = self._source(temp_dir, ".pptx")
            workspace = Path(temp_dir) / "existing-workspace"
            (workspace / "exports").mkdir(parents=True)
            with patch.object(native_gate.tempfile, "mkdtemp", return_value=str(workspace)):
                dispatch = unittest.mock.Mock()
                result = native_gate.check_file(
                    source,
                    "pptx",
                    allow_office_com=True,
                    process_probe=no_process,
                    dispatch_ex=dispatch,
                    com_runtime=FakeComRuntime(),
                )
            self.assertEqual(result["status"], "UNVERIFIED")
            self.assertIn("existing native output directory", result["error"])
            dispatch.assert_not_called()

    def test_unknown_instance_ownership_refuses_quit_and_is_unverified(self) -> None:
        class UninspectableApplication:
            Visible = True

            class Presentations:
                @property
                def Count(self):
                    raise RuntimeError("collection unavailable")

            def Quit(self):
                self.quit_calls = getattr(self, "quit_calls", 0) + 1

        app = UninspectableApplication()
        with tempfile.TemporaryDirectory() as temp_dir:
            source = self._source(temp_dir, ".pptx")
            runtime = FakeComRuntime()
            result = native_gate.check_file(
                source,
                "pptx",
                allow_office_com=True,
                process_probe=no_process,
                dispatch_ex=dispatch_for(app),
                com_runtime=runtime,
            )
            self.assertEqual(result["status"], "UNVERIFIED")
            self.assertEqual(runtime.uninitialize_calls, 1)
            self.assertEqual(getattr(app, "quit_calls", 0), 0)


@unittest.skipUnless(
    sys.platform == "win32" and os.environ.get("OFFICE_NATIVE_GATE_INTEGRATION") == "1",
    "set OFFICE_NATIVE_GATE_INTEGRATION=1 on Windows to opt into real Office COM checks",
)
class NativeGateIntegrationTests(unittest.TestCase):
    """Opt-in controls; skipped runs never report PASS."""

    def test_generated_controls_and_corrupt_files(self) -> None:
        from docx import Document
        from openpyxl import Workbook
        from pptx import Presentation

        with tempfile.TemporaryDirectory(prefix="office-native-integration-") as temp_dir:
            root = Path(temp_dir)
            pptx = root / "control.pptx"
            presentation = Presentation()
            presentation.slides.add_slide(presentation.slide_layouts[6])
            presentation.save(pptx)
            docx = root / "control.docx"
            document = Document()
            document.add_paragraph("native gate control")
            document.save(docx)
            xlsx = root / "control.xlsx"
            workbook = Workbook()
            workbook.active["A1"] = "native gate control"
            workbook.save(xlsx)

            for source, format_name, render in ((pptx, "pptx", True), (docx, "docx", True)):
                result = native_gate.check_file(source, format_name, allow_office_com=True, require_render=render)
                self.assertEqual(result["status"], "PASS", result)
            result = native_gate.check_file(xlsx, "xlsx", allow_office_com=True)
            self.assertEqual(result["status"], "PASS", result)

            for source, format_name in ((pptx, "pptx"), (docx, "docx"), (xlsx, "xlsx")):
                corrupt = root / f"corrupt-{format_name}{source.suffix}"
                corrupt.write_bytes(b"not an Office package")
                result = native_gate.check_file(corrupt, format_name, allow_office_com=True)
                self.assertEqual(result["status"], "FAIL_OPEN", result)
                self.assertNotEqual(result["status"], "APP_UNAVAILABLE")


if __name__ == "__main__":
    unittest.main()
