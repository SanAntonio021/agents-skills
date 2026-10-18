from __future__ import annotations

import json
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[2]


class TemplateBundleTests(unittest.TestCase):
    def test_docx_is_the_only_word_skill_entrypoint(self) -> None:
        source = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        retired_name = "word" + "-template"
        self.assertIn("name: docx", source)
        self.assertIn("$docx", source)
        self.assertNotIn(f"${retired_name}", source)
        self.assertFalse((SKILL_ROOT.parent / retired_name).exists())

    def test_all_template_profiles_are_valid_json(self) -> None:
        profile_dir = SKILL_ROOT / "assets" / "template"
        profiles = sorted(profile_dir.glob("*.style-profile.json"))
        self.assertEqual(len(profiles), 10)
        for profile in profiles:
            with self.subTest(profile=profile.name):
                payload = json.loads(profile.read_text(encoding="utf-8"))
                self.assertIsInstance(payload, dict)
                self.assertIn("styles", payload)

    def test_template_commands_and_references_are_bundled(self) -> None:
        script_dir = SKILL_ROOT / "scripts" / "template"
        reference_dir = SKILL_ROOT / "references" / "template"
        required_scripts = {
            "OfficeComGuard.psm1",
            "build_master_template.py",
            "export_markdown_to_word.ps1",
            "install_normal_template.py",
            "office_com_guard.py",
            "validate_master_default.py",
            "word_constants.py",
            "word_template_formatter.py",
        }
        required_references = {
            "template-governance.md",
            "template-presets.md",
            "workflow.md",
        }
        self.assertTrue(required_scripts.issubset({p.name for p in script_dir.iterdir()}))
        self.assertTrue(required_references.issubset({p.name for p in reference_dir.iterdir()}))


if __name__ == "__main__":
    unittest.main()
