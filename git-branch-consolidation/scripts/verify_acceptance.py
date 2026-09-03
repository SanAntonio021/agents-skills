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


def canonical_path(path) -> str:
    return os.path.normcase(os.path.realpath(os.path.abspath(str(path))))


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
                expected[relative] = (digest, int(size))
        actual = {
            path.relative_to(root).as_posix(): path
            for path in root.rglob("*")
            if path.is_file() and path.name != manifest.name
        }
        if set(actual) != set(expected):
            return False, "package file set differs from manifest"
        for relative, (digest, size) in expected.items():
            path = actual[relative]
            if path.stat().st_size != size or sha256_file(path) != digest:
                return False, f"package hash mismatch: {relative}"
        return True, f"{len(expected)} files"
    except Exception as error:
        return False, str(error)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    parser.add_argument("--remote", default="origin")
    parser.add_argument("--snapshot", required=True)
    parser.add_argument("--expected-commit", required=True)
    parser.add_argument("--output")
    parser.add_argument("--require-no-ignored", action="store_true")
    arguments = parser.parse_args()

    expected = arguments.expected_commit.lower()
    if not re.fullmatch(r"[0-9a-f]{40}", expected):
        raise RuntimeError("Expected commit must be a full 40-character SHA")
    repo = Path(arguments.repo).resolve()
    snapshot = Path(arguments.snapshot).resolve()
    summary = json.loads((snapshot / "snapshot-summary.json").read_text(encoding=UTF8))
    protected = json.loads((snapshot / "snapshot" / "protected-objects.json").read_text(encoding=UTF8))
    if summary.get("schemaVersion") != 2:
        raise RuntimeError("Unsupported recovery-package schema")
    default = summary["defaultBranch"]
    default_ref = f"refs/heads/{default}"
    checks = []

    def record(name: str, ok: bool, detail) -> None:
        checks.append({"name": name, "ok": bool(ok), "detail": detail})

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
    record(
        "new-history-is-linear",
        merges.returncode == 0 and not merges.stdout.strip(),
        decode(merges.stdout + merges.stderr),
    )

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

    result = {
        "schemaVersion": 1,
        "verifiedUtc": datetime.now(timezone.utc).isoformat(),
        "ok": all(item["ok"] for item in checks),
        "repo": str(repo),
        "remote": arguments.remote,
        "defaultBranch": default,
        "expectedCommit": expected,
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
    try:
        main()
    except Exception as error:
        print(f"FATAL: {error}", file=sys.stderr, flush=True)
        sys.exit(2)
