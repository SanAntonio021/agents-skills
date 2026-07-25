#!/usr/bin/env python3
"""Deterministic local PDF OCR router and validator.

The script intentionally keeps all environment changes process-local. It never
modifies the input PDF and only publishes artifacts after validation succeeds.
"""

from __future__ import annotations

import argparse
import collections
import dataclasses
import datetime as dt
import hashlib
import itertools
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import time
import unicodedata
import uuid
from collections.abc import Iterable, Sequence
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

import fitz
from pypdf import PdfReader

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_DEPENDENCY = 3
EXIT_INPUT = 4
EXIT_ENGINE = 5
EXIT_VALIDATION = 6
EXIT_CONFLICT = 7

SCHEMA_VERSION = 1
MIN_SCAN_IMAGE_COVERAGE = 0.45
FULL_PAGE_IMAGE_COVERAGE = 0.55
SPARSE_TEXT_LIMIT = 32
MIN_GOOD_TEXT_CHARS = 20
BAD_TEXT_RATIO_LIMIT = 0.20


class PipelineError(RuntimeError):
    """Expected pipeline failure with a stable process exit code."""

    def __init__(self, message: str, exit_code: int, *, details: Any = None) -> None:
        super().__init__(message)
        self.exit_code = exit_code
        self.details = details


@dataclasses.dataclass
class PageFeatures:
    page_number: int
    width: float
    height: float
    rotation: int
    text_chars: int
    visible_chars: int
    bad_text_chars: int
    bad_text_ratio: float
    image_count: int
    image_coverage: float
    category: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "page_number": self.page_number,
            "width_points": round(self.width, 3),
            "height_points": round(self.height, 3),
            "rotation": self.rotation,
            "text_chars": self.text_chars,
            "visible_chars": self.visible_chars,
            "bad_text_chars": self.bad_text_chars,
            "bad_text_ratio": round(self.bad_text_ratio, 4),
            "image_count": self.image_count,
            "image_coverage": round(self.image_coverage, 4),
            "category": self.category,
        }


@dataclasses.dataclass
class Inspection:
    path: Path
    pages: list[PageFeatures]
    encrypted: bool

    @property
    def page_count(self) -> int:
        return len(self.pages)

    def as_dict(self) -> dict[str, Any]:
        return {
            "page_count": self.page_count,
            "encrypted": self.encrypted,
            "pages": [page.as_dict() for page in self.pages],
        }


@dataclasses.dataclass
class Dependencies:
    tesseract: Path | None
    tessdata: Path | None
    pdftotext: Path
    pdfinfo: Path
    pdftoppm: Path
    python: str
    versions: dict[str, str]
    ghostscript: str | None
    qpdf: str | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "python": self.python,
            "tesseract": str(self.tesseract) if self.tesseract else None,
            "tessdata": str(self.tessdata) if self.tessdata else None,
            "pdftotext": str(self.pdftotext),
            "pdfinfo": str(self.pdfinfo),
            "pdftoppm": str(self.pdftoppm),
            "versions": self.versions,
            "ghostscript": self.ghostscript,
            "qpdf": self.qpdf,
        }


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def json_dump(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while True:
            block = stream.read(chunk_size)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest().upper()


def run_command(
    command: Sequence[str],
    *,
    env: dict[str, str] | None = None,
    timeout: int = 120,
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            list(command),
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as exc:
        raise PipelineError(f"Executable not found: {command[0]}", EXIT_DEPENDENCY) from exc
    except subprocess.TimeoutExpired as exc:
        raise PipelineError(
            f"Command timed out after {timeout}s: {command[0]}",
            EXIT_ENGINE,
        ) from exc


def first_line(output: str) -> str:
    for line in output.splitlines():
        if line.strip():
            return line.strip()
    return ""


def locate_executable(
    candidates: Iterable[Path],
    names: Iterable[str],
    *,
    env_name: str | None = None,
) -> Path | None:
    if env_name:
        override = os.environ.get(env_name)
        if override:
            candidate = Path(override)
            if candidate.is_file():
                return candidate.resolve()
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    for name in names:
        resolved = shutil.which(name)
        if resolved:
            return Path(resolved).resolve()
    return None


def locate_dependencies(require_ocr: bool, languages: Sequence[str]) -> Dependencies:
    local_app = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local"))
    user_profile = Path(os.environ.get("USERPROFILE", Path.home()))
    tesseract_dirs = [
        local_app / "Programs" / "Tesseract-OCR",
        local_app / "pdf-ocr" / "tesseract",
        Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Tesseract-OCR",
        Path(os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)"))
        / "Tesseract-OCR",
    ]
    tesseract = locate_executable(
        [directory / "tesseract.exe" for directory in tesseract_dirs],
        ("tesseract.exe", "tesseract"),
        env_name="PDF_OCR_TESSERACT",
    )
    tessdata: Path | None = None
    if tesseract:
        override_tessdata = os.environ.get("PDF_OCR_TESSDATA")
        if override_tessdata and Path(override_tessdata).is_dir():
            tessdata = Path(override_tessdata).resolve()
        else:
            sibling = tesseract.parent / "tessdata"
            if sibling.is_dir():
                tessdata = sibling.resolve()

    poppler_bin_env = os.environ.get("PDF_OCR_POPPLER_BIN")
    poppler_dirs: list[Path] = []
    if poppler_bin_env:
        poppler_dirs.append(Path(poppler_bin_env))
    poppler_dirs.extend(
        [
            user_profile / "poppler" / "poppler-24.08.0" / "Library" / "bin",
            Path(os.environ.get("ProgramFiles", "C:/Program Files"))
            / "poppler"
            / "Library"
            / "bin",
        ]
    )

    def poppler(name: str) -> Path | None:
        return locate_executable(
            [directory / name for directory in poppler_dirs],
            (name,),
        )

    pdftotext = poppler("pdftotext.exe") or poppler("pdftotext")
    pdfinfo = poppler("pdfinfo.exe") or poppler("pdfinfo")
    pdftoppm = poppler("pdftoppm.exe") or poppler("pdftoppm")
    missing = [
        label
        for label, value in (
            ("pdftotext", pdftotext),
            ("pdfinfo", pdfinfo),
            ("pdftoppm", pdftoppm),
        )
        if value is None
    ]
    if missing:
        raise PipelineError(
            "Missing Poppler executable(s): " + ", ".join(missing),
            EXIT_DEPENDENCY,
        )
    if require_ocr and (tesseract is None or tessdata is None):
        raise PipelineError(
            "OCR requires Tesseract and a sibling tessdata directory",
            EXIT_DEPENDENCY,
        )

    versions: dict[str, str] = {
        "ocrmypdf": package_version("ocrmypdf"),
        "pymupdf": package_version("PyMuPDF"),
        "pypdf": package_version("pypdf"),
        "pypdfium2": package_version("pypdfium2"),
    }
    for label, executable in (
        ("tesseract", tesseract),
        ("pdftotext", pdftotext),
        ("pdfinfo", pdfinfo),
        ("pdftoppm", pdftoppm),
    ):
        if executable is None:
            continue
        result = run_command([str(executable), "-v"], timeout=30)
        versions[label] = first_line(result.stdout + "\n" + result.stderr)

    if require_ocr and tesseract and tessdata:
        env = process_environment(tesseract, tessdata, poppler_dirs)
        result = run_command(
            [
                str(tesseract),
                "--tessdata-dir",
                str(tessdata),
                "--list-langs",
            ],
            env=env,
            timeout=30,
        )
        if result.returncode != 0:
            raise PipelineError(
                "Tesseract language listing failed: "
                + first_line(result.stderr or result.stdout),
                EXIT_DEPENDENCY,
            )
        available = {
            line.strip()
            for line in (result.stdout + "\n" + result.stderr).splitlines()
            if line.strip() and not line.lower().startswith("list of available")
        }
        missing_languages = [language for language in languages if language not in available]
        if missing_languages:
            raise PipelineError(
                "Tesseract language pack(s) missing: "
                + ", ".join(missing_languages),
                EXIT_DEPENDENCY,
            )

    ghostscript = shutil.which("gswin64c") or shutil.which("gswin32c") or shutil.which("gs")
    qpdf = shutil.which("qpdf")
    return Dependencies(
        tesseract=tesseract,
        tessdata=tessdata,
        pdftotext=pdftotext,
        pdfinfo=pdfinfo,
        pdftoppm=pdftoppm,
        python=sys.executable,
        versions=versions,
        ghostscript=ghostscript,
        qpdf=qpdf,
    )


def package_version(distribution: str) -> str:
    try:
        return version(distribution)
    except PackageNotFoundError:
        return "unknown"


def process_environment(
    tesseract: Path | None,
    tessdata: Path | None,
    poppler_dirs: Sequence[Path] = (),
) -> dict[str, str]:
    env = os.environ.copy()
    path_entries: list[str] = []
    if tesseract:
        path_entries.append(str(tesseract.parent))
    path_entries.extend(str(directory) for directory in poppler_dirs if directory.is_dir())
    path_entries.append(env.get("PATH", ""))
    env["PATH"] = os.pathsep.join(path_entries)
    if tessdata:
        env["TESSDATA_PREFIX"] = str(tessdata)
    else:
        env.pop("TESSDATA_PREFIX", None)
    return env


def rect_union_area(rects: Sequence[fitz.Rect]) -> float:
    """Return exact union area for axis-aligned image rectangles."""
    if not rects:
        return 0.0
    xs = sorted({coordinate for rect in rects for coordinate in (rect.x0, rect.x1)})
    area = 0.0
    for left, right in itertools.pairwise(xs):
        if right <= left:
            continue
        active = [
            (rect.y0, rect.y1)
            for rect in rects
            if rect.x0 < right and rect.x1 > left and rect.y0 < rect.y1
        ]
        active.sort()
        covered_y = 0.0
        current_start: float | None = None
        current_end: float | None = None
        for start, end in active:
            if current_start is None:
                current_start, current_end = start, end
            elif start > current_end:
                covered_y += current_end - current_start
                current_start, current_end = start, end
            else:
                current_end = max(current_end, end)
        if current_start is not None and current_end is not None:
            covered_y += current_end - current_start
        area += (right - left) * covered_y
    return area


def text_metrics(text: str) -> tuple[int, int, int, float]:
    visible = 0
    bad = 0
    mojibake = 0
    for char in text:
        if char.isspace():
            continue
        visible += 1
        category = unicodedata.category(char)
        if char in {"\ufffd", "\x00"} or category in {"Cc", "Cs", "Co", "Cn"}:
            bad += 1
    for token in ("Ã", "Â", "â€", "锟斤拷", "\ufffd"):
        mojibake += text.count(token)
    bad = min(visible, bad + min(visible, mojibake * 2))
    question_marks = text.count("?")
    if question_marks >= 6 and question_marks / max(visible, 1) >= 0.15:
        bad = min(visible, bad + question_marks)
    ratio = bad / visible if visible else 0.0
    return len(text), visible, bad, ratio


def classify_page(
    *,
    visible_chars: int,
    bad_text_ratio: float,
    image_coverage: float,
) -> str:
    if visible_chars >= 8 and bad_text_ratio >= BAD_TEXT_RATIO_LIMIT:
        return "broken"
    if image_coverage >= FULL_PAGE_IMAGE_COVERAGE:
        if visible_chars <= 3:
            return "scan"
        if visible_chars < SPARSE_TEXT_LIMIT:
            return "page_mixed"
        return "good_ocr"
    if visible_chars <= 3:
        return "blank"
    if visible_chars >= MIN_GOOD_TEXT_CHARS and bad_text_ratio < BAD_TEXT_RATIO_LIMIT:
        return "digital"
    return "sparse_text"


def inspect_pdf(path: Path) -> Inspection:
    try:
        document = fitz.open(path)
    except Exception as exc:
        raise PipelineError(f"Cannot open input PDF: {exc}", EXIT_INPUT) from exc
    try:
        if document.needs_pass:
            raise PipelineError(
                "Encrypted PDF requires an explicit password workflow",
                EXIT_INPUT,
            )
        pages: list[PageFeatures] = []
        for index, page in enumerate(document):
            text = page.get_text("text", sort=True)
            text_chars, visible, bad, bad_ratio = text_metrics(text)
            image_rects: list[fitz.Rect] = []
            for image in page.get_images(full=True):
                xref = image[0]
                for image_rect in page.get_image_rects(xref):
                    clipped = fitz.Rect(image_rect)
                    clipped.intersect(page.rect)
                    if not clipped.is_empty and clipped.get_area() > 0:
                        image_rects.append(clipped)
            page_area = max(page.rect.get_area(), 1.0)
            coverage = min(1.0, rect_union_area(image_rects) / page_area)
            pages.append(
                PageFeatures(
                    page_number=index + 1,
                    width=page.rect.width,
                    height=page.rect.height,
                    rotation=page.rotation,
                    text_chars=text_chars,
                    visible_chars=visible,
                    bad_text_chars=bad,
                    bad_text_ratio=bad_ratio,
                    image_count=len(page.get_images(full=True)),
                    image_coverage=coverage,
                    category=classify_page(
                        visible_chars=visible,
                        bad_text_ratio=bad_ratio,
                        image_coverage=coverage,
                    ),
                )
            )
        if not pages:
            raise PipelineError("Input PDF has no pages", EXIT_INPUT)
        return Inspection(path=path, pages=pages, encrypted=False)
    except PipelineError:
        raise
    except Exception as exc:
        raise PipelineError(f"Cannot inspect input PDF: {exc}", EXIT_INPUT) from exc
    finally:
        document.close()


def select_mode(pages: Sequence[PageFeatures], requested: str) -> tuple[str, str]:
    if requested != "auto":
        reasons = {
            "none": "user requested no OCR",
            "skip": "user requested OCR only where no text layer exists",
            "redo": "user requested OCR layer replacement",
        }
        return requested, reasons[requested]
    categories = collections.Counter(page.category for page in pages)
    if categories["broken"] or categories["page_mixed"]:
        reason = "page-level mixed content or damaged text layer detected"
        return "redo", reason
    if categories["scan"]:
        if categories["digital"] or categories["good_ocr"] or categories["sparse_text"]:
            return "skip", "document-level mixture of image-only and text-bearing pages"
        return "skip", "image-only pages detected"
    return "none", "text layer is present and no damaged or mixed page was detected"


def validate_languages(raw: str) -> list[str]:
    if not re.fullmatch(r"[A-Za-z0-9_]+(?:\+[A-Za-z0-9_]+)*", raw):
        raise PipelineError(
            "Languages must be an explicit + separated Tesseract list",
            EXIT_USAGE,
        )
    languages = raw.split("+")
    if len(set(languages)) != len(languages):
        raise PipelineError("Languages must not contain duplicates", EXIT_USAGE)
    return languages


def nonwhite_fraction(pixmap: fitz.Pixmap) -> float:
    channels = pixmap.n
    samples = pixmap.samples
    if not samples or channels < 3:
        return 0.0
    total_pixels = pixmap.width * pixmap.height
    stride = max(1, total_pixels // 50000)
    nonwhite = 0
    sampled = 0
    for pixel_index in range(0, total_pixels, stride):
        offset = pixel_index * channels
        red, green, blue = samples[offset : offset + 3]
        sampled += 1
        if min(red, green, blue) < 245:
            nonwhite += 1
    return nonwhite / sampled if sampled else 0.0


def render_validation(
    input_pdf: Path,
    output_pdf: Path,
    output_dir: Path,
    dependencies: Dependencies,
) -> dict[str, Any]:
    try:
        input_doc = fitz.open(input_pdf)
        output_doc = fitz.open(output_pdf)
    except Exception as exc:
        raise PipelineError(f"Output cannot be opened by PyMuPDF: {exc}", EXIT_VALIDATION) from exc
    try:
        if input_doc.page_count != output_doc.page_count:
            raise PipelineError("Output page count differs from input", EXIT_VALIDATION)
        page_reports: list[dict[str, Any]] = []
        for index, (input_page, output_page) in enumerate(zip(input_doc, output_doc), start=1):
            input_size = (input_page.rect.width, input_page.rect.height)
            output_size = (output_page.rect.width, output_page.rect.height)
            if any(abs(a - b) > 0.5 for a, b in zip(input_size, output_size)):
                raise PipelineError(f"Page {index} size changed", EXIT_VALIDATION)
            if input_page.rotation != output_page.rotation:
                raise PipelineError(f"Page {index} rotation changed", EXIT_VALIDATION)
            input_pix = input_page.get_pixmap(dpi=36, alpha=False)
            output_pix = output_page.get_pixmap(dpi=36, alpha=False)
            input_nonwhite = nonwhite_fraction(input_pix)
            output_nonwhite = nonwhite_fraction(output_pix)
            if input_nonwhite > 0.002 and output_nonwhite < 0.0002:
                raise PipelineError(f"Page {index} became blank after OCR", EXIT_VALIDATION)
            page_reports.append(
                {
                    "page_number": index,
                    "input_size_points": [round(value, 3) for value in input_size],
                    "output_size_points": [round(value, 3) for value in output_size],
                    "input_rotation": input_page.rotation,
                    "output_rotation": output_page.rotation,
                    "input_nonwhite_fraction": round(input_nonwhite, 6),
                    "output_nonwhite_fraction": round(output_nonwhite, 6),
                    "render_width": output_pix.width,
                    "render_height": output_pix.height,
                }
            )
    finally:
        input_doc.close()
        output_doc.close()

    try:
        reader = PdfReader(str(output_pdf), strict=True)
        if len(reader.pages) != len(page_reports):
            raise PipelineError("pypdf page count validation failed", EXIT_VALIDATION)
    except PipelineError:
        raise
    except Exception as exc:
        raise PipelineError(f"Output cannot be opened by pypdf strict mode: {exc}", EXIT_VALIDATION) from exc

    info = run_command([str(dependencies.pdfinfo), str(output_pdf)], timeout=60)
    if info.returncode != 0:
        raise PipelineError(
            "pdfinfo failed: " + first_line(info.stderr or info.stdout),
            EXIT_VALIDATION,
        )
    render_prefix = output_dir / "poppler-render"
    render = run_command(
        [
            str(dependencies.pdftoppm),
            "-r",
            "36",
            "-png",
            str(output_pdf),
            str(render_prefix),
        ],
        timeout=300,
    )
    if render.returncode != 0:
        raise PipelineError(
            "pdftoppm failed: " + first_line(render.stderr or render.stdout),
            EXIT_VALIDATION,
        )
    rendered_files = sorted(output_dir.glob("poppler-render-*.png"))
    if len(rendered_files) != len(page_reports):
        raise PipelineError(
            f"Poppler rendered {len(rendered_files)} pages; expected {len(page_reports)}",
            EXIT_VALIDATION,
        )
    for rendered_file in rendered_files:
        rendered_file.unlink(missing_ok=True)
    return {
        "pymupdf": page_reports,
        "pypdf_strict": True,
        "pdfinfo": True,
        "pdftoppm": True,
    }


def extract_text(
    output_pdf: Path,
    output_txt: Path,
    dependencies: Dependencies,
) -> str:
    result = run_command(
        [
            str(dependencies.pdftotext),
            "-layout",
            "-enc",
            "UTF-8",
            str(output_pdf),
            str(output_txt),
        ],
        timeout=300,
    )
    if result.returncode == 0 and output_txt.is_file():
        text = output_txt.read_text(encoding="utf-8", errors="replace")
        if text.strip():
            return text

    try:
        document = fitz.open(output_pdf)
        try:
            text = "\n\f\n".join(page.get_text("text", sort=True) for page in document)
        finally:
            document.close()
        output_txt.write_text(text, encoding="utf-8")
        if result.returncode != 0:
            return text
        if text.strip():
            return text
    except Exception as exc:
        raise PipelineError(f"Text extraction fallback failed: {exc}", EXIT_VALIDATION) from exc
    if result.returncode != 0:
        raise PipelineError(
            "pdftotext failed: " + first_line(result.stderr or result.stdout),
            EXIT_VALIDATION,
        )
    return output_txt.read_text(encoding="utf-8", errors="replace")


def run_ocr(
    input_pdf: Path,
    temporary_output: Path,
    mode: str,
    languages: str,
    deskew: bool,
    jobs: int,
    timeout_seconds: int,
    dependencies: Dependencies,
    logger: logging.Logger,
) -> None:
    if mode == "none":
        shutil.copy2(input_pdf, temporary_output)
        logger.info("No OCR selected; copied input to staging output.")
        return
    command = [
        sys.executable,
        "-m",
        "ocrmypdf",
        "--mode",
        mode,
        "-l",
        languages,
        "--output-type",
        "pdf",
        "--optimize",
        "0",
        "--jobs",
        str(jobs),
    ]
    if deskew:
        command.append("--deskew")
    command.extend([str(input_pdf), str(temporary_output)])
    logger.info("Running OCRmyPDF mode=%s languages=%s deskew=%s", mode, languages, deskew)
    poppler_dirs = [dependencies.pdftotext.parent]
    env = process_environment(dependencies.tesseract, dependencies.tessdata, poppler_dirs)
    result = run_command(command, env=env, timeout=timeout_seconds)
    if result.stdout:
        logger.info("OCRmyPDF stdout:\n%s", result.stdout.rstrip())
    if result.stderr:
        logger.info("OCRmyPDF stderr:\n%s", result.stderr.rstrip())
    if result.returncode != 0:
        raise PipelineError(
            f"OCRmyPDF failed with exit code {result.returncode}",
            EXIT_ENGINE,
            details={"ocrmypdf_exit_code": result.returncode},
        )
    if not temporary_output.is_file() or temporary_output.stat().st_size == 0:
        raise PipelineError("OCRmyPDF returned success without a PDF output", EXIT_ENGINE)


def setup_logger(log_path: Path) -> logging.Logger:
    logger = logging.getLogger(f"pdf_ocr_{uuid.uuid4().hex}")
    logger.setLevel(logging.INFO)
    handler = logging.FileHandler(log_path, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)
    return logger


def close_logger(logger: logging.Logger) -> None:
    for handler in list(logger.handlers):
        handler.flush()
        handler.close()
        logger.removeHandler(handler)


def artifact_paths(input_pdf: Path, output_dir: Path) -> dict[str, Path]:
    stem = input_pdf.stem
    return {
        "pdf": output_dir / f"{stem}_ocr.pdf",
        "txt": output_dir / f"{stem}_ocr.txt",
        "log": output_dir / f"{stem}_ocr.log",
        "status": output_dir / f"{stem}_ocr.status.json",
    }


def ensure_output_targets_are_free(
    input_pdf: Path,
    targets: dict[str, Path],
) -> None:
    resolved_input = input_pdf.resolve()
    conflicts = [
        str(path)
        for path in targets.values()
        if path.exists() or path.resolve() == resolved_input
    ]
    if conflicts:
        raise PipelineError(
            "Output already exists or points to input: " + ", ".join(conflicts),
            EXIT_CONFLICT,
        )


def base_status(
    *,
    run_id: str,
    started_at: str,
    input_pdf: Path,
    requested_mode: str,
    languages: str,
    deskew: bool,
    jobs: int,
    timeout_seconds: int,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "running",
        "run_id": run_id,
        "started_at": started_at,
        "finished_at": None,
        "duration_seconds": None,
        "exit_code": None,
        "input": {
            "path": str(input_pdf),
            "sha256": None,
            "bytes": input_pdf.stat().st_size,
        },
        "route": {
            "requested_mode": requested_mode,
            "selected_mode": None,
            "reason": None,
            "languages": languages,
            "deskew": deskew,
            "jobs": jobs,
            "timeout_seconds": timeout_seconds,
            "inspection": None,
        },
        "dependencies": None,
        "output": None,
        "validation": None,
        "error": None,
    }


def finalize(
    staged: dict[str, Path],
    targets: dict[str, Path],
    temporary_dir: Path,
) -> None:
    moved_keys: list[str] = []
    try:
        for key in ("pdf", "txt", "log", "status"):
            if targets[key].exists():
                raise FileExistsError(f"Output appeared during publish: {targets[key]}")
            os.rename(staged[key], targets[key])
            moved_keys.append(key)
    except Exception:
        for key in reversed(moved_keys):
            if targets[key].exists():
                os.rename(targets[key], staged[key])
        raise
    shutil.rmtree(temporary_dir, ignore_errors=True)


def process(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    started_clock = time.monotonic()
    started_at = now_utc()
    input_pdf = Path(args.input).expanduser().resolve()
    languages = validate_languages(args.languages)
    if not input_pdf.is_file():
        raise PipelineError(f"Input PDF does not exist: {input_pdf}", EXIT_INPUT)
    if input_pdf.suffix.lower() != ".pdf":
        raise PipelineError("Input must have a .pdf extension", EXIT_INPUT)
    if args.output_directory:
        output_dir = Path(args.output_directory).expanduser().resolve()
    else:
        output_dir = input_pdf.parent
    output_dir.mkdir(parents=True, exist_ok=True)
    targets = artifact_paths(input_pdf, output_dir)
    ensure_output_targets_are_free(input_pdf, targets)
    run_id = (
        dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d-%H%M%S")
        + "-"
        + uuid.uuid4().hex[:8]
    )
    temporary_dir = output_dir / f".pdf-ocr-run-{run_id}"
    temporary_dir.mkdir()
    staged = {
        "pdf": temporary_dir / "output.pdf",
        "txt": temporary_dir / "output.txt",
        "log": temporary_dir / "run.log",
        "status": temporary_dir / "status.json",
    }
    logger = setup_logger(staged["log"])
    status = base_status(
        run_id=run_id,
        started_at=started_at,
        input_pdf=input_pdf,
        requested_mode=args.mode,
        languages=args.languages,
        deskew=args.deskew,
        jobs=args.jobs,
        timeout_seconds=args.timeout_seconds,
    )
    try:
        status["input"]["sha256"] = sha256_file(input_pdf)
        inspection = inspect_pdf(input_pdf)
        selected_mode, reason = select_mode(inspection.pages, args.mode)
        status["route"].update(
            {
                "selected_mode": selected_mode,
                "reason": reason,
                "inspection": inspection.as_dict(),
            }
        )
        require_ocr = selected_mode in {"skip", "redo"}
        dependencies = locate_dependencies(require_ocr, languages)
        status["dependencies"] = dependencies.as_dict()
        logger.info("Input SHA256=%s", status["input"]["sha256"])
        logger.info("Selected route=%s (%s)", selected_mode, reason)
        run_ocr(
            input_pdf,
            staged["pdf"],
            selected_mode,
            args.languages,
            args.deskew,
            args.jobs,
            args.timeout_seconds,
            dependencies,
            logger,
        )
        text = extract_text(staged["pdf"], staged["txt"], dependencies)
        if require_ocr and not text.strip():
            raise PipelineError(
                "OCR output contains no extractable text",
                EXIT_VALIDATION,
            )
        validation = render_validation(input_pdf, staged["pdf"], temporary_dir, dependencies)
        input_after = sha256_file(input_pdf)
        if input_after != status["input"]["sha256"]:
            raise PipelineError("Input SHA256 changed during processing", EXIT_VALIDATION)
        output_meta = {
            "sha256": sha256_file(staged["pdf"]),
            "bytes": staged["pdf"].stat().st_size,
            "text_sha256": sha256_file(staged["txt"]),
            "text_bytes": staged["txt"].stat().st_size,
            "text_characters": len(text),
            "final_paths": {key: str(path) for key, path in targets.items()},
        }
        status["output"] = output_meta
        status["output"]["finalized"] = True
        status["validation"] = validation
        status["status"] = "success"
        status["exit_code"] = EXIT_OK
        status["finished_at"] = now_utc()
        status["duration_seconds"] = round(time.monotonic() - started_clock, 3)
        json_dump(staged["status"], status)
        logger.info("Validation passed; publishing four artifacts.")
        close_logger(logger)
        finalize(staged, targets, temporary_dir)
        return EXIT_OK, status
    except PipelineError as exc:
        status["status"] = "failed"
        status["exit_code"] = exc.exit_code
        if status.get("output"):
            status["output"]["finalized"] = False
        status["error"] = {
            "message": str(exc),
            "details": exc.details,
        }
        status["finished_at"] = now_utc()
        status["duration_seconds"] = round(time.monotonic() - started_clock, 3)
        logger.error("%s", str(exc))
        close_logger(logger)
        json_dump(staged["status"], status)
        raise PipelineError(
            f"{exc} (failure artifacts kept in {temporary_dir})",
            exc.exit_code,
            details={"status_path": str(staged["status"]), "original": exc.details},
        ) from exc
    except Exception as exc:
        status["status"] = "failed"
        status["exit_code"] = EXIT_ENGINE
        if status.get("output"):
            status["output"]["finalized"] = False
        status["error"] = {"message": str(exc), "details": None}
        status["finished_at"] = now_utc()
        status["duration_seconds"] = round(time.monotonic() - started_clock, 3)
        logger.exception("Unexpected pipeline error")
        close_logger(logger)
        json_dump(staged["status"], status)
        raise PipelineError(
            f"Unexpected pipeline error: {exc} (failure artifacts kept in {temporary_dir})",
            EXIT_ENGINE,
            details={"status_path": str(staged["status"])},
        ) from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Route a PDF through local OCRmyPDF/Tesseract without overwriting input."
    )
    parser.add_argument("--input", required=True, help="Input PDF path")
    parser.add_argument(
        "--languages",
        required=True,
        help="Explicit Tesseract language list, for example chi_sim+eng",
    )
    parser.add_argument(
        "--mode",
        choices=("auto", "none", "skip", "redo"),
        default="auto",
        help="OCR route; auto inspects page content",
    )
    parser.add_argument("--output-directory", help="Directory for published artifacts")
    parser.add_argument("--deskew", action="store_true", help="Enable OCRmyPDF deskew")
    parser.add_argument("--jobs", type=int, default=1)
    parser.add_argument("--timeout-seconds", type=int, default=1800)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.jobs < 1 or args.jobs > 64:
        parser.error("--jobs must be between 1 and 64")
    if args.timeout_seconds < 30 or args.timeout_seconds > 86400:
        parser.error("--timeout-seconds must be between 30 and 86400")
    try:
        exit_code, status = process(args)
    except PipelineError as exc:
        payload = {
            "status": "failed",
            "exit_code": exc.exit_code,
            "error": str(exc),
            "details": exc.details,
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2), file=sys.stderr)
        return exc.exit_code
    print(json.dumps(status, ensure_ascii=False, indent=2))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
