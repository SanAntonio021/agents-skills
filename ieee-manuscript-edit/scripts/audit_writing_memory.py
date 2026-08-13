#!/usr/bin/env python3
"""Deterministic read-only audit for the shared academic writing memory.

The script deliberately treats user style rules as hard denies. A confirmed
technical term can suppress a style finding only when the term row explicitly
allows that exception and its scope matches the audit context. Ambiguous
cases remain visible instead of being silently rewritten.
"""

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


AUDIT_VERSION = "1.2"


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip().lower())


def split_values(value: str) -> list[str]:
    if not value:
        return []
    return [normalize(item) for item in re.split(r"[;,/|]", value) if normalize(item)]


def truthy(value: str) -> bool:
    return normalize(value) in {"yes", "y", "true", "是", "1", "confirmed", "已确认"}


def canonical_status(value: str, default: str = "confirmed") -> str:
    token = normalize(value)
    if token in {"候选", "待审", "待判定", "candidate", "pending"}:
        return "candidate"
    if token in {"已拒绝", "拒绝", "rejected", "declined"}:
        return "rejected"
    if token in {"冲突待审", "conflict", "conflict_pending"}:
        return "conflict"
    if token in {"待迁移", "migration", "needs_migration"}:
        return "migration"
    if token in {"弃用", "deprecated"}:
        return "deprecated"
    if token in {"已确认", "confirmed", "active", "approved"}:
        return "confirmed"
    return default


def unescape_cell(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value.startswith("`") and value.endswith("`"):
        value = value[1:-1]
    return value.replace(r"\|", "|").replace("\\\\", "\\").strip()


def is_regex_escaped(text: str, position: int) -> bool:
    backslashes = 0
    position -= 1
    while position >= 0 and text[position] == "\\":
        backslashes += 1
        position -= 1
    return backslashes % 2 == 1


def pipe_is_regex_alternation(text: str) -> bool:
    """Recognize the unescaped `|` inside a regex group in legacy tables."""
    if is_regex_escaped(text, len(text)):
        return True
    if not text.lstrip().startswith("(?"):
        return False
    depth = 0
    escaped = False
    for char in text:
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
        elif char == "(":
            depth += 1
        elif char == ")" and depth:
            depth -= 1
    return depth > 0


def split_table_line(line: str) -> list[str]:
    """Split a Markdown table row while preserving escaped regex alternation."""
    text = line.strip().strip("|")
    cells: list[str] = []
    current: list[str] = []
    in_code = False
    for position, char in enumerate(text):
        if char == "`" and not is_regex_escaped(text, position):
            in_code = not in_code
            current.append(char)
            continue
        if char == "|" and not in_code and not pipe_is_regex_alternation("".join(current)):
            cells.append(unescape_cell("".join(current)))
            current = []
            continue
        current.append(char)
    cells.append(unescape_cell("".join(current)))
    return cells


def table_rows(text: str) -> Iterable[tuple[list[str], list[str]]]:
    """Yield Markdown table headers and cells without losing duplicate names."""
    lines = text.splitlines()
    index = 0
    while index + 1 < len(lines):
        header = lines[index].strip()
        separator = lines[index + 1].strip()
        if "|" not in header or not re.search(r"\|?\s*:?-{3,}", separator):
            index += 1
            continue
        headers = split_table_line(header)
        index += 2
        while index < len(lines):
            raw = lines[index].strip()
            if not raw or "|" not in raw:
                break
            cells = split_table_line(raw)
            if len(cells) < len(headers):
                cells.extend([""] * (len(headers) - len(cells)))
            yield headers, cells
            index += 1


def field(headers: Sequence[str], cells: Sequence[str], *names: str) -> str:
    for name in names:
        sought = normalize(name)
        for index, key in enumerate(headers):
            if normalize(key) == sought:
                return cells[index].strip() if index < len(cells) else ""
    return ""


@dataclass
class Rule:
    kind: str
    status: str
    source_form: str
    preferred: str
    variants: str
    scope: str
    domain: str
    journal: str
    section: str
    pattern: str
    has_explicit_pattern: bool
    exception_note: str
    exception_patterns: str
    override_user_deny: bool
    source: str
    user_reviewed: bool
    candidate_type: str
    migrated_to: str
    rejection_reason: str
    row: int


def rule_from_row(headers: Sequence[str], cells: Sequence[str], kind: str, row_number: int) -> Rule | None:
    source_form = field(headers, cells, "词条", "中文术语", "原始触发", "原始表达", "source_form", "source form")
    preferred = field(headers, cells, "改用", "推荐英文", "推荐表达模式", "preferred_form", "preferred form")
    variants = field(headers, cells, "可接受变体", "可接受变体/同义词", "已知同义变体", "同义变体", "variants")
    explicit_pattern = field(headers, cells, "匹配模式", "例外模式", "match_pattern", "match pattern")
    if not source_form and not preferred and not explicit_pattern:
        return None
    pattern = explicit_pattern or re.escape(source_form or preferred)
    return Rule(
        kind=kind,
        status=canonical_status(
            field(headers, cells, "状态", "status"),
            default="candidate" if kind == "candidate" else "confirmed",
        ),
        source_form=source_form or preferred,
        preferred=preferred,
        variants=variants,
        scope=field(headers, cells, "场景", "scope", "适用场景"),
        domain=field(headers, cells, "适用领域", "domain"),
        journal=field(headers, cells, "目标期刊", "期刊", "journal"),
        section=field(headers, cells, "章节功能", "section", "章节"),
        pattern=pattern,
        has_explicit_pattern=bool(explicit_pattern),
        exception_note=field(headers, cells, "例外语境", "例外说明", "exception_note"),
        exception_patterns=field(headers, cells, "例外模式", "例外匹配", "exception_patterns"),
        override_user_deny=truthy(field(headers, cells, "例外覆盖用户禁用", "override_user_deny")),
        source=field(headers, cells, "来源", "source"),
        user_reviewed=truthy(field(headers, cells, "用户审阅", "用户确认", "user_reviewed")),
        candidate_type=field(headers, cells, "类型", "candidate_type", "candidate type", "type"),
        migrated_to=field(headers, cells, "迁入位置", "migrated_to", "migrated to"),
        rejection_reason=field(headers, cells, "拒绝理由", "rejection_reason", "rejection reason"),
        row=row_number,
    )


def load_rules(path: Path, kind: str) -> list[Rule]:
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    rules: list[Rule] = []
    for row_number, (headers, cells) in enumerate(table_rows(text), start=1):
        rule = rule_from_row(headers, cells, kind, row_number)
        if rule:
            rules.append(rule)
    return rules


def context_matches(rule: Rule, domain: str, journal: str, section: str, document_kind: str) -> bool:
    def matches(rule_values: str, actual: str, aliases: set[str] | None = None) -> bool:
        values = split_values(rule_values)
        if not values or "通用" in values or "any" in values or "all" in values or "*" in values:
            return True
        actual_norm = normalize(actual)
        if not actual_norm:
            return False
        aliases = aliases or set()
        return any(value == actual_norm or value in actual_norm or actual_norm in value or value in aliases for value in values)

    scope = split_values(rule.scope)
    if scope and "通用" not in scope and "all" not in scope:
        kind = normalize(document_kind)
        if kind == "paper" and not ({"论文", "paper", "manuscript", "通用"} & set(scope)):
            return False
        if kind == "proposal" and not ({"申报书", "proposal", "通用"} & set(scope)):
            return False
    section_aliases = {normalize(section), normalize(section.rstrip("s"))}
    return (
        matches(rule.domain, domain)
        and matches(rule.journal, journal)
        and matches(rule.section, section, section_aliases)
    )


def compile_pattern(pattern: str) -> re.Pattern[str] | None:
    if not pattern:
        return None
    flags = re.IGNORECASE if pattern.startswith("(?i)") else 0
    expression = pattern[4:] if pattern.startswith("(?i)") else pattern
    try:
        return re.compile(expression, flags)
    except re.error:
        return None


def mask_line(line: str) -> str:
    masked = line
    patterns = [
        r"`[^`]*`",
        r"https?://\S+",
        r"\\(?:cite|citep|citet|ref|label|url|href)\*?(?:\[[^]]*\])?\{[^}]*\}",
        r"\\[A-Za-z@]+(?:\*)?(?:\[[^]]*\])?\{[^{}]*\}",
    ]
    for expression in patterns:
        masked = re.sub(expression, lambda match: " " * (match.end() - match.start()), masked)
    return masked


def masked_text(text: str) -> str:
    result: list[str] = []
    fenced = False
    bibliography = False
    for line in text.splitlines(keepends=True):
        stripped = line.lstrip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            fenced = not fenced
            result.append(" " * len(line))
            continue
        if re.search(r"\\begin\{(?:thebibliography|references)\}", line, re.I):
            bibliography = True
        if re.match(r"^\s*#{1,6}\s*(references|bibliography|参考文献)\s*$", line, re.I):
            bibliography = True
        if fenced or bibliography:
            result.append(" " * len(line))
            if re.search(r"\\end\{(?:thebibliography|references)\}", line, re.I):
                bibliography = False
            continue
        result.append(mask_line(line))
    return "".join(result)


def match_rule(rule: Rule, text: str) -> list[re.Match[str]]:
    compiled = compile_pattern(rule.pattern)
    return list(compiled.finditer(text)) if compiled else []


def line_column(text: str, offset: int) -> tuple[int, int]:
    line = text.count("\n", 0, offset) + 1
    last_newline = text.rfind("\n", 0, offset)
    return line, offset - last_newline


def overlaps(left: re.Match[str], right: re.Match[str]) -> bool:
    return left.start() < right.end() and right.start() < left.end()


def structured_exception_for(
    style_rule: Rule,
    style_hit: re.Match[str],
    exception_rules: list[Rule],
    visible: str,
    args: argparse.Namespace,
) -> Rule | None:
    for exception_rule in exception_rules:
        if exception_rule.status != "confirmed" or not exception_rule.user_reviewed:
            continue
        if normalize(exception_rule.source_form) != normalize(style_rule.source_form):
            continue
        if not context_matches(exception_rule, args.domain, args.journal, args.section, args.document_kind):
            continue
        for exception_hit in match_rule(exception_rule, visible):
            if overlaps(style_hit, exception_hit):
                return exception_rule
    return None


def source_record(path: Path) -> dict[str, object]:
    return {"path": str(path), "sha256": sha256_path(path), "bytes": path.stat().st_size}


def content_word_count(pattern: str) -> int:
    cleaned = re.sub(r"\(\?[a-z-]+\)", " ", pattern or "")
    return len(re.findall(r"[A-Za-z]+(?:[-'][A-Za-z]+)?", cleaned))


def same_rule(candidate: Rule, active_rule: Rule) -> bool:
    """Return whether an active rule is the recorded migration destination."""
    return (
        normalize(candidate.source_form) == normalize(active_rule.source_form)
        and normalize(candidate.preferred) == normalize(active_rule.preferred)
    )


def candidate_destination_kind(candidate_type: str) -> str | None:
    token = normalize(candidate_type)
    if token in {"通用文风词", "文风词", "词级偏好", "style", "style_rule", "style rule"}:
        return "style"
    if token in {"专业术语", "术语", "term", "terminology"}:
        return "term"
    if token in {"表达模式", "学术表达", "expression", "expression_pattern", "expression pattern"}:
        return "expression"
    return None


def candidate_destination_matches(candidate: Rule, active_rule: Rule) -> bool:
    expected_filename = {
        "style": "vocab-full.md",
        "term": "scientific-terminology-bank.md",
        "expression": "academic-expression-bank.md",
    }.get(active_rule.kind)
    if not expected_filename:
        return False
    return normalize(Path(candidate.migrated_to).name) == expected_filename


def candidate_migrated(candidate: Rule, active_rules: list[Rule]) -> bool:
    expected_kind = candidate_destination_kind(candidate.candidate_type)
    return bool(expected_kind and candidate.migrated_to) and any(
        rule.kind == expected_kind
        and candidate_destination_matches(candidate, rule)
        and same_rule(candidate, rule)
        for rule in active_rules
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", action="append", required=True, help="Markdown or LaTeX source to audit")
    parser.add_argument("--domain", required=True)
    parser.add_argument("--journal", required=True)
    parser.add_argument("--section", required=True)
    parser.add_argument("--document-kind", default="paper", choices=["paper", "proposal", "letter", "other"])
    parser.add_argument("--vocab-table", required=True)
    parser.add_argument("--term-bank", required=True)
    parser.add_argument("--expression-bank", default="")
    parser.add_argument("--exception-table", default="")
    parser.add_argument("--candidate-ledger", default="")
    parser.add_argument("--output-format", choices=["json", "markdown"], default="json")
    return parser


def audit(args: argparse.Namespace) -> dict[str, object]:
    source_paths = [Path(item).resolve() for item in args.file]
    vocab_path = Path(args.vocab_table).resolve()
    term_path = Path(args.term_bank).resolve()
    expression_path = Path(args.expression_bank).resolve() if args.expression_bank else None
    exception_path = Path(args.exception_table).resolve() if args.exception_table else None
    candidate_path = Path(args.candidate_ledger).resolve() if args.candidate_ledger else None

    # A missing table must not behave like an empty table, because a path typo
    # would otherwise turn a failed quality gate into a false pass.
    for label, path in (
        ("vocab_table", vocab_path),
        ("term_bank", term_path),
        ("expression_bank", expression_path),
        ("exception_table", exception_path),
        ("candidate_ledger", candidate_path),
    ):
        if path is None:
            continue
        if not path.is_file():
            raise ValueError(f"configured {label} does not exist or is not a file: {path}")

    style_rules = load_rules(vocab_path, "style")
    term_rules = load_rules(term_path, "term")
    expression_rules = load_rules(expression_path, "expression") if expression_path else []
    exception_rules = load_rules(exception_path, "exception") if exception_path else []
    candidate_rules = load_rules(candidate_path, "candidate") if candidate_path else []

    violations: list[dict[str, object]] = []
    exceptions: list[dict[str, object]] = []
    conflicts: list[dict[str, object]] = []
    unresolved: list[dict[str, object]] = []
    expression_matches: list[dict[str, object]] = []
    schema_errors: list[dict[str, object]] = []

    all_active_rules = style_rules + term_rules + expression_rules
    for bank_path, bank_rules, require_explicit_pattern, validate_pattern in (
        (vocab_path, style_rules, False, False),
        (term_path, term_rules, False, True),
        (expression_path, expression_rules, False, True),
        (exception_path, exception_rules, True, True),
        (candidate_path, candidate_rules, True, True),
    ):
        if bank_path is None:
            continue
        for rule in bank_rules:
            if require_explicit_pattern and not rule.has_explicit_pattern:
                schema_errors.append({"type": "missing_match_pattern", "rule": rule.source_form, "row": rule.row, "bank": str(bank_path)})
            if validate_pattern and not compile_pattern(rule.pattern):
                schema_errors.append({"type": "invalid_match_pattern", "rule": rule.source_form, "row": rule.row, "bank": str(bank_path)})

    rule_files = [vocab_path, term_path]
    for optional_path in (expression_path, exception_path, candidate_path):
        if optional_path and optional_path.exists():
            rule_files.append(optional_path)

    for source_path in source_paths:
        if not source_path.exists():
            unresolved.append({"type": "missing_input", "path": str(source_path)})
            continue
        raw = source_path.read_text(encoding="utf-8")
        visible = masked_text(raw)
        term_hits: list[tuple[Rule, re.Match[str]]] = []
        for rule in term_rules:
            if rule.status in {"rejected", "deprecated"}:
                continue
            hits = match_rule(rule, visible)
            if rule.status == "candidate":
                for hit in hits:
                    line, column = line_column(raw, hit.start())
                    unresolved.append({
                        "type": "candidate_not_active",
                        "file": str(source_path),
                        "line": line,
                        "column": column,
                        "match": hit.group(0),
                        "rule": rule.source_form,
                    })
                continue
            if rule.status != "confirmed":
                continue
            if not context_matches(rule, args.domain, args.journal, args.section, args.document_kind):
                if hits:
                    for hit in hits:
                        line, column = line_column(raw, hit.start())
                        unresolved.append({
                            "type": "scope_mismatch",
                            "file": str(source_path),
                            "line": line,
                            "column": column,
                            "match": hit.group(0),
                            "rule": rule.source_form,
                            "domain": rule.domain,
                            "journal": rule.journal,
                            "section": rule.section,
                        })
                continue
            for hit in hits:
                term_hits.append((rule, hit))

        # The candidate ledger is deliberately never an active rule source.
        # It exists to prevent unconfirmed or rejected wording from silently
        # re-entering a later draft.
        for rule in candidate_rules:
            if not context_matches(rule, args.domain, args.journal, args.section, args.document_kind):
                continue
            if rule.status == "confirmed":
                continue
            for hit in match_rule(rule, visible):
                line, column = line_column(raw, hit.start())
                candidate_base = {
                    "file": str(source_path),
                    "line": line,
                    "column": column,
                    "match": hit.group(0),
                    "rule": rule.source_form,
                    "preferred": rule.preferred,
                    "candidate_status": rule.status,
                    "rule_row": rule.row,
                }
                if rule.status == "rejected":
                    violations.append({**candidate_base, "reason": "previously rejected candidate reappeared"})
                elif rule.status == "conflict":
                    unresolved.append({**candidate_base, "type": "candidate_conflict_pending", "reason": "candidate conflict requires user decision"})
                else:
                    unresolved.append({**candidate_base, "type": "candidate_not_active", "reason": "candidate ledger never changes generated text"})

        for rule in style_rules:
            if rule.status in {"rejected", "deprecated"} or not context_matches(rule, args.domain, args.journal, args.section, args.document_kind):
                continue
            style_pattern = compile_pattern(rule.pattern)
            if not style_pattern:
                unresolved.append({
                    "type": "legacy_style_pattern_unparseable",
                    "rule": rule.source_form,
                    "rule_row": rule.row,
                    "reason": "repair the active vocab-full match pattern before relying on automated enforcement",
                })
                continue
            for hit in style_pattern.finditer(visible):
                line, column = line_column(raw, hit.start())
                overlapping = [(term, term_hit) for term, term_hit in term_hits if overlaps(hit, term_hit)]
                base = {
                    "file": str(source_path),
                    "line": line,
                    "column": column,
                    "match": hit.group(0),
                    "rule": rule.source_form,
                    "preferred": rule.preferred,
                    "priority": "user-hard-deny",
                    "rule_row": rule.row,
                }
                exception_rule = structured_exception_for(rule, hit, exception_rules, visible, args)
                if overlapping:
                    term, term_hit = overlapping[0]
                    conflict = {
                        **base,
                        "term": term.source_form,
                        "term_match": term_hit.group(0),
                        "term_preferred": term.preferred,
                        "term_row": term.row,
                        "term_scope": {"domain": term.domain, "journal": term.journal, "section": term.section},
                    }
                    conflicts.append(conflict)
                    if exception_rule and exception_rule.override_user_deny:
                        exceptions.append({**base, "reason": "confirmed structured exception resolves term/style conflict", "exception": exception_rule.pattern, "exception_rule": exception_rule.source_form, "term": term.source_form})
                    elif term.override_user_deny and term.user_reviewed:
                        exceptions.append({**base, "reason": "confirmed scoped term explicitly overrides user hard deny", "term": term.source_form})
                    else:
                        violations.append({**base, "reason": "user hard deny wins; overlapping term requires explicit exception confirmation"})
                        unresolved.append({**base, "type": "term_style_conflict", "reason": "requires user decision"})
                else:
                    if exception_rule and exception_rule.override_user_deny:
                        exceptions.append({**base, "reason": "confirmed structured exception", "exception": exception_rule.pattern, "exception_rule": exception_rule.source_form})
                    elif exception_rule:
                        violations.append({**base, "reason": "structured exception exists but does not explicitly override user hard deny"})
                        unresolved.append({**base, "type": "exception_priority_conflict", "reason": "requires explicit user override"})
                    elif rule.exception_note and not rule.exception_patterns:
                        violations.append({**base, "reason": "legacy natural-language exception cannot be proven automatically"})
                        unresolved.append({**base, "type": "manual_exception_review", "reason": rule.exception_note})
                    else:
                        violations.append(base)

        for rule in expression_rules:
            if rule.status != "confirmed":
                continue
            if content_word_count(rule.pattern) > 4:
                schema_errors.append({"type": "expression_too_long", "rule": rule.source_form, "row": rule.row, "word_count": content_word_count(rule.pattern)})
            if not context_matches(rule, args.domain, args.journal, args.section, args.document_kind):
                continue
            for hit in match_rule(rule, visible):
                line, column = line_column(raw, hit.start())
                expression_matches.append({"file": str(source_path), "line": line, "column": column, "match": hit.group(0), "rule": rule.source_form})

    for rule in term_rules:
        if rule.status == "confirmed" and not rule.source:
            schema_errors.append({"type": "missing_source", "rule": rule.source_form, "row": rule.row, "bank": str(term_path)})
        if rule.status == "confirmed" and not rule.user_reviewed:
            schema_errors.append({"type": "unreviewed_confirmed_term", "rule": rule.source_form, "row": rule.row, "bank": str(term_path)})
        if rule.override_user_deny and not (rule.status == "confirmed" and rule.user_reviewed):
            schema_errors.append({"type": "invalid_override", "rule": rule.source_form, "row": rule.row, "bank": str(term_path)})

    for rule in expression_rules:
        if rule.status == "confirmed" and not rule.source:
            schema_errors.append({"type": "missing_source", "rule": rule.source_form, "row": rule.row, "bank": str(expression_path)})
        if rule.status == "confirmed" and not rule.user_reviewed:
            schema_errors.append({"type": "unreviewed_confirmed_expression", "rule": rule.source_form, "row": rule.row, "bank": str(expression_path)})

    for rule in exception_rules:
        if rule.status == "confirmed" and not rule.source:
            schema_errors.append({"type": "missing_source", "rule": rule.source_form, "row": rule.row, "bank": str(exception_path)})
        if rule.status == "confirmed" and not rule.user_reviewed:
            schema_errors.append({"type": "unreviewed_confirmed_exception", "rule": rule.source_form, "row": rule.row, "bank": str(exception_path)})
        if rule.status == "confirmed" and not rule.override_user_deny:
            schema_errors.append({"type": "exception_missing_explicit_override", "rule": rule.source_form, "row": rule.row, "bank": str(exception_path)})

    for rule in candidate_rules:
        if rule.status == "confirmed" and not rule.candidate_type:
            schema_errors.append({"type": "confirmed_candidate_missing_type", "rule": rule.source_form, "row": rule.row, "bank": str(candidate_path)})
        if rule.status == "confirmed" and not rule.source:
            schema_errors.append({"type": "missing_source", "rule": rule.source_form, "row": rule.row, "bank": str(candidate_path)})
        if rule.status == "confirmed" and not rule.user_reviewed:
            schema_errors.append({"type": "unreviewed_confirmed_candidate", "rule": rule.source_form, "row": rule.row, "bank": str(candidate_path)})
        if rule.status == "confirmed" and not candidate_migrated(rule, all_active_rules):
            schema_errors.append({"type": "confirmed_candidate_not_migrated", "rule": rule.source_form, "row": rule.row, "migrated_to": rule.migrated_to, "bank": str(candidate_path)})
        if rule.status == "rejected" and not rule.rejection_reason:
            schema_errors.append({"type": "rejected_candidate_missing_reason", "rule": rule.source_form, "row": rule.row, "bank": str(candidate_path)})

    inputs = [source_record(path) for path in source_paths if path.exists()]
    rules = [source_record(path) for path in rule_files if path.exists()]
    return {
        "audit_version": AUDIT_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "context": {"domain": args.domain, "journal": args.journal, "section": args.section, "document_kind": args.document_kind},
        "inputs": inputs,
        "rule_files": rules,
        "counts": {
            "violations": len(violations),
            "exceptions": len(exceptions),
            "conflicts": len(conflicts),
            "unresolved": len(unresolved),
            "expression_matches": len(expression_matches),
            "schema_errors": len(schema_errors),
        },
        "violations": violations,
        "exceptions": exceptions,
        "conflicts": conflicts,
        "unresolved": unresolved,
        "expression_matches": expression_matches,
        "schema_errors": schema_errors,
        "pass": not violations and not unresolved and not schema_errors,
    }


def markdown_report(result: dict[str, object]) -> str:
    counts = result["counts"]
    lines = [
        "# Writing Memory Audit",
        "",
        f"- Audit version: `{result['audit_version']}`",
        f"- Generated (UTC): `{result['generated_at_utc']}`",
        f"- Context: `{json.dumps(result['context'], ensure_ascii=False)}`",
        f"- Pass: `{result['pass']}`",
        "",
        "## Counts",
        "",
        "| Category | Count |",
        "|---|---:|",
    ]
    for key, value in counts.items():
        lines.append(f"| {key} | {value} |")
    for title, key in (("Violations", "violations"), ("Exceptions", "exceptions"), ("Conflicts", "conflicts"), ("Unresolved", "unresolved"), ("Schema errors", "schema_errors")):
        lines.extend(["", f"## {title}", ""])
        entries = result[key]
        if not entries:
            lines.append("None.")
        else:
            lines.append("```json")
            lines.append(json.dumps(entries, ensure_ascii=False, indent=2))
            lines.append("```")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        result = audit(args)
    except (OSError, UnicodeError, ValueError) as exc:
        print(json.dumps({"audit_version": AUDIT_VERSION, "pass": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    output = json.dumps(result, ensure_ascii=False, indent=2) if args.output_format == "json" else markdown_report(result)
    print(output)
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
