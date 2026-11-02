"""Independent Word-semantics tests for the read-only static layout auditor.

Fixtures are small python-docx packages with explicit OOXML, not documents or
property-merging helpers taken from the implementation. Only audit() and the
CLI are exercised. No Office process is required or started.

Set LAYOUT_AUDIT_TEST_ARTIFACTS to retain each test's package and CLI inputs.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from docx import Document
from lxml import etree


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import layout_audit  # noqa: E402


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W = "{" + W_NS + "}"
NS = {"w": W_NS}
SCRIPT = SCRIPTS / "layout_audit.py"


def xml_nodes(fragment):
    return list(etree.fromstring(
        ('<w:root xmlns:w="' + W_NS + '">' + fragment + '</w:root>').encode("utf-8")
    ))


def put_properties(parent, tag, fragment):
    old = parent.find(W + tag)
    if old is not None:
        parent.remove(old)
    props = etree.Element(W + tag)
    props.extend(xml_nodes(fragment))
    parent.insert(0, props)
    return props


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class LayoutAuditTests(unittest.TestCase):
    def setUp(self):
        artifact_root = os.environ.get("LAYOUT_AUDIT_TEST_ARTIFACTS")
        if artifact_root:
            Path(artifact_root).mkdir(parents=True, exist_ok=True)
            self.root = Path(tempfile.mkdtemp(prefix=self._testMethodName + "_", dir=artifact_root))
        else:
            temporary = tempfile.TemporaryDirectory(prefix="layout_audit_test_")
            self.addCleanup(temporary.cleanup)
            self.root = Path(temporary.name)
        self.path = self.root / "input.docx"
        self.doc = Document()
        self.styles = self.doc.styles.element
        for child in list(self.styles):
            self.styles.remove(child)
        self.styles.extend(xml_nodes(
            '<w:docDefaults><w:rPrDefault><w:rPr>'
            '<w:rFonts w:ascii="Arial" w:eastAsia="宋体"/>'
            '<w:sz w:val="24"/>'
            '</w:rPr></w:rPrDefault><w:pPrDefault><w:pPr>'
            '<w:spacing w:after="120"/>'
            '</w:pPr></w:pPrDefault></w:docDefaults>'
            '<w:style w:type="paragraph" w:default="1" w:styleId="Normal">'
            '<w:name w:val="Normal"/></w:style>'
        ))
        self.numbering = self.doc.part.numbering_part.element
        for child in list(self.numbering):
            self.numbering.remove(child)
        self.page_size(11906, 16838)

    def style(self, sid, *, based_on=None, kind="paragraph", p="", r=""):
        style = etree.SubElement(self.styles, W + "style", {
            W + "type": kind, W + "styleId": sid,
        })
        etree.SubElement(style, W + "name", {W + "val": sid})
        if based_on:
            etree.SubElement(style, W + "basedOn", {W + "val": based_on})
        if p:
            props = etree.SubElement(style, W + "pPr")
            props.extend(xml_nodes(p))
        if r:
            props = etree.SubElement(style, W + "rPr")
            props.extend(xml_nodes(r))
        return style

    def paragraph(self, text="Probe", *, style=None, p="", r=""):
        paragraph = self.doc.add_paragraph()
        style_xml = '<w:pStyle w:val="' + style + '"/>' if style else ""
        if style_xml or p:
            put_properties(paragraph._p, "pPr", style_xml + p)
        run = paragraph.add_run(text)
        if r:
            put_properties(run._r, "rPr", r)
        return paragraph

    def page_size(self, width, height, *, landscape=False):
        section = self.doc.sections[-1]._sectPr
        size = section.find(W + "pgSz")
        if size is None:
            size = etree.SubElement(section, W + "pgSz")
        size.set(W + "w", str(width))
        size.set(W + "h", str(height))
        if landscape:
            size.set(W + "orient", "landscape")

    def abstract_numbering(self, aid=40, *, start=1, p=""):
        abstract = etree.SubElement(self.numbering, W + "abstractNum", {W + "abstractNumId": str(aid)})
        etree.SubElement(abstract, W + "multiLevelType", {W + "val": "singleLevel"})
        level = etree.SubElement(abstract, W + "lvl", {W + "ilvl": "0"})
        level.extend(xml_nodes(
            '<w:start w:val="' + str(start) + '"/>'
            '<w:numFmt w:val="decimal"/><w:lvlText w:val="%1."/>'
        ))
        if p:
            props = etree.SubElement(level, W + "pPr")
            props.extend(xml_nodes(p))
        return abstract

    def number_instance(self, nid, aid=40, *, start_override=None, replacement_start=None):
        instance = etree.SubElement(self.numbering, W + "num", {W + "numId": str(nid)})
        etree.SubElement(instance, W + "abstractNumId", {W + "val": str(aid)})
        if start_override is not None or replacement_start is not None:
            override = etree.SubElement(instance, W + "lvlOverride", {W + "ilvl": "0"})
            if start_override is not None:
                etree.SubElement(override, W + "startOverride", {W + "val": str(start_override)})
            if replacement_start is not None:
                level = etree.SubElement(override, W + "lvl", {W + "ilvl": "0"})
                level.extend(xml_nodes(
                    '<w:start w:val="' + str(replacement_start) + '"/>'
                    '<w:numFmt w:val="decimal"/><w:lvlText w:val="%1."/>'
                ))
        return instance

    def numbered(self, nid, text="Item", *, style=None, extra=""):
        return self.paragraph(text, style=style, p=(
            '<w:numPr><w:ilvl w:val="0"/><w:numId w:val="' + str(nid) + '"/></w:numPr>' + extra
        ))

    @staticmethod
    def paragraph_rules(expected, *, select=None, **bounds):
        return {"schema": 1, "paragraph_rules": [{
            "name": "probe", "select": {"text": "Probe"} if select is None else select,
            "expect": expected, **bounds,
        }]}

    @staticmethod
    def group_rules(counts, *, start=1, select=None):
        return {"schema": 1, "numbering_groups": [{
            "name": "lists", "select": {"text_regex": "^Item"} if select is None else select,
            "counts": counts, "start": start,
        }]}

    def save(self):
        self.doc.save(self.path)
        return self.path

    def audit(self, rules):
        path = self.save()
        # A retained rules file makes failing fixtures independently replayable.
        (self.root / "rules.json").write_text(json.dumps(rules, ensure_ascii=False, indent=2), encoding="utf-8")
        report = layout_audit.audit(path, rules)
        path.with_suffix(".audit.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        return report

    def assert_pass(self, rules):
        report = self.audit(rules)
        self.assertEqual(report["status"], "STATIC_PASS", json.dumps(report, ensure_ascii=False, indent=2))
        self.assertEqual(report["findings"], [])
        return report

    def assert_fail(self, rules):
        report = self.audit(rules)
        self.assertEqual(report["status"], "STATIC_FAIL", json.dumps(report, ensure_ascii=False, indent=2))
        self.assertTrue(report["findings"])
        return report

    def cli(self, rules=None, *, report=None):
        if not self.path.exists():
            self.save()
        rule_path = self.root / "rules.json"
        if rules is not None:
            rule_path.write_text(json.dumps(rules, ensure_ascii=False, indent=2), encoding="utf-8")
        command = [sys.executable, "-B", "-X", "utf8", str(SCRIPT), str(self.path), "--rules", str(rule_path)]
        if report is not None:
            command.extend(["--report", str(report)])
        environment = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", timeout=30,
                                cwd=self.root, env=environment)
        (self.root / "cli-output.txt").write_text(
            subprocess.list2cmdline(command) + "\nexit=" + str(result.returncode) +
            "\nSTDOUT\n" + result.stdout + "\nSTDERR\n" + result.stderr, encoding="utf-8")
        return result

    # Word applies each property through the hierarchy, not whole-property blocks.
    def test_paragraph_inherits_document_defaults_and_based_on_chain(self):
        self.style("Base", based_on="Normal", p='<w:jc w:val="both"/><w:spacing w:before="240"/>',
                   r='<w:rFonts w:eastAsia="仿宋"/><w:sz w:val="28"/>')
        self.style("Child", based_on="Base", p='<w:spacing w:after="60"/>')
        self.paragraph(style="Child")
        self.assert_pass(self.paragraph_rules({"alignment": "both", "before_pt": 12,
            "after_pt": 3, "font_ascii": "Arial", "font_east_asia": "仿宋", "size_pt": 14}))

    def test_partial_direct_spacing_keeps_unrelated_inherited_attributes(self):
        self.style("Body", based_on="Normal", p='<w:spacing w:before="200" w:after="160" w:line="480" w:lineRule="exact"/>')
        self.paragraph(style="Body", p='<w:spacing w:after="40"/>')
        self.assert_pass(self.paragraph_rules({"before_pt": 10, "after_pt": 2, "line": 480, "line_rule": "exact"}))

    def test_character_style_overrides_paragraph_run_properties(self):
        self.style("Body", based_on="Normal", r='<w:rFonts w:ascii="Georgia"/><w:sz w:val="28"/>')
        self.style("Emphasis", kind="character", r='<w:rFonts w:ascii="Consolas"/><w:sz w:val="20"/>')
        self.paragraph(style="Body", r='<w:rStyle w:val="Emphasis"/>')
        self.assert_pass(self.paragraph_rules({"font_ascii": "Consolas", "size_pt": 10, "font_east_asia": "宋体"}))

    def test_direct_run_format_overrides_character_style(self):
        self.style("Small", kind="character", r='<w:sz w:val="18"/>')
        self.paragraph(r='<w:rStyle w:val="Small"/><w:sz w:val="32"/>')
        self.assert_pass(self.paragraph_rules({"size_pt": 16}))

    def test_every_text_run_is_checked_and_mismatch_has_location(self):
        paragraph = self.paragraph("Good")
        bad = paragraph.add_run("Bad")
        put_properties(bad._r, "rPr", '<w:sz w:val="20"/>')
        report = self.assert_fail(self.paragraph_rules({"size_pt": 12}, select={"text": "GoodBad"}))
        issue = next(f for f in report["findings"] if f.get("property") == "size_pt")
        self.assertEqual(issue["actual"], 10)
        self.assertEqual(issue["part"], "word/document.xml")
        self.assertTrue(issue["xpath"])
        self.assertEqual(issue["text"], "GoodBad")

    def test_direct_explicit_ascii_font_overrides_inherited_theme(self):
        self.style("Themed", based_on="Normal", r='<w:rFonts w:asciiTheme="minorHAnsi"/>')
        self.paragraph(style="Themed", r='<w:rFonts w:ascii="Consolas"/>')
        self.assert_pass(self.paragraph_rules({"font_ascii": "Consolas"}))

    def test_child_explicit_east_asian_font_overrides_parent_theme(self):
        self.style("Themed", based_on="Normal", r='<w:rFonts w:eastAsiaTheme="majorEastAsia"/>')
        self.style("Explicit", based_on="Themed", r='<w:rFonts w:eastAsia="仿宋"/>')
        self.paragraph("Probe汉字", style="Explicit")
        self.assert_pass(self.paragraph_rules({"font_east_asia": "仿宋"}, select={"text": "Probe汉字"}))

    def test_theme_in_same_font_element_beats_explicit_font(self):
        self.paragraph(r='<w:rFonts w:ascii="Consolas" w:asciiTheme="majorHAnsi"/>')
        report = self.assert_fail(self.paragraph_rules({"font_ascii": "Consolas"}))
        actual = next(f["actual"] for f in report["findings"] if f.get("property") == "font_ascii")
        self.assertIsInstance(actual, dict)
        self.assertEqual(actual.get("theme"), "majorHAnsi")

    def test_direct_font_change_does_not_erase_other_language_slot(self):
        self.style("Mixed", based_on="Normal", r='<w:rFonts w:ascii="Georgia" w:eastAsia="黑体"/>')
        self.paragraph(style="Mixed", r='<w:rFonts w:ascii="Consolas"/>')
        self.assert_pass(self.paragraph_rules({"font_ascii": "Consolas", "font_east_asia": "黑体"}))

    def test_direct_theme_replaces_inherited_explicit_family(self):
        self.paragraph(r='<w:rFonts w:asciiTheme="minorHAnsi"/>')
        self.assert_fail(self.paragraph_rules({"font_ascii": "Arial"}))

    def test_two_true_bold_style_toggles_cancel(self):
        self.style("BaseBold", based_on="Normal", r='<w:b/>')
        self.style("ToggleAgain", based_on="BaseBold", r='<w:b/>')
        self.paragraph(style="ToggleAgain")
        self.assert_pass(self.paragraph_rules({"bold": False}))

    def test_false_bold_in_style_does_not_clear_inherited_bold(self):
        self.style("BaseBold", based_on="Normal", r='<w:b/>')
        self.style("NoToggle", based_on="BaseBold", r='<w:b w:val="false"/>')
        self.paragraph(style="NoToggle")
        self.assert_pass(self.paragraph_rules({"bold": True}))

    def test_character_style_bold_toggles_paragraph_style_bold(self):
        self.style("BoldParagraph", based_on="Normal", r='<w:b/>')
        self.style("BoldCharacter", kind="character", r='<w:b/>')
        self.paragraph(style="BoldParagraph", r='<w:rStyle w:val="BoldCharacter"/>')
        self.assert_pass(self.paragraph_rules({"bold": False}))

    def test_direct_bold_true_sets_absolute_true_after_two_style_toggles(self):
        self.style("BaseBold", based_on="Normal", r='<w:b/>')
        self.style("Cancel", based_on="BaseBold", r='<w:b/>')
        self.paragraph(style="Cancel", r='<w:b w:val="true"/>')
        self.assert_pass(self.paragraph_rules({"bold": True}))

    def test_direct_bold_false_sets_absolute_false(self):
        self.style("BaseBold", based_on="Normal", r='<w:b/>')
        self.paragraph(style="BaseBold", r='<w:b w:val="0"/>')
        self.assert_pass(self.paragraph_rules({"bold": False}))

    def test_bold_toggle_handles_all_true_lexical_forms_in_document_defaults(self):
        default_rpr = self.styles.find("w:docDefaults/w:rPrDefault/w:rPr", NS)
        bold = etree.SubElement(default_rpr, W + "b")
        self.style("Toggle", based_on="Normal", r='<w:b/>')
        self.paragraph(style="Toggle")
        for spelling in ("1", "true", "on"):
            with self.subTest(spelling=spelling):
                self.path = self.root / ("input_" + spelling + ".docx")
                bold.set(W + "val", spelling)
                self.assert_pass(self.paragraph_rules({"bold": False}))

    def test_numid_zero_cancels_style_numbering_without_looking_up_zero(self):
        self.abstract_numbering(p='<w:ind w:left="720"/>')
        self.number_instance(51)
        self.style("List", based_on="Normal", p='<w:numPr><w:ilvl w:val="0"/><w:numId w:val="51"/></w:numPr>')
        self.paragraph(style="List", p='<w:numPr><w:numId w:val="0"/></w:numPr><w:ind w:left="0"/>')
        self.assert_pass(self.paragraph_rules({"left_pt": 0, "size_pt": 12}))

    def test_numid_zero_reports_missing_auto_numbering_when_rule_requires_it(self):
        self.numbered(0)
        report = self.assert_fail(self.group_rules([1]))
        self.assertTrue(any(f.get("problem") == "missing_auto_numbering" for f in report["findings"]))

    def test_distinct_numids_share_abstract_but_start_separate_groups(self):
        self.abstract_numbering()
        self.number_instance(51)
        self.number_instance(52)
        for nid in (51, 51, 52, 52, 52):
            self.numbered(nid)
        report = self.assert_pass(self.group_rules([2, 3]))
        self.assertEqual(report["checks"][0]["groups"], [2, 3])

    def test_unnumbered_separator_does_not_restart_same_number_instance(self):
        self.abstract_numbering()
        self.number_instance(51)
        self.numbered(51)
        self.paragraph("Separator")
        self.numbered(51)
        self.assert_pass(self.group_rules([2]))

    def test_start_override_takes_priority_over_abstract_and_replacement_level(self):
        self.abstract_numbering(start=9)
        self.number_instance(51, replacement_start=4, start_override=1)
        self.numbered(51)
        self.assert_pass(self.group_rules([1], start=1))

    def test_replacement_level_start_used_without_start_override(self):
        self.abstract_numbering(start=9)
        self.number_instance(51, replacement_start=3)
        self.numbered(51)
        self.assert_pass(self.group_rules([1], start=3))

    def test_wrong_start_is_checked_for_each_independent_number_instance(self):
        self.abstract_numbering()
        self.number_instance(51)
        self.number_instance(52, start_override=5)
        self.numbered(51)
        self.numbered(52)
        report = self.assert_fail(self.group_rules([1, 1]))
        issues = [f for f in report["findings"] if f.get("problem") == "wrong_start"]
        self.assertEqual(len(issues), 1)
        self.assertEqual(str(issues[0]["num_id"]), "52")
        self.assertEqual(issues[0]["actual"], 5)

    def test_number_group_count_mismatch_is_not_pass(self):
        self.abstract_numbering()
        self.number_instance(51)
        self.numbered(51)
        self.assert_fail(self.group_rules([2]))

    def test_paragraph_style_indent_overrides_numbering_level_indent(self):
        # ISO 29500 formatting hierarchy: numbering precedes paragraph styles.
        self.abstract_numbering(p='<w:ind w:left="720" w:hanging="360"/>')
        self.number_instance(51)
        self.style("ListBody", based_on="Normal", p='<w:ind w:left="1440"/>')
        self.numbered(51, text="Probe", style="ListBody")
        self.assert_pass(self.paragraph_rules({"left_pt": 72, "hanging_pt": 18}))

    def test_direct_indent_overrides_numbering_level_indent(self):
        self.abstract_numbering(p='<w:ind w:left="720" w:hanging="360"/>')
        self.number_instance(51)
        self.numbered(51, text="Probe", extra='<w:ind w:left="1800"/>')
        self.assert_pass(self.paragraph_rules({"left_pt": 90, "hanging_pt": 18}))

    def table(self, *, span=False, width_error=False, overflow=False, skip_edges=False):
        # Fixed preferred widths form an explicit grid-consistency policy fixture.
        if skip_edges:
            row = ('<w:tr><w:trPr><w:gridBefore w:val="1"/><w:gridAfter w:val="1"/></w:trPr>'
                   '<w:tc><w:tcPr><w:tcW w:w="2000" w:type="dxa"/></w:tcPr><w:p/></w:tc></w:tr>')
            widths = (1000, 2000, 3000)
        elif span:
            row = ('<w:tr><w:tc><w:tcPr><w:tcW w:w="3000" w:type="dxa"/>'
                   '<w:gridSpan w:val="' + ("3" if overflow else "2") + '"/></w:tcPr><w:p/></w:tc></w:tr>')
            widths = (1000, 2000)
        else:
            row = ('<w:tr><w:tc><w:tcPr><w:tcW w:w="' + ("900" if width_error else "1000") + '" w:type="dxa"/></w:tcPr><w:p/></w:tc>'
                   '<w:tc><w:tcPr><w:tcW w:w="2000" w:type="dxa"/></w:tcPr><w:p/></w:tc></w:tr>')
            widths = (1000, 2000)
        grid = "".join('<w:gridCol w:w="' + str(width) + '"/>' for width in widths)
        table = xml_nodes('<w:tbl><w:tblPr><w:tblW w:w="' + str(sum(widths)) + '" w:type="dxa"/>'
                          '<w:tblLayout w:type="fixed"/></w:tblPr><w:tblGrid>' + grid + '</w:tblGrid>' + row + '</w:tbl>')[0]
        self.doc.element.body.insert(0, table)
        return table

    def test_consistent_table_grid_passes(self):
        self.table()
        self.assert_pass({"schema": 1, "table_grid": True})

    def test_merged_cell_width_is_sum_of_spanned_grid_columns(self):
        self.table(span=True)
        self.assert_pass({"schema": 1, "table_grid": True})

    def test_table_grid_before_and_after_are_valid_omitted_cells(self):
        self.table(skip_edges=True)
        self.assert_pass({"schema": 1, "table_grid": True})

    def test_table_cell_width_mismatch_is_detected(self):
        self.table(width_error=True)
        report = self.assert_fail({"schema": 1, "table_grid": True})
        self.assertTrue(any(f.get("problem") == "cell_width_grid_mismatch" for f in report["findings"]))

    def test_table_grid_span_overflow_is_detected(self):
        self.table(span=True, overflow=True)
        self.assert_fail({"schema": 1, "table_grid": True})

    def test_a4_portrait_passes_without_claiming_rendered_layout(self):
        self.paragraph()
        report = self.assert_pass({"schema": 1, "a4": True})
        self.assertEqual(report["layout_status"], "NOT_CHECKED")

    def test_a4_landscape_accepts_swapped_dimensions(self):
        self.page_size(16838, 11906, landscape=True)
        self.assert_pass({"schema": 1, "a4": True})

    def test_letter_page_is_not_a4(self):
        self.page_size(12240, 15840)
        self.assert_fail({"schema": 1, "a4": True})

    def test_a4_checks_all_sections(self):
        from docx.enum.section import WD_SECTION_START
        self.paragraph()
        self.doc.add_section(WD_SECTION_START.NEW_PAGE)
        self.page_size(12240, 15840)
        report = self.assert_fail({"schema": 1, "a4": True})
        issues = [f for f in report["findings"] if f["rule"] == "A4"]
        self.assertEqual([f["section"] for f in issues], [2])

    def test_missing_page_size_cannot_establish_a4(self):
        section = self.doc.sections[-1]._sectPr
        section.remove(section.find(W + "pgSz"))
        self.assert_fail({"schema": 1, "a4": True})

    def test_absent_section_properties_cannot_establish_a4(self):
        self.paragraph()
        body = self.doc.element.body
        body.remove(body.find(W + "sectPr"))
        self.assert_fail({"schema": 1, "a4": True})

    def test_zero_matching_paragraphs_fail_by_default(self):
        self.paragraph()
        report = self.assert_fail(self.paragraph_rules({"size_pt": 12}, select={"text": "Absent"}))
        self.assertTrue(any(f.get("problem") == "match_count" and f.get("actual") == 0 for f in report["findings"]))

    def test_explicit_optional_rule_may_match_zero_paragraphs(self):
        self.paragraph()
        self.assert_pass(self.paragraph_rules({"size_pt": 12}, select={"text": "Absent"}, min=0))

    def test_zero_matching_number_group_does_not_pass(self):
        self.paragraph()
        self.assert_fail(self.group_rules([]))

    def test_empty_or_disabled_rule_sets_are_rejected(self):
        self.paragraph()
        for rules in ({"schema": 1}, {"schema": 1, "paragraph_rules": []},
                      {"schema": 1, "a4": False, "table_grid": False, "numbering_groups": []}):
            with self.subTest(rules=rules), self.assertRaises(ValueError):
                self.audit(rules)

    def test_empty_paragraph_expectation_is_rejected(self):
        self.paragraph()
        with self.assertRaises(ValueError):
            self.audit(self.paragraph_rules({}))

    def test_unsupported_property_is_rejected(self):
        self.paragraph()
        with self.assertRaises(ValueError):
            self.audit(self.paragraph_rules({"font_size": 12}))

    def test_unknown_selector_is_rejected(self):
        self.paragraph()
        with self.assertRaises(ValueError):
            self.audit(self.paragraph_rules({"size_pt": 12}, select={"styel": "Normal"}))

    def test_source_hash_unchanged_for_passing_and_failing_audits(self):
        self.paragraph()
        self.save()
        before = self.path.read_bytes()
        fingerprint = sha256(self.path)
        for wanted, expected_status in ((12, "STATIC_PASS"), (48, "STATIC_FAIL")):
            with self.subTest(wanted=wanted):
                report = layout_audit.audit(self.path, self.paragraph_rules({"size_pt": wanted}))
                self.assertEqual(report["status"], expected_status)
                self.assertEqual(report["source_sha256"], fingerprint)
                self.assertTrue(report["source_unchanged"])
                self.assertEqual(self.path.read_bytes(), before)

    def test_source_hash_unchanged_when_rules_rejected(self):
        self.paragraph()
        self.save()
        fingerprint = sha256(self.path)
        with self.assertRaises(ValueError):
            layout_audit.audit(self.path, self.paragraph_rules({}))
        self.assertEqual(sha256(self.path), fingerprint)

    def test_cli_new_report_and_source_and_rules_hashes(self):
        self.paragraph("Probe汉字")
        rules = self.paragraph_rules({"size_pt": 12}, select={"text": "Probe汉字"})
        self.save()
        original = self.path.read_bytes()
        report_path = self.root / "new-report.json"
        result = self.cli(rules, report=report_path)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        disk = json.loads(report_path.read_text(encoding="utf-8"))
        self.assertEqual(disk, json.loads(result.stdout))
        self.assertEqual(disk["source_sha256"], hashlib.sha256(original).hexdigest())
        self.assertEqual(disk["rules_sha256"], sha256(self.root / "rules.json"))
        self.assertEqual(self.path.read_bytes(), original)

    def test_cli_failed_check_returns_one_and_still_writes_report(self):
        self.paragraph()
        report_path = self.root / "failed-report.json"
        result = self.cli(self.paragraph_rules({"size_pt": 48}), report=report_path)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertEqual(json.loads(report_path.read_text(encoding="utf-8"))["status"], "STATIC_FAIL")

    def test_cli_empty_rules_are_error_and_do_not_create_report(self):
        self.paragraph()
        report_path = self.root / "must-not-exist.json"
        result = self.cli({"schema": 1}, report=report_path)
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"], "ERROR")
        self.assertFalse(report_path.exists())

    def test_cli_report_cannot_overwrite_input_even_with_dot_alias(self):
        self.paragraph()
        self.save()
        original = self.path.read_bytes()
        alias = str(self.root) + os.sep + "." + os.sep + self.path.name
        result = self.cli(self.paragraph_rules({"size_pt": 12}), report=alias)
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertEqual(self.path.read_bytes(), original)

    def test_cli_report_cannot_overwrite_rules(self):
        self.paragraph()
        rules_path = self.root / "rules.json"
        rules = self.paragraph_rules({"size_pt": 12})
        rules_path.write_text(json.dumps(rules), encoding="utf-8")
        original = rules_path.read_bytes()
        result = self.cli(report=rules_path)
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertEqual(rules_path.read_bytes(), original)

    def test_cli_report_cannot_overwrite_existing_report(self):
        self.paragraph()
        report_path = self.root / "existing.json"
        sentinel = b"previous report must survive\r\n"
        report_path.write_bytes(sentinel)
        result = self.cli(self.paragraph_rules({"size_pt": 12}), report=report_path)
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertEqual(report_path.read_bytes(), sentinel)

    def test_cli_report_hardlink_cannot_change_source(self):
        self.paragraph()
        self.save()
        original = self.path.read_bytes()
        alias = self.root / "input-hardlink.json"
        try:
            os.link(self.path, alias)
        except OSError as exc:
            self.skipTest("Filesystem does not support hardlinks: " + str(exc))
        result = self.cli(self.paragraph_rules({"size_pt": 12}), report=alias)
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(alias.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
