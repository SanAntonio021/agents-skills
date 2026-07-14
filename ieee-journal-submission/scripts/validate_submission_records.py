#!/usr/bin/env python3
"""Validate private author profiles and per-project IEEE submission state."""

from __future__ import annotations

import argparse
import json
import re
import sys
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

REQUIRED_GATES = {
    "author_roles",
    "declarations",
    "reviewers",
    "final_submit",
    "open_access_fees",
    "copyright",
    "withdrawal_transfer",
}

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


def validate_authors(data: Any) -> tuple[list[str], list[str], set[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    profile_ids: set[str] = set()

    if not isinstance(data, dict):
        return ["authors document must be a JSON object"], warnings, profile_ids

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
            priorities = [email.get("priority") for email in emails if isinstance(email, dict)]
            numeric = [item for item in priorities if isinstance(item, int)]
            if len(numeric) != len(priorities) or numeric != sorted(numeric) or len(set(numeric)) != len(numeric):
                errors.append(f"{base}.emails priorities must be unique ascending integers")

        orcid = field_value(author.get("orcid"))
        if orcid and not ORCID_RE.fullmatch(str(orcid)):
            errors.append(f"{base}.orcid has invalid format")

        verification = author.get("verification", {})
        if verification.get("status") in {None, "pending"}:
            warnings.append(f"{base} remains pending verification")

    return errors, warnings, profile_ids


def validate_state(data: Any, known_profiles: set[str] | None = None) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    if not isinstance(data, dict):
        return ["submission state must be a JSON object"], warnings

    for key, path in iter_keys(data):
        if key in FORBIDDEN_KEYS:
            errors.append(f"forbidden sensitive field at {path}")

    stage = data.get("lifecycle", {}).get("current_stage")
    if stage not in VALID_STAGES:
        errors.append(f"invalid lifecycle.current_stage: {stage!r}")

    for index, author in enumerate(data.get("authors", [])):
        profile_id = author.get("profile_id") if isinstance(author, dict) else None
        if not profile_id:
            errors.append(f"state.authors[{index}].profile_id is required")
        elif known_profiles is not None and profile_id not in known_profiles:
            errors.append(f"unknown author profile_id in state: {profile_id}")

    for index, file_item in enumerate(data.get("files", [])):
        if not isinstance(file_item, dict):
            errors.append(f"state.files[{index}] must be an object")
            continue
        checksum = file_item.get("sha256")
        if checksum is not None and not SHA256_RE.fullmatch(str(checksum)):
            errors.append(f"state.files[{index}].sha256 must be 64 hexadecimal characters")

    for index, source in enumerate(data.get("official_sources", [])):
        if not isinstance(source, dict):
            errors.append(f"state.official_sources[{index}] must be an object")
            continue
        for key in ("url", "accessed_on", "key_requirement", "applies_to"):
            if not source.get(key):
                errors.append(f"state.official_sources[{index}].{key} is required")

    gates = data.get("confirmation_gates", [])
    gate_actions = {
        gate.get("action")
        for gate in gates
        if isinstance(gate, dict) and gate.get("action")
    }
    missing_gates = sorted(REQUIRED_GATES - gate_actions)
    if missing_gates:
        errors.append("missing confirmation gates: " + ", ".join(missing_gates))

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
