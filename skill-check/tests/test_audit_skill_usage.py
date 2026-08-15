from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = SKILL_ROOT / "scripts" / "audit_skill_usage.py"
FIXTURES = SKILL_ROOT / "evals" / "fixtures"


def load_module():
    spec = importlib.util.spec_from_file_location("audit_skill_usage", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


AUDIT = load_module()


class AuditSkillUsageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.skills_a = self.root / "skills-a"
        self.skills_b = self.root / "skills-b"
        self.codex = self.root / "codex"
        self.claude = self.root / "claude"
        self.telemetry = self.root / "telemetry"
        self.reports = self.root / "reports"
        for path in (self.skills_a, self.skills_b, self.codex, self.claude, self.telemetry):
            path.mkdir(parents=True)
        self.make_skill(
            self.skills_a,
            "alpha-skill",
            "alpha-skill",
            "执行专用阿尔法校验流程，并输出确定性结果。",
        )
        self.make_skill(
            self.skills_b,
            "beta-skill",
            "beta-skill",
            "用于频谱整理和曲线检查，发现绘图与数据问题。",
        )
        shutil.copy2(FIXTURES / "codex-session-sample.jsonl", self.codex / "sample.jsonl")
        shutil.copy2(FIXTURES / "claude-session-sample.jsonl", self.claude / "sample.jsonl")
        shutil.copy2(FIXTURES / "claude-telemetry-sample.jsonl", self.telemetry / "sample.jsonl")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    @staticmethod
    def make_skill(root: Path, directory: str, name: str, description: str) -> None:
        skill_dir = root / directory
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            f"---\nname: {name}\ndescription: {description}\n---\n\n# {name}\n",
            encoding="utf-8",
        )

    def run_audit(self, *extra: str):
        argv = [
            "--reports-root",
            str(self.reports),
            "--date",
            "2026-01-03",
            "--skills-root",
            str(self.skills_a),
            "--skills-root",
            str(self.skills_b),
            "--codex-sessions-root",
            str(self.codex),
            "--claude-projects-root",
            str(self.claude),
            "--claude-telemetry-root",
            str(self.telemetry),
            *extra,
        ]
        return AUDIT.audit(AUDIT.parse_args(argv))

    def test_inventory_merges_repeated_skill_roots(self) -> None:
        self.make_skill(self.skills_b, "alpha-copy", "alpha-skill", "重复位置。")
        summary = self.run_audit()
        self.assertEqual(summary["counts"]["skills"], 2)
        alpha = next(item for item in summary["skill_inventory"] if item["skill"] == "alpha-skill")
        self.assertEqual(len(alpha["locations"]), 2)
        self.assertEqual({item["root_id"] for item in alpha["locations"]}, {"skills-1", "skills-2"})

    def test_codex_prefers_event_message_and_deduplicates_response_item(self) -> None:
        summary = self.run_audit()
        alpha = next(item for item in summary["classifications"]["已用"] if item["skill"] == "alpha-skill")
        self.assertEqual(alpha["codex_explicit"], 1)

    def test_claude_skill_tool_is_usage_but_startup_load_is_not(self) -> None:
        summary = self.run_audit()
        beta = next(item for item in summary["classifications"]["已用"] if item["skill"] == "beta-skill")
        self.assertEqual(beta["claude_skill_calls"], 1)
        self.assertEqual(summary["claude_startup_candidate_loads"], {"alpha-skill": 1})

    def test_suspected_missed_use_uses_description_rules(self) -> None:
        summary = self.run_audit()
        pairs = {(item["skill"], item["host"]) for item in summary["classifications"]["疑似漏用"]}
        self.assertIn(("beta-skill", "codex"), pairs)
        self.assertIn(("alpha-skill", "claude"), pairs)
        self.assertNotIn(("beta-skill", "claude"), pairs)
        for item in summary["classifications"]["疑似漏用"]:
            self.assertTrue(any(term.lower() in item["excerpt"].lower() for term in item["matched_terms"]))

    def test_parse_and_missing_field_warnings_are_separate(self) -> None:
        summary = self.run_audit()
        warnings = summary["warnings"]
        self.assertEqual(warnings["parse_error_count"], 2)
        self.assertEqual(warnings["missing_field_count"], 3)
        self.assertTrue(all("detail" in item for item in warnings["parse_errors"]))

    def test_bridge_workspace_session_is_excluded(self) -> None:
        summary = self.run_audit()
        self.assertEqual(summary["warnings"]["bridge_copy_excluded_count"], 1)
        alpha_events = summary["usage_evidence"]["alpha-skill"]
        self.assertFalse(any(event["host"] == "claude" for event in alpha_events))

    def test_excerpts_are_redacted_and_limited(self) -> None:
        with (self.codex / "sample.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(
                '{"type":"event_msg","timestamp":"2026-01-01T00:05:00Z",'
                '"payload":{"type":"user_message","message":"$alpha-skill 读取 /home/example/private.txt"}}\n'
            )
        summary = self.run_audit("--excerpt-chars", "80")
        serialized = json.dumps(summary, ensure_ascii=False)
        self.assertNotIn("demo@example.com", serialized)
        self.assertNotIn("C:\\Private", serialized)
        self.assertNotIn("/home/example", serialized)
        for events in summary["usage_evidence"].values():
            for event in events:
                self.assertLessEqual(len(event.get("excerpt", "")), 80)

    def test_no_excerpt_removes_all_excerpt_fields(self) -> None:
        summary = self.run_audit("--no-excerpt")
        self.assertNotIn('"excerpt"', json.dumps(summary, ensure_ascii=False))

    def test_hygiene_intersection_only_marks_unused_skill(self) -> None:
        hygiene = self.root / "hygiene.json"
        hygiene.write_text(
            json.dumps(
                {
                    "findings": {
                        "duplicate_candidates": [],
                        "overlap_candidates": [
                            {"left": "alpha-skill", "right": "gamma-skill"}
                        ],
                    }
                }
            ),
            encoding="utf-8",
        )
        self.make_skill(self.skills_b, "gamma-skill", "gamma-skill", "只用于伽马检查。")
        summary = self.run_audit("--hygiene-summary", str(hygiene))
        redundant = [item["skill"] for item in summary["classifications"]["可能冗余"]]
        self.assertEqual(redundant, ["gamma-skill"])

    def test_report_paths_do_not_persist_absolute_input_roots(self) -> None:
        summary = self.run_audit()
        summary_path = self.reports / "usage" / "manifests" / "2026-01-03" / "summary.json"
        weekly_path = self.reports / "usage" / "weekly" / "2026-01-03.md"
        self.assertTrue(summary_path.is_file())
        self.assertTrue(weekly_path.is_file())
        serialized = summary_path.read_text(encoding="utf-8")
        self.assertNotIn(str(self.root), serialized)
        self.assertTrue(summary["warnings"]["codex_implicit_usage_not_captured"])

    def test_path_only_skill_name_does_not_create_candidate(self) -> None:
        with (self.codex / "sample.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(
                '{"type":"event_msg","timestamp":"2026-01-01T00:06:00Z",'
                '"payload":{"type":"user_message","message":"比较 C:\\\\skills\\\\beta-skill\\\\config.txt 的哈希。"}}\n'
            )
        summary = self.run_audit()
        self.assertFalse(
            any(
                item["timestamp"] == "2026-01-01T00:06:00Z"
                for item in summary["classifications"]["疑似漏用"]
            )
        )

    def test_cli_accepts_repeated_roots(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--reports-root",
                str(self.reports),
                "--date",
                "2026-01-04",
                "--skills-root",
                str(self.skills_a),
                "--skills-root",
                str(self.skills_b),
                "--codex-sessions-root",
                str(self.codex),
                "--claude-projects-root",
                str(self.claude),
                "--claude-telemetry-root",
                str(self.telemetry),
                "--no-excerpt",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("summary:", result.stdout)

    def test_candidate_limit_prioritizes_different_skills(self) -> None:
        collector = AUDIT.CandidateCollector(10)
        for skill_index in range(20):
            for event_index in range(6):
                collector.add(
                    {
                        "skill": f"skill-{skill_index:02d}",
                        "host": "codex",
                        "timestamp": f"2026-01-01T00:{event_index:02d}:00Z",
                        "source": {"root_id": "fixture", "path": "sample.jsonl", "line": event_index + 1},
                        "score": 100,
                    }
                )
        items = collector.items()
        self.assertEqual(len(items), 10)
        self.assertEqual(len({item["skill"] for item in items}), 10)
        self.assertEqual(collector.total, 120)
        self.assertEqual(collector.unique_skills, 20)


if __name__ == "__main__":
    unittest.main()
