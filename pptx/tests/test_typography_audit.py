import contextlib
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
import zipfile
from html import escape
from pathlib import Path


MODULE = Path(__file__).parents[1] / "scripts" / "typography_audit.py"
spec = importlib.util.spec_from_file_location("pptx_typography_audit", MODULE)
audit = importlib.util.module_from_spec(spec)
assert spec is not None and spec.loader is not None
sys.modules[spec.name] = audit
spec.loader.exec_module(audit)


P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
C_NS = "http://schemas.openxmlformats.org/drawingml/2006/chart"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"


def text_body(text, size=None, autofit="", *, hyperlink=False, hyperlink_id="rId99"):
    size_attr = "" if size is None else f' sz="{size}"'
    hyperlink_xml = f'<a:hlinkClick r:id="{hyperlink_id}"/>' if hyperlink else ""
    return f"""
<a:txBody>
  <a:bodyPr>{autofit}</a:bodyPr>
  <a:lstStyle/>
  <a:p>
    <a:r><a:rPr{size_attr}>{hyperlink_xml}</a:rPr><a:t>{escape(text)}</a:t></a:r>
    <a:endParaRPr{size_attr}/>
  </a:p>
</a:txBody>
"""


def shape_xml(
    shape_id,
    name,
    text,
    size=None,
    autofit="",
    *,
    placeholder=None,
    placeholder_idx=None,
    hyperlink=False,
    hyperlink_id="rId99",
):
    ph_attrs = []
    if placeholder is not None:
        ph_attrs.append(f'type="{placeholder}"')
    if placeholder_idx is not None:
        ph_attrs.append(f'idx="{placeholder_idx}"')
    ph = "" if not ph_attrs else f"<p:ph {' '.join(ph_attrs)}/>"
    return f"""
<p:sp>
  <p:nvSpPr><p:cNvPr id="{shape_id}" name="{escape(name)}"/><p:cNvSpPr/><p:nvPr>{ph}</p:nvPr></p:nvSpPr>
  <p:spPr/>
  {text_body(text, size, autofit, hyperlink=hyperlink, hyperlink_id=hyperlink_id).replace('a:txBody', 'p:txBody')}
</p:sp>
"""


def table_xml(shape_id, name, cells):
    rendered_cells = "".join(
        f"<a:tc>{text_body(text, size).replace('<a:txBody>', '<a:txBody>').replace('</a:txBody>', '</a:txBody>')}<a:tcPr/></a:tc>"
        for text, size in cells
    )
    return f"""
<p:graphicFrame>
  <p:nvGraphicFramePr><p:cNvPr id="{shape_id}" name="{escape(name)}"/><p:cNvGraphicFramePr/><p:nvPr/></p:nvGraphicFramePr>
  <p:xfrm/>
  <a:graphic><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/table">
    <a:tbl><a:tblPr/><a:tblGrid/><a:tr h="1">{rendered_cells}</a:tr></a:tbl>
  </a:graphicData></a:graphic>
</p:graphicFrame>
"""


def chart_frame_xml(shape_id=8, name="Chart"):
    return f"""
<p:graphicFrame>
  <p:nvGraphicFramePr><p:cNvPr id="{shape_id}" name="{name}"/><p:cNvGraphicFramePr/><p:nvPr/></p:nvGraphicFramePr>
  <p:xfrm/>
  <a:graphic><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/chart">
    <c:chart r:id="rId2"/>
  </a:graphicData></a:graphic>
</p:graphicFrame>
"""


def chart_text_body(text=None, size=1800):
    run = "" if text is None else f'<a:r><a:rPr sz="{size}"/><a:t>{escape(text)}</a:t></a:r>'
    return f"""
<a:bodyPr/><a:lstStyle/><a:p><a:pPr><a:defRPr sz="{size}"/></a:pPr>{run}<a:endParaRPr sz="{size}"/></a:p>
"""


def chart_xml(axis_size=1800, title_size=1000, title="Source: https://example.com"):
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<c:chartSpace xmlns:c="{C_NS}" xmlns:a="{A_NS}">
  <c:chart>
    <c:title><c:tx><c:rich>{chart_text_body(title, title_size)}</c:rich></c:tx></c:title>
    <c:plotArea><c:catAx><c:txPr>{chart_text_body(None, axis_size)}</c:txPr></c:catAx></c:plotArea>
  </c:chart>
</c:chartSpace>
"""


def write_package(path, slide_content, *, default_size=1800, chart=None, master_body_size=None):
    default_style = (
        ""
        if default_size is None
        else f'<p:defaultTextStyle><a:lvl1pPr><a:defRPr sz="{default_size}"/></a:lvl1pPr></p:defaultTextStyle>'
    )
    presentation = f"""<?xml version="1.0" encoding="UTF-8"?>
<p:presentation xmlns:p="{P_NS}" xmlns:a="{A_NS}" xmlns:r="{R_NS}">
  <p:sldIdLst><p:sldId id="256" r:id="rId1"/></p:sldIdLst>{default_style}
</p:presentation>
"""
    presentation_rels = f"""<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="{PKG_REL_NS}">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slides/slide1.xml"/>
</Relationships>
"""
    slide = f"""<?xml version="1.0" encoding="UTF-8"?>
<p:sld xmlns:p="{P_NS}" xmlns:a="{A_NS}" xmlns:c="{C_NS}" xmlns:r="{R_NS}">
  <p:cSld><p:spTree>{slide_content}</p:spTree></p:cSld>
</p:sld>
"""
    layout_rel = (
        ""
        if master_body_size is None
        else '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout1.xml"/>'
    )
    slide_rels = f"""<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="{PKG_REL_NS}">
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/chart" Target="../charts/chart1.xml"/>
  <Relationship Id="rId99" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink" Target="https://example.com" TargetMode="External"/>
  {layout_rel}
</Relationships>
"""
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("ppt/presentation.xml", presentation)
        zf.writestr("ppt/_rels/presentation.xml.rels", presentation_rels)
        zf.writestr("ppt/slides/slide1.xml", slide)
        zf.writestr("ppt/slides/_rels/slide1.xml.rels", slide_rels)
        if chart is not None:
            zf.writestr("ppt/charts/chart1.xml", chart)
        if master_body_size is not None:
            layout = f"""<p:sldLayout xmlns:p="{P_NS}" xmlns:a="{A_NS}"><p:cSld><p:spTree>
<p:sp><p:nvSpPr><p:cNvPr id="2" name="Body Placeholder"/><p:cNvSpPr/><p:nvPr><p:ph type="body" idx="1"/></p:nvPr></p:nvSpPr><p:spPr/>
<p:txBody><a:bodyPr/><a:lstStyle/><a:p><a:endParaRPr/></a:p></p:txBody></p:sp>
</p:spTree></p:cSld></p:sldLayout>"""
            layout_rels = f"""<Relationships xmlns="{PKG_REL_NS}"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="../slideMasters/slideMaster1.xml"/></Relationships>"""
            master = f"""<p:sldMaster xmlns:p="{P_NS}" xmlns:a="{A_NS}"><p:txStyles>
<p:titleStyle><a:lvl1pPr><a:defRPr sz="3600"/></a:lvl1pPr></p:titleStyle>
<p:bodyStyle><a:lvl1pPr><a:defRPr sz="{master_body_size}"/></a:lvl1pPr></p:bodyStyle>
<p:otherStyle><a:lvl1pPr><a:defRPr sz="1800"/></a:lvl1pPr></p:otherStyle>
</p:txStyles></p:sldMaster>"""
            zf.writestr("ppt/slideLayouts/slideLayout1.xml", layout)
            zf.writestr("ppt/slideLayouts/_rels/slideLayout1.xml.rels", layout_rels)
            zf.writestr("ppt/slideMasters/slideMaster1.xml", master)


def run_audit(path, rules=None):
    package = audit.Package(path)
    try:
        return audit.TypographyAuditor(package, rules or {}).audit()
    finally:
        package.close()


class TypographyAuditTests(unittest.TestCase):
    def test_body_title_and_source_thresholds(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "thresholds.pptx"
            content = "".join(
                [
                    shape_xml(2, "Title", "Readable title", 3600),
                    shape_xml(3, "SectionHeader", "Readable section", 2000),
                    shape_xml(4, "Body", "Readable body", 1800),
                    shape_xml(5, "Source", "https://example.com", 1000),
                ]
            )
            write_package(path, content)
            result = run_audit(path)
            self.assertEqual(result["summary"]["failures"], 0)
            classes = {item["classification"] for item in result["items"]}
            self.assertEqual(
                classes,
                {"slide_title", "section_header", "ordinary", "source_or_footnote"},
            )

    def test_body_title_and_source_below_threshold_fail(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "too-small.pptx"
            content = "".join(
                [
                    shape_xml(2, "Title", "Small title", 3599),
                    shape_xml(3, "SectionHeader", "Small section", 1999),
                    shape_xml(4, "Body", "Small body", 1799),
                    shape_xml(5, "Source", "https://example.com", 999),
                ]
            )
            write_package(path, content)
            result = run_audit(path)
            failures = [item for item in result["items"] if item["status"] == "fail"]
            self.assertEqual(len(failures), 4)
            self.assertTrue(all(item["reason"] == "below_minimum" for item in failures))

    def test_norm_autofit_uses_effective_size(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "norm-autofit.pptx"
            content = shape_xml(2, "Body", "Shrunk body", 1800, '<a:normAutofit fontScale="80000"/>')
            write_package(path, content)
            result = run_audit(path)
            item = result["items"][0]
            self.assertEqual(item["autofit_mode"], "normAutofit")
            self.assertAlmostEqual(item["effective_pt"], 14.4)
            self.assertEqual(item["reason"], "below_minimum")

    def test_norm_autofit_without_scale_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "unknown-autofit.pptx"
            write_package(path, shape_xml(2, "Body", "Unknown shrink", 1800, "<a:normAutofit/>"))
            result = run_audit(path)
            self.assertEqual(result["items"][0]["reason"], "normAutofit_missing_fontScale")
            self.assertIsNone(result["items"][0]["effective_pt"])

    def test_sp_autofit_passes_only_with_resolved_base_size(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            passing = Path(temp_dir) / "sp-autofit-pass.pptx"
            unresolved = Path(temp_dir) / "sp-autofit-unresolved.pptx"
            write_package(passing, shape_xml(2, "Body", "Growing box", 1800, "<a:spAutoFit/>"))
            write_package(
                unresolved,
                shape_xml(2, "Body", "No base size", None, "<a:spAutoFit/>"),
                default_size=None,
            )
            self.assertEqual(run_audit(passing)["summary"]["failures"], 0)
            item = run_audit(unresolved)["items"][0]
            self.assertEqual(item["autofit_mode"], "spAutoFit")
            self.assertEqual(item["reason"], "font_size_unresolved")

    def test_placeholder_type_and_size_inherit_from_layout_and_master(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "master-inheritance.pptx"
            content = shape_xml(
                2,
                "Inherited body",
                "Master-sized body",
                None,
                placeholder_idx="1",
            )
            write_package(path, content, default_size=None, master_body_size=1800)
            result = run_audit(path)
            item = result["items"][0]
            self.assertEqual(result["summary"]["failures"], 0)
            self.assertEqual(item["classification"], "ordinary")
            self.assertEqual(item["base_pt"], 18.0)
            self.assertEqual(item["size_source"], "bodyStyle level 1")

    def test_nested_group_and_table_text_are_audited(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "group-table.pptx"
            content = (
                "<p:grpSp>"
                + shape_xml(2, "Nested body", "Nested readable", 1800)
                + "</p:grpSp>"
                + table_xml(3, "Task table", [("Task", 1800), ("Too small", 1700)])
            )
            write_package(path, content)
            result = run_audit(path)
            self.assertEqual(result["summary"]["text_items"], 3)
            failures = [item for item in result["items"] if item["status"] == "fail"]
            self.assertEqual(len(failures), 1)
            self.assertEqual(failures[0]["location"], "table cell 2")

    def test_table_url_doi_and_ordinary_text_use_correct_thresholds(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "table-source.pptx"
            write_package(
                path,
                table_xml(
                    3,
                    "References table",
                    [
                        ("https://example.com", 1000),
                        ("doi:10.1000/test", 1000),
                        ("Ordinary label", 1700),
                    ],
                ),
            )
            result = run_audit(path)
            self.assertEqual(result["summary"]["failures"], 1)
            self.assertEqual(result["items"][0]["classification"], "source_or_footnote")
            self.assertEqual(result["items"][1]["classification"], "source_or_footnote")
            self.assertEqual(result["items"][2]["classification"], "ordinary")

    def test_hyperlink_requires_relationship_and_does_not_relax_adjacent_text(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            valid = Path(temp_dir) / "valid-link.pptx"
            broken = Path(temp_dir) / "broken-link.pptx"
            write_package(valid, shape_xml(2, "Body", "Project site", 1000, hyperlink=True))
            write_package(
                broken,
                shape_xml(
                    2,
                    "Body",
                    "Broken link",
                    1000,
                    hyperlink=True,
                    hyperlink_id="rId404",
                ),
            )
            valid_item = run_audit(valid)["items"][0]
            broken_item = run_audit(broken)["items"][0]
            self.assertEqual(valid_item["classification"], "source_or_footnote")
            self.assertEqual(valid_item["status"], "pass")
            self.assertEqual(broken_item["classification"], "ordinary")
            self.assertEqual(broken_item["status"], "fail")

            mixed = Path(temp_dir) / "mixed-link.pptx"
            mixed_body = """
<p:sp>
  <p:nvSpPr><p:cNvPr id="3" name="Body"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
  <p:spPr/>
  <p:txBody><a:bodyPr/><a:lstStyle/><a:p>
    <a:r><a:rPr sz="1000"><a:hlinkClick r:id="rId99"/></a:rPr><a:t>Linked</a:t></a:r>
    <a:r><a:rPr sz="1000"/><a:t> ordinary</a:t></a:r>
    <a:endParaRPr sz="1000"/>
  </a:p></p:txBody>
</p:sp>
"""
            write_package(mixed, mixed_body)
            items = run_audit(mixed)["items"]
            self.assertEqual(items[0]["classification"], "source_or_footnote")
            self.assertEqual(items[0]["status"], "pass")
            self.assertEqual(items[1]["classification"], "ordinary")
            self.assertEqual(items[1]["status"], "fail")

    def test_native_chart_title_and_axis_are_audited(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "chart.pptx"
            write_package(path, chart_frame_xml(), chart=chart_xml(axis_size=1700))
            result = run_audit(path)
            source = next(item for item in result["items"] if item["location"] == "chart title")
            axis = next(item for item in result["items"] if item["location"] == "category axis labels")
            self.assertEqual(source["status"], "pass")
            self.assertEqual(source["classification"], "source_or_footnote")
            self.assertEqual(axis["status"], "fail")
            self.assertEqual(axis["effective_pt"], 17.0)

    def test_chart_without_explicit_text_size_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "chart-unresolved.pptx"
            chart = f"""<c:chartSpace xmlns:c="{C_NS}" xmlns:a="{A_NS}"><c:chart><c:legend/></c:chart></c:chartSpace>"""
            write_package(path, chart_frame_xml(), chart=chart)
            result = run_audit(path)
            self.assertEqual(result["items"][0]["reason"], "chart_text_size_not_explicit")

    def test_exact_shape_exception_and_stale_exception_handling(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            path = root / "exception.pptx"
            manifest = root / "exceptions.json"
            write_package(path, shape_xml(7, "Dense label", "User-approved label", 1200))
            manifest.write_text(
                json.dumps({"exceptions": [{"slide": 1, "shape_id": 7, "reason": "User approved 12pt"}]}),
                encoding="utf-8",
            )
            rules = audit.load_exception_rules(manifest)
            result = run_audit(path, rules)
            self.assertEqual(result["summary"]["failures"], 0)
            self.assertEqual(result["items"][0]["classification"], "authorized_exception")

            stale = {(1, "99"): audit.ExceptionRule(1, "99", "Stale")}
            with self.assertRaisesRegex(audit.AuditInputError, "unused or stale"):
                run_audit(path, stale)

    def test_exception_never_waives_absolute_floor(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "absolute-floor.pptx"
            write_package(path, shape_xml(7, "Dense label", "Still unreadable", 999))
            rules = {(1, "7"): audit.ExceptionRule(1, "7", "User approved smaller body text")}
            result = run_audit(path, rules)
            self.assertEqual(result["items"][0]["minimum_pt"], 10.0)
            self.assertEqual(result["items"][0]["status"], "fail")

    def test_cli_accepts_potx_and_json_output(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "template.potx"
            write_package(path, shape_xml(2, "Body", "Readable", 1800))
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = audit.main([str(path), "--json"])
            self.assertEqual(exit_code, 0)
            parsed = json.loads(stdout.getvalue())
            self.assertEqual(parsed["summary"]["failures"], 0)

    def test_cli_emits_utf8_when_parent_requests_gbk(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "utf8-output.pptx"
            write_package(path, shape_xml(2, "Body", "中文摘要", 1800))
            environment = dict(os.environ)
            environment["PYTHONIOENCODING"] = "gbk"
            process = subprocess.run(
                [sys.executable, str(MODULE), str(path), "--json"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                env=environment,
            )
            self.assertEqual(process.returncode, 0, process.stderr.decode("utf-8", errors="replace"))
            parsed = json.loads(process.stdout.decode("utf-8"))
            self.assertEqual(parsed["items"][0]["text"], "中文摘要")


if __name__ == "__main__":
    unittest.main()
