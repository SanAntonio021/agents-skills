import json
import tempfile
from pathlib import Path

import pytest

from extract_paper_images import extract_figures

IRMMW_PDF = Path(
    r"D:\BaiduSyncdisk\Program\100Gbps1kmIQ\refs"
    r"\2024_IRMMW-THz_Single-carrier-200Gbps-300GHz-200m.pdf"
)


@pytest.fixture
def irmmw_manifest():
    if not IRMMW_PDF.exists():
        pytest.skip("IRMMW 2024 PDF not available")
    with tempfile.TemporaryDirectory() as tmpdir:
        result = extract_figures(
            pdf_path=IRMMW_PDF,
            out_dir=Path(tmpdir),
            mode="auto",
            min_bytes=10 * 1024,
            min_width=100,
            min_height=100,
            render_dpi=240,
            confidence_threshold=0.7,
            write_debug_pages=False,
            save_embedded=False,
            html_file=None,
            html_base_url=None,
        )
        manifest_path = Path(tmpdir) / "manifest.json"
        yield json.loads(manifest_path.read_text(encoding="utf-8"))


def test_schema_version(irmmw_manifest):
    assert irmmw_manifest["schema_version"] == 2


def test_confidence_is_string(irmmw_manifest):
    for fig in irmmw_manifest["figures"]:
        assert fig["confidence"] in ("high", "medium", "low")


def test_confidence_score_is_number(irmmw_manifest):
    for fig in irmmw_manifest["figures"]:
        assert isinstance(fig["confidence_score"], (int, float))
        assert 0.0 <= fig["confidence_score"] <= 1.0


def test_figure_count(irmmw_manifest):
    assert len(irmmw_manifest["figures"]) == 4


def test_figure_ids_in_order(irmmw_manifest):
    ids = [f["figure_id"] for f in irmmw_manifest["figures"]]
    assert ids == ["Fig. 1", "Fig. 2", "Fig. 3", "Fig. 4"]


def test_filenames_no_zero_padding(irmmw_manifest):
    for fig in irmmw_manifest["figures"]:
        filename = fig["file"]
        assert "fig_0" not in filename, f"Zero-padded filename: {filename}"


def test_all_figures_in_figures_dir(irmmw_manifest):
    for fig in irmmw_manifest["figures"]:
        assert fig["file"].startswith("figures/")
