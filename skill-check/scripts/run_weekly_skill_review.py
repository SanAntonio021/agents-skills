#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable
from zoneinfo import ZoneInfo

try:  # Windows
    import msvcrt
except ImportError:  # pragma: no cover
    msvcrt = None

try:  # POSIX test environments
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None


SCHEMA_VERSION = 1
UNSEEN_STREAK_THRESHOLD = 4
ROUTINE_QUEUE_LIMIT = 3
MAX_DECISION_SUMMARY = 600
MAX_COMMAND_DETAIL = 1200
LOCK_TIMEOUT_SECONDS = 5.0
GIT_COMMAND_TIMEOUT_SECONDS = 30.0
SHA40_PATTERN = re.compile(r"^[0-9a-f]{40}$")
NULL_FINGERPRINT_VALUES = {"", "none", "null"}
ATOMIC_REPLACE_DELAYS = (0.0, 0.05, 0.1, 0.2, 0.4)

PENDING_STATUSES = {
    "queued",
    "awaiting_decision",
    "facts",
    "revising",
    "retry_pending",
}
ACTIVE_BATCH_STATUSES = {"awaiting_confirmation", "ready"}
INVALIDATABLE_BATCH_STATUSES = {
    *ACTIVE_BATCH_STATUSES,
    "partial_failed",
    "partial_blocked",
    "blocked",
}
TERMINAL_FINDING_STATUSES = {
    "closed",
    "completed",
    "execution_declined",
    "rejected",
    "resolved",
    "waiting_evidence",
}

SCRIPT_PATH = Path(__file__).resolve()
SKILL_ROOT = SCRIPT_PATH.parent.parent
DEFAULT_SKILLS_ROOT = SKILL_ROOT.parent
DEFAULT_AGENTS_ROOT = DEFAULT_SKILLS_ROOT.parent
DEFAULT_REPORTS_ROOT = DEFAULT_AGENTS_ROOT / "reports" / "skill-upstream"
DEFAULT_STATE_PATH = DEFAULT_REPORTS_ROOT / "weekly-review-state.json"
DEFAULT_SYNC_HELPER = (
    DEFAULT_AGENTS_ROOT
    / "automation"
    / "ccswitch-skill-sync"
    / "Invoke-CcSwitchSkillSync.ps1"
)


class StateError(RuntimeError):
    pass


class LockConflict(StateError):
    pass


def now_iso() -> str:
    return datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds")


def today_local() -> str:
    return datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()


def compact_text(value: Any, limit: int = MAX_DECISION_SUMMARY) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)].rstrip() + "..."


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def fingerprint(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stable_slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug[:48] or "item"


def stable_finding_id(kind: str, subject: str, purpose: str) -> str:
    suffix = fingerprint([kind, subject, purpose])[:12]
    return f"{stable_slug(kind)}:{stable_slug(subject)}:{suffix}"


def normalize_targets(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    for raw in values:
        raw_value = str(raw or "").replace("\\", "/").strip()
        if (
            not raw_value
            or raw_value.startswith("/")
            or re.match(r"^[a-zA-Z]:", raw_value)
        ):
            continue
        value = raw_value.strip(" /")
        if not value or value.startswith(".") or ".." in Path(value).parts:
            continue
        if value not in result:
            result.append(value)
    return result


def target_skill_name(path_value: str) -> str:
    normalized = str(path_value or "").replace("\\", "/").strip("/")
    return normalized.split("/", 1)[0] if normalized else ""


def tree_fingerprint(path: Path) -> str:
    if not path.exists():
        return fingerprint({"status": "missing", "path": path.name})
    if path.is_file():
        return fingerprint({"type": "file", "name": path.name, "sha256": file_sha256(path)})
    rows: list[dict[str, str]] = []
    for child in sorted(path.rglob("*"), key=lambda item: item.as_posix().lower()):
        if not child.is_file():
            continue
        relative = child.relative_to(path)
        if any(part in {".git", "__pycache__"} for part in relative.parts):
            continue
        try:
            child_fingerprint = file_sha256(child)
        except OSError as exc:
            child_fingerprint = f"read-error:{exc.__class__.__name__}"
        rows.append({"path": relative.as_posix(), "sha256": child_fingerprint})
    return fingerprint(rows)


def source_fingerprint(skills_root: Path, targets: Iterable[str]) -> str:
    normalized = normalize_targets(targets)
    rows = []
    for target in normalized:
        candidate = (skills_root / target).resolve()
        try:
            candidate.relative_to(skills_root.resolve())
        except ValueError:
            rows.append({"target": target, "fingerprint": "outside-skills-root"})
            continue
        rows.append({"target": target, "fingerprint": tree_fingerprint(candidate)})
    return fingerprint(rows)


def outside_root_targets(skills_root: Path, targets: Iterable[str]) -> list[str]:
    root = skills_root.resolve()
    outside = []
    for target in normalize_targets(targets):
        try:
            (root / target).resolve().relative_to(root)
        except (OSError, ValueError):
            outside.append(target)
    return outside


def run_retry_git(
    repository: Path, *arguments: str
) -> tuple[subprocess.CompletedProcess[str] | None, str | None]:
    try:
        completed = subprocess.run(
            ["git", "-C", str(repository), *arguments],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=GIT_COMMAND_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return None, compact_text(f"git command failed: {exc}")
    return completed, None


def verified_retry_source_fingerprint(
    skills_root: Path, finding: dict[str, Any]
) -> tuple[str | None, str | None]:
    proposed = finding.get("proposal") or {}
    targets = normalize_targets(proposed.get("targets", []))
    if not targets:
        return None, "retry proposal has no valid source targets"
    outside = outside_root_targets(skills_root, targets)
    if outside:
        return None, f"retry targets resolve outside the skills root: {', '.join(outside)}"

    current = source_fingerprint(skills_root, targets)
    if current == finding.get("source_fingerprint"):
        return current, None

    execution = finding.get("execution") or {}
    execution_commit = str(execution.get("commit") or "").lower()
    remote_sha = str(execution.get("remote_sha") or "").lower()
    if execution.get("outcome") != "failed":
        return None, "retry source changed without a failed execution record"
    if not SHA40_PATTERN.fullmatch(execution_commit):
        return None, "failed execution does not record a full source commit"
    if not SHA40_PATTERN.fullmatch(remote_sha):
        return None, "failed execution does not record a full pushed remote SHA"

    top_level, error = run_retry_git(skills_root, "rev-parse", "--show-toplevel")
    if error or top_level is None or top_level.returncode != 0:
        return None, error or "unable to resolve the skills Git root"
    try:
        resolved_top_level = Path(top_level.stdout.strip()).resolve()
    except OSError as exc:
        return None, compact_text(f"unable to resolve the skills Git root: {exc}")
    if resolved_top_level != skills_root.resolve():
        return None, "retry source is not the authoritative skills Git root"

    head_result, error = run_retry_git(skills_root, "rev-parse", "HEAD")
    if error or head_result is None or head_result.returncode != 0:
        return None, error or "unable to resolve the current skills HEAD"
    head = head_result.stdout.strip().lower()
    if not SHA40_PATTERN.fullmatch(head):
        return None, "current skills HEAD is not a full commit SHA"

    for commit in (execution_commit, remote_sha):
        exists, error = run_retry_git(skills_root, "cat-file", "-e", f"{commit}^{{commit}}")
        if error or exists is None or exists.returncode != 0:
            return None, error or f"recorded retry commit is unavailable: {commit}"

    for ancestor, descendant, label in (
        (execution_commit, remote_sha, "source commit is not contained in the recorded remote SHA"),
        (remote_sha, head, "recorded remote SHA is not an ancestor of current HEAD"),
    ):
        ancestry, error = run_retry_git(
            skills_root, "merge-base", "--is-ancestor", ancestor, descendant
        )
        if error or ancestry is None:
            return None, error or label
        if ancestry.returncode == 1:
            return None, label
        if ancestry.returncode != 0:
            return None, f"unable to verify retry commit ancestry: {label}"

    changed, error = run_retry_git(
        skills_root,
        "diff-tree",
        "--root",
        "--no-commit-id",
        "--name-only",
        "-r",
        execution_commit,
        "--",
        *targets,
    )
    if error or changed is None or changed.returncode != 0:
        return None, error or "unable to inspect the failed execution commit"
    changed_paths = [
        line.strip().replace("\\", "/")
        for line in changed.stdout.splitlines()
        if line.strip()
    ]
    for target in targets:
        prefix = target.rstrip("/") + "/"
        if not any(path == target or path.startswith(prefix) for path in changed_paths):
            return None, f"failed execution commit did not change retry target: {target}"

    dirty, error = run_retry_git(
        skills_root, "status", "--porcelain=v1", "--untracked-files=all", "--", *targets
    )
    if error or dirty is None or dirty.returncode != 0:
        return None, error or "unable to inspect retry target cleanliness"
    if dirty.stdout.strip():
        return None, "retry targets contain uncommitted or untracked changes"

    unchanged, error = run_retry_git(
        skills_root, "diff", "--quiet", execution_commit, head, "--", *targets
    )
    if error or unchanged is None:
        return None, error or "unable to compare retry targets with the failed execution commit"
    if unchanged.returncode == 1:
        return None, "retry targets changed after the failed execution commit"
    if unchanged.returncode != 0:
        return None, "unable to compare retry targets with the failed execution commit"
    return current, None


def relative_report_ref(path: Path, reports_root: Path) -> str:
    try:
        return path.resolve().relative_to(reports_root.resolve()).as_posix()
    except ValueError:
        return path.name


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        replace_error: OSError | None = None
        for delay in ATOMIC_REPLACE_DELAYS:
            if delay:
                time.sleep(delay)
            try:
                os.replace(temporary_path, path)
                replace_error = None
                break
            except OSError as exc:
                replace_error = exc
        if replace_error is not None:
            raise replace_error
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def atomic_write_json(path: Path, payload: Any) -> None:
    atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


class StateLock:
    def __init__(self, state_path: Path, timeout: float = LOCK_TIMEOUT_SECONDS) -> None:
        self.path = Path(f"{state_path}.lock")
        self.timeout = timeout
        self.handle: Any = None

    def __enter__(self) -> "StateLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = self.path.open("a+b")
        self.handle.seek(0, os.SEEK_END)
        if self.handle.tell() == 0:
            self.handle.write(b"0")
            self.handle.flush()
        deadline = time.monotonic() + self.timeout
        while True:
            try:
                self.handle.seek(0)
                if os.name == "nt" and msvcrt is not None:
                    msvcrt.locking(self.handle.fileno(), msvcrt.LK_NBLCK, 1)
                elif fcntl is not None:  # pragma: no cover - exercised on CI
                    fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                else:  # pragma: no cover
                    raise RuntimeError("No cross-process file lock implementation is available")
                return self
            except (OSError, RuntimeError) as exc:
                if time.monotonic() >= deadline:
                    self.handle.close()
                    self.handle = None
                    raise LockConflict(f"state lock is busy: {self.path}") from exc
                time.sleep(0.05)

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        if self.handle is None:
            return
        try:
            self.handle.seek(0)
            if os.name == "nt" and msvcrt is not None:
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_UNLCK, 1)
            elif fcntl is not None:  # pragma: no cover
                fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
        finally:
            self.handle.close()
            self.handle = None


def new_state() -> dict[str, Any]:
    timestamp = now_iso()
    return {
        "schema_version": SCHEMA_VERSION,
        "created_at": timestamp,
        "updated_at": timestamp,
        "scope_fingerprint": None,
        "unseen_streaks": {},
        "findings": {},
        "queue": [],
        "batches": [],
        "runs": [],
    }


def validate_state(state: Any) -> dict[str, Any]:
    if not isinstance(state, dict):
        raise StateError("state root must be an object")
    if state.get("schema_version") != SCHEMA_VERSION:
        raise StateError(
            f"unsupported state schema_version: {state.get('schema_version')!r}; expected {SCHEMA_VERSION}"
        )
    required_types = {
        "unseen_streaks": dict,
        "findings": dict,
        "queue": list,
        "batches": list,
        "runs": list,
    }
    for key, expected_type in required_types.items():
        if not isinstance(state.get(key), expected_type):
            raise StateError(f"state field {key!r} must be {expected_type.__name__}")
    for finding_id, finding in state["findings"].items():
        if not isinstance(finding_id, str) or not isinstance(finding, dict):
            raise StateError("state findings must map string IDs to objects")
        if finding.get("id") != finding_id:
            raise StateError(f"finding {finding_id!r} has a mismatched id")
        required_finding_fields = (
            "source",
            "severity",
            "title",
            "evidence_summary",
            "evidence_fingerprint",
            "proposal_fingerprint",
            "source_fingerprint",
            "status",
        )
        if any(field not in finding for field in required_finding_fields):
            raise StateError(f"finding {finding_id!r} is missing required fields")
        if any(
            not isinstance(finding.get(field), str)
            for field in required_finding_fields
            if field != "proposal_fingerprint"
        ):
            raise StateError(f"finding {finding_id!r} has invalid field types")
        if finding.get("proposal_fingerprint") is not None and not isinstance(
            finding.get("proposal_fingerprint"), str
        ):
            raise StateError(f"finding {finding_id!r} has an invalid proposal fingerprint")
    for finding_id in state["queue"]:
        if not isinstance(finding_id, str):
            raise StateError("state queue entries must be finding IDs")
        if finding_id not in state["findings"]:
            raise StateError(f"state queue references unknown finding {finding_id!r}")
    batch_ids: set[str] = set()
    for batch in state["batches"]:
        if not isinstance(batch, dict) or not isinstance(batch.get("id"), str):
            raise StateError("state batches must contain string IDs")
        if batch["id"] in batch_ids:
            raise StateError(f"duplicate batch id: {batch['id']}")
        batch_ids.add(batch["id"])
        if not isinstance(batch.get("status"), str) or not isinstance(batch.get("items"), list):
            raise StateError(f"batch {batch['id']!r} has invalid status or items")
        if any(
            not isinstance(item, dict) or not isinstance(item.get("finding_id"), str)
            for item in batch["items"]
        ):
            raise StateError(f"batch {batch['id']!r} has an invalid item")
    if any(not isinstance(run, dict) for run in state["runs"]):
        raise StateError("state runs must contain objects")
    return state


def load_state(state_path: Path) -> tuple[dict[str, Any], bool]:
    if not state_path.exists():
        return new_state(), True
    try:
        raw = state_path.read_text(encoding="utf-8")
        parsed = json.loads(raw)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise StateError(f"state file could not be read without loss: {exc}") from exc
    return validate_state(parsed), False


def save_state(state_path: Path, state: dict[str, Any]) -> None:
    validate_state(state)
    state["updated_at"] = now_iso()
    atomic_write_json(state_path, state)


def fatal_payload(kind: str, detail: str, state_path: Path) -> dict[str, Any]:
    finding_id = stable_finding_id("weekly_review_state", state_path.name, kind)
    return {
        "status": "blocked",
        "fatal_finding": {
            "id": finding_id,
            "severity": "critical",
            "title": "周检状态不可安全更新",
            "detail": compact_text(detail),
            "suggested_action": "保留原状态文件，修复格式或解除锁冲突后重试；不要自动重建。",
        },
    }


def proposal(
    action: str,
    summary: str,
    targets: Iterable[str],
    *,
    skills: Iterable[str] = (),
    dependencies: Iterable[str] = (),
    requires_runtime_sync: bool = True,
    candidate_workspace: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "action": compact_text(action, 120),
        "summary": compact_text(summary, 1000),
        "targets": normalize_targets(targets),
        "skills": sorted(set(normalize_targets(skills))),
        "dependencies": sorted(set(str(value) for value in dependencies if value)),
        "requires_runtime_sync": bool(requires_runtime_sync),
    }
    if candidate_workspace:
        payload["candidate_workspace"] = compact_text(candidate_workspace, 500)
    return payload


def make_observation(
    *,
    kind: str,
    source: str,
    subject: str,
    purpose: str,
    severity: str,
    title: str,
    evidence_summary: str,
    evidence: Any,
    suggested_proposal: dict[str, Any] | None,
    report_refs: Iterable[str],
    queueable: bool = True,
    needs_facts: bool = False,
    fact_questions: Iterable[str] = (),
    skills_root: Path,
) -> dict[str, Any]:
    finding_id = stable_finding_id(kind, subject, purpose)
    proposed = copy.deepcopy(suggested_proposal)
    targets = proposed.get("targets", []) if proposed else []
    return {
        "id": finding_id,
        "kind": kind,
        "source": source,
        "subject": compact_text(subject, 300),
        "purpose": compact_text(purpose, 300),
        "severity": severity,
        "title": compact_text(title, 300),
        "evidence_summary": compact_text(evidence_summary, 1000),
        "evidence_fingerprint": fingerprint(evidence),
        "proposal": proposed,
        "proposal_fingerprint": fingerprint(proposed) if proposed else None,
        "source_fingerprint": source_fingerprint(skills_root, targets),
        "report_refs": sorted(set(str(value) for value in report_refs if value)),
        "queueable": queueable,
        "needs_facts": needs_facts,
        "fact_questions": [compact_text(value, 500) for value in fact_questions if value][:2],
    }


def load_json_file(path: Path) -> tuple[Any | None, str | None]:
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except FileNotFoundError:
        return None, "missing"
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return None, f"invalid: {exc.__class__.__name__}: {exc}"


def summary_is_valid(payload: Any, audit: str, date: str) -> tuple[bool, str | None]:
    if not isinstance(payload, dict):
        return False, "summary root is not an object"
    expected_versions: dict[str, Any] = {
        "upstream": 1,
        "hygiene": "flat-skill-tree-v1",
        "usage": "skill-usage-audit-v1",
    }
    key = "schema_version" if audit == "upstream" else "version"
    if payload.get(key) != expected_versions[audit]:
        return False, f"unexpected {key}: {payload.get(key)!r}"
    if payload.get("date") != date:
        return False, f"summary date {payload.get('date')!r} does not match {date!r}"
    if audit == "hygiene" and not isinstance(payload.get("findings"), dict):
        return False, "hygiene summary has no findings object"
    if audit == "usage" and not isinstance(payload.get("classifications"), dict):
        return False, "usage summary has no classifications object"
    if audit == "upstream" and not isinstance(payload.get("sources"), list):
        return False, "upstream summary has no sources list"
    if audit == "upstream":
        for field in (
            "candidate_conflicts",
            "registry_coverage_gaps",
            "unreferenced_mirror_failures",
        ):
            if field in payload and not isinstance(payload[field], list):
                return False, f"upstream summary field {field!r} is not a list"
    if audit == "hygiene":
        for field, value in payload["findings"].items():
            if field != "no_action_notes" and not isinstance(value, list):
                return False, f"hygiene finding category {field!r} is not a list"
    if audit == "usage":
        if not isinstance(payload.get("warnings"), dict):
            return False, "usage summary has no warnings object"
        if not isinstance(payload.get("skill_inventory"), list):
            return False, "usage summary has no skill_inventory list"
        for field, value in payload["classifications"].items():
            if not isinstance(value, list):
                return False, f"usage classification {field!r} is not a list"
    return True, None


def run_process(name: str, command: list[str], cwd: Path, summary_path: Path) -> dict[str, Any]:
    before = file_sha256(summary_path) if summary_path.is_file() else None
    environment = os.environ.copy()
    environment["PYTHONUTF8"] = "1"
    environment["PYTHONIOENCODING"] = "utf-8"
    started = time.monotonic()
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            env=environment,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=1800,
            check=False,
        )
        exit_code: int | None = completed.returncode
        stdout = compact_text(completed.stdout, MAX_COMMAND_DETAIL)
        stderr = compact_text(completed.stderr, MAX_COMMAND_DETAIL)
        error = None
    except (OSError, subprocess.TimeoutExpired) as exc:
        exit_code = None
        stdout = ""
        stderr = ""
        error = compact_text(f"{exc.__class__.__name__}: {exc}", MAX_COMMAND_DETAIL)
    after = file_sha256(summary_path) if summary_path.is_file() else None
    return {
        "name": name,
        "exit_code": exit_code,
        "duration_seconds": round(time.monotonic() - started, 3),
        "summary_exists": summary_path.is_file(),
        "summary_changed": before != after,
        "stdout": stdout,
        "stderr": stderr,
        "error": error,
    }


def run_audits(
    *,
    agents_root: Path,
    skills_root: Path,
    reports_root: Path,
    date: str,
    reuse_reports: bool,
) -> tuple[dict[str, Any], dict[str, Path]]:
    paths = {
        "upstream": reports_root / date / "summary.json",
        "hygiene": reports_root / "manifests" / date / "summary.json",
        "usage": reports_root / "usage" / "manifests" / date / "summary.json",
    }
    if reuse_reports:
        return {
            name: {
                "name": name,
                "exit_code": None,
                "duration_seconds": 0.0,
                "summary_exists": path.is_file(),
                "summary_changed": False,
                "stdout": "",
                "stderr": "",
                "error": None,
                "reused": True,
            }
            for name, path in paths.items()
        }, paths

    python = sys.executable
    commands = {
        "upstream": [
            python,
            str(skills_root / "agent-rules" / "scripts" / "skill_upstream_maintenance.py"),
            "weekly-run",
            "--registry",
            str(agents_root / "upstream" / "skill-sources.toml"),
            "--mirrors-registry",
            str(agents_root / "upstream" / "repo-mirrors.toml"),
            "--skills-root",
            str(skills_root),
            "--reports-root",
            str(reports_root),
            "--date",
            date,
            "--json",
        ],
        "hygiene": [
            python,
            str(skills_root / "skill-check" / "scripts" / "audit_skill_tree.py"),
            "scan",
            "--root",
            str(skills_root),
            "--reports-root",
            str(reports_root),
            "--date",
            date,
            "--json",
        ],
        "usage": [
            python,
            str(skills_root / "skill-check" / "scripts" / "audit_skill_usage.py"),
            "--reports-root",
            str(reports_root),
            "--date",
            date,
            "--hygiene-summary",
            str(paths["hygiene"]),
            "--json",
        ],
    }
    results: dict[str, Any] = {}
    for name in ("upstream", "hygiene", "usage"):
        results[name] = run_process(name, commands[name], agents_root, paths[name])
    return results, paths


def scan_failure_observation(
    audit: str,
    detail: str,
    report_ref: str,
    skills_root: Path,
) -> dict[str, Any]:
    target = "agent-rules" if audit == "upstream" else "skill-check"
    return make_observation(
        kind="scan_failure",
        source=audit,
        subject=audit,
        purpose="restore-complete-weekly-scan",
        severity="critical",
        title=f"{audit} 周检结果不完整",
        evidence_summary=detail,
        evidence={"audit": audit, "detail": detail},
        suggested_proposal=proposal(
            "修复周检入口",
            f"修复 {audit} 扫描或报告格式，并以同一范围重新运行完整周检。",
            [target],
            skills=[target],
            requires_runtime_sync=True,
        ),
        report_refs=[report_ref],
        skills_root=skills_root,
    )


def extract_upstream_observations(
    summary: dict[str, Any], report_ref: str, skills_root: Path
) -> list[dict[str, Any]]:
    observations: list[dict[str, Any]] = []
    benign_statuses = {
        "already_reviewed",
        "no_relevant_change",
        "provenance_only",
        "up_to_date",
    }
    for conflict in summary.get("candidate_conflicts", []):
        if not isinstance(conflict, dict):
            continue
        skill = str(conflict.get("skill") or "unknown-skill")
        observations.append(
            make_observation(
                kind="upstream_candidate_conflict",
                source="upstream",
                subject=skill,
                purpose="resolve-candidate-conflict",
                severity="critical",
                title=f"{skill} 的隔离候选发生冲突",
                evidence_summary=compact_text(conflict),
                evidence=conflict,
                suggested_proposal=proposal(
                    "重建技能级候选",
                    f"保留正式技能不变，从同一源码快照重新合成 {skill} 的全部上游候选并复测。",
                    [skill],
                    skills=[skill],
                ),
                report_refs=[report_ref],
                skills_root=skills_root,
            )
        )

    for gap in summary.get("registry_coverage_gaps", []):
        gap_text = compact_text(gap)
        subject = str(gap.get("skill") if isinstance(gap, dict) else gap_text)
        observations.append(
            make_observation(
                kind="upstream_registry_gap",
                source="upstream",
                subject=subject or "registry",
                purpose="repair-source-coverage",
                severity="high",
                title="上游来源登记存在覆盖缺口",
                evidence_summary=gap_text,
                evidence=gap,
                suggested_proposal=proposal(
                    "补齐来源登记",
                    "核对缺口技能的真实来源状态；确认后只补机器可读登记和生成页，不自动认定新上游。",
                    ["agent-rules"],
                    skills=["agent-rules"],
                ),
                report_refs=[report_ref],
                needs_facts=True,
                fact_questions=[
                    f"`{subject}` 是否确实需要纳入上游来源登记？",
                    "如果需要，已确认的仓库、仓内路径和许可证证据是什么？",
                ],
                skills_root=skills_root,
            )
        )

    rows = list(summary.get("sources", [])) + list(summary.get("unreferenced_mirror_failures", []))
    for row in rows:
        if not isinstance(row, dict):
            continue
        status = str(row.get("status") or "unknown")
        skill = str(row.get("skill") or row.get("mirror") or "unregistered-mirror")
        source_id = str(row.get("source") or row.get("mirror") or "unknown-source")
        subject = f"{skill}:{source_id}"
        if status in benign_statuses:
            continue
        if status == "review_required":
            observations.append(
                make_observation(
                    kind="upstream_review_required",
                    source="upstream",
                    subject=subject,
                    purpose="prepare-isolated-candidate",
                    severity="medium",
                    title=f"{skill} 的上游变化需要隔离评估",
                    evidence_summary=compact_text(row.get("changed") or row),
                    evidence={
                        "status": status,
                        "current_commit": row.get("current_commit"),
                        "changed": row.get("changed", []),
                    },
                    suggested_proposal=proposal(
                        "准备隔离候选",
                        f"在报告目录中评估 {skill} 的上游变化；只有收益、测试、许可证和风险门全部通过后才进入用户批准队列。",
                        [skill],
                        skills=[skill],
                    ),
                    report_refs=[report_ref],
                    queueable=False,
                    skills_root=skills_root,
                )
            )
            continue
        if status == "awaiting_approval":
            workspace = str(row.get("review_workspace") or "")
            observations.append(
                make_observation(
                    kind="upstream_candidate",
                    source="upstream",
                    subject=subject,
                    purpose="apply-reviewed-upstream-candidate",
                    severity="high",
                    title=f"{skill} 有已评估的上游修改候选",
                    evidence_summary=(
                        f"候选已通过收益、测试、许可证和风险门；上游提交 "
                        f"{row.get('current_commit') or 'unknown'}。"
                    ),
                    evidence={
                        "status": status,
                        "current_commit": row.get("current_commit"),
                        "workspace": workspace,
                        "source_count": row.get("review_source_count"),
                    },
                    suggested_proposal=proposal(
                        "应用已审核候选",
                        f"应用 {skill} 的技能级隔离候选，完成复测、接受基线更新、精确提交、推送和双端运行时同步。",
                        [skill],
                        skills=[skill],
                        candidate_workspace=workspace,
                    ),
                    report_refs=[report_ref, workspace] if workspace else [report_ref],
                    skills_root=skills_root,
                )
            )
            continue

        diagnostic = row.get("error") or row.get("original_error") or row.get("mirror_details") or row
        approval_scope = row.get("approval_scope") or row.get("approval_required")
        observations.append(
            make_observation(
                kind="upstream_diagnostic",
                source="upstream",
                subject=subject,
                purpose=f"repair-{status}",
                severity="critical" if status in {"mirror_blocked", "mirror_manager_failed"} else "high",
                title=f"{skill} 上游检查异常：{status}",
                evidence_summary=compact_text(diagnostic),
                evidence={
                    "status": status,
                    "current_commit": row.get("current_commit"),
                    "error": diagnostic,
                    "impact": row.get("impact"),
                    "approval_scope": approval_scope,
                },
                suggested_proposal=proposal(
                    "修复上游检查异常",
                    compact_text(
                        row.get("repair_steps")
                        or row.get("next_steps")
                        or row.get("suggested_action")
                        or f"按报告中的隔离边界修复 {subject}，随后重跑周检。",
                        1000,
                    ),
                    ["agent-rules"],
                    skills=["agent-rules"],
                    requires_runtime_sync=True,
                ),
                report_refs=[report_ref],
                skills_root=skills_root,
            )
        )
    return observations


def hygiene_targets(item: dict[str, Any]) -> list[str]:
    values = []
    for key in ("path", "left", "right"):
        if item.get(key):
            skill = target_skill_name(str(item[key]))
            if skill:
                values.append(skill)
    return normalize_targets(values)


def extract_hygiene_observations(
    summary: dict[str, Any], report_ref: str, skills_root: Path
) -> list[dict[str, Any]]:
    observations: list[dict[str, Any]] = []
    findings = summary.get("findings", {})
    category_names = (
        "directory_structure_problems",
        "duplicate_candidates",
        "name_mismatch",
        "overlap_candidates",
        "link_or_path_issues",
        "broken_items",
    )
    for category in category_names:
        for item in findings.get(category, []):
            if not isinstance(item, dict):
                continue
            targets = hygiene_targets(item) or ["skill-check"]
            subject = "+".join(targets)
            kind = str(item.get("kind") or category)
            serious = item.get("severity") == "严重问题"
            needs_facts = kind in {
                "directory_structure",
                "duplicate_candidate",
                "missing_skill_md",
                "overlap_candidate",
            }
            title = str(item.get("title") or item.get("detail") or category)
            detail = str(item.get("detail") or title)
            action = str(item.get("suggested_action") or "人工复核")
            if kind in {"duplicate_candidate", "overlap_candidate"}:
                fact_questions = [
                    f"`{targets[0]}` 与 `{targets[-1]}` 的目标、输入、输出和执行方式是否实际相同？",
                    "是否存在仍需保留的旧入口、兼容名称或不同触发场景？",
                ]
            elif needs_facts:
                fact_questions = [
                    f"`{item.get('path') or subject}` 是正式技能、工作材料还是历史副本？",
                    "是否有其他任务或运行时仍依赖这个位置或名称？",
                ]
            else:
                fact_questions = []
            observations.append(
                make_observation(
                    kind=f"hygiene_{kind}",
                    source="hygiene",
                    subject=subject,
                    purpose=f"{action}:{kind}",
                    severity="critical" if serious else "medium",
                    title=title,
                    evidence_summary=detail,
                    evidence={key: item.get(key) for key in sorted(item)},
                    suggested_proposal=proposal(
                        action,
                        f"{action}：{detail}",
                        targets,
                        skills=targets,
                    ),
                    report_refs=[report_ref],
                    needs_facts=needs_facts,
                    fact_questions=fact_questions,
                    skills_root=skills_root,
                )
            )
    return observations


def usage_evidence_complete(summary: dict[str, Any]) -> tuple[bool, list[str]]:
    warnings = summary.get("warnings", {})
    reasons: list[str] = []
    if warnings.get("missing_roots"):
        reasons.append("missing roots")
    if warnings.get("parse_error_count"):
        reasons.append("parse errors")
    if warnings.get("missing_field_count"):
        reasons.append("missing target fields")
    if warnings.get("hygiene_summary_warning"):
        reasons.append("invalid hygiene summary")
    return not reasons, reasons


def evidence_scope_fingerprint(
    upstream: dict[str, Any], hygiene: dict[str, Any], usage: dict[str, Any]
) -> str:
    source_ids = sorted(
        (str(row.get("skill")), str(row.get("source")))
        for row in upstream.get("sources", [])
        if isinstance(row, dict)
    )
    inventory = sorted(
        str(row.get("skill"))
        for row in usage.get("skill_inventory", [])
        if isinstance(row, dict)
    )
    return fingerprint(
        {
            "upstream_sources": source_ids,
            "hygiene_root": hygiene.get("root"),
            "hygiene_version": hygiene.get("version"),
            "usage_configuration": usage.get("configuration"),
            "usage_inventory": inventory,
        }
    )


def update_unseen_streaks(
    state: dict[str, Any],
    usage: dict[str, Any] | None,
    *,
    complete: bool,
    scope_value: str | None,
    date: str,
) -> tuple[dict[str, int], str | None]:
    streaks = state["unseen_streaks"]
    previous_scope = state.get("scope_fingerprint")
    if not complete or not usage or not scope_value:
        for entry in streaks.values():
            if isinstance(entry, dict):
                entry["count"] = 0
                entry["last_reset_date"] = date
        return {}, "incomplete_scan"
    if previous_scope and previous_scope != scope_value:
        for entry in streaks.values():
            if isinstance(entry, dict):
                entry["count"] = 0
                entry["last_reset_date"] = date
                entry["last_counted_date"] = date
        for item in usage.get("classifications", {}).get("历史内未见使用", []):
            if not isinstance(item, dict) or not item.get("skill"):
                continue
            entry = streaks.setdefault(str(item["skill"]), {"count": 0})
            entry["count"] = 0
            entry["last_reset_date"] = date
            entry["last_counted_date"] = date
        state["scope_fingerprint"] = scope_value
        return {}, "scope_changed"

    state["scope_fingerprint"] = scope_value
    used = {
        str(item.get("skill"))
        for item in usage.get("classifications", {}).get("已用", [])
        if isinstance(item, dict)
    }
    unseen = {
        str(item.get("skill"))
        for item in usage.get("classifications", {}).get("历史内未见使用", [])
        if isinstance(item, dict)
    }
    for skill in used:
        entry = streaks.setdefault(skill, {"count": 0})
        entry["count"] = 0
        entry["last_used_date"] = date
        entry["last_counted_date"] = date
    counts: dict[str, int] = {}
    for skill in unseen:
        entry = streaks.setdefault(skill, {"count": 0})
        if entry.get("last_counted_date") != date:
            entry["count"] = int(entry.get("count", 0)) + 1
            entry["last_counted_date"] = date
        counts[skill] = int(entry.get("count", 0))
    for skill, entry in streaks.items():
        if skill not in used and skill not in unseen and isinstance(entry, dict):
            entry["count"] = 0
            entry["last_reset_date"] = date
    return counts, None


def extract_usage_observations(
    summary: dict[str, Any],
    report_ref: str,
    skills_root: Path,
    unseen_counts: dict[str, int],
) -> list[dict[str, Any]]:
    observations: list[dict[str, Any]] = []
    classifications = summary.get("classifications", {})

    grouped_candidates: dict[str, list[dict[str, Any]]] = {}
    for item in classifications.get("疑似漏用", []):
        if isinstance(item, dict) and item.get("skill"):
            grouped_candidates.setdefault(str(item["skill"]), []).append(item)
    for skill, items in sorted(grouped_candidates.items()):
        evidence_rows = [
            {
                "host": item.get("host"),
                "source": item.get("source"),
                "matched_terms": item.get("matched_terms"),
                "score": item.get("score"),
            }
            for item in items[:5]
        ]
        observations.append(
            make_observation(
                kind="suspected_missed_use",
                source="usage",
                subject=skill,
                purpose="repair-trigger-boundary",
                severity="medium",
                title=f"{skill} 可能存在漏触发",
                evidence_summary=f"发现 {len(items)} 条确定性规则候选；候选不是实际漏触发结论。",
                evidence=evidence_rows,
                suggested_proposal=proposal(
                    "补触发边界",
                    f"若真实使用习惯确认需要自动触发，则收紧或补充 {skill} 的 description，并补正反触发测试。",
                    [skill],
                    skills=[skill],
                ),
                report_refs=[report_ref],
                needs_facts=True,
                fact_questions=[
                    f"这些请求是否确实应该自动触发 `{skill}`，而不是由普通能力直接处理？",
                    f"你通常希望自动触发 `{skill}`，还是只在显式点名时使用？",
                ],
                skills_root=skills_root,
            )
        )

    for item in classifications.get("可能冗余", []):
        if not isinstance(item, dict) or not item.get("skill"):
            continue
        skill = str(item["skill"])
        related = [str(value) for value in item.get("related_skills", [])]
        targets = [skill, *related]
        observations.append(
            make_observation(
                kind="possible_redundancy",
                source="usage",
                subject="+".join(targets),
                purpose="review-redundancy",
                severity="medium",
                title=f"{skill} 进入可能冗余人工复核候选",
                evidence_summary=str(item.get("reason") or "历史内未见使用并与目录重叠发现相交。"),
                evidence=item,
                suggested_proposal=proposal(
                    "人工复核",
                    f"比较 {', '.join(targets)} 的目标、输入、输出和触发场景；只有实际高度重合时才形成合并或归档方案。",
                    targets,
                    skills=targets,
                ),
                report_refs=[report_ref],
                needs_facts=True,
                fact_questions=[
                    f"`{skill}` 与 {', '.join(related) or '相关技能'} 在你的实际工作里是否承担相同产物？",
                    f"`{skill}` 是否仍有独立入口、兼容需求或只点名调用的场景？",
                ],
                skills_root=skills_root,
            )
        )

    for skill, count in sorted(unseen_counts.items()):
        if count < UNSEEN_STREAK_THRESHOLD:
            continue
        observations.append(
            make_observation(
                kind="unseen_four_complete_weeks",
                source="usage",
                subject=skill,
                purpose="review-unused-skill",
                severity="medium",
                title=f"{skill} 连续 {count} 次完整周检未见使用证据",
                evidence_summary="未见记录不等于实际未使用；需结合你的真实调用方式判断。",
                evidence={"skill": skill, "complete_week_streak": count},
                suggested_proposal=proposal(
                    "人工复核",
                    f"复核 {skill} 的保留、自动触发或点名调用边界；不因未见使用证据自动删除、归档或降级。",
                    [skill],
                    skills=[skill],
                ),
                report_refs=[report_ref],
                needs_facts=True,
                fact_questions=[
                    f"你目前是否还会在 Codex 或 Claude 中使用 `{skill}`？",
                    f"如果会，通常是显式点名 `{skill}`，还是希望它根据任务描述自动触发？",
                ],
                skills_root=skills_root,
            )
        )
    return observations


def invalidate_batches_for_finding(
    state: dict[str, Any], finding_id: str, reason: str, *, changed_finding: bool = True
) -> list[str]:
    invalidated: list[str] = []
    for batch in state["batches"]:
        if batch.get("status") not in INVALIDATABLE_BATCH_STATUSES:
            continue
        if finding_id not in {item.get("finding_id") for item in batch.get("items", [])}:
            continue
        batch["status"] = "stale"
        batch["stale_reason"] = compact_text(reason)
        batch["stale_at"] = now_iso()
        invalidated.append(str(batch.get("id")))
        for item in batch.get("items", []):
            other_id = item.get("finding_id")
            if other_id == finding_id and changed_finding:
                continue
            other = state["findings"].get(other_id)
            if other and other.get("status") == "execution_pending":
                other["status"] = "approved"
    return invalidated


def advance_retry_source_baseline(
    state: dict[str, Any],
    finding: dict[str, Any],
    skills_root: Path,
    *,
    event: str,
    timestamp: str,
) -> tuple[dict[str, Any] | None, str | None]:
    current, error = verified_retry_source_fingerprint(skills_root, finding)
    if error or current is None:
        return None, error or "retry source baseline could not be verified"
    previous = finding.get("source_fingerprint")
    invalidated: list[str] = []
    changed = current != previous
    if changed:
        invalidated = invalidate_batches_for_finding(
            state,
            finding["id"],
            "verified retry source baseline advanced to the recorded execution commit",
        )
        finding["source_fingerprint"] = current
        finding.setdefault("history", []).append(
            {
                "event": event,
                "previous_source_fingerprint": previous,
                "source_fingerprint": current,
                "execution_commit": finding.get("execution", {}).get("commit"),
                "recorded_at": timestamp,
            }
        )
    return {
        "changed": changed,
        "source_fingerprint": current,
        "invalidated_batches": invalidated,
    }, None


def recover_legacy_retry_source_baselines(
    state: dict[str, Any], skills_root: Path
) -> list[str]:
    recovered: list[str] = []
    for finding in state["findings"].values():
        if finding.get("status") != "waiting_evidence":
            continue
        if finding.get("execution", {}).get("outcome") != "failed":
            continue
        if finding.get("decision", {}).get("value") != "approved":
            continue
        has_blocked_retry = any(
            batch.get("status") == "blocked"
            and any(
                item.get("finding_id") == finding.get("id")
                and item.get("status") == "blocked_drift"
                for item in batch.get("items", [])
            )
            for batch in state["batches"]
        )
        if not has_blocked_retry:
            continue
        result, error = advance_retry_source_baseline(
            state,
            finding,
            skills_root,
            event="legacy_retry_source_baseline_recovered",
            timestamp=now_iso(),
        )
        if error or not result or not result["changed"]:
            continue
        finding["status"] = "approved"
        finding["decision"]["source_fingerprint"] = result["source_fingerprint"]
        remove_from_queue(state, finding["id"])
        recovered.append(finding["id"])
    return recovered


def finding_changed(previous: dict[str, Any], observation: dict[str, Any]) -> bool:
    return (
        previous.get("evidence_fingerprint") != observation.get("evidence_fingerprint")
        or previous.get("proposal_fingerprint") != observation.get("proposal_fingerprint")
        or previous.get("source_fingerprint") != observation.get("source_fingerprint")
    )


def merge_observations(
    state: dict[str, Any],
    observations: list[dict[str, Any]],
    date: str,
    *,
    authoritative_sources: set[str] | None = None,
) -> dict[str, Any]:
    if authoritative_sources is None:
        authoritative_sources = {"upstream", "hygiene", "usage"}
    findings = state["findings"]
    queue = [finding_id for finding_id in state["queue"] if finding_id in findings]
    seen_ids: set[str] = set()
    new_critical: list[str] = []
    new_high: list[str] = []
    routine_candidates: list[str] = []
    routine_requeues: list[str] = []
    invalidated: list[str] = []

    for observation in observations:
        finding_id = observation["id"]
        seen_ids.add(finding_id)
        previous = findings.get(finding_id)
        changed = False
        previous_status = previous.get("status") if previous else None
        if previous is None:
            current = copy.deepcopy(observation)
            current.update(
                {
                    "first_seen": date,
                    "last_seen": date,
                    "status": "observed" if not observation["queueable"] else "deferred",
                    "facts": [],
                    "history": [],
                }
            )
            findings[finding_id] = current
            if not observation["queueable"]:
                continue
        else:
            changed = finding_changed(previous, observation)
            previous_fingerprints = {
                "evidence_fingerprint": previous.get("evidence_fingerprint"),
                "proposal_fingerprint": previous.get("proposal_fingerprint"),
                "source_fingerprint": previous.get("source_fingerprint"),
            }
            preserved = {
                key: copy.deepcopy(previous.get(key))
                for key in (
                    "decision",
                    "execution",
                    "facts",
                    "first_seen",
                    "history",
                    "pending_revision",
                    "requested_adjustment",
                    "status",
                )
                if key in previous
            }
            previous.update(copy.deepcopy(observation))
            previous.update(preserved)
            previous["last_seen"] = date
            current = previous
            if changed:
                current.setdefault("history", []).append(
                    {
                        "event": "fingerprint_changed",
                        "date": date,
                        "previous": previous_fingerprints,
                    }
                )
                invalidated.extend(
                    invalidate_batches_for_finding(
                        state,
                        finding_id,
                        "finding evidence, proposal, or source baseline changed",
                    )
                )
                current.pop("decision", None)
                current.pop("execution", None)
                current.pop("pending_revision", None)
                current.pop("requested_adjustment", None)
                current["facts"] = []
                current["status"] = "deferred" if current["queueable"] else "observed"

        if not current["queueable"]:
            current["status"] = "observed"
            continue
        if current.get("status") in {"deferred", "queued"}:
            if current["severity"] == "critical":
                new_critical.append(finding_id)
            elif current["severity"] == "high":
                new_high.append(finding_id)
            elif current.get("status") == "deferred":
                if changed and previous_status not in {None, "deferred", "observed"}:
                    routine_requeues.append(finding_id)
                else:
                    routine_candidates.append(finding_id)

    for finding_id, finding in findings.items():
        if finding_id in seen_ids:
            continue
        if finding.get("source") not in authoritative_sources:
            continue
        if finding.get("status") in {"execution_failed", "retry_pending", "completed"}:
            continue
        if finding.get("status") not in TERMINAL_FINDING_STATUSES and finding.get("status") != "observed":
            invalidate_batches_for_finding(state, finding_id, "finding no longer appears in the latest scan")
            finding["status"] = "resolved"
            finding["resolved_date"] = date

    queue = [
        finding_id
        for finding_id in queue
        if findings.get(finding_id, {}).get("status") in PENDING_STATUSES
    ]
    for finding_id in reversed(new_critical):
        if finding_id not in queue:
            queue.insert(0, finding_id)
        findings[finding_id]["status"] = "queued"
    for finding_id in new_high:
        if finding_id not in queue:
            queue.append(finding_id)
        findings[finding_id]["status"] = "queued"

    for finding_id in sorted(set(routine_requeues)):
        if finding_id not in queue:
            queue.append(finding_id)
        findings[finding_id]["status"] = "queued"

    admitted_this_week = sum(
        1
        for finding in findings.values()
        if finding.get("routine_admitted_date") == date
    )
    added_routine: list[str] = []
    for finding_id in sorted(set(routine_candidates)):
        if admitted_this_week + len(added_routine) >= ROUTINE_QUEUE_LIMIT:
            findings[finding_id]["status"] = "deferred"
            continue
        if finding_id not in queue:
            queue.append(finding_id)
        findings[finding_id]["status"] = "queued"
        findings[finding_id]["routine_admitted_date"] = date
        added_routine.append(finding_id)
    state["queue"] = queue
    return {
        "observed": len(observations),
        "queued_critical": len(new_critical),
        "queued_high": len(new_high),
        "queued_routine": len(added_routine),
        "requeued_routine": len(set(routine_requeues)),
        "deferred_routine": max(0, len(set(routine_candidates)) - len(added_routine)),
        "invalidated_batches": sorted(set(invalidated)),
    }


def build_scan_report(
    *,
    date: str,
    command_results: dict[str, Any],
    validation: dict[str, Any],
    complete: bool,
    completeness_reasons: list[str],
    scope_value: str | None,
    streak_reset_reason: str | None,
    observations: list[dict[str, Any]],
    merge_result: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "date": date,
        "generated_at": now_iso(),
        "complete": complete,
        "completeness_reasons": completeness_reasons,
        "scope_fingerprint": scope_value,
        "streak_reset_reason": streak_reset_reason,
        "commands": command_results,
        "validation": validation,
        "observations": observations,
        "merge": merge_result,
    }


def scan_command(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    agents_root = args.agents_root.resolve()
    skills_root = args.skills_root.resolve()
    reports_root = args.reports_root.resolve()
    state_path = args.state.resolve()
    command_results, summary_paths = run_audits(
        agents_root=agents_root,
        skills_root=skills_root,
        reports_root=reports_root,
        date=args.date,
        reuse_reports=args.reuse_reports,
    )
    summaries: dict[str, dict[str, Any] | None] = {}
    validation: dict[str, Any] = {}
    observations: list[dict[str, Any]] = []
    completeness_reasons: list[str] = []

    for audit in ("upstream", "hygiene", "usage"):
        payload, read_error = load_json_file(summary_paths[audit])
        valid, validation_error = summary_is_valid(payload, audit, args.date)
        if not args.reuse_reports:
            result = command_results[audit]
            exit_code = result.get("exit_code")
            upstream_partial = (
                audit == "upstream"
                and exit_code == 2
                and bool(result.get("summary_changed"))
            )
            if exit_code != 0 and not upstream_partial:
                valid = False
                validation_error = (
                    f"command exited with {exit_code!r}"
                    if result.get("summary_changed")
                    else "command failed and did not refresh its summary"
                )
        error = read_error or validation_error
        result = command_results[audit]
        command_detail = result.get("error") or result.get("stderr")
        if not command_detail and result.get("exit_code") not in {None, 0}:
            command_detail = result.get("stdout")
        if not valid and command_detail:
            error = compact_text(f"{error}; command detail: {command_detail}", 1000)
        validation[audit] = {
            "valid": valid,
            "error": error,
            "command_detail": compact_text(command_detail, 1000) if command_detail else None,
            "report_ref": relative_report_ref(summary_paths[audit], reports_root),
        }
        if not valid:
            completeness_reasons.append(f"{audit}: {error}")
            observations.append(
                scan_failure_observation(
                    audit,
                    f"{audit} report is incomplete: {error}",
                    validation[audit]["report_ref"],
                    skills_root,
                )
            )
            summaries[audit] = None
        else:
            summaries[audit] = payload

    if summaries["upstream"]:
        observations.extend(
            extract_upstream_observations(
                summaries["upstream"], validation["upstream"]["report_ref"], skills_root
            )
        )
    if summaries["hygiene"]:
        observations.extend(
            extract_hygiene_observations(
                summaries["hygiene"], validation["hygiene"]["report_ref"], skills_root
            )
        )

    usage_complete = False
    usage_reasons: list[str] = []
    if summaries["usage"]:
        usage_complete, usage_reasons = usage_evidence_complete(summaries["usage"])
        completeness_reasons.extend(f"usage: {reason}" for reason in usage_reasons)
    complete = all(summaries.values()) and usage_complete
    scope_value = None
    if all(summaries.values()):
        scope_value = evidence_scope_fingerprint(
            summaries["upstream"], summaries["hygiene"], summaries["usage"]
        )

    report_path = reports_root / args.date / "weekly-review.json"
    try:
        with StateLock(state_path, args.lock_timeout):
            state, _ = load_state(state_path)
            unseen_counts, streak_reset_reason = update_unseen_streaks(
                state,
                summaries["usage"],
                complete=complete,
                scope_value=scope_value,
                date=args.date,
            )
            if summaries["usage"]:
                observations.extend(
                    extract_usage_observations(
                        summaries["usage"],
                        validation["usage"]["report_ref"],
                        skills_root,
                        unseen_counts,
                    )
                )
            authoritative_sources = {
                audit for audit in ("upstream", "hygiene") if summaries[audit] is not None
            }
            if summaries["usage"] is not None and usage_complete:
                authoritative_sources.add("usage")
            merge_result = merge_observations(
                state,
                observations,
                args.date,
                authoritative_sources=authoritative_sources,
            )
            run_record = {
                "date": args.date,
                "completed_at": now_iso(),
                "complete": complete,
                "scope_fingerprint": scope_value,
                "streak_reset_reason": streak_reset_reason,
                "report_ref": relative_report_ref(report_path, reports_root),
                "observation_ids": [item["id"] for item in observations],
                "command_exit_codes": {
                    name: result.get("exit_code") for name, result in command_results.items()
                },
            }
            existing_run = next(
                (item for item in state["runs"] if item.get("date") == args.date), None
            )
            if existing_run is None:
                state["runs"].append(run_record)
            else:
                existing_run.update(run_record)
            save_state(state_path, state)
    except (StateError, LockConflict, OSError) as exc:
        failure = fatal_payload(exc.__class__.__name__, str(exc), state_path)
        report = build_scan_report(
            date=args.date,
            command_results=command_results,
            validation=validation,
            complete=False,
            completeness_reasons=[*completeness_reasons, str(exc)],
            scope_value=scope_value,
            streak_reset_reason="state_blocked",
            observations=observations,
            merge_result=None,
        )
        atomic_write_json(report_path, report)
        return {**failure, "scan_report": relative_report_ref(report_path, reports_root)}, 3

    report = build_scan_report(
        date=args.date,
        command_results=command_results,
        validation=validation,
        complete=complete,
        completeness_reasons=completeness_reasons,
        scope_value=scope_value,
        streak_reset_reason=streak_reset_reason,
        observations=observations,
        merge_result=merge_result,
    )
    atomic_write_json(report_path, report)
    return {
        "status": "scanned",
        "date": args.date,
        "complete": complete,
        "completeness_reasons": completeness_reasons,
        "scan_report": relative_report_ref(report_path, reports_root),
        "state": relative_report_ref(state_path, reports_root),
        "merge": merge_result,
    }, 0 if complete else 2


def pending_approved_findings(state: dict[str, Any]) -> list[dict[str, Any]]:
    active_items = {
        item.get("finding_id")
        for batch in state["batches"]
        if batch.get("status") in ACTIVE_BATCH_STATUSES
        for item in batch.get("items", [])
    }
    return [
        finding
        for finding in state["findings"].values()
        if finding.get("status") == "approved" and finding.get("id") not in active_items
    ]


def select_queue_item(state: dict[str, Any]) -> dict[str, Any] | None:
    candidates = [
        state["findings"].get(finding_id)
        for finding_id in state["queue"]
        if state["findings"].get(finding_id, {}).get("status") in PENDING_STATUSES
    ]
    candidates = [item for item in candidates if item]
    critical = [item for item in candidates if item.get("severity") == "critical"]
    if critical:
        return critical[0]
    retries = [item for item in candidates if item.get("status") == "retry_pending"]
    if retries:
        return retries[0]
    return candidates[0] if candidates else None


def fact_question_limit(finding: dict[str, Any]) -> int:
    return min(2, len(finding.get("fact_questions", [])))


def question_payload(finding: dict[str, Any]) -> dict[str, Any]:
    status = finding.get("status")
    if status == "retry_pending":
        execution = finding.get("execution", {})
        question = (
            f"`{finding['title']}` 上次执行失败：{compact_text(execution.get('details'))}。"
            "是否按相同证据和方案重试？"
        )
        question_type = "retry"
    elif status == "facts":
        facts = finding.setdefault("facts", [])
        questions = finding.get("fact_questions", [])
        index = min(len(facts), max(0, len(questions) - 1))
        question = questions[index] if questions else "还需要什么事实才能判断是否形成修改建议？"
        question_type = "fact"
    elif status == "revising":
        pending = finding.get("pending_revision") or finding.get("proposal") or {}
        question = f"修订后的建议是：{pending.get('summary', '')} 是否批准这项修订后的修改？"
        question_type = "revision_decision"
    else:
        proposed = finding.get("proposal") or {}
        question = f"是否批准这项修改：{proposed.get('summary') or finding.get('title')}"
        question_type = "decision"
    return {
        "status": "question",
        "question_type": question_type,
        "finding_id": finding["id"],
        "severity": finding["severity"],
        "title": finding["title"],
        "evidence": finding["evidence_summary"],
        "proposal": finding.get("pending_revision") or finding.get("proposal"),
        "question": question,
        "choices": ["批准", "不批准", "解释一下"],
        "expected_evidence_fingerprint": finding["evidence_fingerprint"],
        "expected_proposal_fingerprint": finding.get("proposal_fingerprint"),
    }


def next_question_command(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    state_path = args.state.resolve()
    try:
        with StateLock(state_path, args.lock_timeout):
            state, created = load_state(state_path)
            if created:
                return {
                    "status": "not_initialized",
                    "message": "尚未运行完整周检。",
                }, 2
            finding = select_queue_item(state)
            if finding is None:
                approved = pending_approved_findings(state)
                if approved:
                    return {
                        "status": "execution_ready",
                        "approved_count": len(approved),
                        "approved_finding_ids": [item["id"] for item in approved],
                        "message": "所有逐项问题已处理，可以生成一次最终执行确认。",
                    }, 0
                return {
                    "status": "empty",
                    "message": "本周没有需要决定的修改。",
                }, 0
            changed = False
            if finding.get("status") == "queued":
                if finding.get("needs_facts") and len(
                    finding.get("facts", [])
                ) < fact_question_limit(finding):
                    finding["status"] = "facts"
                else:
                    finding["status"] = "awaiting_decision"
                changed = True
            if changed:
                save_state(state_path, state)
            return question_payload(finding), 0
    except (StateError, LockConflict, OSError) as exc:
        return fatal_payload(exc.__class__.__name__, str(exc), state_path), 3


def add_state_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE_PATH)
    parser.add_argument("--lock-timeout", type=float, default=LOCK_TIMEOUT_SECONDS)
    parser.add_argument("--json", action="store_true")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Combine weekly skill audits into one persistent, approval-gated review queue."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    scan = subparsers.add_parser("scan", help="Run or ingest all weekly audits and merge findings.")
    add_state_arguments(scan)
    scan.add_argument("--date", default=today_local())
    scan.add_argument("--agents-root", type=Path, default=DEFAULT_AGENTS_ROOT)
    scan.add_argument("--skills-root", type=Path, default=DEFAULT_SKILLS_ROOT)
    scan.add_argument("--reports-root", type=Path, default=DEFAULT_REPORTS_ROOT)
    scan.add_argument(
        "--reuse-reports",
        action="store_true",
        help="Do not rerun audit commands; ingest the report files for --date.",
    )

    next_question = subparsers.add_parser(
        "next-question", help="Return exactly one pending question or the fixed empty result."
    )
    add_state_arguments(next_question)

    record = subparsers.add_parser(
        "record-decision", help="Record one answer with optimistic fingerprint checks."
    )
    add_state_arguments(record)
    record.add_argument("--skills-root", type=Path, default=DEFAULT_SKILLS_ROOT)
    record.add_argument("--finding-id", required=True)
    record.add_argument("--expected-evidence-fingerprint", required=True)
    record.add_argument(
        "--expected-proposal-fingerprint",
        required=True,
        help="Use the literal value from next-question, or 'none' when it is null.",
    )
    record.add_argument("--answer", required=True)
    record.add_argument("--reason")
    record.add_argument(
        "--classification",
        choices=("auto", "approve", "reject", "explain", "adjust"),
        default="auto",
    )
    record.add_argument("--facts-outcome", choices=("close", "propose", "wait"))
    record.add_argument("--revised-proposal-json")

    prepare = subparsers.add_parser(
        "prepare-execution", help="Freeze approved findings and handle the one batch confirmation."
    )
    add_state_arguments(prepare)
    prepare.add_argument("--date", default=today_local())
    prepare.add_argument("--skills-root", type=Path, default=DEFAULT_SKILLS_ROOT)
    prepare.add_argument("--reports-root", type=Path, default=DEFAULT_REPORTS_ROOT)
    prepare.add_argument("--sync-helper", type=Path, default=DEFAULT_SYNC_HELPER)
    prepare.add_argument(
        "--decision", choices=("ask", "approve", "reject", "explain"), default="ask"
    )
    prepare.add_argument("--batch-id")
    prepare.add_argument("--expected-batch-fingerprint")

    execution = subparsers.add_parser(
        "record-execution", help="Record one frozen batch item's execution result."
    )
    add_state_arguments(execution)
    execution.add_argument("--batch-id", required=True)
    execution.add_argument("--finding-id", required=True)
    execution.add_argument("--expected-proposal-fingerprint", required=True)
    execution.add_argument("--outcome", choices=("success", "failed", "blocked"), required=True)
    execution.add_argument("--details", required=True)
    execution.add_argument("--commit")
    execution.add_argument("--remote-sha")
    execution.add_argument(
        "--sync-status",
        choices=("not_run", "timed_out", "failed", "verified"),
        default="not_run",
    )
    execution.add_argument("--synced-skill", action="append", default=[])
    return normalize_cli_fingerprints(parser.parse_args(argv))


def normalize_cli_fingerprints(args: argparse.Namespace) -> argparse.Namespace:
    for field in ("expected_proposal_fingerprint", "expected_batch_fingerprint"):
        value = getattr(args, field, None)
        if isinstance(value, str) and value.strip().lower() in NULL_FINGERPRINT_VALUES:
            setattr(args, field, None)
    return args


def classify_answer(value: str) -> str:
    normalized = re.sub(r"[\s，。！？、,.!?]+", "", value or "").lower()
    if normalized in {
        "不批准",
        "不执行",
        "不同意",
        "拒绝",
        "否",
        "no",
        "先不批准",
        "暂不批准",
    } or normalized.startswith(("不批准", "不同意", "拒绝")):
        return "reject"
    if normalized in {
        "批准",
        "同意",
        "可以",
        "执行",
        "是",
        "yes",
        "ok",
        "确认",
        "确认执行",
        "可以执行",
        "开始执行",
        "批准执行",
        "行",
        "好",
        "行可以执行",
        "好可以执行",
    }:
        return "approve"
    if normalized in {
        "解释一下",
        "解释",
        "说明一下",
        "为什么",
        "explain",
        "没看懂",
        "不明白",
        "再解释一下",
        "说清楚",
    }:
        return "explain"
    return "adjust"


def parse_proposal_json(raw: str | None) -> dict[str, Any] | None:
    if raw is None:
        return None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"revised proposal is not valid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("revised proposal must be an object")
    required = ("action", "summary", "targets")
    missing = [key for key in required if key not in payload]
    if missing:
        raise ValueError(f"revised proposal is missing fields: {', '.join(missing)}")
    for field in ("action", "summary"):
        if not isinstance(payload[field], str) or not payload[field].strip():
            raise ValueError(f"revised proposal field {field!r} must be a non-empty string")
    for field in ("targets", "skills", "dependencies"):
        if field in payload and not isinstance(payload[field], list):
            raise ValueError(f"revised proposal field {field!r} must be a list")
    if "requires_runtime_sync" in payload and not isinstance(
        payload["requires_runtime_sync"], bool
    ):
        raise ValueError("revised proposal field 'requires_runtime_sync' must be a boolean")
    if "candidate_workspace" in payload and not isinstance(
        payload["candidate_workspace"], str
    ):
        raise ValueError("revised proposal field 'candidate_workspace' must be a string")
    parsed = proposal(
        str(payload["action"]),
        str(payload["summary"]),
        payload.get("targets", []),
        skills=payload.get("skills", []),
        dependencies=payload.get("dependencies", []),
        requires_runtime_sync=payload.get("requires_runtime_sync", True),
        candidate_workspace=payload.get("candidate_workspace"),
    )
    if not parsed["targets"]:
        raise ValueError("revised proposal must contain at least one relative target")
    return parsed


def decision_explanation(finding: dict[str, Any]) -> str:
    proposed = finding.get("pending_revision") or finding.get("proposal") or {}
    return compact_text(
        f"证据：{finding.get('evidence_summary', '')} 建议：{proposed.get('summary', '尚未形成修改建议')}。"
        "批准只授权这一个稳定 finding 和当前证据/方案 fingerprint；内容变化后批准自动失效。",
        1400,
    )


def remove_from_queue(state: dict[str, Any], finding_id: str) -> None:
    state["queue"] = [value for value in state["queue"] if value != finding_id]


def ensure_in_queue(state: dict[str, Any], finding_id: str, *, front: bool = False) -> None:
    remove_from_queue(state, finding_id)
    if front:
        state["queue"].insert(0, finding_id)
    else:
        state["queue"].append(finding_id)


def record_decision_command(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    args = normalize_cli_fingerprints(args)
    state_path = args.state.resolve()
    skills_root = args.skills_root.resolve()
    try:
        revised = parse_proposal_json(args.revised_proposal_json)
    except ValueError as exc:
        return {"status": "invalid_request", "error": str(exc)}, 2
    try:
        with StateLock(state_path, args.lock_timeout):
            state, created = load_state(state_path)
            if created:
                return {"status": "not_initialized", "message": "尚未运行完整周检。"}, 2
            finding = state["findings"].get(args.finding_id)
            if finding is None:
                return {"status": "not_found", "finding_id": args.finding_id}, 2
            if args.expected_evidence_fingerprint != finding.get("evidence_fingerprint"):
                return {
                    "status": "stale_fingerprint",
                    "field": "evidence",
                    "finding_id": args.finding_id,
                }, 4
            if args.expected_proposal_fingerprint != finding.get("proposal_fingerprint"):
                return {
                    "status": "stale_fingerprint",
                    "field": "proposal",
                    "finding_id": args.finding_id,
                }, 4

            classification = args.classification
            if classification == "auto":
                classification = classify_answer(args.answer)
            timestamp = now_iso()
            status = finding.get("status")
            if classification == "explain":
                return {
                    "status": "explanation",
                    "finding_id": finding["id"],
                    "explanation": decision_explanation(finding),
                    "question": question_payload(finding),
                }, 0

            if status == "facts":
                answer_summary = compact_text(args.reason or args.answer)
                if args.facts_outcome is None and classification in {"approve", "reject"}:
                    if classification == "approve" and finding.get("proposal_fingerprint") is None:
                        return {
                            "status": "invalid_state",
                            "error": "a finding without a proposal cannot be approved",
                        }, 2
                    finding["status"] = "approved" if classification == "approve" else "rejected"
                    finding["decision"] = {
                        "value": "approved" if classification == "approve" else "rejected",
                        "reason_summary": answer_summary,
                        "evidence_fingerprint": finding["evidence_fingerprint"],
                        "proposal_fingerprint": finding.get("proposal_fingerprint"),
                        "recorded_at": timestamp,
                    }
                    remove_from_queue(state, finding["id"])
                    save_state(state_path, state)
                    return {
                        "status": "recorded",
                        "finding_id": finding["id"],
                        "decision": finding["decision"]["value"],
                        "next_status": finding["status"],
                    }, 0
                facts = finding.setdefault("facts", [])
                facts.append({"answer_summary": answer_summary, "recorded_at": timestamp})
                outcome = args.facts_outcome
                if outcome is None and len(facts) >= max(1, fact_question_limit(finding)):
                    outcome = "wait"
                if outcome == "close":
                    finding["status"] = "closed"
                    finding["decision"] = {
                        "value": "closed_after_facts",
                        "reason_summary": answer_summary,
                        "recorded_at": timestamp,
                    }
                    remove_from_queue(state, finding["id"])
                elif outcome == "wait":
                    finding["status"] = "waiting_evidence"
                    finding["decision"] = {
                        "value": "waiting_for_new_evidence",
                        "reason_summary": answer_summary,
                        "recorded_at": timestamp,
                    }
                    remove_from_queue(state, finding["id"])
                elif outcome == "propose":
                    if revised is not None:
                        finding["proposal"] = revised
                    finding["proposal_fingerprint"] = fingerprint(finding.get("proposal"))
                    finding["status"] = "awaiting_decision"
                    ensure_in_queue(state, finding["id"])
                else:
                    finding["status"] = "facts"
                    ensure_in_queue(state, finding["id"], front=finding.get("severity") == "critical")
                save_state(state_path, state)
                return {
                    "status": "recorded",
                    "finding_id": finding["id"],
                    "next_status": finding["status"],
                    "fact_count": len(facts),
                }, 0

            if classification == "adjust":
                if status not in {
                    "awaiting_decision",
                    "queued",
                    "revising",
                    "retry_pending",
                    "approved",
                    "execution_pending",
                }:
                    return {
                        "status": "invalid_state",
                        "finding_id": finding["id"],
                        "finding_status": status,
                    }, 2
                invalidated = invalidate_batches_for_finding(
                    state,
                    finding["id"],
                    "user requested a material proposal adjustment",
                )
                finding.pop("decision", None)
                finding["status"] = "revising"
                finding["requested_adjustment"] = compact_text(args.reason or args.answer)
                if revised is None:
                    revised = copy.deepcopy(finding.get("proposal") or {})
                    revised["summary"] = compact_text(
                        f"{revised.get('summary', finding.get('title', ''))}；按用户意见调整："
                        f"{finding['requested_adjustment']}",
                        1000,
                    )
                finding["pending_revision"] = revised
                ensure_in_queue(state, finding["id"], front=finding.get("severity") == "critical")
                save_state(state_path, state)
                return {
                    "status": "revision_staged",
                    "finding_id": finding["id"],
                    "invalidated_batches": invalidated,
                    "proposal_fingerprint_unchanged_until_approval": True,
                    "next_question": question_payload(finding),
                }, 0

            if status not in {"awaiting_decision", "queued", "revising", "retry_pending"}:
                return {
                    "status": "invalid_state",
                    "finding_id": finding["id"],
                    "finding_status": status,
                }, 2

            if classification not in {"approve", "reject"}:
                return {"status": "invalid_request", "error": "unsupported classification"}, 2

            retry_baseline: dict[str, Any] | None = None
            if classification == "approve" and status == "retry_pending":
                retry_baseline, retry_error = advance_retry_source_baseline(
                    state,
                    finding,
                    skills_root,
                    event="retry_source_baseline_advanced",
                    timestamp=timestamp,
                )
                if retry_error:
                    return {
                        "status": "blocked_retry_source_drift",
                        "finding_id": finding["id"],
                        "reason": retry_error,
                    }, 4

            if classification == "approve":
                if status == "revising":
                    pending = finding.pop("pending_revision", None)
                    if not pending:
                        return {"status": "invalid_state", "error": "no pending revision"}, 2
                    finding["proposal"] = pending
                    finding["proposal_fingerprint"] = fingerprint(pending)
                finding["status"] = "approved"
                finding["decision"] = {
                    "value": "approved",
                    "reason_summary": compact_text(args.reason or args.answer),
                    "evidence_fingerprint": finding["evidence_fingerprint"],
                    "proposal_fingerprint": finding["proposal_fingerprint"],
                    "recorded_at": timestamp,
                }
                if retry_baseline is not None:
                    finding["decision"]["source_fingerprint"] = retry_baseline[
                        "source_fingerprint"
                    ]
            else:
                finding.pop("pending_revision", None)
                finding["status"] = "rejected"
                finding["decision"] = {
                    "value": "rejected",
                    "reason_summary": compact_text(args.reason or args.answer),
                    "evidence_fingerprint": finding["evidence_fingerprint"],
                    "proposal_fingerprint": finding.get("proposal_fingerprint"),
                    "recorded_at": timestamp,
                }
            remove_from_queue(state, finding["id"])
            save_state(state_path, state)
            response = {
                "status": "recorded",
                "finding_id": finding["id"],
                "decision": finding["decision"]["value"],
                "next_status": finding["status"],
            }
            if retry_baseline is not None:
                response["retry_source_rebased"] = retry_baseline["changed"]
                response["invalidated_batches"] = retry_baseline["invalidated_batches"]
            return response, 0
    except (StateError, LockConflict, OSError) as exc:
        return fatal_payload(exc.__class__.__name__, str(exc), state_path), 3


def sync_helper_fingerprint(path: Path) -> str:
    if not path.is_file():
        return fingerprint({"status": "missing", "name": path.name})
    return file_sha256(path)


def targets_overlap(left: Iterable[str], right: Iterable[str]) -> bool:
    left_values = normalize_targets(left)
    right_values = normalize_targets(right)
    for first in left_values:
        for second in right_values:
            if first == second or first.startswith(second + "/") or second.startswith(first + "/"):
                return True
    return False


def batch_fingerprint(items: list[dict[str, Any]]) -> str:
    return fingerprint(
        [
            {
                "finding_id": item["finding_id"],
                "evidence_fingerprint": item["evidence_fingerprint"],
                "proposal_fingerprint": item["proposal_fingerprint"],
                "source_fingerprint": item["source_fingerprint"],
            }
            for item in items
        ]
    )


def build_batch_items(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for finding in sorted(findings, key=lambda item: (item.get("first_seen", ""), item["id"])):
        proposed = finding.get("proposal") or {}
        explicit_dependencies = list(proposed.get("dependencies", []))
        overlap_dependencies = [
            item["finding_id"]
            for item in items
            if targets_overlap(item.get("targets", []), proposed.get("targets", []))
        ]
        items.append(
            {
                "finding_id": finding["id"],
                "title": finding["title"],
                "evidence_fingerprint": finding["evidence_fingerprint"],
                "proposal_fingerprint": finding["proposal_fingerprint"],
                "source_fingerprint": finding["source_fingerprint"],
                "targets": list(proposed.get("targets", [])),
                "skills": list(proposed.get("skills", [])),
                "requires_runtime_sync": bool(proposed.get("requires_runtime_sync", True)),
                "candidate_workspace": proposed.get("candidate_workspace"),
                "blocked_by": sorted(set(explicit_dependencies + overlap_dependencies)),
                "status": "pending",
            }
        )
    return items


def find_batch(state: dict[str, Any], batch_id: str) -> dict[str, Any] | None:
    return next((batch for batch in state["batches"] if batch.get("id") == batch_id), None)


def execution_confirmation_payload(
    state: dict[str, Any], batch: dict[str, Any]
) -> dict[str, Any]:
    summaries = [
        state["findings"].get(item["finding_id"], {}).get("proposal", {}).get("summary", "")
        for item in batch["items"]
    ]
    return {
        "status": "execution_confirmation",
        "batch_id": batch["id"],
        "batch_fingerprint": batch["batch_fingerprint"],
        "approved_count": len(batch["items"]),
        "approved_changes": summaries,
        "question": "以上逐项批准的修改是否现在统一执行？",
        "choices": ["批准", "不批准", "解释一下"],
    }


def unique_batch_id(state: dict[str, Any], base: str) -> str:
    used = {str(batch.get("id")) for batch in state["batches"]}
    if base not in used:
        return base
    counter = 2
    while f"{base}-{counter}" in used:
        counter += 1
    return f"{base}-{counter}"


def prepare_execution_command(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    args = normalize_cli_fingerprints(args)
    state_path = args.state.resolve()
    skills_root = args.skills_root.resolve()
    helper_path = args.sync_helper.resolve()
    if args.decision != "ask" and (
        not args.batch_id or not args.expected_batch_fingerprint
    ):
        return {
            "status": "invalid_request",
            "error": (
                "--batch-id and --expected-batch-fingerprint are required "
                "when --decision is not ask"
            ),
        }, 2
    try:
        with StateLock(state_path, args.lock_timeout):
            state, created = load_state(state_path)
            if created:
                return {"status": "not_initialized", "message": "尚未运行完整周检。"}, 2

            if args.decision == "ask":
                unresolved = [
                    finding_id
                    for finding_id in state["queue"]
                    if state["findings"].get(finding_id, {}).get("status") in PENDING_STATUSES
                ]
                if unresolved:
                    return {
                        "status": "questions_pending",
                        "pending_count": len(unresolved),
                        "next_finding_id": unresolved[0],
                    }, 2
                awaiting = next(
                    (
                        batch
                        for batch in reversed(state["batches"])
                        if batch.get("status") == "awaiting_confirmation"
                    ),
                    None,
                )
                if awaiting is not None:
                    return execution_confirmation_payload(state, awaiting), 0
                recovered_retry_ids = recover_legacy_retry_source_baselines(
                    state, skills_root
                )
                approved = pending_approved_findings(state)
                if not approved:
                    return {
                        "status": "empty",
                        "message": "本周没有需要决定的修改。",
                    }, 0
                items = build_batch_items(approved)
                identity = batch_fingerprint(items)
                existing = next(
                    (
                        batch
                        for batch in state["batches"]
                        if batch.get("status") == "awaiting_confirmation"
                        and batch.get("batch_fingerprint") == identity
                    ),
                    None,
                )
                if existing is None:
                    helper_identity = sync_helper_fingerprint(helper_path)
                    batch_id = unique_batch_id(
                        state,
                        f"batch-{args.date}-{identity[:12]}-{helper_identity[:8]}",
                    )
                    existing = {
                        "id": batch_id,
                        "date": args.date,
                        "created_at": now_iso(),
                        "status": "awaiting_confirmation",
                        "batch_fingerprint": identity,
                        "sync_helper_fingerprint": helper_identity,
                        "items": items,
                    }
                    state["batches"].append(existing)
                    save_state(state_path, state)
                payload = execution_confirmation_payload(state, existing)
                if recovered_retry_ids:
                    payload["recovered_retry_finding_ids"] = recovered_retry_ids
                return payload, 0

            if not args.batch_id:
                return {"status": "invalid_request", "error": "--batch-id is required"}, 2
            batch = find_batch(state, args.batch_id)
            if batch is None:
                return {"status": "not_found", "batch_id": args.batch_id}, 2
            if batch.get("status") != "awaiting_confirmation":
                return {
                    "status": "invalid_state",
                    "batch_id": args.batch_id,
                    "batch_status": batch.get("status"),
                }, 2
            if args.expected_batch_fingerprint != batch.get("batch_fingerprint"):
                return {"status": "stale_fingerprint", "field": "batch"}, 4

            if args.decision == "reject":
                batch["status"] = "cancelled"
                batch["decided_at"] = now_iso()
                for item in batch["items"]:
                    finding = state["findings"].get(item["finding_id"])
                    if finding and finding.get("status") == "approved":
                        finding["status"] = "execution_declined"
                save_state(state_path, state)
                return {"status": "execution_declined", "batch_id": batch["id"]}, 0
            if args.decision == "explain":
                return {
                    "status": "explanation",
                    "batch_id": batch["id"],
                    "batch_fingerprint": batch["batch_fingerprint"],
                    "explanation": (
                        "这次确认只覆盖已逐项批准且 fingerprint 未变化的修改。执行仍会逐项隔离、复测、"
                        "精确暂存、提交、推送和定向同步；单项失败不会带动无依赖项失败。"
                    ),
                    "question": "以上逐项批准的修改是否现在统一执行？",
                    "choices": ["批准", "不批准", "解释一下"],
                }, 0
            if args.decision != "approve":
                return {"status": "invalid_request", "error": "unsupported execution decision"}, 2

            current_helper = sync_helper_fingerprint(helper_path)
            if current_helper != batch.get("sync_helper_fingerprint"):
                batch["status"] = "stale"
                batch["stale_reason"] = "sync helper identity changed"
                batch["stale_at"] = now_iso()
                for item in batch["items"]:
                    finding = state["findings"].get(item["finding_id"])
                    if finding:
                        finding["status"] = "approved"
                save_state(state_path, state)
                return {
                    "status": "blocked_helper_drift",
                    "batch_id": batch["id"],
                }, 4

            drifted: list[str] = []
            for item in batch["items"]:
                finding = state["findings"].get(item["finding_id"])
                if not finding:
                    drifted.append(item["finding_id"])
                    item["status"] = "blocked_drift"
                    continue
                outside_targets = outside_root_targets(skills_root, item.get("targets", []))
                if (
                    outside_targets
                    or item["evidence_fingerprint"] != finding.get("evidence_fingerprint")
                    or item["proposal_fingerprint"] != finding.get("proposal_fingerprint")
                    or item["source_fingerprint"]
                    != source_fingerprint(skills_root, item.get("targets", []))
                ):
                    drifted.append(item["finding_id"])
                    item["status"] = "blocked_drift"
                    if outside_targets:
                        item["blocked_reason"] = "target resolves outside skills root"
                    finding["status"] = "waiting_evidence"
                    continue
                finding["status"] = "execution_pending"

            dependency_blocked: list[str] = []
            for item in batch["items"]:
                if item.get("status") != "pending":
                    continue
                unavailable = []
                for dependency in item.get("blocked_by", []):
                    dependency_item = batch_item(batch, dependency)
                    if dependency_item is not None:
                        if dependency_item.get("status") in {
                            "blocked_drift",
                            "blocked_dependency",
                            "failed",
                        }:
                            unavailable.append(dependency)
                        continue
                    dependency_finding = state["findings"].get(dependency)
                    if not dependency_finding or dependency_finding.get("status") != "completed":
                        unavailable.append(dependency)
                if unavailable:
                    item["status"] = "blocked_dependency"
                    item["unavailable_dependencies"] = unavailable
                    dependency_blocked.append(item["finding_id"])
            ready_items = [item for item in batch["items"] if item.get("status") == "pending"]
            if not ready_items and not dependency_blocked:
                batch["status"] = "blocked"
                batch["decided_at"] = now_iso()
                save_state(state_path, state)
                return {
                    "status": "blocked_source_drift",
                    "batch_id": batch["id"],
                    "drifted_finding_ids": drifted,
                }, 4
            batch["status"] = "ready"
            batch["decided_at"] = now_iso()
            batch["execution_root"] = relative_report_ref(
                args.reports_root.resolve() / args.date / "execution-candidates" / batch["id"],
                args.reports_root.resolve(),
            )
            save_state(state_path, state)
            return {
                "status": "ready",
                "batch_id": batch["id"],
                "items": ready_items,
                "drifted_finding_ids": drifted,
                "dependency_blocked_finding_ids": dependency_blocked,
                "execution_root": batch["execution_root"],
            }, 0
    except (StateError, LockConflict, OSError) as exc:
        return fatal_payload(exc.__class__.__name__, str(exc), state_path), 3


def batch_item(batch: dict[str, Any], finding_id: str) -> dict[str, Any] | None:
    return next(
        (item for item in batch.get("items", []) if item.get("finding_id") == finding_id), None
    )


def refresh_batch_status(batch: dict[str, Any]) -> None:
    statuses = {item.get("status") for item in batch.get("items", [])}
    if statuses and statuses <= {"success", "blocked_drift"}:
        batch["status"] = "completed" if statuses == {"success"} else "partial_blocked"
    elif "failed" in statuses or "blocked_dependency" in statuses:
        batch["status"] = "partial_failed"
    elif statuses <= {"success"}:
        batch["status"] = "completed"
    else:
        batch["status"] = "ready"


def record_execution_command(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    args = normalize_cli_fingerprints(args)
    state_path = args.state.resolve()
    try:
        with StateLock(state_path, args.lock_timeout):
            state, created = load_state(state_path)
            if created:
                return {"status": "not_initialized", "message": "尚未运行完整周检。"}, 2
            batch = find_batch(state, args.batch_id)
            if batch is None:
                return {"status": "not_found", "batch_id": args.batch_id}, 2
            if batch.get("status") not in {"ready", "partial_failed"}:
                return {
                    "status": "invalid_state",
                    "batch_status": batch.get("status"),
                }, 2
            item = batch_item(batch, args.finding_id)
            finding = state["findings"].get(args.finding_id)
            if item is None or finding is None:
                return {"status": "not_found", "finding_id": args.finding_id}, 2
            if args.expected_proposal_fingerprint != item.get("proposal_fingerprint"):
                return {"status": "stale_fingerprint", "field": "proposal"}, 4
            if item.get("status") not in {"pending", "blocked_dependency", "failed"}:
                return {"status": "invalid_state", "item_status": item.get("status")}, 2
            unmet = []
            for dependency in item.get("blocked_by", []):
                dependency_item = batch_item(batch, dependency)
                if dependency_item is not None:
                    dependency_finding = state["findings"].get(dependency)
                    if dependency_item.get("status") != "success" and (
                        not dependency_finding
                        or dependency_finding.get("status") != "completed"
                    ):
                        unmet.append(dependency)
                    continue
                dependency_finding = state["findings"].get(dependency)
                if not dependency_finding or dependency_finding.get("status") != "completed":
                    unmet.append(dependency)
            if args.outcome == "success" and unmet:
                return {
                    "status": "blocked_dependency",
                    "finding_id": args.finding_id,
                    "blocked_by": unmet,
                }, 4
            if args.outcome == "success" and item.get("requires_runtime_sync"):
                remote_sha = (args.remote_sha or "").lower()
                expected_skills = sorted(set(item.get("skills", [])))
                actual_skills = sorted(set(args.synced_skill or []))
                if not SHA40_PATTERN.fullmatch(remote_sha):
                    return {
                        "status": "invalid_request",
                        "error": "success requires a 40-character hexadecimal remote SHA",
                    }, 2
                if args.sync_status != "verified":
                    return {
                        "status": "invalid_request",
                        "error": "runtime-syncing success requires sync_status=verified",
                    }, 2
                if expected_skills != actual_skills:
                    return {
                        "status": "invalid_request",
                        "error": "synced Skill set does not match the frozen batch item",
                        "expected_skills": expected_skills,
                        "actual_skills": actual_skills,
                    }, 2

            timestamp = now_iso()
            execution = {
                "outcome": args.outcome,
                "details": compact_text(args.details),
                "commit": compact_text(args.commit or "", 80),
                "remote_sha": (args.remote_sha or "").lower() or None,
                "sync_status": args.sync_status,
                "recorded_at": timestamp,
            }
            finding["execution"] = execution
            item["execution"] = execution
            if args.outcome == "success":
                item["status"] = "success"
                item.pop("unavailable_dependencies", None)
                finding["status"] = "completed"
                finding["completed_at"] = timestamp
            elif args.outcome == "failed":
                item["status"] = "failed"
                finding["status"] = "retry_pending"
                ensure_in_queue(state, finding["id"], front=False)
                for dependent in batch.get("items", []):
                    if finding["id"] not in dependent.get("blocked_by", []):
                        continue
                    if dependent.get("status") != "pending":
                        continue
                    dependent["status"] = "blocked_dependency"
                    dependent_finding = state["findings"].get(dependent["finding_id"])
                    if dependent_finding:
                        dependent_finding["status"] = "approved"
            else:
                item["status"] = "blocked_drift"
                finding["status"] = "waiting_evidence"
            refresh_batch_status(batch)
            save_state(state_path, state)
            return {
                "status": "recorded",
                "batch_id": batch["id"],
                "batch_status": batch["status"],
                "finding_id": finding["id"],
                "finding_status": finding["status"],
            }, 0
    except (StateError, LockConflict, OSError) as exc:
        return fatal_payload(exc.__class__.__name__, str(exc), state_path), 3


def render_plain(payload: dict[str, Any]) -> str:
    status = payload.get("status")
    if status == "empty":
        return str(payload.get("message") or "本周没有需要决定的修改。")
    if status == "question":
        proposed = payload.get("proposal") or {}
        lines = [
            f"[{payload.get('severity', 'unknown')}] {payload.get('title', '')}",
            f"证据：{payload.get('evidence', '')}",
        ]
        if proposed.get("summary"):
            lines.append(f"建议：{proposed['summary']}")
        lines.extend(
            [
                str(payload.get("question") or ""),
                "可回复：批准 / 不批准 / 解释一下；也可以直接说明事实或调整意见。",
            ]
        )
        return "\n".join(lines)
    if status == "execution_confirmation":
        changes = [
            f"{index}. {summary}"
            for index, summary in enumerate(payload.get("approved_changes", []), start=1)
        ]
        return "\n".join(
            [
                "已批准的修改目的：",
                *changes,
                str(payload.get("question") or ""),
                "可回复：批准 / 不批准 / 解释一下。",
            ]
        )
    if status == "explanation":
        question = payload.get("question")
        lines = [str(payload.get("explanation") or "")]
        if isinstance(question, dict):
            lines.append(str(question.get("question") or ""))
        elif question:
            lines.append(str(question))
        return "\n".join(line for line in lines if line)
    if payload.get("message"):
        return str(payload["message"])
    if status == "scanned":
        return (
            f"周检扫描完成：complete={payload.get('complete')}; "
            f"report={payload.get('scan_report')}"
        )
    if status == "blocked" and isinstance(payload.get("fatal_finding"), dict):
        finding = payload["fatal_finding"]
        return f"{finding.get('title')}：{finding.get('detail')}"
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    handlers = {
        "scan": scan_command,
        "next-question": next_question_command,
        "record-decision": record_decision_command,
        "prepare-execution": prepare_execution_command,
        "record-execution": record_execution_command,
    }
    payload, exit_code = handlers[args.command](args)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(render_plain(payload))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
