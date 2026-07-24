#!/usr/bin/env python
"""Fail-closed ownership guard for Microsoft Word COM automation."""

from __future__ import annotations

import argparse
import csv
import subprocess
import warnings
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Callable, Iterator


class OfficeComSafetyError(RuntimeError):
    """Raised when Word COM ownership cannot be established safely."""


class OfficeComPermissionError(OfficeComSafetyError):
    """Raised when the caller did not provide per-operation permission."""


def add_office_com_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--allow-office-com",
        action="store_true",
        help=(
            "Confirm that the user explicitly approved Word COM for this operation. "
            "The script still refuses to run while WINWORD.EXE is present."
        ),
    )


def word_process_present() -> bool:
    """Check for WINWORD.EXE without connecting to Word's COM object model."""

    creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        result = subprocess.run(
            [
                "tasklist.exe",
                "/FI",
                "IMAGENAME eq WINWORD.EXE",
                "/FO",
                "CSV",
                "/NH",
            ],
            capture_output=True,
            text=True,
            check=False,
            creationflags=creation_flags,
        )
    except OSError as exc:
        raise OfficeComSafetyError(
            "Unable to verify whether WINWORD.EXE is running; Word COM is refused."
        ) from exc

    if result.returncode != 0:
        raise OfficeComSafetyError(
            "Unable to verify whether WINWORD.EXE is running; Word COM is refused."
        )

    for row in csv.reader(result.stdout.splitlines()):
        if row and row[0].strip().lower() == "winword.exe":
            return True
    return False


def require_office_com_permission(
    allow_office_com: bool,
    *,
    process_probe: Callable[[], bool] = word_process_present,
) -> None:
    """Reject before COM initialization unless permission and isolation are clear."""

    if not allow_office_com:
        raise OfficeComPermissionError(
            "Word COM is disabled by default. Obtain explicit permission for this "
            "operation, then pass --allow-office-com (or -AllowOfficeCom)."
        )

    try:
        process_present = bool(process_probe())
    except OfficeComSafetyError:
        raise
    except Exception as exc:
        raise OfficeComSafetyError(
            "Unable to verify whether WINWORD.EXE is running; Word COM is refused."
        ) from exc

    if process_present:
        raise OfficeComSafetyError(
            "WINWORD.EXE is already running. Refusing to start, connect to, or close Word."
        )


def _document_count(application: Any) -> int:
    try:
        return int(application.Documents.Count)
    except Exception as exc:
        raise OfficeComSafetyError(
            "Unable to verify Word's open-document count; Application.Quit() is refused."
        ) from exc


def _show_for_manual_recovery(application: Any) -> bool:
    try:
        application.Visible = True
        return True
    except Exception:
        return False


def _manual_recovery_status(application: Any) -> str:
    if _show_for_manual_recovery(application):
        return "The task-created instance was made visible for manual recovery."
    return "The task-created instance could not be made visibly accessible."


@dataclass
class OwnedWordApplication:
    application: Any
    created_by_this_task: bool = True
    exclusive_at_start: bool = False
    quit_performed: bool = False


def quit_owned_word_application(owner: OwnedWordApplication) -> None:
    """Quit only a task-created, initially empty, currently empty Word instance."""

    if not owner.created_by_this_task or not owner.exclusive_at_start:
        raise OfficeComSafetyError(
            "Word instance ownership is not proven; Application.Quit() is refused."
        )
    try:
        document_count = _document_count(owner.application)
    except OfficeComSafetyError:
        _show_for_manual_recovery(owner.application)
        raise
    if document_count != 0:
        raise OfficeComSafetyError(
            "Word still has open documents; Application.Quit() is refused. "
            + _manual_recovery_status(owner.application)
        )

    try:
        owner.application.Quit(False)
    except Exception as exc:
        raise OfficeComSafetyError(
            "Application.Quit() failed. "
            + _manual_recovery_status(owner.application)
        ) from exc
    owner.quit_performed = True
    owner.created_by_this_task = False


@contextmanager
def word_application(
    *,
    allow_office_com: bool = False,
    process_probe: Callable[[], bool] = word_process_present,
    com_runtime: Any | None = None,
    dispatch_ex: Callable[[str], Any] | None = None,
) -> Iterator[Any]:
    """Create and own an isolated Word instance after fail-closed preflight."""

    require_office_com_permission(
        allow_office_com,
        process_probe=process_probe,
    )

    if com_runtime is None:
        import pythoncom as com_runtime

    com_runtime.CoInitialize()
    owner: OwnedWordApplication | None = None
    operation_error: BaseException | None = None
    try:
        if dispatch_ex is None:
            from win32com.client import DispatchEx

            dispatch_ex = DispatchEx

        application = dispatch_ex("Word.Application")
        owner = OwnedWordApplication(application=application)
        try:
            initial_document_count = _document_count(application)
        except OfficeComSafetyError:
            _show_for_manual_recovery(application)
            raise
        if initial_document_count != 0:
            raise OfficeComSafetyError(
                "The new Word COM object already has open documents; exclusive ownership "
                "cannot be proven. "
                + _manual_recovery_status(application)
            )
        owner.exclusive_at_start = True

        application.Visible = False
        application.DisplayAlerts = 0
        application.ScreenUpdating = False
        yield application
    except BaseException as exc:
        operation_error = exc
        raise
    finally:
        try:
            if owner is not None and owner.exclusive_at_start:
                try:
                    owner.application.ScreenUpdating = True
                except Exception:
                    pass
                try:
                    quit_owned_word_application(owner)
                except OfficeComSafetyError as cleanup_error:
                    if operation_error is None:
                        raise
                    note = f"Word COM cleanup also failed: {cleanup_error}"
                    if hasattr(operation_error, "add_note"):
                        operation_error.add_note(note)
                    else:  # pragma: no cover - Python < 3.11
                        warnings.warn(note, RuntimeWarning, stacklevel=2)
        finally:
            com_runtime.CoUninitialize()
