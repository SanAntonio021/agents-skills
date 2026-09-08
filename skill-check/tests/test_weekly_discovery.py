from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "run_weekly_skill_review.py"
SPEC = importlib.util.spec_from_file_location("weekly_review_discovery_tests", SCRIPT)
REVIEW = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(REVIEW)
DISCOVERY = REVIEW.DISCOVERY


def inventory(*keys):
    return {key: {"skill_key": key, "name": key.split(":")[1], "source_scope": key.split(":")[0],
                  "status": "none", "local_digest": "v1", "adopted": []} for key in keys}


def trigger(key, kind="user_feedback", evidence="Observed capability gap"):
    return {"skill_key": key, "trigger": kind, "purpose": "clarification", "evidence": evidence}


def update(state, inv, intake=None, date="2026-09-08"):
    return DISCOVERY.update_discovery(state, inventory=inv, date_value=date, intake=intake)


def result(task, outcome="no_benefit", candidates=None):
    return {"task_id": task["id"], "expected_evidence_fingerprint": task["evidence_fingerprint"],
            "outcome": outcome, "evidence": "Primary-source comparison completed",
            "candidates": candidates or []}


def candidate(suffix="one"):
    return {"repo_url": "https://example.invalid/" + suffix, "upstream_path": "skills/example",
            "revision": "unverified", "license": "unverified", "source_evidence": "Repository page; author attribution unresolved",
            "upstream_improvement": "Tests whether the stated goal follows from facts",
            "local_gap": "No premise check", "expected_benefit": "Find unjustified premises",
            "conflicts": "Keep explicit invocation only"}


def test_old_state_works_and_limits_prioritize_feedback_then_evals():
    state = REVIEW.new_state()
    inv = inventory("public:a", "public:b", "private:a", "public:c")
    triggers = [trigger("public:a", "source_unknown"), trigger("public:b", "eval_gap"),
                trigger("private:a"), trigger("public:c", "source_unknown")]
    report = update(state, inv, {"triggers": triggers})
    assert report["admitted_skills"][:2] == ["private:a", "public:b"]
    assert len(report["admitted_skills"]) == 3
    assert len(report["deferred_task_ids"]) == 1
    REVIEW.validate_state(state)
    again = update(state, inv, {"triggers": triggers}, "2026-09-09")
    assert again["admitted_skills"] == report["admitted_skills"]
    for task in report["research_tasks"]:
        update(state, inv, {"results": [result(task)]})
    next_week = update(state, inv, date="2026-09-12")
    assert len(next_week["research_tasks"]) == 1
    assert next_week["research_tasks"][0]["id"] == report["deferred_task_ids"][0]


@pytest.mark.parametrize("outcome", ["no_benefit", "blocked"])
def test_terminal_research_does_not_repeat_until_new_evidence(outcome):
    state, inv = {}, inventory("public:a")
    first = update(state, inv, {"triggers": [trigger("public:a")]})["research_tasks"][0]
    update(state, inv, {"results": [result(first, outcome)]})
    assert update(state, inv, {"triggers": [trigger("public:a")]}, "2026-09-19")["research_tasks"] == []
    reopened = update(state, inv, {"triggers": [trigger("public:a", evidence="new evaluation evidence")]})
    assert len(reopened["research_tasks"]) == 1
    assert reopened["research_tasks"][0]["history"][0]["status"] == outcome


def test_same_named_private_and_public_skills_have_separate_tasks_and_candidates():
    state, inv = {}, inventory("public:pdf", "private:pdf")
    tasks = update(state, inv, {"triggers": [trigger(k) for k in inv]})["research_tasks"]
    assert len({t["id"] for t in tasks}) == 2
    report = update(state, inv, {"results": [result(t, "candidates", [candidate()]) for t in tasks]})
    assert len(report["reviews"]) == 2
    assert len({r["id"] for r in report["reviews"]}) == 2


def test_candidate_budget_dedup_and_bad_intake_rolls_back():
    state, inv = {}, inventory("public:a")
    task = update(state, inv, {"triggers": [trigger("public:a")]})["research_tasks"][0]
    data = {"results": [result(task, "candidates", [candidate("one"), candidate("two")])]}
    update(state, inv, data)
    assert len(update(state, inv, data)["reviews"]) == 2
    before = copy.deepcopy(state)
    with pytest.raises(ValueError, match="candidate limit"):
        update(state, inv, {"results": [result(task, "candidates", [candidate("three")])]})
    assert state == before
    incomplete = candidate()
    incomplete.pop("license")
    with pytest.raises(ValueError, match="license"):
        update(state, inv, {"results": [result(task, "candidates", [incomplete])]})
    assert state == before


def test_low_usage_and_external_packages_cannot_trigger_and_none_is_normal():
    state, inv = {}, inventory("public:original")
    assert update(state, inv)["research_tasks"] == []
    for row in (trigger("public:original", "low_usage"), trigger("plugin:external")):
        with pytest.raises(ValueError, match="maintained skill"):
            update(state, inv, {"triggers": [row]})


def test_local_edit_is_manual_signal_and_failed_source_check_preserves_claims():
    state, inv = {}, inventory("public:a")
    inv["public:a"].update(status="confirmed", adopted=[{"source": "a", "adopted": ["Check premises"]}])
    assert update(state, inv)["reviews"] == []
    inv["public:a"].update(local_digest="v2", status="unregistered", adopted=[])
    report = update(state, inv)
    row = report["reviews"][0]
    assert row["evidence"]["adopted"] == row["evidence"]["previous_adopted"]
    assert state["discovery"]["snapshots"]["public:a"]["adopted"]
    assert "不能证明行为退化" in row["summary"]
    again = update(state, inv)
    assert again["reviews"] == report["reviews"]


def test_manual_review_closed_via_existing_facts_does_not_requeue(tmp_path):
    state = REVIEW.new_state()
    inv = inventory("public:a")
    inv["public:a"].update(status="confirmed", adopted=["check facts"])
    update(state, inv)
    inv["public:a"]["local_digest"] = "v2"
    report = update(state, inv)
    observations = REVIEW.discovery_observations(report, tmp_path)
    REVIEW.merge_observations(state, observations, "2026-09-08")
    path = tmp_path / "state.json"
    REVIEW.save_state(path, state)
    q, code = REVIEW.next_question_command(REVIEW.parse_args(["next-question", "--state", str(path)]))
    assert code == 0 and q["question_type"] == "fact" and q["proposal"] is None
    answer = REVIEW.parse_args([
        "record-decision", "--state", str(path), "--finding-id", q["finding_id"],
        "--expected-evidence-fingerprint", q["expected_evidence_fingerprint"],
        "--expected-proposal-fingerprint", "none", "--classification", "auto", "--facts-outcome", "close",
        "--answer", "人工比对方法和评测输出：能力仍保留，无需修改。",
    ])
    recorded, code = REVIEW.record_decision_command(answer)
    assert code == 0 and recorded["next_status"] == "closed"
    saved, _ = REVIEW.load_state(path)
    REVIEW.merge_observations(saved, observations, "2026-09-12")
    assert saved["findings"][q["finding_id"]]["status"] == "closed"
    assert q["finding_id"] not in saved["queue"]


def test_private_findings_have_no_public_mutation_proposal(tmp_path):
    original = REVIEW.make_observation(kind="hygiene", source="hygiene", subject="pdf", purpose="fix",
        severity="medium", title="pdf", evidence_summary="check", evidence={}, report_refs=[],
        suggested_proposal=REVIEW.proposal("fix", "fix public pdf", ["pdf"], skills=["pdf"]), skills_root=tmp_path)
    converted = REVIEW.private_observations([copy.deepcopy(original)])[0]
    assert converted["id"] != original["id"]
    assert converted["proposal"] is None and converted["subject"] == "private:pdf"


def test_inventory_roots_and_generated_source_page_exclusion(tmp_path):
    public, private = tmp_path / "public", tmp_path / "private"
    for root in (public, private):
        (root / "pdf" / "references").mkdir(parents=True)
        (root / "pdf" / "SKILL.md").write_text("body", encoding="utf-8")
    (public / "materials").mkdir()
    inv, errors = DISCOVERY.read_inventory({"public": public, "private": private}, {}, DISCOVERY.local_content_digest)
    assert set(inv) == {"public:pdf", "private:pdf"} and errors == []
    (public / "pdf" / "references" / "upstream-sources.md").write_text("generated", encoding="utf-8")
    current, _ = DISCOVERY.read_inventory({"public": public}, {}, DISCOVERY.local_content_digest)
    assert current["public:pdf"]["local_digest"] == inv["public:pdf"]["local_digest"]


def test_private_scanners_use_separate_roots_reports_and_registry(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(REVIEW, "run_process", lambda name, command, cwd, summary: calls.append((name, command, summary)) or {})
    REVIEW.run_audits(agents_root=tmp_path, skills_root=tmp_path / "skills", reports_root=tmp_path / "reports",
        date="2026-09-08", usage_window_start="a", usage_window_end="b", usage_timezone="Asia/Shanghai",
        reuse_reports=False, private_skills_root=tmp_path / "private-skills", private_registry=tmp_path / "private.toml")
    assert len(calls) == 5
    private = next(c for c in calls if c[0] == "upstream_private")
    assert str(tmp_path / "private-skills") in private[1] and str(tmp_path / "private.toml") in private[1]
    assert private[1][private[1].index("--source-scope") + 1] == "private"
    assert private[2].is_relative_to(tmp_path / "reports" / "private")


def test_bad_discovery_input_and_private_network_failure_preserve_other_audits(tmp_path, monkeypatch):
    skills, private, reports = tmp_path / "skills", tmp_path / "private-skills", tmp_path / "reports"
    for root in (skills, private):
        (root / "pdf").mkdir(parents=True)
        (root / "pdf" / "SKILL.md").write_text("body", encoding="utf-8")
    summaries = {
        "upstream": {"schema_version": 1, "date": "2026-09-08", "sources": []},
        "hygiene": {"version": "flat-skill-tree-v1", "date": "2026-09-08", "findings": {}},
        "hygiene_private": {"version": "flat-skill-tree-v1", "date": "2026-09-08",
                            "findings": {"broken_items": [{"path": "pdf/SKILL.md", "detail": "review private source"}]}},
        "usage": {"version": "skill-usage-audit-v2", "date": "2026-09-08", "warnings": {},
                  "skill_inventory": [], "classifications": {}, "configuration": {"count_unit": "request"},
                  "window": {"start": "2026-09-01T14:00:00+08:00", "end": "2026-09-08T14:00:00+08:00"}},
    }
    reports.mkdir()
    paths = {name: reports / (name + ".json") for name in (*summaries, "upstream_private")}
    for name, value in summaries.items():
        paths[name].write_text(json.dumps(value), encoding="utf-8")
    outcomes = {name: {"exit_code": 0, "summary_changed": True} for name in summaries}
    outcomes["upstream_private"] = {"exit_code": 1, "summary_changed": False, "stderr": "network unavailable"}
    monkeypatch.setattr(REVIEW, "run_audits", lambda **_: (outcomes, paths))
    state = REVIEW.new_state()
    update(state, inventory("public:pdf"), {"triggers": [trigger("public:pdf")]})
    before = copy.deepcopy(state["discovery"])
    state_path = reports / "state.json"
    REVIEW.save_state(state_path, state)
    bad_input = reports / "bad-input.json"
    bad_input.write_text('{"results": "invalid"}', encoding="utf-8")
    args = REVIEW.parse_args(["scan", "--state", str(state_path), "--agents-root", str(tmp_path),
        "--skills-root", str(skills), "--reports-root", str(reports), "--date", "2026-09-08",
        "--discovery-input", str(bad_input)])
    payload, code = REVIEW.scan_command(args)
    assert code == 2 and not payload["complete"]
    saved, _ = REVIEW.load_state(state_path)
    assert saved["discovery"] == before
    findings = list(saved["findings"].values())
    assert any(f["source"] == "hygiene_private" for f in findings)
    assert any(f["source"] == "upstream_private" and f["kind"] == "scan_failure" for f in findings)
    assert any(f["source"] == "discovery" and f["kind"] == "scan_failure" for f in findings)
    report = json.loads((reports / "2026-09-08" / "weekly-review.json").read_text(encoding="utf-8"))
    assert report["validation"]["upstream"]["valid"] and report["validation"]["usage"]["valid"]


def test_unreadable_skill_is_isolated_from_other_inventory(tmp_path):
    for name in ("a", "b"):
        (tmp_path / name).mkdir()
        (tmp_path / name / "SKILL.md").write_text("body", encoding="utf-8")
    def hash_one(path):
        if path.name == "a":
            raise PermissionError("unreadable")
        return "digest"
    inv, errors = DISCOVERY.read_inventory({"public": tmp_path}, {}, hash_one)
    assert set(inv) == {"public:b"} and len(errors) == 1


@pytest.mark.parametrize("status, expected", [("none", "report"), ("confirmed", "weekly-run")])
def test_private_without_confirmed_sources_does_not_refresh_mirrors(tmp_path, monkeypatch, status, expected):
    registry = tmp_path / "private.toml"
    registry.write_text(f'schema_version = 1\n[[skill]]\nname = "pdf"\nstatus = "{status}"\n', encoding="utf-8")
    calls = []
    monkeypatch.setattr(REVIEW, "run_process", lambda name, command, cwd, summary: calls.append((name, command)) or {})
    REVIEW.run_audits(agents_root=tmp_path, skills_root=tmp_path / "skills", reports_root=tmp_path / "reports",
        date="2026-09-08", usage_window_start="a", usage_window_end="b", usage_timezone="Asia/Shanghai",
        reuse_reports=False, private_skills_root=tmp_path / "private-skills", private_registry=registry)
    command = next(command for name, command in calls if name == "upstream_private")
    assert command[2] == expected
