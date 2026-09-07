import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import collect_sessions  # noqa: E402


class CollectSessionsTests(unittest.TestCase):
    def test_powershell_quoted_image_paths_are_individual_candidates(self):
        self.assertEqual(collect_sessions.candidate_paths(r"'D:\work\plot one.png' and 'D:\work\photo.jpg'"),
                         [r"D:\work\plot one.png", r"D:\work\photo.jpg"])

    def test_extracts_separate_windows_paths_and_preserves_unc(self):
        first = r"C:\project\run1\ber.png"
        second = r"D:\project\run2\evm.png"
        unc = r"\\server\share\bench photo.jpg"
        self.assertEqual(collect_sessions.candidate_paths(f"结果 {first} 和 {second}，台架 {unc}"),
                         [first, second, unc])

    def test_markdown_images_with_spaces_and_relative_paths(self):
        text = r'![curve](C:\my project\ber plot.png) ![bench](<\\server\share\setup photo.jpg>) ![result](results/foo.png "BER")'
        self.assertEqual(collect_sessions.candidate_paths(text),
                         [r"C:\my project\ber plot.png", r"\\server\share\setup photo.jpg", "results/foo.png"])
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            image = root / "results" / "foo.png"
            image.parent.mkdir()
            image.write_bytes(b"original")
            start, end, _ = collect_sessions.local_window("today", "2026-07-15")
            records = [{"cwd": str(root), "project": "demo",
                        "artifact_candidates": collect_sessions.candidate_paths("![result](results/foo.png)")}]
            assets = collect_sessions.discover_assets(records, start, end, False, 0, 0)
            self.assertEqual([a["path"] for a in assets], [str(image.resolve())])

    def test_remote_markdown_and_bare_urls_are_not_local_assets(self):
        self.assertEqual(collect_sessions.candidate_paths(
            '![remote](https://host/path/plot.png) https://host/another/plot.jpg ![local](results/local.png)'),
            ["results/local.png"])

    def test_supplements_each_project_and_experiment_without_changing_sources(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            start, end, _ = collect_sessions.local_window("today", "2026-07-15")
            images = [base / "a" / "run1" / "spectrum.png",
                      base / "a" / "run2" / "ber.png", base / "b" / "evm.png"]
            for path in images:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"original")
                os.utime(path, (start.timestamp(), start.timestamp()))
            records = [{"cwd": str(base / name), "project": name,
                        "artifact_candidates": [str(images[0])] if name == "a" else []}
                       for name in ("a", "b")]
            assets = collect_sessions.discover_assets(records, start, end, True, 3, 20)
            self.assertEqual({a["path"] for a in assets}, {str(p) for p in images})
            self.assertEqual({a["project"] for a in assets}, {"a", "b"})
            self.assertTrue(all(a["status"] == "unverified" for a in assets))
            for path in images:
                self.assertEqual(path.read_bytes(), b"original")
                self.assertEqual(path.stat().st_mtime, start.timestamp())

    def test_old_platform_images_are_context_and_old_curves_are_excluded(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            start, end, _ = collect_sessions.local_window("today", "2026-07-15")
            for name in ("bench_photo.jpg", "old_ber.png", "manual.jpg"):
                path = base / name
                path.write_bytes(b"image")
                os.utime(path, (1, 1))
            records = [{"cwd": str(base), "project": "demo", "artifact_candidates": []}]
            assets = collect_sessions.discover_assets(records, start, end, True, 3, 20,
                                                      context_images=[str(base / "manual.jpg")])
            self.assertEqual({Path(a["path"]).name for a in assets}, {"bench_photo.jpg", "manual.jpg"})
            self.assertTrue(all(a["period"] == "context" and a["role"] == "platform_context" for a in assets))

    def test_scan_budget_is_shared_deterministically_between_roots(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            start, end, _ = collect_sessions.local_window("today", "2026-07-15")
            records = []
            for name in ("b", "a"):
                root = base / name
                root.mkdir()
                records.append({"cwd": str(root), "project": name})
                for index in range(5):
                    path = root / f"{index}.png"
                    path.write_bytes(b"image")
                    os.utime(path, (start.timestamp(), start.timestamp()))
            assets = collect_sessions.discover_assets(records, start, end, True, 3, 2)
            self.assertEqual([(a["project"], Path(a["path"]).name) for a in assets], [("a", "0.png"), ("b", "0.png")])
            self.assertEqual(collect_sessions.discover_assets(records, start, end, True, 0, 20), [])

    def test_injected_asset_paths_and_secrets_are_not_candidates(self):
        text = '<INSTRUCTIONS>image /private/rules.png</INSTRUCTIONS> result /project/ber.png'
        self.assertEqual(collect_sessions.clean_artifact_paths({"text": text}), ["/project/ber.png"])
        self.assertEqual(collect_sessions.clean_artifact_paths({"text": 'api_key=/private/token.png'}), [])

    def test_project_filter_includes_children_but_not_prefix_siblings(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            project = base / "project"
            def parse_fixture(path, start, end, sessions):
                for index, root in enumerate((project, project / "run1", base / "project-other")):
                    record = collect_sessions.session_record(str(index), "codex", path)
                    record.update(cwd=str(root), project=root.name)
                    record["events"] = [{"timestamp": start.isoformat(), "role": "user", "text": "测试结果"}]
                    sessions[str(index)] = record
            args = type("Args", (), {"mode": "today", "date": "2026-07-15", "codex_root": str(base),
                                     "claude_root": str(base), "project_root": str(project), "scan_fallback": False})()
            with patch.object(collect_sessions, "codex_session_files", return_value=[base / "fixture.jsonl"]), \
                 patch.object(collect_sessions, "parse_codex_file", side_effect=parse_fixture):
                result = collect_sessions.collect(args)
            self.assertEqual({r["cwd"] for r in result["sessions"]}, {str(project), str(project / "run1")})

    def test_explicit_asset_root_is_scanned_without_broadening_session_root(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            start, end, _ = collect_sessions.local_window("today", "2026-07-15")
            image = base / "spectrum.png"
            image.write_bytes(b"image")
            os.utime(image, (start.timestamp(), start.timestamp()))
            assets = collect_sessions.discover_assets([], start, end, True, 3, 10, asset_roots=[str(base)])
            self.assertEqual([a["path"] for a in assets], [str(image)])

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
