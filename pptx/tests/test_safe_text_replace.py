import sys
import unittest
from copy import deepcopy
from pathlib import Path

from pptx import Presentation
from pptx.enum.text import PP_ALIGN
from pptx.oxml.xmlchemy import OxmlElement
from pptx.oxml.ns import qn
from pptx.util import Inches, Pt

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
from safe_text_replace import replace_text, UnsafeTextStructureError


class SafeTextReplaceTests(unittest.TestCase):
    def setUp(self):
        self.prs = Presentation()
        slide = self.prs.slides.add_slide(self.prs.slide_layouts[6])
        self.shape = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(5), Inches(2))
        self.other = slide.shapes.add_textbox(Inches(1), Inches(4), Inches(5), Inches(1))
        self.other.text = "untouched"
        self.frame = self.shape.text_frame
        p = self.frame.paragraphs[0]
        p.alignment = PP_ALIGN.CENTER
        p.space_after = Pt(6)
        p.level = 2
        p.font.size = Pt(20)
        p._p.get_or_add_pPr().append(OxmlElement("a:buNone"))
        run = p.add_run()
        run.text = "original"
        run.font.name = "Arial"
        run.font.size = Pt(22)
        run.font.bold = True
        second = p.add_run()
        second.text = "mixed"
        second.font.italic = True
        p._p.append(OxmlElement("a:endParaRPr"))

    def test_repeated_replacement_preserves_format_and_other_shape(self):
        other_xml = self.other._element.xml
        ppr = self.frame.paragraphs[0]._p.pPr.xml
        rpr = self.frame.paragraphs[0].runs[0]._r.rPr.xml
        for _ in range(5):
            replace_text(self.shape, "new text")
            p = self.frame.paragraphs[0]
            self.assertEqual(p._p.pPr.xml, ppr)
            self.assertEqual(p.runs[0]._r.rPr.xml, rpr)
            self.assertEqual(len(p._p.findall(qn("a:pPr"))), 1)
            self.assertEqual(len(p.runs), 1)
            self.assertEqual(len(p.runs[0]._r.findall(qn("a:rPr"))), 1)
            self.assertEqual(p._p[-1].tag, qn("a:endParaRPr"))
        self.assertEqual(self.other._element.xml, other_xml)

    def test_multiline_and_added_paragraphs(self):
        p = self.frame.add_paragraph()
        p.alignment = PP_ALIGN.RIGHT
        p.add_run().text = "second"
        p.runs[0].font.italic = True
        replace_text(self.frame, "one\vtwo\nthree\nfour")
        self.assertEqual(self.frame.text, "one\vtwo\nthree\nfour")
        self.assertEqual(self.frame.paragraphs[0].alignment, PP_ALIGN.CENTER)
        self.assertEqual(self.frame.paragraphs[1].alignment, PP_ALIGN.RIGHT)
        self.assertEqual(self.frame.paragraphs[2].alignment, PP_ALIGN.RIGHT)
        self.assertTrue(self.frame.paragraphs[2].runs[0].font.italic)

    def test_empty_text_keeps_paragraph_properties(self):
        replace_text(self.frame, "")
        self.assertEqual(self.frame.text, "")
        self.assertEqual(len(self.frame.paragraphs), 1)
        self.assertEqual(self.frame.paragraphs[0].alignment, PP_ALIGN.CENTER)
        replace_text(self.frame, "restored")
        self.assertTrue(self.frame.paragraphs[0].runs[0].font.bold)
        self.assertEqual(self.frame.paragraphs[0].runs[0].font.size, Pt(22))

    def test_duplicate_format_rejected_without_mutation(self):
        for kind in ("pPr", "rPr", "defRPr", "endParaRPr"):
            with self.subTest(kind=kind):
                self.setUp()
                p = self.frame.paragraphs[0]._p
                node = next(p.iter(qn("a:" + kind)))
                node.addnext(deepcopy(node))
                before = self.shape._element.xml
                with self.assertRaises(UnsafeTextStructureError):
                    replace_text(self.shape, "replacement")
                self.assertEqual(before, self.shape._element.xml)

    def test_invalid_literal_leaves_target_unchanged(self):
        before = self.shape._element.xml
        with self.assertRaises(ValueError):
            replace_text(self.frame, "valid\ninvalid\x00")
        self.assertEqual(before, self.shape._element.xml)

    def test_round_trip(self):
        import io
        replace_text(self.shape, "中文结果\nsecond paragraph")
        buffer = io.BytesIO()
        self.prs.save(buffer)
        buffer.seek(0)
        loaded = Presentation(buffer)
        self.assertEqual(loaded.slides[0].shapes[0].text, "中文结果\nsecond paragraph")


if __name__ == "__main__":
    unittest.main()
