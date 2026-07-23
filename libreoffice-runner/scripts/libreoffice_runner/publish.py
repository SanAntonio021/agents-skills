"""Validate then publish outputs without replacing an existing user file."""

from __future__ import annotations

import os
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import pywintypes
import win32file
import winerror


class OutputExistsError(FileExistsError):
    """A final output already exists or appeared during atomic publication."""


class PublishError(RuntimeError):
    """A staged output could not be copied or atomically published."""


@dataclass(frozen=True)
class PublishResult:
    output: Path
    temporary: Path


def publish_exclusive(
    generated: Path,
    output: Path,
    validate: Callable[[Path], None],
) -> PublishResult:
    """Copy to a same-directory temporary file, validate it, then rename once."""

    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise OutputExistsError(f"Output already exists: {output}")
    temporary = output.parent / f".{output.name}.tmp-{uuid.uuid4()}"
    try:
        _copy_and_sync(generated, temporary)
        validate(temporary)
        try:
            win32file.MoveFileEx(str(temporary), str(output), win32file.MOVEFILE_WRITE_THROUGH)
        except pywintypes.error as exc:
            if exc.winerror in {winerror.ERROR_FILE_EXISTS, winerror.ERROR_ALREADY_EXISTS}:
                raise OutputExistsError(f"Output already exists: {output}") from exc
            raise PublishError(f"Could not atomically publish {output}: {exc}") from exc
        validate(output)
        return PublishResult(output=output, temporary=temporary)
    except BaseException:
        # An interrupted process leaves a clearly named temporary file, never a partial final file.
        raise


def _copy_and_sync(source: Path, destination: Path) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_BINARY"):
        flags |= os.O_BINARY
    try:
        descriptor = os.open(destination, flags, 0o600)
    except OSError as exc:
        if exc.errno == 17:
            raise OutputExistsError(f"Temporary output already exists: {destination}") from exc
        raise PublishError(f"Could not create temporary output {destination}: {exc}") from exc
    try:
        with os.fdopen(descriptor, "wb", closefd=True) as destination_handle:
            with source.open("rb") as source_handle:
                shutil.copyfileobj(source_handle, destination_handle, length=1024 * 1024)
            destination_handle.flush()
            os.fsync(destination_handle.fileno())
    except Exception as exc:
        raise PublishError(f"Could not stage output {destination}: {exc}") from exc
