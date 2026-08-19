#!/usr/bin/env python3
"""Find a Python interpreter that can run the PPTX static QA tools.

The preflight intentionally uses only the Python standard library.  It never
installs packages; each candidate is checked in its own interpreter process so
the result describes the runtime that will actually run the validators.
"""

from __future__ import annotations

import argparse
import datetime as _datetime
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence


SCHEMA_VERSION = 1
DEFAULT_TIMEOUT_SECONDS = 10.0
NO_RUNTIME_EXIT = 1
_FORBIDDEN_REPORT_PARTS = {
    ".codex",
    ".cc-switch",
    ".claude",
    "codex-runtimes",
    "codex-primary-runtime",
    "openai-primary-runtime",
}

# The keys are distribution names used in the report; the values are the
# import names exercised by validate.py and typography_audit.py.
REQUIRED_IMPORTS: tuple[tuple[str, str], ...] = (
    ("defusedxml", "defusedxml"),
    ("lxml", "lxml"),
    ("python-pptx", "pptx"),
)

_PROBE_CODE = r"""
import importlib
import json
import os
import sys

required = json.loads(sys.argv[1])
dependencies = {}
for distribution, module_name in required:
    try:
        module = importlib.import_module(module_name)
        dependencies[distribution] = {
            "module": module_name,
            "ok": True,
            "version": getattr(module, "__version__", None),
            "error": None,
        }
    except Exception as exc:
        dependencies[distribution] = {
            "module": module_name,
            "ok": False,
            "version": None,
            "error": f"{type(exc).__name__}: {exc}",
        }

print(json.dumps({
    "executable": os.path.abspath(sys.executable),
    "python_version": sys.version.split()[0],
    "dependencies": dependencies,
}, ensure_ascii=True, sort_keys=True))
"""


@dataclass(frozen=True)
class Candidate:
    """A no-shell command that can be used to start a Python interpreter."""

    source: str
    command: tuple[str, ...]

    @property
    def label(self) -> str:
        return " ".join(self.command)


Runner = Callable[..., subprocess.CompletedProcess[str]]
Which = Callable[[str], str | None]


def _normalise_path(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return os.path.abspath(os.path.expanduser(value))
    except (OSError, TypeError, ValueError):
        return value


def _dedupe_candidates(candidates: Iterable[Candidate]) -> list[Candidate]:
    seen: set[tuple[str, ...]] = set()
    result: list[Candidate] = []
    for candidate in candidates:
        key = tuple(
            item.casefold() if os.name == "nt" else item for item in candidate.command
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(candidate)
    return result


def discover_system_python_paths() -> list[str]:
    """Return common Windows system-Python paths without touching any runtime dir."""

    if os.name != "nt":
        return []

    roots = [
        Path("C:/Python*"),
        Path("C:/Program Files/Python*"),
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Python" / "Python*",
    ]
    paths: list[str] = []
    for pattern in roots:
        if not str(pattern):
            continue
        parent = pattern.parent
        name_pattern = pattern.name
        try:
            matches = sorted(parent.glob(name_pattern), key=lambda item: str(item).casefold())
        except OSError:
            continue
        for directory in matches:
            executable = directory / "python.exe"
            if executable.is_file():
                paths.append(str(executable))
    return paths


def build_candidates(
    *,
    current_executable: str | None = None,
    explicit_candidates: Sequence[str] = (),
    which: Which = shutil.which,
    system_paths: Sequence[str] | None = None,
) -> list[Candidate]:
    """Build the deterministic candidate order used by the CLI.

    The current interpreter is always first.  The Python launcher and PATH
    interpreters follow, then explicit and common system-Python paths.  A
    caller can provide explicit candidates without changing the current
    interpreter's first-check guarantee.
    """

    current = current_executable or sys.executable
    candidates: list[Candidate] = []
    if current:
        candidates.append(Candidate("current_interpreter", (current,)))

    py_launcher = which("py")
    if py_launcher:
        candidates.append(Candidate("py_launcher", (py_launcher, "-3")))

    for command_name in ("python", "python3"):
        executable = which(command_name)
        if executable:
            candidates.append(Candidate(f"path_{command_name}", (executable,)))

    for executable in explicit_candidates:
        if executable:
            candidates.append(Candidate("explicit_candidate", (executable,)))

    for executable in (
        list(system_paths)
        if system_paths is not None
        else discover_system_python_paths()
    ):
        if executable:
            candidates.append(Candidate("known_system_path", (executable,)))

    return _dedupe_candidates(candidates)


def _empty_dependencies() -> dict[str, dict[str, Any]]:
    return {
        distribution: {
            "module": module,
            "ok": False,
            "version": None,
            "error": None,
        }
        for distribution, module in REQUIRED_IMPORTS
    }


def _result_base(candidate: Candidate) -> dict[str, Any]:
    return {
        "source": candidate.source,
        "command": list(candidate.command),
        "label": candidate.label,
        "executable": _normalise_path(candidate.command[0]),
        "status": "UNAVAILABLE",
        "ok": False,
        "python_version": None,
        "dependencies": _empty_dependencies(),
        "returncode": None,
        "error": None,
        "stderr": None,
    }


def probe_candidate(
    candidate: Candidate,
    *,
    runner: Runner = subprocess.run,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Probe one candidate and return a JSON-serialisable result."""

    result = _result_base(candidate)
    command = [*candidate.command, "-c", _PROBE_CODE, json.dumps(REQUIRED_IMPORTS)]
    try:
        completed = runner(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        result["status"] = "TIMEOUT"
        result["error"] = f"TimeoutExpired: candidate exceeded {timeout_seconds:g}s"
        result["stderr"] = str(getattr(exc, "stderr", "") or "")[-2000:] or None
        return result
    except (OSError, ValueError) as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
        return result

    result["returncode"] = completed.returncode
    result["stderr"] = (completed.stderr or "")[-2000:] or None
    if completed.returncode != 0:
        result["status"] = "FAIL"
        result["error"] = f"interpreter exited with code {completed.returncode}"
        return result

    try:
        payload = json.loads((completed.stdout or "").strip())
    except json.JSONDecodeError as exc:
        result["status"] = "FAIL"
        result["error"] = f"invalid probe JSON: {exc}"
        return result

    if not isinstance(payload, dict):
        result["status"] = "FAIL"
        result["error"] = "probe JSON was not an object"
        return result

    result["executable"] = _normalise_path(str(payload.get("executable") or candidate.command[0]))
    result["python_version"] = payload.get("python_version")
    dependencies = payload.get("dependencies")
    if isinstance(dependencies, dict):
        for distribution, module in REQUIRED_IMPORTS:
            candidate_result = dependencies.get(distribution)
            if isinstance(candidate_result, dict):
                result["dependencies"][distribution] = {
                    "module": candidate_result.get("module", module),
                    "ok": bool(candidate_result.get("ok", False)),
                    "version": candidate_result.get("version"),
                    "error": candidate_result.get("error"),
                }

    result["ok"] = all(
        bool(result["dependencies"][distribution]["ok"])
        for distribution, _module in REQUIRED_IMPORTS
    )
    result["status"] = "PASS" if result["ok"] else "FAIL"
    if not result["ok"]:
        result["error"] = "one or more required imports failed"
    return result


def run_preflight(
    *,
    current_executable: str | None = None,
    explicit_candidates: Sequence[str] = (),
    which: Which = shutil.which,
    system_paths: Sequence[str] | None = None,
    runner: Runner = subprocess.run,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Probe candidates and return the complete preflight report."""

    candidates = build_candidates(
        current_executable=current_executable,
        explicit_candidates=explicit_candidates,
        which=which,
        system_paths=system_paths,
    )
    results: list[dict[str, Any]] = []
    selected: dict[str, Any] | None = None
    for candidate in candidates:
        result = probe_candidate(
            candidate,
            runner=runner,
            timeout_seconds=timeout_seconds,
        )
        results.append(result)
        if result["ok"]:
            selected = result
            break

    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "checked_at_utc": _datetime.datetime.now(_datetime.timezone.utc).isoformat(),
        "required_imports": [
            {"distribution": distribution, "module": module}
            for distribution, module in REQUIRED_IMPORTS
        ],
        "candidates": results,
        "status": "PASS" if selected is not None else "FAIL",
        "selected_executable": selected["executable"] if selected else None,
        "selected_source": selected["source"] if selected else None,
        "selected_python_version": selected["python_version"] if selected else None,
        "selected_dependencies": selected["dependencies"] if selected else None,
        "failure_reason": None
        if selected is not None
        else "no candidate interpreter imported all required modules",
    }
    return report


def _write_json(path: Path, report: dict[str, Any]) -> None:
    resolved = path.expanduser().resolve()
    parts = {part.casefold() for part in resolved.parts}
    if parts & _FORBIDDEN_REPORT_PARTS:
        raise ValueError("refusing to write a report inside a runtime directory")
    if not resolved.parent.is_dir():
        raise FileNotFoundError(f"report parent directory does not exist: {resolved.parent}")
    resolved.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Check Python runtimes for defusedxml, lxml, and python-pptx; "
            "never installs packages."
        )
    )
    parser.add_argument(
        "--candidate",
        action="append",
        default=[],
        help="Additional Python executable path to check after discovered candidates.",
    )
    parser.add_argument(
        "--json-out",
        type=Path,
        help="Optional user-selected path for a copy of the JSON report.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT_SECONDS,
        help=f"Per-interpreter probe timeout in seconds (default: {DEFAULT_TIMEOUT_SECONDS:g}).",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.timeout <= 0:
        raise SystemExit("--timeout must be greater than zero")

    report = run_preflight(
        explicit_candidates=args.candidate,
        timeout_seconds=args.timeout,
    )
    if args.json_out is not None:
        _write_json(args.json_out, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "PASS" else NO_RUNTIME_EXIT


if __name__ == "__main__":
    raise SystemExit(main())
