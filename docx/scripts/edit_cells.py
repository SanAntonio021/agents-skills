#!/usr/bin/env python3
"""Inspect, apply and check text edits inside labelled table cells of a DOCX form.

Application forms usually keep each section as a table row: the first cell holds the
label (for example a column title) and another cell holds the body paragraphs. This tool
edits that body cell directly in the OOXML package, without OfficeCLI, Word or LibreOffice.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import re
import sys
import tempfile
import zipfile
from pathlib import Path

from lxml import etree

import document_versions as versions
import edit_paragraphs as paragraphs_tool
import style_guard as guard

W = guard.W
PART = paragraphs_tool.PART
OPS = {"replace_cell", "replace_text"}
XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"
PLAIN_RUN_CHILDREN = {W + "rPr", W + "t"}


def normalize_label(text: str) -> str:
    return re.sub(r"\s+", "", text)


def cell_text(cell: etree._Element) -> str:
    return "".join(paragraphs_tool.text_of(p) for p in cell.findall(W + "p"))


def labelled_rows(root: etree._Element) -> list[tuple[str, etree._Element]]:
    rows = []
    for row in root.iter(W + "tr"):
        cells = row.findall(W + "tc")
        if len(cells) >= 2:
            rows.append((normalize_label(cell_text(cells[0])), row))
    return rows


def plain_paragraph_reason(paragraph: etree._Element) -> str | None:
    """Return why a cell paragraph cannot be rewritten as plain text, or None."""
    if any(child.tag not in {W + "pPr", W + "r"} for child in paragraph):
        return "Formula, hyperlink, revision, bookmark or other structured paragraph content"
    properties = paragraph.find(W + "pPr")
    if properties is not None and any(
            node.tag in {W + "sectPr", W + "pPrChange", W + "rPrChange", W + "ins", W + "del"}
            for node in properties.iter()):
        return "Tracked or section paragraph properties"
    for run in paragraph.findall(W + "r"):
        if any(child.tag not in PLAIN_RUN_CHILDREN for child in run):
            return "Field, break, drawing or other structured run content"
        props = run.find(W + "rPr")
        if props is not None and props.find(W + "rPrChange") is not None:
            return "Tracked character formatting"
    return None


def run_signature(run: etree._Element) -> bytes:
    props = run.find(W + "rPr")
    return paragraphs_tool.canonical(props) if props is not None else b""


def select_cell(root: etree._Element, edit: dict) -> etree._Element:
    label = edit.get("label")
    if not isinstance(label, str) or not label.strip():
        raise ValueError("Each edit requires a nonempty 'label'")
    wanted = normalize_label(label)
    rows = [row for text, row in labelled_rows(root) if text == wanted]
    if "occurrence" in edit:
        index = edit["occurrence"]
        if type(index) is not int or not 0 <= index < len(rows):
            raise ValueError(f"Invalid occurrence for label {label!r}")
        rows = [rows[index]]
    if len(rows) != 1:
        raise ValueError(f"Label {label!r} matched {len(rows)} table rows; inspect and supply 'occurrence'")
    cells = rows[0].findall(W + "tc")
    column = edit.get("column", len(cells) - 1)
    if type(column) is not int or not 1 <= column < len(cells):
        raise ValueError(f"Invalid body column for label {label!r}")
    return cells[column]


def body_paragraph(text: str, template: etree._Element) -> etree._Element:
    paragraph = etree.Element(W + "p")
    props = template.find(W + "pPr")
    if props is not None:
        paragraph.append(copy.deepcopy(props))
    runs = template.findall(W + "r")
    run = etree.SubElement(paragraph, W + "r")
    if runs and runs[0].find(W + "rPr") is not None:
        run.append(copy.deepcopy(runs[0].find(W + "rPr")))
    node = etree.SubElement(run, W + "t")
    node.set(XML_SPACE, "preserve")
    node.text = text
    return paragraph


def choose_template(cell: etree._Element, format_from: object) -> etree._Element:
    candidates = cell.findall(W + "p")
    if format_from is not None:
        if type(format_from) is not int or not 0 <= format_from < len(candidates):
            raise ValueError("format_from must be a paragraph index inside the target cell")
        candidates = [candidates[format_from]]
    for paragraph in candidates:
        runs = paragraph.findall(W + "r")
        if plain_paragraph_reason(paragraph) is None and runs and \
                len({run_signature(run) for run in runs}) == 1:
            return paragraph
    raise ValueError("No uniformly formatted plain paragraph in the cell; supply format_from")


def replace_cell(cell: etree._Element, edit: dict) -> None:
    texts = edit.get("paragraphs")
    if not isinstance(texts, list) or not texts or not all(isinstance(t, str) and t for t in texts):
        raise ValueError("replace_cell requires a nonempty list of nonempty 'paragraphs'")
    if any(c in t for t in texts for c in "\r\n\t"):
        raise ValueError("Each paragraph must be one line without tabs or line breaks")
    old = cell.findall(W + "p")
    for paragraph in old:
        reason = plain_paragraph_reason(paragraph)
        if reason:
            raise ValueError(f"Cell {edit['label']!r} contains unsupported content: {reason}")
    template = choose_template(cell, edit.get("format_from"))
    position = list(cell).index(old[0])
    new = [body_paragraph(text, template) for text in texts]
    for paragraph in old:
        cell.remove(paragraph)
    for offset, paragraph in enumerate(new):
        cell.insert(position + offset, paragraph)


def replace_text(cell: etree._Element, edit: dict) -> None:
    old, new = edit.get("old"), edit.get("new", "")
    if not isinstance(old, str) or not old or not isinstance(new, str):
        raise ValueError("replace_text requires nonempty 'old' and string 'new'")
    if any(c in new for c in "\r\n\t"):
        raise ValueError("Replacement text must not contain tabs or line breaks")
    count = cell_text(cell).count(old)
    if count != 1:
        raise ValueError(f"Text occurs {count} times in cell {edit['label']!r}; it must occur exactly once")
    nodes = [node for node in cell.iter(W + "t") if node.text and old in node.text]
    if len(nodes) != 1:
        raise ValueError("Text spans several runs; use replace_cell or merge runs first")
    run = nodes[0].getparent()
    if run.tag != W + "r" or any(child.tag not in PLAIN_RUN_CHILDREN for child in run):
        raise ValueError("Target run contains structured content")
    nodes[0].text = nodes[0].text.replace(old, new, 1)
    nodes[0].set(XML_SPACE, "preserve")


def inspect_document(source: Path, label: str | None = None) -> dict:
    package = guard.DocxPackage.from_path(source)
    root = paragraphs_tool.xml(package.entries[PART])
    wanted = normalize_label(label) if label else None
    rows, seen = [], {}
    for text, row in labelled_rows(root):
        occurrence = seen.get(text, 0)
        seen[text] = occurrence + 1
        if wanted is not None and text != wanted:
            continue
        cells = row.findall(W + "tc")
        body = cells[-1]
        paragraphs = []
        for index, paragraph in enumerate(body.findall(W + "p")):
            runs = paragraph.findall(W + "r")
            paragraphs.append({
                "index": index, "text": paragraphs_tool.text_of(paragraph),
                "characters": len(paragraphs_tool.text_of(paragraph)), "runs": len(runs),
                "uniform_format": len({run_signature(run) for run in runs}) <= 1,
                "unsupported": plain_paragraph_reason(paragraph)})
        rows.append({"label": text, "occurrence": occurrence, "cells": len(cells),
                     "body_column": len(cells) - 1,
                     "characters": sum(p["characters"] for p in paragraphs),
                     "paragraphs": paragraphs})
    return {"ok": True, "source": str(source.resolve()), "rows": rows,
            "note": "characters include punctuation and exclude paragraph breaks"}


def plan(package: guard.DocxPackage, edits_path: Path) -> tuple[guard.DocxPackage, list]:
    edits = json.loads(edits_path.read_text(encoding="utf-8-sig"))
    if not isinstance(edits, list) or not edits:
        raise ValueError("Edits must be a nonempty JSON list")
    if any(name.startswith("_xmlsignatures/") for name in package.entries):
        raise ValueError("Signed documents require a specialized tool")
    root = paragraphs_tool.xml(package.entries[PART])
    protected = paragraphs_tool.protected_spans(root)
    targets = set()
    allowed = {"op", "label", "occurrence", "column", "paragraphs", "format_from", "old", "new"}
    for edit in edits:
        if not isinstance(edit, dict) or edit.get("op") not in OPS:
            raise ValueError("Unknown cell operation")
        if set(edit) - allowed:
            raise ValueError("Unknown edit field")
        cell = select_cell(root, edit)
        if any(p in protected for p in cell.findall(W + "p")):
            raise ValueError(f"Cell {edit['label']!r} overlaps a field or annotated range")
        if edit["op"] == "replace_cell":
            if id(cell) in targets:
                raise ValueError(f"Conflicting operations on cell {edit['label']!r}")
            targets.add(id(cell))
            replace_cell(cell, edit)
        else:
            replace_text(cell, edit)
    entries = dict(package.entries)
    entries[PART] = guard._serialize_xml(root, package.entries[PART])
    return guard.DocxPackage(package.infos, entries, package.comment), edits


def check_edits(source: Path, edits_path: Path, output: Path) -> dict:
    inputs = versions.capture_inputs([source, edits_path, output])
    baseline = guard.DocxPackage.from_path(source)
    expected, edits = plan(baseline, edits_path)
    checks = paragraphs_tool.check_packages(baseline, expected, guard.DocxPackage.from_path(output))
    if versions.changed_files(inputs["files"]):
        raise ValueError("Files changed during checking")
    return {"ok": True, "status": "PASS", "source": str(output.resolve()),
            "baseline": str(source.resolve()), "operations": len(edits), **checks}


def apply_edits(source: Path, edits_path: Path, output: Path, record: Path | None = None) -> dict:
    source, edits_path, output = source.resolve(), edits_path.resolve(), output.resolve()
    record = (record or output.with_suffix(".check.json")).resolve()
    inputs = versions.capture_inputs([source, edits_path])
    versions.protect_output_path(output, inputs)
    versions.protect_record_path(record, output, inputs)
    if output.exists() or record.exists():
        raise ValueError("Output or check record already exists; choose new paths")
    baseline = guard.DocxPackage.from_path(source)
    expected, _ = plan(baseline, edits_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    published = False
    record_claimed = False
    try:
        descriptor, name = tempfile.mkstemp(prefix=".cell-edit-", suffix=".docx", dir=output.parent)
        os.close(descriptor)
        temporary = Path(name)
        with zipfile.ZipFile(temporary, "w") as archive:
            archive.comment = expected.comment
            for info in expected.infos:
                archive.writestr(info, expected.entries[info.filename])
        paragraphs_tool.check_packages(baseline, expected, guard.DocxPackage.from_path(temporary))
        if versions.changed_files(inputs["files"]):
            raise ValueError("Inputs changed during editing")
        record.parent.mkdir(parents=True, exist_ok=True)
        with record.open("x", encoding="utf-8"):
            pass
        record_claimed = True
        os.link(temporary, output)
        published = True
        versions.record_generation(output, record, inputs)
        result = versions.run_check(output, record,
            [sys.executable, "-X", "utf8", str(Path(__file__).resolve()), "check",
             str(source), str(edits_path), str(output)], kind="cell-content-style", inputs=inputs)
        if not result.get("ok"):
            raise ValueError(f"Verification failed: {result.get('status')}")
        return result
    except Exception:
        if published and output.exists() and os.path.samefile(output, temporary):
            output.unlink(missing_ok=True)
        if record_claimed:
            record.unlink(missing_ok=True)
        raise
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="operation", required=True)
    inspect = commands.add_parser("inspect")
    inspect.add_argument("source", type=Path)
    inspect.add_argument("--label")
    for operation in ("apply", "check"):
        child = commands.add_parser(operation)
        child.add_argument("source", type=Path)
        child.add_argument("edits", type=Path)
        child.add_argument("output", type=Path)
        if operation == "apply":
            child.add_argument("--record", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.operation == "inspect":
            result = inspect_document(args.source, args.label)
        elif args.operation == "apply":
            result = apply_edits(args.source, args.edits, args.output, args.record)
        else:
            result = check_edits(args.source, args.edits, args.output)
    except (OSError, ValueError, KeyError, TypeError, etree.Error, zipfile.BadZipFile,
            guard.StyleGuardError) as exc:
        result = {"ok": False, "status": "UNVERIFIED", "message": str(exc), "layout": "not_checked"}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
