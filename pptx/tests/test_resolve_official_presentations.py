"""Package selection failures must never fall back to an arbitrary old cache."""
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/resolve_official_presentations.py"
spec = importlib.util.spec_from_file_location("official_resolver", SCRIPT)
resolver = importlib.util.module_from_spec(spec)
spec.loader.exec_module(resolver)


class ResolverTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "registered"
        self.skill = self.root / "skills/presentations"
        self.skill.mkdir(parents=True)
        self.manifest = self.root / ".codex-plugin/plugin.json"
        self.manifest.parent.mkdir()
        self.manifest.write_text(json.dumps({"name": "presentations", "version": "v1", "skills": "./skills/"}))
        (self.skill / "SKILL.md").write_text("---\nname: Presentations\n---\n[design](design.md)\n")
        for relative in (*resolver.REQUIRED, "design.md"):
            path = self.skill / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("fixture")
        self.entry = {"pluginId": resolver.PLUGIN_ID, "installed": True, "enabled": True,
                      "version": "v1", "source": {"source": "local", "path": str(self.root)}}
        self.registry = {"installed": [self.entry]}

    def rejects(self, reason):
        with self.assertRaisesRegex(resolver.Unavailable, reason):
            resolver.resolve(self.registry)

    def test_registered_package_with_old_cache_present(self):
        old = Path(self.temp.name) / "cache/presentations/v0/skills/presentations"
        old.mkdir(parents=True)
        (old / "SKILL.md").write_text("old")
        result = resolver.resolve(self.registry)
        self.assertEqual(Path(result["skill_path"]), self.skill / "SKILL.md")
        self.assertEqual(result["version"], "v1")

    def test_missing_and_duplicate_registration(self):
        self.registry["installed"] = []
        self.rejects("plugin_missing")
        self.registry["installed"] = [self.entry, dict(self.entry)]
        self.rejects("plugin_ambiguous")

    def test_disabled_is_not_a_hidden_skill(self):
        self.entry["enabled"] = False
        self.rejects("plugin_not_installed_or_enabled")

    def test_version_change_requires_matching_manifest(self):
        self.entry["version"] = "v2"
        self.rejects("plugin_version_mismatch")
        self.manifest.write_text(json.dumps({"name": "presentations", "version": "v2", "skills": "./skills/"}))
        self.assertEqual(resolver.resolve(self.registry)["version"], "v2")

    def test_missing_dependency(self):
        (self.skill / resolver.REQUIRED[-1]).unlink()
        self.rejects("required_dependency_missing")

    def test_missing_linked_guidance(self):
        (self.skill / "design.md").unlink()
        self.rejects("required_dependency_missing:design.md")

    def test_ambiguous_skill(self):
        second = self.root / "skills/second"
        second.mkdir()
        (second / "SKILL.md").write_text("---\nname: Presentations\n---\n")
        self.rejects("skill_ambiguous")

    def test_manifest_escape(self):
        self.manifest.write_text(json.dumps({"name": "presentations", "version": "v1", "skills": "../cache"}))
        self.rejects("path_outside_package")

    def test_missing_code_quoted_reference(self):
        with (self.skill / "SKILL.md").open("a") as stream:
            stream.write("Read `references/new-required.md` before creating.\n")
        self.rejects("required_dependency_missing:references/new-required.md")

    def test_invalid_explicit_codex_home(self):
        with self.assertRaisesRegex(resolver.Unavailable, "invalid_codex_home"):
            resolver.find_codex({"CODEX_HOME": "relative/path"})

    def test_no_scan_when_registered_source_missing(self):
        self.entry["source"]["path"] = str(Path(self.temp.name) / "missing")
        self.rejects("plugin_manifest_missing")

    def test_cli_failure_and_invalid_json(self):
        for returncode, stdout, reason in [(2, "", "plugin_list_failed"), (0, "no JSON", "plugin_list_invalid_json")]:
            with self.subTest(reason=reason), patch.object(resolver.subprocess, "run", return_value=subprocess.CompletedProcess([], returncode, stdout, "private")):
                with self.assertRaisesRegex(resolver.Unavailable, reason):
                    resolver.load_registry(Path("codex.exe"))

    def test_invalid_registry_schema(self):
        self.registry = {"installed": {}}
        self.rejects("plugin_list_invalid_schema")

    def test_cli_timeout(self):
        with patch.object(resolver.subprocess, "run", side_effect=subprocess.TimeoutExpired("codex", 60)):
            with self.assertRaisesRegex(resolver.Unavailable, "plugin_list_failed"):
                resolver.load_registry(Path("codex.exe"))


if __name__ == "__main__":
    unittest.main()
