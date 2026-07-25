import importlib.util
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "validate_submission_records.py"
FIXTURE = ROOT / "tests" / "fixtures" / "synthetic-cases.json"

SPEC = importlib.util.spec_from_file_location("validate_submission_records", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def gate(action, status="required", **extra):
    value = {"action": action, "status": status}
    value.update(extra)
    return value


def make_state(schema_version="1.1", stage="preparation", review_status="not_run"):
    gates = [
        gate("author_roles"),
        gate("declarations"),
        gate("reviewers"),
        gate("final_submit"),
        gate("open_access_fees"),
        gate("copyright"),
        gate("withdrawal_transfer"),
    ]
    if schema_version == "1.1":
        review = gate("pre_submission_review", review_status)
        if review_status == "pass":
            review.update(
                checked_at="2026-07-26T15:30:00+08:00",
                evidence=[{"type": "paper_review_report", "path": "review.md"}],
            )
        gates.insert(0, review)
    return {
        "schema_version": schema_version,
        "journal": {"name": "Journal of Synthetic Results"},
        "manuscript": {"title": "Synthetic manuscript", "submission_id": "TEST-2026-0001"},
        "platform": {"name": "Synthetic Portal", "institution_match_status": "matched"},
        "lifecycle": {"current_stage": stage},
        "authors": [
            {"profile_id": "alice-researcher", "order": 1},
            {"profile_id": "bob-scholar", "order": 2},
        ],
        "files": [],
        "declarations": {},
        "official_sources": [],
        "confirmation_gates": gates,
        "operation_history": [],
        "next_action": {"action": "inspect current page"},
    }


def make_file(**overrides):
    value = {
        "path": "main.pdf",
        "submission_name": "main.pdf",
        "purpose": "main_manuscript",
        "size_bytes": 1024,
        "sha256": "A" * 64,
        "stage": "initial_submission",
        "upload_status": "pending",
    }
    value.update(overrides)
    return value


class ValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))

    def test_synthetic_author_library(self):
        errors, warnings, profile_ids = MODULE.validate_authors(self.fixture["authors"])
        self.assertEqual(errors, [])
        self.assertEqual(profile_ids, {"alice-researcher", "bob-scholar"})
        self.assertTrue(any("pending" in warning for warning in warnings))

    def test_every_lifecycle_stage_is_accepted(self):
        for stage in self.fixture["stages"]:
            with self.subTest(stage=stage):
                errors, _ = MODULE.validate_state(make_state(stage=stage))
                self.assertEqual(errors, [])

    def test_schema_1_0_is_compatible_and_warns(self):
        errors, warnings = MODULE.validate_state(make_state(schema_version="1.0"))
        self.assertEqual(errors, [])
        self.assertTrue(any("supported for compatibility" in item for item in warnings))

    def test_schema_1_1_requires_review_gate(self):
        state = make_state()
        state["confirmation_gates"] = state["confirmation_gates"][1:]
        errors, _ = MODULE.validate_state(state)
        self.assertTrue(any("pre_submission_review" in item for item in errors))

    def test_review_gate_allows_three_statuses(self):
        for status in ("not_run", "blocked", "pass"):
            with self.subTest(status=status):
                errors, _ = MODULE.validate_state(make_state(review_status=status))
                self.assertEqual(errors, [])

    def test_review_pass_requires_checked_at_and_evidence(self):
        for missing_key in ("checked_at", "evidence"):
            with self.subTest(missing_key=missing_key):
                state = make_state(review_status="pass")
                review = state["confirmation_gates"][0]
                review.pop(missing_key)
                errors, _ = MODULE.validate_state(state)
                self.assertTrue(any(missing_key in item for item in errors))

    def test_review_pass_rejects_empty_evidence_entries(self):
        state = make_state(review_status="pass")
        state["confirmation_gates"][0]["evidence"] = [None]
        errors, _ = MODULE.validate_state(state)
        self.assertTrue(any("locatable object" in item for item in errors))

    def test_review_pass_rejects_non_string_time_and_locator(self):
        state = make_state(review_status="pass")
        state["confirmation_gates"][0]["checked_at"] = 0
        state["confirmation_gates"][0]["evidence"] = [{"path": 0}]
        errors, _ = MODULE.validate_state(state)
        self.assertTrue(any("ISO date or datetime" in item for item in errors))
        self.assertTrue(any("locatable object" in item for item in errors))

    def test_review_gate_rejects_unknown_status(self):
        state = make_state()
        state["confirmation_gates"][0]["status"] = "required"
        errors, _ = MODULE.validate_state(state)
        self.assertTrue(any("must be one of" in item for item in errors))

    def test_duplicate_confirmation_gate_is_rejected(self):
        state = make_state()
        state["confirmation_gates"].append(gate("final_submit"))
        errors, _ = MODULE.validate_state(state)
        self.assertTrue(any("duplicate confirmation gate" in item for item in errors))

    def test_unknown_protected_gate_status_is_rejected(self):
        state = make_state()
        final_gate = next(
            item for item in state["confirmation_gates"] if item["action"] == "final_submit"
        )
        final_gate["status"] = "done"
        errors, _ = MODULE.validate_state(state)
        self.assertTrue(any("final_submit.status must be one of" in item for item in errors))

    def test_unknown_schema_version_is_rejected(self):
        errors, _ = MODULE.validate_state(make_state(schema_version="2.0"))
        self.assertTrue(any("unsupported" in item for item in errors))

    def test_final_submit_cannot_close_without_review_pass(self):
        state = make_state(review_status="blocked")
        next(item for item in state["confirmation_gates"] if item["action"] == "final_submit")[
            "status"
        ] = "completed"
        errors, _ = MODULE.validate_state(state)
        self.assertTrue(any("cannot be closed" in item for item in errors))

    def test_closed_gate_requires_user_confirmation_record(self):
        state = make_state(review_status="pass")
        final_gate = next(
            item for item in state["confirmation_gates"] if item["action"] == "final_submit"
        )
        final_gate["status"] = "completed"
        errors, _ = MODULE.validate_state(state)
        for field in ("question", "user_choice", "confirmed_at", "applies_to"):
            self.assertTrue(any(f"final_submit.{field}" in item for item in errors))

    def test_closed_gate_with_user_confirmation_record_is_accepted(self):
        state = make_state(review_status="pass")
        final_gate = next(
            item for item in state["confirmation_gates"] if item["action"] == "final_submit"
        )
        final_gate.update(
            status="completed",
            question="Do you confirm the final Submit action?",
            user_choice="confirmed",
            confirmed_at="2026-07-26T16:00:00+08:00",
            applies_to="Final Review page",
        )
        errors, _ = MODULE.validate_state(state)
        self.assertEqual(errors, [])

    def test_final_submit_exit_conditions_are_enforced(self):
        state = make_state(review_status="pass")
        final_gate = next(
            item for item in state["confirmation_gates"] if item["action"] == "final_submit"
        )
        final_gate.update(
            status="completed",
            question="Do you confirm the final Submit action?",
            user_choice="confirmed",
            confirmed_at="2026-07-26T16:00:00+08:00",
            applies_to="Final Review page",
        )
        state["platform"].pop("institution_match_status")
        state["portal_tasks"] = [{
            "task_type": "proof",
            "page": "Final Review",
            "required": True,
            "status": "not_viewed",
        }]
        state["blockers"] = [{"id": "missing-field", "status": "open"}]
        errors, _ = MODULE.validate_state(state)
        self.assertTrue(any("institution_match_status" in item for item in errors))
        self.assertTrue(any("required but not completed" in item for item in errors))
        self.assertTrue(any("viewed_at" in item for item in errors))
        self.assertTrue(any("proof/preview" in item for item in errors))
        self.assertTrue(any("is not closed" in item for item in errors))

    def test_verified_freshness_requires_checked_at(self):
        state = make_state()
        state["files"] = [make_file(provenance={
            "inputs": [{"path": "main.tex", "sha256": "B" * 64}],
            "freshness_status": "verified",
        })]
        errors, _ = MODULE.validate_state(state)
        self.assertTrue(any("freshness_checked_at" in item for item in errors))

    def test_no_input_snapshot_requires_unknown(self):
        state = make_state()
        state["files"] = [make_file(provenance={"freshness_status": "verified"})]
        errors, _ = MODULE.validate_state(state)
        self.assertTrue(any("without inputs" in item for item in errors))

    def test_invalid_institution_match_status_is_rejected(self):
        state = make_state()
        state["platform"]["institution_match_status"] = "ringgold_confirmed"
        errors, _ = MODULE.validate_state(state)
        self.assertTrue(any("institution_match_status" in item for item in errors))

    def test_schema_1_1_rejects_empty_file_record(self):
        state = make_state()
        state["files"] = [{}]
        errors, _ = MODULE.validate_state(state)
        self.assertTrue(any("schema 1.1" in item for item in errors))

    def test_schema_1_1_rejects_numeric_file_strings(self):
        state = make_state()
        state["files"] = [make_file(
            path=0,
            submission_name=0,
            purpose=0,
            stage=0,
            upload_status=0,
        )]
        errors, _ = MODULE.validate_state(state)
        self.assertTrue(any("non-empty string" in item for item in errors))

    def test_sensitive_author_field_is_rejected(self):
        unsafe = json.loads(json.dumps(self.fixture["authors"]))
        unsafe["authors"][0]["phone"] = "000-0000"
        errors, _, _ = MODULE.validate_authors(unsafe)
        self.assertTrue(any("forbidden sensitive field" in item for item in errors))


if __name__ == "__main__":
    unittest.main()
