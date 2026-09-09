import json
import tempfile
from pathlib import Path

import pytest

from extract_paper_images import extract_figures

PLASMONIC_PDF = Path(
    r"D:\BaiduSyncdisk\Program\100Gbps1kmIQ\refs"
    r"\2026_Nat-Commun_Plasmonic-modulator-kilometer-sub-THz.pdf"
)


@pytest.fixture(scope="module")
def plasmonic_manifest():
    if not PLASMONIC_PDF.exists():
        pytest.skip("Plasmonic 2026 PDF not available")
    with tempfile.TemporaryDirectory() as tmpdir:
        extract_figures(
            pdf_path=PLASMONIC_PDF,
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


def test_long_caption_figure_is_not_filtered(plasmonic_manifest):
    fig = by_id(plasmonic_manifest, "Fig. 3")
    assert fig["page"] == 7
    assert fig["caption_bbox"][3] - fig["caption_bbox"][1] > 120
    assert len(fig["caption"]) > 1200
    assert fig["confidence"] == "high"


def test_long_caption_crop_stays_above_caption(plasmonic_manifest):
    fig = by_id(plasmonic_manifest, "Fig. 3")
    assert fig["bbox"][3] <= fig["caption_bbox"][1]
    assert fig["width"] > 1000
    assert fig["height"] > 700
    assert fig["file"].startswith("figures/fig_3")


def test_long_caption_sequence_audit_is_clear(plasmonic_manifest):
    fig_audits = [
        item
        for item in plasmonic_manifest["sequence_audit"]
        if item["group"] == "Fig."
    ]
    assert not fig_audits
