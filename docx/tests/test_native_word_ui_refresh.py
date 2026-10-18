from __future__ import annotations

from pathlib import Path
import sys
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import native_word_ui_refresh as ui_refresh


def _inventory(fields=None, issues=None):
    return {
        "ok": not issues,
        "status": "PASS" if not issues else "UNVERIFIED",
        "fields": fields or [{"kind": "PAGEREF", "instruction": "PAGEREF Heading", "result": "1"}],
        "issues": issues or [],
    }


class _Process:
    def wait(self, timeout=None):
        return 0


class _Gui:
    def IsWindow(self, _hwnd):
        return True

    def PostMessage(self, *_args):
        return None


def _patch_refresh(monkeypatch, tmp_path, *, process_path=None, observed=None, wps_pids=None):
    source = tmp_path / "source.docx"
    output = tmp_path / "output.docx"
    source.write_bytes(b"test docx")
    word_exe = tmp_path / "WINWORD.EXE"
    word_exe.write_bytes(b"word")
    process_path = process_path or word_exe
    observed = observed or {"status": "OBSERVED", "owned_pids": [20]}

    monkeypatch.setattr(ui_refresh, "_imports", lambda: (object(), SimpleNamespace(WM_SYSCOMMAND=0, SC_CLOSE=0), _Gui(), object()))
    monkeypatch.setattr(ui_refresh, "reference_word_server", lambda: word_exe)
    monkeypatch.setattr(ui_refresh, "_field_inventory", lambda *_args, **_kwargs: _inventory())
    monkeypatch.setattr(ui_refresh, "_word_field_results", lambda *_args: {
        "before_field_count": 1, "after_field_count": 1, "toc_count": 0,
        "pageref_count": 1, "pageref_results": ["1"], "word_saved_field_issues": [],
    })
    monkeypatch.setattr(ui_refresh, "_main_window", lambda *_args: 99)
    monkeypatch.setattr(ui_refresh, "_focus_and_send", lambda *_args: None)
    monkeypatch.setattr(ui_refresh, "_handle_toc_update_dialog", lambda *_args: False)
    monkeypatch.setattr(ui_refresh, "_wait_for_file_stable", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(ui_refresh.gate, "_observe_owned_processes", lambda *_args, **_kwargs: observed)
    monkeypatch.setattr(ui_refresh.gate, "_safe_process_executable_path", lambda *_args, **_kwargs: (Path(process_path), None))
    monkeypatch.setattr(ui_refresh.gate, "_wait_for_owned_processes_exit", lambda *_args, **_kwargs: {
        "status": "CLEAN", "owned_pids": [20], "residual_pids": [],
    })

    def process_ids(image):
        if image.casefold() == "winword.exe":
            return [], None
        return list(wps_pids or []), None

    monkeypatch.setattr(ui_refresh.gate, "_safe_process_ids", process_ids)
    monkeypatch.setattr(ui_refresh.subprocess, "Popen", lambda *_args, **_kwargs: _Process())
    monkeypatch.setattr(ui_refresh, "_publish_field_results", lambda _source, _evaluated, destination: destination.write_bytes(b"output"))
    return source, output, word_exe


def test_requires_explicit_ui_permission(tmp_path):
    source = tmp_path / "source.docx"
    source.write_bytes(b"test docx")
    result = ui_refresh.refresh_copy(source, tmp_path / "output.docx")
    assert result["status"] == "UNVERIFIED"
    assert "allow-office-ui" in result["error"]


def test_existing_word_still_blocks(monkeypatch, tmp_path):
    source, output, _word_exe = _patch_refresh(monkeypatch, tmp_path)
    monkeypatch.setattr(ui_refresh.gate, "_safe_process_ids", lambda image: ([123], None) if image == "WINWORD.EXE" else ([], None))
    result = ui_refresh.refresh_copy(source, output, allow_office_ui=True)
    assert result["status"] == "UNSAFE_PROCESS"
    assert "already running" in result["error"]


def test_existing_wps_is_recorded_but_does_not_block(monkeypatch, tmp_path):
    source, output, word_exe = _patch_refresh(monkeypatch, tmp_path, wps_pids=[10, 11])
    result = ui_refresh.refresh_copy(source, output, allow_office_ui=True)
    assert result["status"] == "PASS"
    assert result["ownership"]["preflight_wps_pids"] == [10, 11]
    assert result["ownership"]["process_paths"] == {"20": str(word_exe.resolve())}


def test_no_new_word_pid_is_rejected(monkeypatch, tmp_path):
    source, output, _word_exe = _patch_refresh(
        monkeypatch, tmp_path,
        observed={"status": "NO_NEW_PID", "owned_pids": []},
        wps_pids=[10],
    )
    result = ui_refresh.refresh_copy(source, output, allow_office_ui=True)
    assert result["status"] == "UNVERIFIED"
    assert "did not produce" in result["error"]
    assert not output.exists()


def test_word_pid_path_must_not_be_wps(monkeypatch, tmp_path):
    source, output, _word_exe = _patch_refresh(
        monkeypatch, tmp_path,
        process_path=tmp_path / "wps.exe",
    )
    result = ui_refresh.refresh_copy(source, output, allow_office_ui=True)
    assert result["status"] == "UNVERIFIED"
    assert "does not match registered Word" in result["error"]
    assert not output.exists()


def test_pageref_results_survive_word_hyperlink_wrappers(monkeypatch, tmp_path):
    source = tmp_path / "source.docx"
    evaluated = tmp_path / "evaluated.docx"
    source.write_bytes(b"source")
    evaluated.write_bytes(b"evaluated")
    before = [
        {"kind": "TOC", "instruction": "TOC \\o 1", "result": ""},
        {"kind": "PAGEREF", "instruction": "PAGEREF Heading", "result": "5"},
    ]
    after = before + [{"kind": "HYPERLINK", "instruction": "HYPERLINK \\l Heading", "result": ""}]
    monkeypatch.setattr(ui_refresh, "_field_inventory", lambda path, **_kwargs: _inventory(after if path == evaluated else before))
    result = ui_refresh._word_field_results(source, evaluated)
    assert result["pageref_count"] == 1
    assert result["pageref_results"] == ["5"]

