#!/usr/bin/env python
"""Build a clean master Word template for long-term default formatting."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

import pythoncom
import win32com.client.gencache
from win32com.client import constants


SKILL_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_TEMPLATE = SKILL_ROOT / "assets" / "master-default-template.docx"

STYLE_PARAGRAPH = 1


@contextmanager
def word_application():
    pythoncom.CoInitialize()
    app = None
    try:
        app = win32com.client.gencache.EnsureDispatch("Word.Application")
        app.Visible = False
        app.DisplayAlerts = 0
        app.ScreenUpdating = False
        yield app
    finally:
        if app is not None:
            try:
                app.ScreenUpdating = True
            except Exception:
                pass
            try:
                app.Quit(False)
            except Exception:
                pass
        pythoncom.CoUninitialize()


def ensure_style(doc, name: str, style_type: int = STYLE_PARAGRAPH):
    try:
        return doc.Styles(name)
    except Exception:
        return doc.Styles.Add(name, style_type)


def style_name(doc, style_ref) -> str:
    try:
        return doc.Styles(style_ref).NameLocal
    except Exception:
        return str(style_ref)


def set_font(font, *, name=None, name_ascii=None, name_far_east=None, size=None, bold=None):
    if name is not None:
        font.Name = name
    if name_ascii is not None:
        font.NameAscii = name_ascii
    if name_far_east is not None:
        font.NameFarEast = name_far_east
    if size is not None:
        font.Size = size
    if bold is not None:
        font.Bold = -1 if bold else 0


def set_paragraph_format(
    paragraph_format,
    *,
    alignment=None,
    before=None,
    after=None,
    line_rule=None,
    line_spacing=None,
    first_line_indent=None,
    keep_with_next=None,
    keep_together=None,
    page_break_before=None,
):
    if alignment is not None:
        paragraph_format.Alignment = alignment
    if before is not None:
        paragraph_format.SpaceBefore = before
    if after is not None:
        paragraph_format.SpaceAfter = after
    if line_rule is not None:
        paragraph_format.LineSpacingRule = line_rule
    if line_spacing is not None:
        paragraph_format.LineSpacing = line_spacing
    if first_line_indent is not None:
        paragraph_format.FirstLineIndent = first_line_indent
    if keep_with_next is not None:
        paragraph_format.KeepWithNext = -1 if keep_with_next else 0
    if keep_together is not None:
        paragraph_format.KeepTogether = -1 if keep_together else 0
    if page_break_before is not None:
        paragraph_format.PageBreakBefore = -1 if page_break_before else 0


def configure_style(doc, style_ref, **spec):
    style = doc.Styles(style_ref) if not isinstance(style_ref, str) else ensure_style(doc, style_ref)
    if spec.get("base_style") is not None:
        style.BaseStyle = spec["base_style"]
    if spec.get("next_style") is not None:
        style.NextParagraphStyle = spec["next_style"]
    set_font(
        style.Font,
        name=spec.get("font_name"),
        name_ascii=spec.get("font_ascii"),
        name_far_east=spec.get("font_far_east"),
        size=spec.get("font_size"),
        bold=spec.get("bold"),
    )
    set_paragraph_format(
        style.ParagraphFormat,
        alignment=spec.get("alignment"),
        before=spec.get("before"),
        after=spec.get("after"),
        line_rule=spec.get("line_rule"),
        line_spacing=spec.get("line_spacing"),
        first_line_indent=spec.get("first_line_indent"),
        keep_with_next=spec.get("keep_with_next"),
        keep_together=spec.get("keep_together"),
        page_break_before=spec.get("page_break_before"),
    )
    return style


def append_paragraph(doc, text: str, style_ref):
    insertion_range = doc.Range(doc.Content.End - 1, doc.Content.End - 1)
    insertion_range.InsertAfter(text)
    paragraph = doc.Paragraphs.Last
    paragraph.Range.Style = style_name(doc, style_ref)
    paragraph.Range.InsertParagraphAfter()
    return paragraph


def insert_page_break(doc):
    doc.Paragraphs.Last.Range.InsertBreak(constants.wdPageBreak)


def configure_page_setup(doc):
    section = doc.Sections(1)
    page_setup = section.PageSetup
    page_setup.PageWidth = 595.45
    page_setup.PageHeight = 841.7
    page_setup.TopMargin = 93.55
    page_setup.BottomMargin = 100.95
    page_setup.LeftMargin = 86.45
    page_setup.RightMargin = 79.1
    page_setup.HeaderDistance = 42.55
    page_setup.FooterDistance = 49.6
    page_setup.Gutter = 14.45
    page_setup.DifferentFirstPageHeaderFooter = True


def build_template():
    OUTPUT_TEMPLATE.parent.mkdir(parents=True, exist_ok=True)
    temp_output = OUTPUT_TEMPLATE.with_name(f"{OUTPUT_TEMPLATE.stem}.tmp.docx")
    with word_application() as app:
        doc = app.Documents.Add()
        try:
            configure_page_setup(doc)

            normal_name = style_name(doc, constants.wdStyleNormal)
            title_name = style_name(doc, constants.wdStyleTitle)
            heading_1_name = style_name(doc, constants.wdStyleHeading1)
            heading_2_name = style_name(doc, constants.wdStyleHeading2)
            heading_3_name = style_name(doc, constants.wdStyleHeading3)
            body_text_name = style_name(doc, constants.wdStyleBodyText)
            caption_name = style_name(doc, constants.wdStyleCaption)
            toc_1_name = style_name(doc, constants.wdStyleTOC1)
            toc_2_name = style_name(doc, constants.wdStyleTOC2)
            toc_3_name = style_name(doc, constants.wdStyleTOC3)

            configure_style(
                doc,
                constants.wdStyleTitle,
                base_style=normal_name,
                next_style=normal_name,
                font_name="FZXiaoBiaoSong-B05S",
                font_ascii="FZXiaoBiaoSong-B05S",
                font_far_east="FZXiaoBiaoSong-B05S",
                font_size=28,
                bold=False,
                alignment=constants.wdAlignParagraphCenter,
                before=0,
                after=18,
                line_rule=constants.wdLineSpaceExactly,
                line_spacing=28,
                first_line_indent=0,
            )
            configure_style(
                doc,
                constants.wdStyleNormal,
                next_style=normal_name,
                font_name="Times New Roman",
                font_ascii="Times New Roman",
                font_far_east="SimSun",
                font_size=10.5,
                bold=False,
                alignment=constants.wdAlignParagraphJustify,
                before=0,
                after=0,
                line_rule=constants.wdLineSpaceExactly,
                line_spacing=18,
                first_line_indent=21,
            )
            configure_style(
                doc,
                constants.wdStyleBodyText,
                base_style=normal_name,
                next_style=body_text_name,
                font_name="Times New Roman",
                font_ascii="Times New Roman",
                font_far_east="SimSun",
                font_size=10.5,
                bold=False,
                alignment=constants.wdAlignParagraphJustify,
                before=0,
                after=0,
                line_rule=constants.wdLineSpaceExactly,
                line_spacing=18,
                first_line_indent=21,
            )
            configure_style(
                doc,
                constants.wdStyleHeading1,
                base_style=normal_name,
                next_style=normal_name,
                font_name="SimHei",
                font_ascii="SimHei",
                font_far_east="SimHei",
                font_size=14,
                bold=False,
                alignment=constants.wdAlignParagraphLeft,
                before=18,
                after=0,
                line_rule=constants.wdLineSpaceExactly,
                line_spacing=18,
                first_line_indent=0,
                keep_with_next=True,
                keep_together=True,
            )
            configure_style(
                doc,
                constants.wdStyleHeading2,
                base_style=normal_name,
                next_style=normal_name,
                font_name="SimHei",
                font_ascii="SimHei",
                font_far_east="SimHei",
                font_size=10.5,
                bold=False,
                alignment=constants.wdAlignParagraphLeft,
                before=12,
                after=0,
                line_rule=constants.wdLineSpaceExactly,
                line_spacing=18,
                first_line_indent=0,
                keep_with_next=True,
                keep_together=True,
            )
            configure_style(
                doc,
                constants.wdStyleHeading3,
                base_style=normal_name,
                next_style=normal_name,
                font_name="KaiTi_GB2312",
                font_ascii="KaiTi_GB2312",
                font_far_east="KaiTi_GB2312",
                font_size=10.5,
                bold=True,
                alignment=constants.wdAlignParagraphLeft,
                before=12,
                after=0,
                line_rule=constants.wdLineSpaceExactly,
                line_spacing=18,
                first_line_indent=0,
                keep_with_next=True,
                keep_together=True,
            )
            configure_style(
                doc,
                constants.wdStyleCaption,
                base_style=normal_name,
                next_style=normal_name,
                font_name="Times New Roman",
                font_ascii="Times New Roman",
                font_far_east="SimHei",
                font_size=10.5,
                bold=False,
                alignment=constants.wdAlignParagraphCenter,
                before=12,
                after=12,
                line_rule=constants.wdLineSpaceExactly,
                line_spacing=18,
                first_line_indent=0,
            )
            configure_style(
                doc,
                constants.wdStyleTOC1,
                base_style=normal_name,
                next_style=toc_1_name,
                font_name="Times New Roman",
                font_ascii="Times New Roman",
                font_far_east="SimSun",
                font_size=10.5,
                bold=False,
                alignment=constants.wdAlignParagraphLeft,
                before=0,
                after=6,
                line_rule=constants.wdLineSpaceExactly,
                line_spacing=18,
                first_line_indent=0,
            )
            configure_style(doc, constants.wdStyleTOC2, base_style=normal_name, next_style=toc_2_name, font_name="Times New Roman", font_ascii="Times New Roman", font_far_east="SimSun", font_size=10.5, bold=False, alignment=constants.wdAlignParagraphLeft, before=0, after=3, line_rule=constants.wdLineSpaceExactly, line_spacing=18, first_line_indent=0)
            configure_style(doc, constants.wdStyleTOC3, base_style=normal_name, next_style=toc_3_name, font_name="Times New Roman", font_ascii="Times New Roman", font_far_east="SimSun", font_size=10.5, bold=False, alignment=constants.wdAlignParagraphLeft, before=0, after=3, line_rule=constants.wdLineSpaceExactly, line_spacing=18, first_line_indent=0)

            configure_style(
                doc,
                "Master Cover Field",
                base_style=normal_name,
                next_style="Master Cover Field",
                font_name="KaiTi_GB2312",
                font_ascii="KaiTi_GB2312",
                font_far_east="KaiTi_GB2312",
                font_size=14,
                bold=False,
                alignment=constants.wdAlignParagraphLeft,
                before=0,
                after=0,
                line_rule=constants.wdLineSpaceExactly,
                line_spacing=22,
                first_line_indent=0,
            )
            configure_style(doc, "Master Cover Signature", base_style=normal_name, next_style="Master Cover Signature", font_name="KaiTi_GB2312", font_ascii="KaiTi_GB2312", font_far_east="KaiTi_GB2312", font_size=14, bold=False, alignment=constants.wdAlignParagraphLeft, before=0, after=0, line_rule=constants.wdLineSpaceExactly, line_spacing=30, first_line_indent=0)
            configure_style(doc, "Master Cover Footer", base_style=normal_name, next_style=normal_name, font_name="KaiTi_GB2312", font_ascii="KaiTi_GB2312", font_far_east="KaiTi_GB2312", font_size=16, bold=False, alignment=constants.wdAlignParagraphCenter, before=0, after=0, line_rule=constants.wdLineSpaceExactly, line_spacing=23, first_line_indent=0)
            configure_style(doc, "Master TOC Title", base_style=heading_1_name, next_style=toc_1_name, font_name="SimHei", font_ascii="SimHei", font_far_east="SimHei", font_size=16, bold=False, alignment=constants.wdAlignParagraphCenter, before=18, after=18, line_rule=constants.wdLineSpaceExactly, line_spacing=24, first_line_indent=0)
            configure_style(doc, "Master Body", base_style=normal_name, next_style="Master Body", font_name="Times New Roman", font_ascii="Times New Roman", font_far_east="SimSun", font_size=10.5, bold=False, alignment=constants.wdAlignParagraphJustify, before=0, after=0, line_rule=constants.wdLineSpaceExactly, line_spacing=18, first_line_indent=21)
            configure_style(doc, "Master Body No Indent", base_style="Master Body", next_style="Master Body No Indent", font_name="Times New Roman", font_ascii="Times New Roman", font_far_east="SimSun", font_size=10.5, bold=False, alignment=constants.wdAlignParagraphJustify, before=0, after=0, line_rule=constants.wdLineSpaceExactly, line_spacing=18, first_line_indent=0)
            configure_style(doc, "Master Figure Caption", base_style=caption_name, next_style=normal_name, font_name="Times New Roman", font_ascii="Times New Roman", font_far_east="SimHei", font_size=10.5, bold=False, alignment=constants.wdAlignParagraphCenter, before=12, after=12, line_rule=constants.wdLineSpaceExactly, line_spacing=18, first_line_indent=0)
            configure_style(doc, "Master Table Caption", base_style=caption_name, next_style=normal_name, font_name="Times New Roman", font_ascii="Times New Roman", font_far_east="SimHei", font_size=10.5, bold=False, alignment=constants.wdAlignParagraphCenter, before=12, after=12, line_rule=constants.wdLineSpaceExactly, line_spacing=18, first_line_indent=0)
            configure_style(doc, "Master Table Text", base_style=normal_name, next_style="Master Table Text", font_name="Times New Roman", font_ascii="Times New Roman", font_far_east="SimSun", font_size=9, bold=False, alignment=constants.wdAlignParagraphCenter, before=0, after=0, line_rule=constants.wdLineSpaceExactly, line_spacing=12, first_line_indent=0)
            configure_style(doc, "Master Appendix Title", base_style=heading_1_name, next_style=normal_name, font_name="SimHei", font_ascii="SimHei", font_far_east="SimHei", font_size=14, bold=False, alignment=constants.wdAlignParagraphCenter, before=18, after=18, line_rule=constants.wdLineSpaceExactly, line_spacing=18, first_line_indent=0)
            configure_style(doc, "Master References Title", base_style=heading_1_name, next_style=normal_name, font_name="SimHei", font_ascii="SimHei", font_far_east="SimHei", font_size=14, bold=False, alignment=constants.wdAlignParagraphLeft, before=18, after=0, line_rule=constants.wdLineSpaceExactly, line_spacing=18, first_line_indent=0)
            configure_style(doc, "Master References Body", base_style=normal_name, next_style="Master References Body", font_name="Times New Roman", font_ascii="Times New Roman", font_far_east="SimSun", font_size=9, bold=False, alignment=constants.wdAlignParagraphLeft, before=0, after=0, line_rule=constants.wdLineSpaceExactly, line_spacing=18, first_line_indent=17)
            configure_style(doc, constants.wdStyleTitle, next_style="Master Cover Field", first_line_indent=0)
            configure_style(doc, constants.wdStyleHeading1, next_style="Master Body")
            configure_style(doc, constants.wdStyleHeading2, next_style="Master Body")
            configure_style(doc, constants.wdStyleHeading3, next_style="Master Body")

            append_paragraph(doc, "MASTER REPORT TITLE", title_name)
            append_paragraph(doc, "Contract Name: XXXXX", "Master Cover Field")
            append_paragraph(doc, "Project Lead: XXXXX", "Master Cover Signature")
            append_paragraph(doc, "Organization: XXXXX", "Master Cover Signature")
            append_paragraph(doc, "Date: YYYY-MM-DD", "Master Cover Signature")
            append_paragraph(doc, "XXXX ORGANIZATION", "Master Cover Footer")
            insert_page_break(doc)

            append_paragraph(doc, "TABLE OF CONTENTS", "Master TOC Title")
            append_paragraph(doc, "1. First-Level Heading\t1", toc_1_name)
            append_paragraph(doc, "1.1 Second-Level Heading\t2", toc_2_name)
            append_paragraph(doc, "1.1.1 Third-Level Heading\t3", toc_3_name)
            insert_page_break(doc)

            append_paragraph(doc, "1. First-Level Heading", heading_1_name)
            append_paragraph(doc, "This paragraph uses the default body style for the new master template.", "Master Body")
            append_paragraph(doc, "1.1 Second-Level Heading", heading_2_name)
            append_paragraph(doc, "This paragraph shows the indented body text style.", "Master Body")
            append_paragraph(doc, "1.1.1 Third-Level Heading", heading_3_name)
            append_paragraph(doc, "This paragraph uses the no-indent body style for summaries and notes.", "Master Body No Indent")
            append_paragraph(doc, "Figure 1. Example figure caption.", "Master Figure Caption")
            append_paragraph(doc, "Table 1. Example table caption.", "Master Table Caption")
            append_paragraph(doc, "Example table cell text", "Master Table Text")
            append_paragraph(doc, "Appendix A. Example appendix title", "Master Appendix Title")
            append_paragraph(doc, "References", "Master References Title")
            append_paragraph(doc, "[1] Example reference entry for the master template.", "Master References Body")

            doc.SaveAs2(
                str(temp_output),
                FileFormat=constants.wdFormatXMLDocument,
                AddToRecentFiles=False,
            )
        finally:
            doc.Close(False)
    if OUTPUT_TEMPLATE.exists():
        OUTPUT_TEMPLATE.unlink()
    temp_output.replace(OUTPUT_TEMPLATE)


def main():
    build_template()
    print(OUTPUT_TEMPLATE)


if __name__ == "__main__":
    main()
