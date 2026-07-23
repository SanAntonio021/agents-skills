from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "skill_upstream_maintenance.py"
SPEC = importlib.util.spec_from_file_location("skill_upstream_maintenance", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def run_git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return completed.stdout.strip()


def init_repo(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    run_git(path, "init", "-b", "main")
    run_git(path, "config", "user.name", "Skill Test")
    run_git(path, "config", "user.email", "skill-test@example.com")


def commit_all(path: Path, message: str) -> str:
    run_git(path, "add", ".")
    run_git(path, "commit", "-m", message)
    return run_git(path, "rev-parse", "HEAD")


def write_skill(root: Path, name: str) -> Path:
    skill = root / name
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: test\n---\n\n# {name}\n",
        encoding="utf-8",
    )
    return skill


def write_mirrors(path: Path, mirror: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "[[mirror]]",
                'id = "example"',
                'repo_url = "https://github.com/example/upstream.git"',
                'branch = "main"',
                f'local_path = "{mirror.as_posix()}"',
                'exposure_policy = "zero"',
                'tracked_upstream_skills = ["source-skill"]',
                'custom_wrappers = ["alpha"]',
                "",
            ]
        ),
        encoding="utf-8",
    )


def write_registry(path: Path, baseline: str, include_beta: bool = True) -> None:
    lines = [
        "schema_version = 1",
        "",
        "[[skill]]",
        'name = "alpha"',
        'status = "confirmed"',
        'last_discovery_date = "2026-07-22"',
        'last_review_date = "2026-07-22"',
        'notes = "test source"',
        "",
        "[[skill.source]]",
        'id = "example-source"',
        'mirror_id = "example"',
        'repo_url = "https://github.com/example/upstream"',
        'upstream_path = "skills/source-skill"',
        f'accepted_commit = "{baseline}"',
        'accepted_version = "1.0"',
        'license = "MIT"',
        'baseline_kind = "exact"',
        'tracked_paths = ["SKILL.md", "scripts", "references"]',
        'license_paths = ["LICENSE"]',
        'evidence = ["fixture"]',
        'evidence_files = ["alpha/SKILL.md"]',
        'adopted = ["workflow"]',
        'excluded = ["telemetry"]',
        "",
    ]
    if include_beta:
        lines.extend(
            [
                "[[skill]]",
                'name = "beta"',
                'status = "none"',
                'last_discovery_date = "2026-07-22"',
                'last_review_date = "2026-07-22"',
                'notes = "no source"',
                "",
            ]
        )
    path.write_text("\n".join(lines), encoding="utf-8")


class SkillUpstreamMaintenanceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.skills = self.root / "skills"
        self.skills.mkdir()
        write_skill(self.skills, "alpha")
        write_skill(self.skills, "beta")
        init_repo(self.skills)
        commit_all(self.skills, "initial skills")

        self.mirror = self.root / "mirror"
        init_repo(self.mirror)
        run_git(self.mirror, "remote", "add", "origin", "https://github.com/example/upstream.git")
        upstream = self.mirror / "skills" / "source-skill"
        (upstream / "scripts").mkdir(parents=True)
        (upstream / "references").mkdir()
        (upstream / "SKILL.md").write_text("# source\n", encoding="utf-8")
        (upstream / "scripts" / "run.py").write_text("print('v1')\n", encoding="utf-8")
        (upstream / "references" / "guide.md").write_text("v1\n", encoding="utf-8")
        (self.mirror / "README.md").write_text("v1\n", encoding="utf-8")
        (self.mirror / "LICENSE").write_text("MIT\n", encoding="utf-8")
        self.baseline = commit_all(self.mirror, "initial upstream")

        self.registry = self.root / "skill-sources.toml"
        self.mirrors = self.root / "repo-mirrors.toml"
        write_registry(self.registry, self.baseline)
        write_mirrors(self.mirrors, self.mirror)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def load(self):
        return MODULE.load_sources(self.registry), MODULE.load_mirrors(self.mirrors)

    def test_validate_requires_complete_skill_coverage(self) -> None:
        write_registry(self.registry, self.baseline, include_beta=False)
        skills, mirrors = self.load()
        result = MODULE.validate_registry(skills, mirrors, self.skills)
        self.assertEqual(result["status"], "invalid")
        self.assertIn("Skills missing from registry: beta", result["errors"])

    def test_validate_supports_repository_root_sources_and_rejects_path_escape(self) -> None:
        (self.mirror / "SKILL.md").write_text("# root source\n", encoding="utf-8")
        baseline = commit_all(self.mirror, "add root skill")
        write_registry(self.registry, baseline)
        registry_text = self.registry.read_text(encoding="utf-8").replace(
            'upstream_path = "skills/source-skill"', 'upstream_path = "."'
        ).replace(
            'tracked_paths = ["SKILL.md", "scripts", "references"]',
            'tracked_paths = ["SKILL.md"]',
        )
        self.registry.write_text(registry_text, encoding="utf-8")
        skills, mirrors = self.load()
        self.assertEqual(MODULE.validate_registry(skills, mirrors, self.skills)["status"], "ok")

        self.registry.write_text(
            registry_text.replace('tracked_paths = ["SKILL.md"]', 'tracked_paths = ["../LICENSE"]'),
            encoding="utf-8",
        )
        skills, mirrors = self.load()
        invalid = MODULE.validate_registry(skills, mirrors, self.skills)
        self.assertEqual(invalid["status"], "invalid")
        self.assertTrue(any("repository-relative" in item for item in invalid["errors"]))

    def test_render_is_deterministic_and_detects_drift(self) -> None:
        skills, _ = self.load()
        first = MODULE.render_references(skills, self.skills, check_only=False)
        self.assertEqual(set(first["changed_skills"]), {"alpha", "beta"})
        self.assertIn("example-source", (self.skills / "alpha" / "references" / "upstream-sources.md").read_text(encoding="utf-8"))
        self.assertIn("没有经用户确认", (self.skills / "beta" / "references" / "upstream-sources.md").read_text(encoding="utf-8"))
        second = MODULE.render_references(skills, self.skills, check_only=True)
        self.assertEqual(second["status"], "up_to_date")

    def test_report_classifies_relevant_and_ignored_changes(self) -> None:
        skills, mirrors = self.load()
        reports = self.root / "reports"
        (self.mirror / "README.md").write_text("v2\n", encoding="utf-8")
        commit_all(self.mirror, "readme only")
        ignored = MODULE.build_report(skills, mirrors, reports, "2026-07-22", reports / "state.json")
        self.assertEqual(ignored["sources"][0]["status"], "no_relevant_change")

        (self.mirror / "skills" / "source-skill" / "scripts" / "run.py").write_text("print('v2')\n", encoding="utf-8")
        new_head = commit_all(self.mirror, "functional update")
        relevant = MODULE.build_report(skills, mirrors, reports, "2026-07-29", reports / "state.json")
        self.assertEqual(relevant["sources"][0]["status"], "review_required")
        self.assertEqual(relevant["sources"][0]["current_commit"], new_head)

    def test_blocked_mirror_records_observed_commit_without_marking_it_reviewed(self) -> None:
        skills, mirrors = self.load()
        reports = self.root / "reports"
        report = MODULE.build_report(
            skills,
            mirrors,
            reports,
            "2026-07-22",
            reports / "state.json",
            mirror_results={
                "example": {
                    "status": "sync_failed",
                    "local_head": self.baseline,
                    "error": "Local mirror has uncommitted changes; refusing to sync.",
                }
            },
        )

        self.assertEqual(report["sources"][0]["status"], "mirror_blocked")
        source_row = report["sources"][0]
        for field in (
            "problem",
            "impact",
            "repair_plan",
            "automatic_action",
            "approval_required",
        ):
            self.assertIn(field, source_row)
        self.assertIn("未提交修改", source_row["problem"])
        self.assertTrue(source_row["approval_required"])
        self.assertTrue(any("git -C" in step for step in source_row["repair_plan"]))
        markdown = (reports / "2026-07-22" / "summary.md").read_text(encoding="utf-8")
        self.assertIn("## 异常详情与修复计划", markdown)
        self.assertIn("问题：", markdown)
        self.assertIn("修复步骤：", markdown)
        state = json.loads((reports / "state.json").read_text(encoding="utf-8"))
        source_state = state["sources"]["example-source"]
        self.assertEqual(source_state["last_seen_commit"], self.baseline)
        self.assertNotIn("last_reviewed_commit", source_state)

    def test_diagnostics_cover_every_blocking_status(self) -> None:
        skills, mirrors = self.load()
        source = skills[0].sources[0]
        mirror = mirrors["example"]
        cases = {
            "mirror_blocked": {
                "mirror_status": "sync_failed",
                "error": "Git command timed out after 20 seconds.",
            },
            "dirty_mirror": {
                "mirror_details": {"actual_branch": "main", "actual_origin": mirror.repo_url},
            },
            "branch_mismatch": {
                "mirror_details": {"actual_branch": "develop", "actual_origin": mirror.repo_url},
            },
            "origin_mismatch": {
                "mirror_details": {"actual_branch": "main", "actual_origin": "https://example.test/wrong.git"},
            },
            "baseline_unavailable": {},
            "non_fast_forward": {},
            "diff_failed": {"error": "fatal: bad object"},
            "upstream_removed_or_moved": {},
            "license_review_required": {"changed": [{"change": "LICENSE", "path": "LICENSE"}]},
        }
        for status, extra in cases.items():
            with self.subTest(status=status):
                row = {
                    "skill": "alpha",
                    "source": source.id,
                    "status": status,
                    "current_commit": "b" * 40,
                    "changed": [],
                    **extra,
                }
                diagnosis = MODULE.diagnose_report_row(row, source, mirror)
                self.assertEqual(
                    set(diagnosis),
                    {
                        "problem",
                        "impact",
                        "repair_plan",
                        "automatic_action",
                        "approval_required",
                        "approval_reason",
                    },
                )
                self.assertTrue(diagnosis["problem"])
                self.assertTrue(diagnosis["impact"])
                self.assertGreaterEqual(len(diagnosis["repair_plan"]), 3)
                self.assertIsInstance(diagnosis["approval_required"], bool)

        for status in ("mirror_missing", "mirror_error"):
            with self.subTest(status=status):
                diagnosis = MODULE.diagnose_report_row(
                    {"status": status, "changed": [], "current_commit": None},
                    source,
                    mirror,
                )
                self.assertTrue(diagnosis["problem"])
                self.assertIsInstance(diagnosis["repair_plan"], list)

    def test_rejected_commit_is_not_repeated_after_unrelated_commit(self) -> None:
        skills, mirrors = self.load()
        reports = self.root / "reports"
        source_file = self.mirror / "skills" / "source-skill" / "SKILL.md"
        source_file.write_text("# rejected change\n", encoding="utf-8")
        rejected_commit = commit_all(self.mirror, "rejected upstream change")
        MODULE.record_review(
            reports / "state.json",
            "example-source",
            rejected_commit,
            self.baseline,
            "rejected",
            True,
        )
        (self.mirror / "README.md").write_text("unrelated\n", encoding="utf-8")
        commit_all(self.mirror, "unrelated follow-up")

        report = MODULE.build_report(
            skills, mirrors, reports, "2026-07-29", reports / "state.json"
        )
        self.assertEqual(report["sources"][0]["status"], "no_relevant_change")
        state = json.loads((reports / "state.json").read_text(encoding="utf-8"))
        self.assertEqual(state["sources"]["example-source"]["last_disposition"], "no-impact")
        self.assertEqual(state["history"][-1]["disposition"], "no-impact")
        self.assertTrue(state["history"][-1]["automatic"])

    def test_structured_version_only_is_ignored_but_dependency_change_is_relevant(self) -> None:
        manifest = self.mirror / "skills" / "source-skill" / "manifest.json"
        manifest.write_text('{"version":"1.0.0","dependencies":{"a":"1"}}\n', encoding="utf-8")
        baseline = commit_all(self.mirror, "add manifest")
        write_registry(self.registry, baseline)
        registry_text = self.registry.read_text(encoding="utf-8").replace(
            'tracked_paths = ["SKILL.md", "scripts", "references"]',
            'tracked_paths = ["SKILL.md", "scripts", "references", "manifest.json"]',
        )
        self.registry.write_text(registry_text, encoding="utf-8")
        skills, mirrors = self.load()
        reports = self.root / "reports"

        manifest.write_text('{"version":"1.0.1","dependencies":{"a":"1"}}\n', encoding="utf-8")
        commit_all(self.mirror, "version only")
        version_report = MODULE.build_report(
            skills, mirrors, reports, "2026-07-22", reports / "state.json"
        )
        self.assertEqual(version_report["sources"][0]["status"], "no_relevant_change")

        manifest.write_text('{"version":"1.0.2","dependencies":{"a":"2"}}\n', encoding="utf-8")
        commit_all(self.mirror, "dependency update")
        dependency_report = MODULE.build_report(
            skills, mirrors, reports, "2026-07-29", reports / "state.json"
        )
        self.assertEqual(dependency_report["sources"][0]["status"], "review_required")

    def test_new_behavior_path_can_be_tracked_after_accepted_baseline(self) -> None:
        sections = self.mirror / "skills" / "source-skill" / "sections"
        sections.mkdir()
        (sections / "release-body.md").write_text("new behavior\n", encoding="utf-8")
        current = commit_all(self.mirror, "extract behavior section")
        registry_text = self.registry.read_text(encoding="utf-8").replace(
            'tracked_paths = ["SKILL.md", "scripts", "references"]',
            'tracked_paths = ["SKILL.md", "scripts", "references", "sections"]',
        )
        self.registry.write_text(registry_text, encoding="utf-8")
        skills, mirrors = self.load()

        validation = MODULE.validate_registry(skills, mirrors, self.skills)
        self.assertEqual(validation["status"], "ok", validation["errors"])
        diff = MODULE.source_diff(self.mirror, skills[0].sources[0], current)
        self.assertEqual(diff["status"], "review_required")
        self.assertIn(
            "skills/source-skill/sections/release-body.md",
            [item["path"] for item in diff["changed"]],
        )

    def test_license_change_and_upstream_removal_are_blocked(self) -> None:
        skills, mirrors = self.load()
        (self.mirror / "LICENSE").write_text("changed terms\n", encoding="utf-8")
        license_head = commit_all(self.mirror, "license change")
        license_diff = MODULE.source_diff(self.mirror, skills[0].sources[0], license_head)
        self.assertEqual(license_diff["status"], "license_review_required")

        (self.mirror / "skills" / "source-skill" / "SKILL.md").write_text(
            "# change after rejected license\n", encoding="utf-8"
        )
        later_head = commit_all(self.mirror, "functional change after license")
        still_license_blocked = MODULE.source_diff(
            self.mirror, skills[0].sources[0], later_head, comparison_base=license_head
        )
        self.assertEqual(still_license_blocked["status"], "license_review_required")

        run_git(self.mirror, "rm", "-r", "skills/source-skill")
        removed_head = commit_all(self.mirror, "remove upstream skill")
        removed = MODULE.source_diff(self.mirror, skills[0].sources[0], removed_head)
        self.assertEqual(removed["status"], "upstream_removed_or_moved")

    def test_verified_path_migration_preserves_accepted_path_and_allows_review(self) -> None:
        run_git(
            self.mirror,
            "mv",
            "skills/source-skill",
            "skills/source-skill-renamed",
        )
        migration_commit = commit_all(self.mirror, "move source skill")
        registry_text = self.registry.read_text(encoding="utf-8").replace(
            'upstream_path = "skills/source-skill"',
            "\n".join(
                [
                    'upstream_path = "skills/source-skill-renamed"',
                    'accepted_upstream_path = "skills/source-skill"',
                    f'path_migration_commit = "{migration_commit}"',
                    'path_migration_evidence = ["Git R100 rename with identical trees."]',
                ]
            ),
        )
        self.registry.write_text(registry_text, encoding="utf-8")
        skills, mirrors = self.load()

        validation = MODULE.validate_registry(skills, mirrors, self.skills)
        self.assertEqual(validation["status"], "ok", validation["errors"])
        source = skills[0].sources[0]
        self.assertEqual(source.accepted_upstream_path, "skills/source-skill")
        self.assertEqual(source.upstream_path, "skills/source-skill-renamed")
        self.assertEqual(source.accepted_commit, self.baseline)

        diff = MODULE.source_diff(self.mirror, source, migration_commit)
        self.assertEqual(diff["status"], "review_required")
        renamed = [item for item in diff["changed"] if item["change"].startswith("R")]
        self.assertTrue(renamed)

        rendered = MODULE.render_skill_reference(skills[0])
        self.assertIn("接受时上游路径", rendered)
        self.assertIn(migration_commit, rendered)

    def test_prepare_review_does_not_touch_source_and_blocks_dirty_target(self) -> None:
        skills, mirrors = self.load()
        (self.mirror / "skills" / "source-skill" / "SKILL.md").write_text("# source v2\n", encoding="utf-8")
        commit_all(self.mirror, "upstream change")
        before = MODULE.tree_hash(self.skills / "alpha")
        prepared = MODULE.prepare_review(
            skills,
            mirrors,
            self.skills,
            self.root / "reports",
            "2026-07-22",
            "alpha",
            "example-source",
            run_git(self.mirror, "rev-parse", "HEAD"),
        )
        self.assertEqual(prepared["status"], "prepared")
        self.assertEqual(MODULE.tree_hash(self.skills / "alpha"), before)
        workspace = Path(prepared["workspace"])
        self.assertTrue((workspace / "old_skill" / "SKILL.md").is_file())
        self.assertTrue((workspace / "candidate_skill" / "SKILL.md").is_file())

        (self.skills / "alpha" / "SKILL.md").write_text("dirty\n", encoding="utf-8")
        blocked = MODULE.prepare_review(
            skills,
            mirrors,
            self.skills,
            self.root / "reports",
            "2026-07-29",
            "alpha",
            "example-source",
            run_git(self.mirror, "rev-parse", "HEAD"),
        )
        self.assertEqual(blocked["status"], "blocked_dirty_target")

    def test_record_review_requires_explicit_confirmation(self) -> None:
        state = self.root / "state.json"
        with self.assertRaises(ValueError):
            MODULE.record_review(state, "example-source", self.baseline, self.baseline, "rejected", False)
        result = MODULE.record_review(
            state, "example-source", self.baseline, self.baseline, "rejected", True
        )
        self.assertEqual(result["status"], "recorded")
        payload = json.loads(state.read_text(encoding="utf-8"))
        self.assertEqual(payload["sources"]["example-source"]["last_disposition"], "rejected")
        self.assertEqual(
            payload["sources"]["example-source"]["reviewed_against_accepted_commit"], self.baseline
        )
        with self.assertRaises(ValueError):
            MODULE.record_review(
                state, "example-source", self.baseline, self.baseline, "accepted", True
            )

    def test_finalize_and_apply_require_complete_current_approval(self) -> None:
        skills, mirrors = self.load()
        upstream = self.mirror / "skills" / "source-skill" / "SKILL.md"
        upstream.write_text("# source v2\n", encoding="utf-8")
        head = commit_all(self.mirror, "functional update")
        prepared = MODULE.prepare_review(
            skills,
            mirrors,
            self.skills,
            self.root / "reports",
            "2026-07-22",
            "alpha",
            "example-source",
            head,
        )
        workspace = Path(prepared["workspace"])
        candidate = workspace / "candidate_skill" / "SKILL.md"
        candidate.write_text(
            "---\nname: alpha\ndescription: improved\n---\n\n# alpha improved\n",
            encoding="utf-8",
        )
        before = MODULE.tree_hash(self.skills / "alpha")
        incomplete = MODULE.finalize_review(
            skills,
            mirrors,
            self.skills,
            workspace,
            "alpha",
            "example-source",
            {"benefit_confirmed": True, "tests_passed": False, "license_ok": True, "risk_reviewed": True},
        )
        self.assertEqual(incomplete["status"], "blocked_review_incomplete")
        self.assertEqual(MODULE.tree_hash(self.skills / "alpha"), before)

        (workspace / "benefit-assessment.md").write_text(
            "# 收益评估\n\n状态：有可证明收益\n", encoding="utf-8"
        )
        (workspace / "test-report.md").write_text(
            "# 测试报告\n\n状态：通过\n", encoding="utf-8"
        )
        finalized = MODULE.finalize_review(
            skills,
            mirrors,
            self.skills,
            workspace,
            "alpha",
            "example-source",
            {"benefit_confirmed": True, "tests_passed": True, "license_ok": True, "risk_reviewed": True},
        )
        self.assertEqual(finalized["status"], "awaiting_approval")
        self.assertEqual(MODULE.tree_hash(self.skills / "alpha"), before)

        reports = self.root / "reports"
        weekly = MODULE.build_report(
            skills,
            mirrors,
            reports,
            "2026-07-29",
            reports / "state.json",
        )
        weekly_source = weekly["sources"][0]
        self.assertEqual(weekly_source["status"], "awaiting_approval")
        self.assertEqual(Path(weekly_source["review_workspace"]), workspace.resolve())
        weekly_markdown = (reports / "2026-07-29" / "summary.md").read_text(encoding="utf-8")
        self.assertIn("## 等待逐项批准", weekly_markdown)
        self.assertIn(str(workspace.resolve()), weekly_markdown)
        state = json.loads((reports / "state.json").read_text(encoding="utf-8"))
        source_state = state["sources"]["example-source"]
        self.assertEqual(source_state["last_seen_commit"], head)
        self.assertNotIn("last_reviewed_commit", source_state)
        self.assertEqual(skills[0].sources[0].accepted_commit, self.baseline)

        test_report = workspace / "test-report.md"
        original_test_report = test_report.read_text(encoding="utf-8")
        test_report.write_text(original_test_report + "tampered\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Review evidence changed"):
            MODULE.apply_review(
                skills,
                mirrors,
                self.skills,
                workspace,
                "alpha",
                "example-source",
                True,
                "User approved this skill candidate in the active task.",
            )
        test_report.write_text(original_test_report, encoding="utf-8")
        with self.assertRaises(ValueError):
            MODULE.apply_review(
                skills, mirrors, self.skills, workspace, "alpha", "example-source", False, ""
            )

        applied = MODULE.apply_review(
            skills,
            mirrors,
            self.skills,
            workspace,
            "alpha",
            "example-source",
            True,
            "User approved this skill candidate in the active task.",
        )
        self.assertEqual(applied["status"], "applied_pending_retest")
        self.assertIn("alpha improved", (self.skills / "alpha" / "SKILL.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
