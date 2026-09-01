#!/usr/bin/env python3
"""Offline citation normalization, auditing, and rendering helpers.

The caller supplies metadata that has already been gathered and verified.  This
module never retrieves metadata, opens URLs, reads credentials, or guesses a
missing bibliographic fact.
"""

from __future__ import annotations

import re
from typing import Any, Iterable, Sequence

from bibtex_compare import audit_bibtex, parse_bibtex, patch_bibtex
from ieee_renderer import ieee_author_name, ieee_authors, ieee_reference, ieee_text


DOI_PATTERN = re.compile(r"\b(10\.\d{4,9}/[-._;()/:A-Z0-9]+)", re.IGNORECASE)
ARXIV_PATTERN = re.compile(
    r"(?:arxiv\s*:\s*|arxiv\.org/(?:abs|pdf)/)([a-z-]+(?:\.[A-Z]{2})?/\d{7}|\d{4}\.\d{4,5})(?:v\d+)?",
    re.IGNORECASE,
)

CITATION_FIELDS = (
    "journal",
    "journal_abbreviation",
    "conference",
    "conference_abbreviation",
    "book_title",
    "editors",
    "edition",
    "publication_place",
    "chapter",
    "standard_number",
    "report_number",
    "volume",
    "issue",
    "pages",
    "article_number",
    "publisher",
    "publication_date",
    "accessed_date",
    "isbn",
    "arxiv_id",
    "original_citation",
)

FIELD_LABELS = {
    "authors": "作者",
    "year": "年份",
    "journal": "期刊名",
    "journal_abbreviation": "期刊标准缩写",
    "conference": "会议名",
    "conference_abbreviation": "会议标准缩写",
    "book_title": "书名",
    "editors": "编者",
    "edition": "版次",
    "publication_place": "出版地",
    "chapter": "章节号",
    "standard_number": "标准号",
    "report_number": "报告号",
    "venue": "出版来源",
    "volume": "卷号",
    "issue": "期号",
    "pages": "页码",
    "article_number": "文章号",
    "publisher": "出版者",
    "publication_date": "出版日期",
    "accessed_date": "访问日期",
    "doi": "DOI",
    "isbn": "ISBN",
    "arxiv_id": "arXiv 标识",
    "title": "题名",
}


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def first_text(record: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = clean_text(record.get(key))
        if value:
            return value
    return ""


def normalize_title(value: Any) -> str:
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", " ", clean_text(value).lower()).strip()


def normalize_doi(value: Any) -> str:
    text = clean_text(value)
    if not text:
        return ""
    text = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^doi\s*:\s*", "", text, flags=re.IGNORECASE)
    match = DOI_PATTERN.search(text)
    return match.group(1).rstrip(".,;:)]}").lower() if match else ""


def normalize_arxiv_id(value: Any) -> str:
    text = clean_text(value)
    if not text:
        return ""
    match = ARXIV_PATTERN.search(text)
    if match:
        return match.group(1).lower()
    text = re.sub(r"^arxiv\s*:\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"v\d+$", "", text, flags=re.IGNORECASE)
    if re.fullmatch(r"(?:[a-z-]+(?:\.[A-Z]{2})?/\d{7}|\d{4}\.\d{4,5})", text, re.IGNORECASE):
        return text.lower()
    return ""


def _author_from_mapping(value: dict[str, Any]) -> str:
    literal = first_text(value, "literal", "name", "full_name")
    if literal:
        return literal
    given = first_text(value, "given", "given_name", "first", "first_name")
    family = first_text(value, "family", "family_name", "last", "last_name")
    suffix = first_text(value, "suffix")
    return " ".join(item for item in (given, family, suffix) if item)


def normalize_author_list(value: Any) -> list[str]:
    """Return explicit authors without guessing comma-separated name counts."""
    if isinstance(value, (list, tuple)):
        authors: list[str] = []
        for item in value:
            author = _author_from_mapping(item) if isinstance(item, dict) else clean_text(item)
            if author:
                authors.append(author)
        return authors
    text = clean_text(value)
    if not text:
        return []
    if re.search(r"\s+and\s+", text, flags=re.IGNORECASE):
        return [item for item in (clean_text(part) for part in re.split(r"\s+and\s+", text, flags=re.IGNORECASE)) if item]
    if ";" in text:
        return [item for item in (clean_text(part) for part in text.split(";")) if item]
    return [text]


def authors_legacy(value: Any) -> str:
    return " and ".join(normalize_author_list(value))


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


def _normalize_source_entry(source: str, value: Any) -> dict[str, str]:
    if isinstance(value, dict):
        entry_source = first_text(value, "source", "name", "provider") or clean_text(source)
        entry_value = first_text(value, "value", "text", "metadata")
        entry_url = first_text(value, "url", "source_url")
    else:
        entry_source = clean_text(source)
        entry_value = clean_text(value)
        entry_url = ""
    return {
        key: item
        for key, item in (("source", entry_source), ("value", entry_value), ("url", entry_url))
        if item
    }


def normalize_field_sources(value: Any) -> dict[str, list[dict[str, str]]]:
    """Normalize field-level provenance while retaining conflicting values."""
    if not isinstance(value, dict):
        return {}
    normalized: dict[str, list[dict[str, str]]] = {}
    for field, raw_entries in value.items():
        field_name = clean_text(field)
        if not field_name:
            continue
        entries: list[dict[str, str]] = []
        if isinstance(raw_entries, list):
            for item in raw_entries:
                if isinstance(item, dict):
                    entry = _normalize_source_entry("", item)
                else:
                    entry = _normalize_source_entry(clean_text(item), "")
                if entry:
                    entries.append(entry)
        elif isinstance(raw_entries, dict):
            if set(raw_entries).intersection({"source", "name", "provider", "value", "text", "metadata", "url", "source_url"}):
                entry = _normalize_source_entry("", raw_entries)
                if entry:
                    entries.append(entry)
            else:
                for source, item in raw_entries.items():
                    entry = _normalize_source_entry(clean_text(source), item)
                    if entry:
                        entries.append(entry)
        elif clean_text(raw_entries):
            entries.append({"source": clean_text(raw_entries)})
        if entries:
            normalized[field_name] = entries
    return normalized


def _comparison_value(field: str, value: Any) -> str:
    text = clean_text(value)
    if field == "doi":
        return normalize_doi(text)
    if field == "title":
        return normalize_title(text)
    if field in {"pages", "volume", "issue", "article_number", "year"}:
        return re.sub(r"[^a-z0-9]+", "", text.lower())
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", " ", text.lower()).strip()


def source_conflict_issues(field_sources: dict[str, list[dict[str, str]]]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for field, entries in field_sources.items():
        values: dict[str, str] = {}
        for entry in entries:
            value = entry.get("value", "")
            normalized = _comparison_value(field, value)
            if normalized:
                values.setdefault(normalized, value)
        if len(values) > 1:
            shown_values = list(values.values())
            issues.append(
                make_issue(
                    "source_conflict",
                    field,
                    f"不同来源给出的{FIELD_LABELS.get(field, field)}不一致：{' / '.join(shown_values)}。",
                    values=shown_values,
                    sources=[entry.get("source", "") for entry in entries if entry.get("source")],
                )
            )
    return issues


def _identifier_values(raw: Any, normalizer: Any) -> list[str]:
    values = raw if isinstance(raw, (list, tuple, set)) else [raw]
    normalized: list[str] = []
    for value in values:
        item = normalizer(value)
        if item and item not in normalized:
            normalized.append(item)
    return normalized


def citation_metadata(raw: dict[str, Any], base: dict[str, Any], index: int) -> dict[str, Any]:
    author_list = normalize_author_list(raw.get("author_list") or raw.get("authors") or raw.get("author"))
    source_type = clean_text(base.get("source_type"))
    venue = clean_text(base.get("venue"))
    journal = first_text(raw, "journal", "journal_name", "container_title")
    conference = first_text(raw, "conference", "conference_name", "event", "booktitle")
    book_title = first_text(raw, "book_title", "booktitle", "book")
    if not journal and source_type in {"journal-article", "systematic-review", "meta-analysis", "review", "early-access"}:
        journal = venue
    if not conference and source_type == "conference-paper":
        conference = venue
    if not book_title and source_type in {"book", "book-chapter"}:
        book_title = venue

    field_sources = normalize_field_sources(raw.get("field_sources") or raw.get("metadata_sources"))
    supplied_issues = [
        dict(issue)
        for issue in (raw.get("issues") or [])
        if isinstance(issue, dict)
    ] if isinstance(raw.get("issues"), list) else []
    issues = merge_issues(supplied_issues, source_conflict_issues(field_sources))
    normalized_authors = [
        re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", author.lower())
        for author in author_list
    ]
    if len(set(normalized_authors)) < len(normalized_authors):
        issues.append(
            make_issue(
                "author_sequence_duplicate",
                "authors",
                "作者序列含重复姓名，已保留原顺序，未自动删除。",
                severity="info",
                values=author_list,
            )
        )
    alternate_dois = _identifier_values(raw.get("alternate_dois"), normalize_doi)
    for key in ("published_doi", "version_of"):
        value = normalize_doi(raw.get(key))
        if value and value != clean_text(base.get("doi")) and value not in alternate_dois:
            alternate_dois.append(value)
    alternate_arxiv_ids = _identifier_values(raw.get("alternate_arxiv_ids"), normalize_arxiv_id)
    arxiv_id = normalize_arxiv_id(first_text(raw, "arxiv_id", "arxiv", "eprint"))
    generic_number = first_text(raw, "number")
    issue = first_text(raw, "issue", "journal_issue")
    if not issue and source_type in {
        "journal-article",
        "systematic-review",
        "meta-analysis",
        "review",
        "early-access",
    }:
        issue = generic_number
    standard_number = first_text(raw, "standard_number", "standard_no", "document_number")
    if source_type == "standard" and not standard_number:
        standard_number = generic_number
    report_number = first_text(raw, "report_number", "report_no")
    if source_type == "report" and not report_number:
        report_number = generic_number

    return {
        "input_index": index,
        "merged_input_indices": [index],
        "author_list": author_list,
        "authors": " and ".join(author_list),
        "journal": journal,
        "journal_abbreviation": first_text(raw, "journal_abbreviation", "journal_abbrev", "short_journal"),
        "conference": conference,
        "conference_abbreviation": first_text(raw, "conference_abbreviation", "conference_abbrev", "short_conference"),
        "book_title": book_title,
        "editor_list": normalize_author_list(raw.get("editor_list") or raw.get("editors") or raw.get("editor")),
        "editors": authors_legacy(raw.get("editor_list") or raw.get("editors") or raw.get("editor")),
        "edition": first_text(raw, "edition"),
        "publication_place": first_text(raw, "publication_place", "place", "address"),
        "chapter": first_text(raw, "chapter", "chapter_number"),
        "standard_number": standard_number,
        "report_number": report_number,
        "volume": first_text(raw, "volume", "journal_volume"),
        "issue": issue,
        "pages": first_text(raw, "pages", "page", "page_range"),
        "article_number": first_text(raw, "article_number", "article_no", "eid"),
        "publisher": first_text(raw, "publisher", "institution", "organization"),
        "publication_date": first_text(raw, "publication_date", "publish_date", "published", "date"),
        "accessed_date": first_text(raw, "accessed_date", "access_date", "urldate"),
        "isbn": first_text(raw, "isbn"),
        "arxiv_id": arxiv_id,
        "field_sources": field_sources,
        "original_citation": first_text(raw, "original_citation", "citation", "reference"),
        "alternate_dois": alternate_dois,
        "alternate_arxiv_ids": alternate_arxiv_ids,
        "issues": issues,
    }


def _issue_identity(issue: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        clean_text(issue.get("code")),
        clean_text(issue.get("field")),
        clean_text(issue.get("expected")),
        clean_text(issue.get("actual")),
    )


def merge_issues(*collections: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for collection in collections:
        for issue in collection:
            if not isinstance(issue, dict):
                continue
            identity = _issue_identity(issue)
            if identity in seen:
                continue
            seen.add(identity)
            merged.append(dict(issue))
    return merged


def merge_citation_records(
    preferred: dict[str, Any], records: Sequence[dict[str, Any]]
) -> dict[str, Any]:
    """Merge only known metadata and preserve disagreements as issues."""
    merged = dict(preferred)
    issues = list(merged.get("issues") or [])
    compatible = [
        item
        for item in records
        if bool(item.get("preprint")) == bool(preferred.get("preprint"))
        and (item.get("source_type") == "early-access")
        == (preferred.get("source_type") == "early-access")
    ]
    for field in (*CITATION_FIELDS, "authors", "year", "venue", "doi"):
        current = clean_text(merged.get(field))
        observed: list[str] = []
        for item in compatible:
            value = clean_text(item.get(field))
            if value and _comparison_value(field, value) not in {
                _comparison_value(field, seen) for seen in observed
            }:
                observed.append(value)
        if not current and observed:
            merged[field] = observed[0]
        if len(observed) > 1:
            issues.append(
                make_issue(
                    "source_conflict",
                    field,
                    f"重复记录中的{FIELD_LABELS.get(field, field)}不一致：{' / '.join(observed)}；保留优先版本的值。",
                    values=observed,
                )
            )

    author_lists = [item.get("author_list") or [] for item in compatible if item.get("author_list")]
    if not merged.get("author_list") and author_lists:
        merged["author_list"] = list(author_lists[0])
        merged["authors"] = " and ".join(merged["author_list"])
    editor_lists = [item.get("editor_list") or [] for item in compatible if item.get("editor_list")]
    if not merged.get("editor_list") and editor_lists:
        merged["editor_list"] = list(editor_lists[0])
        merged["editors"] = " and ".join(merged["editor_list"])

    field_sources: dict[str, list[dict[str, str]]] = {}
    for item in records:
        for field, entries in (item.get("field_sources") or {}).items():
            target = field_sources.setdefault(field, [])
            for entry in entries:
                if entry not in target:
                    target.append(dict(entry))
    merged["field_sources"] = field_sources
    issues.extend(source_conflict_issues(field_sources))

    for field, normalizer in (
        ("alternate_dois", normalize_doi),
        ("alternate_arxiv_ids", normalize_arxiv_id),
    ):
        values: list[str] = []
        for item in records:
            candidates = list(item.get(field) or [])
            if field == "alternate_dois" and item.get("doi") != merged.get("doi"):
                candidates.append(item.get("doi"))
            if field == "alternate_arxiv_ids" and item.get("arxiv_id") != merged.get("arxiv_id"):
                candidates.append(item.get("arxiv_id"))
            for candidate in candidates:
                value = normalizer(candidate)
                if value and value not in values:
                    values.append(value)
        merged[field] = values

    merged["input_index"] = min(int(item.get("input_index") or 0) for item in records)
    merged["merged_input_indices"] = sorted(
        {
            int(input_index)
            for item in records
            for input_index in (item.get("merged_input_indices") or [item.get("input_index")])
            if input_index
        }
    )
    merged["issues"] = merge_issues(issues)
    return merged


def add_missing_citation_issues(record: dict[str, Any]) -> None:
    source_type = clean_text(record.get("source_type"))
    required = ["year"] if source_type == "standard" else ["authors", "year"]
    if source_type in {"journal-article", "systematic-review", "meta-analysis", "review", "early-access"}:
        required.extend(["journal", "journal_abbreviation", "doi"])
        if source_type == "early-access":
            required.append("publication_date")
        else:
            required.extend(["volume", "issue"])
        if source_type != "early-access" and not record.get("pages") and not record.get("article_number"):
            required.append("pages")
    elif source_type == "conference-paper":
        required.extend(["conference", "conference_abbreviation", "doi"])
        if not record.get("pages") and not record.get("article_number"):
            required.append("pages")
    elif source_type == "book":
        required.extend(["publisher", "isbn"])
    elif source_type == "book-chapter":
        required.extend(["book_title", "publisher", "pages"])
    elif source_type in {"standard", "report", "policy", "official-data"}:
        required.append("publisher")
    elif source_type == "online-resource":
        required.extend(["url", "accessed_date"])
    elif source_type == "preprint" and not (record.get("doi") or record.get("arxiv_id")):
        required.append("arxiv_id")

    issues = list(record.get("issues") or [])
    if source_type == "early-access":
        publication_date = clean_text(record.get("publication_date"))
        if publication_date and not re.fullmatch(
            r"(?:18|19|20)\d{2}-\d{1,2}-\d{1,2}", publication_date
        ):
            issues.append(
                make_issue(
                    "citation_field_incomplete",
                    "publication_date",
                    "Early Access 未查到完整出版日期。",
                    severity="info",
                )
            )
    for field in required:
        if field == "pages" and (record.get("pages") or record.get("article_number")):
            continue
        if record.get(field):
            continue
        issues.append(
            make_issue(
                "citation_field_missing",
                field,
                f"未查到{FIELD_LABELS.get(field, field)}。",
                severity="info",
            )
        )
    record["issues"] = merge_issues(issues)
