from __future__ import annotations

import io
import logging
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pypdf import PdfWriter

from institutional_access.pdf_tools import validate_pdf_bytes, write_new_file


class _Page:
    def __init__(self, text: str):
        self._text = text

    def extract_text(self):
        return self._text


class _Reader:
    def __init__(self, _stream, strict=False):
        self.pages = [
            _Page(
                "IEEE TRANSACTIONS ON TERAHERTZ SCIENCE AND TECHNOLOGY\n"
                "DOI: 10.1109/TTHZ.2026.3695375\n"
                "TPE-CSM-BPS for Robust Carrier Phase Recovery"
            )
        ]


class PdfTests(unittest.TestCase):
    def test_pypdf_font_warnings_are_suppressed(self):
        self.assertEqual(logging.getLogger("pypdf").level, logging.ERROR)

    def test_identity_verification(self):
        raw = b"%PDF-1.7\nsynthetic bytes"
        with patch("institutional_access.pdf_tools.PdfReader", _Reader):
            result = validate_pdf_bytes(
                raw,
                doi="10.1109/TTHZ.2026.3695375",
                title="TPE-CSM-BPS for Robust Carrier Phase Recovery",
                provider_identity_match=True,
            )
        self.assertTrue(result["doi_on_pdf"])
        self.assertTrue(result["title_on_pdf"])
        self.assertTrue(result["identity_verified"])
        self.assertEqual(result["pages"], 1)

    def test_real_minimal_pdf_is_readable_but_identity_is_unverified(self):
        stream = io.BytesIO()
        writer = PdfWriter()
        writer.add_blank_page(width=72, height=72)
        writer.write(stream)
        result = validate_pdf_bytes(
            stream.getvalue(),
            doi="10.1109/TTHZ.2026.3695375",
            title="Example",
            provider_identity_match=True,
        )
        self.assertFalse(result["identity_verified"])
        self.assertEqual(result["pages"], 1)

    def test_rejects_non_pdf_and_never_overwrites(self):
        with self.assertRaises(ValueError):
            validate_pdf_bytes(
                b"<html>not a pdf</html>",
                doi="10.1109/TTHZ.2026.3695375",
                title="Example",
                provider_identity_match=False,
            )

    def test_write_new_file_never_overwrites(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "paper.pdf"
            write_new_file(path, b"%PDF-first")
            self.assertEqual(path.read_bytes(), b"%PDF-first")
            with self.assertRaises(FileExistsError):
                write_new_file(path, b"%PDF-second")


if __name__ == "__main__":
    unittest.main()
