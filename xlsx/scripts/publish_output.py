from __future__ import annotations

import argparse
import ctypes
import errno
import hashlib
import json
import os
import re
import stat
import sys
import tempfile
from pathlib import Path
from typing import BinaryIO, Sequence


EXIT_INTERNAL_ERROR = 1
EXIT_ARGUMENT_ERROR = 2
EXIT_GUARD_REJECTED = 3
EXIT_PUBLISH_FAILED = 4

_SHA256_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")
_FILE_ATTRIBUTE_REPARSE_POINT = 0x0400
_MOVEFILE_REPLACE_EXISTING = 0x00000001
_MOVEFILE_WRITE_THROUGH = 0x00000008
_CHUNK_SIZE = 1024 * 1024


class PublishError(Exception):
    def __init__(self, exit_code: int, error: str, message: str) -> None:
        super().__init__(message)
        self.exit_code = exit_code
        self.error = error
        self.message = message


class JsonArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise PublishError(EXIT_ARGUMENT_ERROR, "argument_error", message)


def _lexical_absolute(path: str | os.PathLike[str]) -> Path:
    return Path(os.path.abspath(os.fspath(path)))


def _path_exists(path: Path) -> bool:
    return os.path.lexists(path)


def _is_reparse_point(path: Path) -> bool:
    path_is_junction = getattr(path, "is_junction", None)
    if path.is_symlink() or (path_is_junction is not None and path_is_junction()):
        return True
    attributes = getattr(os.lstat(path), "st_file_attributes", 0)
    return bool(attributes & _FILE_ATTRIBUTE_REPARSE_POINT)


def _reject_reparse_chain(path: Path, label: str) -> None:
    current = path
    while True:
        if _path_exists(current) and _is_reparse_point(current):
            raise PublishError(
                EXIT_GUARD_REJECTED,
                "reparse_point_rejected",
                f"{label} contains a symbolic link, junction, or reparse point: {current}",
            )
        parent = current.parent
        if parent == current:
            return
        current = parent


def _require_regular_file(path: Path, label: str) -> None:
    if not _path_exists(path):
        raise PublishError(
            EXIT_GUARD_REJECTED,
            f"{label}_missing",
            f"{label} does not exist: {path}",
        )
    _reject_reparse_chain(path, label)
    if not stat.S_ISREG(os.lstat(path).st_mode):
        raise PublishError(
            EXIT_GUARD_REJECTED,
            f"{label}_not_regular_file",
            f"{label} must be a regular file: {path}",
        )


def _require_destination_parent(path: Path) -> None:
    parent = path.parent
    if not _path_exists(parent):
        raise PublishError(
            EXIT_GUARD_REJECTED,
            "destination_parent_missing",
            f"destination parent does not exist: {parent}",
        )
    _reject_reparse_chain(parent, "destination parent")
    if not stat.S_ISDIR(os.lstat(parent).st_mode):
        raise PublishError(
            EXIT_GUARD_REJECTED,
            "destination_parent_not_directory",
            f"destination parent is not a directory: {parent}",
        )


def _canonical_destination(path: Path) -> Path:
    if _path_exists(path):
        return path.resolve(strict=True)
    return path.parent.resolve(strict=True) / path.name


def _reject_same_file(candidate: Path, destination: Path) -> None:
    candidate_canonical = candidate.resolve(strict=True)
    destination_canonical = _canonical_destination(destination)
    same_path = os.path.normcase(str(candidate_canonical)) == os.path.normcase(
        str(destination_canonical)
    )
    if not same_path and _path_exists(destination):
        same_path = os.path.samefile(candidate, destination)
    if same_path:
        raise PublishError(
            EXIT_GUARD_REJECTED,
            "same_path_rejected",
            "candidate and destination must be different files",
        )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(_CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _copy_file_contents(source: BinaryIO, destination: BinaryIO) -> str:
    digest = hashlib.sha256()
    while True:
        chunk = source.read(_CHUNK_SIZE)
        if not chunk:
            return digest.hexdigest()
        destination.write(chunk)
        digest.update(chunk)


def _create_staging_copy(candidate: Path, destination: Path) -> tuple[Path, str]:
    descriptor, raw_stage = tempfile.mkstemp(
        prefix=f".{destination.name}.publish-",
        suffix=".tmp",
        dir=destination.parent,
    )
    stage = Path(raw_stage)
    descriptor_open = True
    try:
        with os.fdopen(descriptor, "wb") as target:
            descriptor_open = False
            with candidate.open("rb") as source:
                copied_sha256 = _copy_file_contents(source, target)
            target.flush()
            os.fsync(target.fileno())
        return stage, copied_sha256
    except BaseException:
        if descriptor_open:
            os.close(descriptor)
        try:
            stage.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def _atomic_publish(stage: Path, destination: Path, *, replace: bool) -> None:
    if os.name == "nt":
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        move_file_ex = kernel32.MoveFileExW
        move_file_ex.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint32]
        move_file_ex.restype = ctypes.c_int
        flags = _MOVEFILE_WRITE_THROUGH
        if replace:
            flags |= _MOVEFILE_REPLACE_EXISTING
        if not move_file_ex(str(stage), str(destination), flags):
            raise ctypes.WinError(ctypes.get_last_error())
        return

    if replace:
        os.replace(stage, destination)
    else:
        os.link(stage, destination)


def _is_destination_exists_error(error: OSError) -> bool:
    return error.errno == errno.EEXIST or getattr(error, "winerror", None) in {80, 183}


def _validate_expected_sha256(value: str | None) -> str | None:
    if value is None:
        return None
    if not _SHA256_PATTERN.fullmatch(value):
        raise PublishError(
            EXIT_ARGUMENT_ERROR,
            "invalid_sha256",
            "--replace-existing-if-sha256 must be exactly 64 hexadecimal characters",
        )
    return value.lower()


def _publish(
    candidate_arg: str | os.PathLike[str],
    destination_arg: str | os.PathLike[str],
    expected_sha256_arg: str | None,
) -> dict[str, object]:
    expected_sha256 = _validate_expected_sha256(expected_sha256_arg)
    candidate = _lexical_absolute(candidate_arg)
    destination = _lexical_absolute(destination_arg)

    _require_regular_file(candidate, "candidate")
    _require_destination_parent(destination)
    _reject_same_file(candidate, destination)
    candidate_canonical = candidate.resolve(strict=True)
    destination_canonical = _canonical_destination(destination)

    destination_exists = _path_exists(destination)
    previous_sha256: str | None = None
    if destination_exists:
        _require_regular_file(destination, "destination")
        if expected_sha256 is None:
            raise PublishError(
                EXIT_GUARD_REJECTED,
                "destination_ownership_unconfirmed",
                "existing destination requires an authorized expected SHA-256",
            )
        previous_sha256 = _sha256_file(destination)
        if previous_sha256 != expected_sha256:
            raise PublishError(
                EXIT_GUARD_REJECTED,
                "destination_sha256_mismatch",
                "destination SHA-256 does not match the recorded draft hash",
            )
    elif expected_sha256 is not None:
        raise PublishError(
            EXIT_ARGUMENT_ERROR,
            "replacement_hash_without_destination",
            "replacement SHA-256 is not allowed when destination does not exist",
        )

    candidate_sha256 = _sha256_file(candidate)
    stage: Path | None = None
    try:
        stage, copied_sha256 = _create_staging_copy(candidate, destination)
        if copied_sha256 != candidate_sha256 or _sha256_file(stage) != copied_sha256:
            raise PublishError(
                EXIT_GUARD_REJECTED,
                "candidate_changed_during_copy",
                "candidate content changed while the staging copy was created",
            )
        if _sha256_file(candidate) != copied_sha256:
            raise PublishError(
                EXIT_GUARD_REJECTED,
                "candidate_changed_before_publish",
                "candidate content changed before publication",
            )

        _require_destination_parent(destination)
        if destination_exists:
            _require_regular_file(destination, "destination")
            current_sha256 = _sha256_file(destination)
            if current_sha256 != expected_sha256:
                raise PublishError(
                    EXIT_GUARD_REJECTED,
                    "destination_changed_before_publish",
                    "destination changed after preflight; publication was refused",
                )
        elif _path_exists(destination):
            raise PublishError(
                EXIT_GUARD_REJECTED,
                "destination_appeared_before_publish",
                "destination appeared after preflight; publication was refused",
            )

        try:
            _atomic_publish(stage, destination, replace=destination_exists)
        except OSError as error:
            if not destination_exists and _is_destination_exists_error(error):
                raise PublishError(
                    EXIT_GUARD_REJECTED,
                    "destination_appeared_during_publish",
                    "another process created the destination; publication was refused",
                ) from error
            raise PublishError(
                EXIT_PUBLISH_FAILED,
                "atomic_publish_failed",
                f"atomic publication failed: {error}",
            ) from error

        return {
            "ok": True,
            "action": "replaced" if destination_exists else "created",
            "candidate_path": str(candidate_canonical),
            "destination_path": str(destination_canonical),
            "previous_sha256": previous_sha256,
            "published_sha256": copied_sha256,
        }
    finally:
        if stage is not None and _path_exists(stage):
            try:
                stage.unlink()
            except OSError:
                pass


def publish_output(
    candidate: str | os.PathLike[str],
    destination: str | os.PathLike[str],
    *,
    replace_existing_if_sha256: str | None = None,
) -> dict[str, object]:
    try:
        return _publish(candidate, destination, replace_existing_if_sha256)
    except PublishError:
        raise
    except OSError as error:
        raise PublishError(
            EXIT_PUBLISH_FAILED,
            "filesystem_error",
            f"filesystem operation failed: {error}",
        ) from error


def _build_parser() -> JsonArgumentParser:
    parser = JsonArgumentParser(description="Publish a verified candidate file safely")
    parser.add_argument("candidate")
    parser.add_argument("destination")
    parser.add_argument(
        "--replace-existing-if-sha256",
        metavar="SHA256",
        help="replace only when the existing destination has this SHA-256",
    )
    return parser


def _display_path(value: str | None) -> str | None:
    return str(_lexical_absolute(value)) if value is not None else None


def _failure_payload(
    error: PublishError,
    candidate: str | None,
    destination: str | None,
) -> dict[str, object]:
    return {
        "ok": False,
        "error": error.error,
        "message": error.message,
        "candidate_path": _display_path(candidate),
        "destination_path": _display_path(destination),
    }


def _write_json(payload: dict[str, object]) -> None:
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n"
    binary_stdout = getattr(sys.stdout, "buffer", None)
    if binary_stdout is None:
        sys.stdout.write(serialized)
        sys.stdout.flush()
        return
    binary_stdout.write(serialized.encode("utf-8"))
    binary_stdout.flush()


def main(argv: Sequence[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    candidate: str | None = None
    destination: str | None = None
    try:
        namespace = _build_parser().parse_args(arguments)
        candidate = namespace.candidate
        destination = namespace.destination
        result = publish_output(
            candidate,
            destination,
            replace_existing_if_sha256=namespace.replace_existing_if_sha256,
        )
    except PublishError as error:
        _write_json(_failure_payload(error, candidate, destination))
        return error.exit_code
    except Exception as error:
        internal = PublishError(
            EXIT_INTERNAL_ERROR,
            "internal_error",
            f"unclassified error: {type(error).__name__}: {error}",
        )
        _write_json(_failure_payload(internal, candidate, destination))
        return internal.exit_code

    _write_json(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
