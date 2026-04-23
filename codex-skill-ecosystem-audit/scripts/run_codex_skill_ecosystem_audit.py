#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


LINK_PATTERN = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
ABSOLUTE_PATH_PATTERN = re.compile(
    r"(?<![A-Za-z])(?P<path>(?:[A-Za-z]:[\\/]|[A-Za-z]:/)[^`<>\r\n\t )\]]+)"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Codex-local skill ecosystem audit.")
    parser.add_argument("--date", required=True, help="Audit date in YYYY-MM-DD format.")
    parser.add_argument("--skills-root", required=True, help="Synced skill root.")
    parser.add_argument("--hygiene-reports-root", required=True, help="Report root used by skill-hygiene-audit.")
    parser.add_argument("--output-root", required=True, help="Output root for merged Codex audit reports.")
    parser.add_argument("--json", action="store_true", help="Print merged JSON to stdout.")
    return parser.parse_args()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def run_command(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def normalize_name(value: str) -> str:
    return re.sub(r"[-_\s]+", "", value.lower())


def collect_prose_paths(text: str) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()

    for raw in LINK_PATTERN.findall(text):
        cleaned = raw.split("#", 1)[0].split("?", 1)[0].strip().strip("`\"'")
        if cleaned and not cleaned.lower().startswith(("http://", "https://", "mailto:", "file://")):
            if cleaned not in seen:
                found.append(cleaned)
                seen.add(cleaned)

    for match in ABSOLUTE_PATH_PATTERN.finditer(text):
        cleaned = match.group("path").rstrip(".,;:").strip("`\"'")
        if cleaned and cleaned not in seen:
            found.append(cleaned)
            seen.add(cleaned)

    return found


def resolve_vendor_refs(skills_root: Path) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    vendor_root = (skills_root / "vendor").resolve()
    wrapper_refs: list[dict[str, str]] = []
    missing_refs: list[dict[str, str]] = []

    for skill_md in sorted((skills_root / "custom").glob("*/SKILL.md")):
        text = skill_md.read_text(encoding="utf-8")
        for target in collect_prose_paths(text):
            resolved = (skill_md.parent / target).resolve(strict=False) if not Path(target).is_absolute() else Path(target)
            try:
                relative_to_vendor = resolved.relative_to(vendor_root)
            except ValueError:
                continue

            if resolved == vendor_root:
                continue

            looks_like_skill_entry = (
                resolved.is_dir()
                or (
                    resolved.suffix.lower() == ".md"
                    and "skill" in resolved.name.lower()
                )
            )
            if not looks_like_skill_entry:
                continue

            entry = {
                "custom_skill": skill_md.parent.relative_to(skills_root).as_posix(),
                "vendor_target": Path("vendor").joinpath(relative_to_vendor).as_posix(),
            }
            if resolved.exists():
                wrapper_refs.append(entry)
            else:
                missing_refs.append(entry)

    unique_wrapper_refs = []
    seen_wrapper_refs: set[tuple[str, str]] = set()
    for item in wrapper_refs:
        key = (item["custom_skill"], item["vendor_target"])
        if key not in seen_wrapper_refs:
            unique_wrapper_refs.append(item)
            seen_wrapper_refs.add(key)

    unique_missing_refs = []
    seen_missing_refs: set[tuple[str, str]] = set()
    for item in missing_refs:
        key = (item["custom_skill"], item["vendor_target"])
        if key not in seen_missing_refs:
            unique_missing_refs.append(item)
            seen_missing_refs.add(key)

    return unique_wrapper_refs, unique_missing_refs


def find_latest_previous_summary(manifests_root: Path, current_date: str) -> Path | None:
    summaries = sorted(manifests_root.glob("*/summary.json"))
    candidates = [path for path in summaries if path.parent.name < current_date]
    return candidates[-1] if candidates else None


def pair_moved_or_renamed(
    added: list[dict[str, Any]], removed: list[dict[str, Any]]
) -> tuple[list[dict[str, str]], list[dict[str, Any]], list[dict[str, Any]]]:
    added_by_name: dict[str, list[dict[str, Any]]] = defaultdict(list)
    removed_by_name: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in added:
        added_by_name[normalize_name(item["name"] or Path(item["relative_path"]).name)].append(item)
    for item in removed:
        removed_by_name[normalize_name(item["name"] or Path(item["relative_path"]).name)].append(item)

    moved: list[dict[str, str]] = []
    matched_added: set[str] = set()
    matched_removed: set[str] = set()

    for key in sorted(set(added_by_name) & set(removed_by_name)):
        add_list = sorted(added_by_name[key], key=lambda item: item["relative_path"])
        remove_list = sorted(removed_by_name[key], key=lambda item: item["relative_path"])
        for added_item, removed_item in zip(add_list, remove_list):
            moved.append(
                {
                    "name": added_item["name"],
                    "from": removed_item["relative_path"],
                    "to": added_item["relative_path"],
                }
            )
            matched_added.add(added_item["relative_path"])
            matched_removed.add(removed_item["relative_path"])

    remaining_added = [item for item in added if item["relative_path"] not in matched_added]
    remaining_removed = [item for item in removed if item["relative_path"] not in matched_removed]
    return moved, remaining_added, remaining_removed


def compute_scope_counts(active_skills: list[dict[str, Any]]) -> dict[str, int]:
    counter = Counter(item["scope"] for item in active_skills)
    return {
        "active_total": len(active_skills),
        "custom_active_count": counter.get("custom", 0),
        "vendor_active_count": counter.get("vendor", 0),
        "root_legacy_active_count": counter.get("root", 0),
    }


def build_same_name_overlays(active_skills: list[dict[str, Any]]) -> list[dict[str, Any]]:
    custom_map: dict[str, list[str]] = defaultdict(list)
    vendor_map: dict[str, list[str]] = defaultdict(list)
    for item in active_skills:
        leaf_name = Path(item["relative_path"]).name
        if item["scope"] == "custom":
            custom_map[leaf_name].append(item["relative_path"])
        elif item["scope"] == "vendor":
            vendor_map[leaf_name].append(item["relative_path"])

    overlays = []
    for leaf_name in sorted(set(custom_map) & set(vendor_map)):
        overlays.append(
            {
                "leaf_name": leaf_name,
                "custom_skills": sorted(custom_map[leaf_name]),
                "vendor_skills": sorted(vendor_map[leaf_name]),
            }
        )
    return overlays


def build_vendor_without_wrapper(
    active_skills: list[dict[str, Any]],
    wrapper_refs: list[dict[str, str]],
    overlays: list[dict[str, Any]],
) -> list[str]:
    overlaid_leaf_names = {item["leaf_name"] for item in overlays}
    referenced_vendor_dirs: set[str] = set()

    for item in wrapper_refs:
        target = Path(item["vendor_target"])
        if target.suffix.lower() == ".md":
            referenced_vendor_dirs.add(target.parent.as_posix())
        else:
            referenced_vendor_dirs.add(target.as_posix())

    candidates: list[str] = []
    for item in active_skills:
        if item["scope"] != "vendor":
            continue
        relative_path = item["relative_path"]
        leaf_name = Path(relative_path).name
        if leaf_name in overlaid_leaf_names:
            continue
        if relative_path in referenced_vendor_dirs:
            continue
        candidates.append(relative_path)
    return sorted(candidates)


def build_diff(current_summary: dict[str, Any], previous_summary: dict[str, Any] | None) -> dict[str, Any]:
    current_active = current_summary.get("active_skills", [])
    if previous_summary is None:
        return {
            "previous_date": None,
            "previous_summary_path": None,
            "added_active_skills": sorted(current_active, key=lambda item: item["relative_path"]),
            "removed_active_skills": [],
            "moved_or_renamed_candidates": [],
        }

    previous_active = previous_summary.get("active_skills", [])
    current_by_path = {item["relative_path"]: item for item in current_active}
    previous_by_path = {item["relative_path"]: item for item in previous_active}

    added = [current_by_path[path] for path in sorted(set(current_by_path) - set(previous_by_path))]
    removed = [previous_by_path[path] for path in sorted(set(previous_by_path) - set(current_by_path))]
    moved, remaining_added, remaining_removed = pair_moved_or_renamed(added, removed)

    return {
        "previous_date": previous_summary.get("date"),
        "previous_summary_path": previous_summary.get("_summary_path"),
        "added_active_skills": sorted(remaining_added, key=lambda item: item["relative_path"]),
        "removed_active_skills": sorted(remaining_removed, key=lambda item: item["relative_path"]),
        "moved_or_renamed_candidates": moved,
    }


def build_market_section(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "global_skill_root": payload.get("global_skill_root"),
        "global_skill_roots": payload.get("global_skill_roots", []),
        "listed_global_count": payload.get("listed_global_count", 0),
        "detected_global_count": payload.get("detected_global_count", 0),
        "update_candidate_count": payload.get("update_candidate_count", 0),
        "update_candidates": payload.get("update_candidates", []),
        "repairable_empty_residual_count": payload.get("repairable_empty_residual_count", 0),
        "repairable_empty_residual": payload.get("repairable_empty_residual", []),
        "nonempty_unlisted_global_count": payload.get("nonempty_unlisted_global_count", 0),
        "nonempty_unlisted_global": payload.get("nonempty_unlisted_global", []),
        "status": payload.get("status"),
        "note": payload.get("note"),
    }


def main() -> int:
    args = parse_args()
    skills_root = Path(args.skills_root).resolve()
    hygiene_reports_root = Path(args.hygiene_reports_root).resolve()
    output_root = Path(args.output_root).resolve()
    manifests_root = hygiene_reports_root / "manifests"

    repo_root = skills_root.parent
    market_script = repo_root / "skills" / "custom" / "market-skill-updater" / "scripts" / "manage_market_skills.ps1"
    hygiene_script = repo_root / "skills" / "custom" / "skill-hygiene-audit" / "scripts" / "audit_skill_tree.py"

    market_result = run_command(
        [
            "powershell.exe",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(market_script),
            "-Mode",
            "check",
            "-Scope",
            "global",
            "-Json",
        ],
        cwd=repo_root,
    )
    if market_result.returncode != 0:
        raise SystemExit(
            f"market-skill-updater failed with code {market_result.returncode}\n{market_result.stderr or market_result.stdout}"
        )

    market_payload = json.loads(market_result.stdout)

    hygiene_result = run_command(
        [
            sys.executable,
            str(hygiene_script),
            "scan",
            "--root",
            str(skills_root),
            "--reports-root",
            str(hygiene_reports_root),
            "--date",
            args.date,
        ],
        cwd=repo_root,
    )
    if hygiene_result.returncode != 0:
        raise SystemExit(
            f"skill-hygiene-audit failed with code {hygiene_result.returncode}\n{hygiene_result.stderr or hygiene_result.stdout}"
        )

    current_summary_path = manifests_root / args.date / "summary.json"
    current_summary = load_json(current_summary_path)
    current_summary["_summary_path"] = str(current_summary_path)

    previous_summary_path = find_latest_previous_summary(manifests_root, args.date)
    previous_summary = load_json(previous_summary_path) if previous_summary_path else None
    if previous_summary is not None and previous_summary_path is not None:
        previous_summary["_summary_path"] = str(previous_summary_path)

    wrapper_refs, missing_vendor_refs = resolve_vendor_refs(skills_root)
    overlays = build_same_name_overlays(current_summary.get("active_skills", []))
    vendor_without_wrapper = build_vendor_without_wrapper(current_summary.get("active_skills", []), wrapper_refs, overlays)
    diff = build_diff(current_summary, previous_summary)

    output_payload = {
        "version": 1,
        "date": args.date,
        "sources": {
            "skills_root": str(skills_root),
            "market_check_script": str(market_script),
            "hygiene_script": str(hygiene_script),
            "hygiene_summary_path": str(current_summary_path),
            "hygiene_weekly_path": str(hygiene_reports_root / "weekly" / f"{args.date}.md"),
            "previous_hygiene_summary_path": str(previous_summary_path) if previous_summary_path else None,
        },
        "market_check": build_market_section(market_payload),
        "sync_tree": {
            **compute_scope_counts(current_summary.get("active_skills", [])),
            "archive_count": current_summary.get("counts", {}).get("archive_skills", 0),
            "total_discovered_skill_dirs": current_summary.get("counts", {}).get("total_discovered_skill_dirs", 0),
            "directory_hygiene_count": current_summary.get("counts", {}).get("directory_hygiene", 0),
            "broken_items_count": current_summary.get("counts", {}).get("broken_items", 0),
            "path_drift_count": current_summary.get("counts", {}).get("path_drift", 0),
            "duplicate_candidates_count": current_summary.get("counts", {}).get("duplicate_candidates", 0),
            "overlap_candidates_count": current_summary.get("counts", {}).get("overlap_candidates", 0),
        },
        "diff_vs_previous": diff,
        "wrapper_insights": {
            "same_name_overlays": overlays,
            "explicit_vendor_wrapper_links": wrapper_refs,
            "missing_vendor_targets": missing_vendor_refs,
            "vendor_without_local_wrapper_count": len(vendor_without_wrapper),
            "vendor_without_local_wrapper": vendor_without_wrapper,
            "vendor_entry_variants": current_summary.get("findings", {}).get("vendor_entry_variants", []),
        },
        "consistency_checks": {
            "market_list_matches_detected": (
                market_payload.get("listed_global_count") == market_payload.get("detected_global_count")
                and sorted(market_payload.get("listed_global", [])) == sorted(market_payload.get("detected_global", []))
            ),
            "repair_needed": market_payload.get("repairable_empty_residual_count", 0) > 0,
        },
    }

    output_path = output_root / "manifests" / args.date / "summary.json"
    write_json(output_path, output_payload)

    if args.json:
        json.dump(output_payload, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    else:
        print(f"summary: {output_path}")
        print(f"hygiene_summary: {current_summary_path}")
        print(f"hygiene_weekly: {hygiene_reports_root / 'weekly' / f'{args.date}.md'}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
