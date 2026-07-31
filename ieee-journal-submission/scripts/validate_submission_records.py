#!/usr/bin/env python3
"""Compatibility shim for the shared journal-submission validator.

IEEE-specific lifecycle rules stay in this skill's references and tests, while
the data-contract validator has one canonical implementation in the sibling
``journal-submission`` skill. Keeping this import path preserves existing
scripts and tests without silently maintaining two validators.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path


CANONICAL_SCRIPT = (
    Path(__file__).resolve().parents[2]
    / "journal-submission"
    / "scripts"
    / "validate_submission_records.py"
)


def _load_canonical():
    if not CANONICAL_SCRIPT.is_file():
        raise ImportError(
            "ieee-journal-submission requires the sibling journal-submission skill "
            f"at {CANONICAL_SCRIPT}"
        )
    spec = importlib.util.spec_from_file_location(
        "_journal_submission_validate_submission_records", CANONICAL_SCRIPT
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load shared validator: {CANONICAL_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_CANONICAL = _load_canonical()
for _name in dir(_CANONICAL):
    if not _name.startswith("_"):
        globals()[_name] = getattr(_CANONICAL, _name)

__all__ = [name for name in globals() if not name.startswith("_")]


if __name__ == "__main__":
    raise SystemExit(_CANONICAL.main())
