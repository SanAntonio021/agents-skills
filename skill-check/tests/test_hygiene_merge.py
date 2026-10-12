import copy
import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/run_weekly_skill_review.py"
SPEC = importlib.util.spec_from_file_location("hygiene_merge_review", SCRIPT)
REVIEW = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(REVIEW)


def observations(root, paths):
    summary = {"findings": {"directory_structure_problems": [
        {"path": path, "kind": "directory_structure", "severity": "严重问题",
         "detail": "Nested skill", "suggested_action": "人工复核"}
        for path in paths
    ]}}
    return REVIEW.extract_hygiene_observations(summary, "summary.json", root)


def test_distinct_paths_aggregate_under_legacy_id_and_repeat_scan_keeps_decision(tmp_path):
    paths = ["archive/first/skill-snapshot", "archive/second/skill-snapshot"]
    first = observations(tmp_path, paths)
    assert len(first) == 1
    assert first[0]["id"] == observations(tmp_path, paths[:1])[0]["id"]
    assert {item["path"] for item in first[0]["evidence_items"]} == set(paths)
    state = REVIEW.new_state()
    REVIEW.merge_observations(state, first, "2026-10-10")
    finding = state["findings"][first[0]["id"]]
    finding.update(status="closed", decision={"value": "closed_after_facts"},
                   facts=[{"answer_summary": "Both historical copies checked"}])
    state["queue"] = []
    saved = copy.deepcopy(finding)
    repeated = observations(tmp_path, list(reversed(paths)) + paths[:1])
    REVIEW.merge_observations(state, repeated, "2026-10-10")
    assert finding == saved
    assert state["queue"] == []
    changed = observations(tmp_path, paths + ["archive/new/SKILL.md"])
    REVIEW.merge_observations(state, changed, "2026-10-10")
    assert finding["status"] == "queued"
    previous = finding["history"][-1]["previous"]
    assert previous["decision"] == saved["decision"]
    assert previous["evidence_items"] == saved["evidence_items"]


def test_legacy_collision_decision_is_archived_once_not_silently_reused(tmp_path):
    single = observations(tmp_path, ["archive/first/SKILL.md"])
    state = REVIEW.new_state()
    REVIEW.merge_observations(state, single, "2026-10-10")
    finding = state["findings"][single[0]["id"]]
    finding.update(status="closed", decision={"value": "closed_after_facts"})
    combined = observations(tmp_path, ["archive/first/SKILL.md", "archive/second/SKILL.md"])
    REVIEW.merge_observations(state, combined, "2026-10-10")
    assert finding["history"][-1]["previous"]["decision"]["value"] == "closed_after_facts"
    assert "decision" not in finding
    size = len(finding["history"])
    REVIEW.merge_observations(state, combined, "2026-10-10")
    assert len(finding["history"]) == size


def test_absent_wait_resolves_only_with_authoritative_hygiene_and_no_failed_execution(tmp_path):
    state = REVIEW.new_state()
    obs = observations(tmp_path, ["archive/first/SKILL.md"])
    REVIEW.merge_observations(state, obs, "2026-10-10")
    finding = state["findings"][obs[0]["id"]]
    finding.update(status="waiting_evidence", decision={"value": "approved"})
    state["queue"] = []
    REVIEW.merge_observations(state, [], "2026-10-10", authoritative_sources=set())
    assert finding["status"] == "waiting_evidence"
    finding["execution"] = {"outcome": "failed"}
    REVIEW.merge_observations(state, [], "2026-10-10", authoritative_sources={"hygiene"})
    assert finding["status"] == "waiting_evidence"
    del finding["execution"]
    for source in ("discovery", "upstream_private"):
        finding["source"] = source
        REVIEW.merge_observations(state, [], "2026-10-10", authoritative_sources={source})
        assert finding["status"] == "waiting_evidence"
    finding["source"] = "hygiene"
    REVIEW.merge_observations(state, [], "2026-10-10", authoritative_sources={"hygiene"})
    assert finding["status"] == "resolved"
    assert finding["decision"] == {"value": "approved"}
