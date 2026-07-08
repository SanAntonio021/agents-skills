"""Reusable Matplotlib helpers for IEEE-style manuscript figures."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Sequence

import matplotlib as mpl
import matplotlib.pyplot as plt


IEEE_SINGLE_COLUMN_IN = 3.5
IEEE_DOUBLE_COLUMN_IN = 7.16

FIGURE_PRIORITY_COLORS = {
    "primary": "#0072B2",  # blue
    "secondary": "#D55E00",  # vermillion
    "tertiary": "#009E73",  # bluish green
    "quaternary": "#CC79A7",  # reddish purple
    "category_extra_1": "#56B4E9",  # sky blue
    "category_extra_2": "#E69F00",  # orange
    "reference": "#4C4C4C",  # dark gray
    "threshold": "#8A8A8A",  # medium gray
    "grid": "#D9D9D9",  # light gray
}

DEFAULT_CATEGORY_COLORS = [
    "#0072B2",  # blue
    "#D55E00",  # vermillion
    "#009E73",  # bluish green
    "#CC79A7",  # reddish purple
    "#56B4E9",  # sky blue
    "#E69F00",  # orange
]

OKABE_ITO = DEFAULT_CATEGORY_COLORS


def ieee_figure_size(width: str = "single", height_ratio: float = 0.72) -> tuple[float, float]:
    """Return figure size in inches for IEEE single or double column output."""

    if width not in {"single", "double"}:
        raise ValueError("width must be 'single' or 'double'")
    base_width = IEEE_SINGLE_COLUMN_IN if width == "single" else IEEE_DOUBLE_COLUMN_IN
    return base_width, base_width * height_ratio


def resolve_ieee_width(width: str | float = "single") -> float:
    """Resolve a named IEEE width or explicit width in inches."""

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
    """Compute one panel size from the final figure width and panel count.

    This is a layout calculator, not a fixed IEEE preset. Use it when separate
    panels are exported and later assembled in PowerPoint, Illustrator, or LaTeX.
    """

    if ncols < 1:
        raise ValueError("ncols must be at least 1")
    if total_gutter_in < 0:
        raise ValueError("total_gutter_in must be non-negative")
    if height_ratio <= 0:
        raise ValueError("height_ratio must be positive")

    figure_width = resolve_ieee_width(total_width)
    available_width = figure_width - total_gutter_in
    if available_width <= 0:
        raise ValueError("total_gutter_in leaves no positive panel width")
    panel_width = available_width / ncols
    return panel_width, panel_width * height_ratio


def use_ieee_style(
    font_family: str = "Arial",
    base_font_size: float = 8.0,
    line_width: float = 1.1,
    marker_size: float = 3.5,
) -> None:
    """Apply conservative IEEE-style defaults to Matplotlib."""

    mpl.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": [font_family, "Helvetica", "DejaVu Sans"],
            "font.size": base_font_size,
            "axes.labelsize": base_font_size,
            "axes.titlesize": base_font_size,
            "xtick.labelsize": base_font_size - 1,
            "ytick.labelsize": base_font_size - 1,
            "legend.fontsize": base_font_size - 1,
            "axes.linewidth": 0.6,
            "lines.linewidth": line_width,
            "lines.markersize": marker_size,
            "xtick.major.width": 0.6,
            "ytick.major.width": 0.6,
            "xtick.major.size": 3,
            "ytick.major.size": 3,
            "legend.frameon": False,
            "figure.dpi": 150,
            "savefig.dpi": 600,
            "savefig.bbox": "tight",
            "savefig.pad_inches": 0.02,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
            "svg.fonttype": "none",
            "axes.prop_cycle": mpl.cycler(color=DEFAULT_CATEGORY_COLORS),
        }
    )


def new_ieee_figure(
    width: str = "single",
    height_ratio: float = 0.72,
    nrows: int = 1,
    ncols: int = 1,
    **subplot_kwargs,
):
    """Create a Matplotlib figure sized for IEEE output."""

    use_ieee_style()
    figsize = ieee_figure_size(width=width, height_ratio=height_ratio)
    return plt.subplots(nrows=nrows, ncols=ncols, figsize=figsize, **subplot_kwargs)


def save_ieee_figure(
    fig,
    stem: str,
    output_dir: str | Path = ".",
    formats: Sequence[str] = ("pdf", "png"),
    dpi: int = 600,
) -> list[Path]:
    """Save a figure in one or more IEEE-friendly formats.

    This uses a tight bounding box, which is convenient for standalone figures
    but can change the final physical size. Use save_exact_size_figure() when
    the exported panel must keep the exact figsize for multi-panel assembly.
    """

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
    """Save a figure without automatic bounding-box resizing."""

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    saved: list[Path] = []
    for fmt in formats:
        suffix = fmt.lower().lstrip(".")
        path = out_dir / f"{stem}.{suffix}"
        fig.savefig(path, dpi=dpi, bbox_inches=None, pad_inches=0.0)
        saved.append(path)
    return saved


def apply_axes_box(
    fig,
    left: float,
    right: float,
    bottom: float,
    top: float,
) -> None:
    """Apply an explicit axes box recorded in a plot profile."""

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
    """Apply compact spacing for small IEEE data panels."""

    ax.xaxis.labelpad = xlabel_pad
    ax.yaxis.labelpad = ylabel_pad
    ax.tick_params(axis="x", direction=tick_direction, top=top_ticks, pad=xtick_pad)
    ax.tick_params(axis="y", direction=tick_direction, right=right_ticks, pad=ytick_pad)
    ax.tick_params(
        axis="x",
        which="minor",
        direction=tick_direction,
        top=top_ticks,
        length=minor_tick_length,
    )
    ax.tick_params(
        axis="y",
        which="minor",
        direction=tick_direction,
        right=right_ticks,
        length=minor_tick_length,
    )


def apply_ieee_grid(
    ax,
    major_color: str = "#B8B8B8",
    minor_color: str = "#D6D6D6",
    major_width: float = 0.35,
    minor_width: float = 0.30,
    major_alpha: float = 0.60,
    minor_alpha: float = 0.55,
) -> None:
    """Apply a restrained major/minor grid for small scientific plots."""

    ax.set_axisbelow(True)
    ax.grid(
        True,
        which="major",
        color=major_color,
        linewidth=major_width,
        linestyle="-",
        alpha=major_alpha,
    )
    ax.grid(
        True,
        which="minor",
        color=minor_color,
        linewidth=minor_width,
        linestyle=(0, (2.0, 2.2)),
        alpha=minor_alpha,
    )


def apply_axis_cleanup(ax, keep_grid: bool = False) -> None:
    """Remove common chart clutter while keeping IEEE-style axes readable."""

    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    if keep_grid:
        ax.grid(True, color=FIGURE_PRIORITY_COLORS["grid"], linewidth=0.4, alpha=0.7)
    else:
        ax.grid(False)


def add_panel_labels(axes: Iterable, labels: Sequence[str] | None = None) -> None:
    """Add IEEE-style panel labels such as (a), (b), (c)."""

    axes_list = list(axes)
    labels = labels or [f"({chr(97 + i)})" for i in range(len(axes_list))]
    for ax, label in zip(axes_list, labels):
        ax.text(
            -0.12,
            1.04,
            label,
            transform=ax.transAxes,
            ha="left",
            va="bottom",
            fontweight="bold",
        )
