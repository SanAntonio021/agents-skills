from __future__ import annotations

import json
import sys
import time
import unittest
from pathlib import Path

import pywintypes
import win32api
import win32con
import win32process
import winerror


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = SKILL_ROOT / "scripts"
HELPERS = Path(__file__).resolve().parent / "helpers"
RUNNER_CLI = SCRIPTS / "libreoffice_run.py"
PYTHON = Path(sys.executable)

if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


def wait_for_path(path: Path, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while not path.exists():
        if time.monotonic() >= deadline:
            raise TimeoutError(f"Timed out waiting for {path}")
        time.sleep(0.02)


def read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def pid_is_alive(pid: int) -> bool:
    try:
        handle = win32api.OpenProcess(win32con.PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    except pywintypes.error as exc:
        if exc.winerror in {winerror.ERROR_INVALID_PARAMETER, winerror.ERROR_NOT_FOUND}:
            return False
        raise
    try:
        return win32process.GetExitCodeProcess(handle) == win32con.STILL_ACTIVE
    finally:
        win32api.CloseHandle(handle)


class WindowsOnlyTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if sys.platform != "win32":
            raise unittest.SkipTest("Windows-only runner test")
