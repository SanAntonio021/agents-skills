"""Legacy GLOBECOM/SCIS regression helper; do not use for new figures.

New IEEE single-column data plots use ``scripts/ieee_plot_style.py`` and
``assets/ieee_single_column_data_plot.py``.  This file retains the historical
CH1/CH2 mapping only so existing figures can be audited reproducibly.
"""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

import matplotlib as mpl
from matplotlib.transforms import blended_transform_factory


IEEE_SINGLE_COLUMN_IN = 3.5
DEFAULT_AXES_BOX = (0.115, 0.985, 0.120, 0.960)
CHANNEL_COLORS = {
    "channel_1": "#009E73",
    "channel_2": "#CC79A7",
    "reference": "#000000",
    "threshold": "#000000",
    "batch_separator": "#D0D0D0",
}
GRID_STYLE = {
    "major_color": "#B8B8B8",
    "minor_color": "#D6D6D6",
    "major_width": 0.35,
    "minor_width": 0.35,
    "major_alpha": 0.52,
    "minor_alpha": 0.40,
}


def use_compact_single_column_style(
    *, base_font_size: float = 8.0, marker_size: float = 3.8
) -> None:
    """Apply the common font, frame, and exact-export defaults."""

    mpl.rcParams.update(
        {
            "font.family": "serif",
            "font.serif": ["Times New Roman", "Nimbus Roman", "DejaVu Serif"],
            "font.size": base_font_size,
            "axes.labelsize": base_font_size,
            "axes.titlesize": base_font_size,
            "xtick.labelsize": base_font_size - 1.0,
            "ytick.labelsize": base_font_size - 1.0,
            "legend.fontsize": base_font_size - 1.0,
            "axes.linewidth": 0.7,
            "lines.linewidth": 1.1,
            "lines.markersize": marker_size,
            "xtick.major.width": 0.7,
            "ytick.major.width": 0.7,
            "xtick.minor.width": 0.6,
            "ytick.minor.width": 0.6,
            "legend.frameon": False,
            "figure.dpi": 150,
            "savefig.dpi": 600,
            "savefig.bbox": None,
            "savefig.pad_inches": 0.0,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
            "svg.fonttype": "none",
        }
    )


def apply_compact_single_column_layout(
    fig, *, axes_box: tuple[float, float, float, float] = DEFAULT_AXES_BOX
) -> None:
    """Set the compact visible boundary without using a tight bounding box."""

    left, right, bottom, top = axes_box
    fig.subplots_adjust(left=left, right=right, bottom=bottom, top=top)


def apply_compact_single_column_axes(ax) -> None:
    """Apply four black spines and inward major/minor ticks on all sides."""

    for spine in ax.spines.values():
        spine.set_color("black")
        spine.set_linewidth(0.7)
    ax.tick_params(
        axis="x", which="major", bottom=True, top=True, direction="in", width=0.7, length=3.0, pad=1.5
    )
    ax.tick_params(
        axis="y", which="major", left=True, right=True, direction="in", width=0.7, length=3.0, pad=0.6
    )
    ax.tick_params(
        axis="x", which="minor", bottom=True, top=True, direction="in", width=0.6, length=2.2
    )
    ax.tick_params(
        axis="y", which="minor", left=True, right=True, direction="in", width=0.6, length=2.2
    )


def apply_compact_grid(ax) -> None:
    """Apply equal-width major/minor grids that stay behind the data."""

    ax.set_axisbelow(True)
    ax.grid(
        True,
        which="major",
        color=GRID_STYLE["major_color"],
        linewidth=GRID_STYLE["major_width"],
        linestyle=(0, (5.0, 3.0)),
        alpha=GRID_STYLE["major_alpha"],
    )
    ax.grid(
        True,
        which="minor",
        color=GRID_STYLE["minor_color"],
        linewidth=GRID_STYLE["minor_width"],
        linestyle=":",
        alpha=GRID_STYLE["minor_alpha"],
    )


def prepare_compact_ylabel(ax, *, x: float = -0.075) -> None:
    """Set an initial label position before display-coordinate adjustment."""

    ax.yaxis.labelpad = 0.0
    ax.yaxis.set_label_coords(x, 0.5)


def align_y_tick_labels(axes, *, pad_points: float = 1.5) -> None:
    """Right-align visible y-tick labels a fixed distance left of the spine."""

    axes = tuple(axes)
    if not axes:
        return
    fig = axes[0].figure
    fig.canvas.draw()
    target_right = min(ax.bbox.x0 for ax in axes) - pad_points * fig.dpi / 72.0
    for ax in axes:
        anchor = (target_right - ax.bbox.x0) / ax.bbox.width
        transform = blended_transform_factory(ax.transAxes, ax.transData)
        for label in ax.get_yticklabels():
            if label.get_visible() and label.get_text():
                label.set_transform(transform)
                label.set_x(anchor)
                label.set_horizontalalignment("right")
    fig.canvas.draw()


def place_ylabels_clear_of_ticks(axes, *, pad_points: float = 1.2) -> None:
    """Place y-axis titles directly left of the widest visible tick-label block."""

    axes = tuple(axes)
    if not axes:
        return
    fig = axes[0].figure
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
        x, _ = label.get_position()
        label.set_x(x + (target_right - bbox.x1) / ax.bbox.width)
        label.set_horizontalalignment("center")
    fig.canvas.draw()


def fit_outer_label_margins(
    fig, ax, *, target_points: float = 3.0
) -> tuple[float, float, float, float]:
    """Fit a single panel so its left and bottom label margins match.

    Call this after the first y-tick/y-label alignment pass, then repeat
    ``align_y_tick_labels()`` and ``place_ylabels_clear_of_ticks()``. The
    returned axes box belongs in the project's plot profile.
    """

    if target_points < 0:
        raise ValueError("target_points must be non-negative")
    if not ax.yaxis.label.get_text() or not ax.xaxis.label.get_text():
        raise ValueError("both axis labels must be set before fitting margins")
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    target_pixels = target_points * fig.dpi / 72.0
    ylabel_left = ax.yaxis.label.get_window_extent(renderer).x0
    xlabel_bottom = ax.xaxis.label.get_window_extent(renderer).y0
    axes_box = ax.get_position()
    left = axes_box.x0 + (target_pixels - ylabel_left) / fig.bbox.width
    bottom = axes_box.y0 + (target_pixels - xlabel_bottom) / fig.bbox.height
    if not 0.0 < left < axes_box.x1 or not 0.0 < bottom < axes_box.y1:
        raise ValueError("target margin would place the axes outside the canvas")
    fig.subplots_adjust(left=left, right=axes_box.x1, bottom=bottom, top=axes_box.y1)
    return left, axes_box.x1, bottom, axes_box.y1


def save_exact_size_figure(
    fig,
    stem: str,
    output_dir: str | Path = ".",
    *,
    formats: Sequence[str] = ("pdf", "svg", "png"),
    dpi: int = 600,
) -> list[Path]:
    """Export exact physical dimensions with no automatic outer padding."""

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    saved = []
    for fmt in formats:
        path = output_path / f"{stem}.{fmt.lower().lstrip('.')}"
        with mpl.rc_context({"savefig.bbox": None, "savefig.pad_inches": 0.0}):
            fig.savefig(path, dpi=dpi, bbox_inches=None, pad_inches=0.0)
        saved.append(path)
    return saved
