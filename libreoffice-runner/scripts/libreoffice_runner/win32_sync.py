"""Cross-process capacity control built on Windows byte-range file locks."""

from __future__ import annotations

import json
import os
import tempfile
import time
import uuid
from dataclasses import dataclass
from datetime import timezone
from pathlib import Path
from typing import Any

import pywintypes
import win32api
import win32con
import win32file
import win32process
import winerror


CAPACITY = 2
RUNNER_ID = "sanan-libreoffice-runner"
_BUSY_ERRORS = {winerror.ERROR_LOCK_VIOLATION, winerror.ERROR_SHARING_VIOLATION}


class SyncError(RuntimeError):
    """The capacity controller could not safely manage its local state."""


class LockBusyError(SyncError):
    """A nonblocking LockFileEx request found a held lock."""


@dataclass
class FileLock:
    """An exclusive one-byte LockFileEx lease kept alive by its file handle."""

    path: Path
    handle: Any
    overlapped: pywintypes.OVERLAPPED
    closed: bool = False

    @classmethod
    def acquire(
        cls,
        path: Path,
        *,
        deadline: float | None = None,
        fail_immediately: bool = False,
    ) -> "FileLock":
        path.parent.mkdir(parents=True, exist_ok=True)
        while True:
            handle = win32file.CreateFile(
                str(path),
                win32con.GENERIC_READ | win32con.GENERIC_WRITE,
                win32con.FILE_SHARE_READ
                | win32con.FILE_SHARE_WRITE
                | win32con.FILE_SHARE_DELETE,
                None,
                win32con.OPEN_ALWAYS,
                win32con.FILE_ATTRIBUTE_NORMAL,
                None,
            )
            overlapped = pywintypes.OVERLAPPED()
            try:
                win32file.LockFileEx(
                    handle,
                    win32con.LOCKFILE_EXCLUSIVE_LOCK
                    | win32con.LOCKFILE_FAIL_IMMEDIATELY,
                    0,
                    1,
                    overlapped,
                )
                return cls(path=path, handle=handle, overlapped=overlapped)
            except pywintypes.error as exc:
                win32api.CloseHandle(handle)
                if exc.winerror not in _BUSY_ERRORS:
                    raise SyncError(f"LockFileEx failed for {path}: {exc}") from exc
                if fail_immediately:
                    raise LockBusyError(str(path)) from exc
                if deadline is not None and time.monotonic() >= deadline:
                    raise LockBusyError(str(path)) from exc
                time.sleep(0.05)

    def close(self) -> None:
        if self.closed:
            return
        try:
            win32file.UnlockFileEx(self.handle, 0, 1, self.overlapped)
        except pywintypes.error:
            # Closing the handle still releases a lock if the process is exiting.
            pass
        finally:
            win32api.CloseHandle(self.handle)
            self.closed = True

    def __enter__(self) -> "FileLock":
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()


@dataclass
class SlotLease:
    """A capacity slot. Release only after publish and task cleanup complete."""

    index: int
    lock: FileLock

    def release(self) -> None:
        self.lock.close()

    def __enter__(self) -> "SlotLease":
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.release()


def default_state_root() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA") or tempfile.gettempdir())
    return base / "SanAn" / "libreoffice-runner"


def process_creation_time(pid: int) -> str | None:
    """Return a stable UTC marker for a live PID, or None when it is gone."""

    try:
        handle = win32api.OpenProcess(win32con.PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    except pywintypes.error as exc:
        if exc.winerror in {winerror.ERROR_INVALID_PARAMETER, winerror.ERROR_NOT_FOUND}:
            return None
        return None
    try:
        created = win32process.GetProcessTimes(handle)["CreationTime"]
        return created.astimezone(timezone.utc).isoformat()
    finally:
        win32api.CloseHandle(handle)


def current_process_identity() -> dict[str, object]:
    pid = os.getpid()
    created_at = process_creation_time(pid)
    if created_at is None:
        raise SyncError(f"Could not read creation time for runner PID {pid}")
    return {"pid": pid, "created_at": created_at}


def process_identity_matches(pid: int, created_at: str) -> bool | None:
    """True means same live process; False means gone/reused; None means unknown."""

    try:
        handle = win32api.OpenProcess(win32con.PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    except pywintypes.error as exc:
        if exc.winerror in {winerror.ERROR_INVALID_PARAMETER, winerror.ERROR_NOT_FOUND}:
            return False
        return None
    try:
        current = win32process.GetProcessTimes(handle)["CreationTime"].astimezone(timezone.utc).isoformat()
    except pywintypes.error:
        return None
    finally:
        win32api.CloseHandle(handle)
    return current == created_at


class CapacitySlots:
    """FIFO admission plus two LockFileEx-backed conversion capacity slots."""

    def __init__(self, state_root: Path | None = None) -> None:
        self.state_root = (state_root or default_state_root()).resolve()
        self.slots_dir = self.state_root / "slots"
        self.queue_lock_path = self.state_root / "queue.lock"
        self.queue_data_path = self.state_root / "queue.json"

    def acquire(self, queue_timeout: float) -> SlotLease | None:
        if queue_timeout < 0:
            raise ValueError("queue_timeout must be non-negative")
        self.slots_dir.mkdir(parents=True, exist_ok=True)
        deadline = time.monotonic() + queue_timeout
        identity = current_process_identity()
        ticket = str(uuid.uuid4())
        self._insert_ticket(ticket, identity, deadline)
        try:
            while True:
                is_front = self._is_front(ticket, deadline)
                if is_front:
                    lease = self._try_acquire_slot()
                    if lease is not None:
                        try:
                            self._remove_ticket(ticket, deadline)
                        except Exception:
                            lease.release()
                            raise
                        return lease
                if time.monotonic() >= deadline:
                    return None
                time.sleep(0.05)
        finally:
            # It is harmless after a successful remove and essential after timeout/error.
            self._remove_ticket_best_effort(ticket)

    def _try_acquire_slot(self) -> SlotLease | None:
        for index in range(CAPACITY):
            path = self.slots_dir / f"slot-{index}.lock"
            try:
                lock = FileLock.acquire(path, fail_immediately=True)
            except LockBusyError:
                continue
            return SlotLease(index=index, lock=lock)
        return None

    def _insert_ticket(self, ticket: str, identity: dict[str, object], deadline: float) -> None:
        with self._queue_lock(deadline):
            entries = self._live_entries(self._read_queue())
            entries.append({"ticket": ticket, **identity})
            self._write_queue(entries)

    def _is_front(self, ticket: str, deadline: float) -> bool:
        with self._queue_lock(deadline):
            entries = self._live_entries(self._read_queue())
            self._write_queue(entries)
            return bool(entries and entries[0].get("ticket") == ticket)

    def _remove_ticket(self, ticket: str, deadline: float) -> None:
        with self._queue_lock(deadline):
            entries = [entry for entry in self._live_entries(self._read_queue()) if entry.get("ticket") != ticket]
            self._write_queue(entries)

    def _remove_ticket_best_effort(self, ticket: str) -> None:
        try:
            with self._queue_lock(time.monotonic() + 1.0):
                entries = [
                    entry for entry in self._live_entries(self._read_queue()) if entry.get("ticket") != ticket
                ]
                self._write_queue(entries)
        except SyncError:
            pass

    def _queue_lock(self, deadline: float) -> FileLock:
        try:
            return FileLock.acquire(self.queue_lock_path, deadline=deadline)
        except LockBusyError as exc:
            raise SyncError("Timed out while updating the LibreOffice admission queue") from exc

    def _read_queue(self) -> list[dict[str, object]]:
        if not self.queue_data_path.exists():
            return []
        try:
            data = json.loads(self.queue_data_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise SyncError(f"Could not read LibreOffice admission queue: {exc}") from exc
        if not isinstance(data, list) or not all(isinstance(item, dict) for item in data):
            raise SyncError("LibreOffice admission queue has an invalid structure")
        return data

    def _write_queue(self, entries: list[dict[str, object]]) -> None:
        temporary = self.queue_data_path.with_name(f"queue.json.tmp-{uuid.uuid4()}")
        payload = json.dumps(entries, ensure_ascii=False, separators=(",", ":"))
        try:
            with temporary.open("x", encoding="utf-8", newline="\n") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.queue_data_path)
        finally:
            if temporary.exists():
                temporary.unlink(missing_ok=True)

    @staticmethod
    def _live_entries(entries: list[dict[str, object]]) -> list[dict[str, object]]:
        live: list[dict[str, object]] = []
        for entry in entries:
            ticket = entry.get("ticket")
            pid = entry.get("pid")
            created_at = entry.get("created_at")
            if not isinstance(ticket, str) or not isinstance(pid, int) or not isinstance(created_at, str):
                continue
            if process_identity_matches(pid, created_at) is not False:
                live.append(entry)
        return live
