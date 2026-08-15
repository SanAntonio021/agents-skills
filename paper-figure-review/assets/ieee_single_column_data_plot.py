"""Copyable starting point for an IEEE single-column Matplotlib data plot.

Keep ``ieee_plot_style.py`` importable beside the project plot script.  This
template intentionally contains no duplicated style constants and no fixed
channel colors.
"""

from __future__ import annotations

from pathlib import Path
from typing import Mapping, Sequence

import matplotlib.pyplot as plt

from ieee_plot_style import (
    IEEE_DEFAULT_GRID_MODE,
    IEEE_SINGLE_COLUMN_IN,
    export_ieee_single_column,
    place_reference_line_label,
    propose_figure_color_map,
    use_ieee_single_column_style,
)


def build_single_panel(
    x: Sequence[float],
    series: Mapping[str, Sequence[float]],
    *,
    xlabel: str,
    ylabel: str,
    figure_height_in: float = 2.45,
    color_map: Mapping[str, object] | None = None,
):
    """Build one panel and return the figure, axes, and palette proposal."""

    use_ieee_single_column_style()
    proposal = dict(color_map or propose_figure_color_map(list(series)))
    role_colors = proposal["roles"]
    markers = proposal.get("markers", {})
    linestyles = proposal.get("linestyles", {})

    fig, ax = plt.subplots(figsize=(IEEE_SINGLE_COLUMN_IN, figure_height_in))
    for role, values in series.items():
        ax.plot(
            x,
            values,
            label=role,
            color=role_colors[role],
            marker=markers.get(role, "o"),
            linestyle=linestyles.get(role, "-"),
        )
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    if len(series) > 1:
        ax.legend(loc="best")
    return fig, ax, proposal


def add_reference_line(ax, value: float, label: str, *, linestyle="--", linewidth: float = 0.8):
    """Draw a black reference line and label it at the inside right end."""

    line = ax.axhline(
        value,
        color="#000000",
        linestyle=linestyle,
        linewidth=linewidth,
        label="_nolegend_",
    )
    place_reference_line_label(ax, value, label)
    return line


def export_figure(
    fig,
    stem: str,
    output_dir: str | Path,
    *,
    profile_path: str | Path,
    mode: str = "draft",
    grid_mode: str = IEEE_DEFAULT_GRID_MODE,
    panel_labels: Sequence[str] | None = None,
):
    """Export with complete major grids, or pass ``none`` to disable all grids."""

    return export_ieee_single_column(
        fig,
        stem,
        output_dir,
        mode=mode,
        profile_path=profile_path,
        formats=("pdf", "svg", "png"),
        dpi=600,
        grid_mode=grid_mode,
        panel_labels=panel_labels,
    )
