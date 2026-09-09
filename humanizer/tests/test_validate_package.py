"""Exercise the package validator on isolated, deliberately damaged packages."""

from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest


TEST_DIR = Path(__file__).resolve().parent
PACKAGE = Path(os.environ.get("HUMANIZER_TEST_PACKAGE", str(TEST_DIR.parent))).resolve()


class PackageValidationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="validator-test-", dir=TEST_DIR)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for relative in ("SKILL.md", "README.md", ".claude-plugin/plugin.json", "scripts/validate-package.py"):
            target = self.root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(PACKAGE / relative, target)

    def replace(self, relative, old, new):
        path = self.root / relative
        source = path.read_text(encoding="utf-8")
        self.assertIn(old, source)
        path.write_text(source.replace(old, new, 1), encoding="utf-8")

    def run_validator(self, legacy_encoding=False):
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        command = [sys.executable, "-X", "utf8=0" if legacy_encoding else "utf8=1"]
        command.append(str(self.root / "scripts/validate-package.py"))
        return subprocess.run(command, cwd=self.root, env=env, capture_output=True,
                              text=True, encoding="utf-8", timeout=20)

    def rejected_with(self, message):
        result = self.run_validator()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(message, result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_valid_package_passes(self):
        result = self.run_validator()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("is valid", result.stdout)

    def test_utf8_package_survives_legacy_locale(self):
        path = self.root / "README.md"
        path.write_text(path.read_text(encoding="utf-8") + "\n中文备注，保持原意。🧪\n", encoding="utf-8")
        result = self.run_validator(legacy_encoding=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_duplicate_readme_number_rejected(self):
        path = self.root / "README.md"
        source = path.read_text(encoding="utf-8")
        row = re.search(r"(?m)^\| 1 \|.*$", source).group(0)
        path.write_text(source + "\n" + row + "\n", encoding="utf-8")
        self.rejected_with("exactly once")

    def test_missing_readme_has_actionable_error(self):
        (self.root / "README.md").unlink()
        self.rejected_with("Cannot read README.md")

    def test_malformed_json_has_location(self):
        (self.root / ".claude-plugin/plugin.json").write_text('{"version":}', encoding="utf-8")
        self.rejected_with("Invalid JSON in .claude-plugin/plugin.json at line 1")

    def test_non_object_json_rejected(self):
        (self.root / ".claude-plugin/plugin.json").write_text("[]", encoding="utf-8")
        self.rejected_with("must contain a JSON object")

    def test_invalid_utf8_identifies_file(self):
        (self.root / "README.md").write_bytes(b"\xff")
        self.rejected_with("Cannot read README.md as UTF-8")

    def test_top_level_version_rejected(self):
        self.replace("SKILL.md", "name: humanizer", "name: humanizer\nversion: 9.9.9")
        self.rejected_with("Remove nonportable frontmatter key: version")

    def test_version_mismatch_still_rejected(self):
        path = self.root / ".claude-plugin/plugin.json"
        source = path.read_text(encoding="utf-8")
        source = re.sub(r'"version":\s*"[^"]+"', '"version": "9.9.9"', source, count=1)
        path.write_text(source, encoding="utf-8")
        self.rejected_with("Version mismatch")


if __name__ == "__main__":
    unittest.main(verbosity=2)
