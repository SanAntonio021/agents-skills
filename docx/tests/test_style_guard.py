from __future__ import annotations

import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

from lxml import etree


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = SKILL_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from style_guard import (  # noqa: E402
    M_NS,
    W_NS,
    DocxPackage,
    audit_docx,
    remap_docx,
)


W = f"{{{W_NS}}}"
M = f"{{{M_NS}}}"


def build_styles(
    specifications: list[dict[str, object]],
) -> bytes:
    root = etree.Element(f"{W}styles", nsmap={"w": W_NS})
    for specification in specifications:
        style = etree.SubElement(root, f"{W}style")
        style.set(f"{W}type", str(specification.get("type", "paragraph")))
        style.set(f"{W}styleId", str(specification["id"]))
        if specification.get("default"):
            style.set(f"{W}default", "1")
        if specification.get("custom"):
            style.set(f"{W}customStyle", "1")

        name = etree.SubElement(style, f"{W}name")
        name.set(f"{W}val", str(specification["name"]))
        if specification.get("based_on"):
            based_on = etree.SubElement(style, f"{W}basedOn")
            based_on.set(f"{W}val", str(specification["based_on"]))
        if specification.get("next"):
            next_style = etree.SubElement(style, f"{W}next")
            next_style.set(f"{W}val", str(specification["next"]))
        if specification.get("quick"):
            etree.SubElement(style, f"{W}qFormat")

        paragraph_properties = etree.SubElement(style, f"{W}pPr")
        spacing = etree.SubElement(paragraph_properties, f"{W}spacing")
        spacing.set(f"{W}before", str(specification.get("before", 0)))
        run_properties = etree.SubElement(style, f"{W}rPr")
        size = etree.SubElement(run_properties, f"{W}sz")
        size.set(f"{W}val", str(specification.get("size", 20)))
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8")


def build_document(
    paragraphs: list[dict[str, object]],
    include_equation: bool = False,
) -> bytes:
    root = etree.Element(
        f"{W}document",
        nsmap={"w": W_NS, "m": M_NS},
    )
    body = etree.SubElement(root, f"{W}body")
    for index, specification in enumerate(paragraphs):
        paragraph = etree.SubElement(body, f"{W}p")
        properties = etree.SubElement(paragraph, f"{W}pPr")
        if specification.get("style"):
            style = etree.SubElement(properties, f"{W}pStyle")
            style.set(f"{W}val", str(specification["style"]))
        if specification.get("paragraph_bold"):
            paragraph_mark = etree.SubElement(properties, f"{W}rPr")
            etree.SubElement(paragraph_mark, f"{W}b")
        run = etree.SubElement(paragraph, f"{W}r")
        if specification.get("bold"):
            run_properties = etree.SubElement(run, f"{W}rPr")
            etree.SubElement(run_properties, f"{W}b")
        text = etree.SubElement(run, f"{W}t")
        text.text = str(specification.get("text", ""))
        if include_equation and index == 0:
            equation = etree.SubElement(paragraph, f"{M}oMath")
            math_run = etree.SubElement(equation, f"{M}r")
            math_text = etree.SubElement(math_run, f"{M}t")
            math_text.text = "x+y"
    etree.SubElement(body, f"{W}sectPr")
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8")


def write_docx(
    path: Path,
    styles: bytes,
    document: bytes,
    media: bytes = b"fixture-image",
) -> None:
    content_types = b"""<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
</Types>"""
    relationships = b"""<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>"""
    numbering = (
        f'<?xml version="1.0" encoding="UTF-8"?>'
        f'<w:numbering xmlns:w="{W_NS}"/>'.encode("utf-8")
    )
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", relationships)
        archive.writestr("word/document.xml", document)
        archive.writestr("word/styles.xml", styles)
        archive.writestr("word/numbering.xml", numbering)
        archive.writestr("word/_rels/document.xml.rels", relationships)
        archive.writestr("word/media/image1.png", media)


class StyleAuditTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp_dir.name)
        self.base_styles = build_styles(
            [
                {
                    "id": "Normal",
                    "name": "Normal",
                    "default": True,
                },
                {"id": "Body", "name": "Body", "custom": True, "before": 20},
            ]
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_content_replacement_does_not_add_styles(self) -> None:
        baseline = self.directory / "baseline.docx"
        candidate = self.directory / "candidate.docx"
        write_docx(
            baseline,
            self.base_styles,
            build_document([{"style": "Body", "text": "Old text"}]),
        )
        write_docx(
            candidate,
            self.base_styles,
            build_document([{"style": "Body", "text": "New text"}]),
        )

        report = audit_docx(baseline, candidate)

        self.assertTrue(report["ok"])
        self.assertEqual(report["violations"], {})

    def test_new_style_is_blocked_and_reported_as_orphan(self) -> None:
        baseline = self.directory / "baseline.docx"
        candidate = self.directory / "candidate.docx"
        candidate_styles = build_styles(
            [
                {
                    "id": "Normal",
                    "name": "Normal",
                    "default": True,
                },
                {"id": "Body", "name": "Body", "custom": True, "before": 20},
                {"id": "ParallelBody", "name": "Parallel Body", "custom": True},
            ]
        )
        document = build_document([{"style": "Body", "text": "Same text"}])
        write_docx(baseline, self.base_styles, document)
        write_docx(candidate, candidate_styles, document)

        report = audit_docx(baseline, candidate)

        self.assertFalse(report["ok"])
        self.assertEqual(report["violations"]["added_styles"], ["ParallelBody"])
        self.assertEqual(
            report["violations"]["new_orphan_styles"], ["ParallelBody"]
        )

    def test_paragraph_style_change_is_blocked(self) -> None:
        baseline = self.directory / "baseline.docx"
        candidate = self.directory / "candidate.docx"
        styles = build_styles(
            [
                {"id": "Normal", "name": "Normal", "default": True},
                {"id": "Body", "name": "Body", "custom": True},
                {"id": "Other", "name": "Other", "custom": True},
            ]
        )
        write_docx(
            baseline,
            styles,
            build_document([{"style": "Body", "text": "Same text"}]),
        )
        write_docx(
            candidate,
            styles,
            build_document([{"style": "Other", "text": "Same text"}]),
        )

        report = audit_docx(baseline, candidate)

        self.assertFalse(report["ok"])
        self.assertIn("paragraph_style_changes", report["violations"])

    def test_direct_formatting_drift_is_blocked(self) -> None:
        baseline = self.directory / "baseline.docx"
        candidate = self.directory / "candidate.docx"
        write_docx(
            baseline,
            self.base_styles,
            build_document([{"style": "Body", "text": "Same text"}]),
        )
        write_docx(
            candidate,
            self.base_styles,
            build_document(
                [{"style": "Body", "text": "Same text", "bold": True}]
            ),
        )

        report = audit_docx(baseline, candidate)

        self.assertFalse(report["ok"])
        self.assertIn("direct_formatting_drift", report["violations"])

    def test_approved_existing_style_definition_change_is_allowed(self) -> None:
        baseline = self.directory / "baseline.docx"
        candidate = self.directory / "candidate.docx"
        changed_styles = build_styles(
            [
                {
                    "id": "Normal",
                    "name": "Normal",
                    "default": True,
                },
                {"id": "Body", "name": "Body", "custom": True, "before": 30},
            ]
        )
        document = build_document([{"style": "Body", "text": "Same text"}])
        write_docx(baseline, self.base_styles, document)
        write_docx(candidate, changed_styles, document)

        blocked = audit_docx(baseline, candidate)
        allowed = audit_docx(
            baseline, candidate, allowed_style_changes={"Body"}
        )

        self.assertFalse(blocked["ok"])
        self.assertTrue(allowed["ok"])


class StyleRemapTests(unittest.TestCase):
    MAPPING = {
        "ProposalBody": "Normal",
        "ProposalHeading1": "1",
        "ProposalHeading2": "2",
        "ProposalHeading3": "3",
        "ProposalHeading4": "4",
        "ProposalEquation": "af0",
        "ProposalCaption": "a4",
        "ProposalReference": "001",
    }
    NAMES = {
        "Normal": "Normal",
        "1": "heading 1",
        "2": "heading 2",
        "3": "heading 3",
        "4": "heading 4",
        "af0": "公式",
        "a4": "caption",
        "001": "00正文1",
    }
    NEXT = {
        "Normal": "Normal",
        "1": "Normal",
        "2": "Normal",
        "3": "Normal",
        "4": "Normal",
        "af0": "Normal",
        "a4": "Normal",
        "001": "001",
    }

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp_dir.name)
        self.source = self.directory / "source.docx"
        self.template = self.directory / "template.docx"
        self.output = self.directory / "output.docx"

        source_specifications: list[dict[str, object]] = [
            {"id": "Normal", "name": "Normal", "default": True}
        ]
        for index, old_id in enumerate(self.MAPPING, start=1):
            source_specifications.append(
                {
                    "id": old_id,
                    "name": old_id,
                    "custom": True,
                    "before": index * 11,
                    "size": 20 + index,
                    "next": "ProposalBody" if "Heading" in old_id else None,
                }
            )
        for target_id in ("1", "2", "3", "4", "a4"):
            source_specifications.append(
                {
                    "id": target_id,
                    "name": f"wrong-{target_id}",
                    "before": 999,
                    "size": 99,
                }
            )

        template_specifications: list[dict[str, object]] = []
        for target_id, name in self.NAMES.items():
            template_specifications.append(
                {
                    "id": target_id,
                    "name": name,
                    "default": target_id == "Normal",
                    "custom": target_id in {"af0", "001"},
                    "quick": target_id in {"1", "2", "3", "4", "a4"},
                    "before": 777,
                    "size": 77,
                    "based_on": None if target_id == "Normal" else "Normal",
                }
            )

        paragraphs = [
            {"style": old_id, "text": f"text-{index}"}
            for index, old_id in enumerate(self.MAPPING, start=1)
        ]
        write_docx(
            self.source,
            build_styles(source_specifications),
            build_document(paragraphs, include_equation=True),
            media=b"unchanged-image",
        )
        write_docx(
            self.template,
            build_styles(template_specifications),
            build_document([{"style": "Normal", "text": "template"}]),
            media=b"template-image",
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_chinese_template_identities_keep_source_layout(self) -> None:
        report = remap_docx(
            self.source,
            self.template,
            self.output,
            self.MAPPING,
            self.NEXT,
        )

        self.assertTrue(report["ok"])
        self.assertTrue(report["style_audit"]["ok"])
        self.assertTrue(all(report["invariants"]["checks"].values()))
        for target_id, expected_name in self.NAMES.items():
            self.assertEqual(
                report["target_styles"][target_id]["name"], expected_name
            )
            self.assertEqual(
                report["target_styles"][target_id]["next_style"],
                self.NEXT[target_id],
            )

        package = DocxPackage.from_path(self.output)
        styles_root = etree.fromstring(package.entries["word/styles.xml"])
        styles = {
            style.get(f"{W}styleId"): style
            for style in styles_root.findall(f"{W}style")
        }
        for index, (old_id, target_id) in enumerate(self.MAPPING.items(), start=1):
            self.assertNotIn(old_id, styles)
            target = styles[target_id]
            self.assertEqual(target.find(f"{W}name").get(f"{W}val"), self.NAMES[target_id])
            self.assertEqual(
                target.find(f"{W}pPr/{W}spacing").get(f"{W}before"),
                str(index * 11),
            )
            self.assertEqual(
                target.find(f"{W}rPr/{W}sz").get(f"{W}val"),
                str(20 + index),
            )
        self.assertEqual(styles["Normal"].get(f"{W}default"), "1")

    def test_old_styles_are_deleted_only_after_all_references_move(self) -> None:
        remap_docx(
            self.source,
            self.template,
            self.output,
            self.MAPPING,
            self.NEXT,
        )

        package = DocxPackage.from_path(self.output)
        for payload in package.entries.values():
            for old_id in self.MAPPING:
                self.assertNotIn(old_id.encode("utf-8"), payload)
        with zipfile.ZipFile(self.source) as before, zipfile.ZipFile(self.output) as after:
            self.assertEqual(
                before.read("word/media/image1.png"),
                after.read("word/media/image1.png"),
            )
            self.assertEqual(
                before.read("word/numbering.xml"),
                after.read("word/numbering.xml"),
            )
            self.assertEqual(
                before.read("word/_rels/document.xml.rels"),
                after.read("word/_rels/document.xml.rels"),
            )

    def test_output_is_never_overwritten(self) -> None:
        self.output.write_bytes(b"existing")

        with self.assertRaises(FileExistsError):
            remap_docx(
                self.source,
                self.template,
                self.output,
                self.MAPPING,
                self.NEXT,
            )
        self.assertEqual(self.output.read_bytes(), b"existing")


if __name__ == "__main__":
    unittest.main()
