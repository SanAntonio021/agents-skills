#!/usr/bin/env python
"""Install the master template as Word's global blank-document template."""

from __future__ import annotations

import argparse
import gc
import shutil
import time
from datetime import datetime
from pathlib import Path

import pythoncom
import win32com.client
from win32com.client import constants

from word_template_formatter import (
    DEFAULT_PRESET,
    PRESET_PATHS,
    apply_page_setup,
    open_document,
    word_application,
)


DEFAULT_NORMAL_TEMPLATE = Path.home() / "AppData" / "Roaming" / "Microsoft" / "Templates" / "Normal.dotm"


def running_word_instance_present() -> bool:
    pythoncom.CoInitialize()
    try:
        try:
            app = win32com.client.GetActiveObject("Word.Application")
        except Exception:
            return False
        try:
            return True if app is not None else False
        finally:
            app = None
    finally:
        pythoncom.CoUninitialize()


def backup_normal_template(normal_template: Path) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = normal_template.with_name(f"Normal.codex-backup-{timestamp}.dotm")
    if normal_template.exists():
        shutil.copy2(normal_template, backup_path)
    return backup_path


def install_template(template_path: Path, normal_template: Path) -> Path:
    normal_template.parent.mkdir(parents=True, exist_ok=True)
    backup_path = backup_normal_template(normal_template)
    temp_output = normal_template.with_name(f"{normal_template.stem}.codex-new.dotm")
    if temp_output.exists():
        temp_output.unlink()
    format_macro_template = getattr(constants, "wdFormatXMLTemplateMacroEnabled", 15)

    with word_application() as app:
        template_doc = open_document(app, template_path, read_only=True)
        normal_doc = app.Documents.Add(Visible=False)
        try:
            normal_doc.CopyStylesFromTemplate(str(template_path))
            apply_page_setup(template_doc, normal_doc, "first-section")
            normal_doc.SaveAs2(
                FileName=str(temp_output),
                FileFormat=format_macro_template,
                AddToRecentFiles=False,
            )
        finally:
            try:
                normal_doc.Close(False)
            finally:
                template_doc.Close(False)
        normal_doc = None
        template_doc = None
    gc.collect()
    last_error = None
    for _ in range(10):
        try:
            if normal_template.exists():
                normal_template.unlink()
            temp_output.replace(normal_template)
            return backup_path
        except PermissionError as exc:
            last_error = exc
            time.sleep(0.5)
    if last_error is not None:
        raise last_error
    return backup_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Install the master default template into Word's Normal.dotm."
    )
    parser.add_argument(
        "--template",
        type=Path,
        default=PRESET_PATHS[DEFAULT_PRESET]["template"],
        help="Source DOCX template. Defaults to the current default preset.",
    )
    parser.add_argument(
        "--normal-template",
        type=Path,
        default=DEFAULT_NORMAL_TEMPLATE,
        help="Path to Normal.dotm.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    template_path = args.template.expanduser().resolve()
    normal_template = args.normal_template.expanduser().resolve()

    if running_word_instance_present():
        raise SystemExit(
            "Word is currently running. Close all Word windows before installing the global blank template."
        )
    if not template_path.exists():
        raise SystemExit(f"Template not found: {template_path}")
    if template_path.suffix.lower() != ".docx":
        raise SystemExit(f"Template must be a .docx file: {template_path}")

    backup_path = install_template(template_path, normal_template)
    print(f"Installed blank-document template: {normal_template}")
    if backup_path.exists():
        print(f"Backup written: {backup_path}")
    else:
        print("No previous Normal.dotm existed; no backup was needed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
