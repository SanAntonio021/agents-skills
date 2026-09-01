#!/usr/bin/env python3
"""Conservatively compare local verified records with existing BibTeX."""

from __future__ import annotations

import re
from typing import Any, Sequence


FIELD_LABELS = {
    "title": "题名",
    "authors": "作者",
    "year": "年份",
    "venue": "出版来源",
    "volume": "卷号",
    "issue": "期号",
    "pages": "页码",
    "article_number": "文章号",
    "doi": "DOI",
}


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def normalize_title(value: Any) -> str:
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", " ", clean_text(value).lower()).strip()


def normalize_doi(value: Any) -> str:
    text = clean_text(value)
    text = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^doi\s*:\s*", "", text, flags=re.IGNORECASE)
    match = re.search(r"\b(10\.\d{4,9}/[-._;()/:A-Z0-9]+)", text, re.IGNORECASE)
    return match.group(1).rstrip(".,;:)]}").lower() if match else ""


def normalize_author_list(value: Any) -> list[str]:
    if isinstance(value, (list, tuple)):
        return [clean_text(item) for item in value if clean_text(item)]
    text = clean_text(value)
    if not text:
        return []
    if re.search(r"\s+and\s+", text, re.IGNORECASE):
        return [clean_text(item) for item in re.split(r"\s+and\s+", text, flags=re.IGNORECASE) if clean_text(item)]
    if ";" in text:
        return [clean_text(item) for item in text.split(";") if clean_text(item)]
    return [text]


def make_issue(
    code: str,
    field: str,
    message: str,
    *,
    severity: str = "warning",
    **details: Any,
) -> dict[str, Any]:
    issue: dict[str, Any] = {
        "code": code,
        "field": field,
        "severity": severity,
        "message": message,
    }
    for key, value in details.items():
        if value not in (None, "", [], {}):
            issue[key] = value
    return issue


def _issue_identity(issue: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        clean_text(issue.get("code")),
        clean_text(issue.get("field")),
        clean_text(issue.get("expected")),
        clean_text(issue.get("actual")),
    )


def merge_issues(*collections: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for collection in collections:
        for issue in collection:
            if not isinstance(issue, dict):
                continue
            identity = _issue_identity(issue)
            if identity not in seen:
                seen.add(identity)
                merged.append(dict(issue))
    return merged


def _find_balanced(text: str, start: int, opener: str, closer: str) -> int:
    depth = 0
    quoted = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == '"' and opener == "{":
            quoted = not quoted
            continue
        if quoted:
            continue
        if char == opener:
            depth += 1
        elif char == closer:
            depth -= 1
            if depth == 0:
                return index
    return -1


def _split_entry_head(body: str) -> tuple[str, str]:
    depth = 0
    quoted = False
    escaped = False
    for index, char in enumerate(body):
        if escaped:
            escaped = False
        elif char == "\\":
            escaped = True
        elif char == '"' and depth == 0:
            quoted = not quoted
        elif not quoted and char == "{":
            depth += 1
        elif not quoted and char == "}":
            depth = max(0, depth - 1)
        elif char == "," and depth == 0 and not quoted:
            return clean_text(body[:index]), body[index + 1 :]
    return clean_text(body), ""


def _parse_value(text: str, start: int) -> tuple[str, int, bool]:
    while start < len(text) and text[start].isspace():
        start += 1
    if start >= len(text):
        return "", start, True
    if text[start] == "{":
        end = _find_balanced(text, start, "{", "}")
        return (text[start + 1 : end], end + 1, False) if end >= 0 else (text[start + 1 :], len(text), True)
    if text[start] == '"':
        escaped = False
        for index in range(start + 1, len(text)):
            if escaped:
                escaped = False
            elif text[index] == "\\":
                escaped = True
            elif text[index] == '"':
                return text[start + 1 : index], index + 1, False
        return text[start + 1 :], len(text), True
    end = text.find(",", start)
    end = len(text) if end < 0 else end
    value = text[start:end].strip()
    unresolved = bool(value) and not re.fullmatch(r"[+-]?\d+(?:\.\d+)?", value)
    return value, end, unresolved


def _parse_fields(text: str) -> tuple[dict[str, str], bool]:
    fields: dict[str, str] = {}
    unresolved = False
    position = 0
    while position < len(text):
        while position < len(text) and (text[position].isspace() or text[position] == ","):
            position += 1
        if position >= len(text):
            break
        match = re.match(r"([A-Za-z][A-Za-z0-9_-]*)\s*=", text[position:])
        if not match:
            unresolved = True
            break
        name = match.group(1).lower()
        position += match.end()
        value, position, value_unresolved = _parse_value(text, position)
        fields[name] = clean_text(value)
        unresolved = unresolved or value_unresolved or any(
            marker in value for marker in ("{", "}", "\\")
        )
    return fields, unresolved


def parse_bibtex(text: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    entries: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []
    position = 0
    while True:
        match = re.search(r"@([A-Za-z]+)\s*([({])", text[position:])
        if not match:
            break
        entry_start = position + match.start()
        entry_type = match.group(1).lower()
        opener = match.group(2)
        start = position + match.end() - 1
        closer = "}" if opener == "{" else ")"
        end = _find_balanced(text, start, opener, closer)
        if end < 0:
            issues.append(make_issue("bibtex_parse_unresolved", "bibtex", "BibTeX 条目括号未闭合，未强行解析。"))
            break
        body = text[start + 1 : end]
        raw_entry = text[entry_start : end + 1]
        position = end + 1
        if entry_type in {"comment", "preamble"}:
            continue
        if entry_type == "string":
            issues.append(make_issue("bibtex_parse_unresolved", "bibtex", "BibTeX 字符串宏未展开，相关字段保持原样。", severity="info", raw=raw_entry))
            continue
        key, field_text = _split_entry_head(body)
        fields, unresolved = _parse_fields(field_text)
        entry: dict[str, Any] = {
            "entry_type": entry_type,
            "key": key,
            "raw": raw_entry,
            "span_start": entry_start,
            "span_end": end + 1,
            **fields,
        }
        if unresolved:
            entry["parse_unresolved"] = True
            issues.append(make_issue("bibtex_parse_unresolved", "bibtex", f"BibTeX 条目 {key or '(unknown)'} 含无法可靠解析的表达式，未强行改写。", severity="info", bibtex_key=key))
        entries.append(entry)
    if clean_text(text) and not entries and not issues:
        issues.append(make_issue("bibtex_parse_unresolved", "bibtex", "没有识别到可可靠解析的 BibTeX 条目。"))
    return entries, issues


def _comparison_value(field: str, value: Any) -> str:
    text = clean_text(value)
    if field == "doi":
        return normalize_doi(text)
    if field == "title":
        return normalize_title(text)
    if field in {"pages", "volume", "issue", "article_number", "year"}:
        return re.sub(r"[^a-z0-9]+", "", text.lower())
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", " ", text.lower()).strip()


def _authors_for_compare(value: Any) -> str:
    canonical: list[str] = []
    for author in normalize_author_list(value):
        if "," in author:
            family, given = (clean_text(part) for part in author.split(",", 1))
        else:
            tokens = author.split()
            family = tokens[-1] if tokens else ""
            given = " ".join(tokens[:-1])
        family_key = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", family.lower())
        given_tokens = re.findall(r"[a-z0-9\u4e00-\u9fff]+", given.lower())
        given_key = "".join(token[0] for token in given_tokens if token)
        canonical.append(f"{family_key}|{given_key}")
    return "||".join(canonical)


def _record_field(record: dict[str, Any], field: str) -> str:
    if field == "venue":
        return clean_text(record.get("journal") or record.get("conference") or record.get("book_title") or record.get("venue"))
    return clean_text(record.get("authors") if field == "authors" else record.get(field))


def _record_field_values(record: dict[str, Any], field: str) -> list[str]:
    if field == "venue":
        values = [
            record.get("journal_abbreviation"),
            record.get("conference_abbreviation"),
            record.get("journal"),
            record.get("conference"),
            record.get("book_title"),
            record.get("venue"),
        ]
        return list(dict.fromkeys(clean_text(value) for value in values if clean_text(value)))
    value = _record_field(record, field)
    return [value] if value else []


def _entry_field(entry: dict[str, Any], field: str) -> str:
    aliases = {
        "authors": ("author",),
        "venue": ("journal", "booktitle"),
        "issue": ("number",),
        "article_number": ("eid", "articleno", "article-number"),
    }
    for key in aliases.get(field, (field,)):
        value = clean_text(entry.get(key))
        if value:
            return value
    return ""


def _fields_equal(field: str, expected: str, actual: str) -> bool:
    if field == "authors":
        return _authors_for_compare(expected) == _authors_for_compare(actual)
    return _comparison_value(field, expected) == _comparison_value(field, actual)


def audit_bibtex(records: Sequence[dict[str, Any]], text: str) -> dict[str, Any]:
    entries, parse_issues = parse_bibtex(text)
    used: set[int] = set()
    matched = 0
    fields = ("title", "authors", "year", "venue", "volume", "issue", "pages", "article_number", "doi")
    for record in records:
        record_doi = normalize_doi(record.get("doi"))
        record_title = normalize_title(record.get("title"))
        match_index: int | None = None
        if record_doi:
            match_index = next((index for index, entry in enumerate(entries) if index not in used and normalize_doi(entry.get("doi")) == record_doi), None)
        if match_index is None and record_title:
            match_index = next((index for index, entry in enumerate(entries) if index not in used and normalize_title(entry.get("title")) == record_title), None)

        issues = list(record.get("issues") or [])
        if match_index is None:
            issues.append(make_issue("bibtex_entry_unmatched", "bibtex", "原 BibTeX 中未找到这篇论文的对应条目。", severity="info"))
            record["issues"] = merge_issues(issues)
            continue
        used.add(match_index)
        matched += 1
        entry = entries[match_index]
        record["bibtex_key"] = clean_text(entry.get("key"))
        if entry.get("parse_unresolved"):
            issues.append(make_issue("bibtex_parse_unresolved", "bibtex", "对应 BibTeX 条目含无法可靠解析的表达式，未强行改写。", severity="info", bibtex_key=entry.get("key")))
            record["issues"] = merge_issues(issues)
            continue
        for field in fields:
            expected_values = _record_field_values(record, field)
            if not expected_values:
                continue
            expected = expected_values[0]
            actual = _entry_field(entry, field)
            if not actual:
                issues.append(make_issue("bibtex_field_missing", field, f"原 BibTeX 缺少{FIELD_LABELS.get(field, field)}。", severity="info", expected=expected, bibtex_key=entry.get("key")))
            elif not any(
                _fields_equal(field, candidate, actual)
                for candidate in expected_values
            ):
                issues.append(make_issue("bibtex_field_mismatch", field, f"原 BibTeX 的{FIELD_LABELS.get(field, field)}与已核实记录不一致。", expected=expected, actual=actual, bibtex_key=entry.get("key")))
        record["issues"] = merge_issues(issues)

    unmatched_entries = [entry for index, entry in enumerate(entries) if index not in used]
    unmatched_issues = [
        make_issue("bibtex_entry_unmatched", "bibtex", f"BibTeX 条目 {entry.get('key') or '(unknown)'} 未匹配到输入论文。", severity="info", bibtex_key=entry.get("key"))
        for entry in unmatched_entries
    ]
    return {
        "provided": True,
        "entries": len(entries),
        "matched_entries": matched,
        "unmatched_entries": len(unmatched_entries),
        "issues": merge_issues(parse_issues, unmatched_issues),
    }


def _bibtex_escape(value: Any) -> str:
    return (
        clean_text(value)
        .replace("\\", "\\\\")
        .replace("{", "\\{")
        .replace("}", "\\}")
    )


def _verified_updates(record: dict[str, Any], entry_type: str) -> dict[str, str]:
    if record.get("verification_status") not in {
        "primary-source-verified",
        "metadata-verified",
    }:
        return {}
    venue_field = "journal" if entry_type == "article" else "booktitle"
    venue_value = (
        record.get("journal_abbreviation") or record.get("journal")
        if entry_type == "article"
        else record.get("conference_abbreviation")
        or record.get("conference")
        or record.get("book_title")
        or record.get("venue")
    )
    number_value = record.get("issue")
    if entry_type == "techreport":
        number_value = record.get("report_number")
    elif record.get("source_type") == "standard":
        number_value = record.get("standard_number")
    publisher_field = "institution" if entry_type == "techreport" else "publisher"
    if record.get("source_type") == "standard":
        publisher_field = "organization"
    values = {
        "title": record.get("title"),
        "author": record.get("authors"),
        "year": record.get("year"),
        venue_field: venue_value,
        "volume": record.get("volume"),
        "number": number_value,
        "pages": re.sub(
            r"(?<=\d)\s*(?:--|[-–—])\s*(?=\d)",
            "--",
            clean_text(record.get("pages")),
        ),
        "eid": record.get("article_number"),
        "editor": record.get("editors"),
        "edition": record.get("edition"),
        "address": record.get("publication_place"),
        "chapter": record.get("chapter"),
        publisher_field: record.get("publisher"),
        "isbn": record.get("isbn"),
        "doi": record.get("doi"),
        "url": record.get("url"),
        "urldate": record.get("accessed_date"),
    }
    return {key: clean_text(value) for key, value in values.items() if clean_text(value)}


def _render_patched_entry(record: dict[str, Any], entry: dict[str, Any]) -> str:
    if entry.get("parse_unresolved"):
        return clean_text(entry.get("raw"))
    entry_type = clean_text(entry.get("entry_type")) or "misc"
    key = clean_text(entry.get("key"))
    internal = {
        "entry_type",
        "key",
        "raw",
        "span_start",
        "span_end",
        "parse_unresolved",
    }
    fields = {
        name: clean_text(value)
        for name, value in entry.items()
        if name not in internal and clean_text(value)
    }
    updates = _verified_updates(record, entry_type)
    if not updates:
        return str(entry.get("raw") or "")
    changed = False
    for name, value in updates.items():
        actual = fields.get(name, "")
        if actual:
            if name == "author" and _fields_equal("authors", value, actual):
                continue
            if name in {"journal", "booktitle"} and any(
                _fields_equal("venue", candidate, actual)
                for candidate in _record_field_values(record, "venue")
            ):
                continue
            semantic_field = {
                "number": "issue",
                "eid": "article_number",
            }.get(name, name)
            if _fields_equal(semantic_field, value, actual):
                continue
        fields[name] = value
        changed = True
    if not changed:
        return str(entry.get("raw") or "")
    lines = [f"@{entry_type}{{{key},"]
    for name, value in fields.items():
        lines.append(f"  {name} = {{{_bibtex_escape(value)}}},")
    lines.append("}")
    return "\n".join(lines)


def patch_bibtex(records: Sequence[dict[str, Any]], text: str) -> str:
    """Patch simple matched entries; preserve keys, order, macros, and extras."""
    entries, _ = parse_bibtex(text)
    if not entries:
        return text
    records_by_key = {
        clean_text(record.get("bibtex_key")): record
        for record in records
        if clean_text(record.get("bibtex_key"))
    }
    chunks: list[str] = []
    cursor = 0
    for entry in sorted(entries, key=lambda item: int(item.get("span_start") or 0)):
        start = int(entry.get("span_start") or 0)
        end = int(entry.get("span_end") or start)
        chunks.append(text[cursor:start])
        record = records_by_key.get(clean_text(entry.get("key")))
        if record is None or entry.get("parse_unresolved"):
            chunks.append(text[start:end])
        else:
            chunks.append(_render_patched_entry(record, entry))
        cursor = end
    chunks.append(text[cursor:])
    return "".join(chunks)
