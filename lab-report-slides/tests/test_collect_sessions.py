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


if __name__ == "__main__":
    unittest.main()
