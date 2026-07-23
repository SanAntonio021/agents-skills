from __future__ import annotations

import os
import subprocess
import tempfile
import time
from pathlib import Path

from _support import HELPERS, PYTHON, WindowsOnlyTestCase, pid_is_alive, read_json, wait_for_path
from libreoffice_runner.win32_job import launch_suspended_in_job


class JobObjectTests(WindowsOnlyTestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(prefix="lo-runner-job-")
        self.root = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_timeout_terminates_owned_tree_but_not_unrelated_process(self) -> None:
        pid_file = self.root / "job-pids.json"
        process = launch_suspended_in_job(
            [
                str(PYTHON),
                str(HELPERS / "spawn_process_tree.py"),
                "tree-parent",
                "--pid-file",
                str(pid_file),
                "--hold",
                "30",
            ],
            cwd=self.root,
            environment=dict(os.environ),
            stdout_path=self.root / "stdout.txt",
            stderr_path=self.root / "stderr.txt",
        )
        unrelated = subprocess.Popen(
            [str(PYTHON), str(HELPERS / "spawn_process_tree.py"), "tree-child", "--hold", "30"]
        )
        try:
            wait_for_path(pid_file)
            pids = read_json(pid_file)
            owned = {int(pids["parent"]), *(int(pid) for pid in pids["children"])}
            deadline = time.monotonic() + 3.0
            while not owned.issubset(set(process.active_pids())) and time.monotonic() < deadline:
                time.sleep(0.05)
            self.assertTrue(owned.issubset(set(process.active_pids())))
            process.terminate()
            self.assertTrue(process.wait_for_empty(time.monotonic() + 10.0))
            for pid in owned:
                self.assertFalse(pid_is_alive(pid), pid)
            self.assertIsNone(unrelated.poll())
        finally:
            try:
                process.close()
            finally:
                if unrelated.poll() is None:
                    unrelated.terminate()
                unrelated.wait(timeout=5)
