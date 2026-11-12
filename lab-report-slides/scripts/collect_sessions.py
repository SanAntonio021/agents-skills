#!/usr/bin/env python3
"""Collect high-signal Codex, Claude Code and Cursor session material for lab reports.

The collector deliberately emits structured evidence rather than attempting to
write the report itself. The calling skill can then summarize the evidence
with the current model and reuse an already agreed report scope.
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
    ".cc-switch",
    ".agents",
    "dist",
    "build",
}
IGNORED_SCAN_ROOTS = {".agents", ".cc-switch", ".codex", ".claude"}
IGNORED_ASSET_SEQUENCES = (
    (".agents", "skills"),
    (".cc-switch", "skills"),
    (".claude", "skills"),
    (".codex", "skills"),
    (".codex", "plugins"),
)
PATH_RE = re.compile(
    r"(?:(?:[A-Za-z]:[\\/]|\\\\)[^\"<>|;\r\n]{1,500}?\.(?:png|jpg|jpeg|svg|gif|webp|bmp|pdf|csv|xlsx|xls|mat|fig|html|pptx|mp4|webm))(?=$|[\s\"'<>`,;:!?\])}。，；：）])",
    re.IGNORECASE,
)
POSIX_PATH_RE = re.compile(
    r"(?<![\w./-])/(?:[^\s\"<>|/]{1,120}/){1,20}[^\s\"<>|/]{1,240}\.(?:png|jpg|jpeg|svg|gif|webp|bmp|pdf|csv|xlsx|xls|mat|fig|html|pptx|mp4|webm)",
    re.IGNORECASE,
)
MARKDOWN_LINK_RE = re.compile(r"!?\[[^\]\r\n]*\]\(\s*(<[^>\r\n]+>|[^)\r\n]+)\s*\)")
HTTP_URL_RE = re.compile(r"https?://[^\s<>\"\r\n]+", re.IGNORECASE)
REDACTIONS = [
    (re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"), "[REDACTED_API_KEY]"),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b"), "[REDACTED_TOKEN]"),
    (re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._-]{20,}"), "Bearer [REDACTED_TOKEN]"),
]
# Labelled secrets, including Chinese labels and full-width colons such as "密码：...".
LABELLED_SECRET_RE = re.compile(
    r"(?i)(password|passwd|api[_-]?key|secret|密码|口令|密钥)\s*[:：=]\s*([^\s,;，；。、]+)"
)
# Values seen behind a label during this run. The same value is often repeated
# without its label (tables, echoes), so those mentions are scrubbed as well.
SECRET_VALUES: set[str] = set()
CURSOR_TIMESTAMP_RE = re.compile(
    r"<timestamp>\s*(?:[A-Za-z]+,\s*)?([A-Za-z]{3,9})\s+(\d{1,2}),\s*(\d{4}),\s*(\d{1,2}):(\d{2})\s*([AP]M)\s*"
    r"\(UTC(?:([+-]\d{1,2})(?::(\d{2}))?)?\)\s*</timestamp>"
)
CURSOR_QUERY_RE = re.compile(r"<user_query>(.*?)</user_query>", re.DOTALL)
CURSOR_BLOCK_RE = re.compile(
    r"<(user_info|agent_transcripts|rules|available_subagent_types|available_subagent_models|agent_skills|"
    r"dynamic_tool_catalog|manually_attached_skills|system_reminder|system_notification|attached_files|timestamp)"
    r"\b[^>]*>.*?</\1>",
    re.DOTALL,
)
MONTHS = {name: number for number, name in enumerate(
    ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"), 1)}
CURSOR_WORKSPACES: dict[str, str | None] = {}
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
INJECTED_BLOCK_RE = re.compile(
    r"<(recommended_plugins|INSTRUCTIONS|environment_context|local-command-caveat|"
    r"command-name|command-message|command-args|local-command-stdout|ide_opened_file|"
    r"skills_instructions|plugins_instructions|app-context|codex_delegation|oai-mem-citation)"
    r"\b[^>]*>.*?</\1>",
    re.IGNORECASE | re.DOTALL,
)
INJECTED_HEADING_RE = re.compile(r"(?im)^\s*#\s*AGENTS\.md instructions(?:\s+for\s+.*)?\s*$")
SKILL_DUMP_RE = re.compile(r"(?im)^\s*Base directory for this skill:\s*.+$")
CONTEXT_IMAGE_RE = re.compile(r"(?:^|[\\/_. -])(?:photos?|setup|bench|apparatus)(?:$|[\\/_. -])|台架|照片|实验平台", re.IGNORECASE)


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


def collection_window(args: argparse.Namespace) -> tuple[datetime, datetime, str, str]:
    """Use an explicit report-to-report interval without changing calendar modes."""
    since, until = getattr(args, "since", None), getattr(args, "until", None)
    if since is None:
        if until is not None:
            raise ValueError("--until requires --since")
        start, end, target = local_window(args.mode, args.date)
        return start, end, target, args.mode
    if getattr(args, "date", None):
        raise ValueError("Choose --since/--until or --date, not both")
    def bound(value: str) -> datetime | None:
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=LOCAL_TZ)
            return parsed.astimezone(LOCAL_TZ)
        except (ValueError, TypeError):
            return None

    start = bound(since)
    end = bound(until) if until is not None else datetime.now(LOCAL_TZ)
    if start is None or end is None:
        raise ValueError("--since and --until must be ISO dates or timestamps")
    if end <= start:
        raise ValueError("--until must be later than --since")
    return start, end, end.date().isoformat(), "interval"


def remember_secret(match: re.Match[str]) -> str:
    value = match.group(2).strip("`'\"*|()（）[]<>")
    mixed = len(value) >= 6 and re.search(r"\d", value) and re.search(r"[A-Za-z]", value)
    if "[REDACTED" not in value and (len(value) >= 8 or mixed):
        SECRET_VALUES.add(value)
    return f"{match.group(1)}=[REDACTED]"


def scrub_secret_values(records: Iterable[dict[str, Any]]) -> None:
    """Remove bare repeats of values that appeared behind a secret label in this run."""
    if not SECRET_VALUES:
        return
    pattern = re.compile("|".join(re.escape(value) for value in sorted(SECRET_VALUES, key=len, reverse=True)))
    for record in records:
        for event in record["events"]:
            event["text"] = pattern.sub("[REDACTED]", event["text"])
        record["artifact_candidates"] = [path for path in record["artifact_candidates"] if not pattern.search(path)]


def redact(text: str) -> str:
    result = text.replace("\x00", "").replace("\r\n", "\n").strip()
    for pattern, replacement in REDACTIONS:
        result = pattern.sub(replacement, result)
    result = LABELLED_SECRET_RE.sub(remember_secret, result)
    if len(result) > 4000:
        result = result[:4000].rstrip() + " [...]"
    return result


def strip_injected_text(text: str) -> str:
    result = INJECTED_BLOCK_RE.sub("", text)
    skill_dump = SKILL_DUMP_RE.search(result)
    if skill_dump:
        result = result[: skill_dump.start()]
    result = INJECTED_HEADING_RE.sub("", result)
    result = re.sub(r"\n{3,}", "\n\n", result)
    return result.strip()


def clean_event_text(text: str) -> str:
    return redact(strip_injected_text(text))


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
        matches = []
        for link in MARKDOWN_LINK_RE.finditer(item):
            target = link.group(1).strip()
            if target.startswith("<") and target.endswith(">"):
                target = target[1:-1]
            else:
                target = re.sub(r'\s+[\"\'][^\"\']*[\"\']\s*$', "", target)
            if not re.match(r"^[A-Za-z][A-Za-z0-9+.-]*://", target) and Path(target).suffix.lower() in ARTIFACT_EXTENSIONS:
                matches.append(target)
        # JSON has already decoded backslashes. Preserve UNC prefixes and keep
        # remote URLs/Markdown targets out of the bare local-path scan.
        bare = HTTP_URL_RE.sub("", MARKDOWN_LINK_RE.sub("", item))
        matches.extend(PATH_RE.findall(bare) + POSIX_PATH_RE.findall(bare))
        for match in matches:
            cleaned = match.rstrip(".,;:)]}\u3002，；：）")
            if not cleaned.lower().startswith(("http://", "https://")):
                if cleaned not in found:
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
    cleaned = clean_event_text(text)
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
                    record["artifact_candidates"].extend(clean_artifact_paths(payload))
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
                    record["artifact_candidates"].extend(clean_artifact_paths(event.get("message", {})))
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


def cursor_timestamp(text: str) -> datetime | None:
    """Cursor stamps each user message, e.g. 'Thursday, Nov 12, 2026, 5:57 AM (UTC-7)'."""
    match = CURSOR_TIMESTAMP_RE.search(text)
    if not match:
        return None
    month, day, year, hour, minute, half, offset_hours, offset_minutes = match.groups()
    month_number = MONTHS.get(month[:3].lower())
    if month_number is None:
        return None
    offset = timedelta(hours=abs(int(offset_hours or 0)), minutes=int(offset_minutes or 0))
    if (offset_hours or "").startswith("-"):
        offset = -offset
    try:
        return datetime(int(year), month_number, int(day), int(hour) % 12 + (12 if half == "PM" else 0),
                        int(minute), tzinfo=timezone(offset)).astimezone(LOCAL_TZ)
    except ValueError:
        return None


def cursor_user_text(text: str) -> str:
    queries = [item.strip() for item in CURSOR_QUERY_RE.findall(text)]
    if queries:
        return "\n\n".join(item for item in queries if item)
    return CURSOR_BLOCK_RE.sub("", text).strip()


def cursor_slug(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", name).strip("-")


def cursor_workspace(folder: str) -> str | None:
    """Best-effort reverse of Cursor's project folder name.

    Cursor replaces every run of characters outside [A-Za-z0-9] with '-', so
    different folders can share one name. Only a unique match is returned.
    """
    if folder in CURSOR_WORKSPACES:
        return CURSOR_WORKSPACES[folder]
    head, _, rest = folder.partition("-")
    drive = Path(f"{head.upper()}:\\") if os.name == "nt" and len(head) == 1 and head.isalpha() else None
    root, remaining = (drive, rest) if drive is not None and drive.is_dir() else (Path(os.sep), folder)
    matches: list[Path] = []

    def descend(current: Path, left: str, depth: int) -> None:
        if len(matches) > 1 or depth > 16:
            return
        if not left:
            matches.append(current)
            return
        try:
            children = [entry for entry in os.scandir(current) if entry.is_dir(follow_symlinks=False)]
        except OSError:
            return
        for entry in children:
            part = cursor_slug(entry.name)
            if part and (left == part or left.startswith(part + "-")):
                descend(Path(entry.path), left[len(part) + 1:], depth + 1)

    if remaining:
        descend(root, remaining, 0)
    CURSOR_WORKSPACES[folder] = str(matches[0]) if len(matches) == 1 else None
    return CURSOR_WORKSPACES[folder]


def cursor_session_files(root: Path, start: datetime, end: datetime) -> list[tuple[Path, str | None]]:
    """Return (transcript, parent id). A subagent copy is used only without a top-level transcript."""
    projects = root / "projects"
    if not projects.exists():
        return []
    chosen: dict[str, Path] = {}
    parents: dict[str, str] = {}
    for path in sorted(projects.glob("*/agent-transcripts/*/subagents/*.jsonl")):
        parents[path.stem] = path.parent.parent.name
        chosen[path.stem] = path
    for path in sorted(projects.glob("*/agent-transcripts/*/*.jsonl")):
        chosen[path.stem] = path
    recent = set(recent_files(chosen.values(), start, end))
    return [(path, parents.get(session_id)) for session_id, path in sorted(chosen.items()) if path in recent]


def parse_cursor_file(
    path: Path,
    start: datetime,
    end: datetime,
    sessions: OrderedDict[str, dict[str, Any]],
    parent_id: str | None = None,
) -> None:
    """Keep each turn's request and final answer; progress notes between tool calls are skipped."""
    record = sessions.setdefault(path.stem, session_record(path.stem, "cursor", path))
    if parent_id:
        record["parent_id"], record["is_subagent"] = parent_id, True
    folder = next((parent.parent.name for parent in path.parents if parent.name == "agent-transcripts"), "")
    record["cwd"] = cursor_workspace(folder) if folder else None
    record["project"] = project_name(record["cwd"]) if record["cwd"] else (folder or "unknown-project")
    try:
        fallback = datetime.fromtimestamp(path.stat().st_mtime, LOCAL_TZ)
    except OSError:
        return
    turn_time: datetime | None = None
    clock: datetime | None = None
    answer = ""

    def emit(role: str, text: str) -> None:
        nonlocal clock
        stamp = turn_time or fallback
        if not text or not (start <= stamp < end):
            return
        # Stamps have minute precision; keep file order when turns share a minute.
        clock = stamp if clock is None or stamp > clock else clock + timedelta(seconds=1)
        add_event(record, clock, role, text)

    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    continue
                role, message = item.get("role"), item.get("message")
                if role not in {"user", "assistant"} or not isinstance(message, dict):
                    emit("assistant", answer)
                    answer = ""
                    continue
                text = text_from_content(message.get("content"))
                if role == "user":
                    emit("assistant", answer)
                    answer = ""
                    turn_time = cursor_timestamp(text) or turn_time
                    emit("user", cursor_user_text(text))
                elif text.strip():
                    answer = text
                if ARTIFACT_HINT_RE.search(line) and start <= (turn_time or fallback) < end:
                    record["artifact_candidates"].extend(
                        clean_artifact_paths(cursor_user_text(text) if role == "user" else message))
        emit("assistant", answer)
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
        unique[(item["role"], item["text"])] = item
    return sorted(unique.values(), key=lambda item: item["timestamp"])


def normalize_path(raw: str, cwd: str | None) -> Path | None:
    path = Path(os.path.expandvars(os.path.expanduser(raw.strip())))
    if not path.is_absolute() and cwd:
        path = Path(cwd) / path
    try:
        return path.resolve()
    except OSError:
        return path


def path_has_sequence(path: Path, sequence: tuple[str, ...]) -> bool:
    parts = tuple(part.casefold() for part in path.parts)
    target = tuple(part.casefold() for part in sequence)
    width = len(target)
    return any(parts[index : index + width] == target for index in range(len(parts) - width + 1))


def is_ignored_asset_path(path: Path) -> bool:
    return any(path_has_sequence(path, sequence) for sequence in IGNORED_ASSET_SEQUENCES)


def is_ignored_scan_root(path: Path) -> bool:
    return path.name.casefold() in IGNORED_SCAN_ROOTS or is_ignored_asset_path(path)


def clean_artifact_paths(value: Any) -> list[str]:
    return [path for text in iter_strings(value)
            for path in candidate_paths(redact(strip_injected_text(text)))
            if "[REDACTED" not in path]


def asset_candidate(path: Path, source: str, project: str, start: datetime,
                    end: datetime, force_context: bool = False) -> dict[str, Any] | None:
    if is_ignored_asset_path(path) or path.suffix.lower() not in IMAGE_EXTENSIONS:
        return None
    try:
        if not path.is_file():
            return None
        modified = datetime.fromtimestamp(path.stat().st_mtime, LOCAL_TZ)
    except OSError:
        return None
    context = force_context or bool(CONTEXT_IMAGE_RE.search(str(path)))
    current = start <= modified < end
    if source == "scanned" and not current and not context:
        return None
    return {"path": str(path), "source": source, "project": project,
            "role": "platform_context" if context else "result_candidate",
            "period": "context" if context else ("current" if current else "unknown"),
            "status": "unverified", "modified_at": modified.isoformat()}


def discover_assets(
    records: list[dict[str, Any]],
    start: datetime,
    end: datetime,
    scan_fallback: bool,
    scan_seconds: float,
    scan_files: int,
    asset_roots: Iterable[str] = (),
    context_images: Iterable[str] = (),
) -> list[dict[str, Any]]:
    assets: dict[str, dict[str, Any]] = {}
    for record in records:
        cwd = record.get("cwd")
        for raw in record.get("artifact_candidates", []):
            path = normalize_path(raw, cwd)
            item = asset_candidate(path, "referenced", record["project"], start, end) if path else None
            if item:
                assets[str(path)] = item
    for raw in context_images:
        path = normalize_path(raw, None)
        project = next((record["project"] for record in records if record.get("cwd")
                        and path.is_relative_to(Path(record["cwd"]).resolve())), path.parent.name)
        item = asset_candidate(path, "explicit_context", project, start, end, True)
        if item:
            assets[str(path)] = item
    if scan_fallback and scan_files > 0 and scan_seconds > 0:
        roots = {str(Path(record["cwd"]).resolve()): record["project"]
                 for record in records if record.get("cwd")}
        for raw in asset_roots:
            root = Path(raw).expanduser().resolve()
            roots.setdefault(str(root), root.name)
        roots = {root: project for root, project in sorted(roots.items())
                 if Path(root).is_dir() and not is_ignored_scan_root(Path(root))}
        # Each root gets its own share: a busy first project cannot consume the
        # whole budget. Referenced images never disable discovery elsewhere.
        count = len(roots)
        for index, (root, project) in enumerate(roots.items()):
            budget = scan_files // count + (index < scan_files % count)
            asset_budget = 80 // count + (index < 80 % count)
            deadline = time.monotonic() + scan_seconds / count
            scanned = found = 0
            if not budget or not asset_budget:
                continue
            for current, dirs, files in os.walk(root):
                dirs[:] = sorted(name for name in dirs if name.casefold() not in SKIP_DIRS
                                 and not (Path(current) / name).is_symlink())
                if time.monotonic() >= deadline:
                    break
                for name in sorted(files):
                    if scanned >= budget or found >= asset_budget or time.monotonic() >= deadline:
                        break
                    scanned += 1
                    path = Path(current) / name
                    if path.is_symlink() or str(path) in assets:
                        continue
                    item = asset_candidate(path, "scanned", project, start, end)
                    if item:
                        assets[str(path)] = item
                        found += 1
                if scanned >= budget or found >= asset_budget or time.monotonic() >= deadline:
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


def session_index_ids(root: Path, start: datetime, end: datetime) -> set[str]:
    index_ids: set[str] = set()
    index_path = root / "session_index.jsonl"
    if not index_path.exists():
        return index_ids
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
    return index_ids


def codex_session_files(root: Path, start: datetime, end: datetime, include_archived: bool = True) -> list[Path]:
    """Select by filename/index and metadata before parsing any rollout content."""
    session_root = root / "sessions"
    if not session_root.exists():
        return []
    index_ids = session_index_ids(root, start, end)
    result: list[Path] = []
    # Rollouts stay in their creation-date directory when an old task resumes.
    # The index is only a hint: missing/stale entries must not suppress files
    # updated during or after the requested window. The parser filters events.
    for path in sorted(session_root.rglob("rollout-*.jsonl")):
        if not path.is_file():
            continue
        if any(session_id in path.name for session_id in index_ids):
            result.append(path)
        else:
            result.extend(recent_files([path], start, end, include_date_dirs=True))
    if include_archived:
        archived = root / "archived_sessions"
        if archived.exists() and index_ids:
            try:
                result.extend(
                    archived / entry.name
                    for entry in os.scandir(archived)
                    if entry.is_file() and entry.name.endswith(".jsonl") and any(session_id in entry.name for session_id in index_ids)
                )
            except OSError:
                pass
    return result


def collect(args: argparse.Namespace) -> dict[str, Any]:
    start, end, target_date, mode = collection_window(args)
    codex_root = Path(args.codex_root).expanduser()
    claude_root = Path(args.claude_root).expanduser()
    sessions: OrderedDict[str, dict[str, Any]] = OrderedDict()
    SECRET_VALUES.clear()
    codex_files = codex_session_files(codex_root, start, end, getattr(args, "include_archived", True))
    for path in codex_files:
        parse_codex_file(path, start, end, sessions)
    projects = claude_root / "projects"
    claude_files = recent_files(projects.rglob("*.jsonl"), start, end) if projects.exists() else []
    for path in claude_files:
        parse_claude_file(path, start, end, sessions)
    # Callers that do not name a Cursor root keep the Codex/Claude-only behaviour.
    cursor_root = getattr(args, "cursor_root", None)
    if cursor_root:
        for path, parent_id in cursor_session_files(Path(cursor_root).expanduser(), start, end):
            parse_cursor_file(path, start, end, sessions, parent_id)
    scrub_secret_values(sessions.values())

    known = dict(sessions)
    records: list[dict[str, Any]] = []
    project_root = getattr(args, "project_root", None)
    project_root = Path(project_root).expanduser().resolve() if project_root else None
    for record in sessions.values():
        if project_root and (not record.get("cwd") or not Path(record["cwd"]).resolve().is_relative_to(project_root)):
            continue
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
        getattr(args, "asset_root", []),
        getattr(args, "context_image", []),
    )
    project_names = sorted({record["project"] for record in records})
    return {
        "schema_version": 1,
        "timezone": "Asia/Shanghai",
        "mode": mode,
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
    parser.add_argument("--since", help="Inclusive report cutoff (ISO date/timestamp); overrides calendar mode")
    parser.add_argument("--until", help="Exclusive end of --since interval; defaults to collection time")
    parser.add_argument("--codex-root", default=str(Path.home() / ".codex"))
    parser.add_argument("--claude-root", default=str(Path.home() / ".claude"))
    parser.add_argument("--cursor-root", default=str(Path.home() / ".cursor"),
                        help="Cursor data directory (projects/*/agent-transcripts); pass an empty value to skip Cursor")
    parser.add_argument("--scan-fallback", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--include-archived", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--scan-seconds", type=float, default=5.0)
    parser.add_argument("--scan-files", type=int, default=2000)
    parser.add_argument("--project-root", help="Include sessions in this project and its subdirectories only")
    parser.add_argument("--asset-root", action="append", default=[], help="Additional explicit directory for bounded image discovery")
    parser.add_argument("--context-image", action="append", default=[], help="Explicit platform/context image; remains an unverified candidate")
    parser.add_argument("--out", required=True, help="Output JSON path")
    args = parser.parse_args()
    try:
        result = collect(args)
    except ValueError as exc:
        parser.error(str(exc))
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    # Keep redirected PowerShell output UTF-8 independently of its codepage.
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from runtime_config import emit_json
    emit_json(result["stats"])


if __name__ == "__main__":
    main()
