from __future__ import annotations

import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt
from lxml import etree


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import document_versions as versions  # noqa: E402
import edit_paragraphs as editor  # noqa: E402


W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


class ParagraphEditTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "source.docx"
        self.edits = self.root / "edits.json"
        self.output = self.root / "updated.docx"
        self.record = self.root / "updated.check.json"
        self.document = Document()
        for text in ("Alpha", "Bravo", "Charlie", "Delta", "Echo"):
            paragraph = self.document.add_paragraph(text)
            paragraph.paragraph_format.space_after = Pt(7)
        self.document.sections[0].header.paragraphs[0].text = "Preserved header"
        self.save_source()

    def save_source(self) -> None:
        self.document.save(self.source)
        self.original = self.source.read_bytes()

    def write_edits(self, edits: list[dict]) -> None:
        self.edits.write_text(json.dumps(edits, ensure_ascii=False), encoding="utf-8")

    def apply(self, edits: list[dict]) -> dict:
        self.write_edits(edits)
        return editor.apply_edits(self.source, self.edits, self.output, self.record)

    def texts(self) -> list[str]:
        return [p.text for p in Document(self.output).paragraphs]

    def assert_rejected(self, edits: list[dict]) -> None:
        with self.assertRaises(ValueError):
            self.apply(edits)
        self.assertFalse(self.output.exists())
        self.assertFalse(self.record.exists())
        self.assertEqual(self.original, self.source.read_bytes())

    def assert_unrelated_parts_unchanged(self) -> None:
        with zipfile.ZipFile(self.source) as baseline, zipfile.ZipFile(self.output) as candidate:
            self.assertEqual(set(baseline.namelist()), set(candidate.namelist()))
            self.assertIsNone(candidate.testzip())
            for name in baseline.namelist():
                if name != "word/document.xml":
                    self.assertEqual(baseline.read(name), candidate.read(name), name)
            before = etree.fromstring(baseline.read("word/document.xml"))
            after = etree.fromstring(candidate.read("word/document.xml"))
            for target in (W + "sectPr", W + "tbl"):
                self.assertEqual(
                    [etree.tostring(node) for node in before.iter(target)],
                    [etree.tostring(node) for node in after.iter(target)],
                )

    def test_four_operations_use_original_indexes_and_preserve_other_parts(self) -> None:
        self.document.add_table(rows=1, cols=1).cell(0, 0).text = "Untouched cell"
        self.save_source()
        result = self.apply([
            {"op": "replace", "old": "Alpha", "text": "New alpha"},
            {"op": "insert_before", "old": "Bravo", "text": "Before bravo"},
            {"op": "insert_after", "old": "Charlie", "text": "After charlie"},
            {"op": "delete", "old": "Delta", "index": 3},
        ])
        self.assertTrue(result["ok"], result)
        self.assertEqual(self.texts(), ["New alpha", "Before bravo", "Bravo", "Charlie", "After charlie", "Echo"])
        self.assertEqual(self.original, self.source.read_bytes())
        self.assert_unrelated_parts_unchanged()
        self.assertTrue(editor.check_edits(self.source, self.edits, self.output)["ok"])

    def test_replacement_preserves_paragraph_and_uniform_character_format(self) -> None:
        paragraph = self.document.paragraphs[0]
        paragraph.style = "Heading 2"
        paragraph.runs[0].bold = True
        paragraph.runs[0].font.size = Pt(15)
        self.save_source()
        self.apply([{"op": "replace", "old": "Alpha", "text": "Approved wording"}])
        updated = Document(self.output).paragraphs[0]
        self.assertEqual(updated.style.style_id, paragraph.style.style_id)
        self.assertEqual(updated.paragraph_format.space_after, paragraph.paragraph_format.space_after)
        self.assertTrue(updated.runs[0].bold)
        self.assertEqual(updated.runs[0].font.size, Pt(15))

    def test_insert_can_inherit_specified_adjacent_paragraph(self) -> None:
        self.document.paragraphs[0].style = "Heading 2"
        self.save_source()
        self.apply([{"op": "insert_before", "old": "Bravo", "text": "Added heading", "format_from": {"old": "Alpha", "index": 0}}])
        self.assertEqual(Document(self.output).paragraphs[1].style.style_id, "Heading2")

    def test_insert_rejects_nonadjacent_format_source(self) -> None:
        self.assert_rejected([{"op": "insert_after", "old": "Alpha", "text": "New", "format_from": {"old": "Delta"}}])

    def test_duplicate_text_requires_index(self) -> None:
        self.document.add_paragraph("Alpha")
        self.save_source()
        self.assert_rejected([{"op": "replace", "old": "Alpha", "text": "New"}])

    def test_inspection_index_disambiguates_duplicate_and_includes_table_paragraphs(self) -> None:
        self.document.add_paragraph("Alpha")
        self.document.add_table(rows=1, cols=1).cell(0, 0).text = "Cell text"
        self.save_source()
        inspection = editor.inspect_document(self.source)
        matches = [p for p in inspection["paragraphs"] if p["text"] == "Alpha"]
        self.assertEqual([p["index"] for p in matches], [0, 5])
        self.assertTrue(any(p["text"] == "Cell text" for p in inspection["paragraphs"]))
        self.apply([{"op": "replace", "old": "Alpha", "index": matches[1]["index"], "text": "Second alpha"}])
        self.assertEqual(self.texts()[0], "Alpha")
        self.assertEqual(self.texts()[5], "Second alpha")

    def test_inspect_filter_keeps_original_indexes(self) -> None:
        inspection = editor.inspect_document(self.source, contains="Charlie")
        self.assertEqual([(p["index"], p["text"]) for p in inspection["paragraphs"]], [(2, "Charlie")])

    def test_index_still_requires_matching_original_text(self) -> None:
        self.assert_rejected([{"op": "replace", "old": "Alpha", "index": 1, "text": "Wrong target"}])

    def test_stale_text_rejects_entire_batch_without_partial_output(self) -> None:
        self.assert_rejected([
            {"op": "replace", "old": "Alpha", "text": "Valid first change"},
            {"op": "replace", "old": "Old missing wording", "text": "Invalid second change"},
        ])

    def test_conflicting_operations_reject_entire_batch(self) -> None:
        self.assert_rejected([
            {"op": "insert_before", "old": "Alpha", "text": "Added"},
            {"op": "delete", "old": "Alpha"},
        ])

    def test_mixed_character_format_is_not_flattened(self) -> None:
        self.document.paragraphs[0].add_run(" bold").bold = True
        self.save_source()
        inspection = editor.inspect_document(self.source)
        self.assertFalse(inspection["paragraphs"][0]["supported"])
        self.assert_rejected([{"op": "replace", "old": "Alpha bold", "text": "Flattened"}])

    def test_formula_target_is_rejected_for_all_operations(self) -> None:
        formula = OxmlElement("m:oMath")
        run = OxmlElement("m:r")
        text = OxmlElement("m:t")
        text.text = "x"
        run.append(text)
        formula.append(run)
        self.document.paragraphs[0]._p.append(formula)
        self.save_source()
        target = editor.inspect_document(self.source)["paragraphs"][0]
        self.assertFalse(target["supported"])
        for op in ("replace", "insert_before", "insert_after", "delete"):
            with self.subTest(op=op):
                edit = {"op": op, "old": target["text"], "index": 0}
                if op != "delete":
                    edit["text"] = "New text"
                self.assert_rejected([edit])

    def test_fields_hyperlinks_revisions_and_bookmarks_are_rejected(self) -> None:
        for tag in ("w:fldSimple", "w:hyperlink", "w:ins", "w:bookmarkStart"):
            with self.subTest(tag=tag):
                node = OxmlElement(tag)
                if tag == "w:bookmarkStart":
                    node.set(qn("w:id"), "1")
                    node.set(qn("w:name"), "Anchor")
                paragraph = self.document.paragraphs[0]._p
                paragraph.append(node)
                self.save_source()
                target = editor.inspect_document(self.source)["paragraphs"][0]
                self.assertFalse(target["supported"])
                self.assert_rejected([{"op": "replace", "old": target["text"], "index": 0, "text": "New"}])
                paragraph.remove(node)

    def test_existing_output_is_preserved(self) -> None:
        self.output.write_bytes(b"Existing user's output")
        self.write_edits([{"op": "replace", "old": "Alpha", "text": "New"}])
        with self.assertRaises(ValueError):
            editor.apply_edits(self.source, self.edits, self.output)
        self.assertEqual(self.output.read_bytes(), b"Existing user's output")
        self.assertEqual(self.original, self.source.read_bytes())

    def test_source_cannot_be_used_as_output(self) -> None:
        self.write_edits([{"op": "replace", "old": "Alpha", "text": "New"}])
        with self.assertRaises(ValueError):
            editor.apply_edits(self.source, self.edits, self.source)
        self.assertEqual(self.original, self.source.read_bytes())

    def test_multiline_and_tab_text_are_rejected(self) -> None:
        for text in ("Two\nparagraphs", "Two\rparagraphs", "A\tB"):
            with self.subTest(text=text):
                self.assert_rejected([{"op": "replace", "old": "Alpha", "text": text}])

    def test_invalid_operation_and_boolean_index_are_rejected(self) -> None:
        self.assert_rejected([{"op": "append", "old": "Alpha", "text": "New"}])
        self.assert_rejected([{"op": "replace", "old": "Bravo", "index": True, "text": "New"}])

    def test_checker_detects_candidate_content_tampering(self) -> None:
        self.apply([{"op": "replace", "old": "Alpha", "text": "New"}])
        candidate = Document(self.output)
        candidate.paragraphs[2].text = "Unrequested change"
        candidate.save(self.output)
        with self.assertRaisesRegex(ValueError, "content or paragraph formatting"):
            editor.check_edits(self.source, self.edits, self.output)

    def test_checker_detects_unrelated_package_part_tampering(self) -> None:
        self.apply([{"op": "replace", "old": "Alpha", "text": "New"}])
        with zipfile.ZipFile(self.output) as package:
            entries = [(info, package.read(info.filename)) for info in package.infolist()]
        with zipfile.ZipFile(self.output, "w") as package:
            for info, content in entries:
                if info.filename == "word/header1.xml":
                    content = content.replace(b"Preserved header", b"Changed header")
                package.writestr(info, content)
        with self.assertRaisesRegex(ValueError, "Unrelated package parts"):
            editor.check_edits(self.source, self.edits, self.output)

    def test_existing_check_is_reused_without_starting_another_process(self) -> None:
        self.apply([{"op": "replace", "old": "Alpha", "text": "Approved text"}])
        command = [sys.executable, "-X", "utf8", str(SCRIPTS / "edit_paragraphs.py"),
                   "check", str(self.source), str(self.edits), str(self.output)]
        with patch.object(versions.subprocess, "run", side_effect=AssertionError("Checker should be reused")):
            result = versions.run_check(self.output, self.record, command, kind="paragraph-content-style")
        self.assertTrue(result["ok"], result)
        self.assertTrue(result["reused"], result)

    def test_table_paragraph_does_not_enter_fast_layout_path(self) -> None:
        self.document.add_table(rows=1, cols=1).cell(0, 0).text = "Cell text"
        self.save_source()
        target = editor.inspect_document(self.source, contains="Cell text")["paragraphs"][0]
        self.assertFalse(target["supported"])
        self.assert_rejected([{"op": "replace", "old": "Cell text", "text": "Changed cell"}])

    def test_changed_input_before_publication_rejects_candidate(self) -> None:
        with patch.object(versions, "changed_files", return_value=[{"path": str(self.source)}]):
            self.assert_rejected([{"op": "replace", "old": "Alpha", "text": "New"}])
        self.assertFalse(list(self.root.glob(".paragraph-edit-*")))

    def test_output_race_does_not_overwrite_or_delete_other_output(self) -> None:
        self.write_edits([{"op": "replace", "old": "Alpha", "text": "New"}])

        def competing_output(_temporary: Path, destination: Path) -> None:
            destination.write_bytes(b"Another process output")
            raise FileExistsError("A different process published the output")

        with patch.object(editor.os, "link", side_effect=competing_output):
            with self.assertRaises(FileExistsError):
                editor.apply_edits(self.source, self.edits, self.output, self.record)
        self.assertEqual(self.output.read_bytes(), b"Another process output")
        self.assertFalse(self.record.exists())
        self.assertEqual(self.source.read_bytes(), self.original)
        self.assertFalse(list(self.root.glob(".paragraph-edit-*")))

    def test_editing_format_donor_conflicts_with_insertion(self) -> None:
        self.assert_rejected([
            {"op": "insert_before", "old": "Bravo", "text": "New", "format_from": {"old": "Alpha"}},
            {"op": "replace", "old": "Alpha", "text": "Changed donor"},
        ])

    def test_signed_package_is_rejected_without_invalidating_signature(self) -> None:
        with zipfile.ZipFile(self.source, "a") as package:
            package.writestr("_xmlsignatures/origin.sigs", b"")
        self.original = self.source.read_bytes()
        self.assert_rejected([{"op": "replace", "old": "Alpha", "text": "New"}])

    def test_paragraph_inside_multi_paragraph_field_is_rejected(self) -> None:
        for kind in ("begin", "separate"):
            marker = OxmlElement("w:fldChar")
            marker.set(qn("w:fldCharType"), kind)
            self.document.paragraphs[0].add_run()._r.append(marker)
        end = OxmlElement("w:fldChar")
        end.set(qn("w:fldCharType"), "end")
        self.document.paragraphs[2].add_run()._r.append(end)
        self.save_source()
        target = editor.inspect_document(self.source, contains="Bravo")["paragraphs"][0]
        self.assertFalse(target["supported"])
        self.assert_rejected([{"op": "replace", "old": "Bravo", "text": "Flattened field result"}])
        self.assertTrue(editor.inspect_document(self.source, contains="Delta")["paragraphs"][0]["supported"])

    def test_paragraph_inside_bookmark_or_comment_range_is_rejected(self) -> None:
        for tag in ("bookmark", "commentRange"):
            with self.subTest(tag=tag):
                start = OxmlElement("w:" + tag + "Start")
                end = OxmlElement("w:" + tag + "End")
                start.set(qn("w:id"), "1")
                end.set(qn("w:id"), "1")
                self.document.paragraphs[0]._p.append(start)
                self.document.paragraphs[2]._p.append(end)
                self.save_source()
                self.assertFalse(editor.inspect_document(self.source, contains="Bravo")["paragraphs"][0]["supported"])
                self.assert_rejected([{"op": "delete", "old": "Bravo"}])
                self.assertTrue(editor.inspect_document(self.source, contains="Delta")["paragraphs"][0]["supported"])
                self.document.paragraphs[0]._p.remove(start)
                self.document.paragraphs[2]._p.remove(end)

    def test_empty_paragraph_character_properties_survive_replace_and_insert(self) -> None:
        paragraph = self.document.paragraphs[0]
        paragraph._p.remove(paragraph.runs[0]._r)
        properties = OxmlElement("w:rPr")
        properties.append(OxmlElement("w:b"))
        fonts = OxmlElement("w:rFonts")
        fonts.set(qn("w:ascii"), "Arial")
        fonts.set(qn("w:hAnsi"), "Arial")
        properties.append(fonts)
        paragraph._p.get_or_add_pPr().append(properties)
        self.save_source()
        for operation in ("replace", "insert_after"):
            with self.subTest(operation=operation):
                output = self.root / (operation + ".docx")
                self.write_edits([{"op": operation, "old": "", "index": 0, "text": "Added text"}])
                editor.apply_edits(self.source, self.edits, output)
                inserted = Document(output).paragraphs[0 if operation == "replace" else 1]
                self.assertTrue(inserted.runs[0].bold)
                self.assertEqual(inserted.runs[0].font.name, "Arial")

    def test_same_gap_insertions_are_rejected(self) -> None:
        self.assert_rejected([
            {"op": "insert_after", "old": "Alpha", "text": "After alpha"},
            {"op": "insert_before", "old": "Bravo", "text": "Before bravo"},
        ])

    def test_competing_record_is_preserved_and_no_output_is_published(self) -> None:
        self.write_edits([{"op": "replace", "old": "Alpha", "text": "New"}])
        original_plan = editor.plan

        def competing_record(*args, **kwargs):
            planned = original_plan(*args, **kwargs)
            self.record.write_bytes(b"Another process record")
            return planned

        with patch.object(editor, "plan", side_effect=competing_record):
            with self.assertRaises((ValueError, FileExistsError)):
                editor.apply_edits(self.source, self.edits, self.output, self.record)
        self.assertEqual(self.record.read_bytes(), b"Another process record")
        self.assertFalse(self.output.exists())
        self.assertEqual(self.original, self.source.read_bytes())
        self.assertFalse(list(self.root.glob(".paragraph-edit-*")))

    def test_fast_update_records_content_styles_and_layout_not_checked(self) -> None:
        result = self.apply([{"op": "replace", "old": "Alpha", "text": "Approved text"}])
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["layout"], "not_checked")
        record = json.loads(self.record.read_text(encoding="utf-8"))
        self.assertEqual(record["layout"], "not_checked")
        self.assertTrue(versions.assess(record, self.output)["reusable"])
        self.assertFalse(list(self.root.glob("*.pdf")))
        self.assertFalse(list(self.root.glob("*.png")))
        self.assertFalse(list(self.root.glob("*.py")))
        self.edits.write_text("[]", encoding="utf-8")
        self.assertFalse(versions.assess(record, self.output)["reusable"])


if __name__ == "__main__":
    unittest.main()
