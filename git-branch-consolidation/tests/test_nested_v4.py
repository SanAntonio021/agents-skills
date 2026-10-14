"""Composite recovery uses sealed child packages and rejects missing proof/drift."""
from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path
from unittest import mock

from test_recovery_flow import TemporaryGitCase, CAPTURE, VERIFY, git, run, write, fs, capture_module
from git_layout import discover_worktrees


class NestedRecoveryTests(TemporaryGitCase):
    def nested_fixture(self, dirty=False, linked=False):
        parent, remote, _ = self.create_repository(feature=False)
        child = parent / "vendor" / "model"
        git(parent, "clone", remote, child)
        git(child, "config", "user.name", "Nested Test")
        git(child, "config", "user.email", "nested@example.invalid")
        if linked:
            git(child, "worktree", "add", "-b", "child-local", child / "checkouts/local")
            write(child / "checkouts/local/config.txt", "base\nlinked local change\n")
        if dirty:
            write(child / "tracked.txt", "base\nstaged\n")
            git(child, "add", "tracked.txt")
            write(child / "tracked.txt", "base\nstaged\nunstaged\n")
            write(child / "new.py", "value = 42\n")
            write(child / "preserve-cache" / "result.bin", "measured local bytes\n")
        disposition = None
        if dirty:
            disposition = {"schemaVersion": 1, "worktrees": {str(child): {
                "preserve": ["preserve-cache"], "reproducible": []}}}
        primary, mirror = self.root / "child-primary", self.root / "child-mirror"
        captured = self.capture(child, primary, mirror, disposition, stamp="child")
        self.assertEqual(captured.returncode, 0, captured.stdout + captured.stderr)
        restore = self.root / "child-proof"
        verified = run([sys.executable, VERIFY, "--source", primary, "--mirror", mirror,
                        "--restore", restore], check=False)
        self.assertEqual(verified.returncode, 0, verified.stdout + verified.stderr)
        entry = {"parentWorktree": str(parent), "relativePath": "vendor/model", "packagePath": str(primary),
                 "manifestSha256": fs.sha256_file(primary / "package-manifest.sha256"),
                 "frozenStateSha256": fs.sha256_file(primary / "snapshot/full-frozen-state.json"),
                 "gitLayout": discover_worktrees(child)[0],
                 "verificationPath": str(restore / "restore-verification.json"),
                 "verificationSha256": fs.sha256_file(restore / "restore-verification.json")}
        return parent, child, remote, entry

    def capture_parent(self, parent, entry, stamp="parent"):
        mapping = self.root / f"{stamp}-nested.json"
        write(mapping, json.dumps({"schemaVersion": 1, "entries": [entry]}))
        primary, mirror = self.root / f"{stamp}-primary", self.root / f"{stamp}-mirror"
        process = run([sys.executable, CAPTURE, "--repo", parent, "--remote", "origin", "--primary", primary,
                       "--mirror", mirror, "--stamp", stamp, "--nested-recovery-map", mapping], check=False)
        return process, primary, mirror

    def test_clean_and_dirty_child_replay_from_parent_packages_only(self):
        for dirty in (False, True):
            with self.subTest(dirty=dirty):
                # Each subcase uses a separate temporary scope so stamp and paths cannot collide.
                fixture = self.root / ("dirty" if dirty else "clean")
                fixture.mkdir()
                previous = self.root
                self.root = fixture
                try:
                    parent, child, remote, entry = self.nested_fixture(dirty, linked=dirty)
                    process, primary, mirror = self.capture_parent(parent, entry)
                    self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
                    manifest = (primary / "package-manifest.sha256").read_bytes()
                    parent.rename(self.root / "original-unavailable")
                    remote.rename(self.root / "remote-unavailable.git")
                    shutil.rmtree(fs.io_path(self.root / "child-primary"))
                    shutil.rmtree(fs.io_path(self.root / "child-mirror"))
                    (self.root / "child-proof").rename(self.root / "proof-unavailable")
                    restore = self.root / "restore"
                    # The package-bundled entry point resolves all imports beside itself.
                    env = dict(os.environ, PYTHONPATH=str(self.root / "missing-installation"))
                    with mock.patch.dict(os.environ, env, clear=True):
                        replay = run([sys.executable, primary / "restore-runtime/verify_recovery.py",
                                      "--source", primary, "--mirror", mirror, "--restore", restore],
                                     cwd=self.root, check=False)
                    self.assertEqual(replay.returncode, 0, replay.stdout + replay.stderr)
                    nested = restore / "states/000/vendor/model"
                    self.assertTrue((nested / ".git").is_file())
                    if dirty:
                        self.assertEqual((nested / "tracked.txt").read_text(), "base\nstaged\nunstaged\n")
                        self.assertEqual(git(nested, "show", ":tracked.txt").stdout, "base\nstaged\n")
                        self.assertEqual((nested / "new.py").read_text(), "value = 42\n")
                        self.assertEqual((nested / "preserve-cache/result.bin").read_text(), "measured local bytes\n")
                        self.assertEqual((nested / "checkouts/local/config.txt").read_text(), "base\nlinked local change\n")
                        self.assertEqual(git(nested, "rev-parse", "--path-format=absolute", "--git-common-dir").stdout,
                                         git(nested / "checkouts/local", "rev-parse", "--path-format=absolute", "--git-common-dir").stdout)
                    receipt = json.loads((restore / "restore-verification.json").read_text())
                    self.assertEqual(receipt["worktreeReplays"][0]["nestedReplays"][0]["relativePath"], "vendor/model")
                    self.assertEqual((primary / "package-manifest.sha256").read_bytes(), manifest)
                    capture_module.verify_package(primary)
                    self.assertFalse((primary / "restore-runtime/__pycache__").exists())
                finally:
                    self.root = previous

    def test_unregistered_hash_path_receipt_and_child_drift_are_rejected(self):
        parent, child, _, entry = self.nested_fixture(dirty=True)
        unregistered = self.capture(parent, self.root / "absent-primary", self.root / "absent-mirror", stamp="unregistered")
        self.assertNotEqual(unregistered.returncode, 0)
        self.assertIn("Nested repository", unregistered.stderr)
        for field, value, text in [
            ("manifestSha256", "0" * 64, "manifest hash mismatch"),
            ("frozenStateSha256", "0" * 64, "frozen state hash mismatch"),
            ("relativePath", "vendor/other", "no supported .git"),
            ("verificationSha256", "0" * 64, "receipt hash mismatch"),
        ]:
            with self.subTest(field=field):
                process, _, _ = self.capture_parent(parent, dict(entry, **{field: value}), stamp=field)
                self.assertNotEqual(process.returncode, 0)
                self.assertIn(text, process.stderr)
        write(child / "new.py", "value = 43\n")
        process, _, _ = self.capture_parent(parent, entry, stamp="child-drift")
        self.assertNotEqual(process.returncode, 0)
        self.assertIn("state drifted", process.stderr)

    def test_nested_map_paths_overlap_and_link_escape_are_rejected(self):
        parent, child, _, entry = self.nested_fixture()
        path = self.root / "map.json"
        write(path, json.dumps({"schemaVersion": 1, "entries": [entry, dict(entry, relativePath="vendor/model/deeper")]}))
        with self.assertRaisesRegex(RuntimeError, "paths overlap"):
            capture_module.load_nested_recovery_map(str(path))
        write(path, json.dumps({"schemaVersion": 1, "entries": [dict(entry, relativePath="../escape")]}))
        with self.assertRaisesRegex(RuntimeError, "Unsafe relative"):
            capture_module.load_nested_recovery_map(str(path))

    def test_sealed_nested_package_corruption_and_original_overlap_are_rejected(self):
        parent, _, _, entry = self.nested_fixture()
        process, primary, mirror = self.capture_parent(parent, entry)
        self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
        overlap = run([sys.executable, VERIFY, "--source", primary, "--mirror", mirror,
                       "--restore", parent / "new-restore"], check=False)
        self.assertNotEqual(overlap.returncode, 0)
        self.assertIn("overlaps original", overlap.stderr)
        self.assertFalse((parent / "new-restore").exists())
        write(mirror / "nested/000/package/worktrees/000/staged.patch", "damaged")
        failed = run([sys.executable, VERIFY, "--source", primary, "--mirror", mirror,
                      "--restore", self.root / "restore-corrupt"], check=False)
        self.assertNotEqual(failed.returncode, 0)
        self.assertIn("hash mismatch", failed.stderr)

    def test_same_common_directory_is_replayed_as_a_linked_worktree(self):
        parent, _, _ = self.create_repository(feature=True)
        linked = parent / "checkouts" / "feature"
        git(parent, "worktree", "add", linked, "feature")
        write(linked / "feature.txt", "feature\nlinked modification\n")
        primary, mirror = self.root / "primary", self.root / "mirror"
        captured = self.capture(parent, primary, mirror, stamp="contained-linked")
        self.assertEqual(captured.returncode, 0, captured.stdout + captured.stderr)
        summary = json.loads((primary / "snapshot-summary.json").read_text())
        self.assertEqual(summary["nestedRecoveryCount"], 0)
        restore = self.root / "restore"
        replay = run([sys.executable, VERIFY, "--source", primary, "--mirror", mirror,
                      "--restore", restore], check=False)
        self.assertEqual(replay.returncode, 0, replay.stdout + replay.stderr)
        root = restore / "states/000"
        recovered = root / "checkouts/feature"
        self.assertEqual((recovered / "feature.txt").read_text(), "feature\nlinked modification\n")
        self.assertEqual(git(root, "rev-parse", "--path-format=absolute", "--git-common-dir").stdout,
                         git(recovered, "rev-parse", "--path-format=absolute", "--git-common-dir").stdout)
