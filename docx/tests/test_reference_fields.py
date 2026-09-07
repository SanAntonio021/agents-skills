"""Synthetic reference tests. No fixture generation or evaluation uses Word."""

from __future__ import annotations

import base64
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import zipfile

from docx import Document
from docx.oxml import OxmlElement
from lxml import etree
import pytest


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import reference_fields as refs  # noqa: E402


W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
M = "{http://schemas.openxmlformats.org/officeDocument/2006/math}"
MC = "{http://schemas.openxmlformats.org/markup-compatibility/2006}"
WP = "{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}"
V = "{urn:schemas-microsoft-com:vml}"
REL = "{http://schemas.openxmlformats.org/package/2006/relationships}"
CT = "{http://schemas.openxmlformats.org/package/2006/content-types}"
SPACE = "{http://www.w3.org/XML/1998/namespace}space"
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8"
    "/x8AAwMCAO+aD1sAAAAASUVORK5CYII="
)


@pytest.fixture(autouse=True)
def forbid_real_evaluation(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("A test attempted to invoke the real Word evaluator")

    monkeypatch.setitem(sys.modules, "reference_word", SimpleNamespace(evaluate_copy=forbidden))
    real_run_check = refs.versions.run_check

    def safe_run_check(*args, **kwargs):
        if kwargs.get("kind") == "word-native":
            pytest.fail("A test attempted to launch the native Word checker")
        return real_run_check(*args, **kwargs)

    monkeypatch.setattr(refs.versions, "run_check", safe_run_check)


def text_run(parent, value):
    run = etree.SubElement(parent, W + "r")
    node = etree.SubElement(run, W + "t")
    node.text = value
    node.set(SPACE, "preserve")
    return run


def field(parent, code, result="1", *, simple=False, locked=False, split=False):
    """Independently construct a field, without calling field_nodes/set_result."""
    if simple:
        start = etree.SubElement(parent, W + "fldSimple", {W + "instr": code})
        text_run(start, result)
    else:
        start = etree.SubElement(etree.SubElement(parent, W + "r"), W + "fldChar")
        start.set(W + "fldCharType", "begin")
        chunks = [code[:len(code) // 2], code[len(code) // 2:]] if split else [code]
        for chunk in chunks:
            node = etree.SubElement(etree.SubElement(parent, W + "r"), W + "instrText")
            node.set(SPACE, "preserve")
            node.text = chunk
        sep = etree.SubElement(etree.SubElement(parent, W + "r"), W + "fldChar")
        sep.set(W + "fldCharType", "separate")
        if result is not None:
            text_run(parent, result)
        end = etree.SubElement(etree.SubElement(parent, W + "r"), W + "fldChar")
        end.set(W + "fldCharType", "end")
    start.set(W + "dirty", "true")
    if locked:
        start.set(W + "fldLock", "true")
    return start


def bookmarked_field(parent, *, name="ExistingFigure", number="1", simple=False, code=None):
    etree.SubElement(parent, W + "bookmarkStart", {W + "id": "41", W + "name": name})
    start = field(parent, code or " SEQ Figure \\* ARABIC ", number, simple=simple)
    etree.SubElement(parent, W + "bookmarkEnd", {W + "id": "41"})
    return start


def math(parent, value="x=2"):
    equation = OxmlElement("m:oMath")
    run = OxmlElement("m:r")
    node = OxmlElement("m:t")
    node.text = value
    run.append(node)
    equation.append(run)
    parent.append(equation)
    return equation


def package(document):
    stream = io.BytesIO()
    document.save(stream)
    return refs.guard.DocxPackage.from_bytes(stream.getvalue())


def root_of(pkg, part="word/document.xml"):
    return etree.fromstring(pkg.entries[part])


def with_root(pkg, root, part="word/document.xml"):
    entries = dict(pkg.entries)
    entries[part] = etree.tostring(root, encoding="UTF-8", xml_declaration=True, standalone=True)
    infos = list(pkg.infos)
    if part not in pkg.entries:
        infos.append(zipfile.ZipInfo(part))
    return refs.guard.DocxPackage(infos, entries, pkg.comment)


def persisted(pkg, path):
    with zipfile.ZipFile(path, "w") as archive:
        archive.comment = pkg.comment
        for info in pkg.infos:
            archive.writestr(info, pkg.entries[info.filename])
    return refs.guard.DocxPackage.from_path(path)


def texts(pkg):
    return ["".join(p.itertext(W + "t")) for p in root_of(pkg).iter(W + "p")]


def canonical(node):
    return etree.tostring(node, method="c14n")


def evaluated_results(pkg, result="27"):
    """Emulate saved OOXML results directly, not COM Result.Text or core setters."""
    out = pkg
    for part in pkg.entries:
        if not (part.startswith("word/") and part.endswith(".xml")):
            continue
        root = root_of(pkg, part)
        stack = []
        for node in root.iter():
            if node.tag == W + "fldSimple":
                node.set(W + "dirty", "false")
                for index, value in enumerate(node.iter(W + "t")):
                    value.text = result if index == 0 else ""
                    value.set(SPACE, "preserve")
            elif node.tag == W + "fldChar":
                kind = node.get(W + "fldCharType")
                if kind == "begin":
                    node.set(W + "dirty", "false")
                    stack.append([False, False])
                elif kind == "separate":
                    stack[-1][0] = True
                elif kind == "end":
                    stack.pop()
            elif node.tag == W + "t" and stack and stack[-1][0]:
                node.text = "" if stack[-1][1] else result
                node.set(SPACE, "preserve")
                stack[-1][1] = True
        out = with_root(out, root, part)
    return out


def existing_package(*, simple=False, rich=False):
    document = Document()
    paragraph = document.add_paragraph("Figure ")
    bookmarked_field(paragraph._p, simple=simple)
    paragraph.add_run(" Caption remains prose")
    paragraph = document.add_paragraph("See Figure ")
    field(paragraph._p, " REF ExistingFigure \\h ", simple=simple, split=not simple)
    paragraph.add_run(" for details.")
    if rich:
        math(document.add_paragraph()._p)
        document.add_picture(io.BytesIO(PNG))
    return package(document)


@pytest.mark.parametrize("labels", [("Figure", "Table", "Equation"), ("\u56fe", "\u8868", "\u5f0f")])
def test_full_builds_separate_sequences_and_forward_references(labels):
    figure_label, table_label, eq_label = labels
    document = Document()
    document.add_paragraph(f"See {figure_label} 2, {table_label} 3 and {eq_label} (4).")
    document.add_paragraph(f"{figure_label} 2 Figure caption")
    document.add_paragraph(f"{table_label} 3 Table caption")
    document.add_table(rows=1, cols=1).cell(0, 0).text = f"See {figure_label} 2."
    paragraph = document.add_paragraph()
    math(paragraph._p)
    paragraph.add_run(" (4)")
    original = package(document)
    prepared, counts = refs.prepare_package(original)
    inventory = refs.Inventory(prepared)
    inventory.require_safe()
    assert counts == {"converted_targets": 3, "converted_references": 4}
    sequences = [f for f in inventory.fields if f.kind == "SEQ"]
    references = [f for f in inventory.fields if f.kind == "REF"]
    assert {f.instruction for f in sequences} == {
        "SEQ Figure \\* ARABIC", "SEQ Table \\* ARABIC", "SEQ Equation \\* ARABIC"
    }
    assert [f.text for f in sequences] == ["2", "3", "4"]
    assert [f.text for f in references] == ["2", "3", "4", "2"]
    assert texts(prepared) == texts(original)
    assert len(inventory.bookmarks) == 3
    for reference in references:
        name = reference.instruction.split()[1]
        bookmark = inventory.bookmarks[name]
        parent = bookmark.getparent()
        siblings = list(parent)
        stop = next(n for n in siblings if n.tag == W + "bookmarkEnd" and n.get(W + "id") == bookmark.get(W + "id"))
        number = "".join(t.text or "" for n in siblings[siblings.index(bookmark) + 1:siblings.index(stop)] for t in n.iter(W + "t"))
        assert number == reference.text
        assert any(f.start.getparent().getparent() is parent and f.text == number for f in sequences)
    for part, payload in original.entries.items():
        if part != "word/document.xml":
            assert prepared.entries[part] == payload, part


def test_unnumbered_inline_and_display_math_are_byte_preserved():
    document = Document()
    inline = document.add_paragraph("Inline formula: ")
    math(inline._p, "x=(123)")
    display = document.add_paragraph()
    block = OxmlElement("m:oMathPara")
    math(block, "y=(456)")
    display._p.append(block)
    original = package(document)
    prepared, counts = refs.prepare_package(original)
    assert counts == {"converted_targets": 0, "converted_references": 0}
    assert prepared.entries == original.entries
    assert not refs.Inventory(prepared).fields


def test_split_run_reference_preserves_presentation_and_end_formatting():
    document = Document()
    document.add_paragraph("Figure 12 Caption")
    paragraph = document.add_paragraph()
    paragraph.add_run("See Fig").bold = True
    paragraph.add_run("ure (")
    paragraph.add_run("1").italic = True
    paragraph.add_run("2) after.").underline = True
    original = package(document)
    prepared, counts = refs.prepare_package(original)
    assert counts["converted_references"] == 1
    assert texts(prepared) == texts(original)
    inventory = refs.Inventory(prepared)
    reference = next(f for f in inventory.fields if f.kind == "REF")
    assert reference.text == "12"
    assert reference.results[0].getparent().find(W + "rPr/" + W + "i") is not None
    trailing = next(t for t in root_of(prepared).iter(W + "t") if t.text == ") after.")
    assert trailing.getparent().find(W + "rPr/" + W + "u") is not None


@pytest.mark.parametrize("simple", [False, True])
def test_prepare_is_idempotent_and_reuses_existing_bookmark(simple):
    document = Document()
    paragraph = document.add_paragraph("Figure ")
    bookmarked_field(paragraph._p, simple=simple)
    paragraph.add_run(" Caption")
    document.add_paragraph("See Figure 1.")
    original = package(document)
    prepared, counts = refs.prepare_package(original)
    assert counts == {"converted_targets": 0, "converted_references": 1}
    inventory = refs.Inventory(prepared)
    assert set(inventory.bookmarks) == {"ExistingFigure"}
    assert next(f for f in inventory.fields if f.kind == "REF").instruction == "REF ExistingFigure \\h"
    second, counts = refs.prepare_package(prepared)
    assert counts == {"converted_targets": 0, "converted_references": 0}
    assert second.entries == prepared.entries


def test_freshly_generated_bookmark_identity_survives_second_prepare():
    document = Document()
    document.add_paragraph("Figure 1 Caption")
    document.add_paragraph("See Figure 1.")
    first, _ = refs.prepare_package(package(document))
    second, counts = refs.prepare_package(first)
    assert first.entries == second.entries
    assert counts == {"converted_targets": 0, "converted_references": 0}


@pytest.mark.parametrize("number", ["2.3", "A.2", "3-1"])
def test_existing_chapter_sequence_is_preserved_but_plain_number_requires_design(number):
    document = Document()
    paragraph = document.add_paragraph("Figure ")
    bookmarked_field(paragraph._p, number=number, code=" SEQ Figure \\s 1 ")
    paragraph.add_run(" Caption")
    document.add_paragraph(f"See Figure {number}.")
    prepared, _ = refs.prepare_package(package(document))
    assert next(f for f in refs.Inventory(prepared).fields if f.kind == "SEQ").instruction == "SEQ Figure \\s 1"
    plain = Document()
    plain.add_paragraph(f"Figure {number} Caption")
    with pytest.raises(ValueError, match="chapter|appendix|numbering"):
        refs.prepare_package(package(plain))


@pytest.mark.parametrize("duplicate", [False, True])
def test_missing_or_duplicate_target_refuses_to_guess(duplicate):
    document = Document()
    if duplicate:
        document.add_paragraph("Figure 1 First")
        document.add_paragraph("Figure 1 Second")
    document.add_paragraph("See Figure 1.")
    with pytest.raises(ValueError, match="Ambiguous/missing.*main:p"):
        refs.prepare_package(package(document))


def test_explicit_mapping_selects_second_duplicate_object():
    document = Document()
    document.add_paragraph("Figure 1 First")
    document.add_paragraph("Figure 1 Second")
    document.add_paragraph("See Figure 1.")
    prepared, _ = refs.prepare_package(package(document), mapping={"references": {"main:p2:c11": "main:p1"}})
    inventory = refs.Inventory(prepared)
    ref = next(f for f in inventory.fields if f.kind == "REF")
    selected = inventory.bookmarks[ref.instruction.split()[1]]
    assert "Second" in "".join(selected.getparent().itertext(W + "t"))


def test_explicit_ignore_leaves_missing_reference_literal():
    document = Document()
    document.add_paragraph("See Figure 99.")
    original = package(document)
    prepared, counts = refs.prepare_package(original, mapping={"ignore": ["main:p0:c11"]})
    assert prepared.entries == original.entries
    assert counts == {"converted_targets": 0, "converted_references": 0}


def test_explicit_mapping_cannot_invent_a_target():
    document = Document()
    document.add_paragraph("See Figure 99.")
    with pytest.raises(ValueError, match="Ambiguous/missing"):
        refs.prepare_package(package(document), mapping={"references": {"main:p0:c11": "main:p404"}})


def test_unknown_mapping_key_and_unknown_mode_are_rejected():
    original = package(Document())
    with pytest.raises(ValueError, match="Mapping"):
        refs.prepare_package(original, mapping={"guess": True})
    with pytest.raises(ValueError, match="mode"):
        refs.prepare_package(original, mode="guess")


def test_local_mode_does_not_convert_literals_or_resolve_missing_literals():
    document = Document()
    document.add_paragraph("Figure 1 Caption")
    document.add_paragraph("See Figure 99.")
    original = package(document)
    prepared, counts = refs.prepare_package(original, mode="local")
    assert prepared.entries == original.entries
    assert counts == {"converted_targets": 0, "converted_references": 0}


@pytest.mark.parametrize("reference", ["Figure 1-2", "Figure 1~2", "Figure 1\u81f32", "Figure 1\u52302", "Figure 1\u20132", "Figure 1\u20142", "Figure (1)-(2)"])
def test_abbreviated_range_fails_without_partially_publishing(reference):
    document = Document()
    document.add_paragraph("Figure 1 First")
    document.add_paragraph("Figure 2 Second")
    document.add_paragraph(f"See {reference}.")
    original = package(document)
    before = dict(original.entries)
    with pytest.raises(ValueError, match="range|Ambiguous/missing"):
        refs.prepare_package(original)
    assert original.entries == before


def test_explicit_range_endpoint_labels_both_get_references():
    document = Document()
    document.add_paragraph("Figure 1 First")
    document.add_paragraph("Figure 2 Second")
    document.add_paragraph("See Figure 1 to Figure 2.")
    original = package(document)
    prepared, counts = refs.prepare_package(original)
    assert counts["converted_references"] == 2
    assert texts(prepared) == texts(original)


@pytest.mark.parametrize("simple", [False, True])
@pytest.mark.parametrize("kind", ["SEQ Figure", "STYLEREF Heading1", "REF ExistingFigure", "PAGEREF ExistingFigure"])
def test_locked_internal_fields_fail_closed(simple, kind):
    document = Document()
    paragraph = document.add_paragraph()
    bookmarked_field(paragraph._p)
    field(document.add_paragraph()._p, kind, simple=simple, locked=True)
    inventory = refs.Inventory(package(document))
    assert any("Locked field" in issue for issue in inventory.issues)
    with pytest.raises(ValueError, match="Locked field"):
        inventory.require_safe()


@pytest.mark.parametrize("simple_outer", [False, True])
def test_nested_internal_field_fails_closed(simple_outer):
    document = Document()
    paragraph = document.add_paragraph()._p
    start = field(paragraph, "SEQ Figure", simple=simple_outer)
    if simple_outer:
        field(start, "SEQ Table")
    else:
        container = etree.Element(W + "p")
        field(container, "SEQ Table")
        position = len(paragraph) - 1
        for node in list(container):
            paragraph.insert(position, node)
            position += 1
    inventory = refs.Inventory(package(document))
    with pytest.raises(ValueError, match="nested|structured"):
        inventory.require_safe()


@pytest.mark.parametrize("fault", ["unclosed", "unmatched_end", "orphan_separator", "no_separator", "structured_result", "missing_bookmark", "duplicate_bookmark"])
def test_malformed_and_unsafe_inventory_failures(fault):
    original = existing_package()
    root = root_of(original)
    chars = list(root.iter(W + "fldChar"))
    if fault == "unclosed":
        chars[-1].getparent().remove(chars[-1])
    elif fault == "unmatched_end":
        chars[0].getparent().remove(chars[0])
        chars[1].getparent().remove(chars[1])
    elif fault == "orphan_separator":
        chars[0].getparent().remove(chars[0])
    elif fault == "no_separator":
        chars[1].getparent().remove(chars[1])
    elif fault == "structured_result":
        sep_run = chars[1].getparent()
        run = etree.Element(W + "r")
        etree.SubElement(run, W + "drawing")
        sep_run.addnext(run)
    elif fault == "missing_bookmark":
        bookmark = next(root.iter(W + "bookmarkStart"))
        bookmark.getparent().remove(bookmark)
    else:
        bookmark = next(root.iter(W + "bookmarkStart"))
        duplicate = copy.deepcopy(bookmark)
        duplicate.set(W + "id", "99")
        root.find(W + "body").find(W + "p").append(duplicate)
    with pytest.raises(ValueError):
        refs.Inventory(with_root(original, root)).require_safe()


def add_textbox(parent, name="BoxA", *, alternate=True, mismatch=False):
    outer = etree.SubElement(parent, MC + "AlternateContent") if alternate else parent
    choice = etree.SubElement(outer, MC + "Choice", Requires="wps") if alternate else outer
    drawing = etree.SubElement(etree.SubElement(choice, W + "r"), W + "drawing")
    inline = etree.SubElement(drawing, WP + "inline")
    etree.SubElement(inline, WP + "docPr", id="100", name=name)
    box = etree.SubElement(inline, W + "txbxContent")
    field(etree.SubElement(box, W + "p"), "SEQ Figure", "1")
    if alternate:
        fallback = etree.SubElement(outer, MC + "Fallback")
        shape = etree.SubElement(etree.SubElement(fallback, W + "pict"), V + "shape", id=name)
        box = etree.SubElement(etree.SubElement(shape, V + "textbox"), W + "txbxContent")
        field(etree.SubElement(box, W + "p"), "SEQ Table" if mismatch else "SEQ Figure", "1")


def all_stories_package():
    document = Document()
    field(document.add_paragraph()._p, "SEQ Figure")
    field(document.add_table(rows=1, cols=1).cell(0, 0).paragraphs[0]._p, "SEQ Table")
    section = document.sections[0]
    for container in (section.header, section.first_page_header, section.even_page_header,
                      section.footer, section.first_page_footer, section.even_page_footer):
        field(container.paragraphs[0]._p, "SEQ Figure")
    add_textbox(document.add_paragraph()._p)
    add_textbox(section.header.add_paragraph()._p, "HeaderBox")
    document.add_section()  # Linked headers/footers must not appear twice.
    out = package(document)
    relationships = root_of(out, "word/_rels/document.xml.rels")
    content_types = root_of(out, "[Content_Types].xml")
    for kind in ("footnote", "endnote"):
        root = etree.Element(W + kind + "s", nsmap={"w": W[1:-1]})
        for note_id in (-1, 0, 1, 2):
            note = etree.SubElement(root, W + kind, {W + "id": str(note_id)})
            field(etree.SubElement(note, W + "p"), "SEQ Equation", str(note_id))
        part = f"word/{kind}s.xml"
        out = with_root(out, root, part)
        etree.SubElement(relationships, REL + "Relationship", Id=f"rIdTest{kind}",
                         Type=f"http://schemas.openxmlformats.org/officeDocument/2006/relationships/{kind}s",
                         Target=f"{kind}s.xml")
        etree.SubElement(content_types, CT + "Override", PartName="/" + part,
                         ContentType=f"application/vnd.openxmlformats-officedocument.wordprocessingml.{kind}s+xml")
    out = with_root(out, relationships, "word/_rels/document.xml.rels")
    return with_root(out, content_types, "[Content_Types].xml")


def test_inventory_all_stories_linked_headers_and_fallback_twins():
    inventory = refs.Inventory(all_stories_package())
    inventory.require_safe()
    ids = {story.id for story in inventory.stories}
    expected = {"main", "footnotes", "endnotes", "textbox:main:BoxA", "textbox:header:1:1:HeaderBox"}
    expected.update(f"{kind}:1:{index}" for kind in ("header", "footer") for index in (1, 2, 3))
    assert ids == expected
    assert len(inventory.stories) == len(expected)
    assert len(inventory.fields) == 14
    assert len(inventory.twins) == 2
    assert all(len(twins) == 1 for twins in inventory.twins.values())
    for story in inventory.stories:
        ordinals = [f.ordinal for f in inventory.fields if f.story == story.id]
        assert ordinals == list(range(len(ordinals)))
    for kind in ("footnotes", "endnotes"):
        assert [f.text for f in inventory.fields if f.story == kind] == ["1", "2"]


def test_inventory_refuses_fallback_instruction_mismatch():
    document = Document()
    add_textbox(document.add_paragraph()._p, mismatch=True)
    with pytest.raises(ValueError, match="AlternateContent field mismatch"):
        refs.Inventory(package(document)).require_safe()


@pytest.mark.parametrize("fault", ["locked", "nested"])
def test_inventory_refuses_unsafe_fallback_twin(fault):
    document = Document()
    add_textbox(document.add_paragraph()._p)
    original = package(document)
    root = root_of(original)
    fallback = next(root.iter(MC + "Fallback"))
    if fault == "locked":
        next(fallback.iter(W + "fldChar")).set(W + "fldLock", "true")
    else:
        paragraph = next(fallback.iter(W + "p"))
        result = next(paragraph.iter(W + "t"))
        wrapper = etree.Element(W + "fldSimple", {W + "instr": "SEQ Table"})
        result.getparent().addprevious(wrapper)
        text_run(wrapper, "1")
    with pytest.raises(ValueError):
        refs.Inventory(with_root(original, root)).require_safe()


@pytest.mark.parametrize("simple", [False, True])
def test_transplant_reads_persisted_results_and_check_delta_accepts_only_that(tmp_path, simple):
    baseline = existing_package(simple=simple, rich=True)
    evaluated = evaluated_results(baseline, "27")
    evaluated = persisted(evaluated, tmp_path / "evaluated.docx")
    candidate, report = refs.transplant(baseline, evaluated)
    assert [f.text for f in refs.Inventory(candidate).fields] == ["27", "27"]
    assert [row["result"] for row in report] == ["27", "27"]
    assert all(f.start.get(W + "dirty") == "false" for f in refs.Inventory(candidate).fields)
    assert refs.check_delta(baseline, candidate)["field_result_delta"] == "checked"
    assert baseline.entries != candidate.entries
    assert [f.text for f in refs.Inventory(baseline).fields] == ["1", "1"]
    for part in baseline.entries:
        if part != "word/document.xml":
            assert candidate.entries[part] == baseline.entries[part], part


def test_transplant_updates_every_story_and_both_fallback_copies(tmp_path):
    baseline = all_stories_package()
    evaluated = persisted(evaluated_results(baseline, "27"), tmp_path / "evaluated.docx")
    candidate, report = refs.transplant(baseline, evaluated)
    assert len(report) == 14
    inventory = refs.Inventory(candidate)
    assert {f.text for f in inventory.fields} == {"27"}
    assert {f.text for twins in inventory.twins.values() for f in twins} == {"27"}
    assert refs.check_delta(baseline, candidate)["field_result_delta"] == "checked"


def test_transplant_does_not_copy_word_side_effects_outside_results():
    baseline = existing_package(rich=True)
    evaluated = evaluated_results(baseline)
    entries = dict(evaluated.entries)
    entries["word/styles.xml"] += b"\n"
    evaluated = refs.guard.DocxPackage(evaluated.infos, entries, evaluated.comment)
    root = root_of(evaluated)
    next(t for t in root.iter(W + "t") if t.text == "Figure ").text = "Word changed prose "
    candidate, _ = refs.transplant(baseline, with_root(evaluated, root))
    assert "Word changed prose" not in " ".join(texts(candidate))
    assert candidate.entries["word/styles.xml"] == baseline.entries["word/styles.xml"]
    refs.check_delta(baseline, candidate)


@pytest.mark.parametrize("dirty", [None, "true", "false", "0", "1"])
def test_check_delta_allows_internal_dirty_attribute_only(dirty):
    baseline = existing_package()
    root = root_of(baseline)
    for node in root.iter(W + "fldChar"):
        if node.get(W + "fldCharType") == "begin":
            if dirty is None:
                node.attrib.pop(W + "dirty", None)
            else:
                node.set(W + "dirty", dirty)
    refs.check_delta(baseline, with_root(baseline, root))


@pytest.mark.parametrize("mutation", ["prose", "styles", "media", "bookmark", "instruction", "omml", "result_style", "relationships", "members", "comment"])
def test_check_delta_rejects_every_non_result_mutation(mutation):
    baseline = existing_package(rich=True)
    candidate = evaluated_results(baseline)
    root = root_of(candidate)
    if mutation == "prose":
        next(t for t in root.iter(W + "t") if t.text == "Figure ").text = "Edited prose "
    elif mutation == "bookmark":
        next(root.iter(W + "bookmarkEnd")).set(W + "id", "999")
    elif mutation == "instruction":
        next(root.iter(W + "instrText")).text = " SEQ Table \\* ARABIC "
    elif mutation == "omml":
        next(root.iter(M + "t")).text = "x=999"
    elif mutation == "result_style":
        result = next(t for t in root.iter(W + "t") if t.text == "27")
        etree.SubElement(etree.SubElement(result.getparent(), W + "rPr"), W + "b")
    candidate = with_root(candidate, root)
    entries = dict(candidate.entries)
    if mutation in {"styles", "relationships"}:
        part = {"styles": "word/styles.xml", "relationships": "word/_rels/document.xml.rels"}[mutation]
        other_root = root_of(candidate, part)
        if mutation == "styles":
            next(other_root.iter(W + "name")).set(W + "val", "Changed style name")
        else:
            next(rel for rel in other_root if rel.get("Type", "").endswith("/image")).set("Target", "media/changed.png")
        entries[part] = etree.tostring(other_root)
    elif mutation == "media":
        part = next(name for name in entries if name.startswith("word/media/"))
        entries[part] += b"changed"
    elif mutation == "members":
        entries["word/new-part.xml"] = b"<new/>"
    candidate = refs.guard.DocxPackage(candidate.infos, entries, b"changed" if mutation == "comment" else candidate.comment)
    with pytest.raises(ValueError):
        refs.check_delta(baseline, candidate)


@pytest.mark.parametrize("result", ["Error! Reference source not found.", "\u9519\u8bef!\u672a\u5b9a\u4e49\u4e66\u7b7e", "\u672a\u627e\u5230\u5f15\u7528\u6e90", "1\n2", "1\t2"])
def test_invalid_or_multiline_evaluated_result_is_rejected(result):
    baseline = existing_package()
    with pytest.raises(ValueError):
        refs.transplant(baseline, evaluated_results(baseline, result))


def test_unrelated_field_result_cannot_be_transplanted_or_checked():
    document = Document()
    field(document.add_paragraph()._p, "DATE \\@ yyyy", "2026")
    baseline = package(document)
    evaluated = evaluated_results(baseline, "2030")
    with pytest.raises(ValueError, match="Unrelated field"):
        refs.transplant(baseline, evaluated)
    with pytest.raises(ValueError):
        refs.check_delta(baseline, evaluated)


@pytest.mark.parametrize("mode", ["local", "full"])
@pytest.mark.parametrize("unrelated_field", [False, True])
def test_finalize_without_internal_fields_never_calls_evaluator(tmp_path, mode, unrelated_field):
    document = Document()
    document.add_paragraph("Ordinary prose only.")
    if unrelated_field:
        field(document.add_paragraph()._p, "DATE \\@ yyyy", "2026")
    source, output = tmp_path / "source.docx", tmp_path / "output.docx"
    baseline = persisted(package(document), source)
    original = source.read_bytes()
    result = refs.finalize(source, output, mode=mode)
    assert result["ok"], result
    assert result["status"] == "PASS"
    assert result["reference_refresh"]["status"] == "NOT_APPLICABLE"
    assert result["native_acceptance"]["status"] == "NOT_APPLICABLE"
    assert source.read_bytes() == original
    assert refs.guard.DocxPackage.from_path(output).entries == baseline.entries
    record = json.loads(Path(str(output) + ".check.json").read_text(encoding="utf-8"))
    assert record["ok"]
    checked = refs.check_files(source, output)
    assert checked["source_sha256"] == hashlib.sha256(output.read_bytes()).hexdigest()
    assert checked["source"] == str(output.resolve())
    assert checked["layout"] == "not_checked"


@pytest.mark.parametrize("mode", ["local", "full"])
def test_finalize_uses_fake_saved_package_not_evaluator_report_values(tmp_path, mode):
    source, output = tmp_path / "source.docx", tmp_path / "output.docx"
    if mode == "full":
        document = Document()
        document.add_paragraph("Figure 1 Caption")
        document.add_paragraph("See Figure 1.")
        baseline = package(document)
    else:
        baseline = existing_package()
    persisted(baseline, source)
    original = source.read_bytes()
    calls = []
    native_calls = []

    def evaluator(eval_source, destination, descriptors, stories, *, allow_office_com):
        calls.append(Path(eval_source))
        assert allow_office_com is False
        assert [d["kind"] for d in descriptors] == ["SEQ", "REF"]
        assert all({"story", "ordinal", "instruction"} <= set(d) for d in descriptors)
        assert stories[0] == {"id": "main", "kind": "main"}
        prepared = refs.guard.DocxPackage.from_path(Path(eval_source))
        persisted(evaluated_results(prepared, "27"), destination)
        return {"ok": True, "status": "PASS", "engine": "test-fake", "results": ["DO NOT USE COM TEXT"]}

    def native_checker(path, format_, *, allow_office_com, require_render):
        native_calls.append(Path(path))
        assert path == output
        assert format_ == "docx"
        assert not allow_office_com
        assert not require_render
        assert [f.text for f in refs.Inventory(refs.guard.DocxPackage.from_path(path)).fields] == ["27", "27"]
        return {"ok": True, "status": "PASS"}

    result = refs.finalize(source, output, mode=mode, evaluator=evaluator, native_checker=native_checker)
    assert result["ok"], result
    assert len(calls) == 1
    assert calls[0] == (output.with_name("output.references-prepared.docx") if mode == "full" else source)
    assert [f.text for f in refs.Inventory(refs.guard.DocxPackage.from_path(output)).fields] == ["27", "27"]
    assert [row["result"] for row in result["evaluated_results"]] == ["27", "27"]
    assert native_calls == [output]
    assert result["native_acceptance"] == {"ok": True, "status": "PASS"}
    assert source.read_bytes() == original


@pytest.mark.parametrize("mismatch", ["instruction", "count"])
def test_finalize_refuses_saved_field_bijection_mismatch_before_output(tmp_path, mismatch):
    source, output = tmp_path / "source.docx", tmp_path / "output.docx"
    persisted(existing_package(), source)
    original = source.read_bytes()

    def evaluator(eval_source, destination, descriptors, stories, **kwargs):
        prepared = refs.guard.DocxPackage.from_path(Path(eval_source))
        root = root_of(evaluated_results(prepared))
        if mismatch == "instruction":
            next(root.iter(W + "instrText")).text = " SEQ Table \\* ARABIC "
        else:
            field(root.find(W + "body").find(W + "p"), "SEQ Equation")
        persisted(with_root(prepared, root), destination)
        return {"ok": True, "status": "PASS"}

    with pytest.raises(ValueError, match="bijection|identity|count|instruction"):
        refs.finalize(source, output, evaluator=evaluator)
    assert source.read_bytes() == original
    assert not output.exists()
    assert not Path(str(output) + ".check.json").exists()


@pytest.mark.parametrize("collision", ["source", "existing_output", "existing_record", "record_source", "record_output", "source_hardlink", "prepared_source", "existing_prepared"])
def test_finalize_protects_source_output_and_records(tmp_path, collision):
    source, output = tmp_path / "source.docx", tmp_path / "output.docx"
    record = tmp_path / "result.json"
    persisted(existing_package(), source)
    mode = "local"
    if collision == "source":
        output = source
    elif collision == "existing_output":
        output.write_bytes(b"User's existing output")
    elif collision == "existing_record":
        record.write_text('{"approved": true}', encoding="utf-8")
    elif collision == "record_source":
        record = source
    elif collision == "record_output":
        output = tmp_path / "output.json"
        record = output
    elif collision == "source_hardlink":
        os.link(source, output)
    elif collision == "prepared_source":
        source = tmp_path / "output.references-prepared.docx"
        persisted(existing_package(), source)
        mode = "full"
    elif collision == "existing_prepared":
        output.with_name("output.references-prepared.docx").write_bytes(b"Preserve prepared file")
        mode = "full"
    originals = {p: p.read_bytes() for p in tmp_path.iterdir() if p.is_file()}
    with pytest.raises(ValueError):
        refs.finalize(source, output, mode=mode, record=record)
    assert {p: p.read_bytes() for p in tmp_path.iterdir() if p.is_file()} == originals


def test_finalize_refuses_source_change_during_fake_evaluation(tmp_path):
    source, output = tmp_path / "source.docx", tmp_path / "output.docx"
    persisted(existing_package(), source)
    changed = source.read_bytes() + b"external edit"

    def evaluator(eval_source, destination, descriptors, stories, **kwargs):
        prepared = refs.guard.DocxPackage.from_path(Path(eval_source))
        persisted(evaluated_results(prepared), destination)
        source.write_bytes(changed)
        return {"ok": True, "status": "PASS"}

    with pytest.raises(ValueError, match="Source changed"):
        refs.finalize(source, output, evaluator=evaluator)
    assert source.read_bytes() == changed
    assert not output.exists()


def test_failed_evaluator_cannot_claim_pass_and_retains_cached_candidate(tmp_path):
    source, output = tmp_path / "source.docx", tmp_path / "output.docx"
    baseline = persisted(existing_package(), source)

    def unavailable(*args, **kwargs):
        return {"ok": False, "status": "UNSAFE_PROCESS", "message": "Synthetic refusal"}

    result = refs.finalize(source, output, evaluator=unavailable)
    assert not result["ok"]
    assert result["status"] == "UNVERIFIED"
    assert result["reference_refresh"]["status"] == "UNSAFE_PROCESS"
    assert refs.guard.DocxPackage.from_path(output).entries == baseline.entries
    assert not json.loads(Path(str(output) + ".check.json").read_text(encoding="utf-8"))["ok"]


def test_publish_refuses_existing_destination_and_leaves_no_temporary_file(tmp_path):
    destination = tmp_path / "existing.docx"
    destination.write_bytes(b"Keep this file")
    with pytest.raises(ValueError, match="exists"):
        refs.publish(existing_package(), destination)
    assert destination.read_bytes() == b"Keep this file"
    assert not list(tmp_path.glob(".reference-*"))


def test_prepare_refuses_reference_inside_hyperlink_without_mutating_package():
    document = Document()
    document.add_paragraph("Figure 1 Caption")
    paragraph = document.add_paragraph("See ")
    link = etree.SubElement(paragraph._p, W + "hyperlink", {W + "anchor": "ExistingFigure"})
    text_run(link, "Figure 1")
    original = package(document)
    snapshot = dict(original.entries)
    with pytest.raises(ValueError, match="hyperlink|structured"):
        refs.prepare_package(original)
    assert original.entries == snapshot


def test_literal_code_style_is_not_converted_or_resolved():
    from docx.enum.style import WD_STYLE_TYPE

    document = Document()
    document.styles.add_style("SourceCode", WD_STYLE_TYPE.PARAGRAPH)
    document.add_paragraph("Figure 1 Not a caption", style="SourceCode")
    document.add_paragraph("See Figure 99", style="SourceCode")
    original = package(document)
    prepared, counts = refs.prepare_package(original)
    assert prepared.entries == original.entries
    assert counts == {"converted_targets": 0, "converted_references": 0}


def test_split_instruction_and_result_runs_use_logical_field_identity(tmp_path):
    document = Document()
    paragraph = document.add_paragraph()._p
    field(paragraph, " SEQ   Figure   \\* ARABIC ", "1", split=True)
    extra = etree.Element(W + "r")
    etree.SubElement(extra, W + "t").text = "2"
    paragraph.insert(len(paragraph) - 1, extra)
    baseline = package(document)
    inventory = refs.Inventory(baseline)
    assert inventory.fields[0].key == ("main", 0, "SEQ Figure \\* ARABIC")
    assert inventory.fields[0].text == "12"
    saved = persisted(evaluated_results(baseline, "99"), tmp_path / "saved.docx")
    candidate, _ = refs.transplant(baseline, saved)
    result_field = refs.Inventory(candidate).fields[0]
    assert result_field.text == "99"
    assert len(result_field.results) == 2
    assert result_field.results[1].text in (None, "")
    refs.check_delta(baseline, candidate)


@pytest.mark.parametrize("simple", [False, True])
def test_transplant_can_populate_previously_empty_result(simple):
    document = Document()
    paragraph = document.add_paragraph()._p
    field(paragraph, "SEQ Figure", None, simple=simple)
    baseline = package(document)
    root = root_of(baseline)
    paragraph = next(root.iter(W + "p"))
    if simple:
        simple_node = next(root.iter(W + "fldSimple"))
        next(simple_node.iter(W + "t")).text = "7"
    else:
        container = etree.Element(W + "p")
        run = text_run(container, "7")
        paragraph.insert(len(paragraph) - 1, run)
    candidate, _ = refs.transplant(baseline, with_root(baseline, root))
    assert refs.Inventory(candidate).fields[0].text == "7"
    refs.check_delta(baseline, candidate)


def test_whitespace_only_instruction_rewrite_is_not_an_allowed_delta():
    baseline = existing_package()
    root = root_of(baseline)
    instruction = next(root.iter(W + "instrText"))
    instruction.text = "   " + instruction.text
    candidate = with_root(baseline, root)
    assert [f.key for f in refs.Inventory(candidate).fields] == [f.key for f in refs.Inventory(baseline).fields]
    with pytest.raises(ValueError, match="Non-result"):
        refs.check_delta(baseline, candidate)


def test_native_checker_failure_prevents_final_pass(tmp_path):
    source, output = tmp_path / "source.docx", tmp_path / "output.docx"
    persisted(existing_package(), source)

    def evaluator(eval_source, destination, descriptors, stories, **kwargs):
        persisted(evaluated_results(refs.guard.DocxPackage.from_path(Path(eval_source))), destination)
        return {"ok": True, "status": "PASS"}

    def checker(path, format_, **kwargs):
        assert path == output
        return {"ok": False, "status": "UNVERIFIED", "message": "Synthetic native-check failure"}

    result = refs.finalize(source, output, evaluator=evaluator, native_checker=checker)
    assert not result["ok"]
    assert result["status"] == "UNVERIFIED"
    assert result["reference_refresh"]["ok"]
    assert not result["native_acceptance"]["ok"]
    assert not json.loads(Path(str(output) + ".check.json").read_text(encoding="utf-8"))["ok"]


def test_markdown_inventory_uses_ast_and_excludes_code_and_inline_math(tmp_path, monkeypatch):
    source = tmp_path / "source.md"
    source.write_text("Approved source is not rewritten.", encoding="utf-8")
    original = source.read_bytes()
    ast = {"blocks": [
        {"t": "Para", "c": [{"t": "Image", "c": [[], [], ["figure.png", ""]]}]},
        {"t": "Table", "c": []},
        {"t": "Math", "c": [{"t": "DisplayMath"}, "x=1"]},
        {"t": "Math", "c": [{"t": "InlineMath"}, "y=2"]},
        {"t": "CodeBlock", "c": [[], "![image](ignored.png) $$ ignored $$ @fig:ignored"]},
        {"t": "Code", "c": [[], "@eq:ignored"]},
    ]}

    def fake_pandoc(command, **kwargs):
        assert command == ["synthetic-pandoc", str(source.resolve()), "--from=markdown", "--to=json"]
        assert kwargs["cwd"] == source.parent
        assert kwargs["encoding"] == "utf-8"
        return SimpleNamespace(returncode=0, stdout=json.dumps(ast), stderr="")

    monkeypatch.setattr(refs.subprocess, "run", fake_pandoc)
    result = refs.markdown_inventory(source, pandoc="synthetic-pandoc")
    assert result == {"source": str(source.resolve()), "parser": "pandoc-json", "images": 1, "tables": 1, "display_equations": 1}
    assert source.read_bytes() == original


@pytest.mark.parametrize("citation", ["fig:one", "tbl_one", "eq-two"])
def test_markdown_object_citations_fail_without_explicit_rendered_mapping(tmp_path, monkeypatch, citation):
    source = tmp_path / "source.md"
    source.write_text("@" + citation, encoding="utf-8")
    ast = {"blocks": [{"t": "Cite", "c": [[{"citationId": citation}], []]}]}
    monkeypatch.setattr(refs.subprocess, "run", lambda *a, **kw: SimpleNamespace(returncode=0, stdout=json.dumps(ast), stderr=""))
    with pytest.raises(ValueError, match="Unresolved Markdown object citation"):
        refs.markdown_inventory(source)


@pytest.mark.parametrize("returncode,stdout", [(1, ""), (0, "{}")])
def test_markdown_parser_failure_is_not_a_successful_empty_inventory(tmp_path, monkeypatch, returncode, stdout):
    source = tmp_path / "source.md"
    source.write_text("Source", encoding="utf-8")
    monkeypatch.setattr(refs.subprocess, "run", lambda *a, **kw: SimpleNamespace(returncode=returncode, stdout=stdout, stderr="synthetic error"))
    with pytest.raises(ValueError, match="Markdown|syntax tree"):
        refs.markdown_inventory(source)
