"""Read-only regression audit for the existing GLOBECOM Fig. 2--4 exports."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

from ieee_plot_style import _inspect_export_geometry, _sha256, resolve_ieee_serif_font


FIGURES = {
    "Fig. 2": "fig2_power_sweep",
    "Fig. 3": "fig3_endurance",
    "Fig. 4": "fig4_reversal",
}


def _snapshot(paths: Sequence[Path]) -> dict[str, dict[str, Any]]:
    return {
        str(path.resolve()): {
            "bytes": path.stat().st_size,
            "mtime_ns": path.stat().st_mtime_ns,
            "sha256": _sha256(path),
        }
        for path in paths
        if path.is_file()
    }


def audit_globecom_exports(figure_dir: str | Path, profile_path: str | Path) -> dict[str, Any]:
    figure_root = Path(figure_dir).resolve()
    profile_file = Path(profile_path).resolve()
    profile = json.loads(profile_file.read_text(encoding="utf-8"))
    dpi = int(profile.get("export", {}).get("png_dpi", 600))
    font_resolution = resolve_ieee_serif_font()
    targets = [profile_file]
    targets.extend(figure_root / f"{stem}.{suffix}" for stem in FIGURES.values() for suffix in ("pdf", "svg", "png"))
    before = _snapshot(targets)
    errors: list[str] = []
    figures: dict[str, Any] = {}

    for figure_id, stem in FIGURES.items():
        expected = profile.get("figures", {}).get(figure_id, {}).get("figsize_in")
        if not expected or len(expected) != 2:
            errors.append(f"{figure_id} has no two-value figsize_in in plot_profile.json")
            continue
        records = []
        for suffix in ("pdf", "svg", "png"):
            path = figure_root / f"{stem}.{suffix}"
            if not path.is_file():
                errors.append(f"missing regression artifact: {path}")
                continue
            try:
                geometry = _inspect_export_geometry(
                    path,
                    expected_width_in=float(expected[0]),
                    expected_height_in=float(expected[1]),
                    dpi=dpi,
                    font_resolution=font_resolution,
                )
                records.append(geometry)
                if not geometry["exact_size"]:
                    errors.append(f"{path.name} does not match plot_profile.json physical dimensions")
                font_validation = geometry.get("font_validation", {})
                if not font_validation.get("ok", False):
                    unexpected = (
                        font_validation.get("unexpected_families")
                        or font_validation.get("unexpected_postscript_names")
                        or []
                    )
                    detail = f": {', '.join(str(value) for value in unexpected)}" if unexpected else ""
                    errors.append(f"{path.name} failed font validation{detail}")
            except (KeyError, OSError, ValueError) as exc:
                errors.append(str(exc))
        figures[figure_id] = {"stem": stem, "expected_size_in": expected, "files": records}

    after = _snapshot(targets)
    unchanged = before == after
    if not unchanged:
        errors.append("read-only regression inputs changed during audit")
    return {
        "schema_version": 1,
        "audit_mode": "read_only_no_rerender",
        "figure_dir": str(figure_root),
        "profile_path": str(profile_file),
        "ok": not errors,
        "errors": errors,
        "read_only_unchanged": unchanged,
        "figures": figures,
        "snapshot": after,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--figure-dir", required=True)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--output")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    figure_dir = Path(args.figure_dir).resolve()
    report = audit_globecom_exports(figure_dir, args.profile)
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        output = Path(args.output).resolve()
        if output == figure_dir or figure_dir in output.parents:
            raise ValueError("audit output must be outside the read-only regression directory")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
