from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from ooxml_common import (
    FORMULA_ERRORS,
    MAIN_NS,
    cached_value,
    formula_signature,
    has_formula_cache,
    json_write,
    load_package,
    parse_xml,
    qn,
    resolve_sheet_parts,
    serialize_xml,
    worksheet_cells,
    write_package,
)


COMPLEX_FORMULA_TYPES = {"shared", "array", "dataTable"}


def set_cache(target: ET.Element, recalculated: ET.Element) -> bool:
    recalculated_value = recalculated.find(qn(MAIN_NS, "v"))
    if recalculated_value is None:
        return False
    target_value = target.find(qn(MAIN_NS, "v"))
    old_value = None if target_value is None else (target_value.text or "")
    old_type = target.attrib.get("t")
    recalculated_type = recalculated.attrib.get("t")
    new_type = recalculated_type if recalculated_type in {"str", "b", "e"} else None
    if old_value == (recalculated_value.text or "") and old_type == new_type:
        return False
    if target_value is None:
        target_formula = target.find(qn(MAIN_NS, "f"))
        target_value = ET.Element(qn(MAIN_NS, "v"))
        if target_formula is None:
            target.append(target_value)
        else:
            children = list(target)
            target.insert(children.index(target_formula) + 1, target_value)
    target_value.text = recalculated_value.text

    if recalculated_type in {"str", "b", "e"}:
        target.attrib["t"] = recalculated_type
    elif target.attrib.get("t") in {"str", "b", "e"}:
        target.attrib.pop("t", None)
    return True


def merge_caches(target: Path, recalculated: Path, output: Path) -> dict[str, Any]:
    target_entries, _, _ = load_package(target)
    recalc_entries, _, _ = load_package(recalculated)
    target_sheets = resolve_sheet_parts(target_entries)
    recalc_sheets = resolve_sheet_parts(recalc_entries)
    if set(target_sheets) != set(recalc_sheets):
        raise ValueError("Worksheet name sets differ between target and recalculated files")

    replacements: dict[str, bytes] = {}
    formula_count = 0
    verified_cache_count = 0
    updated_cache_count = 0
    missing: list[str] = []
    mismatches: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []

    for sheet_name, target_part in target_sheets.items():
        target_root = parse_xml(target_entries[target_part])
        recalc_root = parse_xml(recalc_entries[recalc_sheets[sheet_name]])
        target_cells = worksheet_cells(target_root)
        recalc_cells = worksheet_cells(recalc_root)
        sheet_changed = False
        for ref, target_cell in target_cells.items():
            target_formula = formula_signature(target_cell)
            if target_formula is None:
                continue
            formula_count += 1
            target_type = target_formula["attributes"].get("t")
            if target_type in COMPLEX_FORMULA_TYPES:
                mismatches.append(
                    {
                        "cell": f"{sheet_name}!{ref}",
                        "reason": f"unsupported formula type: {target_type}",
                    }
                )
                continue
            recalc_cell = recalc_cells.get(ref)
            if recalc_cell is None:
                missing.append(f"{sheet_name}!{ref}")
                continue
            recalc_formula = formula_signature(recalc_cell)
            if recalc_formula is None:
                mismatches.append(
                    {"cell": f"{sheet_name}!{ref}", "reason": "formula missing after recalc"}
                )
                continue
            if target_formula["text"] != recalc_formula["text"]:
                mismatches.append(
                    {
                        "cell": f"{sheet_name}!{ref}",
                        "reason": "formula text changed",
                        "target": target_formula["text"],
                        "recalculated": recalc_formula["text"],
                    }
                )
                continue
            if not has_formula_cache(recalc_cell):
                missing.append(f"{sheet_name}!{ref}")
                continue
            value = cached_value(recalc_cell)
            if value is None:
                missing.append(f"{sheet_name}!{ref}")
                continue
            if recalc_cell.attrib.get("t") == "e" or value.upper() in FORMULA_ERRORS:
                errors.append({"cell": f"{sheet_name}!{ref}", "value": value})
                continue
            verified_cache_count += 1
            if set_cache(target_cell, recalc_cell):
                updated_cache_count += 1
                sheet_changed = True
        if sheet_changed:
            replacements[target_part] = serialize_xml(target_root)

    if missing or mismatches or errors or verified_cache_count != formula_count:
        raise ValueError(
            json.dumps(
                {
                    "formula_count": formula_count,
                    "verified_cache_count": verified_cache_count,
                    "updated_cache_count": updated_cache_count,
                    "missing_caches": missing,
                    "formula_mismatches": mismatches,
                    "formula_errors": errors,
                },
                ensure_ascii=False,
            )
        )

    write_package(target, output, replacements)
    return {
        "ok": True,
        "target": str(target.resolve()),
        "recalculated": str(recalculated.resolve()),
        "output": str(output.resolve()),
        "formula_count": formula_count,
        "formula_cache_count": verified_cache_count,
        "formula_caches_updated": updated_cache_count,
        "formula_error_count": 0,
        "changed_package_entries": sorted(replacements),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Merge verified formula caches from a recalculated OOXML workbook"
    )
    parser.add_argument("target", type=Path)
    parser.add_argument("recalculated", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--json-out", type=Path)
    args = parser.parse_args()
    try:
        report = merge_caches(args.target, args.recalculated, args.output)
        print(json_write(report, args.json_out))
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
