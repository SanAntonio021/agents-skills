"""Sealed ordinary, external and linked Git layout recovery without live files."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import git_layout as layout
from recovery_fs import canonical_path, io_path, sha256_file


class GitLayoutTests(unittest.TestCase):
    def setUp(self):
        # Git metadata never enters the cloud-sync test/source directory.
        root = Path(os.environ.get("GBC_TEST_ROOT", "D:/AgentSkillTests"))
        root.mkdir(parents=True, exist_ok=True)
        self.root = Path(tempfile.mkdtemp(prefix="git-layout-", dir=root)).resolve()
        environment = layout.recovery_environment()
        environment["XDG_CONFIG_HOME"] = str(self.root / "xdg")
        self.environment = mock.patch.dict(os.environ, environment, clear=True)
        self.environment.start()

    def tearDown(self):
        self.environment.stop()
        if os.environ.get("GBC_KEEP_TEST_ARTIFACTS") != "1":
            shutil.rmtree(io_path(self.root), ignore_errors=True)

    def git(self, repo, *args, check=True):
        process = subprocess.run(["git", "-C", str(repo), *map(str, args)],
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                 env=layout.recovery_environment())
        if check and process.returncode:
            self.fail(process.stderr.decode("utf-8", "replace"))
        return process

    def create(self, separate=False, autocrlf=False):
        repo = self.root / "repo"
        args = ["git", "init", "--initial-branch=main"]
        if separate:
            args += ["--separate-git-dir", str(self.root / "metadata.git")]
        subprocess.run(args + [str(repo)], check=True, capture_output=True,
                       env=layout.recovery_environment())
        self.git(repo, "config", "user.name", "Layout Test")
        self.git(repo, "config", "user.email", "layout@example.invalid")
        self.git(repo, "config", "core.autocrlf", "true" if autocrlf else "false")
        (repo / "text.txt").write_bytes(b"one\r\ntwo\r\n" if autocrlf else b"one\ntwo\n")
        self.git(repo, "add", "--", "text.txt")
        self.git(repo, "commit", "-m", "base")
        return repo

    def seal(self, repo):
        sealed = self.root / "sealed-layout"
        captured = layout.capture_layout(repo, layout.discover_worktrees(repo), sealed)
        bundle = self.root / "recovery.bundle"
        self.git(repo, "bundle", "create", bundle, "--all")
        return sealed, captured, bundle

    def mirror(self, bundle):
        bare = self.root / "recovered.git"
        process = subprocess.run(["git", "clone", "--mirror", str(bundle), str(bare)],
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                 env=layout.recovery_environment())
        self.assertEqual(process.returncode, 0, process.stderr)
        return bare

    def replay(self, sealed, bare, index, head="main"):
        destination = self.root / f"restored-{index}"
        layout.prepare_restore(sealed, bare, index)
        self.git(bare, "worktree", "add", "--detach", destination, head)
        report = layout.configure_restore(sealed, bare, destination, index)
        return destination, report

    def test_ordinary_layout_raw_lf_bytes_and_excludes_are_restored_from_package(self):
        repo = self.create()
        config = repo / ".git/config"
        config.write_bytes(config.read_bytes().replace(b"\r\n", b"\n"))
        (repo / ".git/info/exclude").write_bytes(b"local-data.dat\n")
        sealed, captured, bundle = self.seal(repo)
        self.assertEqual(captured["worktrees"][0]["layout"]["layout_kind"], "ordinary")
        self.assertEqual((sealed / "common/config").read_bytes(), config.read_bytes())
        repo.rename(self.root / "unavailable-original")
        destination, report = self.replay(sealed, self.mirror(bundle), 0)
        (destination / "local-data.dat").write_bytes(b"data")
        self.assertEqual(self.git(destination, "status", "--porcelain").stdout, b"")
        self.assertEqual((destination / "text.txt").read_bytes(), b"one\ntwo\n")
        self.assertEqual(report["savedRawFiles"]["common/config"], sha256_file(sealed / "common/config"))
        self.assertTrue(report["remappedFiles"]["config.worktree"])
        self.assertFalse(report["hooksExecuted"])

    def test_separate_layout_crlf_pointer_include_dependencies_hooks_and_filters(self):
        repo = self.create(separate=True, autocrlf=True)
        metadata = self.root / "metadata.git"
        self.git(repo, "config", "core.worktree", str(repo))
        self.git(repo, "config", "extensions.worktreeConfig", "true")
        self.git(repo, "config", "--worktree", "core.eol", "crlf")
        included = self.root / "included.config"
        empty = self.root / "empty.config"
        empty.write_bytes(b"# empty dependency\r\n")
        included.write_bytes(b"[core]\r\n\tautocrlf = true\r\n[include]\r\n\tpath = empty.config\r\n")
        self.git(repo, "config", "include.path", str(included))
        excluded = self.root / "global-ignore"
        excluded.write_bytes(b"global-data.dat\r\n")
        self.git(repo, "config", "core.excludesfile", str(excluded))
        marker = self.root / "must-not-execute"
        hooks = self.root / "custom-hooks"
        hooks.mkdir()
        (hooks / "post-checkout").write_bytes(("#!/bin/sh\nprintf ran > '" + marker.as_posix() + "'\n").encode())
        self.git(repo, "config", "core.hooksPath", str(hooks))
        (repo / ".gitattributes").write_bytes(b"text.txt filter=audit\n")
        self.git(repo, "add", "--", ".gitattributes")
        self.git(repo, "commit", "-m", "Declare inactive audit filter")
        # Add actions only after the commit: capture reads settings but must not
        # run the filter, hook or fsmonitor. Restore likewise keeps them inert.
        self.git(repo, "config", "filter.audit.smudge", "echo ran > " + marker.as_posix())
        self.git(repo, "config", "filter.audit.clean", "echo ran > " + marker.as_posix())
        self.git(repo, "config", "core.fsmonitor", "echo ran > " + marker.as_posix())
        for raw_file in (repo / ".git", metadata / "config", metadata / "config.worktree"):
            data = raw_file.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
            # Git marks the Windows pointer hidden; OPEN_ALWAYS/truncating wb
            # refuses it, while updating the existing isolated file is allowed.
            with raw_file.open("r+b") as handle:
                handle.write(data)
                handle.truncate()
        pointer = (repo / ".git").read_bytes()
        raw_config = (metadata / "config").read_bytes()
        sealed, captured, bundle = self.seal(repo)
        worktree = captured["worktrees"][0]
        self.assertEqual(worktree["layout"]["layout_kind"], "separate")
        self.assertEqual(canonical_path(worktree["layout"]["worktree"]), canonical_path(repo))
        self.assertEqual((sealed / worktree["files"]["gitPointer"]).read_bytes(), pointer)
        self.assertEqual((sealed / "common/config").read_bytes(), raw_config)
        self.assertIn(b"\r\n", (sealed / worktree["files"]["worktreeConfig"]).read_bytes())
        self.assertEqual({canonical_path(item["source"]) for item in captured["files"].values()} &
                         {canonical_path(included), canonical_path(empty)},
                         {canonical_path(included), canonical_path(empty)})
        repo.rename(self.root / "unavailable-repo")
        metadata.rename(self.root / "unavailable-metadata")
        included.unlink()
        empty.unlink()
        excluded.unlink()
        hooks.rename(self.root / "unavailable-hooks")
        destination, report = self.replay(sealed, self.mirror(bundle), 0)
        self.assertEqual((destination / "text.txt").read_bytes(), b"one\r\ntwo\r\n")
        (destination / "global-data.dat").write_bytes(b"data")
        self.assertEqual(self.git(destination, "status", "--porcelain").stdout, b"")
        self.assertFalse(marker.exists())
        self.assertNotIn(str(repo).encode(), (destination / ".git").read_bytes())
        self.assertEqual(self.git(destination, "config", "--get", "core.worktree").stdout.strip(),
                         str(destination).encode())
        self.assertNotEqual(self.git(destination, "config", "--get", "filter.audit.smudge", check=False).returncode, 0)
        self.assertFalse(report["filtersExecuted"])
        self.assertTrue((Path(report["adminDir"]) / "sealed-layout/hooks/post-checkout").is_file())

    def test_linked_worktrees_keep_distinct_worktree_config(self):
        repo = self.create()
        self.git(repo, "config", "extensions.worktreeConfig", "true")
        self.git(repo, "config", "--worktree", "core.autocrlf", "false")
        linked = self.root / "linked"
        self.git(repo, "worktree", "add", "--detach", linked, "main")
        self.git(linked, "config", "--worktree", "core.autocrlf", "true")
        sealed, captured, bundle = self.seal(repo)
        records = captured["worktrees"]
        linked_records = layout.discover_worktrees(linked)
        self.assertEqual(layout.discover_worktrees(repo, layout.discover_worktrees(repo)),
                         layout.discover_worktrees(repo))
        self.assertEqual([canonical_path(item["worktree"]) for item in linked_records],
                         [canonical_path(item["layout"]["worktree"]) for item in records])
        self.assertEqual([item["layout"]["role"] for item in records], ["main", "linked"])
        self.assertIsNotNone(records[1]["files"]["adminGitdir"])
        self.assertIsNotNone(records[1]["files"]["adminCommondir"])
        self.assertEqual(canonical_path(records[0]["layout"]["common_dir"]),
                         canonical_path(records[1]["layout"]["common_dir"]))
        bare = self.mirror(bundle)
        first, _ = self.replay(sealed, bare, 0)
        second, _ = self.replay(sealed, bare, 1)
        self.assertEqual((first / "text.txt").read_bytes(), b"one\ntwo\n")
        self.assertEqual((second / "text.txt").read_bytes(), b"one\r\ntwo\r\n")
        self.assertEqual(self.git(first, "config", "--worktree", "--get", "core.autocrlf").stdout, b"false\n")
        self.assertEqual(self.git(second, "config", "--worktree", "--get", "core.autocrlf").stdout, b"true\n")

    def test_layout_integrity_rejects_drift_extra_files_and_overwrite(self):
        repo = self.create()
        sealed, captured, _ = self.seal(repo)
        with self.assertRaises(FileExistsError):
            layout.capture_layout(repo, layout.discover_worktrees(repo), sealed)
        self.assertEqual(layout.verify_layout(sealed), captured)
        (sealed / "extra").write_bytes(b"unsealed")
        with self.assertRaisesRegex(RuntimeError, "file-set"):
            layout.verify_layout(sealed)
        (sealed / "extra").unlink()
        with (sealed / "common/config").open("ab") as handle:
            handle.write(b"# drift")
        with self.assertRaisesRegex(RuntimeError, "hash mismatch"):
            layout.verify_layout(sealed)

    def test_config_dependency_links_are_rejected_without_following(self):
        repo = self.create()
        external = self.root / "external.config"
        external.write_bytes(b"[core]\n\tautocrlf = false\n")
        link = self.root / "link.config"
        try:
            link.symlink_to(external)
        except OSError as error:
            self.skipTest("Symlink creation unavailable: " + str(error))
        self.git(repo, "config", "include.path", str(link))
        with self.assertRaisesRegex(RuntimeError, "linked"):
            layout.inspect_layout(repo)
        self.assertEqual(external.read_bytes(), b"[core]\n\tautocrlf = false\n")

    def test_recovery_environment_removes_git_injection(self):
        with mock.patch.dict(os.environ, {"GIT_DIR": "untrusted", "GIT_CONFIG_COUNT": "1",
                                          "GIT_CONFIG_KEY_0": "core.hooksPath",
                                          "GIT_CONFIG_VALUE_0": "untrusted"}):
            environment = layout.recovery_environment()
        self.assertNotIn("GIT_DIR", environment)
        self.assertNotIn("GIT_CONFIG_COUNT", environment)
        self.assertEqual(environment["GIT_CONFIG_GLOBAL"], os.devnull)
        self.assertEqual(environment["GIT_CONFIG_NOSYSTEM"], "1")

    def test_relocation_rebinds_config_and_rejects_local_config_drift(self):
        repo = self.create()
        sealed, _, bundle = self.seal(repo)
        bare = self.mirror(bundle)
        destination, first = self.replay(sealed, bare, 0)
        moved = self.root / "nested-location" / "child"
        moved.parent.mkdir()
        self.git(bare, "worktree", "move", destination, moved)
        relocated = layout.configure_restore(sealed, bare, moved, 0, relocate=True)
        self.assertEqual(relocated["relocations"][0]["destination"], first["destination"])
        self.assertEqual(self.git(moved, "config", "--get", "core.worktree").stdout.strip(), str(moved).encode())
        self.assertEqual(self.git(moved, "status", "--porcelain").stdout, b"")
        self.git(moved, "config", "--worktree", "core.autocrlf", "true")
        with self.assertRaisesRegex(RuntimeError, "drifted"):
            layout.configure_restore(sealed, bare, moved, 0, relocate=True)

    def test_relocation_rebinds_contained_linked_worktree_core_worktree(self):
        repo = self.create()
        source_linked = repo / "checkouts/local"
        self.git(repo, "worktree", "add", "-b", "local", source_linked)
        sealed, _, bundle = self.seal(repo)
        bare = self.mirror(bundle)
        old, _ = self.replay(sealed, bare, 0)
        child = old / "checkouts/local"
        layout.prepare_restore(sealed, bare, 1)
        self.git(bare, "worktree", "add", "--detach", child, "local")
        first = layout.configure_restore(sealed, bare, child, 1)
        moved = self.root / "nested-location/child"
        moved.parent.mkdir()
        self.git(bare, "worktree", "move", old, moved)
        self.git(bare, "worktree", "repair", moved, moved / "checkouts/local")
        layout.configure_restore(sealed, bare, io_path(moved), 0, relocate=True)
        relocated = layout.configure_restore(sealed, bare, io_path(moved / "checkouts/local"), 1, relocate=True)
        self.assertEqual(relocated["relocations"][0]["destination"], first["destination"])
        self.assertEqual(self.git(moved / "checkouts/local", "config", "--get", "core.worktree").stdout.strip(),
                         str(moved / "checkouts/local").encode())
        self.assertEqual(self.git(moved / "checkouts/local", "status", "--porcelain").stdout, b"")
        self.git(moved / "checkouts/local", "config", "--worktree", "core.autocrlf", "true")
        with self.assertRaisesRegex(RuntimeError, "drifted"):
            layout.configure_restore(sealed, bare, moved / "checkouts/local", 1, relocate=True)

    def test_separate_main_without_core_worktree_captures_and_restores_external_linked(self):
        repo = self.create(separate=True)
        remote = self.root / "remote.git"
        self.assertEqual(subprocess.run(["git", "init", "--bare", "--initial-branch=main", str(remote)],
                                        capture_output=True, env=layout.recovery_environment()).returncode, 0)
        self.git(repo, "remote", "add", "origin", remote)
        self.git(repo, "push", "-u", "origin", "main")
        self.git(repo, "tag", "v1")
        self.git(repo, "push", "origin", "v1")
        linked = self.root / "external-linked"
        self.git(repo, "worktree", "add", "-b", "feature", linked, "main")
        (linked / "linked.py").write_bytes(b"value = 42\n")
        self.git(linked, "add", "--", "linked.py")
        self.git(linked, "commit", "-m", "linked source")
        (linked / "linked.py").write_bytes(b"value = 43\n")
        self.git(linked, "add", "--", "linked.py")
        (linked / "linked.py").write_bytes(b"value = 44\n")
        (linked / "new.py").write_bytes(b"new_value = 1\n")
        self.assertNotEqual(self.git(repo, "config", "--local", "--get", "core.worktree", check=False).returncode, 0)
        primary, mirror = self.root / "primary", self.root / "mirror"
        scripts = Path(__file__).resolve().parents[1] / "scripts"
        captured = subprocess.run([sys.executable, str(scripts / "capture_recovery.py"),
                                   "--repo", str(repo), "--remote", "origin", "--primary", str(primary),
                                   "--mirror", str(mirror), "--stamp", "separate-linked"],
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                  env=layout.recovery_environment())
        self.assertEqual(captured.returncode, 0, captured.stdout + captured.stderr)
        snapshot = json.loads((primary / "snapshot-summary.json").read_text(encoding="utf-8"))
        self.assertEqual(snapshot["worktreeCount"], 2)
        # Integration checks run from the candidate linked checkout. It need
        # not infer the separate-git-dir main checkout to report missing work.
        candidate = self.root / "candidate"
        self.git(repo, "worktree", "add", "--detach", candidate, "main")
        head = self.git(candidate, "rev-parse", "HEAD").stdout.decode().strip()
        checked = subprocess.run([sys.executable, str(scripts / "verify_acceptance.py"),
                                  "--repo", str(candidate), "--snapshot", str(primary),
                                  "--expected-commit", head, "--check-integration-only"],
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                 env=layout.recovery_environment())
        self.assertEqual(checked.returncode, 1, checked.stdout + checked.stderr)
        self.assertFalse(json.loads(checked.stdout)["ok"])
        self.git(repo, "worktree", "remove", candidate)
        # Recovery cannot consult either checkout, the external common/admin
        # directory or the original remote after they are renamed away.
        repo.rename(self.root / "unavailable-repo")
        linked.rename(self.root / "unavailable-linked")
        (self.root / "metadata.git").rename(self.root / "unavailable-metadata")
        remote.rename(self.root / "unavailable-remote.git")
        restore = self.root / "restore"
        replay = subprocess.run([sys.executable, str(primary / "restore-runtime/verify_recovery.py"),
                                 "--source", str(primary), "--mirror", str(mirror), "--restore", str(restore)],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                env=layout.recovery_environment())
        self.assertEqual(replay.returncode, 0, replay.stdout + replay.stderr)
        recovered = restore / "states/001"
        self.assertEqual((recovered / "linked.py").read_bytes(), b"value = 44\n")
        self.assertEqual(self.git(recovered, "show", ":linked.py").stdout, b"value = 43\n")
        self.assertEqual((recovered / "new.py").read_bytes(), b"new_value = 1\n")
        receipt = json.loads((restore / "restore-verification.json").read_text(encoding="utf-8"))
        self.assertTrue(all(item["statusMatch"] and item["indexMatch"] for item in receipt["worktreeReplays"]))


if __name__ == "__main__":
    unittest.main()
