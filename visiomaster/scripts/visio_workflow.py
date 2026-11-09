"""Local lifecycle and revision checks around the unchanged Visiomaster renderer."""
from __future__ import annotations

import argparse
import gc
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = ROOT / "vendor" / "upstream"
sys.path.insert(0, str(UPSTREAM / "scripts"))
import scene_to_visio as engine
from scene_validate import validate_scene
from font_utils import font_resolution_for_style, has_cjk_text

VIS_SECTION_CHARACTER = 3
VIS_CHARACTER_FONT = 0
VIS_CHARACTER_ASIAN_FONT = 51
UPSTREAM_UNKNOWN_EFFECTIVE_FIELD = (
    "Scene changes do not hit any known renderer-effective fields; "
    "update the effective-field map before claiming a new round."
)


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_report(path, data):
    if path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def scene_changes(before, after):
    """Compare persistent object IDs; metadata edits are reported separately."""
    changes = {}
    for section in ("nodes", "edges", "assets"):
        left = {item["id"]: item for item in before.get(section, [])}
        right = {item["id"]: item for item in after.get(section, [])}
        for key in sorted(left.keys() | right.keys()):
            if left.get(key) != right.get(key):
                changes[f"{section}:{key}"] = {
                    "before": left.get(key), "after": right.get(key),
                }
    return {
        "objects": changes,
        "page_changed": before.get("page") != after.get("page"),
        "metadata_changed": before.get("metadata") != after.get("metadata"),
        "other_changed": {
            key for key in before.keys() | after.keys()
            if key not in {"nodes", "edges", "assets", "page", "metadata"}
            and before.get(key) != after.get(key)
        },
    }


def only_node_font_size_changes(before, after):
    if set(before) != set(after):
        return []
    if any(key != "nodes" and before.get(key) != after.get(key) for key in before):
        return []
    before_nodes = {item["id"]: item for item in before.get("nodes", [])}
    after_nodes = {item["id"]: item for item in after.get("nodes", [])}
    if before_nodes.keys() != after_nodes.keys():
        return []
    changed = []
    for node_id in sorted(before_nodes):
        left = before_nodes[node_id]
        right = after_nodes[node_id]
        if left == right:
            continue
        if {key: value for key, value in left.items() if key != "style"} != {
            key: value for key, value in right.items() if key != "style"
        }:
            return []
        left_style = left.get("style")
        right_style = right.get("style")
        if not isinstance(left_style, dict) or not isinstance(right_style, dict):
            return []
        if {key: value for key, value in left_style.items() if key != "font_size_pt"} != {
            key: value for key, value in right_style.items() if key != "font_size_pt"
        }:
            return []
        left_size = left_style.get("font_size_pt")
        right_size = right_style.get("font_size_pt")
        if left_size is None or right_size is None or left_size == right_size:
            return []
        changed.append(node_id)
    return changed


def pixel_diff_report(before_path, after_path):
    from PIL import Image, ImageChops

    with Image.open(before_path) as source:
        before = source.convert("RGB")
    with Image.open(after_path) as source:
        after = source.convert("RGB")
    if before.size != after.size:
        return {
            "same_pixels": False,
            "size_changed": True,
            "before_size": list(before.size),
            "after_size": list(after.size),
        }
    bbox = ImageChops.difference(before, after).getbbox()
    return {
        "same_pixels": bbox is None,
        "size_changed": False,
        "size": list(before.size),
        "diff_bbox": list(bbox) if bbox else None,
    }


def font_size_noop_fallback(before, after, gate_failures, before_png, after_png):
    if gate_failures != [UPSTREAM_UNKNOWN_EFFECTIVE_FIELD]:
        return None
    changed_ids = only_node_font_size_changes(before, after)
    if not changed_ids:
        return None
    pixels = pixel_diff_report(before_png, after_png)
    if pixels["size_changed"] or pixels["same_pixels"]:
        return None
    return {
        "reason": "Only nested node style.font_size_pt changed; the upstream field classifier did not recognize it.",
        "changed_ids": changed_ids,
        "pixel_diff": pixels,
    }


def check_scene(path):
    scene = read_json(path)
    errors, warnings = validate_scene(scene)
    for warning in warnings:
        print("WARNING:", warning)
    if errors:
        raise ValueError("; ".join(errors))
    normalized = engine.normalize_scene_coordinates(scene)
    cmap = engine.load_component_map()
    _, profile = engine.resolve_profile(normalized, engine.load_style_profiles(), None)
    profile["global_text"] = {
        **profile.get("global_text", {}),
        "font_family": "SimSun",
        "font_family_candidates": ["SimSun", "Microsoft YaHei"],
        "font_role": "cjk_serif",
        "font_size_pt": 18,
        "font_weight": "regular",
        "text_fit": "none",
    }
    for node in normalized.get("nodes", []):
        text = str(node.get("text", ""))
        if not text:
            continue
        _, style, _ = engine.node_style(node, cmap, profile)
        font = font_resolution_for_style(style, text)
        if not font.available or font.used_fallback:
            raise ValueError(f"Font unavailable or substituted for {node['id']}: {font}")
    # These audits write no files unless explicitly passed a report path.
    for script in ("text_render_audit.py", "raster_policy_audit.py"):
        result = subprocess.run([sys.executable, str(UPSTREAM / "scripts" / script),
                                 str(Path(path).resolve()), "--strict"],
                                capture_output=True, text=True, encoding="utf-8")
        if result.returncode:
            raise ValueError(result.stdout + result.stderr)
    return scene, normalized, cmap, profile


def descendants(shape):
    yield shape
    for index in range(1, shape.Shapes.Count + 1):
        yield from descendants(shape.Shapes.Item(index))


def page_shapes(page):
    for index in range(1, page.Shapes.Count + 1):
        yield from descendants(page.Shapes.Item(index))


def fix_cjk_font(shape, style, source_text):
    if shape is None or not has_cjk_text(source_text):
        return
    font = font_resolution_for_style(style, source_text).resolved
    for child in descendants(shape):
        if child.Text:
            # Font and AsianFont are separate cells in Visio's character rows.
            for row in range(child.RowCount(VIS_SECTION_CHARACTER)):
                child.CellsSRC(VIS_SECTION_CHARACTER, row, VIS_CHARACTER_FONT).FormulaU = f'FONT("{font}")'
                child.CellsSRC(VIS_SECTION_CHARACTER, row, VIS_CHARACTER_ASIAN_FONT).FormulaU = f'FONT("{font}")'


def measured_text_extent(shape):
    """Use temporary User-defined ShapeSheet cells and remove them immediately."""
    names = (f"CodexVmh{shape.ID}", f"CodexVmw{shape.ID}")
    formulas = ("TEXTHEIGHT(TheText,TxtWidth)", "TEXTWIDTH(TheText,TxtHeight)")
    values = []
    for name, formula in zip(names, formulas):
        while shape.CellExistsU(f"User.{name}", 0):
            name += "_x"
        shape.AddNamedRow(242, name, 0)
        cell = shape.CellsU(f"User.{name}")
        try:
            cell.FormulaU = formula
            values.append(float(cell.ResultIU))
        finally:
            shape.DeleteRow(242, cell.Row)
    return values


def character_font_rows(shape):
    rows = []
    for row in range(shape.RowCount(VIS_SECTION_CHARACTER)):
        rows.append({
            "row": row,
            "font": shape.CellsSRC(VIS_SECTION_CHARACTER, row, VIS_CHARACTER_FONT).FormulaU,
            "asian_font": shape.CellsSRC(VIS_SECTION_CHARACTER, row, VIS_CHARACTER_ASIAN_FONT).FormulaU,
        })
    return rows


def render(args):
    scene_path = Path(args.scene).resolve()
    raw, scene, cmap, profile = check_scene(scene_path)
    pending = raw.get("metadata", {}).get("pending_questions", [])
    if pending and not args.draft:
        raise ValueError("Unresolved pending_questions: use --draft for a clearly marked draft.")
    basename = args.basename or scene_path.name.removesuffix(".scene.json").removesuffix(".json")
    if not basename or Path(basename).name != basename or any(c in basename for c in '/\\:'):
        raise ValueError("basename must be a filename without directories")
    out = Path(args.output_dir).resolve()
    outputs = {ext: out / f"{basename}.{ext}" for ext in ("vsdx", "svg", "png")}
    collisions = [str(p) for p in outputs.values() if p.exists()]
    if collisions:
        raise FileExistsError("Choose a new version; existing outputs: " + ", ".join(collisions))
    out.mkdir(parents=True, exist_ok=True)
    import pythoncom
    import win32com.client
    pythoncom.CoInitialize()
    app = doc = stencil = page = shape = candidate = None
    masters = {}
    created = []
    report = {"status": "failed", "draft": bool(args.draft), "scene": str(scene_path),
              "scene_sha256": sha256(scene_path), "upstream_commit":
              "0d8ccf2c015dc99935a71d2618fe0399e00a0d10", "shapes": []}
    try:
        # DispatchEx creates a dedicated instance; never Quit a user's application.
        app = win32com.client.DispatchEx("Visio.Application")
        app.Visible = False
        app.AlertResponse = 7
        stencil = engine.open_basic_flow_stencil(app)
        masters = {name: engine.get_master(stencil, variants) for name, variants in {
            "Process": ["Process", "流程"], "Decision": ["Decision", "判定"],
            "Start/End": ["Start/End", "开始/结束"],
        }.items()}
        doc = app.Documents.Add("")
        page = doc.Pages.Item(1)
        height = float(scene["page"]["height"])
        page.PageSheet.CellsU("PageWidth").FormulaU = f'{scene["page"]["width"]} in'
        page.PageSheet.CellsU("PageHeight").FormulaU = f"{height} in"
        nodes = {n["id"]: n for n in scene.get("nodes", [])}
        assets = {}
        for asset in scene.get("assets", []):
            if asset.get("path"):
                asset_path = Path(asset["path"])
                assets[asset["id"]] = (scene_path.parent / asset_path).resolve()
        for entry in engine.render_queue_entries(scene):
            item = entry["item"]
            existing_ids = {shape.ID for shape in page_shapes(page)}
            if entry["kind"] == "node":
                shape = engine.draw_node(page, height, item, assets, cmap, profile, masters)
                _, style, _ = engine.node_style(item, cmap, profile)
                fix_cjk_font(shape, style, str(item.get("text", "")))
            elif entry["kind"] == "edge":
                shape = engine.draw_edge(page, height, item, nodes, cmap, profile)[0]
            else:
                points = engine.edge_route_points(item, engine.edge_style(item, cmap, profile), nodes)
                shape = engine.draw_edge_label_for_edge(page, height, item, points, profile)
                fix_cjk_font(shape, profile.get("global_text", {}), str(item.get("label", "")))
            created = [candidate for candidate in page_shapes(page) if candidate.ID not in existing_ids]
            for segment, candidate in enumerate(created, start=1):
                # Persistent scene IDs are also visible in Visio's shape names.
                candidate.NameU = f"{entry['kind']}__{item['id']}__{segment:02d}"
        for shape in page_shapes(page):
            text = str(shape.Text)
            record = {"id": shape.ID, "name": shape.NameU, "text": text,
                      "font": shape.CellsU("Char.Font").FormulaU,
                      "asian_font": shape.CellsU("Char.AsianFont").FormulaU,
                      "size_pt": round(shape.CellsU("Char.Size").ResultIU * 72, 3)}
            if text:
                record["character_fonts"] = character_font_rows(shape)
                if record["character_fonts"]:
                    record["font"] = record["character_fonts"][0]["font"]
                    record["asian_font"] = record["character_fonts"][0]["asian_font"]
                report["shapes"].append(record)
                # Compare Visio's measured layout with the actual text box dimensions.
                needed_h, needed_w = measured_text_extent(shape)
                available_h = shape.CellsU("TxtHeight").ResultIU
                available_w = shape.CellsU("TxtWidth").ResultIU
                record.update(text_height_in=needed_h, available_height_in=available_h,
                              text_width_in=needed_w, available_width_in=available_w)
                if needed_h > available_h + 0.03 or needed_w > available_w + 0.03:
                    raise ValueError(f"Rendered text exceeds its box: {shape.NameU}")
                if has_cjk_text(text):
                    bad_rows = [row for row in record["character_fonts"]
                                if "SIMSUN" not in row["font"].upper()
                                or "SIMSUN" not in row["asian_font"].upper()]
                    if not record["character_fonts"] or bad_rows:
                        raise ValueError(
                            f"Chinese font was not applied to both Visio font fields: "
                            f"{shape.NameU}; rows={record['character_fonts']}"
                        )
            else:
                report["shapes"].append(record)
        doc.SaveAs(str(outputs["vsdx"]))
        for ext in ("svg", "png"):
            page.Export(str(outputs[ext]))
        if any(not p.is_file() or p.stat().st_size == 0 for p in outputs.values()):
            raise RuntimeError("One or more Visio exports are missing or empty")
        from PIL import Image
        with Image.open(outputs["png"]) as image:
            image.verify()
        report["outputs"] = {ext: {"path": str(p), "sha256": sha256(p)} for ext, p in outputs.items()}
        report["status"] = "rendered_pending_visual_review"
        print("Rendered:", outputs["vsdx"])
        print("Visual review required:", outputs["png"])
    except Exception as exc:
        report["error"] = str(exc)
        raise
    finally:
        # Only the private document/instance created above is closed.
        cleanup_errors = []
        if doc is not None:
            try:
                doc.Saved = True
                doc.Close()
            except Exception as exc:
                cleanup_errors.append(f"document close: {exc}")
        if stencil is not None:
            try:
                stencil.Close()
            except Exception as exc:
                cleanup_errors.append(f"stencil close: {exc}")
        masters.clear()
        created.clear()
        candidate = shape = page = doc = stencil = None
        if app is not None:
            try:
                app.Quit()
            except Exception as exc:
                cleanup_errors.append(f"Visio quit: {exc}")
        app = None
        gc.collect()
        pythoncom.CoUninitialize()
        if cleanup_errors:
            report["cleanup_errors"] = cleanup_errors
            if report["status"] != "failed":
                report["status"] = "cleanup_failed"
        write_report(args.report, report)


def compare(args):
    before_scene = read_json(args.before_scene)
    after_scene = read_json(args.after_scene)
    changes = scene_changes(before_scene, after_scene)
    allowed = set(args.allow_id or [])
    unexpected = [key for key in changes["objects"] if key.split(":", 1)[1] not in allowed]
    if changes["page_changed"] and not args.allow_page:
        unexpected.append("page")
    unexpected.extend(sorted(changes["other_changed"]))
    changes["other_changed"] = sorted(changes["other_changed"])
    report = {"status": "failed", "changes": changes, "unexpected": unexpected}
    try:
        if unexpected:
            raise ValueError("Changes outside requested objects: " + ", ".join(unexpected))
        result = subprocess.run([
            sys.executable, str(UPSTREAM / "scripts" / "round_noop_gate.py"),
            "--before-scene", args.before_scene, "--after-scene", args.after_scene,
            "--before-png", args.before_png, "--after-png", args.after_png,
        ], capture_output=True, text=True, encoding="utf-8")
        report["noop_gate"] = result.stdout + result.stderr
        if result.returncode:
            gate_failures = [line[2:].strip() for line in result.stdout.splitlines() if line.startswith("- ")]
            fallback = font_size_noop_fallback(
                before_scene, after_scene, gate_failures, args.before_png, args.after_png
            )
            if fallback is None:
                raise ValueError(report["noop_gate"])
            report["font_size_fallback"] = fallback
            report["noop_gate_status"] = "passed_by_local_pixel_checked_font_size_fallback"
            print("Local font-size fallback passed with a nonzero pixel diff:", fallback["pixel_diff"])
        else:
            report["noop_gate_status"] = "passed_upstream"
        report["status"] = "passed"
        print("Changed objects:", ", ".join(changes["objects"]))
        if result.returncode == 0:
            print(report["noop_gate"])
    finally:
        write_report(args.report, report)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("check")
    check.add_argument("scene")
    draw = commands.add_parser("render")
    draw.add_argument("scene")
    draw.add_argument("--output-dir", required=True)
    draw.add_argument("--basename")
    draw.add_argument("--report")
    draw.add_argument("--draft", action="store_true")
    diff = commands.add_parser("compare")
    for name in ("before-scene", "after-scene", "before-png", "after-png"):
        diff.add_argument("--" + name, required=True)
    diff.add_argument("--allow-id", action="append", help="Repeat for each requested node/edge/asset ID")
    diff.add_argument("--allow-page", action="store_true")
    diff.add_argument("--report")
    args = parser.parse_args()
    try:
        if args.command == "check":
            check_scene(args.scene)
            print("Scene and fonts passed preflight")
        elif args.command == "render":
            render(args)
        else:
            compare(args)
        return 0
    except Exception as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
