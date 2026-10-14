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

from recovery_fs import package_files, canonical_path, canonical_rel, current_entry, path_within, kind_at, manifest_for_roots, inventory_tree
from capture_recovery import assert_supported_worktree, validate_nested_entry
from git_layout import discover_worktrees

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


def manifest_digest(manifest: list[dict]) -> str:
    return hashlib.sha256(json.dumps(manifest, sort_keys=True, ensure_ascii=False).encode(UTF8)).hexdigest()


def validate_durable_destination(destination: Path, repo: Path, snapshot: Path, protected: dict, summary: dict) -> None:
    normalized = canonical_path(destination)
    surviving_root = canonical_path(summary["repo"])
    forbidden = [canonical_path(snapshot)]
    forbidden += [canonical_path(item["worktree"]) for item in protected.get("worktrees", [])
                  if canonical_path(item["worktree"]) not in (canonical_path(repo), surviving_root)]
    forbidden += [canonical_path(summary[key]) for key in ("primary", "mirror") if summary.get(key)]
    if any(normalized == path or normalized.startswith(path + os.sep) for path in forbidden):
        raise RuntimeError("destination is recovery package or removed worktree")
    if kind_at(destination)[0] != "directory":
        raise RuntimeError("destination is not a durable directory: " + str(destination))


def validate_retained_path(path: Path, entry: dict, repo: Path, snapshot: Path, protected: dict, summary: dict) -> None:
    # Check the payload itself as well as the base directory; selecting a
    # package name beneath its parent must not turn a backup into delivery.
    forbidden = [canonical_path(snapshot)]
    forbidden += [canonical_path(summary[key]) for key in ("primary", "mirror") if summary.get(key)]
    forbidden += [canonical_path(item["worktree"]) for item in protected.get("worktrees", [])
                  if canonical_path(item["worktree"]) not in (canonical_path(repo), canonical_path(summary["repo"]))]
    # A link is material in its own right. Its target is never read here.
    normalized = os.path.normcase(os.path.abspath(str(path))) if entry["kind"] in ("symlink", "junction") else canonical_path(path)
    if any(normalized == root or normalized.startswith(root + os.sep)
           or (entry["kind"] == "directory" and root.startswith(normalized + os.sep)) for root in forbidden):
        raise RuntimeError("retained-local payload overlaps a recovery package or removed worktree")


def stash_untracked_manifest(repo: Path, sha: str) -> list[dict]:
    """Derive frozen material bytes from the protected stash third-parent tree."""
    third = git(repo, "rev-parse", "--verify", sha + "^3", check=False)
    if third.returncode:
        return []
    manifest = []
    for raw in git(repo, "ls-tree", "-r", "-z", sha + "^3").stdout.split(b"\0"):
        if not raw:
            continue
        info, raw_path = raw.split(b"\t", 1)
        mode, kind, blob = info.split(b" ")
        if kind != b"blob" or mode not in (b"100644", b"100755", b"120000"):
            raise RuntimeError("Unsupported stash material entry: " + decode(raw_path))
        content = git(repo, "cat-file", "blob", decode(blob)).stdout
        link = mode == b"120000"
        manifest.append({"path": canonical_rel(decode(raw_path)), "kind": "symlink" if link else "file",
                         "size": len(content), "sha256": hashlib.sha256(content).hexdigest(),
                         "mode": 0o777 if link else (0o755 if mode == b"100755" else 0o644),
                         "linkTarget": decode(content) if link else None})
    return manifest


def committed_payload_matches(repo: Path, expected: str, item: dict) -> bool:
    relative = canonical_rel(item["path"])
    if item["kind"] == "directory":
        return True  # Git stores leaves; every frozen child is checked separately.
    listed = git(repo, "ls-tree", "-z", expected, "--", relative, check=False)
    entries = [entry for entry in listed.stdout.split(b"\0") if entry]
    if listed.returncode or len(entries) != 1:
        return False
    info, raw_path = entries[0].split(b"\t", 1)
    mode, kind, blob = info.split(b" ")
    if decode(raw_path) != relative or kind != b"blob":
        return False
    if item["kind"] == "symlink":
        if mode != b"120000":
            return False
    elif item["kind"] == "file":
        if mode not in (b"100644", b"100755"):
            return False
        if os.name != "nt" and bool(item["mode"] & 0o111) != (mode == b"100755"):
            return False
    else:
        return False
    content = git(repo, "cat-file", "blob", decode(blob)).stdout
    return (len(content) == item["size"] and hashlib.sha256(content).hexdigest() == item["sha256"]
            and (item["kind"] != "symlink" or decode(content) == item["linkTarget"]))


def retained_local_state(repo: Path, snapshot: Path, protected: dict, expected: str, records: list[dict]) -> dict:
    """Verify exact frozen local-material subsets; never exempt tracked work.

    source_sha binds the full category manifest while paths/payload select the
    retained subset. The reason describes the project use; it does not prove
    that arbitrary source code is disposable. Source and patch coverage remain
    independent mandatory checks.
    """
    summary = json.loads((snapshot / "snapshot-summary.json").read_text(encoding=UTF8))
    catalog = {}
    for state in sorted((snapshot / "worktrees").iterdir()):
        if not state.is_dir():
            continue
        metadata = json.loads((state / "metadata.json").read_text(encoding=UTF8))
        for category in ("untracked", "ignored-preserved"):
            source = "worktree:" + state.name + ":" + category
            manifest = json.loads((state / (category + "-manifest.json")).read_text(encoding=UTF8))
            catalog[source] = (manifest, metadata)
    for sha in protected.get("stashCommits", []):
        catalog["stash:" + sha + ":untracked"] = (stash_untracked_manifest(repo, sha), {"stash": sha})
    checks, covered, root_paths = [], {}, set()
    retained_directories = []
    for number, item in enumerate(records):
        if not isinstance(item, dict):
            raise RuntimeError("Integration records must contain JSON objects")
        if item.get("classification") != "retained-local":
            continue
        source = item.get("source_ref")
        detail = {"source_ref": source}
        try:
            if summary.get("schemaVersion") != 4:
                raise RuntimeError("retained-local cannot relax a schema-2 or schema-3 package")
            if source not in catalog:
                raise RuntimeError("retained-local only accepts frozen untracked or ignored-preserved payloads")
            manifest, metadata = catalog[source]
            digest = manifest_digest(manifest)
            if item.get("source_sha") != digest or item.get("resulting_sha") != expected:
                raise RuntimeError("retained-local source or final commit binding differs")
            if item.get("action") != "retain" or not str(item.get("reason", "")).strip():
                raise RuntimeError("retained-local requires action retain and a local-material reason")
            paths, payload = item.get("paths"), item.get("payload")
            if (not isinstance(paths, list) or not paths or not all(isinstance(path, str) for path in paths)
                    or len(set(paths)) != len(paths) or not isinstance(payload, list)):
                raise RuntimeError("retained-local requires unique exact paths and payload")
            paths = [canonical_rel(path) for path in paths]
            if len(set(path.casefold() if os.name == "nt" else path for path in paths)) != len(paths):
                raise RuntimeError("retained-local paths alias the same filesystem entry")
            frozen = {entry["path"]: entry for entry in manifest}
            if any(path not in frozen for path in paths):
                raise RuntimeError("retained-local path is absent from frozen manifest")
            subset = [entry for entry in manifest if entry["path"] in paths]
            if payload != subset:
                raise RuntimeError("retained-local payload differs from frozen manifest subset")
            # Selecting a directory also selects every frozen child; callers
            # cannot register a broad folder while dropping one source file.
            if any(entry["kind"] == "directory" and any(
                    other["path"].startswith(entry["path"] + "/") and other["path"] not in paths
                    for other in manifest) for entry in subset):
                raise RuntimeError("retained-local directory omits frozen descendants")
            raw_destination = item.get("destination")
            if not isinstance(raw_destination, str) or not Path(raw_destination).is_absolute():
                raise RuntimeError("retained-local destination must be an absolute directory")
            # Inspect the submitted destination before resolving it; otherwise
            # a directory link would disguise a removed worktree or package.
            destination = Path(raw_destination).absolute()
            validate_durable_destination(destination, repo, snapshot, protected, summary)
            if metadata.get("root") and canonical_path(destination) != canonical_path(summary["repo"]):
                raise RuntimeError("root local materials must stay at the surviving root")
            for entry in subset:
                retained_path = path_within(destination, entry["path"])
                validate_retained_path(retained_path, entry, repo, snapshot, protected, summary)
                actual = current_entry(retained_path, entry["path"])
                if actual is None or any(actual.get(key) != entry.get(key) for key in ("kind", "size", "sha256", "linkTarget")):
                    raise RuntimeError("retained-local payload drift: " + entry["path"])
                if ((not metadata.get("stash") and actual["mode"] != entry["mode"])
                        or (metadata.get("stash") and os.name != "nt" and entry["kind"] == "file"
                            and bool(actual["mode"] & 0o111) != bool(entry["mode"] & 0o111))):
                    raise RuntimeError("retained-local payload mode drift: " + entry["path"])
                if canonical_path(destination) in (canonical_path(repo), canonical_path(summary["repo"])):
                    tracked = git(destination, "ls-files", "--error-unmatch", "--", entry["path"], check=False)
                    if entry["kind"] != "directory" and tracked.returncode == 0:
                        raise RuntimeError("retained-local cannot exempt a tracked path: " + entry["path"])
                if entry["kind"] == "directory":
                    retained_directories.append((number, destination, entry["path"]))
            previous = covered.setdefault(source, set())
            if previous.intersection(paths):
                raise RuntimeError("duplicate retained-local payload registration")
            previous.update(paths)
            if canonical_path(destination) == canonical_path(repo):
                root_paths.update(paths)
            detail.update(source_sha=digest, resulting_sha=expected, destination=str(destination), paths=paths)
            checks.append({"name": "integrated:retained-local:" + str(number), "ok": True, "detail": detail})
        except (OSError, RuntimeError) as error:
            detail["reason"] = str(error)
            checks.append({"name": "integrated:retained-local:" + str(number), "ok": False, "detail": detail})
    # Different frozen worktrees/stashes may contribute registered materials
    # to the same normal directory. Compare its exact final file set against
    # the union of records whose bindings and contents actually passed.
    valid_paths = {}
    by_name = {check["name"]: check for check in checks}
    for check in checks:
        if check["ok"]:
            detail = check["detail"]
            paths = valid_paths.setdefault(canonical_path(detail["destination"]), set())
            for path in detail["paths"]:
                parts = path.split("/")
                paths.update("/".join(parts[:end]) for end in range(1, len(parts) + 1))
    for number, destination, relative in retained_directories:
        check = by_name["integrated:retained-local:" + str(number)]
        if not check["ok"]:
            continue
        expected_children = {path for path in valid_paths[canonical_path(destination)]
                             if path == relative or path.startswith(relative + "/")}
        actual_children = {entry["path"] for entry in inventory_tree(path_within(destination, relative), relative)}
        if actual_children != expected_children:
            check["ok"] = False
            check["detail"]["reason"] = "retained-local directory file set drift: " + relative
    return {"checks": checks, "covered": covered, "rootPaths": root_paths}


def working_tree_policy(repo: Path, snapshot: Path, protected: dict, expected: str, records_path, status: bytes) -> dict:
    records = json.loads(Path(records_path).read_text(encoding=UTF8)) if records_path else []
    if not isinstance(records, list):
        raise RuntimeError("Integration records must be a JSON array")
    retention = retained_local_state(repo, snapshot, protected, expected, records)
    summary = json.loads((snapshot / "snapshot-summary.json").read_text(encoding=UTF8))
    excluded = []
    reproducible = []
    if summary.get("schemaVersion") == 4:
        # Exempt only frozen cache roots and independently captured child repos.
        # Precise material records never exempt subsequent files in a folder.
        for state in sorted((snapshot / "worktrees").iterdir()):
            metadata = json.loads((state / "metadata.json").read_text(encoding=UTF8))
            if canonical_path(metadata["worktree"]) == canonical_path(repo) or metadata.get("root"):
                if canonical_path(metadata["worktree"]) == canonical_path(repo):
                    excluded += metadata.get("nestedPaths", [])
                    disposition = json.loads((state / "ignored-disposition.json").read_text(encoding=UTF8))
                    reproducible += disposition.get("reproducible", [])

    def under(path, roots):
        path = path.casefold() if os.name == "nt" else path
        return any(path == (root.casefold() if os.name == "nt" else root)
                   or path.startswith((root.casefold() if os.name == "nt" else root) + "/") for root in roots)

    unclassified = []
    fields = status.split(b"\0")
    position = 0
    while position < len(fields):
        entry = fields[position]
        position += 1
        if not entry:
            continue
        path = canonical_rel(decode(entry[3:]))
        code = entry[:2]
        if b"R" in code or b"C" in code:
            position += 1  # porcelain -z writes the original name next
        if code != b"??" or (path not in retention["rootPaths"] and not under(path, excluded)):
            unclassified.append(decode(entry))
    ignored_unclassified = []
    if summary.get("schemaVersion") == 4:
        live_ignored = git(repo, "status", "--porcelain=v1", "--untracked-files=normal", "--ignored=matching", "-z").stdout
        roots = [canonical_rel(decode(entry[3:])) for entry in live_ignored.split(b"\0") if entry.startswith(b"!! ")]
        tracked = {canonical_rel(decode(path)) for path in git(repo, "ls-files", "-z").stdout.split(b"\0") if path}
        known = retention["rootPaths"] | tracked
        exempt = excluded + reproducible
        for root in roots:
            if under(root, exempt):
                continue
            # Unknown roots fail without scanning their interiors (which can
            # include very large caches or unregistered nested repositories).
            if root not in known and not any(path.startswith(root + "/") for path in known | set(exempt)):
                ignored_unclassified.append(root)
                continue
            for item in manifest_for_roots(repo, [root], exclude_roots=exempt):
                path = item["path"]
                if path in known or under(path, retention["rootPaths"]):
                    continue
                if item["kind"] == "directory" and any(other.startswith(path + "/") for other in known | set(exempt)):
                    continue
                ignored_unclassified.append(path)
    cached = git(repo, "diff", "--cached", "--quiet", "--no-ext-diff", "--no-textconv", check=False)
    return {"ok": not unclassified and not ignored_unclassified and cached.returncode == 0 and all(check["ok"] for check in retention["checks"]),
            "unclassified": unclassified, "indexClean": cached.returncode == 0,
            "unclassifiedIgnored": sorted(set(ignored_unclassified)),
            "retainedPaths": sorted(retention["rootPaths"])}


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

    summary = json.loads((snapshot / "snapshot-summary.json").read_text(encoding=UTF8))
    retention = retained_local_state(repo, snapshot, protected, expected, records)
    checks.extend(retention["checks"])
    nested_path = snapshot / "snapshot/nested-recovery.json"
    if summary.get("schemaVersion") == 4 and nested_path.exists():
        nested = json.loads(nested_path.read_text(encoding=UTF8))
        if nested.get("schemaVersion") != 1 or not isinstance(nested.get("entries"), list):
            raise RuntimeError("Invalid frozen nested recovery registry")
        for index, frozen_entry in enumerate(nested["entries"]):
            try:
                entry = dict(frozen_entry)
                entry["packagePath"] = str(path_within(snapshot, entry["package"]))
                entry["verificationPath"] = str(path_within(snapshot, entry["verification"]))
                state = validate_nested_entry(entry)
                record("integrated:nested:" + str(index), True,
                       {"path": str(path_within(entry["parentWorktree"], entry["relativePath"])),
                        "manifestSha256": state["manifestSha256"], "frozenStateSha256": state["frozenStateSha256"]})
            except (OSError, RuntimeError, KeyError, ValueError) as error:
                record("integrated:nested:" + str(index), False, str(error))

    def payload_covered(source, manifest, durable=False):
        if not manifest:
            return
        digest = manifest_digest(manifest)
        remaining = [item for item in manifest if item["path"] not in retention["covered"].get(source, set())]
        if not remaining:
            record("integrated:" + source, True, {"source": digest, "method": "retained-local"})
            return
        destinations = [repo]
        if durable and summary.get("schemaVersion") in (2, 3):
            # Older packages retain their original durable-payload semantics.
            # Adding a new retained-local record never changes old validation.
            destinations += [Path(item["destination"]) for item in records
                             if item.get("source_ref") == source and item.get("source_sha") == digest
                             and item.get("destination") and item.get("resulting_sha") == expected]
        failures = []
        require_committed = not durable or summary.get("schemaVersion") == 4
        for destination in destinations:
            destination = destination.resolve()
            try:
                validate_durable_destination(destination, repo, snapshot, protected, summary)
                for item in remaining:
                    actual = current_entry(path_within(destination, item["path"]), item["path"])
                    if actual is None or any(actual.get(key) != item.get(key) for key in ("kind", "size", "sha256", "linkTarget", "mode")):
                        raise RuntimeError("payload differs: " + item["path"])
                    if require_committed and (destination != repo or not committed_payload_matches(repo, expected, item)):
                        raise RuntimeError("payload is not committed with frozen bytes and kind: " + item["path"])
                record("integrated:" + source, True, {"source": digest, "method": "payload-content", "destination": str(destination)})
                return
            except (OSError, RuntimeError) as error:
                failures.append(str(error))
        detail = comparison(source, digest) if require_committed else None
        if detail is not None:
            # A content comparison may explain normalization or deliberate
            # source edits, but cannot turn an uncommitted file into coverage.
            leaves = [item for item in remaining if item["kind"] != "directory"]
            if (summary.get("schemaVersion") == 4 and
                    (not leaves or any(git(repo, "cat-file", "-e", expected + ":" + item["path"], check=False).returncode
                                       for item in leaves))):
                detail = None
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
                    retained_source = "stash:" + sha + ":untracked"
                    retained = decode(path) in retention["covered"].get(retained_source, set())
                    detail = ({"method": "stash-untracked-blob", "source": decode(blob)} if ok else
                              ({"method": "retained-local", "source": decode(blob)} if retained else comparison(source, decode(blob))))
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
    if summary.get("schemaVersion") not in (2, 3, 4):
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

    # A candidate can be a linked checkout of a separate-git-dir repository
    # whose main path is not inferable from this checkout. Integration-only
    # does not require the final topology; keep its read-only raw enumeration.
    worktrees = (parse_worktrees(git(repo, "worktree", "list", "--porcelain", "-z").stdout)
                 if arguments.check_integration_only else discover_worktrees(repo))
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
    policy = working_tree_policy(repo, snapshot, protected, expected, arguments.integration_records, status)
    record("working-tree-clean", policy["ok"], policy)
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
