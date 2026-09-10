"""Structural regressions from duplicate paragraph formatting in a text edit."""
from __future__ import annotations

import io
import subprocess
import sys
import tempfile
import unittest
import zipfile
from contextlib import redirect_stdout
from pathlib import Path

OFFICE_DIR = Path(__file__).parents[1] / "scripts" / "office"
sys.path.insert(0, str(OFFICE_DIR))
from validators.pptx import PPTXSchemaValidator

DML = "http://schemas.openxmlformats.org/drawingml/2006/main"


class TextFormatValidationTests(unittest.TestCase):
    def check(self, body, part="ppt/slides/slide1.xml", original=False):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "unpacked"
            path = root / part
            path.parent.mkdir(parents=True)
            content = f'<root xmlns:a="{DML}">{body}</root>'.encode()
            path.write_bytes(content)
            baseline = Path(temp) / "original.pptx"
            if original:
                with zipfile.ZipFile(baseline, "w") as archive:
                    archive.writestr(part, content)
            validator = PPTXSchemaValidator(root, baseline if original else None)
            output = io.StringIO()
            with redirect_stdout(output):
                valid = validator.validate_text_format_singletons()
            self.assertEqual(path.read_bytes(), content, "Validation must be read-only")
            return valid, output.getvalue()

    def test_all_singleton_locations_rejected_with_or_without_baseline(self):
        pairs = [("p", "pPr"), ("p", "endParaRPr"), ("fld", "pPr")]
        pairs += [(parent, "rPr") for parent in ("r", "br", "fld")]
        pairs += [(parent, "defRPr") for parent in (
            "pPr", "defPPr", *(f"lvl{i}pPr" for i in range(1, 10)))]
        for parent, child in pairs:
            for original in (False, True):
                with self.subTest(parent=parent, child=child, original=original):
                    valid, message = self.check(
                        f'<a:{parent}><a:{child}/><a:{child}/></a:{parent}>',
                        original=original,
                    )
                    self.assertFalse(valid)
                    self.assertIn("ppt/slides/slide1.xml", message)
                    self.assertIn(f"duplicate a:{child}", message)
                    self.assertIn(f"XPath: /root/a:{parent}/a:{child}[1]", message)

    def test_other_text_parts_are_checked(self):
        for directory in ("charts", "slideLayouts", "slideMasters", "notesSlides",
                          "notesMasters", "handoutMasters", "theme"):
            with self.subTest(directory=directory):
                self.assertFalse(self.check('<a:p><a:pPr/><a:pPr/></a:p>',
                                           f"ppt/{directory}/part1.xml")[0])

    def test_distinct_paragraphs_runs_and_levels_are_allowed(self):
        body = '<a:p><a:pPr><a:defRPr/></a:pPr><a:r><a:rPr/></a:r>'
        body += '<a:r><a:rPr/></a:r><a:endParaRPr/></a:p>'
        body += body
        body += '<a:lstStyle><a:lvl1pPr><a:defRPr/></a:lvl1pPr>'
        body += '<a:lvl2pPr><a:defRPr/></a:lvl2pPr></a:lstStyle>'
        self.assertTrue(self.check(body)[0])

    def test_namespace_and_direct_parent_scope(self):
        # Same local names from unrelated extensions and separate parents are not duplicates.
        self.assertTrue(self.check(
            '<x:p xmlns:x="urn:custom"><x:pPr/><x:pPr/></x:p>'
            '<a:p><a:pPr/><extension><a:pPr/></extension></a:p>'
        )[0])

    def test_minimal_package_cli_rejects_defect_even_in_original(self):
        from copy import deepcopy
        from lxml import etree
        from pptx import Presentation
        from pptx.util import Inches

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            clean, broken = root / "clean.pptx", root / "broken.pptx"
            presentation = Presentation()
            slide = presentation.slides.add_slide(presentation.slide_layouts[6])
            paragraph = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(5),
                                                 Inches(2)).text_frame.paragraphs[0]
            paragraph.text = "Short frame: 224,768 samples"
            paragraph.space_after = Inches(0)
            presentation.save(clean)
            with zipfile.ZipFile(clean) as source, zipfile.ZipFile(broken, "w") as target:
                for item in source.infolist():
                    content = source.read(item.filename)
                    if item.filename == "ppt/slides/slide1.xml":
                        xml = etree.fromstring(content)
                        ppr = xml.find(f".//{{{DML}}}pPr")
                        ppr.addnext(deepcopy(ppr))
                        content = etree.tostring(xml, xml_declaration=True, encoding="UTF-8")
                    target.writestr(item, content)
            for original in (None, clean, broken):
                for candidate, expected in ((broken, 1), (clean, 0)):
                    with self.subTest(candidate=candidate.name, original=original):
                        command = [sys.executable, "-X", "utf8", str(OFFICE_DIR / "validate.py"),
                                   str(candidate)]
                        if original:
                            command += ["--original", str(original)]
                        result = subprocess.run(command, capture_output=True, text=True,
                                                encoding="utf-8", timeout=60)
                        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
                        if expected:
                            self.assertIn("duplicate a:pPr", result.stdout)


if __name__ == "__main__":
    unittest.main()
