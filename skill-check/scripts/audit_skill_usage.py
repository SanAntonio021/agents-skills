#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import heapq
import json
import os
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable


MAX_WARNING_DETAILS = 200
MAX_EXCERPT_CHARS = 240
BRIDGE_MARKERS = (
    "claude-codex-bridge",
    "cross-model-orchestration-workspace",
    "bridge-workspace",
    "bridge_workspace",
    "review-copy",
    "review_copy",
)
SKIP_DIR_NAMES = {".git", "node_modules", "__pycache__", "rescued-skill-materials"}
SKIP_DIR_SUFFIXES = ("-workspace",)
ENGLISH_STOPWORDS = {
    "about",
    "after",
    "agent",
    "agents",
    "also",
    "and",
    "before",
    "check",
    "create",
    "from",
    "into",
    "local",
    "only",
    "skill",
    "skills",
    "that",
    "the",
    "their",
    "this",
    "through",
    "user",
    "when",
    "where",
    "with",
}
CHINESE_STOP_TERMS = {
    "以及",
    "使用",
    "用户",
    "需要",
    "进行",
    "处理",
    "相关",
    "本地",
    "技能",
    "任务",
    "适用于",
    "当用户",
}

FRONTMATTER_PATTERN = re.compile(r"\A---\s*\r?\n(.*?)\r?\n---(?:\r?\n|\Z)", re.DOTALL)
EXPLICIT_DOLLAR_PATTERN = re.compile(r"(?<![\w$])\$([A-Za-z0-9][A-Za-z0-9_:-]*)")
EXPLICIT_SLASH_PATTERN = re.compile(
    r"(?:(?<=^)|(?<=[\s（(]))/([A-Za-z0-9][A-Za-z0-9_:-]*)(?=$|[\s，。；;、）)])",
    re.MULTILINE,
)
SKILL_LINK_PATTERN = re.compile(
    r"(?:^|[/\\])skills[/\\]+([^/\\)\]>'\"\s]+)[/\\]+SKILL\.md\b",
    re.IGNORECASE,
)
URL_PATTERN = re.compile(r"https?://[^\s<>'\"]+", re.IGNORECASE)
EMAIL_PATTERN = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
WINDOWS_PATH_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])(?:[A-Za-z]:[\\/]|\\\\)[^\\/:*?\"<>|\r\n,;，。；、）)\]]+"
    r"(?:[\\/][^\\/:*?\"<>|\r\n,;，。；、）)\]]+)*"
)
POSIX_PATH_PATTERN = re.compile(
    r"(?<![A-Za-z0-9:])/(?:Users|home|tmp|var|etc|mnt|workspace|root)(?:/[^\s<>|\"']+)+",
    re.IGNORECASE,
)
SECRET_PATTERN = re.compile(
    r"(?i)\b(?:sk|api|token|key|secret)[-_]?[A-Za-z0-9]{12,}\b|\bBearer\s+[A-Za-z0-9._~-]+"
)
LONG_ID_PATTERN = re.compile(r"\b[0-9a-f]{24,}\b", re.IGNORECASE)


@dataclass(frozen=True)
class RootSpec:
    root_id: str
    path: Path
    kind: str
    active_hosts: tuple[str, ...] = ()


@dataclass
class SkillInfo:
    key: str
    name: str
    descriptions: set[str] = field(default_factory=set)
    aliases: set[str] = field(default_factory=set)
    locations: list[dict[str, Any]] = field(default_factory=list)
    trigger_terms: list[str] = field(default_factory=list)


@dataclass
class MessageRecord:
    host: str
    session_id: str
    timestamp: str
    text: str
    source: dict[str, Any]
    message_id: str = ""
    used_skills: set[str] = field(default_factory=set)


class WarningCollector:
    def __init__(self) -> None:
        self.parse_errors: list[dict[str, Any]] = []
        self.missing_fields: list[dict[str, Any]] = []
        self.parse_error_count = 0
        self.missing_field_count = 0

    def parse_error(self, source: dict[str, Any], detail: str) -> None:
        self.parse_error_count += 1
        if len(self.parse_errors) < MAX_WARNING_DETAILS:
            self.parse_errors.append({**source, "detail": detail})

    def missing_field(self, source: dict[str, Any], detail: str) -> None:
        self.missing_field_count += 1
        if len(self.missing_fields) < MAX_WARNING_DETAILS:
            self.missing_fields.append({**source, "detail": detail})


class CandidateCollector:
    def __init__(self, limit: int) -> None:
        self.limit = limit
        self.per_skill_limit = min(5, limit)
        self.total = 0
        self._sequence = 0
        self._by_skill: dict[str, list[tuple[tuple[int, int], int, dict[str, Any]]]] = defaultdict(list)

    def add(self, item: dict[str, Any]) -> None:
        self.total += 1
        self._sequence += 1
        stable_text = json.dumps(
            [item["skill"], item["host"], item["timestamp"], item["source"]],
            ensure_ascii=False,
            sort_keys=True,
        )
        tie_break = int.from_bytes(hashlib.sha256(stable_text.encode("utf-8")).digest()[:8], "big")
        quality = (int(item["score"]), tie_break)
        entry = (quality, self._sequence, item)
        skill_heap = self._by_skill[item["skill"]]
        if len(skill_heap) < self.per_skill_limit:
            heapq.heappush(skill_heap, entry)
        elif quality > skill_heap[0][0]:
            heapq.heapreplace(skill_heap, entry)

    def items(self) -> list[dict[str, Any]]:
        groups = {
            skill: sorted(
                (entry[2] for entry in skill_heap),
                key=lambda item: (
                    -item["score"],
                    item["timestamp"],
                    item["source"]["path"],
                    item["source"]["line"],
                ),
            )
            for skill, skill_heap in self._by_skill.items()
        }
        skill_order = sorted(
            groups,
            key=lambda skill: (-groups[skill][0]["score"], skill.lower()),
        )
        result: list[dict[str, Any]] = []
        for rank in range(self.per_skill_limit):
            for skill in skill_order:
                if rank < len(groups[skill]):
                    result.append(groups[skill][rank])
                    if len(result) == self.limit:
                        return result
        return result

    @property
    def unique_skills(self) -> int:
        return len(self._by_skill)


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def excerpt_size(value: str) -> int:
    parsed = positive_int(value)
    if parsed > MAX_EXCERPT_CHARS:
        raise argparse.ArgumentTypeError(f"must not exceed {MAX_EXCERPT_CHARS}")
    return parsed


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Read local Codex and Claude history and audit skill usage evidence."
    )
    parser.add_argument("--reports-root", required=True, help="Directory for generated reports.")
    parser.add_argument("--date", required=True, help="Report date in YYYY-MM-DD format.")
    parser.add_argument(
        "--skills-root",
        action="append",
        default=[],
        help="Skill root to inventory. Repeat to use multiple custom roots; overrides defaults.",
    )
    parser.add_argument(
        "--codex-sessions-root",
        action="append",
        default=[],
        help="Codex session root. Repeat for multiple roots; overrides defaults.",
    )
    parser.add_argument(
        "--claude-projects-root",
        action="append",
        default=[],
        help="Claude project history root. Repeat for multiple roots; overrides defaults.",
    )
    parser.add_argument(
        "--claude-telemetry-root",
        action="append",
        default=[],
        help="Claude telemetry root. Repeat for multiple roots; overrides defaults.",
    )
    parser.add_argument(
        "--hygiene-summary",
        help="Optional skill-check summary.json used only to find possible redundancy intersections.",
    )
    parser.add_argument(
        "--max-candidates",
        type=positive_int,
        default=50,
        help="Maximum suspected missed-use candidates in the report (default: 50).",
    )
    parser.add_argument(
        "--excerpt-chars",
        type=excerpt_size,
        default=MAX_EXCERPT_CHARS,
        help=f"Maximum redacted excerpt length (default/max: {MAX_EXCERPT_CHARS}).",
    )
    parser.add_argument("--no-excerpt", action="store_true", help="Do not store message excerpts.")
    parser.add_argument("--json", action="store_true", help="Print summary JSON to stdout.")
    return parser.parse_args(argv)


def normalize_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def short_session_ref(session_id: str) -> str:
    return hashlib.sha256(session_id.encode("utf-8", errors="replace")).hexdigest()[:12]


def source_ref(root: RootSpec, path: Path, line: int) -> dict[str, Any]:
    try:
        relative = path.relative_to(root.path).as_posix()
    except ValueError:
        relative = path.name
    return {"root_id": root.root_id, "path": relative, "line": line}


def redact_text(text: str) -> str:
    cleaned = text.replace("\x00", " ")
    cleaned = URL_PATTERN.sub("<URL>", cleaned)
    cleaned = EMAIL_PATTERN.sub("<EMAIL>", cleaned)
    cleaned = WINDOWS_PATH_PATTERN.sub("<PATH>", cleaned)
    cleaned = POSIX_PATH_PATTERN.sub("<PATH>", cleaned)
    cleaned = SECRET_PATTERN.sub("<SECRET>", cleaned)
    cleaned = LONG_ID_PATTERN.sub("<ID>", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def sanitize_excerpt(text: str, limit: int) -> str:
    return redact_text(text)[:limit]


def sanitize_excerpt_around(text: str, terms: list[str], limit: int) -> str:
    lowered = text.lower()
    positions = [lowered.find(term.lower()) for term in terms]
    positions = [position for position in positions if position >= 0]
    if not positions:
        return sanitize_excerpt(text, limit)
    start = max(0, min(positions) - limit // 3)
    raw = text[start : start + limit * 2]
    cleaned = sanitize_excerpt(raw, limit - (4 if start else 0))
    return f"... {cleaned}" if start else cleaned


def read_frontmatter(path: Path) -> tuple[str, str]:
    text = path.read_text(encoding="utf-8", errors="replace")
    match = FRONTMATTER_PATTERN.match(text)
    if not match:
        return path.parent.name, ""
    name = ""
    description_lines: list[str] = []
    collecting_description = False
    for line in match.group(1).splitlines():
        if re.match(r"^name\s*:", line):
            name = line.split(":", 1)[1].strip().strip("'\"")
            collecting_description = False
            continue
        if re.match(r"^description\s*:", line):
            value = line.split(":", 1)[1].strip()
            collecting_description = value in {"", "|", ">", "|-", ">-"}
            if not collecting_description:
                description_lines.append(value.strip("'\""))
            continue
        if collecting_description and (line.startswith(" ") or line.startswith("\t")):
            description_lines.append(line.strip())
        elif line and not line.startswith((" ", "\t")):
            collecting_description = False
    return name or path.parent.name, " ".join(description_lines).strip()


def should_skip_dir(name: str) -> bool:
    lowered = name.lower()
    return lowered in SKIP_DIR_NAMES or lowered.endswith(SKIP_DIR_SUFFIXES)


def skill_path_allowed(root: RootSpec, relative: Path) -> bool:
    parts = relative.parts
    if not parts or parts[-1].lower() != "skill.md":
        return False
    if root.kind == "source":
        return len(parts) == 2
    if root.kind in {"codex_runtime", "claude_runtime", "lark_entity"}:
        return len(parts) == 2 or (len(parts) == 3 and parts[0] in {".system", "codex-primary-runtime"})
    return True


def iter_skill_files(root: RootSpec) -> Iterable[Path]:
    if not root.path.is_dir():
        return
    stack = [root.path]
    seen_real_dirs: set[str] = set()
    while stack:
        directory = stack.pop()
        try:
            real_key = os.path.normcase(os.path.realpath(directory))
            if real_key in seen_real_dirs:
                continue
            seen_real_dirs.add(real_key)
            entries = sorted(os.scandir(directory), key=lambda item: item.name.lower())
        except OSError:
            continue
        for entry in entries:
            path = Path(entry.path)
            try:
                relative = path.relative_to(root.path)
            except ValueError:
                continue
            if entry.is_file(follow_symlinks=True) and entry.name.lower() == "skill.md":
                if skill_path_allowed(root, relative):
                    yield path
            elif entry.is_dir(follow_symlinks=True) and not should_skip_dir(entry.name):
                stack.append(path)


def default_skill_roots(script_path: Path) -> list[RootSpec]:
    user = Path.home()
    authoritative_source = Path(r"D:\BaiduSyncdisk\.agents\skills")
    source_root = authoritative_source if authoritative_source.is_dir() else script_path.absolute().parents[2]
    return [
        RootSpec("source", source_root, "source"),
        RootSpec("codex-runtime", user / ".codex" / "skills", "codex_runtime", ("codex",)),
        RootSpec("claude-runtime", user / ".claude" / "skills", "claude_runtime", ("claude",)),
        RootSpec("lark-entity", user / ".agents" / "skills", "lark_entity", ("codex",)),
        RootSpec("plugin-cache", user / ".codex" / "plugins" / "cache", "plugin_cache", ("codex",)),
    ]


def custom_roots(values: list[str], prefix: str, kind: str) -> list[RootSpec]:
    return [RootSpec(f"{prefix}-{index}", Path(value).expanduser(), kind) for index, value in enumerate(values, 1)]


def build_inventory(roots: list[RootSpec]) -> tuple[dict[str, SkillInfo], list[str]]:
    inventory: dict[str, SkillInfo] = {}
    missing_roots: list[str] = []
    for root in roots:
        if not root.path.is_dir():
            missing_roots.append(root.root_id)
            continue
        for skill_md in iter_skill_files(root):
            name, description = read_frontmatter(skill_md)
            key = normalize_name(name or skill_md.parent.name)
            if not key:
                continue
            skill = inventory.setdefault(key, SkillInfo(key=key, name=name or skill_md.parent.name))
            skill.aliases.update({name.lower(), skill_md.parent.name.lower(), key})
            if ":" in name:
                skill.aliases.add(name.rsplit(":", 1)[1].lower())
            if description:
                skill.descriptions.add(description)
            skill.locations.append(
                {
                    "root_id": root.root_id,
                    "kind": root.kind,
                    "path": skill_md.relative_to(root.path).as_posix(),
                    "line": 1,
                    "active_hosts": list(root.active_hosts),
                }
            )
    for skill in inventory.values():
        skill.locations.sort(key=lambda item: (item["root_id"], item["path"]))
    return inventory, missing_roots


def chinese_ngrams(text: str) -> set[str]:
    terms: set[str] = set()
    for chunk in re.findall(r"[\u4e00-\u9fff]{4,40}", text):
        for size in (6, 5, 4):
            for index in range(0, len(chunk) - size + 1):
                term = chunk[index : index + size]
                if not any(stop in term for stop in CHINESE_STOP_TERMS):
                    terms.add(term)
    return terms


def build_trigger_terms(inventory: dict[str, SkillInfo]) -> None:
    chinese_by_skill: dict[str, set[str]] = {}
    document_frequency: Counter[str] = Counter()
    for key, skill in inventory.items():
        terms = set()
        for description in skill.descriptions:
            terms.update(chinese_ngrams(description))
        chinese_by_skill[key] = terms
        document_frequency.update(terms)

    for key, skill in inventory.items():
        selected_chinese = sorted(
            (term for term in chinese_by_skill[key] if document_frequency[term] <= 2),
            key=lambda term: (-len(term), document_frequency[term], term),
        )[:24]
        english: set[str] = set()
        for description in skill.descriptions:
            for token in re.findall(r"[A-Za-z][A-Za-z0-9_-]{3,}", description.lower()):
                normalized = token.replace("_", "-")
                if normalized not in ENGLISH_STOPWORDS:
                    english.add(normalized)
        selected_english = sorted(english, key=lambda term: (-len(term), term))[:16]
        skill.trigger_terms = selected_chinese + selected_english


def build_alias_map(inventory: dict[str, SkillInfo]) -> dict[str, set[str]]:
    aliases: dict[str, set[str]] = defaultdict(set)
    for key, skill in inventory.items():
        for alias in skill.aliases:
            normalized = normalize_name(alias)
            if normalized:
                aliases[normalized].add(key)
    return aliases


class TriggerMatcher:
    def __init__(self, inventory: dict[str, SkillInfo]) -> None:
        self.alias_to_skills: dict[str, set[str]] = defaultdict(set)
        self.chinese_to_skills: dict[str, set[str]] = defaultdict(set)
        self.english_to_skills: dict[str, set[str]] = defaultdict(set)
        for key, skill in inventory.items():
            for alias in skill.aliases:
                lowered = alias.lower()
                if len(lowered) >= 4:
                    self.alias_to_skills[lowered].add(key)
            for term in skill.trigger_terms:
                if re.fullmatch(r"[\u4e00-\u9fff]+", term):
                    self.chinese_to_skills[term].add(key)
                else:
                    self.english_to_skills[term.lower()].add(key)
        self.alias_pattern = self._compile_terms(self.alias_to_skills, word_boundaries=True)
        self.chinese_pattern = self._compile_terms(self.chinese_to_skills, word_boundaries=False)
        self.english_pattern = self._compile_terms(self.english_to_skills, word_boundaries=True)

    @staticmethod
    def _compile_terms(mapping: dict[str, set[str]], *, word_boundaries: bool) -> re.Pattern[str] | None:
        if not mapping:
            return None
        alternatives = "|".join(re.escape(term) for term in sorted(mapping, key=lambda item: (-len(item), item)))
        if word_boundaries:
            return re.compile(rf"(?<![a-z0-9])(?:{alternatives})(?![a-z0-9])", re.IGNORECASE)
        return re.compile(rf"(?:{alternatives})")

    @staticmethod
    def _matched_terms(pattern: re.Pattern[str] | None, text: str) -> set[str]:
        if pattern is None:
            return set()
        return {match.group(0).lower() for match in pattern.finditer(text)}

    def matches(self, text: str) -> dict[str, tuple[int, list[str]]]:
        lowered = text.lower()
        alias_terms = self._matched_terms(self.alias_pattern, lowered)
        chinese_terms = self._matched_terms(self.chinese_pattern, text)
        english_terms = self._matched_terms(self.english_pattern, lowered)
        aliases_by_skill: dict[str, set[str]] = defaultdict(set)
        chinese_by_skill: dict[str, set[str]] = defaultdict(set)
        english_by_skill: dict[str, set[str]] = defaultdict(set)
        for term in alias_terms:
            for key in self.alias_to_skills.get(term, set()):
                aliases_by_skill[key].add(term)
        for term in chinese_terms:
            for key in self.chinese_to_skills.get(term, set()):
                chinese_by_skill[key].add(term)
        for term in english_terms:
            for key in self.english_to_skills.get(term, set()):
                english_by_skill[key].add(term)

        result: dict[str, tuple[int, list[str]]] = {}
        keys = set(aliases_by_skill) | set(chinese_by_skill) | set(english_by_skill)
        for key in keys:
            if aliases_by_skill[key]:
                chosen_alias = sorted(aliases_by_skill[key], key=lambda item: (-len(item), item))[0]
                result[key] = (100, [chosen_alias])
                continue
            chosen_chinese: list[str] = []
            for term in sorted(chinese_by_skill[key], key=lambda item: (-len(item), item)):
                if not any(term in existing or existing in term for existing in chosen_chinese):
                    chosen_chinese.append(term)
                if len(chosen_chinese) == 3:
                    break
            if len(chosen_chinese) >= 2 or (chosen_chinese and len(chosen_chinese[0]) >= 6):
                result[key] = (sum(len(term) for term in chosen_chinese) * 3, chosen_chinese)
                continue
            chosen_english = sorted(english_by_skill[key], key=lambda item: (-len(item), item))
            if len(chosen_english) >= 2:
                selected = chosen_english[:3]
                result[key] = (sum(len(term) for term in selected), selected)
        return result


def extract_explicit_skills(text: str, aliases: dict[str, set[str]]) -> set[str]:
    raw_names = set(EXPLICIT_DOLLAR_PATTERN.findall(text))
    raw_names.update(EXPLICIT_SLASH_PATTERN.findall(text))
    raw_names.update(SKILL_LINK_PATTERN.findall(text))
    matched: set[str] = set()
    for raw_name in raw_names:
        matched.update(aliases.get(normalize_name(raw_name), set()))
    return matched


def iter_json_lines(
    path: Path, root: RootSpec, warnings: WarningCollector
) -> Iterable[tuple[int, dict[str, Any]]]:
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for line_number, line in enumerate(handle, 1):
                if not line.strip():
                    continue
                source = source_ref(root, path, line_number)
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError as exc:
                    warnings.parse_error(source, f"JSON decode failed at column {exc.colno}")
                    continue
                if isinstance(payload, dict):
                    yield line_number, payload
                elif isinstance(payload, list):
                    for item in payload:
                        if isinstance(item, dict):
                            yield line_number, item
    except OSError as exc:
        warnings.parse_error(source_ref(root, path, 0), f"file read failed: {exc.__class__.__name__}")


def list_history_files(root: RootSpec, suffixes: tuple[str, ...]) -> list[Path]:
    if not root.path.is_dir():
        return []
    files: list[Path] = []
    for path in root.path.rglob("*"):
        if path.is_file() and path.suffix.lower() in suffixes:
            files.append(path)
    return sorted(files, key=lambda item: item.as_posix().lower())


def read_codex_session_metadata(path: Path) -> tuple[str, bool]:
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(row, dict) or row.get("type") != "session_meta":
                    continue
                payload = row.get("payload")
                if not isinstance(payload, dict):
                    break
                session_id = str(payload.get("session_id") or payload.get("id") or path.stem)
                is_bridge = context_is_bridge(payload.get("cwd")) or context_is_bridge(
                    payload.get("workspace")
                )
                return session_id, is_bridge
    except OSError:
        pass
    return path.stem, False


def codex_message_text(payload: dict[str, Any]) -> str | None:
    value = payload.get("message")
    if isinstance(value, str):
        return value
    content = payload.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [
            item.get("text", "")
            for item in content
            if isinstance(item, dict) and item.get("type") in {"input_text", "text"} and isinstance(item.get("text"), str)
        ]
        return "\n".join(part for part in parts if part)
    return None


def context_is_bridge(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    lowered = value.replace("\\", "/").lower()
    return any(marker in lowered for marker in BRIDGE_MARKERS)


def add_excerpt(target: dict[str, Any], text: str, args: argparse.Namespace) -> None:
    if not args.no_excerpt:
        target["excerpt"] = sanitize_excerpt(text, args.excerpt_chars)


def build_usage_event(
    *, host: str, kind: str, skill: SkillInfo, message: MessageRecord, detail_text: str, args: argparse.Namespace
) -> dict[str, Any]:
    event = {
        "host": host,
        "kind": kind,
        "skill": skill.name,
        "timestamp": message.timestamp,
        "session_ref": short_session_ref(message.session_id),
        "source": message.source,
    }
    add_excerpt(event, detail_text, args)
    return event


def add_candidates(
    message: MessageRecord,
    inventory: dict[str, SkillInfo],
    matcher: TriggerMatcher,
    explicit: set[str],
    candidates: CandidateCollector,
    args: argparse.Namespace,
) -> None:
    lowered = message.text.lower()
    if (
        not message.text.strip()
        or len(message.text) > 20_000
        or "<skills_instructions>" in lowered
        or "<recommended_plugins>" in lowered
    ):
        return
    excluded = explicit | message.used_skills
    matching_text = redact_text(message.text)
    for key, match in matcher.matches(matching_text).items():
        if key in excluded:
            continue
        skill = inventory[key]
        score, terms = match
        candidate = {
            "skill": skill.name,
            "host": message.host,
            "timestamp": message.timestamp,
            "session_ref": short_session_ref(message.session_id),
            "source": message.source,
            "matched_terms": terms,
            "score": score,
            "reason": "技能名或 description 规则命中，但该条用户记录未见对应显式调用证据。",
        }
        if not args.no_excerpt:
            candidate["excerpt"] = sanitize_excerpt_around(matching_text, terms, args.excerpt_chars)
        candidates.add(candidate)


def scan_codex_history(
    roots: list[RootSpec],
    inventory: dict[str, SkillInfo],
    aliases: dict[str, set[str]],
    matcher: TriggerMatcher,
    usage: dict[str, list[dict[str, Any]]],
    candidates: CandidateCollector,
    warnings: WarningCollector,
    args: argparse.Namespace,
) -> tuple[int, set[tuple[str, str, str]]]:
    excluded_sessions: set[tuple[str, str, str]] = set()
    seen_messages: set[tuple[str, str]] = set()
    scanned_files = 0
    for root in roots:
        for path in list_history_files(root, (".jsonl",)):
            scanned_files += 1
            session_id, session_bridge = read_codex_session_metadata(path)
            if session_bridge:
                excluded_sessions.add((root.root_id, path.relative_to(root.path).as_posix(), session_id))
                continue

            preferred: dict[tuple[str, str], MessageRecord] = {}
            priorities: dict[tuple[str, str], int] = {}
            for line_number, row in iter_json_lines(path, root, warnings):
                row_type = row.get("type")
                payload = row.get("payload")
                if not isinstance(payload, dict):
                    continue
                timestamp = str(row.get("timestamp") or payload.get("timestamp") or "")
                source = source_ref(root, path, line_number)
                priority = 0
                text_value: str | None = None
                if row_type == "event_msg" and payload.get("type") == "user_message":
                    priority = 2
                    text_value = codex_message_text(payload)
                elif (
                    row_type == "response_item"
                    and payload.get("type") == "message"
                    and payload.get("role") == "user"
                ):
                    priority = 1
                    text_value = codex_message_text(payload)
                else:
                    continue
                if text_value is None or not text_value.strip():
                    warnings.missing_field(source, "Codex user record is missing message text")
                    continue
                if not timestamp:
                    warnings.missing_field(source, "Codex user record is missing timestamp")
                    timestamp = f"line-{line_number}"
                key = (session_id, timestamp)
                if priority <= priorities.get(key, -1):
                    continue
                preferred[key] = MessageRecord(
                    host="codex",
                    session_id=session_id,
                    timestamp=timestamp,
                    text=text_value,
                    source=source,
                )
                priorities[key] = priority

            for key in sorted(preferred, key=lambda item: item[1]):
                if key in seen_messages:
                    continue
                seen_messages.add(key)
                message = preferred[key]
                explicit = extract_explicit_skills(message.text, aliases)
                for skill_key in sorted(explicit):
                    usage[skill_key].append(
                        build_usage_event(
                            host="codex",
                            kind="explicit_user_invocation",
                            skill=inventory[skill_key],
                            message=message,
                            detail_text=message.text,
                            args=args,
                        )
                    )
                add_candidates(message, inventory, matcher, explicit, candidates, args)
    return scanned_files, excluded_sessions


def claude_text_content(message: Any) -> str:
    if not isinstance(message, dict):
        return ""
    content = message.get("content")
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts = [
        item.get("text", "")
        for item in content
        if isinstance(item, dict) and item.get("type") == "text" and isinstance(item.get("text"), str)
    ]
    return "\n".join(part for part in parts if part)


def ancestor_user_id(parent_id: str, nodes: dict[str, tuple[str, str]]) -> str:
    current = parent_id
    visited: set[str] = set()
    while current and current not in visited:
        visited.add(current)
        node = nodes.get(current)
        if node is None:
            return ""
        node_type, parent = node
        if node_type == "user":
            return current
        current = parent
    return ""


def scan_claude_history(
    roots: list[RootSpec],
    inventory: dict[str, SkillInfo],
    aliases: dict[str, set[str]],
    matcher: TriggerMatcher,
    usage: dict[str, list[dict[str, Any]]],
    candidates: CandidateCollector,
    warnings: WarningCollector,
    args: argparse.Namespace,
) -> tuple[int, set[tuple[str, str, str]]]:
    excluded_sessions: set[tuple[str, str, str]] = set()
    seen_user_ids: set[tuple[str, str]] = set()
    seen_tool_ids: set[tuple[str, str]] = set()
    scanned_files = 0
    for root in roots:
        for path in list_history_files(root, (".jsonl",)):
            scanned_files += 1
            nodes: dict[str, tuple[str, str]] = {}
            users: dict[str, MessageRecord] = {}
            tools_found: list[tuple[str, str, str, str, dict[str, Any], str, str]] = []
            bridge_session_ids: set[str] = set()
            file_session_ids: set[str] = set()
            for line_number, row in iter_json_lines(path, root, warnings):
                row_type = str(row.get("type") or "")
                row_id = str(row.get("uuid") or "")
                parent_id = str(row.get("parentUuid") or "")
                session_id = str(row.get("sessionId") or row.get("session_id") or path.stem)
                timestamp = str(row.get("timestamp") or f"line-{line_number}")
                source = source_ref(root, path, line_number)
                file_session_ids.add(session_id)
                if context_is_bridge(row.get("cwd")) or context_is_bridge(row.get("projectPath")):
                    bridge_session_ids.add(session_id)
                if row_id:
                    nodes[row_id] = (row_type, parent_id)

                if row_type == "user":
                    text_value = claude_text_content(row.get("message"))
                    if text_value.strip():
                        user_key = row_id or f"line-{line_number}"
                        users[user_key] = MessageRecord(
                            host="claude",
                            session_id=session_id,
                            timestamp=timestamp,
                            text=text_value,
                            source=source,
                            message_id=user_key,
                        )
                    continue

                if row_type != "assistant" or not isinstance(row.get("message"), dict):
                    continue
                content = row["message"].get("content")
                if not isinstance(content, list):
                    continue
                for index, item in enumerate(content):
                    if not isinstance(item, dict) or item.get("type") != "tool_use" or item.get("name") != "Skill":
                        continue
                    tool_id = str(item.get("id") or f"{row_id}:{index}:{line_number}")
                    input_value = item.get("input")
                    raw_skill = input_value.get("skill") if isinstance(input_value, dict) else None
                    if not isinstance(raw_skill, str) or not raw_skill.strip():
                        warnings.missing_field(source, "Claude Skill tool_use is missing input.skill")
                        continue
                    args_text = input_value.get("args", "") if isinstance(input_value, dict) else ""
                    tools_found.append(
                        (
                            tool_id,
                            parent_id,
                            session_id,
                            timestamp,
                            source,
                            str(args_text or raw_skill),
                            raw_skill,
                        )
                    )

            for session_id in bridge_session_ids:
                excluded_sessions.add((root.root_id, path.relative_to(root.path).as_posix(), session_id))
            if file_session_ids and file_session_ids.issubset(bridge_session_ids):
                continue

            for tool_id, parent_id, session_id, timestamp, source, args_text, raw_skill in tools_found:
                if session_id in bridge_session_ids or (session_id, tool_id) in seen_tool_ids:
                    continue
                seen_tool_ids.add((session_id, tool_id))
                matched_keys = aliases.get(normalize_name(raw_skill), set())
                if not matched_keys:
                    continue
                user_id = ancestor_user_id(parent_id, nodes)
                if user_id in users:
                    users[user_id].used_skills.update(matched_keys)
                for skill_key in sorted(matched_keys):
                    message = MessageRecord(
                        host="claude",
                        session_id=session_id,
                        timestamp=timestamp,
                        text=args_text,
                        source=source,
                    )
                    usage[skill_key].append(
                        build_usage_event(
                            host="claude",
                            kind="skill_tool_use",
                            skill=inventory[skill_key],
                            message=message,
                            detail_text=args_text,
                            args=args,
                        )
                    )

            for user_id, message in sorted(users.items(), key=lambda item: item[1].timestamp):
                if message.session_id in bridge_session_ids or (message.session_id, user_id) in seen_user_ids:
                    continue
                seen_user_ids.add((message.session_id, user_id))
                explicit = extract_explicit_skills(message.text, aliases)
                add_candidates(message, inventory, matcher, explicit, candidates, args)
    return scanned_files, excluded_sessions


def scan_claude_telemetry(
    roots: list[RootSpec], aliases: dict[str, set[str]], warnings: WarningCollector
) -> tuple[int, Counter[str], int]:
    scanned_files = 0
    loaded: Counter[str] = Counter()
    unmatched = 0
    for root in roots:
        for path in list_history_files(root, (".json", ".jsonl")):
            scanned_files += 1
            for line_number, row in iter_json_lines(path, root, warnings):
                event_data = row.get("event_data")
                if isinstance(event_data, str):
                    try:
                        event_data = json.loads(event_data)
                    except json.JSONDecodeError:
                        event_data = None
                if not isinstance(event_data, dict) or event_data.get("event_name") != "tengu_skill_loaded":
                    continue
                source = source_ref(root, path, line_number)
                raw_skill = event_data.get("skill_name")
                if not isinstance(raw_skill, str) or not raw_skill.strip():
                    warnings.missing_field(source, "tengu_skill_loaded is missing event_data.skill_name")
                    continue
                matched = aliases.get(normalize_name(raw_skill), set())
                if not matched:
                    unmatched += 1
                for skill_key in matched:
                    loaded[skill_key] += 1
    return scanned_files, loaded, unmatched


def paths_from_hygiene_item(item: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for key in ("path", "left", "right"):
        value = item.get(key)
        if isinstance(value, str) and value:
            values.append(value)
    return values


def possible_redundancy(
    hygiene_path: Path | None,
    inventory: dict[str, SkillInfo],
    usage: dict[str, list[dict[str, Any]]],
) -> tuple[list[dict[str, Any]], str | None]:
    if hygiene_path is None:
        return [], None
    try:
        payload = json.loads(hygiene_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [], f"hygiene summary could not be read: {exc.__class__.__name__}"
    findings = payload.get("findings", {})
    if not isinstance(findings, dict):
        return [], "hygiene summary has no findings object"
    candidates: dict[str, dict[str, Any]] = {}
    for category in ("duplicate_candidates", "overlap_candidates"):
        items = findings.get(category, [])
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            related = [normalize_name(Path(path).name) for path in paths_from_hygiene_item(item)]
            related = [key for key in related if key in inventory]
            for key in related:
                if usage.get(key):
                    continue
                entry = candidates.setdefault(
                    key,
                    {
                        "skill": inventory[key].name,
                        "reason": "历史内未见使用，并与已有重复/职责重叠发现相交；仅作为人工复核候选。",
                        "hygiene_categories": [],
                        "related_skills": [],
                    },
                )
                if category not in entry["hygiene_categories"]:
                    entry["hygiene_categories"].append(category)
                for other in related:
                    if other != key and inventory[other].name not in entry["related_skills"]:
                        entry["related_skills"].append(inventory[other].name)
    result = sorted(candidates.values(), key=lambda item: item["skill"].lower())
    return result, None


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        f"# 技能历史使用审计（{summary['date']}）",
        "",
        "## 扫描范围",
        f"- 技能：{summary['counts']['skills']} 个",
        f"- Codex 历史文件：{summary['counts']['codex_history_files']} 个",
        f"- Claude 历史文件：{summary['counts']['claude_history_files']} 个",
        f"- Claude telemetry 文件：{summary['counts']['claude_telemetry_files']} 个",
        "- 报告只保存配置根下的相对路径和行号；片段经过脱敏。",
        "",
        "## 已用",
    ]
    used = summary["classifications"]["已用"]
    lines.extend(
        [
            f"- `{item['skill']}`：Codex 显式点名 {item['codex_explicit']} 次，Claude Skill 调用 {item['claude_skill_calls']} 次"
            for item in used
        ]
        or ["- 无"]
    )
    lines.extend(["", "## 历史内未见使用"])
    unseen = summary["classifications"]["历史内未见使用"]
    lines.extend([f"- `{item['skill']}`" for item in unseen] or ["- 无"])
    lines.extend(["", "## 疑似漏用"])
    missed = summary["classifications"]["疑似漏用"]
    if missed:
        for item in missed:
            detail = f"；片段：{item['excerpt']}" if "excerpt" in item else ""
            lines.append(
                f"- `{item['skill']}`（{item['host']}，{item['source']['root_id']}:{item['source']['path']}:{item['source']['line']}，命中 {', '.join(item['matched_terms'])}）{detail}"
            )
    else:
        lines.append("- 无")
    lines.extend(["", "## 可能冗余"])
    redundant = summary["classifications"]["可能冗余"]
    lines.extend(
        [
            f"- `{item['skill']}`：{item['reason']}"
            + (f" 相关技能：{', '.join(item['related_skills'])}" if item["related_skills"] else "")
            for item in redundant
        ]
        or ["- 无"]
    )
    warnings = summary["warnings"]
    lines.extend(
        [
            "",
            "## 解释边界",
            "- Codex 当前没有稳定的隐式 Skill 调用事件；未见记录不等于实际未使用。",
            "- `tengu_skill_loaded` 只表示 Claude 启动时把技能列为候选，不计为实际使用。",
            f"- 疑似漏用候选共 {warnings['candidate_total']} 条，报告保留 {warnings['candidate_returned']} 条，截断 {warnings['candidate_truncated']} 条。",
            f"- 已排除 bridge 临时副本会话 {warnings['bridge_copy_excluded_count']} 个。",
            f"- JSON 解析错误 {warnings['parse_error_count']} 条；目标事件缺字段 {warnings['missing_field_count']} 条。",
            "",
        ]
    )
    return "\n".join(lines)


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def audit(args: argparse.Namespace) -> dict[str, Any]:
    script_path = Path(__file__)
    if args.skills_root:
        skill_roots = custom_roots(args.skills_root, "skills", "custom")
    else:
        skill_roots = default_skill_roots(script_path)

    user = Path.home()
    codex_roots = (
        custom_roots(args.codex_sessions_root, "codex-history", "codex_history")
        if args.codex_sessions_root
        else [
            RootSpec("codex-sessions", user / ".codex" / "sessions", "codex_history"),
            RootSpec("codex-archived", user / ".codex" / "archived_sessions", "codex_history"),
        ]
    )
    claude_roots = (
        custom_roots(args.claude_projects_root, "claude-history", "claude_history")
        if args.claude_projects_root
        else [RootSpec("claude-projects", user / ".claude" / "projects", "claude_history")]
    )
    telemetry_roots = (
        custom_roots(args.claude_telemetry_root, "claude-telemetry", "claude_telemetry")
        if args.claude_telemetry_root
        else [RootSpec("claude-telemetry", user / ".claude" / "telemetry", "claude_telemetry")]
    )

    inventory, missing_skill_roots = build_inventory(skill_roots)
    build_trigger_terms(inventory)
    aliases = build_alias_map(inventory)
    matcher = TriggerMatcher(inventory)
    usage: dict[str, list[dict[str, Any]]] = defaultdict(list)
    candidates = CandidateCollector(args.max_candidates)
    warnings = WarningCollector()

    codex_files, codex_excluded = scan_codex_history(
        codex_roots, inventory, aliases, matcher, usage, candidates, warnings, args
    )
    claude_files, claude_excluded = scan_claude_history(
        claude_roots, inventory, aliases, matcher, usage, candidates, warnings, args
    )
    telemetry_files, loaded_counts, unmatched_loaded = scan_claude_telemetry(
        telemetry_roots, aliases, warnings
    )

    candidate_total = candidates.total
    returned_candidates = candidates.items()

    used: list[dict[str, Any]] = []
    unseen: list[dict[str, Any]] = []
    evidence: dict[str, list[dict[str, Any]]] = {}
    inventory_output: list[dict[str, Any]] = []
    for key, skill in sorted(inventory.items(), key=lambda item: item[1].name.lower()):
        events = sorted(
            usage.get(key, []), key=lambda item: (item["timestamp"], item["host"], item["source"]["path"])
        )
        if events:
            used.append(
                {
                    "skill": skill.name,
                    "codex_explicit": sum(event["host"] == "codex" for event in events),
                    "claude_skill_calls": sum(event["host"] == "claude" for event in events),
                    "evidence_count": len(events),
                }
            )
            evidence[skill.name] = events
        else:
            unseen.append({"skill": skill.name, "startup_candidate_loads": loaded_counts.get(key, 0)})
        inventory_output.append(
            {
                "skill": skill.name,
                "locations": skill.locations,
                "active_hosts": sorted(
                    {host for location in skill.locations for host in location.get("active_hosts", [])}
                ),
            }
        )

    redundant, hygiene_warning = possible_redundancy(
        Path(args.hygiene_summary) if args.hygiene_summary else None, inventory, usage
    )
    missing_history_roots = [
        root.root_id for root in [*codex_roots, *claude_roots, *telemetry_roots] if not root.path.is_dir()
    ]
    warning_payload = {
        "codex_implicit_usage_not_captured": True,
        "claude_startup_candidates_not_counted_as_usage": True,
        "candidate_limit": args.max_candidates,
        "candidate_per_skill_limit": candidates.per_skill_limit,
        "candidate_total": candidate_total,
        "candidate_unique_skills": candidates.unique_skills,
        "candidate_returned": len(returned_candidates),
        "candidate_truncated": max(0, candidate_total - len(returned_candidates)),
        "bridge_copy_excluded_count": len(codex_excluded | claude_excluded),
        "parse_error_count": warnings.parse_error_count,
        "parse_errors": warnings.parse_errors,
        "missing_field_count": warnings.missing_field_count,
        "missing_fields": warnings.missing_fields,
        "warning_details_truncated": (
            warnings.parse_error_count > len(warnings.parse_errors)
            or warnings.missing_field_count > len(warnings.missing_fields)
        ),
        "missing_roots": missing_skill_roots + missing_history_roots,
        "unmatched_claude_startup_candidates": unmatched_loaded,
        "hygiene_summary_warning": hygiene_warning,
    }
    summary = {
        "version": "skill-usage-audit-v1",
        "date": args.date,
        "configuration": {
            "skill_roots": [
                {"root_id": root.root_id, "kind": root.kind, "active_hosts": list(root.active_hosts)}
                for root in skill_roots
            ],
            "codex_history_roots": [root.root_id for root in codex_roots],
            "claude_history_roots": [root.root_id for root in claude_roots],
            "claude_telemetry_roots": [root.root_id for root in telemetry_roots],
            "excerpt_enabled": not args.no_excerpt,
            "excerpt_chars": 0 if args.no_excerpt else args.excerpt_chars,
        },
        "counts": {
            "skills": len(inventory),
            "used_skills": len(used),
            "unseen_skills": len(unseen),
            "suspected_missed_use": len(returned_candidates),
            "possible_redundancy": len(redundant),
            "codex_history_files": codex_files,
            "claude_history_files": claude_files,
            "claude_telemetry_files": telemetry_files,
            "claude_startup_candidate_loads": sum(loaded_counts.values()),
        },
        "classifications": {
            "已用": used,
            "历史内未见使用": unseen,
            "疑似漏用": returned_candidates,
            "可能冗余": redundant,
        },
        "usage_evidence": evidence,
        "skill_inventory": inventory_output,
        "claude_startup_candidate_loads": {
            inventory[key].name: count for key, count in sorted(loaded_counts.items())
        },
        "warnings": warning_payload,
    }

    reports_root = Path(args.reports_root).resolve()
    summary_path = reports_root / "usage" / "manifests" / args.date / "summary.json"
    weekly_path = reports_root / "usage" / "weekly" / f"{args.date}.md"
    write_text(summary_path, json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    write_text(weekly_path, render_markdown(summary))
    return summary


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    summary = audit(args)
    if args.json:
        json.dump(summary, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    else:
        reports_root = Path(args.reports_root).resolve()
        print(f"summary: {reports_root / 'usage' / 'manifests' / args.date / 'summary.json'}")
        print(f"weekly: {reports_root / 'usage' / 'weekly' / f'{args.date}.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
