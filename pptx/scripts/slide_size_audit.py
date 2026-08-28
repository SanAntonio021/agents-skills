#!/usr/bin/env python3
"""Read-only slide-size gate for PowerPoint OOXML packages."""

from __future__ import annotations

import argparse
import json
import sys
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

import defusedxml.ElementTree as ET
from defusedxml.common import DefusedXmlException


P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
EMU_PER_INCH = 914400

# PowerPoint's standard Widescreen preset is not the same canvas as
# pptxgenjs' LAYOUT_16x9 preset. Keep both values explicit so a same-ratio
# canvas cannot silently pass as compatible for slide copying.
EXPECTED_SIZES = {
    "wide16x9": (12192000, 6858000),
    "legacy16x9": (9144000, 5143500),
}


class SlideSizeInputError(ValueError):
    """Raised when a PPTX package has no readable slide-size declaration."""


@dataclass(frozen=True)
class SlideSizeReport:
    width_emu: int
    height_emu: int
    width_inches: float
    height_inches: float
    aspect_ratio: float
    detected_format: str


def configure_utf8_stdio() -> None:
    """Keep human and JSON output stable on Windows."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if not callable(reconfigure):
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def _parse_positive_emu(value: str | None, attribute: str) -> int:
    if value is None:
        raise SlideSizeInputError(f"p:sldSz is missing {attribute}")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise SlideSizeInputError(
            f"p:sldSz {attribute} must be a positive integer; got {value!r}"
        ) from exc
    if parsed <= 0:
        raise SlideSizeInputError(
            f"p:sldSz {attribute} must be a positive integer; got {value!r}"
        )
    return parsed


def _detected_format(width_emu: int, height_emu: int) -> str:
    for name, dimensions in EXPECTED_SIZES.items():
        if (width_emu, height_emu) == dimensions:
            return name
    if abs((width_emu / height_emu) - (16 / 9)) < 1e-6:
        return "custom16x9"
    return "custom"


def read_slide_size(path: str | Path) -> SlideSizeReport:
    """Read the presentation-level p:sldSz declaration without modifying it."""
    source = Path(path)
    if source.suffix.lower() not in {".pptx", ".potx"}:
        raise SlideSizeInputError("input must be a .pptx or .potx file")
    if not source.is_file():
        raise SlideSizeInputError(f"file does not exist: {source}")

    try:
        with zipfile.ZipFile(source) as package:
            try:
                xml = package.read("ppt/presentation.xml")
            except KeyError as exc:
                raise SlideSizeInputError(
                    "package is missing ppt/presentation.xml"
                ) from exc
    except (OSError, zipfile.BadZipFile) as exc:
        raise SlideSizeInputError(f"unable to read PPTX package: {exc}") from exc

    try:
        root = ET.fromstring(xml)
    except (ET.ParseError, DefusedXmlException) as exc:
        raise SlideSizeInputError(f"ppt/presentation.xml is not valid XML: {exc}") from exc

    slide_size = root.find(f"{{{P_NS}}}sldSz")
    if slide_size is None:
        raise SlideSizeInputError("ppt/presentation.xml is missing p:sldSz")
    width_emu = _parse_positive_emu(slide_size.get("cx"), "cx")
    height_emu = _parse_positive_emu(slide_size.get("cy"), "cy")
    return SlideSizeReport(
        width_emu=width_emu,
        height_emu=height_emu,
        width_inches=round(width_emu / EMU_PER_INCH, 6),
        height_inches=round(height_emu / EMU_PER_INCH, 6),
        aspect_ratio=round(width_emu / height_emu, 6),
        detected_format=_detected_format(width_emu, height_emu),
    )


def audit(
    path: str | Path,
    expected: str | None = "wide16x9",
    *,
    reference: str | Path | None = None,
) -> dict[str, object]:
    report = read_slide_size(path)
    if reference is not None and expected not in {None, "any"}:
        raise SlideSizeInputError("--reference cannot be combined with --expected")
    reference_report = read_slide_size(reference) if reference is not None else None
    if reference_report is not None:
        passed = (report.width_emu, report.height_emu) == (
            reference_report.width_emu,
            reference_report.height_emu,
        )
        expected_label = "reference"
    else:
        expected = expected or "wide16x9"
        expected_dimensions = EXPECTED_SIZES.get(expected)
        passed = expected == "any" or (
            expected_dimensions is not None
            and (report.width_emu, report.height_emu) == expected_dimensions
        )
        expected_label = expected
    result: dict[str, object] = {
        "status": "PASS" if passed else "FAIL",
        "path": str(Path(path)),
        "expected": expected_label,
        "slide_size": asdict(report),
    }
    if reference_report is not None:
        result["reference"] = str(Path(reference))
        result["reference_slide_size"] = asdict(reference_report)
    if not passed:
        if reference_report is not None:
            result["reason"] = (
                "reference mismatch: expected "
                f"{reference_report.width_emu} x {reference_report.height_emu} EMU, "
                f"got {report.width_emu} x {report.height_emu} EMU"
            )
        else:
            result["reason"] = (
                f"expected {expected_dimensions[0]} x {expected_dimensions[1]} EMU, "
                f"got {report.width_emu} x {report.height_emu} EMU"
            )
    return result


def emit_human(result: dict[str, object]) -> None:
    report = result["slide_size"]
    assert isinstance(report, dict)
    state = result["status"]
    print(
        f"Slide size audit {state}: {report['width_inches']:.3f} x "
        f"{report['height_inches']:.3f} in "
        f"({report['width_emu']} x {report['height_emu']} EMU), "
        f"detected={report['detected_format']}, expected={result['expected']}."
    )
    if "reference_slide_size" in result:
        reference = result["reference_slide_size"]
        assert isinstance(reference, dict)
        print(
            f"- reference={result['reference']}: "
            f"{reference['width_inches']:.3f} x {reference['height_inches']:.3f} in "
            f"({reference['width_emu']} x {reference['height_emu']} EMU)"
        )
    if result["status"] != "PASS":
        print(f"- {result['reason']}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Audit the presentation-level PowerPoint slide size"
    )
    parser.add_argument("path", help="Input .pptx or .potx file (read-only)")
    expected = parser.add_mutually_exclusive_group()
    expected.add_argument(
        "--expected",
        choices=("wide16x9", "legacy16x9", "any"),
        help="Expected canvas; standard PowerPoint wide-screen is the default",
    )
    expected.add_argument(
        "--reference",
        help="Reference PPTX/POTX whose physical EMU canvas must match exactly",
    )
    parser.add_argument("--json", action="store_true", dest="as_json")
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    configure_utf8_stdio()
    args = build_parser().parse_args(argv)
    try:
        result = audit(args.path, args.expected, reference=args.reference)
    except SlideSizeInputError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    if args.as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        emit_human(result)
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
