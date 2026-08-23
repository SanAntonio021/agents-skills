from __future__ import annotations

import hashlib
import os
import sys
import tempfile
import unittest
import zipfile
from datetime import datetime, timezone
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = SKILL_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_ROOT))

from markdown_docx_delivery import (  # noqa: E402
    ContractError,
    acceptance_from_gate,
    check_output_collision,
    cleanup_failure_evidence,
    confirm_content,
    select_primary_failure,
    sha256_bytes,
    submit_manual_review,
    validate_docx_package,
    validate_export_readiness,
    validate_manifest,
    validate_manual_checklist,
    validate_baseline_manifest,
    validate_word_permission_record,
    write_json_atomic,
)


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class MarkdownDocxDeliveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.source = self.root / "manuscript" / "main.md"
        self.source.parent.mkdir(parents=True)
        self.source.write_bytes("# Frozen heading\n\nBody.\n".encode("utf-8"))
        self.manifest_path = self.root / "deliverables" / "manifests" / "demo-doc.r1.manifest.json"
        self.manifest_path.parent.mkdir(parents=True)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def manifest(self, **overrides):
        value = {
            "contract_version": "1",
            "artifact_id": "demo-doc",
            "template_id": "plain-template",
            "source_markdown": "manuscript/main.md",
            "source_sha256": hashlib.sha256(self.source.read_bytes()).hexdigest(),
            "content_status": "draft",
            "content_open_items": [],
            "content_confirmed": False,
            "content_owner": "user:test-user",
            "confirmed_at": None,
            "revision": 1,
            "format_source": "none",
            "template_path": None,
            "template_sha256": "none",
            "output_docx": "deliverables/word/demo-doc.r1.docx",
            "output_sha256": None,
            "toolchain_versions": {
                "pandoc": None,
                "officecli": None,
                "libreoffice-runner": None,
                "libreoffice": None,
                "word": None,
                "poppler": None,
                "mcp": None,
            },
            "acceptance": {
                "STATIC_PASS": "NOT_RUN",
                "LO_RENDER_PASS": "NOT_RUN",
                "NATIVE_OPEN_PASS": "NOT_RUN",
                "NATIVE_RENDER_PASS": "NOT_RUN",
            },
            "evidence_paths": {},
            "source_unchanged": True,
            "failure_code": None,
            "failure_detail": None,
        }
        value.update(overrides)
        write_json_atomic(self.manifest_path, value)
        return value

    def test_draft_is_blocked_but_explicit_preview_is_separate(self) -> None:
        self.manifest()
        context = validate_manifest(self.manifest_path, project_root=self.root)
        with self.assertRaises(ContractError) as raised:
            validate_export_readiness(context["manifest"])
        self.assertEqual(raised.exception.code, "CONTENT_NOT_FROZEN")
        preview = validate_export_readiness(context["manifest"], preview=True)
        self.assertEqual(preview["mode"], "preview")
        self.assertFalse(preview["delivered"])

    def test_open_items_and_confirmation_are_independent_blockers(self) -> None:
        self.manifest(content_status="frozen", content_open_items=["figure"], content_confirmed=False)
        context = validate_manifest(self.manifest_path, project_root=self.root)
        with self.assertRaises(ContractError) as raised:
            validate_export_readiness(context["manifest"])
        self.assertEqual(raised.exception.code, "CONTENT_OPEN_ITEMS")

        self.manifest(content_status="frozen", content_open_items=[], content_confirmed=False)
        context = validate_manifest(self.manifest_path, project_root=self.root)
        with self.assertRaises(ContractError) as raised:
            validate_export_readiness(context["manifest"])
        self.assertEqual(raised.exception.code, "CONTENT_NOT_CONFIRMED")

    def test_exact_content_confirmation_is_recorded_for_one_revision(self) -> None:
        self.manifest(content_status="frozen")
        with self.assertRaises(ContractError) as raised:
            confirm_content(
                self.manifest_path,
                project_root=self.root,
                actor="user:test-user",
                user_response="确认一下",
            )
        self.assertEqual(raised.exception.code, "CONTENT_NOT_CONFIRMED")

        result = confirm_content(
            self.manifest_path,
            project_root=self.root,
            actor="user:test-user",
            user_response="确认内容并导出 Word",
        )
        self.assertTrue(Path(result["confirmation"]).is_file())
        context = validate_manifest(self.manifest_path, project_root=self.root)
        self.assertTrue(context["manifest"]["content_confirmed"])
        self.assertIn("confirmation", context["manifest"]["evidence_paths"])

    def test_source_hash_and_encoding_drift_fail_closed(self) -> None:
        self.manifest()
        self.source.write_bytes(b"# changed\n")
        with self.assertRaises(ContractError) as raised:
            validate_manifest(self.manifest_path, project_root=self.root)
        self.assertEqual(raised.exception.code, "SOURCE_HASH_MISMATCH")

        self.source.write_bytes(b"\xef\xbb\xbf# bom\r\n")
        manifest = self.manifest(source_sha256=sha256_bytes(self.source.read_bytes()))
        del manifest  # the manifest helper rewrites the source hash for the fixture
        with self.assertRaises(ContractError) as raised:
            validate_manifest(self.manifest_path, project_root=self.root)
        self.assertEqual(raised.exception.code, "SOURCE_ENCODING_INVALID")

    def test_unknown_fields_and_unsafe_paths_are_rejected(self) -> None:
        self.manifest(extra="reject")
        with self.assertRaises(ContractError):
            validate_manifest(self.manifest_path, project_root=self.root)

        self.manifest(source_markdown="../outside.md")
        with self.assertRaises(ContractError):
            validate_manifest(self.manifest_path, project_root=self.root)

    def test_missing_template_is_distinct_from_hash_drift(self) -> None:
        self.manifest(
            format_source="template",
            template_path="templates/reference.docx",
            template_sha256="0" * 64,
        )
        with self.assertRaises(ContractError) as raised:
            validate_manifest(self.manifest_path, project_root=self.root)
        self.assertEqual(raised.exception.code, "MISSING_TEMPLATE")

    def test_existing_output_is_never_overwritten(self) -> None:
        manifest = self.manifest()
        output = self.root / manifest["output_docx"]
        output.parent.mkdir(parents=True)
        output.write_bytes(b"DO NOT OVERWRITE")
        with self.assertRaises(ContractError) as raised:
            check_output_collision(manifest, project_root=self.root)
        self.assertEqual(raised.exception.code, "OUTPUT_COLLISION")
        self.assertEqual(output.read_bytes(), b"DO NOT OVERWRITE")

        manifest["output_sha256"] = hashlib.sha256(output.read_bytes()).hexdigest()
        result = check_output_collision(manifest, project_root=self.root)
        self.assertTrue(result["reused"])

    def test_static_package_validator_rejects_damage(self) -> None:
        valid = self.root / "valid.docx"
        with zipfile.ZipFile(valid, "w") as package:
            package.writestr("[Content_Types].xml", "<Types/>")
            package.writestr("word/document.xml", "<document/>")
            package.writestr("word/styles.xml", "<styles/>")
        self.assertEqual(validate_docx_package(valid)["status"], "PASS")

        damaged = self.root / "damaged.docx"
        damaged.write_bytes(b"not a zip")
        with self.assertRaises(ContractError) as raised:
            validate_docx_package(damaged)
        self.assertEqual(raised.exception.code, "STATIC_VALIDATION_FAILED")

    def test_acceptance_and_failure_mapping_are_explicit(self) -> None:
        self.assertEqual(acceptance_from_gate("LO_RENDER_PASS", {"status": "PASS"}), "PASS")
        self.assertEqual(acceptance_from_gate("NATIVE_OPEN_PASS", {"status": "APP_UNAVAILABLE"}), "UNVERIFIED")
        self.assertEqual(acceptance_from_gate("STATIC_PASS", {"status": "FAIL_OPEN"}), "FAIL")
        self.assertEqual(
            select_primary_failure(["NATIVE_RENDER_FAILED", "STATIC_VALIDATION_FAILED"]),
            "STATIC_VALIDATION_FAILED",
        )

    def test_word_permission_and_baseline_are_bound_to_current_identity(self) -> None:
        validate_word_permission_record(
            {
                "run_id": "run-1",
                "artifact_id": "demo-doc",
                "actor": "user:test-user",
                "user_response": "允许本次 Word 验收",
                "granted_at": _now(),
                "scope": "task_run",
            },
            run_id="run-1",
            artifact_id="demo-doc",
        )
        with self.assertRaises(ContractError) as raised:
            validate_word_permission_record(
                {
                    "run_id": "run-1",
                    "artifact_id": "demo-doc",
                    "actor": "user:test-user",
                    "user_response": "允许以后都验收",
                    "granted_at": _now(),
                    "scope": "task_run",
                },
                run_id="run-1",
                artifact_id="demo-doc",
            )
        self.assertEqual(raised.exception.code, "PERMISSION_DENIED")

        validate_baseline_manifest(
            {
                "baseline_version": "1",
                "template_id": "plain-template",
                "template_sha256": "a" * 64,
                "word_major_version": "16",
                "poppler_version": "24.08.0",
                "raster_command": ["pdftoppm", "-r", "150", "-png", "-aa", "yes", "-aaVector", "yes"],
                "page_count": 1,
                "pages_sha256": ["b" * 64],
                "baseline_approver": "user:test-user",
                "approved_at": _now(),
                "status": "approved",
            },
            template_id="plain-template",
            template_sha256="a" * 64,
            word_major_version="16",
        )

    def test_manual_checklist_requires_every_page_and_every_boolean(self) -> None:
        checklist = {
            "checklist_version": "1",
            "artifact_id": "demo-doc",
            "revision": 1,
            "reviewer_id": "user:test-user",
            "reviewed_at": _now(),
            "pages": [
                {
                    "page_num": 1,
                    "no_cropping": True,
                    "no_overlap": True,
                    "no_missing_chars": True,
                    "no_formula_table_breaks": True,
                    "no_pagination_anomalies": True,
                    "notes": "",
                    "evidence_screenshot": None,
                }
            ],
            "overall_pass": True,
        }
        validate_manual_checklist(checklist, page_count=1)
        checklist["pages"][0]["no_overlap"] = False
        with self.assertRaises(ContractError) as raised:
            validate_manual_checklist(checklist, page_count=1)
        self.assertEqual(raised.exception.code, "UNVERIFIED_GATE")

    def test_manual_review_submit_updates_same_run_and_native_render(self) -> None:
        state_path = self.root / "deliverables" / "state" / "demo-doc.r1.run.json"
        state_path.parent.mkdir(parents=True)
        state = {
            "schema_version": "1",
            "run_id": "docx-gate_20260823T040000Z_ab12cd34",
            "artifact_id": "demo-doc",
            "revision": 1,
            "status": "awaiting_manual_review",
            "created_at": _now(),
            "updated_at": _now(),
            "expires_at": "2099-08-24T04:00:00Z",
            "manifest_path": "deliverables/manifests/demo-doc.r1.manifest.json",
            "page_count": 1,
            "native_render_pdf": "evidence/native-render/native.pdf",
            "native_render_pages": "evidence/native-render",
            "lock_path": "deliverables/state/demo-doc.r1.run.lock",
        }
        write_json_atomic(state_path, state)
        checklist_path = self.root / "evidence" / "manual-inspection" / "demo-doc.r1.checklist.json"
        checklist_path.parent.mkdir(parents=True)
        write_json_atomic(
            checklist_path,
            {
                "checklist_version": "1",
                "artifact_id": "demo-doc",
                "revision": 1,
                "reviewer_id": "user:test-user",
                "reviewed_at": _now(),
                "pages": [
                    {
                        "page_num": 1,
                        "no_cropping": True,
                        "no_overlap": True,
                        "no_missing_chars": True,
                        "no_formula_table_breaks": True,
                        "no_pagination_anomalies": True,
                        "notes": "",
                        "evidence_screenshot": None,
                    }
                ],
                "overall_pass": True,
            },
        )
        manifest = self.manifest(
            content_status="frozen",
            content_confirmed=True,
            confirmed_at=_now(),
            evidence_paths={"manual_review_state": "deliverables/state/demo-doc.r1.run.json"},
        )
        result = submit_manual_review(self.manifest_path, checklist_path, project_root=self.root)
        self.assertEqual(result["status"], "manual_review_passed")
        updated = validate_manifest(self.manifest_path, project_root=self.root)["manifest"]
        self.assertEqual(updated["acceptance"]["NATIVE_RENDER_PASS"], "PASS")

    def test_cleanup_only_removes_old_unlocked_runs(self) -> None:
        root = self.root / "gates"
        old = root / "docx-gate_old"
        recent = root / "docx-gate_recent"
        locked = root / "docx-gate_locked"
        for path in (old, recent, locked):
            path.mkdir(parents=True)
            (path / "failure.json").write_text("{}", encoding="utf-8")
        (locked / ".lock").write_text("active", encoding="utf-8")
        cutoff = datetime.now(timezone.utc).timestamp() - 8 * 86400
        os.utime(old, (cutoff, cutoff))
        result = cleanup_failure_evidence(root, now=datetime.now(timezone.utc), retention_days=7)
        self.assertIn(str(old), result["removed"])
        self.assertFalse(old.exists())
        self.assertTrue(recent.exists())
        self.assertTrue(locked.exists())


if __name__ == "__main__":
    unittest.main()
