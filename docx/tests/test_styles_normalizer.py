from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

from lxml import etree


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = SKILL_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_ROOT))

from styles_normalizer import (  # noqa: E402
    MC_NS,
    W_NS,
    StylesNormalizationError,
    main,
    normalize_styles_xml,
    scan_production_style_writers,
    validate_styles_xml,
)


W = f"{{{W_NS}}}"
MC = f"{{{MC_NS}}}"


def styles_xml(*, nested_id: str = "Nested", duplicate: bool = False) -> bytes:
    root = etree.Element(f"{W}styles", nsmap={"w": W_NS, "mc": MC_NS})
    normal = etree.SubElement(root, f"{W}style")
    normal.set(f"{W}type", "paragraph")
    normal.set(f"{W}styleId", "Normal")
    etree.SubElement(normal, f"{W}name").set(f"{W}val", "Normal")

    alternate = etree.SubElement(root, f"{MC}AlternateContent")
    choice = etree.SubElement(alternate, f"{MC}Choice")
    choice.set("Requires", "w14")
    nested = etree.SubElement(choice, f"{W}style")
    nested.set(f"{W}type", "paragraph")
    nested.set(f"{W}styleId", "Normal" if duplicate else nested_id)
    etree.SubElement(nested, f"{W}name").set(f"{W}val", nested_id)
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8")


def paragraph_part(style_id: str) -> bytes:
    root = etree.Element(f"{W}document", nsmap={"w": W_NS})
    body = etree.SubElement(root, f"{W}body")
    paragraph = etree.SubElement(body, f"{W}p")
    properties = etree.SubElement(paragraph, f"{W}pPr")
    etree.SubElement(properties, f"{W}pStyle").set(f"{W}val", style_id)
    etree.SubElement(body, f"{W}sectPr")
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8")


class StylesNormalizerTests(unittest.TestCase):
    def test_nested_alternate_content_style_and_reference_are_valid(self) -> None:
        result = validate_styles_xml(
            styles_xml(),
            package_entries={"word/document.xml": paragraph_part("Nested")},
        )

        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["style_count"], 2)
        self.assertEqual(result["alternate_content"], 1)

    def test_duplicate_style_id_inside_alternate_content_is_rejected(self) -> None:
        with self.assertRaisesRegex(StylesNormalizationError, "Duplicate style definition: Normal"):
            validate_styles_xml(styles_xml(duplicate=True))

    def test_cross_part_unresolved_reference_is_rejected(self) -> None:
        with self.assertRaisesRegex(StylesNormalizationError, "word/header1.xml"):
            validate_styles_xml(
                styles_xml(),
                package_entries={"word/header1.xml": paragraph_part("Missing")},
            )

    def test_wrong_root_namespace_is_rejected(self) -> None:
        payload = b'<?xml version="1.0" encoding="UTF-8"?><styles><style/></styles>'
        with self.assertRaisesRegex(StylesNormalizationError, "root must be w:styles"):
            validate_styles_xml(payload)

    def test_normalization_preserves_outer_bytes_and_root_attribute_order(self) -> None:
        original = (
            b'<?xml version="1.0" encoding="UTF-8"?>\n<!-- <w:styles> lookalike -->\n '
            b'<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
            b'xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006" '
            b'xmlns:data="urn:example" mc:Ignorable="w14" data:marker="first=second">'
            b'<w:style w:type="paragraph" w:styleId="Normal"><w:name w:val="Normal"/></w:style>'
            b'</w:styles>\n<!-- </w:styles> lookalike -->\n'
        )
        candidate = original.replace(b'w:val="Normal"', b'w:val="Updated"').replace(
            b'data:marker="first=second"', b'data:marker="third=fourth"'
        )

        normalized = normalize_styles_xml(original, candidate)

        self.assertTrue(
            normalized.startswith(b'<?xml version="1.0" encoding="UTF-8"?>\n<!-- <w:styles> lookalike -->\n ')
        )
        self.assertTrue(normalized.endswith(b'</w:styles>\n<!-- </w:styles> lookalike -->\n'))
        self.assertIn(
            b'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
            b'xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006" '
            b'xmlns:data="urn:example" mc:Ignorable="w14" data:marker="third=fourth"',
            normalized,
        )
        self.assertEqual(normalize_styles_xml(original, original), original)

    def test_normalization_rejects_moving_a_style_out_of_alternate_content(self) -> None:
        original = styles_xml()
        candidate_root = etree.fromstring(original)
        nested = candidate_root.find(f"{MC}AlternateContent/{MC}Choice/{W}style")
        assert nested is not None
        nested.getparent().remove(nested)
        candidate_root.append(nested)
        candidate = etree.tostring(candidate_root, xml_declaration=True, encoding="UTF-8")

        with self.assertRaisesRegex(StylesNormalizationError, "AlternateContent structure changed"):
            normalize_styles_xml(original, candidate)

    def test_ast_scan_detects_builtin_open_and_ignores_read_only_access(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "writer.py").write_text(
                'target = "word/styles.xml"\nopen(target, mode="wb")\n',
                encoding="utf-8",
            )
            (root / "direct_writer.py").write_text(
                'entries["word/styles.xml"] = payload\n',
                encoding="utf-8",
            )
            (root / "path_writer.py").write_text(
                'from pathlib import Path\nPath("word/styles.xml").write_bytes(b"payload")\n',
                encoding="utf-8",
            )
            (root / "reader.py").write_text('open("word/styles.xml", "rb")\n', encoding="utf-8")

            violations = scan_production_style_writers(root)

        self.assertEqual([violation["kind"] for violation in violations], ["subscript", "write_bytes", "open"])
        self.assertTrue(violations[0]["path"].endswith("direct_writer.py"))
        self.assertTrue(violations[1]["path"].endswith("path_writer.py"))
        self.assertTrue(violations[2]["path"].endswith("writer.py"))

    def test_production_writer_registry_and_cli_are_clean(self) -> None:
        self.assertEqual(scan_production_style_writers(SCRIPTS_ROOT), [])
        self.assertEqual(main(["--scripts-root", str(SCRIPTS_ROOT)]), 0)


if __name__ == "__main__":
    unittest.main()
