#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


SEGMENTED_ROOT_DIRS = {"archive", "custom", "docs", "vendor"}
SYSTEM_CONTAINER_DIRS = {".system", "codex-primary-runtime"}
RESERVED_ROOT_DIRS = SEGMENTED_ROOT_DIRS | SYSTEM_CONTAINER_DIRS
ACTIVE_SCOPES = {"custom", "vendor", "root_flat", "root_legacy", "system", "runtime_bundle"}
BODY_DUPLICATE_THRESHOLD = 0.82
OVERLAP_THRESHOLD = 0.65
DESCRIPTION_COMPARE_MAX = 1200
BODY_COMPARE_MAX = 4000
WRAPPER_KEYWORDS = (
    "wrapper",
    "wrapping",
    "base capability",
    "base skill",
    "custom",
    "vendor",
    "upstream",
    "本地包装",
    "包装层",
    "收口",
    "基座",
    "上游",
)
LOCAL_LINK_PATTERN = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
FENCED_CODE_BLOCK_PATTERN = re.compile(r"```.*?```", re.DOTALL)
ABSOLUTE_PATH_PATTERN = re.compile(
    r"(?<![A-Za-z])(?P<path>(?:[A-Za-z]:[\\/]|[A-Za-z]:/)[^`<>\r\n\t )\]]+)"
)
SKIP_WALK_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv"}


@dataclass(frozen=True)
class SkillRecord:
    path: Path
    skill_md: Path
    scope: str
    relative_path: str
    name: str
    normalized_name: str
    description: str
    description_norm: str
    description_tokens: frozenset[str]
    body: str
    body_norm: str
    body_tokens: frozenset[str]
    local_targets: tuple[str, ...]
    has_frontmatter: bool
    body_is_empty: bool
    frontmatter_is_empty: bool

    @property
    def is_active(self) -> bool:
        return self.scope in ACTIVE_SCOPES


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit synced skill tree hygiene.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    scan = subparsers.add_parser("scan", help="Scan a skill tree and write a report.")
    scan.add_argument("--root", required=True, help="Skill root to scan.")
    scan.add_argument("--reports-root", required=True, help="Directory for generated reports.")
    scan.add_argument("--date", required=True, help="Report date in YYYY-MM-DD format.")
    return parser.parse_args()


def split_frontmatter(text: str) -> tuple[dict[str, Any], str, bool]:
    if not text.startswith("---"):
        return {}, text, False

    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text, False

    closing_index = None
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            closing_index = index
            break

    if closing_index is None:
        return {}, text, False

    raw_frontmatter = "\n".join(lines[1:closing_index])
    try:
        loaded = yaml.safe_load(raw_frontmatter) or {}
        frontmatter = loaded if isinstance(loaded, dict) else {}
    except yaml.YAMLError:
        frontmatter = {}
        for raw_line in lines[1:closing_index]:
            if ":" not in raw_line:
                continue
            key, value = raw_line.split(":", 1)
            frontmatter[key.strip()] = value.strip()

    body = "\n".join(lines[closing_index + 1 :]).strip()
    return frontmatter, body, True


def normalize_name(value: str) -> str:
    return re.sub(r"[-_\s]+", "", value.lower())


def normalize_text(value: str) -> str:
    no_code = value.replace("`", " ")
    no_links = LOCAL_LINK_PATTERN.sub(lambda match: f" {match.group(1)} ", no_code)
    lowered = no_links.lower()
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", " ", lowered).strip()


def detect_layout_mode(root: Path) -> str:
    if any((root / name).is_dir() for name in SEGMENTED_ROOT_DIRS):
        return "segmented"
    return "flat"


def safe_resolve(path: Path) -> Path:
    try:
        return path.resolve()
    except OSError:
        return path


def tokenize_text(value: str, limit: int) -> frozenset[str]:
    tokens = value.split()
    return frozenset(tokens[:limit])


def token_similarity(left: frozenset[str], right: frozenset[str]) -> float:
    if not left or not right:
        return 0.0
    overlap = len(left & right)
    return (2 * overlap) / (len(left) + len(right))


def strip_anchor(target: str) -> str:
    cleaned = target.split("#", 1)[0].split("?", 1)[0].strip()
    return cleaned.strip("`\"'")


def is_local_target(target: str) -> bool:
    lowered = target.lower()
    return not (
        lowered.startswith("http://")
        or lowered.startswith("https://")
        or lowered.startswith("mailto:")
        or lowered.startswith("file://")
    )


def extract_local_targets(text: str) -> tuple[str, ...]:
    found: list[str] = []
    seen: set[str] = set()

    for raw_target in LOCAL_LINK_PATTERN.findall(text):
        cleaned = strip_anchor(raw_target)
        if cleaned and is_local_target(cleaned) and cleaned not in seen:
            found.append(cleaned)
            seen.add(cleaned)

    prose_text = FENCED_CODE_BLOCK_PATTERN.sub(" ", text)
    for line in prose_text.splitlines():
        if "|" in line:
            continue
        for match in ABSOLUTE_PATH_PATTERN.finditer(line):
            cleaned = match.group("path").rstrip(".,;:").strip("`\"'")
            if cleaned and cleaned not in seen:
                found.append(cleaned)
                seen.add(cleaned)

    return tuple(found)


def walk_tree(root: Path) -> list[tuple[Path, list[str], list[str]]]:
    walked: list[tuple[Path, list[str], list[str]]] = []
    seen: set[Path] = set()

    for current_root, dirnames, filenames in os.walk(root, followlinks=True):
        current_path = Path(current_root)
        resolved = safe_resolve(current_path)
        if resolved in seen:
            dirnames[:] = []
            continue
        seen.add(resolved)
        dirnames[:] = [name for name in dirnames if name not in SKIP_WALK_DIRS]
        walked.append((current_path, list(dirnames), list(filenames)))

    return walked


def discover_vendor_bundles(root: Path) -> set[str]:
    vendor_root = root / "vendor"
    bundles: set[str] = set()
    if not vendor_root.is_dir():
        return bundles

    for child in vendor_root.iterdir():
        if not child.is_dir() or (child / "SKILL.md").is_file():
            continue
        direct_dirs = [item for item in child.iterdir() if item.is_dir()]
        if not direct_dirs:
            continue
        if all((item / "SKILL.md").is_file() for item in direct_dirs):
            bundles.add(child.name.lower())
    return bundles


def classify_scope(root: Path, skill_dir: Path, vendor_bundles: set[str], layout_mode: str) -> str:
    relative = skill_dir.relative_to(root)
    parts = relative.parts
    if not parts:
        return "root_flat"

    head = parts[0].lower()
    if layout_mode == "segmented":
        if head == "custom":
            return "custom" if len(parts) == 2 else "nested"
        if head == "vendor":
            if len(parts) == 2:
                return "vendor"
            if len(parts) == 3 and parts[1].lower() in vendor_bundles:
                return "vendor"
            return "nested"
        if head == "archive":
            return "archive" if len(parts) == 2 else "archive_nested"
        if head == "docs":
            return "docs"
        if head == ".system":
            return "system" if len(parts) == 2 else "nested"
        if head == "codex-primary-runtime":
            return "runtime_bundle" if len(parts) == 2 else "nested"
        return "root_legacy" if len(parts) == 1 else "nested"

    if head == "archive":
        return "archive" if len(parts) == 1 else "archive_nested"
    if head == "docs":
        return "docs"
    if head == ".system":
        return "system" if len(parts) == 2 else "nested"
    if head == "codex-primary-runtime":
        return "runtime_bundle" if len(parts) == 2 else "nested"
    return "root_flat" if len(parts) == 1 else "nested"


def load_skill_record(root: Path, skill_md: Path, vendor_bundles: set[str], layout_mode: str) -> SkillRecord:
    text = skill_md.read_text(encoding="utf-8")
    frontmatter, body, has_frontmatter = split_frontmatter(text)
    name = frontmatter.get("name", skill_md.parent.name).strip()
    description = frontmatter.get("description", "").strip()
    description_norm = normalize_text(description)[:DESCRIPTION_COMPARE_MAX]
    body_norm = normalize_text(body)[:BODY_COMPARE_MAX]
    body_is_empty = not body.strip()
    frontmatter_is_empty = has_frontmatter and not any(value.strip() for value in frontmatter.values())
    return SkillRecord(
        path=skill_md.parent,
        skill_md=skill_md,
        scope=classify_scope(root, skill_md.parent, vendor_bundles, layout_mode),
        relative_path=skill_md.parent.relative_to(root).as_posix(),
        name=name,
        normalized_name=normalize_name(name or skill_md.parent.name),
        description=description,
        description_norm=description_norm,
        description_tokens=tokenize_text(description_norm, 160),
        body=body,
        body_norm=body_norm,
        body_tokens=tokenize_text(body_norm, 600),
        local_targets=extract_local_targets(text),
        has_frontmatter=has_frontmatter,
        body_is_empty=body_is_empty,
        frontmatter_is_empty=frontmatter_is_empty,
    )


def discover_skill_records(root: Path) -> list[SkillRecord]:
    vendor_bundles = discover_vendor_bundles(root)
    layout_mode = detect_layout_mode(root)
    skill_paths: list[Path] = []
    for current_root, _, filenames in walk_tree(root):
        if "SKILL.md" in filenames:
            skill_paths.append(Path(current_root) / "SKILL.md")
    records = [load_skill_record(root, path, vendor_bundles, layout_mode) for path in skill_paths]
    return sorted(records, key=lambda item: item.relative_path)


def tree_contains_skill_md(path: Path) -> bool:
    for _, _, filenames in walk_tree(path):
        if "SKILL.md" in filenames:
            return True
    return False


def looks_skillish(path: Path) -> bool:
    if (path / "scripts").is_dir() or (path / "references").is_dir() or (path / "assets").is_dir():
        return True
    if (path / "SKILL.md").is_file():
        return True
    if any(path.glob("*.md")):
        return True
    return tree_contains_skill_md(path)


def is_nonstandard_skill_entry(path: Path) -> bool:
    if path.suffix.lower() != ".md":
        return False
    if path.name.lower() == "skill.md":
        return False
    return "skill" in path.stem.lower()


def resolve_target(base_dir: Path, raw_target: str) -> Path:
    cleaned = strip_anchor(raw_target)
    if re.match(r"^[A-Za-z]:[\\/]", cleaned) or re.match(r"^[A-Za-z]:/", cleaned):
        return safe_resolve(Path(cleaned))
    return safe_resolve(base_dir / cleaned)


def scan_directory_hygiene(root: Path, records: list[SkillRecord]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for record in records:
        if record.scope == "root_legacy":
            findings.append(
                {
                    "kind": "root_level_active_skill",
                    "path": str(record.path),
                    "relative_path": record.relative_path,
                    "reason": "分层目录模式下，根目录不应直接放活跃 skill。",
                    "suggested_action": "人工复核",
                    "blocking": True,
                }
            )
        elif record.scope == "docs":
            findings.append(
                {
                    "kind": "docs_misplaced_skill",
                    "path": str(record.path),
                    "relative_path": record.relative_path,
                    "reason": "`docs/` 下不应存在可路由 skill。",
                    "suggested_action": "人工复核",
                    "blocking": True,
                }
            )
        elif record.scope == "nested":
            findings.append(
                {
                    "kind": "nested_skill_layout",
                    "path": str(record.path),
                    "relative_path": record.relative_path,
                    "reason": "skill 目录嵌套过深，或工作区快照混进了活跃树。",
                    "suggested_action": "人工复核",
                    "blocking": True,
                }
            )
    return sorted(findings, key=lambda item: item["relative_path"])


def discover_vendor_entry_variants(root: Path, records: list[SkillRecord]) -> list[dict[str, Any]]:
    variants_by_dir: dict[str, dict[str, Any]] = {}
    for record in records:
        if not record.is_active or record.scope != "custom":
            continue
        for target in record.local_targets:
            resolved = resolve_target(record.path, target)
            if not resolved.is_file() or not is_nonstandard_skill_entry(resolved):
                continue
            try:
                relative = resolved.relative_to(root)
            except ValueError:
                continue
            if len(relative.parts) != 3 or relative.parts[0].lower() != "vendor":
                continue
            vendor_dir = resolved.parent.resolve()
            if (vendor_dir / "SKILL.md").is_file():
                continue

            key = vendor_dir.relative_to(root).as_posix()
            item = variants_by_dir.setdefault(
                key,
                {
                    "kind": "known_vendor_entry_variant",
                    "path": str(vendor_dir),
                    "relative_path": key,
                    "entry_files": set(),
                    "source_wrappers": set(),
                    "reason": "custom wrapper 已显式引用该 vendor 目录中的非标准上游入口。",
                    "suggested_action": "保留",
                },
            )
            item["entry_files"].add(relative.as_posix())
            item["source_wrappers"].add(record.relative_path)

    findings: list[dict[str, Any]] = []
    for key in sorted(variants_by_dir):
        item = variants_by_dir[key]
        findings.append(
            {
                **item,
                "entry_files": sorted(item["entry_files"]),
                "source_wrappers": sorted(item["source_wrappers"]),
            }
        )
    return findings


def scan_broken_items(
    root: Path,
    records: list[SkillRecord],
    vendor_bundles: set[str],
    known_vendor_variants: set[str],
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    layout_mode = detect_layout_mode(root)
    active_bases = [root / "custom", root / "vendor"] if layout_mode == "segmented" else []
    seen_paths = {record.path for record in records}

    for base in active_bases:
        if not base.is_dir():
            continue
        for child in sorted(base.iterdir(), key=lambda item: item.name.lower()):
            if not child.is_dir() or child.name.startswith(".") or child.name.startswith("__"):
                continue
            if base.name.lower() == "vendor" and child.name.lower() in vendor_bundles:
                continue
            child_relative = child.resolve().relative_to(root).as_posix()
            if child_relative in known_vendor_variants:
                continue
            if child not in seen_paths:
                findings.append(
                    {
                        "kind": "missing_skill_md",
                        "path": str(child.resolve()),
                        "relative_path": child_relative,
                        "reason": "活跃 skill 目录缺少直接可解析的 `SKILL.md`。",
                        "suggested_action": "人工复核",
                        "blocking": True,
                    }
                )

    if layout_mode == "flat":
        for container_name in SYSTEM_CONTAINER_DIRS:
            container = root / container_name
            if not container.is_dir():
                continue
            for child in sorted(container.iterdir(), key=lambda item: item.name.lower()):
                if not child.is_dir() or child.name.startswith(".") or child.name.startswith("__"):
                    continue
                if child in seen_paths:
                    continue
                if looks_skillish(child):
                    findings.append(
                        {
                            "kind": "container_missing_skill_md",
                            "path": str(child),
                            "relative_path": child.relative_to(root).as_posix(),
                            "reason": "系统容器下的目录像 skill，但缺少直接可解析的 `SKILL.md`。",
                            "suggested_action": "人工复核",
                            "blocking": True,
                        }
                    )

    for child in sorted(root.iterdir(), key=lambda item: item.name.lower()):
        if not child.is_dir():
            continue
        if child.name.lower() in RESERVED_ROOT_DIRS or child.name.startswith("."):
            continue
        if (child / "SKILL.md").is_file():
            continue
        if looks_skillish(child):
            findings.append(
                {
                    "kind": "root_level_missing_skill_md",
                    "path": str(child.resolve()),
                    "relative_path": child.resolve().relative_to(root).as_posix(),
                    "reason": "根目录遗留 skill-like 目录，但缺少 `SKILL.md`。",
                    "suggested_action": "人工复核",
                    "blocking": True,
                }
            )

    for record in records:
        if not record.is_active:
            continue
        if record.frontmatter_is_empty:
            findings.append(
                {
                    "kind": "empty_frontmatter",
                    "path": str(record.skill_md),
                    "relative_path": f"{record.relative_path}/SKILL.md",
                    "reason": "`SKILL.md` 文件开头配置为空，无法稳定路由。",
                    "suggested_action": "人工复核",
                    "blocking": True,
                }
            )
        if record.body_is_empty:
            findings.append(
                {
                    "kind": "empty_body",
                    "path": str(record.skill_md),
                    "relative_path": f"{record.relative_path}/SKILL.md",
                    "reason": "`SKILL.md` 正文为空。",
                    "suggested_action": "人工复核",
                    "blocking": True,
                }
            )

    unique = {
        (item["kind"], item["relative_path"]): item
        for item in findings
    }
    return sorted(unique.values(), key=lambda item: (item["kind"], item["relative_path"]))


def scan_name_drift(records: list[SkillRecord]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for record in records:
        if not record.is_active or record.scope == "runtime_bundle":
            continue
        folder_name = record.path.name
        if normalize_name(folder_name) == record.normalized_name:
            continue
        findings.append(
            {
                "skill": record.relative_path,
                "folder_name": folder_name,
                "declared_name": record.name,
                "reason": "目录名和 `SKILL.md` 里的 `name:` 对不上。",
                "suggested_action": "人工复核",
            }
        )

    unique = {
        (item["skill"], item["folder_name"], item["declared_name"]): item
        for item in findings
    }
    return sorted(unique.values(), key=lambda item: item["skill"])


def references_other_skill(custom_skill: SkillRecord, vendor_skill: SkillRecord) -> bool:
    custom_text = f"{custom_skill.description}\n{custom_skill.body}".lower()
    vendor_tokens = {
        vendor_skill.name.lower(),
        vendor_skill.path.name.lower(),
        vendor_skill.relative_path.lower(),
        vendor_skill.skill_md.as_posix().lower(),
    }
    if any(token and token in custom_text for token in vendor_tokens):
        return True

    vendor_candidates = {
        vendor_skill.skill_md,
        vendor_skill.path,
        safe_resolve(vendor_skill.skill_md),
        safe_resolve(vendor_skill.path),
    }
    for target in custom_skill.local_targets:
        resolved = resolve_target(custom_skill.path, target)
        if resolved in vendor_candidates:
            return True
    return False


def wrapper_relationship(left: SkillRecord, right: SkillRecord) -> tuple[bool, str]:
    if {left.scope, right.scope} != {"custom", "vendor"}:
        return False, ""

    custom_skill = left if left.scope == "custom" else right
    vendor_skill = right if custom_skill is left else left
    relation_text = f"{custom_skill.description}\n{custom_skill.body}".lower()
    has_wrapper_keyword = any(keyword in relation_text for keyword in WRAPPER_KEYWORDS)
    has_direct_reference = references_other_skill(custom_skill, vendor_skill)
    if has_wrapper_keyword and has_direct_reference:
        return True, "custom skill 明确声明了对 vendor 基座的本地包装关系。"
    if has_direct_reference:
        return True, "custom skill 在正文或 Related Skills 中显式指向对应 vendor skill。"
    return False, ""


def compare_active_pairs(records: list[SkillRecord]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    active_records = [record for record in records if record.is_active]
    duplicates: list[dict[str, Any]] = []
    overlaps: list[dict[str, Any]] = []
    wrapper_exclusions: list[dict[str, Any]] = []

    for index, left in enumerate(active_records):
        for right in active_records[index + 1 :]:
            name_collision = left.normalized_name == right.normalized_name
            body_score = token_similarity(left.body_tokens, right.body_tokens)
            description_score = token_similarity(left.description_tokens, right.description_tokens)
            effective_score = max(body_score, description_score)

            is_wrapper, wrapper_reason = wrapper_relationship(left, right)
            if is_wrapper and (name_collision or effective_score >= OVERLAP_THRESHOLD):
                wrapper_exclusions.append(
                    {
                        "left": left.relative_path,
                        "right": right.relative_path,
                        "body_score": round(body_score, 4),
                        "description_score": round(description_score, 4),
                        "reason": wrapper_reason,
                        "suggested_action": "保留",
                    }
                )
                continue

            if name_collision or body_score >= BODY_DUPLICATE_THRESHOLD:
                duplicates.append(
                    {
                        "left": left.relative_path,
                        "right": right.relative_path,
                        "body_score": round(body_score, 4),
                        "description_score": round(description_score, 4),
                        "reason": "归一化名称冲突。" if name_collision else "正文相似度达到重复阈值。",
                        "suggested_action": "合并候选" if body_score >= BODY_DUPLICATE_THRESHOLD else "人工复核",
                    }
                )
                continue

            if left.scope == right.scope == "vendor":
                continue

            if OVERLAP_THRESHOLD <= effective_score < BODY_DUPLICATE_THRESHOLD:
                overlaps.append(
                    {
                        "left": left.relative_path,
                        "right": right.relative_path,
                        "body_score": round(body_score, 4),
                        "description_score": round(description_score, 4),
                        "reason": "description 或正文相似，疑似边界没收紧。",
                        "suggested_action": "补边界",
                    }
                )

    sort_key = lambda item: (item["left"], item["right"])
    return sorted(duplicates, key=sort_key), sorted(overlaps, key=sort_key), sorted(wrapper_exclusions, key=sort_key)


def scan_path_drift(records: list[SkillRecord]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for record in records:
        if not record.is_active:
            continue
        for target in record.local_targets:
            resolved = resolve_target(record.path, target)
            if resolved.exists():
                continue
            findings.append(
                {
                    "skill": record.relative_path,
                    "target": target,
                    "resolved_path": str(resolved),
                    "reason": "本地引用目标不存在。",
                    "suggested_action": "补引用",
                }
            )
    unique = {
        (item["skill"], item["target"]): item
        for item in findings
    }
    return sorted(unique.values(), key=lambda item: (item["skill"], item["target"]))


def build_counts(
    records: list[SkillRecord],
    directory_hygiene: list[dict[str, Any]],
    duplicates: list[dict[str, Any]],
    name_drift: list[dict[str, Any]],
    overlaps: list[dict[str, Any]],
    path_drift: list[dict[str, Any]],
    broken_items: list[dict[str, Any]],
    wrapper_exclusions: list[dict[str, Any]],
) -> dict[str, int]:
    return {
        "active_skills": sum(1 for record in records if record.is_active),
        "archive_skills": sum(1 for record in records if record.scope.startswith("archive")),
        "total_discovered_skill_dirs": len(records),
        "directory_hygiene": len(directory_hygiene),
        "duplicate_candidates": len(duplicates),
        "name_drift": len(name_drift),
        "overlap_candidates": len(overlaps),
        "path_drift": len(path_drift),
        "broken_items": len(broken_items),
        "wrapper_exclusions": len(wrapper_exclusions),
        "blocking_items": len(directory_hygiene) + len(broken_items),
    }


def build_suggested_actions(
    directory_hygiene: list[dict[str, Any]],
    duplicates: list[dict[str, Any]],
    name_drift: list[dict[str, Any]],
    overlaps: list[dict[str, Any]],
    path_drift: list[dict[str, Any]],
    broken_items: list[dict[str, Any]],
) -> list[dict[str, str]]:
    actions: list[dict[str, str]] = []
    for item in directory_hygiene + broken_items:
        actions.append(
            {
                "label": item["suggested_action"],
                "subject": item["relative_path"],
                "reason": item["reason"],
            }
        )
    for item in duplicates:
        actions.append(
            {
                "label": item["suggested_action"],
                "subject": f"{item['left']} <-> {item['right']}",
                "reason": item["reason"],
            }
        )
    for item in name_drift:
        actions.append(
            {
                "label": item["suggested_action"],
                "subject": item["skill"],
                "reason": item["reason"],
            }
        )
    for item in overlaps:
        actions.append(
            {
                "label": item["suggested_action"],
                "subject": f"{item['left']} <-> {item['right']}",
                "reason": item["reason"],
            }
        )
    for item in path_drift:
        actions.append(
            {
                "label": item["suggested_action"],
                "subject": f"{item['skill']} -> {item['target']}",
                "reason": item["reason"],
            }
        )
    return sorted(actions, key=lambda item: (item["label"], item["subject"]))


def build_no_action_notes(
    directory_hygiene: list[dict[str, Any]],
    duplicates: list[dict[str, Any]],
    name_drift: list[dict[str, Any]],
    overlaps: list[dict[str, Any]],
    path_drift: list[dict[str, Any]],
    broken_items: list[dict[str, Any]],
    wrapper_exclusions: list[dict[str, Any]],
    vendor_entry_variants: list[dict[str, Any]],
) -> list[str]:
    notes: list[str] = []
    for item in wrapper_exclusions:
        notes.append(
            f"[保留] {item['left']} <-> {item['right']}: {item['reason']}"
        )
    for item in vendor_entry_variants:
        entry_files = "、".join(f"`{path}`" for path in item["entry_files"])
        wrappers = "、".join(f"`{path}`" for path in item["source_wrappers"])
        notes.append(
            f"[保留] {item['relative_path']}: {wrappers} 显式引用了非标准上游入口 {entry_files}。"
        )
    if not directory_hygiene:
        notes.append("目录结构问题：未发现异常嵌套、`docs/` 误放 skill 或分层不一致。")
    if not duplicates:
        notes.append("真的重复技能：未发现满足重复阈值的当前可用技能组合。")
    if not name_drift:
        notes.append("名字不一致：未发现目录名和 `name:` 对不上的当前可用技能。")
    if not overlaps:
        notes.append("职责相近但不该直接合并：未发现满足相似阈值的当前可用技能组合。")
    if not path_drift:
        notes.append("链接或路径失效：未发现失效的本地绝对路径或相对引用。")
    if not broken_items:
        notes.append("空技能或坏技能：未发现缺 `SKILL.md`、空文件开头配置或空正文的当前可用技能。")
    return notes


def render_list(lines: list[str]) -> str:
    return "\n".join(lines) if lines else "- 无"


def render_directory_hygiene(items: list[dict[str, Any]]) -> list[str]:
    return [
        f"- `{item['relative_path']}`: {item['reason']} 建议：`{item['suggested_action']}`"
        for item in items
    ]


def render_duplicates(items: list[dict[str, Any]]) -> list[str]:
    return [
        f"- `{item['left']}` <-> `{item['right']}`: {item['reason']} "
        f"(body={item['body_score']:.2f}, desc={item['description_score']:.2f}) 建议：`{item['suggested_action']}`"
        for item in items
    ]


def render_name_drift(items: list[dict[str, Any]]) -> list[str]:
    return [
        f"- `{item['skill']}`: 目录名是 `{item['folder_name']}`，`name:` 是 `{item['declared_name']}`。"
        for item in items
    ]


def render_overlaps(items: list[dict[str, Any]]) -> list[str]:
    return [
        f"- `{item['left']}` <-> `{item['right']}`: {item['reason']} "
        f"(body={item['body_score']:.2f}, desc={item['description_score']:.2f}) 建议：`{item['suggested_action']}`"
        for item in items
    ]


def render_path_drift(items: list[dict[str, Any]]) -> list[str]:
    return [
        f"- `{item['skill']}` -> `{item['target']}`: 解析到 `{item['resolved_path']}`，但目标不存在。"
        for item in items
    ]


def render_broken(items: list[dict[str, Any]]) -> list[str]:
    return [
        f"- `{item['relative_path']}`: {item['reason']} 建议：`{item['suggested_action']}`"
        for item in items
    ]


def render_actions(items: list[dict[str, str]]) -> list[str]:
    return [
        f"- `[{item['label']}]` {item['subject']}: {item['reason']}"
        for item in items
    ]


def render_summary_counts(counts: dict[str, int]) -> list[str]:
    return [
        f"- 当前实际会用到的技能：`{counts['active_skills']}`",
        f"- 归档技能：`{counts['archive_skills']}`",
        f"- 发现的 `SKILL.md` 目录：`{counts['total_discovered_skill_dirs']}`",
        f"- 严重问题：`{counts['blocking_items']}`",
        f"- 目录结构问题：`{counts['directory_hygiene']}`",
        f"- 真的重复技能：`{counts['duplicate_candidates']}`",
        f"- 名字不一致：`{counts['name_drift']}`",
        f"- 职责相近但不该直接合并：`{counts['overlap_candidates']}`",
        f"- 链接或路径失效：`{counts['path_drift']}`",
        f"- 空技能或坏技能：`{counts['broken_items']}`",
        f"- 本地补充关系，不算重复：`{counts['wrapper_exclusions']}`",
    ]


def render_active_skills(records: list[SkillRecord]) -> list[str]:
    return [
        f"- `{record.relative_path}` -> `name: {record.name}` (`{record.scope}`)"
        for record in records
        if record.is_active
    ]


def render_weekly_report(
    date_str: str,
    root: Path,
    reports_root: Path,
    layout_mode: str,
    records: list[SkillRecord],
    counts: dict[str, int],
    directory_hygiene: list[dict[str, Any]],
    duplicates: list[dict[str, Any]],
    name_drift: list[dict[str, Any]],
    overlaps: list[dict[str, Any]],
    path_drift: list[dict[str, Any]],
    broken_items: list[dict[str, Any]],
    suggested_actions: list[dict[str, str]],
    no_action_notes: list[str],
) -> str:
    scope_lines = [
        f"- 扫描根目录：`{root}`",
        f"- 报告目录：`{reports_root}`",
        f"- 目录模型：`{layout_mode}`",
    ]
    if layout_mode == "segmented":
        scope_lines.extend(
            [
                "- 当前会用到的来源：`custom/`、`vendor/` 和少量迁移遗留的根目录 skill",
                "- `archive/` 只作辅助判断，不参与活跃路由",
                "- `docs/` 不参与 skill 路由，但会检查是否误放 `SKILL.md`",
            ]
        )
    else:
        scope_lines.extend(
            [
                "- 顶层含 `SKILL.md` 的目录视为活跃 skill",
                "- `.system/` 和 `codex-primary-runtime/` 视为系统容器",
                "- 如果要判断“当前真的加载了什么”，优先扫描 Codex 实际读取的技能目录",
            ]
        )
    blocking_items = directory_hygiene + broken_items
    return f"""# Skill Hygiene Audit

- 日期：`{date_str}`

## 扫描范围

{render_list(scope_lines)}

## 摘要计数

{render_list(render_summary_counts(counts))}

## 当前实际会用到的技能

{render_list(render_active_skills(records))}

## 严重问题

{render_list(render_directory_hygiene(blocking_items))}

## 真的重复技能

{render_list(render_duplicates(duplicates))}

## 名字不一致

{render_list(render_name_drift(name_drift))}

## 职责相近但不该直接合并

{render_list(render_overlaps(overlaps))}

## 链接或路径失效

{render_list(render_path_drift(path_drift))}

## 空技能或坏技能

{render_list(render_broken(broken_items))}

## 建议动作

{render_list(render_actions(suggested_actions))}

## 无需动作说明

{render_list([f"- {note}" for note in no_action_notes])}
"""


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(content)


def scan(root: Path, reports_root: Path, date_str: str) -> dict[str, Path]:
    root = root.resolve()
    reports_root = reports_root.resolve()
    reports_root.mkdir(parents=True, exist_ok=True)
    layout_mode = detect_layout_mode(root)
    vendor_bundles = discover_vendor_bundles(root)
    records = discover_skill_records(root)
    vendor_entry_variants = discover_vendor_entry_variants(root, records)
    known_vendor_variants = {item["relative_path"] for item in vendor_entry_variants}

    directory_hygiene = scan_directory_hygiene(root, records)
    broken_items = scan_broken_items(root, records, vendor_bundles, known_vendor_variants)
    duplicates, overlaps, wrapper_exclusions = compare_active_pairs(records)
    name_drift = scan_name_drift(records)
    path_drift = scan_path_drift(records)
    counts = build_counts(
        records,
        directory_hygiene,
        duplicates,
        name_drift,
        overlaps,
        path_drift,
        broken_items,
        wrapper_exclusions,
    )
    suggested_actions = build_suggested_actions(
        directory_hygiene,
        duplicates,
        name_drift,
        overlaps,
        path_drift,
        broken_items,
    )
    no_action_notes = build_no_action_notes(
        directory_hygiene,
        duplicates,
        name_drift,
        overlaps,
        path_drift,
        broken_items,
        wrapper_exclusions,
        vendor_entry_variants,
    )

    summary_payload = {
        "version": 1,
        "date": date_str,
        "root": str(root),
        "reports_root": str(reports_root),
        "layout_mode": layout_mode,
        "counts": counts,
        "active_skills": [
            {
                "name": record.name,
                "path": str(record.path),
                "relative_path": record.relative_path,
                "scope": record.scope,
                "description": record.description,
            }
            for record in records
            if record.is_active
        ],
        "findings": {
            "directory_hygiene": directory_hygiene,
            "duplicate_candidates": duplicates,
            "name_drift": name_drift,
            "overlap_candidates": overlaps,
            "path_drift": path_drift,
            "broken_items": broken_items,
            "vendor_entry_variants": vendor_entry_variants,
            "wrapper_exclusions": wrapper_exclusions,
            "suggested_actions": suggested_actions,
            "no_action_notes": no_action_notes,
        },
    }

    summary_path = reports_root / "manifests" / date_str / "summary.json"
    weekly_path = reports_root / "weekly" / f"{date_str}.md"
    weekly_report = render_weekly_report(
        date_str,
        root,
        reports_root,
        layout_mode,
        records,
        counts,
        directory_hygiene,
        duplicates,
        name_drift,
        overlaps,
        path_drift,
        broken_items,
        suggested_actions,
        no_action_notes,
    )

    write_json(summary_path, summary_payload)
    write_text(weekly_path, weekly_report)
    return {"summary": summary_path, "weekly": weekly_path}


def main() -> int:
    args = parse_args()
    if args.command == "scan":
        outputs = scan(Path(args.root), Path(args.reports_root), args.date)
        print(f"summary: {outputs['summary']}")
        print(f"weekly: {outputs['weekly']}")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
