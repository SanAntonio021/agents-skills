"""PDF validation and safe local publication."""

from __future__ import annotations

import hashlib
import io
import re
from pathlib import Path
from typing import Any

from pypdf import PdfReader


MAX_PDF_BYTES = 50_000_000


def compact_text(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (value or "").lower())


def validate_pdf_bytes(
    raw: bytes,
    *,
    doi: str,
    title: str,
    provider_identity_match: bool,
) -> dict[str, Any]:
    if not raw.startswith(b"%PDF-"):
        raise ValueError("downloaded content is not a PDF")
    if not raw or len(raw) > MAX_PDF_BYTES:
        raise ValueError("downloaded PDF size is outside the allowed range")
    reader = PdfReader(io.BytesIO(raw), strict=False)
    if not reader.pages:
        raise ValueError("PDF has no readable pages")
    extracted = []
    for page in reader.pages[: min(3, len(reader.pages))]:
        try:
            extracted.append(page.extract_text() or "")
        except Exception:
            extracted.append("")
    text = "\n".join(extracted)
    printable = text[:120000]
    doi_found = compact_text(doi) in compact_text(printable)
    title_fragment = compact_text(title)[:160]
    title_found = bool(title_fragment) and title_fragment in compact_text(printable)
    identity_verified = provider_identity_match and (doi_found or title_found)
    return {
        "pages": len(reader.pages),
        "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "doi_on_pdf": doi_found,
        "title_on_pdf": title_found,
        "provider_identity_match": provider_identity_match,
        "identity_verified": identity_verified,
    }


def write_new_file(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(raw)
