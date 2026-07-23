"""Safe, isolated LibreOffice operations for Windows-based agent workflows."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import tempfile
import time
import uuid
import zipfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable
from xml.etree import ElementTree

from .cleanup import _remove_without_reparse_points, cleanup_abandoned
from .publish import OutputExistsError, PublishError, publish_exclusive
from .win32_job import JobProcess, JobSetupError, launch_suspended_in_job
from .win32_sync import CapacitySlots, FileLock, RUNNER_ID, current_process_identity, default_state_root


RUNNER_VERSION = "0.1.0"
_OFFICE_XML_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_PDF_SOURCES = {
    ".doc": "pdf:writer_pdf_Export",
    ".docx": "pdf:writer_pdf_Export",
    ".odt": "pdf:writer_pdf_Export",
    ".xls": "pdf:calc_pdf_Export",
    ".xlsx": "pdf:calc_pdf_Export",
    ".xlsm": "pdf:calc_pdf_Export",
    ".xltx": "pdf:calc_pdf_Export",
    ".odp": "pdf:impress_pdf_Export",
    ".ppt": "pdf:impress_pdf_Export",
    ".pptx": "pdf:impress_pdf_Export",
}


class RunFailure(RuntimeError):
    def __init__(self, error: str, message: str, execution: dict[str, object] | None = None) -> None:
        super().__init__(message)
        self.error = error
        self.execution = execution


@dataclass(frozen=True)
class RunRequest:
    operation: str
    source: Path
    output: Path
    soffice: Path | None = None
    queue_timeout: float = 600.0
    run_timeout: float = 120.0
    convert_to: str | None = None
    keep_diagnostics_on_error: bool = False


@dataclass
class RunReport:
    ok: bool
    operation: str
    source: str
    output: str
    source_sha256: str | None = None
    output_sha256: str | None = None
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""
    libreoffice: str | None = None
    queue_seconds: float = 0.0
    run_seconds: float = 0.0
    root_pid: int | None = None
    owned_pids: list[int] | None = None
    error: str | None = None
    message: str | None = None
    diagnostics: str | None = None
    command: list[str] | None = None
    validation: dict[str, object] | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class _PreparedRequest:
    request: RunRequest
    source: Path
    output: Path
    source_suffix: str
    expected_suffix: str
    convert_to: str | None


def find_soffice(explicit: Path | None) -> Path:
    if explicit is not None:
        candidate = explicit.expanduser().resolve()
        if candidate.is_file():
            return candidate
        raise FileNotFoundError(candidate)
    candidates = [
        shutil.which("soffice.com"),
        shutil.which("soffice.exe"),
        shutil.which("soffice"),
        r"C:\Program Files\LibreOffice\program\soffice.com",
        r"C:\Program Files\LibreOffice\program\soffice.exe",
        r"C:\Program Files (x86)\LibreOffice\program\soffice.com",
        r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return Path(candidate).resolve()
    raise FileNotFoundError("LibreOffice soffice executable was not found")


def run(request: RunRequest) -> RunReport:
    """Run one operation without using the default LibreOffice user profile."""

    prepared: _PreparedRequest | None = None
    source_text = str(request.source.expanduser())
    output_text = str(request.output.expanduser())
    try:
        prepared = _prepare(request)
        source_text = str(prepared.source)
        output_text = str(prepared.output)
        if prepared.output.exists():
            return _failure(prepared, "output_exists", f"Output already exists: {prepared.output}")
        try:
            soffice = find_soffice(request.soffice)
        except FileNotFoundError as exc:
            return _failure(prepared, "job_setup_failed", str(exc))
        queue_started = time.monotonic()
        try:
            lease = CapacitySlots().acquire(request.queue_timeout)
        except Exception as exc:
            return _failure(prepared, "capacity_acquire_failed", str(exc), queue_seconds=time.monotonic() - queue_started)
        queue_seconds = time.monotonic() - queue_started
        if lease is None:
            return _failure(prepared, "queue_timeout", "Timed out waiting for LibreOffice capacity", queue_seconds=queue_seconds)
        with lease:
            if prepared.output.exists():
                return _failure(prepared, "output_exists", f"Output already exists: {prepared.output}", queue_seconds=queue_seconds)
            return _run_owned(prepared, soffice, queue_seconds)
    except RunFailure as exc:
        if prepared is not None:
            return _failure(prepared, exc.error, str(exc))
        return RunReport(False, request.operation, source_text, output_text, error=exc.error, message=str(exc))
    except Exception as exc:
        if prepared is not None:
            return _failure(prepared, "job_setup_failed", str(exc))
        return RunReport(False, request.operation, source_text, output_text, error="job_setup_failed", message=str(exc))


def convert(
    mode: str,
    source: Path,
    output: Path,
    soffice: Path | None = None,
    timeout: int = 120,
) -> dict[str, object]:
    """Compatibility wrapper for the local xlsx skill's historical API."""

    report = run(
        RunRequest(
            operation=mode,
            source=Path(source),
            output=Path(output),
            soffice=Path(soffice) if soffice is not None else None,
            run_timeout=float(timeout),
        )
    )
    if not report.ok:
        _raise_compatibility_error(report)
    result = report.to_dict()
    result["mode"] = mode
    return result


def _prepare(request: RunRequest) -> _PreparedRequest:
    source = request.source.expanduser().resolve()
    output = request.output.expanduser().resolve()
    if not source.is_file():
        raise RunFailure("input_not_found", f"Input does not exist: {source}")
    if source == output:
        raise RunFailure("unsupported_format", "Source and output paths must differ")
    if request.queue_timeout < 0 or request.run_timeout <= 0:
        raise RunFailure("unsupported_format", "Timeout values must be non-negative and run_timeout must be positive")
    source_suffix = source.suffix.lower()
    output_suffix = output.suffix.lower()
    operation = request.operation
    if operation == "pdf":
        if output_suffix != ".pdf" or source_suffix not in _PDF_SOURCES:
            raise RunFailure("unsupported_format", "PDF operation does not support these source/output extensions")
        return _PreparedRequest(request, source, output, source_suffix, ".pdf", _PDF_SOURCES[source_suffix])
    if operation == "recalc":
        if source_suffix not in {".xlsx", ".xltx"} or output_suffix != ".xlsx":
            raise RunFailure("unsupported_format", "Recalc supports .xlsx or .xltx input and .xlsx output")
        return _PreparedRequest(request, source, output, source_suffix, ".xlsx", "xlsx:Calc MS Excel 2007 XML")
    if operation == "convert":
        if not request.convert_to or not output_suffix:
            raise RunFailure("unsupported_format", "Convert requires --convert-to and an output extension")
        return _PreparedRequest(request, source, output, source_suffix, output_suffix, request.convert_to)
    if operation == "accept-changes":
        if source_suffix != ".docx" or output_suffix != ".docx":
            raise RunFailure("unsupported_format", "accept-changes supports .docx input and .docx output")
        return _PreparedRequest(request, source, output, source_suffix, ".docx", None)
    raise RunFailure("unsupported_format", f"Unsupported operation: {operation}")


def _run_owned(prepared: _PreparedRequest, soffice: Path, queue_seconds: float) -> RunReport:
    run_started = time.monotonic()
    root = _new_task_root()
    task_id = root.name.removeprefix("sanan-lo-")
    active_lock: FileLock | None = None
    report: RunReport | None = None
    owner: dict[str, object] | None = None
    execution: dict[str, object] | None = None
    try:
        identity = current_process_identity()
        active_lock = FileLock.acquire(root / "active.lock")
        owner = {
            "runner_id": RUNNER_ID,
            "schema_version": 1,
            "runner_version": RUNNER_VERSION,
            "task_id": task_id,
            "runner_pid": identity["pid"],
            "runner_created_at": identity["created_at"],
            "started_at": _utc_now(),
            "state": "starting",
        }
        _write_json(root / "owner.json", owner)
        input_dir = root / "input"
        output_dir = root / "output"
        profile_dir = root / "profile"
        diagnostics_dir = root / "diagnostics"
        for directory in (input_dir, output_dir, profile_dir, diagnostics_dir):
            directory.mkdir()
        input_copy = input_dir / prepared.source.name
        shutil.copy2(prepared.source, input_copy)
        source_sha = _sha256(input_copy)
        generated = input_copy.with_suffix(prepared.expected_suffix)
        generated = output_dir / generated.name
        if prepared.request.operation == "accept-changes":
            execution = _accept_changes(prepared, soffice, root, input_copy, generated, diagnostics_dir, owner)
        else:
            command = _conversion_command(prepared, soffice, profile_dir, input_copy, output_dir)
            execution = _run_conversion(command, root, diagnostics_dir, owner, prepared.request.run_timeout)
        validation = _validate_generated(generated, prepared.expected_suffix, input_copy, prepared.request.operation)
        publish_exclusive(
            generated,
            prepared.output,
            lambda candidate: _validate_generated(
                candidate,
                prepared.expected_suffix,
                input_copy,
                prepared.request.operation,
            ),
        )
        owner.update({"state": "complete", "completed_at": _utc_now()})
        _write_json(root / "owner.json", owner)
        report = RunReport(
            ok=True,
            operation=prepared.request.operation,
            source=str(prepared.source),
            output=str(prepared.output),
            source_sha256=source_sha,
            output_sha256=_sha256(prepared.output),
            exit_code=execution["exit_code"],
            stdout=execution["stdout"],
            stderr=execution["stderr"],
            libreoffice=str(soffice),
            queue_seconds=queue_seconds,
            run_seconds=time.monotonic() - run_started,
            root_pid=execution["root_pid"],
            owned_pids=execution["owned_pids"],
            command=execution["command"],
            validation=validation,
        )
        return report
    except RunFailure as exc:
        report = _failure(
            prepared,
            exc.error,
            str(exc),
            queue_seconds=queue_seconds,
            run_seconds=time.monotonic() - run_started,
            execution=exc.execution or execution,
            libreoffice=soffice,
        )
        return report
    except OutputExistsError as exc:
        report = _failure(
            prepared,
            "output_exists",
            str(exc),
            queue_seconds=queue_seconds,
            run_seconds=time.monotonic() - run_started,
            execution=execution,
            libreoffice=soffice,
        )
        return report
    except PublishError as exc:
        report = _failure(
            prepared,
            "publish_failed",
            str(exc),
            queue_seconds=queue_seconds,
            run_seconds=time.monotonic() - run_started,
            execution=execution,
            libreoffice=soffice,
        )
        return report
    except JobSetupError as exc:
        report = _failure(
            prepared,
            "job_setup_failed",
            str(exc),
            queue_seconds=queue_seconds,
            run_seconds=time.monotonic() - run_started,
            execution=execution,
            libreoffice=soffice,
        )
        return report
    except Exception as exc:
        report = _failure(
            prepared,
            "job_setup_failed",
            str(exc),
            queue_seconds=queue_seconds,
            run_seconds=time.monotonic() - run_started,
            execution=execution,
            libreoffice=soffice,
        )
        return report
    finally:
        if owner is not None and report is not None and not report.ok:
            owner.update({"state": "failed", "failed_at": _utc_now(), "error": report.error})
            _write_json(root / "owner.json", owner)
        if active_lock is not None:
            active_lock.close()
        if report is None or report.ok:
            _remove_task_root(root)
        else:
            report.diagnostics = _retain_failure_diagnostics(root, report, prepared.request.keep_diagnostics_on_error)


def _conversion_command(
    prepared: _PreparedRequest,
    soffice: Path,
    profile_dir: Path,
    input_copy: Path,
    output_dir: Path,
) -> list[str]:
    assert prepared.convert_to is not None
    return [
        str(soffice),
        "--headless",
        "--nologo",
        "--nodefault",
        "--nofirststartwizard",
        f"-env:UserInstallation={profile_dir.resolve().as_uri()}",
        "--convert-to",
        prepared.convert_to,
        "--outdir",
        str(output_dir),
        str(input_copy),
    ]


def _run_conversion(
    command: list[str],
    root: Path,
    diagnostics_dir: Path,
    owner: dict[str, object],
    run_timeout: float,
) -> dict[str, object]:
    process = launch_suspended_in_job(
        command,
        cwd=root,
        environment=dict(os.environ),
        stdout_path=diagnostics_dir / "stdout.txt",
        stderr_path=diagnostics_dir / "stderr.txt",
    )
    try:
        owner.update({"state": "running", "root_pid": process.pid, "root_created_at": _process_created_at(process.pid)})
        _write_json(root / "owner.json", owner)
        deadline = time.monotonic() + run_timeout
        if not process.wait_for_root(max(0.0, deadline - time.monotonic())):
            _terminate_and_wait(process)
            result = _job_result(process, command, diagnostics_dir, process.exit_code())
            raise RunFailure("run_timeout", "LibreOffice root process exceeded run_timeout", result)
        if not process.wait_for_empty(deadline):
            _terminate_and_wait(process)
            result = _job_result(process, command, diagnostics_dir, process.exit_code())
            raise RunFailure("run_timeout", "LibreOffice process tree exceeded run_timeout", result)
        exit_code = process.exit_code()
        if exit_code != 0:
            result = _job_result(process, command, diagnostics_dir, exit_code)
            raise RunFailure("nonzero_exit", f"LibreOffice exited with code {exit_code}", result)
        return _job_result(process, command, diagnostics_dir, exit_code)
    finally:
        _close_job_process(process)


def _accept_changes(
    prepared: _PreparedRequest,
    soffice: Path,
    root: Path,
    input_copy: Path,
    generated: Path,
    diagnostics_dir: Path,
    owner: dict[str, object],
) -> dict[str, object]:
    lo_python = soffice.parent / "python.exe"
    if not lo_python.is_file():
        raise RunFailure("job_setup_failed", f"LibreOffice Python is not available: {lo_python}")
    worker = diagnostics_dir / "accept_changes_worker.py"
    worker.write_text(_ACCEPT_CHANGES_WORKER, encoding="utf-8", newline="\n")
    profile_uri = (root / "profile").resolve().as_uri()
    pipe_name = f"sanan_lo_{uuid.uuid4().hex}"
    server_command = [
        str(soffice),
        "--headless",
        "--nologo",
        "--nodefault",
        "--nofirststartwizard",
        f"-env:UserInstallation={profile_uri}",
        f"--accept=pipe,name={pipe_name};urp;StarOffice.ComponentContext",
    ]
    worker_command = [
        str(lo_python),
        str(worker),
        input_copy.resolve().as_uri(),
        generated.resolve().as_uri(),
        pipe_name,
    ]
    server = launch_suspended_in_job(
        server_command,
        cwd=root,
        environment=dict(os.environ),
        stdout_path=diagnostics_dir / "server-stdout.txt",
        stderr_path=diagnostics_dir / "server-stderr.txt",
    )
    worker_process: JobProcess | None = None
    try:
        owner.update({"state": "running", "root_pid": server.pid, "root_created_at": _process_created_at(server.pid)})
        _write_json(root / "owner.json", owner)
        worker_process = launch_suspended_in_job(
            worker_command,
            cwd=root,
            environment=dict(os.environ),
            stdout_path=diagnostics_dir / "worker-stdout.txt",
            stderr_path=diagnostics_dir / "worker-stderr.txt",
        )
        deadline = time.monotonic() + prepared.request.run_timeout
        if not worker_process.wait_for_root(max(0.0, deadline - time.monotonic())):
            _terminate_and_wait(worker_process)
            _terminate_and_wait(server)
            result = _accept_changes_result(server, worker_process, server_command, worker_command, diagnostics_dir, worker_process.exit_code())
            raise RunFailure("run_timeout", "accept-changes worker exceeded run_timeout", result)
        if not worker_process.wait_for_empty(deadline):
            _terminate_and_wait(worker_process)
            _terminate_and_wait(server)
            result = _accept_changes_result(server, worker_process, server_command, worker_command, diagnostics_dir, worker_process.exit_code())
            raise RunFailure("run_timeout", "accept-changes worker process tree exceeded run_timeout", result)
        exit_code = worker_process.exit_code()
        if exit_code != 0:
            _terminate_and_wait(server)
            result = _accept_changes_result(server, worker_process, server_command, worker_command, diagnostics_dir, exit_code)
            raise RunFailure("nonzero_exit", f"accept-changes worker exited with code {exit_code}", result)
        # The server was itself created suspended and attached to this Job before it could spawn soffice.bin.
        _terminate_and_wait(server)
        return _accept_changes_result(server, worker_process, server_command, worker_command, diagnostics_dir, exit_code)
    finally:
        if worker_process is not None:
            _close_job_process(worker_process)
        _close_job_process(server)


def _accept_changes_result(
    server: JobProcess,
    worker: JobProcess,
    server_command: list[str],
    worker_command: list[str],
    diagnostics_dir: Path,
    exit_code: int,
) -> dict[str, object]:
    server.active_pids()
    worker.active_pids()
    stdout = _read_capture(diagnostics_dir / "server-stdout.txt") + _read_capture(diagnostics_dir / "worker-stdout.txt")
    stderr = _read_capture(diagnostics_dir / "server-stderr.txt") + _read_capture(diagnostics_dir / "worker-stderr.txt")
    return {
        "exit_code": exit_code,
        "root_pid": server.pid,
        "owned_pids": sorted(server.seen_pids | worker.seen_pids),
        "stdout": stdout,
        "stderr": stderr,
        "command": server_command + ["--uno-worker"] + worker_command,
    }


def _terminate_and_wait(process: JobProcess) -> None:
    process.terminate()
    if not process.wait_for_empty(time.monotonic() + 10.0):
        raise JobSetupError("Job Object still contains processes after termination")


def _close_job_process(process: JobProcess) -> None:
    try:
        if process.active_pids():
            _terminate_and_wait(process)
    finally:
        process.close()


def _job_result(
    process: JobProcess,
    command: list[str],
    diagnostics_dir: Path,
    exit_code: int,
) -> dict[str, object]:
    process.active_pids()
    return {
        "exit_code": exit_code,
        "root_pid": process.pid,
        "owned_pids": sorted(process.seen_pids),
        "stdout": _read_capture(diagnostics_dir / "stdout.txt"),
        "stderr": _read_capture(diagnostics_dir / "stderr.txt"),
        "command": command,
    }


def _validate_generated(path: Path, suffix: str, source: Path, operation: str) -> dict[str, object]:
    if not path.is_file() or path.stat().st_size == 0:
        raise RunFailure("no_output", f"Expected output was not created: {path.name}")
    if suffix == ".pdf":
        return _validate_pdf(path, source)
    if suffix == ".xlsx":
        return _validate_xlsx(path)
    if suffix == ".docx":
        return _validate_docx(path, require_accepted_changes=operation == "accept-changes")
    if suffix == ".pptx":
        return _validate_pptx(path)
    return {"format": suffix, "bytes": path.stat().st_size}


def _validate_pdf(path: Path, source: Path) -> dict[str, object]:
    try:
        from PyPDF2 import PdfReader
    except ImportError as exc:
        raise RunFailure("validation_unavailable", "PyPDF2 is required to validate PDF output") from exc
    try:
        with path.open("rb") as handle:
            if handle.read(5) != b"%PDF-":
                raise ValueError("missing PDF header")
        reader = PdfReader(str(path), strict=True)
        pages = len(reader.pages)
    except Exception as exc:
        raise RunFailure("corrupt_output", f"PDF validation failed: {exc}") from exc
    if pages < 1:
        raise RunFailure("corrupt_output", "PDF has no pages")
    result: dict[str, object] = {"format": "pdf", "pages": pages}
    if source.suffix.lower() == ".pptx":
        visible = _visible_pptx_slides(source)
        result["visible_slides"] = visible
        if pages != visible:
            raise RunFailure("corrupt_output", f"PPTX PDF has {pages} pages; expected {visible}")
    return result


def _validate_xlsx(path: Path) -> dict[str, object]:
    required = {"[Content_Types].xml", "xl/workbook.xml"}
    formula_count = cached_formula_count = formula_error_count = 0
    try:
        with zipfile.ZipFile(path, "r") as archive:
            if archive.testzip() is not None:
                raise ValueError("ZIP CRC check failed")
            names = set(archive.namelist())
            if not required.issubset(names) or not any(name.startswith("xl/worksheets/") for name in names):
                raise ValueError("missing required OOXML parts")
            for name in names:
                if not name.startswith("xl/worksheets/") or not name.endswith(".xml"):
                    continue
                root = ElementTree.fromstring(archive.read(name))
                for cell in root.findall(f".//{{{_OFFICE_XML_NS}}}c"):
                    formula = cell.find(f"{{{_OFFICE_XML_NS}}}f")
                    if formula is None:
                        continue
                    formula_count += 1
                    value = cell.find(f"{{{_OFFICE_XML_NS}}}v")
                    if value is None:
                        raise ValueError("formula without a cached value")
                    cached_formula_count += 1
                    if cell.attrib.get("t") == "e":
                        formula_error_count += 1
    except (OSError, zipfile.BadZipFile, ElementTree.ParseError, ValueError) as exc:
        raise RunFailure("corrupt_output", f"XLSX validation failed: {exc}") from exc
    if formula_error_count:
        raise RunFailure("corrupt_output", f"XLSX contains {formula_error_count} formula errors")
    return {
        "format": "xlsx",
        "formula_count": formula_count,
        "formula_cache_count": cached_formula_count,
        "formula_error_count": formula_error_count,
    }


def _validate_docx(path: Path, *, require_accepted_changes: bool) -> dict[str, object]:
    required = {"[Content_Types].xml", "word/document.xml"}
    try:
        with zipfile.ZipFile(path, "r") as archive:
            if archive.testzip() is not None:
                raise ValueError("ZIP CRC check failed")
            if not required.issubset(set(archive.namelist())):
                raise ValueError("missing required OOXML parts")
            document = archive.read("word/document.xml")
    except (OSError, zipfile.BadZipFile, ValueError) as exc:
        raise RunFailure("corrupt_output", f"DOCX validation failed: {exc}") from exc
    if require_accepted_changes:
        markers = (b"<w:ins", b"<w:del", b"<w:moveFrom", b"<w:moveTo")
        if any(marker in document for marker in markers):
            raise RunFailure("corrupt_output", "DOCX still contains tracked-change markup")
    return {"format": "docx", "tracked_changes_accepted": require_accepted_changes}


def _validate_pptx(path: Path) -> dict[str, object]:
    try:
        with zipfile.ZipFile(path, "r") as archive:
            if archive.testzip() is not None:
                raise ValueError("ZIP CRC check failed")
            names = set(archive.namelist())
            if "[Content_Types].xml" not in names or "ppt/presentation.xml" not in names:
                raise ValueError("missing required OOXML parts")
    except (OSError, zipfile.BadZipFile, ValueError) as exc:
        raise RunFailure("corrupt_output", f"PPTX validation failed: {exc}") from exc
    return {"format": "pptx"}


def _visible_pptx_slides(path: Path) -> int:
    try:
        with zipfile.ZipFile(path, "r") as archive:
            slide_names = sorted(
                name
                for name in archive.namelist()
                if name.startswith("ppt/slides/slide") and name.endswith(".xml")
            )
            visible = 0
            for name in slide_names:
                root = ElementTree.fromstring(archive.read(name))
                if root.attrib.get("show", "1").lower() not in {"0", "false"}:
                    visible += 1
            return visible
    except (OSError, zipfile.BadZipFile, ElementTree.ParseError) as exc:
        raise RunFailure("corrupt_output", f"Could not inspect PPTX slides: {exc}") from exc


def _new_task_root() -> Path:
    base = Path(tempfile.gettempdir()).resolve()
    for _ in range(20):
        path = base / f"sanan-lo-{uuid.uuid4()}"
        try:
            path.mkdir()
            return path
        except FileExistsError:
            continue
    raise RunFailure("job_setup_failed", "Could not create a unique LibreOffice task directory")


def _remove_task_root(path: Path) -> None:
    if path.exists():
        _remove_without_reparse_points(path)


def _retain_failure_diagnostics(root: Path, report: RunReport, keep_root: bool) -> str:
    if keep_root:
        return str(root)
    destination = default_state_root() / "diagnostics" / f"{root.name}.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    _write_json(destination, report.to_dict())
    _remove_task_root(root)
    return str(destination)


def _failure(
    prepared: _PreparedRequest,
    error: str,
    message: str,
    *,
    queue_seconds: float = 0.0,
    run_seconds: float = 0.0,
    execution: dict[str, object] | None = None,
    libreoffice: Path | None = None,
) -> RunReport:
    return RunReport(
        ok=False,
        operation=prepared.request.operation,
        source=str(prepared.source),
        output=str(prepared.output),
        exit_code=int(execution["exit_code"]) if execution and execution.get("exit_code") is not None else None,
        stdout=str(execution.get("stdout", "")) if execution else "",
        stderr=str(execution.get("stderr", "")) if execution else "",
        libreoffice=str(libreoffice) if libreoffice is not None else None,
        root_pid=int(execution["root_pid"]) if execution and execution.get("root_pid") is not None else None,
        owned_pids=list(execution.get("owned_pids", [])) if execution else None,
        command=list(execution.get("command", [])) if execution else None,
        error=error,
        message=message,
        queue_seconds=queue_seconds,
        run_seconds=run_seconds,
    )


def _raise_compatibility_error(report: RunReport) -> None:
    message = report.message or report.error or "LibreOffice conversion failed"
    if report.error == "input_not_found":
        raise FileNotFoundError(message)
    if report.error == "output_exists":
        raise FileExistsError(message)
    if report.error == "unsupported_format":
        raise ValueError(message)
    raise RuntimeError(f"LibreOffice conversion failed: {report.error}, {message}")


def _sha256(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_capture(path: Path, maximum_bytes: int = 512 * 1024) -> str:
    if not path.exists():
        return ""
    data = path.read_bytes()
    if len(data) > maximum_bytes:
        data = data[-maximum_bytes:]
        return "[truncated to final 512 KiB]\n" + data.decode("utf-8", errors="replace")
    return data.decode("utf-8", errors="replace")


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{uuid.uuid4()}")
    with temporary.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _process_created_at(pid: int) -> str | None:
    from .win32_sync import process_creation_time

    return process_creation_time(pid)


_ACCEPT_CHANGES_WORKER = r'''import json
import sys
import time

import uno


def property_value(name, value):
    item = uno.createUnoStruct("com.sun.star.beans.PropertyValue")
    item.Name = name
    item.Value = value
    return item


def main():
    source_uri, output_uri, pipe_name = sys.argv[1:]
    document = None
    desktop = None
    try:
        local_context = uno.getComponentContext()
        resolver = local_context.ServiceManager.createInstanceWithContext(
            "com.sun.star.bridge.UnoUrlResolver", local_context
        )
        remote_context = None
        deadline = time.monotonic() + 45.0
        while time.monotonic() < deadline:
            try:
                remote_context = resolver.resolve(
                    "uno:pipe,name=" + pipe_name + ";urp;StarOffice.ComponentContext"
                )
                break
            except Exception:
                time.sleep(0.1)
        if remote_context is None:
            raise RuntimeError("UNO server did not become ready")
        service_manager = remote_context.ServiceManager
        desktop = service_manager.createInstanceWithContext("com.sun.star.frame.Desktop", remote_context)
        document = desktop.loadComponentFromURL(
            source_uri,
            "_blank",
            0,
            (property_value("Hidden", True),),
        )
        if document is None:
            raise RuntimeError("LibreOffice could not load the DOCX")
        frame = document.getCurrentController().getFrame()
        dispatcher = service_manager.createInstanceWithContext("com.sun.star.frame.DispatchHelper", remote_context)
        dispatcher.executeDispatch(frame, ".uno:AcceptAllTrackedChanges", "", 0, ())
        document.storeAsURL(
            output_uri,
            (
                property_value("FilterName", "Office Open XML Text"),
                property_value("Overwrite", True),
            ),
        )
        document.close(True)
        document = None
        print(json.dumps({"ok": True, "operation": "accept-changes"}))
        return 0
    finally:
        if document is not None:
            try:
                document.close(True)
            except Exception:
                pass
if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        raise SystemExit(1)
'''


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run an isolated LibreOffice operation through the shared Windows runner")
    subparsers = parser.add_subparsers(dest="operation", required=True)
    for operation in ("pdf", "recalc", "convert", "accept-changes"):
        child = subparsers.add_parser(operation)
        child.add_argument("source", type=Path)
        child.add_argument("output", type=Path)
        child.add_argument("--soffice", type=Path)
        child.add_argument("--queue-timeout", type=float, default=600.0)
        child.add_argument("--run-timeout", type=float, default=120.0)
        child.add_argument("--json-out", type=Path)
        child.add_argument("--keep-diagnostics-on-error", action="store_true")
        if operation == "convert":
            child.add_argument("--convert-to", required=True)
    cleanup = subparsers.add_parser("cleanup")
    cleanup.add_argument("--older-than", type=float, default=24 * 60 * 60)
    cleanup.add_argument("--json-out", type=Path)
    args = parser.parse_args(list(argv) if argv is not None else None)
    if args.operation == "cleanup":
        payload = cleanup_abandoned(older_than=args.older_than)
        _emit_json(payload, args.json_out)
        return 0
    report = run(
        RunRequest(
            operation=args.operation,
            source=args.source,
            output=args.output,
            soffice=args.soffice,
            queue_timeout=args.queue_timeout,
            run_timeout=args.run_timeout,
            convert_to=getattr(args, "convert_to", None),
            keep_diagnostics_on_error=args.keep_diagnostics_on_error,
        )
    )
    _emit_json(report.to_dict(), args.json_out)
    return 0 if report.ok else 1


def _emit_json(payload: dict[str, object], json_out: Path | None) -> None:
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    if json_out is not None:
        json_out.parent.mkdir(parents=True, exist_ok=True)
        json_out.write_text(serialized + "\n", encoding="utf-8", newline="\n")
    print(serialized)
