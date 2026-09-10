#!/usr/bin/env python3
"""Capture a fail-closed, dual-copy Git branch-consolidation recovery package."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tarfile
from datetime import datetime, timezone
from pathlib import Path

from recovery_fs import (
    LINK_KINDS, canonical_path, canonical_rel, current_entry, inventory_tree,
    io_path, manifest_for_roots, package_files, path_within, plain_path, sha256_file,
    kind_at, reproducible_roots_metadata, validate_rebuild_disposition,
)
from recovery_fs import create_payload_tar, walk_paths
import time

UTF8 = "utf-8"
BACKUP_NAMESPACE = "refs/backup/branch-consolidation"


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


def decode(data: bytes) -> str:
    return data.decode(UTF8, "surrogateescape")


def git_text(repo, *args, check=True) -> str:
    return decode(git(repo, *args, check=check).stdout).strip()


def write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding=UTF8, newline="\n")


def write_json(path: Path, value) -> None:
    write_text(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def is_within(candidate, parent) -> bool:
    candidate = canonical_path(candidate)
    parent = canonical_path(parent)
    try:
        return os.path.commonpath([candidate, parent]) == parent
    except ValueError:
        return False


def parse_ref_lines(raw: bytes) -> dict[str, str]:
    refs = {}
    for line in decode(raw).splitlines():
        if not line:
            continue
        sha, ref = line.split("\t", 1)
        if not ref.endswith("^{}"):
            refs[ref] = sha
    return dict(sorted(refs.items()))


def local_refs(repo, prefix: str, excluded_prefix: str | None = None) -> dict[str, str]:
    raw = git(repo, "for-each-ref", "--format=%(objectname)%09%(refname)", prefix).stdout
    refs = parse_ref_lines(raw)
    if excluded_prefix:
        refs = {ref: sha for ref, sha in refs.items() if not ref.startswith(excluded_prefix + "/")}
    return dict(sorted(refs.items()))


def live_remote(repo, remote: str) -> dict:
    heads = parse_ref_lines(git(repo, "ls-remote", remote, "refs/heads/*").stdout)
    tags = parse_ref_lines(git(repo, "ls-remote", remote, "refs/tags/*").stdout)
    symbolic_raw = decode(git(repo, "ls-remote", "--symref", remote, "HEAD").stdout)
    match = re.search(r"^ref:\s+(refs/heads/[^\t ]+)\s+HEAD$", symbolic_raw, re.MULTILINE)
    if not match:
        raise RuntimeError(f"Remote {remote!r} has no unambiguous symbolic HEAD")
    default_ref = match.group(1)
    if default_ref not in heads:
        raise RuntimeError(f"Remote symbolic HEAD {default_ref} is absent from live heads")
    return {
        "heads": heads,
        "tags": tags,
        "symbolicHead": default_ref,
        "symbolicHeadRaw": symbolic_raw,
    }


def parse_worktrees(raw: bytes) -> list[dict]:
    worktrees = []
    for block in raw.rstrip(b"\0").split(b"\0\0"):
        item = {}
        for field in block.split(b"\0"):
            if not field:
                continue
            key, separator, value = decode(field).partition(" ")
            item[key] = value if separator else True
        if item.get("worktree"):
            worktrees.append(item)
    return worktrees


def status_roots(raw: bytes, prefix: bytes) -> list[str]:
    values = []
    for item in raw.split(b"\0"):
        if item.startswith(prefix):
            values.append(canonical_rel(decode(item[len(prefix) :])))
    return sorted(set(values), key=str.casefold)


def parse_nul_paths(raw: bytes) -> list[str]:
    return [canonical_rel(decode(item)) for item in raw.split(b"\0") if item]


def load_ignored_dispositions(path: str | None) -> dict:
    if path is None:
        return {}
    payload = json.loads(io_path(path).read_text(encoding=UTF8))
    version = payload.get("schemaVersion")
    if version not in (1, 2) or not isinstance(payload.get("worktrees"), dict):
        raise RuntimeError("Ignored disposition must use schemaVersion 1 or 2 and a worktrees object")
    result = {}
    for worktree, disposition in payload["worktrees"].items():
        if not isinstance(disposition, dict):
            raise RuntimeError(f"Invalid ignored disposition for {worktree}")
        preserve = [canonical_rel(value) for value in disposition.get("preserve", [])]
        reproducible = [canonical_rel(value) for value in disposition.get("reproducible", [])]
        folded_preserve = {value.casefold() for value in preserve}
        folded_reproducible = {value.casefold() for value in reproducible}
        if len(folded_preserve) != len(preserve) or len(folded_reproducible) != len(reproducible):
            raise RuntimeError(f"Duplicate ignored path disposition for {worktree}")
        overlap = sorted(folded_preserve & folded_reproducible)
        if overlap:
            raise RuntimeError(f"Ignored paths have two dispositions for {worktree}: {overlap}")
        key = canonical_path(worktree)
        if key in result:
            raise RuntimeError(f"Duplicate worktree entry in ignored disposition: {worktree}")
        result[key] = {
            "preserve": sorted(preserve, key=str.casefold),
            "reproducible": sorted(reproducible, key=str.casefold),
        }
        if version == 2:
            result[key].update(schemaVersion=2, rebuild=disposition.get("rebuild"))
        validate_rebuild_disposition(result[key])
    return result


def command_capture(repo, destination: Path, args, check=True):
    process = git(repo, *args, check=check)
    write_bytes(destination, process.stdout)
    if process.stderr:
        write_bytes(destination.with_suffix(destination.suffix + ".stderr"), process.stderr)
    return process


def active_operations(worktree: Path) -> list[dict]:
    names = [
        "MERGE_HEAD",
        "CHERRY_PICK_HEAD",
        "REVERT_HEAD",
        "BISECT_LOG",
        "rebase-merge",
        "rebase-apply",
        "sequencer",
    ]
    active = []
    for name in names:
        raw = git_text(worktree, "rev-parse", "--git-path", name)
        candidate = Path(raw)
        if not candidate.is_absolute():
            candidate = worktree / candidate
        if candidate.exists():
            active.append({"name": name, "path": str(candidate.resolve())})
    return active


def filtered_reflog(repo, refbase: str) -> bytes:
    raw = git(repo, "reflog", "show", "--all", "--date=iso-strict", "--format=%H%x09%gD%x09%gs").stdout
    kept = []
    marker = f"\t{refbase}@{{"
    marker_child = f"\t{refbase}/"
    for line in decode(raw).splitlines():
        if marker not in line and marker_child not in line:
            kept.append(line)
    return (("\n".join(kept) + "\n") if kept else "").encode(UTF8, "surrogateescape")


def validate_disposition(
    worktree: Path,
    ignored_roots: list[str],
    disposition: dict[str, list[str]],
) -> None:
    validate_rebuild_disposition(disposition)
    expected = {value.casefold(): value for value in ignored_roots}
    declared = {
        value.casefold(): value
        for value in disposition["preserve"] + disposition["reproducible"]
    }
    missing = sorted(set(expected) - set(declared))
    extra = sorted(set(declared) - set(expected))
    if missing or extra:
        raise RuntimeError(
            f"Ignored disposition is incomplete for {worktree}: "
            f"missing={[expected[key] for key in missing]}, extra={[declared[key] for key in extra]}"
        )


def assert_supported_worktree(worktree: Path) -> None:
    """Stop before destructive use when the package cannot replay Git state."""
    if active_operations(worktree) or git(worktree, "ls-files", "--unmerged", "-z").stdout:
        raise RuntimeError(f"Git operation or unmerged index in {worktree}")
    flags = git(worktree, "ls-files", "-v", "-z").stdout.split(b"\0")
    if any(item and (item[:1].islower() or item[:1] == b"S") for item in flags):
        raise RuntimeError(f"assume-unchanged/skip-worktree entries require separate recovery: {worktree}")
    if git_text(worktree, "config", "--bool", "core.sparseCheckout", check=False) == "true":
        raise RuntimeError(f"Sparse checkout requires separate recovery: {worktree}")
    stages = git(worktree, "ls-files", "--stage", "-z").stdout.split(b"\0")
    if any(item.startswith(b"160000 ") for item in stages):
        raise RuntimeError(f"Submodule state requires separate recovery: {worktree}")


def protection_snapshot(worktree: Path, disposition: dict) -> dict:
    """Re-enumerate using Git; never reuse a stale ignored classification."""
    assert_supported_worktree(worktree)
    status = git(worktree, "status", "--porcelain=v1", "--untracked-files=normal", "--ignored=matching", "-z").stdout
    ignored = status_roots(status, b"!! ")
    validate_disposition(worktree, ignored, disposition)
    tracked = sorted(set(parse_nul_paths(git(worktree, "ls-files", "-z").stdout)))
    others = sorted(set(parse_nul_paths(git(worktree, "ls-files", "--others", "--exclude-standard", "-z").stdout)))
    lightweight = disposition.get("schemaVersion", 1) == 2
    if lightweight:
        for root in disposition["reproducible"]:
            folded = root.casefold()
            if any(name.casefold() == folded or name.casefold().startswith(folded + "/")
                   or folded.startswith(name.casefold() + "/") for name in tracked + others):
                raise RuntimeError(f"Reproducible root overlaps a protected Git path: {root}")
    # Git reports a nested repository as a directory rather than its contents.
    for name in others:
        path = path_within(worktree, name)
        if kind_at(path)[0] == "directory" and (
                kind_at(path / ".git")[0] is not None
                or (kind_at(path / "HEAD")[0] == "file" and kind_at(path / "objects")[0] == "directory")):
            raise RuntimeError(f"Nested repository requires separate recovery: {path}")
    rules = {}
    # All potentially active ignore files outside excluded cache interiors.
    for name in tracked + others:
        if name.rsplit("/", 1)[-1] == ".gitignore":
            rules[name] = current_entry(path_within(worktree, name), name)
    exclude = Path(git_text(worktree, "rev-parse", "--git-path", "info/exclude"))
    if not exclude.is_absolute():
        exclude = worktree / exclude
    external = [exclude]
    global_exclude = git_text(worktree, "config", "--path", "--get", "core.excludesFile", check=False)
    if global_exclude:
        global_path = Path(global_exclude).expanduser()
        external.append(global_path if global_path.is_absolute() else worktree / global_path)
    else:
        external.append(Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))) / "git" / "ignore")
    for index, path in enumerate(external):
        rules[f"external-{index}"] = {"path": plain_path(path), "entry": current_entry(path, "ignore-rule")}
    # Ancestor .gitignore files can themselves be ignored; capture their bytes.
    for root in disposition["reproducible"]:
        parts = root.split("/")
        for end in range(len(parts)):
            name = "/".join(parts[:end] + [".gitignore"])
            rules[name] = current_entry(path_within(worktree, name), name)
    return {"tracked": tracked, "untracked": others if lightweight else status_roots(status, b"?? "),
            "ignored": ignored, "rules": rules,
            "reproducibleRoots": reproducible_roots_metadata(worktree, disposition) if lightweight else None}


def reject_nested_payload(manifest: list[dict]) -> None:
    if any(".git" in item["path"].split("/") for item in manifest):
        raise RuntimeError("Nested repository in protected payload requires separate recovery")


def backup_worktree(
    repo: Path,
    worktree_record: dict,
    index: int,
    output_root: Path,
    ignored_dispositions: dict[str, dict[str, list[str]]],
) -> dict:
    worktree = io_path(worktree_record["worktree"])
    output = output_root / f"{index:03d}"
    output.mkdir(parents=True, exist_ok=False)
    metadata = dict(worktree_record)
    metadata.update({"index": index, "exists": worktree.exists(), "root": canonical_path(worktree) == canonical_path(repo)})
    if not worktree.exists():
        write_json(output / "metadata.json", metadata)
        raise RuntimeError(f"Registered worktree is missing: {worktree}")

    operations = active_operations(worktree)
    if operations:
        write_json(output / "active-git-operations.json", operations)
        raise RuntimeError(f"Git operation is active in {worktree}: {operations}")
    unmerged = git(worktree, "ls-files", "--unmerged", "-z").stdout
    if unmerged:
        write_bytes(output / "unmerged-index.z", unmerged)
        raise RuntimeError(f"Unmerged index entries exist in {worktree}")

    head = git_text(worktree, "rev-parse", "HEAD")
    branch_process = git(worktree, "symbolic-ref", "-q", "HEAD", check=False)
    branch = decode(branch_process.stdout).strip() if branch_process.returncode == 0 else None
    metadata.update({"head": head, "branch": branch})

    command_capture(worktree, output / "status-v2.z", ("status", "--porcelain=v2", "--branch", "--untracked-files=all", "-z"))
    status_no_branch = command_capture(
        worktree,
        output / "status-v2-no-branch.z",
        ("status", "--porcelain=v2", "--untracked-files=all", "-z"),
    ).stdout
    command_capture(worktree, output / "status-v2.txt", ("status", "--porcelain=v2", "--branch", "--untracked-files=all"))
    status_v1 = command_capture(
        worktree,
        output / "status-v1-with-ignored.z",
        ("status", "--porcelain=v1", "--untracked-files=normal", "--ignored=matching", "-z"),
    ).stdout
    staged = command_capture(
        worktree,
        output / "staged.patch",
        ("diff", "--cached", "--binary", "--full-index", "--no-ext-diff", "--no-textconv"),
    ).stdout
    unstaged = command_capture(
        worktree,
        output / "unstaged.patch",
        ("diff", "--binary", "--full-index", "--no-ext-diff", "--no-textconv"),
    ).stdout
    index_raw = command_capture(worktree, output / "ls-files-stage.z", ("ls-files", "--stage", "-z")).stdout
    command_capture(worktree, output / "ls-files-stage.txt", ("ls-files", "--stage"))
    command_capture(worktree, output / "diff-summary.txt", ("diff", "--summary", "--no-textconv"))
    command_capture(worktree, output / "diff-cached-summary.txt", ("diff", "--cached", "--summary", "--no-textconv"))

    ignored_roots = status_roots(status_v1, b"!! ")
    disposition = ignored_dispositions.get(canonical_path(worktree), {"preserve": [], "reproducible": []})
    protection = protection_snapshot(worktree, disposition)
    write_json(output / "protection-state.json", protection)
    untracked_roots = protection["untracked"]
    lightweight = disposition.get("schemaVersion", 1) == 2

    modified_paths = set()
    for command in [
        ("diff", "--name-only", "-z", "--no-renames", "--diff-filter=ACMRTUXB", "--no-textconv"),
        ("diff", "--cached", "--name-only", "-z", "--no-renames", "--diff-filter=ACMRTUXB", "--no-textconv"),
    ]:
        modified_paths.update(parse_nul_paths(git(worktree, *command).stdout))
    tracked_roots = []
    for relative in sorted(modified_paths, key=str.casefold):
        candidate = path_within(worktree, relative)
        if candidate.exists() or candidate.is_symlink():
            tracked_roots.append(relative)

    untracked_manifest = manifest_for_roots(worktree, untracked_roots)
    tracked_manifest = manifest_for_roots(worktree, tracked_roots)
    preserved_manifest = manifest_for_roots(worktree, disposition["preserve"])
    reproducible_manifest = (protection["reproducibleRoots"] if lightweight
                             else manifest_for_roots(worktree, disposition["reproducible"]))
    for manifest in (untracked_manifest, tracked_manifest, preserved_manifest):
        reject_nested_payload(manifest)

    create_payload_tar(worktree, untracked_roots, output / "untracked-payload.tar")
    create_payload_tar(worktree, tracked_roots, output / "tracked-current.tar")
    create_payload_tar(worktree, disposition["preserve"], output / "ignored-preserved-payload.tar")

    write_json(output / "untracked-roots.json", untracked_roots)
    write_json(output / "ignored-roots.json", ignored_roots)
    write_json(output / "ignored-disposition.json", disposition)
    write_json(output / "tracked-current-roots.json", tracked_roots)
    write_json(output / "untracked-manifest.json", untracked_manifest)
    write_json(output / "tracked-current-manifest.json", tracked_manifest)
    write_json(output / "ignored-preserved-manifest.json", preserved_manifest)
    write_json(output / ("ignored-reproducible-roots.json" if lightweight else "ignored-reproducible-manifest.json"), reproducible_manifest)
    write_json(output / "links.json", {
        "schemaVersion": 1,
        "entries": [dict(item, payload=category)
                    for category, manifest in [("tracked-current", tracked_manifest),
                        ("untracked", untracked_manifest), ("ignored-preserved", preserved_manifest),
                        ("ignored-reproducible", reproducible_manifest)]
                    for item in manifest if item["kind"] in LINK_KINDS],
    })
    metadata.update(
        {
            "statusBytes": len(status_no_branch),
            "stagedPatchBytes": len(staged),
            "unstagedPatchBytes": len(unstaged),
            "indexBytes": len(index_raw),
            "untrackedRootCount": len(untracked_roots),
            "untrackedEntryCount": len(untracked_manifest),
            "ignoredPreservedRootCount": len(disposition["preserve"]),
            "ignoredPreservedEntryCount": len(preserved_manifest),
            "ignoredReproducibleRootCount": len(disposition["reproducible"]),
            "ignoredReproducibleEntryCount": len(reproducible_manifest),
            "trackedCurrentEntryCount": len(tracked_manifest),
        }
    )
    write_json(output / "metadata.json", metadata)
    return metadata


def verify_worktree_unchanged(worktree: Path, state_dir: Path) -> None:
    metadata = json.loads((state_dir / "metadata.json").read_text(encoding=UTF8))
    if git_text(worktree, "rev-parse", "HEAD") != metadata["head"]:
        raise RuntimeError(f"HEAD changed while freezing {worktree}")
    branch_process = git(worktree, "symbolic-ref", "-q", "HEAD", check=False)
    branch = decode(branch_process.stdout).strip() if branch_process.returncode == 0 else None
    if branch != metadata["branch"]:
        raise RuntimeError(f"Branch changed while freezing {worktree}")
    if active_operations(worktree):
        raise RuntimeError(f"A Git operation started while freezing {worktree}")

    comparisons = [
        (("status", "--porcelain=v2", "--untracked-files=all", "-z"), "status-v2-no-branch.z"),
        (("ls-files", "--stage", "-z"), "ls-files-stage.z"),
        (("diff", "--cached", "--binary", "--full-index", "--no-ext-diff", "--no-textconv"), "staged.patch"),
        (("diff", "--binary", "--full-index", "--no-ext-diff", "--no-textconv"), "unstaged.patch"),
    ]
    for command, filename in comparisons:
        actual = git(worktree, *command).stdout
        expected = (state_dir / filename).read_bytes()
        if actual != expected:
            raise RuntimeError(f"{filename} changed while freezing {worktree}")

    status_v1 = git(
        worktree,
        "status",
        "--porcelain=v1",
        "--untracked-files=normal",
        "--ignored=matching",
        "-z",
    ).stdout
    disposition = json.loads((state_dir / "ignored-disposition.json").read_text(encoding=UTF8))
    protection = protection_snapshot(worktree, disposition)
    if (state_dir / "protection-state.json").exists() and protection != json.loads((state_dir / "protection-state.json").read_text(encoding=UTF8)):
        raise RuntimeError(f"Git protection/classification changed while freezing {worktree}")
    if protection["untracked"] != json.loads((state_dir / "untracked-roots.json").read_text(encoding=UTF8)):
        raise RuntimeError(f"Untracked roots changed while freezing {worktree}")
    if status_roots(status_v1, b"!! ") != json.loads((state_dir / "ignored-roots.json").read_text(encoding=UTF8)):
        raise RuntimeError(f"Ignored roots changed while freezing {worktree}")

    root_manifest_pairs = [
        ("untracked-roots.json", "untracked-manifest.json"),
        ("tracked-current-roots.json", "tracked-current-manifest.json"),
    ]
    for roots_file, manifest_file in root_manifest_pairs:
        roots = json.loads((state_dir / roots_file).read_text(encoding=UTF8))
        expected = json.loads((state_dir / manifest_file).read_text(encoding=UTF8))
        if manifest_for_roots(worktree, roots) != expected:
            raise RuntimeError(f"{manifest_file} changed while freezing {worktree}")
    for key, manifest_file in [
        ("preserve", "ignored-preserved-manifest.json"),
        ("reproducible", "ignored-reproducible-manifest.json"),
    ]:
        if key == "reproducible" and disposition.get("schemaVersion", 1) == 2:
            expected = json.loads((state_dir / "ignored-reproducible-roots.json").read_text(encoding=UTF8))
            if protection["reproducibleRoots"] != expected:
                raise RuntimeError(f"Reproducible roots changed while freezing {worktree}")
            continue
        expected = json.loads((state_dir / manifest_file).read_text(encoding=UTF8))
        if manifest_for_roots(worktree, disposition[key]) != expected:
            raise RuntimeError(f"{manifest_file} changed while freezing {worktree}")


def package_manifest(root: Path) -> int:
    lines = []
    for relative, path in sorted(package_files(root).items(), key=lambda item: item[0].casefold()):
        lines.append(f"{sha256_file(path)}  {path.stat().st_size}  {relative}")
    write_text(root / "package-manifest.sha256", "\n".join(lines) + "\n")
    return len(lines)


def verify_package(root: Path) -> int:
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
            f"Package file set differs for {root}: "
            f"missing={sorted(set(expected) - set(actual))}, extra={sorted(set(actual) - set(expected))}"
        )
    for relative, (digest, size) in expected.items():
        path = actual[relative]
        if path.stat().st_size != size or sha256_file(path) != digest:
            raise RuntimeError(f"Package hash mismatch: {path}")
    return len(expected)


def assert_output_paths(repo: Path, worktrees: list[dict], primary: Path, mirror: Path) -> None:
    if primary.exists() or mirror.exists():
        raise RuntimeError("Primary and mirror destinations must both be absent")
    if canonical_path(primary) == canonical_path(mirror):
        raise RuntimeError("Primary and mirror destinations resolve to the same path")
    if is_within(primary, mirror) or is_within(mirror, primary):
        raise RuntimeError("Primary and mirror destinations must not contain one another")
    protected_paths = [repo] + [Path(item["worktree"]) for item in worktrees]
    for output in (primary, mirror):
        for protected in protected_paths:
            if is_within(output, protected) or is_within(protected, output):
                raise RuntimeError(f"Recovery output {output} overlaps repository worktree {protected}")


def full_snapshot(repo: Path, remote: str, refbase: str, dispositions: dict) -> dict:
    """Read every protected state, including payload bytes and clean tracked files."""
    worktrees_raw = git(repo, "worktree", "list", "--porcelain", "-z").stdout
    result = {
        "liveRemote": live_remote(repo, remote),
        "refs": local_refs(repo, "refs", excluded_prefix=refbase),
        "worktreesRaw": decode(worktrees_raw),
        "stash": decode(git(repo, "stash", "list", "--format=%gd%x09%H%x09%gs").stdout),
        "reflog": decode(filtered_reflog(repo, refbase)),
        "config": decode(git(repo, "config", "--list", "--show-origin").stdout),
        "worktrees": [],
    }
    for record in parse_worktrees(worktrees_raw):
        worktree = io_path(record["worktree"])
        status = git(worktree, "status", "--porcelain=v1", "--untracked-files=normal", "--ignored=matching", "-z").stdout
        untracked, ignored = status_roots(status, b"?? "), status_roots(status, b"!! ")
        disposition = dispositions.get(canonical_path(worktree), {"preserve": [], "reproducible": []})
        protection = protection_snapshot(worktree, disposition)
        tracked, untracked = protection["tracked"], protection["untracked"]
        ignored_manifest_roots = (disposition["preserve"] if disposition.get("schemaVersion", 1) == 2 else ignored)
        index_path = Path(git_text(worktree, "rev-parse", "--git-path", "index"))
        if not index_path.is_absolute():
            index_path = worktree / index_path
        item = {
            "record": record,
            "head": git_text(worktree, "rev-parse", "HEAD"),
            "branch": git_text(worktree, "symbolic-ref", "-q", "HEAD", check=False),
            "indexSha256": sha256_file(index_path),
            "stage": decode(git(worktree, "ls-files", "--stage", "-z").stdout),
            "status": decode(status),
            "statusAll": decode(git(worktree, "status", "--porcelain=v2", "--untracked-files=all", "-z").stdout),
            "stagedPatchSha256": hashlib.sha256(git(worktree, "diff", "--cached", "--binary", "--full-index", "--no-ext-diff", "--no-textconv").stdout).hexdigest(),
            "unstagedPatchSha256": hashlib.sha256(git(worktree, "diff", "--binary", "--full-index", "--no-ext-diff", "--no-textconv").stdout).hexdigest(),
            "tracked": [current_entry(path_within(worktree, name), name) for name in tracked],
            "untracked": manifest_for_roots(worktree, untracked),
            "ignored": manifest_for_roots(worktree, ignored_manifest_roots),
            "disposition": disposition,
            "protection": protection,
        }
        for manifest in (item["untracked"], item["ignored"]):
            reject_nested_payload(manifest)
        result["worktrees"].append(item)
    return result


def stable_snapshot(reader, sleeper=time.sleep) -> dict:
    first = reader()
    sleeper(2.0)
    second = reader()
    if first != second:
        raise RuntimeError("Full frozen snapshots differ across the 2-second interval")
    return second


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    parser.add_argument("--remote", default="origin")
    parser.add_argument("--primary", required=True)
    parser.add_argument("--mirror", required=True)
    parser.add_argument("--stamp", required=True)
    parser.add_argument("--ignored-disposition")
    arguments = parser.parse_args()

    repo = io_path(Path(arguments.repo).resolve())
    primary = io_path(Path(arguments.primary).resolve())
    mirror = io_path(Path(arguments.mirror).resolve())
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,80}", arguments.stamp):
        raise RuntimeError("Stamp must be a safe 1-81 character Git ref segment")
    refbase = f"{BACKUP_NAMESPACE}/{arguments.stamp}"
    if git(repo, "check-ref-format", f"{refbase}/probe", check=False).returncode != 0:
        raise RuntimeError(f"Invalid backup ref namespace: {refbase}")

    actual_root = Path(git_text(repo, "rev-parse", "--show-toplevel")).resolve()
    if canonical_path(actual_root) != canonical_path(repo):
        raise RuntimeError(f"Repository root mismatch: expected {repo}, Git reports {actual_root}")
    if local_refs(repo, refbase):
        raise RuntimeError(f"Backup ref namespace already exists: {refbase}")

    worktrees_raw = git(repo, "worktree", "list", "--porcelain", "-z").stdout
    worktrees = parse_worktrees(worktrees_raw)
    if not worktrees:
        raise RuntimeError("No registered worktree was found")
    assert_output_paths(repo, worktrees, primary, mirror)
    dispositions = load_ignored_dispositions(arguments.ignored_disposition)
    disposition_hash = sha256_file(arguments.ignored_disposition) if arguments.ignored_disposition else None

    def current_snapshot():
        if arguments.ignored_disposition and (
                sha256_file(arguments.ignored_disposition) != disposition_hash
                or load_ignored_dispositions(arguments.ignored_disposition) != dispositions):
            raise RuntimeError("Ignored disposition changed during capture")
        return full_snapshot(repo, arguments.remote, refbase, dispositions)
    registered = {canonical_path(item["worktree"]) for item in worktrees}
    unknown_dispositions = sorted(set(dispositions) - registered)
    if unknown_dispositions:
        raise RuntimeError(f"Ignored disposition names unregistered worktrees: {unknown_dispositions}")

    common_dir_raw = git_text(repo, "rev-parse", "--git-common-dir")
    common_dir = Path(common_dir_raw)
    if not common_dir.is_absolute():
        common_dir = repo / common_dir
    common_dir = io_path(common_dir.resolve())
    for output in (primary, mirror):
        if is_within(output, common_dir) or is_within(common_dir, output):
            raise RuntimeError(f"Recovery output {output} overlaps Git common directory {common_dir}")
    pollution = sorted(str(path) for path in (path for path in walk_paths(common_dir) if path.name.endswith(".baiduyun.uploading.cfg")))
    if pollution:
        raise RuntimeError(f"Cloud-sync Git metadata pollution is present: {pollution}")
    for record in worktrees:
        worktree = io_path(record["worktree"])
        if not worktree.exists():
            raise RuntimeError(f"Registered worktree is missing: {worktree}")
        operations = active_operations(worktree)
        if operations:
            raise RuntimeError(f"Git operation is active in {record['worktree']}: {operations}")
        if git(worktree, "ls-files", "--unmerged", "-z").stdout:
            raise RuntimeError(f"Unmerged index entries exist in {worktree}")
        ignored_status = git(
            worktree,
            "status",
            "--porcelain=v1",
            "--untracked-files=normal",
            "--ignored=matching",
            "-z",
        ).stdout
        disposition = dispositions.get(
            canonical_path(worktree),
            {"preserve": [], "reproducible": []},
        )
        protection_snapshot(worktree, disposition)

    log(f"fetching {arguments.remote} and reading live refs")
    fetch = git(repo, "fetch", "--prune", arguments.remote)
    live_before = live_remote(repo, arguments.remote)
    log("reading two complete frozen snapshots, separated by at least 2 seconds")
    frozen = stable_snapshot(current_snapshot)
    if frozen["liveRemote"] != live_before or frozen["worktreesRaw"] != decode(worktrees_raw):
        raise RuntimeError("Remote or worktrees changed before the stable snapshot")

    primary.mkdir(parents=True)
    snapshot_dir = primary / "snapshot"
    snapshot_dir.mkdir()
    write_bytes(snapshot_dir / "fetch.stdout", fetch.stdout)
    write_bytes(snapshot_dir / "fetch.stderr", fetch.stderr)
    write_json(snapshot_dir / "live-remote-before-pin.json", live_before)
    write_json(snapshot_dir / "ignored-dispositions.json", dispositions)
    write_json(snapshot_dir / "full-frozen-state.json", frozen)
    write_json(snapshot_dir / "stability-check.json", {"snapshotsMatch": True, "minimumIntervalSeconds": 2})

    all_refs_before = local_refs(repo, "refs", excluded_prefix=refbase)
    local_heads = local_refs(repo, "refs/heads")
    remote_tracking = local_refs(repo, "refs/remotes")
    local_tags = local_refs(repo, "refs/tags")
    stash_raw = git(repo, "stash", "list", "--format=%gd%x09%H%x09%gs").stdout
    reflog_raw = filtered_reflog(repo, refbase)
    root_symbolic_process = git(repo, "symbolic-ref", "-q", "HEAD", check=False)
    root_symbolic = decode(root_symbolic_process.stdout).strip() if root_symbolic_process.returncode == 0 else None
    root_head = git_text(repo, "rev-parse", "HEAD")
    if current_snapshot() != frozen:
        raise RuntimeError("Full frozen state drifted before pinning protected refs")

    log("pinning every protected object under temporary backup refs")
    backup_map = {}
    for source_ref, sha in all_refs_before.items():
        destination = f"{refbase}/original-refs/{source_ref[len('refs/'):]}"
        git(repo, "update-ref", destination, sha)
        backup_map[destination] = sha

    for ref, sha in list(live_before["heads"].items()) + list(live_before["tags"].items()):
        category = "remote-heads" if ref.startswith("refs/heads/") else "remote-tags"
        prefix = "refs/heads/" if category == "remote-heads" else "refs/tags/"
        destination = f"{refbase}/{category}/{ref[len(prefix):]}"
        fetch_pin = git(
            repo,
            "fetch",
            "--no-tags",
            "--no-write-fetch-head",
            arguments.remote,
            f"+{ref}:{destination}",
        )
        if fetch_pin.stderr:
            with (snapshot_dir / "pin-fetch.stderr").open("ab") as handle:
                handle.write(fetch_pin.stderr)
        actual = git_text(repo, "rev-parse", destination)
        if actual != sha:
            raise RuntimeError(f"Remote ref drifted while pinning {ref}: expected {sha}, got {actual}")
        backup_map[destination] = sha

    stash_commits = []
    for line in decode(stash_raw).splitlines():
        if line:
            _, sha, _ = (line.split("\t", 2) + ["", ""])[:3]
            stash_commits.append(sha)
    reflog_commits = []
    for line in decode(reflog_raw).splitlines():
        if line:
            reflog_commits.append(line.split("\t", 1)[0])
    worktree_commits = [record.get("HEAD") for record in worktrees if record.get("HEAD")]
    for category, commits in [
        ("stash", stash_commits),
        ("reflog", reflog_commits),
        ("worktrees", worktree_commits),
    ]:
        for index, sha in enumerate(dict.fromkeys(commits)):
            if git(repo, "cat-file", "-e", f"{sha}^{{commit}}", check=False).returncode != 0:
                raise RuntimeError(f"Protected {category} object is not a readable commit: {sha}")
            destination = f"{refbase}/{category}/{index:05d}"
            git(repo, "update-ref", destination, sha)
            backup_map[destination] = sha

    actual_backup = local_refs(repo, refbase)
    if actual_backup != dict(sorted(backup_map.items())):
        raise RuntimeError("Temporary backup refs differ from the planned protected-object map")

    live_after_pin = live_remote(repo, arguments.remote)
    if live_after_pin != live_before:
        raise RuntimeError("Live remote changed while protected objects were being pinned")

    write_json(snapshot_dir / "live-remote-after-pin.json", live_after_pin)
    write_json(snapshot_dir / "backup-refs.json", actual_backup)
    write_json(
        snapshot_dir / "protected-objects.json",
        {
            "allRefs": all_refs_before,
            "localHeads": local_heads,
            "remoteTracking": remote_tracking,
            "localTags": local_tags,
            "liveRemoteHeads": live_before["heads"],
            "liveRemoteTags": live_before["tags"],
            "worktrees": worktrees,
            "stashCommits": sorted(set(stash_commits)),
            "reflogCommits": sorted(set(reflog_commits)),
        },
    )
    write_bytes(snapshot_dir / "worktrees.porcelain.z", worktrees_raw)
    write_bytes(snapshot_dir / "stash.tsv", stash_raw)
    write_bytes(snapshot_dir / "reflog.tsv", reflog_raw)
    write_json(snapshot_dir / "root-head.json", {"symbolic": root_symbolic, "sha": root_head})
    config_snapshot = git(repo, "config", "--list", "--show-origin").stdout
    write_bytes(snapshot_dir / "git-config-origin.txt", config_snapshot)
    command_capture(repo, snapshot_dir / "remote-v.txt", ("remote", "-v"))

    log(f"capturing {len(worktrees)} worktree states")
    worktree_root = primary / "worktrees"
    worktree_root.mkdir()
    summaries = []
    for index, record in enumerate(worktrees):
        log(f"worktree {index + 1}/{len(worktrees)}: {record['worktree']}")
        summaries.append(backup_worktree(repo, record, index, worktree_root, dispositions))
    write_json(snapshot_dir / "worktree-summaries.json", summaries)

    log("capturing Git metadata and validating source objects")
    metadata_names = [name for name in ["HEAD", "config", "packed-refs", "logs", "refs"] if (common_dir / name).exists()]
    create_payload_tar(common_dir, metadata_names, primary / "git-metadata" / "git-metadata.tar")
    fsck = git(repo, "fsck", "--full", check=False)
    write_bytes(snapshot_dir / "fsck.stdout", fsck.stdout)
    write_bytes(snapshot_dir / "fsck.stderr", fsck.stderr)
    write_json(snapshot_dir / "fsck-result.json", {"exitCode": fsck.returncode})
    if fsck.returncode != 0:
        raise RuntimeError("Source git fsck --full failed")
    command_capture(repo, snapshot_dir / "log-all.txt", ("log", "--all", "--decorate=full", "--date=iso-strict", "--pretty=fuller"))

    log(f"creating bundle from {len(actual_backup)} explicit backup refs")
    bundle = primary / "repository-recovery.bundle"
    revisions = ("\n".join(sorted(actual_backup)) + "\n").encode(UTF8)
    bundle_create = git(repo, "bundle", "create", bundle, "--stdin", input_bytes=revisions)
    write_bytes(snapshot_dir / "bundle-create.stdout", bundle_create.stdout)
    write_bytes(snapshot_dir / "bundle-create.stderr", bundle_create.stderr)
    bundle_verify = git(repo, "bundle", "verify", bundle, check=False)
    write_bytes(snapshot_dir / "bundle-verify.stdout", bundle_verify.stdout)
    write_bytes(snapshot_dir / "bundle-verify.stderr", bundle_verify.stderr)
    if bundle_verify.returncode != 0:
        raise RuntimeError("Primary bundle verification failed")
    bundle_heads_raw = git(repo, "bundle", "list-heads", bundle).stdout
    write_bytes(snapshot_dir / "bundle-heads.tsv", bundle_heads_raw)
    bundle_heads = {}
    for line in decode(bundle_heads_raw).splitlines():
        sha, ref = line.split(" ", 1)
        bundle_heads[ref] = sha
    if any(bundle_heads.get(ref) != sha for ref, sha in actual_backup.items()):
        raise RuntimeError("Bundle does not expose every protected backup ref at the frozen SHA")

    log("rechecking the frozen source and remote before sealing packages")
    if live_remote(repo, arguments.remote) != live_before:
        raise RuntimeError("Live remote changed before package sealing")
    if local_refs(repo, "refs", excluded_prefix=refbase) != all_refs_before:
        raise RuntimeError("Repository refs changed before package sealing")
    if git(repo, "worktree", "list", "--porcelain", "-z").stdout != worktrees_raw:
        raise RuntimeError("Registered worktrees changed before package sealing")
    if git(repo, "stash", "list", "--format=%gd%x09%H%x09%gs").stdout != stash_raw:
        raise RuntimeError("Stash changed before package sealing")
    if filtered_reflog(repo, refbase) != reflog_raw:
        raise RuntimeError("Reflog changed before package sealing")
    if git(repo, "config", "--list", "--show-origin").stdout != config_snapshot:
        raise RuntimeError("Git configuration changed before package sealing")
    if list((path for path in walk_paths(common_dir) if path.name.endswith(".baiduyun.uploading.cfg"))):
        raise RuntimeError("Cloud-sync Git metadata pollution appeared before package sealing")
    for index, record in enumerate(worktrees):
        verify_worktree_unchanged(io_path(record["worktree"]), worktree_root / f"{index:03d}")
    if current_snapshot() != frozen:
        raise RuntimeError("Full frozen state changed before package sealing")

    default_ref = live_before["symbolicHead"]
    summary = {
        "schemaVersion": 3,
        "createdUtc": datetime.now(timezone.utc).isoformat(),
        "primary": plain_path(primary),
        "mirror": plain_path(mirror),
        "repo": str(repo),
        "remote": arguments.remote,
        "stamp": arguments.stamp,
        "refbase": refbase,
        "defaultBranch": default_ref[len("refs/heads/") :],
        "frozenDefaultSha": live_before["heads"][default_ref],
        "rootHead": {"symbolic": root_symbolic, "sha": root_head},
        "liveRemote": live_before,
        "localHeadCount": len(local_heads),
        "remoteHeadCount": len(live_before["heads"]),
        "localTagCount": len(local_tags),
        "remoteTagCount": len(live_before["tags"]),
        "worktreeCount": len(worktrees),
        "stashCount": len(stash_commits),
        "reflogCommitCount": len(set(reflog_commits)),
        "backupRefCount": len(actual_backup),
        "bundleSha256": sha256_file(bundle),
        "bundleBytes": bundle.stat().st_size,
        "fsckExitCode": fsck.returncode,
    }
    write_json(primary / "snapshot-summary.json", summary)
    package_count = package_manifest(primary)

    log("copying the sealed package to the mirror")
    shutil.copytree(primary, mirror, symlinks=True, copy_function=shutil.copy2)
    if verify_package(primary) != package_count or verify_package(mirror) != package_count:
        raise RuntimeError("Recovery package manifest verification failed")
    if (primary / "package-manifest.sha256").read_bytes() != (mirror / "package-manifest.sha256").read_bytes():
        raise RuntimeError("Primary and mirror manifests differ")
    mirror_bundle = mirror / bundle.name
    mirror_verify = git(repo, "bundle", "verify", mirror_bundle, check=False)
    if mirror_verify.returncode != 0 or sha256_file(mirror_bundle) != summary["bundleSha256"]:
        raise RuntimeError("Mirror bundle verification failed")
    if full_snapshot(repo, arguments.remote, refbase, dispositions) != frozen:
        raise RuntimeError("Full frozen state changed while copying/verifying the mirror")

    log("dual recovery packages are sealed and verified")
    print(json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding=UTF8)
    sys.stderr.reconfigure(encoding=UTF8)
    try:
        main()
    except Exception as error:
        print(f"FATAL: {error}", file=sys.stderr, flush=True)
        sys.exit(1)
