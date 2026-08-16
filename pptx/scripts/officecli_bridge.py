#!/usr/bin/env python3
"""Safe local adapter for the pinned OfficeCLI binary.

This file is kept byte-identical in pptx, docx, xlsx, and pdf so their runtime
packages remain self-contained after a targeted CC Switch synchronization.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence


OFFICECLI_VERSION = "1.0.144"
OFFICECLI_SHA256 = "E780CC6A5385F84B4D54D71B0C179904ED534125EC33FE39B1A8711FA80E387E"
DEFAULT_EXE = Path(r"D:\BaiduSyncdisk\.agents\tools\officecli\v1.0.144\officecli.exe")
OFFICE_PROCESSES = {
    ".pptx": "POWERPNT.EXE",
    ".potx": "POWERPNT.EXE",
    ".docx": "WINWORD.EXE",
    ".dotx": "WINWORD.EXE",
    ".dotm": "WINWORD.EXE",
    ".xlsx": "EXCEL.EXE",
    ".xlsm": "EXCEL.EXE",
    ".xltx": "EXCEL.EXE",
}
NATIVE_RENDER_EXTENSIONS = {".docx", ".pptx"}
XLSX_EXTENSIONS = {".xlsx", ".xlsm", ".xltx"}
VIEW_MODES = {
    "text",
    "annotated",
    "outline",
    "stats",
    "issues",
    "html",
    "svg",
    "screenshot",
    "pdf",
    "forms",
}
NON_FIDELITY_VISUAL_MODES = {"html", "svg"}


class BridgeError(RuntimeError):
    """A user-actionable bridge or safety failure."""


@dataclass(frozen=True)
class ResolvedOfficeCli:
    path: Path
    sha256: str
    version: str
    is_override: bool


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def repair_command() -> str:
    return f"{sys.executable} {Path(__file__).with_name('repair_officecli.py')} --repair"


def validation_error(candidate: Path, reason: str, *, is_override: bool) -> BridgeError:
    if is_override:
        return BridgeError(
            f"OfficeCLI at override path {candidate} [{reason}]. Fix the override path or unset "
            "OFFICECLI_EXE. repair_officecli.py only fixes the default path."
        )
    return BridgeError(
        f"OfficeCLI at default path {candidate} [{reason}]. Run {repair_command()} to fix."
    )


def resolve_exe() -> ResolvedOfficeCli:
    override = os.environ.get("OFFICECLI_EXE")
    is_override = override is not None
    candidate = Path(override if is_override else DEFAULT_EXE)
    if not candidate.is_file():
        raise validation_error(candidate, "missing", is_override=is_override)

    actual_sha256 = sha256(candidate)
    if actual_sha256 != OFFICECLI_SHA256:
        raise validation_error(
            candidate,
            f"hash mismatch: expected {OFFICECLI_SHA256}, got {actual_sha256}",
            is_override=is_override,
        )

    try:
        result = run_process([str(candidate), "--version"])
    except BridgeError as exc:
        raise validation_error(candidate, f"version check failed: {exc}", is_override=is_override) from exc
    version = result.stdout.strip() or result.stderr.strip()
    if result.returncode != 0:
        raise validation_error(
            candidate,
            f"version check failed with exit code {result.returncode}: {version or 'no output'}",
            is_override=is_override,
        )
    if version != OFFICECLI_VERSION:
        raise validation_error(
            candidate,
            f"version mismatch: expected {OFFICECLI_VERSION}, got {version or 'no output'}",
            is_override=is_override,
        )
    return ResolvedOfficeCli(candidate, actual_sha256, version, is_override)


def run_process(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            list(command),
            check=False,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
        )
    except OSError as exc:
        raise BridgeError(f"Could not start OfficeCLI: {exc}") from exc


def close_isolated_document(exe: Path, file_path: Path, *, required: bool = False) -> None:
    """Release only the OfficeCLI resident bound to this temporary file."""
    result = run_process([str(exe), "close", str(file_path)])
    if required and result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip() or "unknown OfficeCLI close failure"
        raise BridgeError(f"Could not flush isolated OfficeCLI document: {message}")


def cleanup_workspace(path: Path) -> None:
    """OfficeCLI may release a resident handle just after close returns on Windows."""
    for attempt in range(20):
        try:
            shutil.rmtree(path)
            return
        except PermissionError:
            if attempt == 19:
                return
            time.sleep(0.1)


@contextmanager
def isolated_document(exe: Path, source: Path, isolated_name: str | None = None):
    workspace = Path(tempfile.mkdtemp(prefix="officecli-bridge-"))
    isolated = workspace / (isolated_name or source.name)
    shutil.copy2(source, isolated)
    try:
        yield workspace, isolated
    finally:
        close_isolated_document(exe, isolated)
        cleanup_workspace(workspace)


def process_exists(image_name: str) -> bool:
    result = run_process(
        ["tasklist", "/FI", f"IMAGENAME eq {image_name}", "/FO", "CSV", "/NH"]
    )
    if result.returncode != 0:
        raise BridgeError(f"Could not inspect Office processes: {result.stderr.strip()}")
    return any(image_name.lower() in line.lower() for line in result.stdout.splitlines())


def relevant_process(path: Path) -> str | None:
    return OFFICE_PROCESSES.get(path.suffix.lower())


def require_file(path_text: str) -> Path:
    path = Path(path_text).expanduser().resolve()
    if not path.is_file():
        raise BridgeError(f"Input file not found: {path}")
    return path


def find_option(args: Sequence[str], name: str) -> str | None:
    for index, value in enumerate(args):
        if value == name and index + 1 < len(args):
            return args[index + 1]
        if value.startswith(name + "="):
            return value.split("=", 1)[1]
    return None


def normalize_short_output_option(args: Iterable[str]) -> list[str]:
    return ["--out" if value == "-o" else value for value in args]


def remove_flag(args: Iterable[str], flag: str) -> list[str]:
    return [value for value in args if value != flag]


def remove_value_option(args: Iterable[str], name: str) -> list[str]:
    values = list(args)
    result: list[str] = []
    index = 0
    while index < len(values):
        value = values[index]
        if value == name:
            index += 2
        elif value.startswith(name + "="):
            index += 1
        else:
            result.append(value)
            index += 1
    return result


def resolve_new_output(path_text: str) -> Path:
    path = Path(path_text).expanduser().resolve()
    if path.exists():
        raise BridgeError(f"Refusing to overwrite existing output: {path}")
    return path


def ensure_new_output(path_text: str) -> Path:
    path = resolve_new_output(path_text)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def office_command(exe: Path, verb: str, file_path: Path, args: Sequence[str]) -> list[str]:
    return [str(exe), "--json", verb, str(file_path), *args]


def emit_result(result: subprocess.CompletedProcess[str], replacements: dict[str, str] | None = None) -> int:
    def display(text: str) -> str:
        for old, new in (replacements or {}).items():
            text = text.replace(old, new)
            text = text.replace(json.dumps(old)[1:-1], json.dumps(new)[1:-1])
        if replacements and text.strip().startswith(("{", "[")):
            try:
                payload = json.loads(text)

                def replace_value(value):
                    if isinstance(value, str):
                        for old, new in replacements.items():
                            value = value.replace(old, new)
                        return value
                    if isinstance(value, list):
                        return [replace_value(item) for item in value]
                    if isinstance(value, dict):
                        return {key: replace_value(item) for key, item in value.items()}
                    return value

                return json.dumps(replace_value(payload), ensure_ascii=False, indent=2) + "\n"
            except json.JSONDecodeError:
                pass
        return text

    if result.stdout:
        sys.stdout.write(display(result.stdout))
    if result.stderr:
        sys.stderr.write(display(result.stderr))
    return result.returncode


def run_read(exe: Path, verb: str, file_path: Path, args: Sequence[str]) -> int:
    if verb == "validate" and file_path.suffix.lower() in XLSX_EXTENSIONS:
        raise BridgeError(
            "OfficeCLI XLSX schema validation is disabled because it reports valid "
            "workbook styles as schema errors; use the xlsx skill's "
            "scripts/verify_xlsx.py instead"
        )
    source_hash = sha256(file_path)
    with isolated_document(exe, file_path) as (_, isolated):
        result = run_process(office_command(exe, verb, isolated, args))
        exit_code = emit_result(result)
    if sha256(file_path) != source_hash:
        raise BridgeError(f"Source changed during OfficeCLI {verb}: {file_path}")
    return exit_code


def resolve_render_mode(mode: str, args: Sequence[str]) -> tuple[list[str], bool, bool]:
    clean_args = remove_flag(args, "--allow-native")
    non_fidelity_preview = "--non-fidelity-preview" in clean_args
    clean_args = remove_flag(clean_args, "--non-fidelity-preview")
    if mode == "pdf":
        raise BridgeError(
            "OfficeCLI PDF export is unavailable because no exporter plugin is installed; "
            "use the relevant native Office or libreoffice-runner route instead"
        )
    render = find_option(clean_args, "--render")
    if render is not None and render.lower() == "auto":
        raise BridgeError("--render auto is prohibited; choose html or explicitly authorized native")
    if mode in NON_FIDELITY_VISUAL_MODES:
        if not non_fidelity_preview:
            raise BridgeError(
                f"OfficeCLI view {mode} is a non-fidelity preview; "
                "pass --non-fidelity-preview to use it diagnostically"
            )
        return clean_args, False, True
    if mode == "screenshot":
        if render is None:
            raise BridgeError(
                "OfficeCLI screenshot requires an explicit render mode: use "
                "--render native --allow-native after current-task authorization, or "
                "--render html --non-fidelity-preview for diagnostics"
            )
        render = render.lower()
        if render not in {"html", "native"}:
            raise BridgeError(f"Unsupported OfficeCLI screenshot render mode: {render}")
        is_native = render == "native"
        if is_native and non_fidelity_preview:
            raise BridgeError("--non-fidelity-preview only applies to HTML or SVG previews")
        if not is_native and not non_fidelity_preview:
            raise BridgeError(
                "OfficeCLI HTML screenshot is a non-fidelity preview; "
                "pass --non-fidelity-preview to use it diagnostically"
            )
        return clean_args, is_native, not is_native
    if non_fidelity_preview:
        raise BridgeError("--non-fidelity-preview only applies to HTML or SVG previews")
    return clean_args, False, False


def run_view(exe: Path, file_path: Path, args: Sequence[str]) -> int:
    args = normalize_short_output_option(args)
    mode = args[0] if args else "text"
    if mode not in VIEW_MODES:
        raise BridgeError(f"Unsupported OfficeCLI view mode: {mode}")

    allow_native = "--allow-native" in args
    clean_args, is_native, non_fidelity_preview = resolve_render_mode(mode, args)
    output_text = find_option(clean_args, "--out")
    if is_native and not allow_native:
        raise BridgeError("Native or auto rendering requires --allow-native and current-task user authorization")
    if mode in {"screenshot", "pdf"} and output_text is None:
        raise BridgeError(f"OfficeCLI view {mode} requires --out <new-output-path>")

    process_name = relevant_process(file_path)
    if is_native and file_path.suffix.lower() not in NATIVE_RENDER_EXTENSIONS:
        raise BridgeError(f"OfficeCLI native rendering is unsupported for this extension: {file_path.suffix}")
    if is_native and process_name and process_exists(process_name):
        raise BridgeError(
            f"Refusing native rendering while {process_name} is running; close Office and obtain current-task authorization first"
        )
    output = resolve_new_output(output_text) if output_text else None
    if non_fidelity_preview:
        print(
            "Warning: OfficeCLI HTML/SVG output is a non-fidelity diagnostic preview. "
            "Do not use it for final images, layout PDF, print/page QA, or publication graphics.",
            file=sys.stderr,
        )
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)

    source_hash = sha256(file_path)
    with isolated_document(exe, file_path) as (temp_dir, isolated):
        isolated_output = None
        if output:
            isolated_output = temp_dir / output.name
            clean_args = remove_value_option(clean_args, "--out")
            clean_args.extend(["--out", str(isolated_output)])
        result = run_process(office_command(exe, "view", isolated, clean_args))
        replacements = {str(isolated_output): str(output)} if output and isolated_output else None
        exit_code = emit_result(result, replacements)
        if exit_code != 0:
            return exit_code
        if sha256(file_path) != source_hash:
            raise BridgeError(f"Source changed during OfficeCLI view: {file_path}")
        if output and isolated_output:
            if not isolated_output.is_file():
                raise BridgeError(f"OfficeCLI did not produce requested output: {isolated_output}")
            shutil.copy2(isolated_output, output)
    return 0


def run_get_with_save(exe: Path, file_path: Path, args: Sequence[str]) -> int:
    output_text = find_option(args, "--save")
    if output_text is None:
        return run_read(exe, "get", file_path, args)
    output = ensure_new_output(output_text)
    source_hash = sha256(file_path)
    with isolated_document(exe, file_path) as (temp_dir, isolated):
        isolated_output = temp_dir / output.name
        clean_args = remove_value_option(args, "--save")
        clean_args.extend(["--save", str(isolated_output)])
        result = run_process(office_command(exe, "get", isolated, clean_args))
        exit_code = emit_result(result)
        if exit_code != 0:
            return exit_code
        if sha256(file_path) != source_hash:
            raise BridgeError(f"Source changed during OfficeCLI get: {file_path}")
        if not isolated_output.is_file():
            raise BridgeError(f"OfficeCLI did not produce requested output: {isolated_output}")
        shutil.copy2(isolated_output, output)
    return 0


def run_mutation(exe: Path, source: Path, output_text: str, verb: str, args: Sequence[str]) -> int:
    output = ensure_new_output(output_text)
    if output.suffix.lower() != source.suffix.lower():
        raise BridgeError(f"Mutation output extension must match source: {source.suffix}")
    source_hash = sha256(source)
    with isolated_document(exe, source, output.name) as (_, isolated):
        result = run_process(office_command(exe, verb, isolated, args))
        exit_code = emit_result(result)
        if sha256(source) != source_hash:
            raise BridgeError(f"Source changed during OfficeCLI mutation: {source}")
        if exit_code != 0:
            return exit_code
        close_isolated_document(exe, isolated, required=True)
        shutil.copy2(isolated, output)
    if sha256(source) != source_hash:
        raise BridgeError(f"Source changed during OfficeCLI mutation: {source}")
    return 0


def run_status(resolved: ResolvedOfficeCli) -> int:
    print(
        json.dumps(
            {
                "ok": True,
                "officecli": str(resolved.path),
                "source": "override" if resolved.is_override else "default",
                "expected_version": OFFICECLI_VERSION,
                "version": resolved.version,
                "expected_sha256": OFFICECLI_SHA256,
                "sha256": resolved.sha256,
            },
            ensure_ascii=False,
        )
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Safe adapter for the local OfficeCLI binary")
    subparsers = parser.add_subparsers(dest="operation", required=True)
    subparsers.add_parser("status")
    view = subparsers.add_parser("view")
    view.add_argument("file")
    view.add_argument("args", nargs=argparse.REMAINDER)
    for name in ("query", "get", "validate"):
        command = subparsers.add_parser(name)
        command.add_argument("file")
        command.add_argument("args", nargs=argparse.REMAINDER)
    mutate = subparsers.add_parser("mutate")
    mutate.add_argument("source")
    mutate.add_argument("output")
    mutate.add_argument("verb", choices=("set", "add", "remove", "move", "swap", "batch"))
    mutate.add_argument("args", nargs=argparse.REMAINDER)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parsed = build_parser().parse_args(argv)
    try:
        resolved = resolve_exe()
        if parsed.operation == "status":
            return run_status(resolved)
        exe = resolved.path
        if parsed.operation == "mutate":
            return run_mutation(
                exe,
                require_file(parsed.source),
                parsed.output,
                parsed.verb,
                parsed.args,
            )
        file_path = require_file(parsed.file)
        if parsed.operation == "view":
            return run_view(exe, file_path, parsed.args)
        if parsed.operation == "get":
            return run_get_with_save(exe, file_path, parsed.args)
        return run_read(exe, parsed.operation, file_path, parsed.args)
    except BridgeError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
