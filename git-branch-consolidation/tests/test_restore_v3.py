"""New root-only cache records and historical recovery remain independently usable."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from test_recovery_flow import TemporaryGitCase, VERIFY, run, write, verify_module, fs


class RootRecordRestoreTests(TemporaryGitCase):
    def state(self, version=2):
        state = self.root / "state"
        state.mkdir(exist_ok=True)
        disposition = {"preserve": [], "reproducible": ["build-cache"]}
        if version == 2:
            disposition.update(schemaVersion=2, rebuild={"build-cache": "Rebuild from locked test inputs"})
        write(state / "ignored-disposition.json", json.dumps(disposition))
        write(state / "ls-files-stage.z", "")
        for category in ("tracked-current", "untracked", "ignored-preserved"):
            write(state / f"{category}-manifest.json", "[]")
        if version == 2:
            original = self.root / "original"
            (original / "build-cache").mkdir(parents=True, exist_ok=True)
            records = fs.reproducible_roots_metadata(original, disposition)
            write(state / "ignored-reproducible-roots.json", json.dumps(records))
        else:
            write(state / "ignored-reproducible-manifest.json", "[]")
        return state

    def test_new_lightweight_restore_does_not_require_original_or_run_rebuild(self):
        repo, _, _ = self.create_repository(feature=False)
        write(repo / "build-cache" / "large.bin", "reproducible contents\n" * 1000)
        write(repo / "preserve-cache" / "experiment.csv", "Power,BER\n-10,0.000123456789\n")
        write(repo / "untracked.txt", "useful work\n")
        marker = self.root / "rebuild-must-not-run.txt"
        disposition = {"schemaVersion": 2, "worktrees": {str(repo): {
            "preserve": ["preserve-cache"], "reproducible": ["build-cache"],
            "rebuild": {"build-cache": f"echo executed > {marker}"},
        }}}
        primary, mirror = self.root / "primary", self.root / "mirror"
        captured = self.capture(repo, primary, mirror, disposition, stamp="light-restore")
        self.assertEqual(captured.returncode, 0, captured.stdout + captured.stderr)
        self.assertFalse((primary / "worktrees/000/ignored-reproducible-manifest.json").exists())
        self.assertEqual(json.loads((primary / "snapshot-summary.json").read_text())["schemaVersion"], 3)
        # The original path no longer exists; a real recovery must still work.
        repo.rename(self.root / "retired-original")
        restore = self.root / "restore"
        result = run([sys.executable, VERIFY, "--source", primary, "--mirror", mirror,
                      "--restore", restore], check=False)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        state = restore / "states/000"
        self.assertEqual((state / "untracked.txt").read_text(), "useful work\n")
        self.assertIn("0.000123456789", (state / "preserve-cache/experiment.csv").read_text())
        self.assertFalse((state / "build-cache").exists())
        self.assertFalse(marker.exists())
        receipt = json.loads((restore / "restore-verification.json").read_text())
        self.assertEqual(receipt["worktreeReplays"][0]["reproducibleRepresentation"], "roots")
        write(mirror / "worktrees/000/staged.patch", "corrupted package")
        refused = run([sys.executable, VERIFY, "--source", primary, "--mirror", mirror,
                       "--restore", self.root / "restore-corrupt"], check=False)
        self.assertNotEqual(refused.returncode, 0)
        self.assertIn("hash mismatch", refused.stderr)

    def test_snapshot_disposition_version_matrix(self):
        legacy = self.state(version=1)
        for snapshot_version in (2, 3):
            self.assertFalse(verify_module.ignored_records(legacy, snapshot_version)[2])
        (legacy / "ignored-reproducible-manifest.json").unlink()
        light = self.state(version=2)
        self.assertTrue(verify_module.ignored_records(light, 3)[2])
        with self.assertRaisesRegex(RuntimeError, "Incompatible"):
            verify_module.ignored_records(light, 2)
        with self.assertRaisesRegex(RuntimeError, "Incompatible"):
            verify_module.ignored_records(light, 99)

    def test_lightweight_records_reject_missing_basis_and_mixed_representations(self):
        state = self.state()
        write(state / "ignored-reproducible-manifest.json", "[]")
        with self.assertRaisesRegex(RuntimeError, "Ambiguous"):
            verify_module.ignored_records(state, 3)
        (state / "ignored-reproducible-manifest.json").unlink()
        disposition = json.loads((state / "ignored-disposition.json").read_text())
        disposition["rebuild"] = {}
        write(state / "ignored-disposition.json", json.dumps(disposition))
        with self.assertRaisesRegex(RuntimeError, "rebuild"):
            verify_module.ignored_records(state, 3)

    def test_cache_records_cannot_cover_captured_protected_files(self):
        state = self.state()
        write(state / "ls-files-stage.z", "100644 " + "a" * 40 + " 0\tbuild-cache/source.py\0")
        with self.assertRaisesRegex(RuntimeError, "protected path"):
            verify_module.ignored_records(state, 3)

    def test_cache_ancestor_must_be_regular_and_complete(self):
        state = self.state()
        path = state / "ignored-reproducible-roots.json"
        records = json.loads(path.read_text())
        records[0]["ancestors"][0]["kind"] = "symlink"
        write(path, json.dumps(records))
        with self.assertRaisesRegex(RuntimeError, "ancestor"):
            verify_module.ignored_records(state, 3)
