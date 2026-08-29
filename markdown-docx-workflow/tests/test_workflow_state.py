from __future__ import annotations

import hashlib
import sys
import unittest


sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1] / "scripts"))

from workflow_state import (  # noqa: E402
    CONFIRM_CONTENT,
    ITEMS,
    LAYERS,
    WorkflowError,
    accept_docx,
    confirm_word,
    freeze_content,
    invalidate_if_changed,
    new_state,
    record_docx_generated,
    release_pdf,
)


def h(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def report(state: dict, *, item_result: str = "PASS", layer_status: str = "PASS", warning: bool = False) -> dict:
    item_layers = {
        "fonts_and_fallback": "STATIC_PASS",
        "paragraph_formatting": "STATIC_PASS",
        "table_formatting": "STATIC_PASS",
        "header_footer_geometry": "LO_RENDER_PASS",
        "pagination": "LO_RENDER_PASS",
        "word_native_open": "NATIVE_OPEN_PASS",
        "word_native_render": "NATIVE_RENDER_PASS",
    }
    items = [
        {
            "id": item_id,
            "owner_layer": owner,
            "result": "WARN" if warning and item_id == "pagination" else item_result,
            "severity": "warning" if warning and item_id == "pagination" else "hard_block",
            "baseline": "approved baseline",
            "comparison": "compare against baseline",
            "evidence_path": "evidence/item.json",
        }
        for item_id, owner in item_layers.items()
    ]
    return {
        "report_version": "1",
        "artifact_id": state["artifact_id"],
        "revision": state["revision"],
        "word_path": state["docx"]["word_path"],
        "word_sha256": state["docx"]["word_sha256"],
        "layers": [{"id": layer, "status": layer_status, "evidence_path": "evidence/layer.json"} for layer in LAYERS],
        "items": items,
        "overall_verdict": "PASS_WITH_WARNINGS" if warning else "PASS",
        "warnings": ["pagination warning"] if warning else [],
    }


class WorkflowStateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.source = b"# report\n\nbody\n"
        self.state = new_state(
            artifact_id="demo-doc",
            revision=1,
            source_markdown="manuscript/main.md",
            source_sha256=h(self.source),
            now="2026-08-29T00:00:00Z",
        )

    def freeze_and_generate(self) -> None:
        freeze_content(self.state, source_bytes=self.source, actor="user:test-user", user_response=CONFIRM_CONTENT, now="2026-08-29T01:00:00Z")
        record_docx_generated(
            self.state,
            manifest_path="deliverables/manifests/demo-doc.r1.manifest.json",
            template_path="templates/default.docx",
            template_sha256="a" * 64,
            word_path="deliverables/word/demo-doc.r1.docx",
            word_sha256="b" * 64,
            now="2026-08-29T02:00:00Z",
        )

    def test_unconfirmed_word_export_is_blocked(self) -> None:
        with self.assertRaises(WorkflowError) as raised:
            record_docx_generated(
                self.state,
                manifest_path="m.json",
                template_path="t.docx",
                template_sha256="a" * 64,
                word_path="w.docx",
                word_sha256="b" * 64,
            )
        self.assertEqual(raised.exception.code, "INVALID_TRANSITION")
        self.assertEqual(self.state["state"], "DRAFT")

    def test_markdown_mutation_invalidates_all_downstream_states(self) -> None:
        self.freeze_and_generate()
        accept_docx(self.state, report_path="evidence/report.json", report_sha256="c" * 64, report=report(self.state))
        confirm_word(self.state, actor="user:test-user", user_response="确认这个 Word")
        invalidate_if_changed(self.state, source_sha256=h(b"changed"), now="2026-08-29T03:00:00Z")
        self.assertEqual(self.state["state"], "DRAFT")
        self.assertIsNone(self.state["content_confirmation"])
        self.assertIsNone(self.state["docx"])
        self.assertEqual(self.state["invalidation"]["reason"], "source_markdown_changed")

    def test_invalid_invalidation_fingerprint_is_rejected_without_mutation(self) -> None:
        self.freeze_and_generate()
        before = self.state.copy()
        with self.assertRaises(WorkflowError) as raised:
            invalidate_if_changed(self.state, source_sha256="not-a-sha")
        self.assertEqual(raised.exception.code, "WORKFLOW_SCHEMA_INVALID")
        self.assertEqual(self.state, before)

    def test_report_word_fingerprint_mismatch_is_blocked_without_transition(self) -> None:
        self.freeze_and_generate()
        bad = report(self.state)
        bad["word_sha256"] = "d" * 64
        with self.assertRaises(WorkflowError) as raised:
            accept_docx(self.state, report_path="evidence/report.json", report_sha256="c" * 64, report=bad)
        self.assertEqual(raised.exception.code, "SOURCE_MUTATED")
        self.assertEqual(self.state["state"], "DOCX_GENERATED")

    def test_report_item_schema_is_checked_before_transition(self) -> None:
        self.freeze_and_generate()
        bad = report(self.state)
        del next(item for item in bad["items"] if item["id"] == "table_formatting")["comparison"]
        with self.assertRaises(WorkflowError) as raised:
            accept_docx(self.state, report_path="evidence/report.json", report_sha256="c" * 64, report=bad)
        self.assertEqual(raised.exception.code, "DOCX_ACCEPTANCE_UNVERIFIED")
        self.assertEqual(self.state["state"], "DOCX_GENERATED")

    def test_each_layer_failure_or_unavailable_blocks_acceptance(self) -> None:
        for status in ("FAIL", "UNVERIFIED", "ENV_UNVERIFIED", "NOT_RUN"):
            with self.subTest(status=status):
                self.freeze_and_generate()
                for layer in LAYERS:
                    bad = report(self.state, layer_status="PASS")
                    next(entry for entry in bad["layers"] if entry["id"] == layer)["status"] = status
                    with self.assertRaises(WorkflowError):
                        accept_docx(self.state, report_path="evidence/report.json", report_sha256="c" * 64, report=bad)
                    self.assertEqual(self.state["state"], "DOCX_GENERATED")
                self.state = new_state(artifact_id="demo-doc", revision=1, source_markdown="manuscript/main.md", source_sha256=h(self.source))

    def test_each_authoritative_item_is_hard_blocked_when_failed(self) -> None:
        for item_id in ITEMS:
            with self.subTest(item_id=item_id):
                self.freeze_and_generate()
                bad = report(self.state)
                next(item for item in bad["items"] if item["id"] == item_id)["result"] = "FAIL"
                with self.assertRaises(WorkflowError) as raised:
                    accept_docx(self.state, report_path="evidence/report.json", report_sha256="c" * 64, report=bad)
                self.assertEqual(raised.exception.code, "DOCX_ACCEPTANCE_UNVERIFIED")
                self.state = new_state(artifact_id="demo-doc", revision=1, source_markdown="manuscript/main.md", source_sha256=h(self.source))

    def test_warning_is_retained_and_requires_acknowledgement(self) -> None:
        self.freeze_and_generate()
        accept_docx(self.state, report_path="evidence/report.json", report_sha256="c" * 64, report=report(self.state, warning=True))
        with self.assertRaises(WorkflowError) as raised:
            confirm_word(self.state, actor="user:test-user", user_response="Word 没问题，可以提交")
        self.assertEqual(raised.exception.code, "WARNING_ACK_REQUIRED")
        confirm_word(self.state, actor="user:test-user", user_response="Word 没问题，可以提交", warnings_acknowledged=True)
        self.assertEqual(self.state["state"], "WORD_CONFIRMED")

    def test_word_change_invalidates_confirmation(self) -> None:
        self.freeze_and_generate()
        accept_docx(self.state, report_path="evidence/report.json", report_sha256="c" * 64, report=report(self.state))
        confirm_word(self.state, actor="user:test-user", user_response="Word 可以作为最终版本")
        invalidate_if_changed(self.state, word_sha256="d" * 64)
        self.assertEqual(self.state["state"], "CONTENT_FROZEN")
        self.assertIsNone(self.state["word_confirmation"])

    def test_pdf_release_requires_the_confirmed_word_fingerprint(self) -> None:
        self.freeze_and_generate()
        accept_docx(self.state, report_path="evidence/report.json", report_sha256="c" * 64, report=report(self.state))
        confirm_word(self.state, actor="user:test-user", user_response="确认这个 Word")
        with self.assertRaises(WorkflowError) as raised:
            release_pdf(self.state, pdf_path="deliverables/pdf/demo.pdf", pdf_sha256="e" * 64, word_path="w.docx", word_sha256="d" * 64)
        self.assertEqual(raised.exception.code, "SOURCE_MUTATED")
        self.assertEqual(self.state["state"], "WORD_CONFIRMED")
        release_pdf(self.state, pdf_path="deliverables/pdf/demo.pdf", pdf_sha256="e" * 64, word_path=self.state["word_confirmation"]["word_path"], word_sha256=self.state["word_confirmation"]["word_sha256"])
        self.assertEqual(self.state["state"], "PDF_RELEASED")


if __name__ == "__main__":
    unittest.main()
