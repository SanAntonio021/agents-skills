#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_TRACKED_PATHS = [
    "manifest.json",
    "SKILL.md",
    "scripts/check-mode.js",
    "scripts/generate.js",
    "scripts/edit.js",
    "scripts/shared.js",
    "references/prompt-writing.md",
    "references/academic-figures",
    "references/technical-diagrams",
    "references/editing-workflows/local-object-replacement.md",
    "references/typography-and-text-layout/bilingual-layout-visual.md",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Record a reviewed gpt-image-2 upstream baseline.")
    parser.add_argument("--mirror", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--confirm-reviewed", action="store_true")
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_head(mirror: Path) -> str:
    completed = subprocess.run(
        ["git", "-C", str(mirror), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or "Unable to read mirror HEAD.")
    return completed.stdout.strip()


def collect(skill_root: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for raw in DEFAULT_TRACKED_PATHS:
        target = skill_root / raw
        if target.is_file():
            result[target.relative_to(skill_root).as_posix()] = sha256(target)
        elif target.is_dir():
            for item in sorted(path for path in target.rglob("*") if path.is_file()):
                result[item.relative_to(skill_root).as_posix()] = sha256(item)
    return result


def main() -> int:
    args = parse_args()
    if not args.confirm_reviewed:
        raise SystemExit("Refusing to update baseline without --confirm-reviewed.")
    mirror = args.mirror.resolve()
    skill_root = mirror / "skills" / "gpt-image-2"
    manifest = json.loads((skill_root / "manifest.json").read_text(encoding="utf-8"))
    payload = {
        "source_url": "https://github.com/ConardLi/garden-skills",
        "upstream_skill_path": "skills/gpt-image-2",
        "baseline_repo_commit": git_head(mirror),
        "baseline_version": manifest.get("version"),
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "tracked_paths": DEFAULT_TRACKED_PATHS,
        "files": collect(skill_root),
    }
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
