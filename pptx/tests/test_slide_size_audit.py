import importlib.util
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


MODULE = Path(__file__).parents[1] / "scripts" / "slide_size_audit.py"
spec = importlib.util.spec_from_file_location("pptx_slide_size_audit", MODULE)
audit_module = importlib.util.module_from_spec(spec)
assert spec is not None and spec.loader is not None
sys.modules[spec.name] = audit_module
spec.loader.exec_module(audit_module)


P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"


def write_package(path: Path, *, width: str | None, height: str | None) -> None:
    if width is None or height is None:
        slide_size = ""
    else:
        slide_size = f'<p:sldSz cx="{width}" cy="{height}"/>'
    presentation = (
        f'<p:presentation xmlns:p="{P_NS}">{slide_size}</p:presentation>'
    )
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as package:
        package.writestr("ppt/presentation.xml", presentation)


class SlideSizeAuditTests(unittest.TestCase):
    def test_standard_wide_screen_passes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "wide.pptx"
            write_package(path, width="12192000", height="6858000")
            result = audit_module.audit(path, "wide16x9")
            self.assertEqual(result["status"], "PASS")
            self.assertEqual(result["slide_size"]["detected_format"], "wide16x9")
            self.assertAlmostEqual(result["slide_size"]["width_inches"], 13.333333)

    def test_legacy_same_ratio_fails_wide_gate(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "legacy.pptx"
            write_package(path, width="9144000", height="5143500")
            result = audit_module.audit(path, "wide16x9")
            self.assertEqual(result["status"], "FAIL")
            self.assertEqual(result["slide_size"]["detected_format"], "legacy16x9")

    def test_missing_slide_size_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "missing.pptx"
            write_package(path, width=None, height=None)
            with self.assertRaises(audit_module.SlideSizeInputError):
                audit_module.read_slide_size(path)


if __name__ == "__main__":
    unittest.main()
