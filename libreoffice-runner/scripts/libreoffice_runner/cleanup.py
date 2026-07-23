"""Conservative cleanup for abandoned LibreOffice runner task directories."""

from __future__ import annotations

import json
import re
import shutil
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pywintypes
import win32con
import win32file
import winerror

from .win32_sync import FileLock, LockBusyError, RUNNER_ID, process_identity_matches


_TASK_NAME = re.compile(
    r"^sanan-lo-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


class CleanupError(RuntimeError):
    """An abandoned runner directory did not meet the deletion safety contract."""


def cleanup_abandoned(*, older_than: float = 24 * 60 * 60, temp_root: Path | None = None) -> dict[str, object]:
    if older_than < 0:
        raise ValueError("older_than must be non-negative")
    base = (temp_root or Path(tempfile.gettempdir())).resolve()
    deleted: list[str] = []
    skipped: list[dict[str, str]] = []
    for child in base.iterdir():
        if not _TASK_NAME.fullmatch(child.name):
            continue
        reason = _safe_to_delete(child, base, older_than)
        if reason is not None:
            skipped.append({"path": str(child), "reason": reason})
            continue
        try:
            _remove_without_reparse_points(child)
            deleted.append(str(child))
        except CleanupError as exc:
            skipped.append({"path": str(child), "reason": str(exc)})
    return {"ok": True, "deleted": deleted, "skipped": skipped}


def _safe_to_delete(path: Path, base: Path, older_than: float) -> str | None:
    if _is_reparse_point(path):
        return "root_reparse_point"
    if path.parent.resolve() != base or not path.is_dir():
        return "outside_or_not_directory"
    owner = _read_owner(path / "owner.json")
    if owner is None:
        return "invalid_owner"
    started = _parse_started(owner.get("started_at"))
    if started is None:
        return "invalid_owner"
    if (datetime.now(timezone.utc) - started).total_seconds() < older_than:
        return "too_recent"
    runner_pid = owner.get("runner_pid")
    runner_created_at = owner.get("runner_created_at")
    if not isinstance(runner_pid, int) or not isinstance(runner_created_at, str):
        return "invalid_owner"
    identity = process_identity_matches(runner_pid, runner_created_at)
    if identity is True:
        return "owner_process_active"
    active_lock_path = path / "active.lock"
    if not active_lock_path.is_file() or _is_reparse_point(active_lock_path):
        return "invalid_active_lock"
    try:
        active_lock = FileLock.acquire(active_lock_path, fail_immediately=True)
    except LockBusyError:
        return "active_lock_held"
    try:
        if identity is None:
            return "owner_identity_unknown"
        return None
    finally:
        active_lock.close()


def _read_owner(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    if payload.get("runner_id") != RUNNER_ID or payload.get("schema_version") != 1:
        return None
    return payload


def _parse_started(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        result = datetime.fromisoformat(value)
    except ValueError:
        return None
    if result.tzinfo is None:
        return None
    return result.astimezone(timezone.utc)


def _remove_without_reparse_points(root: Path) -> None:
    _assert_no_reparse_points(root)
    for attempt in range(60):
        try:
            shutil.rmtree(root)
            return
        except OSError as exc:
            if getattr(exc, "winerror", None) != winerror.ERROR_SHARING_VIOLATION or attempt == 59:
                raise CleanupError(f"delete_failed:{exc}") from exc
            time.sleep(0.05)
            _assert_no_reparse_points(root)


def _assert_no_reparse_points(path: Path) -> None:
    if _is_reparse_point(path):
        raise CleanupError("reparse_point")
    if path.is_dir():
        for child in path.iterdir():
            _assert_no_reparse_points(child)


def _is_reparse_point(path: Path) -> bool:
    try:
        attributes = win32file.GetFileAttributes(str(path))
    except pywintypes.error:
        return True
    return bool(attributes & win32con.FILE_ATTRIBUTE_REPARSE_POINT)
