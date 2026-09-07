#!/usr/bin/env python3
"""Create editable lab-report PPTX slides and render that PPTX for inspection."""

from __future__ import annotations

import argparse
import base64
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
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.xmlchemy import OxmlElement
from pptx.util import Inches, Pt


SLIDE_WIDTH = 1600
SLIDE_HEIGHT = 900
FONT = "Microsoft YaHei"
INK = "263344"
BLUE = "4472C4"
MUTED = "64748B"
PROFILE_PATH = Path(__file__).resolve().parents[1] / "references/template-profile.json"


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
    for size in (value for value in (40, 36, 32, 28, 24, 20, 18) if value <= maximum):
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
    for raw in deck["slides"]:
        slide = dict(raw)
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
    profile_path = Path(deck.get("profile_path") or PROFILE_PATH).resolve()
    profile = json.loads(profile_path.read_text(encoding="utf-8-sig"))
    layout = profile["layout"]
    font = profile["font_family"][0]
    presentation = Presentation()
    presentation.slide_width, presentation.slide_height = layout["slide_size_emu"]
    assets = []
    for index, content in enumerate(slides, 1):
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
        add_text(slide, [(chapter, True)], *spec["box"], spec["font_size"], spec["color"], fit=True, font=font)
        subtitle = str(content.get("subtitle") or (title if title != chapter else ""))
        if subtitle:
            spec = layout["subtitle"]
            strip = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, *[Inches(v) for v in spec["box"]])
            strip.fill.solid()
            strip.fill.fore_color.rgb = RGBColor.from_string(spec["fill"])
            strip.line.fill.background()
            add_text(slide, [(subtitle, True)], *spec["box"], spec["font_size"], spec["color"], fit=True, font=font, centered=True)
        pictures = [block for block in content["blocks"] if block["type"] == "image"]
        rows = []
        for block in content["blocks"]:
            if block["type"] != "image":
                rows.extend(text_rows(block))
        summary_rows = [(str(content["summary"]), True)] if content.get("summary") else []
        if pictures:
            summary_rows.extend(rows)
        else:
            add_text(slide, rows, *layout["content"]["box"], 24, font=font, fit=True)
        spec = layout["conclusion"]
        add_text(slide, summary_rows, *spec["box"], spec["font_size"], spec["color"], fit=True, font=font, centered=True)
        boxes = image_boxes(len(pictures), layout["content"]["box"], content.get("layout"))
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
            add_image(slide, block, raster, *box, caption_size=layout["caption"]["font_size"],
                      caption_space=layout["caption"]["height"], font=font)
            assets.append({"slide": index, "path": str(path), "sha256": source_hash,
                           "embedded_sha256": hashlib.sha256(raster).hexdigest(),
                           "caption": block.get("caption", ""), "role": block.get("role", "unverified"),
                           "source": block.get("source", ""), "period": block.get("period", "unknown")})
    presentation.save(output_path)
    return assets


def export_pptx(pptx_path: Path, pdf_path: Path, slide_paths: list[Path]) -> None:
    runner = Path(__file__).resolve().parents[2] / "libreoffice-runner/scripts/libreoffice_run.py"
    if not runner.is_file():
        raise RuntimeError("The existing libreoffice-runner is required to render the actual PPTX")
    result = subprocess.run([sys.executable, "-X", "utf8", str(runner), "pdf", str(pptx_path), str(pdf_path),
                             "--queue-timeout", "60", "--run-timeout", "120"],
                            capture_output=True, text=True, encoding="utf-8")
    report = json.loads(result.stdout)
    if result.returncode or report.get("ok") is not True:
        raise RuntimeError(f"PPTX rendering failed: {report.get('error')}: {report.get('message')}")
    poppler = shutil.which("pdftoppm")
    if not poppler:
        raise RuntimeError("pdftoppm is required for page inspection")
    with tempfile.TemporaryDirectory(prefix="lab-pages-") as temporary:
        prefix = Path(temporary) / "page"
        subprocess.run([poppler, "-png", "-scale-to-x", str(SLIDE_WIDTH), "-scale-to-y", str(SLIDE_HEIGHT),
                        "-aa", "yes", "-aaVector", "yes", str(pdf_path), str(prefix)],
                       check=True, capture_output=True, timeout=120)
        pages = sorted(Path(temporary).glob("page-*.png"), key=lambda path: int(path.stem.rsplit("-", 1)[1]))
        if len(pages) != len(slide_paths):
            raise RuntimeError("PPTX and rendered page counts differ")
        for source, target in zip(pages, slide_paths):
            with Image.open(source) as page:
                if page.size != (SLIDE_WIDTH, SLIDE_HEIGHT):
                    raise RuntimeError("Unexpected rendered page dimensions")
            if target.exists():
                raise FileExistsError(target)
            shutil.copyfile(source, target)


def render(deck_path: Path, output_dir: Path, requested_stem: str) -> dict[str, Any]:
    deck_path, output_dir = deck_path.resolve(), output_dir.resolve()
    deck = json.loads(deck_path.read_text(encoding="utf-8-sig"))
    slides = validate_deck(deck, deck_path.parent)
    output_dir.mkdir(parents=True, exist_ok=True)
    with reserve_stem(output_dir, requested_stem) as stem:
        return render_outputs(deck, slides, deck_path, output_dir, requested_stem, stem)


def render_outputs(deck, slides, deck_path, output_dir, requested_stem, stem):
    pptx_path, pdf_path = output_dir / f"{stem}.pptx", output_dir / f"{stem}.pdf"
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
