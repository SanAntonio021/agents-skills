"""Real DOCX adapter integration tests guarded by RUN_LIBREOFFICE_INTEGRATION."""

import hashlib
import json
import os
import shutil
import sys
import tempfile
import time
import unittest
import zipfile
from pathlib import Path


_SKILLS_ROOT = Path(__file__).resolve().parents[2]
_DOCX_SCRIPTS = _SKILLS_ROOT / "docx" / "scripts"
_RUNNER_SCRIPTS = _SKILLS_ROOT / "libreoffice-runner" / "scripts"
_BOOTSTRAP = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "LibreOffice" / "program" / "bootstrap.ini"
_DEFAULT_PROFILE = Path(os.environ["APPDATA"]) / "LibreOffice" / "4" / "user" / "registrymodifications.xcu"

for _path in (str(_DOCX_SCRIPTS), str(_RUNNER_SCRIPTS)):
    if _path not in sys.path:
        sys.path.insert(0, _path)


def _check_integration_deps() -> list[str]:
    missing = []
    for package, import_name in (
        ("psutil", "psutil"),
        ("python-docx", "docx"),
        ("Pillow", "PIL"),
        ("PyPDF2", "PyPDF2"),
    ):
        try:
            __import__(import_name)
        except ImportError:
            missing.append(package)
    return missing


def _lo_procs():
    import psutil

    processes = []
    for process in psutil.process_iter(["pid", "name"]):
        try:
            if "soffice" in (process.info["name"] or "").lower():
                processes.append(process)
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            continue
    return processes


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _file_state(path: Path) -> tuple[bool, str | None]:
    return (path.is_file(), _sha256_file(path) if path.is_file() else None)


def _task_roots() -> set[str]:
    return {
        str(path.resolve())
        for path in Path(tempfile.gettempdir()).glob("sanan-lo-*")
        if path.is_dir()
    }


def _make_docx_with_text_and_image(path: Path, text: str, tracked_fixture: bool = False) -> None:
    import docx
    from docx.shared import Inches
    from PIL import Image

    image_path = path.with_suffix(".png")
    Image.new("RGB", (32, 32), color=(180, 30, 30)).save(image_path)
    try:
        document = docx.Document()
        document.add_paragraph(text)
        document.add_picture(str(image_path), width=Inches(0.25))
        if tracked_fixture:
            document.add_paragraph("Inserted fixture text")
            document.add_paragraph("Deleted fixture text")
        document.save(str(path))
    finally:
        image_path.unlink(missing_ok=True)


def _inject_tracked_changes(docx_path: Path) -> None:
    inserted_run = b"<w:r><w:t>Inserted fixture text</w:t></w:r>"
    deleted_run = b"<w:r><w:t>Deleted fixture text</w:t></w:r>"
    inserted_change = (
        b'<w:ins w:id="1" w:author="Test" w:date="2024-01-01T00:00:00Z">'
        + inserted_run
        + b"</w:ins>"
    )
    deleted_change = (
        b'<w:del w:id="2" w:author="Test" w:date="2024-01-01T00:00:00Z">'
        b"<w:r><w:delText>Deleted fixture text</w:delText></w:r></w:del>"
    )

    source_copy = docx_path.with_suffix(".source.docx")
    shutil.copy2(docx_path, source_copy)
    try:
        with zipfile.ZipFile(source_copy, "r") as source_zip, zipfile.ZipFile(
            docx_path, "w", zipfile.ZIP_DEFLATED
        ) as output_zip:
            for item in source_zip.infolist():
                data = source_zip.read(item.filename)
                if item.filename == "word/document.xml":
                    if data.count(inserted_run) != 1 or data.count(deleted_run) != 1:
                        raise AssertionError("Tracked-change fixture runs were not unique")
                    data = data.replace(inserted_run, inserted_change)
                    data = data.replace(deleted_run, deleted_change)
                output_zip.writestr(item, data)
    finally:
        source_copy.unlink(missing_ok=True)


def _decode_failure(result) -> dict:
    payload = result.stderr
    if isinstance(payload, bytes):
        payload = payload.decode("utf-8")
    return json.loads(payload)


@unittest.skipUnless(
    os.environ.get("RUN_LIBREOFFICE_INTEGRATION") == "1",
    "Set RUN_LIBREOFFICE_INTEGRATION=1 to run",
)
class TestDocxIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        missing = _check_integration_deps()
        if missing:
            raise RuntimeError(f"Missing integration dependencies: {missing}")
        running = _lo_procs()
        if running:
            raise RuntimeError(
                "LibreOffice already running before DOCX integration tests: "
                + ", ".join(str(process.pid) for process in running)
            )
        cls.bootstrap_before = _file_state(_BOOTSTRAP)
        cls.default_profile_before = _file_state(_DEFAULT_PROFILE)
        cls.task_roots_before = _task_roots()

    @classmethod
    def tearDownClass(cls):
        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline:
            if not _lo_procs() and not (_task_roots() - cls.task_roots_before):
                break
            time.sleep(0.1)

        failures = []
        remaining = _lo_procs()
        if remaining:
            failures.append(
                "LibreOffice processes remain: "
                + ", ".join(str(process.pid) for process in remaining)
            )
        new_roots = _task_roots() - cls.task_roots_before
        if new_roots:
            failures.append(f"New sanan-lo task roots remain: {sorted(new_roots)}")
        if _file_state(_BOOTSTRAP) != cls.bootstrap_before:
            failures.append("bootstrap.ini changed during integration tests")
        if _file_state(_DEFAULT_PROFILE) != cls.default_profile_before:
            failures.append("Default LibreOffice profile changed during integration tests")
        if failures:
            raise AssertionError("; ".join(failures))

    def test_docx_to_pdf_valid(self):
        from PyPDF2 import PdfReader
        from office.soffice import run_soffice

        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "input.docx"
            output = Path(temp_dir) / "input.pdf"
            _make_docx_with_text_and_image(source, "Integration test content")

            result = run_soffice(
                [
                    "--headless",
                    "--convert-to",
                    "pdf:writer_pdf_Export",
                    "--outdir",
                    temp_dir,
                    str(source),
                ],
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(output.is_file())
            self.assertGreaterEqual(len(PdfReader(str(output)).pages), 1)

    def test_accept_changes_removes_insertions_and_deletions(self):
        import docx
        from accept_changes import accept_changes

        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "tracked.docx"
            output = Path(temp_dir) / "clean.docx"
            _make_docx_with_text_and_image(
                source, "Base text", tracked_fixture=True
            )
            _inject_tracked_changes(source)

            with zipfile.ZipFile(source) as package:
                source_xml = package.read("word/document.xml")
            self.assertIn(b"<w:ins", source_xml)
            self.assertIn(b"<w:del", source_xml)

            _, message = accept_changes(str(source), str(output))
            self.assertNotIn("Error", message, message)
            self.assertTrue(output.is_file())

            with zipfile.ZipFile(output) as package:
                output_xml = package.read("word/document.xml")
            self.assertNotIn(b"<w:ins", output_xml)
            self.assertNotIn(b"<w:del", output_xml)

            accepted_text = "\n".join(
                paragraph.text for paragraph in docx.Document(str(output)).paragraphs
            )
            self.assertIn("Inserted fixture text", accepted_text)
            self.assertNotIn("Deleted fixture text", accepted_text)

    def test_output_exists_not_overwritten(self):
        from office.soffice import run_soffice

        sentinel = b"SENTINEL_DO_NOT_OVERWRITE"
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "input.docx"
            output = Path(temp_dir) / "input.pdf"
            _make_docx_with_text_and_image(source, "Output collision test")
            output.write_bytes(sentinel)
            expected_hash = _sha256_file(output)

            result = run_soffice(
                [
                    "--headless",
                    "--convert-to",
                    "pdf:writer_pdf_Export",
                    "--outdir",
                    temp_dir,
                    str(source),
                ],
                capture_output=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(_sha256_file(output), expected_hash)
            failure = _decode_failure(result)
            self.assertFalse(failure["ok"])
            self.assertEqual(failure["error"], "output_exists")

    def test_timeout_reports_owned_pids_and_cleans_job(self):
        import psutil
        from office.soffice import run_soffice

        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "input.docx"
            _make_docx_with_text_and_image(source, "Timeout test")

            result = run_soffice(
                [
                    "--headless",
                    "--convert-to",
                    "pdf:writer_pdf_Export",
                    "--outdir",
                    temp_dir,
                    str(source),
                ],
                capture_output=True,
                timeout=0.01,
            )

            self.assertNotEqual(result.returncode, 0, "Expected forced timeout")
            failure = _decode_failure(result)
            self.assertEqual(failure["error"], "run_timeout")
            self.assertTrue(failure["owned_pids"], "Timeout report has no owned PIDs")
            self.assertTrue(failure["diagnostics"], "Timeout report has no diagnostics")

            deadline = time.monotonic() + 5.0
            while time.monotonic() < deadline and any(
                psutil.pid_exists(pid) for pid in failure["owned_pids"]
            ):
                time.sleep(0.05)
            for pid in failure["owned_pids"]:
                self.assertFalse(psutil.pid_exists(pid), f"Owned PID {pid} is still running")


if __name__ == "__main__":
    unittest.main()
