import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "run_weekly_skill_review.py"
SPEC = importlib.util.spec_from_file_location("scan_cache_regression", SCRIPT)
REVIEW = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(REVIEW)


def test_scan_snapshot_hashes_each_resolved_tree_once_and_separates_roots(tmp_path, monkeypatch):
    public, private = tmp_path / "public", tmp_path / "private"
    calls = []
    monkeypatch.setattr(REVIEW, "tree_fingerprint", lambda path: calls.append(path) or str(path))

    @REVIEW.with_scan_tree_cache
    def scan_snapshot():
        first = REVIEW.source_fingerprint(public, ["pdf"])
        for _ in range(158):
            assert REVIEW.source_fingerprint(public, ["pdf"]) == first
        assert REVIEW.source_fingerprint(private, ["pdf"]) != first
        return first

    scan_snapshot()
    assert calls == [(public / "pdf").resolve(), (private / "pdf").resolve()]
    scan_snapshot()
    assert len(calls) == 4  # No reuse across consecutive scans.
    assert REVIEW._SCAN_TREE_CACHE.get() is None


def test_execution_drift_check_is_fresh_after_scan(tmp_path):
    skill = tmp_path / "pdf"
    skill.mkdir()
    entry = skill / "SKILL.md"
    entry.write_text("before", encoding="utf-8")

    @REVIEW.with_scan_tree_cache
    def scan_snapshot():
        return REVIEW.source_fingerprint(tmp_path, ["pdf"])

    before = scan_snapshot()
    entry.write_text("after", encoding="utf-8")
    fresh = REVIEW.source_fingerprint(tmp_path, ["pdf"])
    assert fresh != before
    entry.write_text("edited again before approval", encoding="utf-8")
    assert REVIEW.source_fingerprint(tmp_path, ["pdf"]) != fresh


def test_exception_discards_scan_cache(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(REVIEW, "tree_fingerprint", lambda path: calls.append(path) or "value")

    @REVIEW.with_scan_tree_cache
    def broken_scan():
        REVIEW.source_fingerprint(tmp_path, ["pdf"])
        raise RuntimeError("report build failed")

    with pytest.raises(RuntimeError, match="report build"):
        broken_scan()
    assert REVIEW._SCAN_TREE_CACHE.get() is None
    REVIEW.source_fingerprint(tmp_path, ["pdf"])
    assert len(calls) == 2


def test_only_scan_entry_is_scoped():
    assert hasattr(REVIEW.scan_command, "__wrapped__")
    for entry in (REVIEW.record_decision_command, REVIEW.prepare_execution_command, REVIEW.record_execution_command):
        assert not hasattr(entry, "__wrapped__")
