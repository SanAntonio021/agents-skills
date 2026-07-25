"""Unit tests for docx/scripts/accept_changes.py adapter (6 items).

Never starts LibreOffice; run() is mocked throughout.
"""
import ast
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

_SKILLS_ROOT = Path(__file__).resolve().parents[2]
_DOCX_SCRIPTS = _SKILLS_ROOT / "docx" / "scripts"
_RUNNER_SCRIPTS = _SKILLS_ROOT / "libreoffice-runner" / "scripts"

for _p in [str(_DOCX_SCRIPTS), str(_RUNNER_SCRIPTS)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from accept_changes import accept_changes  # noqa: E402
import accept_changes as _ac_mod  # noqa: E402


def _mock_report(ok, error=None, message=None, diagnostics=None):
    from libreoffice_runner import RunReport
    return RunReport(
        ok=ok, operation="accept-changes",
        source="in.docx", output="out.docx",
        error=error, message=message, diagnostics=diagnostics,
    )


class TestMissingInputNoRunnerCall(unittest.TestCase):
    """1. Missing input file: error returned locally, runner not called."""

    def test_missing_input_no_runner_call(self):
        with patch("accept_changes.run") as mock_run:
            _, msg = accept_changes("/no/such/file.docx", "/tmp/out.docx")
        mock_run.assert_not_called()
        self.assertIn("Error", msg)
        self.assertIn("not found", msg)


class TestNonDocxInputNoRunnerCall(unittest.TestCase):
    """2. Non-DOCX input: error returned locally, runner not called."""

    def test_non_docx_input_no_runner_call(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "file.pptx"
            src.write_bytes(b"PK")
            with patch("accept_changes.run") as mock_run:
                _, msg = accept_changes(str(src), str(Path(td) / "out.docx"))
        mock_run.assert_not_called()
        self.assertIn("Error", msg)
        self.assertIn("not a DOCX", msg)


class TestSuccessfulAcceptChanges(unittest.TestCase):
    """3. Valid input: runner called with accept-changes operation, success message returned."""

    def test_successful_accept_changes(self):
        report = _mock_report(ok=True)
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "tracked.docx"
            src.write_bytes(b"PK")
            out = Path(td) / "clean.docx"
            with patch("accept_changes.run", return_value=report) as mock_run:
                _, msg = accept_changes(str(src), str(out))
        mock_run.assert_called_once()
        req = mock_run.call_args[0][0]
        self.assertEqual(req.operation, "accept-changes")
        self.assertIn("Successfully", msg)


class TestOutputExistsStructuredError(unittest.TestCase):
    """4. output_exists failure: structured error message returned."""

    def test_output_exists_structured_error(self):
        report = _mock_report(
            ok=False, error="output_exists",
            message="Output already exists: out.docx",
        )
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "in.docx"
            src.write_bytes(b"PK")
            with patch("accept_changes.run", return_value=report):
                _, msg = accept_changes(str(src), str(Path(td) / "out.docx"))
        self.assertIn("Error", msg)
        self.assertIn("output_exists", msg)


class TestRunnerFailureErrorMessage(unittest.TestCase):
    """5. Generic runner failure: error and message included in return string."""

    def test_runner_failure_error_message(self):
        report = _mock_report(
            ok=False, error="nonzero_exit", message="LibreOffice exited with code 1",
            diagnostics="/tmp/sanan-lo-abc/diag.json",
        )
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "in.docx"
            src.write_bytes(b"PK")
            with patch("accept_changes.run", return_value=report):
                _, msg = accept_changes(str(src), str(Path(td) / "out.docx"))
        self.assertIn("Error", msg)
        self.assertIn("nonzero_exit", msg)
        self.assertIn("diagnostics", msg)


class TestAstNoPrivateRunnerImports(unittest.TestCase):
    """6. AST: no imports from libreoffice_runner sub-modules."""

    def test_no_private_runner_imports(self):
        src_file = Path(_ac_mod.__file__).resolve()
        tree = ast.parse(src_file.read_text(encoding="utf-8"))
        forbidden = {"core", "win32_sync", "win32_job"}
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                mod = getattr(node, "module", "") or ""
                for seg in mod.split("."):
                    self.assertNotIn(
                        seg, forbidden,
                        f"Private runner import found: {mod}",
                    )


if __name__ == "__main__":
    unittest.main()
