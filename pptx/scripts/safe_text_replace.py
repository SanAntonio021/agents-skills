"""Deterministic whole-text replacement for python-pptx text frames.

``replace_text(shape_or_text_frame, text)`` changes only paragraphs in that
text frame, in memory. The caller owns saving to a new file and file-level QA.
Newline separates paragraphs; vertical tab is a soft line break. Paragraphs
retain the matching original paragraph's properties and first run's explicit
style. Additional paragraphs use the last original paragraph as their template.
Mixed run styling and fields are intentionally replaced; for a small edit that
must retain mixed styles, assign to the relevant ``run.text`` instead.
This is not a repair tool or a complete OOXML validator.
"""

from copy import deepcopy

from pptx.oxml.xmlchemy import OxmlElement
from pptx.oxml.ns import qn


class UnsafeTextStructureError(ValueError):
    """The target contains duplicate singleton formatting nodes."""


def _check_formatting(root):
    # Scope checks to each actual parent: the same tag in separate paragraphs
    # or separate runs is valid. Never silently normalize malformed input.
    singleton_children = {
        qn("a:p"): ("a:pPr", "a:endParaRPr"),
        qn("a:r"): ("a:rPr", "a:t"),
        qn("a:br"): ("a:rPr",),
        qn("a:fld"): ("a:rPr", "a:pPr", "a:t"),
        qn("a:pPr"): ("a:defRPr",),
    }
    for node in root.iter():
        for tag in singleton_children.get(node.tag, ()):
            if len(node.findall(qn(tag))) > 1:
                path = node.getroottree().getpath(node)
                raise UnsafeTextStructureError(f"Duplicate {tag} at {path}")


def replace_text(target, text: str) -> None:
    """Replace a shape/text-frame's full text without accumulating formatting.

    Paragraph format includes alignment, bullets, indentation and default run
    properties. Explicit first-run style is copied once, including any hyperlink.
    Empty paragraphs retain an empty run so its style survives a later edit.
    The whole replacement is prepared and checked before the target is changed.
    """
    if not isinstance(text, str):
        raise TypeError("text must be str")
    if hasattr(target, "text_frame"):
        if not target.has_text_frame:
            raise TypeError("shape has no text frame")
        frame = target.text_frame
    elif hasattr(target, "_txBody") and hasattr(target, "paragraphs"):
        frame = target
    else:
        raise TypeError("target must be a python-pptx shape or text frame")
    body = frame._txBody
    _check_formatting(body)
    originals = list(body.findall(qn("a:p")))
    if not originals:
        raise UnsafeTextStructureError("Text frame has no paragraph")
    replacements = []
    for index, content in enumerate(text.split("\n")):
        template = originals[min(index, len(originals) - 1)]
        paragraph = deepcopy(template)
        runs = template.findall(qn("a:r"))
        first_style = runs[0].find(qn("a:rPr")) if runs else None
        for child in list(paragraph):
            if child.tag not in (qn("a:pPr"), qn("a:endParaRPr")):
                paragraph.remove(child)
        end = paragraph.find(qn("a:endParaRPr"))
        def append_before_end(element):
            if end is None:
                paragraph.append(element)
            else:
                end.addprevious(element)
        for line_index, line in enumerate(content.split("\v")):
            if line_index:
                append_before_end(OxmlElement("a:br"))
            run = OxmlElement("a:r")
            if first_style is not None:
                run.append(deepcopy(first_style))
            literal = OxmlElement("a:t")
            literal.text = line
            run.append(literal)
            append_before_end(run)
        _check_formatting(paragraph)
        replacements.append(paragraph)
    # No mutation happens until every new paragraph has been built successfully.
    for paragraph in replacements:
        originals[0].addprevious(paragraph)
    for paragraph in originals:
        body.remove(paragraph)
