#!/usr/bin/env python3
"""Validate a standardized test project without importing experiment code."""

from __future__ import annotations

import argparse
import csv
import json
import re
import struct
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


ROOT_FILES = ("README.md", "AGENTS.md", "CLAUDE.md", "GEMINI.md", ".gitignore")
DIRECTORIES = (
    "code/experiments/single_point",
    "code/experiments/frequency_sweep",
    "code/experiments/power_sweep",
    "code/instrument_control",
    "code/acquisition",
    "code/signal_processing",
    "code/plotting",
    "code/result_management",
    "code/analysis",
    "code/simulation",
    "code/tests",
    "config",
    "data",
    "docs",
    "results/single_point",
    "results/scan",
    "results/dry_run",
    "results/simulation",
    "results/analysis",
    "archive",
)
RUN_KINDS = ("single_point", "scan", "dry_run", "simulation", "analysis")
PURPOSES = {"formal", "validation", "debug"}
MODES = {
    "hardware",
    "hardware_query",
    "dry_run",
    "simulation",
    "offline_replay",
    "offline_analysis",
}
STATUSES = {"running", "completed", "completed_with_failures", "failed", "stopped"}
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
INFO_FIELDS = {
    "schema_version",
    "run_id",
    "project_name",
    "test_name",
    "run_kind",
    "planned_run_kind",
    "purpose",
    "execution_mode",
    "status",
    "stop_reason",
    "stop_detail",
    "started_at",
    "finished_at",
    "entry_point",
    "code",
    "runtime",
    "primary_variable",
    "parameters",
    "inputs",
    "instruments",
    "counts",
    "safety",
    "source_runs",
    "artifacts",
}
TRACE_TAIL = (
    "状态",
    "repeat",
    "attempt",
    "采集时间",
    "原始数据文件",
    "单次图片文件",
    "错误代码",
    "错误信息",
)
TIMESTAMP_SUFFIX = re.compile(r"_\d{8}_\d{6}$")
LOG_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})"
    r" \| (?:DEBUG|INFO|WARNING|ERROR) \| [^|]+ \| .+$"
)


@dataclass
class Report:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    run_count: int = 0

    def error(self, message: str) -> None:
        self.errors.append(message)

    def warning(self, message: str) -> None:
        self.warnings.append(message)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", type=Path)
    parser.add_argument(
        "--allow-running",
        action="store_true",
        help="Allow run_info status=running during an active-run inspection",
    )
    return parser.parse_args()


def load_summary(path: Path, report: Report) -> tuple[list[str], list[str], list[list[str]]]:
    raw = path.read_bytes()
    if not raw.startswith(b"\xef\xbb\xbf"):
        report.error(f"{path}: summary.csv is not UTF-8 with BOM")
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as file:
            rows = list(csv.reader(file))
    except (UnicodeDecodeError, csv.Error) as exc:
        report.error(f"{path}: cannot parse CSV: {exc}")
        return [], [], []
    if len(rows) < 2:
        report.error(f"{path}: CSV needs metric and unit rows")
        return [], [], []
    if len(rows[0]) != len(rows[1]) or not rows[0]:
        report.error(f"{path}: header and unit rows have different widths")
    if tuple(rows[0][-len(TRACE_TAIL) :]) != TRACE_TAIL:
        report.error(f"{path}: fixed traceability columns are missing or out of order")
    for index, row in enumerate(rows[2:], start=3):
        if len(row) != len(rows[0]):
            report.error(f"{path}: row {index} has {len(row)} columns, expected {len(rows[0])}")
    return rows[0], rows[1], rows[2:]


def png_dpi(path: Path) -> float | None:
    data = path.read_bytes()
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        return None
    offset = 8
    while offset + 12 <= len(data):
        length = struct.unpack(">I", data[offset : offset + 4])[0]
        chunk_type = data[offset + 4 : offset + 8]
        chunk_data = data[offset + 8 : offset + 8 + length]
        if chunk_type == b"pHYs" and length == 9:
            pixels_per_meter_x, _, unit = struct.unpack(">IIB", chunk_data)
            return pixels_per_meter_x * 0.0254 if unit == 1 else None
        offset += 12 + length
    return None


def validate_file_references(
    run_dir: Path, headers: list[str], rows: list[list[str]], report: Report
) -> None:
    if not headers:
        return
    indexes = {name: headers.index(name) for name in TRACE_TAIL if name in headers}
    missing = [name for name in TRACE_TAIL if name not in indexes]
    if missing:
        return
    for row_number, row in enumerate(rows, start=3):
        if len(row) != len(headers):
            continue
        status = row[indexes["状态"]]
        if status not in {"成功", "无效", "失败"}:
            report.error(f"{run_dir / 'summary.csv'}: row {row_number} has invalid 状态={status!r}")
        for column in ("原始数据文件", "单次图片文件"):
            value = row[indexes[column]].strip()
            for filename in filter(None, (item.strip() for item in value.split(";"))):
                if Path(filename).name != filename:
                    report.error(f"{run_dir}: row {row_number} file reference is not flat: {filename}")
                    continue
                if not (run_dir / filename).is_file():
                    report.error(f"{run_dir}: row {row_number} references missing file: {filename}")
                if status == "失败" and not filename.startswith("FAILED_"):
                    report.error(f"{run_dir}: failed row artifact needs FAILED_ prefix: {filename}")


def validate_artifacts(run_dir: Path, artifacts: Any, report: Report) -> None:
    if not isinstance(artifacts, list):
        report.error(f"{run_dir}: artifacts must be an array")
        return
    for item in artifacts:
        if not isinstance(item, dict) or not item.get("file") or not item.get("role"):
            report.error(f"{run_dir}: each artifact needs file and role")
            continue
        filename = item["file"]
        if Path(filename).name != filename:
            report.error(f"{run_dir}: artifact is not a flat file: {filename}")
        elif not (run_dir / filename).is_file():
            report.error(f"{run_dir}: registered artifact is missing: {filename}")


def validate_log(path: Path, run_kind: str, report: Report) -> None:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except UnicodeDecodeError as exc:
        report.error(f"{path}: log is not UTF-8: {exc}")
        return
    if not lines:
        report.error(f"{path}: log is empty")
        return
    for number, line in enumerate(lines, start=1):
        if not LOG_PATTERN.fullmatch(line):
            report.error(f"{path}: line {number} does not match ISO8601 | level | stage | message")
    if run_kind == "dry_run":
        joined = "\n".join(lines).lower()
        english = all(word in joined for word in ("no instrument connection", "query", "write"))
        english_passive = all(
            word in joined for word in ("not connected", "queried", "written")
        )
        chinese = all(word in joined for word in ("未连接", "未查询", "未写入仪器"))
        if not (english or english_passive or chinese):
            report.error(f"{path}: dry-run log does not state that instrument I/O was absent")


def validate_run(run_dir: Path, category: str, allow_running: bool, report: Report) -> None:
    report.run_count += 1
    if any(item.is_dir() for item in run_dir.iterdir()):
        report.error(f"{run_dir}: run directory contains a forbidden subdirectory")
    if not TIMESTAMP_SUFFIX.search(run_dir.name):
        report.error(f"{run_dir}: run name lacks YYYYMMDD_HHMMSS suffix")
    if re.search(r"\d+p\d+", run_dir.name, re.IGNORECASE):
        report.error(f"{run_dir}: use a real decimal point, not p")
    for reserved in RUN_KINDS:
        if re.search(rf"(?:^|_){re.escape(reserved)}(?:_|$)", run_dir.name, re.IGNORECASE):
            report.error(f"{run_dir}: run name repeats result category {reserved}")

    info_path = run_dir / "run_info.json"
    log_path = run_dir / "run_log.txt"
    for path in (info_path, log_path):
        if not path.is_file():
            report.error(f"{run_dir}: missing {path.name}")
    if not info_path.is_file():
        return
    try:
        info = json.loads(info_path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        report.error(f"{info_path}: cannot parse UTF-8 JSON: {exc}")
        return
    missing = sorted(INFO_FIELDS - set(info))
    if missing:
        report.error(f"{info_path}: missing fields: {', '.join(missing)}")
        return
    if info["run_id"] != run_dir.name or info["run_kind"] != category:
        report.error(f"{info_path}: run_id or run_kind does not match its directory")
    if info["purpose"] not in PURPOSES or info["execution_mode"] not in MODES:
        report.error(f"{info_path}: invalid purpose or execution_mode")
    if info["status"] not in STATUSES:
        report.error(f"{info_path}: invalid status={info['status']!r}")
    if info["status"] == "running" and not allow_running:
        report.error(f"{info_path}: status is still running")
    if info["status"] == "running" and info["stop_reason"]:
        report.error(f"{info_path}: active run must have empty stop_reason")
    if info["status"] != "running" and info["stop_reason"] not in STOP_REASONS:
        report.error(f"{info_path}: final run has invalid stop_reason")
    if info["status"] != "running" and not info["finished_at"]:
        report.error(f"{info_path}: final run lacks finished_at")
    if category == "dry_run":
        if info["execution_mode"] != "dry_run" or info["instruments"]:
            report.error(f"{info_path}: dry_run has unsafe mode or instrument records")
        if info["planned_run_kind"] not in {"single_point", "scan"}:
            report.error(f"{info_path}: dry_run lacks planned_run_kind")
    elif info["planned_run_kind"] is not None:
        report.error(f"{info_path}: planned_run_kind is only valid for dry_run")
    required_counts = {"planned", "executed", "succeeded", "failed", "invalid"}
    if not isinstance(info["counts"], dict) or not required_counts.issubset(info["counts"]):
        report.error(f"{info_path}: counts object is incomplete")
    validate_artifacts(run_dir, info["artifacts"], report)
    if log_path.is_file():
        validate_log(log_path, category, report)

    if info["status"] == "running" and allow_running:
        return
    for filename in ("overview.png", "summary.csv"):
        if not (run_dir / filename).is_file():
            report.error(f"{run_dir}: final run is missing {filename}")
    summary_path = run_dir / "summary.csv"
    if summary_path.is_file():
        headers, _, rows = load_summary(summary_path, report)
        validate_file_references(run_dir, headers, rows, report)
    overview = run_dir / "overview.png"
    if overview.is_file():
        dpi = png_dpi(overview)
        if dpi is None:
            report.error(f"{overview}: PNG lacks readable physical resolution metadata")
        elif not 285 <= dpi <= 315:
            report.error(f"{overview}: expected 300 dpi, found {dpi:.1f}")
    if category == "analysis":
        sources = run_dir / "sources.txt"
        if not sources.is_file():
            report.error(f"{run_dir}: cross-run analysis lacks sources.txt")
        else:
            lines = [line for line in sources.read_text(encoding="utf-8").splitlines() if line]
            if len(lines) < 2:
                report.error(f"{sources}: cross-run analysis needs at least two sources")
            if len(info["source_runs"]) != len(lines):
                report.error(f"{info_path}: source_runs and sources.txt differ in length")


def validate_project(project: Path, allow_running: bool = False) -> Report:
    report = Report()
    project = project.resolve()
    if not project.is_dir():
        report.error(f"project directory does not exist: {project}")
        return report
    for relative in ROOT_FILES:
        if not (project / relative).is_file():
            report.error(f"missing project file: {relative}")
    for relative in DIRECTORIES:
        if not (project / relative).is_dir():
            report.error(f"missing project directory: {relative}")
    root_entries = [
        path
        for pattern in ("*.m", "*.py")
        for path in project.glob(pattern)
        if path.is_file() and not path.name.startswith(("_", "."))
    ]
    if not root_entries:
        report.error("project root lacks a human-run entry script")
    results = project / "results"
    if results.is_dir():
        for category in RUN_KINDS:
            category_dir = results / category
            if not category_dir.is_dir():
                continue
            for item in category_dir.iterdir():
                if item.is_file():
                    report.error(f"{category_dir}: result category contains file {item.name}")
                elif item.is_dir():
                    validate_run(item, category, allow_running, report)
    return report


def main() -> int:
    args = parse_args()
    report = validate_project(args.project, allow_running=args.allow_running)
    print(f"Validated runs: {report.run_count}")
    for warning in report.warnings:
        print(f"WARNING: {warning}")
    for error in report.errors:
        print(f"ERROR: {error}")
    if report.errors:
        print(f"Validation failed with {len(report.errors)} error(s).")
        return 1
    print("Validation passed. No instrument code was imported or executed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
