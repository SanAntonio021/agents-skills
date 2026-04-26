#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable


THEMES = {
    "context_resume": {
        "label": "上下文续跑与线程切换",
        "patterns": [
            "resume",
            "续跑",
            "上下文",
            "线程",
            "thread",
            "对话",
            "session",
            "重开",
            "新开",
        ],
        "failure_mode": "该续跑时重新开线程，或在项目/工作区切换时丢失上下文。",
        "suggestion": "未完成的同类任务优先沿用同一 thread 或 `resume --last`，减少重复描述背景。",
    },
    "workspace_routing": {
        "label": "工作区与项目路由",
        "patterns": [
            "工作区",
            "workspace",
            "项目",
            "路径",
            "目录",
            "cwd",
            "切换项目",
        ],
        "failure_mode": "工作区、目录或项目边界不清，导致对话、文件和命令作用域混淆。",
        "suggestion": "高频项目尽量固定 cwd，并在需要切换目录时先确认应该留在当前 thread 还是新开独立任务。",
    },
    "windows_shell": {
        "label": "Windows 命令与编码摩擦",
        "patterns": [
            "powershell",
            "乱码",
            "编码",
            "utf-8",
            "shell",
            "引号",
            "quote",
            "quoting",
            "cmd",
        ],
        "failure_mode": "路径、编码、quoting 或 PowerShell 语法再次拖慢执行。",
        "suggestion": "高风险命令优先复用已验证模式，尤其是路径、编码和 PowerShell 单行命令场景。",
    },
    "prompt_memory": {
        "label": "提示词记忆负担",
        "patterns": [
            "提示词",
            "prompt",
            "不想记",
            "忘了怎么说",
            "忘记怎么说",
            "怎么提",
            "怎么说",
        ],
        "failure_mode": "把本可由 skill 或 automation 承担的流程继续寄托在记忆提示词上。",
        "suggestion": "优先把常见需求收口成 skill 入口或固定 alias，而不是靠记忆完整 prompt。",
    },
    "automation": {
        "label": "重复任务尚未自动化",
        "patterns": [
            "automation",
            "自动化",
            "每周",
            "定时",
            "重复",
            "周报",
            "日报",
            "复盘",
        ],
        "failure_mode": "重复性检查仍在手工执行，持续占用注意力。",
        "suggestion": "对固定频率、固定输出的任务优先考虑 automation，并默认产出 Markdown 供确认。",
    },
    "skill_routing": {
        "label": "Skill 触发与路由",
        "patterns": [
            "skill",
            "技能",
            "触发",
            "加载",
            "调用",
            "wrapper",
            "alias",
        ],
        "failure_mode": "已有 skill 没有及时触发，导致重复解释或重新发明流程。",
        "suggestion": "遇到高频流程时优先先问“该用哪个 skill”，再决定是否重写 prompt。",
    },
}

FAILURE_HINTS = {
    "windows_shell": [
        "access is denied",
        "cannot find path",
        "unicodeencodeerror",
        "resourceunavailable",
        "parameterbindingexception",
        "illegal multibyte sequence",
        "timed out",
    ]
}


@dataclass
class SessionSummary:
    session_id: str
    started_at: datetime
    path: Path
    cwd: str
    thread_name: str
    user_messages: list[str] = field(default_factory=list)
    tool_failures: list[str] = field(default_factory=list)
    theme_hits: Counter = field(default_factory=Counter)
    theme_examples: dict[str, list[str]] = field(default_factory=lambda: defaultdict(list))
    tool_calls: int = 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a weekly Codex workflow review from local session transcripts."
    )
    parser.add_argument("--codex-home", type=Path, default=Path.home() / ".codex")
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--end-date", type=str, default=None, help="YYYY-MM-DD")
    parser.add_argument("--output", type=Path, default=None)
    return parser.parse_args()


def parse_dt(value: str) -> datetime:
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value).astimezone()


def shorten(text: str, limit: int = 90) -> str:
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


def load_index(path: Path) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
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


def iter_session_files(codex_home: Path) -> Iterable[Path]:
    sessions = codex_home / "sessions"
    archived = codex_home / "archived_sessions"
    if sessions.exists():
        yield from sessions.rglob("*.jsonl")
    if archived.exists():
        yield from archived.glob("*.jsonl")


def record_theme(summary: SessionSummary, theme_key: str, example: str) -> None:
    summary.theme_hits[theme_key] += 1
    examples = summary.theme_examples[theme_key]
    if len(examples) < 3:
        item = shorten(example)
        if item not in examples:
            examples.append(item)


def detect_themes(summary: SessionSummary, text: str) -> None:
    lowered = text.lower()
    for theme_key, spec in THEMES.items():
        if any(pattern in lowered for pattern in spec["patterns"]):
            record_theme(summary, theme_key, text)


def detect_failure_themes(summary: SessionSummary, text: str) -> None:
    lowered = text.lower()
    for theme_key, hints in FAILURE_HINTS.items():
        if any(hint in lowered for hint in hints):
            record_theme(summary, theme_key, text)


def parse_session(path: Path, index: dict[str, dict[str, str]], since: datetime) -> SessionSummary | None:
    with path.open("r", encoding="utf-8") as handle:
        first_line = handle.readline()
        if not first_line:
            return None
        first = json.loads(first_line)
        if first.get("type") != "session_meta":
            return None
        meta = first["payload"]
        started_at = parse_dt(meta["timestamp"])
        if started_at < since:
            return None
        session_id = meta["id"]
        thread_name = index.get(session_id, {}).get("thread_name", "")
        summary = SessionSummary(
            session_id=session_id,
            started_at=started_at,
            path=path,
            cwd=meta.get("cwd", ""),
            thread_name=thread_name,
        )
        if thread_name:
            detect_themes(summary, thread_name)
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
                    summary.user_messages.append(message)
                    detect_themes(summary, message)
            elif outer_type == "response_item":
                item_type = payload.get("type")
                if item_type == "function_call":
                    summary.tool_calls += 1
                elif item_type == "function_call_output":
                    output = as_text(payload.get("output", ""))
                    if not output:
                        continue
                    match = re.search(r"Exit code:\s*(-?\d+)", output)
                    if match and int(match.group(1)) != 0:
                        summary.tool_failures.append(shorten(output.replace("\r", " ")))
                        detect_failure_themes(summary, output)
        return summary


def pick_top_themes(summaries: list[SessionSummary]) -> list[tuple[str, int, list[str], int]]:
    total_hits: Counter[str] = Counter()
    examples: dict[str, list[str]] = defaultdict(list)
    sessions_with_theme: Counter[str] = Counter()
    for summary in summaries:
        for theme_key, count in summary.theme_hits.items():
            total_hits[theme_key] += count
            sessions_with_theme[theme_key] += 1
            for example in summary.theme_examples.get(theme_key, []):
                if len(examples[theme_key]) < 3 and example not in examples[theme_key]:
                    examples[theme_key].append(example)
    ranked = []
    for theme_key, hits in total_hits.most_common():
        ranked.append((theme_key, hits, examples[theme_key], sessions_with_theme[theme_key]))
    return ranked


def top_cwds(summaries: list[SessionSummary]) -> list[tuple[str, int]]:
    counts = Counter(summary.cwd for summary in summaries if summary.cwd)
    return counts.most_common(3)


def output_path(args: argparse.Namespace, end_date: datetime) -> Path:
    if args.output is not None:
        return args.output
    repo_root = Path("<agents-root>/reports/codex-workflow-coach")
    return repo_root / f"{end_date.date().isoformat()}.md"


def build_report(
    summaries: list[SessionSummary],
    top_themes: list[tuple[str, int, list[str], int]],
    start_date: datetime,
    end_date: datetime,
    codex_home: Path,
) -> str:
    total_failures = sum(len(summary.tool_failures) for summary in summaries)
    lines: list[str] = []
    lines.append(f"# Codex 工作流周检 - {end_date.date().isoformat()}")
    lines.append("")
    lines.append("## 这次看了哪些内容")
    lines.append(f"- 统计时间范围：{start_date.date().isoformat()} 到 {end_date.date().isoformat()}")
    lines.append(f"- 扫描到的对话记录数：{len(summaries)}")
    lines.append(f"- 对话来源：`{codex_home / 'sessions'}` 和 `{codex_home / 'archived_sessions'}`")
    lines.append(f"- 索引文件：`{codex_home / 'session_index.jsonl'}` 和 `{codex_home / 'history.jsonl'}`")
    lines.append("- 主要参考：thread 标题、用户消息、工具调用、非零退出的工具结果")
    lines.append("- 说明：未完成的对话也会计入；重复出现只代表“很可能是问题”，不代表绝对结论")
    lines.append("")
    lines.append("## 这周反复卡住的地方")
    if not top_themes:
        lines.append("- 这周还没有明显重复到值得单独提醒的问题。")
    else:
        for theme_key, hits, examples, session_count in top_themes[:3]:
            spec = THEMES[theme_key]
            lines.append(
                f"- {spec['label']}：在 {session_count} 条对话里反复出现，共命中 {hits} 次。"
            )
            if examples:
                lines.append(f"  例子：{' | '.join(examples)}")
    lines.append("")
    lines.append("## 下周最容易再出问题的地方")
    if not top_themes:
        lines.append("- 目前还没有足够证据说明哪一类问题会稳定重复发生。")
    else:
        for theme_key, _, _, _ in top_themes[:3]:
            lines.append(f"- {THEMES[theme_key]['failure_mode']}")
    if total_failures:
        lines.append(f"- 这周记录到的工具失败次数：{total_failures}。")
    lines.append("")
    lines.append("## 建议怎么调整工作流")
    if not top_themes:
        lines.append("- 先继续积累被动对话证据；目前还不需要做很重的工作流调整。")
    else:
        for theme_key, _, _, _ in top_themes[:3]:
            lines.append(f"- {THEMES[theme_key]['suggestion']}")
    lines.append("")
    lines.append("## 哪些重复任务值得以后定时处理")
    cwd_rank = top_cwds(summaries)
    if cwd_rank:
        top_cwd, top_count = cwd_rank[0]
        lines.append(
            f"- 这周最活跃的工作区是 `{top_cwd}`（{top_count} 条对话）。如果要先做一个定时检查，优先从这里开始。"
        )
    if any(theme_key == "automation" for theme_key, _, _, _ in top_themes):
        lines.append("- 对话里已经多次提到重复任务，所以继续保留每周一次的 Codex 工作流周检是合理的。")
    else:
        lines.append("- 就算暂时没有很强的自动化信号，每周产出一份简短 Markdown 周报，仍然是低打扰的做法。")
    lines.append("")
    lines.append("## 需要你确认的地方")
    lines.append("- 这份周报主要来自本地 `.codex` 对话记录和工具事件，不依赖你手写摘要。")
    lines.append("- 如果某条提醒你觉得只是噪音，可以直接把它当成误报忽略掉。")
    lines.append("- 如果某个模式你确认是真的，下一步只处理那一个点就够了，不必一次改很多。")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    codex_home = args.codex_home
    if args.end_date:
        end_date = datetime.fromisoformat(args.end_date).astimezone()
    else:
        end_date = datetime.now().astimezone()
    start_date = end_date - timedelta(days=args.days)
    index = load_index(codex_home / "session_index.jsonl")
    summaries: list[SessionSummary] = []
    for path in iter_session_files(codex_home):
        summary = parse_session(path, index, start_date)
        if summary is not None:
            summaries.append(summary)
    summaries.sort(key=lambda item: item.started_at)
    top_themes = pick_top_themes(summaries)
    report = build_report(summaries, top_themes, start_date, end_date, codex_home)
    destination = output_path(args, end_date)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(report, encoding="utf-8")
    print(destination)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
