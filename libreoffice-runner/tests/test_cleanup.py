from __future__ import annotations

import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from _support import WindowsOnlyTestCase
from libreoffice_runner.cleanup import cleanup_abandoned
from libreoffice_runner.win32_sync import FileLock, RUNNER_ID, current_process_identity


class CleanupTests(WindowsOnlyTestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(prefix="lo-runner-cleanup-")
        self.base = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _task(self, *, pid: int, created_at: str, valid_owner: bool = True) -> Path:
        root = self.base / f"sanan-lo-{uuid.uuid4()}"
        root.mkdir()
        (root / "profile").mkdir()
        (root / "active.lock").touch()
        owner = {
            "runner_id": RUNNER_ID if valid_owner else "wrong-runner",
            "schema_version": 1,
            "runner_pid": pid,
            "runner_created_at": created_at,
            "started_at": (datetime.now(timezone.utc) - timedelta(days=2)).isoformat(),
        }
        (root / "owner.json").write_text(__import__("json").dumps(owner), encoding="utf-8")
        return root

    def test_removes_old_dead_task(self) -> None:
        root = self._task(pid=999_999, created_at="2000-01-01T00:00:00+00:00")
        report = cleanup_abandoned(older_than=3600, temp_root=self.base)
        self.assertIn(str(root), report["deleted"])
        self.assertFalse(root.exists())

    def test_skips_live_owner_and_held_active_lock(self) -> None:
        identity = current_process_identity()
        live = self._task(pid=int(identity["pid"]), created_at=str(identity["created_at"]))
        locked = self._task(pid=999_998, created_at="2000-01-01T00:00:00+00:00")
        lock = FileLock.acquire(locked / "active.lock")
        try:
            report = cleanup_abandoned(older_than=3600, temp_root=self.base)
        finally:
            lock.close()
        skipped = {Path(item["path"]).name: item["reason"] for item in report["skipped"]}
        self.assertEqual(skipped[live.name], "owner_process_active")
        self.assertEqual(skipped[locked.name], "active_lock_held")

    def test_skips_unknown_owner_identity(self) -> None:
        unknown = self._task(pid=999_995, created_at="2000-01-01T00:00:00+00:00")
        with patch("libreoffice_runner.cleanup.process_identity_matches", return_value=None):
            report = cleanup_abandoned(older_than=3600, temp_root=self.base)
        skipped = {Path(item["path"]).name: item["reason"] for item in report["skipped"]}
        self.assertEqual(skipped[unknown.name], "owner_identity_unknown")
        self.assertTrue(unknown.exists())

    def test_skips_invalid_owner_and_reparse_point(self) -> None:
        invalid = self._task(pid=999_997, created_at="2000-01-01T00:00:00+00:00", valid_owner=False)
        reparse = self._task(pid=999_996, created_at="2000-01-01T00:00:00+00:00")
        import libreoffice_runner.cleanup as cleanup

        original = cleanup._is_reparse_point
        with patch.object(cleanup, "_is_reparse_point", side_effect=lambda path: path == reparse or original(path)):
            report = cleanup_abandoned(older_than=3600, temp_root=self.base)
        skipped = {Path(item["path"]).name: item["reason"] for item in report["skipped"]}
        self.assertEqual(skipped[invalid.name], "invalid_owner")
        self.assertEqual(skipped[reparse.name], "root_reparse_point")
