#!/usr/bin/env python3
"""Normalize evidence records already gathered by an agent.

Portions of the normalization design are adapted from K-Dense Inc.'s
``skills/research-lookup/scripts/manuscript_packet.py`` version 1.4, accepted
at commit b085e116c5de7d244fccbd666f1a9e73257999e4 and used under the MIT
license in ../LICENSE.md.

This module deliberately contains no retrieval client. It reads local JSON and
emits JSON, Markdown, BibTeX, or IEEE-style references.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Sequence
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)
_citation = __import__("citation_records")


SCHEMA_VERSION = 2
DOI_PATTERN = re.compile(r"\b(10\.\d{4,9}/[-._;()/:A-Z0-9]+)", re.IGNORECASE)
PMID_PATTERN = re.compile(
    r"(?:\bPMID\s*[:#]?\s*|pubmed\.ncbi\.nlm\.nih\.gov/)(\d{5,10})\b",
    re.IGNORECASE,
)
YEAR_PATTERN = re.compile(r"(?<!\d)((?:18|19|20)\d{2})(?!\d)")

VERIFICATION_RANK = {
    "primary-source-verified": 4,
    "metadata-verified": 3,
    "discovery-only": 2,
    "unverified": 1,
    "conflict-unresolved": 0,
}

VERIFICATION_ALIASES = {
    "primary": "primary-source-verified",
    "primary-verified": "primary-source-verified",
    "source-verified": "primary-source-verified",
    "verified": "metadata-verified",
    "identifier-verified": "metadata-verified",
    "metadata": "metadata-verified",
    "search-only": "discovery-only",
    "discovery": "discovery-only",
    "conflict": "conflict-unresolved",
    "unknown": "unverified",
    "": "discovery-only",
}

SOURCE_TYPE_ALIASES = {
    "article": "journal-article",
    "journal": "journal-article",
    "journal article": "journal-article",
    "conference": "conference-paper",
    "conference paper": "conference-paper",
    "proceedings": "conference-paper",
    "early access": "early-access",
    "early-access article": "early-access",
    "online first": "early-access",
    "book": "book",
    "monograph": "book",
    "technical report": "report",
    "tech report": "report",
    "web": "online-resource",
    "webpage": "online-resource",
    "website": "online-resource",
    "online": "online-resource",
    "systematic review": "systematic-review",
    "meta analysis": "meta-analysis",
    "meta-analysis": "meta-analysis",
    "review article": "review",
    "dataset": "official-data",
    "official dataset": "official-data",
    "government data": "official-data",
}

SOURCE_TYPE_RANK = {
    "systematic-review": 8,
    "meta-analysis": 8,
    "journal-article": 7,
    "conference-paper": 6,
    "early-access": 6,
    "standard": 6,
    "review": 5,
    "methods-protocol": 5,
    "official-data": 5,
    "policy": 4,
    "book-chapter": 3,
    "book": 3,
    "report": 3,
    "online-resource": 2,
    "preprint": 2,
    "other": 1,
}


class EvidenceRecordError(ValueError):
    """Raised when evidence-record input violates the local contract."""


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def _first_text(record: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = _clean_text(record.get(key))
        if value:
            return value
    return ""


def canonicalize_url(url: str) -> str:
    """Return a stable URL for comparison without tracking parameters."""
    value = _clean_text(url)
    if not value:
        return ""
    parts = urlsplit(value)
    if parts.scheme.lower() not in {"http", "https"} or not parts.netloc:
        return value.rstrip("/")
    query = [
        (key, item)
        for key, item in parse_qsl(parts.query, keep_blank_values=True)
        if not key.lower().startswith("utm_")
        and key.lower() not in {"ref", "source", "campaign"}
    ]
    path = parts.path.rstrip("/") or "/"
    return urlunsplit(
        (parts.scheme.lower(), parts.netloc.lower(), path, urlencode(query), "")
    )


def normalize_title(title: str) -> str:
    """Normalize a title for conservative duplicate detection."""
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", " ", _clean_text(title).lower()).strip()


def normalize_doi(value: str) -> str:
    text = _clean_text(value)
    if not text:
        return ""
    text = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^doi\s*:\s*", "", text, flags=re.IGNORECASE)
    match = DOI_PATTERN.search(text)
    return match.group(1).rstrip(".,;:)]}").lower() if match else ""


def extract_doi(text: str) -> str:
    """Extract the first DOI without treating it as verification evidence."""
    match = DOI_PATTERN.search(text or "")
    return match.group(1).rstrip(".,;:)]}").lower() if match else ""


def extract_pmid(text: str) -> str:
    match = PMID_PATTERN.search(text or "")
    return match.group(1) if match else ""


def extract_year(record: dict[str, Any], text: str) -> str:
    for key in (
        "year",
        "published_year",
        "publication_year",
        "publication_date",
        "publish_date",
        "published",
        "date",
    ):
        match = YEAR_PATTERN.search(_clean_text(record.get(key)))
        if match:
            return match.group(1)
    match = YEAR_PATTERN.search(text or "")
    return match.group(1) if match else ""


def _joined_record_text(record: dict[str, Any]) -> str:
    values: list[str] = []
    for key in (
        "title",
        "venue",
        "journal",
        "conference",
        "book_title",
        "publisher",
        "relevance",
        "abstract",
        "snippet",
        "notes",
    ):
        value = record.get(key)
        if isinstance(value, list):
            values.extend(_clean_text(item) for item in value if _clean_text(item))
        elif _clean_text(value):
            values.append(_clean_text(value))
    return "\n".join(values)


def classify_source_type(record: dict[str, Any], text: str) -> str:
    explicit = _first_text(record, "source_type", "publication_type", "type").lower()
    explicit = SOURCE_TYPE_ALIASES.get(explicit, explicit.replace("_", "-"))
    if explicit in SOURCE_TYPE_RANK:
        return explicit

    lowered = f" {text.lower()} "
    url = _first_text(record, "url", "landing_page_url", "source_url").lower()
    if any(term in lowered for term in (" early access ", " online first ", " advance online publication ")):
        return "early-access"
    if any(term in lowered for term in (" systematic review ", " scoping review ")):
        return "systematic-review"
    if any(term in lowered for term in (" meta-analysis ", " meta analysis ")):
        return "meta-analysis"
    if any(term in lowered for term in (" standard ", " recommendation ", " rfc ")):
        return "standard"
    if any(term in lowered for term in (" policy ", " regulation ", " guideline ")):
        return "policy"
    if any(term in lowered for term in (" official data ", " official dataset ", " statistics ")):
        return "official-data"
    if any(term in lowered for term in (" conference ", " proceedings ", " symposium ")):
        return "conference-paper"
    if any(term in lowered for term in (" protocol ", " methodology ", " validation method ")):
        return "methods-protocol"
    if any(term in lowered for term in (" technical report ", " research report ", " tech report ")):
        return "report"
    if any(term in lowered for term in (" review article ", " literature review ")):
        return "review"
    if "arxiv.org" in url or any(term in lowered for term in (" preprint ", " biorxiv ", " medrxiv ")):
        return "preprint"
    if any(term in lowered for term in (" book chapter ", " edited volume ")):
        return "book-chapter"
    if _first_text(record, "isbn") or any(term in lowered for term in (" monograph ", " textbook ")):
        return "book"
    if _first_text(record, "accessed_date", "access_date", "urldate"):
        return "online-resource"
    if _first_text(record, "journal", "venue", "publisher") or normalize_doi(_first_text(record, "doi")):
        return "journal-article"
    return "other"


def normalize_verification_status(value: Any) -> str:
    status = _clean_text(value).lower().replace("_", "-")
    status = VERIFICATION_ALIASES.get(status, status)
    if status not in VERIFICATION_RANK:
        raise EvidenceRecordError(f"unsupported verification_status: {value!r}")
    return status


def _normalize_authors(value: Any) -> str:
    if isinstance(value, list):
        return " and ".join(_clean_text(item) for item in value if _clean_text(item))
    return _clean_text(value)


def _normalize_score(value: Any) -> float:
    if value in (None, ""):
        return 0.0
    try:
        score = float(value)
    except (TypeError, ValueError) as exc:
        raise EvidenceRecordError(f"relevance_score must be numeric, got {value!r}") from exc
    if score < 0:
        raise EvidenceRecordError("relevance_score must not be negative")
    return score


def normalize_record(raw: dict[str, Any], index: int) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise EvidenceRecordError(f"record {index} must be an object")
    title = _first_text(raw, "title", "name")
    relevance = _first_text(raw, "relevance", "why_relevant", "relevance_note")
    raw_url = _first_text(raw, "url", "landing_page_url", "source_url", "direct_link")
    url = canonicalize_url(raw_url)
    text = _joined_record_text(raw)
    doi = normalize_doi(_first_text(raw, "doi")) or extract_doi(f"{raw_url}\n{text}")
    pmid = _first_text(raw, "pmid") or extract_pmid(f"{raw_url}\n{text}")
    arxiv_id = _citation.normalize_arxiv_id(
        _first_text(raw, "arxiv_id", "arxiv", "eprint")
    )
    isbn = _first_text(raw, "isbn")
    year = extract_year(raw, text)
    source_type = classify_source_type(raw, text)
    generic_number = _first_text(raw, "number")
    standard_number = _first_text(raw, "standard_number", "standard_no", "document_number")
    report_number = _first_text(raw, "report_number", "report_no")
    if source_type == "standard" and not standard_number:
        standard_number = generic_number
    if source_type == "report" and not report_number:
        report_number = generic_number

    if not title:
        raise EvidenceRecordError(f"record {index} is missing title")
    if not relevance:
        raise EvidenceRecordError(f"record {index} is missing relevance")
    if not url and not doi and not arxiv_id and not isbn and not standard_number and not report_number:
        raise EvidenceRecordError(
            f"record {index} needs url, doi, arxiv_id, isbn, standard_number, or report_number"
        )

    status = normalize_verification_status(raw.get("verification_status", ""))
    retracted = bool(raw.get("retracted")) or any(
        marker in text.lower() for marker in ("retracted", "retraction notice", "withdrawn")
    )
    corrected = bool(raw.get("corrected")) or any(
        marker in text.lower() for marker in ("correction", "erratum")
    )
    preprint = bool(raw.get("preprint")) or source_type == "preprint"

    record = {
        "record_id": "",
        "title": title,
        "authors": _normalize_authors(raw.get("authors") or raw.get("author")),
        "year": year,
        "venue": _first_text(
            raw,
            "venue",
            "journal",
            "conference",
            "book_title",
            "source_name",
        ),
        "source_type": source_type,
        "url": url,
        "doi": doi,
        "pmid": re.sub(r"\D", "", pmid),
        "relevance": relevance,
        "relevance_score": _normalize_score(raw.get("relevance_score")),
        "verification_status": status,
        "verification_note": _first_text(raw, "verification_note", "verification_basis"),
        "evidence_gap": _first_text(raw, "evidence_gap", "gap", "limitations"),
        "supporting_excerpt": _first_text(raw, "supporting_excerpt", "excerpt", "snippet"),
        "preprint": preprint,
        "corrected": corrected,
        "retracted": retracted,
        "alternate_urls": [],
    }
    record.update(_citation.citation_metadata(raw, record, index))
    if any(issue.get("code") == "source_conflict" for issue in record.get("issues", [])):
        record["verification_status"] = "conflict-unresolved"
    return record


def _record_keys(record: dict[str, Any]) -> list[str]:
    keys = [
        f"doi:{record['doi']}" if record.get("doi") else "",
        f"pmid:{record['pmid']}" if record.get("pmid") else "",
        f"url:{record['url']}" if record.get("url") else "",
        f"arxiv:{record['arxiv_id']}" if record.get("arxiv_id") else "",
    ]
    keys.extend(f"doi:{value}" for value in record.get("alternate_dois") or [] if value)
    keys.extend(
        f"arxiv:{value}" for value in record.get("alternate_arxiv_ids") or [] if value
    )
    return list(dict.fromkeys(key for key in keys if key))


def _version_status_compatible(left: dict[str, Any], right: dict[str, Any]) -> bool:
    return (
        bool(left.get("retracted")) == bool(right.get("retracted"))
        and bool(left.get("corrected")) == bool(right.get("corrected"))
    )


def _author_identity_set(record: dict[str, Any]) -> set[str]:
    authors = record.get("author_list") or _citation.normalize_author_list(
        record.get("authors")
    )
    return {
        re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", str(author).lower())
        for author in authors
        if str(author).strip()
    }


def _years_compatible(
    left: dict[str, Any], right: dict[str, Any], *, cross_version: bool
) -> bool:
    left_year = _clean_text(left.get("year"))
    right_year = _clean_text(right.get("year"))
    if not left_year or not right_year:
        return False
    if not (left_year.isdigit() and right_year.isdigit()):
        return left_year == right_year
    difference = abs(int(left_year) - int(right_year))
    return difference <= 2 if cross_version else difference == 0


def _title_fallback_match(left: dict[str, Any], right: dict[str, Any]) -> bool:
    title = normalize_title(left.get("title", ""))
    if len(title) < 20 or title != normalize_title(right.get("title", "")):
        return False
    if not _version_status_compatible(left, right):
        return False
    if not (_author_identity_set(left) & _author_identity_set(right)):
        return False

    left_doi = _clean_text(left.get("doi"))
    right_doi = _clean_text(right.get("doi"))
    left_version = str(left.get("source_type") or "")
    right_version = str(right.get("source_type") or "")
    prepublication = {"preprint", "early-access"}
    cross_version = (
        left_version != right_version
        and bool({left_version, right_version} & prepublication)
    )
    if left_doi and right_doi and left_doi != right_doi and not cross_version:
        return False
    if not cross_version and left_version != right_version and "other" not in {
        left_version,
        right_version,
    }:
        return False
    return _years_compatible(left, right, cross_version=cross_version)


def _add_identity_issue(
    record: dict[str, Any], other: dict[str, Any], message: str
) -> None:
    issue = _citation.make_issue(
        "duplicate_identity_conflict",
        "doi",
        message,
        values=[record.get("doi") or "", other.get("doi") or ""],
    )
    record["issues"] = _citation.merge_issues(record.get("issues") or [], [issue])


def _sort_key(record: dict[str, Any]) -> tuple[Any, ...]:
    try:
        year = int(record.get("year") or 0)
    except (TypeError, ValueError):
        year = 0
    return (
        1 if record.get("retracted") else 0,
        -float(record.get("relevance_score") or 0),
        -VERIFICATION_RANK.get(str(record.get("verification_status")), 0),
        -SOURCE_TYPE_RANK.get(str(record.get("source_type")), 0),
        -year,
        normalize_title(str(record.get("title") or "")),
    )


def _merge_preference_key(record: dict[str, Any]) -> tuple[Any, ...]:
    source_type = str(record.get("source_type") or "")
    version_rank = 2 if record.get("preprint") or source_type == "preprint" else 1 if source_type == "early-access" else 0
    return (
        1 if record.get("retracted") else 0,
        version_rank,
        -VERIFICATION_RANK.get(str(record.get("verification_status")), 0),
        *_sort_key(record)[1:],
        int(record.get("input_index") or 0),
    )


def _merge_group(group: Sequence[dict[str, Any]]) -> dict[str, Any]:
    ordered = sorted(group, key=_merge_preference_key)
    merged = dict(ordered[0])
    text_fields = (
        "title",
        "authors",
        "relevance",
        "verification_note",
        "evidence_gap",
        "supporting_excerpt",
    )
    for field in text_fields:
        if not merged.get(field):
            merged[field] = next((item.get(field) for item in ordered if item.get(field)), "")
    compatible = [
        item
        for item in ordered
        if bool(item.get("preprint")) == bool(merged.get("preprint"))
        and (item.get("source_type") == "early-access")
        == (merged.get("source_type") == "early-access")
    ]
    for field in ("year", "venue", "url", "doi", "pmid"):
        if not merged.get(field):
            merged[field] = next(
                (item.get(field) for item in compatible if item.get(field)), ""
            )
    merged["verification_status"] = max(
        (item["verification_status"] for item in ordered),
        key=lambda item: VERIFICATION_RANK[item],
    )
    merged["relevance_score"] = max(float(item.get("relevance_score") or 0) for item in ordered)
    merged["retracted"] = any(bool(item.get("retracted")) for item in ordered)
    merged["corrected"] = any(bool(item.get("corrected")) for item in ordered)
    merged["preprint"] = all(bool(item.get("preprint")) for item in ordered)
    urls = []
    for item in ordered:
        for value in [item.get("url"), *(item.get("alternate_urls") or [])]:
            if value and value not in urls:
                urls.append(value)
    if merged.get("url") in urls:
        urls.remove(merged["url"])
    merged["alternate_urls"] = urls
    merged = _citation.merge_citation_records(merged, ordered)
    if any(issue.get("code") == "source_conflict" for issue in merged.get("issues", [])):
        merged["verification_status"] = "conflict-unresolved"
    return merged


def deduplicate_records(records: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Conservatively merge duplicate works using transitive identifier matches."""
    parents = list(range(len(records)))

    def find(item: int) -> int:
        while parents[item] != item:
            parents[item] = parents[parents[item]]
            item = parents[item]
        return item

    def union(left: int, right: int) -> None:
        left_root, right_root = find(left), find(right)
        if left_root != right_root:
            parents[right_root] = left_root

    key_owners: dict[str, list[int]] = {}
    for index, record in enumerate(records):
        for key in _record_keys(record):
            for owner in key_owners.get(key, []):
                if _version_status_compatible(record, records[owner]):
                    union(index, owner)
            key_owners.setdefault(key, []).append(index)

    for left_index, left in enumerate(records):
        for right_index in range(left_index + 1, len(records)):
            right = records[right_index]
            if find(left_index) == find(right_index):
                continue
            if _title_fallback_match(left, right):
                union(left_index, right_index)
                continue
            same_title = (
                len(normalize_title(left.get("title", ""))) >= 20
                and normalize_title(left.get("title", ""))
                == normalize_title(right.get("title", ""))
            )
            author_overlap = bool(_author_identity_set(left) & _author_identity_set(right))
            different_dois = bool(
                left.get("doi")
                and right.get("doi")
                and left.get("doi") != right.get("doi")
            )
            status_difference = not _version_status_compatible(left, right)
            if same_title and author_overlap and (different_dois or status_difference):
                message = (
                    "题名和作者相同，但 DOI 或勘误/撤稿状态不同，已保留为独立记录。"
                )
                _add_identity_issue(left, right, message)
                _add_identity_issue(right, left, message)

    groups: dict[int, list[dict[str, Any]]] = {}
    for index, record in enumerate(records):
        groups.setdefault(find(index), []).append(record)
    return [_merge_group(group) for group in groups.values()]


def _coverage(records: Sequence[dict[str, Any]], input_count: int) -> dict[str, Any]:
    statuses = Counter(record["verification_status"] for record in records)
    source_types = Counter(record["source_type"] for record in records)
    years = Counter(record["year"] or "unknown" for record in records)
    issue_codes = Counter(
        issue.get("code", "unknown")
        for record in records
        for issue in record.get("issues") or []
    )
    verified = statuses["primary-source-verified"] + statuses["metadata-verified"]
    return {
        "input_records": input_count,
        "unique_records": len(records),
        "duplicates_removed": input_count - len(records),
        "verified_records": verified,
        "primary_source_verified": statuses["primary-source-verified"],
        "discovery_or_unverified": (
            statuses["discovery-only"]
            + statuses["unverified"]
            + statuses["conflict-unresolved"]
        ),
        "missing_year": sum(1 for record in records if not record.get("year")),
        "missing_authors": sum(1 for record in records if not record.get("authors")),
        "missing_doi": sum(1 for record in records if not record.get("doi")),
        "records_with_citation_issues": sum(
            1 for record in records if record.get("issues")
        ),
        "citation_issue_mix": dict(sorted(issue_codes.items())),
        "verification_mix": dict(sorted(statuses.items())),
        "source_type_mix": dict(sorted(source_types.items())),
        "publication_years": dict(sorted(years.items())),
        "preprints": sum(1 for record in records if record.get("preprint")),
        "corrected": sum(1 for record in records if record.get("corrected")),
        "retracted_or_withdrawn": sum(1 for record in records if record.get("retracted")),
    }


def build_output(
    payload: Any,
    *,
    order: str = "ranked",
    bibtex_text: str | None = None,
) -> dict[str, Any]:
    if order not in {"ranked", "input"}:
        raise EvidenceRecordError(f"unsupported order: {order!r}")
    if isinstance(payload, list):
        query = ""
        raw_records = payload
    elif isinstance(payload, dict):
        query = _clean_text(payload.get("query"))
        raw_records = payload.get("records")
        if raw_records is None:
            raw_records = payload.get("sources")
    else:
        raise EvidenceRecordError("input must be a JSON array or object")

    if not isinstance(raw_records, list):
        raise EvidenceRecordError("input object must contain a records or sources array")

    normalized = [normalize_record(raw, index + 1) for index, raw in enumerate(raw_records)]
    records = deduplicate_records(normalized)
    if order == "ranked":
        records = sorted(records, key=_sort_key)
    else:
        records = sorted(records, key=lambda record: int(record.get("input_index") or 0))
    for index, record in enumerate(records, 1):
        record["record_id"] = f"E{index:03d}"
        _citation.add_missing_citation_issues(record)

    bibtex_audit = None
    if bibtex_text is not None:
        bibtex_audit = _citation.audit_bibtex(records, bibtex_text)

    coverage = _coverage(records, len(raw_records))
    warnings: list[str] = []
    if coverage["missing_year"]:
        warnings.append(f"{coverage['missing_year']} record(s) have unknown publication year.")
    if coverage["discovery_or_unverified"]:
        warnings.append(
            f"{coverage['discovery_or_unverified']} record(s) still need direct-source or metadata verification."
        )
    if coverage["missing_authors"]:
        warnings.append(
            f"{coverage['missing_authors']} record(s) have no verified author metadata."
        )
    if coverage["retracted_or_withdrawn"]:
        warnings.append(
            f"{coverage['retracted_or_withdrawn']} record(s) are marked retracted or withdrawn; do not use them as supporting evidence."
        )

    output = {
        "schema_version": SCHEMA_VERSION,
        "query": query,
        "order": order,
        "coverage": coverage,
        "warnings": warnings,
        "records": records,
        "duplicate_groups": [
            {
                "record_id": record["record_id"],
                "merged_input_indices": record.get("merged_input_indices") or [record.get("input_index")],
            }
            for record in records
            if len(record.get("merged_input_indices") or []) > 1
        ],
    }
    if bibtex_audit is not None:
        output["bibtex_audit"] = bibtex_audit
        output["_bibtex_source"] = bibtex_text
    return output


def _markdown_escape(value: Any) -> str:
    return _clean_text(value).replace("|", "\\|").replace("\n", " ")


def markdown_text(output: dict[str, Any]) -> str:
    coverage = output["coverage"]
    lines = ["# 证据记录", ""]
    if output.get("query"):
        lines.extend([f"- 检索问题：{output['query']}"])
    lines.extend(
        [
            f"- 唯一记录：{coverage['unique_records']}",
            f"- 已核实记录：{coverage['verified_records']}",
            f"- 去除重复：{coverage['duplicates_removed']}",
            "",
        ]
    )
    if output.get("warnings"):
        lines.extend(["## 提醒", ""])
        lines.extend(f"- {warning}" for warning in output["warnings"])
        lines.append("")

    lines.extend(
        [
            "## 结果",
            "",
            "| ID | 题名 | 年份 | 类型 | 直接链接 / DOI | 相关性 | 核实状态 |",
            "|---|---|---:|---|---|---|---|",
        ]
    )
    for record in output["records"]:
        locator_parts = []
        if record.get("url"):
            locator_parts.append(f"[来源]({record['url']})")
        if record.get("doi"):
            locator_parts.append(f"DOI: `{record['doi']}`")
        lines.append(
            "| {record_id} | {title} | {year} | {source_type} | {locator} | {relevance} | {status} |".format(
                record_id=record["record_id"],
                title=_markdown_escape(record["title"]),
                year=record.get("year") or "unknown",
                source_type=_markdown_escape(record["source_type"]),
                locator="<br>".join(locator_parts),
                relevance=_markdown_escape(record["relevance"]),
                status=_markdown_escape(record["verification_status"]),
            )
        )

    gaps = [record for record in output["records"] if record.get("evidence_gap")]
    if gaps:
        lines.extend(["", "## 证据缺口", ""])
        lines.extend(
            f"- {record['record_id']}：{record['evidence_gap']}" for record in gaps
        )
    issue_records = [record for record in output["records"] if record.get("issues")]
    if issue_records:
        lines.extend(["", "## 引用问题", ""])
        for record in issue_records:
            for issue in record.get("issues") or []:
                lines.append(
                    f"- {record['record_id']} [{issue.get('code', 'unknown')}]：{issue.get('message', '')}"
                )
    audit = output.get("bibtex_audit") or {}
    if audit.get("issues"):
        lines.extend(["", "## BibTeX 对照问题", ""])
        lines.extend(
            f"- [{issue.get('code', 'unknown')}]：{issue.get('message', '')}"
            for issue in audit["issues"]
        )
    return "\n".join(lines).rstrip() + "\n"


def _bibtex_escape(value: Any) -> str:
    return _clean_text(value).replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")


def _bibtex_pages(value: Any) -> str:
    return re.sub(r"(?<=\d)\s*(?:--|[-–—])\s*(?=\d)", "--", _clean_text(value))


def _bibtex_key(record: dict[str, Any], used: set[str]) -> str:
    authors = _clean_text(record.get("authors"))
    author_token = re.split(r"\s+|\band\b|,", authors, maxsplit=1, flags=re.IGNORECASE)[0]
    title_token = normalize_title(record.get("title", "")).split(" ")[0]
    base = re.sub(
        r"[^A-Za-z0-9]+",
        "",
        f"{author_token or 'source'}{record.get('year') or 'nd'}{title_token or record['record_id']}",
    ) or record["record_id"]
    candidate = base
    suffix = 2
    while candidate.lower() in used:
        candidate = f"{base}{suffix}"
        suffix += 1
    used.add(candidate.lower())
    return candidate


def bibtex_text(records: Sequence[dict[str, Any]]) -> str:
    type_map = {
        "conference-paper": "inproceedings",
        "book-chapter": "incollection",
        "book": "book",
        "report": "techreport",
        "standard": "misc",
        "policy": "misc",
        "official-data": "misc",
        "preprint": "misc",
        "online-resource": "misc",
    }
    blocks: list[str] = []
    used: set[str] = set()
    for record in records:
        entry_type = type_map.get(record.get("source_type"), "article")
        key = _bibtex_key(record, used)
        note_parts = [f"verification: {record['verification_status']}"]
        if record.get("retracted"):
            note_parts.append("retracted or withdrawn; do not use as supporting evidence")
        venue_field = ""
        venue_value = ""
        if entry_type == "article":
            venue_field = "journal"
            venue_value = (
                record.get("journal_abbreviation")
                or record.get("journal")
                or record.get("venue")
            )
        elif entry_type in {"inproceedings", "incollection"}:
            venue_field = "booktitle"
            venue_value = (
                record.get("conference_abbreviation")
                or record.get("conference")
                or record.get("book_title")
                or record.get("venue")
            )
        number_value = record.get("issue")
        if entry_type == "techreport":
            number_value = record.get("report_number")
        elif record.get("source_type") == "standard":
            number_value = record.get("standard_number")
        publisher_field = "publisher"
        if entry_type == "techreport":
            publisher_field = "institution"
        elif record.get("source_type") == "standard":
            publisher_field = "organization"
        fields = [
            ("title", record.get("title")),
            ("author", record.get("authors")),
            ("year", record.get("year")),
            (venue_field, venue_value),
            ("volume", record.get("volume")),
            ("number", number_value),
            ("pages", _bibtex_pages(record.get("pages"))),
            ("eid", record.get("article_number")),
            ("editor", record.get("editors")),
            ("edition", record.get("edition")),
            ("address", record.get("publication_place")),
            ("chapter", record.get("chapter")),
            (publisher_field, record.get("publisher")),
            ("isbn", record.get("isbn")),
            ("eprint", record.get("arxiv_id")),
            ("archiveprefix", "arXiv" if record.get("arxiv_id") else ""),
            ("doi", record.get("doi")),
            ("url", record.get("url")),
            ("urldate", record.get("accessed_date")),
            ("note", "; ".join(note_parts)),
        ]
        lines = [f"@{entry_type}{{{key},"]
        for name, value in fields:
            if name and value:
                lines.append(f"  {name} = {{{_bibtex_escape(value)}}},")
        lines.append("}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks) + ("\n" if blocks else "")


def render_output(output: dict[str, Any], output_format: str) -> str:
    if output_format == "json":
        public_output = {
            key: value for key, value in output.items() if not key.startswith("_")
        }
        return json.dumps(public_output, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if output_format == "markdown":
        return markdown_text(output)
    if output_format == "bibtex":
        if output.get("_bibtex_source") is not None:
            patched = _citation.patch_bibtex(
                output["records"], str(output.get("_bibtex_source") or "")
            )
            new_records = [
                record for record in output["records"] if not record.get("bibtex_key")
            ]
            generated = bibtex_text(new_records)
            if generated:
                if not patched or patched.endswith("\n\n"):
                    separator = ""
                elif patched.endswith("\n"):
                    separator = "\n"
                else:
                    separator = "\n\n"
                return patched + separator + generated
            return patched
        return bibtex_text(output["records"])
    if output_format == "ieee":
        return _citation.ieee_text(output["records"])
    raise EvidenceRecordError(f"unsupported output format: {output_format}")


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError as exc:
        raise EvidenceRecordError(f"input file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise EvidenceRecordError(
            f"invalid JSON in {path}: line {exc.lineno}, column {exc.colno}"
        ) from exc


def write_result(text: str, output_path: Path | None) -> None:
    if output_path is None:
        if hasattr(sys.stdout, "buffer"):
            sys.stdout.buffer.write(text.encode("utf-8"))
        else:
            sys.stdout.write(text)
        return
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(text, encoding="utf-8", newline="\n")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Normalize already-gathered evidence records without network access."
    )
    parser.add_argument("--input", required=True, type=Path, help="Input JSON path.")
    parser.add_argument(
        "--format",
        required=True,
        choices=("json", "markdown", "bibtex", "ieee"),
        help="Output format.",
    )
    parser.add_argument("--output", type=Path, help="Optional output path; stdout when omitted.")
    parser.add_argument(
        "--order",
        choices=("ranked", "input"),
        default="ranked",
        help="Rank records (default) or preserve first input occurrence.",
    )
    parser.add_argument(
        "--bibtex-input",
        type=Path,
        help="Optional existing BibTeX file to compare with verified record fields.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        bibtex_source = (
            args.bibtex_input.read_text(encoding="utf-8-sig")
            if args.bibtex_input is not None
            else None
        )
        output = build_output(
            load_json(args.input), order=args.order, bibtex_text=bibtex_source
        )
        write_result(render_output(output, args.format), args.output)
    except (EvidenceRecordError, OSError) as exc:
        sys.stderr.write(f"evidence_records: {exc}\n")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
