import copy
import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "run_weekly_skill_review.py"
SPEC = importlib.util.spec_from_file_location("upstream_completeness_regression", SCRIPT)
REVIEW = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(REVIEW)
STAMP = "2026-09-08T06:00:00+00:00"


def healthy_source():
    return {"skill": "beta", "source": "healthy", "status": "review_required",
            "last_successful_check_at": STAMP, "last_check_attempt_at": STAMP, "last_successful_check_commit": "b" * 40,
            "last_remote_check_attempt_at": STAMP, "last_remote_check_status": "review_required",
            "accepted_commit": "a" * 40, "current_commit": "b" * 40}


def test_report_readability_does_not_prove_remote_check_and_does_not_modify_metadata():
    source = healthy_source()
    summary = {"date": "2026-09-08", "generated_at": STAMP, "sources": [source], "check_error_count": 0}
    assert REVIEW.upstream_check_evidence(summary)["remote_checked"] is True
    source["last_successful_check_at"] = "2026-09-01T06:00:00+00:00"
    before = copy.deepcopy(summary)
    checked = REVIEW.upstream_check_evidence(summary)
    assert checked["checks_complete"] is False and checked["remote_checked"] is False
    assert summary == before
    source.pop("last_successful_check_at")
    assert not REVIEW.upstream_check_evidence(summary)["checks_complete"]


def test_no_confirmed_sources_need_no_remote_check():
    checked = REVIEW.upstream_check_evidence({"sources": [], "check_error_count": 0})
    assert checked["checks_complete"] is True and checked["remote_checked"] is None
    assert not REVIEW.upstream_check_evidence({"sources": [], "check_error_count": 1})["checks_complete"]


def test_same_day_report_render_keeps_success_but_changed_commit_does_not():
    source = healthy_source()
    source["last_check_attempt_at"] = "2026-09-08T07:00:00+00:00"
    summary = {"date": "2026-09-08", "generated_at": "2026-09-08T07:00:00+00:00",
               "sources": [source], "check_error_count": 0}
    assert REVIEW.upstream_check_evidence(summary)["checks_complete"] is True
    source["current_commit"] = "d" * 40
    assert REVIEW.upstream_check_evidence(summary)["checks_complete"] is False


def test_old_remote_metadata_is_unknown_and_later_failure_survives_local_report():
    source = healthy_source()
    summary = {"date": "2026-09-08", "generated_at": "2026-09-08T08:00:00+00:00",
               "sources": [source], "check_error_count": 0}
    source.pop("last_remote_check_attempt_at")
    source.pop("last_remote_check_status")
    legacy = REVIEW.upstream_check_evidence(summary)
    assert legacy["remote_checked"] is None and legacy["checks_complete"] is False
    # A later report sees a healthy local checkout but must retain the failed
    # remote receipt, rather than reuse the earlier same-day success.
    source.update(status="up_to_date", last_remote_check_attempt_at="2026-09-08T07:00:00+00:00",
                  last_remote_check_status="mirror_blocked", last_check_attempt_at="2026-09-08T08:00:00+00:00")
    failed = REVIEW.upstream_check_evidence(summary)
    assert failed["remote_checked"] is False and failed["checks_complete"] is False


@pytest.mark.parametrize("reuse", [False, True])
def test_failed_source_never_counts_as_complete_week_but_healthy_source_continues(tmp_path, monkeypatch, reuse):
    skills, reports = tmp_path / "skills", tmp_path / "reports"
    for name in ("alpha", "beta", "agent-rules"):
        (skills / name).mkdir(parents=True)
        (skills / name / "SKILL.md").write_text("body", encoding="utf-8")
    reports.mkdir()
    failed = {"skill": "alpha", "source": "failed", "status": "mirror_blocked",
              "error": "TLS fetch failed", "accepted_commit": "c" * 40,
              "last_check_attempt_at": STAMP, "last_successful_check_at": "2026-09-01T06:00:00+00:00"}
    upstream = {"schema_version": 1, "date": "2026-09-08", "generated_at": STAMP,
                "check_error_count": 1, "sources": [failed, healthy_source()]}
    usage = {"version": "skill-usage-audit-v2", "date": "2026-09-08", "warnings": {},
             "skill_inventory": [{"skill": "alpha", "active_hosts": ["codex"]}],
             "classifications": {"已用": [], "历史内未见使用": [{"skill": "alpha", "active_hosts": ["codex"]}]},
             "configuration": {"count_unit": "request"},
             "window": {"start": "2026-09-01T14:00:00+08:00", "end": "2026-09-08T14:00:00+08:00"}}
    summaries = {"upstream": upstream, "usage": usage,
                 "hygiene": {"version": "flat-skill-tree-v1", "date": "2026-09-08", "findings": {}}}
    paths = {name: reports / (name + ".json") for name in summaries}
    for name, data in summaries.items():
        paths[name].write_text(json.dumps(data), encoding="utf-8")
    before_upstream = paths["upstream"].read_bytes()
    commands = {name: {"exit_code": 0, "summary_changed": True} for name in summaries}
    commands["upstream"]["exit_code"] = 2
    monkeypatch.setattr(REVIEW, "run_audits", lambda **_: (commands, paths))
    state = REVIEW.new_state()
    previous = REVIEW.make_observation(kind="upstream_candidate", source="upstream", subject="alpha:failed",
        purpose="retain-pending-source-review", severity="medium", title="Existing candidate", evidence={},
        evidence_summary="Previously reviewed candidate", report_refs=[], skills_root=skills,
        suggested_proposal=REVIEW.proposal("review", "Review existing candidate", ["alpha"], skills=["alpha"]))
    REVIEW.merge_observations(state, [previous], "2026-09-01")
    state["findings"][previous["id"]]["status"] = "awaiting_decision"
    state["unseen_streaks"]["alpha"] = {"count": 3, "last_window_end": usage["window"]["start"]}
    state_path = reports / "state.json"
    REVIEW.save_state(state_path, state)
    argv = ["scan", "--state", str(state_path), "--agents-root", str(tmp_path), "--skills-root", str(skills),
            "--reports-root", str(reports), "--date", "2026-09-08"]
    if reuse:
        argv.append("--reuse-reports")
    payload, code = REVIEW.scan_command(REVIEW.parse_args(argv))
    assert code == 2 and not payload["complete"] and payload["dashboard"]["valid"]
    saved, _ = REVIEW.load_state(state_path)
    assert saved["unseen_streaks"]["alpha"]["count"] == 0
    assert saved["findings"][previous["id"]]["status"] == "awaiting_decision"
    assert any(row["subject"] == "beta:healthy" for row in saved["findings"].values())
    assert paths["upstream"].read_bytes() == before_upstream
    report = json.loads((reports / "2026-09-08/weekly-review.json").read_text(encoding="utf-8"))
    validation = report["validation"]["upstream"]
    assert validation["valid"] is True and validation["checks_complete"] is False
    checked = {row["source"]: row["remote_checked"] for row in validation["source_checks"]}
    assert checked == {"failed": False, "healthy": True}
