#!/usr/bin/env python
"""Audit and remap Word style identities without changing document content."""

from __future__ import annotations

import argparse
import copy
import hashlib
import io
import json
import re
import stat
import sys
import zipfile
from collections import Counter, defaultdict
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path, PurePosixPath
from typing import Iterable

from lxml import etree


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
M_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"
W = f"{{{W_NS}}}"
M = f"{{{M_NS}}}"
W_STYLE_ID = f"{W}styleId"
W_VAL = f"{W}val"

STYLE_REFERENCE_NAMES = {
    "basedOn",
    "link",
    "next",
    "numStyleLink",
    "pStyle",
    "rStyle",
    "styleLink",
    "tblStyle",
}
STYLE_RELATIONSHIP_NAMES = {"basedOn", "link", "next"}
STYLE_LAYOUT_NAMES = {"pPr", "rPr", "tblPr", "trPr", "tcPr", "tblStylePr"}
STYLE_REPLACED_NAMES = STYLE_RELATIONSHIP_NAMES | STYLE_LAYOUT_NAMES
STYLE_CHILD_ORDER = {
    name: index
    for index, name in enumerate(
        (
            "name",
            "aliases",
            "basedOn",
            "next",
            "link",
            "autoRedefine",
            "hidden",
            "uiPriority",
            "semiHidden",
            "unhideWhenUsed",
            "qFormat",
            "locked",
            "personal",
            "personalCompose",
            "personalReply",
            "rsid",
            "pPr",
            "rPr",
            "tblPr",
            "trPr",
            "tcPr",
            "tblStylePr",
        )
    )
}
TEXT_NAMES = {f"{W}t", f"{W}delText", f"{W}instrText"}
BREAK_NAMES = {f"{W}br", f"{W}cr"}


class StyleGuardError(RuntimeError):
    """Raised when a DOCX violates the style identity contract."""


@dataclass
class DocxPackage:
    infos: list[zipfile.ZipInfo]
    entries: dict[str, bytes]
    comment: bytes

    @classmethod
    def from_path(cls, path: Path) -> "DocxPackage":
        with path.open("rb") as handle:
            return cls.from_file(handle)

    @classmethod
    def from_bytes(cls, payload: bytes) -> "DocxPackage":
        return cls.from_file(io.BytesIO(payload))

    @classmethod
    def from_file(cls, handle: object) -> "DocxPackage":
        with zipfile.ZipFile(handle, "r") as archive:
            bad_entry = archive.testzip()
            if bad_entry:
                raise StyleGuardError(f"Corrupt ZIP member: {bad_entry}")
            infos = archive.infolist()
            names = [info.filename for info in infos]
            if len(names) != len(set(names)):
                raise StyleGuardError("DOCX contains duplicate ZIP member names")
            for info in infos:
                _validate_zip_member(info)
            entries = {info.filename: archive.read(info) for info in infos}
            comment = archive.comment
        for required in ("word/document.xml", "word/styles.xml"):
            if required not in entries:
                raise StyleGuardError(f"DOCX is missing {required}")
        return cls(infos=infos, entries=entries, comment=comment)


@dataclass(frozen=True)
class ParagraphRecord:
    part: str
    index: int
    text: str
    style_id: str | None
    direct_formatting: str


def _validate_zip_member(info: zipfile.ZipInfo) -> None:
    name = info.filename
    posix = PurePosixPath(name)
    if "\\" in name or posix.is_absolute() or ".." in posix.parts:
        raise StyleGuardError(f"Unsafe ZIP member path: {name}")
    mode = info.external_attr >> 16
    if stat.S_ISLNK(mode):
        raise StyleGuardError(f"Symlink ZIP member is not allowed: {name}")


def _parse_xml(payload: bytes) -> etree._Element:
    parser = etree.XMLParser(
        resolve_entities=False,
        no_network=True,
        remove_blank_text=False,
        huge_tree=True,
    )
    return etree.fromstring(payload, parser=parser)


def _serialize_xml(root: etree._Element, original: bytes) -> bytes:
    declaration = bool(re.match(br"\s*<\?xml\b", original))
    encoding_match = re.match(
        br"\s*<\?xml[^>]*encoding=['\"]([^'\"]+)['\"]",
        original,
        re.IGNORECASE,
    )
    encoding = (
        encoding_match.group(1).decode("ascii", errors="replace")
        if encoding_match
        else "UTF-8"
    )
    standalone_match = re.match(
        br"\s*<\?xml[^>]*standalone=['\"](yes|no)['\"]",
        original,
        re.IGNORECASE,
    )
    options: dict[str, object] = {
        "encoding": encoding,
        "xml_declaration": declaration,
        "pretty_print": False,
    }
    if standalone_match:
        options["standalone"] = standalone_match.group(1).lower() == b"yes"
    serialized = etree.tostring(root.getroottree(), **options)
    if original.endswith(b"\n") and not serialized.endswith(b"\n"):
        serialized += b"\n"
    return serialized


def _canonical(element: etree._Element) -> bytes:
    return etree.tostring(element, method="c14n", with_comments=True)


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest().upper()


def _sequence_digest(values: Iterable[object]) -> str:
    payload = json.dumps(
        list(values), ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
    return _sha256(payload)


def _local_name(element: etree._Element) -> str:
    return etree.QName(element).localname


def _style_reference_nodes(
    root: etree._Element,
) -> Iterable[tuple[etree._Element, str]]:
    for element in root.iter():
        if not isinstance(element.tag, str) or not element.tag.startswith(W):
            continue
        if _local_name(element) not in STYLE_REFERENCE_NAMES:
            continue
        value = element.get(W_VAL)
        if value is not None:
            yield element, value


def _rewrite_style_references(
    root: etree._Element, mapping: dict[str, str]
) -> Counter[str]:
    rewritten: Counter[str] = Counter()
    for element, value in _style_reference_nodes(root):
        target = mapping.get(value)
        if target is None:
            continue
        element.set(W_VAL, target)
        rewritten[f"{value}={target}"] += 1
    return rewritten


def _styles_by_id(styles_root: etree._Element) -> dict[str, etree._Element]:
    styles: dict[str, etree._Element] = {}
    for style in styles_root.findall(f"{W}style"):
        style_id = style.get(W_STYLE_ID)
        if not style_id:
            raise StyleGuardError("A style definition has no w:styleId")
        if style_id in styles:
            raise StyleGuardError(f"Duplicate style definition: {style_id}")
        styles[style_id] = style
    return styles


def _style_name(style: etree._Element) -> str:
    name = style.find(f"{W}name")
    return name.get(W_VAL, "") if name is not None else ""


def _insert_style_child(style: etree._Element, child: etree._Element) -> None:
    child_rank = STYLE_CHILD_ORDER.get(_local_name(child), len(STYLE_CHILD_ORDER))
    for index, existing in enumerate(style):
        existing_rank = STYLE_CHILD_ORDER.get(
            _local_name(existing), len(STYLE_CHILD_ORDER)
        )
        if existing_rank > child_rank:
            style.insert(index, child)
            return
    style.append(child)


def _relationship_child(style: etree._Element, name: str) -> etree._Element | None:
    return style.find(f"{W}{name}")


def _build_target_style(
    old_style: etree._Element,
    template_style: etree._Element,
    target_id: str,
    mapping: dict[str, str],
    next_styles: dict[str, str],
    format_source: str,
) -> etree._Element:
    old_type = old_style.get(f"{W}type")
    target_type = template_style.get(f"{W}type")
    if old_type != target_type:
        raise StyleGuardError(
            f"Style type mismatch for {old_style.get(W_STYLE_ID)}={target_id}: "
            f"{old_type!r} != {target_type!r}"
        )

    result = copy.deepcopy(template_style)
    result.set(W_STYLE_ID, target_id)
    if format_source == "template":
        # Linked character-style IDs often collide across independently authored DOCX files.
        link = _relationship_child(result, "link")
        if link is not None:
            result.remove(link)
        paragraph_properties = result.find(f"{W}pPr")
        if paragraph_properties is not None:
            numbering = paragraph_properties.find(f"{W}numPr")
            if numbering is not None:
                paragraph_properties.remove(numbering)
        _rewrite_style_references(result, mapping)
        next_id = next_styles.get(target_id)
        if next_id is not None:
            old_next = _relationship_child(result, "next")
            if old_next is not None:
                result.remove(old_next)
            next_child = etree.Element(f"{W}next")
            next_child.set(W_VAL, next_id)
            _insert_style_child(result, next_child)
        return result

    for child in list(result):
        if _local_name(child) in STYLE_REPLACED_NAMES:
            result.remove(child)

    for name in ("basedOn", "link"):
        old_child = _relationship_child(old_style, name)
        if old_child is not None:
            child = copy.deepcopy(old_child)
            _rewrite_style_references(child, mapping)
            _insert_style_child(result, child)

    next_id = next_styles.get(target_id)
    if next_id is None:
        old_next = _relationship_child(old_style, "next")
        if old_next is not None:
            old_next_id = old_next.get(W_VAL)
            next_id = mapping.get(old_next_id, old_next_id)
    if next_id:
        next_child = etree.Element(f"{W}next")
        next_child.set(W_VAL, next_id)
        _insert_style_child(result, next_child)

    for child in old_style:
        if _local_name(child) not in STYLE_LAYOUT_NAMES:
            continue
        layout_child = copy.deepcopy(child)
        _rewrite_style_references(layout_child, mapping)
        _insert_style_child(result, layout_child)
    return result


def _replace_or_append_style(
    styles_root: etree._Element,
    existing: etree._Element | None,
    replacement: etree._Element,
) -> None:
    if existing is None:
        styles_root.append(replacement)
        return
    existing.getparent().replace(existing, replacement)


def _validate_mapping(mapping: dict[str, str]) -> None:
    if not mapping:
        raise StyleGuardError("At least one style mapping is required")
    if len(set(mapping.values())) != len(mapping):
        raise StyleGuardError("Style remapping must be one-to-one")
    for old_id, target_id in mapping.items():
        if not old_id or not target_id:
            raise StyleGuardError("Style IDs cannot be empty")
        if old_id == target_id:
            raise StyleGuardError(f"Identity mapping is not allowed: {old_id}")
        if target_id in mapping:
            raise StyleGuardError(
                f"Chained or cyclic style mapping is not allowed: {old_id}={target_id}"
            )


def _parse_assignments(values: Iterable[str], label: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for value in values:
        key, separator, target = value.partition("=")
        key = key.strip()
        target = target.strip()
        if not separator or not key or not target:
            raise StyleGuardError(f"Invalid {label}: {value!r}; expected OLD=NEW")
        if key in result and result[key] != target:
            raise StyleGuardError(f"Conflicting {label} for {key}")
        result[key] = target
    return result


def _write_package(package: DocxPackage) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", allowZip64=True) as archive:
        archive.comment = package.comment
        for original_info in package.infos:
            info = copy.copy(original_info)
            archive.writestr(info, package.entries[info.filename])
    payload = buffer.getvalue()
    DocxPackage.from_bytes(payload)
    return payload


def _style_metadata_signature(styles_root: etree._Element) -> bytes:
    clone = copy.deepcopy(styles_root)
    for style in list(clone.findall(f"{W}style")):
        clone.remove(style)
    return _canonical(clone)


def _style_references_by_part(package: DocxPackage) -> dict[str, Counter[str]]:
    result: dict[str, Counter[str]] = {}
    for name, payload in package.entries.items():
        if not name.lower().endswith(".xml"):
            continue
        root = _parse_xml(payload)
        counts = Counter(value for _, value in _style_reference_nodes(root))
        if counts:
            result[name] = counts
    return result


def _missing_style_references(package: DocxPackage) -> set[str]:
    styles_root = _parse_xml(package.entries["word/styles.xml"])
    style_ids = set(_styles_by_id(styles_root))
    referenced = {
        style_id
        for counts in _style_references_by_part(package).values()
        for style_id in counts
    }
    return referenced - style_ids


def _orphan_styles(package: DocxPackage) -> set[str]:
    styles_root = _parse_xml(package.entries["word/styles.xml"])
    styles = _styles_by_id(styles_root)
    roots: set[str] = set()
    graph: dict[str, set[str]] = defaultdict(set)

    for style_id, style in styles.items():
        default_value = (style.get(f"{W}default") or "").lower()
        if default_value in {"1", "true", "on"}:
            roots.add(style_id)
        graph[style_id].update(value for _, value in _style_reference_nodes(style))

    for part, counts in _style_references_by_part(package).items():
        if part == "word/styles.xml":
            continue
        roots.update(counts)

    reachable: set[str] = set()
    pending = list(roots)
    while pending:
        style_id = pending.pop()
        if style_id in reachable or style_id not in styles:
            continue
        reachable.add(style_id)
        pending.extend(graph[style_id] - reachable)
    return set(styles) - reachable


def _paragraph_text(paragraph: etree._Element) -> str:
    chunks: list[str] = []
    for element in paragraph.iter():
        if element.tag in TEXT_NAMES or element.tag == f"{M}t":
            chunks.append(element.text or "")
        elif element.tag == f"{W}tab":
            chunks.append("\t")
        elif element.tag in BREAK_NAMES:
            chunks.append("\n")
    return "".join(chunks)


def _direct_formatting_signature(paragraph: etree._Element) -> str:
    paragraph_properties = paragraph.find(f"{W}pPr")
    if paragraph_properties is None:
        paragraph_signature = ""
    else:
        clone = copy.deepcopy(paragraph_properties)
        style = clone.find(f"{W}pStyle")
        if style is not None:
            clone.remove(style)
        paragraph_signature = _canonical(clone).decode("utf-8")

    run_signatures: list[str] = []
    for run in paragraph.iter(f"{W}r"):
        run_properties = run.find(f"{W}rPr")
        signature = (
            _canonical(run_properties).decode("utf-8")
            if run_properties is not None
            else ""
        )
        if not run_signatures or run_signatures[-1] != signature:
            run_signatures.append(signature)
    return _sequence_digest((paragraph_signature, run_signatures))


def _paragraph_records(package: DocxPackage) -> dict[str, list[ParagraphRecord]]:
    records: dict[str, list[ParagraphRecord]] = {}
    for part in sorted(package.entries):
        if not part.startswith("word/") or not part.lower().endswith(".xml"):
            continue
        root = _parse_xml(package.entries[part])
        paragraphs = list(root.iter(f"{W}p"))
        if not paragraphs:
            continue
        part_records: list[ParagraphRecord] = []
        for index, paragraph in enumerate(paragraphs):
            style_node = paragraph.find(f"{W}pPr/{W}pStyle")
            part_records.append(
                ParagraphRecord(
                    part=part,
                    index=index,
                    text=_paragraph_text(paragraph),
                    style_id=style_node.get(W_VAL) if style_node is not None else None,
                    direct_formatting=_direct_formatting_signature(paragraph),
                )
            )
        records[part] = part_records
    return records


def _matched_paragraphs(
    baseline: list[ParagraphRecord], candidate: list[ParagraphRecord]
) -> Iterable[tuple[ParagraphRecord, ParagraphRecord]]:
    if len(baseline) == len(candidate):
        yield from zip(baseline, candidate)
        return
    matcher = SequenceMatcher(
        a=[record.text for record in baseline],
        b=[record.text for record in candidate],
        autojunk=False,
    )
    for operation, i1, i2, j1, j2 in matcher.get_opcodes():
        if operation == "equal":
            yield from zip(baseline[i1:i2], candidate[j1:j2])
        elif operation == "replace":
            pair_count = min(i2 - i1, j2 - j1)
            yield from zip(
                baseline[i1 : i1 + pair_count],
                candidate[j1 : j1 + pair_count],
            )


def _paragraph_differences(
    baseline: DocxPackage,
    candidate: DocxPackage,
    allowed_mapping: dict[str, str],
) -> tuple[list[dict[str, object]], list[dict[str, object]], dict[str, object]]:
    baseline_records = _paragraph_records(baseline)
    candidate_records = _paragraph_records(candidate)
    style_changes: list[dict[str, object]] = []
    formatting_changes: list[dict[str, object]] = []
    counts: dict[str, object] = {}
    for part in sorted(set(baseline_records) | set(candidate_records)):
        before = baseline_records.get(part, [])
        after = candidate_records.get(part, [])
        counts[part] = {"baseline": len(before), "candidate": len(after)}
        for old, new in _matched_paragraphs(before, after):
            if old.style_id != new.style_id:
                change = {
                    "part": part,
                    "baseline_index": old.index,
                    "candidate_index": new.index,
                    "baseline_style": old.style_id,
                    "candidate_style": new.style_id,
                    "text": new.text[:120],
                }
                if allowed_mapping.get(old.style_id or "") != new.style_id:
                    style_changes.append(change)
            if old.direct_formatting != new.direct_formatting:
                formatting_changes.append(
                    {
                        "part": part,
                        "baseline_index": old.index,
                        "candidate_index": new.index,
                        "text": new.text[:120],
                    }
                )
    return style_changes, formatting_changes, counts


def _style_equal_after_mapping(
    baseline_style: etree._Element,
    candidate_style: etree._Element,
    mapping: dict[str, str],
) -> bool:
    clone = copy.deepcopy(baseline_style)
    _rewrite_style_references(clone, mapping)
    return _canonical(clone) == _canonical(candidate_style)


def audit_packages(
    baseline: DocxPackage,
    candidate: DocxPackage,
    allowed_mapping: dict[str, str] | None = None,
    allowed_style_changes: set[str] | None = None,
) -> dict[str, object]:
    allowed_mapping = dict(allowed_mapping or {})
    allowed_style_changes = set(allowed_style_changes or set())
    baseline_styles_root = _parse_xml(baseline.entries["word/styles.xml"])
    candidate_styles_root = _parse_xml(candidate.entries["word/styles.xml"])
    baseline_styles = _styles_by_id(baseline_styles_root)
    candidate_styles = _styles_by_id(candidate_styles_root)
    baseline_ids = set(baseline_styles)
    candidate_ids = set(candidate_styles)

    added = sorted(candidate_ids - baseline_ids)
    removed = sorted(baseline_ids - candidate_ids)
    modified = sorted(
        style_id
        for style_id in baseline_ids & candidate_ids
        if _canonical(baseline_styles[style_id])
        != _canonical(candidate_styles[style_id])
    )
    targets = set(allowed_mapping.values())
    unapproved_added = [style_id for style_id in added if style_id not in targets]
    unapproved_removed = [
        style_id for style_id in removed if style_id not in allowed_mapping
    ]
    unapproved_modified: list[str] = []
    for style_id in modified:
        if style_id in targets or style_id in allowed_style_changes:
            continue
        if _style_equal_after_mapping(
            baseline_styles[style_id], candidate_styles[style_id], allowed_mapping
        ):
            continue
        unapproved_modified.append(style_id)

    metadata_changed = _style_metadata_signature(
        baseline_styles_root
    ) != _style_metadata_signature(candidate_styles_root)
    paragraph_style_changes, formatting_changes, paragraph_counts = (
        _paragraph_differences(baseline, candidate, allowed_mapping)
    )
    baseline_orphans = _orphan_styles(baseline)
    candidate_orphans = _orphan_styles(candidate)
    new_orphans = sorted(candidate_orphans - baseline_orphans)
    baseline_missing = _missing_style_references(baseline)
    candidate_missing = _missing_style_references(candidate)
    new_missing = sorted(candidate_missing - baseline_missing)

    violations: dict[str, object] = {}
    if unapproved_added:
        violations["added_styles"] = unapproved_added
    if unapproved_removed:
        violations["removed_styles"] = unapproved_removed
    if unapproved_modified:
        violations["modified_style_definitions"] = unapproved_modified
    if metadata_changed:
        violations["style_table_metadata_changed"] = True
    if paragraph_style_changes:
        violations["paragraph_style_changes"] = paragraph_style_changes
    if formatting_changes:
        violations["direct_formatting_drift"] = formatting_changes
    if new_orphans:
        violations["new_orphan_styles"] = new_orphans
    if new_missing:
        violations["new_missing_style_references"] = new_missing

    reference_counts = {
        part: dict(sorted(counts.items()))
        for part, counts in sorted(_style_references_by_part(candidate).items())
    }
    return {
        "ok": not violations,
        "style_table": {
            "baseline_count": len(baseline_styles),
            "candidate_count": len(candidate_styles),
            "added": added,
            "removed": removed,
            "modified": modified,
            "candidate_orphans": sorted(candidate_orphans),
            "candidate_missing_references": sorted(candidate_missing),
        },
        "paragraph_counts": paragraph_counts,
        "style_reference_counts": reference_counts,
        "violations": violations,
    }


def audit_docx(
    baseline_path: Path,
    candidate_path: Path,
    allowed_mapping: dict[str, str] | None = None,
    allowed_style_changes: set[str] | None = None,
) -> dict[str, object]:
    baseline = DocxPackage.from_path(baseline_path)
    candidate = DocxPackage.from_path(candidate_path)
    report = audit_packages(
        baseline, candidate, allowed_mapping, allowed_style_changes
    )
    report["baseline"] = {
        "path": str(baseline_path.resolve()),
        "sha256": _sha256(baseline_path.read_bytes()),
    }
    report["candidate"] = {
        "path": str(candidate_path.resolve()),
        "sha256": _sha256(candidate_path.read_bytes()),
    }
    return report


def _xml_roots(package: DocxPackage) -> Iterable[tuple[str, etree._Element]]:
    for name in sorted(package.entries):
        if name.lower().endswith(".xml"):
            yield name, _parse_xml(package.entries[name])


def _document_metrics(package: DocxPackage) -> dict[str, object]:
    body_tokens: list[str] = []
    formula_tokens: list[str] = []
    math_structures: list[str] = []
    paragraph_count = 0
    structural_digests: dict[str, str] = {}

    for part, root in _xml_roots(package):
        if part.startswith("word/"):
            paragraph_count += sum(1 for _ in root.iter(f"{W}p"))
        for element in root.iter():
            if element.tag in TEXT_NAMES:
                body_tokens.append(element.text or "")
            elif element.tag == f"{M}t":
                formula_tokens.append(element.text or "")
            if element.tag not in {f"{M}oMath", f"{M}oMathPara"}:
                continue
            if any(
                ancestor.tag in {f"{M}oMath", f"{M}oMathPara"}
                for ancestor in element.iterancestors()
            ):
                continue
            math_structures.append(_sha256(_canonical(element)))

        if part == "word/styles.xml":
            continue
        clone = copy.deepcopy(root)
        for reference, _ in list(_style_reference_nodes(clone)):
            parent = reference.getparent()
            if parent is not None:
                parent.remove(reference)
        structural_digests[part] = _sha256(_canonical(clone))

    media = {
        name: _sha256(payload)
        for name, payload in sorted(package.entries.items())
        if name.startswith("word/media/") and not name.endswith("/")
    }
    relationships = {
        name: _sha256(payload)
        for name, payload in sorted(package.entries.items())
        if name.lower().endswith(".rels")
    }
    numbering = package.entries.get("word/numbering.xml")
    return {
        "paragraph_count": paragraph_count,
        "body_text_count": len(body_tokens),
        "body_text_digest": _sequence_digest(body_tokens),
        "formula_text_count": len(formula_tokens),
        "formula_text_digest": _sequence_digest(formula_tokens),
        "omml_count": len(math_structures),
        "omml_digest": _sequence_digest(math_structures),
        "non_style_xml_digests": structural_digests,
        "media_hashes": media,
        "relationship_hashes": relationships,
        "numbering_sha256": _sha256(numbering) if numbering is not None else None,
    }


def _invariant_report(
    baseline: DocxPackage, candidate: DocxPackage
) -> dict[str, object]:
    before = _document_metrics(baseline)
    after = _document_metrics(candidate)
    changed_parts = sorted(
        name
        for name in set(baseline.entries) | set(candidate.entries)
        if baseline.entries.get(name) != candidate.entries.get(name)
    )
    checks = {
        "package_parts_unchanged": set(baseline.entries) == set(candidate.entries),
        "paragraph_count_unchanged": before["paragraph_count"]
        == after["paragraph_count"],
        "body_text_unchanged": (
            before["body_text_count"], before["body_text_digest"]
        )
        == (after["body_text_count"], after["body_text_digest"]),
        "formula_text_unchanged": (
            before["formula_text_count"], before["formula_text_digest"]
        )
        == (after["formula_text_count"], after["formula_text_digest"]),
        "omml_unchanged": (before["omml_count"], before["omml_digest"])
        == (after["omml_count"], after["omml_digest"]),
        "media_unchanged": before["media_hashes"] == after["media_hashes"],
        "relationships_unchanged": before["relationship_hashes"]
        == after["relationship_hashes"],
        "numbering_unchanged": before["numbering_sha256"]
        == after["numbering_sha256"],
        "non_style_xml_structure_unchanged": before["non_style_xml_digests"]
        == after["non_style_xml_digests"],
    }
    return {
        "ok": all(
            checks[name]
            for name in (
                "package_parts_unchanged",
                "paragraph_count_unchanged",
                "body_text_unchanged",
                "formula_text_unchanged",
                "omml_unchanged",
                "media_unchanged",
                "relationships_unchanged",
                "non_style_xml_structure_unchanged",
            )
        ),
        "checks": checks,
        "changed_parts": changed_parts,
        "baseline": before,
        "candidate": after,
    }


def _layout_signature(
    style: etree._Element, mapping: dict[str, str] | None = None
) -> bytes:
    container = etree.Element("layout")
    for child in style:
        if _local_name(child) not in ({"basedOn", "link"} | STYLE_LAYOUT_NAMES):
            continue
        clone = copy.deepcopy(child)
        if mapping:
            _rewrite_style_references(clone, mapping)
        container.append(clone)
    return _canonical(container)


def remap_docx(
    input_path: Path,
    template_path: Path,
    output_path: Path,
    mapping: dict[str, str],
    next_styles: dict[str, str] | None = None,
    format_source: str = "input",
) -> dict[str, object]:
    _validate_mapping(mapping)
    if format_source not in {"input", "template"}:
        raise StyleGuardError(
            f"Unsupported format source {format_source!r}; expected 'input' or 'template'"
        )
    next_styles = dict(next_styles or {})
    unknown_next_targets = set(next_styles) - set(mapping.values())
    if unknown_next_targets:
        raise StyleGuardError(
            "Next-style assignments target unmapped styles: "
            + ", ".join(sorted(unknown_next_targets))
        )
    if output_path.exists():
        raise FileExistsError(f"Output already exists: {output_path}")

    source = DocxPackage.from_path(input_path)
    template = DocxPackage.from_path(template_path)
    source_styles_root = _parse_xml(source.entries["word/styles.xml"])
    template_styles_root = _parse_xml(template.entries["word/styles.xml"])
    source_styles = _styles_by_id(source_styles_root)
    template_styles = _styles_by_id(template_styles_root)

    missing_old = sorted(set(mapping) - set(source_styles))
    missing_targets = sorted(set(mapping.values()) - set(template_styles))
    if missing_old:
        raise StyleGuardError("Input styles not found: " + ", ".join(missing_old))
    if missing_targets:
        raise StyleGuardError(
            "Template styles not found: " + ", ".join(missing_targets)
        )

    replacements: dict[str, etree._Element] = {}
    for old_id, target_id in mapping.items():
        replacements[target_id] = _build_target_style(
            source_styles[old_id],
            template_styles[target_id],
            target_id,
            mapping,
            next_styles,
            format_source,
        )

    for old_id in mapping:
        old_style = source_styles_root.xpath(
            "./w:style[@w:styleId=$style_id]",
            namespaces={"w": W_NS},
            style_id=old_id,
        )[0]
        old_style.getparent().remove(old_style)

    current_styles = _styles_by_id(source_styles_root)
    for target_id, replacement in replacements.items():
        _replace_or_append_style(
            source_styles_root, current_styles.get(target_id), replacement
        )
        current_styles = _styles_by_id(source_styles_root)
    style_rewrites = _rewrite_style_references(source_styles_root, mapping)

    result_entries = dict(source.entries)
    result_entries["word/styles.xml"] = _serialize_xml(
        source_styles_root, source.entries["word/styles.xml"]
    )
    reference_rewrites: Counter[str] = Counter(style_rewrites)
    for part, payload in source.entries.items():
        if part == "word/styles.xml" or not part.lower().endswith(".xml"):
            continue
        root = _parse_xml(payload)
        rewrites = _rewrite_style_references(root, mapping)
        if not rewrites:
            continue
        reference_rewrites.update(rewrites)
        result_entries[part] = _serialize_xml(root, payload)

    candidate_seed = DocxPackage(
        infos=source.infos,
        entries=result_entries,
        comment=source.comment,
    )
    output_payload = _write_package(candidate_seed)
    candidate = DocxPackage.from_bytes(output_payload)
    candidate_styles_root = _parse_xml(candidate.entries["word/styles.xml"])
    candidate_styles = _styles_by_id(candidate_styles_root)

    remaining_references: dict[str, dict[str, int]] = {}
    for part, counts in _style_references_by_part(candidate).items():
        old_counts = {style_id: counts[style_id] for style_id in mapping if counts[style_id]}
        if old_counts:
            remaining_references[part] = old_counts
    remaining_definitions = sorted(set(mapping) & set(candidate_styles))
    if remaining_references or remaining_definitions:
        raise StyleGuardError(
            "Mapped styles still remain after remap: "
            + json.dumps(
                {
                    "definitions": remaining_definitions,
                    "references": remaining_references,
                },
                ensure_ascii=False,
            )
        )

    target_styles: dict[str, dict[str, object]] = {}
    for old_id, target_id in mapping.items():
        target_style = candidate_styles[target_id]
        template_style = template_styles[target_id]
        if _style_name(target_style) != _style_name(template_style):
            raise StyleGuardError(f"Template style name was not preserved: {target_id}")
        if _layout_signature(replacements[target_id]) != _layout_signature(target_style):
            raise StyleGuardError(
                f"Expected {format_source} layout was not preserved: "
                f"{old_id}={target_id}"
            )
        actual_next = _relationship_child(target_style, "next")
        actual_next_id = actual_next.get(W_VAL) if actual_next is not None else None
        expected_next_id = next_styles.get(target_id)
        if expected_next_id is not None and actual_next_id != expected_next_id:
            raise StyleGuardError(
                f"Next style mismatch for {target_id}: "
                f"{actual_next_id!r} != {expected_next_id!r}"
            )
        target_styles[target_id] = {
            "source_style": old_id,
            "name": _style_name(target_style),
            "next_style": actual_next_id,
            "format_source": format_source,
        }

    invariants = _invariant_report(source, candidate)
    if not invariants["ok"]:
        raise StyleGuardError(
            "Content/package invariants failed: "
            + json.dumps(invariants["checks"], ensure_ascii=False)
        )
    style_audit = audit_packages(source, candidate, mapping)
    if not style_audit["ok"]:
        raise StyleGuardError(
            "Post-remap style audit failed: "
            + json.dumps(style_audit["violations"], ensure_ascii=False)
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("xb") as handle:
        handle.write(output_payload)
        handle.flush()

    return {
        "ok": True,
        "input": {
            "path": str(input_path.resolve()),
            "sha256": _sha256(input_path.read_bytes()),
        },
        "template": {
            "path": str(template_path.resolve()),
            "sha256": _sha256(template_path.read_bytes()),
        },
        "output": {
            "path": str(output_path.resolve()),
            "sha256": _sha256(output_payload),
        },
        "mapping": mapping,
        "format_source": format_source,
        "reference_rewrites": dict(sorted(reference_rewrites.items())),
        "target_styles": dict(sorted(target_styles.items())),
        "invariants": invariants,
        "style_audit": style_audit,
    }


def _write_report(report: dict[str, object], json_out: Path | None) -> None:
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    print(payload)
    if json_out is not None:
        json_out.parent.mkdir(parents=True, exist_ok=True)
        with json_out.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
            handle.write("\n")


def _existing_docx(value: str) -> Path:
    path = Path(value).expanduser().resolve()
    if not path.is_file():
        raise argparse.ArgumentTypeError(f"DOCX not found: {value}")
    if path.suffix.lower() != ".docx":
        raise argparse.ArgumentTypeError(f"Expected a .docx file: {value}")
    return path


def _output_docx(value: str) -> Path:
    path = Path(value).expanduser().resolve()
    if path.suffix.lower() != ".docx":
        raise argparse.ArgumentTypeError(f"Output must be a .docx file: {value}")
    return path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Audit or remap DOCX style identities without editing content."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    audit_parser = subparsers.add_parser(
        "audit", help="Fail on unauthorized style or direct-formatting drift."
    )
    audit_parser.add_argument("--baseline", required=True, type=_existing_docx)
    audit_parser.add_argument("--candidate", required=True, type=_existing_docx)
    audit_parser.add_argument(
        "--allow-map",
        action="append",
        default=[],
        metavar="OLD=NEW",
        help="Allow an explicit style identity remap; repeat as needed.",
    )
    audit_parser.add_argument(
        "--allow-style-change",
        action="append",
        default=[],
        metavar="STYLE_ID",
        help="Allow formatting changes to an existing style definition.",
    )
    audit_parser.add_argument("--json-out", type=Path)
    audit_parser.add_argument(
        "--report-only",
        action="store_true",
        help="Return exit code 0 even when violations are reported.",
    )

    remap_parser = subparsers.add_parser(
        "remap", help="Remap old styles to existing template style identities."
    )
    remap_parser.add_argument("--input", required=True, type=_existing_docx)
    remap_parser.add_argument(
        "--template", "--donor", dest="template", required=True, type=_existing_docx
    )
    remap_parser.add_argument("--output", required=True, type=_output_docx)
    remap_parser.add_argument(
        "--map", action="append", required=True, metavar="OLD=NEW"
    )
    remap_parser.add_argument(
        "--next-style",
        action="append",
        default=[],
        metavar="STYLE=NEXT",
    )
    remap_parser.add_argument(
        "--format-source",
        choices=("input", "template"),
        default="input",
        help=(
            "Take layout properties from the input styles (default), or keep the "
            "template styles' layout properties."
        ),
    )
    remap_parser.add_argument("--json-out", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "audit":
            allowed_mapping = _parse_assignments(args.allow_map, "style mapping")
            report = audit_docx(
                args.baseline,
                args.candidate,
                allowed_mapping,
                set(args.allow_style_change),
            )
            _write_report(report, args.json_out)
            return 0 if report["ok"] or args.report_only else 1

        mapping = _parse_assignments(args.map, "style mapping")
        next_styles = _parse_assignments(args.next_style, "next style")
        report = remap_docx(
            args.input,
            args.template,
            args.output,
            mapping,
            next_styles,
            args.format_source,
        )
        _write_report(report, args.json_out)
        return 0
    except (
        StyleGuardError,
        FileExistsError,
        OSError,
        zipfile.BadZipFile,
        etree.XMLSyntaxError,
    ) as exc:
        print(f"style_guard: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
