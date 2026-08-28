import importlib.util
import json
import tempfile
import unittest
import zipfile
from pathlib import Path


MODULE = Path(__file__).parents[1] / "scripts" / "release_bundle.py"
spec = importlib.util.spec_from_file_location("pptx_release_bundle", MODULE)
release = importlib.util.module_from_spec(spec)
assert spec is not None and spec.loader is not None
spec.loader.exec_module(release)


P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"


def write_presentation(path: Path, slide_texts: list[str], *, global_text: str = "stable") -> None:
    parts = {
        "ppt/presentation.xml": (
            f'<p:presentation xmlns:p="{P_NS}" xmlns:r="{R_NS}">'
            "<p:sldIdLst>"
            + "".join(
                f'<p:sldId id="{index}" r:id="rId{index}"/>'
                for index in range(1, len(slide_texts) + 1)
            )
            + "</p:sldIdLst></p:presentation>"
        ),
        "ppt/_rels/presentation.xml.rels": (
            f'<Relationships xmlns="{REL_NS}">'
            + "".join(
                f'<Relationship Id="rId{index}" Type="slide" Target="slides/slide{index}.xml"/>'
                for index in range(1, len(slide_texts) + 1)
            )
            + "</Relationships>"
        ),
        "docProps/app.xml": f"<app>{global_text}</app>",
    }
    for index, text in enumerate(slide_texts, 1):
        parts[f"ppt/slides/slide{index}.xml"] = f"<slide>{text}</slide>"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as package:
        for name, data in parts.items():
            package.writestr(name, data)


class ReleaseBundleTests(unittest.TestCase):
    def test_initialize_creates_versioned_bundle_and_refuses_existing_version(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "outputs"
            first = release.initialize_release(root, "市场页", date="20260828")
            second = release.initialize_release(root, "市场页", date="20260828")
            self.assertEqual(first.name, "市场页_20260828_v01")
            self.assertEqual(second.name, "市场页_20260828_v02")
            self.assertTrue((first / "release_manifest.json").is_file())
            with self.assertRaises(release.ReleaseBundleError):
                release._write_json(first / "release_manifest.json", {}, refuse_existing=True)

    def test_snapshot_excludes_bundle_and_detects_external_changes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "outputs"
            bundle = root / "topic_20260828_v01"
            bundle.mkdir(parents=True)
            external = root / "old.txt"
            external.write_text("before", encoding="utf-8")
            inside = bundle / "preview.png"
            inside.write_bytes(b"old")
            evidence = bundle / "evidence"
            evidence.mkdir()
            before = evidence / "before.json"
            after = evidence / "after.json"
            release.write_snapshot(root, bundle, before)
            external.write_text("after", encoding="utf-8")
            inside.write_bytes(b"new")
            release.write_snapshot(root, bundle, after)
            result = release.compare_snapshots(before, after)
            self.assertEqual(result["status"], "CHANGED")
            self.assertEqual(result["changed"], ["old.txt"])
            self.assertNotIn("topic_20260828_v01/preview.png", result["changed"])

    def test_snapshot_scope_mismatch_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            first = Path(temp_dir) / "before.json"
            second = Path(temp_dir) / "after.json"
            payload = {"schema_version": 1, "root": "C:/one", "exclude": "bundle", "files": []}
            first.write_text(json.dumps(payload), encoding="utf-8")
            payload["root"] = "C:/two"
            second.write_text(json.dumps(payload), encoding="utf-8")
            result = release.compare_snapshots(first, second)
            self.assertEqual(result["status"], "scope_mismatch")
            self.assertEqual(result["added"], [])
            self.assertEqual(result["deleted"], [])

    def test_snapshot_output_must_stay_inside_excluded_bundle(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "outputs"
            bundle = root / "topic_20260828_v01"
            bundle.mkdir(parents=True)
            with self.assertRaises(release.ReleaseBundleError):
                release.write_snapshot(root, bundle, root / "outside.json")

    def test_changed_slide_can_shrink_visual_scope_only_after_proof(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            parent = temp / "parent.pptx"
            current = temp / "current.pptx"
            write_presentation(parent, ["old-1", "stable-2"])
            write_presentation(current, ["new-1", "stable-2"])
            result = release.compare_slides(parent, current, [1], parent_visual_pass=True)
            self.assertEqual(result["status"], "UNCHANGED_SLIDES_PROVEN")
            self.assertEqual(result["visual_scope"], "CHANGED_SLIDES_ONLY")
            self.assertEqual(result["different_slides"], [1])

    def test_undeclared_slide_change_requires_full_visual_qa(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            parent = temp / "parent.pptx"
            current = temp / "current.pptx"
            write_presentation(parent, ["stable-1", "old-2"])
            write_presentation(current, ["stable-1", "new-2"])
            result = release.compare_slides(parent, current, [1], parent_visual_pass=True)
            self.assertEqual(result["status"], "FULL_VISUAL_QA_REQUIRED")
            self.assertEqual(result["visual_scope"], "FULL_DECK")
            self.assertIn("undeclared slide 2 changed", result["reasons"])

    def test_global_package_change_requires_full_visual_qa(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            parent = temp / "parent.pptx"
            current = temp / "current.pptx"
            write_presentation(parent, ["old-1"], global_text="old")
            write_presentation(current, ["new-1"], global_text="new")
            result = release.compare_slides(parent, current, [1], parent_visual_pass=True)
            self.assertEqual(result["status"], "FULL_VISUAL_QA_REQUIRED")
            self.assertIn("global package parts or relationships changed", result["reasons"])


if __name__ == "__main__":
    unittest.main()
