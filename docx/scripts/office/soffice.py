"""
Windows-safe LibreOffice adapter: delegates conversion to libreoffice-runner.

Only supports: [--headless] --convert-to <filter> [--outdir <dir>] <source>

Unsupported argv shapes return structured failures without starting LibreOffice.
This is a limited-compatibility adapter, NOT a full drop-in for subprocess.run().
"""

import codecs
import json
import os
import subprocess
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Runner path: parents[3] resolves to the shared "skills" root from either layout:
#   source repo:  skills/docx/scripts/office/soffice.py  -> parents[3] = skills/
#   cc-switch:    skills/docx/scripts/office/soffice.py  -> parents[3] = skills/
# Path.resolve() follows symlinks so both layouts produce the same root.
# ---------------------------------------------------------------------------
_RUNNER_SCRIPTS = Path(__file__).resolve().parents[3] / "libreoffice-runner" / "scripts"
if not _RUNNER_SCRIPTS.is_dir():
    raise RuntimeError(f"libreoffice-runner scripts directory not found: {_RUNNER_SCRIPTS}")

if str(_RUNNER_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_RUNNER_SCRIPTS))

from libreoffice_runner import RunReport, RunRequest, run  # noqa: E402

_SUPPORTED_KWARGS = frozenset({
    "capture_output", "text", "universal_newlines",
    "encoding", "errors", "check", "timeout",
})


def get_soffice_env() -> dict:
    """Return a copy of the current environment (no LibreOffice-specific overrides)."""
    return os.environ.copy()


def run_soffice(args, **kwargs) -> subprocess.CompletedProcess:
    """
    Limited-compatibility adapter that translates one conversion argv into a runner call.

    Supported kwargs: capture_output, text, universal_newlines, encoding, errors,
                      check, timeout.
    Any other keyword argument raises TypeError immediately; run() is never called.
    """
    args = list(args)

    # --- validate kwargs first; TypeError before any runner contact ---
    unknown = set(kwargs) - _SUPPORTED_KWARGS
    if unknown:
        raise TypeError(
            f"run_soffice() got unexpected keyword argument(s): {sorted(unknown)!r}"
        )

    text_flag = kwargs.get("text", False)
    uni_flag = kwargs.get("universal_newlines", False)
    if "text" in kwargs and "universal_newlines" in kwargs:
        if bool(text_flag) != bool(uni_flag):
            return _adapter_failure(
                args, "invalid_text_flags",
                "'text' and 'universal_newlines' conflict", kwargs,
            )
    text_mode = bool(text_flag) or bool(uni_flag)

    # Validate codec / error handler before touching runner
    if kwargs.get("encoding") is not None:
        try:
            codecs.lookup(kwargs["encoding"])
        except LookupError as exc:
            return _adapter_failure(args, "invalid_encoding", str(exc), kwargs)
    if kwargs.get("errors") is not None:
        try:
            codecs.lookup_error(kwargs["errors"])
        except LookupError as exc:
            return _adapter_failure(args, "invalid_errors_handler", str(exc), kwargs)

    encoding = kwargs.get("encoding") or "utf-8"
    errors_h = kwargs.get("errors") or "strict"

    timeout_raw = kwargs.get("timeout", None)
    if timeout_raw is None:
        run_timeout = 120.0
    else:
        try:
            run_timeout = float(timeout_raw)
        except (TypeError, ValueError):
            return _adapter_failure(
                args, "invalid_timeout",
                f"timeout must be a positive number, got {timeout_raw!r}", kwargs,
            )
        if run_timeout <= 0:
            return _adapter_failure(
                args, "invalid_timeout",
                f"timeout must be positive, got {run_timeout}", kwargs,
            )

    capture_output = kwargs.get("capture_output", False)
    check = kwargs.get("check", False)

    # --- parse argv ---
    parse_result = _parse_argv(args)
    if isinstance(parse_result, str):
        return _adapter_failure(args, "unsupported_invocation", parse_result, kwargs)

    source_str, convert_to, outdir = parse_result

    # Determine output path from filter extension
    ext = convert_to.split(":")[0].lstrip(".")
    output_name = Path(source_str).stem + "." + ext
    if outdir:
        output_path = Path(outdir) / output_name
    else:
        output_path = Path(source_str).parent / output_name

    operation = "pdf" if ext == "pdf" else "convert"

    request = RunRequest(
        operation=operation,
        source=Path(source_str),
        output=output_path,
        run_timeout=run_timeout,
        convert_to=convert_to if operation == "convert" else None,
    )

    report = run(request)
    runner_report = report.to_dict()

    # Return code: non-zero on failure; prefer non-zero exit_code, else 1
    if report.ok:
        returncode = 0
    else:
        if report.exit_code is not None and report.exit_code != 0:
            returncode = report.exit_code
        else:
            returncode = 1

    # stdout / stderr
    if not capture_output:
        stdout_val = None
        stderr_val = None
    else:
        stdout_bytes = (report.stdout or "").encode("utf-8")
        if report.ok:
            stderr_bytes = (report.stderr or "").encode("utf-8")
        else:
            stderr_bytes = json.dumps({
                "ok": False,
                "error": report.error,
                "message": report.message,
                "owned_pids": report.owned_pids,
                "diagnostics": report.diagnostics,
                "runner_stderr": report.stderr,
            }).encode("utf-8")

        if text_mode:
            stdout_val = stdout_bytes.decode(encoding, errors_h)
            stderr_val = stderr_bytes.decode(encoding, errors_h)
        else:
            stdout_val = stdout_bytes
            stderr_val = stderr_bytes

    result = subprocess.CompletedProcess(
        args=["soffice"] + args,
        returncode=returncode,
        stdout=stdout_val,
        stderr=stderr_val,
    )
    result.runner_report = runner_report

    if check:
        result.check_returncode()

    return result


def _parse_argv(args: list) -> "tuple | str":
    """
    Parse: [--headless] --convert-to <filter> [--outdir <dir>] <source>
    Returns (source, convert_to, outdir) or an error message string.
    """
    seen_convert_to = False
    convert_to = None
    seen_outdir = False
    outdir = None
    sources = []

    i = 0
    while i < len(args):
        tok = str(args[i])
        if tok == "--headless":
            i += 1
            continue
        if tok == "--convert-to":
            if seen_convert_to:
                return "--convert-to appears more than once"
            if i + 1 >= len(args):
                return "--convert-to requires a value"
            val = str(args[i + 1])
            if not val:
                return "--convert-to value must not be empty"
            convert_to = val
            seen_convert_to = True
            i += 2
            continue
        if tok == "--outdir":
            if seen_outdir:
                return "--outdir appears more than once"
            if i + 1 >= len(args):
                return "--outdir requires a value"
            outdir = str(args[i + 1])
            seen_outdir = True
            i += 2
            continue
        if tok.startswith("-env:UserInstallation"):
            return "unsupported: -env:UserInstallation is managed by the runner"
        if tok.startswith("--accept"):
            return "unsupported: --accept (UNO server mode)"
        if tok == "--terminate_after_init":
            return "unsupported: --terminate_after_init"
        if tok.startswith("vnd.sun.star"):
            return "unsupported: macro URI"
        if tok.startswith("-"):
            return f"unsupported option: {tok}"
        sources.append(tok)
        i += 1

    if not seen_convert_to:
        return "--convert-to is required"
    if len(sources) == 0:
        return "source file argument is required"
    if len(sources) > 1:
        return f"only one source file is allowed, got {len(sources)}"

    return (sources[0], convert_to, outdir)


def _adapter_failure(
    args, error: str, message: str, kwargs: dict
) -> subprocess.CompletedProcess:
    """Build a local failure result without calling the runner."""
    capture_output = kwargs.get("capture_output", False) if kwargs else False
    check = kwargs.get("check", False) if kwargs else False

    if capture_output:
        text_mode = bool(kwargs.get("text", False)) or bool(kwargs.get("universal_newlines", False))
        enc = kwargs.get("encoding") or "utf-8"
        err_h = kwargs.get("errors") or "strict"
        raw = json.dumps({
            "ok": False,
            "error": error,
            "message": message,
            "owned_pids": [],
            "diagnostics": None,
            "runner_stderr": "",
        }).encode("utf-8")
        stderr_val = raw.decode(enc, err_h) if text_mode else raw
        stdout_val = "" if text_mode else b""
    else:
        stdout_val = None
        stderr_val = None

    runner_report = RunReport(
        ok=False, operation="convert", source="", output="",
        error=error, message=message,
    ).to_dict()

    result = subprocess.CompletedProcess(
        args=["soffice"] + (list(args) if args else []),
        returncode=2,
        stdout=stdout_val,
        stderr=stderr_val,
    )
    result.runner_report = runner_report

    if check:
        result.check_returncode()

    return result


if __name__ == "__main__":
    result = run_soffice(sys.argv[1:], capture_output=True, text=True)
    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)
    sys.exit(result.returncode)
