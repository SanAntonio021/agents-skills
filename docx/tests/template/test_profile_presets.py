from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch


SKILL_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = SKILL_ROOT / "scripts" / "template"
sys.path.insert(0, str(SCRIPTS_DIR))

import install_normal_template as installer
import word_template_formatter as formatter


class ProfilePresetTests(unittest.TestCase):
    def test_all_ten_profiles_are_registered_and_parseable(self):
        profiles = set((SKILL_ROOT / "assets" / "template").glob("*.style-profile.json"))
        self.assertEqual(len(formatter.PRESET_PATHS), 10)
        self.assertEqual(profiles, {p["profile"] for p in formatter.PRESET_PATHS.values()})
        for name, paths in formatter.PRESET_PATHS.items():
            with self.subTest(preset=name):
                with tempfile.TemporaryDirectory() as directory:
                    input_path = Path(directory) / "input.docx"
                    input_path.touch()
                    args = formatter.build_parser().parse_args(
                        ["apply", "--input", str(input_path), "--preset", name]
                    )
                self.assertEqual(args.preset, name)
                if name not in {"tongyong-moren", "jishu-zongjie", "gongzuo-zongjie", "qiye-shenbao"}:
                    self.assertEqual(paths["profile"].name, f"{name}.style-profile.json")
        for alias, canonical in formatter.PRESET_ALIASES.items():
            self.assertEqual(formatter.preset_arg(alias), canonical)

    def test_bundled_fonts_are_explicit_black(self):
        for paths in formatter.PRESET_PATHS.values():
            profile = formatter.load_profile(paths["profile"])
            for entry in profile["styles"]:
                if "font" in entry:
                    with self.subTest(profile=paths["profile"].name, style=entry["name"]):
                        self.assertEqual(entry["font"]["color_value"], 0)
                        self.assertEqual(entry["font"]["color_hex"], "#000000")

    def test_profile_color_is_applied_without_forcing_black(self):
        for color, hex_color in [(0, "#000000"), (0x563412, "#123456"), (-16777216, None)]:
            with self.subTest(color=color):
                style = SimpleNamespace(Font=SimpleNamespace(Color=999))
                with patch.object(formatter, "ensure_profile_style", return_value=style):
                    formatter.apply_profile_style(None, {
                        "name": "Colored", "type": "character",
                        "font": {"color_value": color, "color_hex": hex_color},
                    })
                self.assertEqual(style.Font.Color, color)

    def test_absent_color_preserves_existing_font(self):
        style = SimpleNamespace(Font=SimpleNamespace(Color=123))
        with patch.object(formatter, "ensure_profile_style", return_value=style):
            formatter.apply_profile_style(None, {"name": "Existing", "font": {}})
        self.assertEqual(style.Font.Color, 123)

    def test_color_failure_or_silent_rejection_raises(self):
        class RejectingFont:
            @property
            def Color(self):
                return 999

            @Color.setter
            def Color(self, value):
                raise OSError("color write rejected")

        class IgnoringFont(RejectingFont):
            @RejectingFont.Color.setter
            def Color(self, value):
                pass

        entry = {"name": "Colored", "font": {"color_value": 0}}
        for font in (RejectingFont(), IgnoringFont()):
            with self.subTest(font=type(font).__name__):
                with patch.object(formatter, "ensure_profile_style",
                                  return_value=SimpleNamespace(Font=font)):
                    with self.assertRaisesRegex(RuntimeError, "Failed to apply font color.*Colored"):
                        formatter.apply_profile_style(None, entry)
        with patch.object(formatter, "ensure_profile_style", return_value=None):
            with self.assertRaisesRegex(RuntimeError, "Cannot apply font color"):
                formatter.apply_profile_style(None, entry)

    def test_profile_only_apply_materializes_with_profile_stem(self):
        with tempfile.TemporaryDirectory() as directory:
            input_path = Path(directory) / "input.docx"
            input_path.touch()
            profile_path = formatter.PRESET_PATHS["funding-usage-report"]["profile"]
            args = formatter.build_parser().parse_args([
                "apply", "--input", str(input_path), "--profile", str(profile_path),
                "--allow-template-style-import",
            ])
            self.assertIsNone(args.preset)
            target = MagicMock()
            # Stop immediately after materialization is requested; never start Word.
            with patch.object(formatter, "word_application") as word, \
                 patch.object(formatter, "open_document", return_value=target), \
                 patch.object(formatter, "materialize_template_from_profile",
                              side_effect=RuntimeError("materialization reached")) as materialize:
                with self.assertRaisesRegex(RuntimeError, "materialization reached"):
                    formatter.apply_command(args)
                materialize.assert_called_once_with(
                    word.return_value.__enter__.return_value,
                    formatter.load_profile(profile_path), profile_path.stem,
                )
                target.Close.assert_called_once_with(False)

    def test_installer_default_is_independent_of_export_default(self):
        self.assertIsNone(formatter.DEFAULT_PRESET)
        self.assertEqual(installer.build_parser().parse_args([]).template,
                         formatter.PRESET_PATHS["qiye-shenbao"]["template"])
        self.assertEqual(installer.build_parser().parse_args(["--template", "custom.docx"]).template,
                         Path("custom.docx"))
        with self.assertRaisesRegex(SystemExit, "No formatting source selected"):
            formatter.resolve_template_path(None, None)

    def test_powershell_preset_resolver_matches_python(self):
        shell = shutil.which("pwsh") or shutil.which("powershell")
        if not shell:
            self.skipTest("PowerShell unavailable")
        script_path = str(SCRIPTS_DIR / "export_markdown_to_word.ps1").replace("'", "''")
        # Evaluate only the resolver function, never the wrapper's Word operations.
        command = """
$tokens = $null; $errors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile('__PATH__', [ref]$tokens, [ref]$errors)
if ($errors.Count) { throw ($errors | Out-String) }
$function = $ast.Find({param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Resolve-PresetName'}, $true)
Invoke-Expression $function.Extent.Text
$names = '__NAMES__'.Split(',')
@($names | ForEach-Object { Resolve-PresetName $_ }) | ConvertTo-Json -Compress
try { Resolve-PresetName 'unknown-preset'; exit 2 } catch { }
exit 0
""".replace("__PATH__", script_path).replace(
            "__NAMES__", ",".join([*formatter.PRESET_PATHS, *formatter.PRESET_ALIASES])
        )
        result = subprocess.run([shell, "-NoProfile", "-NonInteractive", "-Command", command],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout),
                         [*formatter.PRESET_PATHS, *formatter.PRESET_ALIASES.values()])


if __name__ == "__main__":
    unittest.main()
