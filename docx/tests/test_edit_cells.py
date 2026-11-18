from __future__ import annotations

import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

from docx import Document
from docx.shared import Pt
from lxml import etree


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import edit_cells as editor  # noqa: E402


W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


class CellEditTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "form.docx"
        self.edits = self.root / "edits.json"
        self.output = self.root / "updated.docx"
        self.record = self.root / "updated.check.json"
        self.document = Document()
        self.document.add_paragraph("Body before the form")
        table = self.document.add_table(rows=3, cols=2)
        table.cell(0, 0).text = "项目 简介"
        body = table.cell(0, 1)
        body.paragraphs[0].text = "Old first"
        body.add_paragraph("Old second")
        for paragraph in body.paragraphs:
            paragraph.paragraph_format.first_line_indent = Pt(24)
            paragraph.runs[0].font.size = Pt(12)
            paragraph.runs[0].font.name = "KaiTi"
        table.cell(1, 0).text = "技术先进性"
        numbered = table.cell(1, 1).paragraphs[0]
        numbered.add_run("1.")
        numbered.add_run("Fast link without codec delay, verified twice.")
        table.cell(2, 0).text = "其他"
        table.cell(2, 1).text = "Untouched"
        self.save_source()

    def save_source(self) -> None:
        self.document.save(self.source)
        self.original = self.source.read_bytes()

    def apply(self, edits: list[dict]) -> dict:
        self.edits.write_text(json.dumps(edits, ensure_ascii=False), encoding="utf-8")
        return editor.apply_edits(self.source, self.edits, self.output, self.record)

    def cell_paragraphs(self, row: int) -> list:
        return Document(self.output).tables[0].cell(row, 1).paragraphs

    def assert_rejected(self, edits: list[dict]) -> None:
        with self.assertRaises(ValueError):
            self.apply(edits)
        self.assertFalse(self.output.exists())
        self.assertFalse(self.record.exists())
        self.assertEqual(self.original, self.source.read_bytes())

    def test_replace_cell_keeps_cell_format_and_other_content(self) -> None:
        result = self.apply([{"op": "replace_cell", "label": "项目简介",
                              "paragraphs": ["新第一段", "新第二段", "新第三段"]}])
        self.assertTrue(result["ok"], result)
        paragraphs = self.cell_paragraphs(0)
        self.assertEqual([p.text for p in paragraphs], ["新第一段", "新第二段", "新第三段"])
        for paragraph in paragraphs:
            self.assertEqual(paragraph.paragraph_format.first_line_indent, Pt(24))
            self.assertEqual(paragraph.runs[0].font.size, Pt(12))
        updated = Document(self.output)
        self.assertEqual(updated.paragraphs[0].text, "Body before the form")
        self.assertEqual(updated.tables[0].cell(2, 1).text, "Untouched")
        self.assertEqual(self.original, self.source.read_bytes())
        with zipfile.ZipFile(self.source) as before, zipfile.ZipFile(self.output) as after:
            for name in before.namelist():
                if name != "word/document.xml":
                    self.assertEqual(before.read(name), after.read(name), name)
        self.assertTrue(editor.check_edits(self.source, self.edits, self.output)["ok"])

    def test_replace_text_edits_one_run_and_keeps_numbering_run(self) -> None:
        result = self.apply([{"op": "replace_text", "label": "技术先进性",
                              "old": ", verified twice", "new": ""}])
        self.assertTrue(result["ok"], result)
        paragraph = self.cell_paragraphs(1)[0]
        self.assertEqual(paragraph.text, "1.Fast link without codec delay.")
        self.assertEqual(len(paragraph.runs), 2)

    def test_replace_cell_with_split_numbering_runs_uses_uniform_template(self) -> None:
        result = self.apply([{"op": "replace_cell", "label": "技术先进性",
                              "paragraphs": ["1.First", "2.Second"]}])
        self.assertTrue(result["ok"], result)
        self.assertEqual([p.text for p in self.cell_paragraphs(1)], ["1.First", "2.Second"])

    def test_text_spanning_runs_is_rejected(self) -> None:
        self.assert_rejected([{"op": "replace_text", "label": "技术先进性", "old": "1.Fast", "new": "1.Quick"}])

    def test_missing_or_ambiguous_label_is_rejected(self) -> None:
        self.assert_rejected([{"op": "replace_cell", "label": "不存在", "paragraphs": ["x"]}])
        self.document.tables[0].add_row()
        self.document.tables[0].rows[-1].cells[0].text = "项目简介"
        self.save_source()
        self.assert_rejected([{"op": "replace_cell", "label": "项目简介", "paragraphs": ["x"]}])

    def test_repeated_text_and_line_breaks_are_rejected(self) -> None:
        self.assert_rejected([{"op": "replace_text", "label": "项目简介", "old": "Old", "new": "New"}])
        self.assert_rejected([{"op": "replace_cell", "label": "项目简介", "paragraphs": ["a\nb"]}])

    def test_existing_output_is_protected(self) -> None:
        self.output.write_bytes(b"keep")
        with self.assertRaises(ValueError):
            self.apply([{"op": "replace_cell", "label": "项目简介", "paragraphs": ["x"]}])
        self.assertEqual(self.output.read_bytes(), b"keep")

    def test_inspect_reports_rows_counts_and_runs(self) -> None:
        result = editor.inspect_document(self.source, "技术先进性")
        self.assertEqual(len(result["rows"]), 1)
        row = result["rows"][0]
        self.assertEqual(row["paragraphs"][0]["runs"], 2)
        self.assertEqual(row["characters"], len("1.Fast link without codec delay, verified twice."))


if __name__ == "__main__":
    unittest.main()
