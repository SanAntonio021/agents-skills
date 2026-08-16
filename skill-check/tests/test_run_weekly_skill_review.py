from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = SKILL_ROOT / "scripts" / "run_weekly_skill_review.py"


def load_module():
    spec = importlib.util.spec_from_file_location("run_weekly_skill_review", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


REVIEW = load_module()


class WeeklySkillReviewTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.skills = self.root / "skills"
        self.skills.mkdir()
        self.reports = self.root / "reports"
        self.state_path = self.reports / "weekly-review-state.json"
        self.helper = self.root / "Invoke-CcSwitchSkillSync.ps1"
        self.helper.write_text("helper-v1\n", encoding="utf-8")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def make_skill(self, name: str) -> None:
        path = self.skills / name
        path.mkdir(parents=True, exist_ok=True)
        skill_md = path / "SKILL.md"
        if not skill_md.exists():
            skill_md.write_text(
                f"---\nname: {name}\ndescription: test {name}\n---\n\n# {name}\n",
                encoding="utf-8",
            )

    def observation(
        self,
        name: str,
        *,
        severity: str = "medium",
        evidence: object | None = None,
        needs_facts: bool = False,
        dependencies: tuple[str, ...] = (),
        requires_runtime_sync: bool = False,
        source: str = "usage",
        purpose: str | None = None,
    ) -> dict:
        self.make_skill(name)
        return REVIEW.make_observation(
            kind="test_finding",
            source=source,
            subject=name,
            purpose=purpose or "test-purpose",
            severity=severity,
            title=f"{name} finding",
            evidence=evidence if evidence is not None else {"name": name, "v": 1},
            evidence_summary=f"Evidence for {name}",
            suggested_proposal=REVIEW.proposal(
                "modify",
                f"Modify {name}",
                [name],
                skills=[name],
                dependencies=dependencies,
                requires_runtime_sync=requires_runtime_sync,
            ),
            report_refs=["test/summary.json"],
            needs_facts=needs_facts,
            fact_questions=("事实问题一", "事实问题二") if needs_facts else (),
            skills_root=self.skills,
        )

    def save(self, state: dict) -> None:
        REVIEW.save_state(self.state_path, state)

    def load(self) -> dict:
        return json.loads(self.state_path.read_text(encoding="utf-8"))

    def invoke(self, command: str, *extra: str):
        argv = [command, "--state", str(self.state_path), *extra]
        if command in {"prepare-execution", "record-decision"}:
            argv.extend(["--skills-root", str(self.skills)])
        if command == "prepare-execution":
            argv.extend(
                [
                    "--reports-root",
                    str(self.reports),
                    "--sync-helper",
                    str(self.helper),
                    "--date",
                    "2026-08-15",
                ]
            )
        args = REVIEW.parse_args(argv)
        handlers = {
            "next-question": REVIEW.next_question_command,
            "record-decision": REVIEW.record_decision_command,
            "prepare-execution": REVIEW.prepare_execution_command,
            "record-execution": REVIEW.record_execution_command,
        }
        return handlers[command](args)

    def git(self, *arguments: str) -> str:
        completed = subprocess.run(
            ["git", "-C", str(self.skills), *arguments],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=True,
        )
        return completed.stdout.strip()

    def initialize_skills_git(self, *skill_names: str) -> str:
        self.git("init", "--quiet")
        self.git("config", "user.name", "Weekly Review Test")
        self.git("config", "user.email", "weekly-review@example.invalid")
        paths = [f"{name}/SKILL.md" for name in skill_names]
        self.git("add", "--", *paths)
        self.git("commit", "--quiet", "-m", "initial skills")
        return self.git("rev-parse", "HEAD")

    def seed(self, observations: list[dict]) -> dict:
        state = REVIEW.new_state()
        REVIEW.merge_observations(state, observations, "2026-08-15")
        self.save(state)
        return state

    @staticmethod
    def valid_usage(skill: str = "alpha") -> dict:
        return {
            "version": "skill-usage-audit-v1",
            "date": "2026-08-15",
            "classifications": {
                "已用": [],
                "历史内未见使用": [{"skill": skill}],
                "疑似漏用": [],
                "可能冗余": [],
            },
            "warnings": {
                "missing_roots": [],
                "parse_error_count": 0,
                "missing_field_count": 0,
                "hygiene_summary_warning": None,
            },
            "configuration": {"root": "fixture"},
            "skill_inventory": [{"skill": skill}],
        }

    def test_four_complete_weeks_and_reset_conditions(self) -> None:
        state = REVIEW.new_state()
        usage = self.valid_usage()
        scope = REVIEW.fingerprint({"scope": "same"})
        counts = []
        for week in range(1, 5):
            result, reason = REVIEW.update_unseen_streaks(
                state,
                usage,
                complete=True,
                scope_value=scope,
                date=f"2026-08-{week:02d}",
            )
            self.assertIsNone(reason)
            counts.append(result.get("alpha", 0))
        self.assertEqual(counts, [1, 2, 3, 4])
        observations = REVIEW.extract_usage_observations(usage, "usage/summary.json", self.skills, {"alpha": 4})
        self.assertTrue(any(item["kind"] == "unseen_four_complete_weeks" for item in observations))

        used = self.valid_usage()
        used["classifications"]["已用"] = [{"skill": "alpha"}]
        result, reason = REVIEW.update_unseen_streaks(
            state, used, complete=True, scope_value=scope, date="2026-08-05"
        )
        self.assertIsNone(reason)
        self.assertEqual(result.get("alpha"), 0)

        result, reason = REVIEW.update_unseen_streaks(
            state, usage, complete=False, scope_value=scope, date="2026-08-06"
        )
        self.assertEqual(reason, "incomplete_scan")
        self.assertEqual(result, {})

        result, reason = REVIEW.update_unseen_streaks(
            state,
            usage,
            complete=True,
            scope_value=REVIEW.fingerprint({"scope": "changed"}),
            date="2026-08-07",
        )
        self.assertEqual(reason, "scope_changed")
        self.assertEqual(result, {})
        result, reason = REVIEW.update_unseen_streaks(
            state,
            usage,
            complete=True,
            scope_value=REVIEW.fingerprint({"scope": "changed"}),
            date="2026-08-07",
        )
        self.assertIsNone(reason)
        self.assertEqual(result.get("alpha"), 0)

    def test_non_text_user_records_do_not_make_usage_incomplete(self) -> None:
        usage = self.valid_usage()
        usage["warnings"]["non_text_user_record_count"] = 8
        usage["warnings"]["non_text_user_records"] = [
            {"root_id": "codex-archived", "path": "sample.jsonl", "line": 1}
        ]
        complete, reasons = REVIEW.usage_evidence_complete(usage)
        self.assertTrue(complete)
        self.assertEqual(reasons, [])

    def test_queue_limit_retention_and_critical_priority(self) -> None:
        observations = [self.observation(f"routine-{index}") for index in range(4)]
        state = REVIEW.new_state()
        first = REVIEW.merge_observations(state, observations, "2026-08-15")
        self.assertEqual(first["queued_routine"], 3)
        self.assertEqual(first["deferred_routine"], 1)
        self.assertEqual(len(state["queue"]), 3)

        same_week = REVIEW.merge_observations(state, observations, "2026-08-15")
        self.assertEqual(same_week["queued_routine"], 0)
        self.assertEqual(len(state["queue"]), 3)

        answered = observations[0]
        state["findings"][answered["id"]]["status"] = "rejected"
        state["queue"].remove(answered["id"])
        changed_answered = self.observation(answered["subject"], evidence={"v": 2})
        requeued = REVIEW.merge_observations(
            state, [changed_answered, *observations[1:]], "2026-08-15"
        )
        self.assertEqual(requeued["requeued_routine"], 1)
        self.assertEqual(state["findings"][answered["id"]]["status"], "queued")

        second = REVIEW.merge_observations(state, observations, "2026-08-16")
        self.assertEqual(second["queued_routine"], 1)
        self.assertEqual(len(state["queue"]), 4)

        critical = self.observation("critical", severity="critical")
        REVIEW.merge_observations(state, [critical], "2026-08-17")
        self.assertEqual(state["queue"][0], critical["id"])

    def test_failed_source_keeps_old_finding_until_source_is_authoritative(self) -> None:
        old = self.observation("old", source="hygiene")
        state = REVIEW.new_state()
        REVIEW.merge_observations(state, [old], "2026-08-15")
        finding = state["findings"][old["id"]]
        finding["status"] = "approved"
        state["queue"].remove(old["id"])

        REVIEW.merge_observations(state, [], "2026-08-16", authoritative_sources={"usage"})
        self.assertEqual(finding["status"], "approved")
        REVIEW.merge_observations(state, [], "2026-08-17", authoritative_sources={"hygiene"})
        self.assertEqual(finding["status"], "resolved")

    def test_unchanged_deduplicates_and_changed_fingerprint_invalidates_approval(self) -> None:
        original = self.observation("alpha", severity="high", evidence={"v": 1})
        state = REVIEW.new_state()
        REVIEW.merge_observations(state, [original], "2026-08-15")
        finding = state["findings"][original["id"]]
        finding["status"] = "approved"
        finding["decision"] = {"value": "approved"}
        state["queue"].remove(original["id"])
        state["batches"].append(
            {
                "id": "batch-old",
                "status": "awaiting_confirmation",
                "items": [{"finding_id": original["id"]}],
            }
        )
        state["batches"].append(
            {
                "id": "batch-retry",
                "status": "partial_failed",
                "items": [{"finding_id": original["id"]}],
            }
        )
        REVIEW.merge_observations(state, [original], "2026-08-16")
        self.assertEqual(finding["status"], "approved")
        self.assertEqual(len(finding["history"]), 0)

        changed = self.observation("alpha", severity="high", evidence={"v": 2})
        REVIEW.merge_observations(state, [changed], "2026-08-17")
        self.assertEqual(finding["status"], "queued")
        self.assertNotIn("decision", finding)
        self.assertTrue(all(batch["status"] == "stale" for batch in state["batches"]))
        self.assertEqual(
            finding["history"][-1]["previous"]["evidence_fingerprint"],
            original["evidence_fingerprint"],
        )

    def test_stale_decision_refuses_write_and_preserves_state_bytes(self) -> None:
        observation = self.observation("alpha", severity="high")
        self.seed([observation])
        payload, _ = self.invoke("next-question")
        before = self.state_path.read_bytes()
        result, code = self.invoke(
            "record-decision",
            "--finding-id",
            observation["id"],
            "--expected-evidence-fingerprint",
            "stale",
            "--expected-proposal-fingerprint",
            payload["expected_proposal_fingerprint"],
            "--answer",
            "批准",
        )
        self.assertEqual(code, 4)
        self.assertEqual(result["status"], "stale_fingerprint")
        self.assertEqual(before, self.state_path.read_bytes())

    def test_null_proposal_fingerprint_and_rejected_finding_reappearance(self) -> None:
        self.make_skill("no-proposal")
        observation = REVIEW.make_observation(
            kind="test_finding",
            source="usage",
            subject="no-proposal",
            purpose="collect-facts",
            severity="high",
            title="No proposal yet",
            evidence_summary="Facts are incomplete",
            evidence={"v": 1},
            suggested_proposal=None,
            report_refs=["test/summary.json"],
            skills_root=self.skills,
        )
        self.seed([observation])
        question, _ = self.invoke("next-question")
        self.assertIsNone(question["expected_proposal_fingerprint"])
        result, code = self.invoke(
            "record-decision",
            "--finding-id",
            observation["id"],
            "--expected-evidence-fingerprint",
            question["expected_evidence_fingerprint"],
            "--expected-proposal-fingerprint",
            "none",
            "--answer",
            "不批准",
        )
        self.assertEqual(code, 0)
        self.assertEqual(result["decision"], "rejected")

        state = self.load()
        REVIEW.merge_observations(state, [observation], "2026-08-16")
        self.assertEqual(state["findings"][observation["id"]]["status"], "rejected")
        changed = dict(observation)
        changed["evidence_fingerprint"] = REVIEW.fingerprint({"v": 2})
        REVIEW.merge_observations(state, [changed], "2026-08-17")
        self.assertEqual(state["findings"][observation["id"]]["status"], "queued")

    def test_facts_have_two_questions_and_three_exits(self) -> None:
        observation = self.observation("facts", needs_facts=True)
        self.seed([observation])
        first, _ = self.invoke("next-question")
        self.assertEqual(first["question_type"], "fact")
        self.invoke(
            "record-decision",
            "--finding-id",
            observation["id"],
            "--expected-evidence-fingerprint",
            first["expected_evidence_fingerprint"],
            "--expected-proposal-fingerprint",
            first["expected_proposal_fingerprint"],
            "--answer",
            "事实一",
        )
        second, _ = self.invoke("next-question")
        self.assertNotEqual(first["question"], second["question"])
        result, _ = self.invoke(
            "record-decision",
            "--finding-id",
            observation["id"],
            "--expected-evidence-fingerprint",
            second["expected_evidence_fingerprint"],
            "--expected-proposal-fingerprint",
            second["expected_proposal_fingerprint"],
            "--answer",
            "事实二",
        )
        self.assertEqual(result["next_status"], "waiting_evidence")

        for outcome, expected in (("close", "closed"), ("wait", "waiting_evidence"), ("propose", "awaiting_decision")):
            observation = self.observation(f"facts-{outcome}", needs_facts=True)
            self.seed([observation])
            question, _ = self.invoke("next-question")
            extra = ["--facts-outcome", outcome]
            if outcome == "propose":
                extra.extend(
                    [
                        "--revised-proposal-json",
                        json.dumps(
                            {
                                "action": "revised",
                                "summary": "修订后的建议",
                                "targets": [observation["subject"]],
                            },
                            ensure_ascii=False,
                        ),
                    ]
                )
            result, _ = self.invoke(
                "record-decision",
                "--finding-id",
                observation["id"],
                "--expected-evidence-fingerprint",
                question["expected_evidence_fingerprint"],
                "--expected-proposal-fingerprint",
                question["expected_proposal_fingerprint"],
                "--answer",
                "事实回答",
                *extra,
            )
            if outcome == "propose":
                self.assertEqual(result["next_status"], expected)
            else:
                self.assertEqual(result["next_status"], expected)

        for answer, expected in (("批准", "approved"), ("不批准", "rejected")):
            observation = self.observation(f"facts-{expected}", needs_facts=True)
            self.seed([observation])
            question, _ = self.invoke("next-question")
            result, _ = self.invoke(
                "record-decision",
                "--finding-id",
                observation["id"],
                "--expected-evidence-fingerprint",
                question["expected_evidence_fingerprint"],
                "--expected-proposal-fingerprint",
                question["expected_proposal_fingerprint"],
                "--answer",
                answer,
            )
            self.assertEqual(result["next_status"], expected)

    def test_natural_language_decision_classification(self) -> None:
        self.assertEqual(REVIEW.classify_answer("行，可以执行"), "approve")
        self.assertEqual(REVIEW.classify_answer("暂不批准"), "reject")
        self.assertEqual(REVIEW.classify_answer("没看懂"), "explain")
        self.assertEqual(REVIEW.classify_answer("可以，但只改触发边界"), "adjust")
        self.assertEqual(
            REVIEW.normalize_targets(["alpha/SKILL.md", "C:/outside", "/outside", "../outside"]),
            ["alpha/SKILL.md"],
        )
        with self.assertRaises(ValueError):
            REVIEW.parse_proposal_json(
                json.dumps({"action": "change", "summary": "unsafe", "targets": ["C:/outside"]})
            )

    def test_adjustment_invalidates_batch_and_requires_revision_approval(self) -> None:
        observation = self.observation("alpha", severity="high")
        self.seed([observation])
        question, _ = self.invoke("next-question")
        self.invoke(
            "record-decision",
            "--finding-id",
            observation["id"],
            "--expected-evidence-fingerprint",
            question["expected_evidence_fingerprint"],
            "--expected-proposal-fingerprint",
            question["expected_proposal_fingerprint"],
            "--answer",
            "批准",
        )
        confirmation, _ = self.invoke("prepare-execution")
        revised = json.dumps(
            {"action": "revise", "summary": "只改触发边界", "targets": ["alpha"]},
            ensure_ascii=False,
        )
        adjusted, _ = self.invoke(
            "record-decision",
            "--finding-id",
            observation["id"],
            "--expected-evidence-fingerprint",
            question["expected_evidence_fingerprint"],
            "--expected-proposal-fingerprint",
            question["expected_proposal_fingerprint"],
            "--answer",
            "请只调整触发边界",
            "--classification",
            "adjust",
            "--revised-proposal-json",
            revised,
        )
        self.assertEqual(adjusted["status"], "revision_staged")
        self.assertEqual(self.load()["batches"][0]["status"], "stale")
        revision, _ = self.invoke("next-question")
        self.assertEqual(revision["question_type"], "revision_decision")
        approved, _ = self.invoke(
            "record-decision",
            "--finding-id",
            observation["id"],
            "--expected-evidence-fingerprint",
            revision["expected_evidence_fingerprint"],
            "--expected-proposal-fingerprint",
            revision["expected_proposal_fingerprint"],
            "--answer",
            "批准",
        )
        self.assertEqual(approved["decision"], "approved")
        self.assertEqual(confirmation["status"], "execution_confirmation")

    def test_final_confirmation_is_reused_and_empty_batch_is_not_created(self) -> None:
        first, second = self.observation("first", severity="high"), self.observation("second", severity="high")
        self.seed([first, second])
        for observation in (first, second):
            question, _ = self.invoke("next-question")
            self.invoke(
                "record-decision",
                "--finding-id",
                observation["id"],
                "--expected-evidence-fingerprint",
                question["expected_evidence_fingerprint"],
                "--expected-proposal-fingerprint",
                question["expected_proposal_fingerprint"],
                "--answer",
                "批准",
            )
        confirmation, code = self.invoke("prepare-execution")
        self.assertEqual(code, 0)
        before_explanation = self.state_path.read_bytes()
        explanation, code = self.invoke(
            "prepare-execution",
            "--decision",
            "explain",
            "--batch-id",
            confirmation["batch_id"],
            "--expected-batch-fingerprint",
            confirmation["batch_fingerprint"],
        )
        self.assertEqual(code, 0)
        self.assertEqual(explanation["question"], confirmation["question"])
        self.assertEqual(before_explanation, self.state_path.read_bytes())
        repeated, _ = self.invoke("prepare-execution")
        self.assertEqual(repeated["batch_id"], confirmation["batch_id"])
        self.assertEqual(len(self.load()["batches"]), 1)

        empty_state = REVIEW.new_state()
        self.save(empty_state)
        empty, code = self.invoke("prepare-execution")
        self.assertEqual(code, 0)
        self.assertEqual(empty["message"], "本周没有需要决定的修改。")
        self.assertEqual(self.load()["batches"], [])

    def test_prepare_requires_batch_identity_and_helper_drift_recovers(self) -> None:
        observation = self.observation("alpha", severity="high")
        state = self.seed([observation])
        finding = state["findings"][observation["id"]]
        finding["status"] = "approved"
        state["queue"].remove(observation["id"])
        self.save(state)
        invalid, code = self.invoke("prepare-execution", "--decision", "approve")
        self.assertEqual(code, 2)
        self.assertEqual(invalid["status"], "invalid_request")
        confirmation, _ = self.invoke("prepare-execution")
        self.helper.write_text("helper-v2\n", encoding="utf-8")
        blocked, code = self.invoke(
            "prepare-execution",
            "--decision",
            "approve",
            "--batch-id",
            confirmation["batch_id"],
            "--expected-batch-fingerprint",
            confirmation["batch_fingerprint"],
        )
        self.assertEqual(code, 4)
        self.assertEqual(blocked["status"], "blocked_helper_drift")
        replacement, _ = self.invoke("prepare-execution")
        self.assertNotEqual(replacement["batch_id"], confirmation["batch_id"])

    def test_source_drift_blocks_only_drifted_item(self) -> None:
        first, second = self.observation("first", severity="high"), self.observation("second", severity="high")
        state = self.seed([first, second])
        for observation in (first, second):
            state["findings"][observation["id"]]["status"] = "approved"
            state["queue"].remove(observation["id"])
        self.save(state)
        confirmation, _ = self.invoke("prepare-execution")
        (self.skills / "first" / "SKILL.md").write_text("drift\n", encoding="utf-8")
        ready, code = self.invoke(
            "prepare-execution",
            "--decision",
            "approve",
            "--batch-id",
            confirmation["batch_id"],
            "--expected-batch-fingerprint",
            confirmation["batch_fingerprint"],
        )
        self.assertEqual(code, 0)
        self.assertEqual(ready["status"], "ready")
        self.assertIn(first["id"], ready["drifted_finding_ids"])
        self.assertTrue(any(item["finding_id"] == second["id"] for item in ready["items"]))

    def test_failure_blocks_dependency_but_independent_item_continues_and_retry_reappears(self) -> None:
        dependency = self.observation("dependency", severity="high")
        dependent = self.observation(
            "dependent",
            severity="high",
            dependencies=(dependency["id"],),
        )
        independent = self.observation("independent", severity="high")
        state = self.seed([dependency, dependent, independent])
        for observation in (dependency, dependent, independent):
            state["findings"][observation["id"]]["status"] = "approved"
            state["queue"].remove(observation["id"])
        self.save(state)
        confirmation, _ = self.invoke("prepare-execution")
        ready, _ = self.invoke(
            "prepare-execution",
            "--decision",
            "approve",
            "--batch-id",
            confirmation["batch_id"],
            "--expected-batch-fingerprint",
            confirmation["batch_fingerprint"],
        )
        self.assertEqual(len(ready["items"]), 3)
        failed, code = self.invoke(
            "record-execution",
            "--batch-id",
            confirmation["batch_id"],
            "--finding-id",
            dependency["id"],
            "--expected-proposal-fingerprint",
            dependency["proposal_fingerprint"],
            "--outcome",
            "failed",
            "--details",
            "candidate test failed",
        )
        self.assertEqual(code, 0)
        self.assertEqual(failed["batch_status"], "partial_failed")
        current = self.load()
        batch = current["batches"][0]
        self.assertEqual(
            next(item for item in batch["items"] if item["finding_id"] == dependent["id"])["status"],
            "blocked_dependency",
        )
        successful, _ = self.invoke(
            "record-execution",
            "--batch-id",
            confirmation["batch_id"],
            "--finding-id",
            independent["id"],
            "--expected-proposal-fingerprint",
            independent["proposal_fingerprint"],
            "--outcome",
            "success",
            "--details",
            "independent complete",
        )
        self.assertEqual(successful["finding_status"], "completed")
        retry_question, _ = self.invoke("next-question")
        self.assertEqual(retry_question["question_type"], "retry")
        retried, _ = self.invoke(
            "record-decision",
            "--finding-id",
            dependency["id"],
            "--expected-evidence-fingerprint",
            retry_question["expected_evidence_fingerprint"],
            "--expected-proposal-fingerprint",
            retry_question["expected_proposal_fingerprint"],
            "--answer",
            "批准",
        )
        self.assertEqual(retried["decision"], "approved")
        new_confirmation, _ = self.invoke("prepare-execution")
        ids = {item["finding_id"] for item in self.load()["batches"][-1]["items"]}
        self.assertEqual(ids, {dependency["id"], dependent["id"]})
        self.assertEqual(new_confirmation["status"], "execution_confirmation")

    def test_retry_adopts_only_the_clean_recorded_execution_commit(self) -> None:
        observation = self.observation("retry-source", severity="high")
        self.initialize_skills_git("retry-source")
        state = self.seed([observation])
        state["findings"][observation["id"]]["status"] = "approved"
        state["queue"].remove(observation["id"])
        self.save(state)
        confirmation, _ = self.invoke("prepare-execution")
        self.invoke(
            "prepare-execution",
            "--decision",
            "approve",
            "--batch-id",
            confirmation["batch_id"],
            "--expected-batch-fingerprint",
            confirmation["batch_fingerprint"],
        )

        skill_md = self.skills / "retry-source" / "SKILL.md"
        skill_md.write_text(
            skill_md.read_text(encoding="utf-8") + "\nCommitted output.\n",
            encoding="utf-8",
        )
        self.git("add", "--", "retry-source/SKILL.md")
        self.git("commit", "--quiet", "-m", "apply retry source change")
        execution_commit = self.git("rev-parse", "HEAD")
        self.invoke(
            "record-execution",
            "--batch-id",
            confirmation["batch_id"],
            "--finding-id",
            observation["id"],
            "--expected-proposal-fingerprint",
            observation["proposal_fingerprint"],
            "--outcome",
            "failed",
            "--details",
            "source committed but runtime sync failed",
            "--commit",
            execution_commit,
            "--remote-sha",
            execution_commit,
            "--sync-status",
            "failed",
        )
        retry_question, _ = self.invoke("next-question")
        retried, code = self.invoke(
            "record-decision",
            "--finding-id",
            observation["id"],
            "--expected-evidence-fingerprint",
            retry_question["expected_evidence_fingerprint"],
            "--expected-proposal-fingerprint",
            retry_question["expected_proposal_fingerprint"],
            "--answer",
            "批准",
        )
        self.assertEqual(code, 0)
        self.assertTrue(retried["retry_source_rebased"])
        current = self.load()
        self.assertEqual(current["batches"][0]["status"], "stale")
        self.assertEqual(
            current["findings"][observation["id"]]["source_fingerprint"],
            REVIEW.source_fingerprint(self.skills, ["retry-source"]),
        )

        retry_confirmation, _ = self.invoke("prepare-execution")
        ready, code = self.invoke(
            "prepare-execution",
            "--decision",
            "approve",
            "--batch-id",
            retry_confirmation["batch_id"],
            "--expected-batch-fingerprint",
            retry_confirmation["batch_fingerprint"],
        )
        self.assertEqual(code, 0)
        self.assertEqual(ready["status"], "ready")
        self.assertEqual(ready["drifted_finding_ids"], [])

    def test_retry_rejects_uncommitted_changes_after_the_recorded_commit(self) -> None:
        observation = self.observation("retry-drift", severity="high")
        self.initialize_skills_git("retry-drift")
        state = self.seed([observation])
        state["findings"][observation["id"]]["status"] = "approved"
        state["queue"].remove(observation["id"])
        self.save(state)
        confirmation, _ = self.invoke("prepare-execution")
        self.invoke(
            "prepare-execution",
            "--decision",
            "approve",
            "--batch-id",
            confirmation["batch_id"],
            "--expected-batch-fingerprint",
            confirmation["batch_fingerprint"],
        )
        skill_md = self.skills / "retry-drift" / "SKILL.md"
        skill_md.write_text(
            skill_md.read_text(encoding="utf-8") + "\nCommitted output.\n",
            encoding="utf-8",
        )
        self.git("add", "--", "retry-drift/SKILL.md")
        self.git("commit", "--quiet", "-m", "apply retry source change")
        execution_commit = self.git("rev-parse", "HEAD")
        self.invoke(
            "record-execution",
            "--batch-id",
            confirmation["batch_id"],
            "--finding-id",
            observation["id"],
            "--expected-proposal-fingerprint",
            observation["proposal_fingerprint"],
            "--outcome",
            "failed",
            "--details",
            "source committed but runtime sync failed",
            "--commit",
            execution_commit,
            "--remote-sha",
            execution_commit,
            "--sync-status",
            "failed",
        )
        skill_md.write_text(
            skill_md.read_text(encoding="utf-8") + "Uncommitted drift.\n",
            encoding="utf-8",
        )
        retry_question, _ = self.invoke("next-question")
        blocked, code = self.invoke(
            "record-decision",
            "--finding-id",
            observation["id"],
            "--expected-evidence-fingerprint",
            retry_question["expected_evidence_fingerprint"],
            "--expected-proposal-fingerprint",
            retry_question["expected_proposal_fingerprint"],
            "--answer",
            "批准",
        )
        self.assertEqual(code, 4)
        self.assertEqual(blocked["status"], "blocked_retry_source_drift")
        self.assertEqual(
            self.load()["findings"][observation["id"]]["status"], "retry_pending"
        )

    def test_legacy_blocked_retry_is_recovered_without_editing_state_by_hand(self) -> None:
        observation = self.observation("legacy-retry", severity="high")
        self.initialize_skills_git("legacy-retry")
        state = self.seed([observation])
        original_source = state["findings"][observation["id"]]["source_fingerprint"]
        skill_md = self.skills / "legacy-retry" / "SKILL.md"
        skill_md.write_text(
            skill_md.read_text(encoding="utf-8") + "\nCommitted output.\n",
            encoding="utf-8",
        )
        self.git("add", "--", "legacy-retry/SKILL.md")
        self.git("commit", "--quiet", "-m", "apply legacy retry source change")
        execution_commit = self.git("rev-parse", "HEAD")
        finding = state["findings"][observation["id"]]
        finding["status"] = "waiting_evidence"
        finding["execution"] = {
            "outcome": "failed",
            "details": "source committed but runtime sync failed",
            "commit": execution_commit,
            "remote_sha": execution_commit,
            "sync_status": "failed",
        }
        finding["decision"] = {
            "value": "approved",
            "recorded_at": "2026-08-15T12:00:00+08:00",
        }
        state["queue"].remove(observation["id"])
        state["batches"].append(
            {
                "id": "batch-legacy-blocked",
                "status": "blocked",
                "items": [
                    {
                        "finding_id": observation["id"],
                        "status": "blocked_drift",
                        "source_fingerprint": original_source,
                    }
                ],
            }
        )
        self.save(state)

        confirmation, code = self.invoke("prepare-execution")
        self.assertEqual(code, 0)
        self.assertEqual(
            confirmation["recovered_retry_finding_ids"], [observation["id"]]
        )
        current = self.load()
        self.assertEqual(current["batches"][0]["status"], "stale")
        self.assertEqual(current["findings"][observation["id"]]["status"], "approved")
        self.assertNotEqual(
            current["findings"][observation["id"]]["source_fingerprint"],
            original_source,
        )

    def test_corrupt_state_and_lock_are_blocking_without_rebuild(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        corrupt = b'{"schema_version": 99}\n'
        self.state_path.write_bytes(corrupt)
        result, code = self.invoke("next-question")
        self.assertEqual(code, 3)
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(corrupt, self.state_path.read_bytes())

        structural = REVIEW.new_state()
        structural["findings"]["broken"] = "not-an-object"
        structural_bytes = json.dumps(structural).encode("utf-8")
        self.state_path.write_bytes(structural_bytes)
        result, code = self.invoke("next-question")
        self.assertEqual(code, 3)
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(structural_bytes, self.state_path.read_bytes())

        self.state_path.write_text(json.dumps(REVIEW.new_state()), encoding="utf-8")
        with REVIEW.StateLock(self.state_path):
            result, code = self.invoke("next-question", "--lock-timeout", "0.05")
        self.assertEqual(code, 3)
        self.assertEqual(result["status"], "blocked")

    def test_atomic_replace_retries_transient_sync_lock(self) -> None:
        destination = self.root / "atomic.json"
        real_replace = REVIEW.os.replace
        attempts = []

        def flaky_replace(source, target):
            attempts.append((source, target))
            if len(attempts) < 3:
                raise PermissionError("temporary sync lock")
            return real_replace(source, target)

        REVIEW.os.replace = flaky_replace
        try:
            REVIEW.atomic_write_json(destination, {"status": "ok"})
        finally:
            REVIEW.os.replace = real_replace
        self.assertEqual(len(attempts), 3)
        self.assertEqual(json.loads(destination.read_text(encoding="utf-8")), {"status": "ok"})

    def test_scan_allows_fresh_upstream_exit_two_but_rejects_stale_other_report(self) -> None:
        reports = {
            "summary.json": {
                "schema_version": 1,
                "date": "2026-08-15",
                "sources": [],
                "candidate_conflicts": [],
                "registry_coverage_gaps": [],
            },
            "manifests/2026-08-15/summary.json": {
                "version": "flat-skill-tree-v1",
                "date": "2026-08-15",
                "root": str(self.skills),
                "findings": {key: [] for key in (
                    "directory_structure_problems",
                    "duplicate_candidates",
                    "name_mismatch",
                    "overlap_candidates",
                    "link_or_path_issues",
                    "broken_items",
                )},
            },
            "usage/manifests/2026-08-15/summary.json": self.valid_usage(),
        }
        for relative, payload in reports.items():
            path = self.reports / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        original = REVIEW.run_audits
        REVIEW.run_audits = lambda **_: (
            {
                "upstream": {"exit_code": 2, "summary_changed": True},
                "hygiene": {"exit_code": 2, "summary_changed": False},
                "usage": {"exit_code": 0, "summary_changed": True},
            },
            {
                "upstream": self.reports / "summary.json",
                "hygiene": self.reports / "manifests/2026-08-15/summary.json",
                "usage": self.reports / "usage/manifests/2026-08-15/summary.json",
            },
        )
        try:
            args = REVIEW.parse_args(
                [
                    "scan",
                    "--state",
                    str(self.state_path),
                    "--agents-root",
                    str(self.root),
                    "--skills-root",
                    str(self.skills),
                    "--reports-root",
                    str(self.reports),
                    "--date",
                    "2026-08-15",
                ]
            )
            result, code = REVIEW.scan_command(args)
        finally:
            REVIEW.run_audits = original
        self.assertEqual(code, 2)
        self.assertTrue(result["complete"] is False)
        report = json.loads((self.reports / "2026-08-15/weekly-review.json").read_text(encoding="utf-8"))
        self.assertTrue(report["validation"]["upstream"]["valid"])
        self.assertFalse(report["validation"]["hygiene"]["valid"])

        malformed_usage = self.valid_usage()
        malformed_usage["warnings"] = None
        valid, error = REVIEW.summary_is_valid(malformed_usage, "usage", "2026-08-15")
        self.assertFalse(valid)
        self.assertIn("warnings", error)

    def test_runtime_sync_success_requires_sha_skill_set_and_verified_status(self) -> None:
        observation = self.observation("alpha", severity="high", requires_runtime_sync=True)
        state = self.seed([observation])
        state["findings"][observation["id"]]["status"] = "approved"
        state["queue"].remove(observation["id"])
        self.save(state)
        confirmation, _ = self.invoke("prepare-execution")
        self.invoke(
            "prepare-execution",
            "--decision",
            "approve",
            "--batch-id",
            confirmation["batch_id"],
            "--expected-batch-fingerprint",
            confirmation["batch_fingerprint"],
        )
        invalid, code = self.invoke(
            "record-execution",
            "--batch-id",
            confirmation["batch_id"],
            "--finding-id",
            observation["id"],
            "--expected-proposal-fingerprint",
            observation["proposal_fingerprint"],
            "--outcome",
            "success",
            "--details",
            "sync incomplete",
        )
        self.assertEqual(code, 2)
        self.assertEqual(invalid["status"], "invalid_request")
        successful, code = self.invoke(
            "record-execution",
            "--batch-id",
            confirmation["batch_id"],
            "--finding-id",
            observation["id"],
            "--expected-proposal-fingerprint",
            observation["proposal_fingerprint"],
            "--outcome",
            "success",
            "--details",
            "sync verified",
            "--remote-sha",
            "0123456789abcdef0123456789abcdef01234567",
            "--sync-status",
            "verified",
            "--synced-skill",
            "alpha",
        )
        self.assertEqual(code, 0)
        self.assertEqual(successful["finding_status"], "completed")


if __name__ == "__main__":
    unittest.main()
