#!/usr/bin/env python3
"""Reuse local PPTX/POTX slide designs with explicit native shape slots.

Only native text shapes and pictures are writable. Kept design shapes, masters,
layouts and themes retain their XML. Charts, embedded objects, linked resources
and media are rejected in the retained graph. Unselected slide content, notes,
comments, metadata and unreachable package parts are excluded from the output.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import io
import json
import posixpath
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

from lxml import etree as ET
from PIL import Image

NS = {"p": "http://schemas.openxmlformats.org/presentationml/2006/main",
      "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
      "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}
REL = "http://schemas.openxmlformats.org/package/2006/relationships"
CT = "http://schemas.openxmlformats.org/package/2006/content-types"
STRUCTURAL = {"slideLayout", "slideMaster", "theme", "themeOverride"}


def xml(data):
    return ET.fromstring(data, ET.XMLParser(resolve_entities=False, no_network=True))


def dump(root):
    return ET.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def relpath(part):
    folder, name = posixpath.split(part)
    return posixpath.join(folder, "_rels", name + ".rels") if part else "_rels/.rels"


def target(part, rel):
    value = rel.get("Target", "")
    resolved = posixpath.normpath(posixpath.join(posixpath.dirname(part), value)) if not value.startswith("/") else value[1:]
    if resolved.startswith("../") or resolved in {"", ".", ".."}:
        raise ValueError(f"Invalid package relationship: {value}")
    return resolved


def relationships(parts, part):
    return xml(parts[relpath(part)]) if relpath(part) in parts else ET.Element(f"{{{REL}}}Relationships")


def slide_parts(parts):
    root = xml(parts["ppt/presentation.xml"])
    rels = {r.get("Id"): r for r in relationships(parts, "ppt/presentation.xml")}
    ordered = []
    for slide in root.findall("p:sldIdLst/p:sldId", NS):
        relation = rels[slide.get(f"{{{NS['r']}}}id")]
        if relation.get("TargetMode") == "External":
            raise ValueError("External slide relationships are unsupported")
        ordered.append(target("ppt/presentation.xml", relation))
    return root, ordered


def shape_id(shape):
    if ET.QName(shape).localname not in {"sp", "pic", "grpSp", "graphicFrame", "cxnSp", "contentPart"}:
        return None
    node = shape.find(".//p:cNvPr", NS)
    return int(node.get("id")) if node is not None else None


def bounds(shape):
    transform = shape.find("p:spPr/a:xfrm", NS)
    if transform is None:
        transform = shape.find("p:grpSpPr/a:xfrm", NS)
    if transform is None:
        transform = shape.find("p:xfrm", NS)
    if transform is None:
        return None
    off, ext = transform.find("a:off", NS), transform.find("a:ext", NS)
    if off is None or ext is None:
        return None
    return [int(off.get("x")), int(off.get("y")), int(ext.get("cx")), int(ext.get("cy"))]


def inspect_template(path: Path) -> dict:
    with ZipFile(path) as archive:
        parts = {name: archive.read(name) for name in archive.namelist()}
    presentation, ordered = slide_parts(parts)
    size = presentation.find("p:sldSz", NS)
    report = {"size_emu": [int(size.get("cx")), int(size.get("cy"))],
              "slide_count": len(ordered), "slides": []}
    for index, part in enumerate(ordered, 1):
        shapes = []
        for shape in xml(parts[part]).find("p:cSld/p:spTree", NS):
            sid = shape_id(shape)
            if sid is None:
                continue
            props = shape.find(".//p:cNvPr", NS)
            shapes.append({"shape_id": sid, "name": props.get("name", ""),
                           "type": ET.QName(shape).localname,
                           "text": "\n".join("".join(t.text or "" for t in p.findall(".//a:t", NS)) for p in shape.findall(".//a:p", NS)),
                           "bounds_emu": bounds(shape)})
        report["slides"].append({"number": index, "shapes": shapes})
    return report


def replace_text(shape, text):
    if shape.tag != f"{{{NS['p']}}}sp":
        raise ValueError("Text slots must refer to top-level native text shapes")
    body = shape.find("p:txBody", NS)
    if body is None:
        raise ValueError(f"Shape {shape_id(shape)} has no native text body")
    original = body.find("a:p", NS)
    props = original.find("a:pPr", NS) if original is not None else None
    run_props = original.find("a:r/a:rPr", NS) if original is not None else None
    end_props = original.find("a:endParaRPr", NS) if original is not None else None
    for paragraph in list(body.findall("a:p", NS)):
        body.remove(paragraph)
    for line in str(text).split("\n"):
        paragraph = ET.SubElement(body, f"{{{NS['a']}}}p")
        if props is not None:
            paragraph.append(copy.deepcopy(props))
        run = ET.SubElement(paragraph, f"{{{NS['a']}}}r")
        if run_props is not None:
            run.append(copy.deepcopy(run_props))
        ET.SubElement(run, f"{{{NS['a']}}}t").text = line
        if end_props is not None:
            paragraph.append(copy.deepcopy(end_props))


def clean_xml(root):
    # Extensions, animations and hidden payloads can reference old report data.
    for element in list(root.iter()):
        if ET.QName(element).localname in {"extLst", "timing", "transition", "custDataLst", "tagLst"}:
            parent = element.getparent()
            if parent is not None:
                parent.remove(element)
        elif ET.QName(element).localname == "cNvPr":
            for attr in ("descr", "title"):
                element.attrib.pop(attr, None)
        elif ET.QName(element).localname == "cSld":
            element.attrib.pop("name", None)


def check_supported(root):
    for node in root.iter():
        if ET.QName(node).localname in {"graphicFrame", "oleObj", "chart", "videoFile", "audioFile", "wavAudioFile", "contentPart", "control"}:
            raise ValueError("Retained template content includes unsupported chart, embedded object or media")


def referenced_ids(root):
    return {value for node in root.iter() for key, value in node.attrib.items() if key.startswith("{" + NS["r"] + "}")}


def prune(parts):
    """Walk package relations, retaining only reachable design and output parts."""
    result, pending, visited = {}, [""], set()
    allowed = STRUCTURAL | {"officeDocument", "slide", "image"}
    while pending:
        part = pending.pop()
        if part in visited:
            continue
        visited.add(part)
        if part and part not in parts:
            raise ValueError(f"Missing package part: {part}")
        refs = set()
        if part:
            data = parts[part]
            if part.endswith(".xml"):
                root = xml(data)
                clean_xml(root)
                check_supported(root)
                refs = referenced_ids(root)
                data = dump(root)
            result[part] = data
        rels = relationships(parts, part)
        for relation in list(rels):
            kind = relation.get("Type", "").rsplit("/", 1)[-1]
            keep = (not part and kind == "officeDocument") or kind in STRUCTURAL or relation.get("Id") in refs
            if not keep:
                rels.remove(relation)
                continue
            if relation.get("TargetMode") == "External":
                raise ValueError("Retained template contains an external relationship; remove linked resources first")
            if kind not in allowed:
                raise ValueError(f"Unsupported retained relationship: {kind}")
            pending.append(target(part, relation))
        if len(rels):
            result[relpath(part)] = dump(rels)
        if part and refs - {r.get("Id") for r in rels}:
            raise ValueError(f"Unresolved template relationship in {part}")
    content_types = xml(parts["[Content_Types].xml"])
    for entry in list(content_types):
        if ET.QName(entry).localname == "Override" and entry.get("PartName", "").lstrip("/") not in result:
            content_types.remove(entry)
        elif entry.get("PartName") == "/ppt/presentation.xml":
            entry.set("ContentType", "application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml")
    if not any(e.get("Extension") == "png" for e in content_types):
        ET.SubElement(content_types, f"{{{CT}}}Default", Extension="png", ContentType="image/png")
    for name in result:
        if name.startswith("ppt/slides/slide") and name.endswith(".xml") and not any(e.get("PartName") == "/" + name for e in content_types):
            ET.SubElement(content_types, f"{{{CT}}}Override", PartName="/" + name,
                          ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml")
    result["[Content_Types].xml"] = dump(content_types)
    return result


def make_template_pptx(deck, slides, output_path, template_spec_path: Path) -> list:
    from render_deck import raster_bytes, text_rows

    output_path = Path(output_path)
    if output_path.exists():
        raise FileExistsError(output_path)
    spec = json.loads(Path(template_spec_path).read_text(encoding="utf-8-sig"))
    source = Path(spec["template_path"]).expanduser()
    source = source.resolve() if source.is_absolute() else (Path(template_spec_path).resolve().parent / source).resolve()
    original = source.read_bytes()
    with ZipFile(io.BytesIO(original)) as archive:
        parts = {name: archive.read(name) for name in archive.namelist()}
    presentation, ordered = slide_parts(parts)
    output_parts = dict(parts)
    assets = []
    new_relations = []
    for index, content in enumerate(slides, 1):
        key = content.get("template_layout") or ("next_steps" if content.get("type") == "next_steps" else "result")
        if content.get("type") == "next_steps" and "next_steps" not in spec.get("layouts", {}):
            raise ValueError("Template spec requires an explicit next_steps layout")
        if key not in spec.get("layouts", {}):
            raise ValueError(f"No template layout configured: {key}")
        layout = spec["layouts"][key]
        page = layout["slide"]
        if not isinstance(page, int) or not 1 <= page <= len(ordered):
            raise ValueError(f"Invalid template slide number: {page}")
        old_part = ordered[page - 1]
        root = xml(parts[old_part])
        clean_xml(root)
        tree = root.find("p:cSld/p:spTree", NS)
        shapes = {shape_id(s): s for s in tree if shape_id(s) is not None}
        slots = layout.get("slots", {})
        if set(slots) - {"title", "date", "summary", "body", "images", "captions"}:
            raise ValueError("Unknown template slot name")
        image_ids, caption_ids = slots.get("images", []), slots.get("captions", [])
        mapped = [v for k, v in slots.items() if k not in {"images", "captions"}] + image_ids + caption_ids
        if len(mapped) != len(set(mapped)):
            raise ValueError("Each template slot must use a distinct shape ID")
        kept = set(layout.get("keep_shape_ids", [])) | set(mapped)
        if kept - shapes.keys():
            raise ValueError(f"Template references missing top-level shape IDs: {sorted(kept - shapes.keys())}")
        for sid in mapped:
            if shapes[sid].tag == f"{{{NS['p']}}}grpSp":
                raise ValueError("Grouped shapes cannot be mapped as slots; use top-level native shapes")
            shapes[sid].find(".//p:cNvPr", NS).set("name", f"Report slot {sid}")
        size = presentation.find("p:sldSz", NS)
        page_width, page_height = int(size.get("cx")), int(size.get("cy"))
        for raw_id, override in layout.get("shape_overrides", {}).items():
            sid = int(raw_id)
            box = override.get("box_emu")
            if sid not in kept or set(override) != {"box_emu"} or not isinstance(box, list) or len(box) != 4:
                raise ValueError("shape_overrides requires a kept shape ID and box_emu [x, y, width, height]")
            if any(not isinstance(v, int) or isinstance(v, bool) for v in box) or min(box[:2]) < 0 or min(box[2:]) <= 0 or box[0] + box[2] > page_width or box[1] + box[3] > page_height:
                raise ValueError("shape_overrides box_emu must be positive and within the template page")
            shape = shapes[sid]
            if shape.tag not in {f"{{{NS['p']}}}sp", f"{{{NS['p']}}}pic"}:
                raise ValueError("shape_overrides only supports native text and picture shapes")
            transform = shape.find("p:spPr/a:xfrm", NS)
            if transform is None:
                raise ValueError("shape_overrides requires an explicit native transform")
            off, ext = transform.find("a:off", NS), transform.find("a:ext", NS)
            if off is None or ext is None:
                raise ValueError("shape_overrides requires native position and dimensions")
            for name, value in zip(("x", "y"), box[:2]):
                off.set(name, str(value))
            for name, value in zip(("cx", "cy"), box[2:]):
                ext.set(name, str(value))
        for shape in list(tree):
            if shape_id(shape) is not None and shape_id(shape) not in kept:
                tree.remove(shape)
        rows = [row for block in content["blocks"] if block["type"] != "image" for row in text_rows(block)]
        texts = {"title": str(content.get("title") or ""), "date": str(content.get("date") or deck.get("date") or ""),
                 "summary": str(content.get("summary") or content.get("subtitle") or ""),
                 "body": "\n".join(row[0] for row in rows)}
        for name, value in texts.items():
            if name in slots:
                replace_text(shapes[slots[name]], value)
            elif value and name in {"summary", "body", "title"}:
                raise ValueError(f"Template layout {key} has no {name} slot for supplied content")
        pictures = [b for b in content["blocks"] if b["type"] == "image"]
        if len(pictures) > len(image_ids):
            raise ValueError(f"Template layout {key} has {len(image_ids)} image slots, but {len(pictures)} images were supplied")
        if len(caption_ids) > len(image_ids):
            raise ValueError("Caption slots cannot outnumber image slots")
        rels = relationships(parts, old_part)
        # Resolve all remaining relations against the old slide location before copying.
        new_part = f"ppt/slides/slide{index}.xml"
        for relation in rels:
            if relation.get("TargetMode") != "External":
                relation.set("Target", posixpath.relpath(target(old_part, relation), posixpath.dirname(new_part)))
        used_ids = {r.get("Id") for r in rels}
        for position, sid in enumerate(image_ids):
            shape = shapes[sid]
            if shape.tag != f"{{{NS['p']}}}pic":
                raise ValueError("Image slots require top-level native picture shapes")
            if position >= len(pictures):
                tree.remove(shape)
                if position < len(caption_ids):
                    tree.remove(shapes[caption_ids[position]])
                continue
            block = pictures[position]
            if block.get("caption") and position >= len(caption_ids):
                raise ValueError("An image caption was supplied without a corresponding caption slot")
            path = Path(block["path"])
            source_hash = hashlib.sha256(path.read_bytes()).hexdigest()
            raster = raster_bytes(path)
            if hashlib.sha256(path.read_bytes()).hexdigest() != source_hash:
                raise ValueError(f"Research image changed while rendering: {path}")
            media_part = f"ppt/media/lab_report_{index}_{position + 1}.png"
            while media_part in output_parts:
                media_part = media_part[:-4] + "_new.png"
            output_parts[media_part] = raster
            rid = f"rIdLabReport{position + 1}"
            while rid in used_ids:
                rid += "N"
            used_ids.add(rid)
            ET.SubElement(rels, f"{{{REL}}}Relationship", Id=rid, Type=NS["r"] + "/image",
                          Target=posixpath.relpath(media_part, posixpath.dirname(new_part)))
            fill = shape.find("p:blipFill", NS)
            blip = fill.find("a:blip", NS)
            blip.attrib.pop(f"{{{NS['r']}}}link", None)
            blip.set(f"{{{NS['r']}}}embed", rid)
            for child in list(fill):
                if ET.QName(child).localname in {"srcRect", "tile", "stretch"}:
                    fill.remove(child)
            ET.SubElement(ET.SubElement(fill, f"{{{NS['a']}}}stretch"), f"{{{NS['a']}}}fillRect")
            box = bounds(shape)
            if box is None or min(box[2:]) <= 0:
                raise ValueError("Picture slot must have an explicit positive bounding box")
            with Image.open(io.BytesIO(raster)) as image:
                scale = min(box[2] / image.width, box[3] / image.height)
                width, height = round(image.width * scale), round(image.height * scale)
            transform = shape.find("p:spPr/a:xfrm", NS)
            off, ext = transform.find("a:off", NS), transform.find("a:ext", NS)
            off.set("x", str(box[0] + (box[2] - width) // 2))
            off.set("y", str(box[1] + (box[3] - height) // 2))
            ext.set("cx", str(width))
            ext.set("cy", str(height))
            if position < len(caption_ids):
                replace_text(shapes[caption_ids[position]], str(block.get("caption") or ""))
            assets.append({"slide": index, "path": str(path), "sha256": source_hash,
                           "embedded_sha256": hashlib.sha256(raster).hexdigest(),
                           "caption": block.get("caption", ""), "role": block.get("role", "unverified"),
                           "source": block.get("source", ""), "period": block.get("period", "unknown")})
        output_parts[new_part] = dump(root)
        output_parts[relpath(new_part)] = dump(rels)
        new_relations.append(new_part)
    for child in list(presentation):
        if ET.QName(child).localname in {"sldIdLst", "notesMasterIdLst", "handoutMasterIdLst", "custShowLst", "extLst"}:
            presentation.remove(child)
    slide_list = ET.Element(f"{{{NS['p']}}}sldIdLst")
    # OOXML ordering: master lists, slide list, slide size, notes size.
    insertion = next((i for i, c in enumerate(presentation) if ET.QName(c).localname not in {"sldMasterIdLst"}), len(presentation))
    presentation.insert(insertion, slide_list)
    pres_rels = relationships(parts, "ppt/presentation.xml")
    for relation in list(pres_rels):
        if relation.get("Type", "").rsplit("/", 1)[-1] != "slideMaster":
            pres_rels.remove(relation)
    existing = {r.get("Id") for r in pres_rels}
    for index, part in enumerate(new_relations, 1):
        rid = f"rIdReportSlide{index}"
        while rid in existing:
            rid += "N"
        existing.add(rid)
        ET.SubElement(pres_rels, f"{{{REL}}}Relationship", Id=rid, Type=NS["r"] + "/slide", Target=posixpath.relpath(part, "ppt"))
        ET.SubElement(slide_list, f"{{{NS['p']}}}sldId", id=str(255 + index), attrib={f"{{{NS['r']}}}id": rid})
    output_parts["ppt/presentation.xml"] = dump(presentation)
    output_parts[relpath("ppt/presentation.xml")] = dump(pres_rels)
    final_parts = prune(output_parts)
    if hashlib.sha256(source.read_bytes()).digest() != hashlib.sha256(original).digest():
        raise ValueError("Template changed while rendering")
    buffer = io.BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        for name, data in final_parts.items():
            archive.writestr(name, data)
    with output_path.open("xb") as destination:
        destination.write(buffer.getvalue())
    return assets


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    inspect = sub.add_parser("inspect")
    inspect.add_argument("--template", required=True)
    inspect.add_argument("--out", required=True)
    args = parser.parse_args()
    report = inspect_template(Path(args.template))
    with Path(args.out).open("x", encoding="utf-8") as destination:
        json.dump(report, destination, ensure_ascii=False, indent=2)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
