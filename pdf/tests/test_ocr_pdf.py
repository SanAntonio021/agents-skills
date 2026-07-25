from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import fitz
from PIL import Image, ImageDraw, ImageFont

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "ocr_pdf.py"
SPEC = importlib.util.spec_from_file_location("pdf_ocr_router", SCRIPT)
assert SPEC and SPEC.loader
ROUTER = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = ROUTER
SPEC.loader.exec_module(ROUTER)


def make_feature(category: str, page_number: int = 1) -> ROUTER.PageFeatures:
    return ROUTER.PageFeatures(
        page_number=page_number,
        width=595.2,
        height=841.92,
        rotation=0,
        text_chars=100,
        visible_chars=80,
        bad_text_chars=0,
        bad_text_ratio=0.0,
        image_count=1,
        image_coverage=1.0,
        category=category,
    )


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def create_bilingual_scan(path: Path) -> None:
    font_path = Path(r"C:\Windows\Fonts\msyh.ttc")
    bold_path = Path(r"C:\Windows\Fonts\msyhbd.ttc")
    if not font_path.is_file() or not bold_path.is_file():
        raise unittest.SkipTest("Microsoft YaHei fonts are not installed")
    image = Image.new("RGB", (2480, 3508), "white")
    draw = ImageDraw.Draw(image)
    regular = ImageFont.truetype(str(font_path), 72)
    bold = ImageFont.truetype(str(bold_path), 88)
    lines = [
        ("PDF OCR CANARY 2026", bold),
        ("English sample: Searchable text should survive.", regular),
        (
            (
                "\u7b80\u4f53\u4e2d\u6587\u6837\u672c\uff1a"
                "\u81ea\u52a8\u5316\u6587\u5b57\u8bc6\u522b\u3002"
            ),
            regular,
        ),
        ("\u7f16\u53f7\uff1aOCR-20260724", regular),
    ]
    y = 380
    for text, font in lines:
        draw.text((240, y), text, font=font, fill="black")
        y += 210
    image.save(path, format="PDF", resolution=300.0)


def create_plain_scan(path: Path, label: str) -> None:
    image = Image.new("RGB", (1200, 1600), "white")
    draw = ImageDraw.Draw(image)
    draw.text((120, 180), label, fill="black")
    image.save(path, format="PDF", resolution=150.0)


def create_traditional_scan(path: Path) -> None:
    font_path = Path(r"C:\Windows\Fonts\msyh.ttc")
    if not font_path.is_file():
        raise unittest.SkipTest("Microsoft YaHei font is not installed")
    image = Image.new("RGB", (1800, 2400), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype(str(font_path), 88)
    draw.text(
        (180, 300),
        "\u7e41\u9ad4\u4e2d\u6587\u6e2c\u8a66\uff1a"
        "\u81ea\u52d5\u5316\u6587\u5b57\u8b58\u5225\u3002",
        font=font,
        fill="black",
    )
    draw.text(
        (180, 520),
        "\u7de8\u865f\uff1aOCR-TRA-20260724",
        font=font,
        fill="black",
    )
    image.save(path, format="PDF", resolution=200.0)


class ClassificationTests(unittest.TestCase):
    def test_page_classification_thresholds(self) -> None:
        cases = [
            ((0, 0.0, 0.0), "blank"),
            ((0, 0.0, 0.95), "scan"),
            ((12, 0.0, 0.95), "page_mixed"),
            ((100, 0.0, 0.95), "good_ocr"),
            ((100, 0.25, 0.95), "broken"),
            ((100, 0.0, 0.10), "digital"),
            ((10, 0.0, 0.10), "sparse_text"),
        ]
        for values, expected in cases:
            with self.subTest(expected=expected):
                actual = ROUTER.classify_page(
                    visible_chars=values[0],
                    bad_text_ratio=values[1],
                    image_coverage=values[2],
                )
                self.assertEqual(actual, expected)

    def test_auto_route_matrix(self) -> None:
        cases = [
            (["digital"], "none"),
            (["good_ocr"], "none"),
            (["scan"], "skip"),
            (["digital", "scan"], "skip"),
            (["page_mixed"], "redo"),
            (["broken"], "redo"),
            (["digital", "broken"], "redo"),
        ]
        for categories, expected in cases:
            pages = [make_feature(category, index + 1) for index, category in enumerate(categories)]
            with self.subTest(categories=categories):
                mode, _reason = ROUTER.select_mode(pages, "auto")
                self.assertEqual(mode, expected)

    def test_explicit_mode_wins(self) -> None:
        pages = [make_feature("broken")]
        for requested in ("none", "skip", "redo"):
            mode, _reason = ROUTER.select_mode(pages, requested)
            self.assertEqual(mode, requested)

    def test_union_area_does_not_double_count(self) -> None:
        rects = [fitz.Rect(0, 0, 10, 10), fitz.Rect(5, 0, 15, 10)]
        self.assertEqual(ROUTER.rect_union_area(rects), 150.0)


class InspectionTests(unittest.TestCase):
    def test_native_and_image_only_pages_are_distinguished(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            image = Image.new("RGB", (800, 1100), "white")
            draw = ImageDraw.Draw(image)
            draw.text((100, 100), "SCAN PAGE", fill="black")
            png = root / "scan.png"
            image.save(png)

            pdf = root / "mixed.pdf"
            document = fitz.open()
            digital = document.new_page(width=595.2, height=841.92)
            digital.insert_text((72, 100), "Native digital text " * 8, fontsize=12)
            scan = document.new_page(width=595.2, height=841.92)
            scan.insert_image(scan.rect, filename=str(png))
            document.save(pdf)
            document.close()

            inspection = ROUTER.inspect_pdf(pdf)
            self.assertEqual(inspection.page_count, 2)
            self.assertEqual(inspection.pages[0].category, "digital")
            self.assertEqual(inspection.pages[1].category, "scan")
            mode, _reason = ROUTER.select_mode(inspection.pages, "auto")
            self.assertEqual(mode, "skip")


@unittest.skipUnless(
    os.environ.get("PDF_OCR_RUN_E2E") == "1",
    "Set PDF_OCR_RUN_E2E=1 to run the installed OCR stack",
)
class EndToEndTests(unittest.TestCase):
    def test_scan_canary_and_failure_cleanup(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            input_pdf = root / "canary.pdf"
            output_dir = root / "outputs"
            output_dir.mkdir()
            create_bilingual_scan(input_pdf)
            input_hash = sha256(input_pdf)

            success = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--input",
                    str(input_pdf),
                    "--languages",
                    "chi_sim",
                    "--output-directory",
                    str(output_dir),
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=180,
                check=False,
            )
            self.assertEqual(success.returncode, 0, success.stderr)
            output_pdf = output_dir / "canary_ocr.pdf"
            output_txt = output_dir / "canary_ocr.txt"
            status_path = output_dir / "canary_ocr.status.json"
            self.assertTrue(output_pdf.is_file())
            self.assertTrue(output_txt.is_file())
            self.assertTrue((output_dir / "canary_ocr.log").is_file())
            self.assertTrue(status_path.is_file())
            self.assertEqual(sha256(input_pdf), input_hash)
            text = output_txt.read_text(encoding="utf-8", errors="replace")
            self.assertIn("PDF OCR CANARY", text)
            self.assertIn("OCR-20260724", text)
            self.assertIn("\u7b80\u4f53", text)
            self.assertIn("\u7f16\u53f7", text)
            status = json.loads(status_path.read_text(encoding="utf-8"))
            self.assertEqual(status["status"], "success")
            self.assertEqual(status["route"]["selected_mode"], "skip")
            self.assertIsNone(status["dependencies"]["ghostscript"])
            self.assertTrue(status["output"]["finalized"])
            self.assertTrue(status["validation"]["pypdf_strict"])
            self.assertEqual(
                status["validation"]["pymupdf"][0]["input_size_points"],
                status["validation"]["pymupdf"][0]["output_size_points"],
            )

            existing_output_hash = sha256(output_pdf)
            conflict = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--input",
                    str(input_pdf),
                    "--languages",
                    "chi_sim",
                    "--output-directory",
                    str(output_dir),
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=60,
                check=False,
            )
            self.assertEqual(conflict.returncode, ROUTER.EXIT_CONFLICT)
            self.assertEqual(sha256(output_pdf), existing_output_hash)

            second_input = root / "missing-language.pdf"
            create_bilingual_scan(second_input)
            failure = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--input",
                    str(second_input),
                    "--languages",
                    "language_that_does_not_exist",
                    "--output-directory",
                    str(output_dir),
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=60,
                check=False,
            )
            self.assertEqual(failure.returncode, ROUTER.EXIT_DEPENDENCY)
            self.assertFalse((output_dir / "missing-language_ocr.pdf").exists())
            self.assertFalse((output_dir / "missing-language_ocr.txt").exists())
            self.assertFalse((output_dir / "missing-language_ocr.log").exists())
            self.assertFalse((output_dir / "missing-language_ocr.status.json").exists())
            failure_statuses = list(output_dir.glob(".pdf-ocr-run-*/status.json"))
            self.assertEqual(len(failure_statuses), 1)
            failure_status = json.loads(failure_statuses[0].read_text(encoding="utf-8"))
            self.assertEqual(failure_status["status"], "failed")
            self.assertEqual(failure_status["exit_code"], ROUTER.EXIT_DEPENDENCY)

    def test_document_mixed_keeps_native_and_ocr_text(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            scan_source = root / "scan-source.pdf"
            create_plain_scan(scan_source, "SCANNED PAGE OCR 67890")
            scan_document = fitz.open(scan_source)
            scan_page = scan_document[0]
            mixed = fitz.open()
            native_page = mixed.new_page(width=scan_page.rect.width, height=scan_page.rect.height)
            native_page.insert_text(
                (72, 100),
                "NATIVE PAGE TEXT 12345 " * 4,
                fontsize=16,
            )
            mixed_page = mixed.new_page(width=scan_page.rect.width, height=scan_page.rect.height)
            mixed_page.show_pdf_page(mixed_page.rect, scan_document, 0)
            input_pdf = root / "document-mixed.pdf"
            mixed.save(input_pdf)
            mixed.close()
            scan_document.close()
            output_dir = root / "outputs"

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--input",
                    str(input_pdf),
                    "--languages",
                    "eng",
                    "--output-directory",
                    str(output_dir),
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=180,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            status = json.loads(
                (output_dir / "document-mixed_ocr.status.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(status["route"]["selected_mode"], "skip")
            text = (output_dir / "document-mixed_ocr.txt").read_text(
                encoding="utf-8", errors="replace"
            )
            self.assertIn("NATIVE PAGE TEXT 12345", text)
            self.assertIn("SCANNED", text)
            self.assertIn("OCR", text)

    def test_good_existing_text_layer_is_copied_without_ocr(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            scan_source = root / "scan-source.pdf"
            create_plain_scan(scan_source, "BACKGROUND IMAGE")
            document = fitz.open(scan_source)
            page = document[0]
            page.insert_text(
                (72, 100),
                "GOOD EXISTING OCR TEXT " * 8,
                fontsize=16,
                render_mode=3,
            )
            input_pdf = root / "good-ocr.pdf"
            document.save(input_pdf)
            document.close()
            input_hash = sha256(input_pdf)
            output_dir = root / "outputs"

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--input",
                    str(input_pdf),
                    "--languages",
                    "eng",
                    "--output-directory",
                    str(output_dir),
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=60,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            status = json.loads(
                (output_dir / "good-ocr_ocr.status.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(status["route"]["selected_mode"], "none")
            self.assertEqual(
                sha256(output_dir / "good-ocr_ocr.pdf"),
                input_hash,
            )

    def test_page_level_mixed_content_uses_redo(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            scan_source = root / "scan-source.pdf"
            create_plain_scan(scan_source, "PAGE IMAGE OCR 24680")
            document = fitz.open(scan_source)
            page = document[0]
            page.insert_text((72, 90), "HEADER", fontsize=14)
            input_pdf = root / "page-mixed.pdf"
            document.save(input_pdf)
            document.close()
            output_dir = root / "outputs"

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--input",
                    str(input_pdf),
                    "--languages",
                    "eng",
                    "--output-directory",
                    str(output_dir),
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=180,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            status = json.loads(
                (output_dir / "page-mixed_ocr.status.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(status["route"]["selected_mode"], "redo")

    def test_traditional_chinese_language_pack(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            input_pdf = root / "traditional.pdf"
            create_traditional_scan(input_pdf)
            output_dir = root / "outputs"
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--input",
                    str(input_pdf),
                    "--languages",
                    "chi_tra",
                    "--output-directory",
                    str(output_dir),
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=180,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            text = (output_dir / "traditional_ocr.txt").read_text(
                encoding="utf-8", errors="replace"
            )
            self.assertIn("\u7de8\u865f", text)
            self.assertIn("OCR-TRA-20260724", text)


if __name__ == "__main__":
    unittest.main()
