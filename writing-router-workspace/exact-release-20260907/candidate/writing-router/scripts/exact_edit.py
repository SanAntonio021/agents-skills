"""Deterministic UTF-8 title/append edits and byte-exact candidate checks.

Titles are literal single lines (include '# ' yourself for Markdown). Append
text is literal, including its whitespace. Only missing boundary newlines are
inserted: use the source's first LF/CRLF, or LF if none exists. No final newline
is forced. Keep a source BOM at byte zero and all original body bytes intact.

File guards follow the local preflight pattern, not a hostile-concurrency
sandbox. Parents must already exist. Exclusive creation prevents overwrites;
an I/O failure can leave an incomplete new output, never a success receipt.
No model, prose extraction, normalization, or writing-workflow integration.
"""

from __future__ import annotations

import argparse
import codecs
import hashlib
import json
import os
from pathlib import Path
import stat
from typing import Sequence


class ExactEditError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _check_hash(source: bytes, source_sha256: str) -> None:
    if (
        not isinstance(source_sha256, str)
        or len(source_sha256) != 64
        or any(c not in "0123456789abcdefABCDEF" for c in source_sha256)
    ):
        raise ExactEditError("invalid_sha256", "Source SHA256 must be 64 hex digits.")
    if _digest(source) != source_sha256.lower():
        raise ExactEditError("hash_mismatch", "Source bytes no longer match SHA256.")


def _utf8(data: bytes, label: str) -> None:
    if not isinstance(data, bytes):
        raise ExactEditError("invalid_bytes", f"{label} must be bytes.")
    try:
        data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ExactEditError("invalid_utf8", f"{label} is not valid UTF-8.") from exc


def _literal(text: str | None, label: str) -> bytes:
    if text is None:
        return b""
    if not isinstance(text, str) or not text:
        raise ExactEditError("invalid_operation", f"{label} must be nonempty text.")
    if label == "title" and ("\n" in text or "\r" in text or "\ufeff" in text):
        raise ExactEditError("invalid_operation", "Title must be one line without a BOM.")
    try:
        return text.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ExactEditError("invalid_utf8", f"{label} cannot be encoded as UTF-8.") from exc


def _join(left: bytes, right: bytes, newline: bytes) -> bytes:
    if not left or not right or left.endswith(b"\n") or right.startswith((b"\n", b"\r\n")):
        return left + right
    return left + newline + right


def edit_bytes(
    source: bytes, source_sha256: str, *, title: str | None = None,
    append: str | None = None,
) -> bytes:
    """Build the only allowed result, without decoding/re-encoding the body."""
    _utf8(source, "source")
    _check_hash(source, source_sha256)
    if title is None and append is None:
        raise ExactEditError("invalid_operation", "Specify title and/or append.")
    prefix, suffix = _literal(title, "title"), _literal(append, "append")
    bom = codecs.BOM_UTF8 if source.startswith(codecs.BOM_UTF8) else b""
    body = source[len(bom):]
    first_lf = body.find(b"\n")
    newline = b"\r\n" if first_lf > 0 and body[first_lf - 1:first_lf] == b"\r" else b"\n"
    return bom + _join(_join(prefix, body, newline), suffix, newline)


def validate_bytes(
    source: bytes, candidate: bytes, source_sha256: str, *,
    title: str | None = None, append: str | None = None,
) -> dict:
    """Compare the entire candidate against the same explicit edit operation."""
    expected = edit_bytes(source, source_sha256, title=title, append=append)
    _utf8(candidate, "candidate")
    result = {
        "ok": candidate == expected,
        "action": "verify",
        "source_sha256": _digest(source),
        "expected_sha256": _digest(expected),
        "candidate_sha256": _digest(candidate),
    }
    if not result["ok"]:
        result["error"] = "candidate_mismatch"
    return result


def _checked_path(path: str | os.PathLike[str]) -> Path:
    # Inspect before resolving, including link components preceding '..'.
    raw = Path(path)
    if not raw.is_absolute():
        raw = Path.cwd() / raw
    for part in (*reversed(raw.parents), raw):
        if os.path.lexists(part):
            info = part.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x0400:
                raise ExactEditError("link_rejected", f"Linked/reparse path: {part}")
    return Path(os.path.abspath(raw))


def _read_regular(path: str | os.PathLike[str]) -> tuple[Path, bytes]:
    checked = _checked_path(path)
    if not stat.S_ISREG(checked.lstat().st_mode):
        raise ExactEditError("not_regular_file", f"Input is not a regular file: {checked}")
    return checked, checked.read_bytes()


def apply_file(
    source: str | os.PathLike[str], output: str | os.PathLike[str],
    source_sha256: str, *, title: str | None = None, append: str | None = None,
) -> dict:
    source_path, original = _read_regular(source)
    expected = edit_bytes(original, source_sha256, title=title, append=append)
    output_path = _checked_path(output)
    if output_path == source_path or (
        os.path.lexists(output_path) and os.path.samefile(source_path, output_path)
    ):
        raise ExactEditError("source_overwrite", "Output must not refer to the source.")
    if os.path.lexists(output_path):
        raise ExactEditError("target_exists", f"Output already exists: {output_path}")
    if not stat.S_ISDIR(output_path.parent.lstat().st_mode):
        raise ExactEditError("invalid_parent", "Output parent must be an existing directory.")
    # Re-read immediately before creating the new file to catch stale approval.
    _, current = _read_regular(source_path)
    _check_hash(current, source_sha256)
    try:
        with output_path.open("xb") as stream:
            stream.write(expected)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError as exc:
        raise ExactEditError("target_exists", f"Output already exists: {output_path}") from exc
    _, actual = _read_regular(output_path)
    if actual != expected:
        raise ExactEditError("write_verification_failed", "Output differs from expected bytes.")
    return {
        "ok": True, "action": "apply", "output": str(output_path),
        "source_sha256": _digest(original), "output_sha256": _digest(actual),
    }


def validate_file(
    source: str | os.PathLike[str], candidate: str | os.PathLike[str],
    source_sha256: str, *, title: str | None = None, append: str | None = None,
) -> dict:
    _, original = _read_regular(source)
    _, proposed = _read_regular(candidate)
    return validate_bytes(original, proposed, source_sha256, title=title, append=append)


class JsonArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise ExactEditError("argument_error", message)


def main(argv: Sequence[str] | None = None) -> int:
    parser = JsonArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    for action in ("apply", "verify"):
        command = commands.add_parser(action)
        command.add_argument("--source", required=True)
        command.add_argument("--source-sha256", required=True)
        command.add_argument("--title", help="Literal single-line title, including any Markdown marker.")
        command.add_argument("--append", help="Literal text to append, without rewriting.")
        command.add_argument("--output" if action == "apply" else "--candidate", required=True)
    try:
        args = parser.parse_args(argv)
        operation = {"title": args.title, "append": args.append}
        if args.action == "apply":
            result = apply_file(args.source, args.output, args.source_sha256, **operation)
        else:
            result = validate_file(args.source, args.candidate, args.source_sha256, **operation)
    except ExactEditError as exc:
        result = {"ok": False, "error": exc.code, "message": str(exc)}
    except (OSError, ValueError) as exc:
        result = {"ok": False, "error": "io_error", "message": str(exc)}
    print(json.dumps(result, ensure_ascii=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
