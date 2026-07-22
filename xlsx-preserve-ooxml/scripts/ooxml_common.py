from __future__ import annotations

import copy
import hashlib
import io
import json
import os
import posixpath
import re
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Iterable
from xml.etree import ElementTree as ET


MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
DOC_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
XML_NS = "http://www.w3.org/XML/1998/namespace"

CELL_RE = re.compile(r"^\$?([A-Za-z]{1,3})\$?([1-9][0-9]*)$")
FORMULA_ERRORS = {
    "#NULL!",
    "#DIV/0!",
    "#VALUE!",
    "#REF!",
    "#NAME?",
    "#NUM!",
    "#N/A",
    "#GETTING_DATA",
    "#SPILL!",
    "#CALC!",
    "#FIELD!",
}


def qn(namespace: str, local: str) -> str:
    return f"{{{namespace}}}{local}"


def parse_xml(data: bytes) -> ET.Element:
    for _, item in ET.iterparse(io.BytesIO(data), events=("start-ns",)):
        prefix, uri = item
        if prefix not in {"xml", "xmlns"}:
            try:
                ET.register_namespace(prefix or "", uri)
            except ValueError:
                pass
    return ET.fromstring(data)


def serialize_xml(root: ET.Element) -> bytes:
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def load_package(path: Path) -> tuple[dict[str, bytes], list[zipfile.ZipInfo], bytes]:
    if not path.is_file():
        raise FileNotFoundError(path)
    if not zipfile.is_zipfile(path):
        raise ValueError(f"Not a valid OOXML ZIP package: {path}")
    with zipfile.ZipFile(path, "r") as archive:
        bad = archive.testzip()
        if bad:
            raise ValueError(f"Corrupt ZIP entry: {bad}")
        infos = archive.infolist()
        entries = {info.filename: archive.read(info.filename) for info in infos}
        comment = archive.comment
    return entries, infos, comment


def _copy_zip_info(info: zipfile.ZipInfo) -> zipfile.ZipInfo:
    clone = zipfile.ZipInfo(info.filename, info.date_time)
    clone.compress_type = info.compress_type
    clone.comment = info.comment
    clone.extra = info.extra
    clone.create_system = info.create_system
    clone.create_version = info.create_version
    clone.extract_version = info.extract_version
    clone.flag_bits = info.flag_bits
    clone.volume = info.volume
    clone.internal_attr = info.internal_attr
    clone.external_attr = info.external_attr
    return clone


def write_package(
    source: Path,
    output: Path,
    replacements: dict[str, bytes],
    added_entries: dict[str, bytes] | None = None,
) -> None:
    source = source.resolve()
    output = output.resolve()
    if source == output:
        raise ValueError("Source and output paths must differ")
    if output.exists():
        raise FileExistsError(f"Output already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    entries, infos, comment = load_package(source)
    unknown = set(replacements) - set(entries)
    if unknown:
        raise KeyError(f"Replacement entries not found: {sorted(unknown)}")
    added_entries = added_entries or {}
    duplicate_additions = set(added_entries) & set(entries)
    if duplicate_additions:
        raise KeyError(f"Added entries already exist: {sorted(duplicate_additions)}")

    temp_handle = tempfile.NamedTemporaryFile(
        prefix=f".{output.name}.", suffix=".tmp", dir=output.parent, delete=False
    )
    temp_path = Path(temp_handle.name)
    temp_handle.close()
    try:
        with zipfile.ZipFile(temp_path, "w") as archive:
            archive.comment = comment
            for info in infos:
                data = replacements.get(info.filename, entries[info.filename])
                archive.writestr(_copy_zip_info(info), data)
            for name, data in added_entries.items():
                archive.writestr(name, data, compress_type=zipfile.ZIP_DEFLATED)
        with zipfile.ZipFile(temp_path, "r") as archive:
            bad = archive.testzip()
            if bad:
                raise ValueError(f"Generated ZIP is corrupt at entry: {bad}")
        with temp_path.open("rb") as src, output.open("xb") as dst:
            shutil.copyfileobj(src, dst)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def resolve_sheet_parts(entries: dict[str, bytes]) -> dict[str, str]:
    workbook_name = "xl/workbook.xml"
    rels_name = "xl/_rels/workbook.xml.rels"
    if workbook_name not in entries or rels_name not in entries:
        raise ValueError("Workbook parts are missing")
    workbook = parse_xml(entries[workbook_name])
    rels = parse_xml(entries[rels_name])
    targets = {
        rel.attrib["Id"]: rel.attrib["Target"]
        for rel in rels.findall(qn(PKG_REL_NS, "Relationship"))
    }
    result: dict[str, str] = {}
    sheets = workbook.find(qn(MAIN_NS, "sheets"))
    if sheets is None:
        return result
    for sheet in sheets.findall(qn(MAIN_NS, "sheet")):
        rid = sheet.attrib.get(qn(DOC_REL_NS, "id"))
        name = sheet.attrib.get("name")
        if not rid or not name or rid not in targets:
            continue
        target = targets[rid]
        if target.startswith("/"):
            part = target.lstrip("/")
        else:
            part = posixpath.normpath(posixpath.join("xl", target))
        result[name] = part
    return result


def sheet_indexes(entries: dict[str, bytes]) -> dict[str, int]:
    workbook = parse_xml(entries["xl/workbook.xml"])
    sheets = workbook.find(qn(MAIN_NS, "sheets"))
    if sheets is None:
        return {}
    return {
        sheet.attrib["name"]: index
        for index, sheet in enumerate(sheets.findall(qn(MAIN_NS, "sheet")))
    }


def column_to_index(column: str) -> int:
    value = 0
    for char in column.upper():
        if not "A" <= char <= "Z":
            raise ValueError(f"Invalid column: {column}")
        value = value * 26 + ord(char) - ord("A") + 1
    return value


def index_to_column(index: int) -> str:
    if index < 1:
        raise ValueError("Column index must be positive")
    chars: list[str] = []
    while index:
        index, remainder = divmod(index - 1, 26)
        chars.append(chr(ord("A") + remainder))
    return "".join(reversed(chars))


def split_cell_ref(ref: str) -> tuple[int, int]:
    match = CELL_RE.fullmatch(ref)
    if not match:
        raise ValueError(f"Invalid A1 cell reference: {ref}")
    return int(match.group(2)), column_to_index(match.group(1))


def normalize_cell_ref(ref: str) -> str:
    row, column = split_cell_ref(ref)
    return f"{index_to_column(column)}{row}"


def expand_cell_range(value: str) -> list[str]:
    cleaned = value.replace("$", "")
    if ":" not in cleaned:
        return [normalize_cell_ref(cleaned)]
    start, end = cleaned.split(":", 1)
    start_row, start_col = split_cell_ref(start)
    end_row, end_col = split_cell_ref(end)
    if start_row > end_row or start_col > end_col:
        raise ValueError(f"Reversed range: {value}")
    return [
        f"{index_to_column(column)}{row}"
        for row in range(start_row, end_row + 1)
        for column in range(start_col, end_col + 1)
    ]


def parse_qualified_range(value: str) -> tuple[str, list[str]]:
    if "!" not in value:
        raise ValueError(f"Expected Sheet!A1 notation: {value}")
    sheet, cells = value.rsplit("!", 1)
    if sheet.startswith("'") and sheet.endswith("'"):
        sheet = sheet[1:-1].replace("''", "'")
    return sheet, expand_cell_range(cells)


def expand_row_range(value: str) -> list[int]:
    cleaned = value.replace("$", "")
    if ":" not in cleaned:
        row = int(cleaned)
        return [row]
    start, end = (int(item) for item in cleaned.split(":", 1))
    if start > end or start < 1:
        raise ValueError(f"Invalid row range: {value}")
    return list(range(start, end + 1))


def parse_qualified_rows(value: str) -> tuple[str, list[int]]:
    if "!" not in value:
        raise ValueError(f"Expected Sheet!row notation: {value}")
    sheet, rows = value.rsplit("!", 1)
    if sheet.startswith("'") and sheet.endswith("'"):
        sheet = sheet[1:-1].replace("''", "'")
    return sheet, expand_row_range(rows)


def shared_strings(entries: dict[str, bytes]) -> list[str]:
    data = entries.get("xl/sharedStrings.xml")
    if data is None:
        return []
    root = parse_xml(data)
    values: list[str] = []
    for item in root.findall(qn(MAIN_NS, "si")):
        values.append("".join(node.text or "" for node in item.iter(qn(MAIN_NS, "t"))))
    return values


def formula_signature(cell: ET.Element) -> dict[str, Any] | None:
    formula = cell.find(qn(MAIN_NS, "f"))
    if formula is None:
        return None
    return {
        "text": formula.text or "",
        "attributes": dict(sorted(formula.attrib.items())),
    }


def cached_value(cell: ET.Element) -> str | None:
    value = cell.find(qn(MAIN_NS, "v"))
    return None if value is None else (value.text or "")


def displayed_value(cell: ET.Element, strings: list[str]) -> str | None:
    cell_type = cell.attrib.get("t")
    if cell_type == "inlineStr":
        inline = cell.find(qn(MAIN_NS, "is"))
        if inline is None:
            return ""
        return "".join(node.text or "" for node in inline.iter(qn(MAIN_NS, "t")))
    value = cached_value(cell)
    if cell_type == "s" and value is not None:
        try:
            return strings[int(value)]
        except (ValueError, IndexError):
            return value
    return value


def worksheet_cells(root: ET.Element) -> dict[str, ET.Element]:
    result: dict[str, ET.Element] = {}
    for cell in root.iter(qn(MAIN_NS, "c")):
        ref = cell.attrib.get("r")
        if ref:
            result[normalize_cell_ref(ref)] = cell
    return result


def element_fingerprint(element: ET.Element | None) -> str | None:
    if element is None:
        return None
    clone = copy.deepcopy(element)
    return ET.tostring(clone, encoding="unicode")


def json_write(data: Any, path: Path | None = None) -> str:
    rendered = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True)
    if path is not None:
        if path.exists():
            raise FileExistsError(f"JSON output already exists: {path}")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(rendered + os.linesep, encoding="utf-8")
    return rendered


def flatten(values: Iterable[Iterable[Any]]) -> list[Any]:
    return [item for group in values for item in group]
