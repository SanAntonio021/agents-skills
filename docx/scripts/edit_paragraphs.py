#!/usr/bin/env python3
"""Inspect, apply and check simple DOCX paragraph edits without an Office process."""

from __future__ import annotations

import argparse
import copy
import json
import os
import sys
import tempfile
import zipfile
from pathlib import Path

from lxml import etree

import document_versions as versions
import style_guard as guard

W = guard.W
PART = "word/document.xml"
OPS = {"replace", "insert_before", "insert_after", "delete"}


def xml(payload: bytes) -> etree._Element:
    root = etree.fromstring(payload, etree.XMLParser(resolve_entities=False, no_network=True))
    if root.getroottree().docinfo.doctype:
        raise ValueError("DTD declarations are not supported")
    return root


def canonical(node: etree._Element) -> bytes:
    return etree.tostring(node, method="c14n", with_comments=True)


def text_of(paragraph: etree._Element) -> str:
    return guard._paragraph_text(paragraph)


def unsupported(paragraph: etree._Element) -> str | None:
    if paragraph.getparent().tag != W + "body":
        return "Only direct body paragraphs use the fast path; use the specialized layout tool"
    if any(child.tag not in {W + "pPr", W + "r"} for child in paragraph):
        return "Formula, hyperlink, revision, bookmark or other structured paragraph content"
    properties = paragraph.find(W + "pPr")
    if properties is not None:
        if any(node.tag in {W + "sectPr", W + "pPrChange", W + "rPrChange", W + "ins", W + "del"}
               for node in properties.iter()):
            return "Section boundary or tracked paragraph formatting"
    signatures = set()
    for run in paragraph.findall(W + "r"):
        if any(child.tag not in {W + "rPr", W + "t"} for child in run):
            return "Field, formula, break, drawing or other structured run content"
        props = run.find(W + "rPr")
        if props is not None and props.find(W + "rPrChange") is not None:
            return "Tracked character formatting"
        signatures.add(canonical(props) if props is not None else b"")
    if len(signatures) > 1:
        return "Mixed character formatting; use a run-aware editing tool"
    return None


def protected_spans(root: etree._Element) -> set:
    protected, ranges = set(), set()
    field_depth = 0
    for node in root.iter():
        if node.tag == W + "p" and (field_depth or ranges):
            protected.add(node)
        if node.tag == W + "fldChar":
            kind = node.get(W + "fldCharType")
            if kind == "begin":
                field_depth += 1
            elif kind == "end":
                field_depth = max(0, field_depth - 1)
        if node.tag in {W + "bookmarkStart", W + "commentRangeStart", W + "permStart"}:
            ranges.add((node.tag.removesuffix("Start"), node.get(W + "id")))
        elif node.tag in {W + "bookmarkEnd", W + "commentRangeEnd", W + "permEnd"}:
            ranges.discard((node.tag.removesuffix("End"), node.get(W + "id")))
    return protected


def inspect_document(source: Path, contains: str | None = None) -> dict:
    package = guard.DocxPackage.from_path(source)
    paragraphs = []
    root = xml(package.entries[PART])
    protected = protected_spans(root)
    for index, paragraph in enumerate(root.iter(W + "p")):
        text = text_of(paragraph)
        if contains is not None and contains not in text:
            continue
        reason = ("Paragraph overlaps a field or annotated range" if paragraph in protected
                  else unsupported(paragraph))
        style = paragraph.find(W + "pPr/" + W + "pStyle")
        paragraphs.append({"index": index, "text": text, "supported": reason is None,
                           "reason": reason, "style": style.get(W + "val") if style is not None else None})
    return {"ok": True, "source": str(source.resolve()), "index_base": 0, "paragraphs": paragraphs}


def resolve(selector: dict, paragraphs: list) -> int:
    if not isinstance(selector, dict) or not isinstance(selector.get("old"), str):
        raise ValueError("Each selector requires the complete original text in 'old'")
    if "index" in selector:
        index = selector["index"]
        if type(index) is not int or not 0 <= index < len(paragraphs):
            raise ValueError("Invalid original paragraph index")
        if text_of(paragraphs[index]) != selector["old"]:
            raise ValueError(f"Stale original text at paragraph {index}")
        return index
    matches = [i for i, p in enumerate(paragraphs) if text_of(p) == selector["old"]]
    if len(matches) != 1:
        raise ValueError(f"Original text matched {len(matches)} paragraphs; inspect and supply an index")
    return matches[0]


def set_text(paragraph: etree._Element, text: str) -> None:
    runs = paragraph.findall(W + "r")
    props = runs[0].find(W + "rPr") if runs else paragraph.find(W + "pPr/" + W + "rPr")
    for run in runs:
        paragraph.remove(run)
    run = etree.SubElement(paragraph, W + "r")
    if props is not None:
        run.append(copy.deepcopy(props))
    node = etree.SubElement(run, W + "t")
    node.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    node.text = text


def plan(package: guard.DocxPackage, edits_path: Path) -> tuple[guard.DocxPackage, list]:
    edits = json.loads(edits_path.read_text(encoding="utf-8-sig"))
    if not isinstance(edits, list) or not edits:
        raise ValueError("Edits must be a nonempty JSON list")
    if any(name.startswith("_xmlsignatures/") for name in package.entries):
        raise ValueError("Signed documents require a specialized tool")
    root = xml(package.entries[PART])
    protected = protected_spans(root)
    paragraphs = list(root.iter(W + "p"))
    prepared, targets, donors, gaps = [], set(), set(), set()
    for edit in edits:
        if not isinstance(edit, dict) or edit.get("op") not in OPS:
            raise ValueError("Unknown paragraph operation")
        if set(edit) - {"op", "old", "index", "text", "format_from"}:
            raise ValueError("Unknown edit field")
        index = resolve(edit, paragraphs)
        if index in targets:
            raise ValueError(f"Conflicting operations on original paragraph {index}")
        targets.add(index)
        reason = ("Paragraph overlaps a field or annotated range" if paragraphs[index] in protected
                  else unsupported(paragraphs[index]))
        if reason:
            raise ValueError(f"Unsupported target {index}: {reason}")
        operation = edit["op"]
        if operation in {"insert_before", "insert_after"}:
            anchor = paragraphs[index]
            gap = anchor.getparent().index(anchor) + (operation == "insert_after")
            if gap in gaps:
                raise ValueError("Conflicting insertions at the same paragraph boundary")
            gaps.add(gap)
        if operation != "delete":
            if not isinstance(edit.get("text"), str) or any(c in edit["text"] for c in "\r\n\t"):
                raise ValueError("Supply one paragraph of text without tabs or line breaks")
            # Check XML character validity before touching any output.
            etree.Element("text").text = edit["text"]
        elif "text" in edit:
            raise ValueError("Delete does not accept replacement text")
        donor = index
        if "format_from" in edit:
            if operation not in {"insert_before", "insert_after"}:
                raise ValueError("format_from is only supported for insertions")
            selector = edit["format_from"]
            if not isinstance(selector, dict) or set(selector) - {"old", "index"}:
                raise ValueError("Invalid format_from selector")
            donor = resolve(selector, paragraphs)
            anchor, neighbor = paragraphs[index], paragraphs[donor]
            if neighbor not in (anchor, anchor.getprevious(), anchor.getnext()):
                raise ValueError("Formatting donor must be the anchor or an adjacent sibling paragraph")
            reason = ("Paragraph overlaps a field or annotated range" if neighbor in protected
                      else unsupported(neighbor))
            if reason:
                raise ValueError(f"Unsupported formatting donor {donor}: {reason}")
            if donor != index:
                donors.add(donor)
        prepared.append((index, donor, edit))
    if donors & targets:
        raise ValueError("A formatting donor cannot also be edited in the same batch")
    for index, donor, edit in prepared:
        paragraph = paragraphs[index]
        if edit["op"] == "delete":
            paragraph.getparent().remove(paragraph)
        elif edit["op"] == "replace":
            set_text(paragraph, edit["text"])
        else:
            inserted = etree.Element(W + "p")
            props = paragraphs[donor].find(W + "pPr")
            if props is not None:
                inserted.append(copy.deepcopy(props))
            runs = paragraphs[donor].findall(W + "r")
            if runs:
                inserted.append(copy.deepcopy(runs[0]))
            set_text(inserted, edit["text"])
            if edit["op"] == "insert_before":
                paragraph.addprevious(inserted)
            else:
                paragraph.addnext(inserted)
    entries = dict(package.entries)
    entries[PART] = guard._serialize_xml(root, package.entries[PART])
    return guard.DocxPackage(package.infos, entries, package.comment), prepared


def check_packages(baseline: guard.DocxPackage, expected: guard.DocxPackage,
                   candidate: guard.DocxPackage) -> dict:
    if set(baseline.entries) != set(candidate.entries):
        raise ValueError("Package part set changed")
    changed = [name for name in baseline.entries if name != PART and
               baseline.entries[name] != candidate.entries[name]]
    if changed or baseline.comment != candidate.comment:
        raise ValueError(f"Unrelated package parts changed: {changed}")
    if canonical(xml(expected.entries[PART])) != canonical(xml(candidate.entries[PART])):
        raise ValueError("Candidate content or paragraph formatting differs from the approved edits")
    # Align insertions/deletions using the validated plan before the existing style audit.
    # This prevents its text-based alignment from comparing unrelated paragraph styles.
    style = guard.audit_packages(expected, candidate)
    if not style["ok"]:
        raise ValueError(f"Style check failed: {style['violations']}")
    return {"content": "checked", "styles": "checked", "package": "checked",
            "unmodified_parts": "unchanged", "layout": "not_checked"}


def check_edits(source: Path, edits_path: Path, output: Path) -> dict:
    inputs = versions.capture_inputs([source, edits_path, output])
    baseline = guard.DocxPackage.from_path(source)
    expected, prepared = plan(baseline, edits_path)
    checks = check_packages(baseline, expected, guard.DocxPackage.from_path(output))
    if versions.changed_files(inputs["files"]):
        raise ValueError("Files changed during checking")
    return {"ok": True, "status": "PASS", "source": str(output.resolve()),
            "baseline": str(source.resolve()), "operations": len(prepared), **checks}


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
        descriptor, name = tempfile.mkstemp(prefix=".paragraph-edit-", suffix=".docx", dir=output.parent)
        os.close(descriptor)
        temporary = Path(name)
        with zipfile.ZipFile(temporary, "w") as archive:
            archive.comment = expected.comment
            for info in expected.infos:
                archive.writestr(info, expected.entries[info.filename])
        check_packages(baseline, expected, guard.DocxPackage.from_path(temporary))
        if versions.changed_files(inputs["files"]):
            raise ValueError("Inputs changed during editing")
        record.parent.mkdir(parents=True, exist_ok=True)
        with record.open("x", encoding="utf-8"):
            pass
        record_claimed = True
        # A same-volume hard link publishes the fully checked file without overwriting a race winner.
        os.link(temporary, output)
        published = True
        versions.record_generation(output, record, inputs)
        result = versions.run_check(output, record,
            [sys.executable, "-X", "utf8", str(Path(__file__).resolve()), "check",
             str(source), str(edits_path), str(output)], kind="paragraph-content-style", inputs=inputs)
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
    inspect.add_argument("--contains")
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
            result = inspect_document(args.source, args.contains)
        elif args.operation == "apply":
            result = apply_edits(args.source, args.edits, args.output, args.record)
        else:
            result = check_edits(args.source, args.edits, args.output)
    except (OSError, ValueError, KeyError, TypeError, etree.Error, zipfile.BadZipFile, guard.StyleGuardError) as exc:
        result = {"ok": False, "status": "UNVERIFIED", "message": str(exc), "layout": "not_checked"}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
