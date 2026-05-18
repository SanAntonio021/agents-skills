#!/usr/bin/env python3
"""Extract paper figures for paper-summary outputs.

The default path is now caption-driven:

1. Find figure/table captions in PDF text.
2. Infer a local bounding box around the caption and nearby graphic objects.
3. Render only that figure region into ``figures/``.
4. Save whole-page renders only into ``debug_pages/`` for inspection.

This avoids silently putting full-page screenshots into Markdown summaries.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urljoin, urlparse

try:
    import fitz  # PyMuPDF
except ImportError as exc:  # pragma: no cover - exercised by CLI environment
    raise SystemExit(
        "PyMuPDF is required. Install it with: python -m pip install pymupdf"
    ) from exc


CAPTION_RE = re.compile(
    r"^\s*(?:\([a-z]\)\s*){0,8}(?P<label>"
    r"(?:Supplementary\s+Fig(?:ure)?\.?\s*(?:S?\d+[A-Za-z]?|[IVXLCDM]+)(?:\([a-z]\))?)"
    r"|(?:Supplementary\s+(?:Table|Tab)\.?\s*(?:S?\d+[A-Za-z]?|[IVXLCDM]+))"
    r"|(?:Extended\s+Data\s+Fig(?:ure)?\.?\s*(?:\d+[A-Za-z]?|[IVXLCDM]+)(?:\([a-z]\))?)"
    r"|(?:Extended\s+Data\s+Table\s*(?:\d+[A-Za-z]?|[IVXLCDM]+))"
    r"|(?:Source\s+Data\s+Fig(?:ure)?\.?\s*(?:\d+[A-Za-z]?|[IVXLCDM]+)(?:\([a-z]\))?)"
    r"|(?:Fig(?:ure)?\.?\s*(?:\d+[A-Za-z]?|[IVXLCDM]+)(?:\([a-z]\))?)"
    r"|(?:Table\s+(?:S?\d+[A-Za-z]?|[IVXLCDM]+))"
    r")\s*[:.\-|]?\s*(?P<caption>.*)",
    re.IGNORECASE,
)

HTML_FIGURE_RE = re.compile(r"<figure\b[^>]*>(?P<body>.*?)</figure>", re.I | re.S)
HTML_IMG_RE = re.compile(r"<img\b[^>]*\bsrc=[\"'](?P<src>[^\"']+)[\"'][^>]*>", re.I | re.S)
HTML_CAPTION_RE = re.compile(
    r"<figcaption\b[^>]*>(?P<caption>.*?)</figcaption>", re.I | re.S
)

CROP_MARGIN_PT = 10.0
FIGURE_EXTRA_LEFT_PT = 18.0
FIGURE_EXTRA_TOP_PT = 8.0
FIGURE_EXTRA_BOTTOM_PT = 14.0
TABLE_EXTRA_BOTTOM_PT = 32.0
MAX_CAPTION_CHARS = 1200
MAX_DENSE_CAPTION_HEIGHT_PT = 120.0
ROMAN_VALUES = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}


def confidence_label(score: float) -> str:
    if score >= 0.75:
        return "high"
    if score >= 0.50:
        return "medium"
    return "low"


@dataclass
class Caption:
    figure_id: str
    caption: str
    page_index: int
    bbox: fitz.Rect
    text: str


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def clean_html_text(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value)
    return normalize_space(html.unescape(value))


def roman_to_int(value: str) -> int | None:
    value = value.upper()
    if not value or any(char not in ROMAN_VALUES for char in value):
        return None
    total = 0
    previous = 0
    for char in reversed(value):
        current = ROMAN_VALUES[char]
        if current < previous:
            total -= current
        else:
            total += current
            previous = current
    return total if total > 0 else None


def normalize_figure_id(label: str) -> str:
    label = normalize_space(label)
    replacements = [
        (r"(?i)^supplementary\s+fig(?:ure)?\.?\s*", "Supplementary Fig. "),
        (r"(?i)^supplementary\s+tab(?:le)?\.?\s*", "Supplementary Table "),
        (r"(?i)^extended\s+data\s+fig(?:ure)?\.?\s*", "Extended Data Fig. "),
        (r"(?i)^extended\s+data\s+table\s*", "Extended Data Table "),
        (r"(?i)^source\s+data\s+fig(?:ure)?\.?\s*", "Source Data Fig. "),
        (r"(?i)^fig(?:ure)?\.?\s*", "Fig. "),
        (r"(?i)^table\s*", "Table "),
    ]
    for pattern, replacement in replacements:
        label = re.sub(pattern, replacement, label)
    return normalize_space(label)


def is_table_label(figure_id: str) -> bool:
    lowered = figure_id.lower()
    return (
        lowered.startswith("table")
        or lowered.startswith("supplementary table")
        or lowered.startswith("supplementary tab")
        or lowered.startswith("extended data table")
    )


def label_group(figure_id: str) -> str:
    lowered = figure_id.lower()
    if lowered.startswith("supplementary table") or lowered.startswith("supplementary tab"):
        return "Supplementary Table"
    if lowered.startswith("extended data table"):
        return "Extended Data Table"
    if lowered.startswith("table"):
        return "Table"
    if lowered.startswith("supplementary fig"):
        return "Supplementary Fig."
    if lowered.startswith("extended data fig"):
        return "Extended Data Fig."
    if lowered.startswith("source data fig"):
        return "Source Data Fig."
    return "Fig."


def label_number_token(figure_id: str) -> str | None:
    match = re.search(r"\b(S?\d+[A-Za-z]?|[IVXLCDM]+)\b", figure_id, re.I)
    return match.group(1) if match else None


def label_number_value(figure_id: str) -> int | None:
    token = label_number_token(figure_id)
    if not token:
        return None
    digit_match = re.search(r"\d+", token)
    if digit_match:
        return int(digit_match.group(0))
    return roman_to_int(token)


def safe_rect(rect: fitz.Rect, page_rect: fitz.Rect) -> fitz.Rect:
    clipped = fitz.Rect(rect)
    clipped.x0 = max(page_rect.x0, clipped.x0)
    clipped.y0 = max(page_rect.y0, clipped.y0)
    clipped.x1 = min(page_rect.x1, clipped.x1)
    clipped.y1 = min(page_rect.y1, clipped.y1)
    return clipped


def rect_to_list(rect: fitz.Rect) -> list[float]:
    return [round(float(rect.x0), 2), round(float(rect.y0), 2), round(float(rect.x1), 2), round(float(rect.y1), 2)]


def rect_area(rect: fitz.Rect) -> float:
    if rect.is_empty or rect.is_infinite:
        return 0.0
    return max(0.0, float(rect.width)) * max(0.0, float(rect.height))


def intersects_x(a: fitz.Rect, b: fitz.Rect, min_overlap: float = 0.15) -> bool:
    overlap = max(0.0, min(a.x1, b.x1) - max(a.x0, b.x0))
    width = max(1.0, min(float(a.width), float(b.width)))
    return overlap / width >= min_overlap


def union_rects(rects: Iterable[fitz.Rect]) -> fitz.Rect | None:
    result: fitz.Rect | None = None
    for rect in rects:
        if rect.is_empty or rect.is_infinite or rect_area(rect) <= 0:
            continue
        result = fitz.Rect(rect) if result is None else result | rect
    return result


def figure_filename(figure_id: str, index: int) -> str:
    token = label_number_token(figure_id) or str(index)
    digit_match = re.search(r"(S?)(\d+)([A-Za-z]?)", token, re.I)
    if digit_match:
        supplement_prefix = "s" if digit_match.group(1) else ""
        number_part = str(int(digit_match.group(2)))
        suffix = digit_match.group(3).lower()
        number = f"{supplement_prefix}{number_part}{suffix}"
    else:
        roman_number = roman_to_int(token) or index
        number = str(roman_number)

    group = label_group(figure_id)
    prefix = {
        "Table": "table",
        "Supplementary Table": "supp_table",
        "Extended Data Table": "extended_data_table",
        "Supplementary Fig.": "supp_fig",
        "Extended Data Fig.": "extended_data_fig",
        "Source Data Fig.": "source_data_fig",
    }.get(group, "fig")
    return f"{prefix}_{number}.png"


def page_debug_filename(page_number: int) -> str:
    return f"page_{page_number:03d}.png"


def extract_text_blocks(page: fitz.Page) -> list[dict[str, Any]]:
    data = page.get_text("dict")
    blocks: list[dict[str, Any]] = []
    for block in data.get("blocks", []):
        if block.get("type") != 0:
            continue
        lines: list[str] = []
        for line in block.get("lines", []):
            spans = line.get("spans", [])
            text = "".join(span.get("text", "") for span in spans)
            if text.strip():
                lines.append(text.strip())
        text = normalize_space(" ".join(lines))
        if not text:
            continue
        blocks.append({"bbox": fitz.Rect(block["bbox"]), "text": text})
    return blocks


def find_captions(doc: fitz.Document) -> list[Caption]:
    captions: list[Caption] = []
    seen: set[tuple[int, str, tuple[int, int, int, int]]] = set()
    for page_index in range(doc.page_count):
        page = doc.load_page(page_index)
        for block in extract_text_blocks(page):
            text = block["text"]
            if len(text) > MAX_CAPTION_CHARS:
                continue
            if len(text) > 200 and block["bbox"].height > MAX_DENSE_CAPTION_HEIGHT_PT:
                continue
            match = CAPTION_RE.match(text)
            if not match:
                continue
            figure_id = normalize_figure_id(match.group("label"))
            caption = normalize_space(match.group("caption"))
            lower_caption = caption.lower()
            if len(caption) > 120 and lower_caption.startswith(
                (
                    "shows ",
                    "show ",
                    "summarizes ",
                    "illustrates ",
                    "presents ",
                    "depicts ",
                    "gives ",
                    "give ",
                    "plots ",
                    "compares ",
                )
            ):
                continue
            bbox = block["bbox"]
            key = (
                page_index,
                figure_id.lower(),
                (round(bbox.x0), round(bbox.y0), round(bbox.x1), round(bbox.y1)),
            )
            if key in seen:
                continue
            seen.add(key)
            captions.append(
                Caption(
                    figure_id=figure_id,
                    caption=caption,
                    page_index=page_index,
                    bbox=bbox,
                    text=text,
                )
            )
    return captions


def get_image_rects(page: fitz.Page) -> list[dict[str, Any]]:
    rects: list[dict[str, Any]] = []
    for image_order, image_info in enumerate(page.get_images(full=True), start=1):
        xref = image_info[0]
        for rect in page.get_image_rects(xref):
            if rect_area(rect) <= 4:
                continue
            rects.append(
                {
                    "rect": fitz.Rect(rect),
                    "xref": xref,
                    "page_image_order": image_order,
                    "kind": "image",
                }
            )
    return rects


def get_drawing_rects(page: fitz.Page) -> list[dict[str, Any]]:
    rects: list[dict[str, Any]] = []
    for drawing_order, drawing in enumerate(page.get_drawings(), start=1):
        rect = fitz.Rect(drawing.get("rect") or fitz.Rect())
        if rect_area(rect) <= 8:
            continue
        # Extremely thin strokes are still useful in diagrams, but tiny dots are noise.
        if rect.width < 1 and rect.height < 1:
            continue
        if rect.height <= 2 and rect.width >= 80:
            # Header/footer rules and page separators are not figure content.
            continue
        rects.append({"rect": rect, "drawing_order": drawing_order, "kind": "drawing"})
    return rects


def get_table_rule_rects(page: fitz.Page) -> list[fitz.Rect]:
    """Return thin table/grid rules that normal figure extraction ignores."""
    rects: list[fitz.Rect] = []
    for drawing in page.get_drawings():
        rect = fitz.Rect(drawing.get("rect") or fitz.Rect())
        if rect.is_infinite:
            continue
        if rect.width < 1:
            rect.x0 -= 0.5
            rect.x1 += 0.5
        if rect.height < 1:
            rect.y0 -= 0.5
            rect.y1 += 0.5
        if rect.width >= 20 and rect.height <= 2.5:
            rects.append(rect)
        elif rect.height >= 20 and rect.width <= 2.5:
            rects.append(rect)
    return rects


def column_bounds(caption_rect: fitz.Rect, page_rect: fitz.Rect) -> tuple[float, float]:
    page_width = float(page_rect.width)
    if caption_rect.width > page_width * 0.55:
        return float(page_rect.x0), float(page_rect.x1)

    mid = page_rect.x0 + page_width / 2
    center = (caption_rect.x0 + caption_rect.x1) / 2
    gutter = page_width * 0.035
    margin = page_width * 0.035
    if center < mid:
        return float(page_rect.x0 + margin), float(mid - gutter)
    return float(mid + gutter), float(page_rect.x1 - margin)


def is_full_width_caption(caption_rect: fitz.Rect, page_rect: fitz.Rect) -> bool:
    return float(caption_rect.width) > float(page_rect.width) * 0.55


def same_column_candidate(
    rect: fitz.Rect,
    column_rect: fitz.Rect,
    page_rect: fitz.Rect,
    full_width_caption: bool,
) -> bool:
    if not intersects_x(rect, column_rect, min_overlap=0.05):
        return False
    if full_width_caption:
        return True

    column_width = max(1.0, float(column_rect.width))
    if float(rect.width) > column_width * 1.25:
        # In two-column papers, page-wide rules/tables often overlap the caption
        # column but should not be pulled into a one-column figure crop.
        return False

    center_x = (float(rect.x0) + float(rect.x1)) / 2.0
    tolerance = column_width * 0.08
    if center_x < float(column_rect.x0) - tolerance:
        return False
    if center_x > float(column_rect.x1) + tolerance:
        return False
    return True


def trim_excluded_caption_and_body(
    page: fitz.Page,
    crop_rect: fitz.Rect,
    caption_rect: fitz.Rect,
    column_rect: fitz.Rect,
    position: str,
) -> fitz.Rect:
    """Keep figure-only crops from bleeding into nearby captions/paragraphs."""
    trimmed = fitz.Rect(crop_rect)
    if position == "above":
        new_y1 = min(float(trimmed.y1), float(caption_rect.y0) - 0.5)
        if new_y1 > float(trimmed.y0) + 4.0:
            trimmed.y1 = new_y1
    elif position == "below":
        new_y0 = max(float(trimmed.y0), float(caption_rect.y1) + 0.5)
        if new_y0 < float(trimmed.y1) - 4.0:
            trimmed.y0 = new_y0

    for block in extract_text_blocks(page):
        rect = block["bbox"]
        text = block["text"]
        if rect == caption_rect:
            continue
        if CAPTION_RE.match(text):
            if not intersects_x(rect, column_rect, min_overlap=0.05):
                continue
            overlap_y = max(0.0, min(float(trimmed.y1), float(rect.y1)) - max(float(trimmed.y0), float(rect.y0)))
            if overlap_y <= 0:
                continue
            if float(rect.y1) <= float(caption_rect.y0):
                new_y0 = float(rect.y1) + 0.5
                if new_y0 < float(trimmed.y1) - 4.0:
                    trimmed.y0 = max(float(trimmed.y0), new_y0)
            elif float(rect.y0) >= float(caption_rect.y1):
                new_y1 = float(rect.y0) - 0.5
                if new_y1 > float(trimmed.y0) + 4.0:
                    trimmed.y1 = min(float(trimmed.y1), new_y1)
            continue
        if len(text) <= 160:
            continue
        if not intersects_x(rect, column_rect, min_overlap=0.05):
            continue
        if position == "above":
            gap = float(trimmed.y0) - float(rect.y1)
            top_overlap = float(rect.y1) - float(trimmed.y0)
            if 0 <= gap <= 20 or (float(rect.y0) < float(trimmed.y0) and 0 < top_overlap <= 20):
                new_y0 = float(rect.y1) + 1.0
                if new_y0 < float(trimmed.y1) - 4.0:
                    trimmed.y0 = new_y0
        elif position == "below":
            gap = float(rect.y0) - float(trimmed.y1)
            bottom_overlap = float(trimmed.y1) - float(rect.y0)
            if 0 <= gap <= 20 or (float(rect.y1) > float(trimmed.y1) and 0 < bottom_overlap <= 20):
                new_y1 = float(rect.y0) - 1.0
                if new_y1 > float(trimmed.y0) + 4.0:
                    trimmed.y1 = new_y1
    return safe_rect(trimmed, page.rect)


def infer_figure_bbox(
    page: fitz.Page,
    caption: Caption,
    max_vertical_gap: float = 260.0,
    include_caption: bool = False,
) -> tuple[fitz.Rect | None, float, str, list[str]]:
    page_rect = page.rect
    caption_rect = caption.bbox
    col_x0, col_x1 = column_bounds(caption_rect, page_rect)
    column_rect = fitz.Rect(col_x0, page_rect.y0, col_x1, page_rect.y1)
    full_width_caption = is_full_width_caption(caption_rect, page_rect)
    prefer_below = is_table_label(caption.figure_id)
    if prefer_below:
        column_rect = fitz.Rect(page_rect)
        full_width_caption = True

    graphic_items = get_image_rects(page) + get_drawing_rects(page)
    next_caption_y0: float | None = None
    if prefer_below:
        later_caption_tops = [
            float(block["bbox"].y0)
            for block in extract_text_blocks(page)
            if block["bbox"].y0 > caption_rect.y1 + 1.0
            and CAPTION_RE.match(block["text"])
        ]
        if later_caption_tops:
            next_caption_y0 = min(later_caption_tops)
    table_below_limit = (
        max(24.0, next_caption_y0 - float(caption_rect.y1) - 2.0)
        if next_caption_y0 is not None
        else max_vertical_gap * 1.8
    )
    above_graphics: list[fitz.Rect] = []
    below_graphics: list[fitz.Rect] = []
    for item in graphic_items:
        rect = item["rect"]
        if not same_column_candidate(rect, column_rect, page_rect, full_width_caption):
            continue
        above_distance = caption_rect.y0 - rect.y1
        below_distance = rect.y0 - caption_rect.y1
        table_body_overlaps_caption = (
            prefer_below
            and rect.y0 <= caption_rect.y1 + 24
            and rect.y1 >= caption_rect.y1 + 12
        )
        if -12 <= above_distance <= max_vertical_gap:
            above_graphics.append(rect)
        elif table_body_overlaps_caption or -12 <= below_distance <= (
            table_below_limit if prefer_below else max_vertical_gap * 0.55
        ):
            below_graphics.append(rect)

    if prefer_below:
        candidate_graphics = below_graphics or above_graphics
        candidate_position = "below" if below_graphics else "above"
    else:
        candidate_graphics = above_graphics or below_graphics
        candidate_position = "above" if above_graphics else "below"

    if prefer_below:
        all_table_rule_rects = sorted(
            [
                rect
                for rect in get_table_rule_rects(page)
                if rect.y0 >= caption_rect.y1 - 5.0
                and rect.y0 <= caption_rect.y1 + max_vertical_gap * 1.8
                and intersects_x(rect, column_rect, min_overlap=0.01)
            ],
            key=lambda rect: (float(rect.y0), float(rect.x0)),
        )
        table_rule_rects: list[fitz.Rect] = []
        table_cluster_bottom: float | None = None
        for rect in all_table_rule_rects:
            if table_cluster_bottom is None:
                table_rule_rects.append(rect)
                table_cluster_bottom = float(rect.y1)
                continue
            if float(rect.y0) <= table_cluster_bottom + 18.0:
                table_rule_rects.append(rect)
                table_cluster_bottom = max(table_cluster_bottom, float(rect.y1))
                continue
            break
        table_rule_rects = [
            rect
            for rect in table_rule_rects
        ]
        table_rule_union = union_rects(table_rule_rects)
        if table_rule_union is not None and rect_area(table_rule_union) > rect_area(caption_rect):
            candidate_graphics = [table_rule_union]
            candidate_position = "below"

    # Nature-style layouts often place a full-width/tall figure above a narrow
    # one-column caption. If this is the first caption on the page, promote the
    # whole graphic band above the caption instead of clipping to one column.
    promoted_full_band = False
    promoted_column_band = False
    if not prefer_below:
        earlier_captions = [
            block["bbox"]
            for block in extract_text_blocks(page)
            if block["bbox"].y1 <= caption_rect.y0 - 1.0
            and CAPTION_RE.match(block["text"])
        ]
        band_top = max((rect.y1 for rect in earlier_captions), default=page_rect.y0)
        full_band_graphics = [
            item["rect"]
            for item in graphic_items
            if item["rect"].y0 >= band_top - 2.0
            and item["rect"].y1 <= caption_rect.y0 + 3.0
        ]
        full_band_union = union_rects(full_band_graphics)
        current_union = union_rects(candidate_graphics)
        page_width = max(1.0, float(page_rect.width))
        page_height = max(1.0, float(page_rect.height))
        current_width = float(current_union.width) if current_union else 0.0
        current_height = float(current_union.height) if current_union else 0.0
        if (
            full_band_union is not None
            and caption_rect.y0 > page_rect.y0 + page_height * 0.45
            and float(full_band_union.width) > page_width * 0.6
            and float(full_band_union.height) > page_height * 0.25
            and (
                current_union is None
                or float(full_band_union.width) > current_width * 1.25
                or float(full_band_union.height) > current_height * 1.25
                or float(full_band_union.y0) < float(current_union.y0) - 40.0
            )
        ):
            candidate_graphics = full_band_graphics
            candidate_position = "above"
            promoted_full_band = True

    # IEEE two-column pages can expose left/right graphics as a shared drawing.
    # If the figure is not page-wide, keep the crop in the caption's column and
    # allow the whole same-column band above the caption to fill missing panels.
    if not prefer_below and not full_width_caption and not promoted_full_band:
        same_column_earlier = [
            block["bbox"]
            for block in extract_text_blocks(page)
            if block["bbox"].y1 <= caption_rect.y0 - 1.0
            and CAPTION_RE.match(block["text"])
            and intersects_x(block["bbox"], column_rect, min_overlap=0.05)
        ]
        band_top = max((rect.y1 for rect in same_column_earlier), default=page_rect.y0)
        column_band_graphics: list[fitz.Rect] = []
        for item in graphic_items:
            rect = item["rect"]
            if rect.y0 < band_top - 2.0 or rect.y1 > caption_rect.y0 + 3.0:
                continue
            if not intersects_x(rect, column_rect, min_overlap=0.05):
                continue
            clipped = safe_rect(
                fitz.Rect(
                    max(float(rect.x0), float(column_rect.x0)),
                    float(rect.y0),
                    min(float(rect.x1), float(column_rect.x1)),
                    float(rect.y1),
                ),
                page_rect,
            )
            if rect_area(clipped) > 8:
                column_band_graphics.append(clipped)
        column_band_union = union_rects(column_band_graphics)
        current_union = union_rects(candidate_graphics)
        page_height = max(1.0, float(page_rect.height))
        current_height = float(current_union.height) if current_union else 0.0
        if (
            column_band_union is not None
            and float(column_band_union.height) > page_height * 0.12
            and (
                current_union is None
                or float(column_band_union.height) > current_height * 1.2
                or float(column_band_union.y0) < float(current_union.y0) - 35.0
            )
        ):
            candidate_graphics = column_band_graphics
            candidate_position = "above"
            promoted_column_band = True

    warnings: list[str] = []
    graphics_union = union_rects(candidate_graphics)
    if graphics_union is None:
        warnings.append("No nearby graphic object found around caption.")
        fallback = fallback_text_band_bbox(page, caption, column_rect)
        if fallback is None:
            return None, 0.25, "debug-page", warnings
        crop_rect = fallback | caption_rect if include_caption else fallback
        crop_rect = expand_rect(crop_rect, page_rect, CROP_MARGIN_PT)
        return crop_rect, 0.48, "bbox-crop-low-confidence", warnings

    # Add figure labels/text near the graphic union, but avoid unrelated body text.
    text_rects: list[fitz.Rect] = []
    expanded_graphics = expand_rect(graphics_union, page_rect, 12)
    for block in extract_text_blocks(page):
        rect = block["bbox"]
        text = block["text"]
        if rect == caption_rect:
            continue
        if CAPTION_RE.match(text):
            continue
        if len(text) > 80 or rect.height > 30:
            # Keep short labels inside diagrams; avoid pulling nearby paragraphs into the crop.
            continue
        lower_text = text.strip().lower()
        if rect.y1 < page_rect.y0 + 45.0 and (
            len(text) > 10
            or lower_text.isdigit()
            or "et al" in lower_text
            or "ieee transactions" in lower_text
        ):
            continue
        if promoted_full_band and rect.y1 < expanded_graphics.y0 - 8.0:
            # Avoid page headers such as Nature's "Article" label.
            continue
        if not intersects_x(rect, expanded_graphics, min_overlap=0.05):
            continue
        vertical_overlap = max(0.0, min(rect.y1, expanded_graphics.y1) - max(rect.y0, expanded_graphics.y0))
        near_vertical = (
            vertical_overlap > 0
            or abs(rect.y1 - expanded_graphics.y0) < 16
            or abs(rect.y0 - expanded_graphics.y1) < 16
        )
        if near_vertical:
            text_rects.append(rect)

    keep_caption = include_caption or prefer_below
    rects = [graphics_union] + text_rects
    if keep_caption:
        rects.append(caption_rect)
    if prefer_below:
        for block in extract_text_blocks(page):
            rect = block["bbox"]
            if rect == caption_rect:
                continue
            if caption_rect.y0 - 2.0 <= rect.y0 <= caption_rect.y1 + 35.0:
                rects.append(rect)
    crop_rect = union_rects(rects)
    if crop_rect is None:
        return None, 0.25, "debug-page", ["Could not form crop bbox."]

    crop_rect = expand_rect(crop_rect, page_rect, CROP_MARGIN_PT)
    if promoted_full_band:
        for block in extract_text_blocks(page):
            if block["text"].strip().lower() == "article" and block["bbox"].y1 < caption_rect.y0:
                crop_rect.y0 = max(float(crop_rect.y0), float(block["bbox"].y1) + 2.0)
        crop_rect = safe_rect(crop_rect, page_rect)
    elif promoted_column_band and not full_width_caption:
        crop_rect.x0 = max(float(crop_rect.x0), float(column_rect.x0) - CROP_MARGIN_PT)
        crop_rect.x1 = min(float(crop_rect.x1), float(column_rect.x1) + CROP_MARGIN_PT)
        crop_rect = safe_rect(crop_rect, page_rect)
    if prefer_below:
        # Table titles are useful in the rendered image, but page headers above
        # the title are not. Keep the crop anchored at the table caption.
        crop_rect.y0 = max(float(crop_rect.y0), float(caption_rect.y0) - 2.0)
        crop_rect.y1 = min(float(crop_rect.y1), float(graphics_union.y1) + TABLE_EXTRA_BOTTOM_PT)
        crop_rect = safe_rect(crop_rect, page_rect)
    elif not include_caption:
        crop_rect.x0 -= FIGURE_EXTRA_LEFT_PT
        if not promoted_full_band:
            crop_rect.y0 -= FIGURE_EXTRA_TOP_PT
        crop_rect.y1 += FIGURE_EXTRA_BOTTOM_PT
        crop_rect = safe_rect(crop_rect, page_rect)
        crop_rect = trim_excluded_caption_and_body(
            page, crop_rect, caption_rect, column_rect, candidate_position
        )
    confidence = 0.86
    if not text_rects:
        confidence -= 0.08
    if rect_area(graphics_union) < rect_area(caption_rect) * 0.5:
        confidence -= 0.15
        warnings.append("Graphic bbox is small relative to caption; verify manually.")
    if crop_rect.height > page_rect.height * 0.65 and not promoted_full_band:
        confidence -= 0.1
        warnings.append("Crop is tall; possible multi-object or paragraph bleed.")
    return crop_rect, max(0.0, min(0.95, confidence)), "bbox-crop", warnings


def fallback_text_band_bbox(
    page: fitz.Page, caption: Caption, column_rect: fitz.Rect
) -> fitz.Rect | None:
    """Low-confidence fallback when no graphic objects are exposed by the PDF."""
    caption_rect = caption.bbox
    blocks = extract_text_blocks(page)
    nearby: list[fitz.Rect] = []
    for block in blocks:
        rect = block["bbox"]
        text = block["text"]
        if CAPTION_RE.match(text):
            continue
        if not intersects_x(rect, column_rect, min_overlap=0.05):
            continue
        if 0 <= caption_rect.y0 - rect.y1 <= 160:
            # Prefer short text labels, not dense paragraphs.
            if len(text) <= 80 or rect.height <= 24:
                nearby.append(rect)
    return union_rects(nearby)


def expand_rect(rect: fitz.Rect, page_rect: fitz.Rect, margin: float) -> fitz.Rect:
    expanded = fitz.Rect(rect.x0 - margin, rect.y0 - margin, rect.x1 + margin, rect.y1 + margin)
    return safe_rect(expanded, page_rect)


def save_region(page: fitz.Page, bbox: fitz.Rect, path: Path, render_dpi: int) -> tuple[int, int, bytes]:
    scale = render_dpi / 72.0
    pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), clip=bbox, alpha=False)
    image_bytes = pix.tobytes("png")
    path.write_bytes(image_bytes)
    width, height = pix.width, pix.height
    pix = None
    return width, height, image_bytes


def save_debug_page(page: fitz.Page, path: Path, render_dpi: int) -> dict[str, Any]:
    pix = page.get_pixmap(dpi=render_dpi, alpha=False)
    image_bytes = pix.tobytes("png")
    path.write_bytes(image_bytes)
    result = {
        "file": str(path.name),
        "width": pix.width,
        "height": pix.height,
        "bytes": path.stat().st_size,
        "sha256": sha256_bytes(image_bytes),
        "render_dpi": render_dpi,
    }
    pix = None
    return result


def sequence_audit(captions: list[Caption], saved_or_skipped: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Report missing numbered captions by label group for human review."""
    present_by_group: dict[str, set[int]] = {}
    for caption in captions:
        value = label_number_value(caption.figure_id)
        if value is None:
            continue
        present_by_group.setdefault(label_group(caption.figure_id), set()).add(value)

    referenced_by_group: dict[str, set[int]] = {}
    for item in saved_or_skipped:
        figure_id = str(item.get("figure_id") or "")
        value = label_number_value(figure_id)
        if value is None:
            continue
        referenced_by_group.setdefault(label_group(figure_id), set()).add(value)

    audit: list[dict[str, Any]] = []
    for group, present in sorted(present_by_group.items()):
        if len(present) < 2:
            continue
        low = min(present)
        high = max(present)
        missing_in_pdf = [number for number in range(low, high + 1) if number not in present]
        missing_from_manifest = [
            number
            for number in range(low, high + 1)
            if number in present and number not in referenced_by_group.get(group, set())
        ]
        if missing_in_pdf or missing_from_manifest:
            audit.append(
                {
                    "group": group,
                    "range": [low, high],
                    "missing_in_pdf_caption_scan": missing_in_pdf,
                    "missing_from_manifest": missing_from_manifest,
                    "warning": (
                        "Check skipped figures/tables before writing Markdown; "
                        "if a number is intentionally omitted, explain why."
                    ),
                }
            )
    return audit


def local_html_figures(html_file: Path, base_url: str | None, out_dir: Path) -> list[dict[str, Any]]:
    """Parse a local HTML file for figure metadata.

    Remote image URLs are recorded but not downloaded. Network fetching should be
    handled by the calling agent through the configured web workflow.
    """
    if not html_file.exists():
        raise FileNotFoundError(f"HTML file not found: {html_file}")
    text = html_file.read_text(encoding="utf-8", errors="replace")
    figures: list[dict[str, Any]] = []
    copied_dir = out_dir / "figures"
    copied_dir.mkdir(parents=True, exist_ok=True)
    for idx, match in enumerate(HTML_FIGURE_RE.finditer(text), start=1):
        body = match.group("body")
        img_match = HTML_IMG_RE.search(body)
        if not img_match:
            continue
        raw_src = html.unescape(img_match.group("src"))
        caption_match = HTML_CAPTION_RE.search(body)
        caption_text = clean_html_text(caption_match.group("caption")) if caption_match else ""
        caption_match_id = CAPTION_RE.match(caption_text)
        figure_id = (
            normalize_figure_id(caption_match_id.group("label"))
            if caption_match_id
            else f"Fig. {idx}"
        )
        resolved_src = urljoin(base_url or html_file.resolve().as_uri(), raw_src)
        parsed = urlparse(resolved_src)
        entry: dict[str, Any] = {
            "figure_id": figure_id,
            "caption": caption_text,
            "source_type": "html-image",
            "source_url": resolved_src,
            "confidence": confidence_label(0.9 if caption_match_id else 0.65),
            "confidence_score": 0.9 if caption_match_id else 0.65,
            "warning": "" if caption_match_id else "HTML figure has no parseable Fig./Table caption.",
        }
        if parsed.scheme == "file":
            src_path = Path(parsed.path)
            if src_path.exists() and src_path.is_file():
                suffix = src_path.suffix.lower() if src_path.suffix else ".png"
                filename = f"{Path(figure_filename(figure_id, idx)).stem}{suffix}"
                dst = copied_dir / filename
                shutil.copy2(src_path, dst)
                data = dst.read_bytes()
                entry.update(
                    {
                        "file": f"figures/{filename}",
                        "bytes": len(data),
                        "sha256": sha256_bytes(data),
                    }
                )
        figures.append(entry)
    return figures


def embedded_candidates(
    doc: fitz.Document,
    out_dir: Path,
    min_bytes: int,
    min_width: int,
    min_height: int,
) -> list[dict[str, Any]]:
    """Save embedded bitmap candidates for audit; not intended for Markdown by default."""
    embedded_dir = out_dir / "embedded_candidates"
    embedded_dir.mkdir(parents=True, exist_ok=True)
    candidates: list[dict[str, Any]] = []
    seen_hashes: set[str] = set()
    index = 1
    for page_index in range(doc.page_count):
        page = doc.load_page(page_index)
        for image_order, image_info in enumerate(page.get_images(full=True), start=1):
            xref = image_info[0]
            extracted = doc.extract_image(xref)
            image_bytes = extracted.get("image", b"")
            width = int(extracted.get("width") or 0)
            height = int(extracted.get("height") or 0)
            if len(image_bytes) < min_bytes or width < min_width or height < min_height:
                continue
            digest = sha256_bytes(image_bytes)
            if digest in seen_hashes:
                continue
            seen_hashes.add(digest)
            filename = f"embedded_{index:03d}.png"
            path = embedded_dir / filename
            try:
                pix = fitz.Pixmap(doc, xref)
                if pix.alpha or pix.n >= 4:
                    converted = fitz.Pixmap(fitz.csRGB, pix)
                    converted.save(path)
                    converted = None
                else:
                    pix.save(path)
                pix = None
            except Exception:
                # If PyMuPDF cannot rebuild the pixmap, keep original bytes when possible.
                path.write_bytes(image_bytes)
            candidates.append(
                {
                    "file": f"embedded_candidates/{filename}",
                    "page": page_index + 1,
                    "source_type": "embedded-candidate",
                    "width": width,
                    "height": height,
                    "bytes": path.stat().st_size,
                    "sha256": digest,
                    "xref": xref,
                    "page_image_order": image_order,
                    "warning": "Audit candidate only; do not cite unless matched to a figure caption.",
                }
            )
            index += 1
    if not candidates:
        try:
            embedded_dir.rmdir()
        except OSError:
            pass
    return candidates


def extract_figures(
    pdf_path: Path,
    out_dir: Path,
    mode: str,
    min_bytes: int,
    min_width: int,
    min_height: int,
    render_dpi: int,
    confidence_threshold: float,
    write_debug_pages: bool,
    save_embedded: bool,
    html_file: Path | None,
    html_base_url: str | None,
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    figures_dir = out_dir / "figures"
    debug_dir = out_dir / "debug_pages"
    figures_dir.mkdir(parents=True, exist_ok=True)
    if write_debug_pages or mode == "page-render":
        debug_dir.mkdir(parents=True, exist_ok=True)

    doc = fitz.open(pdf_path)
    html_figures: list[dict[str, Any]] = []
    if html_file:
        html_figures = local_html_figures(html_file, html_base_url, out_dir)

    pdf_figures: list[dict[str, Any]] = []
    debug_pages: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    if mode == "embedded":
        candidates = embedded_candidates(doc, out_dir, min_bytes, min_width, min_height)
        pdf_figures.extend(candidates)
    else:
        captions = find_captions(doc)
        seen_files: set[str] = set()
        for idx, caption in enumerate(captions, start=1):
            page = doc.load_page(caption.page_index)
            bbox, confidence, source_type, warnings = infer_figure_bbox(page, caption)
            page_number = caption.page_index + 1
            if bbox is None or confidence < confidence_threshold:
                skipped.append(
                    {
                        "figure_id": caption.figure_id,
                        "caption": caption.caption,
                        "page": page_number,
                        "caption_bbox": rect_to_list(caption.bbox),
                        "source_type": source_type,
                        "confidence": confidence_label(confidence),
                        "confidence_score": round(confidence, 3),
                        "warning": "; ".join(warnings) or "Low-confidence figure; review manually.",
                    }
                )
                if write_debug_pages or mode == "page-render":
                    debug_path = debug_dir / page_debug_filename(page_number)
                    if not debug_path.exists():
                        info = save_debug_page(page, debug_path, render_dpi)
                        info.update({"page": page_number, "source_type": "debug-page"})
                        debug_pages.append(info)
                continue

            filename = figure_filename(caption.figure_id, idx)
            if filename in seen_files:
                filename = f"{Path(filename).stem}_{idx:03d}.png"
            seen_files.add(filename)
            out_path = figures_dir / filename
            width, height, image_bytes = save_region(page, bbox, out_path, render_dpi)
            warning = "; ".join(warnings)
            if confidence < 0.75:
                warning = normalize_space(f"{warning}; verify crop manually")
            pdf_figures.append(
                {
                    "file": f"figures/{filename}",
                    "figure_id": caption.figure_id,
                    "caption": caption.caption,
                    "page": page_number,
                    "bbox": rect_to_list(bbox),
                    "caption_bbox": rect_to_list(caption.bbox),
                    "source_type": source_type,
                    "confidence": confidence_label(confidence),
                    "confidence_score": round(confidence, 3),
                    "warning": warning,
                    "width": width,
                    "height": height,
                    "bytes": out_path.stat().st_size,
                    "sha256": sha256_bytes(image_bytes),
                    "render_dpi": render_dpi,
                }
            )

        if save_embedded:
            embedded = embedded_candidates(doc, out_dir, min_bytes, min_width, min_height)
        else:
            embedded = []

        # In explicit page-render mode, render every page, but keep it in debug_pages only.
        if mode == "page-render":
            existing_pages = {item.get("page") for item in debug_pages}
            for page_index in range(doc.page_count):
                page_number = page_index + 1
                if page_number in existing_pages:
                    continue
                page = doc.load_page(page_index)
                debug_path = debug_dir / page_debug_filename(page_number)
                info = save_debug_page(page, debug_path, render_dpi)
                info.update({"page": page_number, "source_type": "debug-page"})
                debug_pages.append(info)
    if mode == "embedded":
        embedded = []

    # Prefer HTML figures when supplied; PDF figures still remain for fallback/audit.
    figures = html_figures + pdf_figures
    sequence_items = figures + skipped
    result = {
        "schema_version": 2,
        "pdf": str(pdf_path),
        "out_dir": str(out_dir),
        "mode": mode,
        "page_count": doc.page_count,
        "figure_count": len([f for f in figures if f.get("file")]),
        "image_count": len([f for f in figures if f.get("file")]),
        "figures": figures,
        "images": figures,
        "skipped": skipped,
        "sequence_audit": sequence_audit(captions if mode != "embedded" else [], sequence_items),
        "debug_pages": debug_pages,
        "embedded_candidates": embedded,
        "policy": {
            "high": "可进入正文，仍需快速目检",
            "medium": "人工目检通过后可进入正文",
            "low": "不进入正文，仅用于排查",
            "debug_pages_should_reference": False,
            "confidence_threshold": confidence_threshold,
        },
    }
    doc.close()

    manifest_path = out_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return result


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract caption-matched paper figures without promoting full-page screenshots."
    )
    parser.add_argument("--pdf", required=True, type=Path, help="Input PDF path.")
    parser.add_argument("--out", required=True, type=Path, help="Output directory.")
    parser.add_argument(
        "--mode",
        choices=["auto", "embedded", "page-render"],
        default="auto",
        help=(
            "auto finds captions and saves figure crops; embedded saves embedded "
            "audit candidates; page-render writes debug pages only."
        ),
    )
    parser.add_argument("--min-bytes", type=int, default=10 * 1024)
    parser.add_argument("--min-width", type=int, default=100)
    parser.add_argument("--min-height", type=int, default=100)
    parser.add_argument("--render-dpi", type=int, default=240)
    parser.add_argument("--confidence-threshold", type=float, default=0.7)
    parser.add_argument(
        "--write-debug-pages",
        action="store_true",
        help="Write whole-page renders into debug_pages/ for manual inspection.",
    )
    parser.add_argument(
        "--save-embedded-candidates",
        action="store_true",
        help="Also save raw embedded bitmap candidates for audit.",
    )
    parser.add_argument(
        "--html-file",
        type=Path,
        help="Optional local HTML file from an official/arXiv page to parse figure URLs/captions.",
    )
    parser.add_argument(
        "--html-base-url",
        help="Base URL used to resolve relative paths in --html-file.",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    pdf_path = args.pdf.resolve()
    out_dir = args.out.resolve()

    if not pdf_path.exists():
        print(f"PDF not found: {pdf_path}", file=sys.stderr)
        return 2
    if not pdf_path.is_file():
        print(f"PDF path is not a file: {pdf_path}", file=sys.stderr)
        return 2

    try:
        result = extract_figures(
            pdf_path=pdf_path,
            out_dir=out_dir,
            mode=args.mode,
            min_bytes=args.min_bytes,
            min_width=args.min_width,
            min_height=args.min_height,
            render_dpi=args.render_dpi,
            confidence_threshold=args.confidence_threshold,
            write_debug_pages=args.write_debug_pages,
            save_embedded=args.save_embedded_candidates,
            html_file=args.html_file.resolve() if args.html_file else None,
            html_base_url=args.html_base_url,
        )
    except Exception as exc:
        print(f"extract_paper_images failed: {exc}", file=sys.stderr)
        return 1

    print(
        json.dumps(
            {
                "pdf": result["pdf"],
                "out_dir": result["out_dir"],
                "page_count": result["page_count"],
                "figure_count": result["figure_count"],
                "skipped": len(result.get("skipped", [])),
                "debug_pages": len(result.get("debug_pages", [])),
                "manifest": str(out_dir / "manifest.json"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
