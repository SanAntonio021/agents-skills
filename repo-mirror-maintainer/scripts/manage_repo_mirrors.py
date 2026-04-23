#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tomllib
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class MirrorConfig:
    id: str
    repo_url: str
    branch: str
    local_path: Path
    git_dir_path: Path | None
    exposure_policy: str
    tracked_upstream_skills: tuple[str, ...]
    custom_wrappers: tuple[str, ...]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check or sync zero-exposure repo mirrors.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    for name in ("check", "sync"):
        sub = subparsers.add_parser(name)
        sub.add_argument(
            "--registry",
            default="<agents-root>/upstreams/repo-mirrors.toml",
            help="Path to repo-mirror registry TOML.",
        )
        sub.add_argument("--id", action="append", dest="ids", help="Mirror id to target. May be repeated.")
        sub.add_argument("--json", action="store_true", help="Emit JSON.")

    return parser.parse_args()


def apply_git_configs(args: list[str], configs: list[tuple[str, str]] | None = None) -> list[str]:
    if not configs:
        return args
    if not args or args[0] != "git":
        raise ValueError("Git config injection expects a git command.")
    command = ["git"]
    for key, value in configs:
        command.extend(["-c", f"{key}={value}"])
    command.extend(args[1:])
    return command


def run_git(
    args: list[str],
    cwd: Path | None = None,
    configs: list[tuple[str, str]] | None = None,
) -> dict[str, Any]:
    command = apply_git_configs(args, configs)
    completed = subprocess.run(
        command,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    output = "\n".join(part.strip() for part in (completed.stdout, completed.stderr) if part.strip()).strip()
    return {
        "command": " ".join(command),
        "exit_code": completed.returncode,
        "output": output,
    }


def should_retry_with_openssl(output: str) -> bool:
    lowered = output.lower()
    return "schannel" in lowered and (
        "acquirecredentialshandle failed" in lowered or "sec_e_no_credentials" in lowered
    )


def run_git_with_remote_fallback(
    args: list[str],
    cwd: Path | None = None,
    configs: list[tuple[str, str]] | None = None,
) -> dict[str, Any]:
    result = run_git(args, cwd=cwd, configs=configs)
    if result["exit_code"] == 0 or not should_retry_with_openssl(result["output"]):
        return result
    return run_git(args, cwd=cwd, configs=[*(configs or []), ("http.sslBackend", "openssl")])


def safe_directory_value(path: Path) -> str:
    try:
        return path.resolve().as_posix()
    except OSError:
        return path.as_posix()


def run_local_git(mirror: MirrorConfig, args: list[str], allow_remote_fallback: bool = False) -> dict[str, Any]:
    configs = [("safe.directory", safe_directory_value(mirror.local_path))]
    command = ["git", "-C", str(mirror.local_path), *args]
    if allow_remote_fallback:
        return run_git_with_remote_fallback(command, configs=configs)
    return run_git(command, configs=configs)


def run_remote_git(args: list[str]) -> dict[str, Any]:
    return run_git_with_remote_fallback(["git", *args])


def require_fields(raw: dict[str, Any], path: Path) -> MirrorConfig:
    required = (
        "id",
        "repo_url",
        "branch",
        "local_path",
        "exposure_policy",
        "tracked_upstream_skills",
        "custom_wrappers",
    )
    missing = [field for field in required if field not in raw]
    if missing:
        raise ValueError(f"{path}: mirror entry missing required fields: {', '.join(missing)}")

    if raw["exposure_policy"] != "zero":
        raise ValueError(f"{path}: mirror {raw['id']} must use exposure_policy='zero'")

    return MirrorConfig(
        id=str(raw["id"]),
        repo_url=str(raw["repo_url"]),
        branch=str(raw["branch"]),
        local_path=Path(str(raw["local_path"])),
        git_dir_path=Path(str(raw["git_dir_path"])) if raw.get("git_dir_path") else None,
        exposure_policy=str(raw["exposure_policy"]),
        tracked_upstream_skills=tuple(str(item) for item in raw["tracked_upstream_skills"]),
        custom_wrappers=tuple(str(item) for item in raw["custom_wrappers"]),
    )


def load_registry(path: Path) -> list[MirrorConfig]:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    entries = data.get("mirror", [])
    if not isinstance(entries, list):
        raise ValueError(f"{path}: expected [[mirror]] entries")
    return [require_fields(entry, path) for entry in entries]


def select_mirrors(mirrors: list[MirrorConfig], ids: list[str] | None) -> list[MirrorConfig]:
    if not ids:
        return mirrors
    lookup = {mirror.id: mirror for mirror in mirrors}
    missing = [mirror_id for mirror_id in ids if mirror_id not in lookup]
    if missing:
        raise ValueError(f"Unknown mirror id(s): {', '.join(missing)}")
    return [lookup[mirror_id] for mirror_id in ids]


def get_local_repo_state(mirror: MirrorConfig) -> dict[str, Any]:
    state: dict[str, Any] = {
        "local_exists": mirror.local_path.exists(),
        "local_repo_valid": False,
        "local_head": None,
        "local_branch": None,
        "local_dirty": None,
        "local_error": None,
    }
    if not state["local_exists"]:
        return state

    probe = run_local_git(mirror, ["rev-parse", "--is-inside-work-tree"])
    if probe["exit_code"] != 0:
        state["local_error"] = probe["output"] or "Local path is not a git repository."
        return state

    state["local_repo_valid"] = True
    head = run_local_git(mirror, ["rev-parse", "HEAD"])
    branch = run_local_git(mirror, ["rev-parse", "--abbrev-ref", "HEAD"])
    dirty = run_local_git(mirror, ["status", "--porcelain"])
    if head["exit_code"] == 0:
        state["local_head"] = head["output"].splitlines()[0].strip()
    if branch["exit_code"] == 0:
        state["local_branch"] = branch["output"].splitlines()[0].strip()
    state["local_dirty"] = bool(dirty["output"].strip()) if dirty["exit_code"] == 0 else None
    if head["exit_code"] != 0 and not state["local_error"]:
        state["local_error"] = head["output"]
    return state


def get_remote_head(mirror: MirrorConfig) -> dict[str, Any]:
    remote = run_remote_git(["ls-remote", mirror.repo_url, f"refs/heads/{mirror.branch}"])
    if remote["exit_code"] != 0:
        return {
            "remote_reachable": False,
            "remote_head": None,
            "remote_error": remote["output"] or "Failed to query remote HEAD.",
        }

    first_line = remote["output"].splitlines()[0].strip() if remote["output"] else ""
    remote_head = first_line.split()[0] if first_line else None
    return {
        "remote_reachable": bool(remote_head),
        "remote_head": remote_head,
        "remote_error": None if remote_head else "Remote HEAD not found.",
    }


def summarize_status(local: dict[str, Any], remote: dict[str, Any], mirror: MirrorConfig) -> str:
    if not local["local_exists"]:
        return "needs_init" if remote["remote_reachable"] else "check_failed"
    if not local["local_repo_valid"]:
        return "invalid_local_repo"
    if not remote["remote_reachable"]:
        return "remote_check_failed"
    if local["local_branch"] != mirror.branch:
        return "branch_mismatch"
    if local["local_head"] == remote["remote_head"]:
        return "up_to_date"
    return "update_available"


def check_one(mirror: MirrorConfig) -> dict[str, Any]:
    local = get_local_repo_state(mirror)
    remote = get_remote_head(mirror)
    status = summarize_status(local, remote, mirror)
    return {
        "id": mirror.id,
        "repo_url": mirror.repo_url,
        "branch": mirror.branch,
        "local_path": mirror.local_path.as_posix(),
        "git_dir_path": mirror.git_dir_path.as_posix() if mirror.git_dir_path else None,
        "exposure_policy": mirror.exposure_policy,
        "tracked_upstream_skills": list(mirror.tracked_upstream_skills),
        "custom_wrappers": list(mirror.custom_wrappers),
        "status": status,
        **local,
        **remote,
        "sync_recommended": status in {"needs_init", "branch_mismatch", "update_available"},
    }


def summarize_tracked_changes(mirror: MirrorConfig, before_head: str | None, after_head: str | None) -> tuple[list[str], str | None]:
    if not before_head or not after_head:
        return [], "initial_clone"
    if before_head == after_head:
        return [], None

    changed: list[str] = []
    for skill in mirror.tracked_upstream_skills:
        diff = run_local_git(
            mirror,
            [
                "diff",
                "--name-only",
                before_head,
                after_head,
                "--",
                f"skills/{skill}",
            ],
        )
        if diff["exit_code"] == 0 and diff["output"].strip():
            changed.append(skill)
    return changed, None


def sync_one(mirror: MirrorConfig) -> dict[str, Any]:
    before = get_local_repo_state(mirror)
    before_head = before["local_head"]

    if before["local_exists"] and not before["local_repo_valid"]:
        return {
            "id": mirror.id,
            "status": "sync_failed",
            "error": before["local_error"] or "Local path exists but is not a valid git repository.",
        }

    if before["local_exists"] and before["local_dirty"]:
        return {
            "id": mirror.id,
            "status": "sync_failed",
            "error": "Local mirror has uncommitted changes; refusing to sync.",
        }

    if not before["local_exists"]:
        mirror.local_path.parent.mkdir(parents=True, exist_ok=True)
        clone_command = [
            "git",
            "clone",
            "--branch",
            mirror.branch,
            "--single-branch",
        ]
        if mirror.git_dir_path:
            mirror.git_dir_path.parent.mkdir(parents=True, exist_ok=True)
            clone_command.extend(["--separate-git-dir", str(mirror.git_dir_path)])
        clone_command.extend([mirror.repo_url, str(mirror.local_path)])
        clone = run_git_with_remote_fallback(clone_command)
        if clone["exit_code"] != 0:
            return {
                "id": mirror.id,
                "status": "sync_failed",
                "error": clone["output"] or "git clone failed.",
            }
        action = "initialized"
    else:
        fetch = run_local_git(mirror, ["fetch", "origin", mirror.branch], allow_remote_fallback=True)
        if fetch["exit_code"] != 0:
            return {
                "id": mirror.id,
                "status": "sync_failed",
                "error": fetch["output"] or "git fetch failed.",
            }

        checkout = run_local_git(mirror, ["checkout", mirror.branch])
        if checkout["exit_code"] != 0:
            checkout = run_local_git(
                mirror,
                [
                    "checkout",
                    "-b",
                    mirror.branch,
                    "--track",
                    f"origin/{mirror.branch}",
                ],
            )
            if checkout["exit_code"] != 0:
                return {
                    "id": mirror.id,
                    "status": "sync_failed",
                    "error": checkout["output"] or f"Failed to checkout branch {mirror.branch}.",
                }

        pull = run_local_git(mirror, ["pull", "--ff-only", "origin", mirror.branch], allow_remote_fallback=True)
        if pull["exit_code"] != 0:
            return {
                "id": mirror.id,
                "status": "sync_failed",
                "error": pull["output"] or "git pull failed.",
            }
        action = "synced"

    after = check_one(mirror)
    changed_tracked_skills, tracked_change_note = summarize_tracked_changes(
        mirror,
        before_head,
        after["local_head"],
    )
    if action == "synced" and before_head == after["local_head"]:
        action = "already_up_to_date"

    return {
        **after,
        "status": action,
        "before_head": before_head,
        "after_head": after["local_head"],
        "changed_tracked_skills": changed_tracked_skills,
        "tracked_change_note": tracked_change_note,
    }


def build_summary(results: list[dict[str, Any]]) -> dict[str, int]:
    return dict(Counter(result["status"] for result in results))


def emit_text(payload: dict[str, Any]) -> None:
    print(f"Mode: {payload['mode']}")
    print(f"Registry: {payload['registry']}")
    print(f"Mirrors: {payload['mirror_count']}")
    if payload["summary"]:
        print(f"Summary: {payload['summary']}")
    for result in payload["mirrors"]:
        print("")
        print(f"[{result['id']}] {result['status']}")
        print(f"  Local path: {result.get('local_path')}")
        print(f"  Local head: {result.get('local_head')}")
        print(f"  Remote head: {result.get('remote_head')}")
        if result.get("changed_tracked_skills"):
            print(f"  Changed tracked skills: {', '.join(result['changed_tracked_skills'])}")
        if result.get("tracked_change_note"):
            print(f"  Tracked change note: {result['tracked_change_note']}")
        if result.get("error"):
            print(f"  Error: {result['error']}")
        elif result.get("remote_error"):
            print(f"  Remote error: {result['remote_error']}")


def main() -> int:
    args = parse_args()
    registry = Path(args.registry)
    mirrors = select_mirrors(load_registry(registry), args.ids)

    if args.command == "check":
        results = [check_one(mirror) for mirror in mirrors]
    else:
        results = [sync_one(mirror) for mirror in mirrors]

    payload = {
        "mode": args.command,
        "registry": registry.as_posix(),
        "mirror_count": len(results),
        "summary": build_summary(results),
        "mirrors": results,
    }

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        emit_text(payload)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # pragma: no cover - CLI guard
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False))
        raise SystemExit(1)
