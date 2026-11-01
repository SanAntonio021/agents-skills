import copy
import json
from pathlib import Path
import shutil
import subprocess
import pytest

import test_run_weekly_skill_review as harness

REVIEW = harness.REVIEW


@pytest.mark.parametrize("route", ["facts", "adjust"])
@pytest.mark.parametrize("drift", [None, "source", "evidence", "proposal"])
def test_reviewed_proposal_rescan_and_real_drift(route, drift):
    case = harness.WeeklySkillReviewTests()
    case.setUp()
    try:
        original = case.observation("agent-rules", needs_facts=route == "facts")
        case.make_skill("ieee")
        case.seed([original])
        question, _ = case.invoke("next-question")
        revised = {"action": "modify", "summary": "Repair both actual targets",
                   "targets": ["agent-rules", "ieee"], "requires_runtime_sync": True}
        args = ["record-decision", "--finding-id", original["id"],
                "--expected-evidence-fingerprint", question["expected_evidence_fingerprint"],
                "--expected-proposal-fingerprint", question["expected_proposal_fingerprint"],
                "--answer", "Verified concrete repair", "--revised-proposal-json", json.dumps(revised)]
        args += ["--facts-outcome", "propose"] if route == "facts" else ["--classification", "adjust"]
        _, code = case.invoke(*args)
        assert code == 0
        question, _ = case.invoke("next-question")
        _, code = case.invoke("record-decision", "--finding-id", original["id"],
            "--expected-evidence-fingerprint", question["expected_evidence_fingerprint"],
            "--expected-proposal-fingerprint", question["expected_proposal_fingerprint"],
            "--answer", "approve", "--classification", "approve")
        assert code == 0
        state = case.load()
        item = state["findings"][original["id"]]
        assert item["source_fingerprint"] == REVIEW.source_fingerprint(case.skills, ["agent-rules", "ieee"])
        assert item["reviewed_proposal"]["scan_baseline"]["proposal_fingerprint"] == original["proposal_fingerprint"]
        approval = copy.deepcopy(item["decision"])
        concrete = copy.deepcopy(item["proposal"])
        REVIEW.merge_observations(state, [copy.deepcopy(original)], "2026-10-31", skills_root=case.skills)
        assert item["status"] == "approved" and item["proposal"] == concrete
        assert item["decision"] == approval
        case.save(state)
        confirmation, code = case.invoke("prepare-execution")
        assert code == 0
        ready, code = case.invoke("prepare-execution", "--decision", "approve",
            "--batch-id", confirmation["batch_id"],
            "--expected-batch-fingerprint", confirmation["batch_fingerprint"])
        assert code == 0 and ready["status"] == "ready"
        state = case.load()
        observation = copy.deepcopy(original)
        if drift == "source":
            (case.skills / "ieee" / "SKILL.md").write_text("real change", encoding="utf-8")
        elif drift == "evidence":
            observation["evidence_fingerprint"] = REVIEW.fingerprint({"new": "evidence"})
        elif drift == "proposal":
            observation["proposal"]["summary"] = "Changed scanner recommendation"
            observation["proposal_fingerprint"] = REVIEW.fingerprint(observation["proposal"])
        REVIEW.merge_observations(state, [observation], "2026-10-31", skills_root=case.skills)
        item = state["findings"][original["id"]]
        if drift:
            assert "decision" not in item and "reviewed_proposal" not in item
            assert state["batches"][-1]["status"] == "stale"
            previous = item["history"][-1]["previous"]
            assert previous["decision"] == approval and previous["proposal"] == concrete
        else:
            assert item["status"] == "execution_pending" and item["decision"] == approval
            assert state["batches"][-1]["status"] == "ready"
    finally:
        case.tearDown()


def test_unbound_proposal_change_still_invalidates():
    case = harness.WeeklySkillReviewTests()
    case.setUp()
    try:
        observation = case.observation("alpha")
        state = REVIEW.new_state()
        REVIEW.merge_observations(state, [observation], "2026-10-31")
        current = state["findings"][observation["id"]]
        current.update(status="approved", decision={"value": "approved"})
        changed = copy.deepcopy(observation)
        changed["proposal"]["summary"] = "new material plan"
        changed["proposal_fingerprint"] = REVIEW.fingerprint(changed["proposal"])
        REVIEW.merge_observations(state, [changed], "2026-10-31", skills_root=case.skills)
        assert "decision" not in current
    finally:
        case.tearDown()


@pytest.mark.parametrize("publication", ["unknown", "blocked", "failed", "verified"])
def test_components_and_publication_are_independent(tmp_path, publication):
    validation = {"usage": {"valid": True}, "hygiene": {"valid": True},
                  "upstream": {"valid": True, "checks_complete": False, "check_reasons": ["fetch failed"]}}
    parts = REVIEW.audit_components(validation, usage_complete=True, usage_reasons=[])
    assert parts["usage"]["complete"] and parts["hygiene"]["complete"]
    assert not parts["upstream"]["complete"] and parts["upstream"]["reasons"] == ["fetch failed"]
    state = REVIEW.new_state()
    if publication != "unknown":
        state["findings"]["one"] = {"id": "one", "execution": {
            "outcome": "success" if publication == "verified" else publication,
            "sync_status": "verified", "remote_sha": "a" * 40, "details": "recorded result"}}
    result = REVIEW.publication_status(state)
    assert result["status"] == publication and result["known"] == (publication != "unknown")
    snapshot = REVIEW.build_dashboard_snapshot({}, state, date="2026-10-31", complete=True,
        streak_reset_reason=None, components=parts, publication=result)
    assert snapshot["complete"] is True and snapshot["publication"]["status"] == publication
    assert snapshot["components"]["upstream"]["complete"] is False


def test_external_report_readonly_and_unsupported_is_unknown(tmp_path):
    path = tmp_path / "receipt.json"
    receipt = {"checked_at": "2026-10-31T14:00:00+08:00", "unfinished": [
        {"object": "OfficeCLI source and runtime publication", "stage": "not published",
         "blocker": "helper schema unsupported"}]}
    path.write_text(json.dumps(receipt), encoding="utf-8")
    before = path.read_bytes()
    result = REVIEW.publication_status({}, [path])
    assert result["status"] == "blocked" and path.read_bytes() == before
    path.write_text("{}", encoding="utf-8")
    assert REVIEW.publication_status({}, [path])["status"] == "unknown"
    path.write_text("{broken", encoding="utf-8")
    assert REVIEW.publication_status({}, [path])["status"] == "unknown"


def test_freshness_and_dashboard_privacy():
    fresh = REVIEW.report_freshness({"date": "2026-10-31", "generated_at": "2026-10-31T14:00:00+08:00"},
        date="2026-10-31", reused=True)
    assert fresh["status"] == "report_day" and fresh["reused"] and isinstance(fresh["age_seconds"], float)
    assert REVIEW.report_freshness({}, date="2026-10-31", reused=False)["status"] == "unknown"
    safe = REVIEW.dashboard_checks({"usage": {"report_ref": "usage.json", "reasons": [r"bad C:\private\session.json"]}}, {})
    assert "private" not in json.dumps(safe) and "report_ref" not in json.dumps(safe)


@pytest.mark.parametrize("upstream_ok", [False, True])
@pytest.mark.parametrize("external_blocked", [False, True])
def test_scan_components_exit_code_dashboard_and_existing_external_receipt(tmp_path, monkeypatch, upstream_ok, external_blocked):
    skills, reports = tmp_path / "skills", tmp_path / "reports"
    skills.mkdir()
    reports.mkdir()
    stamp = "2026-10-31T14:00:00+08:00"
    summaries = {
        "usage": {"version": REVIEW.USAGE_AUDIT_VERSION, "date": "2026-10-31", "generated_at": stamp,
                  "warnings": {}, "skill_inventory": [], "classifications": {},
                  "configuration": {"count_unit": "request"},
                  "window": {"start": "2026-10-24T14:00:00+08:00", "end": stamp}},
        "hygiene": {"version": "flat-skill-tree-v1", "date": "2026-10-31", "generated_at": stamp, "findings": {}},
        "upstream": {"schema_version": 1, "date": "2026-10-31", "generated_at": stamp,
                     "sources": [], "check_error_count": 0 if upstream_ok else 1},
    }
    paths = {name: reports / (name + ".json") for name in summaries}
    for name, payload in summaries.items():
        paths[name].write_text(json.dumps(payload), encoding="utf-8")
    commands = {name: {"exit_code": 0, "summary_changed": True} for name in summaries}
    monkeypatch.setattr(REVIEW, "run_audits", lambda **_: (commands, paths))
    argv = ["scan", "--agents-root", str(tmp_path), "--skills-root", str(skills),
            "--reports-root", str(reports), "--state", str(reports / "test-state.json"),
            "--date", "2026-10-31", "--reuse-reports"]
    if external_blocked:
        # Read a pre-existing real receipt rather than inventing an OfficeCLI
        # publication outcome. This file belongs to the host, not the fixture.
        existing = Path(__file__).resolve().parents[3] / "reports/skill-upstream/2026-11-01/final-status.json"
        if not existing.is_file():
            pytest.skip("existing external OfficeCLI receipt is unavailable")
        before = existing.read_bytes()
        argv += ["--publication-report", str(existing)]
    payload, code = REVIEW.scan_command(REVIEW.parse_args(argv))
    assert code == (0 if upstream_ok else 2) and payload["complete"] is upstream_ok
    assert payload["components"]["usage"]["complete"] is True
    assert payload["components"]["upstream"]["complete"] is upstream_ok
    assert payload["components"]["hygiene"]["complete"] is True
    assert payload["publication"]["status"] == ("blocked" if external_blocked else "unknown")
    snapshot = json.loads((reports / "usage/dashboard/data/2026-10-31.json").read_text(encoding="utf-8"))
    report = json.loads((reports / "2026-10-31/weekly-review.json").read_text(encoding="utf-8"))
    saved, _ = REVIEW.load_state(reports / "test-state.json")
    assert report["components"] == payload["components"] == saved["runs"][-1]["components"]
    assert snapshot["publication"]["status"] == payload["publication"]["status"]
    html = (reports / "usage/dashboard/index.html").read_text(encoding="utf-8")
    assert "分项完整性与发布验收" in html and "__SKILL_USAGE_DATA__" not in html
    assert "D:\\\\BaiduSyncdisk" not in html
    if external_blocked:
        assert existing.read_bytes() == before


def test_offline_dashboard_javascript_dom_smoke(tmp_path):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js unavailable for offline dashboard DOM smoke")
    template = REVIEW.DEFAULT_DASHBOARD_TEMPLATE.read_text(encoding="utf-8")
    script = template.split("<script>", 1)[1].split("</script>", 1)[0]
    # Run the actual offline JS with minimal DOM objects; this validates text,
    # missing legacy fields and week switching, not browser layout.
    harness_js = r'''
const vm = require("node:vm");
class Element {
  constructor() { this.children = []; this.style = {}; this.textContent = ""; }
  append(...children) { this.children.push(...children); }
  replaceChildren(...children) { this.children = children; }
  setAttribute() {}
  addEventListener(name, fn) { this[name] = fn; }
}
const elements = new Map();
const document = {getElementById(id) { if (!elements.has(id)) elements.set(id, new Element()); return elements.get(id); },
  createElement() {return new Element();}, createDocumentFragment() {return new Element();}, querySelectorAll() {return [];} };
const context = vm.createContext({document, Intl, Date, Number, String, Array, Set, Math});
const script = SCRIPT;
vm.runInContext(script, context);
function text(node) {return [node.textContent, ...node.children.map(text)].join(" ");}
const initial = text(elements.get("checksList"));
if (!initial.includes("触发统计：完整") || !initial.includes("上游检查：不完整") || !initial.includes("发布验收：已知：阻断")) throw Error(initial);
elements.get("weekSelect").change({target:{value:"1"}});
const legacy = text(elements.get("checksList"));
if (!legacy.includes("触发统计：未知") || !legacy.includes("发布验收：未知")) throw Error(legacy);
console.log("offline DOM smoke passed: components, publication, legacy week switch");
'''
    snapshots = [{"complete": False, "components": {"usage": {"complete": True},
        "upstream": {"complete": False, "reasons": ["fetch failed"]}, "hygiene": {"complete": True}},
        "publication": {"status": "blocked", "known": True}}, {"complete": True}]
    javascript = script.replace("__SKILL_USAGE_DATA__", json.dumps(snapshots))
    path = tmp_path / "dashboard-smoke.cjs"
    path.write_text(harness_js.replace("SCRIPT", json.dumps(javascript)), encoding="utf-8")
    result = subprocess.run([node, str(path)], capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr


@pytest.fixture
def selected_case():
    case = harness.WeeklySkillReviewTests()
    case.setUp()
    try:
        observations = [case.observation(f"repair-{i}") for i in range(6)]
        pending = case.observation("unresolved", needs_facts=True)
        state = case.seed(observations + [pending])
        for observation in observations:
            finding = state["findings"][observation["id"]]
            finding["status"] = "approved"
            finding["decision"] = {"value": "approved", **{
                key: finding[key] for key in ("evidence_fingerprint", "proposal_fingerprint")}}
        state["findings"][pending["id"]]["status"] = "facts"
        state["queue"].append(pending["id"])
        case.save(state)
        yield case, observations, pending
    finally:
        case.tearDown()


def select_findings(case, observations):
    return case.invoke("prepare-execution", *[
        argument for item in observations for argument in ("--finding-id", item["id"])])


def test_precise_six_batch_preserves_pending_and_approves_by_batch(selected_case):
    case, observations, pending = selected_case
    before = case.load()
    default, code = case.invoke("prepare-execution")
    assert code == 2 and default["status"] == "questions_pending"
    confirmation, code = select_findings(case, observations)
    assert code == 0 and confirmation["approved_count"] == 6
    assert set(confirmation["selected_finding_ids"]) == {item["id"] for item in observations}
    after = case.load()
    assert after["queue"] == before["queue"] and after["findings"] == before["findings"]
    repeated, code = select_findings(case, list(reversed(observations)))
    assert code == 0 and repeated["batch_id"] == confirmation["batch_id"]
    saved_bytes = case.state_path.read_bytes()
    wrong, code = case.invoke("prepare-execution", "--decision", "approve",
        "--batch-id", confirmation["batch_id"], "--expected-batch-fingerprint", "bad")
    assert code == 4 and wrong["status"] == "stale_fingerprint"
    assert case.state_path.read_bytes() == saved_bytes
    ready, code = case.invoke("prepare-execution", "--decision", "approve",
        "--batch-id", confirmation["batch_id"],
        "--expected-batch-fingerprint", confirmation["batch_fingerprint"])
    assert code == 0 and len(ready["items"]) == 6
    after = case.load()
    assert after["findings"][pending["id"]] == before["findings"][pending["id"]]
    assert after["queue"] == before["queue"]


@pytest.mark.parametrize("invalid", ["unknown", "pending", "decision", "proposal", "source", "evidence"])
def test_selection_rejects_invalid_without_writes(selected_case, invalid):
    case, observations, pending = selected_case
    selected = observations[:1]
    state = case.load()
    finding = state["findings"][selected[0]["id"]]
    if invalid == "unknown":
        selected = [{"id": "missing"}]
    elif invalid == "pending":
        selected = [pending]
    elif invalid == "decision":
        finding["decision"]["proposal_fingerprint"] = "changed"
    elif invalid == "proposal":
        finding["proposal"]["summary"] = "unapproved change"
    elif invalid == "evidence":
        finding["evidence_fingerprint"] = "new evidence"
    else:
        (case.skills / "repair-0" / "SKILL.md").write_text("actual drift", encoding="utf-8")
    case.save(state)
    before = case.state_path.read_bytes()
    result, code = select_findings(case, selected)
    assert code in (2, 4)
    assert result["status"] in {"invalid_selection", "stale_fingerprint"}
    assert case.state_path.read_bytes() == before


def change_selected_proposal(case, item, **changes):
    state = case.load()
    finding = state["findings"][item["id"]]
    finding["proposal"].update(changes)
    finding["proposal_fingerprint"] = REVIEW.fingerprint(finding["proposal"])
    finding["decision"]["proposal_fingerprint"] = finding["proposal_fingerprint"]
    finding["source_fingerprint"] = REVIEW.source_fingerprint(case.skills, finding["proposal"]["targets"])
    case.save(state)


def test_selection_dependencies_and_overlap(selected_case):
    case, observations, pending = selected_case
    first, second = observations[:2]
    change_selected_proposal(case, first, dependencies=[pending["id"]])
    before = case.state_path.read_bytes()
    blocked, code = select_findings(case, [first])
    assert code == 2 and blocked["status"] == "blocked_dependency"
    assert case.state_path.read_bytes() == before
    # Explicit dependency order must win even when targets overlap and IDs sort differently.
    change_selected_proposal(case, first, dependencies=[second["id"]], targets=["repair-1"])
    confirmation, code = select_findings(case, [first, second])
    assert code == 0
    batch = case.load()["batches"][-1]
    assert batch["items"][0]["finding_id"] == second["id"]
    assert batch["items"][1]["blocked_by"] == [second["id"]]
    assert confirmation["approved_count"] == 2


def test_selection_cycle_rejected(selected_case):
    case, observations, _ = selected_case
    first, second = observations[:2]
    change_selected_proposal(case, first, dependencies=[second["id"]])
    change_selected_proposal(case, second, dependencies=[first["id"]])
    before = case.state_path.read_bytes()
    result, code = select_findings(case, [first, second])
    assert code == 2 and result["status"] == "blocked_dependency"
    assert case.state_path.read_bytes() == before


def test_selection_does_not_reuse_unrelated_batch_and_blocks_active_overlap(selected_case):
    case, observations, _ = selected_case
    first, second, third = observations[:3]
    initial, code = select_findings(case, [first])
    assert code == 0
    separate, code = select_findings(case, [second])
    assert code == 0 and initial["batch_id"] != separate["batch_id"]
    change_selected_proposal(case, third, targets=["repair-0/SKILL.md"])
    before = case.state_path.read_bytes()
    conflict, code = select_findings(case, [third])
    assert code == 2 and conflict["status"] == "blocked_batch_conflict"
    assert case.state_path.read_bytes() == before
    conflict, code = select_findings(case, [first, second])
    assert code == 2 and conflict["status"] == "blocked_batch_conflict"


def test_completed_external_dependency_allows_selection(selected_case):
    case, observations, pending = selected_case
    change_selected_proposal(case, observations[0], dependencies=[pending["id"]])
    state = case.load()
    state["findings"][pending["id"]]["status"] = "completed"
    case.save(state)
    result, code = select_findings(case, observations[:1])
    assert code == 0 and result["approved_count"] == 1


@pytest.mark.parametrize("drift", ["source", "evidence_fingerprint", "proposal_fingerprint"])
def test_selected_batch_approval_rechecks_drift(selected_case, drift):
    case, observations, pending = selected_case
    confirmation, code = select_findings(case, observations[:1])
    assert code == 0
    state = case.load()
    pending_before = copy.deepcopy(state["findings"][pending["id"]])
    if drift == "source":
        (case.skills / "repair-0" / "SKILL.md").write_text("post-prepare drift", encoding="utf-8")
    else:
        state["findings"][observations[0]["id"]][drift] = "post-prepare drift"
        case.save(state)
    result, code = case.invoke("prepare-execution", "--decision", "approve",
        "--batch-id", confirmation["batch_id"],
        "--expected-batch-fingerprint", confirmation["batch_fingerprint"])
    assert code == 4 and result["status"] == "blocked_source_drift"
    assert case.load()["findings"][pending["id"]] == pending_before


def test_selector_is_only_for_batch_creation(selected_case):
    case, observations, _ = selected_case
    before = case.state_path.read_bytes()
    result, code = case.invoke("prepare-execution", "--finding-id", observations[0]["id"],
        "--decision", "approve")
    assert code == 2 and result["status"] == "invalid_request"
    assert case.state_path.read_bytes() == before
