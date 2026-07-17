#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare a gpt-image-2 mirror with an accepted baseline.")
    parser.add_argument("--mirror", required=True, type=Path)
    parser.add_argument("--baseline", required=True, type=Path)
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_head(mirror: Path) -> str | None:
    completed = subprocess.run(
        ["git", "-C", str(mirror), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return completed.stdout.strip() if completed.returncode == 0 else None


def collect(skill_root: Path, tracked_paths: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for raw in tracked_paths:
        target = skill_root / raw
        if target.is_file():
            result[target.relative_to(skill_root).as_posix()] = sha256(target)
        elif target.is_dir():
            for item in sorted(path for path in target.rglob("*") if path.is_file()):
                result[item.relative_to(skill_root).as_posix()] = sha256(item)
    return result


def classify(paths: list[str]) -> dict[str, list[str]]:
    buckets = {"core": [], "research_templates": [], "general_templates": [], "metadata": []}
    for path in paths:
        if path.startswith("scripts/"):
            buckets["core"].append(path)
        elif path.startswith("references/academic-figures/"):
            buckets["research_templates"].append(path)
        elif path.startswith("references/"):
            buckets["general_templates"].append(path)
        else:
            buckets["metadata"].append(path)
    return {key: value for key, value in buckets.items() if value}


def main() -> int:
    args = parse_args()
    baseline_path = args.baseline.resolve()
    mirror = args.mirror.resolve()
    if not baseline_path.is_file():
        print(json.dumps({"status": "mirror_error", "error": f"Baseline not found: {baseline_path}"}, ensure_ascii=False))
        return 2
    baseline: dict[str, Any] = json.loads(baseline_path.read_text(encoding="utf-8"))
    skill_root = mirror / baseline["upstream_skill_path"]
    if not skill_root.is_dir():
        print(json.dumps({"status": "mirror_error", "error": f"Upstream skill not found: {skill_root}"}, ensure_ascii=False))
        return 2

    current = collect(skill_root, list(baseline["tracked_paths"]))
    accepted = dict(baseline["files"])
    added = sorted(set(current) - set(accepted))
    deleted = sorted(set(accepted) - set(current))
    modified = sorted(path for path in set(current) & set(accepted) if current[path] != accepted[path])
    changed = sorted([*added, *deleted, *modified])

    manifest_path = skill_root / "manifest.json"
    current_version = None
    if manifest_path.is_file():
        current_version = json.loads(manifest_path.read_text(encoding="utf-8")).get("version")

    current_head = git_head(mirror)
    result = {
        "status": "review_required" if changed else "up_to_date",
        "source_url": baseline["source_url"],
        "baseline_repo_commit": baseline["baseline_repo_commit"],
        "current_repo_commit": current_head,
        "repo_head_changed": bool(current_head and current_head != baseline["baseline_repo_commit"]),
        "baseline_version": baseline["baseline_version"],
        "current_version": current_version,
        "added": added,
        "modified": modified,
        "deleted": deleted,
        "classification": classify(changed),
    }
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"status: {result['status']}")
        print(f"version: {result['baseline_version']} -> {result['current_version']}")
        print(f"repo: {result['baseline_repo_commit']} -> {result['current_repo_commit']}")
        for label in ("added", "modified", "deleted"):
            for path in result[label]:
                print(f"{label}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
