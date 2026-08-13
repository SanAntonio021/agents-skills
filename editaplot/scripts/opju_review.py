#!/usr/bin/env python
"""Prepare and review user-edited Origin OPJU figures without mutating them.

The public functions in this module deliberately separate filesystem evidence
from Origin Automation.  The caller first creates a stable snapshot; the
worker then opens only that snapshot in a fresh, EditaPlot-owned Origin
instance with ``readonly=True``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from editaplot_core import EditaPlotError, bootstrap_engine


WORKSPACE_SCHEMA_VERSION = "1.0"
REVIEW_REPORT_SCHEMA_VERSION = "1.0"
WORKSPACE_FILENAME = "review-workspace.json"
INITIAL_FILENAME = "figure_initial.opju"
EDIT_FILENAME = "figure_edit.opju"
REVIEW_DIRECTORY_NAME = "review"
SNAPSHOT_FILENAME = "figure_edit_snapshot.opju"
REVIEW_REPORT_FILENAME = "review-report.json"
COPY_CHUNK_SIZE = 1024 * 1024


@dataclass(frozen=True)
class _Workspace:
    """Validated immutable fields of one OPJU review workspace."""

    root: Path
    metadata_path: Path
    source_path: Path
    source_sha256: str
    initial_path: Path
    initial_sha256: str
    edit_path: Path
    edit_initial_sha256: str


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(COPY_CHUNK_SIZE), b""):
                digest.update(chunk)
    except PermissionError as exc:
        raise EditaPlotError(
            "opju_file_locked",
            "The OPJU file is locked or cannot be read. Save and close any blocking operation, then retry.",
            path=str(path),
        ) from exc
    except OSError as exc:
        raise EditaPlotError(
            "opju_file_read_failed",
            "The OPJU file could not be read.",
            path=str(path),
            os_error=type(exc).__name__,
        ) from exc
    return digest.hexdigest()


def _require_opju_file(value: str | Path, *, role: str) -> Path:
    path = Path(value).expanduser()
    try:
        resolved = path.resolve(strict=True)
    except FileNotFoundError as exc:
        raise EditaPlotError(
            "opju_file_missing",
            f"The {role} OPJU file does not exist.",
            path=str(path),
        ) from exc
    except OSError as exc:
        raise EditaPlotError(
            "opju_path_unavailable",
            f"The {role} OPJU path could not be resolved.",
            path=str(path),
            os_error=type(exc).__name__,
        ) from exc
    if not resolved.is_file():
        raise EditaPlotError(
            "opju_not_a_file",
            f"The {role} path is not a file.",
            path=str(resolved),
        )
    if resolved.suffix.casefold() != ".opju":
        raise EditaPlotError(
            "opju_extension_required",
            f"The {role} file must use the .opju extension.",
            path=str(resolved),
        )
    return resolved


def _resolve_output_workspace(source: Path, output_dir: str | Path | None) -> Path:
    candidate = (
        Path(output_dir).expanduser()
        if output_dir is not None
        else source.parent / f"{source.stem}_OriginReview"
    )
    if candidate.is_symlink():
        raise EditaPlotError(
            "opju_workspace_symlink",
            "The OPJU review workspace cannot be an existing symbolic link.",
            workspace_path=str(candidate),
        )
    try:
        resolved = candidate.resolve()
    except OSError as exc:
        raise EditaPlotError(
            "opju_workspace_path_unavailable",
            "The requested OPJU review workspace path could not be resolved.",
            path=str(candidate),
            os_error=type(exc).__name__,
        ) from exc
    # A workspace must not contain the source file.  Checking the direction
    # explicitly prevents a nested output directory from copying its own input.
    if resolved == source or source in resolved.parents:
        raise EditaPlotError(
            "opju_workspace_contains_source",
            "The OPJU review workspace cannot contain the source OPJU file.",
            source_path=str(source),
            workspace_path=str(resolved),
        )
    if resolved.exists():
        raise EditaPlotError(
            "opju_workspace_exists",
            "The OPJU review workspace already exists. Choose a new workspace; existing files are never overwritten.",
            workspace_path=str(resolved),
        )
    return resolved


def _write_new_json(path: Path, payload: dict[str, Any]) -> None:
    try:
        with path.open("x", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
    except FileExistsError as exc:
        raise EditaPlotError(
            "opju_output_exists",
            "Refusing to overwrite an existing OPJU review artifact.",
            path=str(path),
        ) from exc
    except OSError as exc:
        raise EditaPlotError(
            "opju_output_write_failed",
            "The OPJU review report could not be written.",
            path=str(path),
            os_error=type(exc).__name__,
        ) from exc


def _copy_stable(source: Path, target: Path, *, role: str) -> str:
    """Copy a source exactly once and reject any source mutation during the copy."""

    before = _sha256(source)
    digest = hashlib.sha256()
    created = False
    try:
        with source.open("rb") as input_handle, target.open("xb") as output_handle:
            created = True
            for chunk in iter(lambda: input_handle.read(COPY_CHUNK_SIZE), b""):
                output_handle.write(chunk)
                digest.update(chunk)
            output_handle.flush()
            os.fsync(output_handle.fileno())
    except FileExistsError as exc:
        raise EditaPlotError(
            "opju_output_exists",
            "Refusing to overwrite an existing OPJU review artifact.",
            path=str(target),
        ) from exc
    except PermissionError as exc:
        raise EditaPlotError(
            "opju_file_locked",
            "The OPJU file is locked or cannot be read. Save and close any blocking operation, then retry.",
            path=str(source),
            role=role,
        ) from exc
    except OSError as exc:
        raise EditaPlotError(
            "opju_copy_failed",
            "The OPJU file could not be copied into the isolated review workspace.",
            source_path=str(source),
            target_path=str(target),
            role=role,
            os_error=type(exc).__name__,
        ) from exc
    finally:
        # A partial review artifact is ours, never a user input. Remove it on
        # failure so a rerun cannot accidentally interpret it as a completed copy.
        if sys.exc_info()[0] is not None and created:
            try:
                target.unlink(missing_ok=True)
            except OSError:
                pass

    copied = digest.hexdigest()
    after = _sha256(source)
    if before != after or copied != before:
        try:
            target.unlink(missing_ok=True)
        except OSError:
            pass
        raise EditaPlotError(
            "opju_source_changed_during_copy",
            "The OPJU file changed while the review snapshot was being copied. No review was started.",
            path=str(source),
            role=role,
            sha256_before=before,
            sha256_after=after,
            snapshot_sha256=copied,
        )
    return copied


def _path_from_metadata(root: Path, payload: dict[str, Any], key: str) -> Path:
    value = payload.get(key)
    if not isinstance(value, dict) or not isinstance(value.get("path"), str):
        raise EditaPlotError(
            "opju_workspace_invalid",
            "The OPJU review workspace metadata is missing a required path.",
            field=key,
        )
    try:
        path = Path(value["path"]).expanduser().resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise EditaPlotError(
            "opju_workspace_invalid",
            "The OPJU review workspace metadata refers to an unavailable path.",
            field=key,
        ) from exc
    if key in {"figure_initial", "figure_edit"} and path.parent != root:
        raise EditaPlotError(
            "opju_workspace_path_escape",
            "The OPJU review metadata points outside its workspace.",
            field=key,
            path=str(path),
            workspace_path=str(root),
        )
    return path


def _sha_from_metadata(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    digest = value.get("sha256") if isinstance(value, dict) else None
    if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise EditaPlotError(
            "opju_workspace_invalid",
            "The OPJU review workspace metadata is missing a valid SHA-256 value.",
            field=key,
        )
    return digest


def _load_workspace(figure_edit: str | Path) -> _Workspace:
    edit_path = _require_opju_file(figure_edit, role="editable")
    root = edit_path.parent.resolve()
    metadata_path = root / WORKSPACE_FILENAME
    if not metadata_path.is_file():
        raise EditaPlotError(
            "opju_workspace_missing",
            "review-opju requires the review-workspace.json created by prepare-opju-review.",
            figure_edit=str(edit_path),
            expected_workspace_metadata=str(metadata_path),
        )
    try:
        if metadata_path.resolve(strict=True).parent != root:
            raise EditaPlotError(
                "opju_workspace_path_escape",
                "The OPJU review metadata points outside its workspace.",
                metadata_path=str(metadata_path),
                workspace_path=str(root),
            )
    except FileNotFoundError as exc:
        raise EditaPlotError(
            "opju_workspace_invalid",
            "The OPJU review metadata disappeared before it could be read.",
            metadata_path=str(metadata_path),
        ) from exc
    try:
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EditaPlotError(
            "opju_workspace_invalid",
            "The OPJU review workspace metadata could not be read.",
            metadata_path=str(metadata_path),
        ) from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != WORKSPACE_SCHEMA_VERSION:
        raise EditaPlotError(
            "opju_workspace_invalid",
            "The OPJU review workspace metadata has an unsupported schema.",
            metadata_path=str(metadata_path),
        )

    recorded_root = payload.get("workspace_path")
    if not isinstance(recorded_root, str) or Path(recorded_root).expanduser().resolve() != root:
        raise EditaPlotError(
            "opju_workspace_path_mismatch",
            "The OPJU review workspace metadata does not belong to this folder.",
            metadata_path=str(metadata_path),
            workspace_path=str(root),
        )
    source_path = _path_from_metadata(root, payload, "source")
    initial_path = _path_from_metadata(root, payload, "figure_initial")
    recorded_edit = _path_from_metadata(root, payload, "figure_edit")
    if recorded_edit != edit_path or recorded_edit.name != EDIT_FILENAME:
        raise EditaPlotError(
            "opju_edit_path_mismatch",
            "review-opju only accepts the figure_edit.opju created in this workspace.",
            requested_path=str(edit_path),
            recorded_path=str(recorded_edit),
        )
    if initial_path.name != INITIAL_FILENAME:
        raise EditaPlotError(
            "opju_workspace_invalid",
            "The review baseline must be figure_initial.opju.",
            path=str(initial_path),
        )
    if initial_path == recorded_edit:
        raise EditaPlotError(
            "opju_workspace_invalid",
            "The immutable baseline and editable OPJU must be separate files.",
            path=str(initial_path),
        )
    return _Workspace(
        root=root,
        metadata_path=metadata_path,
        source_path=source_path,
        source_sha256=_sha_from_metadata(payload, "source"),
        initial_path=initial_path,
        initial_sha256=_sha_from_metadata(payload, "figure_initial"),
        edit_path=recorded_edit,
        edit_initial_sha256=_sha_from_metadata(payload, "figure_edit"),
    )


def _assert_initial_baseline(workspace: _Workspace) -> None:
    actual = _sha256(workspace.initial_path)
    if actual != workspace.initial_sha256:
        raise EditaPlotError(
            "opju_initial_baseline_changed",
            "figure_initial.opju changed after preparation. Review stopped without opening the editable file.",
            baseline_path=str(workspace.initial_path),
            expected_sha256=workspace.initial_sha256,
            actual_sha256=actual,
        )


def _create_review_directory(root: Path) -> Path:
    parent = root / REVIEW_DIRECTORY_NAME
    if parent.is_symlink():
        raise EditaPlotError(
            "opju_review_directory_symlink",
            "The review directory is a symbolic link; refusing to write outside the workspace.",
            path=str(parent),
        )
    try:
        parent.mkdir(exist_ok=True)
    except OSError as exc:
        raise EditaPlotError(
            "opju_review_directory_failed",
            "The review folder could not be created.",
            path=str(parent),
            os_error=type(exc).__name__,
        ) from exc
    for attempt in range(100):
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")
        suffix = "" if attempt == 0 else f"_{attempt:02d}"
        candidate = parent / f"{timestamp}{suffix}"
        try:
            candidate.mkdir()
            return candidate.resolve()
        except FileExistsError:
            continue
        except OSError as exc:
            raise EditaPlotError(
                "opju_review_directory_failed",
                "The timestamped review folder could not be created.",
                path=str(candidate),
                os_error=type(exc).__name__,
            ) from exc
    raise EditaPlotError(
        "opju_review_directory_collision",
        "A unique timestamped OPJU review folder could not be created.",
        path=str(parent),
    )


def _safe_file_stem(value: str, fallback: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9_-]+", "_", value).strip("._")
    return (stem or fallback)[:64]


def _nonempty_file(path: Path, *, artifact: str) -> None:
    try:
        valid = path.is_file() and path.stat().st_size > 0
    except OSError as exc:
        raise EditaPlotError(
            "opju_export_read_failed",
            "The Origin export could not be verified after writing.",
            path=str(path),
            artifact=artifact,
            os_error=type(exc).__name__,
        ) from exc
    if not valid:
        raise EditaPlotError(
            "opju_export_missing",
            "Origin did not produce a non-empty review export.",
            path=str(path),
            artifact=artifact,
        )


def _export_graph_page(graph: Any, path: Path, *, artifact: str) -> dict[str, Any]:
    try:
        result = graph.save_fig(str(path), type=path.suffix[1:].lower(), replace=False, width=2100)
    except Exception as exc:  # noqa: BLE001 - Origin exceptions are intentionally redacted
        raise EditaPlotError(
            "opju_export_failed",
            "Origin could not export one Graph Page from the read-only snapshot.",
            artifact=artifact,
            path=str(path),
        ) from exc
    if not result:
        raise EditaPlotError(
            "opju_export_failed",
            "Origin could not export one Graph Page from the read-only snapshot.",
            artifact=artifact,
            path=str(path),
        )
    _nonempty_file(path, artifact=artifact)
    return {
        "path": str(path),
        "size_bytes": path.stat().st_size,
        "sha256": _sha256(path),
    }


def _graph_object_inventory(graph: Any) -> dict[str, Any]:
    """Read a compact, non-mutating graph-object inventory."""

    layers: list[dict[str, Any]] = []
    for layer_index, layer in enumerate(graph):
        try:
            plot_count = len(layer.plot_list())
        except Exception:  # noqa: BLE001 - unsupported objects remain visible as unknown
            plot_count = None
        layers.append({"index": layer_index, "plot_count": plot_count})
    try:
        embedded = bool(graph.get_int("isEmbedded"))
    except Exception:  # noqa: BLE001 - inventory must not block an otherwise readable graph
        embedded = None
    return {
        "short_name": str(getattr(graph, "name", "")),
        "long_name": str(getattr(graph, "lname", "")),
        "embedded": embedded,
        "layer_count": len(layers),
        "layers": layers,
        "total_plot_count": sum(
            item["plot_count"] for item in layers if isinstance(item["plot_count"], int)
        ),
    }


def _environment_payload(environment: Any) -> dict[str, Any]:
    to_dict = getattr(environment, "to_dict", None)
    if not callable(to_dict):
        raise EditaPlotError(
            "opju_origin_environment_invalid",
            "The isolated Origin session did not provide version and ownership evidence.",
        )
    payload = to_dict()
    if not isinstance(payload, dict):
        raise EditaPlotError(
            "opju_origin_environment_invalid",
            "The isolated Origin session returned invalid environment evidence.",
        )
    return dict(payload)


def run_review_worker(
    snapshot_path: str | Path,
    output_dir: str | Path,
    *,
    session_factory: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """Open an OPJU snapshot read-only in an EditaPlot-owned Origin process.

    This function must never attach to a user session or save an Origin project.
    ``GPage.save_fig`` is the only Origin write operation and writes only new
    files below ``output_dir``.
    """

    snapshot = _require_opju_file(snapshot_path, role="snapshot")
    target = Path(output_dir).expanduser().resolve()
    if not target.is_dir():
        raise EditaPlotError(
            "opju_review_output_missing",
            "The isolated review output directory does not exist.",
            path=str(target),
        )
    # The snapshot and its exports intentionally share exactly one timestamped
    # review directory.  Do not allow a caller or worker bug to redirect exports
    # to an unrelated folder.
    if snapshot.parent.resolve() != target:
        raise EditaPlotError(
            "opju_review_output_contains_snapshot",
            "Review exports must stay beside the OPJU snapshot in its timestamped directory.",
            snapshot_path=str(snapshot),
            output_path=str(target),
        )

    if session_factory is None:
        try:
            from origin_sciplot.origin_backend.capabilities import ConnectionMode
            from origin_sciplot.origin_backend.session import OriginSession
        except Exception as exc:  # noqa: BLE001 - report an actionable local worker failure
            raise EditaPlotError(
                "opju_origin_worker_import_failed",
                "The fixed EditaPlot Origin runtime could not be loaded for OPJU review.",
            ) from exc
        session_factory = OriginSession
        session_kwargs: dict[str, Any] = {
            "keep_open": False,
            "connection_mode": ConnectionMode.NEW_ISOLATED,
        }
    else:
        # The injected test double accepts the same observable lifecycle contract.
        session_kwargs = {"keep_open": False, "connection_mode": "new_isolated"}

    try:
        session_context = session_factory(**session_kwargs)
        with session_context as session:
            origin = getattr(session, "op", None)
            environment = getattr(session, "environment", None)
            if origin is None or environment is None:
                raise EditaPlotError(
                    "opju_origin_session_invalid",
                    "The isolated Origin session did not initialize correctly.",
                )
            opened = origin.open(str(snapshot), readonly=True, asksave=False)
            if not opened:
                raise EditaPlotError(
                    "opju_snapshot_open_failed",
                    "Origin could not open the isolated OPJU snapshot in read-only mode.",
                    snapshot_path=str(snapshot),
                )
            graphs = list(origin.graph_list("p", True))
            if not graphs:
                raise EditaPlotError(
                    "opju_no_graph_pages",
                    "The OPJU snapshot contains no Graph Pages to review.",
                    snapshot_path=str(snapshot),
                )

            pages: list[dict[str, Any]] = []
            for index, graph in enumerate(graphs, start=1):
                inventory = _graph_object_inventory(graph)
                basename = f"graph-{index:03d}-{_safe_file_stem(inventory['short_name'], f'page-{index:03d}')}"
                exports = {
                    extension: _export_graph_page(
                        graph,
                        target / f"{basename}.{extension}",
                        artifact=extension,
                    )
                    for extension in ("png", "pdf", "tif")
                }
                pages.append({"index": index, "inventory": inventory, "exports": exports})
            return {
                "schema_version": REVIEW_REPORT_SCHEMA_VERSION,
                "ok": True,
                "review_mode": "isolated_readonly_snapshot",
                "origin": _environment_payload(environment),
                "graph_page_count": len(pages),
                "graph_pages": pages,
            }
    except EditaPlotError:
        raise
    except Exception as exc:  # noqa: BLE001 - never expose unredacted COM details
        code = str(getattr(exc, "code", "opju_origin_review_failed"))
        stage = str(getattr(exc, "stage", "review_snapshot"))
        raise EditaPlotError(
            code if re.fullmatch(r"[a-z0-9_]{3,100}", code) else "opju_origin_review_failed",
            "Origin could not review the isolated OPJU snapshot.",
            stage=stage,
        ) from exc


def _worker_command(
    snapshot: Path,
    review_dir: Path,
    *,
    engine_home: str | Path | None,
    python_executable: str | Path | None,
) -> tuple[list[str], dict[str, str], Path]:
    root = bootstrap_engine(engine_home)
    python = str(python_executable or os.environ.get("EDITAPLOT_PYTHON") or sys.executable)
    command = [
        python,
        str(Path(__file__).resolve()),
        "_worker",
        "--snapshot",
        str(snapshot),
        "--output-dir",
        str(review_dir),
    ]
    environment = dict(os.environ)
    source_path = str(root / "src")
    environment["PYTHONPATH"] = source_path + (
        os.pathsep + environment["PYTHONPATH"] if environment.get("PYTHONPATH") else ""
    )
    environment["PYTHONIOENCODING"] = "utf-8"
    return command, environment, root


def _parse_worker_payload(stdout: str) -> dict[str, Any]:
    for line in reversed(stdout.splitlines()):
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    raise EditaPlotError(
        "opju_review_worker_output_invalid",
        "The isolated OPJU review worker did not return a structured result.",
    )


def _validate_worker_artifacts(payload: dict[str, Any], review_dir: Path, snapshot: Path) -> None:
    """Keep worker-reported paths inside the timestamped review directory."""

    try:
        snapshot_resolved = snapshot.resolve(strict=True)
        review_resolved = review_dir.resolve(strict=True)
    except OSError as exc:
        raise EditaPlotError(
            "opju_review_artifact_path_invalid",
            "The isolated OPJU review artifacts could not be resolved.",
            review_directory=str(review_dir),
        ) from exc
    if snapshot_resolved.parent != review_resolved:
        raise EditaPlotError(
            "opju_review_artifact_path_invalid",
            "The OPJU snapshot is outside its timestamped review directory.",
            snapshot_path=str(snapshot_resolved),
            review_directory=str(review_resolved),
        )
    pages = payload.get("graph_pages")
    if not isinstance(pages, list) or not pages:
        raise EditaPlotError(
            "opju_no_graph_pages",
            "The OPJU snapshot contains no Graph Pages to review.",
        )
    expected_formats = {"png", "pdf", "tif"}
    if payload.get("graph_page_count") != len(pages):
        raise EditaPlotError(
            "opju_review_artifact_invalid",
            "The isolated OPJU review worker returned an inconsistent Graph Page count.",
        )
    for page in pages:
        exports = page.get("exports") if isinstance(page, dict) else None
        if not isinstance(exports, dict):
            raise EditaPlotError(
                "opju_review_artifact_invalid",
                "The isolated OPJU review worker returned an invalid export record.",
            )
        if set(exports) != expected_formats:
            raise EditaPlotError(
                "opju_review_artifact_incomplete",
                "Every Graph Page must have PNG, PDF, and TIF exports.",
                expected_formats=sorted(expected_formats),
                actual_formats=sorted(str(key) for key in exports),
            )
        for artifact, item in exports.items():
            path_text = item.get("path") if isinstance(item, dict) else None
            if not isinstance(path_text, str):
                raise EditaPlotError(
                    "opju_review_artifact_invalid",
                    "The isolated OPJU review worker returned an invalid export path.",
                    artifact=artifact,
                )
            try:
                path = Path(path_text).resolve(strict=True)
            except OSError as exc:
                raise EditaPlotError(
                    "opju_review_artifact_missing",
                    "An expected OPJU review export is missing.",
                    artifact=artifact,
                    path=path_text,
                ) from exc
            if path.parent != review_resolved or path == snapshot_resolved:
                raise EditaPlotError(
                    "opju_review_artifact_path_invalid",
                    "An OPJU review export points outside its timestamped review directory.",
                    artifact=artifact,
                    path=str(path),
                    review_directory=str(review_resolved),
                )
            _nonempty_file(path, artifact=str(artifact))
            reported_sha = item.get("sha256")
            if not isinstance(reported_sha, str) or not re.fullmatch(r"[0-9a-f]{64}", reported_sha):
                raise EditaPlotError(
                    "opju_review_artifact_invalid",
                    "The isolated OPJU review worker returned an invalid export hash.",
                    artifact=artifact,
                )
            actual_sha = _sha256(path)
            if actual_sha != reported_sha:
                raise EditaPlotError(
                    "opju_review_artifact_hash_mismatch",
                    "An OPJU review export changed after Origin produced it.",
                    artifact=artifact,
                    path=str(path),
                    reported_sha256=reported_sha,
                    actual_sha256=actual_sha,
                )


def prepare_opju_review(
    result_opju: str | Path,
    *,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Create a new no-overwrite OPJU review workspace from a result OPJU."""

    source = _require_opju_file(result_opju, role="source")
    workspace = _resolve_output_workspace(source, output_dir)
    try:
        workspace.mkdir(parents=True)
    except FileExistsError as exc:
        raise EditaPlotError(
            "opju_workspace_exists",
            "The OPJU review workspace already exists. Existing files are never overwritten.",
            workspace_path=str(workspace),
        ) from exc
    except OSError as exc:
        raise EditaPlotError(
            "opju_workspace_create_failed",
            "The OPJU review workspace could not be created.",
            workspace_path=str(workspace),
            os_error=type(exc).__name__,
        ) from exc

    try:
        initial_path = workspace / INITIAL_FILENAME
        edit_path = workspace / EDIT_FILENAME
        initial_sha256 = _copy_stable(source, initial_path, role="source")
        edit_sha256 = _copy_stable(source, edit_path, role="source")
        if initial_sha256 != edit_sha256:
            raise EditaPlotError(
                "opju_prepare_copy_mismatch",
                "The two OPJU review copies do not have the same source hash.",
                figure_initial_sha256=initial_sha256,
                figure_edit_sha256=edit_sha256,
            )
        payload = {
            "schema_version": WORKSPACE_SCHEMA_VERSION,
            "workflow": "opju_collaboration_review",
            "workspace_path": str(workspace),
            "source": {"path": str(source), "sha256": initial_sha256},
            "figure_initial": {
                "path": str(initial_path),
                "sha256": initial_sha256,
                "immutable_baseline": True,
            },
            "figure_edit": {
                "path": str(edit_path),
                "sha256": edit_sha256,
                "role": "user_editable_only",
            },
            "review_policy": {
                "source_overwrite": False,
                "edit_overwrite": False,
                "origin_open_mode": "readonly_snapshot_only",
                "origin_attachment": "forbidden",
                "origin_project_save": "forbidden",
                "review_subdirectory": REVIEW_DIRECTORY_NAME,
            },
        }
        _write_new_json(workspace / WORKSPACE_FILENAME, payload)
        return {
            "schema_version": WORKSPACE_SCHEMA_VERSION,
            "ok": True,
            "workflow": "opju_collaboration_review_prepared",
            "workspace_path": str(workspace),
            "figure_initial": {"path": str(initial_path), "sha256": initial_sha256},
            "figure_edit": {"path": str(edit_path), "sha256": edit_sha256},
            "workspace_metadata": str(workspace / WORKSPACE_FILENAME),
            "next_step": "Open figure_edit.opju in Origin, edit and save it. Run review-opju only after the user says it is saved and ready for review.",
        }
    except BaseException:
        # Remove only known artifacts. Never recursively delete a directory
        # that another process may have populated after workspace creation.
        for artifact in (
            workspace / INITIAL_FILENAME,
            workspace / EDIT_FILENAME,
            workspace / WORKSPACE_FILENAME,
        ):
            try:
                artifact.unlink(missing_ok=True)
            except OSError:
                pass
        try:
            workspace.rmdir()
        except OSError:
            pass
        raise


def review_opju(
    figure_edit_opju: str | Path,
    *,
    engine_home: str | Path | None = None,
    python_executable: str | Path | None = None,
) -> dict[str, Any]:
    """Snapshot a saved editable OPJU and review the snapshot in isolated Origin."""

    workspace = _load_workspace(figure_edit_opju)
    _assert_initial_baseline(workspace)
    review_dir = _create_review_directory(workspace.root)
    snapshot = review_dir / SNAPSHOT_FILENAME
    snapshot_sha256 = _copy_stable(workspace.edit_path, snapshot, role="figure_edit")
    _assert_initial_baseline(workspace)

    command, environment, engine_root = _worker_command(
        snapshot,
        review_dir,
        engine_home=engine_home,
        python_executable=python_executable,
    )
    try:
        completed = subprocess.run(  # noqa: S603 - fixed local worker, never shell=True
            command,
            cwd=str(engine_root),
            env=environment,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except PermissionError as exc:
        raise EditaPlotError(
            "opju_review_worker_permission_denied",
            "Windows blocked the isolated OPJU review worker.",
        ) from exc
    except OSError as exc:
        raise EditaPlotError(
            "opju_review_worker_start_failed",
            "The isolated OPJU review worker could not be started.",
            os_error=type(exc).__name__,
        ) from exc

    worker_payload = _parse_worker_payload(completed.stdout)
    if completed.returncode != 0 or not worker_payload.get("ok"):
        error = worker_payload.get("error") if isinstance(worker_payload.get("error"), dict) else {}
        raise EditaPlotError(
            str(error.get("code", "opju_review_worker_failed")),
            str(error.get("message", "The isolated OPJU review worker failed.")),
            review_directory=str(review_dir),
            worker_returncode=completed.returncode,
        )

    _assert_initial_baseline(workspace)
    current_edit_sha256 = _sha256(workspace.edit_path)
    if current_edit_sha256 != snapshot_sha256:
        raise EditaPlotError(
            "opju_edit_changed_during_review",
            "figure_edit.opju changed after its review snapshot was created. Review results were not accepted.",
            figure_edit_path=str(workspace.edit_path),
            snapshot_sha256=snapshot_sha256,
            current_sha256=current_edit_sha256,
            review_directory=str(review_dir),
        )
    _validate_worker_artifacts(worker_payload, review_dir, snapshot)
    if _sha256(snapshot) != snapshot_sha256:
        raise EditaPlotError(
            "opju_snapshot_changed_during_review",
            "The isolated OPJU snapshot changed during review. Review results were not accepted.",
            snapshot_path=str(snapshot),
            expected_sha256=snapshot_sha256,
        )

    report = {
        "schema_version": REVIEW_REPORT_SCHEMA_VERSION,
        "ok": True,
        "workflow": "opju_collaboration_review",
        "review_directory": str(review_dir),
        "workspace": {
            "path": str(workspace.root),
            "metadata_path": str(workspace.metadata_path),
            "source": {"path": str(workspace.source_path), "sha256": workspace.source_sha256},
            "figure_initial": {
                "path": str(workspace.initial_path),
                "sha256": workspace.initial_sha256,
                "integrity": "unchanged",
            },
            "figure_edit": {
                "path": str(workspace.edit_path),
                "initial_sha256": workspace.edit_initial_sha256,
                "reviewed_sha256": snapshot_sha256,
                "integrity_after_review": "unchanged",
            },
        },
        "snapshot": {
            "path": str(snapshot),
            "sha256": snapshot_sha256,
            "integrity": "unchanged",
        },
        "origin": worker_payload.get("origin"),
        "graph_page_count": worker_payload.get("graph_page_count"),
        "graph_pages": worker_payload.get("graph_pages"),
        "review_scope": {
            "opens_user_project": False,
            "open_mode": "readonly=True",
            "connection_mode": "new_isolated",
            "attach_existing": False,
            "origin_project_save": False,
            "exports_meaning": "readback_and_viewable_only",
            "scientific_and_visual_review": "required_after_export",
        },
        "human_visual_qa": {
            "status": "pending",
            "required_checks": [
                "scientific claim and data meaning",
                "axis direction, labels, units, and scales",
                "font, line-weight, color, clipping, and unintended objects",
                "readability at intended publication size",
            ],
        },
    }
    _write_new_json(review_dir / REVIEW_REPORT_FILENAME, report)
    return report


def _worker_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=argparse.SUPPRESS)
    parser.add_argument("--snapshot", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args(argv)
    try:
        payload = run_review_worker(args.snapshot, args.output_dir)
    except EditaPlotError as exc:
        print(json.dumps(exc.to_dict(), ensure_ascii=False), flush=True)
        return 2
    except Exception:  # noqa: BLE001 - keep COM/runtime details out of worker output
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": {
                        "code": "opju_origin_review_unexpected",
                        "message": "The isolated OPJU review worker failed unexpectedly.",
                    },
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
        return 2
    print(json.dumps(payload, ensure_ascii=False), flush=True)
    return 0


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if not arguments or arguments[0] != "_worker":
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": {
                        "code": "opju_review_worker_private",
                        "message": "This worker is started only by the EditaPlot CLI.",
                    },
                }
            ),
            file=sys.stderr,
        )
        return 2
    return _worker_main(arguments[1:])


if __name__ == "__main__":
    raise SystemExit(main())
