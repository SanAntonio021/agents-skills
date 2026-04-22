#!/usr/bin/env python
"""Extract and apply Word template formatting through Microsoft Word COM."""

from __future__ import annotations

import argparse
import json
import re
import sys
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

try:
    import pythoncom
    import win32com.client.gencache
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "pywin32 is required. Install it before using this skill."
    ) from exc

from win32com.client import constants

SKILL_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TEMPLATE_PATH = SKILL_ROOT / "assets" / "default-template.docx"
DEFAULT_PROFILE_PATH = SKILL_ROOT / "assets" / "default-template.style-profile.json"
DEFAULT_REPORT_PATH = SKILL_ROOT / "references" / "default-template-profile.md"
WORK_TEMPLATE_PATH = SKILL_ROOT / "assets" / "work-summary-template.docx"
WORK_PROFILE_PATH = SKILL_ROOT / "assets" / "work-summary-template.style-profile.json"
WORK_REPORT_PATH = SKILL_ROOT / "references" / "work-summary-template-profile.md"
MASTER_TEMPLATE_PATH = SKILL_ROOT / "assets" / "master-default-template.docx"
MASTER_PROFILE_PATH = SKILL_ROOT / "assets" / "master-default-template.style-profile.json"
MASTER_REPORT_PATH = SKILL_ROOT / "references" / "master-default-template-profile.md"
QIYE_SHENBAO_TEMPLATE_PATH = SKILL_ROOT / "assets" / "qiye-shenbao-template.docx"
QIYE_SHENBAO_PROFILE_PATH = (
    SKILL_ROOT / "assets" / "qiye-shenbao-template.style-profile.json"
)
QIYE_SHENBAO_REPORT_PATH = (
    SKILL_ROOT / "references" / "qiye-shenbao-template-profile.md"
)
DEFAULT_PRESET = "qiye-shenbao"
PRESET_PATHS = {
    "tongyong-moren": {
        "template": MASTER_TEMPLATE_PATH,
        "profile": MASTER_PROFILE_PATH,
        "report": MASTER_REPORT_PATH,
    },
    "jishu-zongjie": {
        "template": DEFAULT_TEMPLATE_PATH,
        "profile": DEFAULT_PROFILE_PATH,
        "report": DEFAULT_REPORT_PATH,
    },
    "gongzuo-zongjie": {
        "template": WORK_TEMPLATE_PATH,
        "profile": WORK_PROFILE_PATH,
        "report": WORK_REPORT_PATH,
    },
    "qiye-shenbao": {
        "template": QIYE_SHENBAO_TEMPLATE_PATH,
        "profile": QIYE_SHENBAO_PROFILE_PATH,
        "report": QIYE_SHENBAO_REPORT_PATH,
    },
}
PRESET_ALIASES = {
    "default": "qiye-shenbao",
    "master-default": "tongyong-moren",
    "technical-summary": "jishu-zongjie",
    "work-summary": "gongzuo-zongjie",
}


STYLE_TYPE_MAP = {
    1: "paragraph",
    2: "character",
    3: "table",
    4: "list",
}

BUILTIN_STYLE_IDS = {
    "normal": -1,
    "heading_1": -2,
    "heading_2": -3,
    "heading_3": -4,
    "heading_4": -5,
    "heading_5": -6,
    "heading_6": -7,
    "heading_7": -8,
    "heading_8": -9,
    "heading_9": -10,
    "toc_1": -20,
    "toc_2": -21,
    "toc_3": -22,
    "caption": -35,
    "title": -63,
    "body_text": -67,
    "subtitle": -75,
    "strong": -88,
    "emphasis": -89,
    "list_paragraph": -180,
    "quote": -181,
    "intense_quote": -182,
}

PAGE_SETUP_FIELDS = [
    "TopMargin",
    "BottomMargin",
    "LeftMargin",
    "RightMargin",
    "HeaderDistance",
    "FooterDistance",
    "Gutter",
    "PageWidth",
    "PageHeight",
    "Orientation",
    "MirrorMargins",
    "DifferentFirstPageHeaderFooter",
    "OddAndEvenPagesHeaderFooter",
    "SectionStart",
]

SPECIAL_BODY_SKIP_TOKENS = (
    "toc",
    "caption",
    "header",
    "footer",
    "footnote",
    "endnote",
    "index",
    "quote",
    "comment",
    "\u76ee\u5f55",
    "\u56fe\u6ce8",
    "\u8868\u6ce8",
    "\u9875\u7709",
    "\u9875\u811a",
    "\u811a\u6ce8",
    "\u5c3e\u6ce8",
    "\u6279\u6ce8",
    "\u5f15\u7528",
)


def canonical_preset_name(preset_name: str) -> str:
    return PRESET_ALIASES.get(preset_name, preset_name)


def preset_arg(value: str) -> str:
    preset_name = canonical_preset_name(value)
    if preset_name not in PRESET_PATHS:
        raise argparse.ArgumentTypeError(
            f"Unknown preset: {value}. Canonical presets: {', '.join(PRESET_PATHS)}."
        )
    return preset_name

BODY_STYLE_TOKENS = (
    "master body",
    "normal",
    "body",
    "body text",
    "list paragraph",
    "gf报告正文",
    "\u6b63\u6587",
    "\u4e3b\u4f53",
    "\u65e0\u95f4\u8ddd",
)

SOURCE_BODY_STYLE_TOKENS = (
    "first paragraph",
    "body text first indent",
    "body text",
    "compact",
    "plain text",
    "\u9996\u6bb5",
)


def normalize_style_name(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).replace("\r", " ").replace("\n", " ").strip()
    return re.sub(r"\s+", " ", text).lower()


def clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).replace("\r", " ").replace("\n", " ").strip()
    text = re.sub(r"\s+", " ", text)
    return text or None


def round_number(value: Any) -> float | int | None:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if abs(number - int(number)) < 1e-6:
        return int(number)
    return round(number, 2)


def word_bool(value: Any) -> bool | None:
    if value in (True, -1, 1):
        return True
    if value in (False, 0):
        return False
    return None


def word_color_to_hex(value: Any) -> str | None:
    try:
        color = int(value)
    except (TypeError, ValueError):
        return None
    if color < 0:
        return None
    red = color & 0xFF
    green = (color >> 8) & 0xFF
    blue = (color >> 16) & 0xFF
    return f"#{red:02X}{green:02X}{blue:02X}"


def safe_get(obj: Any, attr: str, default: Any = None) -> Any:
    try:
        return getattr(obj, attr)
    except Exception:
        return default


def style_name(style_ref: Any) -> str | None:
    if style_ref is None:
        return None
    if isinstance(style_ref, str):
        return clean_text(style_ref)
    for attr in ("NameLocal", "Name"):
        value = safe_get(style_ref, attr)
        cleaned = clean_text(value)
        if cleaned:
            return cleaned
    return clean_text(style_ref)


def style_metadata(style_ref: Any) -> dict[str, Any]:
    return {
        "name": style_name(style_ref),
        "normalized_name": normalize_style_name(style_name(style_ref)),
        "built_in": word_bool(safe_get(style_ref, "BuiltIn")),
        "type": STYLE_TYPE_MAP.get(safe_get(style_ref, "Type")),
    }


def iter_collection(collection: Any):
    for index in range(1, collection.Count + 1):
        yield collection(index)


def resolve_style(doc: Any, identifier: Any) -> Any | None:
    if identifier in (None, ""):
        return None
    try:
        return doc.Styles(identifier)
    except Exception:
        return None


def get_builtin_style_name(doc: Any, role: str) -> str | None:
    return style_name(resolve_style(doc, BUILTIN_STYLE_IDS.get(role)))


def collect_used_styles(doc: Any) -> set[str]:
    used: set[str] = set()
    for paragraph in iter_collection(doc.Paragraphs):
        name = style_name(safe_get(paragraph.Range, "Style"))
        if name:
            used.add(name)
    for table in iter_collection(doc.Tables):
        name = style_name(safe_get(table.Range, "Style"))
        if name:
            used.add(name)
    return used


def collect_paragraph_style_counts(doc: Any) -> dict[str, int]:
    counts: dict[str, int] = {}
    for paragraph in iter_collection(doc.Paragraphs):
        name = style_name(safe_get(paragraph.Range, "Style"))
        if name:
            counts[name] = counts.get(name, 0) + 1
    return counts


def extract_font(font_obj: Any) -> dict[str, Any]:
    if font_obj is None:
        return {}
    color = safe_get(font_obj, "Color")
    return {
        "name": clean_text(safe_get(font_obj, "Name")),
        "name_ascii": clean_text(safe_get(font_obj, "NameAscii")),
        "name_far_east": clean_text(safe_get(font_obj, "NameFarEast")),
        "size_pt": round_number(safe_get(font_obj, "Size")),
        "bold": word_bool(safe_get(font_obj, "Bold")),
        "italic": word_bool(safe_get(font_obj, "Italic")),
        "underline": round_number(safe_get(font_obj, "Underline")),
        "all_caps": word_bool(safe_get(font_obj, "AllCaps")),
        "small_caps": word_bool(safe_get(font_obj, "SmallCaps")),
        "color_value": round_number(color),
        "color_hex": word_color_to_hex(color),
    }


def extract_paragraph_format(format_obj: Any) -> dict[str, Any]:
    if format_obj is None:
        return {}
    return {
        "alignment": round_number(safe_get(format_obj, "Alignment")),
        "left_indent_pt": round_number(safe_get(format_obj, "LeftIndent")),
        "right_indent_pt": round_number(safe_get(format_obj, "RightIndent")),
        "first_line_indent_pt": round_number(safe_get(format_obj, "FirstLineIndent")),
        "space_before_pt": round_number(safe_get(format_obj, "SpaceBefore")),
        "space_after_pt": round_number(safe_get(format_obj, "SpaceAfter")),
        "line_spacing_rule": round_number(safe_get(format_obj, "LineSpacingRule")),
        "line_spacing_pt": round_number(safe_get(format_obj, "LineSpacing")),
        "keep_together": word_bool(safe_get(format_obj, "KeepTogether")),
        "keep_with_next": word_bool(safe_get(format_obj, "KeepWithNext")),
        "page_break_before": word_bool(safe_get(format_obj, "PageBreakBefore")),
        "widow_control": word_bool(safe_get(format_obj, "WidowControl")),
        "outline_level": round_number(safe_get(format_obj, "OutlineLevel")),
    }


def extract_page_setup(page_setup: Any) -> dict[str, Any]:
    return {
        "page_width_pt": round_number(safe_get(page_setup, "PageWidth")),
        "page_height_pt": round_number(safe_get(page_setup, "PageHeight")),
        "top_margin_pt": round_number(safe_get(page_setup, "TopMargin")),
        "bottom_margin_pt": round_number(safe_get(page_setup, "BottomMargin")),
        "left_margin_pt": round_number(safe_get(page_setup, "LeftMargin")),
        "right_margin_pt": round_number(safe_get(page_setup, "RightMargin")),
        "header_distance_pt": round_number(safe_get(page_setup, "HeaderDistance")),
        "footer_distance_pt": round_number(safe_get(page_setup, "FooterDistance")),
        "gutter_pt": round_number(safe_get(page_setup, "Gutter")),
        "orientation": round_number(safe_get(page_setup, "Orientation")),
        "mirror_margins": word_bool(safe_get(page_setup, "MirrorMargins")),
        "different_first_page": word_bool(
            safe_get(page_setup, "DifferentFirstPageHeaderFooter")
        ),
        "odd_even_headers": word_bool(
            safe_get(page_setup, "OddAndEvenPagesHeaderFooter")
        ),
        "section_start": round_number(safe_get(page_setup, "SectionStart")),
    }


def extract_style_entry(style_obj: Any) -> dict[str, Any]:
    entry = {
        "name": style_name(style_obj),
        "type": STYLE_TYPE_MAP.get(safe_get(style_obj, "Type")),
        "built_in": word_bool(safe_get(style_obj, "BuiltIn")),
        "visible": word_bool(safe_get(style_obj, "Visible")),
        "in_use": word_bool(safe_get(style_obj, "InUse")),
        "base_style": style_name(safe_get(style_obj, "BaseStyle")),
        "next_style": style_name(safe_get(style_obj, "NextParagraphStyle")),
        "font": extract_font(safe_get(style_obj, "Font")),
    }
    if entry["type"] == "paragraph":
        entry["paragraph"] = extract_paragraph_format(safe_get(style_obj, "ParagraphFormat"))
    return entry


def find_style_by_tokens(doc: Any, tokens: tuple[str, ...]) -> str | None:
    styles_by_name: dict[str, str] = {}
    for style_obj in iter_collection(doc.Styles):
        name = style_name(style_obj)
        normalized_name = normalize_style_name(name)
        if normalized_name and normalized_name not in styles_by_name:
            styles_by_name[normalized_name] = name
    for token in tokens:
        match = styles_by_name.get(normalize_style_name(token))
        if match:
            return match
    return None


def choose_body_style(doc: Any, paragraph_style_counts: dict[str, int]) -> str | None:
    normalized_counts: dict[str, int] = {}
    canonical_names: dict[str, str] = {}
    for name, count in paragraph_style_counts.items():
        normalized_name = normalize_style_name(name)
        normalized_counts[normalized_name] = normalized_counts.get(normalized_name, 0) + count
        canonical_names.setdefault(normalized_name, name)

    best_name = None
    best_count = -1
    for token in BODY_STYLE_TOKENS:
        normalized_token = normalize_style_name(token)
        count = normalized_counts.get(normalized_token, 0)
        if count > best_count and count > 0:
            best_name = canonical_names.get(normalized_token)
            best_count = count

    return (
        best_name
        or get_builtin_style_name(doc, "normal")
        or get_builtin_style_name(doc, "body_text")
        or find_style_by_tokens(doc, BODY_STYLE_TOKENS)
    )


def build_recommended_map(doc: Any, paragraph_style_counts: dict[str, int]) -> dict[str, Any]:
    recommended: dict[str, Any] = {}
    for role in (
        "title",
        "subtitle",
        "normal",
        "body_text",
        "list_paragraph",
        "caption",
        "toc_1",
        "toc_2",
        "toc_3",
    ):
        name = get_builtin_style_name(doc, role)
        if name:
            recommended[role] = name
    for level in range(1, 10):
        role = f"heading_{level}"
        name = get_builtin_style_name(doc, role)
        if name:
            recommended[role] = name
    recommended["body"] = choose_body_style(doc, paragraph_style_counts)
    return recommended


def build_profile(doc: Any, template_path: Path, include_all_styles: bool) -> dict[str, Any]:
    used_styles = collect_used_styles(doc)
    used_normalized = {normalize_style_name(name) for name in used_styles}
    paragraph_style_counts = collect_paragraph_style_counts(doc)
    recommended_map = build_recommended_map(doc, paragraph_style_counts)
    selected_normalized = set(used_normalized)
    selected_normalized.update(
        normalize_style_name(name) for name in recommended_map.values() if name
    )

    styles: list[dict[str, Any]] = []
    for style_obj in iter_collection(doc.Styles):
        entry = extract_style_entry(style_obj)
        normalized_name = normalize_style_name(entry["name"])
        if not include_all_styles:
            if entry["built_in"] is not False and normalized_name not in selected_normalized:
                continue
        styles.append(entry)

    styles.sort(
        key=lambda item: (
            item.get("type") or "",
            0 if item.get("built_in") else 1,
            normalize_style_name(item.get("name")),
        )
    )

    return {
        "template": str(template_path),
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "document": {
            "page_setup": extract_page_setup(doc.Sections(1).PageSetup),
            "style_count": len(styles),
        },
        "recommended_map": recommended_map,
        "styles": styles,
    }


def format_points(value: Any) -> str:
    if value is None:
        return "-"
    try:
        inches = float(value) / 72.0
    except (TypeError, ValueError):
        return str(value)
    return f"{value} pt ({inches:.2f} in)"


def paragraph_summary(paragraph: dict[str, Any]) -> str:
    parts = []
    if paragraph.get("alignment") is not None:
        parts.append(f"align={paragraph['alignment']}")
    if paragraph.get("space_before_pt") is not None:
        parts.append(f"before={paragraph['space_before_pt']}pt")
    if paragraph.get("space_after_pt") is not None:
        parts.append(f"after={paragraph['space_after_pt']}pt")
    if paragraph.get("line_spacing_rule") is not None:
        parts.append(f"lineRule={paragraph['line_spacing_rule']}")
    if paragraph.get("line_spacing_pt") is not None:
        parts.append(f"line={paragraph['line_spacing_pt']}pt")
    if paragraph.get("first_line_indent_pt") is not None:
        parts.append(f"firstLine={paragraph['first_line_indent_pt']}pt")
    return ", ".join(parts) or "-"


def font_summary(font: dict[str, Any]) -> str:
    parts = []
    if font.get("name"):
        parts.append(font["name"])
    if font.get("size_pt") is not None:
        parts.append(f"{font['size_pt']}pt")
    if font.get("bold"):
        parts.append("bold")
    if font.get("italic"):
        parts.append("italic")
    if font.get("color_hex"):
        parts.append(font["color_hex"])
    return ", ".join(parts) or "-"


def profile_report(profile: dict[str, Any]) -> str:
    page_setup = profile["document"]["page_setup"]
    lines = [
        "# Word Template Profile",
        "",
        f"- Template: `{profile['template']}`",
        f"- Generated: `{profile['generated_at_utc']}`",
        f"- Styles captured: `{profile['document']['style_count']}`",
        "",
        "## Page Setup",
        "",
        "| Rule | Value |",
        "| --- | --- |",
        f"| Page size | {format_points(page_setup.get('page_width_pt'))} x {format_points(page_setup.get('page_height_pt'))} |",
        f"| Margins | top {format_points(page_setup.get('top_margin_pt'))}, bottom {format_points(page_setup.get('bottom_margin_pt'))}, left {format_points(page_setup.get('left_margin_pt'))}, right {format_points(page_setup.get('right_margin_pt'))} |",
        f"| Header distance | {format_points(page_setup.get('header_distance_pt'))} |",
        f"| Footer distance | {format_points(page_setup.get('footer_distance_pt'))} |",
        f"| Orientation | {page_setup.get('orientation', '-')} |",
        "",
        "## Recommended Style Map",
        "",
        "| Role | Style |",
        "| --- | --- |",
    ]
    for role, style_name_value in sorted(profile["recommended_map"].items()):
        lines.append(f"| {role} | {style_name_value or '-'} |")
    lines.extend(["", "## Styles", ""])
    for style in profile["styles"]:
        lines.extend(
            [
                f"### {style['name']}",
                "",
                f"- Type: `{style.get('type') or '-'}`",
                f"- Built-in: `{style.get('built_in')}`",
                f"- Base style: `{style.get('base_style') or '-'}`",
                f"- Next style: `{style.get('next_style') or '-'}`",
                f"- Font: {font_summary(style.get('font') or {})}",
                f"- Paragraph: {paragraph_summary(style.get('paragraph') or {})}",
                "",
            ]
        )
    return "\n".join(lines).strip() + "\n"


@contextmanager
def word_application():
    pythoncom.CoInitialize()
    app = None
    try:
        app = win32com.client.gencache.EnsureDispatch("Word.Application")
        app.Visible = False
        app.DisplayAlerts = 0
        app.ScreenUpdating = False
        yield app
    finally:
        if app is not None:
            try:
                app.ScreenUpdating = True
            except Exception:
                pass
            try:
                app.Quit(False)
            except Exception:
                pass
        pythoncom.CoUninitialize()


def open_document(app: Any, path: Path, read_only: bool) -> Any:
    return app.Documents.Open(
        FileName=str(path),
        ConfirmConversions=False,
        ReadOnly=read_only,
        AddToRecentFiles=False,
        Visible=False,
    )


def paragraph_text(paragraph: Any) -> str:
    raw = safe_get(paragraph.Range, "Text", "") or ""
    return raw.replace("\r", "").replace("\x07", "").strip()


def paragraph_is_list(paragraph: Any) -> bool:
    list_type = safe_get(safe_get(paragraph.Range, "ListFormat"), "ListType")
    return list_type not in (None, 0, constants.wdListNoNumbering)


def paragraph_in_table(paragraph: Any) -> bool:
    tables = safe_get(paragraph.Range, "Tables")
    return bool(tables and tables.Count > 0)


def heading_level_from_paragraph(paragraph: Any, heading_names: dict[int, str]) -> int | None:
    style_info = style_metadata(safe_get(paragraph.Range, "Style"))
    current_name = style_info["normalized_name"]
    for level, style_name_value in heading_names.items():
        if current_name and current_name == normalize_style_name(style_name_value):
            return level
    match = re.search(r"(heading|\u6807\u9898)\s*([1-9])", current_name)
    if match:
        return int(match.group(2))
    outline_level = safe_get(paragraph, "OutlineLevel")
    try:
        level = int(outline_level)
    except (TypeError, ValueError):
        return None
    return level if 1 <= level <= 9 else None


def clear_direct_formatting(range_obj: Any) -> int:
    cleared = 0
    for method_name in ("ClearCharacterDirectFormatting", "ClearParagraphDirectFormatting"):
        method = safe_get(range_obj, method_name)
        if callable(method):
            try:
                method()
                cleared += 1
            except Exception:
                pass
    return cleared


def should_assign_title(
    paragraph: Any,
    style_info: dict[str, Any],
    title_mode: str,
    body_like_names: set[str],
    first_heading_seen: bool,
) -> bool:
    if first_heading_seen or title_mode == "skip":
        return False
    text = paragraph_text(paragraph)
    if not text or paragraph_in_table(paragraph) or paragraph_is_list(paragraph):
        return False
    if title_mode == "first-paragraph":
        return True
    return len(text) <= 120 and (
        not style_info["normalized_name"]
        or style_info["normalized_name"] in body_like_names
    )


def should_apply_body_style(
    paragraph: Any,
    style_info: dict[str, Any],
    body_like_names: set[str],
    special_names: set[str],
) -> bool:
    text = paragraph_text(paragraph)
    if not text:
        return False
    if paragraph_in_table(paragraph) or paragraph_is_list(paragraph):
        return False
    current_name = style_info["normalized_name"]
    if any(token in current_name for token in SPECIAL_BODY_SKIP_TOKENS):
        return False
    if current_name in special_names:
        return False
    if style_info["built_in"] is False and current_name and current_name not in body_like_names:
        return False
    return True


def apply_page_setup(template_doc: Any, target_doc: Any, page_scope: str) -> dict[str, Any]:
    source_setup = template_doc.Sections(1).PageSetup
    if page_scope == "first-section":
        target_sections = [target_doc.Sections(1)]
    else:
        target_sections = list(iter_collection(target_doc.Sections))

    applied_fields = 0
    for section in target_sections:
        target_setup = section.PageSetup
        for field_name in PAGE_SETUP_FIELDS:
            value = safe_get(source_setup, field_name)
            if value is None:
                continue
            try:
                setattr(target_setup, field_name, value)
                applied_fields += 1
            except Exception:
                continue
    return {
        "sections_updated": len(target_sections),
        "page_setup_fields_applied": applied_fields,
    }


def build_apply_style_map(
    doc: Any,
    profile: dict[str, Any],
    body_style_override: str | None,
    title_style_override: str | None,
) -> dict[str, Any]:
    recommended = dict(profile.get("recommended_map") or {})
    if body_style_override:
        recommended["body"] = body_style_override
    if title_style_override:
        recommended["title"] = title_style_override

    body_like_names = {
        normalize_style_name(recommended.get("normal")),
        normalize_style_name(recommended.get("body_text")),
        normalize_style_name(recommended.get("body")),
        normalize_style_name(recommended.get("list_paragraph")),
        normalize_style_name(find_style_by_tokens(doc, ("No Spacing", "\u65e0\u95f4\u8ddd"))),
    }
    for token in SOURCE_BODY_STYLE_TOKENS:
        body_like_names.add(normalize_style_name(find_style_by_tokens(doc, (token,))))
    body_like_names.discard("")

    heading_names = {}
    for level in range(1, 10):
        style_name_value = recommended.get(f"heading_{level}")
        if not style_name_value:
            style_name_value = get_builtin_style_name(doc, f"heading_{level}")
        if style_name_value:
            heading_names[level] = style_name_value

    special_names = {
        normalize_style_name(recommended.get("title")),
        normalize_style_name(recommended.get("subtitle")),
        normalize_style_name(recommended.get("caption")),
        normalize_style_name(recommended.get("toc_1")),
        normalize_style_name(recommended.get("toc_2")),
        normalize_style_name(recommended.get("toc_3")),
    }
    special_names.update(normalize_style_name(name) for name in heading_names.values())
    special_names.discard("")

    return {
        "title": recommended.get("title"),
        "body": recommended.get("body"),
        "headings": heading_names,
        "body_like_names": body_like_names,
        "special_names": special_names,
    }


def apply_styles_to_document(
    doc: Any,
    style_map: dict[str, Any],
    title_mode: str,
    clear_direct: bool,
) -> dict[str, Any]:
    stats = {
        "title_paragraphs": 0,
        "heading_paragraphs": 0,
        "body_paragraphs": 0,
        "skipped_paragraphs": 0,
        "direct_format_resets": 0,
    }
    first_heading_seen = False
    first_non_empty_seen = False

    for paragraph in iter_collection(doc.Paragraphs):
        text = paragraph_text(paragraph)
        if not text:
            continue

        style_info = style_metadata(safe_get(paragraph.Range, "Style"))
        heading_level = heading_level_from_paragraph(paragraph, style_map["headings"])
        if heading_level is not None:
            first_heading_seen = True
            target_style = style_map["headings"].get(heading_level)
            if target_style:
                if clear_direct:
                    stats["direct_format_resets"] += clear_direct_formatting(paragraph.Range)
                paragraph.Range.Style = target_style
                stats["heading_paragraphs"] += 1
            continue

        if not first_non_empty_seen and style_map.get("title"):
            if should_assign_title(
                paragraph,
                style_info,
                title_mode,
                style_map["body_like_names"],
                first_heading_seen,
            ):
                if clear_direct:
                    stats["direct_format_resets"] += clear_direct_formatting(paragraph.Range)
                paragraph.Range.Style = style_map["title"]
                stats["title_paragraphs"] += 1
                first_non_empty_seen = True
                continue
        first_non_empty_seen = True

        if style_map.get("body") and should_apply_body_style(
            paragraph,
            style_info,
            style_map["body_like_names"],
            style_map["special_names"],
        ):
            if clear_direct:
                stats["direct_format_resets"] += clear_direct_formatting(paragraph.Range)
            paragraph.Range.Style = style_map["body"]
            stats["body_paragraphs"] += 1
        else:
            stats["skipped_paragraphs"] += 1

    return stats


def default_profile_path(template_path: Path) -> Path:
    preset_name = preset_name_for_template(template_path)
    if preset_name:
        return PRESET_PATHS[preset_name]["profile"]
    return template_path.with_name(f"{template_path.stem}.style-profile.json")


def default_report_path(template_path: Path) -> Path:
    preset_name = preset_name_for_template(template_path)
    if preset_name:
        return PRESET_PATHS[preset_name]["report"]
    return template_path.with_name(f"{template_path.stem}.style-profile.md")


def preset_name_for_template(template_path: Path) -> str | None:
    resolved = template_path.resolve()
    for preset_name, preset_paths in PRESET_PATHS.items():
        if resolved == preset_paths["template"].resolve():
            return preset_name
    return None


def resolve_template_path(template_arg: Path | None, preset: str | None) -> Path:
    if template_arg is None:
        preset_name = canonical_preset_name(preset or DEFAULT_PRESET)
        if preset_name not in PRESET_PATHS:
            raise SystemExit(
                f"Unknown preset: {preset_name}. Canonical presets: {', '.join(PRESET_PATHS)}."
            )
        template_path = PRESET_PATHS[preset_name]["template"].resolve()
    else:
        template_path = template_arg.expanduser().resolve()
    if not template_path.exists():
        raise SystemExit(
            f"Template not found: {template_path}. "
            f"Pass --template explicitly or check the preset assets under {SKILL_ROOT / 'assets'}."
        )
    if template_path.suffix.lower() != ".docx":
        raise SystemExit(
            f"Template must be a .docx file: {template_path}"
        )
    return template_path


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def extract_command(args: argparse.Namespace) -> int:
    template_path = resolve_template_path(args.template, args.preset)
    profile_path = (args.profile or default_profile_path(template_path)).resolve()
    report_path = (args.report or default_report_path(template_path)).resolve()

    with word_application() as app:
        template_doc = open_document(app, template_path, read_only=True)
        try:
            profile = build_profile(template_doc, template_path, args.all_styles)
        finally:
            template_doc.Close(False)

    write_json(profile_path, profile)
    write_text(report_path, profile_report(profile))
    print(f"Profile written: {profile_path}")
    print(f"Report written:  {report_path}")
    print(f"Styles captured: {profile['document']['style_count']}")
    return 0


def save_document(doc: Any, input_path: Path, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists() and output_path.resolve() != input_path.resolve():
        output_path.unlink()
    if output_path.resolve() == input_path.resolve():
        doc.Save()
        return
    doc.SaveAs2(
        FileName=str(output_path),
        FileFormat=getattr(constants, "wdFormatXMLDocument", 12),
        AddToRecentFiles=False,
    )


def load_or_extract_profile(
    template_doc: Any,
    template_path: Path,
    profile_path: Path | None,
) -> dict[str, Any]:
    if profile_path is None:
        auto_profile_path = default_profile_path(template_path)
        if auto_profile_path.exists():
            profile_path = auto_profile_path
    if profile_path:
        return json.loads(profile_path.read_text(encoding="utf-8"))
    return build_profile(template_doc, template_path, include_all_styles=False)


def apply_command(args: argparse.Namespace) -> int:
    template_path = resolve_template_path(args.template, args.preset)
    input_path = args.input.resolve()
    output_path = (
        args.output or input_path.with_name(f"{input_path.stem}.formatted.docx")
    ).resolve()
    profile_path = args.profile.resolve() if args.profile else None

    with word_application() as app:
        template_doc = open_document(app, template_path, read_only=True)
        target_doc = open_document(app, input_path, read_only=False)
        try:
            profile = load_or_extract_profile(template_doc, template_path, profile_path)
            target_doc.CopyStylesFromTemplate(str(template_path))
            page_stats = apply_page_setup(template_doc, target_doc, args.page_scope)
            style_map = build_apply_style_map(
                target_doc,
                profile,
                body_style_override=args.body_style,
                title_style_override=args.title_style,
            )
            style_stats = apply_styles_to_document(
                target_doc,
                style_map,
                title_mode=args.title_mode,
                clear_direct=args.clear_direct_formatting,
            )
            save_document(target_doc, input_path, output_path)
        finally:
            try:
                target_doc.Close(False)
            finally:
                template_doc.Close(False)

    print(f"Formatted document written: {output_path}")
    print(
        "Updated sections: {sections_updated}, page fields copied: {page_setup_fields_applied}".format(
            **page_stats
        )
    )
    print(
        "Restyled paragraphs: title={title_paragraphs}, headings={heading_paragraphs}, body={body_paragraphs}, skipped={skipped_paragraphs}, resets={direct_format_resets}".format(
            **style_stats
        )
    )
    return 0


def existing_docx_path(value: str) -> Path:
    path = Path(value).expanduser()
    if not path.exists():
        raise argparse.ArgumentTypeError(f"Path does not exist: {value}")
    if path.suffix.lower() != ".docx":
        raise argparse.ArgumentTypeError(f"Expected a .docx file: {value}")
    return path


def output_docx_path(value: str) -> Path:
    path = Path(value).expanduser()
    if path.suffix.lower() != ".docx":
        raise argparse.ArgumentTypeError(f"Output must be a .docx file: {value}")
    return path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Extract Word template formatting and apply it to other DOCX files."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    extract_parser = subparsers.add_parser("extract", help="Extract template formatting.")
    extract_parser.add_argument(
        "--preset",
        type=preset_arg,
        default=DEFAULT_PRESET,
        help=(
            "Built-in template preset to use when --template is omitted. "
            f"Canonical presets: {', '.join(PRESET_PATHS)}. "
            "Legacy English aliases are still accepted."
        ),
    )
    extract_parser.add_argument(
        "--template",
        type=Path,
        help=f"Template DOCX path. Overrides --preset when provided.",
    )
    extract_parser.add_argument("--profile", type=Path)
    extract_parser.add_argument("--report", type=Path)
    extract_parser.add_argument(
        "--all-styles",
        action="store_true",
        help="Capture every style instead of only used/core/custom styles.",
    )
    extract_parser.set_defaults(func=extract_command)

    apply_parser = subparsers.add_parser("apply", help="Apply template formatting.")
    apply_parser.add_argument(
        "--preset",
        type=preset_arg,
        default=DEFAULT_PRESET,
        help=(
            "Built-in template preset to use when --template is omitted. "
            f"Canonical presets: {', '.join(PRESET_PATHS)}. "
            "Legacy English aliases are still accepted."
        ),
    )
    apply_parser.add_argument(
        "--template",
        type=Path,
        help=f"Template DOCX path. Overrides --preset when provided.",
    )
    apply_parser.add_argument("--input", required=True, type=existing_docx_path)
    apply_parser.add_argument("--output", type=output_docx_path)
    apply_parser.add_argument("--profile", type=Path)
    apply_parser.add_argument(
        "--title-mode",
        choices=("auto", "first-paragraph", "skip"),
        default="auto",
        help="How to assign the template title style.",
    )
    apply_parser.add_argument(
        "--page-scope",
        choices=("all-sections", "first-section"),
        default="all-sections",
        help="Where to copy page setup values.",
    )
    apply_parser.add_argument(
        "--clear-direct-formatting",
        action="store_true",
        help="Clear paragraph and character direct formatting before styling.",
    )
    apply_parser.add_argument(
        "--body-style",
        help="Override the detected body style name.",
    )
    apply_parser.add_argument(
        "--title-style",
        help="Override the detected title style name.",
    )
    apply_parser.set_defaults(func=apply_command)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
