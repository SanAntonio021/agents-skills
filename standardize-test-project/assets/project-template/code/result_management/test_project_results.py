"""Result contract for experimental test projects. No instrument I/O."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import platform
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


RUN_KINDS = {"single_point", "scan", "dry_run", "simulation", "analysis"}
PURPOSES = {"formal", "validation", "debug"}
EXECUTION_MODES = {
    "hardware",
    "hardware_query",
    "dry_run",
    "simulation",
    "offline_replay",
    "offline_analysis",
}
FINAL_STATUSES = {
    "completed",
    "completed_with_failures",
    "failed",
    "stopped",
}
STOP_REASONS = {
    "normal_completion",
    "user_stop",
    "preflight_failed",
    "instrument_connection_failed",
    "instrument_read_failed",
    "instrument_write_failed",
    "acquisition_failed",
    "processing_failed",
    "safety_stop",
    "unhandled_exception",
}
LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR"}
UNSAFE_NAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
TIMESTAMP_PATTERN = re.compile(r"^\d{8}_\d{6}$")


@dataclass(frozen=True)
class RunPaths:
    project_root: Path
    results_root: Path
    run_kind: str
    run_id: str
    run_dir: Path
    run_info: Path
    summary: Path
    log: Path


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="milliseconds")


def now_iso() -> str:
    """Return the local ISO 8601 timestamp used by summary and log records."""
    return _now_iso()


def _timestamp(value: str | None = None) -> str:
    text = value or datetime.now().strftime("%Y%m%d_%H%M%S")
    if not TIMESTAMP_PATTERN.fullmatch(text):
        raise ValueError("timestamp must use YYYYMMDD_HHMMSS")
    return text


def _safe_name_part(value: str, label: str) -> str:
    text = str(value).strip()
    if not text or UNSAFE_NAME.search(text) or any(char.isspace() for char in text):
        raise ValueError(f"unsafe or empty {label}: {value!r}")
    return text


def format_value(value: float, precision: int) -> str:
    if not isinstance(precision, int) or not 0 <= precision <= 15:
        raise ValueError("precision must be an integer from 0 to 15")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("value must be finite")
    if abs(number) < 0.5 * 10 ** (-precision):
        number = 0.0
    return f"{number:.{precision}f}"


def format_parameter(
    symbol: str,
    value: float | Sequence[float],
    precision: int,
    unit: str,
) -> str:
    symbol = _safe_name_part(symbol, "symbol")
    unit = _safe_name_part(unit, "unit") if unit else ""
    values = [float(value)] if isinstance(value, (int, float)) else list(value)
    if len(values) not in {1, 2} or not all(math.isfinite(item) for item in values):
        raise ValueError("value must be one finite scalar or a two-element range")
    formatted = [format_value(item, precision) for item in values]
    separator = "_to_" if len(values) == 2 and any(item < 0 for item in values) else "-"
    return f"{symbol}{separator.join(formatted)}{unit}"


def point_filename(
    name_parts: str | Sequence[str],
    repeat: int,
    attempt: int,
    extension: str,
    *,
    failed: bool = False,
) -> str:
    parts = [name_parts] if isinstance(name_parts, str) else list(name_parts)
    parts = [_safe_name_part(part, "point name part") for part in parts]
    if not parts or repeat < 1 or attempt < 1:
        raise ValueError("name parts, positive repeat, and positive attempt are required")
    suffix = extension if extension.startswith(".") else f".{extension}"
    if suffix.count(".") != 1 or "/" in suffix or "\\" in suffix:
        raise ValueError("extension must contain one leading period")
    prefix = "FAILED_" if failed else ""
    return (
        f"{prefix}{'_'.join(parts)}_repeat{repeat:02d}_"
        f"attempt{attempt:02d}{suffix}"
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _git_metadata(project_root: Path) -> tuple[str | None, bool | None]:
    try:
        commit = subprocess.run(
            ["git", "-C", str(project_root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout.strip()
        dirty = bool(
            subprocess.run(
                ["git", "-C", str(project_root), "status", "--porcelain"],
                check=True,
                capture_output=True,
                text=True,
                timeout=5,
            ).stdout.strip()
        )
        return commit, dirty
    except (FileNotFoundError, subprocess.SubprocessError):
        return None, None


def _entry_metadata(project_root: Path, entry_point: str) -> dict[str, Any]:
    commit, dirty = _git_metadata(project_root)
    entry = project_root / entry_point if entry_point else None
    return {
        "git_commit": commit,
        "git_dirty": dirty,
        "entry_file_sha256": _sha256(entry) if entry and entry.is_file() else None,
    }


def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as file:
            json.dump(value, file, ensure_ascii=False, indent=2)
            file.write("\n")
            file.flush()
            os.fsync(file.fileno())
        json.loads(temporary.read_text(encoding="utf-8"))
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _merge(base: dict[str, Any], updates: Mapping[str, Any]) -> dict[str, Any]:
    for key, value in updates.items():
        if isinstance(base.get(key), dict) and isinstance(value, Mapping):
            base[key] = _merge(dict(base[key]), value)
        else:
            base[key] = value
    return base


def create_run(
    project_root: str | Path,
    run_kind: str,
    name_parts: str | Sequence[str],
    *,
    project_name: str,
    test_name: str,
    purpose: str = "validation",
    execution_mode: str | None = None,
    planned_run_kind: str | None = None,
    entry_point: str = "",
    primary_variable: Mapping[str, Any] | None = None,
    parameters: Mapping[str, Any] | None = None,
    planned_count: int = 0,
    inputs: Sequence[Mapping[str, Any] | str] = (),
    instruments: Sequence[Mapping[str, Any]] = (),
    source_runs: Sequence[Mapping[str, Any]] = (),
    safety: Mapping[str, Any] | None = None,
    code: Mapping[str, Any] | None = None,
    timestamp: str | None = None,
    results_root: str | Path | None = None,
) -> RunPaths:
    root = Path(project_root).resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"project root does not exist: {root}")
    run_kind = str(run_kind).strip().lower()
    if run_kind not in RUN_KINDS:
        raise ValueError(f"invalid run_kind: {run_kind}")
    if purpose not in PURPOSES:
        raise ValueError(f"invalid purpose: {purpose}")
    default_modes = {
        "single_point": "hardware",
        "scan": "hardware",
        "dry_run": "dry_run",
        "simulation": "simulation",
        "analysis": "offline_analysis",
    }
    execution_mode = execution_mode or default_modes[run_kind]
    if execution_mode not in EXECUTION_MODES:
        raise ValueError(f"invalid execution_mode: {execution_mode}")
    if run_kind == "dry_run":
        if execution_mode != "dry_run" or instruments:
            raise ValueError("dry_run requires execution_mode=dry_run and no instruments")
        if planned_run_kind not in {"single_point", "scan"}:
            raise ValueError("dry_run requires planned_run_kind single_point or scan")
    elif planned_run_kind is not None:
        raise ValueError("planned_run_kind is only used by dry_run")

    parts = [name_parts] if isinstance(name_parts, str) else list(name_parts)
    parts = [_safe_name_part(part, "run name part") for part in parts]
    if not parts:
        raise ValueError("at least one run name part is required")
    if any(part.lower() in RUN_KINDS for part in parts):
        raise ValueError("run name must not repeat its result category")
    run_id = f"{'_'.join(parts)}_{_timestamp(timestamp)}"
    root_results = Path(results_root).resolve() if results_root else root / "results"
    run_dir = root_results / run_kind / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    paths = RunPaths(
        project_root=root,
        results_root=root_results,
        run_kind=run_kind,
        run_id=run_id,
        run_dir=run_dir,
        run_info=run_dir / "run_info.json",
        summary=run_dir / "summary.csv",
        log=run_dir / "run_log.txt",
    )

    code_info = _entry_metadata(root, entry_point)
    if code:
        code_info.update(dict(code))
    info = {
        "schema_version": "1.0",
        "run_id": run_id,
        "project_name": project_name,
        "test_name": test_name,
        "run_kind": run_kind,
        "planned_run_kind": planned_run_kind,
        "purpose": purpose,
        "execution_mode": execution_mode,
        "status": "running",
        "stop_reason": "",
        "stop_detail": "",
        "started_at": _now_iso(),
        "finished_at": None,
        "entry_point": entry_point,
        "code": code_info,
        "runtime": {
            "name": "Python",
            "version": platform.python_version(),
            "os": platform.platform(),
        },
        "primary_variable": dict(primary_variable) if primary_variable else None,
        "parameters": dict(parameters or {}),
        "inputs": list(inputs),
        "instruments": list(instruments),
        "counts": {
            "planned": int(planned_count),
            "executed": 0,
            "succeeded": 0,
            "failed": 0,
            "invalid": 0,
        },
        "safety": dict(safety or {"preflight": "pending", "shutdown": "pending"}),
        "source_runs": list(source_runs),
        "artifacts": [
            {"file": "run_info.json", "role": "run_metadata"},
            {"file": "run_log.txt", "role": "run_log"},
        ],
    }
    _atomic_json(paths.run_info, info)
    log(paths, "INFO", "startup", f"创建运行目录：{run_id}")
    log(paths, "INFO", "startup", f"用途：{purpose}；执行模式：{execution_mode}")
    if run_kind == "dry_run":
        log(paths, "INFO", "safety", "dry-run：未连接、未查询、未写入仪器")
    return paths


def read_run_info(run: RunPaths | str | Path) -> dict[str, Any]:
    path = run.run_info if isinstance(run, RunPaths) else Path(run)
    if path.is_dir():
        path /= "run_info.json"
    return json.loads(path.read_text(encoding="utf-8"))


def update_run_info(run: RunPaths | str | Path, updates: Mapping[str, Any]) -> dict[str, Any]:
    path = run.run_info if isinstance(run, RunPaths) else Path(run)
    if path.is_dir():
        path /= "run_info.json"
    info = _merge(read_run_info(path), updates)
    _atomic_json(path, info)
    return info


def log(
    run: RunPaths | str | Path,
    level: str,
    stage: str,
    message: str,
) -> None:
    path = run.log if isinstance(run, RunPaths) else Path(run)
    if path.is_dir():
        path /= "run_log.txt"
    level = level.upper()
    if level not in LOG_LEVELS:
        raise ValueError(f"invalid log level: {level}")
    stage = str(stage).strip().lower()
    message = str(message).replace("\r", " ").replace("\n", " | ")
    if not re.fullmatch(r"[a-z][a-z0-9_]*", stage):
        raise ValueError("log stage must use lowercase letters, digits, and underscores")
    with path.open("a", encoding="utf-8", newline="\n") as file:
        file.write(f"{_now_iso()} | {level} | {stage} | {message}\n")


def _artifact_role(filename: str) -> str:
    if filename == "overview.png":
        return "overview_figure"
    if filename == "summary.csv":
        return "detail_table"
    if filename == "run_info.json":
        return "run_metadata"
    if filename == "run_log.txt":
        return "run_log"
    if filename == "sources.txt":
        return "source_list"
    if filename.lower().endswith(".png"):
        return "point_figure"
    if filename.lower().endswith((".mat", ".csv", ".h5", ".hdf5", ".npy", ".npz")):
        return "raw_or_derived_data"
    return "artifact"


def register_artifact(run: RunPaths | str | Path, file: str | Path, role: str) -> None:
    run_dir = run.run_dir if isinstance(run, RunPaths) else Path(run)
    if run_dir.is_file():
        run_dir = run_dir.parent
    file_path = Path(file)
    if file_path.is_absolute():
        file_path = file_path.relative_to(run_dir)
    if len(file_path.parts) != 1:
        raise ValueError("run artifacts must be flat files")
    target = run_dir / file_path
    if not target.is_file():
        raise FileNotFoundError(target)
    info = read_run_info(run_dir)
    artifacts = [item for item in info["artifacts"] if item.get("file") != file_path.name]
    artifact = {"file": file_path.name, "role": role}
    if file_path.name != "run_info.json":
        artifact["sha256"] = _sha256(target)
    artifacts.append(artifact)
    update_run_info(run_dir, {"artifacts": artifacts})


def initialize_summary(
    run: RunPaths | str | Path,
    headers: Sequence[str],
    units: Sequence[str],
) -> Path:
    path = run.summary if isinstance(run, RunPaths) else Path(run)
    if path.is_dir():
        path /= "summary.csv"
    if path.exists():
        raise FileExistsError(f"refusing to overwrite summary: {path}")
    if not headers or len(headers) != len(units):
        raise ValueError("headers and units must have equal nonzero length")
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(headers)
        writer.writerow(units)
    register_artifact(path.parent, path.name, "detail_table")
    return path


def _csv_value(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, float) and not math.isfinite(value):
        return ""
    return value


def append_summary(run: RunPaths | str | Path, row: Sequence[Any]) -> None:
    path = run.summary if isinstance(run, RunPaths) else Path(run)
    if path.is_dir():
        path /= "summary.csv"
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        headers = next(csv.reader(file))
    if len(row) != len(headers):
        raise ValueError(f"expected {len(headers)} columns, received {len(row)}")
    with path.open("a", encoding="utf-8", newline="") as file:
        csv.writer(file).writerow([_csv_value(value) for value in row])


def write_sources(run: RunPaths | str | Path, sources: Iterable[str | Path]) -> Path:
    run_dir = run.run_dir if isinstance(run, RunPaths) else Path(run)
    source_paths = [Path(source).resolve() for source in sources]
    if len(source_paths) < 2:
        raise ValueError("cross-run analysis requires at least two source runs")
    if any(not source.is_dir() for source in source_paths):
        raise FileNotFoundError("one or more source run directories do not exist")
    path = run_dir / "sources.txt"
    if path.exists():
        raise FileExistsError(f"refusing to overwrite sources: {path}")
    info = read_run_info(run_dir)
    project_root = Path(run.project_root if isinstance(run, RunPaths) else run_dir.parents[2])
    source_records = []
    lines = []
    for source in source_paths:
        try:
            display = source.relative_to(project_root).as_posix()
        except ValueError:
            display = str(source)
        source_info_path = source / "run_info.json"
        source_info = json.loads(source_info_path.read_text(encoding="utf-8"))
        lines.append(display)
        source_records.append({"run_id": source_info["run_id"], "path": display})
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    update_run_info(run_dir, {"source_runs": source_records})
    register_artifact(run_dir, path.name, "source_list")
    return path


def reserve_derived_path(
    run: RunPaths | str | Path,
    kind: str,
    stem: str,
    extension: str,
    *,
    timestamp: str | None = None,
) -> Path:
    run_dir = run.run_dir if isinstance(run, RunPaths) else Path(run)
    if kind not in {"replay", "analysis"}:
        raise ValueError("derived kind must be replay or analysis")
    stem = _safe_name_part(stem, "derived stem")
    suffix = extension if extension.startswith(".") else f".{extension}"
    path = run_dir / f"{kind}_{_timestamp(timestamp)}_{stem}{suffix}"
    if path.exists():
        raise FileExistsError(f"refusing to overwrite derived artifact: {path}")
    return path


def check_flat(run: RunPaths | str | Path) -> list[str]:
    run_dir = run.run_dir if isinstance(run, RunPaths) else Path(run)
    return sorted(item.name for item in run_dir.iterdir() if item.is_dir())


def finalize_run(
    run: RunPaths | str | Path,
    status: str,
    stop_reason: str,
    *,
    stop_detail: str = "",
    counts: Mapping[str, int] | None = None,
    safety: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    run_dir = run.run_dir if isinstance(run, RunPaths) else Path(run)
    status = status.lower()
    if status not in FINAL_STATUSES:
        raise ValueError(f"invalid final status: {status}")
    if stop_reason not in STOP_REASONS:
        raise ValueError(f"invalid stop_reason: {stop_reason}")
    if status in {"completed", "completed_with_failures"} and stop_reason != "normal_completion":
        raise ValueError("completed runs require normal_completion")
    log(run_dir, "INFO", "finish", f"最终状态：{status}")
    files = sorted(item for item in run_dir.iterdir() if item.is_file())
    artifacts = []
    for file in files:
        artifact = {"file": file.name, "role": _artifact_role(file.name)}
        if file.name != "run_info.json":
            artifact["sha256"] = _sha256(file)
        artifacts.append(artifact)
    updates: dict[str, Any] = {
        "status": status,
        "stop_reason": stop_reason,
        "stop_detail": stop_detail,
        "finished_at": _now_iso(),
        "artifacts": artifacts,
    }
    if counts is not None:
        updates["counts"] = {key: int(value) for key, value in counts.items()}
    if safety is not None:
        updates["safety"] = dict(safety)
    return update_run_info(run_dir, updates)


__all__ = [
    "RunPaths",
    "append_summary",
    "check_flat",
    "create_run",
    "finalize_run",
    "format_parameter",
    "format_value",
    "initialize_summary",
    "log",
    "now_iso",
    "point_filename",
    "read_run_info",
    "register_artifact",
    "reserve_derived_path",
    "update_run_info",
    "write_sources",
]
