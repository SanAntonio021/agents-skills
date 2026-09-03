from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
CAPTURE = SKILL_ROOT / "scripts" / "capture_recovery.py"
VERIFY = SKILL_ROOT / "scripts" / "verify_recovery.py"
ACCEPTANCE = SKILL_ROOT / "scripts" / "verify_acceptance.py"


def run(args, cwd=None, check=True):
    process = subprocess.run(
        [str(value) for value in args],
        cwd=str(cwd) if cwd else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if check and process.returncode != 0:
        raise AssertionError(
            f"Command failed ({process.returncode}): {args}\n"
            f"stdout={process.stdout}\nstderr={process.stderr}"
        )
    return process


def git(repo, *args, check=True):
    return run(["git", "-C", repo, *args], check=check)


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


class TemporaryGitCase(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="gbc-")).resolve()

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def create_repository(self, feature=True):
        remote = self.root / "remote.git"
        repo = self.root / "repo"
        run(["git", "init", "--bare", "--initial-branch=main", remote])
        run(["git", "init", "--initial-branch=main", repo])
        git(repo, "config", "user.name", "Branch Consolidation Test")
        git(repo, "config", "user.email", "branch-consolidation@example.invalid")
        write(repo / ".gitignore", "preserve-cache/\nbuild-cache/\n")
        write(repo / "tracked.txt", "base\n")
        write(repo / "config.txt", "base\n")
        write(repo / "stash.txt", "base\n")
        git(repo, "add", ".")
        git(repo, "commit", "-m", "initial")
        git(repo, "remote", "add", "origin", remote)
        git(repo, "push", "-u", "origin", "main")
        git(repo, "tag", "v1")
        git(repo, "push", "origin", "v1")
        feature_sha = None
        if feature:
            git(repo, "switch", "-c", "feature")
            write(repo / "feature.txt", "feature\n")
            git(repo, "add", "feature.txt")
            git(repo, "commit", "-m", "feature")
            feature_sha = git(repo, "rev-parse", "HEAD").stdout.strip()
            git(repo, "push", "-u", "origin", "feature")
            git(repo, "switch", "main")
        return repo, remote, feature_sha

    def capture(self, repo: Path, primary: Path, mirror: Path, disposition=None, stamp="test"):
        arguments = [
            sys.executable,
            CAPTURE,
            "--repo",
            repo,
            "--remote",
            "origin",
            "--primary",
            primary,
            "--mirror",
            mirror,
            "--stamp",
            stamp,
        ]
        if disposition is not None:
            disposition_path = self.root / f"{stamp}-ignored.json"
            disposition_path.write_text(
                json.dumps(disposition, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            arguments.extend(["--ignored-disposition", disposition_path])
        return run(arguments, cwd=SKILL_ROOT, check=False)


class RecoveryFlowTests(TemporaryGitCase):
    def test_capture_and_isolated_replay_preserve_every_worktree_state(self):
        repo, _, _ = self.create_repository(feature=True)
        git(repo, "switch", "-c", "local-only")
        write(repo / "local-only.txt", "local\n")
        git(repo, "add", "local-only.txt")
        git(repo, "commit", "-m", "local only")
        git(repo, "switch", "main")

        write(repo / "stash.txt", "stashed\n")
        git(repo, "stash", "push", "-m", "saved state")
        write(repo / "tracked.txt", "base\nstaged\n")
        git(repo, "add", "tracked.txt")
        write(repo / "config.txt", "base\nunstaged\n")
        (repo / "notes.bin").write_bytes(b"\x00\x01unique\xff")
        (repo / "preserve-cache").mkdir()
        (repo / "preserve-cache" / "result.bin").write_bytes(b"result")
        (repo / "build-cache").mkdir()
        write(repo / "build-cache" / "generated.txt", "regenerate\n")

        linked = self.root / "feature-worktree"
        git(repo, "worktree", "add", linked, "feature")
        write(linked / "feature.txt", "feature\nworktree dirty\n")
        write(linked / "worktree-note.txt", "untracked\n")
        (linked / "preserve-cache").mkdir()
        (linked / "preserve-cache" / "measurement.bin").write_bytes(b"measurement")
        (linked / "build-cache").mkdir()
        write(linked / "build-cache" / "generated.txt", "rebuild me\n")

        disposition = {
            "schemaVersion": 1,
            "worktrees": {
                str(repo): {
                    "preserve": ["preserve-cache"],
                    "reproducible": ["build-cache"],
                },
                str(linked): {
                    "preserve": ["preserve-cache"],
                    "reproducible": ["build-cache"],
                },
            },
        }
        primary = self.root / "primary"
        mirror = self.root / "mirror"
        captured = self.capture(repo, primary, mirror, disposition, stamp="full-replay")
        self.assertEqual(captured.returncode, 0, captured.stderr + captured.stdout)
        self.assertEqual(
            (primary / "package-manifest.sha256").read_bytes(),
            (mirror / "package-manifest.sha256").read_bytes(),
        )

        restore = self.root / "restore"
        verified = run(
            [
                sys.executable,
                VERIFY,
                "--source",
                primary,
                "--mirror",
                mirror,
                "--restore",
                restore,
            ],
            cwd=SKILL_ROOT,
            check=False,
        )
        self.assertEqual(verified.returncode, 0, verified.stderr + verified.stdout)
        receipt = json.loads((restore / "restore-verification.json").read_text(encoding="utf-8"))
        self.assertTrue(receipt["packagesIdentical"])
        self.assertEqual(len(receipt["worktreeReplays"]), 2)
        self.assertGreater(sum(item["ignoredPreservedManifestEntries"] for item in receipt["worktreeReplays"]), 0)
        self.assertGreater(
            sum(item["ignoredReproducibleManifestEntriesRecorded"] for item in receipt["worktreeReplays"]),
            0,
        )

    def test_capture_fails_when_any_ignored_root_has_no_disposition(self):
        repo, _, _ = self.create_repository(feature=False)
        (repo / "preserve-cache").mkdir()
        write(repo / "preserve-cache" / "unique.log", "keep me\n")
        disposition = {
            "schemaVersion": 1,
            "worktrees": {
                str(repo): {
                    "preserve": [],
                    "reproducible": [],
                }
            },
        }
        result = self.capture(
            repo,
            self.root / "primary-incomplete",
            self.root / "mirror-incomplete",
            disposition,
            stamp="incomplete",
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Ignored disposition is incomplete", result.stderr)

    def test_final_acceptance_passes_only_after_exact_branch_and_backup_cleanup(self):
        repo, _, feature_sha = self.create_repository(feature=True)
        primary = self.root / "acceptance-primary"
        mirror = self.root / "acceptance-mirror"
        captured = self.capture(repo, primary, mirror, stamp="acceptance")
        self.assertEqual(captured.returncode, 0, captured.stderr + captured.stdout)

        git(
            repo,
            "push",
            "--atomic",
            f"--force-with-lease=refs/heads/feature:{feature_sha}",
            "origin",
            "--delete",
            "feature",
        )
        git(repo, "branch", "-D", "feature")
        git(repo, "fetch", "--prune", "origin")
        backup_refs = git(
            repo,
            "for-each-ref",
            "--format=%(refname)",
            "refs/backup/branch-consolidation/acceptance",
        ).stdout.splitlines()
        for ref in backup_refs:
            git(repo, "update-ref", "-d", ref)

        expected = git(repo, "rev-parse", "HEAD").stdout.strip()
        receipt = self.root / "acceptance.json"
        accepted = run(
            [
                sys.executable,
                ACCEPTANCE,
                "--repo",
                repo,
                "--remote",
                "origin",
                "--snapshot",
                primary,
                "--expected-commit",
                expected,
                "--output",
                receipt,
            ],
            cwd=SKILL_ROOT,
            check=False,
        )
        self.assertEqual(accepted.returncode, 0, accepted.stderr + accepted.stdout)
        self.assertTrue(json.loads(receipt.read_text(encoding="utf-8"))["ok"])

        git(repo, "branch", "unexpected-local-branch")
        rejected = run(
            [
                sys.executable,
                ACCEPTANCE,
                "--repo",
                repo,
                "--remote",
                "origin",
                "--snapshot",
                primary,
                "--expected-commit",
                expected,
            ],
            cwd=SKILL_ROOT,
            check=False,
        )
        self.assertEqual(rejected.returncode, 1, rejected.stderr + rejected.stdout)
        self.assertFalse(json.loads(rejected.stdout)["ok"])


if __name__ == "__main__":
    unittest.main()
