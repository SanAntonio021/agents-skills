"""Coverage is a prerequisite for cleanup, independent of branch count."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

from test_recovery_flow import TemporaryGitCase, git, run, write, ACCEPTANCE
import verify_acceptance as acceptance


class IntegrationAcceptanceTests(TemporaryGitCase):
    def prepare(self, feature=False, disposition=None):
        repo, remote, feature = self.create_repository(feature=feature)
        primary, mirror = self.root / "primary", self.root / "mirror"
        return repo, remote, feature, primary, mirror

    def check(self, repo, primary, *extra):
        result = run([sys.executable, ACCEPTANCE, "--repo", repo, "--remote", "origin",
                      "--snapshot", primary, "--expected-commit", git(repo, "rev-parse", "HEAD").stdout.strip(),
                      *extra], check=False)
        self.assertNotEqual(result.returncode, 2, result.stdout + result.stderr)
        return result, json.loads(result.stdout)

    def test_unmerged_branch_fails_before_deletion_and_false_cleanup(self):
        repo, _, sha, primary, mirror = self.prepare(feature=True)
        captured = self.capture(repo, primary, mirror, stamp="unmerged")
        self.assertEqual(captured.returncode, 0, captured.stdout + captured.stderr)
        result, report = self.check(repo, primary, "--check-integration-only")
        self.assertEqual(result.returncode, 1)
        self.assertTrue(any(not item["ok"] and item["name"].startswith("integrated:") for item in report["checks"]))
        self.assertEqual(git(repo, "rev-parse", "feature").stdout.strip(), sha)

    def test_merge_is_allowed_by_default_and_linear_option_rejects(self):
        repo, _, _, primary, mirror = self.prepare(feature=True)
        captured = self.capture(repo, primary, mirror, stamp="merge")
        self.assertEqual(captured.returncode, 0, captured.stdout + captured.stderr)
        git(repo, "merge", "--no-ff", "feature", "-m", "combine work")
        result, report = self.check(repo, primary, "--check-integration-only")
        self.assertEqual(result.returncode, 0, report)
        result, report = self.check(repo, primary, "--check-integration-only", "--require-linear-history")
        self.assertEqual(result.returncode, 1)
        self.assertFalse(next(item for item in report["checks"] if item["name"] == "new-history-is-linear")["ok"])

    def test_stash_and_dirty_work_have_to_be_committed(self):
        repo, _, _, primary, mirror = self.prepare()
        write(repo / "tracked.txt", "stashed staged change\n")
        git(repo, "add", "tracked.txt")
        write(repo / "config.txt", "stashed working change\n")
        write(repo / "from-stash.txt", "new stashed source\n")
        git(repo, "stash", "push", "--include-untracked", "-m", "effective work")
        write(repo / "stash.txt", "current dirty change\n")
        write(repo / "new-source.txt", "new source\n")
        captured = self.capture(repo, primary, mirror, stamp="stash-dirty")
        self.assertEqual(captured.returncode, 0, captured.stdout + captured.stderr)
        git(repo, "add", ".")
        git(repo, "commit", "-m", "integrate dirty work")
        result, _ = self.check(repo, primary, "--check-integration-only")
        self.assertEqual(result.returncode, 1)
        git(repo, "stash", "apply", "--index")
        git(repo, "add", ".")
        git(repo, "commit", "-m", "integrate all stash layers")
        result, report = self.check(repo, primary, "--check-integration-only")
        self.assertEqual(result.returncode, 0, report)
        self.assertTrue(git(repo, "stash", "list").stdout.strip(), "Coverage check must not drop stash")

    def test_detached_head_work_and_nonbranch_refs_are_retained(self):
        repo, _, _, primary, mirror = self.prepare()
        git(repo, "notes", "add", "-m", "research note")
        note = git(repo, "rev-parse", "refs/notes/commits").stdout.strip()
        linked = self.root / "linked"
        git(repo, "worktree", "add", "--detach", str(linked))
        write(linked / "detached.txt", "unique work\n")
        git(linked, "add", ".")
        git(linked, "commit", "-m", "detached work")
        tip = git(linked, "rev-parse", "HEAD").stdout.strip()
        captured = self.capture(repo, primary, mirror, stamp="detached")
        self.assertEqual(captured.returncode, 0, captured.stdout + captured.stderr)
        result, _ = self.check(repo, primary, "--check-integration-only")
        self.assertEqual(result.returncode, 1)
        git(repo, "merge", "--no-ff", tip, "-m", "integrate detached work")
        result, report = self.check(repo, primary, "--check-integration-only")
        self.assertEqual(result.returncode, 0, report)
        self.assertEqual(git(repo, "rev-parse", "refs/notes/commits").stdout.strip(), note)

    def test_durable_data_needs_usable_copy_not_backup(self):
        repo, _, _, primary, mirror = self.prepare()
        linked = self.root / "linked"
        git(repo, "worktree", "add", "--detach", str(linked))
        write(linked / "preserve-cache" / "measurement.csv", "TxPower,BER\n-10,1.23e-8\n")
        disposition = {"schemaVersion": 2, "worktrees": {str(linked): {
            "preserve": ["preserve-cache"], "reproducible": [], "rebuild": {}}}}
        captured = self.capture(repo, primary, mirror, disposition, stamp="data")
        self.assertEqual(captured.returncode, 0, captured.stdout + captured.stderr)
        state = primary / "worktrees/001"
        manifest = json.loads((state / "ignored-preserved-manifest.json").read_text())
        digest = hashlib.sha256(json.dumps(manifest, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        record = {"source_ref": "worktree:001:ignored-preserved", "source_sha": digest,
                  "resulting_sha": git(repo, "rev-parse", "HEAD").stdout.strip(), "destination": str(mirror)}
        records = self.root / "records.json"
        write(records, json.dumps([record]))
        result, _ = self.check(repo, primary, "--check-integration-only", "--integration-records", str(records))
        self.assertEqual(result.returncode, 1)
        retained = self.root / "retained-data"
        write(retained / "preserve-cache/measurement.csv", (linked / "preserve-cache/measurement.csv").read_text())
        record["destination"] = str(retained)
        write(records, json.dumps([record]))
        result, report = self.check(repo, primary, "--check-integration-only", "--integration-records", str(records))
        self.assertEqual(result.returncode, 0, report)

        # A pre-cleanup candidate is commonly a separate worktree. The lasting
        # project root remains a valid data destination on Windows long paths.
        candidate = self.root / "candidate"
        git(repo, "worktree", "add", "--detach", str(candidate))
        write(repo / "preserve-cache/measurement.csv", (linked / "preserve-cache/measurement.csv").read_text())
        record["destination"] = str(repo)
        write(records, json.dumps([record]))
        result, report = self.check(candidate, primary, "--check-integration-only", "--integration-records", str(records))
        self.assertEqual(result.returncode, 0, report)

    def test_lease_drift_and_atomic_failure_keep_all_remote_targets(self):
        repo, _, feature, _, _ = self.prepare(feature=True)
        git(repo, "branch", "second", "feature")
        git(repo, "push", "origin", "second")
        git(repo, "switch", "feature")
        write(repo / "later.txt", "concurrent work\n")
        git(repo, "add", ".")
        git(repo, "commit", "-m", "concurrent change")
        later = git(repo, "rev-parse", "HEAD").stdout.strip()
        git(repo, "push", "origin", "feature")
        result = git(repo, "push", "--atomic", f"--force-with-lease=refs/heads/feature:{feature}",
                     f"--force-with-lease=refs/heads/second:{feature}", "origin", "--delete", "feature", "second", check=False)
        self.assertNotEqual(result.returncode, 0)
        remote = git(repo, "ls-remote", "origin", "refs/heads/feature", "refs/heads/second").stdout
        self.assertIn(later + "\trefs/heads/feature", remote)
        self.assertIn(feature + "\trefs/heads/second", remote)
