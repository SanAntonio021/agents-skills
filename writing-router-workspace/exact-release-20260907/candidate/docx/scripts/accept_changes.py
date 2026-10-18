"""Accept all tracked changes in a DOCX file using libreoffice-runner."""

import argparse
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Runner path: parents[2] resolves to the shared "skills" root:
#   source repo:  skills/docx/scripts/accept_changes.py -> parents[2] = skills/
#   cc-switch:    skills/docx/scripts/accept_changes.py -> parents[2] = skills/
# ---------------------------------------------------------------------------
_RUNNER_SCRIPTS = Path(__file__).resolve().parents[2] / "libreoffice-runner" / "scripts"
if not _RUNNER_SCRIPTS.is_dir():
    raise RuntimeError(f"libreoffice-runner scripts directory not found: {_RUNNER_SCRIPTS}")

if str(_RUNNER_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_RUNNER_SCRIPTS))

from libreoffice_runner import RunRequest, run  # noqa: E402


def accept_changes(
    input_file: str,
    output_file: str,
) -> tuple:
    """Accept all tracked changes in a DOCX file via libreoffice-runner.

    Returns (None, message) matching the original interface.
    Input validation is performed locally; runner is called only for valid requests.
    """
    input_path = Path(input_file)
    output_path = Path(output_file)

    if not input_path.exists():
        return None, f"Error: Input file not found: {input_file}"

    if input_path.suffix.lower() != ".docx":
        return None, f"Error: Input file is not a DOCX file: {input_file}"

    request = RunRequest(
        operation="accept-changes",
        source=input_path,
        output=output_path,
    )
    report = run(request)

    if report.ok:
        return None, f"Successfully accepted all tracked changes: {input_file} -> {output_file}"

    diagnostics_info = (
        f" (diagnostics: {report.diagnostics})" if report.diagnostics else ""
    )
    return (
        None,
        f"Error: accept-changes failed [{report.error}]: {report.message}{diagnostics_info}",
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Accept all tracked changes in a DOCX file"
    )
    parser.add_argument("input_file", help="Input DOCX file with tracked changes")
    parser.add_argument(
        "output_file", help="Output DOCX file (clean, no tracked changes)"
    )
    args = parser.parse_args()

    _, message = accept_changes(args.input_file, args.output_file)
    print(message)

    if "Error" in message:
        raise SystemExit(1)
