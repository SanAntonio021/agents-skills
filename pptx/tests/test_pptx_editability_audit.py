import contextlib
import importlib.util
import io
import tempfile
import unittest
import zipfile
from pathlib import Path


MODULE = Path(__file__).parents[1] / "scripts" / "pptx_editability_audit.py"
spec = importlib.util.spec_from_file_location("pptx_editability_audit", MODULE)
audit = importlib.util.module_from_spec(spec)
assert spec is not None and spec.loader is not None
spec.loader.exec_module(audit)


P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
WIDTH = 12192000
HEIGHT = 6858000


def text_shape(shape_id: int, name: str, text: str, *, anchor: str, alignment: str) -> str:
    return f"""
    <p:sp>
      <p:nvSpPr><p:cNvPr id="{shape_id}" name="{name}"/></p:nvSpPr>
      <p:txBody>
        <a:bodyPr anchor="{anchor}"/><a:lstStyle/>
        <a:p><a:pPr algn="{alignment}"/><a:r><a:t>{text}</a:t></a:r></a:p>
      </p:txBody>
    </p:sp>
    """


def picture(shape_id: int, *, full_slide: bool) -> str:
    x, y = (0, 0) if full_slide else (100, 200)
    cx, cy = (WIDTH, HEIGHT) if full_slide else (1000, 800)
    return f"""
    <p:pic>
      <p:nvPicPr><p:cNvPr id="{shape_id}" name="Picture {shape_id}"/></p:nvPicPr>
      <p:spPr><a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm></p:spPr>
    </p:pic>
    """


def write_presentation(path: Path, slide_body: str, *, media: tuple[str, ...] = ()) -> None:
    presentation = (
        f'<p:presentation xmlns:p="{P_NS}" xmlns:r="{R_NS}">'
        '<p:sldIdLst><p:sldId id="256" r:id="rId1"/></p:sldIdLst>'
        f'<p:sldSz cx="{WIDTH}" cy="{HEIGHT}"/></p:presentation>'
    )
    relationships = (
        f'<Relationships xmlns="{REL_NS}">'
        '<Relationship Id="rId1" Type="slide" Target="slides/slide1.xml"/>'
        '</Relationships>'
    )
    slide = (
        f'<p:sld xmlns:p="{P_NS}" xmlns:a="{A_NS}">'
        f'<p:cSld><p:spTree>{slide_body}</p:spTree></p:cSld></p:sld>'
    )
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as package:
        package.writestr("ppt/presentation.xml", presentation)
        package.writestr("ppt/_rels/presentation.xml.rels", relationships)
        package.writestr("ppt/slides/slide1.xml", slide)
        for name in media:
            package.writestr(f"ppt/media/{name}", b"media")


class EditabilityAuditTests(unittest.TestCase):
    def test_reports_native_objects_and_centered_top_review(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "native.pptx"
            group = """
            <p:grpSp>
              <p:nvGrpSpPr><p:cNvPr id="4" name="Group 4"/></p:nvGrpSpPr>
              <p:sp><p:nvSpPr><p:cNvPr id="5" name="Native Shape"/></p:nvSpPr></p:sp>
            </p:grpSp>
            """
            body = (
                text_shape(2, "Centered title", "需要复核居中", anchor="t", alignment="ctr")
                + text_shape(3, "Left body", "普通正文", anchor="ctr", alignment="l")
                + group
                + picture(6, full_slide=False)
            )
            write_presentation(source, body, media=("photo.png",))
            result = audit.audit_presentation(source)

            self.assertEqual(result["status"], "WARN")
            self.assertEqual(result["slide_count"], 1)
            self.assertEqual(result["totals"]["native_shapes"], 3)
            self.assertEqual(result["totals"]["text_shapes"], 2)
            self.assertEqual(result["totals"]["groups"], 1)
            self.assertEqual(result["totals"]["pictures"], 1)
            self.assertEqual(result["media"]["svg_count"], 0)
            self.assertEqual(result["text_alignment"]["vertical_anchor"], {"ctr": 1, "t": 1})
            self.assertEqual(result["text_alignment"]["first_paragraph_horizontal"], {"ctr": 1, "l": 1})
            review = result["text_alignment"]["centered_top_review"]
            self.assertEqual(len(review), 1)
            self.assertEqual(review[0]["shape_id"], "2")
            self.assertEqual(review[0]["shape_name"], "Centered title")
            self.assertEqual(review[0]["text"], "需要复核居中")
            self.assertEqual(result["likely_flattened_slides"], [])

    def test_reports_svg_media_in_final_package(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "svg-media.pptx"
            write_presentation(
                source,
                text_shape(2, "Body", "正文", anchor="ctr", alignment="l"),
                media=("icon.svg", "photo.png"),
            )
            result = audit.audit_presentation(source)
            self.assertEqual(result["status"], "PASS")
            self.assertEqual(result["media"]["svg_count"], 1)
            self.assertEqual(result["media"]["extensions"], {".png": 1, ".svg": 1})

    def test_detects_likely_flattened_full_slide_picture_and_strict_failure(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "flattened.pptx"
            write_presentation(source, picture(2, full_slide=True), media=("slide.png",))

            warning = audit.audit_presentation(source)
            self.assertEqual(warning["status"], "WARN")
            self.assertEqual(warning["likely_flattened_slides"], [1])
            self.assertEqual(warning["slides"][0]["exact_full_slide_pictures"], 1)

            strict = audit.audit_presentation(source, fail_on_flattened=True)
            self.assertEqual(strict["status"], "FAIL")
            with contextlib.redirect_stdout(io.StringIO()):
                exit_code = audit.main([str(source), "--fail-on-flattened"])
            self.assertEqual(exit_code, 1)


if __name__ == "__main__":
    unittest.main()
