from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = SKILL_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from libreoffice_headless import convert, find_soffice  # noqa: E402
from merge_formula_caches import merge_caches  # noqa: E402
from ooxml_common import (  # noqa: E402
    MAIN_NS,
    has_formula_cache,
    load_package,
    parse_xml,
    qn,
    resolve_sheet_parts,
    serialize_xml,
    worksheet_cells,
    write_package,
)
from patch_ooxml import patch_workbook  # noqa: E402
from verify_pdf import inspect_pdf  # noqa: E402
from verify_xlsx import compare_workbooks, inspect_workbook  # noqa: E402


class WorkbookToolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(prefix="xlsx-skill-test-")
        self.root = Path(self.temp_dir.name)
        self.source = self.root / "source.xlsx"
        self._build_workbook(self.source)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    @staticmethod
    def _build_workbook(path: Path) -> None:
        from openpyxl import Workbook
        from openpyxl.chart import BarChart, Reference
        from openpyxl.comments import Comment
        from openpyxl.worksheet.datavalidation import DataValidation

        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Template"
        sheet["A1"] = "Audit workbook"
        sheet.merge_cells("A1:E1")
        sheet["B2"] = "Old value"
        sheet["C2"] = 1
        sheet["D2"] = 2
        sheet["E2"] = "=SUM(C2:D2)"
        sheet["B2"].comment = Comment("Keep this comment", "Tester")
        validation = DataValidation(type="list", formula1='"Domestic,Imported"')
        sheet.add_data_validation(validation)
        validation.add("F2:F3")
        sheet.row_dimensions[2].height = 20
        sheet.page_setup.orientation = "landscape"
        sheet.page_setup.fitToWidth = 1
        sheet.page_setup.fitToHeight = 0
        sheet.print_area = "A1:J5"
        sheet.print_title_rows = "1:1"
        chart = BarChart()
        chart.add_data(Reference(sheet, min_col=3, max_col=4, min_row=2, max_row=2))
        sheet.add_chart(chart, "H2")
        workbook.save(path)

    def test_targeted_patch_and_policy(self) -> None:
        output = self.root / "patched.xlsx"
        spec = {
            "sheets": {
                "Template": {
                    "cells": {"B2": {"kind": "string", "value": "New value"}},
                    "row_heights": {"2": 30},
                    "data_validation": {
                        "require_count": 1,
                        "index": 0,
                        "sqref": "F2:F4",
                    },
                    "page_setup": {"fitToHeight": "1", "fitToPage": True},
                    "row_breaks": [2],
                    "print_area": "$A$1:$J$6",
                    "print_titles": "$1:$2",
                }
            }
        }
        patch_workbook(self.source, output, spec, allow_new_cells=False)

        baseline = inspect_workbook(self.source)
        current = inspect_workbook(output)
        protected = [
            name
            for name in baseline["package_entries"]
            if name.startswith("xl/drawings/")
            or name.startswith("xl/comments")
            or name.startswith("xl/media/")
            or name == "xl/styles.xml"
        ]
        policy = {
            "allowed_cells": ["Template!B2"],
            "allowed_row_heights": ["Template!2"],
            "allowed_sheet_features": [
                "Template!data_validations",
                "Template!page_setup",
                "Template!sheet_properties",
                "Template!row_breaks",
                "Workbook!defined_names",
            ],
            "required_unchanged_entries": protected,
            "allow_formula_cache_changes": False,
            "expected": {
                "formula_count": 1,
                "formula_cache_count": 0,
                "formula_error_count": 0,
            },
        }
        comparison = compare_workbooks(baseline, current, policy)
        self.assertTrue(comparison["ok"], json.dumps(comparison, indent=2))
        self.assertEqual(current["sheets"]["Template"]["cells"]["B2"]["value"], "New value")
        self.assertTrue(current["defined_names"])
        self.assertIn("$A$1:$J$6", json.dumps(current["defined_names"]))
        for name in protected:
            self.assertEqual(
                baseline["package_entries"][name], current["package_entries"][name]
            )
        with self.assertRaises(FileExistsError):
            patch_workbook(self.source, output, spec, allow_new_cells=False)

    def test_formula_cache_merge(self) -> None:
        recalc = self.root / "recalculated.xlsx"
        final = self.root / "final.xlsx"
        source_inspection = inspect_workbook(self.source)
        self.assertEqual(source_inspection["formula_count"], 1)
        self.assertEqual(source_inspection["formula_cache_count"], 0)
        entries, _, _ = load_package(self.source)
        part = resolve_sheet_parts(entries)["Template"]
        root = parse_xml(entries[part])
        formula_cell = worksheet_cells(root)["E2"]
        value = formula_cell.find(qn(MAIN_NS, "v"))
        if value is None:
            value = formula_cell.makeelement(qn(MAIN_NS, "v"), {})
            formula_cell.append(value)
        value.text = "3"
        write_package(self.source, recalc, {part: serialize_xml(root)})

        report = merge_caches(self.source, recalc, final)
        self.assertEqual(report["formula_count"], 1)
        self.assertEqual(report["formula_cache_count"], 1)
        inspected = inspect_workbook(final)
        formula = inspected["sheets"]["Template"]["cells"]["E2"]
        self.assertEqual(formula["cached"], "3")
        self.assertEqual(inspected["formula_error_count"], 0)

    def test_empty_numeric_formula_cache_is_rejected(self) -> None:
        final = self.root / "must-not-exist-empty-cache.xlsx"
        entries, _, _ = load_package(self.source)
        part = resolve_sheet_parts(entries)["Template"]
        root = parse_xml(entries[part])
        formula_cell = worksheet_cells(root)["E2"]
        self.assertFalse(has_formula_cache(formula_cell))

        with self.assertRaises(ValueError):
            merge_caches(self.source, self.source, final)
        self.assertFalse(final.exists())

    def test_empty_string_formula_cache_is_valid(self) -> None:
        recalc = self.root / "recalculated-empty-string.xlsx"
        final = self.root / "final-empty-string.xlsx"
        entries, _, _ = load_package(self.source)
        part = resolve_sheet_parts(entries)["Template"]
        root = parse_xml(entries[part])
        formula_cell = worksheet_cells(root)["E2"]
        formula_cell.attrib["t"] = "str"
        value = formula_cell.find(qn(MAIN_NS, "v"))
        if value is None:
            value = formula_cell.makeelement(qn(MAIN_NS, "v"), {})
            formula_cell.append(value)
        value.text = None
        self.assertTrue(has_formula_cache(formula_cell))
        write_package(self.source, recalc, {part: serialize_xml(root)})

        report = merge_caches(self.source, recalc, final)
        self.assertEqual(report["formula_cache_count"], 1)
        inspected = inspect_workbook(final)
        self.assertEqual(inspected["formula_cache_count"], 1)
        self.assertEqual(inspected["sheets"]["Template"]["cells"]["E2"]["cached"], "")

    def test_formula_error_cache_is_rejected(self) -> None:
        recalc = self.root / "recalculated-error.xlsx"
        final = self.root / "must-not-exist.xlsx"
        entries, _, _ = load_package(self.source)
        part = resolve_sheet_parts(entries)["Template"]
        root = parse_xml(entries[part])
        formula_cell = worksheet_cells(root)["E2"]
        value = formula_cell.find(qn(MAIN_NS, "v"))
        if value is None:
            value = formula_cell.makeelement(qn(MAIN_NS, "v"), {})
            formula_cell.append(value)
        formula_cell.attrib["t"] = "e"
        value.text = "#REF!"
        write_package(self.source, recalc, {part: serialize_xml(root)})

        with self.assertRaises(ValueError):
            merge_caches(self.source, recalc, final)
        self.assertFalse(final.exists())

    def test_policy_rejects_unapproved_cell(self) -> None:
        output = self.root / "unexpected.xlsx"
        spec = {
            "sheets": {
                "Template": {
                    "cells": {
                        "B2": {"kind": "string", "value": "Allowed"},
                        "C2": {"kind": "number", "value": 99},
                    }
                }
            }
        }
        patch_workbook(self.source, output, spec, allow_new_cells=False)
        comparison = compare_workbooks(
            inspect_workbook(self.source),
            inspect_workbook(output),
            {"allowed_cells": ["Template!B2"]},
        )
        self.assertFalse(comparison["ok"])
        self.assertEqual(comparison["unexpected"]["cells"][0]["cell"], "Template!C2")

    def test_libreoffice_recalc_when_available(self) -> None:
        if os.environ.get("RUN_LIBREOFFICE_INTEGRATION") != "1":
            self.skipTest("Set RUN_LIBREOFFICE_INTEGRATION=1 to start LibreOffice")
        try:
            soffice = find_soffice(None)
        except FileNotFoundError:
            self.skipTest("LibreOffice is not installed")
        output = self.root / "lo-recalculated.xlsx"
        convert("recalc", self.source, output, soffice, timeout=120)
        inspected = inspect_workbook(output)
        self.assertEqual(inspected["formula_count"], 1)
        self.assertEqual(inspected["formula_cache_count"], 1)
        self.assertEqual(inspected["formula_error_count"], 0)

    def test_pdf_read_only_checks(self) -> None:
        try:
            from reportlab.lib.pagesizes import A4, landscape
            from reportlab.pdfgen import canvas
        except ImportError:
            self.skipTest("reportlab is not installed")
        pdf = self.root / "sample.pdf"
        writer = canvas.Canvas(str(pdf), pagesize=landscape(A4))
        for page_number in (1, 2):
            writer.drawString(40, 40, f"Required footer - page {page_number}")
            writer.showPage()
        writer.save()
        report = inspect_pdf(
            pdf,
            expected_pages=2,
            orientation="landscape",
            expect_every_page=["Required footer"],
            expect_document=["page 2"],
            min_text_chars=1,
        )
        self.assertTrue(report["ok"], json.dumps(report, indent=2))
        self.assertTrue(report["visual_inspection_required"])


class SkillStructureTests(unittest.TestCase):
    def test_required_files_exist(self) -> None:
        required = [
            "SKILL.md",
            "references/general-workflow.md",
            "references/formatting-and-formulas.md",
            "references/high-fidelity-workflow.md",
            "references/patch-spec.md",
            "scripts/patch_ooxml.py",
            "scripts/libreoffice_headless.py",
            "scripts/merge_formula_caches.py",
            "scripts/verify_xlsx.py",
            "scripts/verify_pdf.py",
            "evals/evals.json",
        ]
        for relative in required:
            self.assertTrue((SKILL_ROOT / relative).is_file(), relative)

    def test_skill_is_complete_xlsx_entry(self) -> None:
        skill_text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("name: xlsx", skill_text)
        self.assertIn("这是完整的表格技能", skill_text)
        self.assertNotIn("xlsx-" + "preserve-ooxml", skill_text)
        self.assertNotIn("不使用本 " + "skill", skill_text)

    def test_eval_json_is_valid(self) -> None:
        data = json.loads((SKILL_ROOT / "evals" / "evals.json").read_text(encoding="utf-8"))
        self.assertEqual(data["skill_name"], "xlsx")
        self.assertGreaterEqual(len(data["evals"]), 8)

        triggers = json.loads(
            (SKILL_ROOT / "evals" / "trigger-evals.json").read_text(encoding="utf-8")
        )
        self.assertEqual(len(triggers), 20)
        self.assertEqual(sum(item["should_trigger"] for item in triggers), 10)


if __name__ == "__main__":
    unittest.main()
