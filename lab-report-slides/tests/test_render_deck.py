import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import render_deck  # noqa: E402


class RenderDeckTests(unittest.TestCase):
    def test_exports_html_pdf_png_and_image_pptx(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            image = base / "result.png"
            Image.new("RGB", (320, 180), "#4472C4").save(image)
            deck = base / "deck.json"
            deck.write_text(json.dumps({
                "title": "测试汇报",
                "date": "20260715",
                "slides": [{"title": "测试结果", "status": "已完成", "blocks": [{"type": "text", "text": "完成测试"}, {"type": "image", "path": str(image), "caption": "结果图"}]}]
            }, ensure_ascii=False), encoding="utf-8")
            output = base / "out"
            manifest = render_deck.render(deck, output, "20260715")

            self.assertEqual(manifest["slide_count"], 1)
            self.assertTrue((output / "20260715.html").stat().st_size > 0)
            self.assertTrue((output / "20260715.pdf").stat().st_size > 0)
            self.assertTrue(zipfile.is_zipfile(output / "20260715.pptx"))
            with Image.open(output / "20260715_01.png") as rendered:
                self.assertEqual(rendered.size, (1600, 900))
            second = render_deck.render(deck, output, "20260715")
            self.assertEqual(second["stem"], "20260715_v2")
            self.assertTrue((output / "20260715_v2.pptx").exists())


if __name__ == "__main__":
    unittest.main()
