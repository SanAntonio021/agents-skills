#!/usr/bin/env python3
"""Render verified local metadata as IEEE-style reference text."""

from __future__ import annotations

import re
from typing import Any, Sequence


MONTHS = {
    1: "Jan.",
    2: "Feb.",
    3: "Mar.",
    4: "Apr.",
    5: "May",
    6: "Jun.",
    7: "Jul.",
    8: "Aug.",
    9: "Sep.",
    10: "Oct.",
    11: "Nov.",
    12: "Dec.",
}


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


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


def format_ieee_date(value: Any, *, include_day: bool = True) -> str:
    text = clean_text(value)
    match = re.fullmatch(r"((?:18|19|20)\d{2})(?:-(\d{1,2})(?:-(\d{1,2}))?)?", text)
    if not match:
        return text
    year = match.group(1)
    if not match.group(2):
        return year
    month_number = int(match.group(2))
    month = MONTHS.get(month_number)
    if not month:
        return text
    if match.group(3) and include_day:
        return f"{month} {int(match.group(3))}, {year}"
    return f"{month} {year}"


def format_page_range(value: Any) -> str:
    text = clean_text(value)
    return re.sub(r"(?<=\d)\s*[-–—]\s*(?=\d)", "–", text)


def _initials(given: str) -> str:
    tokens = re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿ]+(?:[-'][A-Za-zÀ-ÖØ-öø-ÿ]+)?", given)
    initials: list[str] = []
    for token in tokens:
        parts = token.split("-")
        initials.append("-".join(f"{part[0].upper()}." for part in parts if part))
    return " ".join(initials)


def ieee_author_name(name: str) -> str:
    value = clean_text(name)
    if not value:
        return ""
    if "," in value:
        family, given = (clean_text(part) for part in value.split(",", 1))
        return " ".join(item for item in (_initials(given), family) if item)
    tokens = value.split()
    if len(tokens) < 2 or re.search(r"[\u4e00-\u9fff]", value):
        return value
    return " ".join(item for item in (_initials(" ".join(tokens[:-1])), tokens[-1]) if item)


def ieee_authors(record: dict[str, Any]) -> str:
    authors = list(record.get("author_list") or normalize_author_list(record.get("authors")))
    if len(authors) == 1 and clean_text(record.get("publisher")):
        if re.sub(r"\W+", "", authors[0].lower()) == re.sub(
            r"\W+", "", clean_text(record.get("publisher")).lower()
        ):
            return authors[0]
    rendered = [ieee_author_name(author) for author in authors]
    rendered = [author for author in rendered if author]
    if not rendered:
        return ""
    if len(rendered) > 6:
        return f"{rendered[0]} et al."
    if len(rendered) == 1:
        return rendered[0]
    if len(rendered) == 2:
        return f"{rendered[0]} and {rendered[1]}"
    return ", ".join(rendered[:-1]) + f", and {rendered[-1]}"


def _append(parts: list[str], value: Any, prefix: str = "") -> None:
    text = clean_text(value)
    comparable = re.sub(r"\W+", "", text.lower())
    existing = {
        re.sub(r"\W+", "", clean_text(item).lower())
        for item in parts
    }
    if text and comparable not in existing:
        parts.append(f"{prefix}{text}")


def _quoted_title(record: dict[str, Any]) -> str:
    title = clean_text(record.get("title"))
    return f"“{title}”" if title else ""


def _journal(record: dict[str, Any]) -> str:
    return clean_text(
        record.get("journal_abbreviation")
        or record.get("journal")
        or record.get("venue")
    )


def _conference(record: dict[str, Any]) -> str:
    return clean_text(
        record.get("conference_abbreviation")
        or record.get("conference")
        or record.get("venue")
    )


def _editors(record: dict[str, Any]) -> str:
    editors = list(record.get("editor_list") or normalize_author_list(record.get("editors")))
    if not editors:
        return ""
    rendered = ieee_authors({"author_list": editors})
    return f"{rendered}, {'Ed.' if len(editors) == 1 else 'Eds.'}"


def _place_and_publisher(record: dict[str, Any]) -> str:
    place = clean_text(record.get("publication_place"))
    publisher = clean_text(record.get("publisher"))
    if place and publisher:
        return f"{place}: {publisher}"
    return publisher or place


def _same_organization(left: Any, right: Any) -> bool:
    left_key = re.sub(r"\W+", "", clean_text(left).lower())
    right_key = re.sub(r"\W+", "", clean_text(right).lower())
    return bool(left_key) and left_key == right_key


def ieee_reference(record: dict[str, Any]) -> str:
    """Use supplied fields only; an absent field stays absent."""
    source_type = clean_text(record.get("source_type"))
    authors = ieee_authors(record)
    title = clean_text(record.get("title"))
    year = clean_text(record.get("year"))
    publication_date = format_ieee_date(record.get("publication_date"))
    periodical_date = format_ieee_date(
        record.get("publication_date"), include_day=False
    )
    pages = format_page_range(record.get("pages"))
    article_number = clean_text(record.get("article_number"))
    doi = normalize_doi(record.get("doi"))
    url = clean_text(record.get("url"))
    parts: list[str] = []
    if source_type != "standard":
        _append(parts, authors)

    if source_type == "book":
        _append(parts, title)
        _append(parts, record.get("edition"))
        _append(parts, _place_and_publisher(record))
        _append(parts, publication_date or year)
        _append(parts, record.get("isbn"), "ISBN ")
    elif source_type == "book-chapter":
        _append(parts, _quoted_title(record))
        _append(parts, record.get("book_title") or record.get("venue"), "in ")
        _append(parts, _editors(record))
        _append(parts, record.get("edition"))
        _append(parts, _place_and_publisher(record))
        _append(parts, publication_date or year)
        _append(parts, record.get("chapter"), "ch. ")
        _append(parts, pages, "pp. ")
    elif source_type == "conference-paper":
        _append(parts, _quoted_title(record))
        conference = _conference(record)
        if conference and not re.match(r"^(?:in\s+)?proc\.", conference, re.IGNORECASE):
            conference = f"in Proc. {conference}"
        _append(parts, conference)
        _append(parts, record.get("publication_place"))
        _append(parts, publication_date or year)
        _append(parts, pages, "pp. ")
        _append(parts, article_number, "Art. no. ")
    elif source_type == "preprint":
        _append(parts, _quoted_title(record))
        arxiv_id = clean_text(record.get("arxiv_id"))
        _append(parts, f"arXiv:{arxiv_id} [Preprint]" if arxiv_id else "Preprint")
        _append(parts, publication_date or year)
    elif source_type == "early-access":
        _append(parts, _quoted_title(record))
        _append(parts, _journal(record))
        _append(parts, "early access")
        _append(parts, publication_date or year)
        _append(parts, article_number, "Art. no. ")
    elif source_type == "standard":
        _append(parts, title)
        _append(parts, record.get("standard_number") or record.get("venue"))
        _append(parts, authors or record.get("publisher"))
        _append(parts, record.get("publication_place"))
        _append(parts, publication_date or year)
    elif source_type == "report":
        _append(parts, _quoted_title(record))
        publisher = clean_text(record.get("publisher"))
        if publisher and not _same_organization(authors, publisher):
            _append(parts, publisher)
        _append(parts, record.get("publication_place"))
        _append(parts, record.get("report_number"), "Rep. ")
        _append(parts, publication_date or year)
        if doi:
            _append(parts, doi, "doi: ")
        rendered = ", ".join(part.rstrip(", ") for part in parts if part).rstrip(", ")
        rendered = rendered.replace("”,", ",”")
        accessed = format_ieee_date(record.get("accessed_date"))
        if accessed:
            rendered += f". Accessed: {accessed}."
        if url:
            if not accessed:
                rendered += "."
            rendered += f" [Online]. Available: {url}"
            return rendered
        return rendered + "."
    elif source_type in {"policy", "official-data"}:
        _append(parts, _quoted_title(record))
        _append(parts, _place_and_publisher(record) or record.get("venue"))
        _append(parts, publication_date or year)
    elif source_type == "online-resource":
        sentences: list[str] = []
        if authors:
            sentences.append(authors.rstrip(". ") + ".")
        if title:
            sentences.append(f"“{title.rstrip('. ')}.”")
        website_title = clean_text(record.get("publisher") or record.get("venue"))
        if website_title:
            sentences.append(website_title.rstrip(". ") + ".")
        if publication_date or year:
            sentences.append((publication_date or year).rstrip(". ") + ".")
        accessed = format_ieee_date(record.get("accessed_date"))
        if accessed:
            sentences.append(f"Accessed: {accessed}.")
        if url:
            sentences.append(f"[Online]. Available: {url}")
        elif doi:
            sentences.append(f"doi: {doi}.")
        return " ".join(sentences)
    else:
        _append(parts, _quoted_title(record))
        _append(parts, _journal(record))
        _append(parts, record.get("volume"), "vol. ")
        _append(parts, record.get("issue"), "no. ")
        if article_number and not pages:
            _append(parts, periodical_date or year)
            _append(parts, article_number, "Art. no. ")
        else:
            _append(parts, pages, "pp. ")
            _append(parts, periodical_date or year)
            _append(parts, article_number, "Art. no. ")

    if doi:
        _append(parts, doi, "doi: ")
    rendered = ", ".join(part.rstrip(", ") for part in parts if part).rstrip(", ")
    rendered = rendered.replace("”,", ",”")
    if url and not doi:
        return rendered + f". [Online]. Available: {url}"
    return rendered + "."


def ieee_text(records: Sequence[dict[str, Any]]) -> str:
    lines = [f"[{index}] {ieee_reference(record)}" for index, record in enumerate(records, 1)]
    return "\n".join(lines) + ("\n" if lines else "")
