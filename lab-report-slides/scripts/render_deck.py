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
from pathlib import Path
from typing import Any
from contextlib import contextmanager

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
        with tempfile.TemporaryDirectory(prefix="lab-svg-") as temporary:
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


def make_pptx(deck, slides, output_path):
    if output_path.exists():
        raise FileExistsError(output_path)
    if deck.get("template_spec"):
        if deck.get("profile_path"):
            raise ValueError("Choose template_spec or profile_path, not both")
        from template_deck import make_template_pptx
        return make_template_pptx(deck, slides, output_path, Path(deck["template_spec"]))
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


def export_pptx(pptx_path: Path, pdf_path: Path, slide_paths: list[Path]) -> None:
    default_runner = Path(__file__).resolve().parents[2] / "libreoffice-runner/scripts/libreoffice_run.py"
    runner = Path(os.environ.get("LAB_REPORT_LO_RUNNER") or default_runner).expanduser().resolve()
    if not runner.is_file():
        raise RuntimeError("Install libreoffice-runner alongside lab-report-slides, or set LAB_REPORT_LO_RUNNER to its scripts/libreoffice_run.py")
    command = [sys.executable, "-X", "utf8", str(runner), "pdf", str(pptx_path), str(pdf_path),
               "--queue-timeout", "60", "--run-timeout", "120"]
    if os.environ.get("LAB_REPORT_SOFFICE"):
        command.extend(["--soffice", os.environ["LAB_REPORT_SOFFICE"]])
    result = subprocess.run(command,
                            capture_output=True, text=True, encoding="utf-8")
    try:
        report = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("LibreOffice runner did not return JSON; run check_dependencies.py with the same Python interpreter") from exc
    if result.returncode or report.get("ok") is not True:
        raise RuntimeError(f"PPTX rendering failed: {report.get('error')}: {report.get('message')}")
    presentation = Presentation(pptx_path)
    page_width = SLIDE_WIDTH
    page_height = round(page_width * presentation.slide_height / presentation.slide_width)
    poppler = os.environ.get("LAB_REPORT_PDFTOPPM") or shutil.which("pdftoppm")
    if not poppler:
        raise RuntimeError("pdftoppm is required for page inspection")
    with tempfile.TemporaryDirectory(prefix="lab-pages-") as temporary:
        prefix = Path(temporary) / "page"
        subprocess.run([poppler, "-png", "-scale-to-x", str(page_width), "-scale-to-y", str(page_height),
                        "-aa", "yes", "-aaVector", "yes", str(pdf_path), str(prefix)],
                       check=True, capture_output=True, timeout=120)
        pages = sorted(Path(temporary).glob("page-*.png"), key=lambda path: int(path.stem.rsplit("-", 1)[1]))
        if len(pages) != len(slide_paths):
            raise RuntimeError("PPTX and rendered page counts differ")
        for source, target in zip(pages, slide_paths):
            with Image.open(source) as page:
                if page.size != (page_width, page_height):
                    raise RuntimeError("Unexpected rendered page dimensions")
            if target.exists():
                raise FileExistsError(target)
            shutil.copyfile(source, target)


def render(deck_path: Path, output_dir: Path, requested_stem: str) -> dict[str, Any]:
    deck_path, output_dir = deck_path.resolve(), output_dir.resolve()
    deck = json.loads(deck_path.read_text(encoding="utf-8-sig"))
    if deck.get("template_spec"):
        spec_path = Path(deck["template_spec"]).expanduser()
        deck["template_spec"] = str((deck_path.parent / spec_path).resolve() if not spec_path.is_absolute() else spec_path.resolve())
    slides = validate_deck(deck, deck_path.parent)
    output_dir.mkdir(parents=True, exist_ok=True)
    with reserve_stem(output_dir, requested_stem) as stem:
        return render_outputs(deck, slides, deck_path, output_dir, requested_stem, stem)


def render_outputs(deck, slides, deck_path, output_dir, requested_stem, stem):
    pptx_path, pdf_path = output_dir / f"{stem}.pptx", output_dir / f"{stem}.pdf"
    template_record = None
    if deck.get("template_spec"):
        spec_path = Path(deck["template_spec"])
        spec_bytes = spec_path.read_bytes()
        spec = json.loads(spec_bytes.decode("utf-8-sig"))
        template_path = Path(spec["template_path"]).expanduser()
        if not template_path.is_absolute():
            template_path = (spec_path.parent / template_path).resolve()
        template_record = {"mode": "native_template", "spec_path": str(spec_path),
                           "spec_sha256": hashlib.sha256(spec_bytes).hexdigest(),
                           "source": str(template_path), "sha256": hashlib.sha256(template_path.read_bytes()).hexdigest()}
    assets = make_pptx(deck, slides, pptx_path)
    slide_paths = [output_dir / f"{stem}_{index:02d}.png" for index in range(1, len(slides)+1)]
    export_pptx(pptx_path, pdf_path, slide_paths)
    html_path = output_dir / f"{stem}.html"
    images = "".join(f'<img alt="{html.escape(str(slide.get("title", "")), quote=True)}" src="data:image/png;base64,{base64.b64encode(path.read_bytes()).decode()}" />'
                     for slide, path in zip(slides, slide_paths))
    html_path.write_text('<!doctype html><meta charset="utf-8"><title>Lab report</title><style>body{margin:0;background:#ddd}img{display:block;width:min(100%,1600px);height:auto;margin:0 auto 16px}</style>' + images, encoding="utf-8")
    manifest = {"schema_version": 2, "requested_stem": requested_stem, "stem": stem, "slide_count": len(slides),
                "render_source": "pptx", "editable_text": True, "independent_images": True,
                "assets": assets, "source_deck": str(deck_path),
                "files": {"html": str(html_path), "pdf": str(pdf_path), "pptx": str(pptx_path), "png": [str(path) for path in slide_paths]}}
    if template_record:
        if (hashlib.sha256(spec_path.read_bytes()).hexdigest() != template_record["spec_sha256"]
                or hashlib.sha256(template_path.read_bytes()).hexdigest() != template_record["sha256"]):
            raise ValueError("Template or template spec changed during report rendering; review the inputs and regenerate")
        manifest["template"] = template_record
    else:
        profile_path = Path(deck.get("profile_path") or PROFILE_PATH).resolve()
        manifest["template"] = {"mode": "style_profile", "path": str(profile_path),
                                "sha256": hashlib.sha256(profile_path.read_bytes()).hexdigest(),
                                "source": json.loads(profile_path.read_text(encoding="utf-8-sig"))["source"]}
    (output_dir / f"{stem}.manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--deck", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--base-name", required=True)
    args = parser.parse_args()
    print(json.dumps(render(Path(args.deck), Path(args.output_dir), args.base_name), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
