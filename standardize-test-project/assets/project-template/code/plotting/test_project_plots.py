"""Shared 300 dpi PNG plots for experimental test projects."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


COLORS = ("#0072B2", "#D55E00", "#009E73", "#CC79A7")
MARKERS = ("o", "s", "^", "D")
FONT_FAMILY = ("Microsoft YaHei", "Noto Sans CJK SC", "SimHei", "DejaVu Sans")


def apply_style() -> None:
    plt.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": list(FONT_FAMILY),
            "font.size": 10,
            "axes.labelsize": 11,
            "axes.titlesize": 12,
            "legend.fontsize": 9,
            "xtick.labelsize": 10,
            "ytick.labelsize": 10,
            "axes.linewidth": 1.0,
            "lines.linewidth": 1.5,
            "axes.unicode_minus": False,
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "savefig.facecolor": "white",
        }
    )


def _axis_label(name: str, unit: str) -> str:
    return f"{name} ({unit})" if unit and unit != "-" else name


def _finish(fig: plt.Figure, output: str | Path) -> Path:
    output = Path(output)
    if output.suffix.lower() != ".png":
        raise ValueError("automatic plots must use .png")
    if output.exists():
        raise FileExistsError(f"refusing to overwrite plot: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return output


def plot_constellation(
    output: str | Path,
    received: Sequence[Sequence[complex] | np.ndarray],
    ideal: Sequence[complex] | np.ndarray,
    *,
    metrics: Sequence[Mapping[str, Any]] | None = None,
    channel_names: Sequence[str] | None = None,
    title: str = "接收星座图",
) -> dict[str, Any]:
    apply_style()
    channels = [np.asarray(values, dtype=complex).reshape(-1) for values in received]
    channels = [values[np.isfinite(values.real) & np.isfinite(values.imag)] for values in channels]
    ideal_values = np.asarray(ideal, dtype=complex).reshape(-1)
    ideal_values = ideal_values[
        np.isfinite(ideal_values.real) & np.isfinite(ideal_values.imag)
    ]
    if not channels or ideal_values.size == 0:
        raise ValueError("received channels and ideal constellation points are required")
    names = list(channel_names or [f"数据流 {index + 1}" for index in range(len(channels))])
    if len(names) != len(channels):
        raise ValueError("channel_names must match received channels")
    metric_rows = list(metrics or [{} for _ in channels])
    if len(metric_rows) != len(channels):
        raise ValueError("metrics must match received channels")

    ideal_radius = float(np.max(np.maximum(np.abs(ideal_values.real), np.abs(ideal_values.imag))))
    limit = ideal_radius * 1.25 if ideal_radius > 0 else 1.25
    width_mm = 180 if len(channels) > 1 else 160
    height_mm = 85 if len(channels) > 1 else 100
    fig, axes = plt.subplots(
        1,
        len(channels),
        figsize=(width_mm / 25.4, height_mm / 25.4),
        squeeze=False,
    )
    outside_counts = []
    for index, (axis, values, name, metric) in enumerate(
        zip(axes[0], channels, names, metric_rows)
    ):
        axis.scatter(
            values.real,
            values.imag,
            s=6,
            c=COLORS[index % len(COLORS)],
            alpha=1.0,
            linewidths=0,
            label="接收符号",
            rasterized=True,
        )
        axis.scatter(
            ideal_values.real,
            ideal_values.imag,
            s=44,
            facecolors="none",
            edgecolors="black",
            marker="s",
            linewidths=1.2,
            label="理想星座点",
        )
        outside = int(
            np.count_nonzero(
                (np.abs(values.real) > limit) | (np.abs(values.imag) > limit)
            )
        )
        outside_counts.append(outside)
        lines = []
        for keys, label, formatter in (
            (("BER",), "BER", lambda value: f"{value:.3g}"),
            (("EVM", "EVMPercent"), "EVM", lambda value: f"{value:.2f}%"),
            (("MER", "MERdB"), "MER", lambda value: f"{value:.2f} dB"),
        ):
            value = next(
                (metric[key] for key in keys if key in metric and metric[key] is not None),
                None,
            )
            if value is not None and np.isfinite(float(value)):
                lines.append(f"{label}={formatter(float(value))}")
        lines.append(f"N={values.size}")
        if outside:
            lines.append(f"超出显示范围={outside}")
        axis.text(
            0.03,
            0.97,
            "\n".join(lines),
            transform=axis.transAxes,
            va="top",
            ha="left",
            fontsize=9,
        )
        axis.set_title(name)
        axis.set_xlabel("同相分量")
        axis.set_ylabel("正交分量")
        axis.set_xlim(-limit, limit)
        axis.set_ylim(-limit, limit)
        axis.set_aspect("equal", adjustable="box")
        axis.grid(True, which="major", color="#D9D9D9", linewidth=0.7)
        axis.legend(loc="best")
    fig.suptitle(title)
    fig.tight_layout()
    _finish(fig, output)
    return {
        "channel_count": len(channels),
        "valid_symbol_count": [int(values.size) for values in channels],
        "outside_count": outside_counts,
        "axis_limit": limit,
        "resolution_dpi": 300,
    }


def plot_spectrum(
    output: str | Path,
    frequency: Sequence[float] | np.ndarray,
    spectra: Sequence[float] | np.ndarray,
    *,
    trace_names: Sequence[str] | None = None,
    title: str = "频谱",
    x_name: str = "横轴变量",
    x_unit: str = "-",
    y_name: str = "纵轴变量",
    y_unit: str = "-",
    x_limits: tuple[float, float] | None = None,
    y_limits: tuple[float, float] | None = None,
) -> dict[str, Any]:
    apply_style()
    x = np.asarray(frequency, dtype=float).reshape(-1)
    y = np.asarray(spectra, dtype=float)
    if y.ndim == 1:
        y = y.reshape(-1, 1)
    if y.ndim != 2 or y.shape[0] != x.size:
        raise ValueError("spectra must have one row per frequency point")
    names = list(trace_names or [f"迹线 {index + 1}" for index in range(y.shape[1])])
    if len(names) != y.shape[1]:
        raise ValueError("trace_names must match spectrum columns")
    fig, axis = plt.subplots(figsize=(160 / 25.4, 100 / 25.4))
    counts = []
    for index in range(y.shape[1]):
        valid = np.isfinite(x) & np.isfinite(y[:, index])
        counts.append(int(np.count_nonzero(valid)))
        axis.plot(
            x[valid],
            y[valid, index],
            color=COLORS[index % len(COLORS)],
            linestyle=("-", "--", "-.", ":")[index % 4],
            label=names[index],
        )
    axis.set_title(title)
    axis.set_xlabel(_axis_label(x_name, x_unit))
    axis.set_ylabel(_axis_label(y_name, y_unit))
    if x_limits:
        axis.set_xlim(*x_limits)
    if y_limits:
        axis.set_ylim(*y_limits)
    axis.grid(True, which="major", color="#D9D9D9", linewidth=0.7)
    axis.legend(loc="best")
    fig.tight_layout()
    _finish(fig, output)
    return {"trace_count": y.shape[1], "valid_point_count": counts, "resolution_dpi": 300}


def plot_scan_summary(
    output: str | Path,
    scan_values: Sequence[float] | np.ndarray,
    metrics: Sequence[Mapping[str, Any]],
    *,
    success_mask: Sequence[bool] | np.ndarray,
    planned_count: int,
    title: str,
    x_name: str,
    x_unit: str,
) -> dict[str, Any]:
    apply_style()
    x = np.asarray(scan_values, dtype=float).reshape(-1)
    success = np.asarray(success_mask, dtype=bool).reshape(-1)
    if x.size != success.size or not metrics:
        raise ValueError("scan values, success mask, and metrics are required")
    unique_x = np.unique(x[np.isfinite(x)])
    fig, axes = plt.subplots(
        len(metrics),
        1,
        figsize=(180 / 25.4, max(70, 50 * len(metrics)) / 25.4),
        sharex=True,
        squeeze=False,
    )
    results = []
    for index, (axis, metric) in enumerate(zip(axes[:, 0], metrics)):
        values = np.asarray(metric["values"], dtype=float).reshape(-1)
        if values.size != x.size:
            raise ValueError("each metric must have one value per scan observation")
        stats_valid = success & np.isfinite(x) & np.isfinite(values)
        display_values = values.copy()
        y_scale = str(metric.get("y_scale", "linear"))
        if y_scale not in {"linear", "log"}:
            raise ValueError("y_scale must be linear or log")
        if y_scale == "log":
            stats_valid &= values >= 0
        zero_mask = stats_valid & (values == 0) & (y_scale == "log")
        if np.any(zero_mask):
            bit_counts = np.asarray(
                metric.get("bit_counts", np.full(x.size, np.nan)), dtype=float
            ).reshape(-1)
            if bit_counts.size == 1:
                bit_counts = np.full(x.size, bit_counts.item())
            if bit_counts.size != x.size or np.any(
                ~np.isfinite(bit_counts[zero_mask]) | (bit_counts[zero_mask] <= 0)
            ):
                raise ValueError("log-scale zero values require positive bit_counts")
            display_values[zero_mask] = 1.0 / bit_counts[zero_mask]
        valid = stats_valid & np.isfinite(display_values)
        if y_scale == "log":
            valid &= display_values > 0
            axis.set_yscale("log")

        color = COLORS[index % len(COLORS)]
        axis.scatter(
            x[valid & ~zero_mask],
            display_values[valid & ~zero_mask],
            s=22,
            color=color,
            marker=MARKERS[index % len(MARKERS)],
            label="有效原始观测",
            zorder=3,
        )
        if np.any(zero_mask):
            axis.scatter(
                x[zero_mask],
                display_values[zero_mask],
                s=34,
                facecolors="none",
                edgecolors=color,
                marker="v",
                label="0 BER（显示位置为 1/N）",
                zorder=4,
            )
        means = np.full(unique_x.shape, np.nan)
        deviations = np.full(unique_x.shape, np.nan)
        counts = np.zeros(unique_x.shape, dtype=int)
        for group_index, value in enumerate(unique_x):
            group = stats_valid & np.isclose(x, value, rtol=0, atol=1e-12)
            group_values = values[group]
            counts[group_index] = group_values.size
            if group_values.size:
                means[group_index] = float(np.mean(group_values))
            if group_values.size >= 2:
                deviations[group_index] = float(np.std(group_values, ddof=1))
        plot_means = means.copy()
        if y_scale == "log":
            plot_means[plot_means <= 0] = np.nan
        axis.plot(unique_x, plot_means, color=color, marker="o", label="均值", zorder=4)
        deviation_mask = np.isfinite(deviations) & np.isfinite(plot_means)
        if np.any(deviation_mask):
            y_error: np.ndarray | Sequence[np.ndarray] = deviations[deviation_mask]
            if y_scale == "log":
                lower = np.minimum(
                    deviations[deviation_mask],
                    plot_means[deviation_mask] * (1 - 1e-9),
                )
                y_error = np.vstack((lower, deviations[deviation_mask]))
            axis.errorbar(
                unique_x[deviation_mask],
                plot_means[deviation_mask],
                yerr=y_error,
                fmt="none",
                ecolor=color,
                elinewidth=1.2,
                capsize=3,
                label="±1 样本标准差",
                zorder=2,
            )
        axis.set_ylabel(_axis_label(str(metric["name"]), str(metric.get("unit", "-"))))
        axis.grid(True, which="major", color="#D9D9D9", linewidth=0.7)
        axis.legend(loc="best")
        results.append(
            {
                "name": str(metric["name"]),
                "unit": str(metric.get("unit", "-")),
                "x": unique_x.tolist(),
                "mean": means.tolist(),
                "sample_std": deviations.tolist(),
                "valid_count": counts.tolist(),
                "y_scale": y_scale,
                "zero_count": int(np.count_nonzero(zero_mask)),
            }
        )
    axes[-1, 0].set_xlabel(_axis_label(x_name, x_unit))
    successful_count = int(np.count_nonzero(success))
    fig.suptitle(title)
    fig.text(
        0.98,
        0.98,
        f"成功采集：{successful_count}/{int(planned_count)}",
        ha="right",
        va="top",
        fontsize=9,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    _finish(fig, output)
    return {
        "successful_count": successful_count,
        "planned_count": int(planned_count),
        "metrics": results,
        "resolution_dpi": 300,
    }


def plot_plan_overview(
    output: str | Path,
    planned_values: Sequence[float] | np.ndarray,
    *,
    title: str = "dry-run 计划检查",
    x_name: str = "计划变量",
    x_unit: str = "-",
    stages: Sequence[str] = ("计划检查", "路径检查", "保存检查"),
    planned_observations: int | None = None,
) -> dict[str, Any]:
    """Plot planned points only; never represent them as measurements."""
    apply_style()
    values = np.asarray(planned_values, dtype=float).reshape(-1)
    values = values[np.isfinite(values)]
    if values.size == 0:
        raise ValueError("at least one finite planned value is required")
    planned_count = int(
        planned_observations if planned_observations is not None else values.size
    )
    stage_text = "阶段：" + "、".join(str(stage) for stage in stages)
    fig, axis = plt.subplots(figsize=(160 / 25.4, 100 / 25.4))
    axis.scatter(
        values,
        np.ones(values.size),
        s=30,
        color=COLORS[0],
        marker="o",
        label="计划点",
        zorder=3,
    )
    axis.set_xlabel(_axis_label(x_name, x_unit))
    axis.set_yticks([])
    axis.set_ylim(0.7, 1.3)
    axis.grid(True, axis="x", which="major", color="#D9D9D9", linewidth=0.7)
    axis.set_title(title)
    axis.legend(loc="best")
    fig.text(
        0.98,
        0.98,
        f"计划观测数：{planned_count}",
        ha="right",
        va="top",
        fontsize=9,
    )
    fig.text(0.02, 0.02, stage_text, ha="left", va="bottom", fontsize=9)
    fig.tight_layout(rect=(0, 0.07, 1, 0.94))
    _finish(fig, output)
    return {
        "planned_point_count": int(values.size),
        "planned_observations": planned_count,
        "stages": list(stages),
        "resolution_dpi": 300,
    }


__all__ = [
    "apply_style",
    "plot_constellation",
    "plot_plan_overview",
    "plot_scan_summary",
    "plot_spectrum",
]
