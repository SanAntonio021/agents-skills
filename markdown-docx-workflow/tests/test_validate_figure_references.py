import importlib.util
import json
import struct
import tempfile
import unittest
import zlib
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "validate_figure_references.py"
SPEC = importlib.util.spec_from_file_location("validate_figure_references", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def write_png(path: Path, width: int = 2, height: int = 3) -> None:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    raw = b"".join(b"\x00" + b"\x00\x00\x00" * width for _ in range(height))
    payload = b"\x89PNG\r\n\x1a\n"
    payload += chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
    payload += chunk(b"IDAT", zlib.compress(raw))
    payload += chunk(b"IEND", b"")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


class FigureReferenceValidationTests(unittest.TestCase):
    def build_fixture(self, root: Path) -> Path:
        current = root / "figures" / "图1" / "final" / "current.png"
        write_png(current)
        document = root / "draft.md"
        document.write_text("![图1 当前图题](figures/图1/final/current.png)\n\n图1 当前图题\n", encoding="utf-8")
        manifest = {
            "project_root": ".",
            "require_final_directory": True,
            "expected_markdown_reference_count": 1,
            "figures": [
                {
                    "number": 1,
                    "title": "当前图题",
                    "status": "confirmed",
                    "path": "figures/图1/final/current.png",
                    "sha256": MODULE._sha256(current),
                    "width": 2,
                    "height": 3,
                    "markdown_references": [{"document": "draft.md", "display_number": 1}],
                }
            ],
        }
        manifest_path = root / "final-manifest.json"
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
        return manifest_path

    def test_confirmed_reference_passes(self):
        with tempfile.TemporaryDirectory() as temp:
            result = MODULE.validate(self.build_fixture(Path(temp)))
            self.assertEqual("passed", result["status"])
            self.assertEqual([], result["issues"])

    def test_old_confirmed_file_is_rejected_even_inside_final(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            manifest = self.build_fixture(root)
            write_png(root / "figures" / "图1" / "final" / "old-confirmed.png")
            (root / "draft.md").write_text(
                "![图1 当前图题](figures/图1/final/old-confirmed.png)\n\n图1 当前图题\n",
                encoding="utf-8",
            )
            result = MODULE.validate(manifest)
            codes = {issue["code"] for issue in result["issues"]}
            self.assertEqual("failed", result["status"])
            self.assertIn("unlisted_image_reference", codes)
            self.assertIn("declared_reference_count_mismatch", codes)

    def test_title_and_placeholder_mismatch_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            manifest = self.build_fixture(root)
            (root / "draft.md").write_text(
                "图建议：后续替换\n\n![图1 旧图题](figures/图1/final/current.png)\n\n图1 旧图题\n",
                encoding="utf-8",
            )
            result = MODULE.validate(manifest)
            codes = {issue["code"] for issue in result["issues"]}
            self.assertIn("figure_placeholder_remaining", codes)
            self.assertIn("figure_alt_mismatch", codes)
            self.assertIn("figure_caption_mismatch", codes)


if __name__ == "__main__":
    unittest.main()
