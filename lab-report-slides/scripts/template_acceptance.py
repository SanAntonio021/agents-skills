"""Prepare title styles and bind template acceptance to the exact tested files."""
from __future__ import annotations

import copy
import hashlib
import io
import json
import math
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

MARKER = "模板适配测试，非科研结果"


class TemplateAdaptationRequired(ValueError):
    def __init__(self, message):
        super().__init__("template_adaptation_required: " + message)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def resolve_path(value, spec_path):
    path = Path(value).expanduser()
    return path.resolve() if path.is_absolute() else (Path(spec_path).resolve().parent / path).resolve()


def spec_digest(spec):
    # The receipt location is metadata, not part of the layout being accepted.
    content = {k: v for k, v in spec.items() if k != "adaptation_receipt"}
    return hashlib.sha256(json.dumps(content, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()


def receipt_path(spec, spec_path):
    return resolve_path(spec["adaptation_receipt"], spec_path) if spec.get("adaptation_receipt") else Path(spec_path).resolve().with_suffix(".adaptation.json")


def template_identity(spec, spec_path):
    if not spec.get("original_template_path") or not spec.get("prepared_template_sha256"):
        raise TemplateAdaptationRequired("Template is not prepared; run template_deck.py prepare before the adaptation test")
    original = resolve_path(spec["original_template_path"], spec_path)
    adapted = resolve_path(spec["template_path"], spec_path)
    if original == adapted:
        raise ValueError("Adapted template must be a separate copy of the original")
    identity = {"original_sha256": digest(original), "template_sha256": digest(adapted), "spec_sha256": spec_digest(spec)}
    if identity["original_sha256"] != spec.get("original_template_sha256") or identity["template_sha256"] != spec.get("prepared_template_sha256"):
        raise TemplateAdaptationRequired("Template changed after preparation; prepare a new copy and repeat the adaptation test")
    return identity


def require_acceptance(spec, spec_path):
    identity = template_identity(spec, spec_path)
    path = receipt_path(spec, spec_path)
    if not path.is_file():
        raise TemplateAdaptationRequired(f"Template adaptation acceptance missing: {path}; generate and inspect a --template-test sample first")
    receipt = json.loads(path.read_text(encoding="utf-8-sig"))
    if receipt.get("schema_version") != 1 or receipt.get("identity") != identity:
        raise TemplateAdaptationRequired("Template adaptation acceptance is stale; repeat the adaptation test")
    if any(receipt.get("checks", {}).get(key) != "passed" for key in ("structure", "libreoffice", "png", "visual")):
        raise ValueError("Template adaptation acceptance has incomplete checks")
    if set(receipt.get("layouts", [])) != set(spec.get("layouts", {})):
        raise ValueError("Template adaptation acceptance does not cover every configured layout")
    for filename, expected in receipt.get("sample_hashes", {}).items():
        if digest(filename) != expected:
            raise ValueError(f"Template adaptation evidence changed: {filename}")
    if not receipt.get("sample_hashes"):
        raise ValueError("Template adaptation acceptance has no sample evidence")
    return receipt


def _size(node, paths, ns):
    if node is None:
        return None
    for path in paths:
        found = node.find(path, ns)
        if found is not None and found.get("sz") is not None:
            value = int(found.get("sz"))
            if not 100 <= value <= 400000:
                raise ValueError(f"Invalid inherited title font size: {value}")
            return value
    return None


def effective_title_size(parts, slide_part, shape):
    from template_deck import NS, relationships, target, xml

    paragraph = shape.find("p:txBody/a:p", NS)
    level = int(paragraph.find("a:pPr", NS).get("lvl", "0")) if paragraph is not None and paragraph.find("a:pPr", NS) is not None else 0
    if not 0 <= level <= 8:
        raise ValueError("Invalid title paragraph level")
    local_paths = ["p:txBody/a:p/a:r/a:rPr", "p:txBody/a:p/a:pPr/a:defRPr",
                   f"p:txBody/a:lstStyle/a:lvl{level + 1}pPr/a:defRPr", "p:txBody/a:lstStyle/a:defPPr/a:defRPr"]
    value = _size(shape, local_paths, NS)
    if value is not None:
        return value
    ph = shape.find("p:nvSpPr/p:nvPr/p:ph", NS)
    ph_type = ph.get("type", "obj") if ph is not None else None

    def linked(part, kind):
        for relation in relationships(parts, part):
            if relation.get("Type", "").endswith("/" + kind):
                if relation.get("TargetMode") == "External":
                    raise ValueError("External template inheritance is unsupported")
                resolved = target(part, relation)
                return resolved, xml(parts[resolved])
        return None, None

    layout_part, layout = linked(slide_part, "slideLayout")
    master_part, master = linked(layout_part, "slideMaster") if layout_part else (None, None)
    if ph is not None:
        for ancestor, mode in ((layout, "idx"), (master, "type")):
            if ancestor is None:
                continue
            matches = []
            for candidate in ancestor.findall("p:cSld/p:spTree/p:sp", NS):
                candidate_ph = candidate.find("p:nvSpPr/p:nvPr/p:ph", NS)
                if candidate_ph is None:
                    continue
                if mode == "idx":
                    same = candidate_ph.get("idx", "0") == ph.get("idx", "0")
                else:
                    candidate_type = candidate_ph.get("type", "obj")
                    same = candidate_type == ph_type or ph_type in {"title", "ctrTitle"} and candidate_type == "title"
                if same:
                    matches.append(candidate)
            if len(matches) > 1:
                raise ValueError("Ambiguous title placeholder inheritance; specify the actual title size")
            if matches:
                value = _size(matches[0], local_paths, NS)
                if value is not None:
                    return value
                if mode == "idx":
                    ph_type = matches[0].find("p:nvSpPr/p:nvPr/p:ph", NS).get("type", "obj")
    style = "titleStyle" if ph_type in {"title", "ctrTitle"} else "bodyStyle" if ph_type in {"body", "obj", "subTitle"} else "otherStyle"
    value = _size(master, [f"p:txStyles/p:{style}/a:lvl{level + 1}pPr/a:defRPr", f"p:txStyles/p:{style}/a:defPPr/a:defRPr"], NS)
    if value is not None:
        return value
    return _size(xml(parts["ppt/presentation.xml"]),
                 [f"p:defaultTextStyle/a:lvl{level + 1}pPr/a:defRPr", "p:defaultTextStyle/a:defPPr/a:defRPr"], NS)


def prepare_template(spec_path, output_template, output_spec, title_size_pt=None):
    from template_deck import NS, dump, shape_id, slide_parts, xml
    from lxml import etree as ET

    spec_path, output_template, output_spec = map(lambda p: Path(p).resolve(), (spec_path, output_template, output_spec))
    if output_template.exists() or output_spec.exists() or output_template == output_spec:
        raise FileExistsError("Preparation requires new, distinct template and mapping paths")
    spec = json.loads(spec_path.read_text(encoding="utf-8-sig"))
    source = resolve_path(spec["template_path"], spec_path)
    original = resolve_path(spec.get("original_template_path", spec["template_path"]), spec_path)
    original_hash = digest(original)
    source_bytes = source.read_bytes()
    with ZipFile(io.BytesIO(source_bytes)) as archive:
        parts = {name: archive.read(name) for name in archive.namelist()}
    _, ordered = slide_parts(parts)
    if title_size_pt is not None and (not math.isfinite(title_size_pt) or not 1 <= title_size_pt <= 4000):
        raise ValueError("Actual title size must be between 1 and 4000 pt")
    resolved_titles = []
    for name, mapping in spec.get("layouts", {}).items():
        page = mapping.get("slide")
        if not isinstance(page, int) or isinstance(page, bool) or not 1 <= page <= len(ordered):
            raise ValueError(f"Invalid template slide for layout {name}: {page}")
        sid = mapping.get("slots", {}).get("title")
        if sid is None:
            continue
        part = ordered[page - 1]
        root = xml(parts[part])
        shape = next((s for s in root.find("p:cSld/p:spTree", NS) if shape_id(s) == sid), None)
        if shape is None or shape.find("p:txBody/a:p", NS) is None:
            raise ValueError(f"Title shape is missing or not native text: slide={page}, shape_id={sid}, layout={name}")
        size_source = "template_inheritance"
        try:
            value = effective_title_size(parts, part, shape)
        except ValueError as exc:
            if not str(exc).startswith("Ambiguous title placeholder inheritance") or title_size_pt is None:
                raise ValueError(f"slide={page}, shape_id={sid}, layout={name}: {exc}") from exc
            value = None
        if value is None and title_size_pt is not None:
            value = round(title_size_pt * 100)
            size_source = "user_actual_size"
        if value is None:
            raise ValueError(f"Cannot determine title font size: slide={page}, shape_id={sid}, layout={name}; retry prepare with the user's actual --title-size-pt")
        paragraph = shape.find("p:txBody/a:p", NS)
        run = paragraph.find("a:r", NS)
        if run is None:
            run = ET.SubElement(paragraph, f"{{{NS['a']}}}r")
            ET.SubElement(run, f"{{{NS['a']}}}t").text = ""
        props = run.find("a:rPr", NS)
        if props is None:
            props = ET.Element(f"{{{NS['a']}}}rPr")
            run.insert(0, props)
        props.set("sz", str(value))
        parts[part] = dump(root)
        resolved_titles.append({"layout": name, "slide": page, "shape_id": sid, "size_pt": value / 100, "source": size_source})
    if digest(original) != original_hash or source.read_bytes() != source_bytes:
        raise ValueError("Template changed during preparation")
    buffer = io.BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        for name, data in parts.items():
            archive.writestr(name, data)
    prepared = buffer.getvalue()
    new_spec = copy.deepcopy(spec)
    new_spec.pop("adaptation_receipt", None)
    new_spec.update(template_path=str(output_template), original_template_path=str(original),
                    original_template_sha256=original_hash, prepared_template_sha256=hashlib.sha256(prepared).hexdigest())
    # New outputs only; the original and any prior prepared copy are never edited.
    try:
        with output_template.open("xb") as destination:
            destination.write(prepared)
        with output_spec.open("x", encoding="utf-8") as destination:
            json.dump(new_spec, destination, ensure_ascii=False, indent=2)
    except OSError as exc:
        raise OSError(f"Template preparation write failed; original unchanged. Inspect incomplete new outputs before retry: template={output_template}, mapping={output_spec}; {exc}") from exc
    return {"template_path": str(output_template), "spec_path": str(output_spec), "titles": resolved_titles,
            "original_sha256": original_hash, "template_sha256": new_spec["prepared_template_sha256"]}


def add_test_marker(tree, width, height, layout, *, minimum_id=1):
    from template_deck import NS, shape_id
    from lxml import etree as ET
    sid = max(minimum_id, max((shape_id(s) or 0 for s in tree), default=0) + 1)
    shape = ET.SubElement(tree, f"{{{NS['p']}}}sp")
    nv = ET.SubElement(shape, f"{{{NS['p']}}}nvSpPr")
    ET.SubElement(nv, f"{{{NS['p']}}}cNvPr", id=str(sid), name="Template adaptation test " + layout)
    ET.SubElement(nv, f"{{{NS['p']}}}cNvSpPr", txBox="1")
    ET.SubElement(nv, f"{{{NS['p']}}}nvPr")
    props = ET.SubElement(shape, f"{{{NS['p']}}}spPr")
    transform = ET.SubElement(props, f"{{{NS['a']}}}xfrm")
    band = min(365760, height // 12)
    ET.SubElement(transform, f"{{{NS['a']}}}off", x="0", y=str(height - band))
    ET.SubElement(transform, f"{{{NS['a']}}}ext", cx=str(width), cy=str(band))
    geom = ET.SubElement(props, f"{{{NS['a']}}}prstGeom", prst="rect")
    ET.SubElement(geom, f"{{{NS['a']}}}avLst")
    ET.SubElement(ET.SubElement(props, f"{{{NS['a']}}}solidFill"), f"{{{NS['a']}}}srgbClr", val="FFFFFF")
    body = ET.SubElement(shape, f"{{{NS['p']}}}txBody")
    ET.SubElement(body, f"{{{NS['a']}}}bodyPr", anchor="ctr")
    ET.SubElement(body, f"{{{NS['a']}}}lstStyle")
    paragraph = ET.SubElement(body, f"{{{NS['a']}}}p")
    ET.SubElement(paragraph, f"{{{NS['a']}}}pPr", algn="ctr")
    run = ET.SubElement(paragraph, f"{{{NS['a']}}}r")
    rpr = ET.SubElement(run, f"{{{NS['a']}}}rPr", sz="1200", b="1")
    ET.SubElement(ET.SubElement(rpr, f"{{{NS['a']}}}solidFill"), f"{{{NS['a']}}}srgbClr", val="B91C1C")
    ET.SubElement(run, f"{{{NS['a']}}}t").text = MARKER


def record_acceptance(spec_path, manifest_path, out=None, *, visual_inspected=False):
    from template_deck import inspect_template

    if not visual_inspected:
        raise ValueError("Every rendered sample page must be visually inspected before acceptance")
    spec_path, manifest_path = Path(spec_path).resolve(), Path(manifest_path).resolve()
    spec = json.loads(spec_path.read_text(encoding="utf-8-sig"))
    identity = template_identity(spec, spec_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    if manifest.get("schema_version") != 3 or manifest.get("template_test") is not True:
        raise ValueError("Acceptance requires a version 3 template-test render manifest")
    if any(manifest.get("stages", {}).get(key) != "passed" for key in ("pptx", "structure", "libreoffice", "png")):
        raise ValueError("Template test structure and actual PDF/PNG rendering must pass before acceptance")
    template = manifest.get("template") or {}
    if template.get("sha256") != identity["template_sha256"] or template.get("spec_sha256") != digest(spec_path):
        raise ValueError("Render manifest does not belong to the current template and mapping")
    files = manifest.get("files", {})
    sample = Path(files["pptx"])
    pngs = files.get("png", [])
    report = inspect_template(sample)
    if not pngs or len(pngs) != report["slide_count"] or report["slide_count"] != manifest.get("slide_count"):
        raise ValueError("Every sample page requires an actual rendered PNG")
    layouts = set()
    for slide in report["slides"]:
        markers = [s for s in slide["shapes"] if s["name"].startswith("Template adaptation test ") and s["text"] == MARKER]
        if len(markers) != 1:
            raise ValueError("Every sample page must carry the adaptation-test marker")
        layouts.add(markers[0]["name"][len("Template adaptation test "):])
    if layouts != set(spec.get("layouts", {})):
        raise ValueError("The adaptation sample must exercise every configured layout")
    evidence = {}
    for filename in [str(sample), files["pdf"], *pngs]:
        path = Path(filename).resolve()
        actual = digest(path)
        expected = manifest.get("file_hashes", {}).get(str(path))
        if path == sample.resolve() and expected is None:
            expected = manifest.get("pptx_sha256")
        if expected != actual:
            raise ValueError(f"Rendered sample evidence hash mismatch: {path}")
        evidence[str(path)] = actual
    if digest(sample) != manifest.get("pptx_sha256"):
        raise ValueError("Sample PPTX changed after rendering")
    evidence[str(manifest_path)] = digest(manifest_path)
    receipt = {"schema_version": 1, "identity": identity, "layouts": sorted(layouts), "sample_hashes": evidence,
               "checks": {"structure": "passed", "libreoffice": "passed", "png": "passed", "visual": "passed"},
               "powerpoint": manifest.get("stages", {}).get("powerpoint", "not_run")}
    expected_out = receipt_path(spec, spec_path)
    if out is not None and Path(out).resolve() != expected_out:
        raise ValueError(f"Receipt must use the mapping's configured/default path: {expected_out}")
    with expected_out.open("x", encoding="utf-8") as destination:
        json.dump(receipt, destination, ensure_ascii=False, indent=2)
    return {"receipt": str(expected_out), **receipt}
