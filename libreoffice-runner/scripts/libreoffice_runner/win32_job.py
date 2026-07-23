"""Job Object process-tree ownership for LibreOffice tasks on Windows."""

from __future__ import annotations

import msvcrt
import os
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

import pywintypes
import win32api
import win32con
import win32event
import win32file
import win32job
import win32process


class JobSetupError(RuntimeError):
    """The runner could not prove that its process belongs to its Job Object."""


@dataclass
class JobProcess:
    job: Any
    process: Any
    thread: Any
    pid: int
    seen_pids: set[int] = field(default_factory=set)
    closed: bool = False

    def __post_init__(self) -> None:
        self.seen_pids.add(self.pid)

    def active_pids(self) -> tuple[int, ...]:
        try:
            raw = win32job.QueryInformationJobObject(self.job, win32job.JobObjectBasicProcessIdList)
        except pywintypes.error as exc:
            raise JobSetupError(f"Could not query Job Object PIDs: {exc}") from exc
        if isinstance(raw, dict):
            values = raw.get("ProcessIdList", ())
        else:
            values = raw
        pids = tuple(int(value) for value in values)
        self.seen_pids.update(pids)
        return pids

    def wait_for_root(self, timeout: float) -> bool:
        result = win32event.WaitForSingleObject(self.process, max(0, int(timeout * 1000)))
        if result == win32con.WAIT_OBJECT_0:
            self.active_pids()
            return True
        if result == win32con.WAIT_TIMEOUT:
            self.active_pids()
            return False
        raise JobSetupError(f"WaitForSingleObject returned {result}")

    def wait_for_empty(self, deadline: float) -> bool:
        while True:
            if not self.active_pids() and not self._seen_pids_still_active():
                return True
            if time.monotonic() >= deadline:
                return False
            time.sleep(0.05)

    def _seen_pids_still_active(self) -> bool:
        for pid in self.seen_pids:
            try:
                handle = win32api.OpenProcess(win32con.PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
            except pywintypes.error:
                continue
            try:
                if win32process.GetExitCodeProcess(handle) == win32con.STILL_ACTIVE:
                    return True
            finally:
                win32api.CloseHandle(handle)
        return False

    def exit_code(self) -> int:
        return int(win32process.GetExitCodeProcess(self.process))

    def terminate(self, exit_code: int = 1) -> None:
        try:
            self.active_pids()
            win32job.TerminateJobObject(self.job, exit_code)
        except pywintypes.error as exc:
            raise JobSetupError(f"TerminateJobObject failed: {exc}") from exc

    def close(self) -> None:
        if self.closed:
            return
        try:
            win32api.CloseHandle(self.thread)
        finally:
            try:
                win32api.CloseHandle(self.process)
            finally:
                # KILL_ON_JOB_CLOSE guarantees crash cleanup if a caller exits early.
                win32api.CloseHandle(self.job)
                self.closed = True


def launch_suspended_in_job(
    command: Sequence[str],
    *,
    cwd: Path,
    environment: Mapping[str, str],
    stdout_path: Path,
    stderr_path: Path,
) -> JobProcess:
    """Create a root process suspended, own it with a Job Object, then resume it."""

    if not command:
        raise JobSetupError("Cannot launch an empty command")
    job = win32job.CreateJobObject(None, "")
    process = thread = None
    try:
        limits = win32job.QueryInformationJobObject(job, win32job.JobObjectExtendedLimitInformation)
        limits["BasicLimitInformation"]["LimitFlags"] |= win32job.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        win32job.SetInformationJobObject(job, win32job.JobObjectExtendedLimitInformation, limits)

        with _child_streams(stdout_path, stderr_path) as streams:
            startup = win32process.STARTUPINFO()
            startup.dwFlags |= win32con.STARTF_USESTDHANDLES
            startup.hStdInput = streams[0]
            startup.hStdOutput = streams[1]
            startup.hStdError = streams[2]
            process, thread, pid, _ = win32process.CreateProcess(
                str(command[0]),
                subprocess.list2cmdline([str(item) for item in command]),
                None,
                None,
                True,
                win32process.CREATE_SUSPENDED | win32process.CREATE_NO_WINDOW,
                dict(environment),
                str(cwd),
                startup,
            )
            try:
                win32job.AssignProcessToJobObject(job, process)
                if not win32job.IsProcessInJob(process, job):
                    raise JobSetupError("Root process is not attached to its Job Object")
                win32process.ResumeThread(thread)
            except Exception:
                win32process.TerminateProcess(process, 1)
                win32event.WaitForSingleObject(process, 5000)
                raise
        return JobProcess(job=job, process=process, thread=thread, pid=int(pid))
    except Exception as exc:
        if thread is not None:
            win32api.CloseHandle(thread)
        if process is not None:
            win32api.CloseHandle(process)
        win32api.CloseHandle(job)
        if isinstance(exc, JobSetupError):
            raise
        raise JobSetupError(f"Job Object setup failed: {exc}") from exc


class _child_streams:
    def __init__(self, stdout_path: Path, stderr_path: Path) -> None:
        self.stdout_path = stdout_path
        self.stderr_path = stderr_path
        self.files: list[Any] = []

    def __enter__(self) -> tuple[int, int, int]:
        self.stdout_path.parent.mkdir(parents=True, exist_ok=True)
        stdin = open(os.devnull, "rb")
        stdout = self.stdout_path.open("wb")
        stderr = self.stderr_path.open("wb")
        self.files = [stdin, stdout, stderr]
        handles: list[int] = []
        for stream in self.files:
            handle = msvcrt.get_osfhandle(stream.fileno())
            win32api.SetHandleInformation(handle, win32con.HANDLE_FLAG_INHERIT, win32con.HANDLE_FLAG_INHERIT)
            handles.append(handle)
        return tuple(handles)  # type: ignore[return-value]

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        for stream in self.files:
            stream.close()
