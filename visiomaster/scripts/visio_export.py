"""Measure and calibrate a new Visio page without scaling its native objects."""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import xml.etree.ElementTree as ET


def measure_white_border(path):
    from PIL import Image, ImageChops

    with Image.open(path) as source:
        rgba = source.convert("RGBA")
    image = Image.new("RGBA", rgba.size, "white")
    image.alpha_composite(rgba)
    image = image.convert("RGB")
    bbox = ImageChops.difference(image, Image.new("RGB", image.size, "white")).getbbox()
    if bbox is None:
        raise ValueError("Cannot measure export padding: no visible content")
    left, top, right, bottom = bbox
    return {
        "size_px": list(image.size),
        "content_bbox_px": list(bbox),
        "margins_px": [left, top, image.width - right, image.height - bottom],
    }


def rasterize_page(document, pdf_path, png_path, width, height, dpi):
    """Use Visio's physical page, avoiding its PNG filter's aspect-ratio padding."""
    import pymupdf
    from PIL import Image

    # Print intent, all pages. render() creates exactly one foreground page.
    document.ExportAsFixedFormat(1, str(pdf_path), 1, 0, 1, 1,
                                 False, True, True, False, False)
    with pymupdf.open(pdf_path) as pdf:
        if len(pdf) != 1:
            raise RuntimeError("Compact export requires one Visio page")
        page = pdf[0]
        if abs(page.rect.width - width * 72) > 0.08 or abs(page.rect.height - height * 72) > 0.08:
            raise RuntimeError("Visio PDF page does not match the requested drawing page")
        # Alpha prevents white-on-white antialiasing from creating stray gray pixels.
        page.get_pixmap(dpi=dpi, alpha=True).save(str(png_path))
    with Image.open(png_path) as source:
        rgba = source.convert("RGBA")
    white = Image.new("RGBA", rgba.size, "white")
    white.alpha_composite(rgba)
    white.convert("RGB").save(png_path, dpi=(dpi, dpi))


def set_page_frame(page, backgrounds, width, height):
    page.PageSheet.CellsU("PageWidth").FormulaU = f"{width:.12f} in"
    page.PageSheet.CellsU("PageHeight").FormulaU = f"{height:.12f} in"
    for background in backgrounds:
        for cell, value in (("Width", width), ("Height", height),
                            ("PinX", width / 2), ("PinY", height / 2),
                            ("LocPinX", width / 2), ("LocPinY", height / 2)):
            background.CellsU(cell).FormulaU = f"{value:.12f} in"
        background.CellsU("LinePattern").FormulaU = "0"
        background.CellsU("FillPattern").FormulaU = "1"
        background.CellsU("FillForegnd").FormulaU = "RGB(255,255,255)"
        background.SendToBack()


def export_compact(document, page, outputs, *, backgrounds=(), dpi=300, padding_px=2):
    """Export PNG/SVG with measured padding, leaving the calibrated page in VSDX."""
    if padding_px not in (1, 2):
        raise ValueError("padding_px must be 1 or 2")
    if not isinstance(dpi, int) or not 72 <= dpi <= 1200:
        raise ValueError("dpi must be an integer from 72 through 1200")
    backgrounds = list(backgrounds)
    # Start outside every shape, rather than inferring strokes/arrowheads from nodes.
    left, bottom, right, top = page.BoundingBox(4)
    guard = 1.0
    width = right - left + 2 * guard
    height = top - bottom + 2 * guard
    offset_x, offset_y = guard - left, guard - bottom
    page.CreateSelection(1).Move(offset_x, offset_y)
    if not backgrounds:
        background = page.DrawRectangle(0, 0, width, height)
        background.NameU = "export__white_background"
        backgrounds.append(background)
    set_page_frame(page, backgrounds, width, height)
    attempts = []
    with TemporaryDirectory(prefix=".visio-export-", dir=Path(outputs["png"]).parent) as temp:
        for _ in range(8):
            rasterize_page(document, Path(temp) / "page.pdf", outputs["png"], width, height, dpi)
            measured = measure_white_border(outputs["png"])
            attempts.append(measured)
            ml, mt, mr, mb = measured["margins_px"]
            if not all((ml, mt, mr, mb)):
                raise RuntimeError("Visible content touches the probe boundary; export may be clipped")
            if [ml, mt, mr, mb] == [padding_px] * 4:
                break
            x1, y1, x2, y2 = measured["content_bbox_px"]
            width = (x2 - x1 + 2 * padding_px) / dpi
            height = (y2 - y1 + 2 * padding_px) / dpi
            dx, dy = (padding_px - ml) / dpi, (padding_px - mb) / dpi
            page.CreateSelection(1).Move(dx, dy)
            offset_x += dx
            offset_y += dy
            set_page_frame(page, backgrounds, width, height)
        else:
            raise RuntimeError(f"Export padding did not converge: {attempts}")
    page.Export(str(outputs["svg"]))
    root = ET.parse(outputs["svg"]).getroot()
    viewbox = [float(value) for value in root.attrib["viewBox"].split()]
    if any(abs(a - b) > 0.02 for a, b in zip(viewbox, (0, 0, width * 72, height * 72))):
        raise RuntimeError("SVG viewport does not match the calibrated Visio page")
    return {
        "dpi": dpi, "padding_px": padding_px, "raster_source": "visio_fixed_format_pdf", **measured,
        "page_size_in": [width, height], "svg_viewbox": viewbox,
        "translation_in": [offset_x, offset_y],
        "calibration_exports": len(attempts), "scaled_objects": False,
    }
