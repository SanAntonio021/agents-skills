from pathlib import Path
import shutil
import sys

import pytest
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from visio_export import export_compact, measure_white_border, rasterize_page


def test_border_counts_all_nonwhite_pixels_after_alpha_compositing(tmp_path):
    path = tmp_path / "alpha.png"
    image = Image.new("RGBA", (20, 15), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rectangle((2, 3, 16, 10), fill=(255, 255, 255, 255))
    draw.point((2, 3), fill=(254, 254, 254, 255))
    draw.point((16, 10), fill=(0, 0, 255, 1))
    image.save(path)
    measured = measure_white_border(path)
    assert measured["content_bbox_px"] == [2, 3, 17, 11]
    assert measured["margins_px"] == [2, 3, 3, 4]


def test_empty_image_is_not_accepted_as_a_finished_export(tmp_path):
    path = tmp_path / "empty.png"
    Image.new("RGB", (12, 12), "white").save(path)
    with pytest.raises(ValueError, match="no visible content"):
        measure_white_border(path)


def test_pdf_rasterization_preserves_physical_size_and_white_background(tmp_path):
    import pymupdf
    source = tmp_path / "source.pdf"
    with pymupdf.open() as pdf:
        page = pdf.new_page(width=144, height=72)
        page.draw_rect(page.rect, color=None, fill=(1, 1, 1))
        page.draw_rect((18, 18, 126, 54), color=(0, 0, 0), width=1)
        pdf.save(source)

    class Document:
        def ExportAsFixedFormat(self, kind, path, *args):
            assert kind == 1
            shutil.copyfile(source, path)

    png = tmp_path / "render.png"
    rasterize_page(Document(), tmp_path / "page.pdf", png, 2, 1, 300)
    measured = measure_white_border(png)
    assert measured["size_px"] == [600, 300]
    assert measured["margins_px"] == [72, 72, 72, 72]
    with Image.open(png) as image:
        assert image.mode == "RGB"
        assert image.getpixel((599, 299)) == (255, 255, 255)
        assert image.info["dpi"][0] == pytest.approx(300, abs=0.01)
    with pytest.raises(RuntimeError, match="does not match"):
        rasterize_page(Document(), tmp_path / "page.pdf", png, 3, 1, 300)


@pytest.mark.parametrize("dpi,padding", [(300, 0), (300, 3), (71, 2), (1201, 2), (300.5, 2)])
def test_invalid_export_options_fail_before_moving_native_shapes(dpi, padding):
    with pytest.raises(ValueError):
        export_compact(None, None, {}, dpi=dpi, padding_px=padding)
