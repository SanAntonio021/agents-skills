#!/usr/bin/env python3
"""Fail-closed state machine for Markdown -> DOCX -> confirmed Word -> PDF."""

from __future__ import annotations

import copy
import datetime as _dt
import hashlib
import re
from pathlib import Path
from typing import Any, Mapping


STATES = (
    "DRAFT",
    "CONTENT_FROZEN",
    "DOCX_GENERATED",
    "DOCX_ACCEPTED",
    "WORD_CONFIRMED",
    "PDF_RELEASED",
)
LAYERS = ("STATIC_PASS", "LO_RENDER_PASS", "NATIVE_OPEN_PASS", "NATIVE_RENDER_PASS")
ITEMS = (
    "fonts_and_fallback",
    "paragraph_formatting",
    "table_formatting",
    "header_footer_geometry",
    "pagination",
    "word_native_open",
    "word_native_render",
)
ITEM_LAYERS = {
    "fonts_and_fallback": "STATIC_PASS",
    "paragraph_formatting": "STATIC_PASS",
    "table_formatting": "STATIC_PASS",
    "header_footer_geometry": "LO_RENDER_PASS",
    "pagination": "LO_RENDER_PASS",
    "word_native_open": "NATIVE_OPEN_PASS",
    "word_native_render": "NATIVE_RENDER_PASS",
}
CONFIRM_CONTENT = "确认内容并导出 Word"
WORD_CONFIRMATIONS = {
    "Word 可以作为最终版本",
    "确认这个 Word",
    "Word 没问题，可以提交",
}
SHA_RE = re.compile(r"[0-9a-f]{64}\Z")
SLUG_RE = re.compile(r"[a-z0-9][a-z0-9._-]{2,127}\Z")


class WorkflowError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message

    def as_dict(self) -> dict[str, str]:
        return {"failure_code": self.code, "failure_detail": self.message}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def utc_now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sha(value: Any, field: str) -> str:
    if not isinstance(value, str) or not SHA_RE.fullmatch(value):
        raise WorkflowError("WORKFLOW_SCHEMA_INVALID", f"{field} must be a lowercase SHA-256")
    return value


def _slug(value: Any, field: str) -> str:
    if not isinstance(value, str) or not SLUG_RE.fullmatch(value):
        raise WorkflowError("WORKFLOW_SCHEMA_INVALID", f"{field} must be a lowercase slug")
    return value


def new_state(*, artifact_id: str, revision: int, source_markdown: str, source_sha256: str, now: str | None = None) -> dict[str, Any]:
    _slug(artifact_id, "artifact_id")
    if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
        raise WorkflowError("WORKFLOW_SCHEMA_INVALID", "revision must be a positive integer")
    _sha(source_sha256, "source_sha256")
    return {
        "schema_version": "1",
        "artifact_id": artifact_id,
        "revision": revision,
        "source_markdown": source_markdown,
        "source_sha256": source_sha256,
        "state": "DRAFT",
        "created_at": now or utc_now(),
        "updated_at": now or utc_now(),
        "content_confirmation": None,
        "docx": None,
        "word_confirmation": None,
        "pdf": None,
        "invalidation": None,
    }


def validate_state(state: Mapping[str, Any]) -> None:
    required = {
        "schema_version", "artifact_id", "revision", "source_markdown", "source_sha256", "state",
        "created_at", "updated_at", "content_confirmation", "docx", "word_confirmation", "pdf", "invalidation",
    }
    if not isinstance(state, Mapping) or set(state) != required:
        raise WorkflowError("WORKFLOW_SCHEMA_INVALID", "workflow state schema mismatch")
    if state["schema_version"] != "1" or state["state"] not in STATES:
        raise WorkflowError("WORKFLOW_SCHEMA_INVALID", "unsupported workflow state")
    _slug(state["artifact_id"], "artifact_id")
    _sha(state["source_sha256"], "source_sha256")
    if not isinstance(state["revision"], int) or isinstance(state["revision"], bool) or state["revision"] < 1:
        raise WorkflowError("WORKFLOW_SCHEMA_INVALID", "revision must be a positive integer")


def _transition(state: dict[str, Any], expected: str, target: str, now: str | None) -> None:
    validate_state(state)
    if state["state"] != expected:
        raise WorkflowError("INVALID_TRANSITION", f"expected {expected}, current state is {state['state']}")
    state["state"] = target
    state["updated_at"] = now or utc_now()
    state["invalidation"] = None


def freeze_content(state: dict[str, Any], *, source_bytes: bytes, actor: str, user_response: str, now: str | None = None) -> dict[str, Any]:
    validate_state(state)
    if user_response != CONFIRM_CONTENT:
        raise WorkflowError("CONTENT_NOT_CONFIRMED", "exact content confirmation is required")
    if not isinstance(actor, str) or not actor.startswith("user:"):
        raise WorkflowError("PERMISSION_DENIED", "content confirmation actor must be user:<slug>")
    if sha256_bytes(source_bytes) != state["source_sha256"]:
        raise WorkflowError("SOURCE_MUTATED", "current Markdown does not match the recorded source hash")
    _transition(state, "DRAFT", "CONTENT_FROZEN", now)
    state["content_confirmation"] = {
        "actor": actor,
        "user_response": user_response,
        "confirmed_at": state["updated_at"],
        "source_sha256": state["source_sha256"],
    }
    return state


def record_docx_generated(
    state: dict[str, Any],
    *,
    manifest_path: str,
    template_path: str,
    template_sha256: str,
    word_path: str,
    word_sha256: str,
    now: str | None = None,
) -> dict[str, Any]:
    validate_state(state)
    if state["state"] != "CONTENT_FROZEN":
        raise WorkflowError("INVALID_TRANSITION", f"expected CONTENT_FROZEN, current state is {state['state']}")
    _sha(template_sha256, "template_sha256")
    _sha(word_sha256, "word_sha256")
    _transition(state, "CONTENT_FROZEN", "DOCX_GENERATED", now)
    state["docx"] = {
        "manifest_path": manifest_path,
        "template_path": template_path,
        "template_sha256": template_sha256,
        "word_path": word_path,
        "word_sha256": word_sha256,
        "generated_at": state["updated_at"],
        "acceptance_report": None,
    }
    return state


def _validate_report(report: Mapping[str, Any], state: Mapping[str, Any]) -> list[str]:
    required = {"report_version", "artifact_id", "revision", "word_path", "word_sha256", "layers", "items", "overall_verdict", "warnings"}
    if not isinstance(report, Mapping) or set(report) != required:
        raise WorkflowError("DOCX_ACCEPTANCE_UNVERIFIED", "DOCX acceptance report schema mismatch")
    docx = state["docx"]
    if report["report_version"] != "1" or report["artifact_id"] != state["artifact_id"] or report["revision"] != state["revision"]:
        raise WorkflowError("DOCX_ACCEPTANCE_UNVERIFIED", "DOCX acceptance report identity mismatch")
    if report["word_path"] != docx["word_path"] or report["word_sha256"] != docx["word_sha256"]:
        raise WorkflowError("SOURCE_MUTATED", "DOCX acceptance report does not match generated Word")
    layers = report["layers"]
    if not isinstance(layers, list) or len(layers) != 4:
        raise WorkflowError("DOCX_ACCEPTANCE_UNVERIFIED", "DOCX acceptance report must contain four ordered layers")
    for expected, layer in zip(LAYERS, layers):
        if not isinstance(layer, Mapping) or set(layer) != {"id", "status", "evidence_path"} or layer.get("id") != expected:
            raise WorkflowError("DOCX_ACCEPTANCE_UNVERIFIED", f"invalid acceptance layer {expected}")
        if layer["status"] not in {"PASS", "FAIL", "UNVERIFIED", "ENV_UNVERIFIED", "NOT_RUN"}:
            raise WorkflowError("DOCX_ACCEPTANCE_UNVERIFIED", f"invalid acceptance status for {expected}")
        if layer["status"] == "PASS" and (not isinstance(layer["evidence_path"], str) or not layer["evidence_path"]):
            raise WorkflowError("DOCX_ACCEPTANCE_UNVERIFIED", f"{expected}=PASS requires evidence_path")
        if layer["status"] != "PASS":
            raise WorkflowError("DOCX_ACCEPTANCE_UNVERIFIED", f"{expected} did not pass")
    items = report["items"]
    if not isinstance(items, list) or {item.get("id") for item in items if isinstance(item, Mapping)} != set(ITEMS) or len(items) != len(ITEMS):
        raise WorkflowError("DOCX_ACCEPTANCE_UNVERIFIED", "DOCX acceptance report does not cover all seven document items")
    if not isinstance(report["warnings"], list) or not all(isinstance(w, str) and w for w in report["warnings"]):
        raise WorkflowError("DOCX_ACCEPTANCE_UNVERIFIED", "DOCX acceptance warnings must be non-empty strings")
    warnings: list[str] = list(report["warnings"])
    for item in items:
        if not isinstance(item, Mapping) or set(item) != {"id", "owner_layer", "result", "severity", "baseline", "comparison", "evidence_path"}:
            raise WorkflowError("DOCX_ACCEPTANCE_UNVERIFIED", "document acceptance item schema mismatch")
        item_id = item["id"]
        if item.get("owner_layer") != ITEM_LAYERS.get(item_id):
            raise WorkflowError("DOCX_ACCEPTANCE_UNVERIFIED", "document acceptance item owner layer is invalid")
        if item["result"] not in {"PASS", "WARN", "FAIL"}:
            raise WorkflowError("DOCX_ACCEPTANCE_UNVERIFIED", f"document item {item_id} has an invalid result")
        if item["severity"] not in {"hard_block", "warning"}:
            raise WorkflowError("DOCX_ACCEPTANCE_UNVERIFIED", f"document item {item_id} has an invalid severity")
        if not isinstance(item["baseline"], str) or not item["baseline"]:
            raise WorkflowError("DOCX_ACCEPTANCE_UNVERIFIED", f"document item {item_id} lacks a baseline")
        if not isinstance(item["comparison"], str) or not item["comparison"]:
            raise WorkflowError("DOCX_ACCEPTANCE_UNVERIFIED", f"document item {item_id} lacks a comparison rule")
        evidence = item["evidence_path"]
        if evidence is not None and (not isinstance(evidence, str) or not evidence):
            raise WorkflowError("DOCX_ACCEPTANCE_UNVERIFIED", f"document item {item_id} has an invalid evidence path")
        result = item.get("result")
        severity = item.get("severity")
        if result == "FAIL" or (result == "WARN" and severity != "warning") or result not in {"PASS", "WARN"}:
            raise WorkflowError("DOCX_ACCEPTANCE_UNVERIFIED", f"document item {item.get('id')} is not releasable")
        if result == "WARN":
            warnings.append(f"{item['id']}: {item.get('comparison', 'warning')}")
    verdict = report["overall_verdict"]
    if verdict not in {"PASS", "PASS_WITH_WARNINGS"}:
        raise WorkflowError("DOCX_ACCEPTANCE_UNVERIFIED", "DOCX acceptance report verdict is not releasable")
    return warnings


def accept_docx(state: dict[str, Any], *, report_path: str, report_sha256: str, report: Mapping[str, Any], now: str | None = None) -> dict[str, Any]:
    validate_state(state)
    if state["state"] != "DOCX_GENERATED":
        raise WorkflowError("INVALID_TRANSITION", f"expected DOCX_GENERATED, current state is {state['state']}")
    _sha(report_sha256, "report_sha256")
    warnings = _validate_report(report, state)
    _transition(state, "DOCX_GENERATED", "DOCX_ACCEPTED", now)
    state["docx"]["acceptance_report"] = {
        "path": report_path,
        "sha256": report_sha256,
        "accepted_at": state["updated_at"],
        "warnings": warnings,
    }
    return state


def confirm_word(state: dict[str, Any], *, actor: str, user_response: str, warnings_acknowledged: bool = False, now: str | None = None) -> dict[str, Any]:
    validate_state(state)
    if state["state"] != "DOCX_ACCEPTED":
        raise WorkflowError("INVALID_TRANSITION", f"expected DOCX_ACCEPTED, current state is {state['state']}")
    if not isinstance(actor, str) or not actor.startswith("user:"):
        raise WorkflowError("PERMISSION_DENIED", "Word confirmation actor must be user:<slug>")
    if user_response not in WORD_CONFIRMATIONS:
        raise WorkflowError("WORD_NOT_CONFIRMED", "a recognized Word final-version confirmation is required")
    warnings = state["docx"]["acceptance_report"].get("warnings", [])
    if warnings and not warnings_acknowledged:
        raise WorkflowError("WARNING_ACK_REQUIRED", "acceptance warnings must be shown and acknowledged")
    _transition(state, "DOCX_ACCEPTED", "WORD_CONFIRMED", now)
    state["word_confirmation"] = {
        "actor": actor,
        "user_response": user_response,
        "confirmed_at": state["updated_at"],
        "word_path": state["docx"]["word_path"],
        "word_sha256": state["docx"]["word_sha256"],
        "warnings_acknowledged": bool(warnings_acknowledged),
    }
    return state


def release_pdf(state: dict[str, Any], *, pdf_path: str, pdf_sha256: str, word_path: str, word_sha256: str, now: str | None = None) -> dict[str, Any]:
    validate_state(state)
    if state["state"] != "WORD_CONFIRMED":
        raise WorkflowError("INVALID_TRANSITION", f"expected WORD_CONFIRMED, current state is {state['state']}")
    _sha(pdf_sha256, "pdf_sha256")
    confirmation = state["word_confirmation"]
    if word_path != confirmation["word_path"] or word_sha256 != confirmation["word_sha256"]:
        raise WorkflowError("SOURCE_MUTATED", "PDF source Word does not match confirmed Word")
    _transition(state, "WORD_CONFIRMED", "PDF_RELEASED", now)
    state["pdf"] = {
        "path": pdf_path,
        "sha256": pdf_sha256,
        "source_word_path": word_path,
        "source_word_sha256": word_sha256,
        "released_at": state["updated_at"],
    }
    return state


def invalidate_if_changed(state: dict[str, Any], *, source_sha256: str | None = None, word_sha256: str | None = None, now: str | None = None) -> dict[str, Any]:
    """Invalidate downstream states when a source or generated Word fingerprint drifts."""

    validate_state(state)
    if source_sha256 is not None:
        _sha(source_sha256, "source_sha256")
    if word_sha256 is not None:
        _sha(word_sha256, "word_sha256")
    reason = None
    if source_sha256 is not None and source_sha256 != state["source_sha256"]:
        reason = "source_markdown_changed"
        state["state"] = "DRAFT"
        state["content_confirmation"] = None
        state["docx"] = None
        state["word_confirmation"] = None
        state["pdf"] = None
    elif word_sha256 is not None and state.get("docx") and word_sha256 != state["docx"]["word_sha256"]:
        reason = "generated_word_changed"
        state["state"] = "CONTENT_FROZEN"
        state["docx"] = None
        state["word_confirmation"] = None
        state["pdf"] = None
    if reason:
        state["updated_at"] = now or utc_now()
        state["invalidation"] = {"reason": reason, "at": state["updated_at"]}
    return state


def clone_state(state: Mapping[str, Any]) -> dict[str, Any]:
    validate_state(state)
    return copy.deepcopy(dict(state))
