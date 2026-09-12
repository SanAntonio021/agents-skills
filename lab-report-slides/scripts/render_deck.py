#!/usr/bin/env python3
"""Create editable lab-report PPTX slides and render that PPTX for inspection."""

from __future__ import annotations

import argparse
import base64
import copy
import hashlib
import html
import io
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
import uuid
from pathlib import Path
from typing import Any
from contextlib import contextmanager
from contextvars import ContextVar

from runtime_config import load_config, emit_json, atomic_write_json

from PIL import Image
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, MSO_AUTO_SIZE, PP_ALIGN
from pptx.oxml.xmlchemy import OxmlElement
from pptx.util import Inches, Pt


SLIDE_WIDTH = 1600
SLIDE_HEIGHT = 900
FONT = "Microsoft YaHei"
INK = "263344"
BLUE = "4472C4"
MUTED = "64748B"
PROFILE_PATH = Path(__file__).resolve().parents[1] / "references/template-profile.json"
FONT_STEPS = (8, 9, 10, 10.5, 11, 12, 14, 16, 18, 20, 22, 24, 26, 28, 32, 36, 40, 44, 48, 54, 60, 66, 72, 80, 88, 96)
WORK_ROOT = ContextVar("lab_report_work_root", default=None)


def topic_font_size(project_size: float) -> float:
    """Two smaller PowerPoint font-size stops, not two points."""
    smaller = [size for size in FONT_STEPS if size < project_size]
    if len(smaller) < 2 or smaller[-2] < 12:
        raise ValueError("Project title needs two smaller readable font-size stops")
    return smaller[-2]


def project_title(content):
    """Keep legacy title-only decks and the final shared next-steps page."""
    if content.get("type") == "next_steps":
        return None
    project = content.get("project")
    if project is None:
        return None
    topic = content.get("title")
    if not isinstance(project, str) or not project.strip() or not isinstance(topic, str) or not topic.strip():
        raise ValueError("Project titles require nonempty project and title strings")
    if any(c in project + topic for c in "\r\n\t\v\f\u2028\u2029"):
        raise ValueError("Project and topic must stay on one title line")
    return project.strip(), topic.strip()


def choose_stem(output_dir: Path, requested: str) -> str:
    if not requested.strip() or requested in {".", ".."} or any(char in requested for char in '<>:"/\\|?*'):
        raise ValueError("base-name must be a file name, without a directory")
    pattern = re.compile(rf"^{re.escape(requested)}(?:_v(\d+))?(?:\.(?:pptx|pdf|html|manifest\.json|reserve)|_\d+\.png)$", re.IGNORECASE)
    existing = []
    for path in output_dir.iterdir() if output_dir.exists() else []:
        match = pattern.match(path.name)
        if match:
            existing.append(int(match.group(1) or 1))
    return requested if not existing else f"{requested}_v{max(existing) + 1}"


@contextmanager
def reserve_stem(output_dir: Path, requested: str):
    while True:
        stem = choose_stem(output_dir, requested)
        reservation = output_dir / f"{stem}.reserve"
        try:
            with reservation.open("x", encoding="utf-8"):
                pass
            break
        except FileExistsError:
            continue
    try:
        yield stem
    finally:
        reservation.unlink(missing_ok=True)


def text_rows(block: dict[str, Any]) -> list[tuple[str, bool]]:
    rows = []
    heading = block.get("heading") or block.get("title")
    if heading:
        rows.append((str(heading), True))
    if block.get("type", block.get("kind")) == "metric":
        rows.append((f"{block.get('value', '')}  {block.get('label', '')}".strip(), True))
    else:
        for line in str(block.get("text") or block.get("body") or "").splitlines():
            line = line.strip()
            if line:
                rows.append((line[2:] if line.startswith(("- ", "* ")) else line, False))
    return rows


def text_size(rows: list[tuple[str, bool]], width: float, height: float, maximum: int) -> int:
    if maximum <= 0:
        raise ValueError("Font size must be positive")
    candidates = sorted({maximum, *(size for size in (40, 36, 32, 28, 24, 22, 20, 18) if size <= maximum)}, reverse=True)
    for size in candidates:
        capacity = max(1, width * 72 / size * 1.65)
        lines = sum(max(1, math.ceil(sum(2 if unicodedata.east_asian_width(c) in {"W", "F"} else 1
                                       for c in text) / capacity)) for text, _ in rows)
        if (lines * size * 1.3 + max(0, len(rows) - 1) * 8) / 72 <= height:
            return size
    raise ValueError("Slide text does not fit at a readable size; shorten it or split the slide")


def add_text(slide, rows, x, y, width, height, size=20, color=INK, *, fit=False,
             font=FONT, centered=False):
    if not rows:
        return
    if fit:
        size = text_size(rows, width, height, size)
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(width), Inches(height))
    frame = box.text_frame
    frame.word_wrap = True
    frame.margin_left = frame.margin_right = frame.margin_top = frame.margin_bottom = 0
    frame.vertical_anchor = MSO_ANCHOR.MIDDLE if centered else MSO_ANCHOR.TOP
    for index, (text, bold) in enumerate(rows):
        paragraph = frame.paragraphs[0] if index == 0 else frame.add_paragraph()
        paragraph.space_before = Pt(0)
        paragraph.space_after = Pt(8 if index < len(rows) - 1 else 0)
        paragraph.line_spacing = 1.15
        if centered:
            paragraph.alignment = PP_ALIGN.CENTER
        run = paragraph.add_run()
        run.text = re.sub(r"(?<=\d) (?=(?:GHz|MHz|kHz|Hz|dBm|dB|km|mm|ms|ns|Gbit/s|Gbps)\b)", "\u00a0", text)
        run.font.name = font
        run.font.size = Pt(size)
        run.font.bold = bold
        run.font.color.rgb = RGBColor.from_string(color)
        east_asian = OxmlElement("a:ea")
        east_asian.set("typeface", font)
        run._r.get_or_add_rPr().append(east_asian)
    return box


def add_project_title(slide, project, topic, spec, size, font):
    box = add_text(slide, [(project, True)], *spec["box"], size, spec["color"], font=font)
    box.text_frame.word_wrap = False
    box.text_frame.auto_size = MSO_AUTO_SIZE.NONE
    run = box.text_frame.paragraphs[0].add_run()
    run.text = "   " + topic
    run.font.name = font
    run.font.size = Pt(topic_font_size(size))
    run.font.bold = False
    run.font.color.rgb = RGBColor.from_string(spec["color"])
    east_asian = OxmlElement("a:ea")
    east_asian.set("typeface", font)
    run._r.get_or_add_rPr().append(east_asian)
    return box


def raster_bytes(path: Path) -> bytes:
    if path.suffix.lower() == ".svg":
        node = shutil.which("node")
        bundled = Path.home() / ".cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/sharp"
        sharp = os.environ.get("SHARP_MODULE") or (str(bundled) if bundled.is_dir() else "sharp")
        if not node:
            raise ValueError("SVG input requires the existing Node.js/sharp runtime or a PNG export")
        with tempfile.TemporaryDirectory(prefix="lab-svg-", dir=WORK_ROOT.get()) as temporary:
            output = Path(temporary) / "image.png"
            completed = subprocess.run(
                [node, "-e", "require(process.argv[1])(process.argv[2],{density:180}).png().toFile(process.argv[3]).catch(e=>{console.error(e.message);process.exit(1)})",
                 sharp, str(path), str(output)], capture_output=True, text=True, encoding="utf-8", timeout=45,
            )
            if completed.returncode or not output.is_file():
                raise ValueError(f"Cannot render SVG image: {path.name}")
            return output.read_bytes()
    with Image.open(path) as image:
        image.seek(0)
        image.thumbnail((3200, 3200), Image.Resampling.LANCZOS)
        buffer = io.BytesIO()
        image.convert("RGBA" if "A" in image.getbands() else "RGB").save(buffer, format="PNG")
        return buffer.getvalue()


def add_image(slide, block, data, x, y, width, height, caption_size=18, caption_space=0.4, font=FONT):
    caption = str(block.get("caption") or "")
    caption_height = caption_space if caption else 0
    image_height = height - caption_height
    with Image.open(io.BytesIO(data)) as image:
        scale = min(width / image.width, image_height / image.height)
        actual_width, actual_height = image.width * scale, image.height * scale
    picture = slide.shapes.add_picture(io.BytesIO(data), Inches(x + (width - actual_width) / 2),
                                       Inches(y + (image_height - actual_height) / 2),
                                       width=Inches(actual_width), height=Inches(actual_height))
    picture.name = f"Research image: {Path(block['path']).name}"
    if caption:
        add_text(slide, [(caption, False)], x, y + image_height + 0.04, width, caption_height - 0.04,
                 caption_size, INK, font=font, centered=True)


def validate_deck(deck: dict[str, Any], source_dir: Path) -> list[dict[str, Any]]:
    if not isinstance(deck.get("slides"), list) or not deck["slides"]:
        raise ValueError("No report material; provide actual findings and visual assets before rendering")
    slides = []
    total_images = 0
    for index, raw in enumerate(deck["slides"]):
        slide = dict(raw)
        project_title(slide)
        if slide.get("type") == "next_steps":
            if index != len(deck["slides"]) - 1:
                raise ValueError("Next steps must be on the final slide")
            steps = slide.get("next_steps")
            if not isinstance(steps, list) or not steps or any(not isinstance(step, str) or not step.strip() for step in steps):
                raise ValueError("Next steps require a nonempty list of confirmed actions")
            if slide.get("blocks") or slide.get("body"):
                raise ValueError("Use next_steps only for the final numbered textbox")
            slide["blocks"] = [{"type": "text", "text": "\n".join(f"{i}. {step}" for i, step in enumerate(steps, 1))}]
        blocks = [dict(block) for block in slide.get("blocks", [])]
        if not blocks and slide.get("body"):
            blocks = [{"type": "text", "text": slide["body"]}]
        pictures = 0
        for block in blocks:
            kind = block.get("type") or block.get("kind") or "text"
            if kind not in {"image", "text", "metric", "callout"}:
                raise ValueError(f"Unsupported slide block: {kind}")
            block["type"] = kind
            if kind == "image":
                if not block.get("path"):
                    raise ValueError("An image block is missing its source path")
                path = Path(block["path"]).expanduser()
                path = (source_dir / path).resolve() if not path.is_absolute() else path.resolve()
                if not path.is_file():
                    raise ValueError(f"Missing research image: {path}")
                block["path"] = str(path)
                pictures += 1
        if pictures > 6:
            raise ValueError("Use at most six images in a template layout; place additional figures on another slide")
        if slide.get("type") in {"result", "setup", "comparison"} and not pictures:
            raise ValueError(f"This experimental slide needs its actual image: {slide.get('title', '')}")
        slide["blocks"] = blocks
        slides.append(slide)
        total_images += pictures
    if total_images == 0 and deck.get("allow_text_only") is not True:
        raise ValueError("No experimental plots or photos selected; locate assets before making a text-only deck")
    return slides


def image_boxes(count, area, layout):
    if count <= 0:
        return []
    x, y, width, height = area
    gap = 0.15
    if count == 1:
        return [tuple(area)]
    if layout == "wide-strip" and count >= 3:
        top_height = height * 0.62
        bottom_height = height - top_height - gap
        item_width = (width - gap * (count - 2)) / (count - 1)
        return [(x, y, width, top_height)] + [
            (x + index * (item_width + gap), y + top_height + gap, item_width, bottom_height)
            for index in range(count - 1)]
    if layout == "stacked-left" and count == 3:
        half_width = (width - gap) / 2
        half_height = (height - gap) / 2
        return [(x, y, half_width, half_height), (x, y + half_height + gap, half_width, half_height),
                (x + half_width + gap, y, half_width, height)]
    columns = 2 if count <= 4 else 3
    rows = math.ceil(count / columns)
    item_width = (width - gap * (columns - 1)) / columns
    item_height = (height - gap * (rows - 1)) / rows
    return [(x + (index % columns) * (item_width + gap), y + (index // columns) * (item_height + gap),
             item_width, item_height) for index in range(count)]


def make_pptx(deck, slides, output_path, *, template_test=False):
    if output_path.exists():
        raise FileExistsError(output_path)
    if deck.get("template_spec"):
        if deck.get("profile_path"):
            raise ValueError("Choose template_spec or profile_path, not both")
        from template_deck import make_template_pptx
        return make_template_pptx(deck, slides, output_path, Path(deck["template_spec"]), template_test=template_test)
    if template_test:
        raise ValueError("--template-test requires template_spec")
    profile_path = Path(deck.get("profile_path") or PROFILE_PATH).resolve()
    profile = json.loads(profile_path.read_text(encoding="utf-8-sig"))
    base_layout = profile["layout"]
    font = profile["font_family"][0]
    presentation = Presentation()
    presentation.slide_width, presentation.slide_height = base_layout["slide_size_emu"]
    assets = []
    for index, content in enumerate(slides, 1):
        layout = copy.deepcopy(base_layout)
        for key, override in content.get("layout_overrides", {}).items():
            if key not in layout or not isinstance(layout[key], dict) or not isinstance(override, dict):
                raise ValueError(f"Invalid layout override: {key}")
            layout[key].update(override)
        fonts = content.get("font_sizes", {})
        slide = presentation.slides.add_slide(presentation.slide_layouts[6])
        slide.background.fill.solid()
        slide.background.fill.fore_color.rgb = RGBColor(255, 255, 255)
        line = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, *[Inches(v) for v in layout["divider"]["box"]])
        line.fill.solid()
        line.fill.fore_color.rgb = RGBColor.from_string(layout["divider"]["color"])
        line.line.fill.background()
        title = str(content.get("title") or f"Slide {index}")
        chapter = str(content.get("section") or content.get("kicker") or title)
        spec = layout["title"]
        title_parts = project_title(content)
        if title_parts:
            add_project_title(slide, *title_parts, spec, fonts.get("title", spec["font_size"]), font)
        else:
            add_text(slide, [(chapter, True)], *spec["box"], fonts.get("title", spec["font_size"]), spec["color"], fit=True, font=font)
        subtitle = str(content.get("summary") or content.get("subtitle") or (title if title != chapter and not title_parts else ""))
        if subtitle:
            spec = layout["subtitle"]
            strip = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, *[Inches(v) for v in spec["box"]])
            strip.fill.solid()
            strip.fill.fore_color.rgb = RGBColor.from_string(spec["fill"])
            strip.line.fill.background()
            add_text(slide, [(subtitle, True)], *spec["box"], fonts.get("summary", spec["font_size"]), spec["color"], fit=True, font=font, centered=True)
        pictures = [block for block in content["blocks"] if block["type"] == "image"]
        rows = []
        for block in content["blocks"]:
            if block["type"] != "image":
                rows.extend(text_rows(block))
        image_area = list(layout["content"]["box"])
        if rows:
            body_area = list(image_area)
            if pictures:
                fraction = float(content.get("body_fraction", 0.27))
                if not 0.1 <= fraction <= 0.6:
                    raise ValueError("body_fraction must be between 0.1 and 0.6")
                body_area[2] = image_area[2] * fraction
                image_area[0] += body_area[2] + 0.2
                image_area[2] -= body_area[2] + 0.2
            add_text(slide, rows, *body_area, fonts.get("body", layout.get("body", {}).get("font_size", 22)), font=font, fit=True)
        boxes = image_boxes(len(pictures), image_area, content.get("layout"))
        slide.notes_slide.notes_text_frame.text = "\n".join(filter(None, [
            str(deck.get("footer") or deck.get("date") or ""), str(content.get("status") or ""),
            str(content.get("source") or ""),
            *[str(block.get("source") or block["path"]) for block in pictures]]))
        for block, box in zip(pictures, boxes):
            path = Path(block["path"])
            source_hash = hashlib.sha256(path.read_bytes()).hexdigest()
            raster = raster_bytes(path)
            if hashlib.sha256(path.read_bytes()).hexdigest() != source_hash:
                raise ValueError(f"Research image changed while rendering: {path}")
            add_image(slide, block, raster, *box, caption_size=fonts.get("caption", layout["caption"]["font_size"]),
                      caption_space=layout["caption"]["height"], font=font)
            assets.append({"slide": index, "path": str(path), "sha256": source_hash,
                           "embedded_sha256": hashlib.sha256(raster).hexdigest(),
                           "caption": block.get("caption", ""), "role": block.get("role", "unverified"),
                           "source": block.get("source", ""), "period": block.get("period", "unknown")})
    presentation.save(output_path)
    return assets


class RenderFailure(RuntimeError):
    def __init__(self, message, manifest):
        super().__init__(message)
        self.manifest = manifest


class ExportFailure(RuntimeError):
    def __init__(self, message, stage, details=None):
        super().__init__(message)
        self.stage = stage
        self.details = details or {}


class ManifestWriteFailure(RuntimeError):
    stage = "manifest"


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def inspect_pptx(path, expected_count=None):
    import zipfile
    with zipfile.ZipFile(path) as archive:
        bad = archive.testzip()
        if bad:
            raise ValueError(f"Corrupt PPTX part: {bad}")
    presentation = Presentation(path)
    count = len(presentation.slides)
    if count < 1 or (expected_count is not None and count != expected_count):
        raise ValueError("PPTX slide count does not match the requested deck")
    return count


def export_pptx(pptx_path, pdf_path, slide_paths, *, config=None, stage_callback=None):
    config = config if config is not None else load_config(discovery_dir=pptx_path.parent)
    values = config["values"]
    default_runner = Path(__file__).resolve().parents[2] / "libreoffice-runner/scripts/libreoffice_run.py"
    runner = Path(values.get("lo_runner") or default_runner).resolve()
    stage = "libreoffice"
    details = {}
    def signal(state):
        if stage_callback:
            stage_callback(stage, state, details)
    try:
        signal("pending")
        if not runner.is_file():
            raise RuntimeError("Install libreoffice-runner alongside lab-report-slides, or set LAB_REPORT_LO_RUNNER")
        work = Path(values["work_root"]) if values.get("work_root") else None
        diagnostics = Path(values.get("diagnostics_root") or pdf_path.parent / "diagnostics")
        if work is not None:
            work.mkdir(parents=True, exist_ok=True)
        command = [sys.executable, "-X", "utf8", str(runner), "pdf", str(pptx_path), str(pdf_path),
                   "--queue-timeout", "60", "--run-timeout", "120",
                   "--diagnostics-root", str(diagnostics)]
        if work is not None:
            command.extend(["--work-root", str(work)])
        if values.get("soffice"):
            command.extend(["--soffice", values["soffice"]])
        result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8")
        details = {"command": command, "returncode": result.returncode,
                   "stdout": result.stdout, "stderr": getattr(result, "stderr", "")}
        try:
            report = json.loads(result.stdout)
            if not isinstance(report, dict):
                raise ValueError("Expected a JSON object")
        except (json.JSONDecodeError, ValueError) as exc:
            raise RuntimeError("LibreOffice runner did not return JSON; run check_dependencies.py with the same Python interpreter") from exc
        details["runner"] = report
        if result.returncode or report.get("ok") is not True:
            raise RuntimeError(f"PPTX rendering failed: {report.get('error')}: {report.get('message')}")
        if not pdf_path.is_file():
            raise RuntimeError("Runner reported success but PDF is missing")
        signal("passed")
        stage, details = "png", {}
        signal("pending")
        presentation = Presentation(pptx_path)
        page_height = round(SLIDE_WIDTH * presentation.slide_height / presentation.slide_width)
        poppler = values.get("pdftoppm") or shutil.which("pdftoppm")
        if not poppler:
            raise RuntimeError("pdftoppm is required for page inspection")
        with tempfile.TemporaryDirectory(prefix="lab-pages-", dir=work) as temporary:
            prefix = Path(temporary) / "page"
            command = [poppler, "-png", "-scale-to-x", str(SLIDE_WIDTH), "-scale-to-y", str(page_height),
                       "-aa", "yes", "-aaVector", "yes", str(pdf_path), str(prefix)]
            result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", timeout=120)
            details = {"command": command, "returncode": result.returncode,
                       "stdout": getattr(result, "stdout", ""), "stderr": getattr(result, "stderr", "")}
            if result.returncode:
                raise RuntimeError(f"PDF page export failed: {details['stderr']}")
            pages = sorted(Path(temporary).glob("page-*.png"), key=lambda p: int(p.stem.rsplit("-", 1)[1]))
            if len(pages) != len(slide_paths):
                raise RuntimeError("PPTX and rendered page counts differ")
            for source, target in zip(pages, slide_paths):
                with Image.open(source) as page:
                    if page.size != (SLIDE_WIDTH, page_height):
                        raise RuntimeError("Unexpected rendered page dimensions")
                with target.open("xb") as destination:
                    destination.write(source.read_bytes())
        signal("passed")
    except Exception as exc:
        if isinstance(exc, (ExportFailure, ManifestWriteFailure)):
            raise
        raise ExportFailure(str(exc), stage, details) from exc


def _template_record(deck):
    if deck.get("template_spec"):
        spec_path = Path(deck["template_spec"])
        spec = json.loads(spec_path.read_text(encoding="utf-8-sig"))
        source = Path(spec["template_path"]).expanduser()
        if not source.is_absolute():
            source = (spec_path.parent / source).resolve()
        return {"mode": "native_template", "spec_path": str(spec_path),
                "spec_sha256": file_hash(spec_path), "source": str(source), "sha256": file_hash(source)}
    profile = Path(deck.get("profile_path") or PROFILE_PATH).resolve()
    return {"mode": "style_profile", "path": str(profile), "sha256": file_hash(profile),
            "source": json.loads(profile.read_text(encoding="utf-8-sig"))["source"]}


def _check_template(record):
    if record["mode"] == "native_template":
        pairs = [(record["spec_path"], record["spec_sha256"]), (record["source"], record["sha256"])]
    else:
        pairs = [(record["path"], record["sha256"])]
    if any(file_hash(path) != expected for path, expected in pairs):
        raise ValueError("Template or template spec changed during report rendering; review the inputs and regenerate")


def _write_manifest(path, manifest, *, primary_error=None):
    try:
        atomic_write_json(path, manifest)
        return True
    except Exception as exc:
        # Never turn an earlier conversion failure into only a diagnostic-write error.
        message = f"Manifest write failed: {exc}. Previous manifest, if any, was not deliberately removed; recovery is not confirmed."
        if primary_error is None:
            raise ManifestWriteFailure(message) from exc
        manifest["manifest_write_error"] = message
        emit_json({"error": str(primary_error), "manifest_write_error": message}, stream=sys.stderr)
        return False


def _save_diagnostic(manifest, name, payload):
    target = Path(manifest["files"]["manifest"]).parent / f"{manifest['stem']}.{name}.json"
    try:
        atomic_write_json(target, payload)
        manifest.setdefault("diagnostics", {})[name] = str(target)
    except Exception as exc:
        manifest.setdefault("diagnostic_write_errors", []).append(str(exc))
        manifest.setdefault("diagnostic_details", {})[name] = payload


def _run_outputs(manifest, config, generate=None, template_check=None, expected_pptx_sha256=None):
    path = Path(manifest["files"]["manifest"])
    pptx = Path(manifest["files"]["pptx"])
    stage = "pptx"
    work = Path(config["values"]["work_root"]) if config["values"].get("work_root") else None
    token = WORK_ROOT.set(work)
    def signal(name, status, details):
        nonlocal stage
        stage = name
        manifest["stages"][name] = status
        if details:
            _save_diagnostic(manifest, name, details)
        if status == "passed":
            paths = [manifest["files"]["pdf"]] if name == "libreoffice" else manifest["files"]["png"]
            for item in paths:
                manifest["file_hashes"][item] = file_hash(item)
        _write_manifest(path, manifest)
    try:
        _write_manifest(path, manifest)
        if work is not None:
            work.mkdir(parents=True, exist_ok=True)
        if generate:
            manifest["assets"] = generate()
        actual_hash = file_hash(pptx)
        if expected_pptx_sha256 is not None and actual_hash != expected_pptx_sha256:
            raise ValueError("PPTX changed after resume validation; regenerate before rendering")
        manifest["pptx_sha256"] = actual_hash
        manifest["file_hashes"][str(pptx)] = manifest["pptx_sha256"]
        manifest["stages"]["pptx"] = "passed"
        _write_manifest(path, manifest)
        stage = "structure"
        inspect_pptx(pptx, manifest["slide_count"])
        manifest["stages"]["structure"] = "passed"
        _write_manifest(path, manifest)
        export_pptx(pptx, Path(manifest["files"]["pdf"]), [Path(p) for p in manifest["files"]["png"]],
                    config=config, stage_callback=signal)
        stage = "html"
        images = "".join(f'<img alt="{html.escape(title, quote=True)}" src="data:image/png;base64,{base64.b64encode(Path(p).read_bytes()).decode()}" />'
                         for title, p in zip(manifest["slide_titles"], manifest["files"]["png"]))
        with Path(manifest["files"]["html"]).open("x", encoding="utf-8") as output:
            output.write('<!doctype html><meta charset="utf-8"><title>Lab report</title><style>body{margin:0;background:#ddd}img{display:block;width:min(100%,1600px);height:auto;margin:0 auto 16px}</style>' + images)
        manifest["file_hashes"][manifest["files"]["html"]] = file_hash(manifest["files"]["html"])
        stage = "structure"
        if file_hash(pptx) != manifest["pptx_sha256"]:
            raise ValueError("PPTX changed during rendering; regenerate and inspect the new file")
        if template_check:
            template_check()
        manifest["ok"] = True
        manifest["status"] = "rendered_visual_pending"
        _write_manifest(path, manifest)
        return manifest
    except Exception as exc:
        stage = getattr(exc, "stage", stage)
        manifest["ok"] = False
        manifest["status"] = "failed"
        manifest["failed_stage"] = stage
        manifest["error"] = str(exc)
        if stage in manifest["stages"]:
            manifest["stages"][stage] = "failed"
        if isinstance(exc, ExportFailure):
            _save_diagnostic(manifest, stage, exc.details)
        _save_diagnostic(manifest, "failure", {"stage": stage, "error": str(exc),
                                             "pptx": str(pptx), "pptx_exists": pptx.is_file()})
        _write_manifest(path, manifest, primary_error=exc)
        raise RenderFailure(str(exc), manifest) from exc
    finally:
        WORK_ROOT.reset(token)


def _new_manifest(output_dir, stem, requested_stem, count, titles, config):
    return {"schema_version": 3, "ok": False, "status": "running", "requested_stem": requested_stem,
            "stem": stem, "slide_count": count, "slide_titles": titles, "render_source": "pptx",
            "editable_text": True, "independent_images": True, "assets": [], "file_hashes": {},
            "config": config, "stages": {name: "not_run" for name in
                       ("pptx", "structure", "libreoffice", "png", "visual", "powerpoint")},
            "files": {"pptx": str(output_dir / f"{stem}.pptx"),
                      "pdf": str(output_dir / f"{stem}.pdf"), "html": str(output_dir / f"{stem}.html"),
                      "manifest": str(output_dir / f"{stem}.manifest.json"),
                      "png": [str(output_dir / f"{stem}_{i:02d}.png") for i in range(1, count + 1)]}}


def render(deck_path, output_dir, requested_stem, *, config_path=None, template_test=False):
    deck_path, output_dir = Path(deck_path).resolve(), Path(output_dir).resolve()
    config = load_config(config_path, discovery_dir=deck_path.parent)
    deck = json.loads(deck_path.read_text(encoding="utf-8-sig"))
    if deck.get("template_spec"):
        spec_path = Path(deck["template_spec"]).expanduser()
        deck["template_spec"] = str((deck_path.parent / spec_path).resolve() if not spec_path.is_absolute() else spec_path.resolve())
    slides = validate_deck(deck, deck_path.parent)
    output_dir.mkdir(parents=True, exist_ok=True)
    with reserve_stem(output_dir, requested_stem) as stem:
        return render_outputs(deck, slides, deck_path, output_dir, requested_stem, stem,
                              config=config, template_test=template_test)


def render_outputs(deck, slides, deck_path, output_dir, requested_stem, stem, *, config=None, template_test=False):
    config = config if config is not None else load_config(discovery_dir=Path(deck_path).parent)
    manifest = _new_manifest(output_dir, stem, requested_stem, len(slides),
                             [str(s.get("title", "")) for s in slides], config)
    manifest.update(source_deck=str(deck_path), template_test=template_test)
    # Read template metadata inside generation so failures still get a stage receipt.
    def generate():
        manifest["template"] = _template_record(deck)
        return make_pptx(deck, slides, Path(manifest["files"]["pptx"]), template_test=template_test)
    return _run_outputs(manifest, config, generate=generate,
                        template_check=lambda: _check_template(manifest["template"]))


def resume_render(manifest_path, output_dir=None, requested_stem=None, *, config_path=None):
    manifest_path = Path(manifest_path).resolve()
    previous = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    if previous.get("schema_version") != 3 or previous.get("failed_stage") not in {"libreoffice", "png", "html"}:
        raise ValueError("--resume-manifest requires a version 3 rendering failure; regenerate or repeat the relevant manual check")
    pptx = Path(previous["files"]["pptx"])
    if previous.get("stages", {}).get("pptx") != "passed" or file_hash(pptx) != previous.get("pptx_sha256"):
        raise ValueError("PPTX hash/state changed; regenerate before rendering")
    count = inspect_pptx(pptx, previous["slide_count"])
    explicit = config_path or previous.get("config", {}).get("path")
    discovery = Path(previous.get("source_deck") or manifest_path).parent
    config = load_config(explicit, discovery_dir=discovery)
    root = Path(output_dir).resolve() if output_dir else manifest_path.parent
    root.mkdir(parents=True, exist_ok=True)
    # This is a durable project output, not a private OS temporary directory.
    # Path.mkdir inherits project access on Windows; mkdtemp applies a private ACL.
    for _ in range(20):
        attempt = root / f"lab-render-{uuid.uuid4().hex}"
        try:
            attempt.mkdir()
            break
        except FileExistsError:
            continue
    else:
        raise FileExistsError("Cannot reserve a unique rendering attempt directory")
    stem = requested_stem or previous["requested_stem"]
    stem = choose_stem(attempt, stem)
    manifest = _new_manifest(attempt, stem, stem, count, previous["slide_titles"], config)
    manifest["files"]["pptx"] = str(pptx)
    for key in ("source_deck", "template", "template_test", "assets"):
        if key in previous:
            manifest[key] = previous[key]
    manifest["resumed_from"] = str(manifest_path)
    return _run_outputs(manifest, config, expected_pptx_sha256=previous["pptx_sha256"])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--deck")
    inputs.add_argument("--resume-manifest")
    parser.add_argument("--output-dir")
    parser.add_argument("--base-name")
    parser.add_argument("--config")
    parser.add_argument("--template-test", action="store_true")
    args = parser.parse_args(argv)
    if args.deck and (not args.output_dir or not args.base_name):
        parser.error("--deck requires --output-dir and --base-name")
    if args.resume_manifest and args.template_test:
        parser.error("--template-test is only valid with --deck")
    try:
        if args.resume_manifest:
            result = resume_render(args.resume_manifest, args.output_dir, args.base_name, config_path=args.config)
        else:
            result = render(args.deck, args.output_dir, args.base_name,
                            config_path=args.config, template_test=args.template_test)
        emit_json(result)
        return 0
    except RenderFailure as exc:
        emit_json(exc.manifest)
        return 1
    except Exception as exc:
        emit_json({"ok": False, "error": str(exc), "failed_stage": "input"})
        return 1


if __name__ == "__main__":
    sys.exit(main())
