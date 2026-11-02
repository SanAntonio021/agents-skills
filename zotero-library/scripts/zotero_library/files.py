"""PDF structural/hash checks shared by import, readback and conservative pruning."""
import hashlib
from pathlib import Path

from .errors import LibraryError


def inspect_pdf(path, expected=None):
    try:
        from pypdf import PdfReader
    except ImportError:
        raise LibraryError('dependency_missing_pypdf') from None
    try:
        path = Path(path)
        if not path.is_file() or not 5 <= path.stat().st_size <= 200 * 1024 * 1024:
            raise LibraryError('pdf_unreadable')
        raw = path.read_bytes()
        sha = hashlib.sha256(raw).hexdigest()
        if expected is not None and expected != sha:
            raise LibraryError('pdf_hash_mismatch')
        if not raw.startswith(b'%PDF-'):
            raise LibraryError('not_pdf')
        # Keep every stream local; Zotero receives no Python-held file handle.
        with path.open('rb') as stream:
            reader = PdfReader(stream, strict=True)
            if reader.is_encrypted or not len(reader.pages):
                raise LibraryError('pdf_unreadable')
            annotated = any(bool(page.get('/Annots')) for page in reader.pages)
            pages = len(reader.pages)
        return {'sha256': sha, 'pages': pages, 'embedded_annotations': annotated}
    except LibraryError:
        raise
    except Exception:
        raise LibraryError('pdf_inspection_unknown') from None
