#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable


ANALYSIS_STATUSES = {"new", "analyzed", "changed_since_last_analysis"}
ACTION_STATUSES = {"pending_review", "reviewed", "adopted", "dismissed"}


@dataclass
class CandidateSession:
    project_root: Path
    session_path: Path
    session_id: str
    started_at: str
    cwd: str
    thread_name: str
    signature: dict[str, Any]
    signal_summary: dict[str, Any]
    project_slug: str
    session_slug: str
    report_path: Path

    @property
    def run_key(self) -> str:
        return normalize_path(self.session_path)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def default_codex_home() -> Path:
    return Path.home() / ".codex"


def resolve_loose(path: Path | str) -> Path:
    return Path(path).expanduser().resolve(strict=False)


def normalize_path(path: Path | str) -> str:
    return str(resolve_loose(path)).replace("\\", "/").lower()


def is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def slugify(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-._")
    return slug.lower() or "item"


def combined_slug(parts: list[str], fallback: str) -> str:
    clean = [slugify(part) for part in parts if part]
    joined = "-".join([part for part in clean if part])
    return joined[:120] if joined else slugify(fallback)


def shorten(text: str, limit: int = 120) -> str:
    clean = " ".join(text.strip().split())
    if len(clean) <= limit:
        return clean
    return clean[: limit - 3] + "..."


def as_text(value: object) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(as_text(item) for item in value)
    if isinstance(value, dict):
        try:
            return json.dumps(value, ensure_ascii=False)
        except TypeError:
            return str(value)
    if value is None:
        return ""
    return str(value)


def parse_iso_datetime(value: str) -> datetime:
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value).astimezone()


def iso_mtime(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_signature(session_path: Path) -> dict[str, Any]:
    stat = session_path.stat()
    info = {
        "path": str(session_path),
        "exists": True,
        "size_bytes": stat.st_size,
        "modified_at": iso_mtime(session_path),
        "sha256": sha256_file(session_path),
    }
    return {
        "files": {"session_jsonl": info},
        "combined_hash": info["sha256"],
    }


def week_bounds(date_str: str) -> tuple[date, date]:
    target = date.fromisoformat(date_str)
    start = target - timedelta(days=target.weekday())
    return start, target


def iter_session_files(codex_home: Path, week_start: date, week_end: date) -> Iterable[Path]:
    seen: set[str] = set()
    sessions_root = codex_home / "sessions"
    if sessions_root.exists():
        current = week_start
        while current <= week_end:
            day_dir = sessions_root / f"{current.year:04d}" / f"{current.month:02d}" / f"{current.day:02d}"
            if day_dir.exists():
                for path in sorted(day_dir.glob("*.jsonl")):
                    key = normalize_path(path)
                    if key not in seen:
                        seen.add(key)
                        yield path
            current += timedelta(days=1)
    archived_root = codex_home / "archived_sessions"
    if archived_root.exists():
        for path in sorted(archived_root.glob("*.jsonl")):
            key = normalize_path(path)
            if key not in seen:
                seen.add(key)
                yield path


def load_session_index(path: Path) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    if not path.exists():
        return result
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            session_id = obj.get("id")
            if session_id:
                result[session_id] = obj
    return result


def detect_git_root(path: Path, root: Path) -> Path | None:
    current = resolve_loose(path)
    root = resolve_loose(root)
    while True:
        if (current / ".git").exists():
            return current
        if current == root or current.parent == current or not is_relative_to(current.parent, root):
            return None
        current = current.parent


def remap_worktree_path(cwd: Path, root: Path) -> Path | None:
    parts = list(cwd.parts)
    lowered = [part.lower() for part in parts]
    try:
        idx = lowered.index("worktrees")
    except ValueError:
        return None
    if idx == 0 or lowered[idx - 1] != ".codex":
        return None
    repo_name = parts[-1]
    candidate = resolve_loose(root / repo_name)
    if candidate.exists():
        return candidate
    return None


def canonical_project_root(raw_cwd: str, root: Path) -> Path | None:
    if not raw_cwd:
        return None
    root = resolve_loose(root)
    cwd = resolve_loose(raw_cwd)
    candidate = cwd if is_relative_to(cwd, root) else remap_worktree_path(cwd, root)
    if candidate is None or not is_relative_to(candidate, root):
        return None
    git_root = detect_git_root(candidate, root)
    return git_root or candidate


def project_slug_from_root(project_root: Path, root: Path) -> str:
    root = resolve_loose(root)
    project_root = resolve_loose(project_root)
    try:
        rel_parts = list(project_root.relative_to(root).parts)
    except ValueError:
        rel_parts = list(project_root.parts[-3:])
    return combined_slug(rel_parts, project_root.name)


def collect_session_signals(handle: Iterable[str]) -> dict[str, Any]:
    user_messages = 0
    user_examples: list[str] = []
    tool_calls = 0
    tool_failures: list[str] = []

    for line in handle:
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        outer_type = obj.get("type")
        payload = obj.get("payload", {})
        if outer_type == "event_msg" and payload.get("type") == "user_message":
            message = payload.get("message", "").strip()
            if message:
                user_messages += 1
                short = shorten(message)
                if len(user_examples) < 3 and short not in user_examples:
                    user_examples.append(short)
        elif outer_type == "response_item":
            item_type = payload.get("type")
            if item_type == "function_call":
                tool_calls += 1
            elif item_type == "function_call_output":
                output = as_text(payload.get("output", ""))
                if not output:
                    continue
                match = re.search(r"Exit code:\s*(-?\d+)", output)
                if match and int(match.group(1)) != 0:
                    short = shorten(output.replace("\r", " ").replace("\n", " "))
                    if len(tool_failures) < 3 and short not in tool_failures:
                        tool_failures.append(short)

    return {
        "user_message_count": user_messages,
        "user_message_examples": user_examples,
        "tool_call_count": tool_calls,
        "tool_failure_examples": tool_failures,
    }


def discover_sessions(
    root: Path,
    reports_root: Path,
    codex_home: Path,
    week_start: date,
    week_end: date,
    session_index: dict[str, dict[str, Any]],
) -> list[CandidateSession]:
    candidates: list[CandidateSession] = []
    for session_path in iter_session_files(codex_home, week_start, week_end):
        try:
            with session_path.open("r", encoding="utf-8") as handle:
                first_line = handle.readline()
                if not first_line:
                    continue
                first = json.loads(first_line)
                if first.get("type") != "session_meta":
                    continue
                meta = first.get("payload", {})
                started_at = parse_iso_datetime(meta["timestamp"])
                started_date = started_at.date()
                if started_date < week_start or started_date > week_end:
                    continue
                raw_cwd = meta.get("cwd", "")
                project_root = canonical_project_root(raw_cwd, root)
                if project_root is None:
                    continue
                session_id = meta.get("id", session_path.stem)
                thread_name = session_index.get(session_id, {}).get("thread_name", "").strip()
                signal_summary = collect_session_signals(handle)
        except (json.JSONDecodeError, KeyError, OSError):
            continue

        project_slug = project_slug_from_root(project_root, root)
        session_slug = combined_slug(
            [started_date.isoformat(), session_path.stem, thread_name or session_id[-8:]],
            session_path.stem,
        )
        report_path = reports_root / "projects" / project_slug / "{date}" / f"{session_slug}.md"
        candidates.append(
            CandidateSession(
                project_root=project_root,
                session_path=resolve_loose(session_path),
                session_id=session_id,
                started_at=started_at.isoformat(),
                cwd=raw_cwd,
                thread_name=thread_name,
                signature=build_signature(session_path),
                signal_summary=signal_summary,
                project_slug=project_slug,
                session_slug=session_slug,
                report_path=report_path,
            )
        )

    candidates.sort(key=lambda item: (item.project_slug, item.started_at, item.run_key))
    return candidates


def ensure_reports_layout(reports_root: Path) -> None:
    for name in ("projects", "cross-project", "weekly", "manifests"):
        (reports_root / name).mkdir(parents=True, exist_ok=True)


def load_index(reports_root: Path) -> dict[str, Any]:
    path = reports_root / "index.json"
    if not path.exists():
        return {"version": 1, "entries": {}}
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def save_index(reports_root: Path, index_data: dict[str, Any]) -> None:
    path = reports_root / "index.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(index_data, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")


def write_text_if_missing(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(content, encoding="utf-8", newline="\n")


def candidate_to_manifest(candidate: CandidateSession, date_str: str) -> dict[str, Any]:
    report_path = Path(str(candidate.report_path).replace("{date}", date_str))
    return {
        "run_key": candidate.run_key,
        "project_root": str(candidate.project_root),
        "project_slug": candidate.project_slug,
        "session_path": str(candidate.session_path),
        "session_id": candidate.session_id,
        "session_slug": candidate.session_slug,
        "started_at": candidate.started_at,
        "cwd": candidate.cwd,
        "thread_name": candidate.thread_name,
        "report_path": str(report_path),
        "signature": candidate.signature,
        "signal_summary": candidate.signal_summary,
    }


def entry_to_manifest(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "run_key": entry["run_key"],
        "project_root": entry["project_root"],
        "project_slug": entry["project_slug"],
        "session_path": entry["session_path"],
        "session_id": entry["session_id"],
        "session_slug": entry["session_slug"],
        "started_at": entry["started_at"],
        "cwd": entry["cwd"],
        "thread_name": entry.get("thread_name", ""),
        "report_path": entry.get("report_path"),
        "signature": entry.get("signature", {}),
        "signal_summary": entry.get("signal_summary", {}),
    }


def render_signal_block(item: dict[str, Any]) -> str:
    signals = item.get("signal_summary", {})
    lines = [
        f"- 用户消息数：{signals.get('user_message_count', 0)}",
        f"- 工具调用数：{signals.get('tool_call_count', 0)}",
    ]
    failure_examples = signals.get("tool_failure_examples") or []
    if failure_examples:
        lines.append("- 非零退出工具样例：")
        for example in failure_examples:
            lines.append(f"  - {example}")
    else:
        lines.append("- 非零退出工具样例：暂无")
    user_examples = signals.get("user_message_examples") or []
    if user_examples:
        lines.append("- 用户消息样例：")
        for example in user_examples:
            lines.append(f"  - {example}")
    else:
        lines.append("- 用户消息样例：暂无")
    return "\n".join(lines)


def render_session_report_stub(item: dict[str, Any]) -> str:
    thread_name = item.get("thread_name") or "未命名 thread"
    return f"""# 技能复盘对话记录
- 项目路径：`{item['project_root']}`
- session 路径：`{item['session_path']}`
- session_id：`{item['session_id']}`
- 开始时间：`{item['started_at']}`
- 工作目录：`{item['cwd']}`
- thread：`{thread_name}`

## 关键信号

{render_signal_block(item)}

## 这周反复出现的问题

- 待补充

## 下周最容易再出问题的地方

- 待补充

## 哪些改法值得采纳

- 待补充

## 哪些事情先继续观察

- 待补充

## 证据路径

- `session_path`：`{item['session_path']}`
- `report_path`：`{item['report_path']}`
"""


def item_label(item: dict[str, Any]) -> str:
    thread_name = item.get("thread_name", "").strip()
    if thread_name:
        return f"`{thread_name}` (`{item['session_path']}`)"
    return f"`{item['session_path']}`"


def render_project_summary_stub(
    project_root: str,
    analysis_items: list[dict[str, Any]],
    pending_items: list[dict[str, Any]],
) -> str:
    analysis_lines = [f"- {item_label(item)}" for item in analysis_items] or ["- 无"]
    pending_lines = [f"- {item_label(item)}" for item in pending_items] or ["- 无"]
    return f"""# 项目技能复盘周报
- 项目路径：`{project_root}`

## 本周新增/变化对话

{chr(10).join(analysis_lines)}

## 未处理遗留项

{chr(10).join(pending_lines)}

## 本项目重复模式

- 待补充
"""


def render_cross_project_stub(date_str: str, grouped_patterns: list[dict[str, Any]]) -> str:
    if grouped_patterns:
        pattern_lines = []
        for item in grouped_patterns:
            pattern_lines.append(f"- `{item['pattern_key']}`: {', '.join(item['projects'])}")
        pattern_block = "\n".join(pattern_lines)
    else:
        pattern_block = "- 暂无跨项目重复模式，等项目摘要完成后再补充。"
    return f"""# 跨项目技能复盘观察
- 日期：`{date_str}`

## 共享改进候选

{pattern_block}

## 说明

- 这里只基于项目摘要归纳，不跨项目混读原始对话。
- 只有同类问题在 2 个以上项目重复出现时，才升级为共享候选。
"""


def render_weekly_stub(date_str: str, week_start: date, analysis_items: list[dict[str, Any]], pending_items: list[dict[str, Any]]) -> str:
    new_lines = [f"- {item_label(item)}" for item in analysis_items] or ["- 无"]
    pending_lines = [f"- {item_label(item)}" for item in pending_items] or ["- 无"]
    return f"""# 每周技能复盘总览

- 日期：`{date_str}`
- 周窗口：`{week_start.isoformat()}` 到 `{date_str}`

## 本周新增/变化对话

{chr(10).join(new_lines)}

## 未处理遗留项

{chr(10).join(pending_lines)}

## 跨项目观察

- 见 `cross-project/{date_str}.md`

## 执行说明

- 对本周新建或有变化的 session 生成项目级报告并补全分析。
- 对未变化但仍处于 `pending_review` 的旧项只做提醒，不重复长篇分析。
"""


def cmd_scan(args: argparse.Namespace) -> int:
    root = resolve_loose(args.root)
    reports_root = resolve_loose(args.reports_root)
    codex_home = resolve_loose(args.codex_home)
    date_str = args.date
    timestamp = args.now or utc_now()
    week_start, week_end = week_bounds(date_str)

    ensure_reports_layout(reports_root)
    session_index = load_session_index(codex_home / "session_index.jsonl")
    index_data = load_index(reports_root)
    entries = index_data.setdefault("entries", {})

    analysis_queue: list[dict[str, Any]] = []
    discovered_manifests: dict[str, dict[str, Any]] = {}

    for candidate in discover_sessions(root, reports_root, codex_home, week_start, week_end, session_index):
        manifest = candidate_to_manifest(candidate, date_str)
        discovered_manifests[manifest["run_key"]] = manifest
        entry = entries.get(candidate.run_key)
        if entry is None:
            entries[candidate.run_key] = {
                "run_key": candidate.run_key,
                "project_root": manifest["project_root"],
                "project_slug": manifest["project_slug"],
                "session_path": manifest["session_path"],
                "session_id": manifest["session_id"],
                "session_slug": manifest["session_slug"],
                "started_at": manifest["started_at"],
                "cwd": manifest["cwd"],
                "thread_name": manifest["thread_name"],
                "analysis_status": "new",
                "action_status": "pending_review",
                "signature": manifest["signature"],
                "signal_summary": manifest["signal_summary"],
                "last_analyzed_at": None,
                "last_reminded_at": None,
                "report_path": None,
                "action_updated_at": None,
                "action_note": None,
            }
            analysis_queue.append(manifest)
            continue

        entry["project_root"] = manifest["project_root"]
        entry["project_slug"] = manifest["project_slug"]
        entry["session_path"] = manifest["session_path"]
        entry["session_id"] = manifest["session_id"]
        entry["session_slug"] = manifest["session_slug"]
        entry["started_at"] = manifest["started_at"]
        entry["cwd"] = manifest["cwd"]
        entry["thread_name"] = manifest["thread_name"]
        entry["signal_summary"] = manifest["signal_summary"]

        if entry.get("signature", {}).get("combined_hash") != manifest["signature"]["combined_hash"]:
            entry["analysis_status"] = "changed_since_last_analysis"
            entry["action_status"] = "pending_review"
            entry["signature"] = manifest["signature"]
            analysis_queue.append(manifest)
        elif entry.get("analysis_status") in {"new", "changed_since_last_analysis"}:
            analysis_queue.append(manifest)
        else:
            entry["signature"] = manifest["signature"]

    pending_queue: list[dict[str, Any]] = []
    for entry in entries.values():
        if not entry.get("session_path"):
            continue
        if entry.get("analysis_status") == "analyzed" and entry.get("action_status") == "pending_review":
            pending_queue.append(entry_to_manifest(entry))

    analysis_queue.sort(key=lambda item: (item["project_slug"], item["started_at"], item["session_path"]))
    pending_queue.sort(key=lambda item: (item["project_slug"], item["started_at"], item["session_path"]))

    project_groups: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for item in analysis_queue:
        bucket = project_groups.setdefault(item["project_slug"], {"analysis": [], "pending": []})
        bucket["analysis"].append(item)
    for item in pending_queue:
        bucket = project_groups.setdefault(item["project_slug"], {"analysis": [], "pending": []})
        bucket["pending"].append(item)

    manifest_root = reports_root / "manifests" / date_str
    write_json(manifest_root / "analysis_queue.json", analysis_queue)
    write_json(manifest_root / "pending_queue.json", pending_queue)
    write_json(manifest_root / "projects.json", project_groups)

    for item in analysis_queue:
        report_path = Path(item["report_path"])
        write_text_if_missing(report_path, render_session_report_stub(item))

    for project_slug, payload in project_groups.items():
        if payload["analysis"] or payload["pending"]:
            project_root = (payload["analysis"] or payload["pending"])[0]["project_root"]
        else:
            project_root = ""
        summary_path = reports_root / "projects" / project_slug / date_str / "summary.md"
        write_text_if_missing(summary_path, render_project_summary_stub(project_root, payload["analysis"], payload["pending"]))

    weekly_path = reports_root / "weekly" / f"{date_str}.md"
    cross_project_path = reports_root / "cross-project" / f"{date_str}.md"
    write_text_if_missing(weekly_path, render_weekly_stub(date_str, week_start, analysis_queue, pending_queue))
    write_text_if_missing(cross_project_path, render_cross_project_stub(date_str, []))

    index_data["last_scanned_at"] = timestamp
    index_data["root"] = str(root)
    index_data["codex_home"] = str(codex_home)
    index_data["window_start"] = week_start.isoformat()
    index_data["window_end"] = week_end.isoformat()
    save_index(reports_root, index_data)

    summary = {
        "date": date_str,
        "window_start": week_start.isoformat(),
        "window_end": week_end.isoformat(),
        "scanned_root": str(root),
        "codex_home": str(codex_home),
        "discovered_session_count": len(discovered_manifests),
        "analysis_count": len(analysis_queue),
        "pending_count": len(pending_queue),
        "weekly_path": str(weekly_path),
        "cross_project_path": str(cross_project_path),
        "manifest_root": str(manifest_root),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def cmd_finalize(args: argparse.Namespace) -> int:
    reports_root = resolve_loose(args.reports_root)
    date_str = args.date
    timestamp = args.now or utc_now()
    index_data = load_index(reports_root)
    entries = index_data.setdefault("entries", {})
    manifest_root = reports_root / "manifests" / date_str

    analysis_path = manifest_root / "analysis_queue.json"
    pending_path = manifest_root / "pending_queue.json"
    analysis_queue = json.loads(analysis_path.read_text(encoding="utf-8")) if analysis_path.exists() else []
    pending_queue = json.loads(pending_path.read_text(encoding="utf-8")) if pending_path.exists() else []

    for item in analysis_queue:
        entry = entries.get(item["run_key"])
        if not entry:
            continue
        entry["analysis_status"] = "analyzed"
        entry["action_status"] = "pending_review"
        entry["last_analyzed_at"] = timestamp
        entry["report_path"] = item["report_path"]
        entry["signature"] = item["signature"]
        entry["signal_summary"] = item.get("signal_summary", {})

    for item in pending_queue:
        entry = entries.get(item["run_key"])
        if not entry:
            continue
        if entry.get("action_status") == "pending_review":
            entry["last_reminded_at"] = timestamp

    index_data["last_finalized_at"] = timestamp
    save_index(reports_root, index_data)
    print(
        json.dumps(
            {
                "date": date_str,
                "finalized_analysis_count": len(analysis_queue),
                "reminded_count": len(pending_queue),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def cmd_mark_action(args: argparse.Namespace) -> int:
    reports_root = resolve_loose(args.reports_root)
    run_key = normalize_path(args.run_dir)
    timestamp = args.now or utc_now()
    index_data = load_index(reports_root)
    entries = index_data.setdefault("entries", {})
    entry = entries.get(run_key)
    if not entry:
        raise SystemExit(f"Run dir not found in index: {args.run_dir}")
    entry["action_status"] = args.status
    entry["action_updated_at"] = timestamp
    if args.note:
        entry["action_note"] = args.note
    save_index(reports_root, index_data)
    print(
        json.dumps(
            {
                "run_dir": entry.get("session_path", entry.get("run_dir")),
                "action_status": entry["action_status"],
                "action_updated_at": entry["action_updated_at"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Scan weekly Codex sessions and maintain skill retro reports.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    scan_parser = subparsers.add_parser("scan", help="Discover weekly sessions and prepare review manifests.")
    scan_parser.add_argument("--root", required=True)
    scan_parser.add_argument("--reports-root", required=True)
    scan_parser.add_argument("--date", required=True)
    scan_parser.add_argument("--codex-home", default=str(default_codex_home()))
    scan_parser.add_argument("--now")
    scan_parser.set_defaults(func=cmd_scan)

    finalize_parser = subparsers.add_parser("finalize", help="Finalize weekly analysis and reminder state.")
    finalize_parser.add_argument("--reports-root", required=True)
    finalize_parser.add_argument("--date", required=True)
    finalize_parser.add_argument("--now")
    finalize_parser.set_defaults(func=cmd_finalize)

    mark_parser = subparsers.add_parser("mark-action", help="Update action_status for one analyzed session.")
    mark_parser.add_argument("--reports-root", required=True)
    mark_parser.add_argument("--run-dir", required=True)
    mark_parser.add_argument("--status", required=True, choices=sorted(ACTION_STATUSES))
    mark_parser.add_argument("--note")
    mark_parser.add_argument("--now")
    mark_parser.set_defaults(func=cmd_mark_action)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
