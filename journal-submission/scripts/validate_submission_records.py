#!/usr/bin/env python3
"""Validate private author profiles and journal submission state records."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable


VALID_STAGES = {
    "preparation",
    "initial_submission",
    "editorial_check",
    "under_review",
    "decision_received",
    "revision",
    "resubmission",
    "accepted",
    "final_files",
    "copyright_fees",
    "proof",
    "published",
    "rejected",
    "withdrawn",
    "transferred",
}

LEGACY_REQUIRED_GATES = {
    "author_roles",
    "declarations",
    "reviewers",
    "final_submit",
    "open_access_fees",
    "copyright",
    "withdrawal_transfer",
}
CURRENT_REQUIRED_GATES = LEGACY_REQUIRED_GATES | {"pre_submission_review"}
REVIEW_STATUSES = {"not_run", "blocked", "pass"}
FINAL_SUBMIT_CLOSED_STATUSES = {"confirmed", "completed", "closed", "pass"}
FRESHNESS_STATUSES = {"verified", "stale", "unknown"}
INSTITUTION_MATCH_STATUSES = {"matched", "manually_entered", "not_listed"}
FILE_REQUIRED_STRING_FIELDS = (
    "path",
    "submission_name",
    "purpose",
    "sha256",
    "stage",
    "upload_status",
)
EVIDENCE_LOCATOR_FIELDS = ("path", "url", "record_id", "reference")
CONFIRMATION_RECORD_STRING_FIELDS = ("question", "user_choice", "applies_to")
PORTAL_TASK_COMPLETE_STATUSES = {"completed", "verified", "viewed"}
BLOCKER_CLOSED_STATUSES = {"closed", "resolved"}
PROTECTED_GATE_STATUSES = {
    "required",
    "pending",
    "blocked",
    "not_applicable",
    "not_required",
    "confirmed",
    "completed",
    "closed",
    "pass",
}
FINAL_SUBMIT_STATUSES = PROTECTED_GATE_STATUSES - {"not_applicable", "not_required"}

FORBIDDEN_KEYS = {
    "id_card",
    "identity_card",
    "身份证号",
    "phone",
    "phone_number",
    "手机号",
    "student_id",
    "学号",
    "staff_id",
    "employee_id",
    "工号",
    "password",
    "密码",
    "cookie",
    "session_token",
    "token",
    "biography",
    "个人经历",
    "个人介绍",
}

PROJECT_ROLE_KEYS = {
    "first_author",
    "author_order",
    "corresponding_author",
    "corresponding_authors",
    "submission_contact",
}

SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
ORCID_RE = re.compile(r"^(?:https://orcid\.org/)?\d{4}-\d{4}-\d{4}-[\dX]{4}$")


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def iter_keys(value: Any, prefix: str = "$") -> Iterable[tuple[str, str]]:
    if isinstance(value, dict):
        for key, child in value.items():
            current = f"{prefix}.{key}"
            yield key, current
            yield from iter_keys(child, current)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from iter_keys(child, f"{prefix}[{index}]")


def field_value(value: Any) -> Any:
    if isinstance(value, dict) and "value" in value:
        return value["value"]
    return value


def non_empty(value: Any) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict)):
        return bool(value)
    return value is not None


def non_empty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def is_iso_timestamp(value: Any) -> bool:
    if not non_empty_string(value):
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return True


def is_iso_date(value: Any) -> bool:
    if not non_empty_string(value):
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def validate_authors(data: Any) -> tuple[list[str], list[str], set[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    profile_ids: set[str] = set()

    if not isinstance(data, dict):
        return ["authors document must be a JSON object"], warnings, profile_ids

    if data.get("schema_version") != "1.0":
        warnings.append("authors.schema_version should remain '1.0'")
    if data.get("privacy", {}).get("scope") != "local-private":
        errors.append("authors.privacy.scope must be 'local-private'")

    for key, path in iter_keys(data):
        if key in FORBIDDEN_KEYS:
            errors.append(f"forbidden sensitive field at {path}")
        if key in PROJECT_ROLE_KEYS:
            errors.append(f"manuscript role must not be stored in global author library: {path}")

    authors = data.get("authors")
    if not isinstance(authors, list) or not authors:
        errors.append("authors.authors must be a non-empty list")
        return errors, warnings, profile_ids

    for index, author in enumerate(authors):
        base = f"authors[{index}]"
        if not isinstance(author, dict):
            errors.append(f"{base} must be an object")
            continue

        profile_id = author.get("profile_id")
        if not isinstance(profile_id, str) or not profile_id:
            errors.append(f"{base}.profile_id is required")
        elif profile_id in profile_ids:
            errors.append(f"duplicate profile_id: {profile_id}")
        else:
            profile_ids.add(profile_id)

        for name_key in ("name_zh", "given_name", "family_name"):
            if not field_value(author.get(name_key)):
                errors.append(f"{base}.{name_key} is required")

        emails = author.get("emails", [])
        if not isinstance(emails, list):
            errors.append(f"{base}.emails must be a list")
        else:
            priorities = [item.get("priority") for item in emails if isinstance(item, dict)]
            numeric = [item for item in priorities if isinstance(item, int)]
            if len(numeric) != len(priorities) or numeric != sorted(numeric) or len(set(numeric)) != len(numeric):
                errors.append(f"{base}.emails priorities must be unique ascending integers")

        orcid = field_value(author.get("orcid"))
        if orcid and not ORCID_RE.fullmatch(str(orcid)):
            errors.append(f"{base}.orcid has invalid format")

        verification = author.get("verification", {})
        if not isinstance(verification, dict) or verification.get("status") in {None, "pending"}:
            warnings.append(f"{base} remains pending verification")

    return errors, warnings, profile_ids


def validate_files(files: Any, schema_version: str) -> list[str]:
    errors: list[str] = []
    if not isinstance(files, list):
        return ["state.files must be a list"]

    for index, file_item in enumerate(files):
        base = f"state.files[{index}]"
        if not isinstance(file_item, dict):
            errors.append(f"{base} must be an object")
            continue

        if schema_version == "1.1":
            for field in FILE_REQUIRED_STRING_FIELDS:
                if not non_empty_string(file_item.get(field)):
                    errors.append(f"{base}.{field} must be a non-empty string for schema 1.1")
            if "size_bytes" not in file_item:
                errors.append(f"{base}.size_bytes is required for schema 1.1")
            if file_item.get("stage") not in VALID_STAGES:
                errors.append(f"{base}.stage must be a valid lifecycle stage")

        checksum = file_item.get("sha256")
        if checksum is not None and not SHA256_RE.fullmatch(str(checksum)):
            errors.append(f"{base}.sha256 must be 64 hexadecimal characters")
        if "size_bytes" in file_item and (
            type(file_item["size_bytes"]) is not int or file_item["size_bytes"] < 0
        ):
            errors.append(f"{base}.size_bytes must be a non-negative integer")

        provenance = file_item.get("provenance")
        if provenance is None:
            continue
        if not isinstance(provenance, dict):
            errors.append(f"{base}.provenance must be an object")
            continue

        freshness_status = provenance.get("freshness_status")
        if freshness_status is not None and freshness_status not in FRESHNESS_STATUSES:
            errors.append(
                f"{base}.provenance.freshness_status must be one of "
                + ", ".join(sorted(FRESHNESS_STATUSES))
            )

        inputs = provenance.get("inputs")
        if inputs is None:
            if freshness_status not in {None, "unknown"}:
                errors.append(f"{base}.provenance.freshness_status must be 'unknown' without inputs")
            continue
        if not isinstance(inputs, list):
            errors.append(f"{base}.provenance.inputs must be a list")
            continue
        if not inputs and freshness_status not in {None, "unknown"}:
            errors.append(f"{base}.provenance.freshness_status must be 'unknown' without inputs")

        for input_index, input_item in enumerate(inputs):
            input_base = f"{base}.provenance.inputs[{input_index}]"
            if not isinstance(input_item, dict):
                errors.append(f"{input_base} must be an object")
                continue
            if not non_empty_string(input_item.get("path")):
                errors.append(f"{input_base}.path must be a non-empty string")
            input_checksum = input_item.get("sha256")
            if not isinstance(input_checksum, str) or not SHA256_RE.fullmatch(input_checksum):
                errors.append(f"{input_base}.sha256 must be 64 hexadecimal characters")
            if "size_bytes" in input_item and (
                type(input_item["size_bytes"]) is not int or input_item["size_bytes"] < 0
            ):
                errors.append(f"{input_base}.size_bytes must be a non-negative integer")

        if freshness_status == "verified":
            if not inputs:
                errors.append(f"{base}.provenance.verified requires a non-empty input snapshot")
            if not is_iso_timestamp(provenance.get("freshness_checked_at")):
                errors.append(
                    f"{base}.provenance.freshness_checked_at must be an ISO date or datetime when verified"
                )

    return errors


def validate_confirmation_gates(
    gates: Any, schema_version: str
) -> tuple[list[str], dict[str, dict[str, Any]]]:
    errors: list[str] = []
    by_action: dict[str, dict[str, Any]] = {}

    if not isinstance(gates, list):
        return ["state.confirmation_gates must be a list"], by_action

    for index, gate in enumerate(gates):
        base = f"state.confirmation_gates[{index}]"
        if not isinstance(gate, dict):
            errors.append(f"{base} must be an object")
            continue
        action = gate.get("action")
        if not isinstance(action, str) or not action:
            errors.append(f"{base}.action is required")
            continue
        if action in by_action:
            errors.append(f"duplicate confirmation gate: {action}")
            continue
        by_action[action] = gate

    required = CURRENT_REQUIRED_GATES if schema_version == "1.1" else LEGACY_REQUIRED_GATES
    missing = sorted(required - set(by_action))
    if missing:
        errors.append("missing confirmation gates: " + ", ".join(missing))

    if schema_version == "1.1":
        for action in sorted(LEGACY_REQUIRED_GATES):
            gate = by_action.get(action, {})
            allowed_statuses = FINAL_SUBMIT_STATUSES if action == "final_submit" else PROTECTED_GATE_STATUSES
            if gate and gate.get("status") not in allowed_statuses:
                errors.append(
                    f"{action}.status must be one of " + ", ".join(sorted(allowed_statuses))
                )
            if gate.get("status") in FINAL_SUBMIT_CLOSED_STATUSES:
                for field in CONFIRMATION_RECORD_STRING_FIELDS:
                    if not non_empty_string(gate.get(field)):
                        errors.append(
                            f"{action}.{field} must be a non-empty string when the confirmation gate is closed"
                        )
                if not is_iso_timestamp(gate.get("confirmed_at")):
                    errors.append(
                        f"{action}.confirmed_at must be an ISO date or datetime when the confirmation gate is closed"
                    )

    if schema_version == "1.1" and "pre_submission_review" in by_action:
        review_gate = by_action["pre_submission_review"]
        status = review_gate.get("status")
        if status not in REVIEW_STATUSES:
            errors.append(
                "pre_submission_review.status must be one of "
                + ", ".join(sorted(REVIEW_STATUSES))
            )
        if status == "pass":
            if not is_iso_timestamp(review_gate.get("checked_at")):
                errors.append(
                    "pre_submission_review.checked_at must be an ISO date or datetime when status is pass"
                )
            evidence = review_gate.get("evidence")
            if not isinstance(evidence, list) or not evidence:
                errors.append("pre_submission_review.evidence must be a non-empty list when status is pass")
            else:
                for index, item in enumerate(evidence):
                    if not isinstance(item, dict) or not any(
                        non_empty_string(item.get(field)) for field in EVIDENCE_LOCATOR_FIELDS
                    ):
                        errors.append(
                            f"pre_submission_review.evidence[{index}] must be a locatable object"
                        )

        final_gate = by_action.get("final_submit", {})
        if final_gate.get("status") in FINAL_SUBMIT_CLOSED_STATUSES and status != "pass":
            errors.append("final_submit cannot be closed before pre_submission_review passes")

    return errors, by_action


def has_locatable_evidence(value: Any) -> bool:
    items = value if isinstance(value, list) else [value]
    return any(
        isinstance(item, dict)
        and any(non_empty_string(item.get(field)) for field in EVIDENCE_LOCATOR_FIELDS)
        for item in items
    )


def validate_final_submit_exit(
    data: dict[str, Any], gates_by_action: dict[str, dict[str, Any]]
) -> list[str]:
    final_gate = gates_by_action.get("final_submit", {})
    if final_gate.get("status") not in FINAL_SUBMIT_CLOSED_STATUSES:
        return []

    errors: list[str] = []
    platform = data.get("platform", {})
    match_status = platform.get("institution_match_status") if isinstance(platform, dict) else None
    if match_status not in INSTITUTION_MATCH_STATUSES:
        errors.append("final_submit requires a recorded institution_match_status")

    tasks = data.get("portal_tasks", [])
    if not isinstance(tasks, list):
        errors.append("state.portal_tasks must be a list")
    else:
        for index, task in enumerate(tasks):
            base = f"state.portal_tasks[{index}]"
            if not isinstance(task, dict):
                errors.append(f"{base} must be an object")
                continue
            required = task.get("required")
            if required is not None and type(required) is not bool:
                errors.append(f"{base}.required must be a boolean")
                continue
            if required is not True:
                continue
            if task.get("status") not in PORTAL_TASK_COMPLETE_STATUSES:
                errors.append(f"{base} is required but not completed")
            task_label = " ".join(
                str(task.get(field, ""))
                for field in ("task_type", "type", "name", "page")
            ).lower()
            if "proof" in task_label or "preview" in task_label:
                if not is_iso_timestamp(task.get("viewed_at")):
                    errors.append(f"{base}.viewed_at must record when required proof/preview was viewed")
                if not has_locatable_evidence(task.get("evidence")):
                    errors.append(f"{base}.evidence must locate the viewed proof/preview")

    blockers = data.get("blockers", [])
    if not isinstance(blockers, list):
        errors.append("state.blockers must be a list")
    else:
        for index, blocker in enumerate(blockers):
            status = blocker.get("status") if isinstance(blocker, dict) else None
            if status not in BLOCKER_CLOSED_STATUSES:
                errors.append(f"state.blockers[{index}] is not closed")

    return errors


def validate_state(data: Any, known_profiles: set[str] | None = None) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    if not isinstance(data, dict):
        return ["submission state must be a JSON object"], warnings

    schema_version = data.get("schema_version")
    if schema_version == "1.0":
        warnings.append(
            "submission-state schema_version 1.0 is supported for compatibility; "
            "upgrade on the next normal update"
        )
    elif schema_version != "1.1":
        errors.append(f"unsupported submission-state schema_version: {schema_version!r}")

    for key, path in iter_keys(data):
        if key in FORBIDDEN_KEYS:
            errors.append(f"forbidden sensitive field at {path}")

    lifecycle = data.get("lifecycle")
    stage = lifecycle.get("current_stage") if isinstance(lifecycle, dict) else None
    if stage not in VALID_STAGES:
        errors.append(f"invalid lifecycle.current_stage: {stage!r}")

    authors = data.get("authors", [])
    if not isinstance(authors, list):
        errors.append("state.authors must be a list")
    else:
        for index, author in enumerate(authors):
            profile_id = author.get("profile_id") if isinstance(author, dict) else None
            if not profile_id:
                errors.append(f"state.authors[{index}].profile_id is required")
            elif known_profiles is not None and profile_id not in known_profiles:
                errors.append(f"unknown author profile_id in state: {profile_id}")

    errors.extend(validate_files(data.get("files", []), schema_version))

    sources = data.get("official_sources", [])
    if not isinstance(sources, list):
        errors.append("state.official_sources must be a list")
    else:
        for index, source in enumerate(sources):
            if not isinstance(source, dict):
                errors.append(f"state.official_sources[{index}] must be an object")
                continue
            for key in ("url", "accessed_on", "key_requirement", "applies_to"):
                if not non_empty_string(source.get(key)):
                    errors.append(f"state.official_sources[{index}].{key} must be a non-empty string")
            if source.get("accessed_on") is not None and not is_iso_date(source.get("accessed_on")):
                errors.append(f"state.official_sources[{index}].accessed_on must use YYYY-MM-DD")

    platform = data.get("platform", {})
    if isinstance(platform, dict):
        match_status = platform.get("institution_match_status")
        if match_status is not None and match_status not in INSTITUTION_MATCH_STATUSES:
            errors.append(
                "platform.institution_match_status must be one of "
                + ", ".join(sorted(INSTITUTION_MATCH_STATUSES))
            )
    else:
        errors.append("state.platform must be an object")

    if schema_version in {"1.0", "1.1"}:
        gate_errors, gates_by_action = validate_confirmation_gates(
            data.get("confirmation_gates", []), schema_version
        )
        errors.extend(gate_errors)
        if schema_version == "1.1":
            errors.extend(validate_final_submit_exit(data, gates_by_action))

    next_action = data.get("next_action")
    if not isinstance(next_action, dict) or not next_action.get("action"):
        warnings.append("state.next_action.action is empty")

    return errors, warnings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--authors", type=Path, help="private authors.json")
    parser.add_argument("--state", type=Path, help="project submission-state.json")
    args = parser.parse_args()

    if not args.authors and not args.state:
        parser.error("provide --authors, --state, or both")

    errors: list[str] = []
    warnings: list[str] = []
    profile_ids: set[str] | None = None

    if args.authors:
        author_errors, author_warnings, profile_ids = validate_authors(load_json(args.authors))
        errors.extend(author_errors)
        warnings.extend(author_warnings)

    if args.state:
        state_errors, state_warnings = validate_state(load_json(args.state), profile_ids)
        errors.extend(state_errors)
        warnings.extend(state_warnings)

    report = {"ok": not errors, "errors": errors, "warnings": warnings}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
