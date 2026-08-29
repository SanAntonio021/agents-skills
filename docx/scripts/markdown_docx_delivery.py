#!/usr/bin/env python3
"""Markdown-first DOCX handoff contract and fail-closed delivery helpers.

The module validates the handoff manifest before an existing Pandoc/template
pipeline is called.  It deliberately does not implement Markdown conversion
or Word formatting; those remain the responsibility of the existing docx
helpers.  The output DOCX is never overwritten by this module.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Iterable, Mapping, Sequence
from xml.etree import ElementTree


CONTRACT_VERSION = "1"
LAYERS = (
    "STATIC_PASS",
    "LO_RENDER_PASS",
    "NATIVE_OPEN_PASS",
    "NATIVE_RENDER_PASS",
)
DOCUMENT_ACCEPTANCE_ITEMS = (
    "fonts_and_fallback",
    "paragraph_formatting",
    "table_formatting",
    "header_footer_geometry",
    "pagination",
    "word_native_open",
    "word_native_render",
)
DOCUMENT_ITEM_LAYERS = {
    "fonts_and_fallback": "STATIC_PASS",
    "paragraph_formatting": "STATIC_PASS",
    "table_formatting": "STATIC_PASS",
    "header_footer_geometry": "LO_RENDER_PASS",
    "pagination": "LO_RENDER_PASS",
    "word_native_open": "NATIVE_OPEN_PASS",
    "word_native_render": "NATIVE_RENDER_PASS",
}
ACCEPTANCE_VALUES = {"PASS", "FAIL", "UNVERIFIED", "ENV_UNVERIFIED", "NOT_RUN"}
FAILURE_CODES = {
    "CONTRACT_SCHEMA_INVALID",
    "CONTENT_NOT_FROZEN",
    "CONTENT_NOT_CONFIRMED",
    "CONTENT_OPEN_ITEMS",
    "SOURCE_ENCODING_INVALID",
    "SOURCE_HASH_MISMATCH",
    "TEMPLATE_HASH_MISMATCH",
    "MISSING_TEMPLATE",
    "OUTPUT_COLLISION",
    "STATIC_VALIDATION_FAILED",
    "LO_RENDER_FAILED",
    "NATIVE_OPEN_FAILED",
    "NATIVE_RENDER_FAILED",
    "UNVERIFIED_GATE",
    "DEPENDENCY_UNAVAILABLE",
    "PERMISSION_DENIED",
    "UNSAFE_OFFICE_PROCESS",
    "TIMEOUT",
    "SOURCE_MUTATED",
    "MCP_NOT_ADMITTED",
    "MCP_NONDETERMINISTIC",
    "CLEANUP_FAILED",
    "INTERNAL_CONTRACT_ERROR",
    "MANUAL_REVIEW_TIMEOUT",
}
FAILURE_PRIORITY = (
    "STATIC_VALIDATION_FAILED",
    "LO_RENDER_FAILED",
    "NATIVE_OPEN_FAILED",
    "NATIVE_RENDER_FAILED",
    "SOURCE_MUTATED",
    "CLEANUP_FAILED",
)
SLUG_RE = re.compile(r"[a-z0-9][a-z0-9._-]{2,127}\Z")
OWNER_RE = re.compile(r"(?:user|agent):[a-z0-9][a-z0-9._-]*\Z")
SHA_RE = re.compile(r"[0-9a-f]{64}\Z")
UTC_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\Z")
CONFIRMATION_RESPONSE = "确认内容并导出 Word"
WORD_PERMISSION_RESPONSE = "允许本次 Word 验收"
WORD_MAJOR_VERSIONS = {"14", "15", "16", "17"}


class ContractError(ValueError):
    """A release-facing, machine-readable contract failure."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        phase: str = "contract",
        evidence_paths: Iterable[str] = (),
        retryable: bool = False,
        secondary_failures: Iterable[str] = (),
    ) -> None:
        if code not in FAILURE_CODES:
            raise ValueError(f"unknown failure code: {code}")
        super().__init__(message)
        self.code = code
        self.phase = phase
        self.message = message
        self.evidence_paths = list(evidence_paths)
        self.retryable = retryable
        self.secondary_failures = list(secondary_failures)

    def as_dict(self) -> dict[str, Any]:
        return {
            "failure_code": self.code,
            "failure_detail": {
                "phase": self.phase,
                "message": self.message,
                "evidence_paths": self.evidence_paths,
                "retryable": self.retryable,
                "secondary_failures": self.secondary_failures,
            },
        }


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def utc_now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _contract_error(message: str, *, phase: str = "contract") -> ContractError:
    return ContractError("CONTRACT_SCHEMA_INVALID", message, phase=phase)


def _read_utf8_lf(path: Path, *, label: str) -> tuple[bytes, str]:
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise _contract_error(f"cannot read {label}: {exc}") from exc
    if data.startswith(b"\xef\xbb\xbf"):
        code = "SOURCE_ENCODING_INVALID" if label == "source Markdown" else "CONTRACT_SCHEMA_INVALID"
        raise ContractError(code, f"{label} must be UTF-8 without BOM")
    if b"\r" in data:
        code = "SOURCE_ENCODING_INVALID" if label == "source Markdown" else "CONTRACT_SCHEMA_INVALID"
        raise ContractError(code, f"{label} must use LF line endings")
    try:
        return data, data.decode("utf-8")
    except UnicodeDecodeError as exc:
        code = "SOURCE_ENCODING_INVALID" if label == "source Markdown" else "CONTRACT_SCHEMA_INVALID"
        raise ContractError(code, f"{label} is not valid UTF-8: {exc}") from exc


def _load_json(path: Path, *, label: str) -> tuple[bytes, dict[str, Any]]:
    data, text = _read_utf8_lf(path, label=label)
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise _contract_error(f"{label} is not valid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise _contract_error(f"{label} must contain a JSON object")
    return data, value


def write_json_atomic(path: str | Path, value: Mapping[str, Any]) -> None:
    """Write UTF-8/no-BOM/LF JSON using a same-directory atomic replace."""

    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    fd, temporary_name = tempfile.mkstemp(prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def _validate_slug(value: Any, field: str) -> str:
    if not isinstance(value, str) or not SLUG_RE.fullmatch(value):
        raise _contract_error(f"{field} must be a 3-128 character lowercase ASCII slug")
    return value


def _validate_sha(value: Any, field: str) -> str:
    if not isinstance(value, str) or not SHA_RE.fullmatch(value):
        raise _contract_error(f"{field} must be a lowercase 64-character SHA-256")
    return value


def _validate_owner(value: Any, field: str = "content_owner") -> str:
    if not isinstance(value, str) or not OWNER_RE.fullmatch(value):
        raise _contract_error(f"{field} must match user:<slug> or agent:<skill-slug>")
    return value


def _validate_utc(value: Any, field: str, *, allow_null: bool = False) -> str | None:
    if value is None and allow_null:
        return None
    if not isinstance(value, str) or not UTC_RE.fullmatch(value):
        raise _contract_error(f"{field} must be an RFC 3339 UTC timestamp with second precision")
    try:
        _dt.datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as exc:
        raise _contract_error(f"{field} is not a valid UTC timestamp") from exc
    return value


def _resolve_project_path(project_root: Path, value: Any, field: str, *, allow_null: bool = False) -> Path | None:
    if value is None and allow_null:
        return None
    if not isinstance(value, str) or not value or "\\" in value:
        raise _contract_error(f"{field} must be a non-empty project-relative POSIX path")
    posix = PurePosixPath(value)
    windows = PureWindowsPath(value)
    if posix.is_absolute() or windows.is_absolute() or windows.drive or value.startswith("/"):
        raise _contract_error(f"{field} must not be absolute")
    if any(part in {"", ".", ".."} for part in posix.parts):
        raise _contract_error(f"{field} must not contain '.', '..', or empty path parts")
    root = project_root.resolve()
    candidate = (root / Path(*posix.parts)).resolve(strict=False)
    if candidate != root and root not in candidate.parents:
        raise _contract_error(f"{field} escapes the project root")
    try:
        relative_parts = candidate.relative_to(root).parts
    except ValueError as exc:
        raise _contract_error(f"{field} escapes the project root") from exc
    current = root
    for part in relative_parts:
        current = current / part
        if current.is_symlink():
            raise _contract_error(f"{field} may not traverse a symbolic link")
    return candidate


def _require_file(path: Path, field: str, *, missing_code: str = "CONTRACT_SCHEMA_INVALID") -> None:
    if not path.exists() or not path.is_file():
        raise ContractError(missing_code, f"{field} is missing or is not a file")
    if path.is_symlink():
        raise _contract_error(f"{field} may not be a symbolic link")


def _path_values(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return list(value)
    if value is None:
        return []
    raise _contract_error("evidence_paths values must be strings, string arrays, or null")


def _validate_evidence_paths(project_root: Path, values: Any) -> dict[str, Any]:
    if not isinstance(values, dict):
        raise _contract_error("evidence_paths must be a JSON object")
    for key, value in values.items():
        if not isinstance(key, str) or not key:
            raise _contract_error("evidence_paths keys must be non-empty strings")
        for item in _path_values(value):
            _resolve_project_path(project_root, item, f"evidence_paths.{key}")
    return values


def _validate_acceptance(project_root: Path, manifest: Mapping[str, Any]) -> None:
    acceptance = manifest.get("acceptance")
    if not isinstance(acceptance, dict) or set(acceptance) != set(LAYERS):
        raise _contract_error("acceptance must contain exactly the four delivery layers")
    evidence = manifest["evidence_paths"]
    for layer in LAYERS:
        value = acceptance[layer]
        if value not in ACCEPTANCE_VALUES:
            raise _contract_error(f"acceptance.{layer} has an invalid status")
        if value == "PASS":
            candidates = _path_values(evidence.get(layer))
            if not candidates:
                raise _contract_error(f"acceptance.{layer}=PASS requires an evidence path")
            for item in candidates:
                path = _resolve_project_path(project_root, item, f"evidence_paths.{layer}")
                _require_file(path, f"evidence_paths.{layer}")


def validate_manifest(
    manifest_path: str | Path,
    *,
    project_root: str | Path | None = None,
    check_inputs: bool = True,
) -> dict[str, Any]:
    """Validate a Markdown-to-DOCX handoff manifest and its source hashes."""

    manifest_file = Path(manifest_path).resolve()
    root = Path(project_root).resolve() if project_root is not None else manifest_file.parent.parent.resolve()
    _require_file(manifest_file, "manifest")
    _, manifest = _load_json(manifest_file, label="manifest")
    required = {
        "contract_version",
        "artifact_id",
        "template_id",
        "source_markdown",
        "source_sha256",
        "content_status",
        "content_open_items",
        "content_confirmed",
        "content_owner",
        "confirmed_at",
        "revision",
        "format_source",
        "template_path",
        "template_sha256",
        "output_docx",
        "output_sha256",
        "toolchain_versions",
        "acceptance",
        "evidence_paths",
        "source_unchanged",
        "failure_code",
        "failure_detail",
    }
    unknown = set(manifest) - required
    missing = required - set(manifest)
    if unknown or missing:
        details = []
        if unknown:
            details.append(f"unknown fields: {sorted(unknown)}")
        if missing:
            details.append(f"missing fields: {sorted(missing)}")
        raise _contract_error("manifest schema mismatch (" + "; ".join(details) + ")")
    if manifest["contract_version"] != CONTRACT_VERSION:
        raise _contract_error("unsupported contract_version")
    _validate_slug(manifest["artifact_id"], "artifact_id")
    _validate_slug(manifest["template_id"], "template_id")
    _validate_sha(manifest["source_sha256"], "source_sha256")
    if manifest["content_status"] not in {"draft", "reviewed", "frozen"}:
        raise _contract_error("content_status must be draft, reviewed, or frozen")
    if not isinstance(manifest["content_open_items"], list) or not all(
        isinstance(item, str) for item in manifest["content_open_items"]
    ):
        raise _contract_error("content_open_items must be a string array")
    if not isinstance(manifest["content_confirmed"], bool):
        raise _contract_error("content_confirmed must be boolean")
    _validate_owner(manifest["content_owner"])
    _validate_utc(manifest["confirmed_at"], "confirmed_at", allow_null=True)
    if not isinstance(manifest["revision"], int) or isinstance(manifest["revision"], bool) or manifest["revision"] < 1:
        raise _contract_error("revision must be an integer greater than or equal to 1")
    format_source = manifest["format_source"]
    if format_source not in {"none", "preset", "template"}:
        raise _contract_error("format_source must be none, preset, or template")
    if format_source == "none":
        if manifest["template_path"] is not None or manifest["template_sha256"] != "none":
            raise _contract_error("format_source=none requires template_path=null and template_sha256=none")
    else:
        _validate_slug(format_source, "format_source")
        _validate_sha(manifest["template_sha256"], "template_sha256")
        if not isinstance(manifest["template_path"], str):
            raise _contract_error("template_path is required for preset/template format sources")
    _resolve_project_path(root, manifest["source_markdown"], "source_markdown")
    _resolve_project_path(root, manifest["output_docx"], "output_docx")
    template_file = _resolve_project_path(root, manifest["template_path"], "template_path", allow_null=True)
    source_file = _resolve_project_path(root, manifest["source_markdown"], "source_markdown")
    output_file = _resolve_project_path(root, manifest["output_docx"], "output_docx")
    if manifest["output_sha256"] is not None:
        _validate_sha(manifest["output_sha256"], "output_sha256")
    toolchain = manifest["toolchain_versions"]
    if not isinstance(toolchain, dict) or not toolchain:
        raise _contract_error("toolchain_versions must be a non-empty object")
    for name, version in toolchain.items():
        if not isinstance(name, str) or not name:
            raise _contract_error("toolchain_versions keys must be non-empty strings")
        if version is not None and (not isinstance(version, str) or version.lower() == "latest"):
            raise _contract_error("toolchain_versions values must be exact strings or null, never latest")
    if not isinstance(manifest["source_unchanged"], bool):
        raise _contract_error("source_unchanged must be boolean")
    if manifest["failure_code"] is not None and manifest["failure_code"] not in FAILURE_CODES:
        raise _contract_error("failure_code is not in the controlled failure enum")
    detail = manifest["failure_detail"]
    if manifest["failure_code"] is None and detail is not None:
        raise _contract_error("failure_detail must be null when failure_code is null")
    if manifest["failure_code"] is not None and detail is None:
        raise _contract_error("failure_detail is required when failure_code is set")
    if detail is not None:
        if not isinstance(detail, dict) or set(detail) != {
            "phase",
            "message",
            "evidence_paths",
            "retryable",
            "secondary_failures",
        }:
            raise _contract_error("failure_detail has an invalid schema")
        if not isinstance(detail["phase"], str) or not isinstance(detail["message"], str):
            raise _contract_error("failure_detail.phase/message must be strings")
        if not isinstance(detail["retryable"], bool) or not isinstance(detail["secondary_failures"], list):
            raise _contract_error("failure_detail.retryable/secondary_failures have invalid types")
        _validate_evidence_paths(root, {"failure": detail["evidence_paths"]})
    _validate_evidence_paths(root, manifest["evidence_paths"])
    _validate_acceptance(root, manifest)
    if check_inputs:
        _require_file(source_file, "source_markdown")
        source_bytes, _ = _read_utf8_lf(source_file, label="source Markdown")
        if sha256_bytes(source_bytes) != manifest["source_sha256"]:
            raise ContractError("SOURCE_HASH_MISMATCH", "source Markdown SHA-256 does not match manifest")
        if template_file is not None:
            _require_file(template_file, "template_path", missing_code="MISSING_TEMPLATE")
            if sha256_file(template_file) != manifest["template_sha256"]:
                raise ContractError("TEMPLATE_HASH_MISMATCH", "template SHA-256 does not match manifest")
    return {
        "manifest": manifest,
        "manifest_path": manifest_file,
        "project_root": root,
        "source_path": source_file,
        "template_path": template_file,
        "output_path": output_file,
    }


def validate_export_readiness(manifest: Mapping[str, Any], *, preview: bool = False) -> dict[str, Any]:
    """Return formal/preview mode without silently promoting a preview."""

    if manifest.get("content_status") != "frozen":
        error = ContractError("CONTENT_NOT_FROZEN", "formal DOCX export requires content_status=frozen")
    elif manifest.get("content_open_items") != []:
        error = ContractError("CONTENT_OPEN_ITEMS", "formal DOCX export requires content_open_items=[]")
    elif manifest.get("content_confirmed") is not True:
        error = ContractError("CONTENT_NOT_CONFIRMED", "formal DOCX export requires current-task user confirmation")
    elif not isinstance(manifest.get("confirmed_at"), str):
        error = ContractError("CONTENT_NOT_CONFIRMED", "formal DOCX export requires confirmed_at")
    else:
        return {"mode": "formal", "delivered": False, "failure_code": None}
    if preview:
        return {"mode": "preview", "delivered": False, "failure_code": error.code, "message": error.message}
    raise error


def validate_confirmation(record: Mapping[str, Any], manifest: Mapping[str, Any], manifest_sha256: str) -> None:
    required = {
        "contract_version",
        "artifact_id",
        "revision",
        "actor",
        "user_response",
        "confirmed_at",
        "manifest_sha256",
        "scope",
    }
    if set(record) != required:
        raise ContractError("CONTENT_NOT_CONFIRMED", "confirmation record schema mismatch")
    if record["contract_version"] != CONTRACT_VERSION or record["artifact_id"] != manifest.get("artifact_id"):
        raise ContractError("CONTENT_NOT_CONFIRMED", "confirmation record does not match artifact")
    if record["revision"] != manifest.get("revision") or record["scope"] != "task_revision":
        raise ContractError("CONTENT_NOT_CONFIRMED", "confirmation record scope/revision mismatch")
    if not isinstance(record["actor"], str) or not record["actor"].startswith("user:"):
        raise ContractError("CONTENT_NOT_CONFIRMED", "confirmation actor must be a user identity")
    if record["user_response"] != CONFIRMATION_RESPONSE:
        raise ContractError("CONTENT_NOT_CONFIRMED", "confirmation response is not the exact required phrase")
    _validate_utc(record["confirmed_at"], "confirmed_at")
    if record["manifest_sha256"] != manifest_sha256:
        raise ContractError("CONTENT_NOT_CONFIRMED", "confirmation manifest SHA-256 does not match current manifest")


def validate_word_permission_record(
    record: Mapping[str, Any],
    *,
    run_id: str,
    artifact_id: str,
) -> None:
    """Validate the one-task permission required before starting Word COM."""

    required = {"run_id", "artifact_id", "actor", "user_response", "granted_at", "scope"}
    if set(record) != required:
        raise ContractError("PERMISSION_DENIED", "Word permission record schema mismatch", phase="native_permission")
    if record["run_id"] != run_id or record["artifact_id"] != artifact_id:
        raise ContractError("PERMISSION_DENIED", "Word permission is bound to another run or artifact", phase="native_permission")
    if not isinstance(record["actor"], str) or not record["actor"].startswith("user:"):
        raise ContractError("PERMISSION_DENIED", "Word permission actor must be a user identity", phase="native_permission")
    if record["user_response"] != WORD_PERMISSION_RESPONSE or record["scope"] != "task_run":
        raise ContractError("PERMISSION_DENIED", "Word permission response/scope is invalid", phase="native_permission")
    _validate_utc(record["granted_at"], "granted_at")


def validate_baseline_manifest(
    baseline: Mapping[str, Any],
    *,
    template_id: str,
    template_sha256: str,
    word_major_version: str,
) -> None:
    """Validate an approved raster baseline before NATIVE_RENDER_PASS."""

    required = {
        "baseline_version",
        "template_id",
        "template_sha256",
        "word_major_version",
        "poppler_version",
        "raster_command",
        "page_count",
        "pages_sha256",
        "baseline_approver",
        "approved_at",
        "status",
    }
    if set(baseline) != required:
        raise ContractError("UNVERIFIED_GATE", "raster baseline manifest schema mismatch", phase="native_baseline")
    if baseline["template_id"] != template_id or baseline["template_sha256"] != template_sha256:
        raise ContractError("UNVERIFIED_GATE", "raster baseline template identity mismatch", phase="native_baseline")
    if baseline["word_major_version"] != word_major_version or word_major_version not in WORD_MAJOR_VERSIONS:
        raise ContractError("UNVERIFIED_GATE", "raster baseline Word major version is not supported", phase="native_baseline")
    if not isinstance(baseline["poppler_version"], str) or not baseline["poppler_version"]:
        raise ContractError("UNVERIFIED_GATE", "raster baseline lacks a pinned Poppler version", phase="native_baseline")
    expected_command = ["pdftoppm", "-r", "150", "-png", "-aa", "yes", "-aaVector", "yes"]
    if baseline["raster_command"] != expected_command:
        raise ContractError("UNVERIFIED_GATE", "raster baseline command is not the fixed PNG/150-DPI command", phase="native_baseline")
    page_count = baseline["page_count"]
    if not isinstance(page_count, int) or page_count < 1:
        raise ContractError("UNVERIFIED_GATE", "raster baseline page_count is invalid", phase="native_baseline")
    pages = baseline["pages_sha256"]
    if not isinstance(pages, list) or len(pages) != page_count or not all(
        isinstance(value, str) and SHA_RE.fullmatch(value) for value in pages
    ):
        raise ContractError("UNVERIFIED_GATE", "raster baseline page hashes are incomplete", phase="native_baseline")
    if not isinstance(baseline["baseline_approver"], str) or not baseline["baseline_approver"].startswith("user:"):
        raise ContractError("PERMISSION_DENIED", "baseline approver must be a user identity", phase="native_baseline")
    _validate_utc(baseline["approved_at"], "approved_at")
    if baseline["status"] not in {"approved", "deprecated"}:
        raise ContractError("UNVERIFIED_GATE", "raster baseline status is invalid", phase="native_baseline")
    if baseline["status"] != "approved":
        raise ContractError("UNVERIFIED_GATE", "raster baseline is deprecated", phase="native_baseline")


def validate_document_acceptance_items(items: Any) -> None:
    """Validate the authoritative document-level Word acceptance checklist."""

    if not isinstance(items, list) or len(items) != len(DOCUMENT_ACCEPTANCE_ITEMS):
        raise ContractError(
            "UNVERIFIED_GATE",
            "document acceptance checklist must contain exactly seven items",
            phase="document_acceptance",
        )
    expected = set(DOCUMENT_ACCEPTANCE_ITEMS)
    seen: set[str] = set()
    required = {"id", "owner_layer", "result", "severity", "baseline", "comparison", "evidence_path"}
    for item in items:
        if not isinstance(item, dict) or set(item) != required:
            raise ContractError(
                "UNVERIFIED_GATE",
                "document acceptance item schema mismatch",
                phase="document_acceptance",
            )
        item_id = item["id"]
        if item_id not in expected or item_id in seen:
            raise ContractError(
                "UNVERIFIED_GATE",
                f"unknown or duplicate document acceptance item: {item_id}",
                phase="document_acceptance",
            )
        seen.add(item_id)
        if item["owner_layer"] != DOCUMENT_ITEM_LAYERS[item_id]:
            raise ContractError(
                "UNVERIFIED_GATE",
                f"document acceptance item {item_id} is assigned to the wrong layer",
                phase="document_acceptance",
            )
        if item["result"] not in {"PASS", "WARN", "FAIL"}:
            raise ContractError(
                "UNVERIFIED_GATE",
                f"document acceptance item {item_id} has an invalid result",
                phase="document_acceptance",
            )
        if item["severity"] not in {"hard_block", "warning"}:
            raise ContractError(
                "UNVERIFIED_GATE",
                f"document acceptance item {item_id} has an invalid severity",
                phase="document_acceptance",
            )
        if not isinstance(item["baseline"], str) or not item["baseline"]:
            raise ContractError("UNVERIFIED_GATE", f"document acceptance item {item_id} lacks a baseline", phase="document_acceptance")
        if not isinstance(item["comparison"], str) or not item["comparison"]:
            raise ContractError("UNVERIFIED_GATE", f"document acceptance item {item_id} lacks a comparison rule", phase="document_acceptance")
        evidence = item["evidence_path"]
        if evidence is not None and (not isinstance(evidence, str) or not evidence):
            raise ContractError("UNVERIFIED_GATE", f"document acceptance item {item_id} has an invalid evidence path", phase="document_acceptance")
        if item["result"] == "FAIL" or (item["result"] == "WARN" and item["severity"] != "warning"):
            raise ContractError(
                "UNVERIFIED_GATE",
                f"document acceptance item {item_id} is not releasable",
                phase="document_acceptance",
            )
    if seen != expected:
        raise ContractError("UNVERIFIED_GATE", "document acceptance checklist is incomplete", phase="document_acceptance")


def validate_acceptance_report(
    report: Mapping[str, Any],
    *,
    artifact_id: str,
    revision: int,
    word_path: str,
    word_sha256: str,
) -> dict[str, Any]:
    """Validate a DOCX acceptance report before it is attached to workflow state."""

    required = {"report_version", "artifact_id", "revision", "word_path", "word_sha256", "layers", "items", "overall_verdict", "warnings"}
    if not isinstance(report, Mapping) or set(report) != required:
        raise ContractError("UNVERIFIED_GATE", "DOCX acceptance report schema mismatch", phase="docx_acceptance")
    if report["report_version"] != "1" or report["artifact_id"] != artifact_id or report["revision"] != revision:
        raise ContractError("UNVERIFIED_GATE", "DOCX acceptance report identity mismatch", phase="docx_acceptance")
    if report["word_path"] != word_path or report["word_sha256"] != word_sha256:
        raise ContractError("SOURCE_MUTATED", "DOCX acceptance report does not match generated Word", phase="docx_acceptance")
    layers = report["layers"]
    if not isinstance(layers, list) or len(layers) != len(LAYERS):
        raise ContractError("UNVERIFIED_GATE", "DOCX acceptance report must list four layers", phase="docx_acceptance")
    for expected, layer in zip(LAYERS, layers):
        if not isinstance(layer, Mapping) or set(layer) != {"id", "status", "evidence_path"} or layer["id"] != expected:
            raise ContractError("UNVERIFIED_GATE", "DOCX acceptance layers are not ordered or complete", phase="docx_acceptance")
        if layer["status"] not in ACCEPTANCE_VALUES:
            raise ContractError("UNVERIFIED_GATE", f"invalid DOCX acceptance status for {expected}", phase="docx_acceptance")
        if layer["status"] == "PASS" and (not isinstance(layer["evidence_path"], str) or not layer["evidence_path"]):
            raise ContractError("UNVERIFIED_GATE", f"{expected}=PASS requires evidence_path", phase="docx_acceptance")
    validate_document_acceptance_items(report["items"])
    warnings = report["warnings"]
    if not isinstance(warnings, list) or not all(isinstance(value, str) and value for value in warnings):
        raise ContractError("UNVERIFIED_GATE", "DOCX acceptance warnings must be a string array", phase="docx_acceptance")
    verdict = report["overall_verdict"]
    if verdict not in {"PASS", "PASS_WITH_WARNINGS"}:
        raise ContractError("UNVERIFIED_GATE", "DOCX acceptance report is not releasable", phase="docx_acceptance")
    if any(layer["status"] != "PASS" for layer in layers):
        raise ContractError("UNVERIFIED_GATE", "all four DOCX acceptance layers must pass", phase="docx_acceptance")
    return {"warnings": list(warnings), "overall_verdict": verdict}


def confirm_content(
    manifest_path: str | Path,
    *,
    project_root: str | Path,
    actor: str,
    user_response: str,
) -> dict[str, Any]:
    """Record one exact, current-task confirmation and update the manifest."""

    if not isinstance(actor, str) or not actor.startswith("user:"):
        raise ContractError("PERMISSION_DENIED", "content confirmation requires actor=user:<slug>")
    if user_response != CONFIRMATION_RESPONSE:
        raise ContractError("CONTENT_NOT_CONFIRMED", "the exact confirmation phrase was not provided")
    context = validate_manifest(manifest_path, project_root=project_root)
    manifest = dict(context["manifest"])
    validate_export_readiness({**manifest, "content_confirmed": True, "confirmed_at": utc_now()})
    manifest["content_confirmed"] = True
    manifest["confirmed_at"] = utc_now()
    confirmation_relative = (
        f"deliverables/confirmations/{manifest['artifact_id']}.r{manifest['revision']}.confirmation.json"
    )
    manifest["evidence_paths"]["confirmation"] = confirmation_relative
    manifest_bytes = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    manifest_sha = sha256_bytes(manifest_bytes)
    write_json_atomic(context["manifest_path"], manifest)
    confirmation = {
        "contract_version": CONTRACT_VERSION,
        "artifact_id": manifest["artifact_id"],
        "revision": manifest["revision"],
        "actor": actor,
        "user_response": user_response,
        "confirmed_at": manifest["confirmed_at"],
        "manifest_sha256": manifest_sha,
        "scope": "task_revision",
    }
    confirmation_path = context["project_root"] / Path(*PurePosixPath(confirmation_relative).parts)
    write_json_atomic(confirmation_path, confirmation)
    return {"manifest": context["manifest_path"], "confirmation": confirmation_path, "manifest_sha256": manifest_sha}


def check_output_collision(
    manifest: Mapping[str, Any],
    *,
    project_root: str | Path,
) -> dict[str, Any]:
    """Check the output path without ever overwriting an existing DOCX."""

    output = _resolve_project_path(Path(project_root).resolve(), manifest.get("output_docx"), "output_docx")
    assert output is not None
    if not output.exists():
        return {"reused": False, "output_path": output, "output_sha256": None}
    if not output.is_file() or output.is_symlink():
        raise ContractError("OUTPUT_COLLISION", "output path exists but is not a regular file")
    expected = manifest.get("output_sha256")
    actual = sha256_file(output)
    if not isinstance(expected, str) or expected != actual:
        raise ContractError("OUTPUT_COLLISION", "existing output does not match the manifest; new revision/path required")
    return {"reused": True, "output_path": output, "output_sha256": actual}


def validate_docx_package(path: str | Path) -> dict[str, Any]:
    """Perform the package-level portion of STATIC_PASS without repairing input."""

    candidate = Path(path)
    _require_file(candidate, "output_docx", missing_code="STATIC_VALIDATION_FAILED")
    try:
        with zipfile.ZipFile(candidate, "r") as package:
            bad_entry = package.testzip()
            if bad_entry is not None:
                raise ContractError("STATIC_VALIDATION_FAILED", f"DOCX ZIP entry is corrupt: {bad_entry}")
            names = set(package.namelist())
            required = {"[Content_Types].xml", "word/document.xml", "word/styles.xml"}
            missing = sorted(required - names)
            if missing:
                raise ContractError("STATIC_VALIDATION_FAILED", f"DOCX package is missing: {missing}")
            for name in sorted(name for name in names if name.endswith(".xml")):
                try:
                    ElementTree.fromstring(package.read(name))
                except (ElementTree.ParseError, KeyError) as exc:
                    raise ContractError("STATIC_VALIDATION_FAILED", f"invalid XML in {name}: {exc}") from exc
            return {"status": "PASS", "entries": len(names), "bytes": candidate.stat().st_size}
    except zipfile.BadZipFile as exc:
        raise ContractError("STATIC_VALIDATION_FAILED", f"DOCX is not a valid ZIP package: {exc}") from exc


def acceptance_from_gate(layer: str, result: Mapping[str, Any]) -> str:
    """Map an independent gate result to the manifest acceptance vocabulary."""

    if layer not in LAYERS:
        raise _contract_error(f"unknown acceptance layer: {layer}")
    status = result.get("status")
    if status == "PASS":
        return "PASS"
    if status == "APP_UNAVAILABLE":
        return "ENV_UNVERIFIED"
    if status in {"UNSAFE_PROCESS", "UNVERIFIED", "NOT_RUN", None}:
        return "UNVERIFIED"
    if status in {"FAIL_OPEN", "FAIL_RENDER", "FAIL"}:
        return "FAIL"
    return "UNVERIFIED"


def aggregate_acceptance(acceptance: Mapping[str, Any]) -> str:
    """Collapse four gate layers without treating an incomplete run as delivered."""

    if not isinstance(acceptance, Mapping) or set(acceptance) != set(LAYERS):
        raise _contract_error("acceptance must contain exactly the four delivery layers")
    values = [acceptance[layer] for layer in LAYERS]
    if any(value not in ACCEPTANCE_VALUES for value in values):
        raise _contract_error("acceptance has an invalid status")
    if all(value == "PASS" for value in values):
        return "PASS"
    if "FAIL" in values:
        return "FAIL"
    if "UNVERIFIED" in values or "NOT_RUN" in values:
        return "UNVERIFIED"
    if "ENV_UNVERIFIED" in values:
        return "ENV_UNVERIFIED"
    raise _contract_error("acceptance aggregate could not be determined")


def select_primary_failure(codes: Iterable[str]) -> str | None:
    values = [code for code in codes if code in FAILURE_CODES]
    for code in FAILURE_PRIORITY:
        if code in values:
            return code
    return values[0] if values else None


def validate_manual_checklist(
    checklist: Mapping[str, Any],
    *,
    page_count: int,
    project_root: str | Path | None = None,
) -> None:
    required = {
        "checklist_version",
        "artifact_id",
        "revision",
        "reviewer_id",
        "reviewed_at",
        "pages",
        "document_items",
        "overall_pass",
    }
    if set(checklist) != required or checklist["checklist_version"] != "1":
        raise ContractError("UNVERIFIED_GATE", "manual-inspection-checklist-v1 schema mismatch")
    if not isinstance(checklist["artifact_id"], str) or not SLUG_RE.fullmatch(checklist["artifact_id"]):
        raise ContractError("UNVERIFIED_GATE", "manual checklist artifact_id is invalid")
    if not isinstance(checklist["revision"], int) or checklist["revision"] < 1:
        raise ContractError("UNVERIFIED_GATE", "manual checklist revision is invalid")
    if not isinstance(checklist["reviewer_id"], str) or not checklist["reviewer_id"].startswith("user:"):
        raise ContractError("UNVERIFIED_GATE", "manual checklist reviewer_id must be a user identity")
    _validate_utc(checklist["reviewed_at"], "reviewed_at")
    pages = checklist["pages"]
    if not isinstance(pages, list) or len(pages) != page_count:
        raise ContractError("UNVERIFIED_GATE", "manual checklist must cover every rendered page")
    validate_document_acceptance_items(checklist["document_items"])
    required_page_fields = {
        "page_num",
        "no_cropping",
        "no_overlap",
        "no_missing_chars",
        "no_formula_table_breaks",
        "no_pagination_anomalies",
        "notes",
        "evidence_screenshot",
    }
    for expected, page in enumerate(pages, 1):
        if not isinstance(page, dict) or set(page) != required_page_fields or page["page_num"] != expected:
            raise ContractError("UNVERIFIED_GATE", "manual checklist page numbers/fields are not continuous")
        for field in required_page_fields - {"page_num", "notes", "evidence_screenshot"}:
            if page[field] is not True:
                raise ContractError("UNVERIFIED_GATE", f"manual checklist page {expected} did not pass {field}")
        if not isinstance(page["notes"], str):
            raise ContractError("UNVERIFIED_GATE", "manual checklist notes must be a string")
        screenshot = page["evidence_screenshot"]
        if screenshot is not None and (not isinstance(screenshot, str) or not screenshot):
            raise ContractError("UNVERIFIED_GATE", "evidence_screenshot must be a project-relative path or null")
        if screenshot is not None and project_root is not None:
            screenshot_path = _resolve_project_path(
                Path(project_root).resolve(), screenshot, f"pages[{expected}].evidence_screenshot"
            )
            assert screenshot_path is not None
            _require_file(screenshot_path, f"pages[{expected}].evidence_screenshot")
    if checklist["overall_pass"] is not True:
        raise ContractError("UNVERIFIED_GATE", "manual checklist overall_pass must be true")


def _load_state(project_root: Path, state_path: str) -> tuple[Path, dict[str, Any]]:
    path = _resolve_project_path(project_root, state_path, "evidence_paths.manual_review_state")
    assert path is not None
    _, state = _load_json(path, label="manual review state")
    return path, state


def submit_manual_review(
    manifest_path: str | Path,
    checklist_path: str | Path,
    *,
    project_root: str | Path,
) -> dict[str, Any]:
    """Validate and atomically submit the same-run manual page review."""

    context = validate_manifest(manifest_path, project_root=project_root)
    manifest = dict(context["manifest"])
    state_rel = manifest["evidence_paths"].get("manual_review_state")
    state_values = _path_values(state_rel)
    if len(state_values) != 1:
        raise ContractError("UNVERIFIED_GATE", "manifest must identify one manual_review_state")
    state_path, state = _load_state(context["project_root"], state_values[0])
    _, checklist = _load_json(Path(checklist_path).resolve(), label="manual checklist")
    page_count = state.get("page_count")
    if not isinstance(page_count, int) or page_count < 1:
        raise ContractError("UNVERIFIED_GATE", "manual review state has no valid page_count")
    if state.get("artifact_id") != manifest["artifact_id"] or state.get("revision") != manifest["revision"]:
        raise ContractError("UNVERIFIED_GATE", "manual review state does not match manifest")
    if state.get("status") != "awaiting_manual_review":
        raise ContractError("UNVERIFIED_GATE", "manual review is not awaiting this submission")
    validate_manual_checklist(checklist, page_count=page_count, project_root=context["project_root"])
    if checklist["artifact_id"] != manifest["artifact_id"] or checklist["revision"] != manifest["revision"]:
        raise ContractError("UNVERIFIED_GATE", "manual checklist does not match manifest")
    lock_rel = state.get("lock_path")
    if not isinstance(lock_rel, str):
        raise ContractError("UNVERIFIED_GATE", "manual review state has no lock_path")
    lock_path = _resolve_project_path(context["project_root"], lock_rel, "manual review lock")
    assert lock_path is not None
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise ContractError("UNVERIFIED_GATE", "manual review lock is held by another process", phase="manual_review_lock") from exc
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            json.dump({"run_id": state.get("run_id"), "pid": os.getpid(), "acquired_at": utc_now()}, stream, ensure_ascii=False)
            stream.write("\n")
        state["status"] = "manual_review_passed"
        state["updated_at"] = utc_now()
        write_json_atomic(state_path, state)
        manifest["acceptance"]["NATIVE_RENDER_PASS"] = "PASS"
        manifest["evidence_paths"]["NATIVE_RENDER_PASS"] = [str(Path(checklist_path).resolve().relative_to(context["project_root"]).as_posix())]
        write_json_atomic(context["manifest_path"], manifest)
        return {"status": "manual_review_passed", "manifest": context["manifest_path"], "state": state_path}
    finally:
        lock_path.unlink(missing_ok=True)


def cleanup_failure_evidence(
    temp_root: str | Path,
    *,
    now: _dt.datetime | None = None,
    retention_days: int = 7,
    active_paths: Iterable[str | Path] = (),
) -> dict[str, Any]:
    """Remove only old, unlocked failure run directories under the temp root."""

    root = Path(temp_root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    current = now or _dt.datetime.now(_dt.timezone.utc)
    cutoff = current.timestamp() - retention_days * 86400
    active = {str(Path(item).resolve()) for item in active_paths}
    removed: list[str] = []
    skipped: list[str] = []
    for candidate in root.glob("docx-gate_*"):
        if not candidate.is_dir() or str(candidate.resolve()) in active:
            continue
        if (candidate / ".lock").exists() or candidate.stat().st_mtime >= cutoff:
            skipped.append(str(candidate))
            continue
        try:
            shutil.rmtree(candidate)
        except OSError as exc:
            raise ContractError("CLEANUP_FAILED", f"could not clean failure evidence {candidate}: {exc}") from exc
        removed.append(str(candidate))
    log = root / "cleanup.log"
    log.write_text(json.dumps({"removed": removed, "skipped": skipped}, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    return {"removed": removed, "skipped": skipped, "log": log}


def _print_result(value: Mapping[str, Any]) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Markdown-first DOCX handoff contract")
    subparsers = parser.add_subparsers(dest="operation", required=True)
    validate = subparsers.add_parser("validate-manifest")
    validate.add_argument("--manifest", required=True)
    validate.add_argument("--project-root", required=True)
    validate.add_argument("--preview", action="store_true")
    confirm = subparsers.add_parser("confirm-content")
    confirm.add_argument("--manifest", required=True)
    confirm.add_argument("--project-root", required=True)
    confirm.add_argument("--actor", required=True)
    confirm.add_argument("--response", required=True)
    review = subparsers.add_parser("review-manual")
    review_sub = review.add_subparsers(dest="review_operation", required=True)
    submit = review_sub.add_parser("submit")
    submit.add_argument("--manifest", required=True)
    submit.add_argument("--checklist", required=True)
    submit.add_argument("--project-root", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.operation == "validate-manifest":
            context = validate_manifest(args.manifest, project_root=args.project_root)
            collision = check_output_collision(context["manifest"], project_root=context["project_root"])
            result = validate_export_readiness(context["manifest"], preview=args.preview)
            result.update(
                {
                    "manifest": str(context["manifest_path"]),
                    "source": str(context["source_path"]),
                    "output": collision,
                }
            )
        elif args.operation == "confirm-content":
            result = confirm_content(
                args.manifest,
                project_root=args.project_root,
                actor=args.actor,
                user_response=args.response,
            )
        elif args.operation == "review-manual" and args.review_operation == "submit":
            result = submit_manual_review(args.manifest, args.checklist, project_root=args.project_root)
        else:
            raise _contract_error("unsupported operation")
    except ContractError as exc:
        _print_result(exc.as_dict())
        return 2
    _print_result(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
