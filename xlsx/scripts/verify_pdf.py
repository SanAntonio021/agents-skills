from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from ooxml_common import json_write, sha256_file


def is_ascii(value: str) -> bool:
    try:
        value.encode("ascii")
        return True
    except UnicodeEncodeError:
        return False


def image_count(page: Any) -> int:
    try:
        resources = page.get("/Resources")
        if resources is None:
            return 0
        resources = resources.get_object()
        xobjects = resources.get("/XObject")
        if xobjects is None:
            return 0
        xobjects = xobjects.get_object()
        count = 0
        for value in xobjects.values():
            obj = value.get_object()
            if obj.get("/Subtype") == "/Image":
                count += 1
        return count
    except Exception:
        return 0


def find_pdftoppm(explicit: Path | None) -> Path:
    if explicit is not None:
        candidate = explicit.expanduser().resolve()
        if candidate.is_file():
            return candidate
        raise FileNotFoundError(candidate)
    located = shutil.which("pdftoppm") or shutil.which("pdftoppm.exe")
    if located:
        return Path(located).resolve()
    raise FileNotFoundError("pdftoppm was not found; render verification cannot run")


def render_pdf(
    pdf: Path,
    render_dir: Path,
    dpi: int,
    executable: Path,
    expected_pages: int,
) -> list[str]:
    if render_dir.exists():
        raise FileExistsError(f"Render directory already exists: {render_dir}")
    render_dir.mkdir(parents=True)
    prefix = render_dir / "page"
    command = [
        str(executable),
        "-png",
        "-r",
        str(dpi),
        "-cropbox",
        str(pdf),
        str(prefix),
    ]
    creation_flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    completed = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        creationflags=creation_flags,
    )
    files = sorted(render_dir.glob("page-*.png"))
    if completed.returncode != 0 or len(files) != expected_pages:
        raise RuntimeError(
            "PDF rendering failed: "
            f"exit={completed.returncode}, expected_pages={expected_pages}, "
            f"rendered_pages={len(files)}, stderr={completed.stderr.strip()}"
        )
    empty = [str(path) for path in files if path.stat().st_size == 0]
    if empty:
        raise ValueError(f"Rendered empty PNG files: {empty}")
    return [str(path.resolve()) for path in files]


def inspect_pdf(
    pdf: Path,
    expected_pages: int | None,
    orientation: str | None,
    expect_every_page: list[str],
    expect_document: list[str],
    min_text_chars: int,
) -> dict[str, Any]:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError("pypdf is required for PDF verification") from exc

    pdf = pdf.resolve()
    if not pdf.is_file():
        raise FileNotFoundError(pdf)
    reader = PdfReader(str(pdf))
    if reader.is_encrypted:
        raise ValueError("Encrypted PDFs are not supported")
    pages: list[dict[str, Any]] = []
    all_text: list[str] = []
    failures: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    for index, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        normalized = " ".join(text.split())
        all_text.append(text)
        width = float(page.mediabox.width)
        height = float(page.mediabox.height)
        rotation = int(page.get("/Rotate", 0) or 0) % 360
        effective_width, effective_height = (
            (height, width) if rotation in {90, 270} else (width, height)
        )
        actual_orientation = (
            "landscape" if effective_width > effective_height else "portrait"
        )
        images = image_count(page)
        blank = len(normalized) < min_text_chars and images == 0
        missing = [item for item in expect_every_page if item not in text]
        replacement_ratio = text.count("\ufffd") / max(len(text), 1)
        text_reliable = replacement_ratio <= 0.02
        if blank:
            failures.append({"page": index, "reason": "blank_page"})
        if orientation and actual_orientation != orientation:
            failures.append(
                {
                    "page": index,
                    "reason": "orientation",
                    "expected": orientation,
                    "actual": actual_orientation,
                }
            )
        if missing:
            definite = [item for item in missing if text_reliable or is_ascii(item)]
            uncertain = [item for item in missing if item not in definite]
            if definite:
                failures.append(
                    {
                        "page": index,
                        "reason": "missing_required_text",
                        "values": definite,
                    }
                )
            if uncertain:
                warnings.append(
                    {
                        "page": index,
                        "reason": "required_text_unverifiable",
                        "values": uncertain,
                        "replacement_character_ratio": round(replacement_ratio, 6),
                    }
                )
        pages.append(
            {
                "page": index,
                "width_points": width,
                "height_points": height,
                "rotation": rotation,
                "orientation": actual_orientation,
                "text_characters": len(normalized),
                "text_extraction_reliable": text_reliable,
                "replacement_character_ratio": round(replacement_ratio, 6),
                "text_head": normalized[:160],
                "text_tail": normalized[-240:],
                "image_count": images,
                "blank": blank,
                "missing_required_text": missing,
            }
        )

    if expected_pages is not None and len(pages) != expected_pages:
        failures.append(
            {
                "reason": "page_count",
                "expected": expected_pages,
                "actual": len(pages),
            }
        )
    document_text = "\n".join(all_text)
    missing_document = [item for item in expect_document if item not in document_text]
    if missing_document:
        document_reliable = all(page["text_extraction_reliable"] for page in pages)
        definite = [item for item in missing_document if document_reliable or is_ascii(item)]
        uncertain = [item for item in missing_document if item not in definite]
        if definite:
            failures.append({"reason": "missing_document_text", "values": definite})
        if uncertain:
            warnings.append(
                {"reason": "document_text_unverifiable", "values": uncertain}
            )

    return {
        "ok": not failures,
        "pdf": str(pdf),
        "sha256": sha256_file(pdf),
        "page_count": len(pages),
        "pages": pages,
        "failures": failures,
        "warnings": warnings,
        "text_checks_complete": not warnings,
        "visual_inspection_required": True,
        "visual_note": (
            "Automated checks do not prove absence of clipping or overlap. Unreliable text extraction also requires visual confirmation of expected text."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify and render a PDF workbook export")
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--expected-pages", type=int)
    orientation = parser.add_mutually_exclusive_group()
    orientation.add_argument("--landscape", action="store_true")
    orientation.add_argument("--portrait", action="store_true")
    parser.add_argument("--expect-every-page", action="append", default=[])
    parser.add_argument("--expect-document", action="append", default=[])
    parser.add_argument("--min-text-chars", type=int, default=1)
    parser.add_argument("--render-dir", type=Path)
    parser.add_argument("--dpi", type=int, default=200)
    parser.add_argument("--pdftoppm", type=Path)
    parser.add_argument("--json-out", type=Path)
    args = parser.parse_args()
    selected_orientation = "landscape" if args.landscape else "portrait" if args.portrait else None
    try:
        report = inspect_pdf(
            args.pdf,
            args.expected_pages,
            selected_orientation,
            args.expect_every_page,
            args.expect_document,
            args.min_text_chars,
        )
        if args.render_dir:
            report["rendered_pages"] = render_pdf(
                args.pdf.resolve(),
                args.render_dir.resolve(),
                args.dpi,
                find_pdftoppm(args.pdftoppm),
                report["page_count"],
            )
        print(json_write(report, args.json_out))
        return 0 if report["ok"] else 2
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
