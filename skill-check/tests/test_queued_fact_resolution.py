import copy
import importlib.util
import json
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/run_weekly_skill_review.py"
SPEC = importlib.util.spec_from_file_location("queued_fact_resolution_review", SCRIPT)
REVIEW = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(REVIEW)


def observation(root, subject="public:ask-first"):
    return REVIEW.make_observation(
        kind="local_capability_review", source="discovery", subject=subject,
        purpose="review adopted capabilities", severity="medium",
        title="Local capability review", evidence_summary="Local content changed",
        evidence={"digest": "current", "adopted": ["Check premises"]},
        suggested_proposal=None, report_refs=[], needs_facts=True,
        skills_root=root,
    )


def setup_finding(tmp_path, status):
    state = REVIEW.new_state()
    # Reproduce the real scan path: the fourth routine item is deferred.
    if status == "deferred":
        REVIEW.merge_observations(
            state, [observation(tmp_path, f"public:existing-{i}")
                    for i in range(REVIEW.ROUTINE_QUEUE_LIMIT)], "2026-09-08",
        )
    item = observation(tmp_path)
    REVIEW.merge_observations(state, [item], "2026-09-08")
    finding = state["findings"][item["id"]]
    assert finding["status"] == status
    path = tmp_path / "state.json"
    REVIEW.save_state(path, state)
    return path, state, finding, item


def command(path, finding, *options):
    return REVIEW.parse_args([
        "record-decision", "--state", str(path), "--skills-root", str(path.parent),
        "--finding-id", finding["id"],
        "--expected-evidence-fingerprint", finding["evidence_fingerprint"],
        "--expected-proposal-fingerprint", finding.get("proposal_fingerprint") or "none",
        "--answer", "Semantic review completed; retained capabilities match the description.",
        "--classification", "auto", *options,
    ])


@pytest.mark.parametrize("status", ["deferred", "queued"])
@pytest.mark.parametrize("outcome,expected", [("close", "closed"), ("wait", "waiting_evidence")])
def test_explicit_fact_resolution_without_question_keeps_other_queue_items(tmp_path, status, outcome, expected):
    path, state, finding, item = setup_finding(tmp_path, status)
    other_findings = {k: v for k, v in state["findings"].items() if k != finding["id"]}
    payload, code = REVIEW.record_decision_command(command(path, finding, "--facts-outcome", outcome))
    assert code == 0 and payload["next_status"] == expected
    saved = json.loads(path.read_text(encoding="utf-8"))
    current = saved["findings"][finding["id"]]
    assert current["status"] == expected and len(current["facts"]) == 1
    assert current["decision"]["reason_summary"].startswith("Semantic review completed")
    assert current["proposal"] is None and current["proposal_fingerprint"] is None
    assert finding["id"] not in saved["queue"]
    assert {k: v for k, v in saved["findings"].items() if k != finding["id"]} == other_findings
    assert saved["batches"] == state["batches"]
    # A later scan with the same evidence must not ask the resolved question again.
    resolved = copy.deepcopy(current)
    REVIEW.merge_observations(saved, [item], "2026-09-12")
    assert saved["findings"][finding["id"]] == {**resolved, "last_seen": "2026-09-12"}
    assert finding["id"] not in saved["queue"]


@pytest.mark.parametrize("options", [[], ["--classification", "approve"], ["--facts-outcome", "propose"]])
def test_deferred_requires_explicit_close_or_wait_and_cannot_be_approved(tmp_path, options):
    path, _, finding, _ = setup_finding(tmp_path, "deferred")
    before = path.read_bytes()
    payload, code = REVIEW.record_decision_command(command(path, finding, *options))
    assert code == 2 and payload["status"] == "invalid_state"
    assert path.read_bytes() == before


@pytest.mark.parametrize("status", ["deferred", "queued"])
@pytest.mark.parametrize("outcome", ["close", "wait"])
@pytest.mark.parametrize("changed", [
    {"needs_facts": False},
    {"proposal": {"summary": "Existing proposal"}},
    {"proposal": {}},
    {"proposal_fingerprint": "existing-proposal-fingerprint"},
])
def test_direct_resolution_rejects_nonfacts_or_any_proposal(tmp_path, status, outcome, changed):
    path, state, finding, _ = setup_finding(tmp_path, status)
    finding.update(changed)
    REVIEW.save_state(path, state)
    before = path.read_bytes()
    # Even an approve classifier must not bypass the facts-only restriction.
    payload, code = REVIEW.record_decision_command(
        command(path, finding, "--classification", "approve", "--facts-outcome", outcome)
    )
    assert code == 2 and payload["status"] == "invalid_state"
    assert path.read_bytes() == before


@pytest.mark.parametrize("status", ["deferred", "queued"])
@pytest.mark.parametrize("field", ["evidence", "proposal"])
def test_direct_resolution_checks_fingerprints_before_recording(tmp_path, status, field):
    path, _, finding, _ = setup_finding(tmp_path, status)
    before = path.read_bytes()
    args = command(path, finding, "--facts-outcome", "close",
                   f"--expected-{field}-fingerprint", "stale")
    payload, code = REVIEW.record_decision_command(args)
    assert code == 4 and payload["status"] == "stale_fingerprint" and payload["field"] == field
    assert path.read_bytes() == before


def test_new_evidence_reopens_review_but_old_close_cannot_apply(tmp_path):
    path, _, finding, item = setup_finding(tmp_path, "deferred")
    old_args = command(path, finding, "--facts-outcome", "close")
    assert REVIEW.record_decision_command(old_args)[1] == 0
    state = json.loads(path.read_text(encoding="utf-8"))
    changed = copy.deepcopy(item)
    changed["evidence_fingerprint"] = REVIEW.fingerprint({"digest": "new"})
    REVIEW.merge_observations(state, [changed], "2026-09-12")
    reopened = state["findings"][finding["id"]]
    assert reopened["status"] == "queued" and "decision" not in reopened
    assert reopened["history"][-1]["previous"]["decision"]["value"] == "closed_after_facts"
    REVIEW.save_state(path, state)
    before = path.read_bytes()
    payload, code = REVIEW.record_decision_command(old_args)
    assert code == 4 and payload["field"] == "evidence"
    assert path.read_bytes() == before
