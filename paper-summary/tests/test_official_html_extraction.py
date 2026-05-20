import json
import tempfile
from pathlib import Path

from PIL import Image

from extract_paper_images import extract_figures, mdpi_static_candidates

PDF_PATH = Path(
    r"D:\BaiduSyncdisk\Program\100Gbps1kmIQ\refs"
    r"\2024_IRMMW-THz_Single-carrier-200Gbps-300GHz-200m.pdf"
)


def write_png(path: Path, size=(240, 120)):
    image = Image.new("RGB", size, "white")
    image.save(path)


def test_official_html_figure_overrides_pdf_crop():
    if not PDF_PATH.exists():
        return
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        image_path = root / "official_fig1.png"
        html_path = root / "article.html"
        write_png(image_path)
        html_path.write_text(
            f"""
            <html><body>
              <figure>
                <img src="{image_path.as_uri()}">
                <figcaption>Fig. 1. Official figure from publisher HTML.</figcaption>
              </figure>
            </body></html>
            """,
            encoding="utf-8",
        )
        extract_figures(
            pdf_path=PDF_PATH,
            out_dir=root / "out",
            mode="auto",
            min_bytes=10 * 1024,
            min_width=100,
            min_height=100,
            render_dpi=120,
            confidence_threshold=0.7,
            write_debug_pages=False,
            save_embedded=False,
            html_file=html_path,
            html_base_url=None,
        )
        manifest = json.loads((root / "out" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == 4
    fig1 = next(item for item in manifest["figures"] if item["figure_id"] == "Fig. 1")
    assert fig1["source_type"] == "official-figure"
    assert fig1["file"] == "figures/fig_1.png"
    duplicate = next(item for item in manifest["skipped"] if item.get("figure_id") == "Fig. 1")
    assert duplicate["is_duplicate"] is True
    assert duplicate["source_type"] != "official-figure"


def test_official_html_table_is_saved_as_markdown():
    if not PDF_PATH.exists():
        return
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        html_path = root / "article.html"
        html_path.write_text(
            """
            <html><body>
              <table>
                <caption>Table 1. Official table from publisher HTML.</caption>
                <tr><th>Rate</th><th>Distance</th></tr>
                <tr><td>200 Gbps</td><td>30 m</td></tr>
              </table>
            </body></html>
            """,
            encoding="utf-8",
        )
        extract_figures(
            pdf_path=PDF_PATH,
            out_dir=root / "out",
            mode="auto",
            min_bytes=10 * 1024,
            min_width=100,
            min_height=100,
            render_dpi=120,
            confidence_threshold=0.7,
            write_debug_pages=False,
            save_embedded=False,
            html_file=html_path,
            html_base_url=None,
        )
        manifest = json.loads((root / "out" / "manifest.json").read_text(encoding="utf-8"))
        table_path = root / "out" / "figures" / "table_1.md"
        table_text = table_path.read_text(encoding="utf-8")
    table = next(item for item in manifest["figures"] if item["figure_id"] == "Table 1")
    assert table["source_type"] == "official-html-table"
    assert table["structured_table"] == "figures/table_1.md"
    assert "| Rate | Distance |" in table_text


def test_mdpi_static_candidates_from_article_url():
    base, urls = mdpi_static_candidates("https://www.mdpi.com/2079-9292/15/9/1814")
    assert base == (
        "https://pub.mdpi-res.com/electronics/electronics-15-01814"
        "/article_deploy/html/images"
    )
    assert urls[0] == (
        "https://pub.mdpi-res.com/electronics/electronics-15-01814"
        "/article_deploy/html/images/electronics-15-01814-g001.png"
    )
