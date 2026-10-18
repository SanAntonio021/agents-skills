#!/usr/bin/env python
"""Single production write boundary for ``word/styles.xml``.

The normalizer deliberately keeps the XML tree as a caller-owned object.  A
caller supplies the transformed XML bytes and this module validates the
candidate before it is placed back into a DOCX package.  The original XML
declaration, outer whitespace, namespace declaration order, and attribute
name order are retained; unchanged input is returned byte-for-byte.
"""

from __future__ import annotations

import argparse
import ast
import copy
import json
import re
from pathlib import Path
from typing import Any, Iterable, Mapping

from lxml import etree


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
MC_NS = "http://schemas.openxmlformats.org/markup-compatibility/2006"
W = f"{{{W_NS}}}"
MC = f"{{{MC_NS}}}"
STYLE_ID = f"{W}styleId"
VALUE = f"{W}val"
STYLE_REFERENCE_NAMES = {
    "basedOn",
    "link",
    "next",
    "numStyleLink",
    "pStyle",
    "rStyle",
    "styleLink",
    "tblStyle",
}
_ASCII_WHITESPACE = b" \t\r\n"


class StylesNormalizationError(ValueError):
    """Raised when a styles part cannot pass the production write contract."""


def _parser() -> etree.XMLParser:
    return etree.XMLParser(
        resolve_entities=False,
        no_network=True,
        remove_blank_text=False,
        strip_cdata=False,
        huge_tree=True,
    )


def parse_styles_xml(payload: bytes | str) -> etree._Element:
    """Parse a styles part without allowing network access or blank removal."""

    data = payload.encode("utf-8") if isinstance(payload, str) else payload
    try:
        root = etree.fromstring(data, parser=_parser())
    except (etree.XMLSyntaxError, TypeError) as exc:
        raise StylesNormalizationError(f"word/styles.xml is not well-formed XML: {exc}") from exc
    qname = etree.QName(root)
    if qname.namespace != W_NS or qname.localname != "styles":
        raise StylesNormalizationError("word/styles.xml root must be w:styles")
    if root.getroottree().docinfo.doctype:
        raise StylesNormalizationError("word/styles.xml must not contain a document type declaration")
    return root


def iter_style_nodes(root: etree._Element) -> Iterable[etree._Element]:
    """Yield styles recursively, including styles in mc:AlternateContent."""

    for element in root.iter():
        if element.tag == f"{W}style":
            yield element


def collect_style_ids(root: etree._Element) -> dict[str, etree._Element]:
    """Return style definitions and reject duplicate IDs at every nesting level."""

    styles: dict[str, etree._Element] = {}
    for style in iter_style_nodes(root):
        style_id = style.get(STYLE_ID)
        if not style_id:
            raise StylesNormalizationError("A w:style definition has no w:styleId")
        if style_id in styles:
            raise StylesNormalizationError(f"Duplicate style definition: {style_id}")
        styles[style_id] = style
    return styles


def iter_style_references(root: etree._Element) -> Iterable[tuple[etree._Element, str]]:
    """Yield all Word style references, including nested AlternateContent branches."""

    for element in root.iter():
        # Comments, processing instructions, and entity nodes do not have a
        # string QName.  They can occur in an OOXML part and must not make the
        # validator crash while walking the tree.
        if not isinstance(element.tag, str):
            continue
        qname = etree.QName(element)
        if qname.namespace != W_NS or qname.localname not in STYLE_REFERENCE_NAMES:
            continue
        value = element.get(VALUE)
        if value:
            yield element, value


def _xml_entries(entries: Mapping[str, bytes] | None) -> Iterable[tuple[str, bytes]]:
    if not entries:
        return
    for name, payload in entries.items():
        if name.lower().endswith(".xml") and isinstance(payload, bytes):
            yield name, payload


def unresolved_style_references(
    styles_root: etree._Element,
    package_entries: Mapping[str, bytes] | None = None,
) -> dict[str, list[str]]:
    """Return unresolved references by package part.

    ``package_entries`` is optional for callers that only have a styles part;
    package-level validation is used by the DOCX remapping path.
    """

    definitions = set(collect_style_ids(styles_root))
    unresolved: dict[str, list[str]] = {}
    local_refs = sorted({value for _, value in iter_style_references(styles_root)})
    missing = sorted(set(local_refs) - definitions)
    if missing:
        unresolved["word/styles.xml"] = missing
    for name, payload in _xml_entries(package_entries):
        if name == "word/styles.xml":
            continue
        try:
            root = etree.fromstring(payload, parser=_parser())
        except etree.XMLSyntaxError:
            continue
        refs = sorted({value for _, value in iter_style_references(root)})
        missing = sorted(set(refs) - definitions)
        if missing:
            unresolved[name] = missing
    return unresolved


def validate_styles_xml(
    payload: bytes,
    *,
    package_entries: Mapping[str, bytes] | None = None,
) -> dict[str, Any]:
    """Validate duplicate IDs and all available style references."""

    root = parse_styles_xml(payload)
    definitions = collect_style_ids(root)
    unresolved = unresolved_style_references(root, package_entries)
    if unresolved:
        raise StylesNormalizationError(
            "Unresolved Word style references: " + json.dumps(unresolved, ensure_ascii=False, sort_keys=True)
        )
    return {
        "status": "PASS",
        "style_count": len(definitions),
        "alternate_content": sum(1 for _ in root.iter(f"{MC}AlternateContent")),
    }


def _encoding(payload: bytes) -> str:
    match = re.search(rb"encoding=['\"]([^'\"]+)['\"]", payload[:256], re.IGNORECASE)
    return match.group(1).decode("ascii", errors="replace") if match else "UTF-8"


def _skip_whitespace(payload: bytes, index: int) -> int:
    while index < len(payload) and payload[index] in _ASCII_WHITESPACE:
        index += 1
    return index


def _scan_tag(payload: bytes, start: int) -> tuple[int, bytes, bool, bool]:
    """Return the end, name, closing flag, and self-closing flag for one tag."""

    if start >= len(payload) or payload[start] != ord("<"):
        raise StylesNormalizationError("word/styles.xml contains an invalid XML tag")
    index = start + 1
    closing = index < len(payload) and payload[index] == ord("/")
    if closing:
        index += 1
    name_start = index
    while index < len(payload) and payload[index] not in b" \t\r\n/>":
        index += 1
    if index == name_start:
        raise StylesNormalizationError("word/styles.xml contains an unnamed XML tag")
    name = payload[name_start:index]

    quote: int | None = None
    while index < len(payload):
        byte = payload[index]
        if quote is None and byte in (ord("'"), ord('"')):
            quote = byte
        elif quote == byte:
            quote = None
        elif quote is None and byte == ord(">"):
            before_close = index - 1
            while before_close > start and payload[before_close] in _ASCII_WHITESPACE:
                before_close -= 1
            return (
                index + 1,
                name,
                closing,
                not closing and payload[before_close] == ord("/"),
            )
        index += 1
    raise StylesNormalizationError("word/styles.xml root start tag is incomplete")


def _skip_markup(payload: bytes, index: int) -> int:
    if payload.startswith(b"<!--", index):
        end = payload.find(b"-->", index + 4)
        if end < 0:
            raise StylesNormalizationError("word/styles.xml contains an incomplete XML comment")
        return end + 3
    if payload.startswith(b"<![CDATA[", index):
        end = payload.find(b"]]>", index + 9)
        if end < 0:
            raise StylesNormalizationError("word/styles.xml contains an incomplete CDATA section")
        return end + 3
    if payload.startswith(b"<?", index):
        end = payload.find(b"?>", index + 2)
        if end < 0:
            raise StylesNormalizationError("word/styles.xml contains an incomplete processing instruction")
        return end + 2
    raise StylesNormalizationError("word/styles.xml contains unsupported declaration markup")


def _root_bounds(payload: bytes) -> tuple[int, int, bytes]:
    """Locate the actual root element without matching lookalikes in comments."""

    if payload.startswith((b"\xff\xfe", b"\xfe\xff", b"\xff\xfe\x00\x00", b"\x00\x00\xfe\xff")):
        raise StylesNormalizationError(
            "word/styles.xml must use an ASCII-compatible encoding for byte-preserving normalization"
        )

    index = 3 if payload.startswith(b"\xef\xbb\xbf") else 0
    index = _skip_whitespace(payload, index)
    if payload.startswith(b"<?xml", index):
        index = _skip_markup(payload, index)

    while True:
        index = _skip_whitespace(payload, index)
        if payload.startswith(b"<!--", index) or payload.startswith(b"<?", index):
            index = _skip_markup(payload, index)
            continue
        break

    start = index
    start_end, root_name, closing, self_closing = _scan_tag(payload, start)
    if closing or root_name.split(b":")[-1] != b"styles":
        raise StylesNormalizationError("word/styles.xml root start tag could not be located")
    if self_closing:
        return start, start_end, payload[start:start_end]

    depth = 1
    index = start_end
    while depth:
        next_tag = payload.find(b"<", index)
        if next_tag < 0:
            raise StylesNormalizationError("word/styles.xml closing tag is missing")
        if payload.startswith((b"<!--", b"<![CDATA[", b"<?"), next_tag):
            index = _skip_markup(payload, next_tag)
            continue
        if payload.startswith(b"<!", next_tag):
            raise StylesNormalizationError("word/styles.xml contains unsupported declaration markup")
        tag_end, _, closing, self_closing = _scan_tag(payload, next_tag)
        if closing:
            depth -= 1
        elif not self_closing:
            depth += 1
        index = tag_end

    return start, index, payload[start:start_end]


def _attribute_name_order(start_tag: bytes) -> tuple[str, ...]:
    # The order check intentionally ignores values and whitespace.  lxml keeps
    # the order of existing attributes; this catches a serializer that silently
    # rebuilds a namespace/attribute table in a different order.
    index = 1
    while index < len(start_tag) and start_tag[index] not in b" \t\r\n/>":
        index += 1
    names: list[str] = []
    while index < len(start_tag):
        index = _skip_whitespace(start_tag, index)
        if index >= len(start_tag) or start_tag[index] in (ord("/"), ord(">")):
            break
        name_start = index
        while index < len(start_tag) and start_tag[index] not in b" \t\r\n=/>":
            index += 1
        if index == name_start:
            raise StylesNormalizationError("word/styles.xml has an invalid root attribute")
        names.append(start_tag[name_start:index].decode("utf-8", errors="replace"))
        index = _skip_whitespace(start_tag, index)
        if index >= len(start_tag) or start_tag[index] != ord("="):
            raise StylesNormalizationError("word/styles.xml root attribute is missing '='")
        index = _skip_whitespace(start_tag, index + 1)
        if index >= len(start_tag) or start_tag[index] not in (ord("'"), ord('"')):
            raise StylesNormalizationError("word/styles.xml root attribute must be quoted")
        quote = start_tag[index]
        index = start_tag.find(bytes((quote,)), index + 1)
        if index < 0:
            raise StylesNormalizationError("word/styles.xml root attribute quote is incomplete")
        index += 1
    return tuple(names)


def _alternate_content_structure(root: etree._Element) -> tuple[bytes, ...]:
    """Return immutable markup-compatibility structure with styles made opaque."""

    signatures: list[bytes] = []
    for wrapper in root.iter(f"{MC}AlternateContent"):
        clone = copy.deepcopy(wrapper)
        for element in clone.iter():
            if not isinstance(element.tag, str):
                continue
            element.text = None
            element.tail = None
            if element.tag != f"{W}style":
                continue
            element.attrib.clear()
            for child in list(element):
                element.remove(child)
        signatures.append(etree.tostring(clone, method="c14n", with_comments=True))
    return tuple(signatures)


def _serialize_root(root: etree._Element, original: bytes) -> bytes:
    return etree.tostring(
        root,
        encoding=_encoding(original),
        xml_declaration=False,
        pretty_print=False,
        with_tail=False,
    )


def normalize_styles_xml(
    original: bytes,
    candidate: bytes,
    *,
    package_entries: Mapping[str, bytes] | None = None,
) -> bytes:
    """Validate and serialize a transformed styles part through one boundary."""

    validate_styles_xml(original)
    original_root = parse_styles_xml(original)
    candidate_root = parse_styles_xml(candidate)
    candidate_entries = dict(package_entries or {})
    candidate_entries["word/styles.xml"] = candidate
    validate_styles_xml(candidate, package_entries=candidate_entries)
    if original == candidate:
        return original

    original_start, original_end, original_tag = _root_bounds(original)
    _, _, candidate_tag = _root_bounds(candidate)
    if _attribute_name_order(original_tag) != _attribute_name_order(candidate_tag):
        raise StylesNormalizationError(
            "word/styles.xml namespace/attribute order changed during normalization"
        )
    if _alternate_content_structure(original_root) != _alternate_content_structure(candidate_root):
        raise StylesNormalizationError(
            "mc:AlternateContent structure changed during normalization"
        )

    serialized = _serialize_root(candidate_root, original)
    _, _, serialized_tag = _root_bounds(serialized)
    if _attribute_name_order(original_tag) != _attribute_name_order(serialized_tag):
        raise StylesNormalizationError(
            "word/styles.xml serializer changed namespace/attribute order"
        )
    # Retain the exact XML declaration and whitespace outside the root.  The
    # candidate root is the only region intentionally rewritten.
    normalized = original[:original_start] + serialized + original[original_end:]
    normalized_entries = dict(candidate_entries)
    normalized_entries["word/styles.xml"] = normalized
    validate_styles_xml(normalized, package_entries=normalized_entries)
    return normalized


def replace_styles_entry(
    entries: Mapping[str, bytes],
    candidate: bytes,
    *,
    original: bytes | None = None,
) -> dict[str, bytes]:
    """Return a package copy with its styles entry validated and replaced."""

    if "word/styles.xml" not in entries:
        raise StylesNormalizationError("DOCX package is missing word/styles.xml")
    source = entries["word/styles.xml"] if original is None else original
    prospective = dict(entries)
    prospective["word/styles.xml"] = candidate
    normalized = normalize_styles_xml(source, candidate, package_entries=prospective)
    prospective["word/styles.xml"] = normalized
    return prospective


def write_styles_xml(
    path: str | Path,
    original: bytes,
    candidate: bytes,
    *,
    package_entries: Mapping[str, bytes] | None = None,
) -> Path:
    """Write one standalone styles part after validation."""

    normalized = normalize_styles_xml(original, candidate, package_entries=package_entries)
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(normalized)
    return destination


def _literal_string(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _call_name(node: ast.AST) -> str:
    """Return the terminal name for a direct or attribute call."""

    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def _open_mode(node: ast.Call) -> str | None:
    """Return a literal ``open`` mode when the call supplies one."""

    mode_index = 0 if isinstance(node.func, ast.Attribute) else 1
    if len(node.args) > mode_index:
        return _literal_string(node.args[mode_index])
    for keyword in node.keywords:
        if keyword.arg == "mode":
            return _literal_string(keyword.value)
    return None


def _is_styles_path(value: str) -> bool:
    normalized = value.replace("\\", "/").lower().strip()
    return normalized == "word/styles.xml" or normalized.endswith("/word/styles.xml")


def _literal_path_expression(node: ast.AST) -> str | None:
    literal = _literal_string(node)
    if literal is not None:
        return literal
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Div)):
        left = _literal_path_expression(node.left)
        right = _literal_path_expression(node.right)
        if left is not None and right is not None:
            separator = "" if isinstance(node.op, ast.Add) else "/"
            return left + separator + right
    if isinstance(node, ast.Call) and _call_name(node.func) in {
        "Path",
        "PurePath",
        "PurePosixPath",
        "PureWindowsPath",
    }:
        if node.args:
            return _literal_path_expression(node.args[0])
    return None


def _is_styles_target(node: ast.AST, tainted: set[str]) -> bool:
    if isinstance(node, ast.Name) and node.id in tainted:
        return True
    value = _literal_path_expression(node)
    return value is not None and _is_styles_path(value)


def scan_production_style_writers(scripts_root: str | Path) -> list[dict[str, Any]]:
    """Find statically discoverable direct writes targeting ``word/styles.xml``.

    The scan is deliberately conservative. A path tainted by the literal
    styles member is considered a writer when it reaches ``write_bytes``,
    ``write_text``, ``writestr`` or ``open(..., 'w*')``. The normalizer itself
    is the only exempt production module; dynamic paths still need code review.
    """

    root = Path(scripts_root).resolve()
    violations: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*.py")):
        if path.name == Path(__file__).name or "__pycache__" in path.parts:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (OSError, SyntaxError) as exc:
            violations.append({"path": str(path), "line": 1, "kind": "parse", "detail": str(exc)})
            continue
        tainted: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                value = _literal_path_expression(node.value)
                if value is not None and _is_styles_path(value):
                    for target in node.targets:
                        if isinstance(target, ast.Name):
                            tainted.add(target.id)
                for target in node.targets:
                    if isinstance(target, ast.Subscript) and _is_styles_target(target.slice, tainted):
                        violations.append(
                            {"path": str(path), "line": node.lineno, "kind": "subscript", "detail": "unregistered styles writer"}
                        )
            elif isinstance(node, ast.AnnAssign):
                if isinstance(node.target, ast.Subscript) and _is_styles_target(node.target.slice, tainted):
                    violations.append(
                        {"path": str(path), "line": node.lineno, "kind": "subscript", "detail": "unregistered styles writer"}
                    )
            if not isinstance(node, ast.Call):
                continue
            function_name = _call_name(node.func)
            targets = list(node.args) + [keyword.value for keyword in node.keywords]
            if isinstance(node.func, ast.Attribute):
                targets.append(node.func.value)
            targets_styles = any(_is_styles_target(target, tainted) for target in targets)
            if function_name in {"write_bytes", "write_text", "writestr"} and targets_styles:
                violations.append(
                    {"path": str(path), "line": node.lineno, "kind": function_name, "detail": "unregistered styles writer"}
                )
            if function_name == "open" and targets_styles:
                mode = _open_mode(node)
                if mode and any(flag in mode for flag in ("w", "a", "+")):
                    violations.append(
                        {"path": str(path), "line": node.lineno, "kind": "open", "detail": "unregistered styles writer"}
                    )
    return violations


def assert_production_style_writer_registry(scripts_root: str | Path) -> None:
    violations = scan_production_style_writers(scripts_root)
    if violations:
        raise StylesNormalizationError(
            "Unregistered word/styles.xml writer(s): " + json.dumps(violations, ensure_ascii=False, sort_keys=True)
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate the DOCX styles.xml write boundary")
    parser.add_argument("--scripts-root", type=Path, default=Path(__file__).resolve().parent)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    violations = scan_production_style_writers(args.scripts_root)
    print(json.dumps({"status": "PASS" if not violations else "FAIL", "violations": violations}, ensure_ascii=False, indent=2))
    return 0 if not violations else 2


if __name__ == "__main__":
    raise SystemExit(main())
