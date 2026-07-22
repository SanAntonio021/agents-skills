from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from ooxml_common import (
    MAIN_NS,
    XML_NS,
    index_to_column,
    json_write,
    load_package,
    normalize_cell_ref,
    parse_xml,
    qn,
    resolve_sheet_parts,
    serialize_xml,
    sheet_indexes,
    split_cell_ref,
    worksheet_cells,
    write_package,
)


def insert_in_schema_order(root: ET.Element, element: ET.Element, before: set[str]) -> None:
    for index, child in enumerate(list(root)):
        local = child.tag.rsplit("}", 1)[-1]
        if local in before:
            root.insert(index, element)
            return
    root.append(element)


def get_or_create_row(sheet_data: ET.Element, row_number: int) -> ET.Element:
    rows = sheet_data.findall(qn(MAIN_NS, "row"))
    for row in rows:
        current = int(row.attrib.get("r", "0"))
        if current == row_number:
            return row
        if current > row_number:
            created = ET.Element(qn(MAIN_NS, "row"), {"r": str(row_number)})
            sheet_data.insert(list(sheet_data).index(row), created)
            return created
    created = ET.SubElement(sheet_data, qn(MAIN_NS, "row"), {"r": str(row_number)})
    return created


def get_or_create_cell(
    sheet_data: ET.Element, ref: str, allow_new_cells: bool
) -> tuple[ET.Element, bool]:
    ref = normalize_cell_ref(ref)
    existing = worksheet_cells(sheet_data).get(ref)
    if existing is not None:
        return existing, False
    if not allow_new_cells:
        raise KeyError(f"Cell does not exist: {ref}")
    row_number, column_number = split_cell_ref(ref)
    row = get_or_create_row(sheet_data, row_number)
    created = ET.Element(qn(MAIN_NS, "c"), {"r": ref})
    for index, cell in enumerate(row.findall(qn(MAIN_NS, "c"))):
        current_ref = cell.attrib.get("r")
        if current_ref and split_cell_ref(current_ref)[1] > column_number:
            row.insert(index, created)
            return created, True
    row.append(created)
    return created, True


def clear_cell_children(cell: ET.Element) -> None:
    for child in list(cell):
        if child.tag in {
            qn(MAIN_NS, "f"),
            qn(MAIN_NS, "v"),
            qn(MAIN_NS, "is"),
        }:
            cell.remove(child)


def set_cell(cell: ET.Element, patch: dict[str, Any]) -> None:
    kind = patch.get("kind")
    if kind not in {"string", "number", "boolean", "blank", "formula"}:
        raise ValueError(f"Unsupported cell kind: {kind}")
    current_formula = cell.find(qn(MAIN_NS, "f"))
    if kind == "formula" and current_formula is not None:
        formula_type = current_formula.attrib.get("t")
        if formula_type in {"shared", "array", "dataTable"}:
            raise ValueError(
                f"Refusing to rewrite {formula_type} formula at {cell.attrib.get('r')}"
            )
    clear_cell_children(cell)

    if kind == "blank":
        cell.attrib.pop("t", None)
        return

    if kind == "string":
        value = patch.get("value")
        if not isinstance(value, str):
            raise TypeError("String cell value must be a string")
        cell.attrib["t"] = "inlineStr"
        inline = ET.SubElement(cell, qn(MAIN_NS, "is"))
        text = ET.SubElement(inline, qn(MAIN_NS, "t"))
        if value != value.strip() or "\n" in value:
            text.attrib[qn(XML_NS, "space")] = "preserve"
        text.text = value
        return

    if kind == "number":
        value = patch.get("value")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError("Number cell value must be a JSON number")
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("Number cell value must be finite")
        cell.attrib.pop("t", None)
        ET.SubElement(cell, qn(MAIN_NS, "v")).text = str(value)
        return

    if kind == "boolean":
        value = patch.get("value")
        if not isinstance(value, bool):
            raise TypeError("Boolean cell value must be true or false")
        cell.attrib["t"] = "b"
        ET.SubElement(cell, qn(MAIN_NS, "v")).text = "1" if value else "0"
        return

    formula_text = patch.get("formula")
    if not isinstance(formula_text, str) or not formula_text.strip():
        raise TypeError("Formula must be a nonempty string")
    formula_text = formula_text[1:] if formula_text.startswith("=") else formula_text
    ET.SubElement(cell, qn(MAIN_NS, "f")).text = formula_text
    result_type = patch.get("result_type", "number")
    type_map = {"number": None, "string": "str", "boolean": "b", "error": "e"}
    if result_type not in type_map:
        raise ValueError(f"Unsupported formula result_type: {result_type}")
    if type_map[result_type] is None:
        cell.attrib.pop("t", None)
    else:
        cell.attrib["t"] = type_map[result_type]
    if "cached" in patch:
        cached = patch["cached"]
        if cached is not None:
            if result_type == "boolean":
                cached_text = "1" if bool(cached) else "0"
            else:
                cached_text = str(cached)
            ET.SubElement(cell, qn(MAIN_NS, "v")).text = cached_text


def update_dimension(root: ET.Element) -> None:
    cells = worksheet_cells(root)
    if not cells:
        return
    positions = [split_cell_ref(ref) for ref in cells]
    min_row = min(row for row, _ in positions)
    max_row = max(row for row, _ in positions)
    min_col = min(column for _, column in positions)
    max_col = max(column for _, column in positions)
    dimension_ref = (
        f"{index_to_column(min_col)}{min_row}:{index_to_column(max_col)}{max_row}"
    )
    dimension = root.find(qn(MAIN_NS, "dimension"))
    if dimension is None:
        dimension = ET.Element(qn(MAIN_NS, "dimension"))
        insert_in_schema_order(root, dimension, {"sheetViews", "sheetFormatPr", "cols", "sheetData"})
    dimension.attrib["ref"] = dimension_ref


def patch_row_heights(root: ET.Element, heights: dict[str, Any]) -> list[int]:
    sheet_data = root.find(qn(MAIN_NS, "sheetData"))
    if sheet_data is None:
        raise ValueError("Worksheet has no sheetData")
    changed: list[int] = []
    for raw_row, raw_height in heights.items():
        row_number = int(raw_row)
        height = float(raw_height)
        if row_number < 1 or height <= 0:
            raise ValueError(f"Invalid row height: {raw_row}={raw_height}")
        row = get_or_create_row(sheet_data, row_number)
        row.attrib["ht"] = format(height, "g")
        row.attrib["customHeight"] = "1"
        changed.append(row_number)
    return changed


def patch_data_validation(root: ET.Element, spec: dict[str, Any]) -> None:
    container = root.find(qn(MAIN_NS, "dataValidations"))
    if container is None:
        raise ValueError("Worksheet has no dataValidations collection")
    items = container.findall(qn(MAIN_NS, "dataValidation"))
    required = spec.get("require_count")
    if required is not None and len(items) != int(required):
        raise ValueError(
            f"Expected {required} data validations, found {len(items)}"
        )
    index = int(spec.get("index", 0))
    if index < 0 or index >= len(items):
        raise IndexError(f"Data validation index out of range: {index}")
    sqref = spec.get("sqref")
    if not isinstance(sqref, str) or not sqref.strip():
        raise ValueError("data_validation.sqref must be nonempty")
    items[index].attrib["sqref"] = sqref
    container.attrib["count"] = str(len(items))


def patch_page_setup(root: ET.Element, spec: dict[str, Any]) -> None:
    page_setup = root.find(qn(MAIN_NS, "pageSetup"))
    if page_setup is None:
        page_setup = ET.Element(qn(MAIN_NS, "pageSetup"))
        insert_in_schema_order(root, page_setup, {"headerFooter", "rowBreaks", "colBreaks", "extLst"})
    for key in ("orientation", "paperSize", "fitToWidth", "fitToHeight", "scale"):
        if key not in spec:
            continue
        value = spec[key]
        if value is None:
            page_setup.attrib.pop(key, None)
        else:
            page_setup.attrib[key] = str(value)
    if "fitToPage" in spec:
        sheet_pr = root.find(qn(MAIN_NS, "sheetPr"))
        if sheet_pr is None:
            sheet_pr = ET.Element(qn(MAIN_NS, "sheetPr"))
            root.insert(0, sheet_pr)
        setup_pr = sheet_pr.find(qn(MAIN_NS, "pageSetUpPr"))
        if setup_pr is None:
            setup_pr = ET.SubElement(sheet_pr, qn(MAIN_NS, "pageSetUpPr"))
        setup_pr.attrib["fitToPage"] = "1" if spec["fitToPage"] else "0"


def patch_row_breaks(root: ET.Element, breaks: list[Any]) -> None:
    existing = root.find(qn(MAIN_NS, "rowBreaks"))
    if existing is not None:
        root.remove(existing)
    ids = [int(value) for value in breaks]
    if not ids:
        return
    if any(value < 1 for value in ids) or len(ids) != len(set(ids)):
        raise ValueError("row_breaks must contain unique positive row numbers")
    container = ET.Element(
        qn(MAIN_NS, "rowBreaks"),
        {"count": str(len(ids)), "manualBreakCount": str(len(ids))},
    )
    for value in sorted(ids):
        ET.SubElement(
            container,
            qn(MAIN_NS, "brk"),
            {"id": str(value), "min": "0", "max": "16383", "man": "1"},
        )
    insert_in_schema_order(root, container, {"colBreaks", "extLst"})


def quote_sheet_name(name: str) -> str:
    return "'" + name.replace("'", "''") + "'"


def set_defined_name(
    workbook: ET.Element, sheet_name: str, sheet_index: int, name: str, value: str
) -> None:
    container = workbook.find(qn(MAIN_NS, "definedNames"))
    if container is None:
        container = ET.Element(qn(MAIN_NS, "definedNames"))
        children = list(workbook)
        insert_at = len(children)
        for index, child in enumerate(children):
            if child.tag.rsplit("}", 1)[-1] in {"calcPr", "extLst"}:
                insert_at = index
                break
        workbook.insert(insert_at, container)
    target = None
    for item in container.findall(qn(MAIN_NS, "definedName")):
        if item.attrib.get("name") == name and item.attrib.get("localSheetId") == str(sheet_index):
            target = item
            break
    if target is None:
        target = ET.SubElement(
            container,
            qn(MAIN_NS, "definedName"),
            {"name": name, "localSheetId": str(sheet_index)},
        )
    target.text = f"{quote_sheet_name(sheet_name)}!{value}"


def patch_workbook(
    source: Path, output: Path, spec: dict[str, Any], allow_new_cells: bool
) -> dict[str, Any]:
    entries, _, _ = load_package(source)
    sheet_parts = resolve_sheet_parts(entries)
    indexes = sheet_indexes(entries)
    replacements: dict[str, bytes] = {}
    report: dict[str, Any] = {"changed_sheets": {}, "changed_package_entries": []}

    workbook = parse_xml(entries["xl/workbook.xml"])
    workbook_changed = False
    sheet_specs = spec.get("sheets")
    if not isinstance(sheet_specs, dict) or not sheet_specs:
        raise ValueError("Spec must contain a nonempty sheets object")

    for sheet_name, sheet_spec in sheet_specs.items():
        if sheet_name not in sheet_parts:
            raise KeyError(f"Worksheet not found: {sheet_name}")
        if not isinstance(sheet_spec, dict):
            raise TypeError(f"Worksheet spec must be an object: {sheet_name}")
        part = sheet_parts[sheet_name]
        root = parse_xml(entries[part])
        sheet_data = root.find(qn(MAIN_NS, "sheetData"))
        if sheet_data is None:
            raise ValueError(f"Worksheet has no sheetData: {sheet_name}")
        changed_cells: list[str] = []
        created_cells = False
        for ref, cell_patch in sheet_spec.get("cells", {}).items():
            if not isinstance(cell_patch, dict):
                raise TypeError(f"Cell patch must be an object: {sheet_name}!{ref}")
            cell, created = get_or_create_cell(sheet_data, ref, allow_new_cells)
            set_cell(cell, cell_patch)
            changed_cells.append(normalize_cell_ref(ref))
            created_cells = created_cells or created
        if created_cells:
            update_dimension(root)

        changed_rows = patch_row_heights(root, sheet_spec.get("row_heights", {}))
        features: list[str] = []
        if "data_validation" in sheet_spec:
            patch_data_validation(root, sheet_spec["data_validation"])
            features.append("data_validation")
        if "page_setup" in sheet_spec:
            patch_page_setup(root, sheet_spec["page_setup"])
            features.append("page_setup")
        if "row_breaks" in sheet_spec:
            patch_row_breaks(root, sheet_spec["row_breaks"])
            features.append("row_breaks")
        if "print_area" in sheet_spec:
            set_defined_name(
                workbook,
                sheet_name,
                indexes[sheet_name],
                "_xlnm.Print_Area",
                str(sheet_spec["print_area"]),
            )
            workbook_changed = True
            features.append("print_area")
        if "print_titles" in sheet_spec:
            set_defined_name(
                workbook,
                sheet_name,
                indexes[sheet_name],
                "_xlnm.Print_Titles",
                str(sheet_spec["print_titles"]),
            )
            workbook_changed = True
            features.append("print_titles")

        serialized = serialize_xml(root)
        if serialized != entries[part]:
            replacements[part] = serialized
        report["changed_sheets"][sheet_name] = {
            "cells": sorted(changed_cells, key=split_cell_ref),
            "row_heights": sorted(changed_rows),
            "features": features,
        }

    if workbook_changed:
        replacements["xl/workbook.xml"] = serialize_xml(workbook)
    write_package(source, output, replacements)
    report["changed_package_entries"] = sorted(replacements)
    report["output"] = str(output.resolve())
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply targeted OOXML workbook patches")
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--allow-new-cells", action="store_true")
    parser.add_argument("--json-out", type=Path)
    args = parser.parse_args()
    try:
        spec = json.loads(args.spec.read_text(encoding="utf-8-sig"))
        report = patch_workbook(args.source, args.output, spec, args.allow_new_cells)
        print(json_write(report, args.json_out))
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
