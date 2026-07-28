from __future__ import annotations

import argparse
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = SKILL_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from word_template_formatter import (  # noqa: E402
    apply_command,
    build_parser,
    require_template_style_import,
)


class TemplateStyleImportGateTests(unittest.TestCase):
    def parse_apply(self, *extra: str) -> argparse.Namespace:
        with tempfile.TemporaryDirectory() as directory:
            input_path = Path(directory) / "input.docx"
            input_path.write_bytes(b"fixture")
            return build_parser().parse_args(
                ["apply", "--input", str(input_path), *extra]
            )

    def test_existing_document_import_is_blocked_by_default(self) -> None:
        with self.assertRaisesRegex(SystemExit, "disabled by default"):
            require_template_style_import(
                argparse.Namespace(allow_template_style_import=False)
            )

    def test_explicit_whole_document_import_is_allowed(self) -> None:
        require_template_style_import(
            argparse.Namespace(allow_template_style_import=True)
        )

    @patch("word_template_formatter.word_application")
    def test_gate_fails_before_word_starts(self, word_application_mock) -> None:
        with self.assertRaisesRegex(SystemExit, "disabled by default"):
            apply_command(argparse.Namespace(allow_template_style_import=False))
        word_application_mock.assert_not_called()

    def test_apply_parser_defaults_to_blocked(self) -> None:
        args = self.parse_apply()
        self.assertFalse(args.allow_template_style_import)

    def test_apply_parser_accepts_explicit_import_permission(self) -> None:
        args = self.parse_apply("--allow-template-style-import")
        self.assertTrue(args.allow_template_style_import)

    def test_markdown_new_document_flow_forwards_permission(self) -> None:
        source = (SCRIPTS_DIR / "export_markdown_to_word.ps1").read_text(
            encoding="utf-8"
        )
        self.assertGreaterEqual(source.count('"--allow-template-style-import"'), 2)


if __name__ == "__main__":
    unittest.main()
