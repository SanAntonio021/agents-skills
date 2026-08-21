"""Reusable, deterministic Matplotlib helpers for IEEE manuscript figures.

The strict single-column entry points in this module are deliberately local and
dependency-light.  They keep the physical canvas fixed, make the visible ink
boundary measurable, and separate semantic palette approval from mechanical
layout repair.  The older generic helpers remain available for compatibility;
new paper data plots should use the ``ieee_single_column`` entry points.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import re
import struct
import warnings
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime
from itertools import cycle
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.collections import PathCollection
from matplotlib.colors import to_hex
from matplotlib.font_manager import FontProperties, fontManager
from matplotlib.ft2font import FT2Font
from matplotlib.legend import Legend
from matplotlib.lines import Line2D
from matplotlib.text import Text
from matplotlib import transforms as mtransforms


IEEE_SINGLE_COLUMN_IN = 3.5
IEEE_DOUBLE_COLUMN_IN = 7.16
IEEE_SINGLE_COLUMN_MARGIN_PT = 3.0
IEEE_SINGLE_COLUMN_MARGIN_TOLERANCE_PT = 0.75
IEEE_STACKED_CONTENT_GAP_PT = 4.0
IEEE_STACKED_CONTENT_GAP_TOLERANCE_PT = 0.75
IEEE_MAJOR_GRID = {
    "color": "#B8B8B8",
    "linewidth": 0.35,
    "alpha": 0.52,
    "linestyle": (0.0, (5.0, 3.0)),
}
IEEE_MINOR_GRID = {
    "color": "#D6D6D6",
    "linewidth": 0.35,
    "alpha": 0.40,
    "linestyle": (0.0, (1.0, 1.65)),
}
IEEE_DEFAULT_GRID_MODE = "major_xy"
IEEE_GRID_MODES = ("major_xy", "none", "legacy_major_minor_xy")
SUPPORTED_MATPLOTLIB_MIN = (3, 5)
SUPPORTED_MATPLOTLIB_MAX = (4, 0)

# Paul Tol's published 2021 values are copied as static data.  Keeping the
# values local prevents a future upstream edit from changing a paper's colors.
TOL_HIGH_CONTRAST = ("#004488", "#DDAA33", "#BB5566")
TOL_BRIGHT = ("#4477AA", "#EE6677", "#228833", "#CCBB44", "#66CCEE", "#AA3377", "#BBBBBB")
TOL_MUTED = (
    "#332288",
    "#88CCEE",
    "#44AA99",
    "#117733",
    "#999933",
    "#DDCC77",
    "#CC6677",
    "#882255",
    "#AA4499",
    "#DDDDDD",
)
TOL_NIGHTFALL = (
    "#125A56",
    "#00767B",
    "#238F9D",
    "#42A7C6",
    "#60BCE9",
    "#9DCCEF",
    "#C6DBED",
    "#DEE6E7",
    "#ECEADA",
    "#F0E6B2",
    "#F9D576",
    "#FFB954",
    "#FD9A44",
    "#F57634",
    "#E94C1F",
    "#D11807",
    "#A01813",
)
PALETTE_LIBRARY = {
    "tol_high_contrast": TOL_HIGH_CONTRAST,
    "tol_bright": TOL_BRIGHT,
    "tol_muted": TOL_MUTED,
    "tol_nightfall": TOL_NIGHTFALL,
}

# These are semantic roles, not an automatic per-figure color cycle.
FIGURE_PRIORITY_COLORS = {
    # Legacy keys remain available to avoid breaking existing plot scripts.
    "primary": "#0072B2",
    "secondary": "#D55E00",
    "tertiary": "#009E73",
    "quaternary": "#CC79A7",
    "category_extra_1": "#56B4E9",
    "category_extra_2": "#E69F00",
    "reference": "#404040",
    "threshold": "#000000",
    "delta": "#000000",
    "grid": IEEE_MAJOR_GRID["color"],
    "grid_major": IEEE_MAJOR_GRID["color"],
    "grid_minor": IEEE_MINOR_GRID["color"],
    "uncertainty_alpha": 0.20,
}
DEFAULT_CATEGORY_COLORS = list(TOL_BRIGHT)
OKABE_ITO = ["#0072B2", "#D55E00", "#009E73", "#CC79A7", "#56B4E9", "#E69F00"]

FONT_ASSET_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"
FONT_MANIFEST_NAME = "manifest.json"
FONT_STYLE_FILES = {
    "regular": "LiberationSerif-Regular.ttf",
    "bold": "LiberationSerif-Bold.ttf",
    "italic": "LiberationSerif-Italic.ttf",
    "bold_italic": "LiberationSerif-BoldItalic.ttf",
}


class FigurePreflightError(RuntimeError):
    """Raised when a formal export cannot meet the selected profile."""

    def __init__(self, report: Mapping[str, Any]):
        self.report = dict(report)
        errors = "; ".join(str(item) for item in self.report.get("errors", []))
        super().__init__(errors or "IEEE figure preflight failed")


class FontResolutionError(RuntimeError):
    """Raised when no approved serif font can be registered safely."""


@dataclass(frozen=True)
class FontResolution:
    family: str
    regular_file: Path
    source: str
    files: dict[str, Path]
    hashes: dict[str, str]
    fallback: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "family": self.family,
            "regular_file": str(self.regular_file),
            "source": self.source,
            "files": {key: str(value) for key, value in self.files.items()},
            "sha256": dict(self.hashes),
            "fallback": self.fallback,
            "complete": set(self.files) == set(FONT_STYLE_FILES),
        }


@dataclass
class PreflightReport:
    errors: list[str]
    warnings: list[str]
    visual_review_required: list[str]
    metrics: dict[str, Any]

    @property
    def ok(self) -> bool:
        return not self.errors

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "visual_review_required": list(self.visual_review_required),
            "metrics": self.metrics,
        }


def _version_tuple(version: str) -> tuple[int, int]:
    match = re.match(r"^(\d+)\.(\d+)", version)
    return (int(match.group(1)), int(match.group(2))) if match else (0, 0)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def _unique_paths(paths: Iterable[Path]) -> list[Path]:
    seen: set[str] = set()
    result: list[Path] = []
    for path in paths:
        resolved = path.expanduser().resolve()
        key = str(resolved).lower()
        if key not in seen and resolved.is_file():
            seen.add(key)
            result.append(resolved)
    return result


def _family_paths(family: str) -> list[Path]:
    paths: list[Path] = []
    family_key = family.lower()
    for entry in getattr(fontManager, "ttflist", []):
        if str(getattr(entry, "name", "")).lower() == family_key:
            paths.append(Path(entry.fname))
    if family == "Times New Roman":
        paths.extend(Path(r"C:\Windows\Fonts") / name for name in ("times.ttf", "timesbd.ttf", "timesi.ttf", "timesbi.ttf"))
    if family == "Liberation Serif":
        paths.extend(
            Path(r"C:\Windows\Fonts") / name
            for name in (
                "LiberationSerif-Regular.ttf",
                "LiberationSerif-Bold.ttf",
                "LiberationSerif-Italic.ttf",
                "LiberationSerif-BoldItalic.ttf",
            )
        )
    return _unique_paths(paths)


def _style_for_path(path: Path) -> str:
    """Read the font's declared style, with filename rules as a fallback."""

    try:
        style_name = str(FT2Font(str(path)).style_name).lower().replace("-", " ")
    except Exception:
        style_name = path.stem.lower().replace("-", " ")
    compact = re.sub(r"[^a-z]", "", style_name)
    if "bolditalic" in compact or ("bold" in compact and "italic" in compact):
        return "bold_italic"
    if "italic" in compact or "oblique" in compact:
        return "italic"
    if "bold" in compact:
        return "bold"

    filename = path.stem.lower()
    if filename in {"timesbi", "timesnewromanpsbolditalicmt"}:
        return "bold_italic"
    if filename in {"timesbd", "timesnewromanpsboldmt"}:
        return "bold"
    if filename in {"timesi", "timesnewromanpsitalicmt"}:
        return "italic"
    return "regular"


def _register_files(files: Mapping[str, Path]) -> None:
    addfont = getattr(fontManager, "addfont", None)
    if addfont is None:
        raise FontResolutionError("Matplotlib does not provide process-local font registration")
    try:
        for path in files.values():
            addfont(str(path))
    except Exception as exc:  # pragma: no cover - backend-specific error text
        raise FontResolutionError(f"could not register approved font files: {exc}") from exc


def _select_style_files(paths: Iterable[Path], *, family: str) -> dict[str, Path]:
    selected: dict[str, Path] = {}
    for path in paths:
        try:
            if str(FT2Font(str(path)).family_name) != family:
                continue
        except Exception:
            continue
        selected.setdefault(_style_for_path(path), path)
    return selected


def _bundled_font_files(asset_dir: Path) -> tuple[dict[str, Path], dict[str, str]]:
    manifest_path = asset_dir / FONT_MANIFEST_NAME
    if not manifest_path.is_file():
        raise FontResolutionError(f"font manifest is missing: {manifest_path}")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise FontResolutionError(f"font manifest is invalid: {manifest_path}") from exc
    if manifest.get("family") != "Liberation Serif" or manifest.get("version") != "2.1.5":
        raise FontResolutionError(f"font manifest has an unexpected family or version: {manifest_path}")
    expected = {str(key): str(value).upper() for key, value in manifest.get("sha256", {}).items()}
    files = {style: asset_dir / filename for style, filename in FONT_STYLE_FILES.items()}
    for style, path in files.items():
        if not path.is_file():
            raise FontResolutionError(f"bundled font file is missing: {path}")
        actual = _sha256(path)
        if expected.get(style) != actual:
            raise FontResolutionError(f"bundled font SHA-256 mismatch for {style}: {path}")
    return files, expected


def resolve_ieee_serif_font(
    *, preferred_family: str = "Times New Roman", asset_dir: str | Path | None = None
) -> FontResolution:
    """Resolve and process-register an approved serif family.

    Times New Roman is preferred.  When it is unavailable, a fixed Liberation
    Serif package is used.  There is deliberately no silent Matplotlib fallback.
    """

    if preferred_family not in {"Times New Roman", "Liberation Serif"}:
        raise FontResolutionError("preferred_family must be Times New Roman or Liberation Serif")

    if preferred_family == "Times New Roman":
        style_files = _select_style_files(_family_paths("Times New Roman"), family="Times New Roman")
        if set(style_files) == set(FONT_STYLE_FILES):
            _register_files(style_files)
            return FontResolution(
                family="Times New Roman",
                regular_file=style_files["regular"],
                source="system",
                files=style_files,
                hashes={style: _sha256(path) for style, path in style_files.items()},
                fallback=False,
            )

    bundled_dir = Path(asset_dir) if asset_dir is not None else FONT_ASSET_DIR
    files, _ = _bundled_font_files(bundled_dir)
    _register_files(files)
    family = FontProperties(fname=str(files["regular"])).get_name()
    if family != "Liberation Serif":
        raise FontResolutionError(f"bundled font reported unexpected family: {family}")
    return FontResolution(
        family=family,
        regular_file=files["regular"],
        source="bundled",
        files=files,
        hashes={style: _sha256(path) for style, path in files.items()},
        fallback=True,
    )


def _apply_rcparams(
    *, family: str, base_font_size: float, marker_size: float, color_cycle: Sequence[str]
) -> None:
    mpl.rcParams.update(
        {
            "font.family": "serif",
            "font.serif": [family],
            "font.size": base_font_size,
            "mathtext.fontset": "custom",
            "mathtext.default": "regular",
            "mathtext.rm": family,
            "mathtext.it": f"{family}:italic",
            "mathtext.bf": f"{family}:bold",
            "mathtext.bfit": f"{family}:italic:bold",
            "mathtext.cal": f"{family}:italic",
            "mathtext.sf": family,
            "mathtext.tt": family,
            "mathtext.fallback": None,
            "axes.labelsize": base_font_size,
            "axes.titlesize": base_font_size,
            "xtick.labelsize": base_font_size,
            "ytick.labelsize": base_font_size,
            "legend.fontsize": base_font_size,
            "axes.linewidth": 0.7,
            "lines.linewidth": 1.1,
            "lines.markersize": marker_size,
            "xtick.major.width": 0.7,
            "ytick.major.width": 0.7,
            "xtick.minor.width": 0.6,
            "ytick.minor.width": 0.6,
            "xtick.major.size": 3.0,
            "ytick.major.size": 3.0,
            "xtick.minor.size": 2.2,
            "ytick.minor.size": 2.2,
            "xtick.direction": "in",
            "ytick.direction": "in",
            "xtick.top": True,
            "ytick.right": True,
            "axes.spines.top": True,
            "axes.spines.right": True,
            "axes.formatter.use_locale": False,
            "legend.frameon": False,
            "figure.dpi": 150,
            "savefig.dpi": 600,
            "savefig.bbox": None,
            "savefig.pad_inches": 0.0,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
            "svg.fonttype": "none",
            "axes.prop_cycle": mpl.cycler(color=list(color_cycle)),
        }
    )


def use_ieee_single_column_style(
    *,
    base_font_size: float = 8.0,
    marker_size: float = 3.8,
    color_cycle: Sequence[str] | None = None,
    font_resolution: FontResolution | None = None,
) -> FontResolution:
    """Apply the strict IEEE single-column defaults and return font metadata."""

    resolution = font_resolution or resolve_ieee_serif_font()
    _apply_rcparams(
        family=resolution.family,
        base_font_size=base_font_size,
        marker_size=marker_size,
        color_cycle=color_cycle or TOL_BRIGHT,
    )
    return resolution


def use_ieee_style(
    font_family: str = "Arial",
    base_font_size: float = 8.0,
    line_width: float = 1.1,
    marker_size: float = 3.5,
) -> None:
    """Preserve the original generic API for existing non-strict figures."""

    mpl.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": [font_family, "Helvetica", "DejaVu Sans"],
            "font.size": base_font_size,
            "axes.labelsize": base_font_size,
            "axes.titlesize": base_font_size,
            "xtick.labelsize": base_font_size - 1.0,
            "ytick.labelsize": base_font_size - 1.0,
            "legend.fontsize": base_font_size - 1.0,
            "axes.linewidth": 0.6,
            "lines.linewidth": line_width,
            "lines.markersize": marker_size,
            "xtick.major.width": 0.6,
            "ytick.major.width": 0.6,
            "xtick.major.size": 3.0,
            "ytick.major.size": 3.0,
            "legend.frameon": False,
            "figure.dpi": 150,
            "savefig.dpi": 600,
            "savefig.bbox": "tight",
            "savefig.pad_inches": 0.02,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
            "svg.fonttype": "none",
            "axes.prop_cycle": mpl.cycler(color=OKABE_ITO),
        }
    )


def ieee_figure_size(width: str = "single", height_ratio: float = 0.72) -> tuple[float, float]:
    """Return a figure size in inches for IEEE single or double column output."""

    if width not in {"single", "double"}:
        raise ValueError("width must be 'single' or 'double'")
    base_width = IEEE_SINGLE_COLUMN_IN if width == "single" else IEEE_DOUBLE_COLUMN_IN
    return base_width, base_width * height_ratio


def resolve_ieee_width(width: str | float = "single") -> float:
    if isinstance(width, (int, float)):
        if width <= 0:
            raise ValueError("width must be positive")
        return float(width)
    if width == "single":
        return IEEE_SINGLE_COLUMN_IN
    if width == "double":
        return IEEE_DOUBLE_COLUMN_IN
    raise ValueError("width must be 'single', 'double', or a positive inch value")


def compute_panel_size(
    total_width: str | float = "double",
    ncols: int = 1,
    total_gutter_in: float = 0.0,
    height_ratio: float = 0.72,
) -> tuple[float, float]:
    if ncols < 1:
        raise ValueError("ncols must be at least 1")
    if total_gutter_in < 0 or height_ratio <= 0:
        raise ValueError("gutter must be non-negative and height_ratio positive")
    figure_width = resolve_ieee_width(total_width)
    available_width = figure_width - total_gutter_in
    if available_width <= 0:
        raise ValueError("total_gutter_in leaves no positive panel width")
    panel_width = available_width / ncols
    return panel_width, panel_width * height_ratio


def new_ieee_figure(
    width: str = "single",
    height_ratio: float = 0.72,
    nrows: int = 1,
    ncols: int = 1,
    **subplot_kwargs,
):
    use_ieee_single_column_style() if width == "single" else use_ieee_style()
    return plt.subplots(
        nrows=nrows,
        ncols=ncols,
        figsize=ieee_figure_size(width=width, height_ratio=height_ratio),
        **subplot_kwargs,
    )


def save_ieee_figure(
    fig,
    stem: str,
    output_dir: str | Path = ".",
    formats: Sequence[str] = ("pdf", "png"),
    dpi: int = 600,
) -> list[Path]:
    """Legacy preview exporter using a tight bounding box."""

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    saved: list[Path] = []
    for fmt in formats:
        suffix = fmt.lower().lstrip(".")
        path = out_dir / f"{stem}.{suffix}"
        fig.savefig(path, dpi=dpi, bbox_inches="tight", pad_inches=0.02)
        saved.append(path)
    return saved


def save_exact_size_figure(
    fig,
    stem: str,
    output_dir: str | Path = ".",
    formats: Sequence[str] = ("pdf", "png"),
    dpi: int = 600,
) -> list[Path]:
    """Compatibility exact-size exporter without the formal palette gate."""

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    saved: list[Path] = []
    for fmt in formats:
        suffix = fmt.lower().lstrip(".")
        path = out_dir / f"{stem}.{suffix}"
        fig.savefig(path, dpi=dpi, bbox_inches=None, pad_inches=0.0)
        saved.append(path)
    return saved


def apply_axes_box(fig, left: float, right: float, bottom: float, top: float) -> None:
    fig.subplots_adjust(left=left, right=right, bottom=bottom, top=top)


def apply_compact_axis_spacing(
    ax,
    xlabel_pad: float = 0.8,
    ylabel_pad: float = 0.8,
    xtick_pad: float = 1.8,
    ytick_pad: float = 0.6,
    minor_tick_length: float = 1.5,
    tick_direction: str = "in",
    top_ticks: bool = True,
    right_ticks: bool = True,
) -> None:
    ax.xaxis.labelpad = xlabel_pad
    ax.yaxis.labelpad = ylabel_pad
    ax.tick_params(axis="x", direction=tick_direction, top=top_ticks, pad=xtick_pad)
    ax.tick_params(axis="y", direction=tick_direction, right=right_ticks, pad=ytick_pad)
    ax.tick_params(axis="x", which="minor", direction=tick_direction, top=top_ticks, length=minor_tick_length)
    ax.tick_params(axis="y", which="minor", direction=tick_direction, right=right_ticks, length=minor_tick_length)


def apply_single_column_axes(ax) -> None:
    """Apply the four-sided frame and inward ticks used by the strict profile."""

    for spine in ax.spines.values():
        spine.set_color("black")
        spine.set_linewidth(0.7)
        spine.set_visible(True)
    ax.tick_params(axis="x", which="major", bottom=True, top=True, direction="in", width=0.7, length=3.0, pad=1.5)
    ax.tick_params(axis="y", which="major", left=True, right=True, direction="in", width=0.7, length=3.0, pad=0.6)
    ax.tick_params(axis="x", which="minor", bottom=True, top=True, direction="in", width=0.6, length=2.2)
    ax.tick_params(axis="y", which="minor", left=True, right=True, direction="in", width=0.6, length=2.2)
    if ax.get_xscale() == "log":
        ax.tick_params(axis="x", which="minor", bottom=False, top=False)
    if ax.get_yscale() == "log":
        ax.tick_params(axis="y", which="minor", left=False, right=False)


def apply_compact_single_column_axes(ax) -> None:
    """Backward-compatible alias for :func:`apply_single_column_axes`."""

    apply_single_column_axes(ax)


def apply_ieee_grid(
    ax,
    major_color: str = IEEE_MAJOR_GRID["color"],
    minor_color: str = IEEE_MINOR_GRID["color"],
    major_width: float = IEEE_MAJOR_GRID["linewidth"],
    minor_width: float = IEEE_MINOR_GRID["linewidth"],
    major_alpha: float = IEEE_MAJOR_GRID["alpha"],
    minor_alpha: float = IEEE_MINOR_GRID["alpha"],
    grid_mode: str = IEEE_DEFAULT_GRID_MODE,
) -> None:
    """Apply a complete Cartesian grid or no grid at all.

    New numerical plots use ``major_xy`` so major grid lines appear on both
    axes. Categorical/image-like panels use ``none`` when a Cartesian grid
    would add clutter. Minor grids are intentionally absent from every default
    route. ``legacy_major_minor_xy`` exists only for reproducibility of old
    plots.
    """

    grid_mode = _normalize_grid_mode(grid_mode)
    ax.set_axisbelow(True)
    ax.minorticks_on()
    ax.grid(False, which="both", axis="both")
    if grid_mode in {"major_xy", "legacy_major_minor_xy"}:
        ax.grid(
            True,
            which="major",
            axis="both",
            color=major_color,
            linewidth=major_width,
            linestyle=IEEE_MAJOR_GRID["linestyle"],
            alpha=major_alpha,
        )
    if grid_mode == "legacy_major_minor_xy":
        ax.grid(
            True,
            which="minor",
            axis="both",
            color=minor_color,
            linewidth=minor_width,
            linestyle=IEEE_MINOR_GRID["linestyle"],
            alpha=minor_alpha,
        )
    setattr(ax, "_ieee_grid_mode", grid_mode)


def apply_compact_grid(ax) -> None:
    apply_ieee_grid(ax)


def place_reference_line_label(
    ax,
    value: float,
    label: str,
    *,
    x: float = 0.985,
    pad_points: float = 2.0,
    color: str = FIGURE_PRIORITY_COLORS["threshold"],
    horizontalalignment: str = "right",
    verticalalignment: str = "bottom",
    **text_kwargs: Any,
) -> Text:
    """Place a short reference/threshold label directly beside its line.

    ``x`` is an axes fraction and ``value`` remains in the axis data units,
    so the helper works for linear and logarithmic y axes alike. The small
    display-space offset keeps the label legible without changing data
    coordinates or adding a legend entry. The default is the inside right end.
    """

    if not label or not math.isfinite(float(value)):
        raise ValueError("value must be finite and label must be non-empty")
    if not 0.0 < float(x) <= 1.0:
        raise ValueError("x must be in the open-closed interval (0, 1]")
    if pad_points < 0.0:
        raise ValueError("pad_points must be non-negative")
    transform = mtransforms.offset_copy(
        ax.get_yaxis_transform(),
        fig=ax.figure,
        x=0.0,
        y=float(pad_points),
        units="points",
    )
    text = ax.text(
        float(x),
        float(value),
        label,
        transform=transform,
        color=color,
        ha=horizontalalignment,
        va=verticalalignment,
        clip_on=True,
        **text_kwargs,
    )
    text.set_gid("ieee-reference-line-label")
    return text


def apply_axis_cleanup(ax, keep_grid: bool = False) -> None:
    """Legacy cleanup; strict single-column plots keep all four spines."""

    warnings.warn(
        "apply_axis_cleanup is a legacy open-axis helper; use apply_single_column_axes instead",
        DeprecationWarning,
        stacklevel=2,
    )
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    if keep_grid:
        ax.grid(True, color=FIGURE_PRIORITY_COLORS["grid_major"], linewidth=0.4, alpha=0.7)
    else:
        ax.grid(False)


def _axes_tuple(axes: Iterable | Any) -> tuple:
    if hasattr(axes, "get_position"):
        return (axes,)
    result = tuple(axes)
    if not result:
        raise ValueError("at least one axes is required")
    return result


def _normalize_grid_mode(grid_mode: str) -> str:
    value = str(grid_mode).strip().lower()
    if value not in IEEE_GRID_MODES:
        allowed = ", ".join(IEEE_GRID_MODES)
        raise ValueError(f"grid_mode must be one of: {allowed}")
    return value


def _grid_modes_for_axes(axes: tuple, grid_mode: str | Sequence[str] | None) -> tuple[str, ...]:
    if grid_mode is None:
        return tuple(
            _normalize_grid_mode(getattr(ax, "_ieee_grid_mode", IEEE_DEFAULT_GRID_MODE))
            for ax in axes
        )
    if isinstance(grid_mode, str):
        return (_normalize_grid_mode(grid_mode),) * len(axes)
    modes = tuple(_normalize_grid_mode(value) for value in grid_mode)
    if len(modes) != len(axes):
        raise ValueError("grid_mode sequence must match the number of axes")
    return modes


def prepare_compact_ylabel(ax, *, x: float = -0.075) -> None:
    ax.yaxis.labelpad = 0.0
    ax.yaxis.set_label_coords(x, 0.5)


def align_y_tick_labels(axes, *, pad_points: float = 1.5) -> None:
    """Align visible y tick-label right edges in display coordinates."""

    axes = _axes_tuple(axes)
    fig = axes[0].figure
    fig.canvas.draw()
    target_right = min(ax.bbox.x0 for ax in axes) - pad_points * fig.dpi / 72.0
    for ax in axes:
        anchor = (target_right - ax.bbox.x0) / ax.bbox.width
        for label in ax.get_yticklabels():
            if label.get_visible() and label.get_text():
                label.set_x(anchor)
                label.set_horizontalalignment("right")
    fig.canvas.draw()


def place_ylabels_clear_of_ticks(axes, *, pad_points: float = 1.2) -> None:
    """Place y-axis titles just beyond the widest visible tick-label block."""

    axes = _axes_tuple(axes)
    fig = axes[0].figure
    # Automatic y-label positions use a blended transform whose x component
    # is already in display pixels. Normalize every label to axes coordinates
    # before measuring, so the shared display-space adjustment below cannot
    # accidentally reinterpret a pixel value as an axes fraction.
    for ax in axes:
        ax.yaxis.set_label_coords(0.0, 0.5, transform=ax.transAxes)
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    tick_labels = [
        label
        for ax in axes
        for label in ax.get_yticklabels()
        if label.get_visible() and label.get_text()
    ]
    if not tick_labels:
        return
    target_right = min(label.get_window_extent(renderer).x0 for label in tick_labels)
    target_right -= pad_points * fig.dpi / 72.0
    for ax in axes:
        label = ax.yaxis.label
        bbox = label.get_window_extent(renderer)
        x, y = label.get_position()
        x += (target_right - bbox.x1) / ax.bbox.width
        ax.yaxis.set_label_coords(x, y, transform=ax.transAxes)
        label.set_horizontalalignment("center")
    fig.canvas.draw()


def place_panel_labels_below(
    axes,
    labels: Sequence[str] | None = None,
    *,
    y: float = -0.10,
    gap_points: float = 2.0,
) -> list[Text]:
    """Place idempotent, centered panel labels below each panel's x label."""

    axes = _axes_tuple(axes)
    labels = list(labels or [f"({chr(97 + index)})" for index in range(len(axes))])
    if len(labels) != len(axes):
        raise ValueError("labels must match the number of axes")
    result: list[Text] = []
    for ax, label in zip(axes, labels):
        existing = [text for text in ax.texts if text.get_gid() == "ieee-single-column-panel-label"]
        text = existing[0] if existing else ax.text(0.5, y, label, transform=ax.transAxes, ha="center", va="top")
        for duplicate in existing[1:]:
            duplicate.remove()
        text.set_text(label)
        text.set_position((0.5, y))
        text.set_horizontalalignment("center")
        text.set_verticalalignment("top")
        text.set_gid("ieee-single-column-panel-label")
        result.append(text)

    axes[0].figure.canvas.draw()
    renderer = axes[0].figure.canvas.get_renderer()
    gap_px = gap_points * axes[0].figure.dpi / 72.0
    for ax, text in zip(axes, result):
        xlabel = ax.xaxis.label
        tick_labels = [item for item in ax.get_xticklabels() if item.get_visible() and item.get_text()]
        anchors = [xlabel.get_window_extent(renderer)] if xlabel.get_visible() and xlabel.get_text() else []
        anchors.extend(item.get_window_extent(renderer) for item in tick_labels)
        anchor_bottom = min((bbox.y0 for bbox in anchors), default=ax.bbox.y0)
        bbox = text.get_window_extent(renderer)
        x, current_y = text.get_position()
        text.set_position((x, current_y + (anchor_bottom - gap_px - bbox.y1) / ax.bbox.height))
    axes[0].figure.canvas.draw()
    return result


def _horizontal_overlap_ratio(first, second) -> float:
    overlap = max(0.0, min(first.x1, second.x1) - max(first.x0, second.x0))
    width = min(first.width, second.width)
    return overlap / width if width > 0.0 else 0.0


def _stacked_axes_pairs(axes: tuple) -> list[tuple[int, Any, int, Any]]:
    """Return nearest vertically adjacent axes with substantially shared x extent."""

    pairs: list[tuple[int, Any, int, Any]] = []
    positions = [ax.get_position().frozen() for ax in axes]
    for upper_index, (upper, upper_position) in enumerate(zip(axes, positions)):
        candidates: list[tuple[float, int, Any]] = []
        for lower_index, (lower, lower_position) in enumerate(zip(axes, positions)):
            if lower is upper or lower_position.y1 > upper_position.y0 + 1e-9:
                continue
            if _horizontal_overlap_ratio(upper_position, lower_position) < 0.80:
                continue
            candidates.append((lower_position.y1, lower_index, lower))
        if candidates:
            _top, lower_index, lower = max(candidates, key=lambda item: item[0])
            pairs.append((upper_index, upper, lower_index, lower))
    return pairs


def _lower_visible_content_edge(ax, renderer) -> float:
    candidates: list[Text] = []
    if ax.xaxis.label.get_visible() and ax.xaxis.label.get_text():
        candidates.append(ax.xaxis.label)
    offset_text = ax.xaxis.get_offset_text()
    if offset_text.get_visible() and offset_text.get_text():
        candidates.append(offset_text)
    candidates.extend(
        label for label in ax.get_xticklabels() if label.get_visible() and label.get_text()
    )
    candidates.extend(
        text
        for text in ax.texts
        if text.get_gid() == "ieee-single-column-panel-label" and text.get_visible() and text.get_text()
    )
    if not candidates:
        return float(ax.bbox.y0)
    return min(float(item.get_window_extent(renderer).y0) for item in candidates)


def measure_stacked_panel_gaps(fig, axes: Iterable) -> list[dict[str, float | int]]:
    """Measure axes-box and visible-content gaps for vertically stacked panels."""

    axes_tuple = _axes_tuple(axes)
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    scale = 72.0 / fig.dpi
    result: list[dict[str, float | int]] = []
    for upper_index, upper, lower_index, lower in _stacked_axes_pairs(axes_tuple):
        result.append(
            {
                "upper_axes": upper_index,
                "lower_axes": lower_index,
                "axes_box_gap_pt": float(upper.bbox.y0 - lower.bbox.y1) * scale,
                "content_clearance_pt": float(_lower_visible_content_edge(upper, renderer) - lower.bbox.y1) * scale,
            }
        )
    return result


def compact_stacked_panel_gaps(
    fig,
    axes: Iterable,
    *,
    target_points: float = IEEE_STACKED_CONTENT_GAP_PT,
    reflow: Callable[[], None] | None = None,
    max_iterations: int = 4,
) -> list[dict[str, float | int]]:
    """Fit stacked-panel spacing to a display-space visible-content target."""

    axes_tuple = _axes_tuple(axes)
    if target_points < 0.0 or max_iterations < 1:
        raise ValueError("target_points must be non-negative and iterations positive")
    if len(axes_tuple) < 2:
        return []
    for _ in range(max_iterations):
        if reflow:
            reflow()
        gaps = measure_stacked_panel_gaps(fig, axes_tuple)
        changed = False
        for gap in gaps:
            error_points = float(gap["content_clearance_pt"]) - target_points
            if abs(error_points) <= 0.05:
                continue
            upper = axes_tuple[int(gap["upper_axes"])]
            lower = axes_tuple[int(gap["lower_axes"])]
            upper_position = upper.get_position().frozen()
            lower_position = lower.get_position().frozen()
            half_delta = (error_points / 72.0 / fig.get_figheight()) / 2.0
            upper_bottom = upper_position.y0 - half_delta
            lower_top = lower_position.y1 + half_delta
            if not 0.0 < upper_bottom < upper_position.y1:
                raise ValueError("stacked-panel repair would collapse the upper axes")
            if not lower_position.y0 < lower_top < 1.0:
                raise ValueError("stacked-panel repair would collapse the lower axes")
            upper.set_position(
                (upper_position.x0, upper_bottom, upper_position.width, upper_position.y1 - upper_bottom)
            )
            lower.set_position(
                (lower_position.x0, lower_position.y0, lower_position.width, lower_top - lower_position.y0)
            )
            changed = True
        if not changed:
            break
    if reflow:
        reflow()
    return measure_stacked_panel_gaps(fig, axes_tuple)


def add_panel_labels(axes: Iterable, labels: Sequence[str] | None = None) -> None:
    """Legacy label helper; new stacked plots should use place_panel_labels_below."""

    axes_tuple = _axes_tuple(axes)
    labels = list(labels or [f"({chr(97 + index)})" for index in range(len(axes_tuple))])
    if len(labels) != len(axes_tuple):
        raise ValueError("labels must match the number of axes")
    for ax, label in zip(axes_tuple, labels):
        ax.text(-0.12, 1.04, label, transform=ax.transAxes, ha="left", va="bottom", fontweight="bold")


def _apply_outer_margin_adjustment(
    axes: tuple,
    *,
    dx_left: float,
    dx_right: float,
    dy_bottom: float,
    dy_top: float,
) -> None:
    positions = {ax: ax.get_position().frozen() for ax in axes}
    for ax, position in positions.items():
        left = position.x0 + dx_left
        right = position.x1 + dx_right
        if not 0.0 < left < right < 1.0:
            raise ValueError("horizontal fit would place an axes outside the canvas")
        ax.set_position((left, position.y0, right - left, position.height))

    bottom_axes = min(axes, key=lambda item: item.get_position().y0)
    top_axes = max(axes, key=lambda item: item.get_position().y1)
    if bottom_axes is top_axes:
        position = bottom_axes.get_position().frozen()
        bottom = position.y0 + dy_bottom
        top = position.y1 + dy_top
        if not 0.0 < bottom < top < 1.0:
            raise ValueError("vertical fit would place an axes outside the canvas")
        bottom_axes.set_position((position.x0, bottom, position.width, top - bottom))
        return
    bottom_position = bottom_axes.get_position().frozen()
    bottom = bottom_position.y0 + dy_bottom
    if not 0.0 < bottom < bottom_position.y1:
        raise ValueError("bottom-panel fit would place an axes outside the canvas")
    bottom_axes.set_position((bottom_position.x0, bottom, bottom_position.width, bottom_position.y1 - bottom))
    top_position = top_axes.get_position().frozen()
    top = top_position.y1 + dy_top
    if not top_position.y0 < top < 1.0:
        raise ValueError("top-panel fit would place an axes outside the canvas")
    top_axes.set_position((top_position.x0, top_position.y0, top_position.width, top - top_position.y0))


def fit_outer_content_margins(
    fig,
    axes: Iterable,
    *,
    target_points: float = IEEE_SINGLE_COLUMN_MARGIN_PT,
    reflow: Callable[[], None] | None = None,
    max_iterations: int = 4,
) -> dict[str, float]:
    """Fit logical visible content to a common outer margin."""

    axes = _axes_tuple(axes)
    if target_points < 0 or max_iterations < 1:
        raise ValueError("target_points must be non-negative and iterations positive")
    target_px = target_points * fig.dpi / 72.0
    for _ in range(max_iterations):
        if reflow:
            reflow()
        fig.canvas.draw()
        bbox = fig.get_tightbbox(fig.canvas.get_renderer())
        if bbox is None:
            raise RuntimeError("could not determine the visible figure boundary")
        left_px = bbox.x0 * fig.dpi
        right_px = bbox.x1 * fig.dpi
        bottom_px = bbox.y0 * fig.dpi
        top_px = bbox.y1 * fig.dpi
        dx_left = (target_px - left_px) / fig.bbox.width
        dx_right = ((fig.bbox.width - target_px) - right_px) / fig.bbox.width
        dy_bottom = (target_px - bottom_px) / fig.bbox.height
        dy_top = ((fig.bbox.height - target_px) - top_px) / fig.bbox.height
        if max(abs(dx_left), abs(dx_right), abs(dy_bottom), abs(dy_top)) < 1e-5:
            break
        _apply_outer_margin_adjustment(axes, dx_left=dx_left, dx_right=dx_right, dy_bottom=dy_bottom, dy_top=dy_top)
    if reflow:
        reflow()
    fig.canvas.draw()
    bbox = fig.get_tightbbox(fig.canvas.get_renderer())
    if bbox is None:
        raise RuntimeError("could not determine the fitted figure boundary")
    return {
        "left": bbox.x0 * 72.0,
        "right": (fig.get_figwidth() - bbox.x1) * 72.0,
        "bottom": bbox.y0 * 72.0,
        "top": (fig.get_figheight() - bbox.y1) * 72.0,
    }


def _measure_rendered_ink(fig, *, measurement_dpi: int = 600, background_tolerance: int = 5) -> dict[str, float]:
    if measurement_dpi <= 0:
        raise ValueError("measurement_dpi must be positive")
    measurement_figure = copy.deepcopy(fig)
    try:
        # Force a transform refresh even if a caller supplied an inconsistent
        # private _dpi value.  The source figure is never mutated.
        measurement_figure.set_dpi(float(measurement_dpi) + 1.0)
        measurement_figure.set_dpi(float(measurement_dpi))
        canvas = FigureCanvasAgg(measurement_figure)
        canvas.draw()
        rgba = np.asarray(canvas.buffer_rgba())
        background = np.rint(np.asarray(measurement_figure.get_facecolor()[:3]) * 255).astype(np.int16)
        difference = np.max(np.abs(rgba[:, :, :3].astype(np.int16) - background), axis=2)
        visible = difference > background_tolerance
        y_indices, x_indices = np.nonzero(visible)
        if not len(x_indices):
            raise RuntimeError("could not determine rendered ink boundary")
        height_px, width_px = visible.shape
        return {
            "left": float(x_indices.min()) * 72.0 / measurement_dpi,
            "right": float(width_px - 1 - x_indices.max()) * 72.0 / measurement_dpi,
            "bottom": float(height_px - 1 - y_indices.max()) * 72.0 / measurement_dpi,
            "top": float(y_indices.min()) * 72.0 / measurement_dpi,
        }
    finally:
        measurement_figure.clear()


def fit_rendered_ink_margins(
    fig,
    axes: Iterable,
    *,
    target_points: float = IEEE_SINGLE_COLUMN_MARGIN_PT,
    reflow: Callable[[], None] | None = None,
    max_iterations: int = 4,
    measurement_dpi: int = 600,
    background_tolerance: int = 5,
) -> dict[str, float]:
    """Fit the actual rasterized ink boundary without changing canvas size."""

    axes = _axes_tuple(axes)
    target_px = target_points * measurement_dpi / 72.0
    for _ in range(max_iterations):
        if reflow:
            reflow()
        margins = _measure_rendered_ink(fig, measurement_dpi=measurement_dpi, background_tolerance=background_tolerance)
        width_px = fig.get_figwidth() * measurement_dpi
        height_px = fig.get_figheight() * measurement_dpi
        dx_left = (target_px - margins["left"] * measurement_dpi / 72.0) / width_px
        dx_right = (margins["right"] * measurement_dpi / 72.0 - target_px) / width_px
        dy_bottom = (target_px - margins["bottom"] * measurement_dpi / 72.0) / height_px
        dy_top = (margins["top"] * measurement_dpi / 72.0 - target_px) / height_px
        if max(abs(dx_left), abs(dx_right), abs(dy_bottom), abs(dy_top)) < 1e-5:
            break
        _apply_outer_margin_adjustment(axes, dx_left=dx_left, dx_right=dx_right, dy_bottom=dy_bottom, dy_top=dy_top)
    if reflow:
        reflow()
    return _measure_rendered_ink(fig, measurement_dpi=measurement_dpi, background_tolerance=background_tolerance)


def _finite_data(artist: Line2D | PathCollection) -> tuple[np.ndarray, np.ndarray]:
    try:
        if isinstance(artist, Line2D):
            x = np.asarray(artist.get_xdata(), dtype=float)
            y = np.asarray(artist.get_ydata(), dtype=float)
        else:
            offsets = np.asarray(artist.get_offsets(), dtype=float)
            if offsets.ndim != 2 or offsets.shape[1] < 2:
                return np.array([]), np.array([])
            x, y = offsets[:, 0], offsets[:, 1]
    except (TypeError, ValueError):
        return np.array([]), np.array([])
    finite = np.isfinite(x) & np.isfinite(y)
    return x[finite], y[finite]


def _overlap_points(first, second, dpi: float) -> tuple[float, float]:
    x = max(0.0, min(first.x1, second.x1) - max(first.x0, second.x0)) * 72.0 / dpi
    y = max(0.0, min(first.y1, second.y1) - max(first.y0, second.y0)) * 72.0 / dpi
    return x, y


def _approved_palette_status(profile: Mapping[str, Any] | None) -> str:
    if not profile:
        return "unconfirmed"
    color_map = profile.get("figure_color_map", profile.get("color_map", {}))
    return str(profile.get("palette_status", color_map.get("palette_status", "unconfirmed")))


def propose_figure_color_map(
    roles: Sequence[str],
    *,
    palette: str | None = None,
    data_kind: str = "categorical",
    center: float | None = None,
) -> dict[str, Any]:
    """Return a proposal only; this function never freezes a paper profile."""

    roles = [str(role) for role in roles]
    data_roles = [role for role in roles if role not in {"reference", "threshold", "delta", "grid", "uncertainty"}]
    if len(set(roles)) != len(roles):
        raise ValueError("roles must be unique")
    if data_kind not in {"categorical", "continuous", "diverging"}:
        raise ValueError("data_kind must be categorical, continuous, or diverging")

    if data_kind == "continuous":
        selected = palette or "cividis"
        if selected not in {"cividis", "viridis"}:
            raise ValueError("continuous data must use cividis or viridis")
        return {
            "data_kind": data_kind,
            "colormap": selected,
            "palette_status": "proposed",
            "roles": {"reference": FIGURE_PRIORITY_COLORS["reference"], "threshold": "#000000", "delta": "#000000"},
            "confirmation_required": True,
        }

    if data_kind == "diverging":
        if center is None or not math.isfinite(float(center)):
            raise ValueError("diverging data requires a finite center")
        selected = palette or "tol_nightfall"
        if selected != "tol_nightfall":
            raise ValueError("the validated diverging palette is tol_nightfall")
        return {
            "data_kind": data_kind,
            "palette": selected,
            "center": float(center),
            "colors": list(TOL_NIGHTFALL),
            "palette_version": "Paul Tol 2021 static values",
            "palette_status": "proposed",
            "roles": {"reference": FIGURE_PRIORITY_COLORS["reference"], "threshold": "#000000", "delta": "#000000"},
            "confirmation_required": True,
        }

    selected = palette or (
        "tol_high_contrast" if len(data_roles) <= 3 else "tol_bright" if len(data_roles) <= 7 else "tol_muted"
    )
    if selected not in {"tol_high_contrast", "tol_bright", "tol_muted"}:
        raise ValueError(f"unknown palette: {selected}")
    colors = PALETTE_LIBRARY[selected]
    if len(data_roles) > len(colors):
        raise ValueError(f"{selected} provides only {len(colors)} distinct categorical colors")
    mapping: dict[str, str] = {}
    for index, role in enumerate(data_roles):
        mapping[role] = colors[index]
    mapping.update({"reference": FIGURE_PRIORITY_COLORS["reference"], "threshold": "#000000", "delta": "#000000"})
    marker_cycle = cycle(("o", "s", "^", "D", "v", "P", "X", "<", ">", "h"))
    linestyle_cycle = cycle(("-", "--", "-.", ":", (0, (5, 2)), (0, (2, 2)), (0, (7, 2, 1, 2))))
    return {
        "data_kind": data_kind,
        "palette": selected,
        "palette_version": "Paul Tol 2021 static values",
        "palette_status": "proposed",
        "roles": mapping,
        "markers": {role: next(marker_cycle) for role in data_roles},
        "linestyles": {role: next(linestyle_cycle) for role in data_roles},
        "confirmation_required": True,
    }


def freeze_figure_color_map(
    profile_path: str | Path,
    mapping: Mapping[str, Any],
    *,
    confirmed_by: str = "user",
    confirmed_at: str | None = None,
) -> dict[str, Any]:
    """Persist a palette only after explicit user confirmation."""

    if confirmed_by != "user":
        raise PermissionError("only an explicit user confirmation can freeze a palette")
    profile_file = Path(profile_path)
    profile: dict[str, Any] = {}
    if profile_file.is_file():
        profile = json.loads(profile_file.read_text(encoding="utf-8"))
    existing = profile.get("figure_color_map", {})
    if existing.get("palette_status") == "confirmed":
        stable_keys = {"data_kind", "palette", "colormap", "center", "roles", "markers", "linestyles", "colors"}
        previous_payload = {key: existing.get(key) for key in stable_keys if key in existing}
        proposed_payload = {key: mapping.get(key) for key in stable_keys if key in mapping}
        proposed_payload = json.loads(json.dumps(proposed_payload))
        if previous_payload != proposed_payload:
            raise PermissionError("the paper's confirmed figure color map is frozen")
        return profile
    frozen = dict(mapping)
    frozen["palette_status"] = "confirmed"
    frozen["confirmed_by"] = confirmed_by
    frozen["confirmed_at"] = confirmed_at or datetime.now().astimezone().isoformat(timespec="seconds")
    profile["palette_status"] = "confirmed"
    profile["figure_color_map"] = frozen
    profile_file.parent.mkdir(parents=True, exist_ok=True)
    profile_file.write_text(json.dumps(profile, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return profile


def _artist_uses_data_coordinates(ax, artist: Line2D | PathCollection) -> bool:
    if isinstance(artist, Line2D):
        return artist.get_transform() == ax.transData
    return artist.get_offset_transform() == ax.transData


def _artist_marker_radius_px(artist: Line2D | PathCollection, dpi: float) -> float:
    if isinstance(artist, Line2D):
        marker = artist.get_marker()
        if marker is None or str(marker).strip().lower() in {"", "none", " ", "null"}:
            return 0.0
        size_points = float(artist.get_markersize())
    else:
        sizes = np.asarray(artist.get_sizes(), dtype=float)
        size_points = math.sqrt(float(np.nanmax(sizes))) if sizes.size else float(mpl.rcParams["lines.markersize"])
    return max(0.0, size_points * dpi / 144.0)


def _expand_scaled_limits(ax, axis_name: str, values: np.ndarray, radius_px: float) -> bool:
    axis = ax.xaxis if axis_name == "x" else ax.yaxis
    limits = ax.get_xlim() if axis_name == "x" else ax.get_ylim()
    dimension_px = ax.bbox.width if axis_name == "x" else ax.bbox.height
    if dimension_px <= 0 or not len(values):
        return False
    transform = axis.get_transform()
    try:
        scaled_limits = np.asarray(transform.transform(np.asarray(limits, dtype=float)), dtype=float)
        scaled_values = np.asarray(transform.transform(np.asarray(values, dtype=float)), dtype=float)
    except (TypeError, ValueError, OverflowError):
        return False
    scaled_values = scaled_values[np.isfinite(scaled_values)]
    if len(scaled_values) == 0 or not np.all(np.isfinite(scaled_limits)):
        return False
    inverted = bool(scaled_limits[0] > scaled_limits[1])
    lower, upper = sorted(float(value) for value in scaled_limits)
    data_lower, data_upper = float(scaled_values.min()), float(scaled_values.max())
    span = max(upper - lower, data_upper - data_lower, np.finfo(float).eps)
    fraction = min(0.20, max(0.0, (radius_px + 0.75) / dimension_px))
    padding = max(span * 0.005, span * fraction / max(1.0 - 2.0 * fraction, 0.5))
    new_lower = min(lower, data_lower - padding) if data_lower - lower < padding else lower
    new_upper = max(upper, data_upper + padding) if upper - data_upper < padding else upper
    if math.isclose(new_lower, lower, rel_tol=1e-12, abs_tol=1e-15) and math.isclose(
        new_upper, upper, rel_tol=1e-12, abs_tol=1e-15
    ):
        return False
    restored = np.asarray(transform.inverted().transform(np.asarray([new_lower, new_upper])), dtype=float)
    if not np.all(np.isfinite(restored)):
        return False
    new_limits = (float(restored[1]), float(restored[0])) if inverted else (float(restored[0]), float(restored[1]))
    if axis_name == "x":
        ax.set_xlim(new_limits)
    else:
        ax.set_ylim(new_limits)
    return True


def _ensure_marker_headroom(axes: tuple, *, locked_limits: bool) -> list[str]:
    if locked_limits:
        return []
    actions: list[str] = []
    axes[0].figure.canvas.draw()
    for index, ax in enumerate(axes):
        x_values: list[np.ndarray] = []
        y_values: list[np.ndarray] = []
        max_radius = 0.0
        for artist in [*ax.lines, *ax.collections]:
            if not isinstance(artist, (Line2D, PathCollection)) or not _artist_uses_data_coordinates(ax, artist):
                continue
            radius = _artist_marker_radius_px(artist, ax.figure.dpi)
            if radius <= 0:
                continue
            x, y = _finite_data(artist)
            if len(x):
                x_values.append(x)
                y_values.append(y)
                max_radius = max(max_radius, radius)
        if not x_values:
            continue
        changed_x = _expand_scaled_limits(ax, "x", np.concatenate(x_values), max_radius)
        changed_y = _expand_scaled_limits(ax, "y", np.concatenate(y_values), max_radius)
        if changed_x or changed_y:
            axes[0].figure.canvas.draw()
            actions.append(f"axes[{index}] marker headroom expanded")
    return actions


def repair_single_column_figure(
    fig,
    axes: Iterable,
    *,
    target_margin_points: float = IEEE_SINGLE_COLUMN_MARGIN_PT,
    locked_limits: bool = False,
    panel_labels: Sequence[str] | None = None,
    font_resolution: FontResolution | None = None,
    grid_mode: str | Sequence[str] | None = None,
) -> dict[str, Any]:
    """Apply safe mechanical repairs and return measured layout metadata."""

    axes = _axes_tuple(axes)
    grid_modes = _grid_modes_for_axes(axes, grid_mode)
    resolution = font_resolution or resolve_ieee_serif_font()
    actions: list[str] = []
    conflicts: list[str] = []
    if not math.isclose(float(fig.get_figwidth()), IEEE_SINGLE_COLUMN_IN, rel_tol=0.0, abs_tol=1e-6):
        fig.set_size_inches(IEEE_SINGLE_COLUMN_IN, float(fig.get_figheight()), forward=True)
        actions.append("figure width set to 3.5 in")
    _apply_rcparams(family=resolution.family, base_font_size=8.0, marker_size=3.8, color_cycle=TOL_BRIGHT)
    fig.canvas.draw()
    for text in fig.findobj(Text):
        text.set_fontfamily(resolution.family)
        text.set_fontsize(8.0)
    for ax, mode in zip(axes, grid_modes):
        apply_single_column_axes(ax)
        apply_ieee_grid(ax, grid_mode=mode)
    actions.append("grid modes applied: " + ", ".join(grid_modes))
    fig.canvas.draw()
    for text in fig.findobj(Text):
        text.set_fontfamily(resolution.family)
        text.set_fontsize(8.0)
    actions.extend(_ensure_marker_headroom(axes, locked_limits=locked_limits))
    active_panel_labels: Sequence[str] | None = panel_labels
    if panel_labels:
        place_panel_labels_below(axes, panel_labels)

    def reflow() -> None:
        align_y_tick_labels(axes)
        place_ylabels_clear_of_ticks(axes)
        if active_panel_labels:
            place_panel_labels_below(axes, active_panel_labels)

    reflow()
    try:
        stacked_gaps = compact_stacked_panel_gaps(fig, axes, reflow=reflow)
        if stacked_gaps:
            actions.append(f"stacked content gaps fitted to {IEEE_STACKED_CONTENT_GAP_PT:g} pt")
    except ValueError as exc:
        conflicts.append(f"stacked-panel gap repair failed: {exc}")
        stacked_gaps = measure_stacked_panel_gaps(fig, axes)
    try:
        margins = fit_rendered_ink_margins(fig, axes, target_points=target_margin_points, reflow=reflow)
        actions.append(f"visible ink margins fitted to {target_margin_points:g} pt")
    except (RuntimeError, ValueError) as exc:
        conflicts.append(f"outer-margin repair failed: {exc}")
        margins = _measure_rendered_ink(fig)
    reflow()
    for text in fig.findobj(Text):
        text.set_fontfamily(resolution.family)
        text.set_fontsize(8.0)
    fig.canvas.draw()
    result = {
        "font": resolution.to_dict(),
        "outer_ink_margin_pt": margins,
        "stacked_panel_gaps": stacked_gaps,
        "grid_modes": list(grid_modes),
        "actions": actions,
        "conflicts": conflicts,
    }
    setattr(fig, "_ieee_single_column_repair", result)
    return result


def _check_artist_bounds(axes: tuple, errors: list[str]) -> None:
    for ax_index, ax in enumerate(axes):
        xlim, ylim = ax.get_xlim(), ax.get_ylim()
        xmin, xmax = min(xlim), max(xlim)
        ymin, ymax = min(ylim), max(ylim)
        for artist in [*ax.lines, *ax.collections]:
            if not isinstance(artist, (Line2D, PathCollection)) or not _artist_uses_data_coordinates(ax, artist):
                continue
            if not artist.get_clip_on():
                _append_unique(errors, f"axes[{ax_index}] data artist has clip_on=False")
            x, y = _finite_data(artist)
            if len(x) and (np.any(x < xmin) or np.any(x > xmax) or np.any(y < ymin) or np.any(y > ymax)):
                _append_unique(errors, f"axes[{ax_index}] data point lies outside its axis limits")


def _append_unique(items: list[str], value: str) -> None:
    if value not in items:
        items.append(value)


def _check_marker_bounds(axes: tuple, errors: list[str]) -> None:
    axes[0].figure.canvas.draw()
    for ax_index, ax in enumerate(axes):
        for artist in [*ax.lines, *ax.collections]:
            if not isinstance(artist, (Line2D, PathCollection)) or not _artist_uses_data_coordinates(ax, artist):
                continue
            radius = _artist_marker_radius_px(artist, ax.figure.dpi)
            if radius <= 0:
                continue
            x, y = _finite_data(artist)
            if not len(x):
                continue
            display = np.asarray(ax.transData.transform(np.column_stack((x, y))), dtype=float)
            outside = (
                np.any(display[:, 0] - radius < ax.bbox.x0 - 0.25)
                or np.any(display[:, 0] + radius > ax.bbox.x1 + 0.25)
                or np.any(display[:, 1] - radius < ax.bbox.y0 - 0.25)
                or np.any(display[:, 1] + radius > ax.bbox.y1 + 0.25)
            )
            if outside:
                _append_unique(errors, f"axes[{ax_index}] marker head crosses its axis frame")


def _drawn_tick_text_ids(axes: tuple) -> set[int]:
    result: set[int] = set()
    for ax in axes:
        for axis in (ax.xaxis, ax.yaxis):
            lower, upper = sorted(float(value) for value in axis.get_view_interval())
            for tick in (*axis.get_major_ticks(), *axis.get_minor_ticks()):
                location = float(tick.get_loc())
                if lower <= location <= upper:
                    if tick.label1.get_visible() and tick.label1.get_text():
                        result.add(id(tick.label1))
                    if tick.label2.get_visible() and tick.label2.get_text():
                        result.add(id(tick.label2))
    return result


def _text_and_legend_bboxes(fig, axes: tuple, *, include_ticks: bool) -> list[tuple[str, Any]]:
    all_tick_ids = {id(label) for ax in axes for label in (*ax.get_xticklabels(), *ax.get_yticklabels())}
    drawn_tick_ids = _drawn_tick_text_ids(axes)
    legends = [legend for legend in fig.findobj(Legend) if legend.get_visible()]
    legend_text_ids = {
        id(text)
        for legend in legends
        for text in [*legend.get_texts(), legend.get_title()]
        if text is not None
    }
    items: list[tuple[str, Any]] = []
    for text in fig.findobj(Text):
        if id(text) in legend_text_ids or not text.get_visible() or not text.get_text().strip():
            continue
        if id(text) in all_tick_ids and id(text) not in drawn_tick_ids:
            continue
        if not include_ticks and id(text) in all_tick_ids:
            continue
        kind = "tick_label" if id(text) in all_tick_ids else "text"
        items.append((kind, text))
    items.extend(("legend", legend) for legend in legends)
    return items


def _font_resolution_is_intact(resolution: FontResolution | None) -> bool:
    if resolution is None or resolution.family not in {"Times New Roman", "Liberation Serif"}:
        return False
    if set(resolution.files) != set(FONT_STYLE_FILES) or set(resolution.hashes) != set(FONT_STYLE_FILES):
        return False
    for style, path in resolution.files.items():
        if not path.is_file() or _sha256(path) != resolution.hashes.get(style):
            return False
        try:
            font = FT2Font(str(path))
        except Exception:
            return False
        if font.family_name != resolution.family or _style_for_path(path) != style:
            return False
    return resolution.regular_file == resolution.files["regular"]


def _mathtext_profile_is_approved(family: str) -> bool:
    expected = {
        "mathtext.fontset": "custom",
        "mathtext.default": "regular",
        "mathtext.rm": family,
        "mathtext.it": f"{family}:italic",
        "mathtext.bf": f"{family}:bold",
        "mathtext.bfit": f"{family}:italic:bold",
        "mathtext.cal": f"{family}:italic",
        "mathtext.sf": family,
        "mathtext.tt": family,
        "mathtext.fallback": None,
    }
    return all(mpl.rcParams[key] == value for key, value in expected.items())


def _visible_axis_gridlines(axis, which: str) -> list[Line2D]:
    getter = axis.get_major_ticks if which == "major" else axis.get_minor_ticks
    return [tick.gridline for tick in getter() if tick.gridline.get_visible()]


def _visible_gridlines(ax, which: str) -> list[Line2D]:
    return [
        *_visible_axis_gridlines(ax.xaxis, which),
        *_visible_axis_gridlines(ax.yaxis, which),
    ]


def _gridline_style_matches(line: Line2D, expected: Mapping[str, Any]) -> bool:
    dash_pattern = getattr(line, "_unscaled_dash_pattern", (None, None))[1]
    expected_dash = expected["linestyle"][1]
    return (
        to_hex(line.get_color()).upper() == str(expected["color"]).upper()
        and math.isclose(float(line.get_linewidth()), float(expected["linewidth"]), abs_tol=0.01)
        and math.isclose(float(line.get_alpha()), float(expected["alpha"]), abs_tol=0.01)
        and dash_pattern is not None
        and len(dash_pattern) == len(expected_dash)
        and all(
            math.isclose(float(actual), float(target), abs_tol=0.01)
            for actual, target in zip(dash_pattern, expected_dash)
        )
    )


def _check_grid_profile(ax, index: int, errors: list[str], grid_mode: str) -> None:
    expectations = {
        "x": (
            grid_mode in {"major_xy", "legacy_major_minor_xy"},
            grid_mode == "legacy_major_minor_xy",
        ),
        "y": (
            grid_mode in {"major_xy", "legacy_major_minor_xy"},
            grid_mode == "legacy_major_minor_xy",
        ),
    }
    for axis_name, axis in (("x", ax.xaxis), ("y", ax.yaxis)):
        for which, expected_visible, style_profile in (
            ("major", expectations[axis_name][0], IEEE_MAJOR_GRID),
            ("minor", expectations[axis_name][1], IEEE_MINOR_GRID),
        ):
            lines = _visible_axis_gridlines(axis, which)
            if expected_visible and not lines:
                _append_unique(errors, f"axes[{index}] {axis_name} {which} grid is missing for {grid_mode}")
            elif not expected_visible and lines:
                _append_unique(errors, f"axes[{index}] {axis_name} {which} grid is not allowed for {grid_mode}")
            elif expected_visible and any(not _gridline_style_matches(line, style_profile) for line in lines):
                _append_unique(errors, f"axes[{index}] {axis_name} {which} grid does not match the fixed profile")


def _check_display_alignment(fig, axes: tuple, errors: list[str], metrics: dict[str, Any]) -> None:
    if len(axes) < 2:
        return
    renderer = fig.canvas.get_renderer()
    tick_rights = [
        label.get_window_extent(renderer).x1
        for ax in axes
        for label in ax.get_yticklabels()
        if label.get_visible() and label.get_text()
    ]
    ylabel_rights = [
        ax.yaxis.label.get_window_extent(renderer).x1
        for ax in axes
        if ax.yaxis.label.get_visible() and ax.yaxis.label.get_text()
    ]
    if tick_rights:
        spread = (max(tick_rights) - min(tick_rights)) * 72.0 / fig.dpi
        metrics["ytick_right_edge_spread_pt"] = spread
        if spread > 0.25:
            _append_unique(errors, "stacked axes y-tick right edges are not display-aligned")
    if ylabel_rights:
        spread = (max(ylabel_rights) - min(ylabel_rights)) * 72.0 / fig.dpi
        metrics["ylabel_right_edge_spread_pt"] = spread
        if spread > 0.25:
            _append_unique(errors, "stacked axes y-label right edges are not display-aligned")


def _check_legend_data_overlap(fig, axes: tuple) -> bool:
    renderer = fig.canvas.get_renderer()
    for ax in axes:
        legend = ax.get_legend()
        if legend is None or not legend.get_visible():
            continue
        legend_bbox = legend.get_window_extent(renderer)
        for artist in [*ax.lines, *ax.collections]:
            if not isinstance(artist, (Line2D, PathCollection)) or not artist.get_visible():
                continue
            try:
                bbox = artist.get_window_extent(renderer)
            except Exception:
                continue
            if bbox.width > 0 and bbox.height > 0 and legend_bbox.overlaps(bbox):
                return True
    return False


def _palette_confirmation_valid(profile: Mapping[str, Any] | None) -> bool:
    if not profile:
        return False
    mapping = profile.get("figure_color_map", profile.get("color_map", {}))
    status = profile.get("palette_status", mapping.get("palette_status"))
    confirmed_by = mapping.get("confirmed_by", profile.get("palette_confirmed_by"))
    confirmed_at = mapping.get("confirmed_at", profile.get("palette_confirmed_at"))
    return status == "confirmed" and confirmed_by == "user" and bool(confirmed_at)


def preflight_single_column_figure(
    fig,
    axes: Iterable | None = None,
    *,
    mode: str = "draft",
    profile: Mapping[str, Any] | None = None,
    font_resolution: FontResolution | None = None,
    locked_limits: bool = False,
    grid_mode: str | Sequence[str] | None = None,
    raise_on_error: bool = False,
) -> dict[str, Any]:
    """Measure hard constraints and return a JSON-serializable report."""

    if mode not in {"draft", "formal"}:
        raise ValueError("mode must be 'draft' or 'formal'")
    axes_tuple = _axes_tuple(axes or fig.axes)
    grid_modes = _grid_modes_for_axes(axes_tuple, grid_mode)
    errors: list[str] = []
    warnings_list: list[str] = []
    visual_review: list[str] = ["final_size_preview"]
    metrics: dict[str, Any] = {
        "figsize_in": [float(value) for value in fig.get_size_inches()],
        "grid_modes": list(grid_modes),
    }
    if not math.isclose(float(fig.get_figwidth()), IEEE_SINGLE_COLUMN_IN, rel_tol=0.0, abs_tol=1e-6):
        errors.append(f"figure width must be exactly {IEEE_SINGLE_COLUMN_IN} in")
    if not _font_resolution_is_intact(font_resolution):
        errors.append("approved serif font files are incomplete or fail SHA-256 integrity")
    elif not _mathtext_profile_is_approved(font_resolution.family):
        errors.append("math text is not locked to the approved serif font without fallback")
    if _version_tuple(mpl.__version__) < SUPPORTED_MATPLOTLIB_MIN or _version_tuple(mpl.__version__) >= SUPPORTED_MATPLOTLIB_MAX:
        visual_review.append("unvalidated_matplotlib_version")

    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    margins = _measure_rendered_ink(fig)
    metrics["outer_ink_margin_pt"] = margins
    lower = IEEE_SINGLE_COLUMN_MARGIN_PT - IEEE_SINGLE_COLUMN_MARGIN_TOLERANCE_PT
    upper = IEEE_SINGLE_COLUMN_MARGIN_PT + IEEE_SINGLE_COLUMN_MARGIN_TOLERANCE_PT
    if any(value < lower or value > upper for value in margins.values()):
        errors.append("rendered ink outer margin is outside the 3 pt profile band")

    repair_metadata = getattr(fig, "_ieee_single_column_repair", {})
    for conflict in repair_metadata.get("conflicts", []):
        _append_unique(errors, str(conflict))

    drawn_tick_ids = _drawn_tick_text_ids(axes_tuple)
    all_tick_ids = {id(label) for ax in axes_tuple for label in (*ax.get_xticklabels(), *ax.get_yticklabels())}
    visible_texts = [
        text
        for text in fig.findobj(Text)
        if text.get_visible() and text.get_text().strip()
        and (id(text) not in all_tick_ids or id(text) in drawn_tick_ids)
    ]
    if any(text.get_fontfamily()[0] != font_resolution.family for text in visible_texts if font_resolution):
        errors.append("visible text contains a non-approved font family")
    if any(not math.isclose(float(text.get_fontsize()), 8.0, abs_tol=0.05) for text in visible_texts):
        errors.append("visible text contains a font size other than 8 pt")

    for index, (ax, selected_grid_mode) in enumerate(zip(axes_tuple, grid_modes)):
        for spine in ax.spines.values():
            if (
                not spine.get_visible()
                or not math.isclose(spine.get_linewidth(), 0.7, abs_tol=0.06)
                or to_hex(spine.get_edgecolor()).upper() != "#000000"
            ):
                errors.append(f"axes[{index}] frame is not the four-sided 0.7 pt profile")
                break
        for tick in (*ax.xaxis.get_major_ticks(), *ax.yaxis.get_major_ticks()):
            if getattr(tick, "_tickdir", "in") != "in" or not tick.tick1line.get_visible() or not tick.tick2line.get_visible():
                errors.append(f"axes[{index}] does not have inward major ticks on both sides")
                break
        _check_grid_profile(ax, index, errors, selected_grid_mode)

    items = _text_and_legend_bboxes(fig, axes_tuple, include_ticks=True)
    canvas_bbox = fig.bbox
    for kind, artist in items:
        bbox = artist.get_window_extent(renderer)
        if bbox.x0 < -0.5 or bbox.y0 < -0.5 or bbox.x1 > canvas_bbox.width + 0.5 or bbox.y1 > canvas_bbox.height + 0.5:
            _append_unique(errors, f"{kind} is clipped by the figure canvas")
    collision_items = _text_and_legend_bboxes(fig, axes_tuple, include_ticks=False)
    for first_index, (first_kind, first_artist) in enumerate(collision_items):
        first_bbox = first_artist.get_window_extent(renderer)
        for second_kind, second_artist in collision_items[first_index + 1 :]:
            x_overlap, y_overlap = _overlap_points(first_bbox, second_artist.get_window_extent(renderer), fig.dpi)
            if x_overlap > 0.5 and y_overlap > 0.5:
                _append_unique(errors, f"independent {first_kind}/{second_kind} text boxes collide")
    _check_artist_bounds(axes_tuple, errors)
    _check_marker_bounds(axes_tuple, errors)
    _check_display_alignment(fig, axes_tuple, errors, metrics)
    stacked_gaps = measure_stacked_panel_gaps(fig, axes_tuple)
    metrics["stacked_panel_gaps"] = stacked_gaps
    for gap in stacked_gaps:
        clearance = float(gap["content_clearance_pt"])
        if abs(clearance - IEEE_STACKED_CONTENT_GAP_PT) > IEEE_STACKED_CONTENT_GAP_TOLERANCE_PT:
            _append_unique(errors, "stacked panel visible-content clearance is outside the 4 pt profile band")
    if _check_legend_data_overlap(fig, axes_tuple):
        visual_review.append("legend_data_overlap")

    palette_status = _approved_palette_status(profile)
    metrics["palette_status"] = palette_status
    if mode == "formal" and not _palette_confirmation_valid(profile):
        errors.append("formal export requires a user-confirmed, timestamped figure color map")
    if visual_review:
        approval = (profile or {}).get("visual_review_approval", {})
        approval_valid = approval.get("approved_by") == "user" and bool(approval.get("approved_at"))
        approved_reasons = set(approval.get("reasons", [])) if approval_valid else set()
        unresolved = [reason for reason in visual_review if reason not in approved_reasons]
        metrics["visual_review_approval"] = dict(approval)
        if mode == "formal" and unresolved:
            errors.append("formal export requires user approval for visual review reasons: " + ", ".join(unresolved))
    if locked_limits:
        warnings_list.append("axis limits were declared locked; marker headroom was not changed")

    report = PreflightReport(errors, warnings_list, visual_review, metrics).to_dict()
    if raise_on_error and report["errors"]:
        raise FigurePreflightError(report)
    return report


def _read_profile(profile_path: str | Path | None) -> dict[str, Any]:
    if profile_path is None:
        return {}
    path = Path(profile_path)
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _runtime_metadata_from_environment() -> dict[str, Any]:
    """Return adapter-provided runtime provenance without inventing values."""

    environment_keys = {
        "runtime_root": "PAPER_FIGURE_REVIEW_RUNTIME_ROOT",
        "python_executable": "PAPER_FIGURE_REVIEW_PYTHON",
        "python_version": "PAPER_FIGURE_REVIEW_PYTHON_VERSION",
        "matplotlib_version": "PAPER_FIGURE_REVIEW_MATPLOTLIB_VERSION",
        "scienceplots_version": "PAPER_FIGURE_REVIEW_SCIENCEPLOTS_VERSION",
        "draft_variant": "PAPER_FIGURE_REVIEW_DRAFT_VARIANT",
    }
    metadata = {
        key: os.environ[name]
        for key, name in environment_keys.items()
        if os.environ.get(name)
    }
    metadata["execution_source"] = "fixed_runtime_adapter" if metadata.get("runtime_root") else "direct_python"
    metadata["formal_style_source"] = "ieee_plot_style.py"
    return metadata


def _parse_svg_length_points(value: str) -> float:
    match = re.fullmatch(r"\s*([0-9]+(?:\.[0-9]+)?)\s*(pt|in|px)?\s*", value)
    if not match:
        raise ValueError(f"unsupported SVG physical length: {value}")
    number = float(match.group(1))
    unit = match.group(2) or "px"
    return number if unit == "pt" else number * 72.0 if unit == "in" else number * 72.0 / 96.0


def _svg_font_families(root: ET.Element) -> list[str]:
    families: set[str] = set()
    for element in root.iter():
        style = element.attrib.get("style", "")
        match = re.search(r"(?:^|;)\s*font-family\s*:\s*([^;]+)", style)
        if not match:
            continue
        for value in match.group(1).split(","):
            family = value.strip().strip("'\"")
            if family:
                families.add(family)
    return sorted(families)


def _pdf_base_fonts(raw: bytes) -> list[str]:
    names = re.findall(rb"/BaseFont\s*/(?:[A-Z]{6}\+)?([^/\s<>()\[\]]+)", raw)
    return sorted({name.decode("latin-1") for name in names})


def _approved_pdf_font_names(resolution: FontResolution) -> list[str]:
    return sorted({FT2Font(str(path)).postscript_name for path in resolution.files.values()})


def _inspect_export_geometry(
    path: Path,
    *,
    expected_width_in: float,
    expected_height_in: float,
    dpi: int,
    font_resolution: FontResolution,
) -> dict[str, Any]:
    suffix = path.suffix.lower()
    result: dict[str, Any] = {
        "path": str(path),
        "bytes": path.stat().st_size,
        "sha256": _sha256(path),
    }
    if suffix == ".png":
        with path.open("rb") as handle:
            header = handle.read(24)
        if len(header) < 24 or header[:8] != b"\x89PNG\r\n\x1a\n":
            raise ValueError(f"invalid PNG header: {path}")
        width_px, height_px = struct.unpack(">II", header[16:24])
        result.update(
            {
                "pixel_size": [width_px, height_px],
                "physical_size_in": [width_px / dpi, height_px / dpi],
                "font_validation": {
                    "ok": True,
                    "verifiable": False,
                    "approved_family": font_resolution.family,
                    "reason": "raster output inherits the audited render configuration",
                },
            }
        )
    elif suffix == ".svg":
        root = ET.parse(path).getroot()
        width_pt = _parse_svg_length_points(root.attrib["width"])
        height_pt = _parse_svg_length_points(root.attrib["height"])
        families = _svg_font_families(root)
        unexpected = sorted(set(families) - {font_resolution.family})
        result.update(
            {
                "physical_size_in": [width_pt / 72.0, height_pt / 72.0],
                "svg_size_pt": [width_pt, height_pt],
                "font_validation": {
                    "ok": bool(families) and not unexpected,
                    "verifiable": True,
                    "approved_family": font_resolution.family,
                    "actual_families": families,
                    "unexpected_families": unexpected,
                },
            }
        )
    elif suffix == ".pdf":
        raw = path.read_bytes()
        matches = re.findall(
            rb"/MediaBox\s*\[\s*([-+0-9.]+)\s+([-+0-9.]+)\s+([-+0-9.]+)\s+([-+0-9.]+)\s*\]",
            raw,
        )
        if not matches:
            raise ValueError(f"PDF MediaBox is missing: {path}")
        x0, y0, x1, y1 = (float(value) for value in matches[0])
        width_pt, height_pt = x1 - x0, y1 - y0
        actual_fonts = _pdf_base_fonts(raw)
        approved_fonts = _approved_pdf_font_names(font_resolution)
        unexpected = sorted(set(actual_fonts) - set(approved_fonts))
        result.update(
            {
                "physical_size_in": [width_pt / 72.0, height_pt / 72.0],
                "pdf_media_box_pt": [x0, y0, x1, y1],
                "font_validation": {
                    "ok": bool(actual_fonts) and not unexpected,
                    "verifiable": True,
                    "approved_family": font_resolution.family,
                    "approved_postscript_names": approved_fonts,
                    "actual_postscript_names": actual_fonts,
                    "unexpected_postscript_names": unexpected,
                },
            }
        )
    else:  # pragma: no cover - caller validates formats
        raise ValueError(f"unsupported export format: {suffix}")

    actual_width, actual_height = result["physical_size_in"]
    result["exact_size"] = math.isclose(actual_width, expected_width_in, abs_tol=1.0 / max(dpi, 72)) and math.isclose(
        actual_height, expected_height_in, abs_tol=1.0 / max(dpi, 72)
    )
    return result


def export_ieee_single_column(
    fig,
    stem: str,
    output_dir: str | Path = ".",
    *,
    mode: str = "draft",
    profile_path: str | Path | None = None,
    profile: Mapping[str, Any] | None = None,
    formats: Sequence[str] = ("pdf", "svg", "png"),
    dpi: int = 600,
    locked_limits: bool = False,
    panel_labels: Sequence[str] | None = None,
    grid_mode: str | Sequence[str] | None = None,
) -> list[Path]:
    """Repair, preflight and export a strict single-column figure.

    Draft artifacts are isolated under ``output_dir/drafts``.  Formal output
    requires a confirmed palette and a timestamped final-size visual review.
    """

    if mode not in {"draft", "formal"}:
        raise ValueError("mode must be 'draft' or 'formal'")
    if dpi <= 0:
        raise ValueError("dpi must be positive")
    if mode == "formal" and dpi != 600:
        raise ValueError("formal single-column export requires dpi=600")
    normalized_formats = [fmt.lower().lstrip(".") for fmt in formats]
    if len(set(normalized_formats)) != len(normalized_formats):
        raise ValueError("formats must not contain duplicates")
    if any(fmt not in {"pdf", "svg", "png"} for fmt in normalized_formats):
        raise ValueError("formats may contain only pdf, svg, and png")
    profile_data = dict(profile or _read_profile(profile_path))
    profile_grid = profile_data.get("grid", {})
    profile_grid_mode = profile_data.get("grid_mode")
    if profile_grid_mode is None and isinstance(profile_grid, Mapping):
        profile_grid_mode = profile_grid.get("mode")
    selected_grid_mode = grid_mode if grid_mode is not None else profile_grid_mode
    resolution = resolve_ieee_serif_font()
    repair = repair_single_column_figure(
        fig,
        fig.axes,
        locked_limits=locked_limits,
        panel_labels=panel_labels,
        font_resolution=resolution,
        grid_mode=selected_grid_mode,
    )
    report = preflight_single_column_figure(
        fig,
        fig.axes,
        mode=mode,
        profile=profile_data,
        font_resolution=resolution,
        locked_limits=locked_limits,
        grid_mode=selected_grid_mode,
        raise_on_error=False,
    )
    if mode == "formal" and report["errors"]:
        raise FigurePreflightError(report)
    destination = Path(output_dir) / ("drafts" if mode == "draft" else "")
    destination.mkdir(parents=True, exist_ok=True)
    saved: list[Path] = []
    for suffix in normalized_formats:
        path = destination / f"{stem}.{suffix}"
        with mpl.rc_context({"savefig.bbox": None, "savefig.pad_inches": 0.0}):
            fig.savefig(path, dpi=dpi, bbox_inches=None, pad_inches=0.0)
        saved.append(path)
    export_geometry: list[dict[str, Any]] = []
    export_errors: list[str] = []
    for path in saved:
        try:
            geometry = _inspect_export_geometry(
                path,
                expected_width_in=float(fig.get_figwidth()),
                expected_height_in=float(fig.get_figheight()),
                dpi=dpi,
                font_resolution=resolution,
            )
            export_geometry.append(geometry)
            if not geometry["exact_size"]:
                export_errors.append(f"{path.suffix} export changed the physical canvas size")
            if not geometry["font_validation"]["ok"]:
                export_errors.append(f"{path.suffix} export contains an unapproved or unverifiable vector font")
        except (KeyError, OSError, ET.ParseError, ValueError) as exc:
            export_errors.append(str(exc))
    manifest = {
        "schema_version": 3,
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "mode": mode,
        "formal": mode == "formal",
        "runtime": _runtime_metadata_from_environment(),
        "formal_style_source": "ieee_plot_style.py",
        "output_files": [str(path) for path in saved],
        "font": resolution.to_dict(),
        "repair": repair,
        "preflight": report,
        "palette_confirmation": profile_data.get("figure_color_map", profile_data.get("color_map", {})),
        "visual_review_approval": profile_data.get("visual_review_approval", {}),
        "matplotlib_version": mpl.__version__,
        "figure_size_in": [float(value) for value in fig.get_size_inches()],
        "grid_modes": repair["grid_modes"],
        "export": {"formats": [path.suffix.lstrip(".") for path in saved], "dpi": dpi, "bbox_inches": None, "pad_inches": 0.0},
        "export_validation": {
            "ok": not export_errors,
            "errors": export_errors,
            "files": export_geometry,
            "source_agg_outer_ink_margin_pt": report["metrics"].get("outer_ink_margin_pt", {}),
        },
    }
    manifest_path = destination / f"{stem}.manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if mode == "formal" and export_errors:
        failed_report = dict(report)
        failed_report["errors"] = [*report["errors"], *export_errors]
        failed_report["ok"] = False
        raise FigurePreflightError(failed_report)
    return saved


__all__ = [
    "DEFAULT_CATEGORY_COLORS",
    "FIGURE_PRIORITY_COLORS",
    "FigurePreflightError",
    "FontResolution",
    "FontResolutionError",
    "IEEE_DOUBLE_COLUMN_IN",
    "IEEE_DEFAULT_GRID_MODE",
    "IEEE_GRID_MODES",
    "IEEE_SINGLE_COLUMN_IN",
    "IEEE_STACKED_CONTENT_GAP_PT",
    "IEEE_STACKED_CONTENT_GAP_TOLERANCE_PT",
    "PALETTE_LIBRARY",
    "TOL_BRIGHT",
    "TOL_HIGH_CONTRAST",
    "TOL_MUTED",
    "TOL_NIGHTFALL",
    "add_panel_labels",
    "align_y_tick_labels",
    "apply_axes_box",
    "apply_axis_cleanup",
    "apply_compact_axis_spacing",
    "apply_compact_grid",
    "apply_compact_single_column_axes",
    "apply_ieee_grid",
    "apply_single_column_axes",
    "compute_panel_size",
    "compact_stacked_panel_gaps",
    "export_ieee_single_column",
    "fit_outer_content_margins",
    "fit_rendered_ink_margins",
    "freeze_figure_color_map",
    "ieee_figure_size",
    "new_ieee_figure",
    "measure_stacked_panel_gaps",
    "place_panel_labels_below",
    "place_reference_line_label",
    "place_ylabels_clear_of_ticks",
    "preflight_single_column_figure",
    "prepare_compact_ylabel",
    "propose_figure_color_map",
    "repair_single_column_figure",
    "resolve_ieee_serif_font",
    "resolve_ieee_width",
    "save_exact_size_figure",
    "save_ieee_figure",
    "use_ieee_single_column_style",
    "use_ieee_style",
]
