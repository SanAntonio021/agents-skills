from __future__ import annotations

import io
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path


OFFICE_DIR = Path(__file__).parents[1] / "scripts" / "office"
sys.path.insert(0, str(OFFICE_DIR))

from validators.pptx import PPTXSchemaValidator  # noqa: E402


PML = "http://schemas.openxmlformats.org/presentationml/2006/main"
DML = "http://schemas.openxmlformats.org/drawingml/2006/main"


def shape(shape_id: int, name: str) -> str:
    return f"""
    <p:sp>
      <p:nvSpPr><p:cNvPr id="{shape_id}" name="{name}"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
      <p:spPr/>
    </p:sp>
    """


def graphic_frame(shape_id: int, name: str, kind: str) -> str:
    return f"""
    <p:graphicFrame>
      <p:nvGraphicFramePr>
        <p:cNvPr id="{shape_id}" name="{name}"/>
        <p:cNvGraphicFramePr/>
        <p:nvPr/>
      </p:nvGraphicFramePr>
      <a:graphic><a:graphicData uri="{DML}/{kind}"/></a:graphic>
    </p:graphicFrame>
    """


def group(shape_id: int, name: str, children: str) -> str:
    return f"""
    <p:grpSp>
      <p:nvGrpSpPr>
        <p:cNvPr id="{shape_id}" name="{name}"/>
        <p:cNvGrpSpPr/>
        <p:nvPr/>
      </p:nvGrpSpPr>
      <p:grpSpPr/>
      {children}
    </p:grpSp>
    """


def slide_xml(children: str) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sld xmlns:p="{PML}" xmlns:a="{DML}">
  <p:cSld>
    <p:spTree>
      <p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>
      <p:grpSpPr/>
      {children}
    </p:spTree>
  </p:cSld>
</p:sld>
"""


class SlideShapeIdValidationTests(unittest.TestCase):
    def _validator(self, root: Path, *slides: str) -> PPTXSchemaValidator:
        slide_dir = root / "ppt" / "slides"
        slide_dir.mkdir(parents=True)
        for index, content in enumerate(slides, start=1):
            (slide_dir / f"slide{index}.xml").write_text(content, encoding="utf-8")
        return PPTXSchemaValidator(root)

    def test_table_collision_is_rejected_with_object_names(self) -> None:
        broken = slide_xml(
            shape(2, "Title")
            + shape(3, "AsOfTag")
            + shape(4, "AsOfTagText")
            + graphic_frame(2, "ConstellationTable", "table")
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            validator = self._validator(Path(temp_dir), broken)
            output = io.StringIO()
            with redirect_stdout(output):
                valid = validator.validate_slide_shape_ids()

        self.assertFalse(valid)
        message = output.getvalue()
        self.assertIn("duplicate p:cNvPr id='2'", message)
        self.assertIn("shape name='Title'", message)
        self.assertIn("table name='ConstellationTable'", message)
        self.assertIn("objectName/name", message)

    def test_table_id_five_fixes_the_regression(self) -> None:
        fixed = slide_xml(
            shape(2, "Title")
            + shape(3, "AsOfTag")
            + shape(4, "AsOfTagText")
            + graphic_frame(5, "ConstellationTable", "table")
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            validator = self._validator(Path(temp_dir), fixed)
            self.assertTrue(validator.validate_slide_shape_ids())

    def test_same_id_on_different_slides_is_allowed(self) -> None:
        first = slide_xml(shape(2, "Title"))
        second = slide_xml(shape(2, "Title"))
        with tempfile.TemporaryDirectory() as temp_dir:
            validator = self._validator(Path(temp_dir), first, second)
            self.assertTrue(validator.validate_slide_shape_ids())

    def test_same_object_name_with_different_ids_is_allowed(self) -> None:
        content = slide_xml(shape(2, "RepeatedName") + shape(3, "RepeatedName"))
        with tempfile.TemporaryDirectory() as temp_dir:
            validator = self._validator(Path(temp_dir), content)
            self.assertTrue(validator.validate_slide_shape_ids())

    def test_chart_and_nested_group_ids_are_checked(self) -> None:
        content = slide_xml(
            group(2, "MetricsGroup", shape(7, "NestedBody"))
            + graphic_frame(7, "RevenueChart", "chart")
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            validator = self._validator(Path(temp_dir), content)
            output = io.StringIO()
            with redirect_stdout(output):
                valid = validator.validate_slide_shape_ids()

        self.assertFalse(valid)
        message = output.getvalue()
        self.assertIn("shape name='NestedBody'", message)
        self.assertIn("chart name='RevenueChart'", message)


if __name__ == "__main__":
    unittest.main()
