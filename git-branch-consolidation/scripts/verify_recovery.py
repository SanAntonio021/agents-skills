#!/usr/bin/env python3
"""Verify dual packages and replay every captured Git worktree in isolation."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import subprocess
import sys
import tarfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from recovery_fs import (
    LINK_KINDS, canonical_path, canonical_rel, current_entry, inventory_tree,
    io_path, manifest_for_roots, package_files, path_within, plain_path, sha256_file,
)
from recovery_fs import kind_at, load_external_link_allowlist, safe_extract_tar, validate_link, validate_link_plan
from recovery_fs import validate_rebuild_disposition, validate_reproducible_roots_metadata

UTF8 = "utf-8"
BUNDLE_NAME = "repository-recovery.bundle"


def log(message: str) -> None:
    print(f"[{datetime.now(timezone.utc).isoformat()}] {message}", flush=True)


def run(args, cwd=None, check=True, input_bytes=None):
    if os.name == "nt" and str(args[0]) == "git":
        args = [args[0], "-c", "core.longpaths=true", *args[1:]]
    process = subprocess.run(
        [plain_path(value) if isinstance(value, Path) else str(value) for value in args],
        cwd=plain_path(cwd) if cwd else None,
        input=input_bytes,
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


def git(repo, *args, check=True, input_bytes=None):
    return run(
        ["git", "--no-optional-locks", "-C", repo, *args],
        check=check,
        input_bytes=input_bytes,
    )


def git_bare(git_dir, *args, check=True, input_bytes=None):
    return run(
        ["git", "--no-optional-locks", f"--git-dir={plain_path(git_dir)}", *args],
        check=check,
        input_bytes=input_bytes,
    )


def is_within(candidate, parent) -> bool:
    try:
        return os.path.commonpath([canonical_path(candidate), canonical_path(parent)]) == canonical_path(parent)
    except ValueError:
        return False


def verify_package(root: Path) -> dict[str, tuple[str, int]]:
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
        raise RuntimeError(
            f"Package file-set mismatch for {root}: "
            f"missing={sorted(set(expected) - set(actual))}, extra={sorted(set(actual) - set(expected))}"
        )
    for relative, (digest, size) in expected.items():
        path = actual[relative]
        if path.stat().st_size != size or sha256_file(path) != digest:
            raise RuntimeError(f"Package hash mismatch: {path}")
    return expected


def verify_manifest(worktree: Path, state_source: Path, roots_file: str, manifest_file: str) -> int:
    roots = json.loads((state_source / roots_file).read_text(encoding=UTF8))
    expected = json.loads((state_source / manifest_file).read_text(encoding=UTF8))
    actual = manifest_for_roots(worktree, roots)
    if actual != expected:
        raise RuntimeError(f"Payload manifest mismatch: {manifest_file} in {worktree}")
    return len(expected)


def ignored_records(state_source: Path, snapshot_version: int) -> tuple[dict, list, bool]:
    """Read the sealed representation; never consult a new external disposition.

    A restore must also work after the original worktree has disappeared. Root
    identities are therefore validated as recorded data, not compared to the
    original filesystem or recreated by running an arbitrary rebuild command.
    """
    disposition = json.loads((state_source / "ignored-disposition.json").read_text(encoding=UTF8))
    validate_rebuild_disposition(disposition)
    version = disposition.get("schemaVersion", 1)
    if snapshot_version not in (2, 3) or (snapshot_version == 2 and version != 1):
        raise RuntimeError("Incompatible snapshot and ignored disposition versions")
    lightweight = version == 2
    filename = "ignored-reproducible-roots.json" if lightweight else "ignored-reproducible-manifest.json"
    forbidden = "ignored-reproducible-manifest.json" if lightweight else "ignored-reproducible-roots.json"
    if (state_source / forbidden).exists():
        raise RuntimeError("Ambiguous reproducible cache representation")
    entries = json.loads((state_source / filename).read_text(encoding=UTF8))
    if lightweight:
        validate_reproducible_roots_metadata(entries, disposition)
        # Check the captured Git index and protected payloads, not the cache's
        # contents. Ignored exclusions cannot hide a protected file.
        protected = []
        for row in (state_source / "ls-files-stage.z").read_bytes().split(b"\0"):
            if row:
                protected.append(row.split(b"\t", 1)[1].decode(UTF8, "surrogateescape"))
        for category in ("tracked-current", "untracked", "ignored-preserved"):
            manifest = json.loads((state_source / f"{category}-manifest.json").read_text(encoding=UTF8))
            protected.extend(item["path"] for item in manifest)
        for root in disposition["reproducible"]:
            folded = canonical_rel(root).casefold()
            if any((name := canonical_rel(path).casefold()) == folded or name.startswith(folded + "/")
                   for path in protected):
                raise RuntimeError(f"Lightweight cache covers a protected path: {root}")
    elif not isinstance(entries, list):
        raise RuntimeError("Invalid legacy reproducible manifest")
    return disposition, entries, lightweight


def read_bundle_heads(repo: Path, bundle: Path) -> dict[str, str]:
    process = git(repo, "bundle", "list-heads", bundle)
    heads = {}
    for line in process.stdout.decode(UTF8, "replace").splitlines():
        sha, ref = line.split(" ", 1)
        heads[ref] = sha
    return heads


def write_log(root: Path, name: str, process) -> None:
    (root / f"{name}.stdout").write_bytes(process.stdout)
    (root / f"{name}.stderr").write_bytes(process.stderr)


def refresh_clean_index_entries(worktree: Path, state_source: Path) -> None:
    """Refresh stat data only where the restored worktree already equals the index."""
    roots = json.loads((state_source / "tracked-current-roots.json").read_text(encoding=UTF8))
    for relative in roots:
        candidate = path_within(worktree, relative)
        if kind_at(candidate)[0] != "file":
            continue
        index_object = git(worktree, "rev-parse", "--verify", f":{relative}", check=False)
        if index_object.returncode != 0:
            continue
        worktree_object = git(
            worktree,
            "hash-object",
            f"--path={relative}",
            "--",
            relative,
            check=False,
        )
        if worktree_object.returncode != 0:
            continue
        if index_object.stdout.strip() == worktree_object.stdout.strip():
            refreshed = git(worktree, "add", "--", relative, check=False)
            if refreshed.returncode != 0:
                raise RuntimeError(f"Could not refresh restored index stat data for {relative}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--mirror", required=True)
    parser.add_argument("--restore", required=True)
    parser.add_argument("--external-link-allowlist", help="JSON schemaVersion=1: links with exact original worktree, relative path, kind and literal target")
    arguments = parser.parse_args()

    source = io_path(Path(arguments.source).resolve())
    mirror = io_path(Path(arguments.mirror).resolve())
    restore = io_path(Path(arguments.restore).resolve())
    allowed_links = load_external_link_allowlist(arguments.external_link_allowlist)
    if canonical_path(source) == canonical_path(mirror):
        raise RuntimeError("Source and mirror resolve to the same path")
    if restore.exists():
        raise RuntimeError(f"Restore destination already exists: {restore}")
    for package in (source, mirror):
        if is_within(restore, package) or is_within(package, restore):
            raise RuntimeError(f"Restore destination overlaps recovery package {package}")
    restore.mkdir(parents=True)
    logs = restore / "logs"
    logs.mkdir()

    log("verifying both sealed package manifests")
    source_manifest = verify_package(source)
    mirror_manifest = verify_package(mirror)
    if source_manifest != mirror_manifest:
        raise RuntimeError("Primary and mirror package manifests differ")
    if (source / "package-manifest.sha256").read_bytes() != (mirror / "package-manifest.sha256").read_bytes():
        raise RuntimeError("Primary and mirror manifest files are not byte-identical")

    summary = json.loads((source / "snapshot-summary.json").read_text(encoding=UTF8))
    mirror_summary = json.loads((mirror / "snapshot-summary.json").read_text(encoding=UTF8))
    if summary != mirror_summary or summary.get("schemaVersion") not in (2, 3):
        raise RuntimeError("Package summaries differ or use an unsupported schema")
    refbase = summary["refbase"]
    source_bundle = source / BUNDLE_NAME
    mirror_bundle = mirror / BUNDLE_NAME
    if sha256_file(source_bundle) != summary["bundleSha256"]:
        raise RuntimeError("Primary bundle hash differs from snapshot summary")
    if sha256_file(source_bundle) != sha256_file(mirror_bundle):
        raise RuntimeError("Primary and mirror bundle hashes differ")

    verification_repo = restore / "bundle-verification.git"
    init = run(["git", "init", "--bare", verification_repo], check=False)
    write_log(logs, "bundle-verification-init", init)
    if init.returncode != 0:
        raise RuntimeError("Could not create the bundle-verification repository")
    for label, bundle in [("primary", source_bundle), ("mirror", mirror_bundle)]:
        process = git_bare(verification_repo, "bundle", "verify", bundle, check=False)
        write_log(logs, f"bundle-verify-{label}", process)
        if process.returncode != 0:
            raise RuntimeError(f"{label} bundle verification failed")

    expected_refs = json.loads((source / "snapshot" / "backup-refs.json").read_text(encoding=UTF8))
    bundle_heads = read_bundle_heads(verification_repo, source_bundle)
    if any(bundle_heads.get(ref) != sha for ref, sha in expected_refs.items()):
        raise RuntimeError("Bundle heads differ from the protected backup-ref map")

    log("cloning the bundle into an isolated mirror repository")
    bare = restore / "repository.git"
    clone = run(["git", "clone", "--mirror", source_bundle, bare], check=False)
    write_log(logs, "clone", clone)
    if clone.returncode != 0:
        raise RuntimeError("Bundle mirror clone failed")

    restored_refs_raw = git_bare(bare, "for-each-ref", "--format=%(objectname)%09%(refname)", refbase).stdout
    restored_refs = {}
    for line in restored_refs_raw.decode(UTF8, "replace").splitlines():
        sha, ref = line.split("\t", 1)
        restored_refs[ref] = sha
    if restored_refs != expected_refs:
        raise RuntimeError("Restored backup refs differ from the recovery package")

    protected = json.loads((source / "snapshot" / "protected-objects.json").read_text(encoding=UTF8))
    for sha in sorted(set(protected["allRefs"].values())):
        if git_bare(bare, "cat-file", "-e", sha, check=False).returncode != 0:
            raise RuntimeError(f"Protected ref object is unavailable after restore: {sha}")
    commit_ids = set(protected["reflogCommits"]) | set(protected["stashCommits"])
    commit_ids |= set(protected["localHeads"].values())
    commit_ids |= set(protected["remoteTracking"].values())
    commit_ids |= set(protected["liveRemoteHeads"].values())
    commit_ids |= {item["HEAD"] for item in protected["worktrees"] if item.get("HEAD")}
    for sha in sorted(commit_ids):
        if git_bare(bare, "cat-file", "-e", f"{sha}^{{commit}}", check=False).returncode != 0:
            raise RuntimeError(f"Protected commit is unavailable after restore: {sha}")

    summaries = json.loads((source / "snapshot" / "worktree-summaries.json").read_text(encoding=UTF8))
    states_root = restore / "states"
    states_root.mkdir()
    results = []
    log(f"replaying {len(summaries)} worktree states")
    for metadata in summaries:
        index = metadata["index"]
        state_source = source / "worktrees" / f"{index:03d}"
        state_destination = states_root / f"{index:03d}"
        head = metadata["head"]
        disposition, reproducible_expected, lightweight = ignored_records(state_source, summary["schemaVersion"])
        link_manifest = state_source / "links.json"
        if link_manifest.exists():
            recorded = json.loads(link_manifest.read_text(encoding=UTF8))
            expected_links = []
            for category in ("tracked-current", "untracked", "ignored-preserved"):
                entries = json.loads((state_source / f"{category}-manifest.json").read_text(encoding=UTF8))
                expected_links.extend(dict(item, payload=category) for item in entries if item["kind"] in LINK_KINDS)
            expected_links.extend(dict(item, payload="ignored-reproducible") for item in reproducible_expected
                                  if item["kind"] in LINK_KINDS)
            if recorded != {"schemaVersion": 1, "entries": expected_links}:
                raise RuntimeError(f"Independent link manifest differs for worktree {index}")
        if lightweight:
            for item in reproducible_expected:
                if item["kind"] in LINK_KINDS:
                    validate_link(state_destination, item["path"], item["kind"], item["linkTarget"],
                                  allowed_links, metadata["worktree"])
        # Checkout also creates unchanged tracked symlinks, which may not appear in
        # a dirty payload. Enforce the same external-link policy before checkout.
        tree = git_bare(bare, "ls-tree", "-r", "-z", head).stdout
        for row in tree.split(b"\0"):
            if not row:
                continue
            header, name = row.split(b"\t", 1)
            mode, _, blob = header.split()
            if mode == b"120000":
                target = git_bare(bare, "cat-file", "blob", blob.decode("ascii")).stdout.decode(UTF8, "surrogateescape")
                validate_link(state_destination, name.decode(UTF8, "surrogateescape"), "symlink", target, allowed_links, metadata["worktree"])
        log(f"restore {index + 1}/{len(summaries)} at {head[:12]}")
        add = git_bare(bare, "worktree", "add", "--detach", state_destination, head, check=False)
        write_log(logs, f"worktree-{index:03d}-add", add)
        if add.returncode != 0:
            raise RuntimeError(f"Could not create restore worktree {index}")

        staged = (state_source / "staged.patch").read_bytes()
        if staged:
            process = git(state_destination, "apply", "--index", "--binary", "-", check=False, input_bytes=staged)
            write_log(logs, f"worktree-{index:03d}-staged", process)
            if process.returncode != 0:
                raise RuntimeError(f"Staged patch replay failed for worktree {index}")
        unstaged = (state_source / "unstaged.patch").read_bytes()
        if unstaged:
            process = git(state_destination, "apply", "--binary", "-", check=False, input_bytes=unstaged)
            write_log(logs, f"worktree-{index:03d}-unstaged", process)
            if process.returncode != 0:
                raise RuntimeError(f"Unstaged patch replay failed for worktree {index}")

        for filename in ("tracked-current.tar", "untracked-payload.tar", "ignored-preserved-payload.tar"):
            safe_extract_tar(state_source / filename, state_destination,
                             allowed=allowed_links, source_worktree=metadata["worktree"])
        validate_link_plan(state_destination, allowed=allowed_links, source_worktree=metadata["worktree"])
        refresh_clean_index_entries(state_destination, state_source)

        expected_status = (state_source / "status-v2-no-branch.z").read_bytes()
        actual_status = git(state_destination, "status", "--porcelain=v2", "--untracked-files=all", "-z").stdout
        if actual_status != expected_status:
            (logs / f"worktree-{index:03d}-expected-status.z").write_bytes(expected_status)
            (logs / f"worktree-{index:03d}-actual-status.z").write_bytes(actual_status)
            raise RuntimeError(f"Status replay mismatch for worktree {index}")

        expected_index = (state_source / "ls-files-stage.z").read_bytes()
        actual_index = git(state_destination, "ls-files", "--stage", "-z").stdout
        if actual_index != expected_index:
            raise RuntimeError(f"Index or file-mode replay mismatch for worktree {index}")

        untracked_count = verify_manifest(
            state_destination,
            state_source,
            "untracked-roots.json",
            "untracked-manifest.json",
        )
        tracked_count = verify_manifest(
            state_destination,
            state_source,
            "tracked-current-roots.json",
            "tracked-current-manifest.json",
        )
        preserved_expected = json.loads((state_source / "ignored-preserved-manifest.json").read_text(encoding=UTF8))
        preserved_actual = manifest_for_roots(state_destination, disposition["preserve"])
        if preserved_actual != preserved_expected:
            raise RuntimeError(f"Preserved ignored payload mismatch for worktree {index}")
        for relative in disposition["reproducible"]:
            if kind_at(path_within(state_destination, relative))[0] is not None:
                raise RuntimeError(f"Reproducible ignored payload was unexpectedly restored: {relative}")
        results.append(
            {
                "index": index,
                "head": head,
                "statusMatch": True,
                "indexMatch": True,
                "untrackedManifestEntries": untracked_count,
                "trackedManifestEntries": tracked_count,
                "ignoredPreservedManifestEntries": len(preserved_expected),
                "ignoredReproducibleManifestEntriesRecorded": 0 if lightweight else len(reproducible_expected),
                "ignoredReproducibleRootEntriesRecorded": len(reproducible_expected) if lightweight else 0,
                "reproducibleRepresentation": "roots" if lightweight else "full-manifest",
            }
        )

    log("running fsck on the isolated restored repository")
    fsck = git_bare(bare, "fsck", "--full", check=False)
    write_log(logs, "fsck", fsck)
    if fsck.returncode != 0:
        raise RuntimeError("Isolated restore git fsck --full failed")

    result = {
        "schemaVersion": 3,
        "snapshotSchemaVersion": summary["schemaVersion"],
        "verifiedUtc": datetime.now(timezone.utc).isoformat(),
        "primaryPackageFiles": len(source_manifest),
        "mirrorPackageFiles": len(mirror_manifest),
        "packagesIdentical": True,
        "bundleSha256": sha256_file(source_bundle),
        "backupRefCount": len(expected_refs),
        "protectedCommitCount": len(commit_ids),
        "worktreeReplays": results,
        "fsckExitCode": fsck.returncode,
        "externalLinkAllowlistEntries": len(allowed_links),
        "externalLinkAllowlistSha256": sha256_file(arguments.external_link_allowlist) if arguments.external_link_allowlist else None,
    }
    (restore / "restore-verification.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding=UTF8,
        newline="\n",
    )
    log("isolated replay verification completed")
    print(json.dumps(result, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding=UTF8)
    sys.stderr.reconfigure(encoding=UTF8)
    try:
        main()
    except Exception as error:
        print(f"FATAL: {error}", file=sys.stderr, flush=True)
        sys.exit(1)
