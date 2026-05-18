#!/usr/bin/env python3
"""Extract useful images from a paper PDF for paper-summary outputs.

The script first extracts embedded images with PyMuPDF. For pages without
usable embedded images, it can render the page as a fallback so vector figures
are still available for Markdown summaries.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

try:
    import fitz  # PyMuPDF
except ImportError as exc:  # pragma: no cover - exercised by CLI environment
    raise SystemExit(
        "PyMuPDF is required. Install it with: python -m pip install pymupdf"
    ) from exc


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def ensure_png_name(index: int) -> str:
    return f"img_{index:03d}.png"


def save_pixmap_png(pix: fitz.Pixmap, path: Path) -> None:
    if pix.alpha or pix.n >= 4:
        converted = fitz.Pixmap(fitz.csRGB, pix)
        converted.save(path)
        converted = None
    else:
        pix.save(path)


def extract_images(
    pdf_path: Path,
    out_dir: Path,
    mode: str,
    min_bytes: int,
    min_width: int,
    min_height: int,
    render_dpi: int,
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)

    doc = fitz.open(pdf_path)
    manifest: list[dict[str, Any]] = []
    seen_hashes: set[str] = set()
    image_index = 1

    for page_index in range(doc.page_count):
        page = doc.load_page(page_index)
        page_number = page_index + 1
        saved_embedded_on_page = 0

        if mode in {"auto", "embedded"}:
            for image_order, image_info in enumerate(page.get_images(full=True), start=1):
                xref = image_info[0]
                extracted = doc.extract_image(xref)
                image_bytes = extracted.get("image", b"")
                width = int(extracted.get("width") or 0)
                height = int(extracted.get("height") or 0)
                ext = str(extracted.get("ext") or "png").lower()

                if len(image_bytes) < min_bytes:
                    continue
                if width < min_width or height < min_height:
                    continue

                digest = sha256_bytes(image_bytes)
                if digest in seen_hashes:
                    continue
                seen_hashes.add(digest)

                filename = ensure_png_name(image_index)
                output_path = out_dir / filename

                if ext == "png":
                    output_path.write_bytes(image_bytes)
                else:
                    pix = fitz.Pixmap(doc, xref)
                    save_pixmap_png(pix, output_path)
                    pix = None

                manifest.append(
                    {
                        "file": filename,
                        "page": page_number,
                        "source_type": "embedded",
                        "width": width,
                        "height": height,
                        "bytes": output_path.stat().st_size,
                        "sha256": digest,
                        "xref": xref,
                        "page_image_order": image_order,
                    }
                )
                image_index += 1
                saved_embedded_on_page += 1

        should_render_page = mode == "page-render" or (
            mode == "auto" and saved_embedded_on_page == 0
        )
        if should_render_page:
            pix = page.get_pixmap(dpi=render_dpi, alpha=False)
            image_bytes = pix.tobytes("png")
            if (
                len(image_bytes) >= min_bytes
                and pix.width >= min_width
                and pix.height >= min_height
            ):
                digest = sha256_bytes(image_bytes)
                if digest not in seen_hashes:
                    seen_hashes.add(digest)
                    filename = ensure_png_name(image_index)
                    output_path = out_dir / filename
                    output_path.write_bytes(image_bytes)
                    manifest.append(
                        {
                            "file": filename,
                            "page": page_number,
                            "source_type": "page-render",
                            "width": pix.width,
                            "height": pix.height,
                            "bytes": output_path.stat().st_size,
                            "sha256": digest,
                            "render_dpi": render_dpi,
                        }
                    )
                    image_index += 1
            pix = None

    result = {
        "pdf": str(pdf_path),
        "out_dir": str(out_dir),
        "mode": mode,
        "page_count": doc.page_count,
        "image_count": len(manifest),
        "images": manifest,
    }
    doc.close()

    manifest_path = out_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return result


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract embedded paper images and optionally render pages."
    )
    parser.add_argument("--pdf", required=True, type=Path, help="Input PDF path.")
    parser.add_argument(
        "--out", required=True, type=Path, help="Output image directory."
    )
    parser.add_argument(
        "--mode",
        choices=["auto", "embedded", "page-render"],
        default="auto",
        help="auto extracts embedded images and renders pages without usable images.",
    )
    parser.add_argument("--min-bytes", type=int, default=10 * 1024)
    parser.add_argument("--min-width", type=int, default=100)
    parser.add_argument("--min-height", type=int, default=100)
    parser.add_argument("--render-dpi", type=int, default=200)
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    pdf_path = args.pdf.resolve()
    out_dir = args.out.resolve()

    if not pdf_path.exists():
        print(f"PDF not found: {pdf_path}", file=sys.stderr)
        return 2
    if not pdf_path.is_file():
        print(f"PDF path is not a file: {pdf_path}", file=sys.stderr)
        return 2

    result = extract_images(
        pdf_path=pdf_path,
        out_dir=out_dir,
        mode=args.mode,
        min_bytes=args.min_bytes,
        min_width=args.min_width,
        min_height=args.min_height,
        render_dpi=args.render_dpi,
    )
    print(
        json.dumps(
            {
                "pdf": result["pdf"],
                "out_dir": result["out_dir"],
                "page_count": result["page_count"],
                "image_count": result["image_count"],
                "manifest": str(out_dir / "manifest.json"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
