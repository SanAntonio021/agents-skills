from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("visiomaster_workflow", ROOT / "scripts" / "visio_workflow.py")
workflow = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(workflow)


def test_templates_pass_scene_and_font_preflight() -> None:
    for path in (ROOT / "templates").glob("*.scene.json"):
        workflow.check_scene(path)


def test_scene_diff_tracks_named_objects_and_page() -> None:
    before = {"nodes": [{"id": "module", "text": "M"}], "edges": [{"id": "edge", "from": "module"}], "page": {}}
    after = {"nodes": [{"id": "module", "text": "Module"}], "edges": [{"id": "edge", "from": "module"}], "page": {"width": 10}}
    changes = workflow.scene_changes(before, after)
    assert set(changes["objects"]) == {"nodes:module"}
    assert changes["page_changed"]


def test_scene_diff_reports_added_and_removed_ids() -> None:
    before = {"nodes": [{"id": "old", "text": "A"}], "edges": []}
    after = {"nodes": [{"id": "new", "text": "B"}], "edges": []}
    changes = workflow.scene_changes(before, after)
    assert set(changes["objects"]) == {"nodes:new", "nodes:old"}


def test_pending_questions_are_read_from_scene_metadata() -> None:
    template = json.loads((ROOT / "templates" / "system-architecture.scene.json").read_text(encoding="utf-8"))
    template["metadata"]["pending_questions"] = ["Which direction is confirmed?"]
    assert template["metadata"]["pending_questions"]


def test_cjk_font_uses_asian_font_cell_without_touching_underline(monkeypatch) -> None:
    class Cell:
        FormulaU = ""

    class Shape:
        Text = "中文标签"
        Shapes = SimpleNamespace(Count=0)

        def __init__(self) -> None:
            self.cells = {}

        def RowCount(self, section: int) -> int:
            assert section == workflow.VIS_SECTION_CHARACTER
            return 1

        def CellsSRC(self, section: int, row: int, column: int) -> Cell:
            key = (section, row, column)
            return self.cells.setdefault(key, Cell())

    monkeypatch.setattr(
        workflow, "font_resolution_for_style",
        lambda style, text: SimpleNamespace(resolved="SimSun"),
    )
    monkeypatch.setattr(workflow, "has_cjk_text", lambda text: True)
    shape = Shape()

    workflow.fix_cjk_font(shape, {}, shape.Text)

    assert shape.cells[(3, 0, workflow.VIS_CHARACTER_FONT)].FormulaU == 'FONT("SimSun")'
    assert shape.cells[(3, 0, workflow.VIS_CHARACTER_ASIAN_FONT)].FormulaU == 'FONT("SimSun")'
    assert (3, 0, 8) not in shape.cells
    assert workflow.character_font_rows(shape) == [
        {"row": 0, "font": 'FONT("SimSun")', "asian_font": 'FONT("SimSun")'}
    ]


def test_font_size_fallback_requires_only_font_size_and_visible_pixels(tmp_path: Path) -> None:
    before = {
        "version": "0.1",
        "metadata": {},
        "page": {"width": 4, "height": 2},
        "nodes": [{"id": "label", "type": "text_block", "text": "标签", "style": {"font_size_pt": 16, "font_family": "SimSun"}}],
        "edges": [],
        "assets": [],
    }
    after = json.loads(json.dumps(before, ensure_ascii=False))
    after["nodes"][0]["style"]["font_size_pt"] = 18
    before_png = tmp_path / "before.png"
    after_png = tmp_path / "after.png"
    from PIL import Image, ImageDraw

    for path, width in ((before_png, 1), (after_png, 2)):
        image = Image.new("RGB", (8, 8), "white")
        ImageDraw.Draw(image).rectangle((0, 0, width - 1, 1), fill="black")
        image.save(path)

    accepted = workflow.font_size_noop_fallback(
        before,
        after,
        [workflow.UPSTREAM_UNKNOWN_EFFECTIVE_FIELD],
        before_png,
        after_png,
    )
    assert accepted is not None
    assert accepted["changed_ids"] == ["label"]

    after["nodes"][0]["text"] = "其他标签"
    assert workflow.only_node_font_size_changes(before, after) == []

    after["nodes"][0]["text"] = "标签"
    same_image = Image.new("RGB", (8, 8), "white")
    ImageDraw.Draw(same_image).rectangle((0, 0, 0, 1), fill="black")
    same_image.save(after_png)
    assert workflow.font_size_noop_fallback(
        before,
        after,
        [workflow.UPSTREAM_UNKNOWN_EFFECTIVE_FIELD],
        after_png,
        after_png,
    ) is None
