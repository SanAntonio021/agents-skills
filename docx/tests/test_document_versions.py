from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import document_versions as versions  # noqa: E402


CHECKER = """import json
import pathlib
import sys

counter = pathlib.Path(sys.argv[1])
counter.write_bytes(counter.read_bytes() + b'.' if counter.exists() else b'.')
result = json.loads(sys.argv[2])
if len(sys.argv) > 3:
    pathlib.Path(sys.argv[3]).write_bytes(sys.argv[4].encode('utf-8'))
print(json.dumps(result))
"""


class DocumentVersionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.document = self.root / "draft.docx"
        self.document.write_bytes(b"original Word content")
        self.source = self.root / "draft.txt"
        self.source.write_text("source content", encoding="utf-8")
        self.template = self.root / "layout.docx"
        self.template.write_bytes(b"template content")
        self.image = self.root / "figure.png"
        self.image.write_bytes(b"image content")
        self.record = self.root / "draft.check.json"
        self.checker = self.root / "checker.py"
        self.checker.write_text(CHECKER, encoding="utf-8")
        self.counter = self.root / "counter.txt"
        self.inputs = versions.capture_inputs(
            [self.source], template=self.template, images=[self.image]
        )

    def calls(self) -> int:
        return len(self.counter.read_bytes()) if self.counter.exists() else 0

    def command(self, result=None, mutate: Path | None = None) -> list[str]:
        if result is None:
            result = {"ok": True, "status": "PASS", "source": str(self.document)}
        command = [sys.executable, "-X", "utf8", str(self.checker), str(self.counter), json.dumps(result)]
        if mutate is not None:
            command += [str(mutate), "changed during check"]
        return command

    def generate(self) -> dict:
        return versions.record_generation(self.document, self.record, self.inputs)

    def check(self, command=None, **kwargs) -> dict:
        return versions.run_check(
            self.document, self.record, command or self.command(),
            kind=kwargs.pop("kind", "package-check"), **kwargs,
        )

    def test_generation_record_is_not_a_pass(self) -> None:
        result = self.generate()
        self.assertFalse(result["ok"])
        self.assertFalse(versions.assess(result, self.document)["reusable"])
        self.assertEqual(self.calls(), 0)

    def test_successful_check_is_reused_without_running_checker_again(self) -> None:
        self.generate()
        first = self.check()
        second = self.check()
        self.assertTrue(first["ok"])
        self.assertFalse(first["reused"])
        self.assertTrue(second["ok"])
        self.assertTrue(second["reused"])
        self.assertEqual(self.calls(), 1)

    def test_each_changed_input_invalidates_pass_without_replacing_word(self) -> None:
        for changed in (self.source, self.template, self.image):
            with self.subTest(input=changed.name):
                self.inputs = versions.capture_inputs(
                    [self.source], template=self.template, images=[self.image]
                )
                self.generate()
                self.assertTrue(self.check()["ok"])
                before_calls = self.calls()
                before_word = self.document.read_bytes()
                changed.write_bytes(changed.read_bytes() + b" changed")
                self.assertFalse(versions.assess(versions.read_record(self.record), self.document)["reusable"])
                result = self.check()
                self.assertFalse(result["ok"])
                self.assertEqual(result["status"], "INPUTS_CHANGED")
                self.assertEqual(self.calls(), before_calls)
                self.assertEqual(self.document.read_bytes(), before_word)

    def test_optional_template_profile_appearance_invalidates_pass(self) -> None:
        self.generate()
        self.assertTrue(self.check()["ok"])
        self.template.with_suffix(".style-profile.json").write_text("{}", encoding="utf-8")
        result = self.check()
        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "INPUTS_CHANGED")
        self.assertEqual(self.calls(), 1)

    def test_manual_word_edit_is_rechecked_and_preserved(self) -> None:
        self.generate()
        self.check()
        edited = b"user manually edited Word content"
        self.document.write_bytes(edited)
        result = self.check()
        self.assertTrue(result["ok"])
        self.assertFalse(result["reused"])
        self.assertEqual(self.calls(), 2)
        self.assertEqual(self.document.read_bytes(), edited)
        self.assertTrue(self.check()["reused"])
        self.assertEqual(self.calls(), 2)

    def test_input_and_word_changes_require_reconciliation_without_overwrite(self) -> None:
        self.generate()
        self.check()
        self.source.write_bytes(b"updated manuscript")
        self.document.write_bytes(b"user edits")
        result = self.check()
        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "INPUTS_CHANGED")
        self.assertTrue(result["version_check"]["word_changed_since_generation"])
        self.assertEqual(self.document.read_bytes(), b"user edits")
        self.assertEqual(self.calls(), 1)

    def test_files_changed_during_check_cannot_pass(self) -> None:
        for changed in (self.source, self.template, self.image, self.document):
            with self.subTest(input=changed.name):
                self.inputs = versions.capture_inputs(
                    [self.source], template=self.template, images=[self.image]
                )
                self.generate()
                changed.write_bytes(changed.read_bytes() + b" before run")
                if changed != self.document:
                    self.inputs = versions.capture_inputs(
                        [self.source], template=self.template, images=[self.image]
                    )
                    self.generate()
                result = self.check(self.command(mutate=changed))
                self.assertFalse(result["ok"])
                self.assertEqual(result["status"], "FILES_CHANGED_DURING_CHECK")
                self.assertFalse(result["version_check"]["reusable"])

    def test_checker_arguments_change_forces_new_check(self) -> None:
        self.generate()
        self.check()
        result = self.check(self.command({"ok": True, "status": "PASS", "scope": "full"}))
        self.assertTrue(result["ok"])
        self.assertFalse(result["reused"])
        self.assertEqual(self.calls(), 2)

    def test_checker_script_change_invalidates_even_readonly_assessment(self) -> None:
        self.generate()
        self.check()
        self.checker.write_text(CHECKER + "\n# new checker revision\n", encoding="utf-8")
        self.assertFalse(versions.assess(versions.read_record(self.record), self.document)["reusable"])
        result = self.check()
        self.assertTrue(result["ok"])
        self.assertFalse(result["reused"])
        self.assertEqual(self.calls(), 2)

    def test_check_kind_change_forces_new_check(self) -> None:
        self.generate()
        self.check()
        result = self.check(kind="layout-check")
        self.assertTrue(result["ok"])
        self.assertFalse(result["reused"])
        self.assertEqual(self.calls(), 2)

    def test_missing_record_checks_current_document(self) -> None:
        before = self.document.read_bytes()
        result = self.check(inputs=self.inputs)
        self.assertTrue(result["ok"])
        self.assertFalse(result["reused"])
        self.assertEqual(self.document.read_bytes(), before)
        self.assertTrue(self.check()["reused"])
        self.assertEqual(self.calls(), 1)

    def test_bad_records_are_rechecked(self) -> None:
        for content in ("not JSON", "[]", '{"ok":true}', '{"document_versions":{"schema_version":999}}'):
            with self.subTest(content=content):
                self.record.write_text(content, encoding="utf-8")
                before_calls = self.calls()
                result = self.check(inputs=self.inputs)
                self.assertTrue(result["ok"])
                self.assertFalse(result["reused"])
                self.assertEqual(self.calls(), before_calls + 1)

    def test_zero_exit_does_not_override_unsuccessful_json(self) -> None:
        for payload in (
            {"ok": False, "status": "PASS"},
            {"ok": True, "status": "UNVERIFIED"},
            {"ok": True, "status": "PASS", "error": "cleanup failed"},
            {"ok": "true", "status": "PASS"},
            {"ok": True, "status": {"unexpected": "PASS"}},
        ):
            with self.subTest(payload=payload):
                self.generate()
                result = self.check(self.command(payload))
                self.assertFalse(result["ok"])
                self.assertFalse(versions.assess(versions.read_record(self.record), self.document)["reusable"])

    def test_nonzero_exit_does_not_override_successful_json(self) -> None:
        self.generate()
        self.checker.write_text(CHECKER + "\nsys.exit(7)\n", encoding="utf-8")
        result = self.check()
        self.assertFalse(result["ok"])
        self.assertEqual(result["check_exit_code"], 7)

    def test_explicit_refresh_runs_the_current_check_again(self) -> None:
        self.generate()
        self.check()
        result = self.check(refresh=True)
        self.assertTrue(result["ok"])
        self.assertFalse(result["reused"])
        self.assertEqual(self.calls(), 2)

    def test_failed_refresh_is_not_reused_later(self) -> None:
        self.generate()
        self.check()
        with patch.object(versions.subprocess, "run", side_effect=subprocess.TimeoutExpired(self.command(), 0.1)):
            result = self.check(refresh=True)
        self.assertFalse(result["ok"])
        self.assertFalse(versions.assess(versions.read_record(self.record), self.document)["reusable"])

    def test_office_checker_is_not_force_killed_by_wrapper_timeout(self) -> None:
        self.generate()
        for kind in ("word-native", "libreoffice-render"):
            with self.subTest(kind=kind):
                with self.assertRaisesRegex(ValueError, "manage their own timeout"):
                    self.check(kind=kind, timeout=1)
        self.assertEqual(self.calls(), 0)

    def test_office_entrypoint_cannot_bypass_timeout_guard_with_another_kind(self) -> None:
        command = [sys.executable, str(self.root / "office_native_gate.py"), "check", str(self.document)]
        with self.assertRaisesRegex(ValueError, "manage their own timeout"):
            self.check(command, kind="package-check", timeout=1)
        self.assertEqual(self.calls(), 0)

    def test_foreign_document_record_is_not_reused(self) -> None:
        self.generate()
        self.check()
        other = self.root / "other.docx"
        other.write_bytes(self.document.read_bytes())
        self.assertFalse(versions.assess(versions.read_record(self.record), other)["reusable"])
        result = versions.run_check(
            other, self.record, self.command({"ok": True, "source": str(other)}),
            kind="package-check", inputs=self.inputs,
        )
        self.assertTrue(result["ok"])
        self.assertFalse(result["reused"])
        self.assertEqual(self.calls(), 2)

    def test_mixed_generated_and_checked_document_bindings_are_rechecked(self) -> None:
        self.generate()
        self.check()
        other = self.root / "other.docx"
        other.write_bytes(b"another checked document")
        record = versions.read_record(self.record)
        record[versions.VERSION_KEY]["checked_document"] = versions.fingerprint(other, "document")
        self.record.write_text(json.dumps(record), encoding="utf-8")
        self.assertFalse(versions.assess(record, self.document)["reusable"])
        result = self.check(inputs=self.inputs)
        self.assertTrue(result["ok"])
        self.assertFalse(result["reused"])
        self.assertEqual(self.calls(), 2)

    def test_record_path_cannot_replace_word_or_inputs(self) -> None:
        for protected in (self.document, self.source, self.template, self.image):
            with self.subTest(path=protected.name):
                original = protected.read_bytes()
                with self.assertRaises(ValueError):
                    versions.record_generation(self.document, protected, self.inputs)
                with self.assertRaises(ValueError):
                    versions.run_check(self.document, protected, self.command(), kind="package-check", inputs=self.inputs)
                self.assertEqual(protected.read_bytes(), original)
                self.assertEqual(self.calls(), 0)

    def test_hardlinked_record_cannot_replace_input(self) -> None:
        try:
            os.link(self.source, self.record)
        except OSError as exc:
            self.skipTest(f"Hardlinks unavailable: {exc}")
        before = self.source.read_bytes()
        with self.assertRaises(ValueError):
            self.check(inputs=self.inputs)
        self.assertEqual(self.source.read_bytes(), before)
        self.assertEqual(self.calls(), 0)

    def test_checker_source_identity_must_match_target(self) -> None:
        for key in ("file", "source", "source_sha256", "source_sha256_before", "source_sha256_after"):
            with self.subTest(key=key):
                self.generate()
                value = str(self.root / "another.docx") if key in {"file", "source"} else "0" * 64
                result = self.check(self.command({"ok": True, "status": "PASS", key: value}))
                self.assertFalse(result["ok"])
                self.assertEqual(result["status"], "CHECK_SOURCE_MISMATCH")

    def test_native_uppercase_hash_is_accepted(self) -> None:
        self.generate()
        digest = hashlib.sha256(self.document.read_bytes()).hexdigest().upper()
        result = self.check(self.command({
            "ok": True, "status": "PASS", "source": str(self.document),
            "source_sha256_before": digest, "source_sha256_after": digest,
        }))
        self.assertTrue(result["ok"])

    def test_generation_input_changes_do_not_create_valid_record(self) -> None:
        self.source.write_bytes(b"changed while generating")
        with self.assertRaises(ValueError):
            self.generate()
        self.assertFalse(self.record.exists())

    def test_stale_explicit_inputs_cannot_be_recorded_as_current_check(self) -> None:
        self.source.write_bytes(b"changed after capture")
        result = self.check(inputs=self.inputs)
        self.assertFalse(result["ok"])
        self.assertFalse(result.get("version_check", {}).get("reusable", False))

    def test_render_artifact_change_invalidates_that_check(self) -> None:
        self.generate()
        rendered = self.root / "render.pdf"
        rendered.write_bytes(b"rendered pages")
        command = self.command({"ok": True, "source": str(self.document), "output": str(rendered)})
        self.assertTrue(self.check(command)["ok"])
        rendered.write_bytes(b"different pages")
        self.assertFalse(versions.assess(versions.read_record(self.record), self.document)["reusable"])

    def test_readonly_verify_does_not_modify_files_or_launch_checker(self) -> None:
        self.generate()
        self.check()
        record_before = self.record.read_bytes()
        document_before = self.document.read_bytes()
        completed = subprocess.run(
            [sys.executable, "-X", "utf8", str(SCRIPTS / "document_versions.py"),
             "verify", str(self.document), "--record", str(self.record)],
            capture_output=True, text=True, encoding="utf-8", timeout=30,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertTrue(json.loads(completed.stdout)["reusable"])
        self.assertEqual(self.calls(), 1)
        self.assertEqual(self.record.read_bytes(), record_before)
        self.assertEqual(self.document.read_bytes(), document_before)

    def test_transient_record_replacement_lock_is_retried(self) -> None:
        self.record.write_text('{"old":true}', encoding="utf-8")
        replace = versions.replace_record
        attempts = 0

        def locked_once(source, destination):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise PermissionError("temporary sharing lock")
            return replace(source, destination)

        with patch.object(versions, "replace_record", side_effect=locked_once), patch.object(versions.time, "sleep"):
            versions.save_record(self.record, {"new": True})
        self.assertEqual(2, attempts)
        self.assertEqual({"new": True}, versions.read_record(self.record))

    def test_persistent_record_lock_preserves_prior_result(self) -> None:
        original = b'{"prior":"inspection"}'
        self.record.write_bytes(original)
        with patch.object(versions, "replace_record", side_effect=PermissionError("locked")) as replace, patch.object(versions.time, "sleep"):
            with self.assertRaises(PermissionError):
                versions.save_record(self.record, {"new": True})
        self.assertEqual(4, replace.call_count)
        self.assertEqual(original, self.record.read_bytes())
        self.assertFalse(list(self.root.glob(".*.tmp")))

    def test_pandoc_reference_images_with_unicode_and_spaces(self) -> None:
        pandoc = shutil.which("pandoc")
        fallback = Path(os.environ.get("LOCALAPPDATA", "")) / "Pandoc" / "pandoc.exe"
        if pandoc is None and fallback.is_file():
            pandoc = str(fallback)
        if pandoc is None:
            self.skipTest("Pandoc is not installed")
        image = self.root / "\u4e2d\u6587 figure.png"
        image.write_bytes(b"image bytes")
        source = self.root / "\u4e3b\u7a3f sample.md"
        source.write_text(
            "![caption][figure]\n\n[figure]: <\u4e2d\u6587 figure.png>\n",
            encoding="utf-8",
        )
        captured = versions.capture_inputs([source], pandoc=pandoc)
        images = [item for item in captured["files"] if item["role"] == "image"]
        self.assertEqual([item["path"] for item in images], [str(image.resolve())])
        self.assertEqual(images[0]["sha256"], hashlib.sha256(image.read_bytes()).hexdigest())
        self.assertEqual(captured["untracked"], [])


if __name__ == "__main__":
    unittest.main()
