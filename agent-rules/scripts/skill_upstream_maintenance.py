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
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
SUCCESSFUL_MIRROR_REFRESH_STATUSES = frozenset(
    {"initialized", "synced", "already_up_to_date"}
)
DIAGNOSTIC_STATUSES = frozenset(
    {
        "mirror_missing",
        "mirror_error",
        "mirror_blocked",
        "blocked_missing_git_dir",
        "git_dir_mismatch",
        "tracked_diff_failed",
        "dirty_mirror",
        "branch_mismatch",
        "origin_mismatch",
        "baseline_unavailable",
        "non_fast_forward",
        "diff_failed",
        "upstream_removed_or_moved",
        "license_review_required",
    }
)
CHECK_ERROR_STATUSES = DIAGNOSTIC_STATUSES - {"license_review_required"}
FINALIZED_CANDIDATE_FILES = (
    "review-context.json",
    "candidate.patch",
    "benefit-assessment.md",
    "test-report.md",
    "upstream.diff",
)
REQUIRED_REVIEW_EVIDENCE = frozenset(
    {"benefit-assessment.md", "test-report.md", "upstream.diff"}
)
REQUIRED_REVIEW_GATES = frozenset(
    {"benefit_confirmed", "tests_passed", "license_ok", "risk_reviewed"}
)


@dataclass(frozen=True)
class SourceRecord:
    id: str
    mirror_id: str
    repo_url: str
    upstream_path: str
    accepted_upstream_path: str
    path_migration_commit: str
    path_migration_evidence: tuple[str, ...]
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
    git_dir_path: Path | None = None


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
    prepare.add_argument(
        "--additional-source",
        action="append",
        default=[],
        nargs=2,
        metavar=("SOURCE", "EXPECTED_COMMIT"),
        help="Add another source and its expected full commit to the same skill-level candidate.",
    )
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


def load_mirror_manager() -> Any:
    module_name = "_skill_upstream_manage_repo_mirrors"
    existing = sys.modules.get(module_name)
    if existing is not None:
        return existing
    script = Path(__file__).with_name("manage_repo_mirrors.py")
    spec = importlib.util.spec_from_file_location(module_name, script)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load mirror manager: {script}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


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
                accepted_upstream_path=str(
                    source.get("accepted_upstream_path", source["upstream_path"])
                ).strip("/"),
                path_migration_commit=str(source.get("path_migration_commit", "")).lower(),
                path_migration_evidence=tuple(
                    str(value) for value in source.get("path_migration_evidence", [])
                ),
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
    manager = load_mirror_manager()
    for item in manager.load_registry(path):
        record = MirrorRecord(
            id=item.id,
            repo_url=item.repo_url,
            branch=item.branch,
            local_path=item.local_path,
            exposure_policy=item.exposure_policy,
            git_dir_path=item.git_dir_path,
        )
        if record.id in result:
            raise ValueError(f"{path}: duplicate mirror id {record.id}")
        result[record.id] = record
    return result


def normalize_repo_url(value: str) -> str:
    return value.rstrip("/").removesuffix(".git").lower()


def canonical_path_key(path: Path) -> str:
    try:
        return path.resolve().as_posix().casefold()
    except OSError:
        return path.as_posix().casefold()


def is_safe_repo_path(value: str, allow_root: bool = False) -> bool:
    normalized = value.replace("\\", "/")
    if allow_root and normalized == ".":
        return True
    if not normalized or normalized in {".", "/"}:
        return False
    if normalized.startswith("/") or re.match(r"^[A-Za-z]:", normalized):
        return False
    return ".." not in PurePosixPath(normalized).parts


def source_repo_path(
    source: SourceRecord,
    child: str | None = None,
    *,
    accepted: bool = False,
) -> str:
    selected_path = source.accepted_upstream_path if accepted else source.upstream_path
    root = "" if selected_path == "." else selected_path.strip("/")
    if child is None:
        return root
    child = child.strip("/")
    return f"{root}/{child}" if root else child


def source_tracked_pathspecs(source: SourceRecord) -> list[str]:
    pathspecs: list[str] = []
    for tracked_path in source.tracked_paths:
        for accepted in (True, False):
            path = source_repo_path(source, tracked_path, accepted=accepted)
            if path not in pathspecs:
                pathspecs.append(path)
    return pathspecs


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
            if not is_safe_repo_path(source.accepted_upstream_path, allow_root=True):
                errors.append(
                    f"{skill.name}/{source.id}: accepted_upstream_path must be a safe repository-relative path"
                )
            paths_migrated = source.accepted_upstream_path != source.upstream_path
            if paths_migrated:
                if not SHA_PATTERN.fullmatch(source.path_migration_commit):
                    errors.append(
                        f"{skill.name}/{source.id}: path_migration_commit is required when upstream paths differ"
                    )
                if not source.path_migration_evidence:
                    errors.append(
                        f"{skill.name}/{source.id}: path_migration_evidence is required when upstream paths differ"
                    )
            elif source.path_migration_commit or source.path_migration_evidence:
                warnings.append(
                    f"{skill.name}/{source.id}: path migration metadata is present but upstream paths are identical"
                )
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
                        source.accepted_commit, source_repo_path(source, accepted=True)
                    )])
                    if baseline_path.returncode != 0:
                        errors.append(f"{skill.name}/{source.id}: upstream path missing at accepted commit")
                    for tracked_path in source.tracked_paths:
                        tracked_blob = git(
                            mirror.local_path,
                            ["cat-file", "-e", git_object(
                                source.accepted_commit,
                                source_repo_path(source, tracked_path, accepted=True),
                            )],
                        )
                        if tracked_blob.returncode != 0:
                            mirror_head = current_head(mirror.local_path)
                            current_tracked_blob = (
                                git(
                                    mirror.local_path,
                                    [
                                        "cat-file",
                                        "-e",
                                        git_object(
                                            mirror_head,
                                            source_repo_path(source, tracked_path),
                                        ),
                                    ],
                                )
                                if mirror_head
                                else None
                            )
                            if current_tracked_blob is None or current_tracked_blob.returncode != 0:
                                errors.append(
                                    f"{skill.name}/{source.id}: tracked path missing at accepted commit and current HEAD: {tracked_path}"
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
                    if paths_migrated and SHA_PATTERN.fullmatch(source.path_migration_commit):
                        migration = source.path_migration_commit
                        migration_exists = git(
                            mirror.local_path,
                            ["cat-file", "-e", f"{migration}^{{commit}}"],
                        )
                        if migration_exists.returncode != 0:
                            errors.append(
                                f"{skill.name}/{source.id}: path migration commit unavailable"
                            )
                        else:
                            accepted_ancestor = git(
                                mirror.local_path,
                                ["merge-base", "--is-ancestor", source.accepted_commit, migration],
                            )
                            current_head_value = current_head(mirror.local_path)
                            migration_ancestor = (
                                git(
                                    mirror.local_path,
                                    ["merge-base", "--is-ancestor", migration, current_head_value],
                                )
                                if current_head_value
                                else None
                            )
                            if accepted_ancestor.returncode != 0:
                                errors.append(
                                    f"{skill.name}/{source.id}: migration commit does not descend from accepted_commit"
                                )
                            if migration_ancestor is None or migration_ancestor.returncode != 0:
                                errors.append(
                                    f"{skill.name}/{source.id}: current mirror HEAD does not contain path migration commit"
                                )
                            old_tree = git(
                                mirror.local_path,
                                [
                                    "rev-parse",
                                    f"{migration}^:{source_repo_path(source, accepted=True)}",
                                ],
                            )
                            new_tree = git(
                                mirror.local_path,
                                ["rev-parse", f"{migration}:{source_repo_path(source)}"],
                            )
                            if (
                                old_tree.returncode != 0
                                or new_tree.returncode != 0
                                or old_tree.stdout.strip() != new_tree.stdout.strip()
                            ):
                                errors.append(
                                    f"{skill.name}/{source.id}: migration commit does not preserve the upstream skill tree"
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
                f"- 当前上游路径：`{source.upstream_path}`",
                f"- 接受时上游路径：`{source.accepted_upstream_path}`",
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
                *(
                    [
                        "",
                        "### 路径迁移证据",
                        "",
                        f"- 迁移提交：`{source.path_migration_commit}`",
                        *[f"- {value}" for value in source.path_migration_evidence],
                    ]
                    if source.accepted_upstream_path != source.upstream_path
                    else []
                ),
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

    baseline_skill_path = source_repo_path(source, "SKILL.md", accepted=True)
    baseline_skill = git(
        mirror,
        ["cat-file", "-e", git_object(source.accepted_commit, baseline_skill_path)],
    )
    if baseline_skill.returncode != 0:
        return {"status": "baseline_unavailable", "changed": []}
    current_identity = git_object(current, source_repo_path(source, "SKILL.md"))
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

    pathspecs = source_tracked_pathspecs(source)
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
    base_details = {
        "local_path": str(mirror.local_path),
        "expected_git_dir_path": str(mirror.git_dir_path) if mirror.git_dir_path else None,
        "expected_branch": mirror.branch,
        "expected_origin": mirror.repo_url,
    }
    if not mirror.local_path.is_dir():
        return {
            "status": "mirror_missing" if mirror.git_dir_path else "blocked_missing_git_dir",
            "head": None,
            "mirror_details": base_details,
        }
    actual_git_dir = git(mirror.local_path, ["rev-parse", "--absolute-git-dir"])
    if actual_git_dir.returncode != 0 or not actual_git_dir.stdout.strip():
        return {
            "status": "mirror_error",
            "head": None,
            "mirror_details": {
                **base_details,
                "git_dir_error": actual_git_dir.stderr.strip() or actual_git_dir.stdout.strip(),
            },
        }
    actual_git_dir_path = Path(actual_git_dir.stdout.strip())
    git_dir_matches_registry = (
        None
        if mirror.git_dir_path is None
        else canonical_path_key(actual_git_dir_path) == canonical_path_key(mirror.git_dir_path)
    )
    git_dir_details = {
        **base_details,
        "actual_git_dir_path": str(actual_git_dir_path),
        "git_dir_matches_registry": git_dir_matches_registry,
    }
    head = current_head(mirror.local_path)
    if not head:
        return {
            "status": "mirror_error",
            "head": None,
            "mirror_details": git_dir_details,
        }
    if git_dir_matches_registry is False:
        return {
            "status": "git_dir_mismatch",
            "head": head,
            "mirror_details": git_dir_details,
        }
    dirty = git(mirror.local_path, ["status", "--porcelain"])
    branch = git(mirror.local_path, ["branch", "--show-current"])
    origin = git(mirror.local_path, ["remote", "get-url", "origin"])
    if dirty.returncode != 0 or branch.returncode != 0 or origin.returncode != 0:
        return {
            "status": "mirror_error",
            "head": head,
            "mirror_details": {
                **git_dir_details,
                "status_error": dirty.stderr.strip(),
                "branch_error": branch.stderr.strip(),
                "origin_error": origin.stderr.strip(),
            },
        }
    details = {
        **git_dir_details,
        "actual_branch": branch.stdout.strip(),
        "actual_origin": origin.stdout.strip(),
        "dirty_entries": dirty.stdout.splitlines(),
    }
    if dirty.stdout.strip():
        return {"status": "dirty_mirror", "head": head, "mirror_details": details}
    if branch.stdout.strip() != mirror.branch:
        return {"status": "branch_mismatch", "head": head, "mirror_details": details}
    if normalize_repo_url(origin.stdout.strip()) != normalize_repo_url(mirror.repo_url):
        return {"status": "origin_mismatch", "head": head, "mirror_details": details}
    return {"status": "healthy", "head": head, "mirror_details": details}


def refresh_mirrors(mirrors_registry: Path) -> dict[str, Any]:
    manager = Path(__file__).with_name("manage_repo_mirrors.py")
    try:
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
    except subprocess.TimeoutExpired as exc:
        return {
            "status": "error",
            "error": f"Mirror manager timed out after {exc.timeout:g} seconds.",
            "exit_code": 124,
            "mirrors": [],
        }
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return {
            "status": "error",
            "error": completed.stderr.strip() or "Mirror manager did not return valid JSON.",
            "exit_code": completed.returncode or 1,
            "mirrors": [],
        }
    if not isinstance(payload, dict):
        return {
            "status": "error",
            "error": "Mirror manager returned JSON with an invalid top-level type.",
            "exit_code": completed.returncode or 1,
            "mirrors": [],
        }
    payload["exit_code"] = completed.returncode
    return payload


def normalize_mirror_refresh_results(
    refresh_payload: dict[str, Any],
    mirrors: dict[str, MirrorRecord],
) -> tuple[dict[str, dict[str, Any]], str | None]:
    raw_results = refresh_payload.get("mirrors", [])
    results: dict[str, dict[str, Any]] = {}
    if isinstance(raw_results, list):
        for item in raw_results:
            if isinstance(item, dict) and isinstance(item.get("id"), str):
                results[item["id"]] = item

    manager_error = None
    if refresh_payload.get("status") == "error" or (
        refresh_payload.get("exit_code") not in {None, 0} and not results
    ):
        manager_error = compact_report_text(
            refresh_payload.get("error") or "Mirror manager failed before returning per-mirror results."
        )
        for mirror_id, mirror in mirrors.items():
            if mirror_id in results:
                continue
            health = inspect_mirror(mirror)
            details = health.get("mirror_details", {})
            results[mirror_id] = {
                "id": mirror_id,
                "status": "mirror_manager_failed",
                "local_path": str(mirror.local_path),
                "local_head": health.get("head"),
                "local_branch": details.get("actual_branch"),
                "local_dirty": bool(details.get("dirty_entries")) if details else None,
                "local_origin": details.get("actual_origin"),
                "git_dir_path": str(mirror.git_dir_path) if mirror.git_dir_path else None,
                "actual_git_dir_path": details.get("actual_git_dir_path"),
                "git_dir_matches_registry": details.get("git_dir_matches_registry"),
                "error": manager_error,
            }
    return results, manager_error


def compact_report_text(value: Any, limit: int = 1000) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text if len(text) <= limit else text[: limit - 3] + "..."


def mirror_result_details(result: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "local_path",
        "local_head",
        "local_branch",
        "local_dirty",
        "local_origin",
        "git_dir_path",
        "actual_git_dir_path",
        "git_dir_matches_registry",
        "local_error",
        "failed_command",
        "failed_exit_code",
        "timed_out",
        "remote_head",
        "remote_reachable",
        "remote_error",
        "timeout_seconds",
    )
    return {key: result[key] for key in keys if key in result}


def review_source_contexts(context: dict[str, Any]) -> list[dict[str, Any]]:
    primary = {
        key: context[key]
        for key in (
            "source",
            "accepted_commit",
            "accepted_upstream_path",
            "upstream_path",
            "path_migration_commit",
            "current_upstream_commit",
        )
        if key in context
    }
    entries = [primary]
    additional = context.get("additional_sources", [])
    if not isinstance(additional, list):
        raise ValueError("Review context additional_sources must be a list.")
    entries.extend(additional)

    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("Each review source context must be an object.")
        source_id = str(entry.get("source", ""))
        if not source_id:
            raise ValueError("Each review source context must name a source.")
        if source_id in seen:
            raise ValueError(f"Duplicate review source context: {source_id}")
        seen.add(source_id)
        normalized.append(dict(entry))
    return normalized


def review_scope_payload(context: dict[str, Any]) -> dict[str, Any]:
    additional_evidence = context.get("additional_review_evidence", [])
    if not isinstance(additional_evidence, list):
        raise ValueError("Review context additional_review_evidence must be a list.")
    return {
        "skill": str(context.get("skill", "")),
        "source_contexts": review_source_contexts(context),
        "local_tree_hash": str(context.get("local_tree_hash", "")).lower(),
        "additional_review_evidence": [str(value) for value in additional_evidence],
    }


def review_scope_hash(context: dict[str, Any]) -> str:
    canonical = json.dumps(
        review_scope_payload(context),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def validate_finalized_review_integrity(context: dict[str, Any], workspace: Path) -> None:
    evidence_hashes = context.get("review_evidence_sha256")
    if not isinstance(evidence_hashes, dict):
        raise ValueError("Finalized review evidence hashes are missing.")
    missing = REQUIRED_REVIEW_EVIDENCE - {str(name) for name in evidence_hashes}
    if missing:
        raise ValueError(f"Required review evidence hashes are missing: {sorted(missing)}")
    for name, expected_hash in evidence_hashes.items():
        name = str(name)
        expected_hash = str(expected_hash).lower()
        if not is_safe_repo_path(name) or not SHA256_PATTERN.fullmatch(expected_hash):
            raise ValueError(f"Invalid review evidence hash: {name}")
        evidence_path = workspace / name
        if not evidence_path.is_file() or file_hash(evidence_path) != expected_hash:
            raise ValueError(f"Review evidence changed after finalization: {name}")

    stored_scope_hash = str(context.get("review_scope_sha256", "")).lower()
    if not SHA256_PATTERN.fullmatch(stored_scope_hash) or review_scope_hash(context) != stored_scope_hash:
        raise ValueError("Review source scope changed after finalization.")

    candidate_hash = str(context.get("candidate_tree_hash", "")).lower()
    old_hash = str(context.get("old_skill_tree_hash", "")).lower()
    patch_hash = str(context.get("candidate_patch_sha256", "")).lower()
    if (
        not SHA256_PATTERN.fullmatch(candidate_hash)
        or tree_hash(workspace / "candidate_skill") != candidate_hash
        or not SHA256_PATTERN.fullmatch(old_hash)
        or tree_hash(workspace / "old_skill") != old_hash
        or not SHA256_PATTERN.fullmatch(patch_hash)
        or file_hash(workspace / "candidate.patch") != patch_hash
    ):
        raise ValueError("Finalized candidate evidence changed after finalization.")


def validate_review_source_contexts_current(
    skill: SkillRecord,
    mirrors: dict[str, MirrorRecord],
    context: dict[str, Any],
) -> list[dict[str, Any]]:
    sources_by_id = {record.id: record for record in skill.sources}
    source_contexts = review_source_contexts(context)
    for source_context in source_contexts:
        current_source_id = str(source_context["source"])
        current_source = sources_by_id.get(current_source_id)
        if not current_source:
            raise ValueError(f"Unknown source for {skill.name}: {current_source_id}")
        if str(source_context.get("accepted_commit", "")).lower() != current_source.accepted_commit:
            raise ValueError(f"Accepted baseline changed for {current_source_id}.")
        if (
            source_context.get("accepted_upstream_path", current_source.accepted_upstream_path)
            != current_source.accepted_upstream_path
        ):
            raise ValueError(f"Accepted upstream path changed for {current_source_id}.")
        if source_context.get("upstream_path", current_source.upstream_path) != current_source.upstream_path:
            raise ValueError(f"Current upstream path changed for {current_source_id}.")
        if (
            str(source_context.get("path_migration_commit", current_source.path_migration_commit)).lower()
            != current_source.path_migration_commit
        ):
            raise ValueError(f"Path migration identity changed for {current_source_id}.")
        mirror = mirrors.get(current_source.mirror_id)
        if mirror is None:
            raise ValueError(f"Unknown mirror for {current_source_id}: {current_source.mirror_id}")
        health = inspect_mirror(mirror)
        if health["status"] != "healthy":
            raise ValueError(f"Mirror for {current_source_id} is not healthy: {health['status']}")
        if health["head"] != str(source_context.get("current_upstream_commit", "")).lower():
            raise ValueError(f"Upstream HEAD changed for {current_source_id}.")
        diff_status = source_diff(mirror.local_path, current_source, health["head"])
        if diff_status["status"] != "review_required":
            raise ValueError(
                f"Source {current_source_id} is no longer eligible for candidate review: "
                f"{diff_status['status']}"
            )
    return source_contexts


def finalized_candidate_index(
    reports_root: Path,
    skills: list[SkillRecord],
    mirrors: dict[str, MirrorRecord],
) -> tuple[dict[tuple[str, str, str, str], dict[str, Any]], list[dict[str, Any]]]:
    index: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    valid_by_skill: dict[str, list[tuple[dict[str, Any], list[tuple[str, str, str, str]]]]] = {}
    conflicts: list[dict[str, Any]] = []
    skills_by_name = {skill.name: skill for skill in skills}
    if not reports_root.is_dir():
        return index, conflicts
    for context_path in reports_root.glob("*/*/*/review-context.json"):
        try:
            context = json.loads(context_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if context.get("candidate_status") != "awaiting_approval":
            continue
        workspace = context_path.parent
        if not (workspace / "old_skill").is_dir() or not (workspace / "candidate_skill").is_dir():
            continue
        if any(not (workspace / name).is_file() for name in FINALIZED_CANDIDATE_FILES):
            continue
        skill_name = str(context.get("skill", ""))
        skill = skills_by_name.get(skill_name)
        if skill is None:
            continue
        try:
            validate_finalized_review_integrity(context, workspace)
            source_contexts = validate_review_source_contexts_current(skill, mirrors, context)
        except ValueError:
            continue
        candidate = {
            "workspace": str(workspace.resolve()),
            "finalized_at": str(context.get("finalized_at", "")),
            "source_count": len(source_contexts),
        }
        candidate_keys = [
            (
                skill_name,
                str(source_context["source"]),
                str(source_context["accepted_commit"]).lower(),
                str(source_context["current_upstream_commit"]).lower(),
            )
            for source_context in source_contexts
        ]
        if all(SHA_PATTERN.fullmatch(key[2]) and SHA_PATTERN.fullmatch(key[3]) for key in candidate_keys):
            valid_by_skill.setdefault(skill_name, []).append((candidate, candidate_keys))

    for skill_name, entries in valid_by_skill.items():
        workspaces = sorted({candidate["workspace"] for candidate, _ in entries})
        if len(workspaces) > 1:
            conflicts.append(
                {
                    "skill": skill_name,
                    "workspaces": workspaces,
                    "problem": "同一技能存在多个独立的待批准候选，无法安全地只批准一次。",
                    "impact": "所有候选暂不恢复为 awaiting_approval；相关来源重新进入差异评估，避免重复批准或漏审来源。",
                    "automatic_action": "保留各隔离候选及证据，未修改技能源码、accepted_commit 或 last_reviewed_commit。",
                    "repair_plan": [
                        "比较各候选的上游差异和本地候选改动，确认合并范围。",
                        "从同一正式技能快照创建一个组合候选，并用 --additional-source 纳入其余来源。",
                        "运行组合评测、回归测试和许可证复核后，只定稿一个技能级候选。",
                    ],
                    "approval_required": False,
                    "approval_reason": "合并候选和重新测试是安全的隔离操作；应用仍需用户逐技能批准。",
                }
            )
            continue
        for candidate, candidate_keys in entries:
            for key in candidate_keys:
                previous = index.get(key)
                if previous is None or (candidate["finalized_at"], candidate["workspace"]) > (
                    previous["finalized_at"],
                    previous["workspace"],
                ):
                    index[key] = candidate
    return index, conflicts


def diagnose_report_row(
    row: dict[str, Any],
    source: SourceRecord | None,
    mirror: MirrorRecord,
) -> dict[str, Any]:
    status = str(row["status"])
    if status not in DIAGNOSTIC_STATUSES:
        return {}

    mirror_path = str(mirror.local_path)
    network_target = mirror.repo_url
    details = row.get("mirror_details") if isinstance(row.get("mirror_details"), dict) else {}
    detail_errors = " | ".join(
        compact_report_text(details.get(key))
        for key in (
            "local_error",
            "git_dir_error",
            "status_error",
            "branch_error",
            "origin_error",
        )
        if compact_report_text(details.get(key))
    )
    error = compact_report_text(row.get("error") or detail_errors)
    effective_status = status
    if status == "mirror_blocked":
        lowered = error.lower()
        mirror_status = str(row.get("mirror_status", ""))
        if mirror_status in {
            "blocked_missing_git_dir",
            "git_dir_mismatch",
            "tracked_diff_failed",
        }:
            effective_status = mirror_status
        elif details.get("git_dir_matches_registry") is False:
            effective_status = "git_dir_mismatch"
        elif details.get("local_dirty") or "uncommitted changes" in lowered:
            effective_status = "dirty_mirror"
        elif "origin" in lowered and ("mismatch" in lowered or "does not match" in lowered):
            effective_status = "origin_mismatch"
        elif "branch" in lowered and ("mismatch" in lowered or "does not match" in lowered):
            effective_status = "branch_mismatch"
        elif "permission denied" in lowered or "access is denied" in lowered:
            effective_status = "permission_denied"
        elif any(
            marker in lowered
            for marker in (
                "non-fast-forward",
                "not a fast-forward",
                "not possible to fast-forward",
            )
        ):
            effective_status = "mirror_non_fast_forward"
        elif "timed out" in lowered or "timeout" in lowered:
            effective_status = "remote_timeout"
        else:
            effective_status = "mirror_refresh_failed"

    if source is None:
        automatic_action = (
            "已隔离该镜像刷新失败并保留现有镜像与状态证据；未修改技能源码、来源登记、"
            "accepted_commit 或 last_reviewed_commit。其他镜像和正式来源继续检查。"
        )
    else:
        automatic_action = (
            "已隔离该来源并保留现有镜像与状态证据；未生成或应用候选，未修改本地技能、"
            "accepted_commit 或 last_reviewed_commit。其他健康来源继续检查。"
        )
    actual_branch = compact_report_text(details.get("actual_branch") or details.get("local_branch")) or "未知"
    actual_origin = compact_report_text(details.get("actual_origin") or details.get("local_origin")) or "未知"

    if effective_status == "blocked_missing_git_dir":
        problem = (
            f"镜像工作树 `{mirror_path}` 不存在，登记表也未配置外置 `git_dir_path`；"
            "为避免在同步盘内重新创建 `.git`，检查和同步均已停止。"
        )
        impact = "没有可验证的本地镜像，无法刷新上游、比较接受基线或生成候选。"
        repair_plan = [
            "为该镜像选择唯一的绝对 `git_dir_path`，路径必须位于同步盘、技能源码目录和各运行时技能目录之外。",
            "把该路径写入 repo-mirrors.toml；核对仓库 URL、分支和 zero-exposure 工作树路径。",
            "重跑镜像 check，确认状态变为 needs_init；再运行 sync，用 `--separate-git-dir` 创建干净镜像。",
            "验证实际 Git 目录、origin、branch、HEAD 和干净工作树后重跑 weekly-run。",
        ]
        approval_required = True
        approval_reason = "新增正式镜像路径配置会改变维护登记，需要用户批准；只读核对不需要批准。"
    elif effective_status == "git_dir_mismatch":
        expected_git_dir = compact_report_text(
            details.get("git_dir_path") or details.get("expected_git_dir_path")
        ) or "未记录"
        actual_git_dir = compact_report_text(details.get("actual_git_dir_path")) or "未知"
        problem = (
            f"镜像声明的 Git 元数据目录 `{expected_git_dir}` 与 Git 实际使用目录 "
            f"`{actual_git_dir}` 不一致。"
        )
        impact = "zero-exposure 边界无法证明，继续刷新可能把 `.git` 留在同步盘或操作错误的对象数据库。"
        repair_plan = [
            f"只读运行 `git -C \"{mirror_path}\" rev-parse --absolute-git-dir`，并核对登记值和实际目录。",
            "保留现有工作树和 Git 元数据；检查 `.git` 文件或目录、对象库完整性、origin、branch 和 HEAD。",
            "优先在新 zero-exposure 工作树按登记的外置 Git 目录重新克隆并验证，不自动移动或删除旧 Git 元数据。",
            "若登记值本身错误，保存来源身份和路径证据，经用户批准后修正 repo-mirrors.toml，再重跑 weekly-run。",
        ]
        approval_required = True
        approval_reason = "迁移 Git 元数据或修改正式登记路径可能影响仓库历史与同步边界，需要用户批准。"
    elif effective_status == "tracked_diff_failed":
        problem = "镜像已刷新，但 Git 未能完整提取更新前后跟踪路径的文件差异。"
        impact = "自动化不能证明哪些已登记上游技能发生变化，因此不会把本次结果当作无变化，也不会生成候选。"
        repair_plan = [
            "保留 before_head、after_head 和原始 Git 错误，确认失败是超时、对象缺失、路径问题还是仓库损坏。",
            "用报告中的两个提交和相同 tracked path 只读重跑 `git diff --name-only`。",
            "若对象缺失或镜像损坏，在新 zero-exposure 目录建立干净镜像并复核两个提交。",
            "差异提取成功后重跑 weekly-run；不得把失败结果记录为 no-impact。",
        ]
        approval_required = False
        approval_reason = "只读重试和新建隔离镜像不需要批准；清理旧镜像或改登记仍需另行批准。"
    elif effective_status == "dirty_mirror":
        problem = f"上游镜像 `{mirror_path}` 含未提交修改，自动刷新为避免覆盖本地内容而停止。"
        impact = "该来源无法确认最新提交，也不能生成可信候选；同一技能的其他健康来源不受影响。"
        repair_plan = [
            f"只读运行 `git -C \"{mirror_path}\" status --short` 和 `git -C \"{mirror_path}\" diff`，保存并判断修改归属。",
            "默认保留原镜像；在新的 zero-exposure 目录建立干净镜像，不清理、不 reset 原目录。",
            "验证新镜像的 origin、branch、HEAD、工作树和许可证后，更新镜像登记并重跑 weekly-run。",
            "只有确认旧修改无需保留时，才在用户逐项批准后清理旧镜像。",
        ]
        approval_required = True
        approval_reason = "读取和新建隔离镜像不需批准；清理现有修改或切换登记路径前需要用户批准。"
    elif effective_status == "branch_mismatch":
        problem = f"镜像当前分支 `{actual_branch}` 与登记分支 `{mirror.branch}` 不一致。"
        impact = "当前 HEAD 可能不是登记来源的预期历史，继续比较会把错误分支变化当成上游更新。"
        source_identity_step = (
            f"确认上游路径 `{source.upstream_path}` 在哪条分支持续维护，并核对接受提交 "
            f"`{source.accepted_commit}` 的归属。"
            if source is not None
            else "核对该镜像登记分支与当前跟踪用途，确认是否仍需保留这条镜像登记。"
        )
        repair_plan = [
            f"只读核对 `{mirror_path}` 的当前分支、远端分支和登记分支 `{mirror.branch}`。",
            source_identity_step,
            "若登记正确，在新 zero-exposure 目录克隆正确分支；若登记错误，保留证据并经用户确认后修改登记表。",
            "验证干净工作树和提交连续性后重跑 weekly-run。",
        ]
        approval_required = True
        approval_reason = "切换现有镜像分支或修改登记分支会改变跟踪对象，需要用户批准。"
    elif effective_status == "origin_mismatch":
        problem = f"镜像 origin `{actual_origin}` 与登记仓库 `{mirror.repo_url}` 不一致。"
        impact = "来源身份无法确认，自动刷新可能从错误仓库取回内容，因此该来源被阻止。"
        repair_plan = [
            f"只读核对 `{mirror_path}` 的 `remote -v`、登记 URL 和接受提交来源。",
            "确认正确仓库及其许可证、默认分支和上游技能路径。",
            "默认保留原镜像并从登记 URL 新建 zero-exposure 镜像；若登记 URL 错误，经用户确认后修正登记表。",
            "验证来源身份和提交历史后重跑 weekly-run。",
        ]
        approval_required = True
        approval_reason = "修改 origin 或来源登记会改变上游身份，需要用户批准。"
    elif effective_status == "permission_denied":
        problem = f"镜像 `{mirror_path}` 的工作树或 Git 元数据拒绝写入，刷新失败。"
        impact = "本地镜像停留在旧提交，无法判断当前上游变化，现有候选也必须先检查是否过期。"
        repair_plan = [
            "保留当前镜像作为证据，检查报错文件的 Windows ACL、只读属性、锁文件和占用进程。",
            "优先在新的 zero-exposure 目录建立干净镜像，验证 URL、分支、HEAD、工作树和许可证。",
            "干净镜像可用后更新镜像登记并重跑 weekly-run，再检查候选提交是否仍是当前 HEAD。",
            "只有新镜像方案不可用时，才在用户批准后最小范围修复报错文件的 ACL；不递归放宽整个目录权限。",
        ]
        approval_required = True
        approval_reason = "新建隔离镜像不需批准；修改 Windows ACL 或替换 Git 元数据前需要用户批准。"
    elif effective_status == "mirror_non_fast_forward":
        problem = "镜像本地分支与 fetch 后的远端跟踪分支发生非快进分叉，本地快进安全检查拒绝合并。"
        impact = "自动化无法确定应保留哪段历史，强制 reset 可能丢失本地证据。"
        repair_plan = [
            f"只读检查 `{mirror_path}` 的 merge-base、reflog 和本地/远端提交图。",
            "保留现有镜像，在新 zero-exposure 目录克隆远端当前分支并核对来源路径与许可证。",
            "比较旧镜像独有提交，确认是否需要保存为补丁或独立分支。",
            "经用户确认历史处理方式后更新镜像登记并重跑 weekly-run；不对旧镜像执行强制 reset。",
        ]
        approval_required = True
        approval_reason = "选择丢弃、保留或迁移分叉提交属于历史处理决策，需要用户批准。"
    elif effective_status == "remote_timeout":
        problem = f"镜像刷新或远端查询 `{network_target}` 超过单仓库超时预算。"
        impact = "本次无法确认远端 HEAD；报告保留本地提交，但不会据此生成候选。"
        repair_plan = [
            f"保留本次错误并记录准确访问目标 `{network_target}`，区分 DNS、TCP、TLS 和 HTTP/Git 响应阶段。",
            "在不修改镜像的前提下，对同一目标执行有次数上限的 `curl.exe -I` 或 `git ls-remote` 复测，确认是瞬时故障还是持续不可达。",
            "单次 TLS 握手超时只说明该次连接没有按时完成，不能据此判断 VPN 不可用；代理、DNS、远端服务或本机 TLS 配置必须由复测证据区分。",
            "网络恢复后重跑 weekly-run；若反复超时，再评估是否需要调整单仓库超时。",
        ]
        approval_required = False
        approval_reason = "只读网络诊断和按现有配置重试不需要用户批准。"
    elif effective_status == "mirror_refresh_failed":
        problem = f"镜像管理器未能完成对 `{network_target}` 的刷新，当前错误尚不能安全归类为权限、工作树、分支或远端身份问题。"
        impact = "该来源停留在已知本地提交，不能生成新的候选。"
        repair_plan = [
            "按原始错误定位失败阶段：clone、fetch、本地 `merge --ff-only`、网络或本地 Git 仓库检查。",
            f"只读核对镜像状态、origin、branch、HEAD 和准确目标 `{network_target}` 的远端可达性。",
            "优先保留原镜像并在新 zero-exposure 目录复现；修复后重跑 weekly-run。",
            "若修复需要清理、重置、改权限或改登记表，先取得用户批准。",
        ]
        approval_required = False
        approval_reason = "只读诊断和新建隔离镜像不需批准；任何破坏性修复仍需另行批准。"
    elif status == "mirror_missing":
        problem = f"登记的镜像目录 `{mirror_path}` 不存在。"
        impact = "没有本地比较副本，无法验证接受基线或检查上游更新。"
        repair_plan = [
            "核对镜像登记路径、仓库 URL、分支和 zero-exposure 位置。",
            f"从 `{mirror.repo_url}` 的 `{mirror.branch}` 分支新建干净镜像，不写入任何技能加载目录。",
            "验证工作树、HEAD、接受提交和许可证后重跑 weekly-run。",
        ]
        approval_required = False
        approval_reason = "按现有登记新建 zero-exposure 镜像不改变技能源码或接受基线。"
    elif status == "mirror_error":
        problem = f"镜像 `{mirror_path}` 无法被 Git 正常读取，或状态、分支、origin 检查失败。"
        impact = "镜像完整性无法确认，不能用它生成上游差异或候选。"
        repair_plan = [
            "保留原目录，记录失败的 Git 子命令和错误。",
            "检查仓库结构、Git 元数据、锁文件、ACL 和磁盘状态。",
            "优先新建干净 zero-exposure 镜像并验证；不要自动删除或 reset 原目录。",
            "新镜像验证通过后更新登记并重跑 weekly-run。",
        ]
        approval_required = False
        approval_reason = "只读检查和新建隔离镜像不需批准；清理旧目录或改权限需另行批准。"
    elif status == "baseline_unavailable":
        problem = f"镜像中找不到已接受提交 `{source.accepted_commit}`。"
        impact = "无法证明当前上游相对本地已吸收基线的变化，候选生成被阻止。"
        repair_plan = [
            "检查镜像是否为浅克隆，并获取完整分支、tag 和必要历史后再次验证该提交。",
            "从远端、旧镜像或归档证据定位原接受提交，核对仓库身份。",
            "若上游重写历史，只在找到 tracked paths 与许可证完全等价的提交后提出基线身份迁移。",
            "没有等价证据时保留原 accepted_commit，改用人工两树比较，不把当前 HEAD 直接设为已接受基线。",
        ]
        approval_required = True
        approval_reason = "任何 accepted_commit 身份迁移都需要用户批准和等价证据。"
    elif status == "non_fast_forward":
        current = compact_report_text(row.get("current_commit")) or "未知"
        problem = f"已接受提交 `{source.accepted_commit}` 不是当前上游 `{current}` 的祖先，历史可能被强制推送或发生分叉。"
        impact = "线性差异不可信，自动化不能判断哪些变化属于正常更新。"
        repair_plan = [
            "只读检查 merge-base、提交图、远端 reflog 或发布 tag，确认历史重写范围。",
            "比较接受提交与新历史中候选等价提交的 tracked paths、tree hash 和许可证。",
            "若找到内容等价提交，经用户批准后只迁移基线身份；若找不到，保留旧镜像并做人工两树比较。",
            "完成历史连续性审查后重跑 weekly-run，不执行强制 reset。",
        ]
        approval_required = True
        approval_reason = "历史身份迁移或分叉处理会改变信任基线，需要用户批准。"
    elif status == "diff_failed":
        problem = "Git 无法完成接受基线与当前提交之间的许可证或跟踪路径差异提取。"
        impact = "变更文件清单不完整，无法开展收益评估或生成候选。"
        repair_plan = [
            "查看原始 Git 错误，分别验证两个提交对象、许可证路径和 tracked paths 是否存在。",
            "用相同参数只读重试 diff，确认是否为瞬时锁、路径或对象数据库问题。",
            "若镜像损坏，保留原目录并新建干净 zero-exposure 镜像后重跑 weekly-run。",
        ]
        approval_required = False
        approval_reason = "只读验证、重试和新建隔离镜像不需要用户批准。"
    elif status == "upstream_removed_or_moved":
        problem = f"当前上游提交中找不到登记路径 `{source.upstream_path}` 下的技能入口，技能可能被删除或移动。"
        impact = "不能仅凭相似名称继续跟踪；自动改路径可能把另一个技能误认为原来源。"
        repair_plan = [
            "用 Git rename 历史、文件清单、blob/tree hash 和提交说明查找旧路径去向。",
            "比较候选新路径的 SKILL.md、脚本、参考文件和许可证，确认是否为同一技能的连续迁移。",
            "确认后保留 accepted_commit，并在登记表记录旧路径、新路径和迁移证据，再重新生成来源页。",
            "运行 validate、render 和相关测试；元数据修正单独提交，不把当前 HEAD 自动当作已吸收基线。",
        ]
        approval_required = True
        approval_reason = "确认新路径属于同一来源并修改正式登记，需要用户逐来源批准。"
    else:
        changed_paths = ", ".join(item.get("path", "") for item in row.get("changed", [])) or "登记的许可证路径"
        problem = f"许可证文件发生变化、缺失或被替换：{changed_paths}。"
        impact = "继续吸收上游内容可能改变复制、修改、再分发或署名义务，因此候选生成被阻止。"
        repair_plan = [
            "对比 accepted_commit 与当前提交的许可证全文、文件路径和 SPDX 标识。",
            "确认变化影响的上游技能文件、第三方依赖及本地已吸收内容。",
            "记录兼容性结论和必须履行的署名、NOTICE 或分发义务；不确定时保持阻止状态。",
            "只有许可证允许且用户明确批准后，才恢复收益评估；不自动更新 accepted_commit。",
        ]
        approval_required = True
        approval_reason = "许可证兼容性和新增义务需要人工复核与用户批准。"

    if status == "mirror_blocked":
        mirror_status = compact_report_text(row.get("mirror_status")) or "unknown"
        problem = f"镜像刷新被阻止（镜像管理器状态：`{mirror_status}`）。{problem}"
    if source is None:
        impact = (
            "该镜像未被正式 skill source 引用，因此本次正式来源和待批准候选不受影响；"
            "但整批镜像刷新不完整，weekly-run 必须返回非零并在摘要中保留异常。"
        )
    if error:
        problem += f" 原始错误：{error}"
    return {
        "problem": problem,
        "impact": impact,
        "repair_plan": repair_plan,
        "automatic_action": automatic_action,
        "approval_required": approval_required,
        "approval_reason": approval_reason,
    }


def markdown_report_text(value: Any) -> str:
    return compact_report_text(value).replace("`", "'") or "-"


def build_report(
    skills: list[SkillRecord],
    mirrors: dict[str, MirrorRecord],
    reports_root: Path,
    date: str,
    state_path: Path,
    mirror_results: dict[str, dict[str, Any]] | None = None,
    mirror_refresh_exit_code: int | None = None,
    mirror_manager_error: str | None = None,
) -> dict[str, Any]:
    if mirror_manager_error:
        mirror_results, _ = normalize_mirror_refresh_results(
            {
                "status": "error",
                "error": mirror_manager_error,
                "exit_code": mirror_refresh_exit_code or 1,
                "mirrors": list((mirror_results or {}).values()),
            },
            mirrors,
        )
    state = read_state(state_path)
    candidates, candidate_conflicts = finalized_candidate_index(reports_root, skills, mirrors)
    rows: list[dict[str, Any]] = []
    now = datetime.now(timezone.utc).isoformat()
    for skill in skills:
        for source in skill.sources:
            mirror = mirrors[source.mirror_id]
            source_state = state["sources"].setdefault(source.id, {})
            refresh_result = mirror_results.get(source.mirror_id) if mirror_results else None
            if refresh_result and refresh_result.get("status") not in SUCCESSFUL_MIRROR_REFRESH_STATUSES:
                row = {
                    "skill": skill.name,
                    "source": source.id,
                    "status": "mirror_blocked",
                    "current_commit": refresh_result.get("local_head") or refresh_result.get("after_head"),
                    "changed": [],
                    "mirror_status": refresh_result.get("status"),
                    "error": refresh_result.get("error") or refresh_result.get("remote_error"),
                    "mirror_details": mirror_result_details(refresh_result),
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
                        "mirror_details": health.get("mirror_details", {}),
                    }
                elif head == source.accepted_commit:
                    row = {"skill": skill.name, "source": source.id, "status": "up_to_date", "current_commit": head, "changed": []}
                elif candidate := candidates.get(
                    (skill.name, source.id, source.accepted_commit, str(head).lower())
                ):
                    row = {
                        "skill": skill.name,
                        "source": source.id,
                        "status": "awaiting_approval",
                        "current_commit": head,
                        "changed": [],
                        "review_workspace": candidate["workspace"],
                        "candidate_finalized_at": candidate["finalized_at"],
                        "review_source_count": candidate["source_count"],
                        "approval_required": True,
                    }
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
            if row["status"] in DIAGNOSTIC_STATUSES:
                row.update(diagnose_report_row(row, source, mirror))
            observed_commit = row.get("current_commit")
            if isinstance(observed_commit, str) and SHA_PATTERN.fullmatch(observed_commit.lower()):
                source_state["last_seen_commit"] = observed_commit.lower()
                source_state["last_seen_at"] = now
            rows.append(row)

    referenced_mirror_ids = {
        source.mirror_id
        for skill in skills
        for source in skill.sources
    }
    unreferenced_mirror_failures: list[dict[str, Any]] = []
    if mirror_results:
        for mirror_id, refresh_result in sorted(mirror_results.items()):
            if (
                mirror_id in referenced_mirror_ids
                or refresh_result.get("status") in SUCCESSFUL_MIRROR_REFRESH_STATUSES
            ):
                continue
            mirror = mirrors.get(mirror_id)
            if mirror is None:
                continue
            failure = {
                "mirror": mirror_id,
                "status": "mirror_blocked",
                "mirror_status": refresh_result.get("status"),
                "current_commit": refresh_result.get("local_head") or refresh_result.get("after_head"),
                "error": refresh_result.get("error") or refresh_result.get("remote_error"),
                "mirror_details": mirror_result_details(refresh_result),
            }
            failure.update(diagnose_report_row(failure, None, mirror))
            unreferenced_mirror_failures.append(failure)

    counts = dict(Counter(row["status"] for row in rows))
    source_check_error_count = sum(
        1
        for row in rows
        if row["status"] in CHECK_ERROR_STATUSES
        and not (
            mirror_manager_error
            and row.get("mirror_status") == "mirror_manager_failed"
        )
    )
    unreferenced_check_error_count = sum(
        1
        for row in unreferenced_mirror_failures
        if not (
            mirror_manager_error
            and row.get("mirror_status") == "mirror_manager_failed"
        )
    )
    check_error_count = (
        source_check_error_count
        + unreferenced_check_error_count
        + len(candidate_conflicts)
        + (1 if mirror_manager_error else 0)
    )
    awaiting_groups = {
        (row["skill"], str(row.get("review_workspace", "")))
        for row in rows
        if row["status"] == "awaiting_approval"
    }
    payload = {
        "schema_version": 1,
        "date": date,
        "generated_at": now,
        "source_count": len(rows),
        "awaiting_approval_skill_count": len(awaiting_groups),
        "candidate_conflict_count": len(candidate_conflicts),
        "candidate_conflicts": candidate_conflicts,
        "check_error_count": check_error_count,
        "counts": counts,
        "sources": rows,
        "unreferenced_mirror_failure_count": len(unreferenced_mirror_failures),
        "unreferenced_mirror_failures": unreferenced_mirror_failures,
    }
    if mirror_manager_error:
        payload["mirror_manager_error"] = mirror_manager_error
    if mirror_refresh_exit_code is not None:
        payload["mirror_refresh_exit_code"] = mirror_refresh_exit_code
    run_root = reports_root / date
    write_json(run_root / "summary.json", payload)
    write_json(state_path, state)

    md = [
        f"# 自建技能上游周检 {date}",
        "",
        f"- 已登记来源：{len(rows)}",
        f"- 等待收益评估：{counts.get('review_required', 0)}",
        f"- 等待逐项批准（技能）：{len(awaiting_groups)}",
        f"- 许可证复核：{counts.get('license_review_required', 0)}",
        f"- 检查异常：{check_error_count}",
        *(
            [f"- 镜像刷新退出码：{mirror_refresh_exit_code}"]
            if mirror_refresh_exit_code is not None
            else []
        ),
        *(
            [f"- 镜像管理器全局错误：{markdown_report_text(mirror_manager_error)}"]
            if mirror_manager_error
            else []
        ),
        "",
        "| 本地技能 | 来源 | 状态 | 当前提交 | 变更文件数 |",
        "| --- | --- | --- | --- | ---: |",
    ]
    for row in rows:
        current = row.get("current_commit") or "-"
        md.append(f"| `{row['skill']}` | `{row['source']}` | `{row['status']}` | `{current[:12]}` | {len(row.get('changed', []))} |")

    awaiting_rows = [row for row in rows if row["status"] == "awaiting_approval"]
    if awaiting_rows:
        md.extend(["", "## 等待逐项批准", ""])
        grouped_rows: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for row in awaiting_rows:
            key = (row["skill"], str(row["review_workspace"]))
            grouped_rows.setdefault(key, []).append(row)
        for (skill_name, workspace), group in grouped_rows.items():
            md.extend(
                [
                    f"### `{skill_name}`",
                    "",
                    "- 上游来源："
                    + "；".join(
                        f"`{row['source']}` @ `{row['current_commit']}`" for row in group
                    ),
                    f"- 审核目录：`{markdown_report_text(workspace)}`",
                    "- 候选性质：这是从正式本地技能复制后形成的隔离可选升级草稿，不是新安装的技能。",
                    "- 正式技能：正式本地技能仍保持原样并可继续使用；候选不会在批准前覆盖它。",
                    "- 对比范围：针对性对比评测只衡量本次拟议行为，不是对技能全部能力的综合评分。",
                    "- 分数解释：旧版在这些用例上得分较低，只说明它未覆盖拟议行为，不能证明旧技能整体失效或不可用。",
                    "- 当前动作：保留已定稿候选并等待该技能的明确批准；未修改 accepted_commit 或 last_reviewed_commit。",
                    "",
                ]
            )

    diagnostic_rows = [row for row in rows if row["status"] in DIAGNOSTIC_STATUSES]
    if diagnostic_rows or unreferenced_mirror_failures or candidate_conflicts or mirror_manager_error:
        md.extend(["", "## 异常详情与修复计划", ""])
        if mirror_manager_error:
            md.extend(
                [
                    "### 镜像管理器全局异常",
                    "",
                    f"- 问题：镜像管理器未返回完整的逐镜像结果。原始错误：{markdown_report_text(mirror_manager_error)}",
                    "- 影响：本次所有缺失结果的来源均被阻止，不能据本地旧镜像生成新结论或候选。",
                    "- 已自动处理：保留顶层错误，并把缺失结果的镜像标记为 mirror_manager_failed；其他已有逐镜像结果仍单独处理。",
                    "- 用户批准：当前安全步骤不需要。只读诊断和按原配置重试不改变技能源码或接受基线。",
                    "",
                    "修复步骤：",
                    "",
                    "1. 查看 mirror-results.json 中的顶层错误、退出码和标准错误，定位登记表加载、进程启动、JSON 解析或总超时阶段。",
                    "2. 单独运行 manage_repo_mirrors.py check，确认能否生成逐镜像 JSON。",
                    "3. 修复对应配置或运行环境后重跑 weekly-run；不得把缺失结果解释为无更新。",
                    "",
                ]
            )
        for row in candidate_conflicts:
            approval = "需要" if row["approval_required"] else "当前安全步骤不需要"
            md.extend(
                [
                    f"### 技能 `{row['skill']}` - 多候选冲突",
                    "",
                    f"- 候选目录：{'；'.join(f'`{markdown_report_text(path)}`' for path in row['workspaces'])}",
                    f"- 问题：{markdown_report_text(row['problem'])}",
                    f"- 影响：{markdown_report_text(row['impact'])}",
                    f"- 已自动处理：{markdown_report_text(row['automatic_action'])}",
                    f"- 用户批准：{approval}。{markdown_report_text(row['approval_reason'])}",
                    "",
                    "修复步骤：",
                    "",
                ]
            )
            for index, step in enumerate(row["repair_plan"], start=1):
                md.append(f"{index}. {markdown_report_text(step)}")
            md.append("")
        for row in unreferenced_mirror_failures:
            approval = "需要" if row["approval_required"] else "当前安全步骤不需要"
            md.extend(
                [
                    f"### 镜像 `{row['mirror']}` - `{row['mirror_status']}`",
                    "",
                    f"- 问题：{markdown_report_text(row['problem'])}",
                    f"- 影响：{markdown_report_text(row['impact'])}",
                    f"- 已自动处理：{markdown_report_text(row['automatic_action'])}",
                    f"- 用户批准：{approval}。{markdown_report_text(row['approval_reason'])}",
                    "",
                    "修复步骤：",
                    "",
                ]
            )
            for index, step in enumerate(row["repair_plan"], start=1):
                md.append(f"{index}. {markdown_report_text(step)}")
            md.append("")
        for row in diagnostic_rows:
            approval = "需要" if row["approval_required"] else "当前安全步骤不需要"
            md.extend(
                [
                    f"### `{row['skill']}` / `{row['source']}` - `{row['status']}`",
                    "",
                    f"- 问题：{markdown_report_text(row['problem'])}",
                    f"- 影响：{markdown_report_text(row['impact'])}",
                    f"- 已自动处理：{markdown_report_text(row['automatic_action'])}",
                    f"- 用户批准：{approval}。{markdown_report_text(row['approval_reason'])}",
                    "",
                    "修复步骤：",
                    "",
                ]
            )
            for index, step in enumerate(row["repair_plan"], start=1):
                md.append(f"{index}. {markdown_report_text(step)}")
            md.append("")
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


def current_awaiting_candidate_workspaces(
    reports_root: Path,
    skill_name: str,
    skills: list[SkillRecord],
    mirrors: dict[str, MirrorRecord],
    exclude_workspace: Path | None = None,
) -> list[Path]:
    excluded = exclude_workspace.resolve() if exclude_workspace else None
    workspaces: list[Path] = []
    skill = next((record for record in skills if record.name == skill_name), None)
    if skill is None:
        return workspaces
    if not reports_root.is_dir():
        return workspaces
    for date_root in reports_root.iterdir():
        skill_root = date_root / skill_name
        if not skill_root.is_dir():
            continue
        for context_path in skill_root.glob("*/review-context.json"):
            workspace = context_path.parent.resolve()
            if excluded is not None and workspace == excluded:
                continue
            try:
                context = json.loads(context_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if context.get("candidate_status") != "awaiting_approval":
                continue
            try:
                validate_finalized_review_integrity(context, workspace)
                validate_review_source_contexts_current(skill, mirrors, context)
            except ValueError:
                continue
            workspaces.append(workspace)
    return sorted(workspaces)


def prepare_review(
    skills: list[SkillRecord],
    mirrors: dict[str, MirrorRecord],
    skills_root: Path,
    reports_root: Path,
    date: str,
    skill_name: str,
    source_id: str,
    expected_commit: str,
    additional_sources: list[tuple[str, str]] | None = None,
) -> dict[str, Any]:
    skill = next((record for record in skills if record.name == skill_name), None)
    if not skill:
        raise ValueError(f"Unknown skill: {skill_name}")
    existing_candidates = current_awaiting_candidate_workspaces(
        reports_root,
        skill_name,
        skills,
        mirrors,
    )
    if existing_candidates:
        return {
            "status": "blocked_existing_skill_candidate",
            "skill": skill_name,
            "existing_workspaces": [str(path) for path in existing_candidates],
        }
    sources_by_id = {record.id: record for record in skill.sources}
    requested_sources = [(source_id, expected_commit), *(additional_sources or [])]
    seen_sources: set[str] = set()
    prepared_sources: list[tuple[SourceRecord, MirrorRecord, str]] = []
    for requested_source_id, requested_commit in requested_sources:
        if requested_source_id in seen_sources:
            raise ValueError(f"Duplicate prepare-review source: {requested_source_id}")
        seen_sources.add(requested_source_id)
        source = sources_by_id.get(requested_source_id)
        if source is None:
            raise ValueError(f"Unknown source for {skill_name}: {requested_source_id}")
        mirror = mirrors[source.mirror_id]
        health = inspect_mirror(mirror)
        if health["status"] != "healthy":
            return {
                "status": f"blocked_{health['status']}",
                "skill": skill_name,
                "source": requested_source_id,
            }
        head = health["head"]
        requested_commit = requested_commit.lower()
        if not SHA_PATTERN.fullmatch(requested_commit) or head != requested_commit:
            return {
                "status": "blocked_stale_report",
                "skill": skill_name,
                "source": requested_source_id,
                "expected_commit": requested_commit,
                "current_commit": head,
            }
        diff_status = source_diff(mirror.local_path, source, head)
        if diff_status["status"] != "review_required":
            return {
                "status": f"blocked_{diff_status['status']}",
                "skill": skill_name,
                "source": requested_source_id,
                "current_commit": head,
            }
        prepared_sources.append((source, mirror, head))

    skill_root = skills_root / skill_name
    repo_root_result = git(skills_root, ["rev-parse", "--show-toplevel"])
    if repo_root_result.returncode != 0:
        raise RuntimeError(repo_root_result.stderr.strip() or "Unable to find skills git repository.")
    target_status = git(skills_root, ["status", "--porcelain", "--", skill_name])
    if target_status.stdout.strip():
        return {"status": "blocked_dirty_target", "skill": skill_name, "details": target_status.stdout.splitlines()}

    workspace = reports_root / date / skill_name / source_id
    if workspace.exists():
        return {"status": "workspace_exists", "workspace": str(workspace)}
    old_skill = workspace / "old_skill"
    candidate_skill = workspace / "candidate_skill"
    old_skill.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(skill_root, old_skill)
    shutil.copytree(skill_root, candidate_skill)
    additional_contexts: list[dict[str, Any]] = []
    additional_evidence: list[str] = []
    for index, (source, mirror, head) in enumerate(prepared_sources):
        pathspecs = source_tracked_pathspecs(source)
        diff = git(
            mirror.local_path,
            ["diff", "--find-renames", source.accepted_commit, head, "--", *pathspecs],
            timeout=60,
        )
        if diff.returncode != 0:
            shutil.rmtree(workspace)
            return {"status": "blocked_diff_failed", "skill": skill_name, "source": source.id}
        evidence_name = "upstream.diff" if index == 0 else f"upstream-additional-{index}.diff"
        (workspace / evidence_name).write_text(diff.stdout, encoding="utf-8", newline="\n")
        if index > 0:
            additional_contexts.append(
                {
                    "source": source.id,
                    "accepted_commit": source.accepted_commit,
                    "accepted_upstream_path": source.accepted_upstream_path,
                    "upstream_path": source.upstream_path,
                    "path_migration_commit": source.path_migration_commit,
                    "current_upstream_commit": head,
                }
            )
            additional_evidence.append(evidence_name)
    primary_source, _, primary_head = prepared_sources[0]
    context = {
        "schema_version": 1,
        "skill": skill_name,
        "source": source_id,
        "accepted_commit": primary_source.accepted_commit,
        "accepted_upstream_path": primary_source.accepted_upstream_path,
        "upstream_path": primary_source.upstream_path,
        "path_migration_commit": primary_source.path_migration_commit,
        "current_upstream_commit": primary_head,
        "additional_sources": additional_contexts,
        "additional_review_evidence": additional_evidence,
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
    context = load_review_context(workspace)
    if context.get("skill") != skill_name or context.get("source") != source_id:
        raise ValueError("Review context does not match the requested skill/source.")
    sources_by_id = {record.id: record for record in skill.sources}
    validate_review_source_contexts_current(skill, mirrors, context)
    source = sources_by_id.get(source_id)
    if source is None:
        raise ValueError(f"Unknown source for {skill_name}: {source_id}")
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
    resolved_workspace = workspace.resolve()
    if len(resolved_workspace.parents) < 3:
        raise ValueError("Review workspace is not inside the expected reports hierarchy.")
    reports_root = resolved_workspace.parents[2]
    existing_candidates = current_awaiting_candidate_workspaces(
        reports_root,
        skill_name,
        skills,
        mirrors,
        exclude_workspace=resolved_workspace,
    )
    if existing_candidates:
        return {
            "status": "blocked_existing_skill_candidate",
            "skill": skill_name,
            "existing_workspaces": [str(path) for path in existing_candidates],
        }
    _, _, context = verify_review_is_current(
        skills, mirrors, skills_root, workspace, skill_name, source_id
    )
    missing = sorted(name for name in REQUIRED_REVIEW_GATES if gates.get(name) is not True)
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
    evidence_paths = {
        "benefit-assessment.md": assessment,
        "test-report.md": test_report,
        "upstream.diff": workspace / "upstream.diff",
    }
    additional_evidence = context.get("additional_review_evidence", [])
    if not isinstance(additional_evidence, list):
        raise ValueError("Review context additional_review_evidence must be a list.")
    for value in additional_evidence:
        name = str(value)
        if not is_safe_repo_path(name) or name in evidence_paths:
            raise ValueError(f"Invalid additional review evidence path: {name}")
        path = workspace / name
        if not path.is_file():
            raise ValueError(f"Additional review evidence is missing: {name}")
        evidence_paths[name] = path
    source_contexts = review_source_contexts(context)
    upstream_evidence_names = ["upstream.diff", *[str(value) for value in additional_evidence]]
    if len(upstream_evidence_names) != len(source_contexts):
        raise ValueError("Each review source must have exactly one upstream diff evidence file.")
    skill = next(record for record in skills if record.name == skill_name)
    sources_by_id = {record.id: record for record in skill.sources}
    for source_context, evidence_name in zip(source_contexts, upstream_evidence_names, strict=True):
        current_source = sources_by_id[str(source_context["source"])]
        mirror = mirrors[current_source.mirror_id]
        pathspecs = source_tracked_pathspecs(current_source)
        diff = git(
            mirror.local_path,
            [
                "diff",
                "--find-renames",
                current_source.accepted_commit,
                str(source_context["current_upstream_commit"]),
                "--",
                *pathspecs,
            ],
            timeout=60,
        )
        if diff.returncode != 0:
            return {
                "status": "blocked_diff_failed",
                "skill": skill_name,
                "source": current_source.id,
            }
        if (workspace / evidence_name).read_text(encoding="utf-8") != diff.stdout:
            return {
                "status": "blocked_upstream_evidence_mismatch",
                "skill": skill_name,
                "source": current_source.id,
                "evidence": evidence_name,
            }
    scope_hash = review_scope_hash(context)
    context.update(
        {
            "candidate_status": "awaiting_approval",
            "candidate_tree_hash": candidate_hash_value,
            "candidate_patch_sha256": patch_hash,
            "review_evidence_sha256": {
                name: file_hash(path) for name, path in evidence_paths.items()
            },
            "review_scope_sha256": scope_hash,
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
    validate_finalized_review_integrity(context, workspace)
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
        if not is_safe_repo_path(str(name)):
            raise ValueError(f"Invalid review evidence path: {name}")
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
    target_skill = skills_root / skill_name
    if tree_hash(target_skill) != candidate_hash_value:
        # Git filters may rewrite line endings in the Windows working tree.
        candidate_skill = workspace / "candidate_skill"
        target_files = {
            path.relative_to(target_skill): path
            for path in target_skill.rglob("*")
            if path.is_file()
        }
        candidate_files = {
            path.relative_to(candidate_skill): path
            for path in candidate_skill.rglob("*")
            if path.is_file()
        }
        if set(target_files) != set(candidate_files):
            raise RuntimeError("Applied file set does not match the reviewed candidate.")
        for relative_path, candidate_file in candidate_files.items():
            target_file = target_files[relative_path]
            if file_hash(target_file) != file_hash(candidate_file):
                shutil.copyfile(candidate_file, target_file)
    if tree_hash(target_skill) != candidate_hash_value:
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
            mirror_manager_error = None
            if args.command == "weekly-run":
                refresh_payload = refresh_mirrors(mirrors_registry)
                write_json(reports_root / args.date / "mirror-results.json", refresh_payload)
                mirror_results, mirror_manager_error = normalize_mirror_refresh_results(
                    refresh_payload, mirrors
                )
            payload = build_report(
                skills,
                mirrors,
                reports_root,
                args.date,
                state_path,
                mirror_results=mirror_results,
                mirror_refresh_exit_code=(
                    refresh_payload["exit_code"] if refresh_payload is not None else None
                ),
                mirror_manager_error=mirror_manager_error,
            )
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
                [(values[0], values[1]) for values in args.additional_source],
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
