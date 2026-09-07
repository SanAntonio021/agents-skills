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


RUN_KINDS = {"single_point", "scan", "dry_run", "simulation", "analysis", "measurement", "checks"}
OUTPUT_CATEGORIES = {"simulation", "measurement", "analysis", "checks"}
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
    data_dir: Path
    full_summary: Path
    output_category: str


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
    if not text or text in {".", ".."} or UNSAFE_NAME.search(text) or any(char.isspace() for char in text):
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
    observation: int | None = None,
    channel: str | int | None = None,
) -> str:
    parts = [name_parts] if isinstance(name_parts, str) else list(name_parts)
    parts = [_safe_name_part(part, "point name part") for part in parts]
    if not parts or repeat < 1 or attempt < 1:
        raise ValueError("name parts, positive repeat, and positive attempt are required")
    suffix = extension if extension.startswith(".") else f".{extension}"
    if suffix.count(".") != 1 or "/" in suffix or "\\" in suffix:
        raise ValueError("extension must contain one leading period")
    if observation is not None:
        if not isinstance(observation, int) or observation < 1:
            raise ValueError("observation must be a positive integer")
        tokens = [f"{observation:03d}", *parts]
        if channel is not None:
            tokens.append(_safe_name_part(f"Channel{channel}", "channel"))
        if failed:
            tokens.append("FAILED")
        return "_".join(tokens) + suffix
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
    output_category: str | None = None,
    retention_mode: str = "compact",
    output_dir: str | Path | None = None,
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
        "measurement": "hardware",
        "checks": "dry_run",
    }
    execution_mode = execution_mode or default_modes[run_kind]
    if execution_mode not in EXECUTION_MODES:
        raise ValueError(f"invalid execution_mode: {execution_mode}")
    if run_kind == "dry_run" and execution_mode != "dry_run":
        raise ValueError("dry_run requires execution_mode=dry_run")
    if execution_mode == "dry_run":
        if instruments:
            raise ValueError("dry_run requires execution_mode=dry_run and no instruments")
        if run_kind == "dry_run" and planned_run_kind not in {"single_point", "scan"}:
            raise ValueError("dry_run requires planned_run_kind single_point or scan")
    elif planned_run_kind is not None:
        raise ValueError("planned_run_kind is only used by dry_run")

    parts = [name_parts] if isinstance(name_parts, str) else list(name_parts)
    parts = [_safe_name_part(part, "run name part") for part in parts]
    if not parts:
        raise ValueError("at least one run name part is required")
    if any(part.lower() in RUN_KINDS for part in parts):
        raise ValueError("run name must not repeat its result category")
    category = output_category or {"hardware": "measurement", "hardware_query": "measurement", "dry_run": "checks", "simulation": "simulation", "offline_replay": "analysis", "offline_analysis": "analysis"}[execution_mode]
    if category not in OUTPUT_CATEGORIES or retention_mode not in {"compact", "full"}:
        raise ValueError("invalid output category or retention mode")
    expected = {"hardware": "measurement", "hardware_query": "measurement", "dry_run": "checks", "offline_replay": "analysis", "offline_analysis": "analysis"}.get(execution_mode)
    if expected and category != expected:
        raise ValueError("output category disagrees with execution mode")
    if execution_mode == "simulation" and category not in {"simulation", "checks"}:
        raise ValueError("simulation output must be simulation or checks")
    run_id = f"{_timestamp(timestamp)}_{'_'.join(parts)}"
    root_results = Path(results_root).resolve() if results_root else root
    base = root_results / category / run_id
    run_dir = Path(output_dir).resolve() if output_dir else base
    counter = 1
    while True:
        try:
            run_dir.mkdir(parents=True, exist_ok=False)
            break
        except FileExistsError:
            if output_dir:
                raise
            counter += 1
            run_dir = base.with_name(f"{base.name}_{counter:02d}")
    run_id = run_dir.name
    data_dir = run_dir / "data"
    data_dir.mkdir()
    paths = RunPaths(
        project_root=root,
        results_root=root_results,
        run_kind=run_kind,
        run_id=run_id,
        run_dir=run_dir,
        run_info=data_dir / "run_info.json",
        summary=run_dir / "summary.csv",
        log=data_dir / "run_log.txt",
        data_dir=data_dir,
        full_summary=data_dir / "observations.csv",
        output_category=category,
    )

    code_info = _entry_metadata(root, entry_point)
    if code:
        code_info.update(dict(code))
    info = {
        "schema_version": "2.0",
        "output_category": category,
        "retention_mode": retention_mode,
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
            {"file": "data/run_info.json", "role": "run_metadata"},
            {"file": "data/run_log.txt", "role": "run_log"},
        ],
    }
    _atomic_json(paths.run_info, info)
    log(paths, "INFO", "startup", f"创建运行目录：{run_id}")
    log(paths, "INFO", "startup", f"用途：{purpose}；执行模式：{execution_mode}")
    if execution_mode == "dry_run":
        log(paths, "INFO", "safety", "dry-run：未连接、未查询、未写入仪器")
    return paths


def artifact_path(run: RunPaths | str | Path, name: str) -> Path:
    """Resolve a record in schema 2, falling back to legacy flat runs."""
    _safe_name_part(name, "artifact name")
    root = run.run_dir if isinstance(run, RunPaths) else Path(run)
    candidate = root / "data" / name
    if candidate.exists() or not (root / name).exists() and (root / "data").is_dir():
        return candidate
    return root / name


def read_run_info(run: RunPaths | str | Path) -> dict[str, Any]:
    path = run.run_info if isinstance(run, RunPaths) else Path(run)
    if path.is_dir():
        path = artifact_path(path, "run_info.json")
    return json.loads(path.read_text(encoding="utf-8"))


def update_run_info(run: RunPaths | str | Path, updates: Mapping[str, Any]) -> dict[str, Any]:
    path = run.run_info if isinstance(run, RunPaths) else Path(run)
    if path.is_dir():
        path = artifact_path(path, "run_info.json")
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
        path = artifact_path(path, "run_log.txt")
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
    if file_path.is_absolute() or ".." in file_path.parts or not (len(file_path.parts) == 1 or len(file_path.parts) == 2 and file_path.parts[0] == "data"):
        raise ValueError("artifacts must be in run root or its flat data directory")
    target = run_dir / file_path
    if not target.is_file():
        raise FileNotFoundError(target)
    info = read_run_info(run_dir)
    artifacts = [item for item in info["artifacts"] if item.get("file") != file_path.as_posix()]
    artifact = {"file": file_path.as_posix(), "role": role}
    if file_path.name != "run_info.json":
        artifact["sha256"] = _sha256(target)
    artifacts.append(artifact)
    update_run_info(run_dir, {"artifacts": artifacts})


def initialize_summary(
    run: RunPaths | str | Path,
    headers: Sequence[str],
    units: Sequence[str],
    *,
    display_columns: Sequence[str] | None = None,
    formats: Mapping[str, str] | None = None,
) -> Path:
    path = run.summary if isinstance(run, RunPaths) else Path(run)
    if path.is_dir():
        path /= "summary.csv"
    if path.exists():
        raise FileExistsError(f"refusing to overwrite summary: {path}")
    if not headers or len(headers) != len(units):
        raise ValueError("headers and units must have equal nonzero length")
    if not artifact_path(path.parent, "run_info.json").exists():
        with path.open("x", encoding="utf-8-sig", newline="") as file:
            writer = csv.writer(file)
            writer.writerow(headers)
            writer.writerow(units)
        return path
    selected = list(display_columns) if display_columns is not None else [h for h in headers if h not in {"repeat", "attempt", "采集时间", "原始数据文件", "单次图片文件", "错误代码", "错误信息"}]
    if not selected or len(set(headers)) != len(headers) or any(h not in headers for h in selected):
        raise ValueError("summary columns must be unique and display columns must exist")
    full = artifact_path(path.parent, "observations.csv")
    with full.open("x", encoding="utf-8-sig", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(headers)
        writer.writerow(units)
    with path.open("x", encoding="utf-8-sig", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(selected)
        writer.writerow([units[headers.index(h)] for h in selected])
    update_run_info(path.parent, {"summary": {"headers": list(headers), "display_columns": selected, "formats": dict(formats or {})}})
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
    full = artifact_path(path.parent, "observations.csv")
    source = full if full.exists() else path
    with source.open("r", encoding="utf-8-sig", newline="") as file:
        headers = next(csv.reader(file))
    if len(row) != len(headers):
        raise ValueError(f"expected {len(headers)} columns, received {len(row)}")
    if source != path:
        with source.open("a", encoding="utf-8", newline="") as file:
            csv.writer(file).writerow([_csv_value(value) for value in row])
        spec = read_run_info(path.parent).get("summary", {})
        selected = spec.get("display_columns", headers)
        values = [display_value(row[headers.index(h)], h, spec.get("formats", {}).get(h)) for h in selected]
    else:
        values = [_csv_value(value) for value in row]
    with path.open("a", encoding="utf-8", newline="") as file:
        csv.writer(file).writerow(values)


def display_value(value: Any, header: str = "", mode: str | None = None) -> Any:
    if value is None or isinstance(value, float) and not math.isfinite(value):
        return ""
    if isinstance(value, bool):
        return value
    if not isinstance(value, (int, float)):
        return value
    if mode == "exact":
        return repr(value)
    if mode and mode.startswith("fixed:"):
        return f"{value:.{int(mode.split(':')[1])}f}"
    if mode == "integer" or isinstance(value, int) or header in {"序号", "计数", "Channel", "Observation", "Sequence"} or re.search(r"(?i)(?:^|_)(?:count|index)$|Count$|比特数|符号数|块数|次数|数量", header):
        return str(int(value))
    if mode == "probability" or any(word in header.upper() for word in ("BER", "BLER", "FER", "误码", "误块")):
        return f"{value:.2e}" if value else "0"
    return f"{value:.2e}" if value and abs(value) < 0.005 else f"{value:.2f}"


def read_summary(run: RunPaths | str | Path) -> list[list[str]]:
    root = run.run_dir if isinstance(run, RunPaths) else Path(run)
    path = artifact_path(root, "observations.csv")
    if not path.exists():
        path = root / "summary.csv"
    with path.open(encoding="utf-8-sig", newline="") as file:
        return list(csv.reader(file))


def write_sources(run: RunPaths | str | Path, sources: Iterable[str | Path]) -> Path:
    run_dir = run.run_dir if isinstance(run, RunPaths) else Path(run)
    source_paths = [Path(source).resolve() for source in sources]
    if not source_paths:
        raise ValueError("analysis requires at least one source run")
    if any(not source.is_dir() for source in source_paths):
        raise FileNotFoundError("one or more source run directories do not exist")
    if any(source == run_dir.resolve() for source in source_paths):
        raise ValueError("analysis output must differ from its sources")
    path = artifact_path(run_dir, "sources.txt")
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
        source_info_path = artifact_path(source, "run_info.json")
        source_info = json.loads(source_info_path.read_text(encoding="utf-8"))
        lines.append(display)
        source_records.append({"run_id": source_info["run_id"], "path": display})
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    update_run_info(run_dir, {"source_runs": source_records})
    register_artifact(run_dir, path, "source_list")
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
    if read_run_info(run_dir).get("output_category", read_run_info(run_dir).get("run_kind")) != "analysis":
        raise ValueError("create a separate analysis run before writing derived artifacts")
    if kind not in {"replay", "analysis"}:
        raise ValueError("derived kind must be replay or analysis")
    stem = _safe_name_part(stem, "derived stem")
    suffix = extension if extension.startswith(".") else f".{extension}"
    target_dir = run_dir if suffix.lower() == ".png" else artifact_path(run_dir, "sources.txt").parent
    path = target_dir / f"{kind}_{_timestamp(timestamp)}_{stem}{suffix}"
    if path.exists():
        raise FileExistsError(f"refusing to overwrite derived artifact: {path}")
    return path


def check_flat(run: RunPaths | str | Path) -> list[str]:
    run_dir = run.run_dir if isinstance(run, RunPaths) else Path(run)
    invalid = [item.name for item in run_dir.iterdir() if item.is_dir() and item.name != "data"]
    if (run_dir / "data").is_dir():
        invalid.extend(f"data/{item.name}" for item in (run_dir / "data").iterdir() if item.is_dir())
    return sorted(invalid)


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
    if check_flat(run_dir):
        raise ValueError("run contains unexpected nested directories")
    files = sorted(item for item in run_dir.rglob("*") if item.is_file())
    artifacts = []
    for file in files:
        artifact = {"file": file.relative_to(run_dir).as_posix(), "role": _artifact_role(file.name)}
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
    "artifact_path",
    "display_value",
    "read_summary",
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
