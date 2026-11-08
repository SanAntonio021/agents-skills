import copy
import importlib.util
import json
import os
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


def test_waiting_evidence_fact_only_finding_can_close(tmp_path):
    path, state, finding, _ = setup_finding(tmp_path, "queued")
    finding["status"] = "waiting_evidence"
    REVIEW.save_state(path, state)
    payload, code = REVIEW.record_decision_command(
        command(path, finding, "--facts-outcome", "close")
    )
    assert code == 0 and payload["next_status"] == "closed"
    saved = json.loads(path.read_text(encoding="utf-8"))
    current = saved["findings"][finding["id"]]
    assert current["status"] == "closed"
    assert current["decision"]["value"] == "closed_after_facts"
    assert current["facts"][-1]["answer_summary"].startswith("Semantic review completed")
    assert finding["id"] not in saved["queue"]


def setup_trigger_hint(tmp_path):
    path, state, finding, item = setup_finding(tmp_path, "deferred")
    finding.update(kind="suspected_missed_use", source="usage")
    subject = finding["subject"]
    finding["proposal"] = REVIEW.proposal(
        "补触发边界",
        f"若真实使用习惯确认需要自动触发，则收紧或补充 {subject} 的 description，并补正反触发测试。",
        [subject], skills=[subject],
    )
    finding["proposal_fingerprint"] = REVIEW.fingerprint(finding["proposal"])
    REVIEW.save_state(path, state)
    return path, state, finding


def test_deferred_trigger_false_positive_closes_without_admission(tmp_path):
    path, state, finding = setup_trigger_hint(tmp_path)
    before_queue = list(state["queue"])
    payload, code = REVIEW.record_decision_command(command(path, finding, "--facts-outcome", "close"))
    assert code == 0 and payload["next_status"] == "closed"
    saved = json.loads(path.read_text(encoding="utf-8"))
    current = saved["findings"][finding["id"]]
    assert current["decision"]["value"] == "closed_after_facts"
    assert current["proposal"] == finding["proposal"]
    assert saved["queue"] == before_queue
    assert saved["batches"] == state["batches"]
    assert current.get("routine_admitted_date") == finding.get("routine_admitted_date")


@pytest.mark.parametrize("case", ["approve", "wait", "changed_proposal", "stale_evidence", "stale_proposal"])
def test_trigger_hint_exception_does_not_bypass_guards(tmp_path, case):
    path, state, finding = setup_trigger_hint(tmp_path)
    options = ["--facts-outcome", "close"]
    if case == "approve":
        options += ["--classification", "approve"]
    elif case == "wait":
        options = ["--facts-outcome", "wait"]
    elif case == "changed_proposal":
        finding["proposal"]["summary"] = "Concrete revised modification"
        finding["proposal_fingerprint"] = REVIEW.fingerprint(finding["proposal"])
        REVIEW.save_state(path, state)
    else:
        options += [f"--expected-{case.removeprefix('stale_')}-fingerprint", "stale"]
    before = path.read_bytes()
    _, code = REVIEW.record_decision_command(command(path, finding, *options))
    assert code in {2, 4}
    assert path.read_bytes() == before


@pytest.mark.parametrize("status", ["deferred", "queued", "waiting_evidence"])
@pytest.mark.parametrize("template", ["old", "current"])
def test_legacy_false_positive_closes_preserving_history(tmp_path, status, template):
    path, state, finding = setup_trigger_hint(tmp_path)
    finding.update(needs_facts=False, status=status)
    if template == "current":
        subject = finding["subject"]
        finding["proposal"] = REVIEW.proposal("复核真实漏用",
            f"{subject} 在相邻两个完整周均出现真实漏用；先核对是否为触发描述或执行遗漏，再形成修改建议。",
            [subject], skills=[subject])
        finding["proposal_fingerprint"] = REVIEW.fingerprint(finding["proposal"])
    finding["history"] = [{"event": "old_scan", "previous": {"decision": {"value": "rejected"}}}]
    finding["facts"] = [{"answer_summary": "Previous evidence", "recorded_at": "old"}]
    if status == "queued":
        REVIEW.ensure_in_queue(state, finding["id"])
    REVIEW.save_state(path, state)
    original = copy.deepcopy(finding)
    payload, code = REVIEW.record_decision_command(command(path, finding, "--facts-outcome", "close"))
    assert code == 0 and payload["next_status"] == "closed"
    saved = json.loads(path.read_text(encoding="utf-8"))
    current = saved["findings"][finding["id"]]
    assert current["decision"]["value"] == "closed_after_facts"
    assert current["facts"][:-1] == original["facts"]
    assert len(current["facts"]) == len(original["facts"]) + 1
    for key in original:
        if key not in {"status", "facts", "decision"}:
            assert current[key] == original[key]
    assert current["needs_facts"] is False
    assert saved["queue"] == [fid for fid in state["queue"] if fid != finding["id"]]
    assert saved["batches"] == state["batches"]
    assert {k:v for k,v in saved["findings"].items() if k != finding["id"]} == {
        k:v for k,v in state["findings"].items() if k != finding["id"]}


def test_legacy_false_positive_ignores_old_completed_batch_for_new_evidence(tmp_path):
    path, state, finding = setup_trigger_hint(tmp_path)
    finding.update(needs_facts=False, status="deferred")
    subject = finding["subject"]
    finding["proposal"] = REVIEW.proposal(
        "复核真实漏用",
        f"{subject} 在相邻两个完整周均出现真实漏用；先核对是否为触发描述或执行遗漏，再形成修改建议。",
        [subject], skills=[subject],
    )
    finding["proposal_fingerprint"] = REVIEW.fingerprint(finding["proposal"])
    state["batches"].append({
        "id": "old-batch",
        "status": "success",
        "items": [{
            "finding_id": finding["id"],
            "evidence_fingerprint": "old-evidence",
            "proposal_fingerprint": "old-proposal",
            "source_fingerprint": "old-source",
            "status": "success",
        }],
    })
    finding["history"] = [{
        "event": "old_scan",
        "previous": {
            "evidence_fingerprint": "old-evidence",
            "proposal_fingerprint": "old-proposal",
            "source_fingerprint": "old-source",
            "status": "completed",
            "execution": {"outcome": "success"},
        },
    }]
    REVIEW.save_state(path, state)

    payload, code = REVIEW.record_decision_command(
        command(path, finding, "--facts-outcome", "close")
    )

    assert code == 0 and payload["next_status"] == "closed"


def test_legacy_false_positive_rejects_matching_completed_batch(tmp_path):
    path, state, finding = setup_trigger_hint(tmp_path)
    finding.update(needs_facts=False, status="deferred")
    state["batches"].append({
        "id": "current-batch",
        "status": "success",
        "items": [{
            "finding_id": finding["id"],
            "evidence_fingerprint": finding["evidence_fingerprint"],
            "proposal_fingerprint": finding["proposal_fingerprint"],
            "source_fingerprint": finding["source_fingerprint"],
            "status": "success",
        }],
    })
    REVIEW.save_state(path, state)

    before = path.read_bytes()
    payload, code = REVIEW.record_decision_command(
        command(path, finding, "--facts-outcome", "close")
    )

    assert code == 2 and payload["status"] == "invalid_state"
    assert path.read_bytes() == before


@pytest.mark.parametrize("case", [
    "wait", "propose", "approve", "reject", "answer_approve", "answer_reject", "empty_answer",
    "revised", "changed_summary", "changed_target", "extra_proposal_key", "no_proposal",
    "other_source", "other_kind", "missing_needs_facts", "null_needs_facts", "numeric_needs_facts",
    "reviewed_proposal", "decision", "approval", "batch_id", "pending_revision",
    "requested_adjustment", "execution", "batch", "stale_evidence", "stale_proposal",
    "observed", "closed", "archived", "completed", "rejected",
    "history_approved", "history_executed", "history_reviewed", "inconsistent_fingerprint",
    "invalid_batches", "invalid_batch_items", "invalid_batch_item",
])
@pytest.mark.parametrize("template", ["old", "current"])
def test_legacy_false_positive_rejects_outside_exact_gate(tmp_path, case, template):
    path, state, finding = setup_trigger_hint(tmp_path)
    finding["needs_facts"] = False
    if template == "current":
        subject = finding["subject"]
        finding["proposal"] = REVIEW.proposal("复核真实漏用",
            f"{subject} 在相邻两个完整周均出现真实漏用；先核对是否为触发描述或执行遗漏，再形成修改建议。",
            [subject], skills=[subject])
        finding["proposal_fingerprint"] = REVIEW.fingerprint(finding["proposal"])
    options = ["--facts-outcome", "close"]
    if case in {"wait", "propose"}:
        options = ["--facts-outcome", case]
    elif case in {"approve", "reject"}:
        options += ["--classification", case]
    elif case in {"answer_approve", "answer_reject"}:
        options += ["--answer", "yes" if case == "answer_approve" else "no"]
    elif case == "empty_answer":
        options += ["--answer", " "]
    elif case == "revised":
        options += ["--revised-proposal-json", json.dumps(finding["proposal"], ensure_ascii=False)]
    elif case in {"changed_summary", "changed_target", "extra_proposal_key", "no_proposal"}:
        if case == "changed_summary": finding["proposal"]["summary"] += " revised"
        elif case == "changed_target": finding["proposal"]["targets"] = ["other"]
        elif case == "extra_proposal_key": finding["proposal"]["reviewed"] = True
        else: finding["proposal"] = None
        finding["proposal_fingerprint"] = REVIEW.fingerprint(finding["proposal"]) if finding["proposal"] else None
    elif case == "other_source": finding["source"] = "discovery"
    elif case == "other_kind": finding["kind"] = "other"
    elif case == "missing_needs_facts": finding.pop("needs_facts")
    elif case == "null_needs_facts": finding["needs_facts"] = None
    elif case == "numeric_needs_facts": finding["needs_facts"] = 0
    elif case in {"reviewed_proposal", "decision", "approval", "batch_id", "pending_revision", "requested_adjustment", "execution"}:
        finding[case] = {} if case != "batch_id" else "old-batch"
    elif case == "batch":
        state["batches"].append({"id": "old-batch", "status": "completed", "items": [{"finding_id": finding["id"]}]})
    elif case == "history_approved":
        finding["history"] = [{"event": "old_scan", "previous": {"decision": {"value": "approved"}}}]
    elif case == "history_executed":
        finding["history"] = [{"event": "old_scan", "previous": {"execution": {"outcome": "success"}}}]
    elif case == "history_reviewed":
        finding["history"] = [{"event": "old_scan", "previous": {"reviewed_proposal": {}}}]
    elif case == "inconsistent_fingerprint": finding["proposal_fingerprint"] = "not-the-default-proposal-hash"
    elif case == "invalid_batches": state["batches"] = {}
    elif case == "invalid_batch_items": state["batches"] = [{"id": "bad", "status": "completed", "items": {}}]
    elif case == "invalid_batch_item": state["batches"] = [{"id": "bad", "status": "completed", "items": [None]}]
    elif case.startswith("stale_"):
        options += [f"--expected-{case.removeprefix('stale_')}-fingerprint", "stale"]
    else:
        finding["status"] = case
    if case.startswith("invalid_batch"):
        path.write_text(json.dumps(state), encoding="utf-8")
    else:
        REVIEW.save_state(path, state)
    before = path.read_bytes()
    payload, code = REVIEW.record_decision_command(command(path, finding, *options))
    expected = 3 if case.startswith("invalid_batch") else (4 if case.startswith("stale_") else 2)
    assert code == expected, payload
    assert path.read_bytes() == before


@pytest.mark.skipif(not os.environ.get("WEEKLY_REVIEW_BASELINE"), reason="optional baseline comparison")
@pytest.mark.parametrize("status", ["facts", "awaiting_decision", "revising", "retry_pending", "approved", "execution_pending"])
def test_other_states_keep_original_behavior(tmp_path, monkeypatch, status):
    # Exercise original branches without changing their semantics or accepted states.
    # The original imports a sibling helper; load identical baseline beside helper instead.
    import shutil
    original_path = tmp_path / "original" / SCRIPT.name
    original_path.parent.mkdir()
    shutil.copyfile(Path(os.environ["WEEKLY_REVIEW_BASELINE"]), original_path)
    shutil.copyfile(SCRIPT.with_name("weekly_discovery.py"), original_path.with_name("weekly_discovery.py"))
    spec = importlib.util.spec_from_file_location("original_review_gate", original_path)
    original = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(original)
    monkeypatch.setattr(original, "now_iso", lambda: "2026-11-01T12:00:00+08:00")
    monkeypatch.setattr(REVIEW, "now_iso", original.now_iso)
    path, state, finding = setup_trigger_hint(tmp_path)
    finding.update(needs_facts=False, status=status)
    REVIEW.save_state(path, state)
    other = tmp_path / "original-state.json"
    shutil.copyfile(path, other)
    expected = original.record_decision_command(command(other, finding, "--facts-outcome", "close"))
    actual = REVIEW.record_decision_command(command(path, finding, "--facts-outcome", "close"))
    assert actual == expected
    assert json.loads(path.read_text(encoding="utf-8")) == json.loads(other.read_text(encoding="utf-8"))
