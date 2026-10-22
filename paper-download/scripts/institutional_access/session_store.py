"""Machine-local browser-session storage.

Only short-lived CDP task identifiers are stored here. School passwords,
browser passwords, cookies, and authorization headers must never be written.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wintypes
import contextlib
import json
import msvcrt
import os
import re
from pathlib import Path
from typing import Any


SESSION_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
SESSION_PREFIX = "PaperDownload:browser-session:"


class SessionError(RuntimeError):
    pass


def validate_session_id(value: str) -> str:
    if not SESSION_RE.fullmatch(value or ""):
        raise SessionError("session ID must match [A-Za-z0-9_-]{1,64}")
    return value


def session_target(session_id: str) -> str:
    return SESSION_PREFIX + validate_session_id(session_id)


class FileSessionStore:
    """Isolated test backend; production never uses this backend."""

    def __init__(self, root: Path):
        self.root = root

    def _path(self, session_id: str) -> Path:
        return self.root / (validate_session_id(session_id) + ".json")

    def read(self, session_id: str) -> dict[str, Any] | None:
        path = self._path(session_id)
        if not path.is_file():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def write(self, session_id: str, value: dict[str, Any]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        path = self._path(session_id)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(value, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
        temporary.replace(path)

    def delete(self, session_id: str) -> None:
        path = self._path(session_id)
        try:
            path.unlink()
        except FileNotFoundError:
            pass


if os.name == "nt":
    class _Credential(ctypes.Structure):
        _fields_ = [
            ("Flags", wintypes.DWORD),
            ("Type", wintypes.DWORD),
            ("TargetName", wintypes.LPWSTR),
            ("Comment", wintypes.LPWSTR),
            ("LastWritten", wintypes.FILETIME),
            ("CredentialBlobSize", wintypes.DWORD),
            ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
            ("Persist", wintypes.DWORD),
            ("AttributeCount", wintypes.DWORD),
            ("Attributes", ctypes.c_void_p),
            ("TargetAlias", wintypes.LPWSTR),
            ("UserName", wintypes.LPWSTR),
        ]


class WindowsCredentialSessionStore:
    _GENERIC = 1
    _PERSIST_LOCAL_MACHINE = 2
    _ERROR_NOT_FOUND = 1168

    def __init__(self) -> None:
        self.api = ctypes.WinDLL("Advapi32.dll", use_last_error=True)
        self.api.CredWriteW.argtypes = [ctypes.POINTER(_Credential), wintypes.DWORD]
        self.api.CredWriteW.restype = wintypes.BOOL
        self.api.CredReadW.argtypes = [
            wintypes.LPCWSTR,
            wintypes.DWORD,
            wintypes.DWORD,
            ctypes.POINTER(ctypes.POINTER(_Credential)),
        ]
        self.api.CredReadW.restype = wintypes.BOOL
        self.api.CredDeleteW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD]
        self.api.CredDeleteW.restype = wintypes.BOOL
        self.api.CredFree.argtypes = [ctypes.c_void_p]

    def read(self, session_id: str) -> dict[str, Any] | None:
        target = session_target(session_id)
        pointer = ctypes.POINTER(_Credential)()
        if not self.api.CredReadW(target, self._GENERIC, 0, ctypes.byref(pointer)):
            error = ctypes.get_last_error()
            if error == self._ERROR_NOT_FOUND:
                return None
            raise SessionError(f"session credential read failed ({error})")
        try:
            size = pointer.contents.CredentialBlobSize
            blob = ctypes.string_at(pointer.contents.CredentialBlob, size)
            return json.loads(blob.decode("utf-16-le"))
        except (ValueError, UnicodeError, json.JSONDecodeError) as error:
            raise SessionError("session credential is unreadable") from error
        finally:
            self.api.CredFree(pointer)

    def write(self, session_id: str, value: dict[str, Any]) -> None:
        raw = json.dumps(
            value, ensure_ascii=False, separators=(",", ":")
        ).encode("utf-16-le")
        buffer = (ctypes.c_ubyte * len(raw)).from_buffer_copy(raw)
        credential = _Credential(
            Type=self._GENERIC,
            TargetName=session_target(session_id),
            Comment="paper-download browser task; no school password",
            CredentialBlobSize=len(raw),
            CredentialBlob=ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)),
            Persist=self._PERSIST_LOCAL_MACHINE,
            UserName="paper-download",
        )
        if not self.api.CredWriteW(ctypes.byref(credential), 0):
            raise SessionError(
                f"session credential write failed ({ctypes.get_last_error()})"
            )

    def delete(self, session_id: str) -> None:
        if not self.api.CredDeleteW(session_target(session_id), self._GENERIC, 0):
            error = ctypes.get_last_error()
            if error != self._ERROR_NOT_FOUND:
                raise SessionError(f"session credential delete failed ({error})")


def get_session_store() -> FileSessionStore | WindowsCredentialSessionStore:
    test_root = os.environ.get("PAPER_DOWNLOAD_TEST_STATE_DIR")
    if test_root:
        if os.environ.get("PAPER_DOWNLOAD_TEST_MODE") != "1":
            raise SessionError("test session store requires PAPER_DOWNLOAD_TEST_MODE=1")
        return FileSessionStore(Path(test_root))
    if os.name != "nt":
        raise SessionError("public institutional-access v1 requires Windows")
    return WindowsCredentialSessionStore()


@contextlib.contextmanager
def session_lock(session_id: str):
    validate_session_id(session_id)
    test_root = os.environ.get("PAPER_DOWNLOAD_TEST_STATE_DIR")
    if test_root:
        root = Path(test_root)
    else:
        local_app_data = os.environ.get("LOCALAPPDATA")
        if not local_app_data or not Path(local_app_data).is_absolute():
            raise SessionError("LOCALAPPDATA is unavailable")
        root = Path(local_app_data) / "PaperDownload"
    lock_root = root / "locks"
    lock_root.mkdir(parents=True, exist_ok=True)
    path = lock_root / (session_id + ".lock")
    stream = path.open("a+b")
    try:
        stream.seek(0, os.SEEK_END)
        if stream.tell() == 0:
            stream.write(b"0")
            stream.flush()
        stream.seek(0)
        try:
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as error:
            raise SessionError("session is already in use by another process") from error
        try:
            yield
        finally:
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
    finally:
        stream.close()
