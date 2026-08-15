#!/usr/bin/env python3
"""Read-only typography gate for PowerPoint OOXML packages."""

from __future__ import annotations

import argparse
import json
import posixpath
import re
import sys
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Iterable

import defusedxml.ElementTree as ET
from defusedxml.common import DefusedXmlException


NS = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "c": "http://schemas.openxmlformats.org/drawingml/2006/chart",
    "dgm": "http://schemas.openxmlformats.org/drawingml/2006/diagram",
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"

BODY_MIN_PT = 18.0
CITATION_MIN_PT = 10.0
TITLE_MIN_PT = 36.0
SECTION_MIN_PT = 20.0

SOURCE_PREFIX_RE = re.compile(
    r"^\s*(?:来源|出处|参考|注|source|citation|reference|footnote|note)\s*[:：]",
    re.IGNORECASE,
)
SOURCE_LINK_RE = re.compile(
    r"(?:https?://|www\.|\bdoi\s*:\s*|\b10\.\d{4,9}/\S+)",
    re.IGNORECASE,
)
SOURCE_NAME_RE = re.compile(
    r"^\s*(?:source|citation|reference|footnote|note|来源|出处|参考|注)(?:\b|\s|[:：_-])",
    re.IGNORECASE,
)
TITLE_NAME_RE = re.compile(r"^\s*(?:title|slide[ _-]*title|标题)(?:\b|\s|[:：_-])", re.IGNORECASE)
SECTION_NAME_RE = re.compile(
    r"^\s*(?:section[ _-]*header|section[ _-]*title|分区标题|小标题)(?:\b|\s|[:：_-])",
    re.IGNORECASE,
)


def configure_utf8_stdio() -> None:
    """Keep machine-readable text stable when Windows redirects Python stdout."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if not callable(reconfigure):
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def q(prefix: str, local: str) -> str:
    return f"{{{NS[prefix]}}}{local}"


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


class AuditInputError(Exception):
    """Invalid input package or exception manifest."""


@dataclass(frozen=True)
class ExceptionRule:
    slide: int
    shape_id: str
    reason: str


@dataclass
class AuditItem:
    slide: int
    part: str
    shape_id: str
    shape_name: str
    location: str
    text: str
    classification: str
    minimum_pt: float
    base_pt: float | None
    size_source: str | None
    autofit_mode: str
    font_scale: float | None
    effective_pt: float | None
    status: str
    reason: str
    exception_reason: str | None = None


@dataclass
class TextContext:
    slide: int
    part: str
    shape_id: str
    shape_name: str
    location: str
    placeholder_type: str | None
    text_body: ET.Element
    layout_body: ET.Element | None
    master_style: ET.Element | None
    presentation_style: ET.Element | None
    relationships: dict[str, dict[str, str]]
    allow_object_marker: bool = True
    require_explicit_size: bool = False


class Package:
    def __init__(self, path: Path):
        self.path = path
        try:
            self.zf = zipfile.ZipFile(path, "r")
        except (zipfile.BadZipFile, OSError) as exc:
            raise AuditInputError(f"cannot open {path}: {exc}") from exc
        self.names = set(self.zf.namelist())

    def close(self) -> None:
        self.zf.close()

    def xml(self, part: str, *, required: bool = True) -> ET.Element | None:
        if part not in self.names:
            if required:
                raise AuditInputError(f"missing OOXML part: {part}")
            return None
        try:
            return ET.fromstring(self.zf.read(part))
        except (ET.ParseError, DefusedXmlException, OSError) as exc:
            raise AuditInputError(f"cannot parse {part}: {exc}") from exc

    def relationships(self, part: str) -> dict[str, dict[str, str]]:
        part_path = PurePosixPath(part)
        rels_name = str(part_path.parent / "_rels" / f"{part_path.name}.rels")
        root = self.xml(rels_name, required=False)
        if root is None:
            return {}
        rels: dict[str, dict[str, str]] = {}
        for rel in root.findall(f"{{{PKG_REL_NS}}}Relationship"):
            rel_id = rel.get("Id")
            target = rel.get("Target")
            if not rel_id or not target:
                continue
            target_mode = rel.get("TargetMode", "Internal")
            resolved = target
            if target_mode.lower() != "external":
                if target.startswith("/"):
                    resolved = target.lstrip("/")
                else:
                    resolved = posixpath.normpath(posixpath.join(posixpath.dirname(part), target))
            rels[rel_id] = {
                "target": resolved,
                "type": rel.get("Type", ""),
                "target_mode": target_mode,
            }
        return rels


def load_exception_rules(path: Path | None) -> dict[tuple[int, str], ExceptionRule]:
    if path is None:
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise AuditInputError(f"cannot read exception manifest {path}: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("exceptions"), list):
        raise AuditInputError("exception manifest must contain an 'exceptions' array")
    rules: dict[tuple[int, str], ExceptionRule] = {}
    for index, raw in enumerate(data["exceptions"], start=1):
        if not isinstance(raw, dict):
            raise AuditInputError(f"exception {index} must be an object")
        slide = raw.get("slide")
        shape_id = raw.get("shape_id")
        reason = raw.get("reason")
        if not isinstance(slide, int) or isinstance(slide, bool) or slide < 1:
            raise AuditInputError(f"exception {index} requires a positive integer slide")
        if isinstance(shape_id, bool) or not isinstance(shape_id, (str, int)):
            raise AuditInputError(f"exception {index} requires one concrete shape_id")
        shape_id = str(shape_id).strip()
        if not shape_id or shape_id == "*":
            raise AuditInputError(f"exception {index} cannot use a blank or wildcard shape_id")
        if not isinstance(reason, str) or not reason.strip():
            raise AuditInputError(f"exception {index} requires the user's non-empty reason")
        key = (slide, shape_id)
        if key in rules:
            raise AuditInputError(f"duplicate exception for slide {slide}, shape {shape_id}")
        rules[key] = ExceptionRule(slide, shape_id, reason.strip())
    return rules


def parse_size(node: ET.Element | None) -> float | None:
    if node is None or node.get("sz") is None:
        return None
    try:
        value = float(node.get("sz", "")) / 100.0
    except ValueError:
        return None
    return value if value > 0 else None


def parse_scale(raw: str | None) -> float | None:
    if raw is None:
        return None
    try:
        value = float(raw[:-1]) / 100.0 if raw.endswith("%") else float(raw) / 100000.0
    except ValueError:
        return None
    return value if 0 < value <= 1 else None


def paragraph_level(paragraph: ET.Element) -> int:
    ppr = paragraph.find("./a:pPr", NS)
    if ppr is None or ppr.get("lvl") is None:
        return 0
    try:
        return min(max(int(ppr.get("lvl", "0")), 0), 8)
    except ValueError:
        return 0


def level_size(container: ET.Element | None, level: int) -> tuple[float | None, str | None]:
    if container is None:
        return None, None
    style = container.find("./a:lstStyle", NS) if local_name(container.tag) in {"txBody", "rich", "txPr"} else container
    if style is None:
        return None, None
    ppr = style.find(f"./a:lvl{level + 1}pPr", NS)
    if ppr is None:
        ppr = style.find("./a:defPPr", NS)
    size = parse_size(ppr.find("./a:defRPr", NS) if ppr is not None else None)
    return (size, f"{local_name(container.tag)} level {level + 1}") if size is not None else (None, None)


def resolve_base_size(
    run: ET.Element | None,
    paragraph: ET.Element,
    context: TextContext,
    *,
    pseudo: bool = False,
) -> tuple[float | None, str | None]:
    if run is not None:
        rpr = run.find("./a:rPr", NS)
        size = parse_size(rpr)
        if size is not None:
            return size, "run rPr"

    ppr = paragraph.find("./a:pPr", NS)
    size = parse_size(ppr.find("./a:defRPr", NS) if ppr is not None else None)
    if size is not None:
        return size, "paragraph defRPr"

    if pseudo:
        size = parse_size(paragraph.find("./a:endParaRPr", NS))
        if size is not None:
            return size, "paragraph endParaRPr"

    level = paragraph_level(paragraph)
    for container in (context.text_body, context.layout_body, context.master_style):
        size, source = level_size(container, level)
        if size is not None:
            return size, source

    if not context.require_explicit_size:
        size, source = level_size(context.presentation_style, level)
        if size is not None:
            return size, source

    size = parse_size(paragraph.find("./a:endParaRPr", NS))
    if size is not None:
        return size, "paragraph endParaRPr"
    return None, None


def autofit_state(text_body: ET.Element) -> tuple[float | None, str, str | None]:
    body_pr = text_body.find("./a:bodyPr", NS)
    if body_pr is None:
        return 1.0, "none", None
    norm = body_pr.find("./a:normAutofit", NS)
    if norm is not None:
        raw = norm.get("fontScale")
        scale = parse_scale(raw)
        if raw is None:
            return None, "normAutofit", "normAutofit_missing_fontScale"
        if scale is None:
            return None, "normAutofit", "normAutofit_invalid_fontScale"
        return scale, "normAutofit", None
    if body_pr.find("./a:spAutoFit", NS) is not None:
        return 1.0, "spAutoFit", None
    if body_pr.find("./a:noAutofit", NS) is not None:
        return 1.0, "noAutofit", None
    return 1.0, "none", None


def shape_metadata(shape: ET.Element) -> tuple[str, str, bool]:
    cnvpr = None
    for path in (
        "./p:nvSpPr/p:cNvPr",
        "./p:nvGraphicFramePr/p:cNvPr",
        "./p:nvCxnSpPr/p:cNvPr",
    ):
        cnvpr = shape.find(path, NS)
        if cnvpr is not None:
            break
    if cnvpr is None:
        return "unknown", "unnamed", False
    hidden = cnvpr.get("hidden", "0").lower() in {"1", "true"}
    return cnvpr.get("id", "unknown"), cnvpr.get("name", "unnamed"), hidden


def placeholder(shape: ET.Element) -> tuple[str | None, str | None]:
    for path in (
        "./p:nvSpPr/p:nvPr/p:ph",
        "./p:nvGraphicFramePr/p:nvPr/p:ph",
        "./p:nvCxnSpPr/p:nvPr/p:ph",
    ):
        ph = shape.find(path, NS)
        if ph is not None:
            return ph.get("type"), ph.get("idx")
    return None, None


def matching_layout_shape(
    layout_root: ET.Element | None, ph_type: str | None, ph_idx: str | None
) -> ET.Element | None:
    if layout_root is None or (ph_type is None and ph_idx is None):
        return None
    fallback = None
    for tag in (q("p", "sp"), q("p", "graphicFrame"), q("p", "cxnSp")):
        for candidate in layout_root.iter(tag):
            candidate_type, candidate_idx = placeholder(candidate)
            if ph_idx is not None and candidate_idx == ph_idx:
                return candidate
            if ph_idx is None and ph_type is not None and candidate_type == ph_type:
                return candidate
            if fallback is None and ph_type is not None and candidate_type == ph_type:
                fallback = candidate
    return fallback


def select_master_style(master_root: ET.Element | None, ph_type: str | None) -> ET.Element | None:
    if master_root is None:
        return None
    if ph_type in {"title", "ctrTitle"}:
        path = "./p:txStyles/p:titleStyle"
    elif ph_type in {"body", "obj", "subTitle"}:
        path = "./p:txStyles/p:bodyStyle"
    else:
        path = "./p:txStyles/p:otherStyle"
    return master_root.find(path, NS)


def normalized_excerpt(text: str, limit: int = 160) -> str:
    cleaned = " ".join(text.split())
    return cleaned if len(cleaned) <= limit else cleaned[: limit - 3] + "..."


def run_has_hyperlink(
    run: ET.Element,
    relationships: dict[str, dict[str, str]],
) -> bool:
    rpr = run.find("./a:rPr", NS)
    if rpr is None:
        return False
    link = rpr.find("./a:hlinkClick", NS)
    if link is None:
        return False
    rel_id = link.get(q("r", "id"))
    if rel_id:
        relationship = relationships.get(rel_id)
        if relationship is not None and relationship["type"].endswith("/hyperlink"):
            return True
    action = link.get("action", "").strip().lower()
    return action.startswith("ppaction://")


def classify_text(
    text: str,
    paragraph_text: str,
    context: TextContext,
    *,
    hyperlinked: bool,
    exception: ExceptionRule | None,
) -> tuple[str, float, str | None]:
    if exception is not None:
        return "authorized_exception", CITATION_MIN_PT, exception.reason
    name = context.shape_name.strip()
    source_by_name = context.allow_object_marker and SOURCE_NAME_RE.search(name) is not None
    source_by_prefix = SOURCE_PREFIX_RE.search(paragraph_text) is not None
    if source_by_name or source_by_prefix or SOURCE_LINK_RE.search(text) or hyperlinked:
        return "source_or_footnote", CITATION_MIN_PT, None
    if context.placeholder_type in {"title", "ctrTitle"} or TITLE_NAME_RE.search(name):
        return "slide_title", TITLE_MIN_PT, None
    if SECTION_NAME_RE.search(name):
        return "section_header", SECTION_MIN_PT, None
    return "ordinary", BODY_MIN_PT, None


class TypographyAuditor:
    def __init__(self, package: Package, rules: dict[tuple[int, str], ExceptionRule]):
        self.package = package
        self.rules = rules
        self.matched_rules: set[tuple[int, str]] = set()
        self.items: list[AuditItem] = []
        self.presentation_root = package.xml("ppt/presentation.xml")
        self.presentation_rels = package.relationships("ppt/presentation.xml")
        self.presentation_style = self.presentation_root.find("./p:defaultTextStyle", NS)

    def slide_parts(self) -> list[str]:
        parts: list[str] = []
        for slide_id in self.presentation_root.findall("./p:sldIdLst/p:sldId", NS):
            rel_id = slide_id.get(q("r", "id"))
            rel = self.presentation_rels.get(rel_id or "")
            if rel and rel["target_mode"].lower() != "external":
                parts.append(rel["target"])
        if not parts:
            raise AuditInputError("presentation contains no ordered slides")
        return parts

    def audit(self) -> dict[str, object]:
        parts = self.slide_parts()
        for slide_number, slide_part in enumerate(parts, start=1):
            self.audit_slide(slide_number, slide_part)
        unused = sorted(set(self.rules) - self.matched_rules)
        if unused:
            rendered = ", ".join(f"slide {slide}, shape {shape}" for slide, shape in unused)
            raise AuditInputError(f"unused or stale exception entries: {rendered}")

        failures = [item for item in self.items if item.status == "fail"]
        effective = [item.effective_pt for item in self.items if item.effective_pt is not None]
        applied = [
            {"slide": rule.slide, "shape_id": rule.shape_id, "reason": rule.reason}
            for key, rule in sorted(self.rules.items())
            if key in self.matched_rules
        ]
        return {
            "file": str(self.package.path),
            "thresholds": {
                "slide_title_pt": TITLE_MIN_PT,
                "section_header_pt": SECTION_MIN_PT,
                "ordinary_pt": BODY_MIN_PT,
                "source_link_footnote_pt": CITATION_MIN_PT,
                "absolute_floor_pt": CITATION_MIN_PT,
            },
            "summary": {
                "slides": len(parts),
                "text_items": len(self.items),
                "failures": len(failures),
                "minimum_effective_pt": min(effective) if effective else None,
                "applied_exceptions": applied,
            },
            "items": [asdict(item) for item in self.items],
            "limitations": [
                "Text baked into raster images, SVG/EMF artwork, video, or embedded objects is not measurable from PowerPoint text XML and still requires full-slide visual inspection."
            ],
        }

    def exception_for(self, slide: int, shape_id: str) -> ExceptionRule | None:
        key = (slide, shape_id)
        rule = self.rules.get(key)
        if rule is not None:
            self.matched_rules.add(key)
        return rule

    def audit_slide(self, slide_number: int, slide_part: str) -> None:
        slide_root = self.package.xml(slide_part)
        slide_rels = self.package.relationships(slide_part)
        layout_part = next(
            (rel["target"] for rel in slide_rels.values() if rel["type"].endswith("/slideLayout")),
            None,
        )
        layout_root = self.package.xml(layout_part, required=False) if layout_part else None
        layout_rels = self.package.relationships(layout_part) if layout_part else {}
        master_part = next(
            (rel["target"] for rel in layout_rels.values() if rel["type"].endswith("/slideMaster")),
            None,
        )
        master_root = self.package.xml(master_part, required=False) if master_part else None

        for shape in slide_root.iter(q("p", "sp")):
            self.audit_shape_text(slide_number, slide_part, shape, slide_rels, layout_root, master_root)
        for shape in slide_root.iter(q("p", "cxnSp")):
            self.audit_shape_text(slide_number, slide_part, shape, slide_rels, layout_root, master_root)
        for frame in slide_root.iter(q("p", "graphicFrame")):
            self.audit_graphic_frame(
                slide_number,
                slide_part,
                frame,
                slide_rels,
                master_root,
            )

    def audit_shape_text(
        self,
        slide: int,
        part: str,
        shape: ET.Element,
        slide_rels: dict[str, dict[str, str]],
        layout_root: ET.Element | None,
        master_root: ET.Element | None,
    ) -> None:
        shape_id, shape_name, hidden = shape_metadata(shape)
        if hidden:
            return
        text_body = shape.find("./p:txBody", NS)
        if text_body is None:
            return
        ph_type, ph_idx = placeholder(shape)
        layout_shape = matching_layout_shape(layout_root, ph_type, ph_idx)
        if ph_type is None and layout_shape is not None:
            inherited_type, _ = placeholder(layout_shape)
            ph_type = inherited_type
        layout_body = layout_shape.find("./p:txBody", NS) if layout_shape is not None else None
        context = TextContext(
            slide=slide,
            part=part,
            shape_id=shape_id,
            shape_name=shape_name,
            location="shape text",
            placeholder_type=ph_type,
            text_body=text_body,
            layout_body=layout_body,
            master_style=select_master_style(master_root, ph_type),
            presentation_style=self.presentation_style,
            relationships=slide_rels,
        )
        self.audit_text_body(context)

    def audit_graphic_frame(
        self,
        slide: int,
        part: str,
        frame: ET.Element,
        slide_rels: dict[str, dict[str, str]],
        master_root: ET.Element | None,
    ) -> None:
        shape_id, shape_name, hidden = shape_metadata(frame)
        if hidden:
            return
        table = frame.find(".//a:tbl", NS)
        if table is not None:
            for index, cell in enumerate(table.findall(".//a:tc", NS), start=1):
                text_body = cell.find("./a:txBody", NS)
                if text_body is None:
                    continue
                context = TextContext(
                    slide=slide,
                    part=part,
                    shape_id=shape_id,
                    shape_name=shape_name,
                    location=f"table cell {index}",
                    placeholder_type=None,
                    text_body=text_body,
                    layout_body=None,
                    master_style=select_master_style(master_root, None),
                    presentation_style=self.presentation_style,
                    relationships=slide_rels,
                    allow_object_marker=False,
                )
                self.audit_text_body(context)

        chart_ref = frame.find(".//c:chart", NS)
        if chart_ref is not None:
            rel_id = chart_ref.get(q("r", "id"))
            rel = slide_rels.get(rel_id or "")
            if rel is None or rel["target_mode"].lower() == "external":
                self.add_unresolved(slide, part, shape_id, shape_name, "native chart", "chart_relationship_unresolved")
            else:
                self.audit_chart(slide, rel["target"], shape_id, shape_name)

        if frame.find(".//dgm:relIds", NS) is not None:
            self.add_unresolved(
                slide,
                part,
                shape_id,
                shape_name,
                "SmartArt",
                "smartart_text_size_not_resolved",
            )

    def audit_chart(self, slide: int, chart_part: str, shape_id: str, shape_name: str) -> None:
        chart_root = self.package.xml(chart_part)
        chart_rels = self.package.relationships(chart_part)
        components = (
            ("title", "chart title"),
            ("legend", "chart legend"),
            ("catAx", "category axis labels"),
            ("valAx", "value axis labels"),
            ("dateAx", "date axis labels"),
            ("serAx", "series axis labels"),
            ("dLbls", "data labels"),
            ("dTable", "chart data table"),
        )
        for tag_name, label in components:
            for component_index, component in enumerate(chart_root.findall(f".//c:{tag_name}", NS), start=1):
                deleted = component.find("./c:delete", NS)
                if deleted is not None and deleted.get("val", "1").lower() in {"1", "true"}:
                    continue
                location = label if component_index == 1 else f"{label} {component_index}"
                rich = component.find("./c:tx/c:rich", NS)
                tx_pr = component.find("./c:txPr", NS)
                text_body = rich if rich is not None else tx_pr
                if text_body is None:
                    self.add_unresolved(
                        slide,
                        chart_part,
                        shape_id,
                        shape_name,
                        location,
                        "chart_text_size_not_explicit",
                    )
                    continue
                context = TextContext(
                    slide=slide,
                    part=chart_part,
                    shape_id=shape_id,
                    shape_name=shape_name,
                    location=location,
                    placeholder_type=None,
                    text_body=text_body,
                    layout_body=None,
                    master_style=None,
                    presentation_style=None,
                    relationships=chart_rels,
                    allow_object_marker=False,
                    require_explicit_size=True,
                )
                self.audit_text_body(context, placeholder_text=f"[{location}]")

    def audit_text_body(self, context: TextContext, placeholder_text: str | None = None) -> None:
        scale, autofit_mode, autofit_error = autofit_state(context.text_body)
        paragraphs = list(context.text_body.findall("./a:p", NS))
        if not paragraphs:
            if placeholder_text:
                self.add_unresolved(
                    context.slide,
                    context.part,
                    context.shape_id,
                    context.shape_name,
                    context.location,
                    "text_paragraph_missing",
                    text=placeholder_text,
                )
            return

        exception = self.exception_for(context.slide, context.shape_id)
        for paragraph in paragraphs:
            runs = [child for child in list(paragraph) if child.tag in {q("a", "r"), q("a", "fld")}]
            texts = []
            for run in runs:
                text_node = run.find("./a:t", NS)
                if text_node is not None and text_node.text and text_node.text.strip():
                    texts.append((run, text_node.text))
            paragraph_text = "".join(text for _, text in texts).strip()
            if not texts and placeholder_text:
                texts = [(None, placeholder_text)]
                paragraph_text = placeholder_text
            if not texts:
                continue

            for run, text in texts:
                hyperlinked = run is not None and run_has_hyperlink(run, context.relationships)
                classification, minimum, exception_reason = classify_text(
                    text,
                    paragraph_text,
                    context,
                    hyperlinked=hyperlinked,
                    exception=exception,
                )
                base, source = resolve_base_size(
                    run,
                    paragraph,
                    context,
                    pseudo=run is None,
                )
                if autofit_error:
                    effective = None
                    status = "fail"
                    reason = autofit_error
                elif base is None:
                    effective = None
                    status = "fail"
                    reason = "font_size_unresolved"
                else:
                    effective = base * (scale if scale is not None else 1.0)
                    status = "pass" if effective + 1e-9 >= minimum else "fail"
                    reason = "ok" if status == "pass" else "below_minimum"
                self.items.append(
                    AuditItem(
                        slide=context.slide,
                        part=context.part,
                        shape_id=context.shape_id,
                        shape_name=context.shape_name,
                        location=context.location,
                        text=normalized_excerpt(text),
                        classification=classification,
                        minimum_pt=minimum,
                        base_pt=base,
                        size_source=source,
                        autofit_mode=autofit_mode,
                        font_scale=scale,
                        effective_pt=effective,
                        status=status,
                        reason=reason,
                        exception_reason=exception_reason,
                    )
                )

    def add_unresolved(
        self,
        slide: int,
        part: str,
        shape_id: str,
        shape_name: str,
        location: str,
        reason: str,
        *,
        text: str = "[unresolved visible text]",
    ) -> None:
        exception = self.exception_for(slide, shape_id)
        classification = "authorized_exception" if exception else "ordinary"
        minimum = CITATION_MIN_PT if exception else BODY_MIN_PT
        self.items.append(
            AuditItem(
                slide=slide,
                part=part,
                shape_id=shape_id,
                shape_name=shape_name,
                location=location,
                text=text,
                classification=classification,
                minimum_pt=minimum,
                base_pt=None,
                size_source=None,
                autofit_mode="unknown",
                font_scale=None,
                effective_pt=None,
                status="fail",
                reason=reason,
                exception_reason=exception.reason if exception else None,
            )
        )


def render_number(value: float | None) -> str:
    return "unresolved" if value is None else f"{value:.2f}".rstrip("0").rstrip(".")


def emit_human(result: dict[str, object]) -> None:
    summary = result["summary"]
    assert isinstance(summary, dict)
    failures = int(summary["failures"])
    state = "PASSED" if failures == 0 else "FAILED"
    print(
        f"Typography audit {state}: {summary['slides']} slide(s), "
        f"{summary['text_items']} text item(s), {failures} failure(s)."
    )
    for raw in result["items"]:
        if raw["status"] != "fail":
            continue
        scale = raw["font_scale"]
        scale_text = "unresolved" if scale is None else f"{scale * 100:.2f}%".rstrip("0").rstrip(".")
        print(
            f"- slide {raw['slide']}, shape {raw['shape_id']} ({raw['shape_name']}), "
            f"{raw['location']}: {raw['reason']}; text={raw['text']!r}; "
            f"base={render_number(raw['base_pt'])}pt; scale={scale_text}; "
            f"effective={render_number(raw['effective_pt'])}pt; "
            f"minimum={render_number(raw['minimum_pt'])}pt"
        )
    applied = summary.get("applied_exceptions", [])
    if applied:
        print("Applied user-authorized exceptions:")
        for entry in applied:
            print(f"- slide {entry['slide']}, shape {entry['shape_id']}: {entry['reason']}")
    print("Note: text embedded in images or other non-text artwork still requires full-slide visual QA.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit effective font sizes in a PowerPoint OOXML package")
    parser.add_argument("path", help="Input .pptx or .potx file (read-only)")
    parser.add_argument("--json", action="store_true", dest="as_json", help="Emit the complete audit as JSON")
    parser.add_argument(
        "--exceptions",
        type=Path,
        default=None,
        help="User-authorized JSON exceptions, each scoped to one slide and one shape",
    )
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    configure_utf8_stdio()
    args = build_parser().parse_args(argv)
    path = Path(args.path)
    if path.suffix.lower() not in {".pptx", ".potx"}:
        print("Error: input must be a .pptx or .potx file", file=sys.stderr)
        return 2
    if not path.is_file():
        print(f"Error: file does not exist: {path}", file=sys.stderr)
        return 2

    package = None
    try:
        rules = load_exception_rules(args.exceptions)
        package = Package(path)
        result = TypographyAuditor(package, rules).audit()
    except AuditInputError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    finally:
        if package is not None:
            package.close()

    if args.as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        emit_human(result)
    summary = result["summary"]
    assert isinstance(summary, dict)
    return 0 if int(summary["failures"]) == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
