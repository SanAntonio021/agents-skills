from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch

from _support import HELPERS, PYTHON, SCRIPTS, WindowsOnlyTestCase, read_json
from libreoffice_runner.publish import publish_exclusive


class PublishTests(WindowsOnlyTestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(prefix="lo-runner-publish-")
        self.root = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_two_processes_competing_for_output_allow_exactly_one(self) -> None:
        source_a = self.root / "a.bin"
        source_b = self.root / "b.bin"
        output = self.root / "result.bin"
        source_a.write_bytes(b"a" * 500_000)
        source_b.write_bytes(b"b" * 500_000)
        result_a = self.root / "a.json"
        result_b = self.root / "b.json"
        workers = []
        for source, result in ((source_a, result_a), (source_b, result_b)):
            workers.append(
                subprocess.Popen(
                    [
                        str(PYTHON),
                        str(HELPERS / "spawn_process_tree.py"),
                        "publish-worker",
                        "--scripts",
                        str(SCRIPTS),
                        "--source",
                        str(source),
                        "--output",
                        str(output),
                        "--result",
                        str(result),
                    ]
                )
            )
        exits = sorted(worker.wait(timeout=10) for worker in workers)
        self.assertEqual(exits, [0, 3])
        self.assertTrue(output.is_file())
        self.assertIn(output.read_bytes(), {source_a.read_bytes(), source_b.read_bytes()})
        results = [read_json(result_a), read_json(result_b)]
        self.assertEqual(sum(bool(item["ok"]) for item in results), 1)

    def test_interrupted_copy_leaves_only_identifiable_temporary_file(self) -> None:
        source = self.root / "source.bin"
        output = self.root / "result.bin"
        source.write_bytes(b"source")

        def interrupt_copy(_source: Path, temporary: Path) -> None:
            temporary.write_bytes(b"partial")
            raise KeyboardInterrupt()

        with patch("libreoffice_runner.publish._copy_and_sync", side_effect=interrupt_copy):
            with self.assertRaises(KeyboardInterrupt):
                publish_exclusive(source, output, lambda candidate: None)
        self.assertFalse(output.exists())
        temporary = list(self.root.glob(".result.bin.tmp-*"))
        self.assertEqual(len(temporary), 1)
        self.assertEqual(temporary[0].read_bytes(), b"partial")
