"""Exercise the real PowerShell/Pandoc export with an offline template stub."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
POWERSHELL = shutil.which("powershell.exe")
PANDOC = shutil.which("pandoc")
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a4s8AAAAASUVORK5CYII=")


@unittest.skipUnless(POWERSHELL and PANDOC, "Windows PowerShell and Pandoc are required")
class ExportVersionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        scripts = self.root / "scripts"
        template_scripts = scripts / "template"
        template_scripts.mkdir(parents=True)
        self.exporter = template_scripts / "export_markdown_to_word.ps1"
        shutil.copy2(SCRIPTS / "template" / self.exporter.name, self.exporter)
        shutil.copy2(SCRIPTS / "document_versions.py", scripts / "document_versions.py")
        for helper in ('reference_fields.py', 'style_guard.py', 'styles_normalizer.py'):
            shutil.copy2(SCRIPTS / helper, scripts / helper)
        (template_scripts / "OfficeComGuard.psm1").write_text(
            "function Assert-WordComPermission { param([switch]$AllowOfficeCom) }\n",
            encoding="utf-8",
        )
        (template_scripts / "word_template_formatter.py").write_text(
            "from pathlib import Path\n"
            "def default_profile_path(path):\n"
            "    return path.with_name(path.stem + '.style-profile.json')\n",
            encoding="utf-8",
        )
        self.source_dir = self.root / "\u4e2d\u6587 source"
        self.source_dir.mkdir()
        self.source = self.source_dir / "draft.md"
        (self.source_dir / "plot image.png").write_bytes(PNG)
        self.source.write_text("# Version fixture\n\n![plot](<plot image.png>)\n", encoding="utf-8")
        self.template = self.root / "template.docx"
        self.template.write_bytes(b"offline formatter placeholder")
        self.environment = dict(os.environ)
        self.environment["PATH"] = str(Path(sys.executable).parent) + os.pathsep + self.environment.get("PATH", "")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def export(self, sources: list[Path] | None = None, *extra: str, pandoc_path: str | None = None) -> subprocess.CompletedProcess:
        return subprocess.run(
            [POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(self.exporter),
             *map(str, sources or [self.source]), "-TemplatePath", str(self.template),
             "-PandocPath", pandoc_path or PANDOC, "-AllowOfficeCom", *extra],
            cwd=self.root, capture_output=True, text=True, encoding="utf-8", errors="replace",
            env=self.environment, timeout=45,
        )

    def assert_exported(self, output: Path) -> dict:
        self.assertTrue(output.is_file())
        with zipfile.ZipFile(output) as package:
            media = [name for name in package.namelist() if name.startswith("word/media/")]
            self.assertEqual(1, len(media))
            self.assertEqual(PNG, package.read(media[0]))
        record = json.loads(Path(str(output) + ".check.json").read_text(encoding="utf-8"))
        self.assertFalse(record["ok"])
        self.assertEqual("UNCHECKED", record["status"])
        self.assertEqual(hashlib.sha256(output.read_bytes()).hexdigest(), record["document_versions"]["generated_document"]["sha256"])
        return record

    def test_export_resolves_reference_images_from_source_directory(self) -> None:
        before = self.source.read_bytes()
        result = self.export()
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        record = self.assert_exported(self.source.with_name("draft.formatted.docx"))
        image = next(item for item in record["document_versions"]["inputs"]["files"] if item["role"] == "image")
        self.assertEqual(str((self.source_dir / "plot image.png").resolve()), image["path"])
        self.assertEqual(before, self.source.read_bytes())

    def test_default_export_keeps_hand_edited_word_and_creates_new_output(self) -> None:
        original = self.source.with_name("draft.formatted.docx")
        original.write_bytes(b"user-edited Word sentinel")
        result = self.export()
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertEqual(b"user-edited Word sentinel", original.read_bytes())
        self.assert_exported(self.source.with_name("draft.formatted-1.docx"))

    def test_relative_pandoc_path_is_resolved_before_changing_directory(self) -> None:
        try:
            relative = os.path.relpath(PANDOC, self.root)
        except ValueError:
            self.skipTest("Pandoc is on a different drive")
        result = self.export(pandoc_path=relative)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assert_exported(self.source.with_name("draft.formatted.docx"))

    def test_explicit_existing_output_is_rejected_before_conversion(self) -> None:
        output = self.root / "chosen.docx"
        output.write_bytes(b"user-edited Word sentinel")
        result = self.export(None, "-OutputPath", str(output))
        self.assertNotEqual(0, result.returncode)
        self.assertEqual(b"user-edited Word sentinel", output.read_bytes())
        self.assertFalse(Path(str(output) + ".check.json").exists())

    def test_explicit_overwrite_permission_is_honored(self) -> None:
        output = self.root / "chosen.docx"
        output.write_bytes(b"approved replacement")
        result = self.export(None, "-OutputPath", str(output), "-OverwriteExisting")
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assert_exported(output)

    def test_batch_exports_keep_distinct_output_paths(self) -> None:
        second = self.source_dir / "second.md"
        second.write_bytes(self.source.read_bytes())
        result = self.export([self.source, second])
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assert_exported(self.source.with_name("draft.formatted.docx"))
        self.assert_exported(second.with_name("second.formatted.docx"))

    def test_duplicate_batch_inputs_fail_before_any_output(self) -> None:
        result = self.export([self.source, self.source])
        self.assertNotEqual(0, result.returncode)
        self.assertFalse(self.source.with_name("draft.formatted.docx").exists())

    def test_record_cannot_replace_an_input(self) -> None:
        before = self.source.read_bytes()
        result = self.export(None, "-CheckRecordPath", str(self.source))
        self.assertNotEqual(0, result.returncode)
        self.assertEqual(before, self.source.read_bytes())
        self.assertFalse(self.source.with_name("draft.formatted.docx").exists())


if __name__ == "__main__":
    unittest.main()
