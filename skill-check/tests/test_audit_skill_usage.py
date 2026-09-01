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

    @staticmethod
    def write_jsonl(path: Path, rows: list[dict]) -> None:
        text = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)
        path.write_text(text, encoding="utf-8")

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
        self.assertEqual(alpha["codex_requests"], 1)

    def test_claude_skill_tool_is_usage_but_startup_load_is_not(self) -> None:
        summary = self.run_audit()
        beta = next(item for item in summary["classifications"]["已用"] if item["skill"] == "beta-skill")
        self.assertEqual(beta["claude_skill_calls"], 1)
        self.assertEqual(beta["claude_requests"], 1)
        self.assertEqual(summary["claude_startup_candidate_loads"], {"alpha-skill": 1})

    def test_codex_deduplicates_explicit_and_observed_read_within_turn(self) -> None:
        self.write_jsonl(
            self.codex / "sample.jsonl",
            [
                {
                    "type": "session_meta",
                    "timestamp": "2026-01-01T00:00:00Z",
                    "payload": {"id": "codex-request-dedupe"},
                },
                {
                    "type": "event_msg",
                    "timestamp": "2026-01-01T00:01:00Z",
                    "payload": {
                        "type": "item_completed",
                        "turn_id": "turn-1",
                        "item": {"type": "UserMessage", "id": "user-1", "content": "$alpha-skill 请检查。"},
                    },
                },
                {
                    "type": "event_msg",
                    "timestamp": "2026-01-01T00:01:10Z",
                    "payload": {
                        "type": "item_completed",
                        "turn_id": "turn-1",
                        "item": {
                            "type": "CommandExecution",
                            "id": "command-1",
                            "command": "Get-Content skills-a/alpha-skill/SKILL.md",
                            "status": "completed",
                            "exit_code": 0,
                        },
                    },
                },
                {
                    "type": "event_msg",
                    "timestamp": "2026-01-01T00:02:00Z",
                    "payload": {
                        "type": "item_completed",
                        "turn_id": "turn-2",
                        "item": {
                            "type": "CommandExecution",
                            "id": "command-2",
                            "command": "Get-Content skills-a/alpha-skill/SKILL.md",
                            "status": "completed",
                            "exit_code": 0,
                        },
                    },
                },
            ],
        )
        self.write_jsonl(self.claude / "sample.jsonl", [])
        self.write_jsonl(self.telemetry / "sample.jsonl", [])
        summary = self.run_audit()
        alpha = next(item for item in summary["classifications"]["已用"] if item["skill"] == "alpha-skill")
        self.assertEqual(alpha["codex_requests"], 2)
        self.assertEqual(alpha["codex_explicit"], 1)
        self.assertEqual(alpha["codex_observed_reads"], 2)
        events = summary["usage_evidence"]["alpha-skill"]
        self.assertEqual(len(events), 2)
        first = next(item for item in events if "explicit_user_invocation" in item["evidence_kinds"])
        self.assertEqual(
            first["evidence_kinds"],
            ["explicit_user_invocation", "observed_skill_read"],
        )

    def test_claude_deduplicates_repeated_skill_tools_by_ancestor_user(self) -> None:
        self.write_jsonl(self.codex / "sample.jsonl", [])
        self.write_jsonl(
            self.claude / "sample.jsonl",
            [
                {
                    "type": "user",
                    "uuid": "u1",
                    "parentUuid": None,
                    "sessionId": "claude-request-dedupe",
                    "timestamp": "2026-01-02T00:00:00Z",
                    "message": {"content": "请检查频谱。"},
                },
                {
                    "type": "assistant",
                    "uuid": "a1",
                    "parentUuid": "u1",
                    "sessionId": "claude-request-dedupe",
                    "timestamp": "2026-01-02T00:00:10Z",
                    "message": {"content": [{"type": "tool_use", "id": "tool-1", "name": "Skill", "input": {"skill": "beta-skill"}}]},
                },
                {
                    "type": "assistant",
                    "uuid": "a2",
                    "parentUuid": "a1",
                    "sessionId": "claude-request-dedupe",
                    "timestamp": "2026-01-02T00:00:20Z",
                    "message": {"content": [{"type": "tool_use", "id": "tool-2", "name": "Skill", "input": {"skill": "beta-skill"}}]},
                },
                {
                    "type": "user",
                    "uuid": "u2",
                    "parentUuid": "a2",
                    "sessionId": "claude-request-dedupe",
                    "timestamp": "2026-01-02T00:01:00Z",
                    "message": {"content": "再次检查频谱。"},
                },
                {
                    "type": "assistant",
                    "uuid": "a3",
                    "parentUuid": "u2",
                    "sessionId": "claude-request-dedupe",
                    "timestamp": "2026-01-02T00:01:10Z",
                    "message": {"content": [{"type": "tool_use", "id": "tool-3", "name": "Skill", "input": {"skill": "beta-skill"}}]},
                },
            ],
        )
        self.write_jsonl(self.telemetry / "sample.jsonl", [])
        summary = self.run_audit()
        beta = next(item for item in summary["classifications"]["已用"] if item["skill"] == "beta-skill")
        self.assertEqual(beta["claude_skill_calls"], 2)
        self.assertEqual(beta["claude_requests"], 2)
        self.assertEqual(len(summary["usage_evidence"]["beta-skill"]), 2)

    def test_claude_tool_result_user_record_does_not_split_the_request(self) -> None:
        self.write_jsonl(self.codex / "sample.jsonl", [])
        self.write_jsonl(
            self.claude / "sample.jsonl",
            [
                {
                    "type": "user",
                    "uuid": "u1",
                    "parentUuid": None,
                    "sessionId": "claude-tool-result",
                    "timestamp": "2026-01-02T00:00:00Z",
                    "message": {"content": "请检查频谱。"},
                },
                {
                    "type": "assistant",
                    "uuid": "a1",
                    "parentUuid": "u1",
                    "sessionId": "claude-tool-result",
                    "timestamp": "2026-01-02T00:00:10Z",
                    "message": {"content": [{"type": "tool_use", "id": "shell-1", "name": "Bash", "input": {"command": "echo test"}}]},
                },
                {
                    "type": "user",
                    "uuid": "tool-result-1",
                    "parentUuid": "a1",
                    "sessionId": "claude-tool-result",
                    "timestamp": "2026-01-02T00:00:11Z",
                    "message": {"content": [{"type": "tool_result", "tool_use_id": "shell-1", "content": "ok"}]},
                },
                {
                    "type": "assistant",
                    "uuid": "a2",
                    "parentUuid": "tool-result-1",
                    "sessionId": "claude-tool-result",
                    "timestamp": "2026-01-02T00:00:20Z",
                    "message": {"content": [{"type": "tool_use", "id": "skill-1", "name": "Skill", "input": {"skill": "beta-skill"}}]},
                },
            ],
        )
        self.write_jsonl(self.telemetry / "sample.jsonl", [])
        summary = self.run_audit()
        beta = next(item for item in summary["classifications"]["已用"] if item["skill"] == "beta-skill")
        self.assertEqual(beta["claude_requests"], 1)
        self.assertEqual(summary["warnings"]["unmapped_request_count"], 0)

    def test_weekly_window_is_left_closed_and_right_open(self) -> None:
        self.write_jsonl(
            self.codex / "sample.jsonl",
            [
                {
                    "type": "session_meta",
                    "timestamp": "2026-01-01T00:00:00Z",
                    "payload": {"id": "codex-window"},
                },
                *[
                    {
                        "type": "event_msg",
                        "timestamp": timestamp,
                        "payload": {
                            "type": "item_completed",
                            "turn_id": turn_id,
                            "item": {"type": "UserMessage", "id": turn_id, "content": "$alpha-skill"},
                        },
                    }
                    for turn_id, timestamp in (
                        ("at-start", "2026-01-01T00:00:00Z"),
                        ("before-end", "2026-01-01T23:59:59Z"),
                        ("at-end", "2026-01-02T00:00:00Z"),
                    )
                ],
            ],
        )
        self.write_jsonl(self.claude / "sample.jsonl", [])
        self.write_jsonl(self.telemetry / "sample.jsonl", [])
        summary = self.run_audit(
            "--window-start",
            "2026-01-01T00:00:00Z",
            "--window-end",
            "2026-01-02T00:00:00Z",
            "--timezone",
            "Asia/Shanghai",
        )
        alpha = next(item for item in summary["classifications"]["已用"] if item["skill"] == "alpha-skill")
        self.assertEqual(alpha["codex_requests"], 2)
        self.assertEqual(summary["version"], "skill-usage-audit-v2")
        self.assertEqual(summary["configuration"]["count_unit"], "request")
        self.assertEqual(summary["window"]["kind"], "weekly")

    def test_unmapped_usage_evidence_is_warned_and_not_counted(self) -> None:
        self.write_jsonl(
            self.codex / "sample.jsonl",
            [
                {
                    "type": "session_meta",
                    "timestamp": "2026-01-01T00:00:00Z",
                    "payload": {"id": "codex-unmapped"},
                },
                {
                    "type": "event_msg",
                    "timestamp": "2026-01-01T00:00:10Z",
                    "payload": {
                        "type": "item_completed",
                        "item": {
                            "type": "CommandExecution",
                            "id": "orphan-command",
                            "command": "Get-Content skills-a/alpha-skill/SKILL.md",
                            "status": "completed",
                            "exit_code": 0,
                        },
                    },
                },
            ],
        )
        self.write_jsonl(
            self.claude / "sample.jsonl",
            [
                {
                    "type": "assistant",
                    "uuid": "orphan-assistant",
                    "parentUuid": "missing-user",
                    "sessionId": "claude-unmapped",
                    "timestamp": "2026-01-02T00:00:10Z",
                    "message": {"content": [{"type": "tool_use", "id": "orphan-tool", "name": "Skill", "input": {"skill": "beta-skill"}}]},
                }
            ],
        )
        self.write_jsonl(self.telemetry / "sample.jsonl", [])
        summary = self.run_audit()
        self.assertEqual(summary["warnings"]["unmapped_request_count"], 2)
        self.assertEqual(summary["classifications"]["已用"], [])

    def test_unmapped_evidence_outside_window_does_not_block_week(self) -> None:
        self.write_jsonl(self.codex / "sample.jsonl", [])
        self.write_jsonl(
            self.claude / "sample.jsonl",
            [
                {
                    "type": "assistant",
                    "uuid": "old-orphan",
                    "parentUuid": "missing-user",
                    "sessionId": "claude-old-unmapped",
                    "timestamp": "2025-12-01T00:00:00Z",
                    "message": {"content": [{"type": "tool_use", "id": "old-tool", "name": "Skill", "input": {"skill": "beta-skill"}}]},
                }
            ],
        )
        self.write_jsonl(self.telemetry / "sample.jsonl", [])
        summary = self.run_audit(
            "--window-start",
            "2026-01-01T00:00:00Z",
            "--window-end",
            "2026-01-08T00:00:00Z",
        )
        self.assertEqual(summary["warnings"]["unmapped_request_count"], 0)

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
        self.assertEqual(warnings["non_text_user_record_count"], 0)
        self.assertTrue(all("detail" in item for item in warnings["parse_errors"]))

    def test_image_only_codex_message_is_not_a_missing_field(self) -> None:
        with (self.codex / "sample.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(
                '{"type":"event_msg","timestamp":"2026-01-01T00:05:00Z",'
                '"payload":{"type":"user_message","message":"\\n",'
                '"images":["data:image/png;base64,fixture"]}}\n'
            )
        summary = self.run_audit()
        warnings = summary["warnings"]
        self.assertEqual(warnings["missing_field_count"], 3)
        self.assertEqual(warnings["non_text_user_record_count"], 1)
        self.assertIn("only image or attachment", warnings["non_text_user_records"][0]["detail"])

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
