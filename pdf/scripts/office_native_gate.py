#!/usr/bin/env python3
"""Fail-closed native Microsoft Office acceptance gate.

The gate is deliberately separate from OfficeCLI.  OfficeCLI is useful for
static inspection and diagnostic previews, but only this module can produce
native-open/native-export evidence.  The Office skills share a baseline CLI
and safety contract, with format-specific implementations.  This PDF copy
retains the compatibility entry point for Office source documents.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterator, Sequence


STATUSES = {
    "PASS",
    "FAIL_OPEN",
    "FAIL_RENDER",
    "APP_UNAVAILABLE",
    "UNVERIFIED",
    "UNSAFE_PROCESS",
}

FORMAT_SPECS = {
    "pptx": {
        "extensions": {".pptx", ".potx"},
        "process": "POWERPNT.EXE",
        "progid": "PowerPoint.Application",
        "collection": "Presentations",
    },
    "docx": {
        "extensions": {".docx", ".dotx", ".dotm"},
        "process": "WINWORD.EXE",
        "progid": "Word.Application",
        "collection": "Documents",
    },
    "xlsx": {
        "extensions": {".xlsx", ".xlsm", ".xltx"},
        "process": "EXCEL.EXE",
        "progid": "Excel.Application",
        "collection": "Workbooks",
    },
}

APP_UNAVAILABLE_HRESULTS = {
    0x80040154,  # REGDB_E_CLASSNOTREG
    -2147221164,
    0x800401F3,  # CO_E_CLASSSTRING
    -2147221005,
}


PID_OBSERVATION_TIMEOUT_SECONDS = 5.0
PROCESS_EXIT_TIMEOUT_SECONDS = 10.0
PROCESS_POLL_SECONDS = 0.1


class GateFailure(RuntimeError):
    """A failure with an explicit stage and release-facing status."""

    def __init__(
        self,
        status: str,
        phase: str,
        message: str,
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        if status not in STATUSES:
            raise ValueError(f"unknown native gate status: {status}")
        super().__init__(message)
        self.status = status
        self.phase = phase
        self.message = message
        self.details = details or {}


class ActivationFailure(RuntimeError):
    """COM activation failed before an Office document was opened."""


class OwnershipFailure(RuntimeError):
    """The task cannot prove exclusive ownership of an Office instance."""

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.details = details or {}



class StageFailure(GateFailure):
    """A document open or native export failed."""


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def _exception_text(exc: BaseException) -> str:
    text = str(exc).strip()
    return f"{type(exc).__name__}: {text}" if text else type(exc).__name__


def _add_note(exc: BaseException, note: str) -> None:
    if hasattr(exc, "add_note"):
        exc.add_note(note)


def process_present(image_name: str) -> bool:
    """Check the exact Office image without touching COM."""

    return bool(_process_ids(image_name))



def _process_ids(image_name: str) -> list[int]:
    """Return PIDs for one exact image name without terminating anything."""

    creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        result = subprocess.run(
            [
                "tasklist.exe",
                "/FI",
                f"IMAGENAME eq {image_name}",
                "/FO",
                "CSV",
                "/NH",
            ],
            capture_output=True,
            check=False,
            creationflags=creation_flags,
        )
    except OSError as exc:
        raise RuntimeError(f"unable to inspect {image_name}: {exc}") from exc
    if result.returncode != 0:
        stderr = (result.stderr or b"").decode("utf-8", errors="replace")
        raise RuntimeError(f"tasklist failed for {image_name}: {stderr.strip()}")
    stdout = result.stdout or b""
    if isinstance(stdout, str):
        rows = stdout.splitlines()
    else:
        rows = stdout.decode("utf-8", errors="replace").splitlines()
    wanted = image_name.lower()
    pids: list[int] = []
    for row in csv.reader(rows):
        if not row or row[0].strip().lower() != wanted:
            continue
        if len(row) < 2:
            raise RuntimeError(f"tasklist returned a missing PID for {image_name}")
        try:
            pid = int(row[1].strip())
        except ValueError as exc:
            raise RuntimeError(f"tasklist returned an invalid PID for {image_name}") from exc
        if pid <= 0:
            raise RuntimeError(f"tasklist returned a non-positive PID for {image_name}")
        pids.append(pid)
    return sorted(set(pids))



def _safe_process_ids(
    image_name: str,
    *,
    process_ids: Callable[[str], list[int]] | None = None,
) -> tuple[list[int] | None, str | None]:
    try:
        probe = process_ids or _process_ids
        return sorted({int(pid) for pid in probe(image_name)}), None
    except Exception as exc:
        return None, _exception_text(exc)



def _observe_owned_processes(
    image_name: str,
    pre_dispatch_pids: list[int],
    *,
    process_ids: Callable[[str], list[int]] | None = None,
    timeout_seconds: float = PID_OBSERVATION_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Identify PIDs created after DispatchEx without guessing from COM alone."""

    started = time.monotonic()
    deadline = started + timeout_seconds
    last: list[int] = []
    while True:
        current, error = _safe_process_ids(image_name, process_ids=process_ids)
        elapsed = time.monotonic() - started
        if current is None:
            return {
                "status": "UNOBSERVED",
                "image": image_name,
                "pre_dispatch_pids": pre_dispatch_pids,
                "observed_pids": last,
                "owned_pids": [],
                "wait_seconds": elapsed,
                "timeout_seconds": timeout_seconds,
                "error": error,
            }
        last = current
        owned = sorted(set(current) - set(pre_dispatch_pids))
        if owned:
            return {
                "status": "OBSERVED",
                "image": image_name,
                "pre_dispatch_pids": pre_dispatch_pids,
                "observed_pids": current,
                "owned_pids": owned,
                "wait_seconds": elapsed,
                "timeout_seconds": timeout_seconds,
            }
        if time.monotonic() >= deadline:
            return {
                "status": "NO_NEW_PID",
                "image": image_name,
                "pre_dispatch_pids": pre_dispatch_pids,
                "observed_pids": current,
                "owned_pids": [],
                "wait_seconds": elapsed,
                "timeout_seconds": timeout_seconds,
            }
        time.sleep(min(PROCESS_POLL_SECONDS, max(0.0, deadline - time.monotonic())))



def _wait_for_owned_processes_exit(
    image_name: str,
    owned_pids: list[int] | None,
    *,
    process_ids: Callable[[str], list[int]] | None = None,
    timeout_seconds: float = PROCESS_EXIT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Wait for task-owned Office PIDs; never force-terminate residual PIDs."""

    started = time.monotonic()
    if not owned_pids:
        return {
            "status": "UNOBSERVED",
            "image": image_name,
            "owned_pids": [],
            "residual_pids": [],
            "wait_seconds": time.monotonic() - started,
            "timeout_seconds": timeout_seconds,
        }
    deadline = started + timeout_seconds
    last: list[int] = list(owned_pids)
    while True:
        current, error = _safe_process_ids(image_name, process_ids=process_ids)
        elapsed = time.monotonic() - started
        if current is None:
            return {
                "status": "UNOBSERVED",
                "image": image_name,
                "owned_pids": owned_pids,
                "residual_pids": last,
                "wait_seconds": elapsed,
                "timeout_seconds": timeout_seconds,
                "error": error,
            }
        last = sorted(set(current) & set(owned_pids))
        if not last:
            return {
                "status": "CLEAN",
                "image": image_name,
                "owned_pids": owned_pids,
                "residual_pids": [],
                "wait_seconds": elapsed,
                "timeout_seconds": timeout_seconds,
            }
        if time.monotonic() >= deadline:
            return {
                "status": "RESIDUAL_PIDS",
                "image": image_name,
                "owned_pids": owned_pids,
                "residual_pids": last,
                "wait_seconds": elapsed,
                "timeout_seconds": timeout_seconds,
            }
        time.sleep(min(PROCESS_POLL_SECONDS, max(0.0, deadline - time.monotonic())))



def default_dispatch_ex(progid: str) -> Any:
    from win32com.client import DispatchEx

    return DispatchEx(progid)


def default_com_runtime() -> Any:
    import pythoncom

    return pythoncom


def _is_app_unavailable(exc: BaseException) -> bool:
    hresult = getattr(exc, "hresult", None)
    if hresult in APP_UNAVAILABLE_HRESULTS:
        return True
    text = str(exc).lower()
    return any(
        marker in text
        for marker in (
            "class not registered",
            "invalid class string",
            "regdb_e_classnotreg",
            "co_e_classstring",
        )
    )


def _collection_count(application: Any, collection_name: str) -> int:
    try:
        collection = getattr(application, collection_name)
        return int(collection.Count)
    except Exception as exc:
        raise OwnershipFailure(
            f"unable to verify {collection_name}.Count; Office instance ownership is unknown"
        ) from exc


def _set_required(application: Any, name: str, value: Any) -> None:
    try:
        setattr(application, name, value)
    except Exception as exc:
        raise OwnershipFailure(
            f"unable to configure isolated Office instance property {name}"
        ) from exc


def _set_optional(application: Any, name: str, value: Any) -> None:
    try:
        setattr(application, name, value)
    except Exception:
        pass


@dataclass
class OwnedApplication:
    application: Any
    collection_name: str
    created_by_task: bool = True
    exclusive_at_start: bool = False
    quit_performed: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


def quit_owned_application(owner: OwnedApplication) -> None:
    """Quit only a task-created instance whose document collection is empty."""

    if not owner.created_by_task or not owner.exclusive_at_start:
        raise OwnershipFailure(
            "Office instance ownership is not proven; Application.Quit() is refused"
        )
    count = _collection_count(owner.application, owner.collection_name)
    if count != 0:
        raise OwnershipFailure(
            f"{owner.collection_name} still contains {count} document(s); Application.Quit() is refused"
        )
    try:
        owner.application.Quit()
    except Exception as exc:
        raise OwnershipFailure("Application.Quit() failed; instance ownership is no longer safe") from exc
    owner.quit_performed = True
    owner.created_by_task = False


@contextmanager
def owned_application(
    spec: dict[str, Any],
    *,
    dispatch_ex: Callable[[str], Any] | None = None,
    com_runtime: Any | None = None,
    process_ids: Callable[[str], list[int]] | None = None,
    pid_observation_timeout_seconds: float = PID_OBSERVATION_TIMEOUT_SECONDS,
    process_exit_timeout_seconds: float = PROCESS_EXIT_TIMEOUT_SECONDS,
    ownership_metadata: dict[str, Any] | None = None,
) -> Iterator[tuple[Any, OwnedApplication]]:
    """Create one isolated COM instance and retain PID ownership evidence."""

    runtime = com_runtime or default_com_runtime()
    dispatch = dispatch_ex or default_dispatch_ex
    metadata = ownership_metadata if ownership_metadata is not None else {}
    metadata.update(
        {
            "process_image": spec["process"],
            "activation_attempted": False,
            "activation_succeeded": False,
        }
    )
    runtime.CoInitialize()
    owner: OwnedApplication | None = None
    operation_error: BaseException | None = None
    try:
        before_pids, before_error = _safe_process_ids(spec["process"], process_ids=process_ids)
        metadata["pre_dispatch_pids"] = before_pids or []
        if before_error:
            metadata["pid_observation"] = {
                "status": "UNOBSERVED",
                "image": spec["process"],
                "pre_dispatch_pids": [],
                "owned_pids": [],
                "error": before_error,
            }
            metadata["cleanup"] = {"status": "NOT_ATTEMPTED", "reason": "PID probe failed before activation"}
            raise OwnershipFailure(
                f"cannot prove that {spec['process']} is absent before DispatchEx: {before_error}",
                details={"ownership": metadata},
            )
        if before_pids:
            metadata["pid_observation"] = {
                "status": "PREEXISTING_PIDS",
                "image": spec["process"],
                "pre_dispatch_pids": before_pids,
                "owned_pids": [],
            }
            metadata["cleanup"] = {"status": "NOT_ATTEMPTED", "reason": "Office appeared before activation"}
            raise OwnershipFailure(
                f"{spec['process']} appeared before DispatchEx; exclusive ownership cannot be proven",
                details={"ownership": metadata},
            )
        try:
            metadata["activation_attempted"] = True
            application = dispatch(spec["progid"])
        except Exception as exc:
            raise ActivationFailure(_exception_text(exc)) from exc
        metadata["activation_succeeded"] = True
        owner = OwnedApplication(application, spec["collection"], metadata=metadata)
        observation = _observe_owned_processes(
            spec["process"],
            before_pids,
            process_ids=process_ids,
            timeout_seconds=pid_observation_timeout_seconds,
        )
        metadata["pid_observation"] = observation
        metadata["owned_pids"] = observation.get("owned_pids", [])
        if observation["status"] != "OBSERVED":
            metadata["cleanup"] = {
                "status": "NOT_ATTEMPTED",
                "reason": "task-owned Office PID was not observed",
                "pid_exit": None,
            }
            raise OwnershipFailure(
                "DispatchEx returned an Office object but task-owned process PID was not observed",
                details={"ownership": metadata},
            )
        initial_count = _collection_count(application, spec["collection"])
        if initial_count != 0:
            metadata["cleanup"] = {
                "status": "NOT_ATTEMPTED",
                "reason": f"{spec['collection']} was not empty at activation",
                "pid_exit": None,
            }
            raise OwnershipFailure(
                f"new {spec['progid']} instance already has {initial_count} open document(s); "
                "exclusive ownership cannot be proven",
                details={"ownership": metadata},
            )
        owner.exclusive_at_start = True

        _set_required(application, "Visible", False)
        _set_optional(application, "DisplayAlerts", 0)
        _set_optional(application, "ScreenUpdating", False)
        if spec["progid"] in {"Excel.Application", "Word.Application"}:
            _set_optional(application, "AutomationSecurity", 3)
        if spec["progid"] == "Excel.Application":
            _set_optional(application, "AskToUpdateLinks", False)
            _set_optional(application, "EnableEvents", False)
            _set_optional(application, "Calculation", -4135)  # xlCalculationManual
        yield application, owner
    except BaseException as exc:
        operation_error = exc
        raise
    finally:
        if owner is not None:
            if owner.exclusive_at_start:
                quit_error: str | None = None
                try:
                    quit_owned_application(owner)
                    owner.metadata["quit"] = {"status": "QUIT"}
                except Exception as cleanup_error:
                    quit_error = _exception_text(cleanup_error)
                    owner.metadata["quit"] = {"status": "QUIT_FAILED", "error": quit_error}
                    if operation_error is not None:
                        _add_note(operation_error, f"Office COM cleanup also failed: {quit_error}")
                owned_pids = owner.metadata.get("owned_pids")
                pid_exit = _wait_for_owned_processes_exit(
                    owner.metadata.get("process_image", "Office"),
                    owned_pids if isinstance(owned_pids, list) else None,
                    process_ids=process_ids,
                    timeout_seconds=process_exit_timeout_seconds,
                )
                owner.metadata["cleanup"] = {
                    "status": "QUIT_FAILED" if quit_error else pid_exit["status"],
                    "quit": owner.metadata["quit"],
                    "pid_exit": pid_exit,
                }
            elif "cleanup" not in owner.metadata:
                owner.metadata["cleanup"] = {
                    "status": "NOT_ATTEMPTED",
                    "reason": "exclusive Office ownership was not proven",
                }
        try:
            runtime.CoUninitialize()
        except Exception as cleanup_error:
            metadata["com_uninitialize"] = {"status": "FAILED", "error": _exception_text(cleanup_error)}
            if operation_error is None:
                raise OwnershipFailure(
                    f"COM uninitialization failed: {_exception_text(cleanup_error)}",
                    details={"ownership": metadata},
                ) from cleanup_error
            _add_note(operation_error, f"COM uninitialization also failed: {_exception_text(cleanup_error)}")



def _new_output(path: Path) -> Path:
    if path.exists():
        raise StageFailure(
            "FAIL_RENDER",
            "render",
            f"refusing to overwrite existing native export: {path}",
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _verify_files(directory: Path, pattern: str, expected: int) -> list[Path]:
    files = sorted(directory.glob(pattern))
    if len(files) != expected:
        raise StageFailure(
            "FAIL_RENDER",
            "render",
            f"native export produced {len(files)} file(s), expected {expected}",
            details={"pattern": pattern, "expected": expected, "actual": len(files)},
        )
    for path in files:
        try:
            size = path.stat().st_size
        except OSError as exc:
            raise StageFailure("FAIL_RENDER", "render", f"cannot inspect native export {path}: {exc}") from exc
        if size <= 0:
            raise StageFailure("FAIL_RENDER", "render", f"native export is empty: {path}")
    return files


def _open_pptx(application: Any, path: Path) -> Any:
    try:
        return application.Presentations.Open(str(path), True, False, False)
    except Exception as exc:
        raise StageFailure("FAIL_OPEN", "open", f"PowerPoint could not open isolated copy: {_exception_text(exc)}") from exc


def _open_docx(application: Any, path: Path) -> Any:
    try:
        return application.Documents.Open(str(path), False, True, False)
    except Exception as exc:
        raise StageFailure("FAIL_OPEN", "open", f"Word could not open isolated copy: {_exception_text(exc)}") from exc


def _open_xlsx(application: Any, path: Path) -> Any:
    try:
        return application.Workbooks.Open(str(path), 0, True)
    except Exception as exc:
        raise StageFailure("FAIL_OPEN", "open", f"Excel could not open isolated copy: {_exception_text(exc)}") from exc


def _close_document(
    document: Any,
    *,
    save_changes: bool = False,
    close_without_arguments: bool = False,
) -> None:
    try:
        if close_without_arguments:
            document.Close()
        elif save_changes:
            document.Close(True)
        else:
            document.Close(False)
    except Exception as exc:
        raise GateFailure("UNVERIFIED", "cleanup", f"could not close isolated Office document: {_exception_text(exc)}") from exc


def _render_pptx(presentation: Any, export_dir: Path, slide_count: int) -> dict[str, Any]:
    for index in range(1, slide_count + 1):
        output = _new_output(export_dir / f"slide-{index:04d}.png")
        try:
            presentation.Slides(index).Export(str(output), "PNG", 1920, 1080)
        except Exception as exc:
            raise StageFailure(
                "FAIL_RENDER",
                "render",
                f"PowerPoint failed to export slide {index}: {_exception_text(exc)}",
                details={"slide": index},
            ) from exc
    files = _verify_files(export_dir, "slide-*.png", slide_count)
    return {"export": "native_png", "expected": slide_count, "files": len(files)}


def _resolve_pdftoppm() -> Path | None:
    user_profile = os.environ.get("USERPROFILE")
    if user_profile:
        candidate = Path(user_profile) / "poppler" / "poppler-24.08.0" / "Library" / "bin" / "pdftoppm.exe"
        if candidate.is_file():
            return candidate
    located = shutil.which("pdftoppm.exe")
    return Path(located).resolve() if located else None


def rasterize_pdf(pdf_path: Path, export_dir: Path, expected_pages: int) -> dict[str, Any]:
    executable = _resolve_pdftoppm()
    if executable is None:
        raise StageFailure(
            "FAIL_RENDER",
            "rasterize",
            "pdftoppm.exe was not found; Word PDF export cannot be accepted without rasterization",
        )
    prefix = _new_output(export_dir / "page-stem")
    try:
        result = subprocess.run(
            [str(executable), "-png", "-r", "144", str(pdf_path), str(prefix)],
            capture_output=True,
            check=False,
        )
    except OSError as exc:
        raise StageFailure("FAIL_RENDER", "rasterize", f"could not start pdftoppm.exe: {exc}") from exc
    if result.returncode != 0:
        stderr = (result.stderr or b"").decode("utf-8", errors="replace")
        raise StageFailure("FAIL_RENDER", "rasterize", f"pdftoppm.exe failed: {stderr.strip()}")
    files = _verify_files(export_dir, "page-stem-*.png", expected_pages)
    return {"rasterizer": str(executable), "expected": expected_pages, "files": len(files)}


def _check_pptx(application: Any, isolated: Path, export_dir: Path, require_render: bool) -> dict[str, Any]:
    presentation = _open_pptx(application, isolated)
    primary_error: BaseException | None = None
    try:
        try:
            slide_count = int(presentation.Slides.Count)
        except Exception as exc:
            raise StageFailure("FAIL_OPEN", "open", f"PowerPoint slide collection could not be read: {_exception_text(exc)}") from exc
        if slide_count < 1:
            raise StageFailure("FAIL_OPEN", "open", "PowerPoint opened the file but reported no slides")
        result: dict[str, Any] = {"slides": slide_count, "native_open": True}
        if require_render:
            result["native_render"] = _render_pptx(presentation, export_dir, slide_count)
        return result
    except BaseException as exc:
        primary_error = exc
        raise
    finally:
        try:
            _close_document(presentation, close_without_arguments=True)
        except BaseException as close_error:
            if primary_error is None:
                raise
            _add_note(primary_error, f"PowerPoint document cleanup also failed: {_exception_text(close_error)}")


def _check_docx(
    application: Any,
    isolated: Path,
    export_dir: Path,
    require_render: bool,
    rasterizer: Callable[[Path, Path, int], dict[str, Any]],
) -> dict[str, Any]:
    document = _open_docx(application, isolated)
    primary_error: BaseException | None = None
    try:
        try:
            repaginate = getattr(document, "Repaginate", None)
            if callable(repaginate):
                repaginate()
            page_count = int(document.ComputeStatistics(2))  # wdStatisticPages
        except Exception as exc:
            raise StageFailure("FAIL_OPEN", "open", f"Word page calculation failed: {_exception_text(exc)}") from exc
        if page_count < 1:
            raise StageFailure("FAIL_OPEN", "open", "Word opened the file but reported no pages")
        result: dict[str, Any] = {"pages": page_count, "native_open": True}
        if require_render:
            pdf_path = _new_output(export_dir / "word-export.pdf")
            try:
                document.ExportAsFixedFormat(str(pdf_path), 17)  # wdExportFormatPDF
            except Exception as exc:
                raise StageFailure("FAIL_RENDER", "office_export", f"Word PDF export failed: {_exception_text(exc)}") from exc
            try:
                if not pdf_path.is_file() or pdf_path.stat().st_size <= 0:
                    raise StageFailure("FAIL_RENDER", "office_export", "Word reported success but produced an empty PDF")
            except OSError as exc:
                raise StageFailure("FAIL_RENDER", "office_export", f"cannot inspect Word PDF export: {exc}") from exc
            office_export = {"format": "pdf", "bytes": pdf_path.stat().st_size}
            native_raster = rasterizer(pdf_path, export_dir, page_count)
            result["office_export"] = office_export
            result["rasterization"] = native_raster
        return result
    except BaseException as exc:
        primary_error = exc
        raise
    finally:
        try:
            _close_document(document)
        except BaseException as close_error:
            if primary_error is None:
                raise
            _add_note(primary_error, f"Word document cleanup also failed: {_exception_text(close_error)}")


def _check_xlsx(application: Any, isolated: Path, export_dir: Path, require_render: bool) -> dict[str, Any]:
    if require_render:
        raise GateFailure(
            "UNVERIFIED",
            "preflight",
            "XLSX native gate is open-only; --require-render is not supported",
        )
    workbook = _open_xlsx(application, isolated)
    primary_error: BaseException | None = None
    try:
        try:
            sheet_count = int(workbook.Worksheets.Count)
            workbook_count = int(application.Workbooks.Count)
        except Exception as exc:
            raise StageFailure("FAIL_OPEN", "open", f"Excel workbook structure could not be read: {_exception_text(exc)}") from exc
        if sheet_count < 1:
            raise StageFailure("FAIL_OPEN", "open", "Excel opened the file but reported no worksheets")
        return {
            "workbooks": workbook_count,
            "worksheets": sheet_count,
            "native_open": True,
            "native_render": False,
            "recalculation": False,
        }
    except BaseException as exc:
        primary_error = exc
        raise
    finally:
        try:
            _close_document(workbook)
        except BaseException as close_error:
            if primary_error is None:
                raise
            _add_note(primary_error, f"Excel workbook cleanup also failed: {_exception_text(close_error)}")


def _base_result(source: Path, format_name: str, before: str | None = None) -> dict[str, Any]:
    return {
        "ok": False,
        "status": "UNVERIFIED",
        "format": format_name,
        "file": str(source),
        "phase": "preflight",
        "source_sha256_before": before,
        "source_sha256_after": None,
        "details": {},
    }


def _record_cleanup_uncertainty(result: dict[str, Any], record: dict[str, Any]) -> None:
    """Downgrade an activated Office run when cleanup cannot be proven complete."""

    details = result.setdefault("details", {})
    if "prior_result" not in details:
        details["prior_result"] = {
            "ok": result.get("ok"),
            "status": result.get("status"),
            "phase": result.get("phase"),
            "error": result.get("error"),
            "details": dict(details),
        }
    failures = details.setdefault("cleanup_uncertainties", [])
    if isinstance(failures, list):
        failures.append(record)
    result["ok"] = False
    result["status"] = "UNVERIFIED"
    result["phase"] = "cleanup"
    result["error"] = "Office native gate cleanup is not proven complete; result is unverified"



def check_file(
    file_path: str | Path,
    format_name: str,
    *,
    allow_office_com: bool = False,
    require_render: bool = False,
    process_probe: Callable[[str], bool] | None = None,
    process_ids: Callable[[str], list[int]] | None = None,
    dispatch_ex: Callable[[str], Any] | None = None,
    com_runtime: Any | None = None,
    rasterizer: Callable[[Path, Path, int], dict[str, Any]] | None = None,
    pid_observation_timeout_seconds: float = PID_OBSERVATION_TIMEOUT_SECONDS,
    process_exit_timeout_seconds: float = PROCESS_EXIT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Run a native gate; dependency injection keeps tests off real COM."""

    format_name = str(format_name).lower()
    source = Path(file_path).expanduser().resolve()
    result = _base_result(source, format_name)
    spec = FORMAT_SPECS.get(format_name)
    if spec is None:
        result["error"] = f"unsupported format: {format_name}"
        return result
    if not source.is_file():
        result["error"] = f"input file not found: {source}"
        return result
    try:
        before = sha256(source)
    except OSError as exc:
        result["error"] = f"cannot hash input: {_exception_text(exc)}"
        return result
    result["source_sha256_before"] = before
    if source.suffix.lower() not in spec["extensions"]:
        result["error"] = f"--format {format_name} does not match input extension {source.suffix.lower()}"
        result["source_sha256_after"] = before
        return result
    if not allow_office_com:
        result["error"] = "native Office gate is disabled; pass --allow-office-com for this operation"
        result["source_sha256_after"] = before
        return result
    if format_name == "xlsx" and require_render:
        result["error"] = "XLSX native gate is open-only; --require-render is not supported"
        result["source_sha256_after"] = before
        return result

    ownership: dict[str, Any] = {"process_image": spec["process"], "activation_attempted": False, "activation_succeeded": False}
    result["ownership"] = ownership
    workspace: Path | None = None
    try:
        preflight_pids, preflight_error = _safe_process_ids(spec["process"], process_ids=process_ids)
        if preflight_pids is None:
            ownership["preflight"] = {
                "status": "UNOBSERVED",
                "process_image": spec["process"],
                "pids": [],
                "error": preflight_error,
            }
            result["error"] = f"cannot prove that {spec['process']} is absent: {preflight_error}"
            return result
        ownership["preflight"] = {
            "status": "PREEXISTING_PIDS" if preflight_pids else "ABSENT",
            "process_image": spec["process"],
            "pids": preflight_pids,
        }
        if preflight_pids:
            result["status"] = "UNSAFE_PROCESS"
            result["error"] = f"{spec['process']} is already running; refusing to start, connect to, or close Office"
            return result
        if process_probe is not None:
            try:
                probe_present = bool(process_probe(spec["process"]))
            except Exception as exc:
                ownership["legacy_process_probe"] = {"status": "UNOBSERVED", "error": _exception_text(exc)}
                result["error"] = f"cannot prove that {spec['process']} is absent: {_exception_text(exc)}"
                return result
            ownership["legacy_process_probe"] = {"status": "PRESENT" if probe_present else "ABSENT"}
            if probe_present:
                result["status"] = "UNSAFE_PROCESS"
                result["error"] = f"{spec['process']} is already running; refusing to start, connect to, or close Office"
                return result

        workspace = Path(tempfile.mkdtemp(prefix="office-native-gate-"))
        isolated = workspace / source.name
        exports = workspace / "exports"
        if exports.exists():
            raise GateFailure("UNVERIFIED", "preflight", f"refusing to reuse existing native output directory: {exports}")
        exports.mkdir()
        shutil.copy2(source, isolated)
        after_copy = sha256(source)
        if after_copy != before or sha256(isolated) != before:
            raise GateFailure("UNVERIFIED", "preflight", "source changed while creating the isolated copy")

        with owned_application(
            spec,
            dispatch_ex=dispatch_ex,
            com_runtime=com_runtime,
            process_ids=process_ids,
            pid_observation_timeout_seconds=pid_observation_timeout_seconds,
            process_exit_timeout_seconds=process_exit_timeout_seconds,
            ownership_metadata=ownership,
        ) as (application, _owner):
            if format_name == "pptx":
                details = _check_pptx(application, isolated, exports, require_render)
            elif format_name == "docx":
                details = _check_docx(application, isolated, exports, require_render, rasterizer or rasterize_pdf)
            else:
                details = _check_xlsx(application, isolated, exports, require_render)
        result.update({"ok": True, "status": "PASS", "phase": "render" if require_render else "open", "details": details})
    except ActivationFailure as exc:
        if _is_app_unavailable(exc.__cause__ or exc):
            result["status"] = "APP_UNAVAILABLE"
        result["phase"] = "activate"
        result["error"] = str(exc)
    except OwnershipFailure as exc:
        result["phase"] = "ownership"
        result["error"] = _exception_text(exc)
        if exc.details:
            supplied_ownership = exc.details.get("ownership")
            if isinstance(supplied_ownership, dict):
                result["ownership"] = supplied_ownership
            result["details"].update({key: value for key, value in exc.details.items() if key != "ownership"})
    except GateFailure as exc:
        result["status"] = exc.status
        result["phase"] = exc.phase
        result["error"] = exc.message
        result["details"].update(exc.details)
    except ModuleNotFoundError as exc:
        result["phase"] = "activate"
        result["error"] = f"native Office runtime is unavailable in this Python environment: {_exception_text(exc)}"
    except Exception as exc:
        result["phase"] = "activate"
        result["error"] = _exception_text(exc)
    finally:
        try:
            result["source_sha256_after"] = sha256(source)
        except OSError as exc:
            result["source_sha256_after"] = None
            result["status"] = "UNVERIFIED"
            result["phase"] = "integrity"
            result["error"] = f"cannot re-hash source after native gate: {_exception_text(exc)}"
        if result["source_sha256_after"] != before:
            result["ok"] = False
            result["status"] = "UNVERIFIED"
            result["phase"] = "integrity"
            result["error"] = "source SHA-256 changed during native gate; result is unverified"
        ownership_record = result.get("ownership")
        if isinstance(ownership_record, dict) and ownership_record.get("activation_succeeded") is True:
            cleanup = ownership_record.get("cleanup")
            cleanup_status = cleanup.get("status") if isinstance(cleanup, dict) else None
            if cleanup_status != "CLEAN":
                _record_cleanup_uncertainty(
                    result,
                    {
                        "kind": "office_process",
                        "cleanup": cleanup,
                    },
                )
        # Do not remove files while an activated (or partly activated) Office
        # process may still hold them. Retain the workspace as diagnostic evidence.
        cleanup = ownership.get("cleanup")
        cleanup_status = cleanup.get("status") if isinstance(cleanup, dict) else None
        may_still_be_running = ownership.get("activation_attempted") and cleanup_status != "CLEAN"
        if workspace is not None and may_still_be_running:
            result["details"]["retained_workspace"] = str(workspace)
        elif workspace is not None:
            try:
                shutil.rmtree(workspace)
            except OSError as exc:
                _record_cleanup_uncertainty(
                    result,
                    {
                        "kind": "temporary_workspace",
                        "workspace": str(workspace),
                        "error": _exception_text(exc),
                    },
                )
    return result



def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Fail-closed native Microsoft Office acceptance gate")
    subparsers = parser.add_subparsers(dest="operation", required=True)
    check = subparsers.add_parser("check", help="open an isolated Office copy and optionally export it")
    check.add_argument("file")
    check.add_argument("--format", required=True, choices=tuple(FORMAT_SPECS))
    check.add_argument("--json", action="store_true", help="emit one machine-readable JSON result")
    check.add_argument("--allow-office-com", action="store_true")
    check.add_argument("--require-render", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = check_file(
        args.file,
        args.format,
        allow_office_com=args.allow_office_com,
        require_render=args.require_render,
    )
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"{result['status']} [{result['phase']}]: {result.get('error', 'native gate passed')}")
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
