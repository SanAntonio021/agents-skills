#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Codex-local skill ecosystem audit.")
    parser.add_argument("--date", required=True, help="Audit date in YYYY-MM-DD format.")
    parser.add_argument("--skills-root", required=True, help="Skill root to scan.")
    parser.add_argument("--hygiene-reports-root", required=True, help="Report root used by skill-check.")
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
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


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
        added_by_name[normalize_name(item.get("name") or Path(item["relative_path"]).name)].append(item)
    for item in removed:
        removed_by_name[normalize_name(item.get("name") or Path(item["relative_path"]).name)].append(item)

    moved: list[dict[str, str]] = []
    matched_added: set[str] = set()
    matched_removed: set[str] = set()

    for key in sorted(set(added_by_name) & set(removed_by_name)):
        add_list = sorted(added_by_name[key], key=lambda item: item["relative_path"])
        remove_list = sorted(removed_by_name[key], key=lambda item: item["relative_path"])
        for added_item, removed_item in zip(add_list, remove_list):
            moved.append(
                {
                    "name": added_item.get("name") or Path(added_item["relative_path"]).name,
                    "from": removed_item["relative_path"],
                    "to": added_item["relative_path"],
                }
            )
            matched_added.add(added_item["relative_path"])
            matched_removed.add(removed_item["relative_path"])

    remaining_added = [item for item in added if item["relative_path"] not in matched_added]
    remaining_removed = [item for item in removed if item["relative_path"] not in matched_removed]
    return moved, remaining_added, remaining_removed


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


def build_skill_tree_section(summary: dict[str, Any]) -> dict[str, Any]:
    counts = summary.get("counts", {})
    return {
        "directory_rule": summary.get("directory_rule"),
        "active_total": counts.get("active_skills", len(summary.get("active_skills", []))),
        "discovered_skill_dirs": counts.get("discovered_skill_dirs", 0),
        "serious_problem_count": counts.get("serious_problem_count", 0),
        "directory_structure_problem_count": counts.get("directory_structure_problems", 0),
        "duplicate_candidate_count": counts.get("duplicate_candidates", 0),
        "name_mismatch_count": counts.get("name_mismatch", 0),
        "overlap_candidate_count": counts.get("overlap_candidates", 0),
        "link_or_path_issue_count": counts.get("link_or_path_issues", 0),
        "broken_item_count": counts.get("broken_items", 0),
        "active_skills": summary.get("active_skills", []),
        "findings": summary.get("findings", {}),
    }


def main() -> int:
    args = parse_args()
    skills_root = Path(args.skills_root).resolve()
    hygiene_reports_root = Path(args.hygiene_reports_root).resolve()
    output_root = Path(args.output_root).resolve()
    manifests_root = hygiene_reports_root / "manifests"

    script_dir = Path(__file__).resolve().parent
    skill_root = script_dir.parent
    repo_root = skill_root.parent
    market_script = script_dir / "manage_market_skills.ps1"
    hygiene_script = script_dir / "audit_skill_tree.py"

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
            f"skill-check failed with code {hygiene_result.returncode}\n{hygiene_result.stderr or hygiene_result.stdout}"
        )

    current_summary_path = manifests_root / args.date / "summary.json"
    current_summary = load_json(current_summary_path)
    current_summary["_summary_path"] = str(current_summary_path)

    previous_summary_path = find_latest_previous_summary(manifests_root, args.date)
    previous_summary = load_json(previous_summary_path) if previous_summary_path else None
    if previous_summary is not None and previous_summary_path is not None:
        previous_summary["_summary_path"] = str(previous_summary_path)

    output_payload = {
        "version": "flat-skill-ecosystem-v1",
        "date": args.date,
        "sources": {
            "skills_root": str(skills_root),
            "market_check_script": str(market_script),
            "skill_tree_script": str(hygiene_script),
            "skill_tree_summary_path": str(current_summary_path),
            "skill_tree_weekly_path": str(hygiene_reports_root / "weekly" / f"{args.date}.md"),
            "previous_skill_tree_summary_path": str(previous_summary_path) if previous_summary_path else None,
        },
        "market_check": build_market_section(market_payload),
        "skill_tree": build_skill_tree_section(current_summary),
        "diff_vs_previous": build_diff(current_summary, previous_summary),
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
        print(f"skill_tree_summary: {current_summary_path}")
        print(f"skill_tree_weekly: {hygiene_reports_root / 'weekly' / f'{args.date}.md'}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
