#!/usr/bin/env python3
"""Read-only style-vocabulary audit routed by language and document kind."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Sequence


AUDIT_VERSION = "2.0"
DEFAULT_VOCAB_ROOT = Path(r"D:\BaiduSyncdisk\.agents\vocab")
DOCUMENT_KINDS = (
    "general",
    "proposal",
    "research-report",
    "paper",
    "review-response",
    "letter",
    "other",
)
STYLE_HEADER = ("不建议", "建议", "例外")
TERM_HEADER = ("中文", "英文")
OVERRIDE_HEADER = ("条目", "匹配")


class AuditError(ValueError):
    """Raised when an input or vocabulary rule is invalid."""


class AuditArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise AuditError(message)


@dataclass(frozen=True)
class Rule:
    source: str
    suggestion: str
    exception: str
    pattern: str
    source_file: Path
    scope: str
    compiled: re.Pattern[str]


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def source_record(path: Path) -> dict[str, object]:
    return {
        "path": str(path),
        "bytes": path.stat().st_size,
        "sha256": sha256_path(path),
    }


def is_escaped(text: str, position: int) -> bool:
    count = 0
    position -= 1
    while position >= 0 and text[position] == "\\":
        count += 1
        position -= 1
    return count % 2 == 1


def unescape_cell(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value.startswith("`") and value.endswith("`"):
        value = value[1:-1]
    return value.replace(r"\|", "|").strip()


def split_table_line(line: str) -> list[str]:
    text = line.strip()
    if text.startswith("|"):
        text = text[1:]
    if text.endswith("|") and not is_escaped(text, len(text) - 1):
        text = text[:-1]

    cells: list[str] = []
    current: list[str] = []
    in_code = False
    for position, char in enumerate(text):
        if char == "`" and not is_escaped(text, position):
            in_code = not in_code
            current.append(char)
            continue
        if char == "|" and not in_code and not is_escaped(text, position):
            cells.append(unescape_cell("".join(current)))
            current = []
            continue
        current.append(char)
    cells.append(unescape_cell("".join(current)))
    return cells


def is_separator(line: str) -> bool:
    cells = split_table_line(line)
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", cell.strip()) for cell in cells)


def parse_tables(text: str) -> list[tuple[list[str], list[tuple[int, list[str]]]]]:
    lines = text.splitlines()
    tables: list[tuple[list[str], list[tuple[int, list[str]]]]] = []
    index = 0
    while index + 1 < len(lines):
        if "|" not in lines[index] or not is_separator(lines[index + 1]):
            index += 1
            continue
        headers = split_table_line(lines[index])
        rows: list[tuple[int, list[str]]] = []
        index += 2
        while index < len(lines):
            raw = lines[index].strip()
            if not raw or "|" not in raw or raw.startswith("#"):
                break
            rows.append((index + 1, split_table_line(lines[index])))
            index += 1
        tables.append((headers, rows))
    return tables


def load_exact_table(path: Path, expected_header: Sequence[str]) -> list[tuple[int, list[str]]]:
    if not path.is_file():
        raise AuditError(f"rule file does not exist: {path}")
    text = path.read_text(encoding="utf-8-sig")
    tables = parse_tables(text)
    if len(tables) != 1:
        raise AuditError(f"expected exactly one Markdown table in {path}, found {len(tables)}")
    headers, rows = tables[0]
    if tuple(headers) != tuple(expected_header):
        raise AuditError(
            f"invalid table header in {path}: expected {list(expected_header)}, got {headers}"
        )
    for line_number, cells in rows:
        if len(cells) != len(expected_header):
            raise AuditError(
                f"invalid column count in {path}:{line_number}: "
                f"expected {len(expected_header)}, got {len(cells)}"
            )
    return rows


def load_style_file(path: Path) -> list[tuple[int, str, str, str]]:
    rows = load_exact_table(path, STYLE_HEADER)
    seen: set[str] = set()
    result: list[tuple[int, str, str, str]] = []
    for line_number, cells in rows:
        source, suggestion, exception = (cell.strip() for cell in cells)
        if not source or not suggestion:
            raise AuditError(f"empty style rule in {path}:{line_number}")
        if source in seen:
            raise AuditError(f"duplicate style rule '{source}' in {path}:{line_number}")
        seen.add(source)
        result.append((line_number, source, suggestion, exception))
    return result


def section_text(text: str, heading: str) -> str:
    lines = text.splitlines()
    start = None
    for index, line in enumerate(lines):
        if line.strip() == f"## {heading}":
            start = index + 1
            break
    if start is None:
        raise AuditError(f"missing section '## {heading}'")
    end = len(lines)
    for index in range(start, len(lines)):
        if lines[index].startswith("## "):
            end = index
            break
    return "\n".join(lines[start:end])


def compile_pattern(expression: str, source: str) -> re.Pattern[str]:
    try:
        return re.compile(expression)
    except re.error as exc:
        raise AuditError(f"invalid match pattern for '{source}': {exc}") from exc


def load_overrides(path: Path) -> dict[str, str]:
    if not path.is_file():
        raise AuditError(f"maintenance file does not exist: {path}")
    text = section_text(path.read_text(encoding="utf-8-sig"), "检查补充")
    tables = parse_tables(text)
    if len(tables) != 1:
        raise AuditError(f"expected one match table in {path}#检查补充, found {len(tables)}")
    headers, rows = tables[0]
    if tuple(headers) != OVERRIDE_HEADER:
        raise AuditError(
            f"invalid match table header in {path}: expected {list(OVERRIDE_HEADER)}, got {headers}"
        )
    overrides: dict[str, str] = {}
    for line_number, cells in rows:
        if len(cells) != 2:
            raise AuditError(f"invalid match table column count in {path}:{line_number}")
        source, expression = (cell.strip() for cell in cells)
        if not source or not expression:
            raise AuditError(f"empty match rule in {path}:{line_number}")
        if source in overrides:
            raise AuditError(f"duplicate match rule '{source}' in {path}:{line_number}")
        compile_pattern(expression, source)
        overrides[source] = expression
    return overrides


def selected_style_paths(vocab_root: Path, language: str, document_kind: str) -> list[Path]:
    if language == "zh":
        common = vocab_root / "中文" / "通用.md"
        task_names = {
            "proposal": "申报书.md",
            "research-report": "调研报告.md",
            "paper": "论文.md",
            "review-response": "审稿回复.md",
        }
        return [common] + (
            [vocab_root / "中文" / task_names[document_kind]]
            if document_kind in task_names
            else []
        )
    if language == "en":
        common = vocab_root / "英文" / "通用.md"
        task_names = {"paper": "论文.md", "review-response": "审稿回复.md"}
        return [common] + (
            [vocab_root / "英文" / task_names[document_kind]]
            if document_kind in task_names
            else []
        )
    raise AuditError(f"unsupported language: {language}")


def default_pattern(source: str, language: str) -> str:
    parts = [part.strip() for part in re.split(r"[；;]", source) if part.strip()]
    if not parts:
        raise AuditError("empty style source")
    patterns: list[str] = []
    for part in parts:
        escaped = re.escape(part).replace(re.escape("……"), ".{0,30}")
        if language == "en":
            escaped = escaped.replace(r"\ ", r"\s+")
            patterns.append(rf"(?i:\b{escaped}\b)")
        else:
            patterns.append(escaped)
    return "(?:" + "|".join(patterns) + ")"


def build_rules(
    vocab_root: Path, language: str, document_kind: str
) -> tuple[list[Rule], list[Path]]:
    style_paths = selected_style_paths(vocab_root, language, document_kind)
    maintenance_path = vocab_root / "维护.md"
    overrides = load_overrides(maintenance_path)
    merged: dict[str, Rule] = {}
    for index, style_path in enumerate(style_paths):
        scope = "general" if index == 0 else document_kind
        for _, source, suggestion, exception in load_style_file(style_path):
            pattern = overrides.get(source, default_pattern(source, language))
            merged[source] = Rule(
                source=source,
                suggestion=suggestion,
                exception=exception,
                pattern=pattern,
                source_file=style_path.resolve(),
                scope=scope,
                compiled=compile_pattern(pattern, source),
            )
    return list(merged.values()), [path.resolve() for path in style_paths] + [maintenance_path.resolve()]


def validate_vocab_root(vocab_root: Path) -> dict[str, int]:
    vocab_root = vocab_root.resolve()
    style_paths = [
        vocab_root / "中文" / "通用.md",
        vocab_root / "中文" / "申报书.md",
        vocab_root / "中文" / "调研报告.md",
        vocab_root / "中文" / "论文.md",
        vocab_root / "中文" / "审稿回复.md",
        vocab_root / "英文" / "通用.md",
        vocab_root / "英文" / "论文.md",
        vocab_root / "英文" / "审稿回复.md",
    ]
    active_sources: set[str] = set()
    style_rule_count = 0
    for path in style_paths:
        rows = load_style_file(path)
        style_rule_count += len(rows)
        active_sources.update(source for _, source, _, _ in rows)

    term_rows = load_exact_table(vocab_root / "术语.md", TERM_HEADER)
    seen_zh: set[str] = set()
    seen_en: set[str] = set()
    for line_number, cells in term_rows:
        chinese, english = (cell.strip() for cell in cells)
        if not chinese or not english:
            raise AuditError(f"empty term in {vocab_root / '术语.md'}:{line_number}")
        if chinese in seen_zh or english.casefold() in seen_en:
            raise AuditError(f"duplicate term in {vocab_root / '术语.md'}:{line_number}")
        seen_zh.add(chinese)
        seen_en.add(english.casefold())

    maintenance_path = vocab_root / "维护.md"
    if not maintenance_path.is_file():
        raise AuditError(f"maintenance file does not exist: {maintenance_path}")
    maintenance_text = maintenance_path.read_text(encoding="utf-8-sig")
    headings = re.findall(r"^##\s+(.+?)\s*$", maintenance_text, flags=re.MULTILINE)
    expected_headings = ["待确认", "不采用", "检查补充", "变更记录"]
    if headings != expected_headings:
        raise AuditError(
            f"invalid maintenance sections: expected {expected_headings}, got {headings}"
        )
    overrides = load_overrides(maintenance_path)
    unmapped = sorted(set(overrides) - active_sources)
    if unmapped:
        raise AuditError(f"match rules without active style rows: {unmapped}")

    route_count = 0
    for language in ("zh", "en"):
        for document_kind in DOCUMENT_KINDS:
            build_rules(vocab_root, language, document_kind)
            route_count += 1
    return {
        "style_files": len(style_paths),
        "style_rules": style_rule_count,
        "term_rows": len(term_rows),
        "match_overrides": len(overrides),
        "routes": route_count,
    }


def blank_like(value: str) -> str:
    return "".join(char if char in "\r\n" else " " for char in value)


def mask_line(line: str) -> str:
    if re.match(r"^\s*(?:>| {4}|\t)", line):
        return blank_like(line)
    masked = line
    patterns = [
        r"`+[^`\n]*`+",
        r"(?:https?://|www\.)[^\s<>()]+",
        r"(?<!\w)(?:[A-Za-z]:\\|\\\\)[^\s`'\"<>|]+",
        r"(?<![\w:])(?:\.{1,2}/|/)[^\s`'\"<>]+",
        r"\\[A-Za-z@]+\*?(?:\[[^\]\n]*\])?(?:\{[^{}\n]*\})*",
        r"\[@[^\]\n]+\]",
        r"(?<![\w])@[A-Za-z][\w:.-]*",
        r"“[^”\n]*”",
        r'"[^"\n]*"',
    ]
    for expression in patterns:
        masked = re.sub(expression, lambda match: blank_like(match.group(0)), masked)
    return masked


def masked_text(text: str) -> str:
    result: list[str] = []
    fence: str | None = None
    reference_heading = False
    latex_bibliography = False
    for line in text.splitlines(keepends=True):
        stripped = line.lstrip()
        fence_match = re.match(r"(`{3,}|~{3,})", stripped)
        if fence is not None:
            result.append(blank_like(line))
            if fence_match and fence_match.group(1)[0] == fence:
                fence = None
            continue
        if fence_match:
            fence = fence_match.group(1)[0]
            result.append(blank_like(line))
            continue
        if re.match(r"^\s*#{1,6}\s*(references|bibliography|参考文献)\s*$", line, re.I):
            reference_heading = True
        if re.search(r"\\begin\{(?:thebibliography|references)\}", line, re.I):
            latex_bibliography = True
        if reference_heading or latex_bibliography:
            result.append(blank_like(line))
            if re.search(r"\\end\{(?:thebibliography|references)\}", line, re.I):
                latex_bibliography = False
            continue
        result.append(mask_line(line))
    return "".join(result)


def line_column(text: str, offset: int) -> tuple[int, int]:
    line = text.count("\n", 0, offset) + 1
    last_newline = text.rfind("\n", 0, offset)
    return line, offset - last_newline


def audit(args: argparse.Namespace) -> dict[str, object]:
    vocab_root = Path(args.vocab_root).expanduser().resolve()
    rules, rule_paths = build_rules(vocab_root, args.language, args.document_kind)
    input_paths = [Path(value).expanduser().resolve() for value in args.file]
    matches: list[dict[str, object]] = []
    for input_path in input_paths:
        if not input_path.is_file():
            raise AuditError(f"input file does not exist: {input_path}")
        raw = input_path.read_text(encoding="utf-8-sig")
        visible = masked_text(raw)
        for rule in rules:
            for hit in rule.compiled.finditer(visible):
                line, column = line_column(raw, hit.start())
                matches.append(
                    {
                        "file": str(input_path),
                        "line": line,
                        "column": column,
                        "match": raw[hit.start() : hit.end()],
                        "not_recommended": rule.source,
                        "suggestion": rule.suggestion,
                        "exception": rule.exception,
                        "rule_file": str(rule.source_file),
                        "rule_scope": rule.scope,
                    }
                )
    matches.sort(key=lambda item: (str(item["file"]), int(item["line"]), int(item["column"])))
    status = "review_required" if matches else "clean"
    return {
        "audit_version": AUDIT_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "context": {"language": args.language, "document_kind": args.document_kind},
        "inputs": [source_record(path) for path in input_paths],
        "rule_files": [source_record(path) for path in rule_paths],
        "counts": {"matches": len(matches), "errors": 0},
        "matches": matches,
        "errors": [],
    }


def markdown_escape(value: object) -> str:
    return str(value).replace("|", r"\|").replace("\n", " ")


def markdown_report(result: dict[str, object]) -> str:
    lines = [
        "# 用词检查",
        "",
        f"- 状态：`{result['status']}`",
        f"- 语言：`{result.get('context', {}).get('language', '—')}`",
        f"- 文稿类型：`{result.get('context', {}).get('document_kind', '—')}`",
        f"- 命中：`{result.get('counts', {}).get('matches', 0)}`",
    ]
    errors = result.get("errors", [])
    if errors:
        lines.extend(["", "## 错误", ""])
        lines.extend(f"- {markdown_escape(item.get('message', item))}" for item in errors)
    matches = result.get("matches", [])
    if matches:
        lines.extend(
            [
                "",
                "## 待复核命中",
                "",
                "| 文件 | 行 | 列 | 命中 | 不建议 | 建议 | 例外 |",
                "|---|---:|---:|---|---|---|---|",
            ]
        )
        for item in matches:
            lines.append(
                "| "
                + " | ".join(
                    markdown_escape(item[key])
                    for key in (
                        "file",
                        "line",
                        "column",
                        "match",
                        "not_recommended",
                        "suggestion",
                        "exception",
                    )
                )
                + " |"
            )
    return "\n".join(lines) + "\n"


def error_result(message: str) -> dict[str, object]:
    return {
        "audit_version": AUDIT_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "error",
        "context": {},
        "inputs": [],
        "rule_files": [],
        "counts": {"matches": 0, "errors": 1},
        "matches": [],
        "errors": [{"message": message}],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = AuditArgumentParser(description=__doc__)
    parser.add_argument("--file", action="append", required=True, help="Markdown or LaTeX file")
    parser.add_argument("--vocab-root", default=str(DEFAULT_VOCAB_ROOT))
    parser.add_argument("--language", required=True, choices=("zh", "en"))
    parser.add_argument("--document-kind", required=True, choices=DOCUMENT_KINDS)
    parser.add_argument("--output-format", choices=("json", "markdown"), default="json")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    output_format = "json"
    try:
        args = build_parser().parse_args(argv)
        output_format = args.output_format
        result = audit(args)
    except (AuditError, OSError, UnicodeError) as exc:
        result = error_result(str(exc))
        output = markdown_report(result) if output_format == "markdown" else json.dumps(result, ensure_ascii=False, indent=2)
        print(output)
        return 2
    output = markdown_report(result) if output_format == "markdown" else json.dumps(result, ensure_ascii=False, indent=2)
    print(output)
    return 0 if result["status"] == "clean" else 1


if __name__ == "__main__":
    raise SystemExit(main())
