from __future__ import annotations

import subprocess
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

import pywintypes
import winerror
from _support import HELPERS, PYTHON, SCRIPTS, WindowsOnlyTestCase, read_json
from libreoffice_runner.win32_sync import CapacitySlots, process_creation_time


class CapacitySlotTests(WindowsOnlyTestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(prefix="lo-runner-lock-")
        self.root = Path(self.temp_dir.name)
        self.state_root = self.root / "state"
        self.events = self.root / "events"

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _worker(self, *extra: str, hold: float = 0.25, queue_timeout: float = 5.0) -> subprocess.Popen[bytes]:
        command = [
            str(PYTHON),
            str(HELPERS / "spawn_process_tree.py"),
            "slot-worker",
            "--scripts",
            str(SCRIPTS),
            "--state-root",
            str(self.state_root),
            "--event-dir",
            str(self.events),
            "--hold",
            str(hold),
            "--queue-timeout",
            str(queue_timeout),
            *extra,
        ]
        return subprocess.Popen(command)

    def test_five_processes_peak_at_two_and_complete(self) -> None:
        workers = [self._worker(hold=0.3) for _ in range(5)]
        for worker in workers:
            self.assertEqual(worker.wait(timeout=15), 0)
        starts = [read_json(path) for path in self.events.glob("*-start.json")]
        ends = [read_json(path) for path in self.events.glob("*-end.json")]
        self.assertEqual(len(starts), 5)
        self.assertEqual(len(ends), 5)
        intervals = [(float(item["at"]), 1) for item in starts] + [(float(item["at"]), -1) for item in ends]
        active = peak = 0
        for _, delta in sorted(intervals, key=lambda item: (item[0], item[1])):
            active += delta
            peak = max(peak, active)
        self.assertEqual(peak, 2)

    def test_queue_timeout_never_starts_worker(self) -> None:
        slots = CapacitySlots(self.state_root)
        first = slots.acquire(1.0)
        second = slots.acquire(1.0)
        self.assertIsNotNone(first)
        self.assertIsNotNone(second)
        try:
            worker = self._worker(hold=0.1, queue_timeout=0.2)
            self.assertEqual(worker.wait(timeout=5), 2)
            self.assertEqual(list(self.events.glob("*-start.json")), [])
            self.assertEqual(len(list(self.events.glob("*-timeout.json"))), 1)
        finally:
            assert first is not None and second is not None
            first.release()
            second.release()

    def test_crashed_holder_releases_slot(self) -> None:
        worker = self._worker("--crash-after-acquire", hold=1.0)
        self.assertEqual(worker.wait(timeout=5), 23)
        deadline = time.monotonic() + 3.0
        slots = CapacitySlots(self.state_root)
        first = second = None
        while time.monotonic() < deadline:
            first = slots.acquire(0.2)
            if first is not None:
                second = slots.acquire(0.2)
                if second is not None:
                    break
                first.release()
                first = None
            time.sleep(0.05)
        try:
            self.assertIsNotNone(first)
            self.assertIsNotNone(second)
        finally:
            if first is not None:
                first.release()
            if second is not None:
                second.release()

    def test_access_denied_process_creation_is_unknown(self) -> None:
        denied = pywintypes.error(winerror.ERROR_ACCESS_DENIED, "OpenProcess", "Access is denied")
        with patch("libreoffice_runner.win32_sync.win32api.OpenProcess", side_effect=denied):
            self.assertIsNone(process_creation_time(123_456))
