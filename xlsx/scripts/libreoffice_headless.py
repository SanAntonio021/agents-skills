from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ooxml_common import json_write


RUNNER_SCRIPTS = Path(__file__).resolve().parents[2] / "libreoffice-runner" / "scripts"
if not RUNNER_SCRIPTS.is_dir():
    raise RuntimeError(f"libreoffice-runner source is missing: {RUNNER_SCRIPTS}")
if str(RUNNER_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(RUNNER_SCRIPTS))

from libreoffice_runner import convert as _runner_convert  # noqa: E402
from libreoffice_runner import find_soffice as _runner_find_soffice  # noqa: E402


def find_soffice(explicit: Path | None) -> Path:
    """Keep the xlsx public helper API while using the shared runner lookup."""

    return _runner_find_soffice(explicit)


def convert(
    mode: str,
    source: Path,
    output: Path,
    soffice: Path,
    timeout: int,
) -> dict[str, object]:
    """Compatibility wrapper; never fall back to a direct LibreOffice subprocess."""

    return _runner_convert(mode, source, output, soffice, timeout)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run XLSX LibreOffice operations through the shared isolated runner"
    )
    parser.add_argument("mode", choices=("recalc", "pdf"))
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--soffice", type=Path)
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--json-out", type=Path)
    args = parser.parse_args()
    try:
        report = convert(
            args.mode,
            args.source,
            args.output,
            find_soffice(args.soffice),
            args.timeout,
        )
        print(json_write(report, args.json_out))
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
