#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover - fallback for minimal Python installs
    yaml = None


SYSTEM_CONTAINERS = {".system", "codex-primary-runtime"}
SUPPORT_DIRS = {"assets", "docs", "evals", "references", "scripts"}
HISTORY_DIR_NAMES = {"rescued-skill-materials"}
HISTORY_SUFFIXES = ("-workspace",)
ACTIVE_SCOPES = {"flat_skill", "system_skill", "runtime_bundle"}
TEXT_EXTENSIONS = {".md", ".txt", ".yaml", ".yml", ".json"}
SKILL_LIKE_EXTENSIONS = {".md", ".yaml", ".yml", ".json", ".py", ".ps1"}
OVERLAP_THRESHOLD = 0.72

SCOPE_LABELS = {
    "flat_skill": "顶层技能",
    "system_skill": "系统技能",
    "runtime_bundle": "运行时技能包",
    "workspace_or_history": "工作材料或历史材料",
    "support_material": "说明或辅助材料",
    "nested": "嵌套目录",
}

LINK_PATTERN = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
ABSOLUTE_PATH_PATTERN = re.compile(
    r"(?<![A-Za-z])(?P<path>(?:[A-Za-z]:[\\/]|[A-Za-z]:/)[^`<>\r\n\t )\]]+)"
)
TOKEN_PATTERN = re.compile(r"[A-Za-z0-9\u4e00-\u9fff]+")
STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "be",
    "by",
    "for",
    "from",
    "if",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "the",
    "to",
    "use",
    "when",
    "with",
    "skill",
    "skills",
}


@dataclass(frozen=True)
class SkillRecord:
    path: Path
    skill_md: Path
    relative_path: str
    directory_name: str
    name: str
    description: str
    body: str
    frontmatter: dict[str, Any]
    scope: str
    local_targets: tuple[str, ...]

    @property
    def is_active(self) -> bool:
        return self.scope in ACTIVE_SCOPES


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check a local skill tree.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    scan = subparsers.add_parser("scan", help="Scan a skill root and write reports.")
    scan.add_argument("--root", required=True, help="Skill root to scan.")
    scan.add_argument("--reports-root", required=True, help="Directory for generated reports.")
    scan.add_argument("--date", required=True, help="Report date in YYYY-MM-DD format.")
    scan.add_argument("--json", action="store_true", help="Print summary JSON to stdout.")

    return parser.parse_args()


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def write_json(path: Path, payload: Any) -> None:
    write_text(path, json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def parse_simple_frontmatter(raw: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    current_key: str | None = None
    current_lines: list[str] = []

    def flush_block() -> None:
        nonlocal current_key, current_lines
        if current_key is not None:
            result[current_key] = "\n".join(line.rstrip() for line in current_lines).strip()
        current_key = None
        current_lines = []

    for line in raw.splitlines():
        if current_key is not None:
            if line.startswith((" ", "\t", "- ")):
                current_lines.append(line.strip())
                continue
            flush_block()

        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        if value in {"|", ">"}:
            current_key = key
            current_lines = []
        else:
            result[key] = value.strip("'\"")

    flush_block()
    return result


def split_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text

    end_index = None
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            end_index = index
            break

    if end_index is None:
        return {}, text

    raw = "\n".join(lines[1:end_index])
    body = "\n".join(lines[end_index + 1 :]).strip()
    if yaml is not None:
        try:
            parsed = yaml.safe_load(raw) or {}
            if isinstance(parsed, dict):
                return {str(key): value for key, value in parsed.items()}, body
        except Exception:
            pass
    return parse_simple_frontmatter(raw), body


def normalize_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def is_history_dir(name: str) -> bool:
    lowered = name.lower()
    return lowered in HISTORY_DIR_NAMES or lowered.endswith(HISTORY_SUFFIXES)


def classify_scope(root: Path, skill_dir: Path) -> str:
    try:
        relative = skill_dir.relative_to(root)
    except ValueError:
        return "nested"

    parts = relative.parts
    if not parts:
        return "nested"

    head = parts[0].lower()
    if is_history_dir(head):
        return "workspace_or_history"
    if head in SUPPORT_DIRS:
        return "support_material"
    if head == ".system":
        return "system_skill" if len(parts) == 2 else "nested"
    if head == "codex-primary-runtime":
        return "runtime_bundle" if len(parts) == 2 else "nested"
    return "flat_skill" if len(parts) == 1 else "nested"


def clean_target(target: str) -> str:
    cleaned = target.strip().strip("<>").strip().strip("`\"'")
    cleaned = cleaned.split("#", 1)[0].split("?", 1)[0].strip()
    return cleaned.replace("%20", " ")


def is_external_target(target: str) -> bool:
    lowered = target.lower()
    return lowered.startswith(
        (
            "#",
            "http://",
            "https://",
            "mailto:",
            "app://",
            "plugin://",
            "data:",
        )
    )


def is_placeholder_target(target: str) -> bool:
    lowered = target.lower().replace("/", "\\")
    return bool(re.match(r"^[a-z]:\\path(\\|$)", lowered))


def collect_local_targets(text: str) -> tuple[str, ...]:
    found: list[str] = []
    seen: set[str] = set()

    for raw in LINK_PATTERN.findall(text):
        if is_external_target(raw):
            continue
        cleaned = clean_target(raw)
        if cleaned and cleaned not in seen:
            found.append(cleaned)
            seen.add(cleaned)

    for match in ABSOLUTE_PATH_PATTERN.finditer(text):
        cleaned = clean_target(match.group("path").rstrip(".,;:"))
        if cleaned and cleaned not in seen:
            found.append(cleaned)
            seen.add(cleaned)

    return tuple(found)


def discover_skill_records(root: Path) -> list[SkillRecord]:
    skill_paths = sorted(
        path for path in root.rglob("SKILL.md") if ".git" not in {part.lower() for part in path.parts}
    )
    records: list[SkillRecord] = []

    for skill_md in skill_paths:
        text = read_text(skill_md)
        frontmatter, body = split_frontmatter(text)
        name = str(frontmatter.get("name", "") or "").strip()
        description = str(frontmatter.get("description", "") or "").strip()
        skill_dir = skill_md.parent
        records.append(
            SkillRecord(
                path=skill_dir,
                skill_md=skill_md,
                relative_path=skill_dir.relative_to(root).as_posix(),
                directory_name=skill_dir.name,
                name=name,
                description=description,
                body=body,
                frontmatter=frontmatter,
                scope=classify_scope(root, skill_dir),
                local_targets=collect_local_targets(text),
            )
        )

    return records


def finding(
    *,
    kind: str,
    severity: str,
    title: str,
    path: str,
    detail: str,
    suggested_action: str,
) -> dict[str, str]:
    return {
        "kind": kind,
        "severity": severity,
        "title": title,
        "path": path,
        "detail": detail,
        "suggested_action": suggested_action,
    }


def looks_like_skill_material(path: Path) -> bool:
    if not path.is_dir():
        return False
    for child in path.rglob("*"):
        if not child.is_file():
            continue
        if child.name == "SKILL.md" or child.suffix.lower() in SKILL_LIKE_EXTENSIONS:
            return True
    return False


def scan_top_level_without_skill(root: Path, records: list[SkillRecord]) -> list[dict[str, str]]:
    known_dirs = {record.path.resolve() for record in records}
    findings: list[dict[str, str]] = []

    for child in sorted(root.iterdir(), key=lambda item: item.name.lower()):
        if not child.is_dir():
            continue
        lowered = child.name.lower()
        if child.resolve() in known_dirs:
            continue
        if lowered.startswith(".") or lowered in SYSTEM_CONTAINERS or lowered in SUPPORT_DIRS:
            continue
        if is_history_dir(lowered):
            continue
        if not looks_like_skill_material(child):
            continue
        findings.append(
            finding(
                kind="missing_skill_md",
                severity="严重问题",
                title="顶层目录没有 SKILL.md",
                path=child.relative_to(root).as_posix(),
                detail="这个目录看起来像技能材料，但没有 `SKILL.md`，当前不会被当作技能。",
                suggested_action="人工复核",
            )
        )

    return findings


def scan_directory_hygiene(records: list[SkillRecord]) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    for record in records:
        if record.is_active:
            continue

        if record.scope == "workspace_or_history":
            title = "工作材料里有 SKILL.md"
            detail = "这个目录不算当前技能。请确认它只是工作材料，还是误放了正式技能。"
        elif record.scope == "support_material":
            title = "说明或辅助材料里有 SKILL.md"
            detail = "说明、脚本、示例材料里不应放正式技能入口。"
        else:
            title = "技能目录嵌套太深"
            detail = "当前本地方案要求一个技能直接放在扫描根目录下一层。"

        findings.append(
            finding(
                kind="directory_structure",
                severity="严重问题",
                title=title,
                path=record.relative_path,
                detail=detail,
                suggested_action="人工复核",
            )
        )

    return findings


def scan_broken_items(root: Path, records: list[SkillRecord]) -> list[dict[str, str]]:
    findings = scan_top_level_without_skill(root, records)

    for record in records:
        if not record.is_active:
            continue
        if not record.frontmatter:
            findings.append(
                finding(
                    kind="empty_frontmatter",
                    severity="严重问题",
                    title="文件开头配置为空",
                    path=record.relative_path,
                    detail="`SKILL.md` 没有可读取的文件开头配置。",
                    suggested_action="补边界",
                )
            )
        if not record.name:
            findings.append(
                finding(
                    kind="missing_name",
                    severity="严重问题",
                    title="缺少 name",
                    path=record.relative_path,
                    detail="`SKILL.md` 文件开头配置里缺少 `name:`。",
                    suggested_action="补边界",
                )
            )
        if not record.description:
            findings.append(
                finding(
                    kind="missing_description",
                    severity="严重问题",
                    title="缺少 description",
                    path=record.relative_path,
                    detail="`SKILL.md` 文件开头配置里缺少 `description:`。",
                    suggested_action="补边界",
                )
            )
        if not record.body.strip():
            findings.append(
                finding(
                    kind="empty_body",
                    severity="严重问题",
                    title="正文为空",
                    path=record.relative_path,
                    detail="`SKILL.md` 文件开头配置后没有正文说明。",
                    suggested_action="补边界",
                )
            )

    return findings


def scan_name_mismatch(records: list[SkillRecord]) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    for record in records:
        if not record.is_active or not record.name:
            continue
        if record.directory_name == record.name:
            continue
        findings.append(
            finding(
                kind="name_mismatch",
                severity="维护项",
                title="目录名和 name 不一致",
                path=record.relative_path,
                detail=f"目录名是 `{record.directory_name}`，`SKILL.md` 里的 `name:` 是 `{record.name}`。",
                suggested_action="补边界",
            )
        )
    return findings


def resolve_local_target(base_dir: Path, raw_target: str) -> Path | None:
    target = clean_target(raw_target)
    if not target or is_external_target(target) or is_placeholder_target(target):
        return None
    target_path = Path(target)
    if not target_path.is_absolute():
        target_path = base_dir / target_path
    return target_path


def scan_link_or_path_issues(records: list[SkillRecord]) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    for record in records:
        if not record.is_active:
            continue
        for target in record.local_targets:
            resolved = resolve_local_target(record.path, target)
            if resolved is None or resolved.exists():
                continue
            findings.append(
                finding(
                    kind="missing_local_target",
                    severity="维护项",
                    title="本地链接或路径失效",
                    path=record.relative_path,
                    detail=f"`{target}` 找不到。",
                    suggested_action="补引用",
                )
            )
    return findings


def collect_tokens(record: SkillRecord) -> set[str]:
    text = f"{record.name}\n{record.description}\n{record.body}".lower()
    tokens = {token for token in TOKEN_PATTERN.findall(text) if len(token) > 1}
    return {token for token in tokens if token not in STOPWORDS}


def similarity(left: SkillRecord, right: SkillRecord) -> float:
    left_tokens = collect_tokens(left)
    right_tokens = collect_tokens(right)
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def compare_active_pairs(records: list[SkillRecord]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    active = [record for record in records if record.is_active]
    duplicates: list[dict[str, Any]] = []
    overlaps: list[dict[str, Any]] = []

    for left, right in combinations(active, 2):
        left_key = normalize_name(left.name or left.directory_name)
        right_key = normalize_name(right.name or right.directory_name)
        if left_key and left_key == right_key:
            duplicates.append(
                {
                    "kind": "duplicate_candidate",
                    "severity": "维护项",
                    "left": left.relative_path,
                    "right": right.relative_path,
                    "name": left.name or right.name or left.directory_name,
                    "detail": "两个当前会用到的技能名字相同或归一化后相同。",
                    "suggested_action": "合并候选",
                }
            )
            continue

        score = similarity(left, right)
        if score >= OVERLAP_THRESHOLD:
            overlaps.append(
                {
                    "kind": "overlap_candidate",
                    "severity": "维护项",
                    "left": left.relative_path,
                    "right": right.relative_path,
                    "score": round(score, 3),
                    "detail": "两个技能文字相似，是否合并要看目标、输入、输出和触发场景是否真的重合。",
                    "suggested_action": "人工复核",
                }
            )

    duplicates.sort(key=lambda item: (item["left"], item["right"]))
    overlaps.sort(key=lambda item: (-item["score"], item["left"], item["right"]))
    return duplicates, overlaps


def build_active_skill_list(records: list[SkillRecord]) -> list[dict[str, str]]:
    return [
        {
            "relative_path": record.relative_path,
            "directory_name": record.directory_name,
            "name": record.name,
            "description": record.description,
            "scope": record.scope,
            "scope_label": SCOPE_LABELS.get(record.scope, record.scope),
        }
        for record in sorted(records, key=lambda item: item.relative_path.lower())
        if record.is_active
    ]


def build_no_action_notes(records: list[SkillRecord]) -> list[dict[str, str]]:
    skipped = sorted(record.relative_path for record in records if record.scope == "workspace_or_history")
    notes = [
        {
            "title": "工作材料和历史材料不算当前技能",
            "detail": "`*-workspace` 和 `rescued-skill-materials` 只作背景材料，不进入当前技能清单。",
        }
    ]
    if skipped:
        notes.append(
            {
                "title": "本次已排除的工作材料",
                "detail": "、".join(f"`{path}`" for path in skipped),
            }
        )
    return notes


def build_counts(
    *,
    records: list[SkillRecord],
    directory_hygiene: list[dict[str, str]],
    duplicates: list[dict[str, Any]],
    name_mismatch: list[dict[str, str]],
    overlaps: list[dict[str, Any]],
    link_or_path_issues: list[dict[str, str]],
    broken_items: list[dict[str, str]],
) -> dict[str, int]:
    return {
        "active_skills": sum(1 for record in records if record.is_active),
        "discovered_skill_dirs": len(records),
        "directory_structure_problems": len(directory_hygiene),
        "duplicate_candidates": len(duplicates),
        "name_mismatch": len(name_mismatch),
        "overlap_candidates": len(overlaps),
        "link_or_path_issues": len(link_or_path_issues),
        "broken_items": len(broken_items),
        "serious_problem_count": len(directory_hygiene) + len(broken_items),
    }


def render_bullets(items: list[str]) -> list[str]:
    return items if items else ["- 无"]


def render_active_skills(active_skills: list[dict[str, str]]) -> list[str]:
    if not active_skills:
        return ["- 无"]
    return [
        f"- `{item['relative_path']}` -> name: `{item['name'] or '未填写'}`（{item['scope_label']}）"
        for item in active_skills
    ]


def render_findings(items: list[dict[str, str]]) -> list[str]:
    if not items:
        return ["- 无"]
    lines = []
    for item in items:
        lines.append(
            f"- [{item['severity']}] `{item['path']}`: {item['title']}。{item['detail']} 建议：{item['suggested_action']}。"
        )
    return lines


def render_pair_findings(items: list[dict[str, Any]]) -> list[str]:
    if not items:
        return ["- 无"]
    lines = []
    for item in items:
        score_text = f" 相似度：{item['score']}。" if "score" in item else ""
        lines.append(
            f"- [{item['severity']}] `{item['left']}` + `{item['right']}`: {item['detail']}{score_text} 建议：{item['suggested_action']}。"
        )
    return lines


def render_counts(counts: dict[str, int]) -> list[str]:
    labels = [
        ("active_skills", "当前实际会用到的技能"),
        ("discovered_skill_dirs", "发现的 SKILL.md 数量"),
        ("directory_structure_problems", "目录结构问题"),
        ("duplicate_candidates", "真的重复技能"),
        ("name_mismatch", "名字不一致"),
        ("overlap_candidates", "职责相近但不该直接合并"),
        ("link_or_path_issues", "链接或路径失效"),
        ("broken_items", "空技能或坏技能"),
    ]
    return [f"- {label}：`{counts[key]}`" for key, label in labels]


def collect_suggested_actions(
    *,
    directory_hygiene: list[dict[str, str]],
    duplicates: list[dict[str, Any]],
    name_mismatch: list[dict[str, str]],
    overlaps: list[dict[str, Any]],
    link_or_path_issues: list[dict[str, str]],
    broken_items: list[dict[str, str]],
) -> list[str]:
    lines: list[str] = []
    for item in directory_hygiene + name_mismatch + link_or_path_issues + broken_items:
        lines.append(f"- `{item['path']}`：{item['suggested_action']}，{item['title']}。")
    for item in duplicates + overlaps:
        lines.append(
            f"- `{item['left']}` + `{item['right']}`：{item['suggested_action']}，{item['detail']}"
        )
    return lines if lines else ["- 无"]


def render_no_action_notes(notes: list[dict[str, str]]) -> list[str]:
    if not notes:
        return ["- 无"]
    return [f"- {item['title']}：{item['detail']}" for item in notes]


def build_report(
    *,
    date: str,
    root: Path,
    reports_root: Path,
    active_skills: list[dict[str, str]],
    counts: dict[str, int],
    directory_hygiene: list[dict[str, str]],
    duplicates: list[dict[str, Any]],
    name_mismatch: list[dict[str, str]],
    overlaps: list[dict[str, Any]],
    link_or_path_issues: list[dict[str, str]],
    broken_items: list[dict[str, str]],
    no_action_notes: list[dict[str, str]],
) -> str:
    action_lines = collect_suggested_actions(
        directory_hygiene=directory_hygiene,
        duplicates=duplicates,
        name_mismatch=name_mismatch,
        overlaps=overlaps,
        link_or_path_issues=link_or_path_issues,
        broken_items=broken_items,
    )

    sections = [
        f"# Skill 目录检查周报 {date}",
        "",
        "## 扫描范围",
        f"- 扫描根目录：`{root}`",
        f"- 报告目录：`{reports_root}`",
        "- 本地目录规则：顶层目录里有 `SKILL.md` 才算技能；工作材料和历史材料不算当前技能。",
        "",
        "## 当前实际会用到的技能",
        *render_active_skills(active_skills),
        "",
        "## 摘要计数",
        *render_counts(counts),
        "",
        "## 严重问题",
        *render_findings(directory_hygiene + broken_items),
        "",
        "## 真的重复技能",
        *render_pair_findings(duplicates),
        "",
        "## 名字不一致",
        *render_findings(name_mismatch),
        "",
        "## 职责相近但不该直接合并",
        *render_pair_findings(overlaps),
        "",
        "## 链接或路径失效",
        *render_findings(link_or_path_issues),
        "",
        "## 空技能或坏技能",
        *render_findings(broken_items),
        "",
        "## 建议动作",
        *render_bullets(action_lines),
        "",
        "## 无需动作说明",
        *render_no_action_notes(no_action_notes),
        "",
    ]
    return "\n".join(sections)


def scan(root: Path, reports_root: Path, date: str) -> dict[str, Any]:
    root = root.resolve()
    reports_root = reports_root.resolve()
    records = discover_skill_records(root)
    directory_hygiene = scan_directory_hygiene(records)
    broken_items = scan_broken_items(root, records)
    duplicates, overlaps = compare_active_pairs(records)
    name_mismatch = scan_name_mismatch(records)
    link_or_path_issues = scan_link_or_path_issues(records)
    active_skills = build_active_skill_list(records)
    no_action_notes = build_no_action_notes(records)
    counts = build_counts(
        records=records,
        directory_hygiene=directory_hygiene,
        duplicates=duplicates,
        name_mismatch=name_mismatch,
        overlaps=overlaps,
        link_or_path_issues=link_or_path_issues,
        broken_items=broken_items,
    )

    summary = {
        "version": "flat-skill-tree-v1",
        "date": date,
        "root": str(root),
        "reports_root": str(reports_root),
        "directory_rule": "顶层目录里有 SKILL.md 才算技能；工作材料和历史材料不算当前技能。",
        "counts": counts,
        "active_skills": active_skills,
        "findings": {
            "directory_structure_problems": directory_hygiene,
            "duplicate_candidates": duplicates,
            "name_mismatch": name_mismatch,
            "overlap_candidates": overlaps,
            "link_or_path_issues": link_or_path_issues,
            "broken_items": broken_items,
            "no_action_notes": no_action_notes,
        },
    }

    summary_path = reports_root / "manifests" / date / "summary.json"
    weekly_path = reports_root / "weekly" / f"{date}.md"
    write_json(summary_path, summary)
    write_text(
        weekly_path,
        build_report(
            date=date,
            root=root,
            reports_root=reports_root,
            active_skills=active_skills,
            counts=counts,
            directory_hygiene=directory_hygiene,
            duplicates=duplicates,
            name_mismatch=name_mismatch,
            overlaps=overlaps,
            link_or_path_issues=link_or_path_issues,
            broken_items=broken_items,
            no_action_notes=no_action_notes,
        ),
    )
    return summary


def main() -> int:
    args = parse_args()
    if args.command == "scan":
        summary = scan(Path(args.root), Path(args.reports_root), args.date)
        if args.json:
            print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
        else:
            print(f"summary: {Path(args.reports_root) / 'manifests' / args.date / 'summary.json'}")
            print(f"weekly: {Path(args.reports_root) / 'weekly' / f'{args.date}.md'}")
        return 0
    raise SystemExit(f"Unknown command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
