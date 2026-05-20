import json
import tempfile
from pathlib import Path

import pytest

from extract_paper_images import extract_figures

COL_2023_PDF = Path(
    r"D:\BaiduSyncdisk\Program\100Gbps1kmIQ\refs"
    r"\2023_COL_200Gbps-multicarrier-64QAM-300GHz-30m.pdf"
)


@pytest.fixture(scope="module")
def col_2023_manifest():
    if not COL_2023_PDF.exists():
        pytest.skip("COL 2023 PDF not available")
    with tempfile.TemporaryDirectory() as tmpdir:
        extract_figures(
            pdf_path=COL_2023_PDF,
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
            html_url="https://www.researching.cn/articles/OJ680ef0f2001f0419",
        )
        yield json.loads((Path(tmpdir) / "manifest.json").read_text(encoding="utf-8"))


def by_id(manifest, figure_id):
    return next(item for item in manifest["figures"] if item["figure_id"] == figure_id)


def test_table_1_stays_in_left_column(col_2023_manifest):
    table = by_id(col_2023_manifest, "Table 1")
    assert table["page_layout"] == "two-column"
    assert table["bbox"][2] < 315
    assert table["bbox"][3] < 315
    assert not table["split"]


def test_fig_1_excludes_caption_and_top_body(col_2023_manifest):
    fig = by_id(col_2023_manifest, "Fig. 1")
    assert fig["source_type"] == "official-figure"
    assert "researching.cn/richHtml/" in fig["source_url"]
    assert fig["height"] > 500


def test_table_2_detects_split_blocks(col_2023_manifest):
    table = by_id(col_2023_manifest, "Table 2")
    assert table["source_type"] == "table-regions"
    assert table["split"]
    assert len(table["files"]) == 2
    assert len(table["regions"]) == 2
    x0s = sorted(region["bbox"][0] for region in table["regions"])
    assert x0s[0] < 315
    assert x0s[1] > 315


def test_fig_2_is_present(col_2023_manifest):
    fig = by_id(col_2023_manifest, "Fig. 2")
    assert fig["file"].startswith("figures/fig_2")
    assert fig["source_type"] == "official-figure"


def test_fig_2_uses_official_researching_image(col_2023_manifest):
    fig = by_id(col_2023_manifest, "Fig. 2")
    assert "researching.cn/richHtml/" in fig["source_url"]
    assert fig["width"] > 900


def test_fig_4_uses_official_researching_image(col_2023_manifest):
    fig = by_id(col_2023_manifest, "Fig. 4")
    assert fig["source_type"] == "official-figure"
    assert "researching.cn/richHtml/" in fig["source_url"]
