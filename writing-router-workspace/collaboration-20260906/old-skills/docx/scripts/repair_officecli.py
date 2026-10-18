#!/usr/bin/env python3
"""Explicitly repair the pinned local OfficeCLI binary.

This file is kept byte-identical in pptx, docx, xlsx, and pdf so their runtime
packages remain self-contained after a targeted CC Switch synchronization.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen


OFFICECLI_VERSION = "1.0.144"
ASSET_NAME = "officecli-win-x64.exe"
EXPECTED_ASSET_SHA256 = "E780CC6A5385F84B4D54D71B0C179904ED534125EC33FE39B1A8711FA80E387E"
EXPECTED_SUMS_SHA256 = "1A97C51CACDAED13DF326233553A57ADFE54F8B8264BD0A7458B87E6A8041D36"
ASSET_URL = "https://github.com/iOfficeAI/OfficeCLI/releases/download/v1.0.144/officecli-win-x64.exe"
SUMS_URL = "https://github.com/iOfficeAI/OfficeCLI/releases/download/v1.0.144/SHA256SUMS"
DEFAULT_TARGET = Path(r"D:\BaiduSyncdisk\.agents\tools\officecli\v1.0.144\officecli.exe")
LOCK_NAME = ".officecli_repair.lock"
LOCK_TIMEOUT_SECONDS = 5.0


class RepairError(RuntimeError):
    """A user-actionable repair failure."""


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def download(url: str, destination: Path) -> None:
    request = Request(url, headers={"User-Agent": f"OfficeCLI-repair/{OFFICECLI_VERSION}"})
    try:
        with urlopen(request, timeout=30) as response, destination.open("wb") as output:
            shutil.copyfileobj(response, output)
    except OSError as exc:
        raise RepairError(f"Could not download {url}: {exc}") from exc


def checksum_from_sums(sums_path: Path) -> str:
    actual_sums_sha256 = sha256(sums_path)
    if actual_sums_sha256 != EXPECTED_SUMS_SHA256:
        raise RepairError(
            "Official SHA256SUMS hash mismatch: "
            f"expected {EXPECTED_SUMS_SHA256}, got {actual_sums_sha256}"
        )
    try:
        text = sums_path.read_text(encoding="ascii")
    except UnicodeDecodeError as exc:
        raise RepairError("Official SHA256SUMS is not ASCII text") from exc
    pattern = re.compile(rf"^([0-9a-fA-F]{{64}})\s+\*?{re.escape(ASSET_NAME)}\s*$")
    for line in text.splitlines():
        match = pattern.match(line)
        if match:
            expected = match.group(1).upper()
            if expected != EXPECTED_ASSET_SHA256:
                raise RepairError(
                    "Official SHA256SUMS entry does not match the pinned asset hash: "
                    f"expected {EXPECTED_ASSET_SHA256}, got {expected}"
                )
            return expected
    raise RepairError(f"Official SHA256SUMS does not contain {ASSET_NAME}")


def lock_file(handle) -> None:
    handle.seek(0)
    if not handle.read(1):
        handle.seek(0)
        handle.write(b"0")
        handle.flush()
        os.fsync(handle.fileno())
    handle.seek(0)
    if os.name == "nt":
        import msvcrt

        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        return
    import fcntl

    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def unlock_file(handle) -> None:
    handle.seek(0)
    if os.name == "nt":
        import msvcrt

        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        return
    import fcntl

    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


@contextmanager
def repair_lock(target: Path):
    target.parent.mkdir(parents=True, exist_ok=True)
    lock_path = target.parent / LOCK_NAME
    with lock_path.open("a+b") as handle:
        deadline = time.monotonic() + LOCK_TIMEOUT_SECONDS
        while True:
            try:
                lock_file(handle)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise RepairError(f"Another OfficeCLI repair process is already running: {lock_path}")
                time.sleep(0.1)
        try:
            yield lock_path
        finally:
            unlock_file(handle)


def backup_path(target: Path, original_sha256: str) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    prefix = original_sha256[:12].lower()
    candidate = target.with_name(f"{target.name}.invalid-{stamp}-{prefix}.bak")
    counter = 1
    while candidate.exists():
        candidate = target.with_name(f"{target.name}.invalid-{stamp}-{prefix}.{counter}.bak")
        counter += 1
    return candidate


def stage_verified_asset(asset: Path, target: Path) -> Path:
    staged = target.parent / f".{target.name}.{uuid.uuid4().hex}.staged"
    try:
        shutil.copyfile(asset, staged)
        staged_sha256 = sha256(staged)
        if staged_sha256 != EXPECTED_ASSET_SHA256:
            raise RepairError(
                f"Staged asset hash mismatch: expected {EXPECTED_ASSET_SHA256}, got {staged_sha256}"
            )
        return staged
    except Exception:
        if staged.exists():
            staged.unlink()
        raise


def repair(target: Path = DEFAULT_TARGET) -> dict[str, str | None]:
    with repair_lock(target):
        if target.exists() and not target.is_file():
            raise RepairError(f"OfficeCLI target is not a file: {target}")
        if target.is_file() and sha256(target) == EXPECTED_ASSET_SHA256:
            return {
                "ok": "true",
                "status": "already_valid",
                "officecli": str(target),
                "sha256": EXPECTED_ASSET_SHA256,
                "backup": None,
            }

        with tempfile.TemporaryDirectory(prefix="officecli-repair-") as temporary_directory:
            temporary_root = Path(temporary_directory)
            sums_path = temporary_root / "SHA256SUMS"
            asset_path = temporary_root / ASSET_NAME
            download(SUMS_URL, sums_path)
            checksum_from_sums(sums_path)
            download(ASSET_URL, asset_path)
            actual_asset_sha256 = sha256(asset_path)
            if actual_asset_sha256 != EXPECTED_ASSET_SHA256:
                raise RepairError(
                    "Downloaded asset hash mismatch: "
                    f"expected {EXPECTED_ASSET_SHA256}, got {actual_asset_sha256}"
                )

            staged = stage_verified_asset(asset_path, target)
            backup = None
            try:
                if target.exists():
                    if not target.is_file():
                        raise RepairError(f"OfficeCLI target is not a file: {target}")
                    current_sha256 = sha256(target)
                    if current_sha256 == EXPECTED_ASSET_SHA256:
                        staged.unlink()
                        return {
                            "ok": "true",
                            "status": "already_valid",
                            "officecli": str(target),
                            "sha256": EXPECTED_ASSET_SHA256,
                            "backup": None,
                        }
                    backup = backup_path(target, current_sha256)
                    os.replace(target, backup)
                if target.exists():
                    raise RepairError(
                        f"OfficeCLI target was recreated during repair; verified staged file retained: {staged}"
                    )
                os.replace(staged, target)
            except Exception:
                if staged.exists():
                    # Keep a verified staged file when replacement failed after a backup was made.
                    if backup is None:
                        staged.unlink()
                raise

            final_sha256 = sha256(target)
            if final_sha256 != EXPECTED_ASSET_SHA256:
                raise RepairError(
                    f"Installed asset hash mismatch: expected {EXPECTED_ASSET_SHA256}, got {final_sha256}"
                )
            return {
                "ok": "true",
                "status": "repaired",
                "officecli": str(target),
                "sha256": final_sha256,
                "backup": str(backup) if backup else None,
            }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Explicit repair for the pinned local OfficeCLI binary")
    parser.add_argument("--repair", action="store_true", help="download and install the pinned OfficeCLI asset")
    return parser


def main(argv: list[str] | None = None) -> int:
    parsed = build_parser().parse_args(argv)
    if not parsed.repair:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": "Refusing to modify OfficeCLI without --repair.",
                    "command": f"{sys.executable} {Path(__file__)} --repair",
                },
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 2
    try:
        result = repair()
        result["ok"] = True
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except RepairError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
