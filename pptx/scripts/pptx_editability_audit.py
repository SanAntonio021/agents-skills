#!/usr/bin/env python3
"""Audit PPTX editability signals and text-alignment risks without launching Office."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import posixpath
import re
import sys
import zipfile
from collections import Counter
from pathlib import Path
from typing import Iterable, Mapping

from defusedxml import ElementTree as ET


P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"


class AuditError(ValueError):
    """Raised when a package cannot be audited safely."""


def _configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (AttributeError, ValueError):
                pass


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _posix(path: Path) -> str:
    return path.as_posix().replace("\\", "/")


def _safe_part_name(name: str) -> bool:
    candidate = name[:-1] if name.endswith("/") else name
    normalized = posixpath.normpath(candidate)
    return (
        candidate == normalized
        and not candidate.startswith(("/", "\\"))
        and "\\" not in candidate
        and normalized not in {"", ".", ".."}
        and not normalized.startswith("../")
        and not re.match(r"^[A-Za-z]:", normalized)
    )


def _read_package(path: Path) -> dict[str, bytes]:
    if path.suffix.lower() not in {".pptx", ".potx"}:
        raise AuditError(f"input must be .pptx or .potx: {path}")
    if not path.is_file():
        raise AuditError(f"input does not exist: {path}")
    try:
        with zipfile.ZipFile(path) as package:
            names = package.namelist()
            if len(names) != len(set(names)):
                raise AuditError("package contains duplicate ZIP part names")
            unsafe = [name for name in names if not _safe_part_name(name)]
            if unsafe:
                raise AuditError(f"package contains unsafe ZIP part name: {unsafe[0]}")
            return {name: package.read(name) for name in names}
    except (OSError, zipfile.BadZipFile) as exc:
        raise AuditError(f"unable to read package: {exc}") from exc


def _parse_xml(parts: Mapping[str, bytes], name: str) -> ET.Element:
    data = parts.get(name)
    if data is None:
        raise AuditError(f"required package part is missing: {name}")
    try:
        return ET.fromstring(data)
    except ET.ParseError as exc:
        raise AuditError(f"invalid XML in {name}: {exc}") from exc


def _rels_name(part: str) -> str:
    directory, filename = posixpath.split(part)
    return posixpath.join(directory, "_rels", filename + ".rels")


def _resolve_target(part: str, target: str) -> str:
    if target.startswith("/"):
        return target.lstrip("/")
    return posixpath.normpath(posixpath.join(posixpath.dirname(part), target))


def _relationship_map(part: str, parts: Mapping[str, bytes]) -> dict[str, tuple[str, str | None]]:
    rels_name = _rels_name(part)
    if rels_name not in parts:
        return {}
    root = _parse_xml(parts, rels_name)
    result: dict[str, tuple[str, str | None]] = {}
    for relationship in root.findall(f"{{{REL_NS}}}Relationship"):
        rel_id = relationship.get("Id")
        target = relationship.get("Target")
        if rel_id and target is not None:
            result[rel_id] = (target, relationship.get("TargetMode"))
    return result


def _slide_order(parts: Mapping[str, bytes]) -> list[str]:
    root = _parse_xml(parts, "ppt/presentation.xml")
    rels = _relationship_map("ppt/presentation.xml", parts)
    slides: list[str] = []
    for slide_id in root.findall(f".//{{{P_NS}}}sldId"):
        rel_id = slide_id.get(f"{{{R_NS}}}id")
        if not rel_id or rel_id not in rels:
            raise AuditError("presentation slide relationship is missing")
        target, mode = rels[rel_id]
        if mode and mode.lower() == "external":
            raise AuditError("presentation contains an external slide relationship")
        part = _resolve_target("ppt/presentation.xml", target)
        if part not in parts:
            raise AuditError(f"slide part is missing: {part}")
        slides.append(part)
    if not slides:
        raise AuditError("presentation contains no slides")
    return slides


def _slide_size(parts: Mapping[str, bytes]) -> tuple[int, int]:
    root = _parse_xml(parts, "ppt/presentation.xml")
    size = root.find(f"{{{P_NS}}}sldSz")
    if size is None:
        raise AuditError("presentation slide size is missing")
    try:
        width = int(size.get("cx", ""))
        height = int(size.get("cy", ""))
    except ValueError as exc:
        raise AuditError("presentation slide size is invalid") from exc
    if width <= 0 or height <= 0:
        raise AuditError("presentation slide size must be positive")
    return width, height


def _shape_identity(shape: ET.Element) -> tuple[str | None, str | None]:
    properties = shape.find(f".//{{{P_NS}}}cNvPr")
    if properties is None:
        return None, None
    return properties.get("id"), properties.get("name")


def _text_preview(shape: ET.Element, limit: int = 80) -> str:
    text = " ".join(
        value.strip()
        for node in shape.findall(f".//{{{A_NS}}}t")
        if (value := (node.text or "")).strip()
    )
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _picture_transform(picture: ET.Element) -> tuple[int, int, int, int] | None:
    transform = picture.find(f"./{{{P_NS}}}spPr/{{{A_NS}}}xfrm")
    if transform is None:
        return None
    offset = transform.find(f"{{{A_NS}}}off")
    extent = transform.find(f"{{{A_NS}}}ext")
    if offset is None or extent is None:
        return None
    try:
        return (
            int(offset.get("x", "")),
            int(offset.get("y", "")),
            int(extent.get("cx", "")),
            int(extent.get("cy", "")),
        )
    except ValueError:
        return None


def _is_exact_full_slide_picture(picture: ET.Element, width: int, height: int) -> bool:
    return _picture_transform(picture) == (0, 0, width, height)


def _counter_dict(counter: Counter[str]) -> dict[str, int]:
    return {key: counter[key] for key in sorted(counter)}


def audit_presentation(source: str | Path, *, fail_on_flattened: bool = False) -> dict[str, object]:
    path = Path(source).expanduser().resolve(strict=False)
    parts = _read_package(path)
    width, height = _slide_size(parts)
    slide_parts = _slide_order(parts)

    media = [name for name in parts if name.startswith("ppt/media/") and not name.endswith("/")]
    media_extensions = Counter((Path(name).suffix.lower() or "<none>") for name in media)
    vertical_alignment: Counter[str] = Counter()
    first_paragraph_alignment: Counter[str] = Counter()
    review_items: list[dict[str, object]] = []
    likely_flattened: list[int] = []
    slide_records: list[dict[str, object]] = []
    totals: Counter[str] = Counter()

    for slide_number, slide_part in enumerate(slide_parts, 1):
        root = _parse_xml(parts, slide_part)
        shape_tree = root.find(f".//{{{P_NS}}}spTree")
        if shape_tree is None:
            raise AuditError(f"slide shape tree is missing: {slide_part}")

        shapes = root.findall(f".//{{{P_NS}}}sp")
        text_shapes = [shape for shape in shapes if shape.find(f"{{{P_NS}}}txBody") is not None]
        pictures = root.findall(f".//{{{P_NS}}}pic")
        groups = root.findall(f".//{{{P_NS}}}grpSp")
        connectors = root.findall(f".//{{{P_NS}}}cxnSp")
        graphic_frames = root.findall(f".//{{{P_NS}}}graphicFrame")
        direct_pictures = [item for item in list(shape_tree) if item.tag == f"{{{P_NS}}}pic"]
        full_slide_pictures = sum(
            1 for picture in direct_pictures
            if _is_exact_full_slide_picture(picture, width, height)
        )

        for shape in text_shapes:
            text_body = shape.find(f"{{{P_NS}}}txBody")
            assert text_body is not None
            body_properties = text_body.find(f"{{{A_NS}}}bodyPr")
            anchor_raw = body_properties.get("anchor") if body_properties is not None else None
            anchor = anchor_raw or "default_top"
            vertical_alignment[anchor] += 1
            first_paragraph = text_body.find(f"{{{A_NS}}}p")
            paragraph_properties = (
                first_paragraph.find(f"{{{A_NS}}}pPr") if first_paragraph is not None else None
            )
            horizontal_raw = (
                paragraph_properties.get("algn") if paragraph_properties is not None else None
            )
            horizontal = horizontal_raw or "inherited"
            first_paragraph_alignment[horizontal] += 1
            if horizontal_raw == "ctr" and anchor in {"t", "default_top"}:
                shape_id, shape_name = _shape_identity(shape)
                review_items.append(
                    {
                        "slide": slide_number,
                        "shape_id": shape_id,
                        "shape_name": shape_name,
                        "text": _text_preview(shape),
                        "horizontal": "ctr",
                        "vertical": anchor,
                        "reason": "horizontally centered text remains top-anchored; inspect rendered centering",
                    }
                )

        native_non_picture_objects = len(shapes) + len(groups) + len(connectors) + len(graphic_frames)
        flattened = full_slide_pictures > 0 and len(text_shapes) == 0 and native_non_picture_objects == 0
        if flattened:
            likely_flattened.append(slide_number)

        record = {
            "slide": slide_number,
            "part": slide_part,
            "native_shapes": len(shapes),
            "text_shapes": len(text_shapes),
            "groups": len(groups),
            "pictures": len(pictures),
            "connectors": len(connectors),
            "graphic_frames": len(graphic_frames),
            "exact_full_slide_pictures": full_slide_pictures,
            "likely_flattened": flattened,
        }
        slide_records.append(record)
        for key in (
            "native_shapes",
            "text_shapes",
            "groups",
            "pictures",
            "connectors",
            "graphic_frames",
            "exact_full_slide_pictures",
        ):
            totals[key] += int(record[key])

    warnings: list[str] = []
    if review_items:
        warnings.append(
            f"{len(review_items)} horizontally centered text shapes are top-anchored and require rendered review"
        )
    if likely_flattened:
        warnings.append(
            "likely flattened full-slide picture detected on slide(s): "
            + ", ".join(str(value) for value in likely_flattened)
        )
    status = "FAIL" if fail_on_flattened and likely_flattened else ("WARN" if warnings else "PASS")
    return {
        "schema_version": 1,
        "status": status,
        "file": {
            "path": _posix(path),
            "bytes": path.stat().st_size,
            "sha256": _sha256(path),
        },
        "slide_size_emu": {"width": width, "height": height},
        "slide_count": len(slide_records),
        "totals": dict(totals),
        "media": {
            "count": len(media),
            "extensions": _counter_dict(media_extensions),
            "svg_count": media_extensions.get(".svg", 0),
        },
        "text_alignment": {
            "vertical_anchor": _counter_dict(vertical_alignment),
            "first_paragraph_horizontal": _counter_dict(first_paragraph_alignment),
            "centered_top_review_count": len(review_items),
            "centered_top_review": review_items,
        },
        "likely_flattened_slides": likely_flattened,
        "warnings": warnings,
        "slides": slide_records,
        "interpretation": {
            "native_objects": "Native text, shapes, groups, connectors, and graphic frames remain PowerPoint objects.",
            "pictures": "Pictures can be moved, resized, and cropped, but their internal pixels are not decomposable PowerPoint objects.",
            "svg": "SVG media count describes the final package, not an authoring or preview intermediate.",
        },
    }


def _write_json(path: Path, value: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit PPTX editability and text-alignment signals")
    parser.add_argument("source")
    parser.add_argument("--json-out")
    parser.add_argument(
        "--fail-on-flattened",
        action="store_true",
        help="return FAIL when a slide is only an exact full-slide picture",
    )
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    _configure_stdio()
    args = build_parser().parse_args(argv)
    try:
        result = audit_presentation(args.source, fail_on_flattened=args.fail_on_flattened)
        if args.json_out:
            _write_json(Path(args.json_out).expanduser().resolve(strict=False), result)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1 if result["status"] == "FAIL" else 0
    except AuditError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
