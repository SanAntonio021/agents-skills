#!/usr/bin/env python3
"""Deterministic release-bundle and revision gates for formal PPTX delivery.

The helper is intentionally file-level: it never starts Office or LibreOffice,
and it refuses to overwrite a newly-created release directory or snapshot.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import posixpath
import re
import sys
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping

from defusedxml import ElementTree as ET


REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


class ReleaseBundleError(ValueError):
    """Raised for an unsafe or invalid release-bundle operation."""


def _configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (AttributeError, ValueError):
                pass


def _canonical_path(path: str | Path) -> Path:
    return Path(os.path.normcase(str(Path(path).expanduser().resolve(strict=False))))


def _posix_path(path: Path) -> str:
    return path.as_posix().replace("\\", "/")


def _scope(root: str | Path, exclude: str | Path) -> tuple[Path, Path, str, str]:
    root_path = _canonical_path(root)
    if not root_path.is_dir():
        raise ReleaseBundleError(f"root directory does not exist: {root_path}")
    exclude_path = Path(exclude)
    if not exclude_path.is_absolute():
        exclude_path = root_path / exclude_path
    exclude_path = _canonical_path(exclude_path)
    try:
        exclude_rel = exclude_path.relative_to(root_path)
    except ValueError as exc:
        raise ReleaseBundleError(
            f"exclude path must be inside root: {exclude_path} not under {root_path}"
        ) from exc
    return (
        root_path,
        exclude_path,
        _posix_path(root_path),
        _posix_path(exclude_rel) or ".",
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, value: Mapping[str, object], *, refuse_existing: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if refuse_existing and path.exists():
        raise ReleaseBundleError(f"refusing to overwrite existing file: {path}")
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _read_json(path: str | Path) -> dict:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReleaseBundleError(f"unable to read JSON: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ReleaseBundleError(f"JSON root must be an object: {path}")
    return value


def _safe_relative(value: str, field: str) -> str:
    candidate = Path(value)
    if candidate.is_absolute():
        raise ReleaseBundleError(f"{field} must be relative to the release directory")
    normalized = posixpath.normpath(_posix_path(candidate))
    if normalized in {"", "."} or normalized == ".." or normalized.startswith("../"):
        raise ReleaseBundleError(f"{field} escapes the release directory: {value}")
    return normalized


def _inside(base: Path, relative: str, field: str) -> Path:
    target = _canonical_path(base / relative)
    try:
        target.relative_to(_canonical_path(base))
    except ValueError as exc:
        raise ReleaseBundleError(f"{field} escapes release directory: {relative}") from exc
    return target


def _topic_slug(topic: str) -> str:
    slug = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff._-]+", "_", topic.strip())
    slug = slug.strip("._-")
    return slug or "presentation"


def _date_slug(value: str | None) -> str:
    if value is None:
        return datetime.now(timezone.utc).astimezone().strftime("%Y%m%d")
    if not re.fullmatch(r"\d{8}", value):
        raise ReleaseBundleError("date must use YYYYMMDD")
    return value


def _file_identity(path: Path) -> dict[str, object]:
    if not path.is_file():
        return {"path": _posix_path(path), "exists": False}
    return {
        "path": _posix_path(path),
        "exists": True,
        "bytes": path.stat().st_size,
        "sha256": _sha256(path),
    }


def initialize_release(
    output_root: str | Path,
    topic: str,
    *,
    date: str | None = None,
    pptx_name: str = "final.pptx",
    pdf_name: str = "final.pdf",
    png_dir: str = "png",
    evidence_dir: str = "evidence",
    template: str | Path | None = None,
    parent: str | Path | None = None,
    changed_slides: Iterable[int] = (),
    require_design_acceptance: bool = False,
) -> Path:
    root = _canonical_path(output_root)
    root.mkdir(parents=True, exist_ok=True)
    topic_slug = _topic_slug(topic)
    date_slug = _date_slug(date)
    pattern = re.compile(rf"^{re.escape(topic_slug)}_{date_slug}_v(\d+)$", re.IGNORECASE)
    versions = []
    for item in root.iterdir():
        if item.is_dir():
            match = pattern.fullmatch(item.name)
            if match:
                versions.append(int(match.group(1)))
    version = max(versions, default=0) + 1
    release_dir = root / f"{topic_slug}_{date_slug}_v{version:02d}"
    if release_dir.exists():
        raise ReleaseBundleError(f"refusing to overwrite existing release directory: {release_dir}")
    release_dir.mkdir()
    artifacts = {
        "pptx": _safe_relative(pptx_name, "pptx_name"),
        "pdf": _safe_relative(pdf_name, "pdf_name"),
        "png_dir": _safe_relative(png_dir, "png_dir"),
        "evidence_dir": _safe_relative(evidence_dir, "evidence_dir"),
    }
    if template is None:
        template_identity: dict[str, object] = {"path": None, "exists": False}
    else:
        template_identity = _file_identity(_canonical_path(template))
    manifest = {
        "schema_version": 1,
        "release_id": release_dir.name,
        "release_dir": _posix_path(release_dir),
        "output_root": _posix_path(root),
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "parent_release": _posix_path(_canonical_path(parent)) if parent else None,
        "artifacts": artifacts,
        "reference_template": template_identity,
        "changed_slides": sorted({int(value) for value in changed_slides}),
        "acceptance": {
            "static": {"status": "PENDING"},
            "lo_render": {"status": "PENDING"},
            "native_open": {"status": "PENDING"},
            "native_render": {"status": "PENDING"},
            "visual_qa": {"status": "PENDING", "scope": "FULL_DECK"},
            "design_acceptance": {
                "required": bool(require_design_acceptance),
                "status": "PENDING" if require_design_acceptance else "NOT_REQUIRED",
            },
        },
        "release_status": "DRAFT",
    }
    _write_json(release_dir / "release_manifest.json", manifest, refuse_existing=True)
    return release_dir


def _required_candidate_identities(
    manifest: Mapping[str, object], release_dir: Path
) -> tuple[dict[str, object], list[dict[str, object]]]:
    artifacts = manifest.get("artifacts", {})
    if not isinstance(artifacts, Mapping):
        raise ReleaseBundleError("manifest artifacts must be an object")
    pptx_relative = artifacts.get("pptx")
    if not isinstance(pptx_relative, str):
        raise ReleaseBundleError("manifest does not declare a PPTX artifact")
    pptx_path = _inside(release_dir, pptx_relative, "pptx")
    if not pptx_path.is_file() or pptx_path.stat().st_size == 0:
        raise ReleaseBundleError("candidate PPTX is missing or empty")

    png_relative = artifacts.get("png_dir")
    if not isinstance(png_relative, str):
        raise ReleaseBundleError("manifest does not declare a PNG directory")
    png_dir = _inside(release_dir, png_relative, "png_dir")
    png_paths = (
        [
            item
            for item in sorted(png_dir.rglob("*.png"))
            if item.is_file() and item.stat().st_size > 0
        ]
        if png_dir.is_dir()
        else []
    )
    if not png_paths:
        raise ReleaseBundleError("candidate render directory contains no PNG files")
    return _file_identity(pptx_path), [_file_identity(item) for item in png_paths]


def record_design_acceptance(
    manifest_path: str | Path,
    status: str,
    statement: str,
) -> dict[str, object]:
    """Bind an explicit user visual verdict to the current PPTX and PNG render bytes."""

    path = _canonical_path(manifest_path)
    manifest = _read_json(path)
    acceptance = manifest.setdefault("acceptance", {})
    if not isinstance(acceptance, dict):
        raise ReleaseBundleError("manifest acceptance must be an object")
    design = acceptance.get("design_acceptance")
    if not isinstance(design, Mapping) or not design.get("required"):
        raise ReleaseBundleError(
            "design acceptance was not required at init; create a new release with "
            "--require-design-acceptance"
        )
    normalized_status = status.strip().upper()
    if normalized_status not in {"PASS", "REJECTED"}:
        raise ReleaseBundleError("design acceptance status must be PASS or REJECTED")
    normalized_statement = statement.strip()
    if not normalized_statement:
        raise ReleaseBundleError("design acceptance requires the user's explicit statement")

    candidate, renders = _required_candidate_identities(manifest, path.parent)
    acceptance["design_acceptance"] = {
        "required": True,
        "status": normalized_status,
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        "statement": normalized_statement,
        "candidate_pptx": candidate,
        "rendered_pages": renders,
    }
    manifest["release_status"] = "DRAFT" if normalized_status == "PASS" else "INCOMPLETE"
    _write_json(path, manifest, refuse_existing=False)
    return {
        "status": normalized_status,
        "manifest": _posix_path(path),
        "candidate_sha256": candidate["sha256"],
        "render_count": len(renders),
    }


def snapshot_tree(root: str | Path, exclude: str | Path) -> dict[str, object]:
    root_path, exclude_path, root_key, exclude_key = _scope(root, exclude)
    files: list[dict[str, object]] = []
    for path in sorted(root_path.rglob("*")):
        if path.is_symlink() or not path.is_file():
            continue
        try:
            path.relative_to(exclude_path)
        except ValueError:
            pass
        else:
            continue
        relative = _posix_path(path.relative_to(root_path))
        files.append(
            {"path": relative, "bytes": path.stat().st_size, "sha256": _sha256(path)}
        )
    return {
        "schema_version": 1,
        "root": root_key,
        "exclude": exclude_key,
        "files": files,
    }


def write_snapshot(root: str | Path, exclude: str | Path, output: str | Path) -> Path:
    snapshot = snapshot_tree(root, exclude)
    output_path = _canonical_path(output)
    _, exclude_path, _, _ = _scope(root, exclude)
    try:
        output_path.relative_to(exclude_path)
    except ValueError as exc:
        raise ReleaseBundleError(
            "snapshot output must be inside the excluded release directory"
        ) from exc
    _write_json(output_path, snapshot, refuse_existing=True)
    return output_path


def compare_snapshots(before: str | Path, after: str | Path) -> dict[str, object]:
    first = _read_json(before)
    second = _read_json(after)
    scope_fields = ("root", "exclude")
    if any(first.get(field) != second.get(field) for field in scope_fields):
        return {
            "status": "scope_mismatch",
            "root_before": first.get("root"),
            "root_after": second.get("root"),
            "exclude_before": first.get("exclude"),
            "exclude_after": second.get("exclude"),
            "added": [],
            "deleted": [],
            "changed": [],
        }
    before_map = {item["path"]: item for item in first.get("files", [])}
    after_map = {item["path"]: item for item in second.get("files", [])}
    added = sorted(set(after_map) - set(before_map))
    deleted = sorted(set(before_map) - set(after_map))
    changed = sorted(
        path for path in set(before_map) & set(after_map)
        if before_map[path].get("bytes") != after_map[path].get("bytes")
        or before_map[path].get("sha256") != after_map[path].get("sha256")
    )
    return {
        "status": "UNCHANGED" if not (added or deleted or changed) else "CHANGED",
        "root": first.get("root"),
        "exclude": first.get("exclude"),
        "added": added,
        "deleted": deleted,
        "changed": changed,
    }


def _package_parts(path: str | Path) -> dict[str, bytes]:
    source = _canonical_path(path)
    if source.suffix.lower() not in {".pptx", ".potx"}:
        raise ReleaseBundleError(f"input must be .pptx or .potx: {source}")
    try:
        with zipfile.ZipFile(source) as package:
            names = package.namelist()
            if len(names) != len(set(names)):
                raise ReleaseBundleError(f"package contains duplicate ZIP part names: {source}")
            return {name: package.read(name) for name in names}
    except (OSError, zipfile.BadZipFile) as exc:
        raise ReleaseBundleError(f"unable to read PPTX package: {source}: {exc}") from exc


def _rels_name(part: str) -> str:
    directory, filename = posixpath.split(part)
    return posixpath.join(directory, "_rels", filename + ".rels")


def _resolve_target(part: str, target: str) -> str:
    if target.startswith("/"):
        return target.lstrip("/")
    return posixpath.normpath(posixpath.join(posixpath.dirname(part), target))


def _relationship_map(part: str, parts: Mapping[str, bytes]) -> dict[str, tuple[str, str | None]]:
    rels_part = _rels_name(part)
    data = parts.get(rels_part)
    if data is None:
        return {}
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise ReleaseBundleError(f"invalid relationships XML: {rels_part}: {exc}") from exc
    result: dict[str, tuple[str, str | None]] = {}
    for relationship in root.findall(f"{{{REL_NS}}}Relationship"):
        rid = relationship.get("Id")
        target = relationship.get("Target")
        if not rid or target is None:
            continue
        mode = relationship.get("TargetMode")
        result[rid] = (target, mode)
    return result


def _relationship_closure(part: str, parts: Mapping[str, bytes]) -> dict[str, bytes]:
    closure: dict[str, bytes] = {}
    pending = [part]
    while pending:
        current = pending.pop()
        if current in closure:
            continue
        payload = parts.get(current)
        if payload is None:
            closure[current] = b"<missing>"
            continue
        closure[current] = payload
        rels_part = _rels_name(current)
        if rels_part in parts:
            closure[rels_part] = parts[rels_part]
        for target, mode in _relationship_map(current, parts).values():
            if mode and mode.lower() == "external":
                continue
            target_part = _resolve_target(current, target)
            if target_part not in closure:
                pending.append(target_part)
    return closure


def _slide_order(parts: Mapping[str, bytes]) -> list[str]:
    presentation = parts.get("ppt/presentation.xml")
    rels = _relationship_map("ppt/presentation.xml", parts)
    if presentation is not None:
        try:
            root = ET.fromstring(presentation)
            ordered: list[str] = []
            for slide_id in root.findall(f".//{{{P_NS}}}sldId"):
                rid = slide_id.get(f"{{{R_NS}}}id")
                if rid and rid in rels:
                    target, mode = rels[rid]
                    if not mode or mode.lower() != "external":
                        target_part = _resolve_target("ppt/presentation.xml", target)
                        if target_part in parts and target_part.startswith("ppt/slides/"):
                            ordered.append(target_part)
            if ordered:
                return ordered
        except ET.ParseError:
            pass
    numeric = []
    for name in parts:
        match = re.fullmatch(r"ppt/slides/slide(\d+)\.xml", name)
        if match:
            numeric.append((int(match.group(1)), name))
    return [name for _, name in sorted(numeric)]


def _global_part_names(parts: Mapping[str, bytes], slides: Iterable[str]) -> set[str]:
    slide_names = set(slides)
    for slide in slides:
        slide_names.add(_rels_name(slide))
    return set(parts) - slide_names


def _parent_visual_pass(manifest_path: str | Path | None) -> bool:
    if manifest_path is None:
        return False
    manifest = _read_json(manifest_path)
    visual = manifest.get("acceptance", {}).get("visual_qa", {})
    return visual.get("status") in {"PASS", "FULL_PASS"} and visual.get("scope") == "FULL_DECK"


def compare_slides(
    parent: str | Path,
    current: str | Path,
    changed_slides: Iterable[int],
    *,
    parent_visual_pass: bool = False,
    parent_manifest: str | Path | None = None,
) -> dict[str, object]:
    if parent_manifest is not None:
        parent_visual_pass = _parent_visual_pass(parent_manifest)
    parent_parts = _package_parts(parent)
    current_parts = _package_parts(current)
    parent_slides = _slide_order(parent_parts)
    current_slides = _slide_order(current_parts)
    changed = sorted({int(item) for item in changed_slides})
    reasons: list[str] = []
    if not parent_visual_pass:
        reasons.append("parent release lacks a recorded full-deck visual pass")
    if len(parent_slides) != len(current_slides):
        reasons.append("slide count changed")
    if any(item < 1 or item > len(current_slides) for item in changed):
        reasons.append("declared changed slide is outside the current slide range")

    page_differences: list[int] = []
    page_details: list[dict[str, object]] = []
    for index in range(1, max(len(parent_slides), len(current_slides)) + 1):
        before = parent_slides[index - 1] if index <= len(parent_slides) else None
        after = current_slides[index - 1] if index <= len(current_slides) else None
        if before is None or after is None:
            page_differences.append(index)
            page_details.append({"slide": index, "reason": "slide missing"})
            continue
        before_closure = _relationship_closure(before, parent_parts)
        after_closure = _relationship_closure(after, current_parts)
        names = sorted(set(before_closure) | set(after_closure))
        different_parts = [
            name for name in names if before_closure.get(name) != after_closure.get(name)
        ]
        if different_parts:
            page_differences.append(index)
            page_details.append({"slide": index, "different_parts": different_parts})
            if index not in changed:
                reasons.append(f"undeclared slide {index} changed")

    global_before = _global_part_names(parent_parts, parent_slides)
    global_after = _global_part_names(current_parts, current_slides)
    global_names = sorted(global_before | global_after)
    global_differences = [
        name for name in global_names if parent_parts.get(name) != current_parts.get(name)
    ]
    if global_differences:
        reasons.append("global package parts or relationships changed")

    proven = not reasons
    return {
        "status": "UNCHANGED_SLIDES_PROVEN" if proven else "FULL_VISUAL_QA_REQUIRED",
        "visual_scope": "CHANGED_SLIDES_ONLY" if proven else "FULL_DECK",
        "changed_slides": changed,
        "parent_slide_count": len(parent_slides),
        "current_slide_count": len(current_slides),
        "different_slides": page_differences,
        "slide_details": page_details,
        "global_differences": global_differences,
        "reasons": reasons,
    }


def finalize_release(manifest_path: str | Path, statuses: Mapping[str, object] | None = None) -> dict[str, object]:
    path = _canonical_path(manifest_path)
    manifest = _read_json(path)
    release_dir = path.parent
    artifacts = manifest.get("artifacts", {})
    required_files = {
        "pptx": artifacts.get("pptx"),
        "pdf": artifacts.get("pdf"),
    }
    missing: list[str] = []
    artifact_records: dict[str, object] = {}
    for key, relative in required_files.items():
        if not isinstance(relative, str):
            missing.append(key)
            continue
        target = _inside(release_dir, relative, key)
        if not target.is_file() or target.stat().st_size == 0:
            missing.append(key)
        else:
            artifact_records[key] = _file_identity(target)
    png_relative = artifacts.get("png_dir")
    png_files: list[Path] = []
    if isinstance(png_relative, str):
        png_dir = _inside(release_dir, png_relative, "png_dir")
        if png_dir.is_dir():
            png_files = [
                item for item in sorted(png_dir.rglob("*.png"))
                if item.is_file() and item.stat().st_size > 0
            ]
        if not png_files:
            missing.append("png_dir")
    else:
        missing.append("png_dir")
    evidence_relative = artifacts.get("evidence_dir")
    evidence_dir = _inside(release_dir, evidence_relative, "evidence_dir") if isinstance(evidence_relative, str) else None
    if evidence_dir is None or not evidence_dir.is_dir() or not any(item.is_file() for item in evidence_dir.rglob("*")):
        missing.append("evidence_dir")

    if statuses:
        acceptance = manifest.setdefault("acceptance", {})
        for key, value in statuses.items():
            if key in acceptance:
                if key == "design_acceptance":
                    raise ReleaseBundleError(
                        "design acceptance cannot come from a gate status file; use "
                        "record-design-acceptance after the user's explicit visual verdict"
                    )
                if isinstance(value, Mapping):
                    acceptance[key] = dict(value)
                else:
                    acceptance[key] = {"status": str(value)}
    manifest["artifacts_verified"] = artifact_records
    manifest["png_verified"] = [_file_identity(item) for item in png_files]
    manifest["missing_artifacts"] = missing
    acceptance = manifest.get("acceptance", {})
    required_statuses = [
        acceptance.get(key, {}).get("status") for key in ("static", "lo_render", "visual_qa")
    ]
    native_statuses = [
        acceptance.get(key, {}).get("status") for key in ("native_open", "native_render")
    ]
    design = acceptance.get("design_acceptance", {})
    design_required = isinstance(design, Mapping) and bool(design.get("required"))
    design_status = design.get("status") if isinstance(design, Mapping) else None
    if design_required and design_status == "PASS":
        current_candidate = artifact_records.get("pptx")
        current_renders = [_file_identity(item) for item in png_files]
        if (
            design.get("candidate_pptx") != current_candidate
            or design.get("rendered_pages") != current_renders
        ):
            updated_design = dict(design)
            updated_design["status"] = "STALE"
            updated_design["stale_reason"] = (
                "candidate PPTX or rendered-page bytes changed after the recorded user verdict"
            )
            acceptance["design_acceptance"] = updated_design
            design_status = "STALE"
    if missing or (design_required and design_status != "PASS"):
        release_status = "INCOMPLETE"
    elif all(value == "PASS" for value in required_statuses + native_statuses):
        release_status = "COMPLETE"
    elif all(value in {"PASS", "UNVERIFIED", "SKIPPED"} for value in required_statuses + native_statuses):
        release_status = "PARTIAL_ACCEPTANCE"
    else:
        release_status = "INCOMPLETE"
    manifest["release_status"] = release_status
    _write_json(path, manifest, refuse_existing=False)
    return {
        "status": release_status,
        "manifest": _posix_path(path),
        "missing_artifacts": missing,
        "artifact_count": len(artifact_records) + len(png_files),
    }


def _load_status_file(path: str | Path | None) -> dict[str, object] | None:
    return _read_json(path) if path else None


def _emit(value: object, output: str | Path | None = None) -> None:
    payload = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    if output:
        target = _canonical_path(output)
        _write_json(target, value if isinstance(value, dict) else {"result": value}, refuse_existing=True)
    else:
        print(payload, end="")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage formal PPTX release bundles")
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="create a new versioned release directory")
    init.add_argument("--output-root", required=True)
    init.add_argument("--topic", required=True)
    init.add_argument("--date")
    init.add_argument("--pptx-name", default="final.pptx")
    init.add_argument("--pdf-name", default="final.pdf")
    init.add_argument("--png-dir", default="png")
    init.add_argument("--evidence-dir", default="evidence")
    init.add_argument("--template")
    init.add_argument("--parent")
    init.add_argument("--changed-slide", type=int, action="append", default=[])
    init.add_argument("--require-design-acceptance", action="store_true")

    snapshot = sub.add_parser("snapshot", help="write a canonical external-output snapshot")
    snapshot.add_argument("--root", required=True)
    snapshot.add_argument("--exclude", required=True)
    snapshot.add_argument("--output", required=True)

    compare = sub.add_parser("compare-snapshots", help="compare two canonical snapshots")
    compare.add_argument("before")
    compare.add_argument("after")
    compare.add_argument("--output")

    slides = sub.add_parser("compare-slides", help="prove unchanged slides for a formal revision")
    slides.add_argument("parent")
    slides.add_argument("current")
    slides.add_argument("--changed-slide", type=int, action="append", default=[])
    slides.add_argument("--parent-manifest")
    slides.add_argument("--parent-visual-pass", action="store_true")
    slides.add_argument("--output")

    design = sub.add_parser(
        "record-design-acceptance",
        help="bind an explicit user visual verdict to the current PPTX and PNG renders",
    )
    design.add_argument("--manifest", required=True)
    design.add_argument("--status", required=True, choices=("PASS", "REJECTED"))
    design.add_argument("--statement", required=True)
    design.add_argument("--output")

    finalize = sub.add_parser("finalize", help="verify artifacts and update release manifest")
    finalize.add_argument("--manifest", required=True)
    finalize.add_argument("--status-json")
    finalize.add_argument("--output")
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    _configure_stdio()
    args = build_parser().parse_args(argv)
    try:
        if args.command == "init":
            release_dir = initialize_release(
                args.output_root,
                args.topic,
                date=args.date,
                pptx_name=args.pptx_name,
                pdf_name=args.pdf_name,
                png_dir=args.png_dir,
                evidence_dir=args.evidence_dir,
                template=args.template,
                parent=args.parent,
                changed_slides=args.changed_slide,
                require_design_acceptance=args.require_design_acceptance,
            )
            result: object = {"release_dir": _posix_path(release_dir)}
        elif args.command == "snapshot":
            result = {"snapshot": _posix_path(write_snapshot(args.root, args.exclude, args.output))}
        elif args.command == "compare-snapshots":
            result = compare_snapshots(args.before, args.after)
        elif args.command == "compare-slides":
            result = compare_slides(args.parent, args.current, args.changed_slide, parent_visual_pass=args.parent_visual_pass, parent_manifest=args.parent_manifest)
        elif args.command == "record-design-acceptance":
            result = record_design_acceptance(args.manifest, args.status, args.statement)
        elif args.command == "finalize":
            result = finalize_release(args.manifest, _load_status_file(args.status_json))
        else:
            raise ReleaseBundleError(f"unknown command: {args.command}")
        # The snapshot command already writes its requested output file; do not
        # try to use that same path for the small command-result envelope.
        result_output = None if args.command in {"init", "snapshot"} else getattr(args, "output", None)
        _emit(result, result_output)
        if isinstance(result, dict) and result.get("status") in {"scope_mismatch", "CHANGED", "FULL_VISUAL_QA_REQUIRED", "INCOMPLETE"}:
            return 1
        return 0
    except ReleaseBundleError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
