"""Historical schema-2/3 shapes replay without adding schema-4 metadata."""
from __future__ import annotations

import json
import shutil
import sys

from test_recovery_flow import TemporaryGitCase, VERIFY, git, run, write, capture_module, fs


class LegacyPackageTests(TemporaryGitCase):
    def legacy_package(self, version):
        repo, _, _ = self.create_repository(feature=False)
        write(repo / "tracked.txt", "base\nstaged\n")
        git(repo, "add", "tracked.txt")
        write(repo / "config.txt", "base\nunstaged\n")
        write(repo / "note.txt", "unique local note\n")
        write(repo / "preserve-cache/data.csv", "sample,value\n1,42\n")
        write(repo / "build-cache/temporary", "rebuild\n")
        disposition = {"preserve": ["preserve-cache"], "reproducible": ["build-cache"]}
        if version == 3:
            disposition.update(schemaVersion=2, rebuild={"build-cache": "Rebuild from pinned inputs"})
        primary, mirror = self.root / "primary", self.root / "mirror"
        (primary / "snapshot").mkdir(parents=True)
        states = primary / "worktrees"
        states.mkdir()
        record = capture_module.parse_worktrees(capture_module.git(repo, "worktree", "list", "--porcelain", "-z").stdout)[0]
        metadata = capture_module.backup_worktree(repo, record, 0, states, {fs.canonical_path(repo): disposition})
        # Historical manifests have neither new path registration nor layout data.
        metadata.pop("nestedPaths", None)
        metadata.pop("containedLinked", None)
        capture_module.write_json(states / "000/metadata.json", metadata)
        head = git(repo, "rev-parse", "HEAD").stdout.strip()
        refbase = "refs/backup/branch-consolidation/legacy"
        backup_ref = refbase + "/main"
        git(repo, "update-ref", backup_ref, head)
        refs = capture_module.local_refs(repo, "refs", excluded_prefix=refbase)
        capture_module.write_json(primary / "snapshot/backup-refs.json", {backup_ref: head})
        capture_module.write_json(primary / "snapshot/worktree-summaries.json", [metadata])
        capture_module.write_json(primary / "snapshot/protected-objects.json", {
            "allRefs": refs, "localHeads": {"refs/heads/main": head}, "remoteTracking": {},
            "liveRemoteHeads": {"refs/heads/main": head}, "reflogCommits": [], "stashCommits": [],
            "worktrees": [record]})
        git(repo, "bundle", "create", primary / "repository-recovery.bundle", backup_ref)
        capture_module.write_json(primary / "snapshot-summary.json", {
            "schemaVersion": version, "repo": str(repo), "remote": "origin", "refbase": refbase,
            "bundleSha256": fs.sha256_file(primary / "repository-recovery.bundle"), "worktreeCount": 1})
        capture_module.package_manifest(primary)
        shutil.copytree(primary, mirror)
        return repo, primary, mirror

    def test_historical_schema2_and_schema3_replay_without_original_repository(self):
        for version in (2, 3):
            with self.subTest(version=version):
                fixture = self.root / str(version)
                fixture.mkdir()
                original_root = self.root
                self.root = fixture
                try:
                    repo, primary, mirror = self.legacy_package(version)
                    repo.rename(self.root / "original-unavailable")
                    restore = self.root / "restore"
                    replay = run([sys.executable, VERIFY, "--source", primary, "--mirror", mirror,
                                  "--restore", restore], check=False)
                    self.assertEqual(replay.returncode, 0, replay.stdout + replay.stderr)
                    self.assertEqual((restore / "states/000/note.txt").read_text(), "unique local note\n")
                    self.assertFalse((restore / "states/000/build-cache").exists())
                    self.assertEqual(json.loads((restore / "restore-verification.json").read_text())["snapshotSchemaVersion"], version)
                finally:
                    self.root = original_root
