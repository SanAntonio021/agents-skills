import json
import tempfile
from pathlib import Path

import pytest

from extract_paper_images import extract_figures

GRAPHENE_PDF = Path(
    r"D:\BaiduSyncdisk\Program\100Gbps1kmIQ\refs"
    r"\2026_Nat-Commun_High-speed-graphene-sub-THz-receivers.pdf"
)


@pytest.fixture(scope="module")
def graphene_manifest():
    if not GRAPHENE_PDF.exists():
        pytest.skip("Graphene 2026 PDF not available")
    with tempfile.TemporaryDirectory() as tmpdir:
        extract_figures(
            pdf_path=GRAPHENE_PDF,
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
        yield json.loads((Path(tmpdir) / "manifest.json").read_text(encoding="utf-8"))


def by_id(manifest, figure_id):
    return next(item for item in manifest["figures"] if item["figure_id"] == figure_id)


def test_rotated_table_is_not_thin_line(graphene_manifest):
    table = by_id(graphene_manifest, "Table 1")
    assert table["page_layout"] == "two-column"
    assert table["source_type"] in {"table-bbox-crop", "table-regions"}
    assert table["height"] > 1000
    assert table["width"] > 1000
    assert table["warning"] == ""
