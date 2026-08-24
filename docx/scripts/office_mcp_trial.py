#!/usr/bin/env python3
"""Offline OOXML determinism checks for non-admitted Office MCP trials.

This module deliberately does not acquire candidates, install dependencies, or
start Office/MCP processes.  It only validates a trial lock and compares three
already-produced DOCX packages.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import posixpath
import re
import stat
import sys
import zipfile
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

STATUS_PASS = "MCP_DETERMINISTIC"
STATUS_FAIL = "MCP_NONDETERMINISTIC"
ADMISSION_STATUS = "MCP_NOT_ADMITTED"
MAX_ENTRIES = 512
MAX_ENTRY_BYTES = 32 * 1024 * 1024
MAX_TOTAL_BYTES = 128 * 1024 * 1024

_VALUE_PATTERNS = {
    "rfc3339_utc": re.compile(r"\A\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\Z"),
    "uuid": re.compile(r"\A[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}\Z"),
    "rsid_hex8": re.compile(r"\A[0-9a-fA-F]{8}\Z"),
}
_XML_RULE_KEYS = {"part", "xpath", "attribute", "value_kind"}


class TrialError(ValueError):
    pass


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _safe_name(name: str) -> str:
    if not name or "\x00" in name or "\\" in name or name.startswith("/"):
        raise TrialError(f"unsafe ZIP member name: {name!r}")
    normalized = posixpath.normpath(name)
    if normalized != name or normalized == "." or normalized.startswith("../") or "/../" in normalized:
        raise TrialError(f"unsafe ZIP member name: {name!r}")
    return name


def read_package(path: Path) -> dict[str, bytes]:
    if not path.is_file():
        raise TrialError(f"missing DOCX: {path}")
    result: dict[str, bytes] = {}
    inflated = 0
    try:
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()
            if len(infos) > MAX_ENTRIES:
                raise TrialError("ZIP entry count exceeds limit")
            for info in infos:
                name = _safe_name(info.filename)
                mode = (info.external_attr >> 16) & 0xFFFF
                if info.is_dir() or stat.S_ISLNK(mode):
                    raise TrialError(f"ZIP directories/symlinks are not allowed: {name}")
                if name in result:
                    raise TrialError(f"duplicate ZIP member: {name}")
                if info.file_size > MAX_ENTRY_BYTES:
                    raise TrialError(f"ZIP member exceeds limit: {name}")
                inflated += info.file_size
                if inflated > MAX_TOTAL_BYTES:
                    raise TrialError("total inflated ZIP size exceeds limit")
                result[name] = archive.read(info)
    except zipfile.BadZipFile as exc:
        raise TrialError(f"invalid DOCX ZIP: {path}") from exc
    return result


def _load_allowlist(path: Path, commit: str) -> list[dict[str, str]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TrialError(f"cannot read allowlist: {path}") from exc
    if not isinstance(data, dict) or data.get("schema_version") != 1 or not isinstance(data.get("candidates"), dict):
        raise TrialError("unsupported or malformed allowlist")
    if commit not in data["candidates"]:
        raise TrialError(f"candidate commit is not allowlisted: {commit}")
    candidate = data["candidates"][commit]
    if not isinstance(candidate, dict) or set(candidate) - {"allowed_differences"}:
        raise TrialError("malformed candidate allowlist entry")
    rules = candidate.get("allowed_differences", [])
    if not isinstance(rules, list):
        raise TrialError("allowed_differences must be a list")
    for rule in rules:
        if not isinstance(rule, dict) or set(rule) != _XML_RULE_KEYS:
            raise TrialError("allowlist rule has unknown or missing fields")
        if not all(isinstance(rule[key], str) and rule[key] for key in _XML_RULE_KEYS):
            raise TrialError("allowlist rule fields must be non-empty strings")
        if rule["value_kind"] not in _VALUE_PATTERNS:
            raise TrialError(f"unknown allowlist value kind: {rule['value_kind']}")
    if len({(rule["part"], rule["xpath"], rule["attribute"]) for rule in rules}) != len(rules):
        raise TrialError("duplicate allowlist XML location")
    return rules


def _scrub_allowed_values(package: dict[str, bytes], part: str, rules: list[dict[str, str]]) -> bytes:
    try:
        root = ET.fromstring(package[part])
    except (KeyError, ET.ParseError) as exc:
        raise TrialError(f"allowlist XML location is invalid: {part}") from exc
    for rule in rules:
        node: ET.Element | None = root
        path = rule["xpath"].lstrip("/").split("/")
        if path and path[0] == root.tag:
            path = path[1:]
        for segment in filter(None, path):
            node = next((child for child in list(node) if child.tag == segment or segment == "*"), None) if node is not None else None
        if node is None or rule["attribute"] not in node.attrib:
            raise TrialError(f"allowlist XML location missing: {rule}")
        value = node.attrib[rule["attribute"]]
        if not _VALUE_PATTERNS[rule["value_kind"]].fullmatch(value):
            raise TrialError(f"allowlist value does not match {rule['value_kind']}: {rule}")
        node.attrib[rule["attribute"]] = "__ALLOWED__"
    return ET.tostring(root, encoding="utf-8")


def _allowed_xml_difference(parts: dict[str, bytes], other: dict[str, bytes], rules: list[dict[str, str]]) -> bool:
    differing = [name for name in parts if parts[name] != other.get(name)]
    for name in differing:
        matching = [rule for rule in rules if rule["part"] == name]
        if not matching:
            return False
        before = _scrub_allowed_values(parts, name, matching)
        after = _scrub_allowed_values(other, name, matching)
        if before == after:
            continue
        return False
    return True


def compare_packages(paths: list[Path], allowlist: Path, commit: str) -> dict[str, Any]:
    if len(paths) != 3:
        raise TrialError("exactly three DOCX paths are required")
    packages = [read_package(path) for path in paths]
    rules = _load_allowlist(allowlist, commit)
    for package in packages:
        for part in {rule["part"] for rule in rules}:
            if part not in package:
                raise TrialError(f"allowlist part is absent: {part}")
        for rule in rules:
            _scrub_allowed_values(package, rule["part"], [rule])
    names = set(packages[0])
    if any(set(package) != names for package in packages[1:]):
        status = STATUS_FAIL
    else:
        status = STATUS_PASS
        for package in packages[1:]:
            if package != packages[0] and not _allowed_xml_difference(packages[0], package, rules):
                status = STATUS_FAIL
                break
    return {"status": status, "admission_status": ADMISSION_STATUS, "candidate_commit": commit,
            "docx_sha256": [_sha256(path) for path in paths], "paths": [str(path) for path in paths]}


def validate_lock(lock_path: Path) -> dict[str, Any]:
    try:
        lock = json.loads(lock_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TrialError("cannot read trial lock") from exc
    required = {"schema_version", "candidate", "commit", "input_sha256", "generator", "rounds"}
    if not isinstance(lock, dict) or set(lock) != required or lock["schema_version"] != 1 or not all(isinstance(lock[key], str) and lock[key] for key in required - {"schema_version", "rounds"}):
        raise TrialError("malformed trial lock")
    if not re.fullmatch(r"[0-9a-f]{40}", lock["commit"]):
        raise TrialError("commit must be a lowercase 40-character SHA-1")
    if not re.fullmatch(r"[0-9a-f]{64}", lock["input_sha256"]):
        raise TrialError("input_sha256 must be lowercase hex")
    rounds = lock["rounds"]
    if not isinstance(rounds, list) or len(rounds) != 3:
        raise TrialError("trial lock must contain exactly three rounds")
    ids, roots, paths = set(), set(), set()
    for item in rounds:
        if not isinstance(item, dict) or set(item) != {"round_id", "run_root", "docx_path", "sha256", "candidate", "commit", "input_sha256", "generator"}:
            raise TrialError("malformed round entry")
        rid, root, docx = (item[key] for key in ("round_id", "run_root", "docx_path"))
        if not all(isinstance(value, str) and value for value in (rid, root, docx)) or rid in ids:
            raise TrialError("round IDs, roots, and DOCX paths must be distinct")
        if any(item[key] != lock[key] for key in ("candidate", "commit", "input_sha256", "generator")):
            raise TrialError("round metadata drifted from the trial lock")
        if not re.fullmatch(r"[0-9a-f]{64}", item["sha256"]):
            raise TrialError("round sha256 must be lowercase hex")
        root_path, docx_path = Path(root).resolve(), Path(docx).resolve()
        root_key, docx_key = os.path.normcase(str(root_path)), os.path.normcase(str(docx_path))
        if root_key in roots or docx_key in paths:
            raise TrialError("round IDs, roots, and DOCX paths must be distinct")
        ids.add(rid); roots.add(root_key); paths.add(docx_key)
        try:
            docx_path.relative_to(root_path)
        except ValueError as exc:
            raise TrialError("DOCX path must be inside its run root") from exc
        if not docx_path.is_file() or _sha256(docx_path) != item["sha256"]:
            raise TrialError(f"DOCX hash does not match the lock: {docx_path}")
    return lock


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    compare = sub.add_parser("compare")
    compare.add_argument("--lock", required=True, type=Path)
    compare.add_argument("--allowlist", type=Path)
    args = parser.parse_args(argv)
    try:
        lock = validate_lock(args.lock)
        allowlist = args.allowlist or Path(__file__).resolve().parents[1] / "mcp-determinism-allowlist.json"
        rounds = lock["rounds"]
        paths = [Path(item["docx_path"]) for item in rounds]
        result = compare_packages(paths, allowlist, lock["commit"])
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["status"] == STATUS_PASS else 2
    except TrialError as exc:
        print(json.dumps({"status": STATUS_FAIL, "admission_status": ADMISSION_STATUS, "error": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    sys.exit(main())
