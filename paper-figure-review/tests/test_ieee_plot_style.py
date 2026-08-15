from __future__ import annotations

import inspect
import json
import math
import shutil
import sys
from pathlib import Path

import matplotlib as mpl

mpl.use("Agg")

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pytest


SKILL_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_ROOT / "scripts"))

import ieee_plot_style as style
import audit_globecom_single_column as globecom_audit


@pytest.fixture(autouse=True)
def restore_rcparams():
    with mpl.rc_context():
        yield
    plt.close("all")


def _simple_figure(*, width: float = 3.5, height: float = 2.4, locked_edges: bool = False):
    resolution = style.use_ieee_single_column_style()
    fig, ax = plt.subplots(figsize=(width, height))
    ax.plot([0.0, 1.0, 2.0], [0.2, 0.9, 0.4], marker="o", label="series_a")
    ax.set_xlabel("Horizontal quantity (a.u.)")
    ax.set_ylabel("Vertical quantity (a.u.)")
    if locked_edges:
        ax.set_xlim(0.0, 2.0)
        ax.set_ylim(0.2, 0.9)
    return fig, ax, resolution


def _confirmed_profile(*, reasons=("final_size_preview",)):
    proposal = style.propose_figure_color_map(["series_a", "series_b"])
    proposal.update(
        {
            "palette_status": "confirmed",
            "confirmed_by": "user",
            "confirmed_at": "2026-08-14T12:00:00+08:00",
        }
    )
    return {
        "palette_status": "confirmed",
        "figure_color_map": proposal,
        "visual_review_approval": {
            "approved_by": "user",
            "approved_at": "2026-08-14T12:05:00+08:00",
            "reasons": list(reasons),
        },
    }


def _ink_margins_from_rgb(rgb: np.ndarray, dpi: float) -> dict[str, float]:
    difference = np.max(np.abs(rgb.astype(np.int16) - 255), axis=2)
    visible = difference > 5
    ys, xs = np.nonzero(visible)
    assert len(xs)
    height, width = visible.shape
    return {
        "left": xs.min() * 72.0 / dpi,
        "right": (width - 1 - xs.max()) * 72.0 / dpi,
        "bottom": (height - 1 - ys.max()) * 72.0 / dpi,
        "top": ys.min() * 72.0 / dpi,
    }


def _render_vector_at_600(path: Path) -> np.ndarray:
    fitz = pytest.importorskip("fitz")
    document = (
        fitz.open(stream=path.read_bytes(), filetype="svg")
        if path.suffix.lower() == ".svg"
        else fitz.open(path)
    )
    try:
        pixmap = document[0].get_pixmap(matrix=fitz.Matrix(600.0 / 72.0, 600.0 / 72.0), alpha=False)
        return np.frombuffer(pixmap.samples, dtype=np.uint8).reshape(pixmap.height, pixmap.width, pixmap.n)[:, :, :3]
    finally:
        document.close()


def test_legacy_api_signatures_are_preserved():
    use_signature = inspect.signature(style.use_ieee_style)
    assert use_signature.parameters["font_family"].default == "Arial"
    assert use_signature.parameters["base_font_size"].default == 8.0
    assert use_signature.parameters["line_width"].default == 1.1
    assert use_signature.parameters["marker_size"].default == 3.5
    assert inspect.signature(style.save_exact_size_figure).parameters["formats"].default == ("pdf", "png")


def test_font_resolution_is_complete_and_uses_correct_regular_face():
    resolution = style.resolve_ieee_serif_font()
    assert resolution.family in {"Times New Roman", "Liberation Serif"}
    assert set(resolution.files) == set(style.FONT_STYLE_FILES)
    assert resolution.regular_file == resolution.files["regular"]
    assert style._style_for_path(resolution.files["regular"]) == "regular"
    assert style._font_resolution_is_intact(resolution)


def test_mathtext_is_locked_to_the_approved_serif_without_fallback():
    resolution = style.use_ieee_single_column_style()
    assert style._mathtext_profile_is_approved(resolution.family)
    assert mpl.rcParams["mathtext.fontset"] == "custom"
    assert mpl.rcParams["mathtext.rm"] == resolution.family
    assert mpl.rcParams["mathtext.fallback"] is None


def test_bundled_liberation_fallback_has_fixed_hashes(monkeypatch):
    monkeypatch.setattr(style, "_family_paths", lambda _family: [])
    resolution = style.resolve_ieee_serif_font(asset_dir=SKILL_ROOT / "assets" / "fonts")
    manifest = json.loads((SKILL_ROOT / "assets" / "fonts" / "manifest.json").read_text(encoding="utf-8"))
    assert resolution.family == "Liberation Serif"
    assert resolution.source == "bundled"
    assert resolution.hashes == manifest["sha256"]
    assert style._font_resolution_is_intact(resolution)


def test_bundled_font_tampering_is_rejected(tmp_path, monkeypatch):
    font_dir = tmp_path / "fonts"
    shutil.copytree(SKILL_ROOT / "assets" / "fonts", font_dir)
    with (font_dir / "LiberationSerif-Regular.ttf").open("ab") as handle:
        handle.write(b"tamper")
    monkeypatch.setattr(style, "_family_paths", lambda _family: [])
    with pytest.raises(style.FontResolutionError, match="SHA-256 mismatch"):
        style.resolve_ieee_serif_font(asset_dir=font_dir)


def test_repair_applies_default_major_xy_grid_and_fixed_geometry():
    fig, ax, resolution = _simple_figure(width=4.1)
    repair = style.repair_single_column_figure(fig, [ax], font_resolution=resolution)
    report = style.preflight_single_column_figure(fig, [ax], font_resolution=resolution)
    assert report["ok"], report
    assert fig.get_figwidth() == pytest.approx(3.5)
    assert any("figure width" in action for action in repair["actions"])
    assert all(2.25 <= value <= 3.75 for value in report["metrics"]["outer_ink_margin_pt"].values())
    assert all(spine.get_visible() and spine.get_linewidth() == pytest.approx(0.7) for spine in ax.spines.values())
    assert all(text.get_fontsize() == pytest.approx(8.0) for text in fig.findobj(mpl.text.Text) if text.get_visible() and text.get_text())
    assert style._visible_axis_gridlines(ax.xaxis, "major")
    assert not style._visible_gridlines(ax, "minor")
    major = style._visible_axis_gridlines(ax.yaxis, "major")[0]
    assert major.get_color().upper() == "#B8B8B8"
    assert major.get_linewidth() == pytest.approx(0.35)
    assert major.get_alpha() == pytest.approx(0.52)
    assert major._unscaled_dash_pattern[1] == (5.0, 3.0)
    assert report["metrics"]["grid_modes"] == ["major_xy"]


def test_grid_modes_are_semantic_and_minor_grid_is_opt_in_only():
    continuous_fig, continuous_ax, resolution = _simple_figure()
    continuous_ax.set_yscale("log")
    continuous_ax.set_ylim(1.0e-2, 2.0)
    style.repair_single_column_figure(
        continuous_fig,
        [continuous_ax],
        font_resolution=resolution,
        grid_mode="major_xy",
    )
    continuous_report = style.preflight_single_column_figure(
        continuous_fig,
        [continuous_ax],
        font_resolution=resolution,
    )
    assert continuous_report["ok"], continuous_report
    assert style._visible_axis_gridlines(continuous_ax.xaxis, "major")
    assert style._visible_axis_gridlines(continuous_ax.yaxis, "major")
    assert not style._visible_gridlines(continuous_ax, "minor")
    assert all(
        not tick.tick1line.get_visible() and not tick.tick2line.get_visible()
        for tick in continuous_ax.yaxis.get_minor_ticks()
    )

    legacy_fig, legacy_ax, resolution = _simple_figure()
    style.repair_single_column_figure(
        legacy_fig,
        [legacy_ax],
        font_resolution=resolution,
        grid_mode="legacy_major_minor_xy",
    )
    legacy_report = style.preflight_single_column_figure(
        legacy_fig,
        [legacy_ax],
        font_resolution=resolution,
    )
    assert legacy_report["ok"], legacy_report
    assert style._visible_gridlines(legacy_ax, "minor")

    with pytest.raises(ValueError, match="grid_mode must be one of"):
        style.repair_single_column_figure(legacy_fig, [legacy_ax], grid_mode="auto")
    with pytest.raises(ValueError, match="grid_mode must be one of"):
        style.repair_single_column_figure(legacy_fig, [legacy_ax], grid_mode="major_y")


def test_stacked_grid_mode_sequence_must_match_axes():
    resolution = style.use_ieee_single_column_style()
    fig, axes = plt.subplots(2, 1, figsize=(3.5, 3.6))
    for ax in axes:
        ax.plot([0, 1], [0.0, 1.0])
    with pytest.raises(ValueError, match="must match the number of axes"):
        style.repair_single_column_figure(
            fig,
            axes,
            font_resolution=resolution,
            grid_mode=("major_xy",),
        )


def test_unlocked_marker_limits_are_repaired_and_locked_limits_block():
    fig, ax, resolution = _simple_figure(locked_edges=True)
    repair = style.repair_single_column_figure(fig, [ax], locked_limits=False, font_resolution=resolution)
    report = style.preflight_single_column_figure(fig, [ax], locked_limits=False, font_resolution=resolution)
    assert any("marker headroom expanded" in action for action in repair["actions"])
    assert not any("marker head" in error for error in report["errors"])
    assert ax.get_xlim()[0] < 0.0 and ax.get_xlim()[1] > 2.0

    locked_fig, locked_ax, resolution = _simple_figure(locked_edges=True)
    style.repair_single_column_figure(locked_fig, [locked_ax], locked_limits=True, font_resolution=resolution)
    locked_report = style.preflight_single_column_figure(
        locked_fig, [locked_ax], locked_limits=True, font_resolution=resolution
    )
    assert any("marker head crosses" in error for error in locked_report["errors"])


def test_text_collision_is_reported_after_safe_repairs():
    fig, ax, resolution = _simple_figure()
    ax.text(0.5, 0.5, "first", transform=ax.transAxes)
    ax.text(0.5, 0.5, "second", transform=ax.transAxes)
    style.repair_single_column_figure(fig, [ax], font_resolution=resolution)
    report = style.preflight_single_column_figure(fig, [ax], font_resolution=resolution)
    assert any("text boxes collide" in error for error in report["errors"])


def test_reference_line_labels_are_inside_the_frame_and_not_legend_items():
    fig, ax, resolution = _simple_figure()
    ax.axhline(0.5, color="#000000", linestyle="--", label="_nolegend_")
    label = style.place_reference_line_label(ax, 0.5, "Threshold 0.5")
    style.repair_single_column_figure(fig, [ax], font_resolution=resolution)
    report = style.preflight_single_column_figure(fig, [ax], font_resolution=resolution)
    assert report["ok"], report
    renderer = fig.canvas.get_renderer()
    bbox = label.get_window_extent(renderer)
    assert bbox.x1 <= ax.bbox.x1 + 0.5
    assert bbox.y0 >= ax.bbox.y0 - 0.5
    assert label.get_gid() == "ieee-reference-line-label"
    assert ax.get_legend() is None


def test_stacked_axes_labels_are_centered_and_display_aligned():
    resolution = style.use_ieee_single_column_style()
    fig, axes_array = plt.subplots(2, 1, figsize=(3.5, 3.6))
    fig.subplots_adjust(hspace=0.72)
    axes = tuple(np.atleast_1d(axes_array))
    for index, ax in enumerate(axes):
        ax.plot([1, 100, 200], [0.001 + index, 10.0 + index, 100.0 + index], marker="s")
        ax.set_xlabel("Acquisition index")
        ax.set_ylabel("Long metric" if index == 0 else "BER")
    style.repair_single_column_figure(fig, axes, panel_labels=("(a)", "(b)"), font_resolution=resolution)
    report = style.preflight_single_column_figure(fig, axes, font_resolution=resolution)
    assert report["ok"], report
    assert report["metrics"]["ytick_right_edge_spread_pt"] <= 0.25
    assert report["metrics"]["ylabel_right_edge_spread_pt"] <= 0.25
    assert len(report["metrics"]["stacked_panel_gaps"]) == 1
    gap = report["metrics"]["stacked_panel_gaps"][0]
    assert gap["content_clearance_pt"] == pytest.approx(style.IEEE_STACKED_CONTENT_GAP_PT, abs=0.25)
    renderer = fig.canvas.get_renderer()
    for ax in axes:
        panel_label = next(text for text in ax.texts if text.get_gid() == "ieee-single-column-panel-label")
        bbox = panel_label.get_window_extent(renderer)
        assert (bbox.x0 + bbox.x1) / 2.0 == pytest.approx((ax.bbox.x0 + ax.bbox.x1) / 2.0, abs=0.5)
        assert bbox.y1 <= ax.xaxis.label.get_window_extent(renderer).y0 - 2.0 * fig.dpi / 72.0 + 0.5


def test_preflight_rejects_unrepaired_oversized_stacked_gap():
    resolution = style.use_ieee_single_column_style()
    fig, axes_array = plt.subplots(2, 1, figsize=(3.5, 4.0))
    fig.subplots_adjust(hspace=0.85)
    axes = tuple(np.atleast_1d(axes_array))
    for ax in axes:
        ax.plot([0, 1], [0, 1])
        ax.set_xlabel("Acquisition index")
        style.apply_single_column_axes(ax)
        style.apply_ieee_grid(ax, grid_mode="major_xy")
    style.place_panel_labels_below(axes, ("(a)", "(b)"))
    report = style.preflight_single_column_figure(fig, axes, font_resolution=resolution)
    assert any("stacked panel visible-content clearance" in error for error in report["errors"])


def test_stacked_ylabels_stay_aligned_with_unequal_tick_widths():
    resolution = style.use_ieee_single_column_style()
    fig, axes_array = plt.subplots(2, 1, figsize=(3.5, 4.0))
    axes = tuple(np.atleast_1d(axes_array))
    top, bottom = axes
    x = np.array([0.0, 40.0, 80.0, 120.0, 160.0, 200.0])
    top.plot(x, [0.008, 0.012, 0.017, 0.019, 0.021, 0.023], marker="s")
    top.set_ylabel(r"Pre-FEC BER ($\times 10^{-3}$)")
    top.set_ylim(0.005, 0.025)
    top.set_yticks([0.005, 0.010, 0.015, 0.020, 0.025])
    top.yaxis.set_major_formatter(mticker.FuncFormatter(lambda value, _position: f"{value * 1.0e3:g}"))
    bottom.plot(x, [1.2, 1.8, 2.4, 2.8, 3.2, 3.7], marker="D")
    bottom.set_ylabel(r"Delta BER ($\times 10^{-3}$)")
    bottom.set_ylim(1.0, 4.0)
    bottom.set_yticks([1.0, 2.0, 3.0, 4.0])
    bottom.yaxis.set_major_formatter(mticker.FormatStrFormatter("%.0f"))
    for ax in axes:
        ax.set_xlabel("Acquisition index")
        ax.set_xlim(-5.0, 200.0)

    style.align_y_tick_labels(axes)
    style.place_ylabels_clear_of_ticks(axes)
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    ylabel_rights = [ax.yaxis.label.get_window_extent(renderer).x1 for ax in axes]
    direct_spread_pt = (max(ylabel_rights) - min(ylabel_rights)) * 72.0 / fig.dpi
    assert direct_spread_pt <= 0.25
    assert all(not ax.yaxis._autolabelpos for ax in axes)
    assert all(-1.0 < ax.yaxis.label.get_position()[0] < 0.0 for ax in axes)

    style.repair_single_column_figure(fig, axes, panel_labels=("(a)", "(b)"), font_resolution=resolution)
    report = style.preflight_single_column_figure(fig, axes, font_resolution=resolution)

    assert report["ok"], report
    assert report["metrics"]["ytick_right_edge_spread_pt"] <= 0.25
    assert report["metrics"]["ylabel_right_edge_spread_pt"] <= 0.25
    assert [label.get_text() for label in top.get_yticklabels()] == ["5", "10", "15", "20", "25"]
    assert [label.get_text() for label in bottom.get_yticklabels()] == ["1", "2", "3", "4"]


def test_palette_routing_and_freeze(tmp_path):
    proposal = style.propose_figure_color_map([f"category_{index}" for index in range(6)])
    assert proposal["palette"] == "tol_bright"
    assert len(set(proposal["roles"].values())) >= 6
    assert proposal["roles"]["threshold"] == "#000000"
    assert proposal["roles"]["delta"] == "#000000"
    assert style.propose_figure_color_map(["power"], data_kind="continuous")["colormap"] == "cividis"
    with pytest.raises(ValueError, match="finite center"):
        style.propose_figure_color_map(["delta_field"], data_kind="diverging")
    assert style.propose_figure_color_map(["delta_field"], data_kind="diverging", center=0.0)["center"] == 0.0

    profile_path = tmp_path / "plot_profile.json"
    frozen = style.freeze_figure_color_map(profile_path, proposal, confirmed_at="2026-08-14T12:00:00+08:00")
    assert frozen["figure_color_map"]["palette_status"] == "confirmed"
    changed = style.propose_figure_color_map(["different_a", "different_b"])
    with pytest.raises(PermissionError, match="frozen"):
        style.freeze_figure_color_map(profile_path, changed)


def test_draft_and_formal_export_gates_and_exact_geometry(tmp_path):
    fig, ax, _resolution = _simple_figure()
    draft_paths = style.export_ieee_single_column(fig, "sample", tmp_path, mode="draft")
    assert all(path.parent == tmp_path / "drafts" for path in draft_paths)
    draft_manifest = json.loads((tmp_path / "drafts" / "sample.manifest.json").read_text(encoding="utf-8"))
    assert draft_manifest["export_validation"]["ok"]
    assert draft_manifest["preflight"]["visual_review_required"] == ["final_size_preview"]

    formal_fig, _formal_ax, _resolution = _simple_figure()
    with pytest.raises(style.FigurePreflightError, match="user-confirmed"):
        style.export_ieee_single_column(formal_fig, "formal", tmp_path, mode="formal")
    assert not (tmp_path / "formal.pdf").exists()

    approved_fig, approved_ax, _resolution = _simple_figure()
    approved_ax.set_ylabel(r"BER ($\times 10^{-3}$)")
    approved_paths = style.export_ieee_single_column(
        approved_fig,
        "formal",
        tmp_path,
        mode="formal",
        profile=_confirmed_profile(),
    )
    assert {path.suffix for path in approved_paths} == {".pdf", ".svg", ".png"}
    manifest = json.loads((tmp_path / "formal.manifest.json").read_text(encoding="utf-8"))
    assert manifest["formal"]
    assert manifest["visual_review_approval"]["approved_at"]
    assert manifest["export_validation"]["ok"]
    for record in manifest["export_validation"]["files"]:
        assert record["exact_size"]
        assert record["physical_size_in"] == pytest.approx([3.5, 2.4], abs=1 / 600)
        assert record["font_validation"]["ok"]
        if record["font_validation"]["verifiable"]:
            assert not any("DejaVu" in name for name in json.dumps(record["font_validation"]))


def test_preflight_rejects_mathtext_font_fallback_drift():
    fig, ax, resolution = _simple_figure()
    style.repair_single_column_figure(fig, [ax], font_resolution=resolution)
    mpl.rcParams["mathtext.fallback"] = "cm"
    report = style.preflight_single_column_figure(fig, [ax], font_resolution=resolution)
    assert any("math text" in error for error in report["errors"])


def test_unvalidated_matplotlib_version_needs_specific_user_approval(monkeypatch):
    fig, ax, resolution = _simple_figure()
    style.repair_single_column_figure(fig, [ax], font_resolution=resolution)
    monkeypatch.setattr(style.mpl, "__version__", "4.1.0")
    draft = style.preflight_single_column_figure(fig, [ax], mode="draft", font_resolution=resolution)
    assert "unvalidated_matplotlib_version" in draft["visual_review_required"]
    formal = style.preflight_single_column_figure(
        fig,
        [ax],
        mode="formal",
        profile=_confirmed_profile(),
        font_resolution=resolution,
    )
    assert any("unvalidated_matplotlib_version" in error for error in formal["errors"])


def test_pdf_svg_png_rendered_ink_and_physical_size_at_600_dpi(tmp_path):
    fig, _ax, _resolution = _simple_figure()
    paths = style.export_ieee_single_column(fig, "render", tmp_path, mode="draft")
    for path in paths:
        if path.suffix == ".png":
            from PIL import Image

            rgb = np.asarray(Image.open(path).convert("RGB"))
        else:
            rgb = _render_vector_at_600(path)
        assert rgb.shape[1] == 2100
        assert rgb.shape[0] == 1440
        margins = _ink_margins_from_rgb(rgb, 600.0)
        assert all(2.0 <= value <= 4.25 for value in margins.values()), (path, margins)


def test_globecom_audit_passes_font_resolution_and_preserves_inputs(tmp_path, monkeypatch):
    figure_dir = tmp_path / "figures"
    figure_dir.mkdir()
    profile_path = figure_dir / "plot_profile.json"
    profile = {
        "export": {"png_dpi": 600},
        "figures": {
            figure_id: {"figsize_in": [3.5, 2.0]}
            for figure_id in globecom_audit.FIGURES
        },
    }
    profile_path.write_text(json.dumps(profile), encoding="utf-8")
    targets = [profile_path]
    for stem in globecom_audit.FIGURES.values():
        for suffix in ("pdf", "svg", "png"):
            path = figure_dir / f"{stem}.{suffix}"
            path.write_bytes(f"{stem}.{suffix}".encode("ascii"))
            targets.append(path)
    before = {path: path.read_bytes() for path in targets}
    sentinel = object()
    seen_resolutions = []

    monkeypatch.setattr(globecom_audit, "resolve_ieee_serif_font", lambda: sentinel)

    def fake_inspect(path, *, expected_width_in, expected_height_in, dpi, font_resolution):
        seen_resolutions.append(font_resolution)
        return {
            "path": str(path),
            "physical_size_in": [expected_width_in, expected_height_in],
            "exact_size": True,
            "font_validation": {"ok": True},
        }

    monkeypatch.setattr(globecom_audit, "_inspect_export_geometry", fake_inspect)
    report = globecom_audit.audit_globecom_exports(figure_dir, profile_path)

    assert report["ok"], report
    assert report["read_only_unchanged"]
    assert len(seen_resolutions) == 9
    assert all(resolution is sentinel for resolution in seen_resolutions)
    assert {path: path.read_bytes() for path in targets} == before


def test_globecom_audit_reports_failed_vector_font_validation(tmp_path, monkeypatch):
    figure_dir = tmp_path / "figures"
    figure_dir.mkdir()
    profile_path = figure_dir / "plot_profile.json"
    profile = {
        "export": {"png_dpi": 600},
        "figures": {
            figure_id: {"figsize_in": [3.5, 2.0]}
            for figure_id in globecom_audit.FIGURES
        },
    }
    profile_path.write_text(json.dumps(profile), encoding="utf-8")
    for stem in globecom_audit.FIGURES.values():
        for suffix in ("pdf", "svg", "png"):
            (figure_dir / f"{stem}.{suffix}").write_bytes(f"{stem}.{suffix}".encode("ascii"))

    monkeypatch.setattr(globecom_audit, "resolve_ieee_serif_font", lambda: object())

    def fake_inspect(path, *, expected_width_in, expected_height_in, dpi, font_resolution):
        is_svg = path.suffix == ".svg"
        return {
            "path": str(path),
            "physical_size_in": [expected_width_in, expected_height_in],
            "exact_size": True,
            "font_validation": {
                "ok": not is_svg,
                "unexpected_families": ["DejaVu Serif"] if is_svg else [],
            },
        }

    monkeypatch.setattr(globecom_audit, "_inspect_export_geometry", fake_inspect)
    report = globecom_audit.audit_globecom_exports(figure_dir, profile_path)

    assert not report["ok"]
    assert report["read_only_unchanged"]
    assert report["errors"] == [
        f"{stem}.svg failed font validation: DejaVu Serif"
        for stem in globecom_audit.FIGURES.values()
    ]
