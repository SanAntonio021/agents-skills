import json
import hashlib
import zipfile
from pathlib import Path

import pytest

from scripts.office_mcp_trial import (
    ADMISSION_STATUS,
    STATUS_FAIL,
    STATUS_PASS,
    TrialError,
    compare_packages,
    read_package,
    validate_lock,
)

COMMIT = "a" * 40
INPUT_SHA256 = "b" * 64


def _docx(path: Path, created: str, body: str = "same", uid: str = "12345678") -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", b"types")
        archive.writestr("word/document.xml", f'<d body="{body}"/>'.encode())
        archive.writestr("docProps/core.xml", f'<c><p created="{created}" uid="{uid}"/></c>'.encode())


def _lock(tmp_path: Path, paths: list[Path]) -> Path:
    rounds = []
    for index, path in enumerate(paths):
        root = tmp_path / f"run-{index}"
        root.mkdir()
        moved = root / path.name
        path.replace(moved)
        rounds.append({
            "round_id": f"r{index}",
            "run_root": str(root),
            "docx_path": str(moved),
            "sha256": hashlib.sha256(moved.read_bytes()).hexdigest(),
            "candidate": "candidate",
            "commit": COMMIT,
            "input_sha256": INPUT_SHA256,
            "generator": "generator",
        })
    lock = tmp_path / "trial-input.lock.json"
    lock.write_text(json.dumps({"schema_version": 1, "candidate": "candidate", "commit": COMMIT, "input_sha256": INPUT_SHA256, "generator": "generator", "rounds": rounds}), encoding="utf-8")
    return lock


def _allowlist(path: Path, rules: list[dict] | None = None) -> None:
    path.write_text(json.dumps({"schema_version": 1, "candidates": {COMMIT: {"allowed_differences": rules or []}}}), encoding="utf-8")


def test_three_packages_pass_and_are_not_admitted(tmp_path: Path):
    allowlist = tmp_path / "allowlist.json"
    _allowlist(allowlist, [{"part": "docProps/core.xml", "xpath": "/c/p", "attribute": "created", "value_kind": "rfc3339_utc"}])
    paths = []
    for index in range(3):
        path = tmp_path / f"{index}.docx"
        _docx(path, f"2026-08-24T00:00:0{index}Z")
        paths.append(path)
    result = compare_packages(paths, allowlist, COMMIT)
    assert result["status"] == STATUS_PASS
    assert result["admission_status"] == ADMISSION_STATUS


def test_multiple_restricted_attributes_can_change(tmp_path: Path):
    allowlist = tmp_path / "allowlist.json"
    _allowlist(allowlist, [
        {"part": "docProps/core.xml", "xpath": "/c/p", "attribute": "created", "value_kind": "rfc3339_utc"},
        {"part": "docProps/core.xml", "xpath": "/c/p", "attribute": "uid", "value_kind": "rsid_hex8"},
    ])
    paths = []
    for index in range(3):
        path = tmp_path / f"{index}.docx"
        _docx(path, f"2026-08-24T00:00:0{index}Z", uid=f"{index + 1:08x}")
        paths.append(path)
    assert compare_packages(paths, allowlist, COMMIT)["status"] == STATUS_PASS


def test_body_difference_fails_closed(tmp_path: Path):
    allowlist = tmp_path / "allowlist.json"
    _allowlist(allowlist)
    paths = []
    for index in range(3):
        path = tmp_path / f"{index}.docx"
        _docx(path, "2026-08-24T00:00:00Z", body="different" if index == 2 else "same")
        paths.append(path)
    assert compare_packages(paths, allowlist, COMMIT)["status"] == STATUS_FAIL


def test_allowlist_rejects_unknown_value_kind(tmp_path: Path):
    allowlist = tmp_path / "allowlist.json"
    _allowlist(allowlist, [{"part": "x", "xpath": "/x", "attribute": "a", "value_kind": "anything"}])
    paths = []
    for index in range(3):
        path = tmp_path / f"{index}.docx"
        _docx(path, "2026-08-24T00:00:00Z")
        paths.append(path)
    with pytest.raises(TrialError):
        compare_packages(paths, allowlist, COMMIT)


def test_lock_requires_three_distinct_rounds(tmp_path: Path):
    paths = []
    for index in range(3):
        path = tmp_path / f"{index}.docx"
        _docx(path, "2026-08-24T00:00:00Z")
        paths.append(path)
    lock = _lock(tmp_path, paths)
    assert validate_lock(lock)["schema_version"] == 1
    data = json.loads(lock.read_text(encoding="utf-8"))
    data["rounds"][0]["sha256"] = "0" * 64
    lock.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(TrialError):
        validate_lock(lock)


def test_lock_rejects_round_metadata_drift(tmp_path: Path):
    paths = []
    for index in range(3):
        path = tmp_path / f"{index}.docx"
        _docx(path, "2026-08-24T00:00:00Z")
        paths.append(path)
    lock = _lock(tmp_path, paths)
    data = json.loads(lock.read_text(encoding="utf-8"))
    data["rounds"][1]["generator"] = "different"
    lock.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(TrialError):
        validate_lock(lock)


def test_allowlist_rejects_unknown_commit(tmp_path: Path):
    allowlist = tmp_path / "allowlist.json"
    _allowlist(allowlist)
    paths = []
    for index in range(3):
        path = tmp_path / f"{index}.docx"
        _docx(path, "2026-08-24T00:00:00Z")
        paths.append(path)
    with pytest.raises(TrialError):
        compare_packages(paths, allowlist, "c" * 40)


def test_zip_path_traversal_is_rejected(tmp_path: Path):
    path = tmp_path / "bad.docx"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("../escape", b"bad")
    with pytest.raises(TrialError):
        read_package(path)
