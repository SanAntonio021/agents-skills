"""Unit tests for docx/scripts/office/soffice.py adapter (14 items).

These tests never start LibreOffice; run() is mocked throughout.
"""
import ast
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Path setup: add docx/scripts so "office.soffice" is importable
# ---------------------------------------------------------------------------
_SKILLS_ROOT = Path(__file__).resolve().parents[2]
_DOCX_SCRIPTS = _SKILLS_ROOT / "docx" / "scripts"
_RUNNER_SCRIPTS = _SKILLS_ROOT / "libreoffice-runner" / "scripts"

for _p in [str(_DOCX_SCRIPTS), str(_RUNNER_SCRIPTS)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

import office.soffice as _mod  # noqa: E402
from office.soffice import _RUNNER_SCRIPTS as MOD_RUNNER_SCRIPTS  # noqa: E402
from office.soffice import get_soffice_env, run_soffice  # noqa: E402


def _mock_report(ok=True, exit_code=0, stdout="", stderr="",
                 error=None, message=None, owned_pids=None, diagnostics=None):
    from libreoffice_runner import RunReport
    return RunReport(
        ok=ok, operation="pdf", source="src.docx", output="out.pdf",
        exit_code=exit_code, stdout=stdout, stderr=stderr,
        error=error, message=message,
        owned_pids=owned_pids or [],
        diagnostics=diagnostics,
    )


class TestRunnerScriptsPath(unittest.TestCase):
    """1. Runner scripts dir exists at runtime."""

    def test_runner_scripts_dir_exists(self):
        self.assertTrue(
            MOD_RUNNER_SCRIPTS.is_dir(),
            f"_RUNNER_SCRIPTS not found: {MOD_RUNNER_SCRIPTS}",
        )


class TestRunnerFailureZeroExitCodeRemapped(unittest.TestCase):
    """2. runner ok=False with exit_code=0 must still produce returncode != 0."""

    def test_runner_failure_zero_exit_code_remapped(self):
        # exit_code=0 from runner, but ok=False -> adapter must return 1
        report = _mock_report(ok=False, exit_code=0, error="corrupt_output", message="bad")
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "f.docx"
            src.write_bytes(b"PK")
            with patch("office.soffice.run", return_value=report):
                result = run_soffice(
                    ["--convert-to", "pdf:writer_pdf_Export", str(src)],
                    capture_output=True,
                )
        self.assertNotEqual(result.returncode, 0)


class TestAstNoPrivateImports(unittest.TestCase):
    """3. AST: no imports from libreoffice_runner sub-modules."""

    def test_no_private_runner_imports(self):
        src_file = Path(_mod.__file__).resolve()
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


class TestAstNoDirectSoffice(unittest.TestCase):
    """4. AST: no subprocess.run/Popen launching soffice directly."""

    def test_no_direct_soffice_subprocess(self):
        src_file = Path(_mod.__file__).resolve()
        tree = ast.parse(src_file.read_text(encoding="utf-8"))
        # Look for subprocess.run or subprocess.Popen calls
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if isinstance(func, ast.Attribute):
                if func.attr in ("run", "Popen") and isinstance(func.value, ast.Name):
                    if func.value.id == "subprocess":
                        # If first arg is a literal containing "soffice", fail
                        if node.args:
                            first = node.args[0]
                            src_text = ast.unparse(first)
                            self.assertNotIn(
                                "soffice", src_text,
                                f"Direct soffice subprocess call found at line {node.lineno}",
                            )


class TestGetSofficeEnv(unittest.TestCase):
    """5. get_soffice_env() must not inject SAL_USE_VCLPLUGIN."""

    def test_no_sal_use_vclplugin(self):
        env = get_soffice_env()
        self.assertNotIn(
            "SAL_USE_VCLPLUGIN", env,
            "get_soffice_env() must not set SAL_USE_VCLPLUGIN",
        )


class TestPdfRunRequest(unittest.TestCase):
    """6. PDF filter -> operation='pdf', RunRequest built correctly."""

    def test_pdf_run_request(self):
        report = _mock_report(ok=True)
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "doc.docx"
            src.write_bytes(b"PK")
            with patch("office.soffice.run", return_value=report) as mock_run:
                result = run_soffice(
                    ["--headless", "--convert-to", "pdf:writer_pdf_Export", str(src)],
                    capture_output=True,
                )
        mock_run.assert_called_once()
        req = mock_run.call_args[0][0]
        self.assertEqual(req.operation, "pdf")
        self.assertIsNone(req.convert_to)
        self.assertEqual(result.returncode, 0)


class TestConvertWithOutdir(unittest.TestCase):
    """7. Non-PDF filter with --outdir -> operation='convert', outdir used."""

    def test_non_pdf_with_outdir(self):
        report = _mock_report(ok=True)
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "slide.pptx"
            src.write_bytes(b"PK")
            outdir = Path(td) / "out"
            outdir.mkdir()
            with patch("office.soffice.run", return_value=report) as mock_run:
                run_soffice([
                    "--convert-to", "docx:MS Word 2007 XML",
                    "--outdir", str(outdir),
                    str(src),
                ], capture_output=True)
        req = mock_run.call_args[0][0]
        self.assertEqual(req.operation, "convert")
        self.assertEqual(req.convert_to, "docx:MS Word 2007 XML")
        self.assertEqual(req.output.parent, outdir)


class TestConvertWithoutOutdir(unittest.TestCase):
    """8. No --outdir -> output lands beside source."""

    def test_non_pdf_without_outdir(self):
        report = _mock_report(ok=True)
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "input.docx"
            src.write_bytes(b"PK")
            with patch("office.soffice.run", return_value=report) as mock_run:
                run_soffice(
                    ["--convert-to", "odt:writer8", str(src)],
                    capture_output=True,
                )
        req = mock_run.call_args[0][0]
        self.assertEqual(req.output.parent, src.parent)
        self.assertEqual(req.output.suffix, ".odt")


class TestCaptureOutputTextMode(unittest.TestCase):
    """9. capture_output=True, text=True -> str stdout/stderr."""

    def test_capture_output_text_mode(self):
        report = _mock_report(ok=True, stdout="converted", stderr="")
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "f.docx"
            src.write_bytes(b"PK")
            with patch("office.soffice.run", return_value=report):
                result = run_soffice(
                    ["--convert-to", "pdf:writer_pdf_Export", str(src)],
                    capture_output=True, text=True,
                )
        self.assertIsInstance(result.stdout, str)
        self.assertIsInstance(result.stderr, str)


class TestCaptureOutputBinaryMode(unittest.TestCase):
    """10. capture_output=True (no text flag) -> bytes stdout/stderr."""

    def test_capture_output_binary_mode(self):
        report = _mock_report(ok=True, stdout="ok", stderr="")
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "f.docx"
            src.write_bytes(b"PK")
            with patch("office.soffice.run", return_value=report):
                result = run_soffice(
                    ["--convert-to", "pdf:writer_pdf_Export", str(src)],
                    capture_output=True,
                )
        self.assertIsInstance(result.stdout, bytes)
        self.assertIsInstance(result.stderr, bytes)


class TestTimeoutMapsToRunTimeout(unittest.TestCase):
    """11. timeout kwarg is forwarded as run_timeout in RunRequest."""

    def test_timeout_maps_to_run_timeout(self):
        report = _mock_report(ok=True)
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "f.docx"
            src.write_bytes(b"PK")
            with patch("office.soffice.run", return_value=report) as mock_run:
                run_soffice(
                    ["--convert-to", "pdf:writer_pdf_Export", str(src)],
                    capture_output=True, timeout=45.0,
                )
        req = mock_run.call_args[0][0]
        self.assertEqual(req.run_timeout, 45.0)


class TestCheckTrueRaisesOnFailure(unittest.TestCase):
    """12. check=True with failing runner raises CalledProcessError."""

    def test_check_true_raises_on_failure(self):
        report = _mock_report(ok=False, exit_code=1, error="nonzero_exit", message="fail")
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "f.docx"
            src.write_bytes(b"PK")
            with patch("office.soffice.run", return_value=report):
                with self.assertRaises(subprocess.CalledProcessError):
                    run_soffice(
                        ["--convert-to", "pdf:writer_pdf_Export", str(src)],
                        capture_output=True, check=True,
                    )


class TestUnknownKwargRaisesTypeError(unittest.TestCase):
    """13. Unknown kwarg raises TypeError; run() must not be called."""

    def test_unknown_kwarg_type_error(self):
        with patch("office.soffice.run") as mock_run:
            with self.assertRaises(TypeError):
                run_soffice(
                    ["--convert-to", "pdf:writer_pdf_Export", "f.docx"],
                    unsupported_kwarg=True,
                )
        mock_run.assert_not_called()


class TestMissingConvertToFailsClosed(unittest.TestCase):
    """14. Missing --convert-to returns structured failure; run() not called."""

    def test_missing_convert_to_fails_closed(self):
        with patch("office.soffice.run") as mock_run:
            result = run_soffice(["--headless", "input.docx"], capture_output=True)
        mock_run.assert_not_called()
        self.assertEqual(result.returncode, 2)
        self.assertIn(b"unsupported_invocation", result.stderr)
        self.assertEqual(result.runner_report["error"], "unsupported_invocation")


if __name__ == "__main__":
    unittest.main()
