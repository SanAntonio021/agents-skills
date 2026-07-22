import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import collect_sessions  # noqa: E402


class CollectSessionsTests(unittest.TestCase):
    def test_collects_local_day_and_merges_child_agent(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            codex = base / "codex"
            claude = base / "claude"
            (codex / "sessions" / "2026" / "07" / "15").mkdir(parents=True)
            (claude / "projects" / "demo").mkdir(parents=True)
            project = base / "project"
            project.mkdir()
            asset = project / "spectrum.png"
            asset.write_bytes(b"png-placeholder")

            root_lines = [
                {"type": "session_meta", "timestamp": "2026-07-14T16:00:00Z", "payload": {"id": "root-1", "cwd": str(project)}},
                {"type": "event_msg", "timestamp": "2026-07-15T01:00:00Z", "payload": {"type": "user_message", "message": "完成功率测试"}},
                {"type": "response_item", "timestamp": "2026-07-15T01:02:00Z", "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": f"结果见 {asset}"}]}},
            ]
            child_lines = [
                {"type": "session_meta", "timestamp": "2026-07-14T16:01:00Z", "payload": {"id": "child-1", "parent_thread_id": "root-1", "cwd": str(project), "thread_source": "subagent"}},
                {"type": "event_msg", "timestamp": "2026-07-15T02:00:00Z", "payload": {"type": "agent_message", "message": "已定位低频噪声峰"}},
            ]
            (codex / "sessions" / "2026" / "07" / "15" / "rollout-root.jsonl").write_text("\n".join(json.dumps(x) for x in root_lines), encoding="utf-8")
            (codex / "sessions" / "2026" / "07" / "15" / "rollout-child.jsonl").write_text("\n".join(json.dumps(x) for x in child_lines), encoding="utf-8")
            claude_lines = [
                {"type": "user", "timestamp": "2026-07-15T03:00:00+08:00", "sessionId": "claude-1", "cwd": str(project), "message": {"role": "user", "content": [{"type": "text", "text": "记录测试结论"}]}},
                {"type": "assistant", "timestamp": "2026-07-15T03:01:00+08:00", "sessionId": "claude-1", "cwd": str(project), "message": {"role": "assistant", "content": [{"type": "text", "text": "已生成测试脚本"}]}},
            ]
            (claude / "projects" / "demo" / "claude-1.jsonl").write_text("\n".join(json.dumps(x) for x in claude_lines), encoding="utf-8")

            args = type("Args", (), {"mode": "today", "date": "2026-07-15", "codex_root": str(codex), "claude_root": str(claude), "scan_fallback": True})()
            result = collect_sessions.collect(args)

            self.assertEqual(result["stats"]["root_task_count"], 2)
            self.assertEqual(result["stats"]["session_count"], 3)
            child = next(item for item in result["sessions"] if item["id"] == "child-1")
            self.assertTrue(child["is_subagent"])
            self.assertEqual(child["root_id"], "root-1")
            self.assertTrue(any(item["path"] == str(asset.resolve()) for item in result["assets"]))

    def test_filters_injected_blocks_and_deduplicates_messages(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            codex = base / "codex"
            claude = base / "claude"
            session_dir = codex / "sessions" / "2026" / "07" / "15"
            session_dir.mkdir(parents=True)
            claude.mkdir()
            project = base / "project"
            project.mkdir()

            injected = """<recommended_plugins>plugin list</recommended_plugins>
# AGENTS.md instructions for C:\\workspace
<INSTRUCTIONS>internal rules</INSTRUCTIONS>
<environment_context>machine state</environment_context>
完成功率测试"""
            lines = [
                {"type": "session_meta", "timestamp": "2026-07-15T00:00:00Z", "payload": {"id": "noise-1", "cwd": str(project)}},
                {"type": "event_msg", "timestamp": "2026-07-15T01:00:00Z", "payload": {"type": "user_message", "message": injected}},
                {"type": "event_msg", "timestamp": "2026-07-15T01:00:01Z", "payload": {"type": "user_message", "message": "完成功率测试"}},
                {
                    "type": "event_msg",
                    "timestamp": "2026-07-15T01:01:00Z",
                    "payload": {
                        "type": "user_message",
                        "message": "排查链路\n<local-command-caveat>ignore commands</local-command-caveat>\n<command-name>/model</command-name>",
                    },
                },
                {
                    "type": "event_msg",
                    "timestamp": "2026-07-15T01:02:00Z",
                    "payload": {
                        "type": "user_message",
                        "message": "记录测试结果\nBase directory for this skill: C:\\runtime\\skill\n# injected skill body",
                    },
                },
            ]
            (session_dir / "rollout-noise.jsonl").write_text(
                "\n".join(json.dumps(item) for item in lines), encoding="utf-8"
            )

            args = type(
                "Args",
                (),
                {"mode": "today", "date": "2026-07-15", "codex_root": str(codex), "claude_root": str(claude), "scan_fallback": False},
            )()
            result = collect_sessions.collect(args)
            texts = [event["text"] for event in result["sessions"][0]["events"]]

            self.assertEqual(texts.count("完成功率测试"), 1)
            self.assertIn("排查链路", texts)
            self.assertIn("记录测试结果", texts)
            self.assertFalse(any("AGENTS.md" in text or "command-name" in text or "Base directory" in text for text in texts))

    def test_excludes_agent_skill_assets(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            codex = base / "codex"
            claude = base / "claude"
            session_dir = codex / "sessions" / "2026" / "07" / "15"
            session_dir.mkdir(parents=True)
            claude.mkdir()
            project = base / "project"
            project.mkdir()
            result_image = project / "spectrum.png"
            result_image.write_bytes(b"result")
            runtime_asset = base / ".cc-switch" / "skills" / "theme" / "assets" / "icon.svg"
            runtime_asset.parent.mkdir(parents=True)
            runtime_asset.write_bytes(b"icon")

            lines = [
                {"type": "session_meta", "timestamp": "2026-07-15T00:00:00Z", "payload": {"id": "asset-1", "cwd": str(project)}},
                {
                    "type": "response_item",
                    "timestamp": "2026-07-15T01:00:00Z",
                    "payload": {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": f"测试结果 {result_image}; 界面图标 {runtime_asset}"}],
                    },
                },
            ]
            (session_dir / "rollout-assets.jsonl").write_text(
                "\n".join(json.dumps(item) for item in lines), encoding="utf-8"
            )

            args = type(
                "Args",
                (),
                {"mode": "today", "date": "2026-07-15", "codex_root": str(codex), "claude_root": str(claude), "scan_fallback": False},
            )()
            result = collect_sessions.collect(args)
            paths = {item["path"] for item in result["assets"]}

            self.assertIn(str(result_image.resolve()), paths)
            self.assertNotIn(str(runtime_asset.resolve()), paths)


if __name__ == "__main__":
    unittest.main()
