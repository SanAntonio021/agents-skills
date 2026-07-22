from __future__ import annotations

import argparse
import fnmatch
import json
import sys
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from ooxml_common import (
    FORMULA_ERRORS,
    MAIN_NS,
    cached_value,
    displayed_value,
    formula_signature,
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
            if cell.find(qn(MAIN_NS, "v")) is not None:
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
    root = parse_xml(entries["xl/workbook.xml"])
    container = root.find(qn(MAIN_NS, "definedNames"))
    if container is None:
        return []
    return canonical_elements(container.findall(qn(MAIN_NS, "definedName")))


def inspect_workbook(path: Path) -> dict[str, Any]:
    entries, infos, _ = load_package(path)
    strings = shared_strings(entries)
    sheet_parts = resolve_sheet_parts(entries)
    sheets: dict[str, Any] = {}
    total_formulas = 0
    total_caches = 0
    errors: list[dict[str, str]] = []
    for sheet_name, part in sheet_parts.items():
        root = parse_xml(entries[part])
        inspected = inspect_sheet(root, strings)
        sheets[sheet_name] = {"part": part, **inspected}
        total_formulas += inspected["formula_count"]
        total_caches += inspected["formula_cache_count"]
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
