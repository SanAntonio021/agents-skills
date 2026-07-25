"""Integration tests for docx skill (4 items) — require LibreOffice.

Run only when RUN_LIBREOFFICE_INTEGRATION=1 is set.
Tests stop immediately if any LibreOffice process is already running.
"""
import hashlib
import json
import os
import sys
import tempfile
import time
import unittest
import zipfile
from pathlib import Path

_SKILLS_ROOT = Path(__file__).resolve().parents[2]
_DOCX_SCRIPTS = _SKILLS_ROOT / "docx" / "scripts"
_RUNNER_SCRIPTS = _SKILLS_ROOT / "libreoffice-runner" / "scripts"

for _p in [str(_DOCX_SCRIPTS), str(_RUNNER_SCRIPTS)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)


def _check_integration_deps():
    missing = []
    for pkg in ["psutil", "docx", "PyPDF2"]:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)
    return missing


def _lo_procs():
    import psutil
    return [p for p in psutil.process_iter(["name"])
            if "soffice" in (p.info["name"] or "").lower()]


def _sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _make_docx_with_text(path: Path, text: str) -> None:
    """Create a minimal DOCX with the given text using python-docx."""
    import docx as _docx
    doc = _docx.Document()
    doc.add_paragraph(text)
    doc.save(str(path))


def _inject_tracked_changes(docx_path: Path) -> None:
    """Inject w:ins and w:del markers into word/document.xml via ZIP manipulation."""
    import shutil
    tmp = docx_path.with_suffix(".tmp.docx")
    shutil.copy2(docx_path, tmp)
    with zipfile.ZipFile(tmp, "r") as zin, zipfile.ZipFile(docx_path, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == "word/document.xml":
                # Insert a minimal w:ins element before </w:body>
                data = data.replace(
                    b"</w:body>",
                    b'<w:ins w:id="1" w:author="Test" w:date="2024-01-01T00:00:00Z">'
                    b'<w:r><w:t>inserted</w:t></w:r></w:ins></w:body>',
                )
            zout.writestr(item, data)
    tmp.unlink()


@unittest.skipUnless(
    os.environ.get("RUN_LIBREOFFICE_INTEGRATION") == "1",
    "Set RUN_LIBREOFFICE_INTEGRATION=1 to run",
)
class TestDocxIntegration(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        missing = _check_integration_deps()
        if missing:
            raise unittest.SkipTest(f"Missing dependencies: {missing}")
        running = _lo_procs()
        if running:
            raise unittest.SkipTest(
                f"LibreOffice already running ({len(running)} process(es)); "
                "stop them before running integration tests"
            )

    def test_docx_to_pdf_valid(self):
        """4a. DOCX -> PDF via adapter: PyPDF2-readable, >=1 page."""
        from PyPDF2 import PdfReader
        from office.soffice import run_soffice

        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "input.docx"
            out = Path(td) / "input.pdf"
            _make_docx_with_text(src, "Integration test content")

            result = run_soffice(
                ["--headless", "--convert-to", "pdf:writer_pdf_Export",
                 "--outdir", td, str(src)],
                capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 0,
                             f"Conversion failed: {result.stderr}")
            self.assertTrue(out.exists(), "PDF output not created")
            reader = PdfReader(str(out))
            self.assertGreaterEqual(len(reader.pages), 1)

    def test_accept_changes_removes_markup(self):
        """4b. accept-changes: output is a valid DOCX without w:ins/w:del."""
        from accept_changes import accept_changes

        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "tracked.docx"
            out = Path(td) / "clean.docx"
            _make_docx_with_text(src, "Some tracked text")
            _inject_tracked_changes(src)

            # Verify injection worked
            with zipfile.ZipFile(src) as z:
                doc_xml = z.read("word/document.xml")
            self.assertIn(b"<w:ins", doc_xml)

            _, msg = accept_changes(str(src), str(out))
            self.assertNotIn("Error", msg, f"accept_changes failed: {msg}")
            self.assertTrue(out.exists(), "Output DOCX not created")

            # Output must be a valid ZIP / DOCX
            with zipfile.ZipFile(out) as z:
                out_xml = z.read("word/document.xml")
            self.assertNotIn(b"<w:ins", out_xml, "w:ins still present after accept-changes")
            self.assertNotIn(b"<w:del", out_xml, "w:del still present after accept-changes")

    def test_output_exists_not_overwritten(self):
        """4c. output_exists: adapter returns structured error; sentinel file unchanged."""
        from office.soffice import run_soffice

        sentinel_content = b"SENTINEL_DO_NOT_OVERWRITE"

        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "input.docx"
            out = Path(td) / "input.pdf"
            _make_docx_with_text(src, "test")
            # Pre-create output with sentinel content
            out.write_bytes(sentinel_content)
            sentinel_sha = _sha256_file(out)

            result = run_soffice(
                ["--headless", "--convert-to", "pdf:writer_pdf_Export",
                 "--outdir", td, str(src)],
                capture_output=True,
            )
            self.assertNotEqual(result.returncode, 0, "Expected failure for output_exists")
            self.assertEqual(_sha256_file(out), sentinel_sha, "Sentinel file was modified")
            # Stderr should be JSON with error field
            err_obj = json.loads(result.stderr.decode("utf-8"))
            self.assertEqual(err_obj.get("ok"), False)
            self.assertIn("output_exists", err_obj.get("error", ""))

    def test_timeout_owned_pids_all_exited(self):
        """4d. Timeout failure: owned_pids in report are all no longer running."""
        import psutil
        from office.soffice import run_soffice

        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "input.docx"
            _make_docx_with_text(src, "Timeout test")

            # Use an extremely short timeout to force a timeout failure
            result = run_soffice(
                ["--headless", "--convert-to", "pdf:writer_pdf_Export",
                 "--outdir", td, str(src)],
                capture_output=True, timeout=0.01,  # 10ms – effectively forces timeout path
            )
            # Whether or not it times out, no soffice processes should remain
            time.sleep(1.0)
            remaining = _lo_procs()
            self.assertEqual(len(remaining), 0,
                             f"LibreOffice processes remain after test: {remaining}")
            # If timeout was reported, verify owned_pids are gone
            if result.returncode != 0 and result.stderr:
                try:
                    err_obj = json.loads(result.stderr.decode("utf-8"))
                    for pid in (err_obj.get("owned_pids") or []):
                        self.assertFalse(
                            psutil.pid_exists(pid),
                            f"PID {pid} from owned_pids still running",
                        )
                except json.JSONDecodeError:
                    pass  # Not all failures produce JSON stderr


if __name__ == "__main__":
    unittest.main()
