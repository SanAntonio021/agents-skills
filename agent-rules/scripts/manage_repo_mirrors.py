#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import tomllib
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


DEFAULT_TIMEOUT_SECONDS = 20.0
MAX_CHECK_WORKERS = 4
TIMEOUT_EXIT_CODE = 124


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


class TrackedChangeError(RuntimeError):
    """Raised when tracked-path change extraction is incomplete."""

    def __init__(self, message: str, result: dict[str, Any]) -> None:
        super().__init__(message)
        self.result = result


def positive_timeout(value: str) -> float:
    timeout = float(value)
    if timeout <= 0:
        raise argparse.ArgumentTypeError("timeout must be greater than zero")
    return timeout


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check or sync zero-exposure repo mirrors.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    for name in ("check", "sync"):
        sub = subparsers.add_parser(name)
        sub.add_argument(
            "--registry",
            default="<agents-root>/upstream/repo-mirrors.toml",
            help="Path to repo-mirror registry TOML.",
        )
        sub.add_argument("--id", action="append", dest="ids", help="Mirror id to target. May be repeated.")
        sub.add_argument(
            "--timeout-seconds",
            "--timeout",
            type=positive_timeout,
            default=DEFAULT_TIMEOUT_SECONDS,
            help=f"Timeout for each Git command (default: {DEFAULT_TIMEOUT_SECONDS:g} seconds).",
        )
        sub.add_argument("--json", action="store_true", help="Emit JSON.")

    return parser.parse_args(argv)


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
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    command = apply_git_configs(args, configs)
    # Keep existing human/JSON command representation for compatibility.
    command_text = " ".join(command)
    try:
        with tempfile.TemporaryFile() as stdout_file, tempfile.TemporaryFile() as stderr_file:
            process = subprocess.Popen(
                command,
                cwd=str(cwd) if cwd else None,
                stdin=subprocess.DEVNULL,
                stdout=stdout_file,
                stderr=stderr_file,
                creationflags=(
                    subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0
                ),
                start_new_session=sys.platform != "win32",
            )
            try:
                exit_code = process.wait(timeout=timeout_seconds)
                timed_out = False
            except subprocess.TimeoutExpired:
                terminate_process_tree(process)
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
                exit_code = TIMEOUT_EXIT_CODE
                timed_out = True
            stdout_file.seek(0)
            stderr_file.seek(0)
            stdout = stdout_file.read().decode("utf-8", errors="replace")
            stderr = stderr_file.read().decode("utf-8", errors="replace")
    except subprocess.TimeoutExpired as exc:
        return {
            "command": command_text,
            "exit_code": TIMEOUT_EXIT_CODE,
            "output": f"Git process tree did not terminate after timeout: {exc}",
            "timed_out": True,
            "timeout_seconds": timeout_seconds,
        }
    except OSError as exc:
        return {
            "command": command_text,
            "exit_code": 1,
            "output": str(exc),
            "timed_out": False,
            "timeout_seconds": timeout_seconds,
        }
    output = "\n".join(part.strip() for part in (stdout, stderr) if part.strip()).strip()
    if timed_out:
        timeout_message = f"Git command timed out after {timeout_seconds:g} seconds."
        output = "\n".join(part for part in (output, timeout_message) if part)
    return {
        "command": command_text,
        "exit_code": exit_code,
        "output": output,
        "timed_out": timed_out,
        "timeout_seconds": timeout_seconds,
    }


def terminate_process_tree(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    if sys.platform == "win32":
        try:
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            process.kill()
        return
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except (OSError, ProcessLookupError):
        process.kill()


def should_retry_with_openssl(output: str) -> bool:
    lowered = output.lower()
    return "schannel" in lowered and (
        "acquirecredentialshandle failed" in lowered
        or "sec_e_no_credentials" in lowered
        or "failed to receive handshake" in lowered
        or "ssl/tls connection failed" in lowered
    )


def should_retry_transient_remote(output: str) -> bool:
    lowered = output.lower()
    return any(
        marker in lowered
        for marker in (
            "tls connect error",
            "unexpected eof",
            "connection reset by peer",
            "connection was reset",
            "recv failure",
        )
    )


def run_git_with_remote_fallback(
    args: list[str],
    cwd: Path | None = None,
    configs: list[tuple[str, str]] | None = None,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    allow_retries: bool = True,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    active_configs = list(configs or [])
    result = run_git(
        args,
        cwd=cwd,
        configs=active_configs,
        timeout_seconds=remaining_timeout(deadline),
    )
    if result["exit_code"] == 0 or not allow_retries:
        return result
    if should_retry_with_openssl(result["output"]):
        active_configs.append(("http.sslBackend", "openssl"))
        result = run_git(
            args,
            cwd=cwd,
            configs=active_configs,
            timeout_seconds=remaining_timeout(deadline),
        )
        if result["exit_code"] == 0:
            return result
    if should_retry_transient_remote(result["output"]):
        return run_git(
            args,
            cwd=cwd,
            configs=active_configs,
            timeout_seconds=remaining_timeout(deadline),
        )
    return result


def remaining_timeout(deadline: float) -> float:
    return max(0.001, deadline - time.monotonic())


def safe_directory_value(path: Path) -> str:
    try:
        return path.resolve().as_posix()
    except OSError:
        return path.as_posix()


def canonical_path_key(path: Path) -> str:
    return safe_directory_value(path).casefold()


def path_is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except (OSError, ValueError):
        return False
    return True


def find_named_ancestor(path: Path, name: str) -> Path | None:
    resolved = path.resolve()
    for candidate in (resolved, *resolved.parents):
        if candidate.name.casefold() == name.casefold():
            return candidate
    return None


def normalize_repo_url(value: str | None) -> str:
    if not value:
        return ""
    return value.strip().rstrip("/").removesuffix(".git").lower()


def run_local_git(
    mirror: MirrorConfig,
    args: list[str],
    allow_remote_fallback: bool = False,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    configs = [("safe.directory", safe_directory_value(mirror.local_path))]
    command = ["git", "-C", str(mirror.local_path), *args]
    if allow_remote_fallback:
        return run_git_with_remote_fallback(command, configs=configs, timeout_seconds=timeout_seconds)
    return run_git(command, configs=configs, timeout_seconds=timeout_seconds)


def run_remote_git(args: list[str], timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS) -> dict[str, Any]:
    return run_git_with_remote_fallback(["git", *args], timeout_seconds=timeout_seconds)


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
    mirrors = [require_fields(entry, path) for entry in entries]
    ids = [mirror.id for mirror in mirrors]
    if len(ids) != len(set(ids)):
        raise ValueError(f"{path}: duplicate mirror id")
    local_paths = [canonical_path_key(mirror.local_path) for mirror in mirrors]
    if len(local_paths) != len(set(local_paths)):
        raise ValueError(f"{path}: duplicate mirror local_path")
    git_dir_paths = [
        canonical_path_key(mirror.git_dir_path)
        for mirror in mirrors
        if mirror.git_dir_path is not None
    ]
    if len(git_dir_paths) != len(set(git_dir_paths)):
        raise ValueError(f"{path}: duplicate mirror git_dir_path")
    mirror_root = path.resolve().parent
    agents_root = mirror_root.parent
    sync_root = find_named_ancestor(path, "BaiduSyncdisk")
    forbidden_git_dir_roots = [
        ("source skill directory", agents_root / "skills"),
        ("Codex skill runtime", Path.home() / ".codex" / "skills"),
        ("Claude skill runtime", Path.home() / ".claude" / "skills"),
        ("CC Switch skill runtime", Path.home() / ".cc-switch" / "skills"),
        ("mirror worktree root", mirror_root),
    ]
    if sync_root is not None:
        forbidden_git_dir_roots.insert(0, ("synchronized root", sync_root))
    for mirror in mirrors:
        try:
            mirror.local_path.resolve().relative_to(mirror_root)
        except ValueError as exc:
            raise ValueError(
                f"{path}: zero-exposure mirror {mirror.id} must stay under {mirror_root}"
            ) from exc
        if mirror.git_dir_path is None:
            continue
        if not mirror.git_dir_path.is_absolute():
            raise ValueError(f"{path}: mirror {mirror.id} git_dir_path must be absolute")
        for root_name, root in forbidden_git_dir_roots:
            if path_is_within(mirror.git_dir_path, root):
                raise ValueError(
                    f"{path}: mirror {mirror.id} git_dir_path must stay outside {root_name} {root}"
                )
    return mirrors


def select_mirrors(mirrors: list[MirrorConfig], ids: list[str] | None) -> list[MirrorConfig]:
    if not ids:
        return mirrors
    lookup = {mirror.id: mirror for mirror in mirrors}
    missing = [mirror_id for mirror_id in ids if mirror_id not in lookup]
    if missing:
        raise ValueError(f"Unknown mirror id(s): {', '.join(missing)}")
    return [lookup[mirror_id] for mirror_id in ids]


def get_local_repo_state(
    mirror: MirrorConfig,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    state: dict[str, Any] = {
        "local_exists": mirror.local_path.exists(),
        "local_repo_valid": False,
        "local_head": None,
        "local_branch": None,
        "local_dirty": None,
        "local_origin": None,
        "actual_git_dir_path": None,
        "git_dir_matches_registry": None,
        "local_error": None,
    }
    if not state["local_exists"]:
        return state

    probe = run_local_git(
        mirror,
        ["rev-parse", "--is-inside-work-tree"],
        timeout_seconds=remaining_timeout(deadline),
    )
    if probe["exit_code"] != 0:
        state["local_error"] = probe["output"] or "Local path is not a git repository."
        return state

    git_dir = run_local_git(
        mirror,
        ["rev-parse", "--absolute-git-dir"],
        timeout_seconds=remaining_timeout(deadline),
    )
    if git_dir["exit_code"] != 0 or not git_dir["output"].strip():
        state["local_error"] = git_dir["output"] or "Unable to resolve the local Git metadata directory."
        return state

    actual_git_dir = Path(git_dir["output"].splitlines()[0].strip())
    state["local_repo_valid"] = True
    state["actual_git_dir_path"] = safe_directory_value(actual_git_dir)
    if mirror.git_dir_path is not None:
        matches_registry = canonical_path_key(actual_git_dir) == canonical_path_key(mirror.git_dir_path)
        state["git_dir_matches_registry"] = matches_registry
        if not matches_registry:
            state["local_error"] = (
                "Actual Git metadata directory does not match git_dir_path: "
                f"expected {safe_directory_value(mirror.git_dir_path)}, "
                f"actual {state['actual_git_dir_path']}."
            )
    head = run_local_git(mirror, ["rev-parse", "HEAD"], timeout_seconds=remaining_timeout(deadline))
    branch = run_local_git(
        mirror,
        ["rev-parse", "--abbrev-ref", "HEAD"],
        timeout_seconds=remaining_timeout(deadline),
    )
    dirty = run_local_git(mirror, ["status", "--porcelain"], timeout_seconds=remaining_timeout(deadline))
    origin = run_local_git(
        mirror,
        ["remote", "get-url", "origin"],
        timeout_seconds=remaining_timeout(deadline),
    )
    if head["exit_code"] == 0:
        state["local_head"] = head["output"].splitlines()[0].strip()
    if branch["exit_code"] == 0:
        state["local_branch"] = branch["output"].splitlines()[0].strip()
    state["local_dirty"] = bool(dirty["output"].strip()) if dirty["exit_code"] == 0 else None
    if origin["exit_code"] == 0:
        state["local_origin"] = origin["output"].splitlines()[0].strip()
    if head["exit_code"] != 0 and not state["local_error"]:
        state["local_error"] = head["output"]
    return state


def get_remote_head(
    mirror: MirrorConfig,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    remote = run_remote_git(
        ["ls-remote", mirror.repo_url, f"refs/heads/{mirror.branch}"],
        timeout_seconds=timeout_seconds,
    )
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
        if mirror.git_dir_path is None:
            return "blocked_missing_git_dir"
        return "needs_init" if remote["remote_reachable"] else "check_failed"
    if not local["local_repo_valid"]:
        return "invalid_local_repo"
    if local.get("git_dir_matches_registry") is False:
        return "git_dir_mismatch"
    if local["local_dirty"]:
        return "dirty_mirror"
    if normalize_repo_url(local.get("local_origin")) != normalize_repo_url(mirror.repo_url):
        return "origin_mismatch"
    if local["local_branch"] != mirror.branch:
        return "branch_mismatch"
    if not remote["remote_reachable"]:
        return "remote_check_failed"
    if local["local_head"] == remote["remote_head"]:
        return "up_to_date"
    return "update_available"


def check_one(
    mirror: MirrorConfig,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    local = get_local_repo_state(mirror, timeout_seconds=remaining_timeout(deadline))
    if not local["local_exists"] and mirror.git_dir_path is None:
        remote = {
            "remote_reachable": None,
            "remote_head": None,
            "remote_error": "Remote check skipped until git_dir_path is configured.",
        }
    else:
        remote = get_remote_head(mirror, timeout_seconds=remaining_timeout(deadline))
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
        "sync_recommended": status in {"needs_init", "update_available"},
    }


def summarize_tracked_changes(
    mirror: MirrorConfig,
    before_head: str | None,
    after_head: str | None,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> tuple[list[str], str | None]:
    deadline = time.monotonic() + timeout_seconds
    if not before_head or not after_head:
        return [], "initial_clone"
    if before_head == after_head:
        return [], None

    changed: list[str] = []
    for skill in mirror.tracked_upstream_skills:
        direct_path = mirror.local_path / skill
        legacy_path = mirror.local_path / "skills" / skill
        if skill == "." or direct_path.exists() or "/" in skill or "\\" in skill:
            tracked_path = skill
        elif legacy_path.exists():
            tracked_path = f"skills/{skill}"
        else:
            tracked_path = f"skills/{skill}"
        diff = run_local_git(
            mirror,
            [
                "diff",
                "--name-only",
                before_head,
                after_head,
                "--",
                tracked_path,
            ],
            timeout_seconds=remaining_timeout(deadline),
        )
        if diff["exit_code"] != 0:
            failure_kind = "timed out" if diff.get("timed_out") else "failed"
            detail = diff["output"].strip() or f"exit code {diff['exit_code']}"
            raise TrackedChangeError(
                f"Tracked path diff {failure_kind} for {skill!r} ({tracked_path!r}): {detail}",
                diff,
            )
        if diff["output"].strip():
            changed.append(skill)
    return changed, None


def sync_failure(
    mirror: MirrorConfig,
    local: dict[str, Any],
    error: str,
    status: str = "sync_failed",
    git_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    failure_details = {}
    if git_result is not None:
        failure_details = {
            "failed_command": git_result.get("command"),
            "failed_exit_code": git_result.get("exit_code"),
            "timed_out": bool(git_result.get("timed_out", False)),
            "timeout_seconds": git_result.get("timeout_seconds"),
        }
    return {
        "id": mirror.id,
        "repo_url": mirror.repo_url,
        "branch": mirror.branch,
        "local_path": mirror.local_path.as_posix(),
        "git_dir_path": mirror.git_dir_path.as_posix() if mirror.git_dir_path else None,
        "exposure_policy": mirror.exposure_policy,
        "tracked_upstream_skills": list(mirror.tracked_upstream_skills),
        "custom_wrappers": list(mirror.custom_wrappers),
        **local,
        **failure_details,
        "status": status,
        "error": error,
    }


def sync_one(
    mirror: MirrorConfig,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    before = get_local_repo_state(mirror, timeout_seconds=remaining_timeout(deadline))
    before_head = before["local_head"]
    tracked_head: str | None = None

    if before["local_exists"] and before.get("git_dir_matches_registry") is False:
        return sync_failure(
            mirror,
            before,
            before["local_error"] or "Actual Git metadata directory does not match git_dir_path.",
            status="git_dir_mismatch",
        )

    if before["local_exists"] and not before["local_repo_valid"]:
        return sync_failure(
            mirror,
            before,
            before["local_error"] or "Local path exists but is not a valid git repository.",
        )

    if before["local_exists"] and before["local_dirty"]:
        return sync_failure(mirror, before, "Local mirror has uncommitted changes; refusing to sync.")

    if before["local_exists"] and normalize_repo_url(before.get("local_origin")) != normalize_repo_url(mirror.repo_url):
        return sync_failure(
            mirror,
            before,
            "Local mirror origin does not match the registry; refusing to sync.",
        )

    if before["local_exists"] and before["local_branch"] != mirror.branch:
        return sync_failure(
            mirror,
            before,
            "Local mirror branch does not match the registry; refusing to sync.",
        )

    if not before["local_exists"]:
        if mirror.git_dir_path is None:
            return sync_failure(
                mirror,
                before,
                "Local mirror is missing and git_dir_path is not configured; refusing to create "
                ".git metadata inside the synchronized mirror worktree.",
                status="blocked_missing_git_dir",
            )
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
        clone = run_git_with_remote_fallback(
            clone_command,
            timeout_seconds=remaining_timeout(deadline),
            allow_retries=False,
        )
        if clone["exit_code"] != 0:
            return sync_failure(
                mirror,
                before,
                clone["output"] or "git clone failed.",
                git_result=clone,
            )
        action = "initialized"
    else:
        fetch = run_local_git(
            mirror,
            ["fetch", "origin", mirror.branch],
            allow_remote_fallback=True,
            timeout_seconds=remaining_timeout(deadline),
        )
        if fetch["exit_code"] != 0:
            return sync_failure(
                mirror,
                before,
                fetch["output"] or "git fetch failed.",
                git_result=fetch,
            )
        tracking = run_local_git(
            mirror,
            ["rev-parse", f"refs/remotes/origin/{mirror.branch}"],
            timeout_seconds=remaining_timeout(deadline),
        )
        if tracking["exit_code"] != 0:
            return sync_failure(
                mirror,
                before,
                tracking["output"] or "Fetched branch cannot be resolved locally.",
                git_result=tracking,
            )
        tracked_head = tracking["output"].splitlines()[0].strip()
        if before_head == tracked_head:
            action = "already_up_to_date"
        else:
            fast_forward = run_local_git(
                mirror,
                ["merge-base", "--is-ancestor", str(before_head), tracked_head],
                timeout_seconds=remaining_timeout(deadline),
            )
            if fast_forward["exit_code"] != 0:
                error = "Fetched branch is not a fast-forward of the local mirror."
                if fast_forward["exit_code"] != 1 and fast_forward["output"]:
                    error = f"Unable to verify fast-forward safety: {fast_forward['output']}"
                return sync_failure(mirror, before, error)
            merge = run_local_git(
                mirror,
                ["merge", "--ff-only", f"refs/remotes/origin/{mirror.branch}"],
                timeout_seconds=remaining_timeout(deadline),
            )
            if merge["exit_code"] != 0:
                return sync_failure(
                    mirror,
                    before,
                    merge["output"] or "Local fast-forward merge failed.",
                )
            action = "synced"

    after_local = get_local_repo_state(mirror, timeout_seconds=remaining_timeout(deadline))
    if tracked_head is None:
        tracking = run_local_git(
            mirror,
            ["rev-parse", f"refs/remotes/origin/{mirror.branch}"],
            timeout_seconds=remaining_timeout(deadline),
        )
        tracked_head = tracking["output"].splitlines()[0].strip() if tracking["exit_code"] == 0 else None
    if (
        not after_local["local_repo_valid"]
        or after_local.get("git_dir_matches_registry") is False
        or after_local["local_dirty"]
        or after_local["local_branch"] != mirror.branch
        or normalize_repo_url(after_local.get("local_origin")) != normalize_repo_url(mirror.repo_url)
        or not tracked_head
        or after_local["local_head"] != tracked_head
    ):
        post_status = (
            "git_dir_mismatch"
            if after_local.get("git_dir_matches_registry") is False
            else "sync_failed"
        )
        return sync_failure(
            mirror,
            after_local,
            after_local.get("local_error") or "Post-sync local mirror health check failed.",
            status=post_status,
        )
    after = {
        "id": mirror.id,
        "repo_url": mirror.repo_url,
        "branch": mirror.branch,
        "local_path": mirror.local_path.as_posix(),
        "git_dir_path": mirror.git_dir_path.as_posix() if mirror.git_dir_path else None,
        "exposure_policy": mirror.exposure_policy,
        "tracked_upstream_skills": list(mirror.tracked_upstream_skills),
        "custom_wrappers": list(mirror.custom_wrappers),
        **after_local,
        "remote_reachable": True,
        "remote_head": tracked_head,
        "remote_error": None,
        "sync_recommended": False,
    }
    try:
        changed_tracked_skills, tracked_change_note = summarize_tracked_changes(
            mirror,
            before_head,
            after["local_head"],
            timeout_seconds=remaining_timeout(deadline),
        )
    except TrackedChangeError as exc:
        return {
            **after,
            "status": "tracked_diff_failed",
            "before_head": before_head,
            "after_head": after["local_head"],
            "changed_tracked_skills": [],
            "tracked_change_note": None,
            "failed_command": exc.result.get("command"),
            "failed_exit_code": exc.result.get("exit_code"),
            "timed_out": bool(exc.result.get("timed_out", False)),
            "timeout_seconds": exc.result.get("timeout_seconds"),
            "error": str(exc),
        }
    return {
        **after,
        "status": action,
        "before_head": before_head,
        "after_head": after["local_head"],
        "changed_tracked_skills": changed_tracked_skills,
        "tracked_change_note": tracked_change_note,
    }


MirrorOperation = Callable[[MirrorConfig, float], dict[str, Any]]


def run_one_isolated(
    mirror: MirrorConfig,
    operation: MirrorOperation,
    mode: str,
    timeout_seconds: float,
) -> dict[str, Any]:
    try:
        return operation(mirror, timeout_seconds)
    except Exception as exc:
        return {
            "id": mirror.id,
            "repo_url": mirror.repo_url,
            "branch": mirror.branch,
            "local_path": mirror.local_path.as_posix(),
            "status": f"{mode}_failed",
            "error": f"{type(exc).__name__}: {exc}",
        }


def process_mirrors(
    mirrors: list[MirrorConfig],
    mode: str,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> list[dict[str, Any]]:
    if not mirrors:
        return []

    if mode in {"check", "sync"}:
        worker_count = min(MAX_CHECK_WORKERS, len(mirrors))
        operation = check_one if mode == "check" else sync_one
        with ThreadPoolExecutor(max_workers=worker_count, thread_name_prefix=f"mirror-{mode}") as executor:
            futures = [
                executor.submit(run_one_isolated, mirror, operation, mode, timeout_seconds)
                for mirror in mirrors
            ]
            return [future.result() for future in futures]

    raise ValueError(f"Unsupported mode: {mode}")


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


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    registry = Path(args.registry)
    mirrors = select_mirrors(load_registry(registry), args.ids)
    results = process_mirrors(mirrors, args.command, timeout_seconds=args.timeout_seconds)

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
    if args.command == "sync":
        success_statuses = {"initialized", "synced", "already_up_to_date"}
    else:
        success_statuses = {"up_to_date", "update_available", "needs_init"}
    return 0 if all(result.get("status") in success_statuses for result in results) else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # pragma: no cover - CLI guard
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False))
        raise SystemExit(1)
