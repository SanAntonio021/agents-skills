from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import fnmatch
import json
import posixpath
import sys
import unicodedata
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from ooxml_common import (
    DOC_REL_NS,
    FORMULA_ERRORS,
    MAIN_NS,
    PKG_REL_NS,
    cached_value,
    displayed_value,
    formula_signature,
    has_formula_cache,
    index_to_column,
    json_write,
    load_package,
    parse_qualified_range,
    parse_qualified_rows,
    parse_xml,
    qn,
    resolve_sheet_parts,
    sha256_bytes,
    sha256_file,
    shared_strings,
    split_cell_ref,
    worksheet_cells,
)


FEATURE_TAGS = {
    "dimension": "dimension",
    "merges": "mergeCells",
    "data_validations": "dataValidations",
    "page_setup": "pageSetup",
    "page_margins": "pageMargins",
    "print_options": "printOptions",
    "sheet_properties": "sheetPr",
    "row_breaks": "rowBreaks",
    "column_breaks": "colBreaks",
    "columns": "cols",
    "conditional_formatting": "conditionalFormatting",
    "hyperlinks": "hyperlinks",
    "auto_filter": "autoFilter",
    "drawing": "drawing",
    "legacy_drawing": "legacyDrawing",
    "sheet_protection": "sheetProtection",
}

SHEET_NAME_FORBIDDEN_CHARS = set("/\\:*?[]")
MAX_SHEET_NAME_UTF16_UNITS = 31
SHEET_RELATIONSHIP_KINDS = {
    "worksheet",
    "chartsheet",
    "dialogsheet",
    "macrosheet",
    "intlmacrosheet",
}


def canonical_element(element: ET.Element | None) -> Any:
    if element is None:
        return None
    return {
        "tag": element.tag,
        "attributes": dict(sorted(element.attrib.items())),
        "text": element.text or "",
        "children": [canonical_element(child) for child in list(element)],
    }


def canonical_elements(elements: list[ET.Element]) -> list[Any]:
    return [canonical_element(element) for element in elements]


def row_records(root: ET.Element) -> tuple[dict[int, dict[str, str]], dict[int, dict[str, str]]]:
    heights: dict[int, dict[str, str]] = {}
    other: dict[int, dict[str, str]] = {}
    for row in root.iter(qn(MAIN_NS, "row")):
        if "r" not in row.attrib:
            continue
        row_number = int(row.attrib["r"])
        height_attrs = {
            key: row.attrib[key]
            for key in ("ht", "customHeight")
            if key in row.attrib
        }
        other_attrs = {
            key: value
            for key, value in sorted(row.attrib.items())
            if key not in {"r", "ht", "customHeight", "spans"}
        }
        if height_attrs:
            heights[row_number] = height_attrs
        if other_attrs:
            other[row_number] = other_attrs
    return heights, other


def range_bounds(value: str) -> tuple[int, int, int, int]:
    refs = value.replace("$", "").split(":")
    if len(refs) == 1:
        refs.append(refs[0])
    if len(refs) != 2:
        raise ValueError(f"Invalid cell range: {value}")
    start_row, start_col = split_cell_ref(refs[0])
    end_row, end_col = split_cell_ref(refs[1])
    if start_row > end_row or start_col > end_col:
        raise ValueError(f"Reversed cell range: {value}")
    return start_row, start_col, end_row, end_col


def range_intersection(left: str, right: str) -> str | None:
    left_start_row, left_start_col, left_end_row, left_end_col = range_bounds(left)
    right_start_row, right_start_col, right_end_row, right_end_col = range_bounds(right)
    start_row = max(left_start_row, right_start_row)
    start_col = max(left_start_col, right_start_col)
    end_row = min(left_end_row, right_end_row)
    end_col = min(left_end_col, right_end_col)
    if start_row > end_row or start_col > end_col:
        return None
    start = f"{index_to_column(start_col)}{start_row}"
    end = f"{index_to_column(end_col)}{end_row}"
    return start if start == end else f"{start}:{end}"


def relationship_part_name(owner_part: str) -> str:
    owner_dir = posixpath.dirname(owner_part)
    owner_name = posixpath.basename(owner_part)
    return posixpath.join(owner_dir, "_rels", f"{owner_name}.rels")


def resolve_relationship_target(owner_part: str, target: str) -> str:
    if target.startswith("/"):
        return target.lstrip("/")
    return posixpath.normpath(posixpath.join(posixpath.dirname(owner_part), target))


def relationship_owner_part(relationships_part: str) -> str | None:
    if relationships_part == "_rels/.rels":
        return ""
    parent = posixpath.dirname(relationships_part)
    if posixpath.basename(parent) != "_rels":
        return None
    relation_name = posixpath.basename(relationships_part)
    if not relation_name.endswith(".rels"):
        return None
    owner_name = relation_name[: -len(".rels")]
    owner_dir = posixpath.dirname(parent)
    return posixpath.join(owner_dir, owner_name) if owner_dir else owner_name


def workbook_issue(kind: str, message: str, **context: Any) -> dict[str, Any]:
    return {"kind": kind, "message": message, **context}


def inspect_workbook_structure(
    entries: dict[str, bytes], infos: list[Any]
) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    entry_counts = Counter(info.filename for info in infos)
    for name, count in sorted(entry_counts.items()):
        if count > 1:
            issues.append(
                workbook_issue(
                    "duplicate_package_entry",
                    f"OOXML ZIP package contains duplicate entry {name!r}",
                    entry=name,
                    count=count,
                )
            )

    workbook_name = "xl/workbook.xml"
    workbook_rels_name = "xl/_rels/workbook.xml.rels"
    if workbook_name not in entries:
        issues.append(
            workbook_issue(
                "missing_workbook_part",
                "OOXML package is missing xl/workbook.xml",
                entry=workbook_name,
            )
        )
        return {"sheet_count": 0, "visible_sheet_count": 0, "issues": issues}
    if workbook_rels_name not in entries:
        issues.append(
            workbook_issue(
                "missing_workbook_relationships",
                "OOXML package is missing xl/_rels/workbook.xml.rels",
                entry=workbook_rels_name,
            )
        )

    workbook = parse_xml(entries[workbook_name])
    sheets_container = workbook.find(qn(MAIN_NS, "sheets"))
    sheets = (
        []
        if sheets_container is None
        else list(sheets_container.findall(qn(MAIN_NS, "sheet")))
    )
    if sheets_container is None:
        issues.append(
            workbook_issue(
                "missing_sheets_container",
                "xl/workbook.xml is missing its sheets container",
            )
        )

    sheet_names: defaultdict[str, list[int]] = defaultdict(list)
    sheet_ids: defaultdict[str, list[int]] = defaultdict(list)
    sheet_relationship_ids: defaultdict[str, list[int]] = defaultdict(list)
    visible_sheet_count = 0
    for index, sheet in enumerate(sheets, start=1):
        name = sheet.attrib.get("name")
        if not name:
            issues.append(
                workbook_issue(
                    "missing_sheet_name",
                    f"Sheet {index} has no name attribute",
                    sheet_index=index,
                )
            )
        else:
            sheet_names[name.casefold()].append(index)
            utf16_units = len(name.encode("utf-16-le")) // 2
            if utf16_units > MAX_SHEET_NAME_UTF16_UNITS:
                issues.append(
                    workbook_issue(
                        "sheet_name_too_long",
                        f"Sheet {name!r} uses {utf16_units} UTF-16 units; Excel allows at most "
                        f"{MAX_SHEET_NAME_UTF16_UNITS}",
                        sheet=name,
                        sheet_index=index,
                        utf16_units=utf16_units,
                    )
                )
            for character in sorted(set(name) & SHEET_NAME_FORBIDDEN_CHARS):
                issues.append(
                    workbook_issue(
                        "invalid_sheet_name_character",
                        f"Sheet {name!r} contains Excel-forbidden character {character!r}",
                        sheet=name,
                        sheet_index=index,
                        character=character,
                    )
                )
            normalized_name = unicodedata.normalize("NFKC", name)
            for character in sorted(set(normalized_name) & SHEET_NAME_FORBIDDEN_CHARS):
                if character in name:
                    continue
                issues.append(
                    workbook_issue(
                        "excel_compatibility_issue",
                        f"Sheet {name!r} normalizes to {normalized_name!r}, which contains "
                        f"Excel-forbidden character {character!r}",
                        rule="sheet_name_nfkc_forbidden_character",
                        sheet=name,
                        sheet_index=index,
                        normalized_name=normalized_name,
                        character=character,
                    )
                )

        state = sheet.attrib.get("state", "visible")
        if state == "visible":
            visible_sheet_count += 1
        elif state not in {"hidden", "veryHidden"}:
            issues.append(
                workbook_issue(
                    "invalid_sheet_state",
                    f"Sheet {name!r} has unsupported state {state!r}",
                    sheet=name,
                    sheet_index=index,
                    state=state,
                )
            )

        sheet_id = sheet.attrib.get("sheetId")
        if not sheet_id:
            issues.append(
                workbook_issue(
                    "missing_sheet_id",
                    f"Sheet {name!r} has no sheetId attribute",
                    sheet=name,
                    sheet_index=index,
                )
            )
        else:
            sheet_ids[sheet_id].append(index)
            try:
                if int(sheet_id) < 1:
                    raise ValueError
            except ValueError:
                issues.append(
                    workbook_issue(
                        "invalid_sheet_id",
                        f"Sheet {name!r} has invalid sheetId {sheet_id!r}",
                        sheet=name,
                        sheet_index=index,
                        sheet_id=sheet_id,
                    )
                )

        relationship_id = sheet.attrib.get(qn(DOC_REL_NS, "id"))
        if not relationship_id:
            issues.append(
                workbook_issue(
                    "missing_sheet_relationship_id",
                    f"Sheet {name!r} has no relationship id",
                    sheet=name,
                    sheet_index=index,
                )
            )
        else:
            sheet_relationship_ids[relationship_id].append(index)

    for occurrences in sheet_names.values():
        if len(occurrences) > 1:
            first_name = sheets[occurrences[0] - 1].attrib.get("name", "")
            issues.append(
                workbook_issue(
                    "duplicate_sheet_name",
                    f"Sheet name {first_name!r} is duplicated (Excel names are case-insensitive)",
                    sheet=first_name,
                    sheet_indexes=occurrences,
                )
            )
    for sheet_id, occurrences in sorted(sheet_ids.items()):
        if len(occurrences) > 1:
            issues.append(
                workbook_issue(
                    "duplicate_sheet_id",
                    f"sheetId {sheet_id!r} is used by multiple sheets",
                    sheet_id=sheet_id,
                    sheet_indexes=occurrences,
                )
            )
    for relationship_id, occurrences in sorted(sheet_relationship_ids.items()):
        if len(occurrences) > 1:
            issues.append(
                workbook_issue(
                    "duplicate_sheet_relationship_id",
                    f"Relationship id {relationship_id!r} is used by multiple sheets",
                    relationship_id=relationship_id,
                    sheet_indexes=occurrences,
                )
            )
    if visible_sheet_count == 0:
        issues.append(
            workbook_issue(
                "no_visible_worksheets",
                "Workbook has no visible worksheet",
            )
        )

    for relationships_part in sorted(name for name in entries if name.endswith(".rels")):
        owner_part = relationship_owner_part(relationships_part)
        if owner_part is None:
            issues.append(
                workbook_issue(
                    "unrecognized_relationship_part",
                    f"Cannot determine the owner of relationship part {relationships_part!r}",
                    relationships_part=relationships_part,
                )
            )
            continue
        if owner_part and owner_part not in entries:
            issues.append(
                workbook_issue(
                    "missing_relationship_owner",
                    f"Relationship part {relationships_part!r} has missing owner {owner_part!r}",
                    relationships_part=relationships_part,
                    owner_part=owner_part,
                )
            )
        relationships = parse_xml(entries[relationships_part]).findall(
            qn(PKG_REL_NS, "Relationship")
        )
        relationship_ids: defaultdict[str, list[int]] = defaultdict(list)
        for index, relationship in enumerate(relationships, start=1):
            relationship_id = relationship.attrib.get("Id")
            if not relationship_id:
                issues.append(
                    workbook_issue(
                        "missing_relationship_id",
                        f"Relationship {index} in {relationships_part!r} has no Id",
                        relationships_part=relationships_part,
                        relationship_index=index,
                    )
                )
            else:
                relationship_ids[relationship_id].append(index)
            target = relationship.attrib.get("Target")
            if not target:
                issues.append(
                    workbook_issue(
                        "missing_relationship_target",
                        f"Relationship {relationship_id!r} in {relationships_part!r} has no Target",
                        relationships_part=relationships_part,
                        relationship_id=relationship_id,
                    )
                )
                continue
            if relationship.attrib.get("TargetMode") == "External":
                continue
            target_part = resolve_relationship_target(owner_part, target)
            if target_part not in entries:
                issues.append(
                    workbook_issue(
                        "missing_relationship_target",
                        f"Relationship {relationship_id!r} in {relationships_part!r} targets "
                        f"missing part {target_part!r}",
                        relationships_part=relationships_part,
                        relationship_id=relationship_id,
                        target=target_part,
                    )
                )
        for relationship_id, occurrences in sorted(relationship_ids.items()):
            if len(occurrences) > 1:
                issues.append(
                    workbook_issue(
                        "duplicate_relationship_id",
                        f"Relationship id {relationship_id!r} is duplicated in "
                        f"{relationships_part!r}",
                        relationships_part=relationships_part,
                        relationship_id=relationship_id,
                        relationship_indexes=occurrences,
                    )
                )

    if workbook_rels_name in entries:
        workbook_relationships = parse_xml(entries[workbook_rels_name]).findall(
            qn(PKG_REL_NS, "Relationship")
        )
        workbook_relationship_ids: defaultdict[str, list[ET.Element]] = defaultdict(list)
        for relationship in workbook_relationships:
            relationship_id = relationship.attrib.get("Id")
            if relationship_id:
                workbook_relationship_ids[relationship_id].append(relationship)
        for index, sheet in enumerate(sheets, start=1):
            name = sheet.attrib.get("name")
            relationship_id = sheet.attrib.get(qn(DOC_REL_NS, "id"))
            if not relationship_id:
                continue
            matching = workbook_relationship_ids.get(relationship_id, [])
            if not matching:
                issues.append(
                    workbook_issue(
                        "unresolved_sheet_relationship_id",
                        f"Sheet {name!r} references missing relationship id {relationship_id!r}",
                        sheet=name,
                        sheet_index=index,
                        relationship_id=relationship_id,
                    )
                )
            elif len(matching) > 1:
                issues.append(
                    workbook_issue(
                        "ambiguous_sheet_relationship_id",
                        f"Sheet {name!r} references duplicate relationship id {relationship_id!r}",
                        sheet=name,
                        sheet_index=index,
                        relationship_id=relationship_id,
                    )
                )
            elif matching[0].attrib.get("TargetMode") == "External":
                issues.append(
                    workbook_issue(
                        "external_sheet_relationship",
                        f"Sheet {name!r} points to external relationship {relationship_id!r}",
                        sheet=name,
                        sheet_index=index,
                        relationship_id=relationship_id,
                    )
                )
            else:
                relationship_type = matching[0].attrib.get("Type", "")
                relationship_kind = relationship_type.rsplit("/", 1)[-1]
                if relationship_kind not in SHEET_RELATIONSHIP_KINDS:
                    issues.append(
                        workbook_issue(
                            "invalid_sheet_relationship_type",
                            f"Sheet {name!r} references relationship {relationship_id!r} of "
                            f"non-sheet type {relationship_type!r}",
                            sheet=name,
                            sheet_index=index,
                            relationship_id=relationship_id,
                            relationship_type=relationship_type,
                        )
                    )

    workbook_views = workbook.find(qn(MAIN_NS, "bookViews"))
    if workbook_views is not None:
        for index, view in enumerate(workbook_views.findall(qn(MAIN_NS, "workbookView")), start=1):
            active_tab = view.attrib.get("activeTab")
            if active_tab is None:
                continue
            try:
                active_tab_index = int(active_tab)
            except ValueError:
                issues.append(
                    workbook_issue(
                        "invalid_active_tab",
                        f"Workbook view {index} has non-numeric activeTab {active_tab!r}",
                        view_index=index,
                        active_tab=active_tab,
                    )
                )
                continue
            if active_tab_index < 0 or active_tab_index >= len(sheets):
                issues.append(
                    workbook_issue(
                        "active_tab_out_of_range",
                        f"Workbook view {index} selects activeTab {active_tab_index}, but there are "
                        f"{len(sheets)} sheets",
                        view_index=index,
                        active_tab=active_tab_index,
                        sheet_count=len(sheets),
                    )
                )

    return {
        "sheet_count": len(sheets),
        "visible_sheet_count": visible_sheet_count,
        "issues": issues,
    }


def inspect_filter_topology(
    entries: dict[str, bytes], sheet_name: str, sheet_part: str, root: ET.Element
) -> dict[str, Any]:
    worksheet_filters: list[str] = []
    for element in root.findall(qn(MAIN_NS, "autoFilter")):
        ref = element.attrib.get("ref")
        if ref:
            range_bounds(ref)
            worksheet_filters.append(ref)

    tables: list[dict[str, Any]] = []
    table_parts = root.find(qn(MAIN_NS, "tableParts"))
    if table_parts is not None:
        rels_part = relationship_part_name(sheet_part)
        if rels_part not in entries:
            raise ValueError(
                f"Worksheet {sheet_name!r} declares tableParts but is missing {rels_part}"
            )
        rels_root = parse_xml(entries[rels_part])
        relationships = {
            relationship.attrib.get("Id"): relationship
            for relationship in rels_root.findall(qn(PKG_REL_NS, "Relationship"))
            if relationship.attrib.get("Id")
        }
        for index, table_part in enumerate(
            table_parts.findall(qn(MAIN_NS, "tablePart")), start=1
        ):
            relationship_id = table_part.attrib.get(qn(DOC_REL_NS, "id"))
            if not relationship_id or relationship_id not in relationships:
                raise ValueError(
                    f"Worksheet {sheet_name!r} tablePart {index} has no resolvable relationship"
                )
            relationship = relationships[relationship_id]
            relationship_type = relationship.attrib.get("Type")
            if not relationship_type or not relationship_type.endswith("/table"):
                raise ValueError(
                    f"Worksheet {sheet_name!r} table relationship {relationship_id!r} "
                    f"has unexpected type {relationship_type!r}"
                )
            target = relationship.attrib.get("Target")
            if not target or relationship.attrib.get("TargetMode") == "External":
                raise ValueError(
                    f"Worksheet {sheet_name!r} table relationship {relationship_id!r} "
                    "does not target an internal table part"
                )
            table_part_name = resolve_relationship_target(sheet_part, target)
            if table_part_name not in entries:
                raise ValueError(
                    f"Worksheet {sheet_name!r} table relationship {relationship_id!r} "
                    f"targets missing part {table_part_name!r}"
                )
            table_root = parse_xml(entries[table_part_name])
            table_ref = table_root.attrib.get("ref")
            if not table_ref:
                raise ValueError(f"Table part {table_part_name!r} has no ref")
            range_bounds(table_ref)
            table_auto_filter = table_root.find(qn(MAIN_NS, "autoFilter"))
            tables.append(
                {
                    "relationship_id": relationship_id,
                    "relationship_type": relationship_type,
                    "part": table_part_name,
                    "name": table_root.attrib.get("name"),
                    "display_name": table_root.attrib.get("displayName"),
                    "ref": table_ref,
                    "auto_filter_ref": (
                        table_auto_filter.attrib.get("ref")
                        if table_auto_filter is not None
                        else None
                    ),
                }
            )

    overlaps: list[dict[str, str | None]] = []
    for worksheet_ref in worksheet_filters:
        for table in tables:
            intersection = range_intersection(worksheet_ref, table["ref"])
            if intersection is None:
                continue
            table_name = table["display_name"] or table["name"] or table["part"]
            overlaps.append(
                {
                    "type": "worksheet_table_filter_overlap",
                    "sheet": sheet_name,
                    "worksheet_auto_filter_ref": worksheet_ref,
                    "table_name": table_name,
                    "table_part": table["part"],
                    "table_ref": table["ref"],
                    "intersection": intersection,
                    "message": (
                        f"Worksheet-level autoFilter {worksheet_ref!r} overlaps Excel Table "
                        f"{table_name!r} range {table['ref']!r} on sheet {sheet_name!r} at "
                        f"{intersection!r}; remove ws.auto_filter.ref or move it outside "
                        "every Table range."
                    ),
                }
            )
    return {
        "worksheet_auto_filters": worksheet_filters,
        "tables": tables,
        "overlaps": overlaps,
    }


def inspect_sheet(root: ET.Element, strings: list[str]) -> dict[str, Any]:
    cells: dict[str, dict[str, Any]] = {}
    formula_count = 0
    formula_cache_count = 0
    formula_errors: list[dict[str, str]] = []
    for ref, cell in worksheet_cells(root).items():
        formula = formula_signature(cell)
        record: dict[str, Any] = {
            "style": cell.attrib.get("s"),
            "type": cell.attrib.get("t"),
            "attributes": {
                key: value
                for key, value in sorted(cell.attrib.items())
                if key != "r"
            },
        }
        if formula is not None:
            formula_count += 1
            cache = cached_value(cell)
            record["formula"] = formula
            record["cached"] = cache
            if has_formula_cache(cell):
                formula_cache_count += 1
            if cell.attrib.get("t") == "e" or (
                cache is not None and cache.upper() in FORMULA_ERRORS
            ):
                formula_errors.append({"cell": ref, "value": cache or ""})
        else:
            record["value"] = displayed_value(cell, strings)
            record["payload"] = canonical_elements(list(cell))
        cells[ref] = record

    heights, other_rows = row_records(root)
    features: dict[str, Any] = {}
    for name, local_tag in FEATURE_TAGS.items():
        matches = root.findall(qn(MAIN_NS, local_tag))
        features[name] = canonical_elements(matches)
    features["row_attributes"] = other_rows
    return {
        "cells": cells,
        "row_heights": heights,
        "features": features,
        "formula_count": formula_count,
        "formula_cache_count": formula_cache_count,
        "formula_errors": formula_errors,
    }


def workbook_defined_names(entries: dict[str, bytes]) -> list[Any]:
    if "xl/workbook.xml" not in entries:
        return []
    root = parse_xml(entries["xl/workbook.xml"])
    container = root.find(qn(MAIN_NS, "definedNames"))
    if container is None:
        return []
    return canonical_elements(container.findall(qn(MAIN_NS, "definedName")))


def inspect_workbook(path: Path) -> dict[str, Any]:
    entries, infos, _ = load_package(path)
    workbook_structure = inspect_workbook_structure(entries, infos)
    strings = shared_strings(entries)
    sheet_parts = (
        resolve_sheet_parts(entries)
        if "xl/workbook.xml" in entries and "xl/_rels/workbook.xml.rels" in entries
        else {}
    )
    sheets: dict[str, Any] = {}
    total_formulas = 0
    total_caches = 0
    errors: list[dict[str, str]] = []
    filter_overlaps: list[dict[str, str | None]] = []
    for sheet_name, part in sheet_parts.items():
        if part not in entries:
            continue
        root = parse_xml(entries[part])
        inspected = inspect_sheet(root, strings)
        filter_topology = inspect_filter_topology(entries, sheet_name, part, root)
        inspected["filter_topology"] = filter_topology
        sheets[sheet_name] = {"part": part, **inspected}
        total_formulas += inspected["formula_count"]
        total_caches += inspected["formula_cache_count"]
        filter_overlaps.extend(filter_topology["overlaps"])
        errors.extend(
            {"cell": f"{sheet_name}!{item['cell']}", "value": item["value"]}
            for item in inspected["formula_errors"]
        )

    entry_hashes = {name: sha256_bytes(data) for name, data in entries.items()}
    names = set(entries)
    return {
        "path": str(path.resolve()),
        "sha256": sha256_file(path),
        "zip_integrity": True,
        "package_entry_count": len(infos),
        "package_entries": entry_hashes,
        "sheets": sheets,
        "defined_names": workbook_defined_names(entries),
        "formula_count": total_formulas,
        "formula_cache_count": total_caches,
        "formula_error_count": len(errors),
        "formula_errors": errors,
        "filter_overlap_count": len(filter_overlaps),
        "filter_overlaps": filter_overlaps,
        "workbook_issue_count": len(workbook_structure["issues"]),
        "workbook_issues": workbook_structure["issues"],
        "workbook_structure": workbook_structure,
        "objects": {
            "drawings": sorted(name for name in names if name.startswith("xl/drawings/")),
            "media": sorted(name for name in names if name.startswith("xl/media/")),
            "comments": sorted(name for name in names if name.startswith("xl/comments")),
            "external_links": sorted(
                name for name in names if name.startswith("xl/externalLinks/")
            ),
            "vba_projects": sorted(name for name in names if name.endswith("vbaProject.bin")),
            "digital_signatures": sorted(
                name for name in names if name.startswith("_xmlsignatures/")
            ),
            "styles_present": "xl/styles.xml" in names,
            "calc_chain_present": "xl/calcChain.xml" in names,
        },
    }


def diff_cells(before: dict[str, Any], after: dict[str, Any]) -> list[dict[str, Any]]:
    changes: list[dict[str, Any]] = []
    for ref in sorted(set(before) | set(after)):
        old = before.get(ref)
        new = after.get(ref)
        if old is None:
            changes.append({"cell": ref, "kinds": ["added"], "before": None, "after": new})
            continue
        if new is None:
            changes.append({"cell": ref, "kinds": ["removed"], "before": old, "after": None})
            continue
        kinds: list[str] = []
        old_formula = old.get("formula")
        new_formula = new.get("formula")
        if old_formula != new_formula:
            kinds.append("formula")
        elif old_formula is not None and (
            old.get("cached") != new.get("cached") or old.get("type") != new.get("type")
        ):
            kinds.append("formula_cache")
        if old_formula is None and new_formula is None:
            if old.get("value") != new.get("value") or old.get("type") != new.get("type"):
                kinds.append("value")
            if old.get("payload") != new.get("payload") and "value" not in kinds:
                kinds.append("payload")
        if old.get("style") != new.get("style"):
            kinds.append("style")
        old_extra = {
            key: value
            for key, value in old.get("attributes", {}).items()
            if key not in {"s", "t"}
        }
        new_extra = {
            key: value
            for key, value in new.get("attributes", {}).items()
            if key not in {"s", "t"}
        }
        if old_extra != new_extra:
            kinds.append("attributes")
        if kinds:
            changes.append({"cell": ref, "kinds": kinds, "before": old, "after": new})
    return changes


def match_any(value: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatchcase(value, pattern) for pattern in patterns)


def expand_allowed_cells(policy: dict[str, Any]) -> set[str]:
    allowed: set[str] = set()
    for item in policy.get("allowed_cells", []):
        sheet, refs = parse_qualified_range(item)
        allowed.update(f"{sheet}!{ref}" for ref in refs)
    return allowed


def expand_allowed_rows(policy: dict[str, Any]) -> set[str]:
    allowed: set[str] = set()
    for item in policy.get("allowed_row_heights", []):
        sheet, rows = parse_qualified_rows(item)
        allowed.update(f"{sheet}!{row}" for row in rows)
    return allowed


def compare_workbooks(
    baseline: dict[str, Any], current: dict[str, Any], policy: dict[str, Any]
) -> dict[str, Any]:
    allowed_cells = expand_allowed_cells(policy)
    allowed_rows = expand_allowed_rows(policy)
    allowed_features = set(policy.get("allowed_sheet_features", []))
    allowed_entries = list(policy.get("allowed_package_entries", []))
    allow_cache = bool(policy.get("allow_formula_cache_changes", False))

    sheet_changes: dict[str, Any] = {}
    unexpected_cells: list[dict[str, Any]] = []
    unexpected_rows: list[dict[str, Any]] = []
    unexpected_features: list[str] = []
    semantically_changed_parts: set[str] = set()
    unmodeled_sheet_parts: set[str] = set()
    all_sheet_names = sorted(set(baseline["sheets"]) | set(current["sheets"]))

    for sheet_name in all_sheet_names:
        old_sheet = baseline["sheets"].get(sheet_name)
        new_sheet = current["sheets"].get(sheet_name)
        if old_sheet is None or new_sheet is None:
            unexpected_features.append(f"{sheet_name}!sheet_presence")
            continue
        cell_changes = diff_cells(old_sheet["cells"], new_sheet["cells"])
        row_height_changes: list[dict[str, Any]] = []
        for row in sorted(set(old_sheet["row_heights"]) | set(new_sheet["row_heights"])):
            old_value = old_sheet["row_heights"].get(row)
            new_value = new_sheet["row_heights"].get(row)
            if old_value != new_value:
                row_height_changes.append(
                    {"row": row, "before": old_value, "after": new_value}
                )

        feature_changes: list[str] = []
        for feature in sorted(set(old_sheet["features"]) | set(new_sheet["features"])):
            if old_sheet["features"].get(feature) != new_sheet["features"].get(feature):
                feature_changes.append(feature)

        for change in cell_changes:
            qualified = f"{sheet_name}!{change['cell']}"
            cache_only = set(change["kinds"]) == {"formula_cache"}
            if not (cache_only and allow_cache) and qualified not in allowed_cells:
                unexpected_cells.append({"cell": qualified, "kinds": change["kinds"]})
        for change in row_height_changes:
            qualified = f"{sheet_name}!{change['row']}"
            if qualified not in allowed_rows:
                unexpected_rows.append({"row": qualified, **change})
        for feature in feature_changes:
            qualified = f"{sheet_name}!{feature}"
            if qualified not in allowed_features:
                unexpected_features.append(qualified)

        if cell_changes or row_height_changes or feature_changes:
            semantically_changed_parts.add(new_sheet["part"])
        sheet_changes[sheet_name] = {
            "cell_changes": cell_changes,
            "row_height_changes": row_height_changes,
            "feature_changes": feature_changes,
        }

    old_entries = baseline["package_entries"]
    new_entries = current["package_entries"]
    defined_names_changed = baseline["defined_names"] != current["defined_names"]
    defined_names_allowed = "Workbook!defined_names" in allowed_features
    added = sorted(set(new_entries) - set(old_entries))
    removed = sorted(set(old_entries) - set(new_entries))
    changed = sorted(
        name
        for name in set(old_entries) & set(new_entries)
        if old_entries[name] != new_entries[name]
    )
    sheet_parts = {
        sheet["part"]
        for sheet in baseline["sheets"].values()
    } | {sheet["part"] for sheet in current["sheets"].values()}
    for part in set(changed) & sheet_parts:
        if part not in semantically_changed_parts:
            unmodeled_sheet_parts.add(part)

    unexpected_package: list[str] = []
    for entry in added + removed + changed:
        if match_any(entry, allowed_entries):
            continue
        if entry in sheet_parts and entry in semantically_changed_parts:
            continue
        if entry == "xl/workbook.xml" and defined_names_changed and defined_names_allowed:
            continue
        unexpected_package.append(entry)
    unexpected_package.extend(sorted(unmodeled_sheet_parts - set(unexpected_package)))
    unexpected_package = sorted(set(unexpected_package))

    protected_failures: list[dict[str, str]] = []
    for entry in policy.get("required_unchanged_entries", []):
        if entry not in old_entries:
            protected_failures.append({"entry": entry, "reason": "missing in baseline"})
        elif entry not in new_entries:
            protected_failures.append({"entry": entry, "reason": "missing in current"})
        elif old_entries[entry] != new_entries[entry]:
            protected_failures.append({"entry": entry, "reason": "content changed"})

    if defined_names_changed and not defined_names_allowed:
        unexpected_features.append("Workbook!defined_names")

    expected_failures: list[dict[str, Any]] = []
    expected = policy.get("expected", {})
    for key in ("formula_count", "formula_cache_count", "formula_error_count"):
        if key in expected and current[key] != expected[key]:
            expected_failures.append(
                {"metric": key, "expected": expected[key], "actual": current[key]}
            )

    ok = not any(
        (
            unexpected_cells,
            unexpected_rows,
            unexpected_features,
            unexpected_package,
            protected_failures,
            expected_failures,
        )
    )
    return {
        "ok": ok,
        "sheet_changes": sheet_changes,
        "package_changes": {"added": added, "removed": removed, "changed": changed},
        "defined_names_changed": defined_names_changed,
        "unexpected": {
            "cells": unexpected_cells,
            "row_heights": unexpected_rows,
            "sheet_features": sorted(set(unexpected_features)),
            "package_entries": unexpected_package,
            "protected_entries": protected_failures,
            "expected_metrics": expected_failures,
        },
    }


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="backslashreplace")
    parser = argparse.ArgumentParser(description="Inspect and compare OOXML workbooks")
    parser.add_argument("workbook", type=Path)
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--policy", type=Path)
    parser.add_argument("--json-out", type=Path)
    args = parser.parse_args()
    try:
        current = inspect_workbook(args.workbook)
        policy: dict[str, Any] = {}
        if args.policy:
            policy = json.loads(args.policy.read_text(encoding="utf-8-sig"))
        comparison = None
        if args.baseline:
            baseline = inspect_workbook(args.baseline)
            comparison = compare_workbooks(baseline, current, policy)
        elif args.policy:
            raise ValueError("--policy requires --baseline")

        standalone_ok = (
            current["zip_integrity"]
            and current["formula_cache_count"] == current["formula_count"]
            and current["formula_error_count"] == 0
            and current["filter_overlap_count"] == 0
            and current["workbook_issue_count"] == 0
        )
        report = {
            "ok": standalone_ok and (comparison is None or comparison["ok"]),
            "workbook": current,
            "comparison": comparison,
        }
        print(json_write(report, args.json_out))
        return 0 if report["ok"] else 2
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
