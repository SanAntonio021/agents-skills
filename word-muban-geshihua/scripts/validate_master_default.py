#!/usr/bin/env python
"""Validate that the default preset resolves to the generated master template."""

from __future__ import annotations

import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path

import pythoncom
import win32com.client.gencache
from win32com.client import constants


SKILL_ROOT = Path(__file__).resolve().parents[1]
FORMATTER_SCRIPT = SKILL_ROOT / "scripts" / "word_template_formatter.py"
TMP_DIR = SKILL_ROOT / "tmp"
INPUT_PATH = TMP_DIR / "master-default-validation-input.docx"
OUTPUT_PATH = TMP_DIR / "master-default-validation-output.docx"


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


def style_name(style_ref) -> str:
    try:
        return style_ref.NameLocal
    except Exception:
        return str(style_ref)


def add_paragraph(doc, text: str, style_ref) -> None:
    insertion_range = doc.Range(doc.Content.End - 1, doc.Content.End - 1)
    insertion_range.InsertAfter(text)
    doc.Paragraphs.Last.Range.Style = style_name(style_ref)
    doc.Paragraphs.Last.Range.InsertParagraphAfter()


def create_input_document() -> None:
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    for path in (INPUT_PATH, OUTPUT_PATH):
        if path.exists():
            path.unlink()

    with word_application() as app:
        doc = app.Documents.Add()
        try:
            add_paragraph(doc, "Validation Document", doc.Styles(constants.wdStyleTitle))
            add_paragraph(doc, "1. First Heading", doc.Styles(constants.wdStyleHeading1))
            add_paragraph(doc, "This is body text before formatting.", doc.Styles(constants.wdStyleNormal))
            add_paragraph(doc, "1.1 Second Heading", doc.Styles(constants.wdStyleHeading2))
            add_paragraph(doc, "Another paragraph for style transfer validation.", doc.Styles(constants.wdStyleNormal))
            doc.SaveAs2(
                str(INPUT_PATH),
                FileFormat=constants.wdFormatXMLDocument,
                AddToRecentFiles=False,
            )
        finally:
            doc.Close(False)


def run_formatter() -> str:
    result = subprocess.run(
        [sys.executable, str(FORMATTER_SCRIPT), "apply", "--input", str(INPUT_PATH), "--output", str(OUTPUT_PATH)],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def inspect_output() -> list[str]:
    lines: list[str] = []
    with word_application() as app:
        doc = app.Documents.Open(
            FileName=str(OUTPUT_PATH),
            ConfirmConversions=False,
            ReadOnly=True,
            AddToRecentFiles=False,
            Visible=False,
        )
        try:
            setup = doc.Sections(1).PageSetup
            lines.append(
                "page top={:.2f} bottom={:.2f} left={:.2f} right={:.2f} gutter={:.2f} first_page={}".format(
                    setup.TopMargin,
                    setup.BottomMargin,
                    setup.LeftMargin,
                    setup.RightMargin,
                    setup.Gutter,
                    bool(setup.DifferentFirstPageHeaderFooter),
                )
            )
            for index in range(1, min(doc.Paragraphs.Count, 6) + 1):
                paragraph = doc.Paragraphs(index)
                text = paragraph.Range.Text.replace("\r", "").replace("\x07", "").strip()
                if not text:
                    continue
                lines.append(
                    "paragraph {}: {} => {}".format(
                        index,
                        style_name(paragraph.Range.Style),
                        text,
                    )
                )
        finally:
            doc.Close(False)
    return lines


def main() -> int:
    create_input_document()
    print(run_formatter())
    for line in inspect_output():
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
