#!/usr/bin/env python3
"""Verify a CC Switch-installed PPT Master tree against the external pptx pin."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
from pathlib import Path, PurePosixPath
from typing import Any


DEFAULT_PIN = Path(__file__).parents[1] / "references" / "ppt-master-pin.json"
MANIFEST_NAME = "distribution.manifest.json"
PROVENANCE_NAME = "ccswitch.provenance.json"
FORK_REPOSITORY = "https://github.com/SanAntonio021/ppt-master"
UPSTREAM_REPOSITORY = "https://github.com/hugohe3/ppt-master"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
TAG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
DRIVE_RE = re.compile(r"^[A-Za-z]:")
WINDOWS_RESERVED = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}


class PinVerificationError(RuntimeError):
    """Raised when the pin or installed distribution fails closed."""


def _configure_utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8")


def _object_without_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise PinVerificationError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _load_json(path: Path, label: str) -> dict[str, Any]:
    if _is_reparse_point(path):
        raise PinVerificationError(f"symbolic link or reparse point is forbidden for {label}: {path}")
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise PinVerificationError(f"cannot read {label}: {path}: {exc}") from exc
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_object_without_duplicates)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PinVerificationError(f"invalid UTF-8 JSON in {label}: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise PinVerificationError(f"{label} must be a JSON object")
    return value


def _exact_keys(value: dict[str, Any], expected: set[str], label: str) -> None:
    actual = set(value)
    if actual != expected:
        missing = sorted(expected - actual)
        unexpected = sorted(actual - expected)
        raise PinVerificationError(
            f"{label} keys mismatch: missing={missing} unexpected={unexpected}"
        )


def _require_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise PinVerificationError(f"{label} must be a non-empty string")
    return value


def _require_nonnegative_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise PinVerificationError(f"{label} must be a non-negative integer")
    return value


def _require_sha256(value: Any, label: str) -> str:
    digest = _require_string(value, label)
    if not SHA256_RE.fullmatch(digest):
        raise PinVerificationError(f"{label} must be a lowercase SHA-256 digest")
    return digest


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise PinVerificationError(f"cannot hash {path}: {exc}") from exc
    return digest.hexdigest()


def _is_reparse_point(path: Path) -> bool:
    try:
        info = path.lstat()
    except OSError as exc:
        raise PinVerificationError(f"cannot inspect path: {path}: {exc}") from exc
    attributes = getattr(info, "st_file_attributes", 0)
    return path.is_symlink() or bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))


def _validate_relative_path(raw_path: Any, label: str) -> str:
    path = _require_string(raw_path, label)
    if "\\" in path or path.startswith(("/", "//")) or DRIVE_RE.match(path):
        raise PinVerificationError(f"unsafe path in {label}: {path}")
    posix = PurePosixPath(path)
    if posix.is_absolute() or not posix.parts:
        raise PinVerificationError(f"unsafe path in {label}: {path}")
    for part in posix.parts:
        if part in {"", ".", ".."} or part != part.rstrip(" ."):
            raise PinVerificationError(f"unsafe path component in {label}: {path}")
        if ":" in part or any(ord(character) < 32 for character in part):
            raise PinVerificationError(f"unsafe path component in {label}: {path}")
        if part.split(".", 1)[0].upper() in WINDOWS_RESERVED:
            raise PinVerificationError(f"Windows reserved name in {label}: {path}")
    return posix.as_posix()


def _validate_release(release: Any, index: int) -> dict[str, Any]:
    label = f"accepted_distributions[{index}]"
    if not isinstance(release, dict):
        raise PinVerificationError(f"{label} must be an object")
    _exact_keys(
        release,
        {"role", "fork_commit", "release_tag", "codeload", "distribution_manifest", "upstream"},
        label,
    )
    role = _require_string(release["role"], f"{label}.role")
    if role not in {"stable", "candidate"}:
        raise PinVerificationError(f"invalid {label}.role: {role}")
    fork_commit = _require_string(release["fork_commit"], f"{label}.fork_commit")
    if not COMMIT_RE.fullmatch(fork_commit):
        raise PinVerificationError(f"{label}.fork_commit must be a lowercase 40-character commit")
    release_tag = _require_string(release["release_tag"], f"{label}.release_tag")
    if not TAG_RE.fullmatch(release_tag):
        raise PinVerificationError(f"invalid {label}.release_tag")

    codeload = release["codeload"]
    if not isinstance(codeload, dict):
        raise PinVerificationError(f"{label}.codeload must be an object")
    _exact_keys(codeload, {"sha256", "size", "members"}, f"{label}.codeload")
    _require_sha256(codeload["sha256"], f"{label}.codeload.sha256")
    _require_nonnegative_int(codeload["size"], f"{label}.codeload.size")
    members = _require_nonnegative_int(codeload["members"], f"{label}.codeload.members")
    if members > 2000:
        raise PinVerificationError(f"{label}.codeload.members exceeds the CC Switch limit")

    manifest = release["distribution_manifest"]
    if not isinstance(manifest, dict):
        raise PinVerificationError(f"{label}.distribution_manifest must be an object")
    _exact_keys(manifest, {"sha256", "files", "bytes"}, f"{label}.distribution_manifest")
    _require_sha256(manifest["sha256"], f"{label}.distribution_manifest.sha256")
    _require_nonnegative_int(manifest["files"], f"{label}.distribution_manifest.files")
    _require_nonnegative_int(manifest["bytes"], f"{label}.distribution_manifest.bytes")

    upstream = release["upstream"]
    if not isinstance(upstream, dict):
        raise PinVerificationError(f"{label}.upstream must be an object")
    _exact_keys(upstream, {"repository", "commit", "version"}, f"{label}.upstream")
    if upstream["repository"] != UPSTREAM_REPOSITORY:
        raise PinVerificationError(f"unexpected {label}.upstream.repository")
    upstream_commit = _require_string(upstream["commit"], f"{label}.upstream.commit")
    if not COMMIT_RE.fullmatch(upstream_commit):
        raise PinVerificationError(f"{label}.upstream.commit must be a lowercase commit")
    _require_string(upstream["version"], f"{label}.upstream.version")
    return release


def validate_pin(pin: dict[str, Any]) -> list[dict[str, Any]]:
    """Validate the strict external-pin schema and return accepted releases."""
    _exact_keys(
        pin,
        {"schema_version", "skill_name", "state", "source", "policy", "accepted_distributions"},
        "pin",
    )
    if pin["schema_version"] != 1 or pin["skill_name"] != "ppt-master":
        raise PinVerificationError("unsupported pin schema or skill name")
    state = _require_string(pin["state"], "pin.state")
    if state not in {"bootstrap", "transition", "stable"}:
        raise PinVerificationError(f"invalid pin state: {state}")

    source = pin["source"]
    if not isinstance(source, dict):
        raise PinVerificationError("pin.source must be an object")
    _exact_keys(source, {"repository", "branch"}, "pin.source")
    if source != {"repository": FORK_REPOSITORY, "branch": "ccswitch"}:
        raise PinVerificationError("pin source must be the trusted Fork ccswitch branch")

    policy = pin["policy"]
    if not isinstance(policy, dict):
        raise PinVerificationError("pin.policy must be an object")
    _exact_keys(policy, {"raw_file_identity", "system_fallback"}, "pin.policy")
    if policy["raw_file_identity"] != "relative_path+size+sha256":
        raise PinVerificationError("pin policy must require raw path, size, and SHA-256 identity")
    if policy["system_fallback"] is not False:
        raise PinVerificationError("system presentation fallback must remain disabled")

    releases_value = pin["accepted_distributions"]
    if not isinstance(releases_value, list):
        raise PinVerificationError("pin.accepted_distributions must be an array")
    releases = [_validate_release(value, index) for index, value in enumerate(releases_value)]
    expected_roles = {
        "bootstrap": ["candidate"],
        "transition": ["stable", "candidate"],
        "stable": ["stable"],
    }[state]
    roles = [release["role"] for release in releases]
    if roles != expected_roles:
        raise PinVerificationError(
            f"pin state {state} requires roles {expected_roles}, found {roles}"
        )
    for field, getter in (
        ("fork commit", lambda item: item["fork_commit"]),
        ("release tag", lambda item: item["release_tag"]),
        ("distribution manifest", lambda item: item["distribution_manifest"]["sha256"]),
    ):
        values = [getter(release) for release in releases]
        if len(values) != len(set(values)):
            raise PinVerificationError(f"duplicate accepted {field}")
    return releases


def _is_transient_cache(relative_path: str) -> bool:
    parts = PurePosixPath(relative_path).parts
    return "__pycache__" in parts and relative_path.endswith((".pyc", ".pyo"))


def _inventory_tree(root: Path) -> dict[str, Path]:
    if not root.is_dir() or _is_reparse_point(root):
        raise PinVerificationError(f"skill root must be a real directory: {root}")
    files: dict[str, Path] = {}
    folded: dict[str, str] = {}
    for current, dirnames, filenames in os.walk(root, followlinks=False):
        current_path = Path(current)
        for name in dirnames:
            directory = current_path / name
            if _is_reparse_point(directory):
                raise PinVerificationError(f"symbolic link or reparse point is forbidden: {directory}")
        for name in filenames:
            path = current_path / name
            if _is_reparse_point(path) or not path.is_file():
                raise PinVerificationError(f"non-regular file is forbidden: {path}")
            relative = _validate_relative_path(path.relative_to(root).as_posix(), "installed tree")
            if _is_transient_cache(relative):
                continue
            case_key = relative.casefold()
            if case_key in folded:
                raise PinVerificationError(
                    f"case-insensitive path collision: {folded[case_key]} and {relative}"
                )
            folded[case_key] = relative
            files[relative] = path
    return files


def _expected_provenance(pin: dict[str, Any], release: dict[str, Any]) -> dict[str, Any]:
    upstream = release["upstream"]
    return {
        "distribution": "ccswitch",
        "fork_repository": pin["source"]["repository"],
        "icon_storage": "deterministic-zip-stored-shards",
        "release_tag": release["release_tag"],
        "schema_version": 1,
        "upstream_commit": upstream["commit"],
        "upstream_repository": upstream["repository"],
        "upstream_version": upstream["version"],
    }


def _validate_distribution_manifest(
    manifest: dict[str, Any], release: dict[str, Any]
) -> dict[str, dict[str, Any]]:
    _exact_keys(manifest, {"schema_version", "distribution", "upstream", "totals", "files"}, "manifest")
    if manifest["schema_version"] != 1 or manifest["distribution"] != "ccswitch":
        raise PinVerificationError("unsupported distribution manifest")
    if manifest["upstream"] != release["upstream"]:
        raise PinVerificationError("distribution manifest upstream does not match the accepted pin")
    totals = manifest["totals"]
    if not isinstance(totals, dict):
        raise PinVerificationError("manifest.totals must be an object")
    _exact_keys(totals, {"files", "bytes"}, "manifest.totals")
    total_files = _require_nonnegative_int(totals["files"], "manifest.totals.files")
    total_bytes = _require_nonnegative_int(totals["bytes"], "manifest.totals.bytes")
    pinned_totals = release["distribution_manifest"]
    if total_files != pinned_totals["files"] or total_bytes != pinned_totals["bytes"]:
        raise PinVerificationError("distribution totals do not match the accepted pin")

    entries_value = manifest["files"]
    if not isinstance(entries_value, list):
        raise PinVerificationError("manifest.files must be an array")
    entries: dict[str, dict[str, Any]] = {}
    folded: dict[str, str] = {}
    ordered_paths: list[str] = []
    byte_sum = 0
    for index, entry in enumerate(entries_value):
        label = f"manifest.files[{index}]"
        if not isinstance(entry, dict):
            raise PinVerificationError(f"{label} must be an object")
        _exact_keys(entry, {"path", "size", "sha256"}, label)
        relative = _validate_relative_path(entry["path"], f"{label}.path")
        if relative == MANIFEST_NAME or _is_transient_cache(relative):
            raise PinVerificationError(f"forbidden manifest member: {relative}")
        size = _require_nonnegative_int(entry["size"], f"{label}.size")
        _require_sha256(entry["sha256"], f"{label}.sha256")
        case_key = relative.casefold()
        if relative in entries or case_key in folded:
            raise PinVerificationError(f"duplicate or case-colliding manifest path: {relative}")
        entries[relative] = entry
        folded[case_key] = relative
        ordered_paths.append(relative)
        byte_sum += size
    if ordered_paths != sorted(ordered_paths):
        raise PinVerificationError("manifest paths are not deterministically sorted")
    if len(entries) != total_files or byte_sum != total_bytes:
        raise PinVerificationError("manifest file or byte totals are internally inconsistent")
    for required in {"SKILL.md", "LICENSE", PROVENANCE_NAME}:
        if required not in entries:
            raise PinVerificationError(f"required protected file is absent from manifest: {required}")
    return entries


def verify_installed(skill_root: Path, pin_path: Path = DEFAULT_PIN) -> dict[str, Any]:
    """Verify one installed skill tree and return machine-readable evidence."""
    pin = _load_json(pin_path, "pin")
    releases = validate_pin(pin)
    input_root = skill_root.absolute()
    if _is_reparse_point(input_root):
        raise PinVerificationError(
            f"symbolic link or reparse point is forbidden for skill root: {input_root}"
        )
    root = input_root.resolve(strict=True)
    files = _inventory_tree(root)
    if MANIFEST_NAME not in files:
        raise PinVerificationError(f"installed tree is missing {MANIFEST_NAME}")
    manifest_digest = _sha256(files[MANIFEST_NAME])
    matches = [
        release
        for release in releases
        if release["distribution_manifest"]["sha256"] == manifest_digest
    ]
    if len(matches) != 1:
        raise PinVerificationError(
            f"distribution manifest digest is not accepted by pin state {pin['state']}: {manifest_digest}"
        )
    release = matches[0]
    manifest = _load_json(files[MANIFEST_NAME], "distribution manifest")
    entries = _validate_distribution_manifest(manifest, release)
    expected_paths = set(entries) | {MANIFEST_NAME}
    actual_paths = set(files)
    missing = sorted(expected_paths - actual_paths)
    unexpected = sorted(actual_paths - expected_paths)
    if missing or unexpected:
        raise PinVerificationError(
            f"installed tree membership mismatch: missing={missing} unexpected={unexpected}"
        )
    for relative, entry in entries.items():
        path = files[relative]
        try:
            size = path.stat().st_size
        except OSError as exc:
            raise PinVerificationError(f"cannot stat protected file {relative}: {exc}") from exc
        if size != entry["size"]:
            raise PinVerificationError(
                f"protected file size mismatch: {relative}: expected={entry['size']} actual={size}"
            )
        digest = _sha256(path)
        if digest != entry["sha256"]:
            raise PinVerificationError(
                f"protected file SHA-256 mismatch: {relative}: expected={entry['sha256']} actual={digest}"
            )
    provenance = _load_json(files[PROVENANCE_NAME], "CC Switch provenance")
    if provenance != _expected_provenance(pin, release):
        raise PinVerificationError("CC Switch provenance does not match the accepted external pin")
    return {
        "accepted_role": release["role"],
        "distribution_bytes": release["distribution_manifest"]["bytes"],
        "distribution_files": release["distribution_manifest"]["files"],
        "distribution_manifest_sha256": manifest_digest,
        "fork_commit": release["fork_commit"],
        "pin_state": pin["state"],
        "raw_file_identity": pin["policy"]["raw_file_identity"],
        "release_tag": release["release_tag"],
        "skill_root": str(root),
        "status": "PASS",
        "system_fallback": False,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skill-root", type=Path, help="Installed ppt-master skill root")
    parser.add_argument("--pin", type=Path, default=DEFAULT_PIN, help="External pin JSON")
    parser.add_argument("--pin-only", action="store_true", help="Validate only the pin state machine")
    parser.add_argument("--json-out", type=Path, help="Optional machine-readable evidence path")
    return parser


def main(argv: list[str] | None = None) -> int:
    _configure_utf8_stdio()
    parser = _parser()
    args = parser.parse_args(argv)
    if args.pin_only and args.skill_root is not None:
        parser.error("--pin-only cannot be combined with --skill-root")
    if not args.pin_only and args.skill_root is None:
        parser.error("--skill-root is required unless --pin-only is used")
    try:
        if args.pin_only:
            pin = _load_json(args.pin, "pin")
            releases = validate_pin(pin)
            report = {
                "accepted_roles": [release["role"] for release in releases],
                "pin_state": pin["state"],
                "status": "PASS",
                "system_fallback": False,
            }
        else:
            report = verify_installed(args.skill_root, args.pin)
    except (OSError, PinVerificationError) as exc:
        report = {"error": str(exc), "status": "FAIL"}
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
        return 1
    rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.json_out is not None:
        try:
            args.json_out.write_text(rendered, encoding="utf-8", newline="\n")
        except OSError as exc:
            print(json.dumps({"error": str(exc), "status": "FAIL"}, ensure_ascii=False))
            return 1
    sys.stdout.write(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
