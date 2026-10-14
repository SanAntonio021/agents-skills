"""Frozen local materials are delivery, while source coverage remains mandatory."""
from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path

from test_recovery_flow import TemporaryGitCase, git, run, write, ACCEPTANCE
import verify_acceptance as acceptance


class RetainedLocalTests(TemporaryGitCase):
    def prepare(self):
        repo, _, _ = self.create_repository(feature=False)
        return repo, self.root / "primary", self.root / "mirror"

    def capture_materials(self, repo, primary, mirror, disposition=None):
        captured = self.capture(repo, primary, mirror, disposition, stamp="retained")
        self.assertEqual(captured.returncode, 0, captured.stdout + captured.stderr)
        self.assertEqual(json.loads((primary / "snapshot-summary.json").read_text(encoding="utf-8"))["schemaVersion"], 4)

    def record(self, repo, primary, destination, category="untracked", state="000", paths=None):
        manifest = json.loads((primary / "worktrees" / state / (category + "-manifest.json")).read_text(encoding="utf-8"))
        if paths is None:
            paths = [item["path"] for item in manifest]
        return {"source_ref": "worktree:" + state + ":" + category,
                "source_sha": acceptance.manifest_digest(manifest), "classification": "retained-local",
                "action": "retain", "reason": "Project measurement data and task process materials",
                "resulting_sha": git(repo, "rev-parse", "HEAD").stdout.strip(),
                "destination": str(destination), "paths": paths,
                "payload": [item for item in manifest if item["path"] in paths]}

    def check(self, repo, primary, records=None):
        extra = ["--check-integration-only"]
        if records is not None:
            records_path = self.root / "records.json"
            write(records_path, json.dumps(records, ensure_ascii=False))
            extra += ["--integration-records", records_path]
        result = run([sys.executable, ACCEPTANCE, "--repo", repo, "--snapshot", primary,
                      "--expected-commit", git(repo, "rev-parse", "HEAD").stdout.strip(), *extra], check=False)
        self.assertNotEqual(result.returncode, 2, result.stdout + result.stderr)
        return result, json.loads(result.stdout)

    def test_source_commits_and_root_materials_stay_usable(self):
        repo, primary, mirror = self.prepare()
        write(repo / "new-source.py", "answer = 42\n")
        write(repo / "tracked.txt", "effective source change\n")
        git(repo, "add", "tracked.txt")
        write(repo / "config.txt", "effective unstaged source change\n")
        write(repo / "data/measurement.csv", "voltage,BER\n1,1e-7\n")
        write(repo / "过程文件/task/state.txt", "ongoing task state\n")
        write(repo / "preserve-cache/result.bin", "retained ignored measurement\n")
        disposition = {"schemaVersion": 2, "worktrees": {str(repo): {
            "preserve": ["preserve-cache"], "reproducible": [], "rebuild": {}}}}
        self.capture_materials(repo, primary, mirror, disposition)
        git(repo, "add", "new-source.py", "tracked.txt", "config.txt")
        git(repo, "commit", "-m", "integrate effective source")
        data_paths = [entry["path"] for entry in json.loads((primary / "worktrees/000/untracked-manifest.json").read_text(encoding="utf-8"))
                      if entry["path"] != "new-source.py"]
        records = [self.record(repo, primary, repo, paths=data_paths),
                   self.record(repo, primary, repo, category="ignored-preserved")]
        result, report = self.check(repo, primary, records)
        self.assertEqual(result.returncode, 0, report)
        self.assertTrue((repo / "data/measurement.csv").is_file())
        self.assertTrue((repo / "过程文件/task/state.txt").is_file())
        self.assertEqual(git(repo, "show", "HEAD:new-source.py").stdout, "answer = 42\n")

    def test_omitted_source_and_unregistered_new_ignored_file_fail(self):
        repo, primary, mirror = self.prepare()
        write(repo / "new-source.py", "answer = 42\n")
        write(repo / "data.csv", "retained data\n")
        self.capture_materials(repo, primary, mirror)
        records = [self.record(repo, primary, repo, paths=["data.csv"])]
        result, report = self.check(repo, primary, records)
        self.assertEqual(result.returncode, 1)
        self.assertTrue(any(not item["ok"] and item["name"] == "integrated:worktree:000:untracked" for item in report["checks"]))
        git(repo, "add", "new-source.py")
        git(repo, "commit", "-m", "integrate source")
        records[0]["resulting_sha"] = git(repo, "rev-parse", "HEAD").stdout.strip()
        write(repo / ".git/info/exclude", "hidden-source.py\n")
        write(repo / "hidden-source.py", "missed_source = True\n")
        result, report = self.check(repo, primary, records)
        self.assertEqual(result.returncode, 1)
        policy = next(item for item in report["checks"] if item["name"] == "working-tree-clean")
        self.assertIn("hidden-source.py", policy["detail"]["unclassifiedIgnored"])

    def test_ignored_preserved_requires_registration_and_content_stability(self):
        repo, primary, mirror = self.prepare()
        write(repo / "preserve-cache/result.bin", "measurement\n")
        disposition = {"schemaVersion": 2, "worktrees": {str(repo): {
            "preserve": ["preserve-cache"], "reproducible": [], "rebuild": {}}}}
        self.capture_materials(repo, primary, mirror, disposition)
        result, _ = self.check(repo, primary)
        self.assertEqual(result.returncode, 1)
        records = [self.record(repo, primary, repo, category="ignored-preserved")]
        result, report = self.check(repo, primary, records)
        self.assertEqual(result.returncode, 0, report)
        write(repo / "preserve-cache/result.bin", "changed measurement\n")
        result, report = self.check(repo, primary, records)
        self.assertEqual(result.returncode, 1)
        self.assertTrue(any(not item["ok"] and item["name"].startswith("integrated:retained-local:") for item in report["checks"]))

    def test_directory_registration_does_not_allow_extra_children(self):
        repo, primary, mirror = self.prepare()
        write(repo / "data/measurement.csv", "measurement\n")
        self.capture_materials(repo, primary, mirror)
        records = [self.record(repo, primary, repo)]
        result, report = self.check(repo, primary, records)
        self.assertEqual(result.returncode, 0, report)
        write(repo / "data/unclassified.py", "missing_source = True\n")
        write(repo / ".git/info/exclude", "data/\n")
        result, report = self.check(repo, primary, records)
        self.assertEqual(result.returncode, 1)

    def test_root_materials_cannot_move_or_exist_only_in_backup(self):
        repo, primary, mirror = self.prepare()
        write(repo / "data.csv", "measurement\n")
        self.capture_materials(repo, primary, mirror)
        retained = self.root / "retained"
        write(retained / "data.csv", "measurement\n")
        record = self.record(repo, primary, retained)
        result, report = self.check(repo, primary, [record])
        self.assertEqual(result.returncode, 1)
        self.assertIn("root local materials", next(item for item in report["checks"]
                                                  if item["name"].startswith("integrated:retained-local:"))["detail"]["reason"])
        (repo / "data.csv").unlink()
        record["destination"] = str(primary)
        result, _ = self.check(repo, primary, [record])
        self.assertEqual(result.returncode, 1)
        record["destination"] = str(repo)
        result, _ = self.check(repo, primary, [record])
        self.assertEqual(result.returncode, 1)

    def test_auxiliary_materials_need_direct_copy_outside_removed_worktree(self):
        repo, primary, mirror = self.prepare()
        linked = self.root / "linked"
        git(repo, "worktree", "add", "--detach", linked)
        write(linked / "measurements/run.csv", "measurement\n")
        self.capture_materials(repo, primary, mirror)
        records = [self.record(repo, primary, linked, state="001")]
        result, _ = self.check(repo, primary, records)
        self.assertEqual(result.returncode, 1)
        retained = self.root / "retained"
        write(retained / "measurements/run.csv", "measurement\n")
        records[0]["destination"] = str(retained)
        result, report = self.check(repo, primary, records)
        self.assertEqual(result.returncode, 0, report)
        git(repo, "worktree", "remove", "--force", linked)
        result, report = self.check(repo, primary, records)
        self.assertEqual(result.returncode, 0, report)
        self.assertEqual((retained / "measurements/run.csv").read_text(encoding="utf-8"), "measurement\n")

    def test_binding_payload_and_manifest_tampering_are_rejected(self):
        repo, primary, mirror = self.prepare()
        write(repo / "data.csv", "measurement\n")
        self.capture_materials(repo, primary, mirror)
        record = self.record(repo, primary, repo)
        for field, value in (("source_sha", "0" * 64), ("resulting_sha", "0" * 40),
                             ("payload", []), ("paths", ["missing.csv"]), ("reason", "")):
            with self.subTest(field=field):
                invalid = dict(record, **{field: value})
                result, _ = self.check(repo, primary, [invalid])
                self.assertEqual(result.returncode, 1)

    def test_stash_data_is_retained_while_source_and_tracked_layers_commit(self):
        repo, primary, mirror = self.prepare()
        git(repo, "config", "core.autocrlf", "false")
        write(repo / "tracked.txt", "staged stash source\n")
        git(repo, "add", "tracked.txt")
        write(repo / "config.txt", "unstaged stash source\n")
        write(repo / "from-stash.py", "source = True\n")
        write(repo / "data.csv", "measurement\n")
        git(repo, "stash", "push", "--include-untracked", "-m", "effective source and data")
        sha = git(repo, "rev-parse", "refs/stash").stdout.strip()
        self.capture_materials(repo, primary, mirror)
        git(repo, "stash", "apply", "--index")
        git(repo, "add", "tracked.txt", "config.txt", "from-stash.py")
        git(repo, "commit", "-m", "integrate stash source")
        manifest = acceptance.stash_untracked_manifest(repo, sha)
        paths = ["data.csv"]
        record = {"source_ref": "stash:" + sha + ":untracked", "source_sha": acceptance.manifest_digest(manifest),
                  "classification": "retained-local", "action": "retain", "reason": "measurement data",
                  "resulting_sha": git(repo, "rev-parse", "HEAD").stdout.strip(), "destination": str(repo),
                  "paths": paths, "payload": [entry for entry in manifest if entry["path"] in paths]}
        result, report = self.check(repo, primary, [record])
        self.assertEqual(result.returncode, 0, report)
        git(repo, "stash", "clear")
        result, report = self.check(repo, primary, [record])
        self.assertEqual(result.returncode, 0, report)
        (repo / "data.csv").unlink()
        result, _ = self.check(repo, primary, [record])
        self.assertEqual(result.returncode, 1)

    def test_legacy_package_records_do_not_relax_clean_policy(self):
        repo, primary, mirror = self.prepare()
        write(repo / "data.csv", "measurement\n")
        self.capture_materials(repo, primary, mirror)
        record = self.record(repo, primary, repo)
        for version in (2, 3):
            with self.subTest(version=version):
                summary_path = primary / "snapshot-summary.json"
                summary = json.loads(summary_path.read_text(encoding="utf-8"))
                summary["schemaVersion"] = version
                write(summary_path, json.dumps(summary))
                # Isolate the policy assertion from package-integrity failure;
                # the normal CLI independently rejects this modified package.
                protected = json.loads((primary / "snapshot/protected-objects.json").read_text(encoding="utf-8"))
                records_path = self.root / "legacy-records.json"
                write(records_path, json.dumps([record]))
                policy = acceptance.working_tree_policy(repo, primary, protected, record["resulting_sha"], records_path,
                                                        acceptance.git(repo, "status", "--porcelain=v1", "--untracked-files=all", "-z").stdout)
                self.assertFalse(policy["ok"])

    def test_frozen_reproducible_cache_can_change_without_new_material_exemption(self):
        repo, primary, mirror = self.prepare()
        write(repo / "build-cache/generated.txt", "rebuildable\n")
        disposition = {"schemaVersion": 2, "worktrees": {str(repo): {
            "preserve": [], "reproducible": ["build-cache"], "rebuild": {"build-cache": "known build command"}}}}
        self.capture_materials(repo, primary, mirror, disposition)
        write(repo / "build-cache/later.tmp", "transient\n")
        result, report = self.check(repo, primary)
        self.assertEqual(result.returncode, 0, report)

    def test_ignored_necessary_dependency_can_be_committed(self):
        repo, primary, mirror = self.prepare()
        write(repo / "preserve-cache/required-model.bin", "necessary dependency bytes\n")
        disposition = {"schemaVersion": 2, "worktrees": {str(repo): {
            "preserve": ["preserve-cache"], "reproducible": [], "rebuild": {}}}}
        self.capture_materials(repo, primary, mirror, disposition)
        git(repo, "add", "--force", "preserve-cache/required-model.bin")
        git(repo, "commit", "-m", "commit necessary dependency")
        result, report = self.check(repo, primary)
        self.assertEqual(result.returncode, 0, report)

    def test_shared_destination_accepts_only_verified_material_union(self):
        repo, primary, mirror = self.prepare()
        write(repo / "data/main.csv", "root measurement\n")
        linked = self.root / "linked"
        git(repo, "worktree", "add", "--detach", linked)
        write(linked / "data/linked.csv", "linked measurement\n")
        self.capture_materials(repo, primary, mirror)
        write(repo / "data/linked.csv", "linked measurement\n")
        records = [self.record(repo, primary, repo), self.record(repo, primary, repo, state="001")]
        result, report = self.check(repo, primary, records)
        self.assertEqual(result.returncode, 0, report)
        records[1]["source_sha"] = "0" * 64
        result, _ = self.check(repo, primary, records)
        self.assertEqual(result.returncode, 1)
        records[1] = self.record(repo, primary, repo, state="001")
        write(repo / "data/unclassified.py", "missed = True\n")
        result, _ = self.check(repo, primary, records)
        self.assertEqual(result.returncode, 1)

    def test_committed_payload_must_match_frozen_blob(self):
        repo, primary, mirror = self.prepare()
        write(repo / "new-source.py", "answer = 42\n")
        self.capture_materials(repo, primary, mirror)
        write(repo / "new-source.py", "answer = 0\n")
        git(repo, "add", "new-source.py")
        git(repo, "commit", "-m", "commit wrong source bytes")
        manifest = json.loads((primary / "worktrees/000/untracked-manifest.json").read_text(encoding="utf-8"))
        self.assertFalse(acceptance.committed_payload_matches(repo, git(repo, "rev-parse", "HEAD").stdout.strip(), manifest[0]))
        result, _ = self.check(repo, primary)
        self.assertEqual(result.returncode, 1)

    def test_ignored_source_normalization_uses_bound_content_record(self):
        repo, primary, mirror = self.prepare()
        git(repo, "config", "core.autocrlf", "true")
        write(repo / "preserve-cache/necessary-source.py", "answer = 42\n")
        (repo / "preserve-cache/necessary-source.py").write_bytes(b"answer = 42\r\n")
        disposition = {"schemaVersion": 2, "worktrees": {str(repo): {
            "preserve": ["preserve-cache"], "reproducible": [], "rebuild": {}}}}
        self.capture_materials(repo, primary, mirror, disposition)
        manifest = json.loads((primary / "worktrees/000/ignored-preserved-manifest.json").read_text(encoding="utf-8"))
        evidence = self.root / "source-comparison.txt"
        write(evidence, "Frozen CRLF source matches committed LF source after built-in newline conversion.\n")
        record = {"source_ref": "worktree:000:ignored-preserved", "source_sha": acceptance.manifest_digest(manifest),
                  "classification": "content-covered", "action": "merge", "evidence": str(evidence),
                  "resulting_sha": git(repo, "rev-parse", "HEAD").stdout.strip()}
        result, _ = self.check(repo, primary, [record])
        self.assertEqual(result.returncode, 1, "A report cannot cover uncommitted necessary source")
        git(repo, "add", "--force", "preserve-cache/necessary-source.py")
        git(repo, "commit", "-m", "commit necessary source with newline conversion")
        record["resulting_sha"] = git(repo, "rev-parse", "HEAD").stdout.strip()
        result, report = self.check(repo, primary, [record])
        self.assertEqual(result.returncode, 0, report)


if __name__ == "__main__":
    unittest.main()
