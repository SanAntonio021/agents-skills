"""Refresh a DOCX through a directly launched Microsoft Word UI instance.

This is the Windows fallback for hosts where WPS hijacks Word COM activation.
It never attaches to an existing Word process and never terminates a process;
only the task-owned Word window is closed through its normal window command.
"""

from __future__ import annotations

import argparse
import ctypes
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time
from typing import Any

import reference_fields
import office_native_gate as gate


class UiRefreshFailure(RuntimeError):
    def __init__(self, status: str, message: str) -> None:
        super().__init__(message)
        self.status = status


def _imports() -> tuple[Any, Any, Any]:
    try:
        import uiautomation as ui
        import win32con
        import win32gui
        import win32process
    except ImportError as exc:
        raise UiRefreshFailure(
            "APP_UNAVAILABLE",
            f"direct Word UI automation dependencies are unavailable: {exc}",
        ) from exc
    return ui, win32con, win32gui, win32process


def _window_handles(pid: int, win32gui: Any, win32process: Any) -> list[int]:
    handles: list[int] = []

    def visit(hwnd: int, _extra: object) -> bool:
        try:
            if win32gui.IsWindowVisible(hwnd):
                _thread_id, window_pid = win32process.GetWindowThreadProcessId(hwnd)
                if window_pid == pid:
                    handles.append(hwnd)
        except Exception:
            pass
        return True

    win32gui.EnumWindows(visit, None)
    return handles


def _main_window(pid: int, win32gui: Any, win32process: Any, timeout_seconds: float) -> int:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        for hwnd in _window_handles(pid, win32gui, win32process):
            if win32gui.GetClassName(hwnd) == "OpusApp":
                return hwnd
        time.sleep(0.1)
    raise UiRefreshFailure("UNVERIFIED", "Microsoft Word window was not observed")


def _modal_windows(pid: int, main_hwnd: int, win32gui: Any, win32process: Any) -> list[int]:
    return [
        hwnd for hwnd in _window_handles(pid, win32gui, win32process)
        if hwnd != main_hwnd
    ]


def _handle_toc_update_dialog(pid: int, main_hwnd: int, ui: Any, win32gui: Any, win32process: Any) -> bool:
    """Handle Word's localized TOC update prompt without matching translated text."""

    for hwnd in _modal_windows(pid, main_hwnd, win32gui, win32process):
        if win32gui.GetClassName(hwnd) != "bosa_sdm_msword":
            raise UiRefreshFailure(
                "UNVERIFIED",
                f"unexpected Microsoft Word modal dialog: {win32gui.GetClassName(hwnd)}",
            )
        dialog = ui.ControlFromHandle(hwnd)
        children = dialog.GetChildren()
        radios = [child for child in children if child.ControlTypeName == "RadioButtonControl"]
        buttons = [child for child in children if child.ControlTypeName == "ButtonControl"]
        if len(radios) != 2 or len(buttons) != 2:
            raise UiRefreshFailure(
                "UNVERIFIED",
                "unrecognized Microsoft Word update dialog; refusing to guess a choice",
            )
        # Word's first radio button is the localized "update page numbers only" choice.
        radios[0].Click()
        buttons[0].Click()
        return True
    return False


def _activate_window(main_hwnd: int, win32gui: Any, win32process: Any) -> None:
    foreground = win32gui.GetForegroundWindow()
    current_thread = ctypes.windll.kernel32.GetCurrentThreadId()
    foreground_thread = win32process.GetWindowThreadProcessId(foreground)[0] if foreground else 0
    attached = bool(foreground_thread and foreground_thread != current_thread)
    user32 = ctypes.windll.user32
    if attached:
        user32.AttachThreadInput(current_thread, foreground_thread, True)
    try:
        win32gui.ShowWindow(main_hwnd, 5)
        win32gui.BringWindowToTop(main_hwnd)
        win32gui.SetForegroundWindow(main_hwnd)
    finally:
        if attached:
            user32.AttachThreadInput(current_thread, foreground_thread, False)
    if win32gui.GetForegroundWindow() != main_hwnd:
        raise OSError("Word window did not become the foreground window")


def _focus_and_send(main_hwnd: int, ui: Any, win32gui: Any, win32process: Any, keys: str) -> None:
    try:
        _activate_window(main_hwnd, win32gui, win32process)
        time.sleep(0.25)
        ui.SendKeys(keys, waitTime=0.25)
    except Exception as exc:
        raise UiRefreshFailure("UNVERIFIED", f"could not send Word UI command {keys!r}: {exc}") from exc


def _wait_for_file_stable(path: Path, timeout_seconds: float, *, initial: tuple[int, int] | None = None) -> None:
    deadline = time.monotonic() + timeout_seconds
    previous: tuple[int, int] | None = None
    stable = 0
    changed = initial is None
    while time.monotonic() < deadline:
        try:
            stat = path.stat()
            current = (stat.st_size, stat.st_mtime_ns)
        except OSError:
            current = None
        if current is not None and initial is not None and current != initial:
            changed = True
        if changed and current is not None and current == previous:
            stable += 1
            if stable >= 3:
                return
        else:
            stable = 0
            previous = current
        time.sleep(0.25)
    raise UiRefreshFailure("UNVERIFIED", f"Word did not finish saving {path}")


def _field_inventory(path: Path, *, strict: bool = True) -> dict[str, Any]:
    try:
        inventory = reference_fields.inspect_document(path)
    except Exception as exc:
        raise UiRefreshFailure("UNVERIFIED", f"could not inspect Word output fields: {exc}") from exc
    if strict and not inventory.get("ok"):
        raise UiRefreshFailure("UNVERIFIED", f"output field structure is unsafe: {inventory.get('issues')}")
    return inventory


def _field_key(field: dict[str, Any]) -> tuple[Any, ...]:
    return (
        field.get("story"), field.get("ordinal"), field.get("instruction"),
        field.get("kind"), field.get("parent_ordinal"), field.get("parent_phase"),
    )


def _word_field_results(source: Path, evaluated: Path) -> dict[str, Any]:
    """Read Word's PAGEREF results while allowing Word's TOC hyperlink wrappers."""

    before = _field_inventory(source)
    after = _field_inventory(evaluated, strict=False)
    before_pages = [item for item in before.get("fields", []) if item.get("kind") == "PAGEREF"]
    after_pages = [item for item in after.get("fields", []) if item.get("kind") == "PAGEREF"]
    if [item.get("instruction") for item in before_pages] != [item.get("instruction") for item in after_pages]:
        raise UiRefreshFailure("UNVERIFIED", "Word changed the PAGEREF field inventory during UI refresh")
    if not before_pages or any(not str(item.get("result", "")).strip() for item in after_pages):
        raise UiRefreshFailure("UNVERIFIED", "one or more PAGEREF results are empty after Word refresh")
    allowed_word_issues = {
        "Unsupported nested field parent",
        "Unsupported structured/nested field",
    }
    unexpected = [
        issue for issue in after.get("issues", [])
        if not any(issue.startswith(prefix) for prefix in allowed_word_issues)
    ]
    if unexpected:
        raise UiRefreshFailure("UNVERIFIED", f"unexpected field structure after Word save: {unexpected}")
    return {
        "before_field_count": len(before.get("fields", [])),
        "after_field_count": len(after.get("fields", [])),
        "toc_count": sum(item.get("kind") == "TOC" for item in before.get("fields", [])),
        "pageref_count": len(after_pages),
        "pageref_results": [item.get("result") for item in after_pages],
        "word_saved_field_issues": after.get("issues", []),
    }


def _publish_field_results(source: Path, evaluated: Path, output: Path) -> None:
    """Transplant only Word-evaluated PAGEREF text into the protected source structure."""

    baseline = reference_fields.Inventory(reference_fields.guard.DocxPackage.from_path(source))
    saved = reference_fields.Inventory(reference_fields.guard.DocxPackage.from_path(evaluated))
    baseline.require_safe()
    source_pages = [field for field in baseline.fields if field.kind == "PAGEREF"]
    saved_pages = [field for field in saved.fields if field.kind == "PAGEREF"]
    if [field.instruction for field in source_pages] != [field.instruction for field in saved_pages]:
        raise UiRefreshFailure("UNVERIFIED", "Word PAGEREF identity mapping is not one-to-one")
    for source_field, saved_field in zip(source_pages, saved_pages):
        if not saved_field.text.strip():
            raise UiRefreshFailure("UNVERIFIED", f"Word returned an empty PAGEREF result: {saved_field.key}")
        if re.search(r"Error!|错误[!！]|未定义书签|未找到引用源", saved_field.text, re.I):
            raise UiRefreshFailure("UNVERIFIED", f"Word reported an invalid reference: {saved_field.key}")
        reference_fields.set_result(source_field, saved_field.text)
    reference_fields.publish(baseline.updated(), output)


def refresh_copy(
    source: str | Path,
    output: str | Path,
    *,
    allow_office_ui: bool = False,
    timeout_seconds: float = 60.0,
) -> dict[str, Any]:
    """Refresh fields in a new output using a directly launched Word process."""

    source = Path(source).expanduser().resolve()
    output = Path(output).expanduser().absolute()
    result: dict[str, Any] = {
        "ok": False,
        "status": "UNVERIFIED",
        "engine": "word-ui",
        "source": str(source),
        "output": str(output),
        "phase": "preflight",
        "ownership": {},
    }
    workspace: Path | None = None
    owned_pids: list[int] = []
    main_hwnd: int | None = None
    before_hash: str | None = None
    registered_word: Path | None = None
    launched_process: Any | None = None
    verified_owned_pids: list[int] = []
    win32con: Any | None = None
    win32gui: Any | None = None
    win32process: Any | None = None
    try:
        if not allow_office_ui:
            raise UiRefreshFailure("UNVERIFIED", "pass --allow-office-ui for this Word UI operation")
        if not source.is_file() or source.suffix.lower() != ".docx":
            raise UiRefreshFailure("INVALID_INPUT", "source must be an existing .docx file")
        if output.exists() or source == output.resolve():
            raise UiRefreshFailure("OUTPUT_EXISTS", "output must be a new path")
        before_hash = gate.sha256(source)
        result["source_sha256_before"] = before_hash
        inventory = _field_inventory(source)
        relevant = [item for item in inventory["fields"] if item.get("kind") in reference_fields.INTERNAL]
        if not relevant:
            raise UiRefreshFailure("NOT_APPLICABLE", "no internal fields require native refresh")

        ui, win32con, win32gui, win32process = _imports()
        registered_word = Path(reference_word_server()).resolve()
        before_word, before_error = gate._safe_process_ids("WINWORD.EXE")
        if before_word is None:
            raise UiRefreshFailure("UNVERIFIED", f"could not inspect existing Word processes: {before_error}")
        if before_word:
            result["ownership"]["preflight_word_pids"] = before_word
            raise UiRefreshFailure("UNSAFE_PROCESS", "WINWORD.EXE is already running; refusing to attach or close it")
        wps, wps_error = gate._safe_process_ids("wps.exe")
        result["ownership"]["preflight_wps_pids"] = wps or []
        if wps_error:
            result["ownership"]["preflight_wps_error"] = wps_error

        workspace = Path(tempfile.mkdtemp(prefix="codex-word-ui_"))
        isolated = workspace / source.name
        # Keep the disposable package byte-for-byte identical before Word opens
        # it. The UI action below is the only field-refresh operation.
        shutil.copy2(source, isolated)
        if gate.sha256(source) != before_hash:
            raise UiRefreshFailure("SOURCE_CHANGED", "source changed while creating the Word UI copy")

        result["phase"] = "launch"
        launched_process = subprocess.Popen(
            [str(registered_word), "/n", "/q", str(isolated)],
            close_fds=True,
        )
        observed = gate._observe_owned_processes(
            "WINWORD.EXE", before_word, timeout_seconds=min(10.0, timeout_seconds),
        )
        if observed["status"] != "OBSERVED":
            raise UiRefreshFailure("UNVERIFIED", "direct Word launch did not produce an observable task-owned PID")
        owned_pids = observed["owned_pids"]
        result["ownership"]["owned_pids"] = owned_pids
        paths: dict[str, str] = {}
        for pid in owned_pids:
            path, path_error = gate._safe_process_executable_path(pid)
            if path is None:
                raise UiRefreshFailure("UNVERIFIED", f"could not verify Word PID {pid}: {path_error}")
            paths[str(pid)] = str(path)
            if str(path).casefold() != str(registered_word).casefold():
                raise UiRefreshFailure("UNVERIFIED", f"Word PID {pid} path does not match registered Word")
            verified_owned_pids.append(pid)
        result["ownership"]["process_paths"] = paths
        if len(owned_pids) != 1:
            raise UiRefreshFailure("UNVERIFIED", f"expected exactly one task-owned Word PID, got {owned_pids}")

        pid = owned_pids[0]
        main_hwnd = _main_window(pid, win32gui, win32process, min(20.0, timeout_seconds))
        result["ownership"]["main_window"] = main_hwnd
        result["phase"] = "refresh"
        _focus_and_send(main_hwnd, ui, win32gui, win32process, "{Ctrl}a{F9}")
        time.sleep(1.0)
        handled_dialog = _handle_toc_update_dialog(pid, main_hwnd, ui, win32gui, win32process)
        if handled_dialog:
            time.sleep(5.0)
        result["ui_actions"] = {
            "select_all": True,
            "update_fields": True,
            "toc_dialog": "page_numbers_only" if handled_dialog else "not_shown",
        }
        initial_save_signature = None
        try:
            stat = isolated.stat()
            initial_save_signature = (stat.st_size, stat.st_mtime_ns)
        except OSError:
            pass
        _focus_and_send(main_hwnd, ui, win32gui, win32process, "{Ctrl}s")
        _wait_for_file_stable(isolated, min(20.0, timeout_seconds), initial=initial_save_signature)
        result["field_verification"] = _word_field_results(source, isolated)

        result["phase"] = "close"
        if not win32gui.IsWindow(main_hwnd):
            raise UiRefreshFailure("UNVERIFIED", "Word main window disappeared before normal close")
        win32gui.PostMessage(main_hwnd, win32con.WM_SYSCOMMAND, win32con.SC_CLOSE, 0)
        exit_record = gate._wait_for_owned_processes_exit(
            "WINWORD.EXE", owned_pids, timeout_seconds=min(20.0, timeout_seconds),
        )
        result["ownership"]["cleanup"] = exit_record
        if exit_record["status"] != "CLEAN":
            raise UiRefreshFailure("UNVERIFIED", "task-owned Word process did not exit cleanly")
        launched_process.wait(timeout=5)

        output.parent.mkdir(parents=True, exist_ok=True)
        _publish_field_results(source, isolated, output)
        final_inventory = _field_inventory(output)
        final_pages = [item for item in final_inventory["fields"] if item.get("kind") == "PAGEREF"]
        if len(final_pages) != result["field_verification"]["pageref_count"]:
            raise UiRefreshFailure("UNVERIFIED", "published output lost PAGEREF fields")
        result["published_field_verification"] = {
            "status": final_inventory["status"],
            "pageref_count": len(final_pages),
            "pageref_results": [item.get("result") for item in final_pages],
        }
        result["evaluation_sha256"] = gate.sha256(output)
        result["phase"] = "complete"
        result.update(ok=True, status="PASS")
    except UiRefreshFailure as exc:
        result["status"] = exc.status
        result["error"] = str(exc)
    except Exception as exc:
        result["status"] = "UNVERIFIED"
        result["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        if before_hash is not None:
            try:
                result["source_sha256_after"] = gate.sha256(source)
                if result["source_sha256_after"] != before_hash:
                    result.update(ok=False, status="SOURCE_CHANGED", error="source hash changed during Word UI refresh")
            except Exception as exc:
                result.update(ok=False, status="SOURCE_CHANGED", error=f"could not re-hash source: {exc}")
        cleanup = result.get("ownership", {}).get("cleanup", {})
        if launched_process is not None and registered_word is not None:
            try:
                if launched_process.poll() is None:
                    path, path_error = gate._safe_process_executable_path(int(launched_process.pid))
                    if path is not None and str(path).casefold() == str(registered_word).casefold():
                        if int(launched_process.pid) not in verified_owned_pids:
                            verified_owned_pids.append(int(launched_process.pid))
                        result["ownership"]["launcher_pid"] = int(launched_process.pid)
                        result["ownership"].setdefault("process_paths", {})[
                            str(launched_process.pid)
                        ] = str(path)
                    else:
                        result["ownership"]["launcher_path_error"] = path_error or (
                            f"launcher PID path did not match {registered_word}"
                        )
            except Exception as exc:
                result["ownership"]["launcher_path_error"] = str(exc)

        if verified_owned_pids and cleanup.get("status") != "CLEAN":
            close_requests: list[dict[str, Any]] = []
            cleanup_pids: list[int] = []
            for pid in verified_owned_pids:
                try:
                    path, path_error = gate._safe_process_executable_path(pid)
                    if path is None or str(path).casefold() != str(registered_word).casefold():
                        close_requests.append({
                            "pid": pid,
                            "status": "SKIPPED_UNVERIFIED",
                            "reason": path_error or f"process path no longer matches {registered_word}",
                        })
                        continue
                    cleanup_pids.append(pid)
                    close_requests.append(gate._request_process_close(pid))
                except Exception as exc:
                    close_requests.append({"pid": pid, "status": "FAILED", "reason": str(exc)})
            result["ownership"]["cleanup_close_requests"] = close_requests
            if cleanup_pids:
                try:
                    result["ownership"]["cleanup"] = gate._wait_for_owned_processes_exit(
                        "WINWORD.EXE", cleanup_pids, timeout_seconds=5.0,
                    )
                except Exception as exc:
                    result["ownership"]["cleanup_error"] = str(exc)
        if workspace is not None:
            if result.get("ok") and not owned_pids:
                shutil.rmtree(workspace, ignore_errors=True)
            elif result.get("ok"):
                # A successful run has already proven the owned process exited.
                shutil.rmtree(workspace, ignore_errors=True)
            else:
                result["retained_workspace"] = str(workspace)
    return result


def reference_word_server() -> Path:
    """Read the registered Microsoft Word executable without activating COM."""

    from reference_word import _registered_word_server

    return _registered_word_server("Word.Application")


def reference_word_prepare_copy(source: Path, isolated: Path) -> None:
    """Prepare only the disposable copy; never rewrite the source document."""

    from reference_word import _prepare_copy

    _prepare_copy(source, isolated)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--allow-office-ui", action="store_true")
    parser.add_argument("--record", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    result = refresh_copy(args.source, args.output, allow_office_ui=args.allow_office_ui)
    if args.record:
        args.record.parent.mkdir(parents=True, exist_ok=True)
        args.record.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
