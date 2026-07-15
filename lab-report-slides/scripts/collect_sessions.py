#!/usr/bin/env python3
"""Collect high-signal Codex and Claude Code session material for lab reports.

The collector deliberately emits structured evidence rather than attempting to
write the report itself. The calling skill can then summarize the evidence
with the current model and ask the user to approve a short outline.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import time
from collections import OrderedDict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable
from zoneinfo import ZoneInfo


LOCAL_TZ = ZoneInfo("Asia/Shanghai")
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".svg", ".gif", ".webp", ".bmp"}
ARTIFACT_EXTENSIONS = IMAGE_EXTENSIONS | {
    ".pdf",
    ".csv",
    ".xlsx",
    ".xls",
    ".mat",
    ".fig",
    ".html",
    ".pptx",
    ".mp4",
    ".webm",
}
SKIP_DIRS = {
    ".git",
    ".venv",
    "node_modules",
    "__pycache__",
    ".codex",
    ".claude",
    "dist",
    "build",
}
PATH_RE = re.compile(
    r"(?:(?:[A-Za-z]:\\|\\\\)[^\"<>|\r\n]{1,500}\.(?:png|jpg|jpeg|svg|gif|webp|bmp|pdf|csv|xlsx|xls|mat|fig|html|pptx|mp4|webm))",
    re.IGNORECASE,
)
POSIX_PATH_RE = re.compile(
    r"(?<![\w./-])/(?:[^\s\"<>|/]{1,120}/){1,20}[^\s\"<>|/]{1,240}\.(?:png|jpg|jpeg|svg|gif|webp|bmp|pdf|csv|xlsx|xls|mat|fig|html|pptx|mp4|webm)",
    re.IGNORECASE,
)
REDACTIONS = [
    (re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"), "[REDACTED_API_KEY]"),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b"), "[REDACTED_TOKEN]"),
    (re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._-]{20,}"), "Bearer [REDACTED_TOKEN]"),
    (re.compile(r"(?i)(password|passwd|api[_-]?key|secret)\s*[:=]\s*[^\s,;]+"), r"\1=[REDACTED]"),
]
RESULT_WORDS = re.compile(
    r"完成|结果|测试|实验|曲线|频谱|功率|噪声|BER|EVM|运行|输出|修复|定位|验证|失败|成功|下一步|保存|生成|导出",
    re.IGNORECASE,
)
CODEX_META_RE = re.compile(r'"type"\s*:\s*"session_meta"')
CODEX_EVENT_RE = re.compile(r'"type"\s*:\s*"event_msg"')
CODEX_VISIBLE_EVENT_RE = re.compile(r'"type"\s*:\s*"(?:user_message|agent_message|assistant_message)"')
CODEX_RESPONSE_RE = re.compile(r'"type"\s*:\s*"response_item"')
MESSAGE_ITEM_RE = re.compile(r'"type"\s*:\s*"message"')
CLAUDE_MESSAGE_RE = re.compile(r'"type"\s*:\s*"(?:user|assistant)"')
ARTIFACT_HINT_RE = re.compile(r'\.(?:png|jpg|jpeg|svg|gif|webp|bmp|pdf|csv|xlsx|xls|mat|fig|html|pptx|mp4|webm)', re.IGNORECASE)


def parse_timestamp(value: Any) -> datetime | None:
    if value is None:
        return None
    try:
        if isinstance(value, (int, float)):
            seconds = float(value)
            if seconds > 100_000_000_000:
                seconds /= 1000
            return datetime.fromtimestamp(seconds, timezone.utc).astimezone(LOCAL_TZ)
        raw = str(value).strip()
        if raw.isdigit():
            return parse_timestamp(int(raw))
        raw = raw.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(raw)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(LOCAL_TZ)
    except (TypeError, ValueError, OSError, OverflowError):
        return None


def local_window(mode: str, requested_date: str | None) -> tuple[datetime, datetime, str]:
    if requested_date:
        target = date.fromisoformat(requested_date)
    else:
        target = datetime.now(LOCAL_TZ).date()
    if mode == "week":
        start_date = target - timedelta(days=6)
    else:
        start_date = target
    start = datetime.combine(start_date, datetime.min.time(), tzinfo=LOCAL_TZ)
    end = datetime.combine(target + timedelta(days=1), datetime.min.time(), tzinfo=LOCAL_TZ)
    return start, end, target.isoformat()


def redact(text: str) -> str:
    result = text.replace("\x00", "").replace("\r\n", "\n").strip()
    for pattern, replacement in REDACTIONS:
        result = pattern.sub(replacement, result)
    if len(result) > 4000:
        result = result[:4000].rstrip() + " [...]"
    return result


def text_from_content(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(filter(None, (text_from_content(item) for item in value)))
    if isinstance(value, dict):
        block_type = value.get("type")
        if block_type in {"tool_result", "tool_use", "thinking", "reasoning"}:
            return ""
        if block_type in {"text", "input_text", "output_text"}:
            return text_from_content(value.get("text") or value.get("value") or "")
        for key in ("text", "content", "message", "output"):
            if key in value:
                text = text_from_content(value[key])
                if text:
                    return text
    return ""


def iter_strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for child in value.values():
            yield from iter_strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from iter_strings(child)


def candidate_paths(value: Any) -> list[str]:
    found: list[str] = []
    for item in iter_strings(value):
        normalized = item.replace("\\\\", "\\")
        matches = PATH_RE.findall(normalized) + POSIX_PATH_RE.findall(normalized)
        for match in matches:
            cleaned = match.rstrip(".,;:)]}\u3002，；：）")
            if not cleaned.lower().startswith(("http://", "https://")):
                found.append(cleaned)
    return found


def project_name(cwd: str | None) -> str:
    if not cwd:
        return "unknown-project"
    return Path(cwd).name or str(Path(cwd).parent.name) or "unknown-project"


def session_record(session_id: str, platform: str, source_path: Path) -> dict[str, Any]:
    return {
        "id": session_id,
        "platform": platform,
        "source_path": str(source_path),
        "cwd": None,
        "project": "unknown-project",
        "parent_id": None,
        "root_id": session_id,
        "is_subagent": False,
        "events": [],
        "artifact_candidates": [],
    }


def add_event(record: dict[str, Any], timestamp: datetime, role: str, text: str) -> None:
    cleaned = redact(text)
    if not cleaned or len(cleaned) < 4:
        return
    record["events"].append(
        {
            "timestamp": timestamp.isoformat(),
            "role": role,
            "text": cleaned,
        }
    )


def parse_codex_file(
    path: Path,
    start: datetime,
    end: datetime,
    sessions: OrderedDict[str, dict[str, Any]],
) -> None:
    session_id = path.stem
    record = sessions.setdefault(session_id, session_record(session_id, "codex", path))
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                has_artifact = bool(ARTIFACT_HINT_RE.search(line))
                relevant = bool(
                    CODEX_META_RE.search(line)
                    or (CODEX_EVENT_RE.search(line) and CODEX_VISIBLE_EVENT_RE.search(line))
                    or (CODEX_RESPONSE_RE.search(line) and MESSAGE_ITEM_RE.search(line))
                )
                if not relevant and not has_artifact:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                payload = event.get("payload") or {}
                event_type = event.get("type")
                if event_type == "session_meta":
                    session_id = str(payload.get("session_id") or payload.get("id") or session_id)
                    if session_id != record["id"]:
                        record = sessions.pop(record["id"], record)
                        record["id"] = session_id
                        sessions[session_id] = record
                    record["cwd"] = payload.get("cwd") or record["cwd"]
                    record["project"] = project_name(record["cwd"])
                    record["parent_id"] = payload.get("parent_thread_id") or record["parent_id"]
                    source = payload.get("source")
                    record["is_subagent"] = bool(record["parent_id"] or payload.get("thread_source") == "subagent" or (isinstance(source, dict) and source.get("subagent")))
                    continue
                timestamp = parse_timestamp(event.get("timestamp") or payload.get("timestamp"))
                if timestamp is None or not (start <= timestamp < end):
                    continue
                if has_artifact:
                    record["artifact_candidates"].extend(candidate_paths(line))
                role = ""
                text = ""
                if event_type == "event_msg":
                    subtype = payload.get("type")
                    if subtype == "user_message":
                        role, text = "user", text_from_content(payload.get("message") or payload.get("text"))
                    elif subtype in {"agent_message", "assistant_message"}:
                        role, text = "assistant", text_from_content(payload.get("message") or payload.get("text"))
                elif event_type == "response_item" and payload.get("type") == "message":
                    role = str(payload.get("role") or "")
                    if role in {"user", "assistant"}:
                        text = text_from_content(payload.get("content"))
                if role and text:
                    add_event(record, timestamp, role, text)
    except OSError:
        return


def parse_claude_file(
    path: Path,
    start: datetime,
    end: datetime,
    sessions: OrderedDict[str, dict[str, Any]],
) -> None:
    fallback_id = path.stem
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                has_artifact = bool(ARTIFACT_HINT_RE.search(line))
                if not CLAUDE_MESSAGE_RE.search(line) and not has_artifact:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                session_id = str(event.get("sessionId") or fallback_id)
                record = sessions.setdefault(session_id, session_record(session_id, "claude", path))
                record["cwd"] = event.get("cwd") or record["cwd"]
                record["project"] = project_name(record["cwd"])
                timestamp = parse_timestamp(event.get("timestamp"))
                if timestamp is None or not (start <= timestamp < end):
                    continue
                if has_artifact:
                    record["artifact_candidates"].extend(candidate_paths(line))
                event_type = event.get("type")
                if event_type not in {"user", "assistant"}:
                    continue
                message = event.get("message")
                role = event_type
                if isinstance(message, dict):
                    role = str(message.get("role") or role)
                    if role not in {"user", "assistant"}:
                        continue
                    text = text_from_content(message.get("content"))
                else:
                    text = text_from_content(message)
                if text:
                    add_event(record, timestamp, role, text)
    except OSError:
        return


def root_id_for(record: dict[str, Any], known: dict[str, dict[str, Any]]) -> str:
    current = record["id"]
    seen: set[str] = set()
    while current in known and known[current].get("parent_id") and current not in seen:
        seen.add(current)
        current = str(known[current]["parent_id"])
    return current


def select_events(events: list[dict[str, str]]) -> list[dict[str, str]]:
    if not events:
        return []
    users = [item for item in events if item["role"] == "user"]
    assistants = [item for item in events if item["role"] == "assistant"]
    selected: list[dict[str, str]] = users[-40:] + assistants[-12:]
    selected.extend(item for item in assistants if RESULT_WORDS.search(item["text"]))
    unique: dict[tuple[str, str], dict[str, str]] = {}
    for item in selected:
        unique[(item["timestamp"], item["text"])] = item
    return sorted(unique.values(), key=lambda item: item["timestamp"])


def normalize_path(raw: str, cwd: str | None) -> Path | None:
    path = Path(os.path.expandvars(os.path.expanduser(raw.strip())))
    if not path.is_absolute() and cwd:
        path = Path(cwd) / path
    try:
        return path.resolve()
    except OSError:
        return path


def discover_assets(
    records: list[dict[str, Any]],
    start: datetime,
    end: datetime,
    scan_fallback: bool,
    scan_seconds: float,
    scan_files: int,
) -> list[dict[str, Any]]:
    assets: dict[str, dict[str, Any]] = {}
    for record in records:
        cwd = record.get("cwd")
        for raw in record.get("artifact_candidates", []):
            path = normalize_path(raw, cwd)
            if not path or path.suffix.lower() not in IMAGE_EXTENSIONS or not path.exists() or not path.is_file():
                continue
            key = str(path)
            assets[key] = {"path": key, "source": "referenced", "project": record["project"]}
    # The fallback is intentionally opt-in after referenced assets fail. A full
    # recursive scan of a synced drive is too expensive for a daily command.
    if scan_fallback and not assets:
        roots = {str(Path(record["cwd"]).resolve()) for record in records if record.get("cwd") and Path(record["cwd"]).is_dir()}
        deadline = time.monotonic() + max(0.1, scan_seconds)
        scanned_files = 0
        for root in roots:
            for current, dirs, files in os.walk(root):
                dirs[:] = [name for name in dirs if name not in SKIP_DIRS]
                for name in files:
                    scanned_files += 1
                    if scanned_files > scan_files or time.monotonic() >= deadline:
                        return list(assets.values())
                    path = Path(current) / name
                    if path.suffix.lower() not in IMAGE_EXTENSIONS:
                        continue
                    try:
                        modified = datetime.fromtimestamp(path.stat().st_mtime, LOCAL_TZ)
                    except OSError:
                        continue
                    if not (start <= modified < end) or str(path) in assets:
                        continue
                    assets[str(path)] = {"path": str(path), "source": "scanned", "project": Path(root).name}
                    if len(assets) >= 80:
                        break
                if len(assets) >= 80:
                    break
            if len(assets) >= 80:
                break
    return list(assets.values())


def recent_files(paths: Iterable[Path], start: datetime, end: datetime, include_date_dirs: bool = False) -> list[Path]:
    """Avoid parsing years of immutable rollout files for a recent report."""
    target_dates = {start.date() + timedelta(days=offset) for offset in range((end.date() - start.date()).days)}
    result: list[Path] = []
    for path in paths:
        try:
            modified = datetime.fromtimestamp(path.stat().st_mtime, LOCAL_TZ)
        except OSError:
            continue
        if modified >= start:
            result.append(path)
            continue
        if include_date_dirs:
            normalized = path.as_posix()
            if any(f"/{item.year:04d}/{item.month:02d}/{item.day:02d}/" in normalized for item in target_dates):
                result.append(path)
    return result


def codex_session_files(root: Path, start: datetime, end: datetime) -> list[Path]:
    """Visit only date directories and index entries that can contain recent events."""
    session_root = root / "sessions"
    if not session_root.exists():
        return []
    target_markers = {
        f"/{(start.date() + timedelta(days=offset)).year:04d}/{(start.date() + timedelta(days=offset)).month:02d}/{(start.date() + timedelta(days=offset)).day:02d}/"
        for offset in range((end.date() - start.date()).days)
    }
    first_marker = f"/{(start.date() - timedelta(days=1)).year:04d}/{(start.date() - timedelta(days=1)).month:02d}/{(start.date() - timedelta(days=1)).day:02d}/"
    index_ids: set[str] = set()
    index_path = root / "session_index.jsonl"
    if index_path.exists():
        try:
            with index_path.open("r", encoding="utf-8", errors="replace") as handle:
                for line in handle:
                    try:
                        item = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    updated = parse_timestamp(item.get("updated_at"))
                    if updated is not None and start <= updated < end and item.get("id"):
                        index_ids.add(str(item["id"]))
        except OSError:
            pass
    result: list[Path] = []
    current = start.date()
    last = end.date() - timedelta(days=1)
    while current <= last:
        directory = session_root / f"{current.year:04d}" / f"{current.month:02d}" / f"{current.day:02d}"
        if directory.exists():
            entries = (item for item in directory.iterdir() if item.is_file() and item.name.startswith("rollout-") and item.suffix.lower() == ".jsonl")
            if current == start.date() - timedelta(days=1):
                if index_ids:
                    result.extend(item for item in entries if any(session_id in item.name for session_id in index_ids))
                else:
                    result.extend(recent_files(entries, start, end))
            else:
                result.extend(entries)
        current += timedelta(days=1)
    return result


def collect(args: argparse.Namespace) -> dict[str, Any]:
    start, end, target_date = local_window(args.mode, args.date)
    codex_root = Path(args.codex_root).expanduser()
    claude_root = Path(args.claude_root).expanduser()
    sessions: OrderedDict[str, dict[str, Any]] = OrderedDict()
    codex_files = codex_session_files(codex_root, start, end)
    archived = codex_root / "archived_sessions"
    if getattr(args, "include_archived", False) and archived.exists():
        codex_files.extend(recent_files((item for item in archived.iterdir() if item.suffix.lower() == ".jsonl"), start, end))
    for path in codex_files:
        parse_codex_file(path, start, end, sessions)
    projects = claude_root / "projects"
    claude_files = recent_files(projects.rglob("*.jsonl"), start, end) if projects.exists() else []
    for path in claude_files:
        parse_claude_file(path, start, end, sessions)

    known = dict(sessions)
    records: list[dict[str, Any]] = []
    for record in sessions.values():
        if not record["events"] and not record["artifact_candidates"]:
            continue
        record["root_id"] = root_id_for(record, known)
        record["events"] = select_events(record["events"])
        record["artifact_candidates"] = sorted(set(record["artifact_candidates"]))
        records.append(record)
    assets = discover_assets(
        records,
        start,
        end,
        getattr(args, "scan_fallback", True),
        getattr(args, "scan_seconds", 5.0),
        getattr(args, "scan_files", 2000),
    )
    project_names = sorted({record["project"] for record in records})
    return {
        "schema_version": 1,
        "timezone": "Asia/Shanghai",
        "mode": args.mode,
        "target_date": target_date,
        "window": {"start": start.isoformat(), "end": end.isoformat()},
        "sessions": records,
        "assets": assets,
        "projects": project_names,
        "stats": {
            "session_count": len(records),
            "root_task_count": len({record["root_id"] for record in records}),
            "message_count": sum(len(record["events"]) for record in records),
            "asset_count": len(assets),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("today", "week"), default="today")
    parser.add_argument("--date", help="Target local date in YYYY-MM-DD; defaults to today")
    parser.add_argument("--codex-root", default=str(Path.home() / ".codex"))
    parser.add_argument("--claude-root", default=str(Path.home() / ".claude"))
    parser.add_argument("--scan-fallback", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--include-archived", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--scan-seconds", type=float, default=5.0)
    parser.add_argument("--scan-files", type=int, default=2000)
    parser.add_argument("--out", required=True, help="Output JSON path")
    args = parser.parse_args()
    result = collect(args)
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result["stats"], ensure_ascii=False))


if __name__ == "__main__":
    main()
