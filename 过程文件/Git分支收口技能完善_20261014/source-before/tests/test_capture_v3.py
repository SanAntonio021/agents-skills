"""Exercise lightweight capture against real Git, without touching business repos."""
import json
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

from test_recovery_flow import TemporaryGitCase, git, write
import capture_recovery as capture
import recovery_fs as fs


class CaptureV3Tests(TemporaryGitCase):
    def setup_cache(self, nested=False):
        repo, _, _ = self.create_repository(feature=False)
        root = "scratch/cache" if nested else "build-cache"
        if nested:
            write(repo / ".gitignore", "scratch/cache/\n")
            write(repo / "scratch/input.txt", "irreplaceable\n")
        write(repo / root / "payload.bin", "rebuildable\n")
        disposition = {"schemaVersion": 2, "preserve": [], "reproducible": [root],
                       "rebuild": {root: "python build.py from the pinned source and config"}}
        return repo, root, disposition

    def snapshot(self, repo, disposition):
        return capture.full_snapshot(repo, "origin", "refs/backup/test", {fs.canonical_path(repo): disposition})

    def test_no_cache_traversal_or_hash_and_internal_change_does_not_drift(self):
        repo, root, disposition = self.setup_cache(nested=True)
        cache_path = fs.io_path(repo / root)
        original_scan, original_hash = os.scandir, fs.sha256_file

        def scan(path):
            if fs.io_path(path) == cache_path or cache_path in fs.io_path(path).parents:
                raise AssertionError("Backup traversed cache")
            return original_scan(path)

        def digest(path):
            if fs.io_path(path) == cache_path or cache_path in fs.io_path(path).parents:
                raise AssertionError("Backup hashed cache")
            return original_hash(path)

        with mock.patch.object(fs.os, "scandir", side_effect=scan), mock.patch.object(fs, "sha256_file", side_effect=digest):
            before = self.snapshot(repo, disposition)
            write(repo / root / "payload.bin", "new ignored bytes")
            write(repo / root / "new.bin", "more ignored bytes")
            after = self.snapshot(repo, disposition)
            self.assertEqual(before, after)
            output = self.root / "states"
            output.mkdir()
            record = capture.parse_worktrees(capture.git(repo, "worktree", "list", "--porcelain", "-z").stdout)[0]
            capture.backup_worktree(repo, record, 0, output, {fs.canonical_path(repo): disposition})
            state = output / "000"
            capture.verify_worktree_unchanged(repo, state)
        self.assertFalse((state / "ignored-reproducible-manifest.json").exists())
        roots = json.loads((state / "ignored-reproducible-roots.json").read_text())
        fs.validate_reproducible_roots_metadata(roots, disposition)
        self.assertEqual(json.loads((state / "untracked-roots.json").read_text()), ["scratch/input.txt"])

    def test_missing_rebuild_and_overlapping_paths_rejected(self):
        _, _, disposition = self.setup_cache()
        invalid = dict(disposition, rebuild={})
        with self.assertRaisesRegex(RuntimeError, "rebuild"):
            fs.validate_rebuild_disposition(invalid)
        invalid = dict(disposition, preserve=["build-cache/input"])
        with self.assertRaisesRegex(RuntimeError, "overlap"):
            fs.validate_rebuild_disposition(invalid)

    def test_tracked_file_below_cache_cannot_be_excluded(self):
        repo, root, disposition = self.setup_cache()
        git(repo, "add", "-f", root + "/payload.bin")
        with self.assertRaises(RuntimeError):
            self.snapshot(repo, disposition)

    def test_new_root_and_ignore_negation_stop_capture(self):
        repo, _, disposition = self.setup_cache()
        before = self.snapshot(repo, disposition)
        write(repo / ".gitignore", "build-cache/*\n!build-cache/payload.bin\n")
        with self.assertRaises(RuntimeError):
            self.snapshot(repo, disposition)
        write(repo / ".gitignore", "build-cache/\nnew-cache/\n")
        write(repo / "new-cache/file", "new")
        with self.assertRaises(RuntimeError):
            self.snapshot(repo, disposition)
        self.assertTrue(before)

    def test_preserved_change_and_root_replacement_drift(self):
        repo, root, disposition = self.setup_cache()
        write(repo / "preserve-cache/data", "measured")
        disposition["preserve"] = ["preserve-cache"]
        before = self.snapshot(repo, disposition)
        write(repo / "preserve-cache/data", "different")
        self.assertNotEqual(before, self.snapshot(repo, disposition))
        before = self.snapshot(repo, disposition)
        (repo / root).rename(repo / "temporary-cache")
        (repo / root).mkdir()
        write(repo / root / "payload.bin", "replacement")
        # Remove the now-untracked former root only from the comparison by ignoring it.
        self.assertNotEqual(before["worktrees"][0]["protection"]["reproducibleRoots"],
                            fs.reproducible_roots_metadata(repo, disposition))

    def test_hidden_index_flags_and_nested_repository_block(self):
        repo, _, disposition = self.setup_cache()
        for flag, undo in [("--assume-unchanged", "--no-assume-unchanged"),
                           ("--skip-worktree", "--no-skip-worktree")]:
            git(repo, "update-index", flag, "tracked.txt")
            with self.assertRaisesRegex(RuntimeError, "separate recovery"):
                self.snapshot(repo, disposition)
            git(repo, "update-index", undo, "tracked.txt")
        git(repo, "init", "nested")
        with self.assertRaisesRegex(RuntimeError, "Nested repository"):
            self.snapshot(repo, disposition)

    def test_legacy_disposition_still_hashes_cache(self):
        repo, root, disposition = self.setup_cache()
        disposition = {key: disposition[key] for key in ("preserve", "reproducible")}
        before = self.snapshot(repo, disposition)
        write(repo / root / "payload.bin", "changed")
        self.assertNotEqual(before, self.snapshot(repo, disposition))

    def test_sparse_submodule_and_interrupted_merge_are_not_silently_captured(self):
        repo, _, disposition = self.setup_cache()
        git(repo, "config", "core.sparseCheckout", "true")
        with self.assertRaisesRegex(RuntimeError, "Sparse checkout"):
            self.snapshot(repo, disposition)
        git(repo, "config", "--unset", "core.sparseCheckout")
        head = git(repo, "rev-parse", "HEAD").stdout.strip()
        git(repo, "update-index", "--add", "--cacheinfo", "160000," + head + ",submodule")
        with self.assertRaisesRegex(RuntimeError, "Submodule"):
            self.snapshot(repo, disposition)
        git(repo, "update-index", "--force-remove", "submodule")
        write(repo / ".git/MERGE_HEAD", head + "\n")
        with self.assertRaisesRegex(RuntimeError, "Git operation"):
            self.snapshot(repo, disposition)
        self.assertTrue((repo / ".git/MERGE_HEAD").exists())

    def test_classification_and_ancestor_replacement_change_snapshot(self):
        repo, root, disposition = self.setup_cache(nested=True)
        before = self.snapshot(repo, disposition)
        preserved = {"schemaVersion": 2, "preserve": [root], "reproducible": [], "rebuild": {}}
        self.assertNotEqual(before, self.snapshot(repo, preserved))
        (repo / "scratch").rename(repo / "old-scratch")
        write(repo / root / "payload.bin", "rebuildable\n")
        self.assertNotEqual(before["worktrees"][0]["protection"]["reproducibleRoots"],
                            fs.reproducible_roots_metadata(repo, disposition))


if __name__ == "__main__":
    unittest.main()
