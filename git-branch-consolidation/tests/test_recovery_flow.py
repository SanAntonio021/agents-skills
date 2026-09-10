from __future__ import annotations

import json
import io
import os
import shutil
import subprocess
import sys
import tempfile
import tarfile
import unittest
from types import SimpleNamespace
from unittest import mock
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
CAPTURE = SKILL_ROOT / "scripts" / "capture_recovery.py"
VERIFY = SKILL_ROOT / "scripts" / "verify_recovery.py"
ACCEPTANCE = SKILL_ROOT / "scripts" / "verify_acceptance.py"
sys.path.insert(0, str(SKILL_ROOT / "scripts"))
import recovery_fs as fs
import capture_recovery as capture_module
import verify_recovery as verify_module


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
        self.root = Path(tempfile.mkdtemp(prefix="gbc-", dir=os.environ.get("GBC_TEST_ROOT"))).resolve()

    def tearDown(self):
        if os.environ.get("GBC_KEEP_TEST_ARTIFACTS") != "1":
            shutil.rmtree(fs.io_path(self.root), ignore_errors=True)

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
    def test_capture_and_replay_ignore_failing_textconv(self):
        repo, _, _ = self.create_repository(feature=False)
        write(repo / ".gitattributes", "*.pdf diff=recovery-test\n")
        (repo / "document.pdf").write_bytes(b"\x00base\xff\n")
        removed = repo / "__MACOSX" / "._IEEEtran_HOWTO.pdf"
        removed.parent.mkdir()
        removed.write_bytes(b"\x00removed\xfe\n")
        git(repo, "add", ".")
        git(repo, "commit", "-m", "binary diff fixtures")

        marker = self.root / "textconv-invoked"
        converter = self.root / "failing-textconv.py"
        write(converter, "from pathlib import Path\n"
              f"Path({str(marker)!r}).write_text('invoked')\nraise SystemExit(97)\n")
        command = f'"{Path(sys.executable).as_posix()}" "{converter.as_posix()}"'
        git(repo, "config", "diff.recovery-test.textconv", command)
        git(repo, "config", "diff.recovery-test.cachetextconv", "false")
        staged_bytes = b"\x00staged\xff\x81\n"
        current_bytes = b"\x00current\xfe\x82\n"
        (repo / "document.pdf").write_bytes(staged_bytes)
        git(repo, "add", "document.pdf")
        (repo / "document.pdf").write_bytes(current_bytes)
        removed.unlink()

        # Prove the fixture actually invokes the failing driver before testing capture.
        control = git(repo, "diff", "--binary", "--full-index", "--no-ext-diff", check=False)
        self.assertNotEqual(control.returncode, 0)
        self.assertTrue(marker.is_file(), control.stderr)
        marker.unlink()
        primary, mirror = self.root / "primary", self.root / "mirror"
        captured = self.capture(repo, primary, mirror, stamp="no-textconv")
        self.assertEqual(captured.returncode, 0, captured.stderr + captured.stdout)
        self.assertFalse(marker.exists(), "Capture invoked the textconv driver")
        for patch in ("staged.patch", "unstaged.patch"):
            self.assertIn(b"GIT binary patch", (primary / "worktrees/000" / patch).read_bytes())
        restore = self.root / "restore"
        verified = run([sys.executable, VERIFY, "--source", primary, "--mirror", mirror,
                        "--restore", restore], check=False)
        self.assertEqual(verified.returncode, 0, verified.stderr + verified.stdout)
        self.assertFalse(marker.exists(), "Replay invoked the textconv driver")
        state = restore / "states/000"
        self.assertEqual((state / "document.pdf").read_bytes(), current_bytes)
        self.assertFalse((state / "__MACOSX/._IEEEtran_HOWTO.pdf").exists())
        index_bytes = subprocess.check_output(["git", "-C", str(state), "show", ":document.pdf"])
        self.assertEqual(index_bytes, staged_bytes)

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

        git(repo, "merge", "--no-ff", "feature", "-m", "retain feature work")
        git(repo, "push", "origin", "main")

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

    def test_long_paths_and_external_junction_are_captured_without_following(self):
        if os.name != "nt":
            self.skipTest("Windows junction and extended-length path integration")
        import _winapi
        repo, _, _ = self.create_repository(feature=False)
        relative = "/".join(["untracked"] + ["segment-" + "x" * 45] * 5 + ["result.bin"])
        long_file = fs.path_within(repo, relative)
        long_file.parent.mkdir(parents=True)
        long_file.write_bytes(b"long path payload\x00\xff")
        outside = self.root / "external-target"
        outside.mkdir()
        write(outside / "never-read.txt", "outside payload stays outside\n")
        junction = fs.io_path(repo / "preserve-cache" / "external-link")
        junction.parent.mkdir()
        _winapi.CreateJunction(str(outside), str(junction))
        target = os.readlink(junction)
        disposition = {"schemaVersion": 1, "worktrees": {str(repo): {"preserve": ["preserve-cache"], "reproducible": []}}}
        primary, mirror = self.root / "primary-long", self.root / "mirror-long"
        captured = self.capture(repo, primary, mirror, disposition, stamp="long-junction")
        self.assertEqual(captured.returncode, 0, captured.stderr + captured.stdout)
        records = json.loads((primary / "worktrees/000/links.json").read_text(encoding="utf-8"))
        self.assertEqual(len(records["entries"]), 1)
        self.assertEqual(records["entries"][0]["kind"], "junction")
        self.assertEqual(records["entries"][0]["linkTarget"], target)
        with tarfile.open(primary / "worktrees/000/ignored-preserved-payload.tar") as archive:
            self.assertEqual(archive.getnames(), ["preserve-cache", "preserve-cache/external-link"])
        args = [sys.executable, VERIFY, "--source", primary, "--mirror", mirror]
        refused = run(args + ["--restore", self.root / "restore-refused"], check=False)
        self.assertNotEqual(refused.returncode, 0)
        self.assertIn("External link requires an exact allowlist", refused.stderr)
        allowlist = self.root / "allowlist.json"
        write(allowlist, json.dumps({"schemaVersion": 1, "links": [{"worktree": str(repo), "path": "preserve-cache/external-link", "kind": "junction", "target": target}]}))
        restored = self.root / "restore-allowed"
        accepted = run(args + ["--restore", restored, "--external-link-allowlist", allowlist], check=False)
        self.assertEqual(accepted.returncode, 0, accepted.stderr + accepted.stdout)
        state = restored / "states/000"
        self.assertEqual(fs.path_within(state, relative).read_bytes(), long_file.read_bytes())
        self.assertEqual(fs.kind_at(state / "preserve-cache/external-link")[0], "junction")
        self.assertEqual(os.readlink(state / "preserve-cache/external-link"), target)
        self.assertEqual((outside / "never-read.txt").read_text(encoding="utf-8"), "outside payload stays outside\n")


class FilesystemSafetyTests(TemporaryGitCase):
    def archive(self, members):
        path = self.root / "payload.tar"
        with tarfile.open(path, "w", format=tarfile.PAX_FORMAT) as archive:
            for member, data in members:
                archive.addfile(member, io.BytesIO(data) if data is not None else None)
        return path

    def regular(self, name, content=b"payload"):
        member = tarfile.TarInfo(name)
        member.size = len(content)
        member.mode = 0o644
        return member, content

    def test_old_plain_tar_is_compatible(self):
        archive = self.archive([self.regular("nested/data.txt")])
        destination = self.root / "restored"
        fs.safe_extract_tar(archive, destination)
        self.assertEqual((destination / "nested/data.txt").read_bytes(), b"payload")

    def test_allowed_external_file_symlink_is_not_read_during_index_refresh(self):
        original, destination = self.root / "original", self.root / "restore"
        destination.mkdir()
        outside = self.root / "external-file.txt"
        write(outside, "external file must not be opened\n")
        probe = destination / "probe"
        try:
            os.symlink(str(outside), probe)
        except OSError as error:
            if getattr(error, "winerror", None) == 1314:
                self.skipTest("File symlink creation unavailable without existing Windows privilege")
            raise
        raw_target = os.readlink(probe)
        probe.unlink()
        link = tarfile.TarInfo("alias")
        link.type, link.linkname = tarfile.SYMTYPE, raw_target
        archive = self.archive([(link, None)])
        allowed = {(fs.canonical_path(original), "alias", "symlink", raw_target)}
        state_source = self.root / "state-source"
        write(state_source / "tracked-current-roots.json", '["alias"]')
        original_open = Path.open
        def guarded_open(path, *args, **kwargs):
            if fs.canonical_path(path) == fs.canonical_path(outside):
                raise AssertionError("External link target was opened")
            return original_open(path, *args, **kwargs)
        with mock.patch.object(Path, "open", guarded_open):
            fs.safe_extract_tar(archive, destination, allowed=allowed, source_worktree=original)
            with mock.patch.object(verify_module, "git") as git_mock:
                verify_module.refresh_clean_index_entries(destination, state_source)
                git_mock.assert_not_called()
        self.assertEqual(os.readlink(destination / "alias"), raw_target)
        self.assertEqual(outside.read_text(encoding="utf-8"), "external file must not be opened\n")

    def test_index_refresh_never_invokes_git_for_a_link_kind(self):
        state = self.root / "state"
        write(state / "tracked-current-roots.json", '["alias"]')
        for kind in ("symlink", "junction"):
            with mock.patch.object(verify_module, "kind_at", return_value=(kind, None)):
                with mock.patch.object(verify_module, "git") as git_mock:
                    verify_module.refresh_clean_index_entries(self.root / "restore", state)
                    git_mock.assert_not_called()

    def test_path_escape_drive_ads_and_duplicates_are_rejected_before_writes(self):
        for name in ("../escape", "/absolute", "C:/escape", "nested/../escape", "file:stream", "nested\\..\\escape"):
            with self.subTest(name=name):
                archive = self.archive([self.regular(name)])
                with self.assertRaises(RuntimeError):
                    fs.safe_extract_tar(archive, self.root / "restore")
                self.assertFalse((self.root / "restore").exists())
        archive = self.archive([self.regular("same"), self.regular("same")])
        with self.assertRaisesRegex(RuntimeError, "Duplicate"):
            fs.safe_extract_tar(archive, self.root / "restore")

    def test_tar_cannot_write_below_a_link_even_when_external_link_is_allowed(self):
        destination = self.root / "restore"
        outside = self.root / "outside"
        outside.mkdir()
        member = tarfile.TarInfo("alias")
        member.type = tarfile.SYMTYPE
        member.linkname = str(outside)
        archive = self.archive([(member, None), self.regular("alias/new.txt")])
        allowed = {(fs.canonical_path(self.root / "original"), "alias", "symlink", str(outside))}
        with self.assertRaisesRegex(RuntimeError, "descends through"):
            fs.safe_extract_tar(archive, destination, allowed=allowed, source_worktree=self.root / "original")
        self.assertFalse((outside / "new.txt").exists())
        self.assertFalse(destination.exists())

    def test_planned_external_link_chain_requires_permission_for_every_alias(self):
        original, destination = self.root / "source", self.root / "restore"
        outside = self.root / "outside"
        outside.mkdir()
        alias = tarfile.TarInfo("alias")
        alias.type, alias.linkname = tarfile.SYMTYPE, "./later"
        later = tarfile.TarInfo("later")
        later.type, later.linkname = tarfile.SYMTYPE, str(outside)
        archive = self.archive([(alias, None), (later, None)])
        allowed = {(fs.canonical_path(original), "later", "symlink", str(outside))}
        with self.assertRaisesRegex(RuntimeError, "exact allowlist entry: alias"):
            fs.safe_extract_tar(archive, destination, allowed=allowed, source_worktree=original)
        self.assertFalse(destination.exists())

    def test_link_plan_rejects_cycles_and_resolves_parent_after_alias(self):
        original, destination = self.root / "source", self.root / "restore"
        with self.assertRaisesRegex(RuntimeError, "Cyclic"):
            fs.validate_link_plan(destination, [("a", "symlink", "b"), ("b", "symlink", "a")])
        outside = str(self.root / "outside" / "child")
        allowed = {(fs.canonical_path(original), "later", "symlink", outside)}
        with self.assertRaisesRegex(RuntimeError, "exact allowlist entry: alias"):
            fs.validate_link_plan(destination, [("alias", "symlink", "later/../secret"),
                                  ("later", "symlink", outside)], allowed=allowed, source_worktree=original)

    def test_later_payload_cannot_redirect_existing_internal_alias_outside(self):
        original, destination = self.root / "source", self.root / "restore"
        destination.mkdir()
        try:
            os.symlink("later", destination / "alias", target_is_directory=True)
        except OSError as error:
            if getattr(error, "winerror", None) == 1314:
                self.skipTest("Existing Windows symlink privilege unavailable")
            raise
        outside = self.root / "outside"
        outside.mkdir()
        later = tarfile.TarInfo("later")
        later.type, later.linkname = tarfile.SYMTYPE, str(outside)
        archive = self.archive([(later, None)])
        allowed = {(fs.canonical_path(original), "later", "symlink", str(outside))}
        with self.assertRaisesRegex(RuntimeError, "exact allowlist entry: alias"):
            fs.safe_extract_tar(archive, destination, allowed=allowed, source_worktree=original)
        self.assertFalse(os.path.lexists(destination / "later"))

    def test_existing_junction_parent_cannot_receive_later_payload(self):
        if os.name != "nt":
            self.skipTest("Windows junction")
        import _winapi
        destination, outside = self.root / "restore", self.root / "outside"
        destination.mkdir()
        outside.mkdir()
        _winapi.CreateJunction(str(outside), str(destination / "alias"))
        archive = self.archive([self.regular("alias/new.txt")])
        with self.assertRaisesRegex(RuntimeError, "descends through"):
            fs.safe_extract_tar(archive, destination)
        self.assertFalse((outside / "new.txt").exists())

    def test_exact_allowlist_rejects_wrong_path_kind_target_and_worktree(self):
        destination, original = self.root / "restore", self.root / "source"
        target = str(self.root / "outside")
        correct = (fs.canonical_path(original), "alias", "symlink", target)
        for index, replacement in enumerate((fs.canonical_path(self.root / "other"), "other", "junction", target + "-other")):
            wrong = list(correct)
            wrong[index] = replacement
            with self.assertRaisesRegex(RuntimeError, "exact allowlist"):
                fs.validate_link(destination, "alias", "symlink", target, {tuple(wrong)}, original)
        fs.validate_link(destination, "alias", "symlink", target, {correct}, original)

    def test_unknown_reparse_and_archive_kind_are_rejected(self):
        fake = SimpleNamespace(st_file_attributes=0x400, st_reparse_tag=0x80000042, st_mode=0o40755)
        with mock.patch.object(Path, "lstat", return_value=fake):
            with self.assertRaisesRegex(RuntimeError, "Unknown reparse"):
                fs.current_entry(self.root / "unknown", "unknown")
        member = tarfile.TarInfo("unknown")
        member.type, member.linkname = tarfile.SYMTYPE, "inside"
        member.pax_headers[fs.PAX_KIND] = "unknown-reparse"
        archive = self.archive([(member, None)])
        with self.assertRaisesRegex(RuntimeError, "Unknown link/reparse"):
            fs.safe_extract_tar(archive, self.root / "restore")

    def test_old_hardlink_cannot_target_a_symlink_or_escape(self):
        alias = tarfile.TarInfo("alias")
        alias.type, alias.linkname = tarfile.SYMTYPE, "regular"
        hard = tarfile.TarInfo("hard")
        hard.type, hard.linkname = tarfile.LNKTYPE, "alias"
        archive = self.archive([self.regular("regular"), (alias, None), (hard, None)])
        with self.assertRaisesRegex(RuntimeError, "regular member"):
            fs.safe_extract_tar(archive, self.root / "restore")

    def test_full_snapshot_detects_payload_drift_across_two_second_gate(self):
        repo, _, _ = self.create_repository(feature=False)
        write(repo / "untracked.txt", "before\n")
        delays = []
        def change_after_first(seconds):
            delays.append(seconds)
            write(repo / "untracked.txt", "after!\n")
        reader = lambda: capture_module.full_snapshot(repo, "origin", "refs/backup/branch-consolidation/test", {})
        with self.assertRaisesRegex(RuntimeError, "snapshots differ"):
            capture_module.stable_snapshot(reader, sleeper=change_after_first)
        self.assertEqual(delays, [2.0])
        sleeper = mock.Mock()
        stable = capture_module.stable_snapshot(reader, sleeper=sleeper)
        self.assertEqual(stable, reader())
        sleeper.assert_called_once_with(2.0)


if __name__ == "__main__":
    unittest.main()
