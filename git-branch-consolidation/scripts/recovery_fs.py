"""Portable, no-follow filesystem operations for recovery packages.

External link permission is scoped to (original worktree, relative path, kind,
literal target). It never permits writing below a link or following it while
capturing a payload. Ordinary schema-2 packages need no link allowlist.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import tarfile
from pathlib import Path

UTF8 = "utf-8"
LINK_KINDS = {"symlink", "junction"}
PAX_KIND = "branch_consolidation.link_kind"
PAX_DIRECTORY = "branch_consolidation.link_directory"


def plain_path(path) -> str:
    value = str(path)
    if value.startswith("\\\\?\\UNC\\"):
        return "\\\\" + value[8:]
    if value.startswith("\\\\?\\"):
        return value[4:]
    return value


def io_path(path) -> Path:
    value = os.path.abspath(str(path))
    if os.name == "nt" and not value.startswith("\\\\?\\"):
        value = "\\\\?\\UNC\\" + value[2:] if value.startswith("\\\\") else "\\\\?\\" + value
    return Path(value)


def canonical_path(path) -> str:
    return os.path.normcase(plain_path(os.path.realpath(io_path(path))))


def canonical_rel(value) -> str:
    value = str(value).replace("\\", "/").rstrip("/")
    parts = value.split("/")
    if (not value or value.startswith("/") or ":" in value or "\0" in value
            or any(p in ("", ".", "..") for p in parts)):
        raise RuntimeError(f"Unsafe relative path: {value!r}")
    if os.name == "nt" and any(
        p.endswith((".", " ")) or re.fullmatch(r"(?i)(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?", p)
        for p in parts
    ):
        raise RuntimeError(f"Unsafe Windows path: {value!r}")
    return value


def kind_at(path) -> tuple[str | None, os.stat_result | None]:
    try:
        info = io_path(path).lstat()
    except FileNotFoundError:
        return None, None
    if getattr(info, "st_file_attributes", 0) & 0x400:
        tag = getattr(info, "st_reparse_tag", None)
        if tag == 0xA0000003:
            return "junction", info
        if tag == 0xA000000C:
            return "symlink", info
        raise RuntimeError(f"Unknown reparse point: {path} (tag={tag})")
    if stat.S_ISLNK(info.st_mode):
        return "symlink", info
    if stat.S_ISDIR(info.st_mode):
        return "directory", info
    if stat.S_ISREG(info.st_mode):
        return "file", info
    raise RuntimeError(f"Unsupported filesystem entry: {path}")


def path_within(root, relative: str) -> Path:
    """Check lexical containment and every parent, but allow a leaf link."""
    relative = canonical_rel(relative)
    root = io_path(root)
    parts = relative.split("/")
    current = root
    for component in [None] + parts[:-1]:
        if component is not None:
            current /= component
        kind, _ = kind_at(current)
        if kind not in (None, "directory"):
            raise RuntimeError(f"Path descends through a link or non-directory: {current}")
    return root.joinpath(*parts)


def sha256_file(path) -> str:
    kind, _ = kind_at(path)
    if kind != "file":
        raise RuntimeError(f"Refusing to hash a non-regular file: {path}")
    digest = hashlib.sha256()
    with io_path(path).open("rb") as handle:
        while block := handle.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def current_entry(path, logical: str) -> dict | None:
    path = io_path(path)
    kind, info = kind_at(path)
    if kind is None:
        return None
    target = digest = None
    size = 0
    if kind in LINK_KINDS:
        target = os.readlink(path)
        encoded = target.encode(UTF8, "surrogateescape")
        size, digest = len(encoded), hashlib.sha256(encoded).hexdigest()
    elif kind == "file":
        size, digest = info.st_size, sha256_file(path)
    return {"path": canonical_rel(logical), "kind": kind, "size": size,
            "sha256": digest, "mode": stat.S_IMODE(info.st_mode), "linkTarget": target}


def inventory_tree(root, logical_prefix: str) -> list[dict]:
    root = io_path(root)
    found = []
    pending = [(root, canonical_rel(logical_prefix))]
    while pending:
        path, logical = pending.pop()
        item = current_entry(path, logical)
        if item is None:
            if path == root:
                return []
            raise RuntimeError(f"Payload path disappeared: {path}")
        found.append(item)
        if item["kind"] == "directory":
            # Never use rglob/os.walk: a junction must remain an independent leaf.
            with os.scandir(path) as children:
                pending.extend((path / child.name, logical + "/" + child.name) for child in children)
    return found[:1] + sorted(found[1:], key=lambda item: item["path"].casefold())


def manifest_for_roots(worktree, roots: list[str]) -> list[dict]:
    entries = []
    for relative in roots:
        source = path_within(worktree, relative)
        inventory = inventory_tree(source, relative)
        if not inventory:
            raise RuntimeError(f"Payload root is missing: {source}")
        entries.extend(inventory)
    return entries


def package_files(root) -> dict[str, Path]:
    result = {}
    root = io_path(root)
    if kind_at(root)[0] != "directory":
        raise RuntimeError(f"Package root is not a regular directory: {root}")
    with os.scandir(root) as children:
        names = [item.name for item in children]
    for name in names:
        for item in inventory_tree(root / name, name):
            if item["kind"] in LINK_KINDS:
                raise RuntimeError(f"Recovery package contains a filesystem link: {item['path']}")
            if item["kind"] == "file" and item["path"] != "package-manifest.sha256":
                result[item["path"]] = root.joinpath(*item["path"].split("/"))
    return result


def walk_paths(root):
    """Yield entry paths without descending into any reparse point or symlink."""
    pending = [io_path(root)]
    while pending:
        path = pending.pop()
        kind, _ = kind_at(path)
        if kind is None:
            raise RuntimeError(f"Entry disappeared during traversal: {path}")
        yield path
        if kind == "directory":
            with os.scandir(path) as children:
                pending.extend(path / item.name for item in children)


def create_payload_tar(source_root, relative_paths: list[str], archive_path) -> None:
    archive_path = io_path(archive_path)
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    manifest = manifest_for_roots(source_root, relative_paths)
    seen = set()
    with tarfile.open(archive_path, "w", format=tarfile.PAX_FORMAT, dereference=False) as archive:
        for item in manifest:
            name = item["path"]
            if name in seen:
                raise RuntimeError(f"Overlapping payload roots: {name}")
            seen.add(name)
            source = path_within(source_root, name)
            if current_entry(source, name) != item:
                raise RuntimeError(f"Payload changed before packing: {name}")
            member = tarfile.TarInfo(name)
            member.mode = item["mode"]
            if item["kind"] in LINK_KINDS:
                member.type, member.linkname = tarfile.SYMTYPE, item["linkTarget"]
                member.pax_headers[PAX_KIND] = item["kind"]
                info = source.lstat()
                member.pax_headers[PAX_DIRECTORY] = str(int(bool(getattr(info, "st_file_attributes", 0) & 0x10)))
                archive.addfile(member)
            elif item["kind"] == "directory":
                member.type = tarfile.DIRTYPE
                archive.addfile(member)
            else:
                member.size = item["size"]
                with source.open("rb") as handle:
                    archive.addfile(member, handle)
            if current_entry(source, name) != item:
                raise RuntimeError(f"Payload changed while packing: {name}")


def load_external_link_allowlist(path) -> set[tuple[str, str, str, str]]:
    if path is None:
        return set()
    data = json.loads(io_path(path).read_text(encoding=UTF8))
    if not isinstance(data, dict) or set(data) != {"schemaVersion", "links"} or data["schemaVersion"] != 1 or not isinstance(data["links"], list):
        raise RuntimeError("External link allowlist requires schemaVersion 1 and a links array")
    allowed = set()
    identities = set()
    for item in data["links"]:
        if not isinstance(item, dict) or set(item) != {"worktree", "path", "kind", "target"} or not all(isinstance(v, str) and v for v in item.values()):
            raise RuntimeError("Each link allowance needs exact worktree, path, kind and target strings")
        if not os.path.isabs(item["worktree"]) or item["kind"] not in LINK_KINDS or "\0" in item["target"]:
            raise RuntimeError("Invalid external link allowance")
        key = (canonical_path(item["worktree"]), canonical_rel(item["path"]), item["kind"], item["target"])
        identity = (key[0], os.path.normcase(key[1]))
        if identity in identities:
            raise RuntimeError("Duplicate external link allowance")
        identities.add(identity)
        allowed.add(key)
    return allowed


def validate_link(root, name, kind, target, allowed=(), source_worktree=None) -> None:
    if not target or "\0" in target:
        raise RuntimeError(f"Invalid link target: {name}")
    root = io_path(root)
    link = path_within(root, name)
    resolved = canonical_path(link.parent / target)
    try:
        internal = os.path.commonpath([resolved, canonical_path(root)]) == canonical_path(root)
    except ValueError:
        internal = False
    if not internal:
        key = (canonical_path(source_worktree), canonical_rel(name), kind, target) if source_worktree else None
        if key not in allowed:
            raise RuntimeError(f"External link requires an exact allowlist entry: {name} -> {target}")


def validate_link_plan(root, planned=(), *, allowed=(), source_worktree=None) -> None:
    """Resolve the whole link graph, including links from earlier payloads.

    Resolution inspects link metadata only. Each alias that ultimately escapes
    needs its own exact permission; permission for its target is not inherited.
    Planned entries are (relative path, kind, literal target or None).
    """
    root = io_path(root)
    root_key = os.path.normcase(os.path.abspath(plain_path(root)))
    links = {}
    if kind_at(root)[0] is not None:
        for path in walk_paths(root):
            kind, _ = kind_at(path)
            if kind in LINK_KINDS:
                name = path.relative_to(root).as_posix()
                links[os.path.normcase(name)] = (name, kind, os.readlink(path))
    for name, kind, target in planned:
        name = canonical_rel(name)
        key = os.path.normcase(name)
        if kind in LINK_KINDS:
            links[key] = (name, kind, target)
        else:
            links.pop(key, None)
    absolute_links = {
        os.path.normcase(os.path.abspath(os.path.join(root_key, name.replace("/", os.sep)))): record
        for record in links.values() for name in [record[0]]
    }

    def resolve(name, target):
        if not target or "\0" in target:
            raise RuntimeError(f"Invalid link target: {name}")
        origin = os.path.join(root_key, name.replace("/", os.sep))
        value = os.path.join(os.path.dirname(origin), plain_path(target).replace("/", os.sep))
        drive, tail = os.path.splitdrive(value)
        if not tail.startswith(os.sep):
            raise RuntimeError(f"Drive-relative link target is unsupported: {name}")
        pending = tail.split(os.sep)
        components = []
        visited = {os.path.normcase(origin)}
        while pending:
            component = pending.pop(0)
            if component in ("", "."):
                continue
            if component == "..":
                if components:
                    components.pop()
                continue
            components.append(component)
            current = drive + os.sep + os.sep.join(components)
            key = os.path.normcase(current)
            if key not in absolute_links:
                continue
            if key in visited:
                raise RuntimeError(f"Cyclic link graph: {name}")
            visited.add(key)
            next_target = plain_path(absolute_links[key][2]).replace("/", os.sep)
            # Expand a symlink before processing a following '..' component.
            value = os.path.join(os.path.dirname(current), next_target)
            drive, tail = os.path.splitdrive(value)
            if not tail.startswith(os.sep):
                raise RuntimeError(f"Drive-relative link target is unsupported: {name}")
            pending = tail.split(os.sep) + pending
            components = []
        return canonical_path(drive + os.sep + os.sep.join(components))

    for name, kind, target in links.values():
        resolved = resolve(name, target)
        try:
            internal = os.path.commonpath([resolved, canonical_path(root)]) == canonical_path(root)
        except ValueError:
            internal = False
        if not internal:
            key = (canonical_path(source_worktree), name, kind, target) if source_worktree else None
            if key not in allowed:
                raise RuntimeError(f"External link requires an exact allowlist entry: {name} -> {target}")


def member_kind(member) -> str:
    marker = member.pax_headers.get(PAX_KIND)
    legacy = member.pax_headers.get("task.windows_junction")
    if legacy is not None:
        if legacy != "1" or marker not in (None, "junction"):
            raise RuntimeError(f"Unknown legacy reparse marker: {member.name}")
        marker = "junction"
    if marker is not None and (marker not in LINK_KINDS or not member.issym()):
        raise RuntimeError(f"Unknown link/reparse kind in archive: {member.name}")
    if member.issym():
        return marker or "symlink"
    if member.islnk():
        return "hardlink"
    if member.isdir():
        return "directory"
    if member.isfile():
        return "file"
    raise RuntimeError(f"Unsupported tar member type: {member.name}")


def safe_extract_tar(tar_path, destination, *, allowed=(), source_worktree=None) -> None:
    destination = io_path(destination)
    with tarfile.open(io_path(tar_path), "r") as archive:
        planned = []
        kinds = {}
        for member in archive.getmembers():
            name = canonical_rel(member.name)
            key = os.path.normcase(name)
            kind = member_kind(member)
            if key in kinds:
                raise RuntimeError(f"Duplicate tar member: {name}")
            kinds[key] = kind
            path = path_within(destination, name)
            if kind in LINK_KINDS:
                validate_link(destination, name, kind, member.linkname, allowed, source_worktree)
                if kind == "junction" and (os.name != "nt" or not os.path.isabs(plain_path(member.linkname))):
                    raise RuntimeError(f"Cannot restore junction on this platform/target: {name}")
            elif kind == "hardlink":
                canonical_rel(member.linkname)
                path_within(destination, member.linkname)
            existing, _ = kind_at(path)
            if kind == "directory" and existing not in (None, "directory"):
                raise RuntimeError(f"Directory destination is a link or file: {name}")
            planned.append((member, name, kind))
        for member, name, kind in planned:
            parts = name.split("/")
            for end in range(1, len(parts)):
                if kinds.get(os.path.normcase("/".join(parts[:end])), "directory") != "directory":
                    raise RuntimeError(f"Tar member descends through a link or file: {name}")
            if kind == "hardlink" and kinds.get(os.path.normcase(member.linkname)) != "file":
                raise RuntimeError(f"Hard link target must be a regular member in the same archive: {name}")
        validate_link_plan(destination, [(name, kind, member.linkname if kind in LINK_KINDS else None)
                           for member, name, kind in planned], allowed=allowed, source_worktree=source_worktree)
        # Regular members first; links are never parents for any extracted member.
        ordered = sorted(planned, key=lambda item: (item[2] in LINK_KINDS or item[2] == "hardlink", item[1].count("/")))
        directories = []
        for member, name, kind in ordered:
            path = path_within(destination, name)
            path.parent.mkdir(parents=True, exist_ok=True)
            existing, _ = kind_at(path)
            if kind == "directory":
                if existing not in (None, "directory"):
                    raise RuntimeError(f"Directory destination changed: {name}")
                path.mkdir(exist_ok=True)
                directories.append((path, member.mode))
                continue
            if existing == "directory":
                raise RuntimeError(f"Refusing to replace a directory with a payload leaf: {name}")
            if existing == "junction":
                os.rmdir(path)
            elif existing is not None:
                path.unlink()
            if kind == "file":
                with archive.extractfile(member) as source, path.open("xb") as target:
                    while block := source.read(1024 * 1024):
                        target.write(block)
                path.chmod(member.mode & 0o777)
            elif kind == "hardlink":
                source = path_within(destination, member.linkname)
                if kind_at(source)[0] != "file":
                    raise RuntimeError(f"Hard link target changed: {name}")
                os.link(source, path)
            else:
                validate_link(destination, name, kind, member.linkname, allowed, source_worktree)
                if kind == "junction":
                    import _winapi
                    _winapi.CreateJunction(plain_path(member.linkname), str(path))
                else:
                    os.symlink(member.linkname, path, target_is_directory=member.pax_headers.get(PAX_DIRECTORY) == "1")
                if kind_at(path)[0] != kind or os.readlink(path) != member.linkname:
                    raise RuntimeError(f"Restored link differs from recorded kind/target: {name}")
        for path, mode in reversed(directories):
            path.chmod(mode & 0o777)
