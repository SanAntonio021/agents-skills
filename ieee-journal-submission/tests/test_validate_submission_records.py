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


def make_state(stage, platform):
    return {
        "schema_version": "1.0",
        "journal": {"name": "IEEE Transactions on Examples"},
        "manuscript": {"title": "Synthetic manuscript"},
        "platform": {"name": platform},
        "lifecycle": {"current_stage": stage},
        "authors": [
            {"profile_id": "author-alice-example", "order": 1},
            {"profile_id": "author-bob-sample", "order": 2}
        ],
        "files": [],
        "declarations": {},
        "official_sources": [],
        "confirmation_gates": [
            {"action": "author_roles", "status": "required"},
            {"action": "declarations", "status": "required"},
            {"action": "reviewers", "status": "required"},
            {"action": "final_submit", "status": "required"},
            {"action": "open_access_fees", "status": "required"},
            {"action": "copyright", "status": "required"},
            {"action": "withdrawal_transfer", "status": "required"}
        ],
        "operation_history": [],
        "next_action": {"action": "inspect current page"}
    }


class ValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))

    def test_synthetic_author_library(self):
        errors, warnings, profile_ids = MODULE.validate_authors(self.fixture["authors"])
        self.assertEqual(errors, [])
        self.assertEqual(profile_ids, {"author-alice-example", "author-bob-sample"})
        self.assertTrue(any("pending" in warning for warning in warnings))

    def test_all_lifecycle_scenarios(self):
        _, _, profile_ids = MODULE.validate_authors(self.fixture["authors"])
        for case in self.fixture["states"]:
            with self.subTest(case=case["name"]):
                errors, _ = MODULE.validate_state(
                    make_state(case["stage"], case["platform"]), profile_ids
                )
                self.assertEqual(errors, [])

    def test_sensitive_fields_are_rejected(self):
        errors, _, _ = MODULE.validate_authors(self.fixture["unsafe_authors"])
        self.assertTrue(any("forbidden sensitive field" in error for error in errors))

    def test_missing_confirmation_gate_is_rejected(self):
        state = make_state("initial_submission", "Research Exchange")
        state["confirmation_gates"] = state["confirmation_gates"][:-1]
        errors, _ = MODULE.validate_state(state)
        self.assertTrue(any("withdrawal_transfer" in error for error in errors))

    def test_invalid_provenance_input_is_rejected(self):
        state = make_state("initial_submission", "Research Exchange")
        state["files"] = [{
            "path": "main_submission.pdf",
            "sha256": "A" * 64,
            "provenance": {
                "built_at": "2026-07-14",
                "inputs": [{"path": "main.tex", "size_bytes": 10, "sha256": "BAD"}],
                "freshness_status": "verified",
            },
        }]
        errors, _ = MODULE.validate_state(state)
        self.assertTrue(any("provenance.inputs[0].sha256" in error for error in errors))

    def test_valid_provenance_input_is_accepted(self):
        state = make_state("initial_submission", "Research Exchange")
        state["files"] = [{
            "path": "main_submission.pdf",
            "sha256": "A" * 64,
            "provenance": {
                "built_at": "2026-07-14",
                "inputs": [{"path": "main.tex", "size_bytes": 10, "sha256": "B" * 64}],
                "freshness_checked_at": "2026-07-14",
                "freshness_status": "verified",
            },
        }]
        errors, _ = MODULE.validate_state(state)
        self.assertEqual(errors, [])

    def test_provenance_without_input_snapshot_requires_unknown(self):
        for status in ("verified", "stale"):
            with self.subTest(status=status):
                state = make_state("initial_submission", "Research Exchange")
                state["files"] = [{
                    "path": "main_submission.pdf",
                    "sha256": "A" * 64,
                    "provenance": {"freshness_status": status},
                }]
                errors, _ = MODULE.validate_state(state)
                self.assertTrue(any("without inputs" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
