from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

from ooxml_common import json_write, sha256_file


DEFAULT_WINDOWS_PATHS = (
    Path(r"C:\Program Files\LibreOffice\program\soffice.exe"),
    Path(r"C:\Program Files (x86)\LibreOffice\program\soffice.exe"),
)


def find_soffice(explicit: Path | None) -> Path:
    if explicit is not None:
        candidate = explicit.expanduser().resolve()
        if candidate.is_file():
            return candidate
        raise FileNotFoundError(candidate)
    from_path = shutil.which("soffice") or shutil.which("soffice.exe")
    if from_path:
        return Path(from_path).resolve()
    for candidate in DEFAULT_WINDOWS_PATHS:
        if candidate.is_file():
            return candidate.resolve()
    raise FileNotFoundError("LibreOffice soffice executable was not found")


def copy_exclusive(source: Path, output: Path) -> None:
    if output.exists():
        raise FileExistsError(f"Output already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    with source.open("rb") as src, output.open("xb") as dst:
        shutil.copyfileobj(src, dst)


def convert(
    mode: str,
    source: Path,
    output: Path,
    soffice: Path,
    timeout: int,
) -> dict[str, object]:
    source = source.resolve()
    output = output.resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    if source == output:
        raise ValueError("Source and output paths must differ")
    if output.exists():
        raise FileExistsError(f"Output already exists: {output}")

    if mode == "recalc":
        if source.suffix.lower() not in {".xlsx", ".xltx"}:
            raise ValueError("Recalc mode supports .xlsx and .xltx only")
        convert_to = "xlsx:Calc MS Excel 2007 XML"
        expected_suffix = ".xlsx"
    elif mode == "pdf":
        if source.suffix.lower() not in {".xlsx", ".xlsm", ".xltx"}:
            raise ValueError("PDF mode expects an OOXML spreadsheet")
        convert_to = "pdf:calc_pdf_Export"
        expected_suffix = ".pdf"
    else:
        raise ValueError(f"Unsupported mode: {mode}")

    with tempfile.TemporaryDirectory(prefix="xlsx-preserve-lo-") as temp_name:
        temp_root = Path(temp_name)
        input_dir = temp_root / "input"
        output_dir = temp_root / "output"
        profile_dir = temp_root / "profile"
        input_dir.mkdir()
        output_dir.mkdir()
        profile_dir.mkdir()
        input_copy = input_dir / source.name
        shutil.copy2(source, input_copy)
        profile_uri = profile_dir.resolve().as_uri()
        command = [
            str(soffice),
            "--headless",
            "--nologo",
            "--nodefault",
            "--nolockcheck",
            "--nofirststartwizard",
            f"-env:UserInstallation={profile_uri}",
            "--convert-to",
            convert_to,
            "--outdir",
            str(output_dir),
            str(input_copy),
        ]
        creation_flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        completed = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
            creationflags=creation_flags,
        )
        candidates = sorted(output_dir.glob(f"*{expected_suffix}"))
        if completed.returncode != 0 or len(candidates) != 1:
            raise RuntimeError(
                "LibreOffice conversion failed: "
                f"exit={completed.returncode}, outputs={len(candidates)}, "
                f"stdout={completed.stdout.strip()}, stderr={completed.stderr.strip()}"
            )
        generated = candidates[0]
        if mode == "recalc":
            if not zipfile.is_zipfile(generated):
                raise ValueError("LibreOffice output is not a valid XLSX package")
            with zipfile.ZipFile(generated, "r") as archive:
                bad = archive.testzip()
                if bad:
                    raise ValueError(f"LibreOffice output has corrupt entry: {bad}")
        copy_exclusive(generated, output)

    return {
        "ok": True,
        "mode": mode,
        "source": str(source),
        "output": str(output),
        "source_sha256": sha256_file(source),
        "output_sha256": sha256_file(output),
        "libreoffice": str(soffice),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run LibreOffice conversion with an isolated user profile"
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
