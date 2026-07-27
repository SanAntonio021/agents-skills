#!/usr/bin/env python
"""Validate the personal CC Switch distribution without changing local state."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any


SKILL_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = SKILL_ROOT / ".editaplot-local.json"


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


def main() -> int:
    errors: list[str] = []
    required_skill_files = (
        SKILL_ROOT / "SKILL.md",
        SKILL_ROOT / "LICENSE",
        SKILL_ROOT / "NOTICE",
        SKILL_ROOT / "editaplot.cmd",
        SKILL_ROOT / "scripts" / "bootstrap_editaplot.py",
        SKILL_ROOT / "scripts" / "requirements-runtime.lock",
        CONFIG_PATH,
    )
    for path in required_skill_files:
        if not path.is_file():
            errors.append(f"missing_skill_file:{path.relative_to(SKILL_ROOT).as_posix()}")

    config = _load_json(CONFIG_PATH, errors) if CONFIG_PATH.is_file() else {}
    if config.get("schema_version") != "1.0":
        errors.append("unsupported_local_config_schema")

    raw_engine_home = config.get("engine_home")
    engine_home = Path(str(raw_engine_home)).expanduser() if raw_engine_home else None
    if engine_home is None or not engine_home.is_dir():
        errors.append("engine_home_missing")
    else:
        required_engine_files = (
            engine_home / "runtime-manifest.json",
            engine_home / "requirements-runtime.lock",
            engine_home / "src" / "origin_sciplot" / "__init__.py",
        )
        for path in required_engine_files:
            if not path.is_file():
                errors.append(f"missing_engine_file:{path.relative_to(engine_home).as_posix()}")

        skill_lock = SKILL_ROOT / "scripts" / "requirements-runtime.lock"
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

    payload = {
        "schema_version": "1.0",
        "ok": not errors,
        "skill_root": str(SKILL_ROOT),
        "config_path": str(CONFIG_PATH),
        "engine_home": str(engine_home) if engine_home is not None else None,
        "errors": errors,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
