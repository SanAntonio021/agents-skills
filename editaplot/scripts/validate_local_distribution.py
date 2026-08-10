#!/usr/bin/env python
"""Validate the personal CC Switch distribution without changing local state."""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any


SKILL_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = SKILL_ROOT / ".editaplot-local.json"
CONFIG_SCHEMA_VERSION = "1.1"
RUNTIME_MANIFEST_SCHEMA_VERSION = "1.0"
SOURCE_REPO_URL = "https://github.com/hang-jin/editaplot.git"
FULL_SHA_PATTERN = re.compile(r"[0-9a-f]{40}")
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path, errors: list[str]) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"invalid_json:{path.name}:{type(exc).__name__}")
        return {}
    if not isinstance(payload, dict):
        errors.append(f"invalid_object:{path.name}")
        return {}
    return payload


def _is_safe_relative_path(value: str) -> bool:
    path = Path(value)
    return bool(value) and not path.is_absolute() and ".." not in path.parts


def _is_versioned_runtime_path(engine_home: Path, expected_commit: str) -> bool:
    parts = [part.casefold() for part in engine_home.parts]
    expected = ["runtimes", "editaplot", expected_commit.casefold()]
    return len(parts) >= len(expected) and parts[-len(expected) :] == expected


def _validate_runtime_manifest(
    engine_home: Path,
    expected_manifest_sha256: str,
    errors: list[str],
) -> tuple[int, str | None]:
    manifest_path = engine_home / "runtime-manifest.json"
    if not manifest_path.is_file():
        return 0, None

    actual_manifest_sha256 = _sha256(manifest_path)
    if SHA256_PATTERN.fullmatch(expected_manifest_sha256):
        if actual_manifest_sha256 != expected_manifest_sha256:
            errors.append("runtime_manifest_hash_mismatch")

    manifest = _load_json(manifest_path, errors)
    if manifest.get("schema_version") != RUNTIME_MANIFEST_SCHEMA_VERSION:
        errors.append("unsupported_runtime_manifest_schema")
    entries = manifest.get("files")
    if not isinstance(entries, list):
        errors.append("invalid_runtime_manifest_files")
        return 0, actual_manifest_sha256
    if manifest.get("file_count") != len(entries):
        errors.append("runtime_manifest_file_count_mismatch")

    checked = 0
    seen: set[str] = set()
    for index, item in enumerate(entries):
        if not isinstance(item, dict):
            errors.append(f"invalid_runtime_manifest_entry:{index}")
            continue
        raw_path = item.get("path")
        expected_size = item.get("size_bytes")
        expected_sha256 = str(item.get("sha256", "")).lower()
        if not isinstance(raw_path, str) or not _is_safe_relative_path(raw_path):
            errors.append(f"unsafe_runtime_manifest_path:{index}")
            continue
        normalized_path = Path(raw_path).as_posix()
        if normalized_path in seen:
            errors.append(f"duplicate_runtime_manifest_path:{normalized_path}")
            continue
        seen.add(normalized_path)
        if not isinstance(expected_size, int) or expected_size < 0:
            errors.append(f"invalid_runtime_manifest_size:{normalized_path}")
            continue
        if not SHA256_PATTERN.fullmatch(expected_sha256):
            errors.append(f"invalid_runtime_manifest_sha256:{normalized_path}")
            continue

        runtime_file = engine_home / raw_path
        if not runtime_file.is_file():
            errors.append(f"runtime_file_missing:{normalized_path}")
            continue
        if runtime_file.stat().st_size != expected_size:
            errors.append(f"runtime_file_size_mismatch:{normalized_path}")
            continue
        if _sha256(runtime_file) != expected_sha256:
            errors.append(f"runtime_file_hash_mismatch:{normalized_path}")
            continue
        checked += 1
    return checked, actual_manifest_sha256


def validate_distribution(
    skill_root: Path = SKILL_ROOT,
    config_path: Path | None = None,
) -> dict[str, Any]:
    skill_root = skill_root.resolve()
    config_path = (config_path or skill_root / ".editaplot-local.json").resolve()
    errors: list[str] = []
    required_skill_files = (
        skill_root / "SKILL.md",
        skill_root / "LICENSE",
        skill_root / "NOTICE",
        skill_root / "editaplot.cmd",
        skill_root / "scripts" / "bootstrap_editaplot.py",
        skill_root / "scripts" / "requirements-runtime.lock",
        config_path,
    )
    for path in required_skill_files:
        if not path.is_file():
            try:
                display_path = path.relative_to(skill_root).as_posix()
            except ValueError:
                display_path = path.name
            errors.append(f"missing_skill_file:{display_path}")

    config = _load_json(config_path, errors) if config_path.is_file() else {}
    if config.get("schema_version") != CONFIG_SCHEMA_VERSION:
        errors.append("unsupported_local_config_schema")
    if config.get("source_repo_url") != SOURCE_REPO_URL:
        errors.append("source_repo_url_mismatch")

    expected_commit = str(config.get("expected_commit", "")).lower()
    if not FULL_SHA_PATTERN.fullmatch(expected_commit):
        errors.append("invalid_expected_commit")
    expected_manifest_sha256 = str(config.get("expected_runtime_manifest_sha256", "")).lower()
    if not SHA256_PATTERN.fullmatch(expected_manifest_sha256):
        errors.append("invalid_expected_runtime_manifest_sha256")

    raw_engine_home = config.get("engine_home")
    engine_home = Path(str(raw_engine_home)).expanduser() if raw_engine_home else None
    if engine_home is not None and not engine_home.is_absolute():
        errors.append("engine_home_not_absolute")
    if engine_home is None or not engine_home.is_dir():
        errors.append("engine_home_missing")
        checked_runtime_files = 0
        actual_manifest_sha256 = None
    else:
        engine_home = engine_home.resolve()
        if FULL_SHA_PATTERN.fullmatch(expected_commit) and not _is_versioned_runtime_path(
            engine_home, expected_commit
        ):
            errors.append("engine_home_not_versioned_snapshot")
        required_engine_files = (
            engine_home / "runtime-manifest.json",
            engine_home / "requirements-runtime.lock",
            engine_home / "src" / "origin_sciplot" / "__init__.py",
        )
        for path in required_engine_files:
            if not path.is_file():
                errors.append(f"missing_engine_file:{path.relative_to(engine_home).as_posix()}")

        checked_runtime_files, actual_manifest_sha256 = _validate_runtime_manifest(
            engine_home, expected_manifest_sha256, errors
        )

        skill_lock = skill_root / "scripts" / "requirements-runtime.lock"
        engine_lock = engine_home / "requirements-runtime.lock"
        if skill_lock.is_file() and engine_lock.is_file():
            if _sha256(skill_lock) != _sha256(engine_lock):
                errors.append("dependency_lock_mismatch")

        environment_root = engine_home / ".editaplot-venv"
        environment_python = environment_root / "Scripts" / "python.exe"
        fingerprint_path = environment_root / ".editaplot-environment.json"
        if not environment_python.is_file():
            errors.append("managed_environment_python_missing")
        fingerprint = _load_json(fingerprint_path, errors) if fingerprint_path.is_file() else {}
        if not fingerprint_path.is_file():
            errors.append("managed_environment_fingerprint_missing")
        elif engine_lock.is_file():
            expected_lock = _sha256(engine_lock)
            if fingerprint.get("dependency_lock_sha256") != expected_lock:
                errors.append("managed_environment_lock_mismatch")

    return {
        "schema_version": CONFIG_SCHEMA_VERSION,
        "ok": not errors,
        "skill_root": str(skill_root),
        "config_path": str(config_path),
        "engine_home": str(engine_home) if engine_home is not None else None,
        "source_repo_url": config.get("source_repo_url"),
        "expected_commit": expected_commit or None,
        "expected_runtime_manifest_sha256": expected_manifest_sha256 or None,
        "actual_runtime_manifest_sha256": actual_manifest_sha256,
        "checked_runtime_files": checked_runtime_files,
        "errors": errors,
    }


def main() -> int:
    payload = validate_distribution()
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
