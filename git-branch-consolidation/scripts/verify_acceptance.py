#!/usr/bin/env python3
"""Read-only final acceptance for a repository consolidated to its default branch."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from recovery_fs import package_files, canonical_path, canonical_rel, current_entry, path_within
from capture_recovery import assert_supported_worktree

UTF8 = "utf-8"
BACKUP_NAMESPACE = "refs/backup/branch-consolidation"
BUNDLE_NAME = "repository-recovery.bundle"


def run(args, check=True):
    process = subprocess.run(
        [str(value) for value in args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if check and process.returncode != 0:
        raise RuntimeError(
            f"Command failed ({process.returncode}): {args}\n"
            f"stdout={process.stdout.decode(UTF8, 'replace')}\n"
            f"stderr={process.stderr.decode(UTF8, 'replace')}"
        )
    return process


def git(repo, *args, check=True):
    return run(["git", "--no-optional-locks", "-C", repo, *args], check=check)


def decode(data: bytes) -> str:
    return data.decode(UTF8, "surrogateescape")


def git_text(repo, *args, check=True) -> str:
    return decode(git(repo, *args, check=check).stdout).strip()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def parse_ref_lines(raw: bytes) -> dict[str, str]:
    refs = {}
    for line in decode(raw).splitlines():
        if line:
            sha, ref = line.split("\t", 1)
            if not ref.endswith("^{}"):
                refs[ref] = sha
    return dict(sorted(refs.items()))


def local_refs(repo, prefix: str) -> dict[str, str]:
    return parse_ref_lines(
        git(repo, "for-each-ref", "--format=%(objectname)%09%(refname)", prefix).stdout
    )


def live_remote(repo, remote: str) -> dict:
    heads = parse_ref_lines(git(repo, "ls-remote", remote, "refs/heads/*").stdout)
    tags = parse_ref_lines(git(repo, "ls-remote", remote, "refs/tags/*").stdout)
    symbolic_raw = decode(git(repo, "ls-remote", "--symref", remote, "HEAD").stdout)
    match = re.search(r"^ref:\s+(refs/heads/[^\t ]+)\s+HEAD$", symbolic_raw, re.MULTILINE)
    return {
        "heads": heads,
        "tags": tags,
        "symbolicHead": match.group(1) if match else None,
    }


def parse_worktrees(raw: bytes) -> list[dict]:
    worktrees = []
    for block in raw.rstrip(b"\0").split(b"\0\0"):
        item = {}
        for field in block.split(b"\0"):
            if field:
                key, separator, value = decode(field).partition(" ")
                item[key] = value if separator else True
        if item.get("worktree"):
            worktrees.append(item)
    return worktrees


def active_operations(worktree: Path) -> list[str]:
    active = []
    for name in [
        "MERGE_HEAD",
        "CHERRY_PICK_HEAD",
        "REVERT_HEAD",
        "BISECT_LOG",
        "rebase-merge",
        "rebase-apply",
        "sequencer",
    ]:
        raw = git_text(worktree, "rev-parse", "--git-path", name)
        candidate = Path(raw)
        if not candidate.is_absolute():
            candidate = worktree / candidate
        if candidate.exists():
            active.append(name)
    return active


def verify_package(root: Path) -> tuple[bool, str]:
    try:
        manifest = root / "package-manifest.sha256"
        expected = {}
        for line in manifest.read_text(encoding=UTF8).splitlines():
            if line:
                digest, size, relative = line.split("  ", 2)
                relative = canonical_rel(relative)
                if relative in expected:
                    raise RuntimeError(f"Duplicate package manifest path: {relative}")
                expected[relative] = (digest, int(size))
        actual = package_files(root)
        if set(actual) != set(expected):
            return False, "package file set differs from manifest"
        for relative, (digest, size) in expected.items():
            path = actual[relative]
            if path.stat().st_size != size or sha256_file(path) != digest:
                return False, f"package hash mismatch: {relative}"
        return True, f"{len(expected)} files"
    except Exception as error:
        return False, str(error)


def integration_checks(repo: Path, snapshot: Path, protected: dict, expected: str, records_path=None) -> list[dict]:
    """Check work coverage, also usable before any destructive cleanup.

    Human content comparisons use the existing classification fields. Their
    report is retained and hashed in this receipt; it is not a machine proof of
    semantic equivalence. Backup-only and unresolved classifications never pass.
    """
    records = []
    if records_path:
        records = json.loads(Path(records_path).read_text(encoding=UTF8))
        if not isinstance(records, list):
            raise RuntimeError("Integration records must be a JSON array")
    checks = []

    def record(name, ok, detail):
        checks.append({"name": name, "ok": bool(ok), "detail": detail})

    def comparison(source, digest):
        for item in records:
            if item.get("source_ref") != source or item.get("source_sha") != digest:
                continue
            if item.get("classification") not in ("content-covered", "patch-equivalent") or item.get("action") not in ("skip", "merge", "rebase", "cherry-pick"):
                continue
            # Reports are bound to the exact candidate; an older review cannot
            # silently bless subsequent changes or a backup-only disposition.
            if item.get("resulting_sha") != expected:
                continue
            evidence = Path(item.get("evidence", ""))
            if not evidence.is_absolute() and records_path:
                evidence = Path(records_path).resolve().parent / evidence
            if evidence.is_file() and evidence.stat().st_size:
                return {"method": "recorded-content-comparison", "report": str(evidence.resolve()),
                        "sha256": sha256_file(evidence), "machineVerifiedEquivalence": False}
        return None

    sources = dict(protected.get("localHeads", {}))
    sources.update({"remote:" + ref: sha for ref, sha in protected.get("liveRemoteHeads", {}).items()})
    sources.update({"worktree:" + str(index): item["HEAD"] for index, item in enumerate(protected.get("worktrees", [])) if item.get("HEAD")})
    for source, sha in sources.items():
        if git(repo, "merge-base", "--is-ancestor", sha, expected, check=False).returncode == 0:
            record("integrated:" + source, True, {"source": sha, "method": "ancestor"})
            continue
        # git cherry omits merges, so explicitly reject automatic equivalence
        # whenever an uncovered merge commit could contain unique resolution.
        merges = git(repo, "rev-list", "--merges", sha, "--not", expected, check=False)
        cherry = git(repo, "cherry", expected, sha, check=False)
        equivalent = (merges.returncode == 0 and not merges.stdout.strip() and
                      cherry.returncode == 0 and all(line.startswith(b"- ") for line in cherry.stdout.splitlines()))
        detail = {"source": sha, "method": "patch-equivalent"} if equivalent else comparison(source, sha)
        record("integrated:" + source, equivalent or detail is not None, detail or {"source": sha, "reason": "unmerged or unresolved work"})

    def patch_covered(source, patch):
        if not patch:
            return
        # --check writes neither index nor working tree; use stdin, not a temp
        # patch inside the repository. Caller checks candidate HEAD and clean index.
        result = subprocess.run(["git", "--no-optional-locks", "-C", str(repo), "apply", "--reverse", "--check", "--binary", "-"],
                                input=patch, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        digest = hashlib.sha256(patch).hexdigest()
        detail = {"method": "reverse-patch", "source": digest} if result.returncode == 0 else comparison(source, digest)
        record("integrated:" + source, detail is not None, detail or {"source": digest, "reason": "patch not present in candidate"})

    def payload_covered(source, manifest, durable=False):
        if not manifest:
            return
        digest = hashlib.sha256(json.dumps(manifest, sort_keys=True, ensure_ascii=False).encode(UTF8)).hexdigest()
        destinations = [repo]
        if durable:
            destinations += [Path(item["destination"]) for item in records
                             if item.get("source_ref") == source and item.get("source_sha") == digest
                             and item.get("destination") and item.get("resulting_sha") == expected]
        failures = []
        frozen_worktrees = [canonical_path(item["worktree"]) for item in protected.get("worktrees", [])]
        for destination in destinations:
            destination = destination.resolve()
            normalized = canonical_path(destination)
            # A package copy or a soon-to-be-removed worktree is not a usable
            # retained destination. Additional recovery roots can be listed by caller.
            summary = json.loads((snapshot / "snapshot-summary.json").read_text(encoding=UTF8))
            surviving_root = canonical_path(summary["repo"])
            forbidden = [canonical_path(snapshot)] + [path for path in frozen_worktrees
                                                       if path not in (canonical_path(repo), surviving_root)]
            forbidden += [canonical_path(summary[key]) for key in ("primary", "mirror") if summary.get(key)]
            if any(normalized == path or normalized.startswith(path + os.sep) for path in forbidden):
                failures.append("destination is recovery package or removed worktree")
                continue
            try:
                for item in manifest:
                    actual = current_entry(path_within(destination, item["path"]), item["path"])
                    if actual is None or any(actual.get(key) != item.get(key) for key in ("kind", "size", "sha256", "linkTarget")):
                        raise RuntimeError("payload differs: " + item["path"])
                    if not durable and item["kind"] != "directory":
                        if destination != repo or git(repo, "cat-file", "-e", expected + ":" + item["path"], check=False).returncode:
                            raise RuntimeError("payload is not committed: " + item["path"])
                record("integrated:" + source, True, {"source": digest, "method": "payload-content", "destination": str(destination)})
                return
            except (OSError, RuntimeError) as error:
                failures.append(str(error))
        detail = None if durable else comparison(source, digest)
        record("integrated:" + source, detail is not None, detail or {"source": digest, "reason": failures})

    for sha in protected.get("stashCommits", []):
        # Stash ^1 -> stash contains the complete tracked working tree, while
        # ^1 -> ^2 separately protects staged work overwritten in the worktree.
        for suffix, target in (("working", sha), ("index", sha + "^2")):
            result = git(repo, "diff", "--binary", "--full-index", "--no-ext-diff", "--no-textconv", sha + "^1", target, check=False)
            if result.returncode:
                record("integrated:stash:" + sha + ":" + suffix, False, "stash object is unavailable")
            else:
                patch_covered("stash:" + sha + ":" + suffix, result.stdout)
        third = git(repo, "rev-parse", "--verify", sha + "^3", check=False)
        if third.returncode == 0:
            for entry in git(repo, "ls-tree", "-r", "-z", sha + "^3").stdout.split(b"\0"):
                if entry:
                    info, path = entry.split(b"\t", 1)
                    mode, kind, blob = info.split(b" ")
                    final = git(repo, "ls-tree", expected, "--", decode(path)).stdout.strip()
                    ok = final == info + b"\t" + path
                    source = "stash:" + sha + ":untracked:" + decode(path)
                    detail = {"method": "stash-untracked-blob", "source": decode(blob)} if ok else comparison(source, decode(blob))
                    record("integrated:" + source, detail is not None, detail or "stash untracked content is missing")

    for state in sorted((snapshot / "worktrees").iterdir()):
        if not state.is_dir():
            continue
        for name in ("staged", "unstaged"):
            patch_covered("worktree:" + state.name + ":" + name, (state / (name + ".patch")).read_bytes())
        for name in ("untracked", "ignored-preserved"):
            payload_covered("worktree:" + state.name + ":" + name,
                            json.loads((state / (name + "-manifest.json")).read_text(encoding=UTF8)),
                            durable=name == "ignored-preserved")
    return checks


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    parser.add_argument("--remote", default="origin")
    parser.add_argument("--snapshot", required=True)
    parser.add_argument("--expected-commit", required=True)
    parser.add_argument("--output")
    parser.add_argument("--require-no-ignored", action="store_true")
    parser.add_argument("--require-linear-history", action="store_true")
    parser.add_argument("--integration-records", help="Existing classification records as a JSON array")
    parser.add_argument("--check-integration-only", action="store_true", help="Check the clean candidate and work coverage before cleanup")
    arguments = parser.parse_args()

    expected = arguments.expected_commit.lower()
    if not re.fullmatch(r"[0-9a-f]{40}", expected):
        raise RuntimeError("Expected commit must be a full 40-character SHA")
    repo = Path(arguments.repo).resolve()
    snapshot = Path(arguments.snapshot).resolve()
    summary = json.loads((snapshot / "snapshot-summary.json").read_text(encoding=UTF8))
    protected = json.loads((snapshot / "snapshot" / "protected-objects.json").read_text(encoding=UTF8))
    if summary.get("schemaVersion") not in (2, 3):
        raise RuntimeError("Unsupported recovery-package schema")
    default = summary["defaultBranch"]
    default_ref = f"refs/heads/{default}"
    checks = []

    def record(name: str, ok: bool, detail) -> None:
        checks.append({"name": name, "ok": bool(ok), "detail": detail})

    record("selected-remote-matches-snapshot", arguments.remote == summary["remote"], arguments.remote)
    checks.extend(integration_checks(repo, snapshot, protected, expected, arguments.integration_records))

    actual_root = Path(git_text(repo, "rev-parse", "--show-toplevel")).resolve()
    record("repository-root", canonical_path(actual_root) == canonical_path(repo), str(actual_root))

    symbolic_process = git(repo, "symbolic-ref", "-q", "HEAD", check=False)
    symbolic = decode(symbolic_process.stdout).strip() if symbolic_process.returncode == 0 else None
    head = git_text(repo, "rev-parse", "HEAD")
    record("root-symbolic-head", symbolic == default_ref, symbolic)
    record("root-head-sha", head == expected, head)

    local_heads = local_refs(repo, "refs/heads")
    record("local-heads-only-default", local_heads == {default_ref: expected}, local_heads)
    tracking_ref = f"refs/remotes/{arguments.remote}/{default}"
    tracking_process = git(repo, "rev-parse", "--verify", tracking_ref, check=False)
    tracking_sha = decode(tracking_process.stdout).strip() if tracking_process.returncode == 0 else None
    record("remote-tracking-default", tracking_sha == expected, {"ref": tracking_ref, "sha": tracking_sha})

    live = live_remote(repo, arguments.remote)
    record("remote-symbolic-head", live["symbolicHead"] == default_ref, live["symbolicHead"])
    record("remote-heads-only-default", live["heads"] == {default_ref: expected}, live["heads"])
    record("local-tags-preserved", local_refs(repo, "refs/tags") == protected["localTags"], local_refs(repo, "refs/tags"))
    record("remote-tags-preserved", live["tags"] == summary["liveRemote"]["tags"], live["tags"])
    original_other_refs = {ref: sha for ref, sha in protected["allRefs"].items()
                           if not ref.startswith(("refs/heads/", "refs/tags/", "refs/remotes/" + arguments.remote + "/", BACKUP_NAMESPACE + "/"))
                           and ref != "refs/stash"}
    current_all_refs = local_refs(repo, "refs")
    record("nonbranch-and-other-remote-refs-preserved", all(current_all_refs.get(ref) == sha for ref, sha in original_other_refs.items()), original_other_refs)

    worktrees = parse_worktrees(git(repo, "worktree", "list", "--porcelain", "-z").stdout)
    one_root_worktree = (
        len(worktrees) == 1
        and canonical_path(worktrees[0].get("worktree", "")) == canonical_path(repo)
        and worktrees[0].get("branch") == default_ref
        and worktrees[0].get("HEAD") == expected
    )
    record("single-default-worktree", one_root_worktree, worktrees)

    stash = decode(git(repo, "stash", "list", "--format=%gd%x09%H").stdout).strip()
    record("stash-empty", not stash, stash)
    status = git(repo, "status", "--porcelain=v1", "--untracked-files=all", "-z").stdout
    record("working-tree-clean", not status, decode(status))
    ignored_status = git(
        repo,
        "status",
        "--porcelain=v1",
        "--untracked-files=normal",
        "--ignored=matching",
        "-z",
    ).stdout
    ignored_entries = [
        item for item in ignored_status.split(b"\0") if item.startswith(b"!! ")
    ]
    record(
        "ignored-content-policy",
        (not ignored_entries) if arguments.require_no_ignored else True,
        {
            "requiredEmpty": arguments.require_no_ignored,
            "entries": [decode(item[3:]) for item in ignored_entries],
        },
    )

    backup_refs = local_refs(repo, BACKUP_NAMESPACE)
    record("temporary-backup-refs-removed", not backup_refs, backup_refs)
    common_dir_raw = git_text(repo, "rev-parse", "--git-common-dir")
    common_dir = Path(common_dir_raw)
    if not common_dir.is_absolute():
        common_dir = repo / common_dir
    pollution = sorted(str(path) for path in common_dir.resolve().rglob("*.baiduyun.uploading.cfg"))
    record("no-cloud-sync-ref-pollution", not pollution, pollution)
    operations = active_operations(repo)
    record("no-active-git-operation", not operations, operations)
    try:
        assert_supported_worktree(repo)
        record("supported-git-state", True, "No hidden index, sparse or submodule state")
    except RuntimeError as error:
        record("supported-git-state", False, str(error))
    unmerged = git(repo, "ls-files", "--unmerged", "-z").stdout
    record("no-unmerged-index", not unmerged, decode(unmerged))

    diff_check = git(repo, "diff", "--check", check=False)
    record(
        "working-diff-check",
        diff_check.returncode == 0 and not diff_check.stdout,
        decode(diff_check.stdout + diff_check.stderr),
    )
    frozen = summary["frozenDefaultSha"]
    range_check = git(repo, "diff", "--check", f"{frozen}..{expected}", check=False)
    record(
        "new-range-diff-check",
        range_check.returncode == 0 and not range_check.stdout,
        decode(range_check.stdout + range_check.stderr),
    )
    conflict_scan = git(
        repo,
        "grep",
        "-n",
        "-I",
        "-E",
        r"^(<<<<<<< .+|>>>>>>> .+)$",
        "--",
        ".",
        check=False,
    )
    record(
        "no-tracked-conflict-markers",
        conflict_scan.returncode == 1,
        decode(conflict_scan.stdout + conflict_scan.stderr),
    )

    ancestor = git(repo, "merge-base", "--is-ancestor", frozen, expected, check=False)
    record("frozen-default-is-ancestor", ancestor.returncode == 0, {"frozen": frozen, "final": expected})
    merges = git(repo, "rev-list", "--merges", f"{frozen}..{expected}", check=False)
    record("new-history-is-linear", not arguments.require_linear_history or (merges.returncode == 0 and not merges.stdout.strip()),
           {"required": arguments.require_linear_history, "merges": decode(merges.stdout + merges.stderr)})

    package_ok, package_detail = verify_package(snapshot)
    record("recovery-package-manifest", package_ok, package_detail)
    bundle = snapshot / BUNDLE_NAME
    bundle_hash = sha256_file(bundle) if bundle.exists() else None
    record("recovery-bundle-hash", bundle_hash == summary["bundleSha256"], bundle_hash)
    bundle_verify = git(repo, "bundle", "verify", bundle, check=False)
    record(
        "recovery-bundle-verify",
        bundle_verify.returncode == 0,
        decode(bundle_verify.stdout + bundle_verify.stderr),
    )

    fsck = git(repo, "fsck", "--full", check=False)
    record("git-fsck-full", fsck.returncode == 0, decode(fsck.stdout + fsck.stderr))
    log_all = git(repo, "log", "--all", "--oneline", check=False)
    record("git-log-all-readable", log_all.returncode == 0, decode(log_all.stderr))

    if arguments.check_integration_only:
        required = {"selected-remote-matches-snapshot", "repository-root", "root-head-sha", "working-tree-clean",
                    "frozen-default-is-ancestor", "new-history-is-linear", "recovery-package-manifest",
                    "recovery-bundle-hash", "recovery-bundle-verify", "no-active-git-operation", "no-unmerged-index",
                    "no-tracked-conflict-markers", "new-range-diff-check", "git-fsck-full", "supported-git-state"}
        checks = [item for item in checks if item["name"] in required or item["name"].startswith("integrated:")]
    result = {
        "schemaVersion": 1,
        "verifiedUtc": datetime.now(timezone.utc).isoformat(),
        "ok": all(item["ok"] for item in checks),
        "repo": str(repo),
        "remote": arguments.remote,
        "defaultBranch": default,
        "expectedCommit": expected,
        "integrationOnly": arguments.check_integration_only,
        "frozenDefaultCommit": frozen,
        "checks": checks,
    }
    serialized = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if arguments.output:
        output = Path(arguments.output).resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(serialized, encoding=UTF8, newline="\n")
    print(json.dumps(result, ensure_ascii=False), flush=True)
    sys.exit(0 if result["ok"] else 1)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding=UTF8)
    sys.stderr.reconfigure(encoding=UTF8)
    try:
        main()
    except Exception as error:
        print(f"FATAL: {error}", file=sys.stderr, flush=True)
        sys.exit(2)
