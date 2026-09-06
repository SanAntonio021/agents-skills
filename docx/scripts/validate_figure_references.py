#!/usr/bin/env python3
"""Validate Markdown figure references against one canonical project manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import struct
import sys
from pathlib import Path
from typing import Any


IMAGE_RE = re.compile(r"!\[(?P<alt>[^\]]*)\]\((?P<target><[^>]+>|[^\s\)]+)(?:\s+['\"][^'\"]*['\"])?\)")
FORBIDDEN_DIRS = {"working", "draft"}


def _issue(code: str, message: str, **details: Any) -> dict[str, Any]:
    return {"code": code, "message": message, **details}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def _png_size(path: Path) -> tuple[int, int] | None:
    with path.open("rb") as handle:
        header = handle.read(24)
    if len(header) < 24 or header[:8] != b"\x89PNG\r\n\x1a\n" or header[12:16] != b"IHDR":
        return None
    return struct.unpack(">II", header[16:24])


def _resolve_project_root(manifest_path: Path, manifest: dict[str, Any], override: Path | None) -> Path:
    if override is not None:
        return override.resolve()
    declared = manifest.get("project_root")
    if declared:
        return (manifest_path.parent / str(declared)).resolve()
    return manifest_path.parent.resolve()


def _resolve_markdown_target(document: Path, raw_target: str) -> Path:
    target = raw_target[1:-1] if raw_target.startswith("<") and raw_target.endswith(">") else raw_target
    candidate = Path(target)
    if not candidate.is_absolute():
        candidate = document.parent / candidate
    return candidate.resolve()


def _parse_images(lines: list[str]) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    for index, line in enumerate(lines):
        for match in IMAGE_RE.finditer(line):
            caption = None
            caption_line = None
            for next_index in range(index + 1, len(lines)):
                value = lines[next_index].strip()
                if value:
                    caption = value
                    caption_line = next_index + 1
                    break
            found.append(
                {
                    "line": index + 1,
                    "alt": match.group("alt").strip(),
                    "target": match.group("target").strip(),
                    "caption": caption,
                    "caption_line": caption_line,
                }
            )
    return found


def validate(
    manifest_path: Path,
    project_root_override: Path | None = None,
    markdown_overrides: list[Path] | None = None,
    expected_count_override: int | None = None,
) -> dict[str, Any]:
    manifest_path = manifest_path.resolve()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    project_root = _resolve_project_root(manifest_path, manifest, project_root_override)
    issues: list[dict[str, Any]] = []
    figures = manifest.get("figures")
    if not isinstance(figures, list):
        raise ValueError("manifest.figures must be an array")
    expected_figure_count = manifest.get("expected_figure_count")
    if expected_figure_count is not None and len(figures) != expected_figure_count:
        issues.append(
            _issue(
                "figure_total_mismatch",
                "最终图清单中的图片数量不符合预期",
                expected=expected_figure_count,
                actual=len(figures),
            )
        )

    by_path: dict[Path, dict[str, Any]] = {}
    declared_refs: dict[Path, list[tuple[dict[str, Any], dict[str, Any]]]] = {}
    numbers: set[int] = set()
    planned_numbers: set[int] = set()

    for entry in figures:
        number = entry.get("number")
        title = entry.get("title")
        rel_path = entry.get("path")
        if not isinstance(number, int) or not isinstance(title, str) or not isinstance(rel_path, str):
            issues.append(_issue("invalid_figure_entry", "图件条目缺少有效的 number、title 或 path", entry=entry))
            continue
        if number in numbers:
            issues.append(_issue("duplicate_figure_number", f"图号 {number} 重复", number=number))
        numbers.add(number)
        planned_number = entry.get("planned_word_number")
        if planned_number is not None:
            if not isinstance(planned_number, int):
                issues.append(_issue("invalid_planned_word_number", f"图{number}的拟定Word图号无效", number=number))
            elif planned_number in planned_numbers:
                issues.append(_issue("duplicate_planned_word_number", f"拟定Word图号 {planned_number} 重复", number=number))
            else:
                planned_numbers.add(planned_number)
        if entry.get("status") != "confirmed":
            issues.append(_issue("figure_not_confirmed", f"图{number}未标记为 confirmed", number=number))

        parts_lower = {part.lower() for part in Path(rel_path).parts}
        if parts_lower & FORBIDDEN_DIRS:
            issues.append(_issue("forbidden_figure_directory", f"图{number}路径位于 working 或 draft", number=number, path=rel_path))
        if manifest.get("require_final_directory", True) and "final" not in parts_lower:
            issues.append(_issue("figure_not_in_final_directory", f"图{number}路径不在 final 目录", number=number, path=rel_path))

        absolute = (project_root / Path(rel_path)).resolve()
        if absolute in by_path:
            issues.append(_issue("duplicate_figure_path", f"图{number}与其他图共用同一路径", number=number, path=rel_path))
        by_path[absolute] = entry
        if not absolute.is_file():
            issues.append(_issue("missing_figure_file", f"图{number}文件不存在", number=number, path=rel_path))
        else:
            expected_hash = str(entry.get("sha256", "")).upper()
            actual_hash = _sha256(absolute)
            if expected_hash and actual_hash != expected_hash:
                issues.append(_issue("figure_hash_mismatch", f"图{number} SHA-256不一致", number=number, expected=expected_hash, actual=actual_hash))
            expected_width = entry.get("width")
            expected_height = entry.get("height")
            if expected_width is not None or expected_height is not None:
                actual_size = _png_size(absolute)
                if actual_size is None:
                    issues.append(_issue("unsupported_image_size_check", f"图{number}不是可读取尺寸的PNG", number=number, path=rel_path))
                elif actual_size != (expected_width, expected_height):
                    issues.append(
                        _issue(
                            "figure_size_mismatch",
                            f"图{number}像素尺寸不一致",
                            number=number,
                            expected=[expected_width, expected_height],
                            actual=list(actual_size),
                        )
                    )

        refs = entry.get("markdown_references", [])
        if not isinstance(refs, list):
            issues.append(_issue("invalid_markdown_references", f"图{number}的 markdown_references 不是数组", number=number))
            continue
        for ref in refs:
            if not isinstance(ref, dict) or not isinstance(ref.get("document"), str):
                issues.append(_issue("invalid_markdown_reference", f"图{number}含无效正文引用条目", number=number, reference=ref))
                continue
            doc = (project_root / Path(ref["document"])).resolve()
            declared_refs.setdefault(doc, []).append((entry, ref))

    if markdown_overrides:
        documents = [path.resolve() for path in markdown_overrides]
    elif isinstance(manifest.get("markdown_document_order"), list):
        documents = [(project_root / Path(path)).resolve() for path in manifest["markdown_document_order"]]
    else:
        documents = sorted(declared_refs)

    actual_reference_count = 0
    actual_sequence: list[int] = []
    for document in documents:
        if not document.is_file():
            issues.append(_issue("missing_markdown_file", "Markdown文件不存在", document=str(document)))
            continue
        text = document.read_text(encoding="utf-8")
        lines = text.splitlines()
        if re.search(r"图\s*建议|图建议", text):
            issues.append(_issue("figure_placeholder_remaining", "Markdown仍含‘图建议’占位文字", document=str(document)))

        images = _parse_images(lines)
        actual_reference_count += len(images)
        seen: dict[Path, int] = {}
        declared_for_doc = declared_refs.get(document, [])
        declared_by_path = {(project_root / Path(entry["path"])).resolve(): (entry, ref) for entry, ref in declared_for_doc}

        for image in images:
            raw_parts = {part.lower() for part in Path(image["target"].strip("<>")).parts}
            if raw_parts & FORBIDDEN_DIRS:
                issues.append(
                    _issue(
                        "forbidden_markdown_image_path",
                        "Markdown图片引用位于 working 或 draft",
                        document=str(document),
                        line=image["line"],
                        target=image["target"],
                    )
                )
            resolved = _resolve_markdown_target(document, image["target"])
            seen[resolved] = seen.get(resolved, 0) + 1
            entry = by_path.get(resolved)
            if entry is None:
                issues.append(
                    _issue(
                        "unlisted_image_reference",
                        "Markdown引用的图片不是最终清单中的当前版本",
                        document=str(document),
                        line=image["line"],
                        target=image["target"],
                    )
                )
                continue
            actual_sequence.append(entry["number"])
            declared = declared_by_path.get(resolved)
            if declared is None:
                issues.append(
                    _issue(
                        "undeclared_document_reference",
                        f"图{entry['number']}未声明在该Markdown中使用",
                        number=entry["number"],
                        document=str(document),
                        line=image["line"],
                    )
                )
                continue
            _, ref = declared
            display_number = ref.get("display_number", entry["number"])
            expected_label = f"图{display_number} {entry['title']}"
            if image["alt"] != expected_label:
                issues.append(
                    _issue(
                        "figure_alt_mismatch",
                        f"图{entry['number']}替代文字与最终图题不一致",
                        number=entry["number"],
                        document=str(document),
                        line=image["line"],
                        expected=expected_label,
                        actual=image["alt"],
                    )
                )
            if image["caption"] != expected_label:
                issues.append(
                    _issue(
                        "figure_caption_mismatch",
                        f"图{entry['number']}题注与最终图题不一致",
                        number=entry["number"],
                        document=str(document),
                        line=image["caption_line"],
                        expected=expected_label,
                        actual=image["caption"],
                    )
                )

        for resolved, (entry, _ref) in declared_by_path.items():
            count = seen.get(resolved, 0)
            if count != 1:
                issues.append(
                    _issue(
                        "declared_reference_count_mismatch",
                        f"图{entry['number']}在声明的Markdown中应恰好引用一次",
                        number=entry["number"],
                        document=str(document),
                        actual=count,
                    )
                )

    expected_count = expected_count_override
    if expected_count is None:
        expected_count = manifest.get("expected_markdown_reference_count")
    if expected_count is not None and actual_reference_count != expected_count:
        issues.append(
            _issue(
                "markdown_reference_total_mismatch",
                "Markdown图片引用总数与清单不一致",
                expected=expected_count,
                actual=actual_reference_count,
            )
        )

    declared_sequence = manifest.get("document_sequence")
    if isinstance(declared_sequence, list):
        selected_documents = set(documents)
        expected_sequence = [
            number
            for number in declared_sequence
            if any(
                (project_root / Path(ref.get("document", ""))).resolve() in selected_documents
                for entry in figures
                if entry.get("number") == number
                for ref in entry.get("markdown_references", [])
                if isinstance(ref, dict)
            )
        ]
        if actual_sequence != expected_sequence:
            issues.append(
                _issue(
                    "markdown_figure_order_mismatch",
                    "Markdown中的图片顺序与最终清单不一致",
                    expected=expected_sequence,
                    actual=actual_sequence,
                )
            )

    return {
        "status": "passed" if not issues else "failed",
        "manifest": str(manifest_path),
        "project_root": str(project_root),
        "figure_count": len(figures),
        "markdown_document_count": len(documents),
        "markdown_reference_count": actual_reference_count,
        "issues": issues,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--project-root", type=Path)
    parser.add_argument("--markdown", action="append", type=Path)
    parser.add_argument("--expected-count", type=int)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        result = validate(args.manifest, args.project_root, args.markdown, args.expected_count)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        result = {"status": "failed", "issues": [_issue("validation_error", str(exc))]}
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"status: {result['status']}")
        for issue in result.get("issues", []):
            print(f"- {issue['code']}: {issue['message']}")
    return 0 if result.get("status") == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
