#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import re
import shutil
import subprocess
import sys
import tomllib
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any


ALLOWED_SKILL_STATUSES = {"confirmed", "none"}
ALLOWED_DISPOSITIONS = {"rejected", "no-impact"}
ALWAYS_IGNORED_NAMES = {
    "changelog",
    "changelog.md",
}
VERSION_FILE_NAMES = {"version", "version.txt", "version.md"}
STRUCTURED_VERSION_FILES = {"manifest.json", "package-lock.json", "package.json", "pyproject.toml"}
SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")


@dataclass(frozen=True)
class SourceRecord:
    id: str
    mirror_id: str
    repo_url: str
    upstream_path: str
    accepted_commit: str
    accepted_version: str
    license: str
    baseline_kind: str
    tracked_paths: tuple[str, ...]
    license_paths: tuple[str, ...]
    evidence: tuple[str, ...]
    evidence_files: tuple[str, ...]
    adopted: tuple[str, ...]
    excluded: tuple[str, ...]


@dataclass(frozen=True)
class SkillRecord:
    name: str
    status: str
    last_discovery_date: str
    last_review_date: str
    notes: str
    sources: tuple[SourceRecord, ...]


@dataclass(frozen=True)
class MirrorRecord:
    id: str
    repo_url: str
    branch: str
    local_path: Path
    exposure_policy: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Maintain reviewed upstream sources for local skills.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    def add_common(sub: argparse.ArgumentParser) -> None:
        sub.add_argument("--registry", required=True, type=Path)
        sub.add_argument("--mirrors-registry", required=True, type=Path)
        sub.add_argument("--skills-root", required=True, type=Path)

    validate = subparsers.add_parser("validate", help="Validate source coverage and mirror references.")
    add_common(validate)
    validate.add_argument("--require-rendered", action="store_true")
    validate.add_argument("--json", action="store_true")

    render = subparsers.add_parser("render", help="Render per-skill upstream source references.")
    add_common(render)
    render.add_argument("--check", action="store_true", help="Check for drift without writing files.")
    render.add_argument("--json", action="store_true")

    for command, help_text in (
        ("report", "Compare accepted baselines with local mirror heads."),
        ("weekly-run", "Refresh mirrors, isolate failures, and generate the weekly report."),
    ):
        report = subparsers.add_parser(command, help=help_text)
        add_common(report)
        report.add_argument("--reports-root", required=True, type=Path)
        report.add_argument("--date", required=True)
        report.add_argument("--state", type=Path)
        report.add_argument("--json", action="store_true")

    prepare = subparsers.add_parser("prepare-review", help="Create an isolated review workspace.")
    add_common(prepare)
    prepare.add_argument("--reports-root", required=True, type=Path)
    prepare.add_argument("--date", required=True)
    prepare.add_argument("--skill", required=True)
    prepare.add_argument("--source", required=True)
    prepare.add_argument("--expected-commit", required=True)
    prepare.add_argument("--json", action="store_true")

    finalize = subparsers.add_parser("finalize-review", help="Validate a candidate and generate its review patch.")
    add_common(finalize)
    finalize.add_argument("--workspace", required=True, type=Path)
    finalize.add_argument("--skill", required=True)
    finalize.add_argument("--source", required=True)
    finalize.add_argument("--benefit-confirmed", action="store_true")
    finalize.add_argument("--tests-passed", action="store_true")
    finalize.add_argument("--license-ok", action="store_true")
    finalize.add_argument("--risk-reviewed", action="store_true")
    finalize.add_argument("--json", action="store_true")

    apply_review = subparsers.add_parser("apply-review", help="Apply one explicitly approved, current candidate.")
    add_common(apply_review)
    apply_review.add_argument("--workspace", required=True, type=Path)
    apply_review.add_argument("--skill", required=True)
    apply_review.add_argument("--source", required=True)
    apply_review.add_argument("--confirm-approved", action="store_true")
    apply_review.add_argument("--approval-note", required=True)
    apply_review.add_argument("--json", action="store_true")

    record = subparsers.add_parser("record-review", help="Record an explicit review disposition.")
    record.add_argument("--state", required=True, type=Path)
    record.add_argument("--source", required=True)
    record.add_argument("--commit", required=True)
    record.add_argument("--accepted-baseline", required=True)
    record.add_argument("--disposition", required=True, choices=sorted(ALLOWED_DISPOSITIONS))
    record.add_argument("--confirm-reviewed", action="store_true")
    record.add_argument("--json", action="store_true")
    return parser.parse_args()


def read_toml(path: Path) -> dict[str, Any]:
    return tomllib.loads(path.read_text(encoding="utf-8"))


def load_sources(path: Path) -> list[SkillRecord]:
    raw = read_toml(path)
    if raw.get("schema_version") != 1:
        raise ValueError(f"{path}: schema_version must be 1")
    records: list[SkillRecord] = []
    for item in raw.get("skill", []):
        sources = tuple(
            SourceRecord(
                id=str(source["id"]),
                mirror_id=str(source["mirror_id"]),
                repo_url=str(source["repo_url"]),
                upstream_path=str(source["upstream_path"]).strip("/"),
                accepted_commit=str(source["accepted_commit"]).lower(),
                accepted_version=str(source.get("accepted_version", "")),
                license=str(source["license"]),
                baseline_kind=str(source.get("baseline_kind", "exact")),
                tracked_paths=tuple(str(value).strip("/") for value in source.get("tracked_paths", [])),
                license_paths=tuple(str(value).strip("/") for value in source.get("license_paths", [])),
                evidence=tuple(str(value) for value in source.get("evidence", [])),
                evidence_files=tuple(str(value).strip("/") for value in source.get("evidence_files", [])),
                adopted=tuple(str(value) for value in source.get("adopted", [])),
                excluded=tuple(str(value) for value in source.get("excluded", [])),
            )
            for source in item.get("source", [])
        )
        records.append(
            SkillRecord(
                name=str(item["name"]),
                status=str(item["status"]),
                last_discovery_date=str(item["last_discovery_date"]),
                last_review_date=str(item.get("last_review_date", item["last_discovery_date"])),
                notes=str(item.get("notes", "")),
                sources=sources,
            )
        )
    return records


def load_mirrors(path: Path) -> dict[str, MirrorRecord]:
    result: dict[str, MirrorRecord] = {}
    for item in read_toml(path).get("mirror", []):
        record = MirrorRecord(
            id=str(item["id"]),
            repo_url=str(item["repo_url"]),
            branch=str(item["branch"]),
            local_path=Path(str(item["local_path"])),
            exposure_policy=str(item.get("exposure_policy", "")),
        )
        if record.id in result:
            raise ValueError(f"{path}: duplicate mirror id {record.id}")
        result[record.id] = record
    return result


def normalize_repo_url(value: str) -> str:
    return value.rstrip("/").removesuffix(".git").lower()


def is_safe_repo_path(value: str, allow_root: bool = False) -> bool:
    normalized = value.replace("\\", "/")
    if allow_root and normalized == ".":
        return True
    if not normalized or normalized in {".", "/"}:
        return False
    if normalized.startswith("/") or re.match(r"^[A-Za-z]:", normalized):
        return False
    return ".." not in PurePosixPath(normalized).parts


def source_repo_path(source: SourceRecord, child: str | None = None) -> str:
    root = "" if source.upstream_path == "." else source.upstream_path.strip("/")
    if child is None:
        return root
    child = child.strip("/")
    return f"{root}/{child}" if root else child


def git_object(commit: str, path: str) -> str:
    return f"{commit}:{path}" if path else f"{commit}^{{tree}}"


def parse_skill_name(path: Path) -> str:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    for line in lines:
        if line.startswith("name:"):
            return line.split(":", 1)[1].strip().strip("\"'")
    return ""


def list_local_skills(root: Path) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for directory in sorted(path for path in root.iterdir() if path.is_dir()):
        skill_md = directory / "SKILL.md"
        if not skill_md.is_file():
            continue
        name = parse_skill_name(skill_md)
        if not name:
            raise ValueError(f"Missing name frontmatter: {skill_md}")
        result[directory.name] = directory
    return result


def git(mirror: Path, args: list[str], timeout: int = 30) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-c", f"safe.directory={mirror.resolve().as_posix()}", "-C", str(mirror), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )


def validate_registry(
    skills: list[SkillRecord],
    mirrors: dict[str, MirrorRecord],
    skills_root: Path,
    require_rendered: bool = False,
) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    local_skills = list_local_skills(skills_root)
    names = [record.name for record in skills]
    duplicates = sorted(name for name, count in Counter(names).items() if count > 1)
    if duplicates:
        errors.append(f"Duplicate skill entries: {', '.join(duplicates)}")
    missing = sorted(set(local_skills) - set(names))
    extra = sorted(set(names) - set(local_skills))
    if missing:
        errors.append(f"Skills missing from registry: {', '.join(missing)}")
    if extra:
        errors.append(f"Registry entries without local skill: {', '.join(extra)}")

    source_ids: list[str] = []
    for skill in skills:
        if skill.status not in ALLOWED_SKILL_STATUSES:
            errors.append(f"{skill.name}: unsupported status {skill.status}")
        if skill.status == "confirmed" and not skill.sources:
            errors.append(f"{skill.name}: confirmed status requires at least one source")
        if skill.status == "none" and skill.sources:
            errors.append(f"{skill.name}: none status cannot contain sources")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", skill.last_review_date):
            errors.append(f"{skill.name}: last_review_date must use YYYY-MM-DD")
        if local_skills.get(skill.name):
            actual_name = parse_skill_name(local_skills[skill.name] / "SKILL.md")
            if actual_name != skill.name:
                errors.append(f"{skill.name}: directory/frontmatter mismatch ({actual_name})")
            if require_rendered and not (local_skills[skill.name] / "references" / "upstream-sources.md").is_file():
                errors.append(f"{skill.name}: rendered upstream-sources.md missing")
        for source in skill.sources:
            source_ids.append(source.id)
            mirror = mirrors.get(source.mirror_id)
            if not mirror:
                errors.append(f"{skill.name}/{source.id}: unknown mirror {source.mirror_id}")
                continue
            if normalize_repo_url(source.repo_url) != normalize_repo_url(mirror.repo_url):
                errors.append(f"{skill.name}/{source.id}: repo_url does not match mirror registry")
            if mirror.exposure_policy != "zero":
                errors.append(f"{skill.name}/{source.id}: mirror exposure_policy must be zero")
            if not SHA_PATTERN.fullmatch(source.accepted_commit):
                errors.append(f"{skill.name}/{source.id}: accepted_commit must be a full 40-character SHA")
            if not is_safe_repo_path(source.upstream_path, allow_root=True):
                errors.append(f"{skill.name}/{source.id}: upstream_path must be a safe repository-relative path")
            if not source.license.strip():
                errors.append(f"{skill.name}/{source.id}: license is required")
            if not source.tracked_paths:
                errors.append(f"{skill.name}/{source.id}: tracked_paths cannot be empty")
            for tracked_path in source.tracked_paths:
                if not is_safe_repo_path(tracked_path):
                    errors.append(
                        f"{skill.name}/{source.id}: tracked path must be repository-relative: {tracked_path}"
                    )
            if not source.license_paths:
                errors.append(f"{skill.name}/{source.id}: license_paths cannot be empty")
            for license_path in source.license_paths:
                if not is_safe_repo_path(license_path):
                    errors.append(
                        f"{skill.name}/{source.id}: license path must be repository-relative: {license_path}"
                    )
            if not source.evidence:
                errors.append(f"{skill.name}/{source.id}: evidence cannot be empty")
            if not source.evidence_files:
                errors.append(f"{skill.name}/{source.id}: evidence_files cannot be empty")
            for evidence_file in source.evidence_files:
                evidence_path = skills_root / evidence_file
                try:
                    evidence_path.resolve().relative_to(skills_root.resolve().parent)
                except ValueError:
                    errors.append(f"{skill.name}/{source.id}: evidence file escapes agents root: {evidence_file}")
                    continue
                if not evidence_path.is_file():
                    errors.append(f"{skill.name}/{source.id}: evidence file missing: {evidence_file}")
            if mirror.local_path.exists():
                upstream_root = mirror.local_path if source.upstream_path == "." else mirror.local_path / source.upstream_path
                if not upstream_root.exists():
                    warnings.append(f"{skill.name}/{source.id}: upstream path not present in current checkout")
                commit = git(mirror.local_path, ["cat-file", "-e", f"{source.accepted_commit}^{{commit}}"])
                if commit.returncode != 0:
                    warnings.append(f"{skill.name}/{source.id}: accepted commit unavailable in local mirror")
                else:
                    baseline_path = git(mirror.local_path, ["cat-file", "-e", git_object(
                        source.accepted_commit, source_repo_path(source)
                    )])
                    if baseline_path.returncode != 0:
                        errors.append(f"{skill.name}/{source.id}: upstream path missing at accepted commit")
                    for tracked_path in source.tracked_paths:
                        tracked_blob = git(
                            mirror.local_path,
                            ["cat-file", "-e", git_object(
                                source.accepted_commit, source_repo_path(source, tracked_path)
                            )],
                        )
                        if tracked_blob.returncode != 0:
                            errors.append(
                                f"{skill.name}/{source.id}: tracked path missing at accepted commit: {tracked_path}"
                            )
                    for license_path in source.license_paths:
                        license_blob = git(
                            mirror.local_path,
                            ["cat-file", "-e", f"{source.accepted_commit}:{license_path}"],
                        )
                        if license_blob.returncode != 0:
                            errors.append(
                                f"{skill.name}/{source.id}: license path missing at accepted commit: {license_path}"
                            )
            else:
                warnings.append(f"{skill.name}/{source.id}: mirror is not initialized")

    duplicate_sources = sorted(name for name, count in Counter(source_ids).items() if count > 1)
    if duplicate_sources:
        errors.append(f"Duplicate source ids: {', '.join(duplicate_sources)}")
    return {
        "status": "ok" if not errors else "invalid",
        "skill_count": len(skills),
        "confirmed_skill_count": sum(skill.status == "confirmed" for skill in skills),
        "source_count": len(source_ids),
        "errors": errors,
        "warnings": warnings,
    }


def render_skill_reference(skill: SkillRecord) -> str:
    lines = [
        "<!-- Generated by agent-rules/scripts/skill_upstream_maintenance.py. -->",
        "# 上游技能来源",
        "",
        f"- 状态：`{skill.status}`",
        f"- 首次统一调查：`{skill.last_discovery_date}`",
        f"- 最近来源登记审核：`{skill.last_review_date}`",
    ]
    if skill.notes:
        lines.append(f"- 说明：{skill.notes}")
    lines.extend(
        [
            "",
            "这里只记录外部上游 `skill`；论文、普通文档和模板不属于本机制。",
            "每周检查的最近观测与审核时间记录在 `reports/skill-upstream/state.json`。",
        ]
    )
    if not skill.sources:
        lines.extend(
            [
                "",
                "当前没有经用户确认的外部上游技能。以后发现候选时，先列证据并经用户逐项确认，再写入集中登记表。",
            ]
        )
        return "\n".join(lines).rstrip() + "\n"

    for source in skill.sources:
        lines.extend(
            [
                "",
                f"## {source.id}",
                "",
                f"- 仓库：{source.repo_url}",
                f"- 上游路径：`{source.upstream_path}`",
                f"- 已接受提交：`{source.accepted_commit}`",
                f"- 已接受版本：`{source.accepted_version or '未提供'}`",
                f"- 基线类型：`{source.baseline_kind}`",
                f"- 许可证：`{source.license}`",
                f"- 镜像登记：`{source.mirror_id}`",
                "",
                "### 证据",
                "",
                *[f"- {value}" for value in source.evidence],
                *[f"- 本地证据文件：`{value}`" for value in source.evidence_files],
                "",
                "### 已吸收",
                "",
                *([f"- {value}" for value in source.adopted] or ["- 未单独记录。"]),
                "",
                "### 明确不吸收",
                "",
                *([f"- {value}" for value in source.excluded] or ["- 未单独记录。"]),
                "",
                "### 跟踪范围",
                "",
                *[f"- `{value}`" for value in source.tracked_paths],
                "",
                "### 许可证监控",
                "",
                *[f"- `{value}`" for value in source.license_paths],
            ]
        )
    lines.extend(
        [
            "",
            "发现更新后只生成隔离候选和测试报告；用户逐项批准前，不修改本地技能源码。",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def render_references(skills: list[SkillRecord], skills_root: Path, check_only: bool) -> dict[str, Any]:
    changed: list[str] = []
    for skill in skills:
        target = skills_root / skill.name / "references" / "upstream-sources.md"
        expected = render_skill_reference(skill)
        current = target.read_text(encoding="utf-8") if target.is_file() else None
        if current == expected:
            continue
        changed.append(skill.name)
        if not check_only:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(expected, encoding="utf-8", newline="\n")
    return {"status": "drift" if changed else "up_to_date", "changed_skills": changed, "check_only": check_only}


def read_state(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"schema_version": 1, "sources": {}, "history": []}
    data = json.loads(path.read_text(encoding="utf-8"))
    data.setdefault("schema_version", 1)
    data.setdefault("sources", {})
    data.setdefault("history", [])
    return data


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def current_head(mirror: Path) -> str | None:
    result = git(mirror, ["rev-parse", "HEAD"])
    return result.stdout.strip() if result.returncode == 0 else None


def git_text_at(mirror: Path, commit: str, path: str) -> str | None:
    result = git(mirror, ["show", f"{commit}:{path}"], timeout=60)
    return result.stdout if result.returncode == 0 else None


def drop_nested_key(payload: dict[str, Any], keys: tuple[str, ...]) -> None:
    current: Any = payload
    for key in keys[:-1]:
        if not isinstance(current, dict) or key not in current:
            return
        current = current[key]
    if isinstance(current, dict):
        current.pop(keys[-1], None)


def normalized_structured_version_file(name: str, text: str) -> Any:
    if name.endswith(".json"):
        payload = json.loads(text)
        if not isinstance(payload, dict):
            return payload
        normalized = copy.deepcopy(payload)
        normalized.pop("version", None)
        if name == "package-lock.json":
            packages = normalized.get("packages")
            if isinstance(packages, dict) and isinstance(packages.get(""), dict):
                packages[""].pop("version", None)
        return normalized
    payload = tomllib.loads(text)
    normalized = copy.deepcopy(payload)
    drop_nested_key(normalized, ("project", "version"))
    drop_nested_key(normalized, ("tool", "poetry", "version"))
    return normalized


def strip_skill_frontmatter_version(text: str) -> str:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return text
    end = next((index for index, line in enumerate(lines[1:], start=1) if line.strip() == "---"), None)
    if end is None:
        return text
    kept = [line for index, line in enumerate(lines) if not (index < end and re.match(r"^version\s*:", line, re.I))]
    return "\n".join(kept)


def is_ignorable_change(
    mirror: Path,
    before: str,
    current: str,
    item: dict[str, str],
) -> bool:
    path = item["path"]
    name = Path(path).name.lower()
    if name.startswith("readme") or name in ALWAYS_IGNORED_NAMES or name in VERSION_FILE_NAMES:
        return True
    if item["change"].startswith(("A", "D")):
        return False
    old_path = item.get("old_path", path)
    before_text = git_text_at(mirror, before, old_path)
    current_text = git_text_at(mirror, current, path)
    if before_text is None or current_text is None:
        return False
    if name in STRUCTURED_VERSION_FILES:
        try:
            return normalized_structured_version_file(name, before_text) == normalized_structured_version_file(
                name, current_text
            )
        except (json.JSONDecodeError, tomllib.TOMLDecodeError, TypeError, ValueError):
            return False
    if name == "skill.md":
        return strip_skill_frontmatter_version(before_text) == strip_skill_frontmatter_version(current_text)
    return False


def source_diff(
    mirror: Path,
    source: SourceRecord,
    current: str,
    comparison_base: str | None = None,
) -> dict[str, Any]:
    baseline = git(mirror, ["cat-file", "-e", f"{source.accepted_commit}^{{commit}}"])
    if baseline.returncode != 0:
        return {"status": "baseline_unavailable", "changed": []}
    ancestor = git(mirror, ["merge-base", "--is-ancestor", source.accepted_commit, current])
    if ancestor.returncode != 0:
        return {"status": "non_fast_forward", "changed": []}
    before = comparison_base or source.accepted_commit
    comparison = git(mirror, ["merge-base", "--is-ancestor", before, current])
    if comparison.returncode != 0:
        before = source.accepted_commit

    skill_path = source_repo_path(source, "SKILL.md")
    baseline_skill = git(mirror, ["cat-file", "-e", git_object(source.accepted_commit, skill_path)])
    current_identity = (
        git_object(current, skill_path)
        if baseline_skill.returncode == 0
        else git_object(current, source_repo_path(source))
    )
    if git(mirror, ["cat-file", "-e", current_identity]).returncode != 0:
        return {"status": "upstream_removed_or_moved", "changed": [], "comparison_base": before}

    license_diff = git(
        mirror,
        ["diff", "--name-only", source.accepted_commit, current, "--", *source.license_paths],
        timeout=60,
    )
    if license_diff.returncode != 0:
        return {"status": "diff_failed", "changed": [], "error": license_diff.stderr.strip()}
    missing_license = [
        path
        for path in source.license_paths
        if git(mirror, ["cat-file", "-e", f"{current}:{path}"]).returncode != 0
    ]
    if license_diff.stdout.strip() or missing_license:
        changed = [
            {"change": "LICENSE", "path": path}
            for path in sorted(set(license_diff.stdout.splitlines()) | set(missing_license))
        ]
        return {"status": "license_review_required", "changed": changed, "comparison_base": before}

    pathspecs = [source_repo_path(source, path) for path in source.tracked_paths]
    result = git(
        mirror,
        ["diff", "--name-status", "--find-renames", before, current, "--", *pathspecs],
        timeout=60,
    )
    if result.returncode != 0:
        return {"status": "diff_failed", "changed": [], "error": result.stderr.strip()}
    changed: list[dict[str, str]] = []
    for line in result.stdout.splitlines():
        fields = line.split("\t")
        if len(fields) < 2:
            continue
        item = {"change": fields[0], "path": fields[-1]}
        if fields[0].startswith(("R", "C")) and len(fields) >= 3:
            item["old_path"] = fields[-2]
        changed.append(item)
    if not changed:
        return {"status": "no_relevant_change", "changed": [], "comparison_base": before}
    if all(is_ignorable_change(mirror, before, current, item) for item in changed):
        return {"status": "no_relevant_change", "changed": changed, "comparison_base": before}
    return {"status": "review_required", "changed": changed, "comparison_base": before}


def inspect_mirror(mirror: MirrorRecord) -> dict[str, Any]:
    if not mirror.local_path.is_dir():
        return {"status": "mirror_missing", "head": None}
    head = current_head(mirror.local_path)
    if not head:
        return {"status": "mirror_error", "head": None}
    dirty = git(mirror.local_path, ["status", "--porcelain"])
    branch = git(mirror.local_path, ["branch", "--show-current"])
    origin = git(mirror.local_path, ["remote", "get-url", "origin"])
    if dirty.returncode != 0 or branch.returncode != 0 or origin.returncode != 0:
        return {"status": "mirror_error", "head": head}
    if dirty.stdout.strip():
        return {"status": "dirty_mirror", "head": head}
    if branch.stdout.strip() != mirror.branch:
        return {"status": "branch_mismatch", "head": head}
    if normalize_repo_url(origin.stdout.strip()) != normalize_repo_url(mirror.repo_url):
        return {"status": "origin_mismatch", "head": head}
    return {"status": "healthy", "head": head}


def refresh_mirrors(mirrors_registry: Path) -> dict[str, Any]:
    manager = Path(__file__).with_name("manage_repo_mirrors.py")
    completed = subprocess.run(
        [
            sys.executable,
            "-B",
            str(manager),
            "sync",
            "--registry",
            str(mirrors_registry),
            "--json",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=600,
    )
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(completed.stderr.strip() or "Mirror manager did not return valid JSON.") from exc
    payload["exit_code"] = completed.returncode
    return payload


def build_report(
    skills: list[SkillRecord],
    mirrors: dict[str, MirrorRecord],
    reports_root: Path,
    date: str,
    state_path: Path,
    mirror_results: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    state = read_state(state_path)
    rows: list[dict[str, Any]] = []
    now = datetime.now(timezone.utc).isoformat()
    for skill in skills:
        for source in skill.sources:
            mirror = mirrors[source.mirror_id]
            source_state = state["sources"].setdefault(source.id, {})
            refresh_result = mirror_results.get(source.mirror_id) if mirror_results else None
            if refresh_result and refresh_result.get("status") not in {
                "initialized",
                "synced",
                "already_up_to_date",
            }:
                row = {
                    "skill": skill.name,
                    "source": source.id,
                    "status": "mirror_blocked",
                    "current_commit": refresh_result.get("local_head") or refresh_result.get("after_head"),
                    "changed": [],
                    "mirror_status": refresh_result.get("status"),
                    "error": refresh_result.get("error") or refresh_result.get("remote_error"),
                }
            else:
                health = inspect_mirror(mirror)
                head = health["head"]
                if health["status"] != "healthy":
                    row = {
                        "skill": skill.name,
                        "source": source.id,
                        "status": health["status"],
                        "current_commit": head,
                        "changed": [],
                    }
                elif head == source.accepted_commit:
                    row = {"skill": skill.name, "source": source.id, "status": "up_to_date", "current_commit": head, "changed": []}
                elif (
                    source_state.get("last_reviewed_commit") == head
                    and source_state.get("reviewed_against_accepted_commit") == source.accepted_commit
                ):
                    row = {"skill": skill.name, "source": source.id, "status": "already_reviewed", "current_commit": head, "changed": []}
                else:
                    comparison_base = None
                    reviewed_commit = source_state.get("last_reviewed_commit")
                    if (
                        source_state.get("reviewed_against_accepted_commit") == source.accepted_commit
                        and isinstance(reviewed_commit, str)
                        and SHA_PATTERN.fullmatch(reviewed_commit)
                        and git(mirror.local_path, ["merge-base", "--is-ancestor", reviewed_commit, head]).returncode == 0
                    ):
                        comparison_base = reviewed_commit
                    diff = source_diff(mirror.local_path, source, head, comparison_base=comparison_base)
                    row = {"skill": skill.name, "source": source.id, "current_commit": head, **diff}
                    if diff["status"] == "no_relevant_change":
                        source_state["last_reviewed_commit"] = head
                        source_state["reviewed_against_accepted_commit"] = source.accepted_commit
                        source_state["last_disposition"] = "no-impact"
                        source_state["last_reviewed_at"] = now
                        state["history"].append(
                            {
                                "source": source.id,
                                "commit": head,
                                "accepted_baseline": source.accepted_commit,
                                "disposition": "no-impact",
                                "reviewed_at": now,
                                "automatic": True,
                            }
                        )
            observed_commit = row.get("current_commit")
            if isinstance(observed_commit, str) and SHA_PATTERN.fullmatch(observed_commit.lower()):
                source_state["last_seen_commit"] = observed_commit.lower()
                source_state["last_seen_at"] = now
            rows.append(row)

    counts = dict(Counter(row["status"] for row in rows))
    payload = {
        "schema_version": 1,
        "date": date,
        "generated_at": now,
        "source_count": len(rows),
        "counts": counts,
        "sources": rows,
    }
    run_root = reports_root / date
    write_json(run_root / "summary.json", payload)
    write_json(state_path, state)

    md = [
        f"# 自建技能上游周检 {date}",
        "",
        f"- 已登记来源：{len(rows)}",
        f"- 等待收益评估：{counts.get('review_required', 0)}",
        f"- 许可证复核：{counts.get('license_review_required', 0)}",
        f"- 检查异常：{sum(count for key, count in counts.items() if key in {'mirror_missing', 'mirror_error', 'mirror_blocked', 'dirty_mirror', 'branch_mismatch', 'origin_mismatch', 'baseline_unavailable', 'non_fast_forward', 'diff_failed', 'upstream_removed_or_moved'})}",
        "",
        "| 本地技能 | 来源 | 状态 | 当前提交 | 变更文件数 |",
        "| --- | --- | --- | --- | ---: |",
    ]
    for row in rows:
        current = row.get("current_commit") or "-"
        md.append(f"| `{row['skill']}` | `{row['source']}` | `{row['status']}` | `{current[:12]}` | {len(row.get('changed', []))} |")
    md.extend(
        [
            "",
            "## 审核门",
            "",
            "`review_required` 只表示上游相关文件发生变化，不表示本地技能应该更新。候选修改必须在隔离目录完成旧版/新版对比和回归测试，并经用户逐项批准。",
        ]
    )
    (run_root / "summary.md").write_text("\n".join(md).rstrip() + "\n", encoding="utf-8", newline="\n")
    return payload


def tree_hash(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare_review(
    skills: list[SkillRecord],
    mirrors: dict[str, MirrorRecord],
    skills_root: Path,
    reports_root: Path,
    date: str,
    skill_name: str,
    source_id: str,
    expected_commit: str,
) -> dict[str, Any]:
    skill = next((record for record in skills if record.name == skill_name), None)
    if not skill:
        raise ValueError(f"Unknown skill: {skill_name}")
    source = next((record for record in skill.sources if record.id == source_id), None)
    if not source:
        raise ValueError(f"Unknown source for {skill_name}: {source_id}")
    skill_root = skills_root / skill_name
    repo_root_result = git(skills_root, ["rev-parse", "--show-toplevel"])
    if repo_root_result.returncode != 0:
        raise RuntimeError(repo_root_result.stderr.strip() or "Unable to find skills git repository.")
    target_status = git(skills_root, ["status", "--porcelain", "--", skill_name])
    if target_status.stdout.strip():
        return {"status": "blocked_dirty_target", "skill": skill_name, "details": target_status.stdout.splitlines()}

    mirror = mirrors[source.mirror_id]
    health = inspect_mirror(mirror)
    if health["status"] != "healthy":
        return {"status": f"blocked_{health['status']}", "skill": skill_name, "source": source_id}
    head = health["head"]
    if not SHA_PATTERN.fullmatch(expected_commit.lower()) or head != expected_commit.lower():
        return {
            "status": "blocked_stale_report",
            "skill": skill_name,
            "source": source_id,
            "expected_commit": expected_commit.lower(),
            "current_commit": head,
        }
    diff_status = source_diff(mirror.local_path, source, head)
    if diff_status["status"] != "review_required":
        return {
            "status": f"blocked_{diff_status['status']}",
            "skill": skill_name,
            "source": source_id,
            "current_commit": head,
        }
    workspace = reports_root / date / skill_name / source_id
    if workspace.exists():
        return {"status": "workspace_exists", "workspace": str(workspace)}
    old_skill = workspace / "old_skill"
    candidate_skill = workspace / "candidate_skill"
    old_skill.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(skill_root, old_skill)
    shutil.copytree(skill_root, candidate_skill)
    pathspecs = [source_repo_path(source, path) for path in source.tracked_paths]
    diff = git(mirror.local_path, ["diff", "--find-renames", source.accepted_commit, head, "--", *pathspecs], timeout=60)
    if diff.returncode != 0:
        shutil.rmtree(workspace)
        return {"status": "blocked_diff_failed", "skill": skill_name, "source": source_id}
    (workspace / "upstream.diff").write_text(diff.stdout, encoding="utf-8", newline="\n")
    context = {
        "schema_version": 1,
        "skill": skill_name,
        "source": source_id,
        "accepted_commit": source.accepted_commit,
        "current_upstream_commit": head,
        "local_tree_hash": tree_hash(skill_root),
        "old_skill_tree_hash": tree_hash(old_skill),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "approval_required": True,
        "candidate_status": "draft",
    }
    write_json(workspace / "review-context.json", context)
    (workspace / "benefit-assessment.md").write_text(
        "# 收益评估\n\n状态：待评估\n\n## 可证明收益\n\n## 风险与许可证\n\n## 建议\n",
        encoding="utf-8",
        newline="\n",
    )
    (workspace / "test-report.md").write_text(
        "# 测试报告\n\n状态：未运行\n\n## 旧版\n\n## 候选版\n\n## 回归结论\n",
        encoding="utf-8",
        newline="\n",
    )
    (workspace / "candidate.patch").write_text("", encoding="utf-8", newline="\n")
    return {"status": "prepared", "workspace": str(workspace), **context}


def load_review_context(workspace: Path) -> dict[str, Any]:
    path = workspace / "review-context.json"
    if not path.is_file():
        raise ValueError(f"Review context missing: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def candidate_patch(workspace: Path, skill_name: str) -> tuple[str, str]:
    diff = git(workspace, ["diff", "--no-index", "--binary", "--", "old_skill", "candidate_skill"], timeout=120)
    if diff.returncode not in {0, 1}:
        raise RuntimeError(diff.stderr.strip() or "Unable to generate candidate patch.")
    patch = diff.stdout.replace("a/old_skill/", f"a/{skill_name}/").replace(
        "b/candidate_skill/", f"b/{skill_name}/"
    )
    digest = hashlib.sha256(patch.encode("utf-8")).hexdigest()
    return patch, digest


def verify_review_is_current(
    skills: list[SkillRecord],
    mirrors: dict[str, MirrorRecord],
    skills_root: Path,
    workspace: Path,
    skill_name: str,
    source_id: str,
) -> tuple[SkillRecord, SourceRecord, dict[str, Any]]:
    skill = next((record for record in skills if record.name == skill_name), None)
    if not skill:
        raise ValueError(f"Unknown skill: {skill_name}")
    source = next((record for record in skill.sources if record.id == source_id), None)
    if not source:
        raise ValueError(f"Unknown source for {skill_name}: {source_id}")
    context = load_review_context(workspace)
    if context.get("skill") != skill_name or context.get("source") != source_id:
        raise ValueError("Review context does not match the requested skill/source.")
    if context.get("accepted_commit") != source.accepted_commit:
        raise ValueError("Accepted baseline changed; discard and recreate the candidate.")
    health = inspect_mirror(mirrors[source.mirror_id])
    if health["status"] != "healthy":
        raise ValueError(f"Mirror is not healthy: {health['status']}")
    if health["head"] != context.get("current_upstream_commit"):
        raise ValueError("Upstream HEAD changed; discard and recreate the candidate.")
    target = skills_root / skill_name
    status = git(skills_root, ["status", "--porcelain", "--", skill_name])
    if status.stdout.strip():
        raise ValueError("Target skill has uncommitted changes.")
    if tree_hash(target) != context.get("local_tree_hash"):
        raise ValueError("Target skill changed after candidate preparation.")
    old_skill = workspace / "old_skill"
    if not old_skill.is_dir() or tree_hash(old_skill) != context.get("old_skill_tree_hash"):
        raise ValueError("Old-skill snapshot changed after candidate preparation.")
    return skill, source, context


def finalize_review(
    skills: list[SkillRecord],
    mirrors: dict[str, MirrorRecord],
    skills_root: Path,
    workspace: Path,
    skill_name: str,
    source_id: str,
    gates: dict[str, bool],
) -> dict[str, Any]:
    _, _, context = verify_review_is_current(
        skills, mirrors, skills_root, workspace, skill_name, source_id
    )
    missing = sorted(name for name, passed in gates.items() if not passed)
    if missing:
        return {"status": "blocked_review_incomplete", "missing_gates": missing}
    assessment = workspace / "benefit-assessment.md"
    test_report = workspace / "test-report.md"
    if not assessment.is_file() or "状态：待评估" in assessment.read_text(encoding="utf-8"):
        return {"status": "blocked_assessment_incomplete"}
    if not test_report.is_file() or "状态：未运行" in test_report.read_text(encoding="utf-8"):
        return {"status": "blocked_tests_incomplete"}
    old_skill = workspace / "old_skill"
    candidate_skill = workspace / "candidate_skill"
    old_hash = tree_hash(old_skill)
    candidate_hash_value = tree_hash(candidate_skill)
    if old_hash == candidate_hash_value:
        return {"status": "blocked_no_candidate_changes"}
    patch, patch_hash = candidate_patch(workspace, skill_name)
    (workspace / "candidate.patch").write_text(patch, encoding="utf-8", newline="\n")
    context.update(
        {
            "candidate_status": "awaiting_approval",
            "candidate_tree_hash": candidate_hash_value,
            "candidate_patch_sha256": patch_hash,
            "review_evidence_sha256": {
                "benefit-assessment.md": file_hash(assessment),
                "test-report.md": file_hash(test_report),
                "upstream.diff": file_hash(workspace / "upstream.diff"),
            },
            "finalized_at": datetime.now(timezone.utc).isoformat(),
            "review_gates": gates,
        }
    )
    write_json(workspace / "review-context.json", context)
    return {"status": "awaiting_approval", "workspace": str(workspace), **context}


def apply_review(
    skills: list[SkillRecord],
    mirrors: dict[str, MirrorRecord],
    skills_root: Path,
    workspace: Path,
    skill_name: str,
    source_id: str,
    confirmed: bool,
    approval_note: str,
) -> dict[str, Any]:
    if not confirmed:
        raise ValueError("Refusing to apply without --confirm-approved")
    if not approval_note.strip():
        raise ValueError("A non-empty approval note is required.")
    _, _, context = verify_review_is_current(
        skills, mirrors, skills_root, workspace, skill_name, source_id
    )
    if context.get("candidate_status") != "awaiting_approval":
        raise ValueError("Candidate is not finalized and awaiting approval.")
    candidate_hash_value = tree_hash(workspace / "candidate_skill")
    if candidate_hash_value != context.get("candidate_tree_hash"):
        raise ValueError("Candidate changed after finalization.")
    patch, patch_hash = candidate_patch(workspace, skill_name)
    if patch_hash != context.get("candidate_patch_sha256"):
        raise ValueError("Candidate patch changed after finalization.")
    expected_evidence = context.get("review_evidence_sha256")
    if not isinstance(expected_evidence, dict):
        raise ValueError("Finalized review evidence hashes are missing.")
    for name, expected_hash in expected_evidence.items():
        evidence_path = workspace / name
        if not evidence_path.is_file() or file_hash(evidence_path) != expected_hash:
            raise ValueError(f"Review evidence changed after finalization: {name}")
    patch_path = workspace / "candidate.patch"
    patch_path.write_text(patch, encoding="utf-8", newline="\n")
    check = git(skills_root, ["apply", "--check", str(patch_path)], timeout=120)
    if check.returncode != 0:
        raise RuntimeError(check.stderr.strip() or "Candidate patch no longer applies cleanly.")
    applied = git(skills_root, ["apply", str(patch_path)], timeout=120)
    if applied.returncode != 0:
        raise RuntimeError(applied.stderr.strip() or "Candidate patch application failed.")
    if tree_hash(skills_root / skill_name) != candidate_hash_value:
        raise RuntimeError("Applied tree does not match the reviewed candidate.")
    context.update(
        {
            "candidate_status": "applied_pending_retest",
            "approved_at": datetime.now(timezone.utc).isoformat(),
            "approval_note": approval_note,
        }
    )
    write_json(workspace / "review-context.json", context)
    return {"status": "applied_pending_retest", "workspace": str(workspace), **context}


def record_review(
    path: Path,
    source: str,
    commit: str,
    accepted_baseline: str,
    disposition: str,
    confirmed: bool,
) -> dict[str, Any]:
    if not confirmed:
        raise ValueError("Refusing to record review without --confirm-reviewed")
    if disposition not in ALLOWED_DISPOSITIONS:
        raise ValueError(f"Unsupported disposition: {disposition}")
    if not SHA_PATTERN.fullmatch(commit.lower()):
        raise ValueError("Invalid commit")
    if not SHA_PATTERN.fullmatch(accepted_baseline.lower()):
        raise ValueError("Invalid accepted baseline")
    state = read_state(path)
    now = datetime.now(timezone.utc).isoformat()
    entry = state["sources"].setdefault(source, {})
    entry.update(
        {
            "last_seen_commit": commit.lower(),
            "last_reviewed_commit": commit.lower(),
            "reviewed_against_accepted_commit": accepted_baseline.lower(),
            "last_disposition": disposition,
            "last_reviewed_at": now,
        }
    )
    state["history"].append(
        {
            "source": source,
            "commit": commit.lower(),
            "accepted_baseline": accepted_baseline.lower(),
            "disposition": disposition,
            "reviewed_at": now,
        }
    )
    write_json(path, state)
    return {
        "status": "recorded",
        "source": source,
        "commit": commit.lower(),
        "accepted_baseline": accepted_baseline.lower(),
        "disposition": disposition,
    }


def emit(payload: dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"status: {payload.get('status', 'ok')}")
        for key in ("skill_count", "source_count", "confirmed_skill_count", "workspace"):
            if key in payload:
                print(f"{key}: {payload[key]}")
        for error in payload.get("errors", []):
            print(f"error: {error}")
        for warning in payload.get("warnings", []):
            print(f"warning: {warning}")


def main() -> int:
    args = parse_args()
    try:
        if args.command == "record-review":
            payload = record_review(
                args.state.resolve(),
                args.source,
                args.commit,
                args.accepted_baseline,
                args.disposition,
                args.confirm_reviewed,
            )
            emit(payload, args.json)
            return 0

        registry = args.registry.resolve()
        mirrors_registry = args.mirrors_registry.resolve()
        skills_root = args.skills_root.resolve()
        skills = load_sources(registry)
        mirrors = load_mirrors(mirrors_registry)

        if args.command == "validate":
            payload = validate_registry(skills, mirrors, skills_root, args.require_rendered)
            emit(payload, args.json)
            return 0 if payload["status"] == "ok" else 2
        if args.command == "render":
            validation = validate_registry(skills, mirrors, skills_root)
            if validation["errors"]:
                emit(validation, args.json)
                return 2
            payload = render_references(skills, skills_root, args.check)
            emit(payload, args.json)
            return 2 if args.check and payload["changed_skills"] else 0
        if args.command in {"report", "weekly-run"}:
            validation = validate_registry(skills, mirrors, skills_root)
            if validation["errors"]:
                emit(validation, args.json)
                return 2
            reports_root = args.reports_root.resolve()
            state_path = args.state.resolve() if args.state else reports_root / "state.json"
            refresh_payload = None
            mirror_results = None
            if args.command == "weekly-run":
                refresh_payload = refresh_mirrors(mirrors_registry)
                write_json(reports_root / args.date / "mirror-results.json", refresh_payload)
                mirror_results = {
                    result["id"]: result for result in refresh_payload.get("mirrors", [])
                }
            payload = build_report(
                skills,
                mirrors,
                reports_root,
                args.date,
                state_path,
                mirror_results=mirror_results,
            )
            if refresh_payload is not None:
                payload["mirror_refresh_exit_code"] = refresh_payload["exit_code"]
            emit(payload, args.json)
            return 0 if not refresh_payload or refresh_payload["exit_code"] == 0 else 2
        if args.command == "prepare-review":
            payload = prepare_review(
                skills,
                mirrors,
                skills_root,
                args.reports_root.resolve(),
                args.date,
                args.skill,
                args.source,
                args.expected_commit,
            )
            emit(payload, args.json)
            return 0 if payload["status"] == "prepared" else 2
        if args.command == "finalize-review":
            payload = finalize_review(
                skills,
                mirrors,
                skills_root,
                args.workspace.resolve(),
                args.skill,
                args.source,
                {
                    "benefit_confirmed": args.benefit_confirmed,
                    "tests_passed": args.tests_passed,
                    "license_ok": args.license_ok,
                    "risk_reviewed": args.risk_reviewed,
                },
            )
            emit(payload, args.json)
            return 0 if payload["status"] == "awaiting_approval" else 2
        if args.command == "apply-review":
            payload = apply_review(
                skills,
                mirrors,
                skills_root,
                args.workspace.resolve(),
                args.skill,
                args.source,
                args.confirm_approved,
                args.approval_note,
            )
            emit(payload, args.json)
            return 0 if payload["status"] == "applied_pending_retest" else 2
        raise ValueError(f"Unsupported command: {args.command}")
    except (KeyError, OSError, RuntimeError, ValueError, subprocess.TimeoutExpired) as exc:
        payload = {"status": "error", "error": str(exc)}
        emit(payload, getattr(args, "json", False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
