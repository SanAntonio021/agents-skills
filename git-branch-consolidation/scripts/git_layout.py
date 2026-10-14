"""Seal Git configuration/layout and replay its inert settings from a package.

Raw files are evidence, never installed as executable recovery configuration.
The effective configuration is flattened into per-worktree config, with paths
remapped and action-producing settings disabled. No original file is read by a
restore operation.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path

from recovery_fs import (
    canonical_path, canonical_rel, current_entry, inventory_tree, io_path,
    kind_at, package_files, path_within, plain_path, sha256_file,
)

UTF8 = "utf-8"
LAYOUT_SCHEMA = 1
# These affect byte conversion or index/status interpretation. Action-producing
# settings (filters, fsmonitor, hooks, textconv, credential helpers, etc.) are
# deliberately absent; their original bytes remain sealed in the package.
REPLAY_KEYS = {
    "core.autocrlf", "core.eol", "core.safecrlf", "core.filemode",
    "core.ignorecase", "core.symlinks", "core.longpaths", "core.quotepath",
    "core.checkstat", "core.trustctime", "core.ignorestat", "core.preloadindex",
    "core.fscache", "core.protecthfs", "core.protectntfs", "core.logallrefupdates",
    "core.abbrev", "core.warnambiguousrefs", "core.commentchar",
    "core.checkroundtripencoding", "core.bigfilethreshold",
    "user.name", "user.email", "status.showuntrackedfiles",
}


def recovery_environment() -> dict[str, str]:
    """Do not inherit config, object directories or attribute injection.

Use this environment for *every* Git invocation during schema-4 recovery,
including init/clone and commands issued before a worktree exists.
"""
    result = {key: value for key, value in os.environ.items()
              if not key.upper().startswith("GIT_")}
    result.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_SYSTEM=os.devnull,
                  GIT_CONFIG_GLOBAL=os.devnull, GIT_ATTR_NOSYSTEM="1",
                  GIT_TERMINAL_PROMPT="0", GIT_OPTIONAL_LOCKS="0")
    return result


def run(repo, *args, check=True, recovery=False, worktree_override=None):
    overrides = ["--work-tree=" + plain_path(worktree_override)] if worktree_override is not None else []
    process = subprocess.run(
        ["git", "--no-optional-locks", "-c", "core.longpaths=true", *overrides, "-C",
         plain_path(repo), *map(str, args)], stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, env=recovery_environment() if recovery else None,
    )
    if check and process.returncode:
        raise RuntimeError("Git layout command failed: " +
                           process.stderr.decode(UTF8, "replace"))
    return process


def text(repo, *args, check=True, recovery=False, worktree_override=None):
    return run(repo, *args, check=check, recovery=recovery, worktree_override=worktree_override).stdout.decode(
        UTF8, "surrogateescape").strip()


def _worktree_records(raw):
    if not isinstance(raw, bytes):
        return [dict(item) for item in raw]
    records = []
    for block in raw.rstrip(b"\0").split(b"\0\0"):
        entry = {}
        for field in block.split(b"\0"):
            key, _, value = field.decode(UTF8, "surrogateescape").partition(" ")
            if key:
                entry[key] = value or True
        if "worktree" in entry:
            records.append(entry)
    return records


def discover_worktrees(repo, raw_records=None):
    """Resolve checkout identities without treating a separate git-dir as one."""
    caller = Path(text(repo, "rev-parse", "--show-toplevel")).resolve()
    caller_admin = text(caller, "rev-parse", "--absolute-git-dir")
    caller_common = text(caller, "rev-parse", "--path-format=absolute", "--git-common-dir")
    records = _worktree_records(raw_records if raw_records is not None else
                                run(caller, "worktree", "list", "--porcelain", "-z").stdout)
    result = []
    seen = set()
    for index, entry in enumerate(records):
        if entry.get("bare"):
            raise RuntimeError("A bare worktree has no recoverable checkout")
        candidate = Path(entry["worktree"])
        # Git reports the metadata directory for a separate-git-dir main tree.
        # Its checkout cannot be inferred when invoked from a linked tree and
        # core.worktree is absent: require the caller to be the main checkout.
        if index == 0 and canonical_path(candidate) == canonical_path(caller_common):
            if canonical_path(caller_admin) == canonical_path(caller_common):
                candidate = caller
            else:
                configured = text(caller, "config", "--local", "--path", "--get",
                                  "core.worktree", check=False)
                if not configured:
                    raise RuntimeError("Invoke capture from the separate-git-dir main checkout")
                candidate = Path(configured)
                if not candidate.is_absolute():
                    candidate = Path(caller_common) / candidate
        if kind_at(candidate)[0] != "directory":
            raise RuntimeError("Registered worktree is missing or linked: " + str(candidate))
        top = Path(text(candidate, "rev-parse", "--show-toplevel")).resolve()
        if canonical_path(top) != canonical_path(candidate):
            raise RuntimeError("Registered path is not a checkout root: " + str(candidate))
        admin_path = Path(text(top, "rev-parse", "--absolute-git-dir"))
        common_path = Path(text(top, "rev-parse", "--path-format=absolute", "--git-common-dir"))
        for metadata in (admin_path, common_path):
            _regular_ancestors(metadata)
            if kind_at(metadata)[0] != "directory":
                raise RuntimeError("Git metadata directory is linked or missing: " + str(metadata))
        admin, common = admin_path.resolve(), common_path.resolve()
        if canonical_path(common) != canonical_path(caller_common):
            raise RuntimeError("Registered checkout belongs to another common Git directory")
        if canonical_path(top) in seen:
            raise RuntimeError("Duplicate registered checkout: " + str(top))
        seen.add(canonical_path(top))
        pointer = current_entry(top / ".git", ".git")
        if pointer is None or pointer["kind"] not in ("directory", "file"):
            raise RuntimeError("Git entry is missing or is a link: " + str(top / ".git"))
        if pointer["kind"] == "file":
            raw = (top / ".git").read_bytes().decode(UTF8, "surrogateescape").strip()
            if not raw.startswith("gitdir: ") or "\n" in raw or "\r" in raw:
                raise RuntimeError("Invalid Git pointer file")
            target = Path(raw[len("gitdir: "):])
            if not target.is_absolute():
                target = top / target
            _regular_ancestors(target)
            if kind_at(target)[0] != "directory":
                raise RuntimeError("Git pointer targets a link or missing directory")
        role = "main" if canonical_path(admin) == canonical_path(common) else "linked"
        result.append(dict(
            entry, worktree=str(top), listed_worktree=str(entry.get("listed_worktree", entry["worktree"])),
            git_dir=str(admin), common_dir=str(common), admin_dir=str(admin),
            role=role, index=index, git_pointer_kind=pointer["kind"],
            git_pointer_sha256=pointer["sha256"],
            layout_kind="linked" if role == "linked" else
                        "separate" if pointer["kind"] == "file" else "ordinary",
        ))
    if not result:
        raise RuntimeError("No registered checkout found")
    return result


def _configuration(repo, *, includes=True):
    fields = run(repo, "config", "--includes" if includes else "--no-includes", "--show-origin", "--show-scope",
                 "--null", "--list").stdout.rstrip(b"\0").split(b"\0")
    if fields == [b""]:
        return []
    if len(fields) % 3:
        raise RuntimeError("Malformed Git configuration origin output")
    result = []
    for offset in range(0, len(fields), 3):
        scope, origin, field = (value.decode(UTF8, "surrogateescape")
                                for value in fields[offset:offset + 3])
        key, separator, value = field.partition("\n")
        result.append(dict(scope=scope, origin=origin, key=key,
                           value=value if separator else None))
    return result


def _resolved_config_path(repo, key):
    value = text(repo, "config", "--path", "--get", key, check=False)
    if not value:
        return None
    path = Path(value).expanduser()
    return path if path.is_absolute() else Path(repo) / path


def _regular_ancestors(path):
    """Do not follow a linked directory while sealing metadata dependencies."""
    candidate = io_path(path)
    for parent in candidate.parents:
        if kind_at(parent)[0] not in (None, "directory"):
            raise RuntimeError("Configuration path descends through a link: " + plain_path(path))


def _include_target(root, value):
    key = value["key"].lower()
    if not (key == "include.path" or key.startswith("includeif.") and key.endswith(".path")):
        return None
    if not value["value"]:
        return None
    target = Path(value["value"]).expanduser()
    if not target.is_absolute():
        if not value["origin"].startswith("file:"):
            raise RuntimeError("Relative include lacks a sealed file origin")
        origin = Path(value["origin"][5:]).expanduser()
        if not origin.is_absolute():
            origin = Path(root) / origin
        target = origin.parent / target
    return target


def _preflight_includes(root, values, include):
    """Ask Git to parse each already checked file without following includes."""
    queue, checked, labels = list(values), set(), []
    while queue:
        target = _include_target(root, queue.pop())
        if target is None:
            continue
        label = "dependencies/" + hashlib.sha256(
            os.path.normcase(os.path.abspath(target)).encode(UTF8, "surrogateescape")).hexdigest() + ".config"
        sealed = include(target, label)
        if sealed is None or sealed in checked:
            continue
        checked.add(sealed)
        labels.append(sealed)
        output = run(root, "config", "--file", plain_path(target), "--no-includes", "--null", "--list").stdout
        for field in output.split(b"\0"):
            if field:
                key, separator, value = field.decode(UTF8, "surrogateescape").partition("\n")
                queue.append(dict(key=key, value=value if separator else None,
                                  origin="file:" + str(target)))
    return labels


def inspect_layout(repo, worktrees=None):
    records = discover_worktrees(repo, worktrees)
    files, sources, items = {}, {}, []

    def include(path, label, required=False):
        path = io_path(path)
        _regular_ancestors(path)
        item = current_entry(path, label)
        if item is None:
            if required:
                raise RuntimeError("Configuration dependency disappeared: " + plain_path(path))
            return None
        if item["kind"] != "file":
            raise RuntimeError("Configuration dependency is linked or not a file: " + plain_path(path))
        identity = canonical_path(path)
        if identity in sources:
            return sources[identity]
        files[label] = dict(item, source=plain_path(path))
        sources[identity] = label
        return label

    for index, record in enumerate(records):
        root, admin, common = (Path(record[name]) for name in
                               ("worktree", "admin_dir", "common_dir"))
        labels = {"commonConfig": include(common / "config", "common/config", required=True),
                  "worktreeConfig": include(admin / "config.worktree", f"worktrees/{index:03d}/config.worktree"),
                  "commonExclude": include(common / "info/exclude", "common/info-exclude"),
                  "adminExclude": include(admin / "info/exclude", f"worktrees/{index:03d}/info-exclude"),
                  "commonAttributes": include(common / "info/attributes", "common/info-attributes"),
                  "gitPointer": include(root / ".git", f"worktrees/{index:03d}/git-pointer")
                                if record["git_pointer_kind"] == "file" else None,
                  "adminGitdir": include(admin / "gitdir", f"worktrees/{index:03d}/admin-gitdir"),
                  "adminCommondir": include(admin / "commondir", f"worktrees/{index:03d}/admin-commondir")}
        origins = _preflight_includes(root, _configuration(root, includes=False), include)
        configuration = _configuration(root)
        for value in configuration:
            if value["origin"].startswith("file:"):
                origin_name = value["origin"][5:]
                # Git may print relative local origins as file:.git/config.
                path = Path(origin_name).expanduser()
                if not path.is_absolute():
                    path = root / path
                label = "dependencies/" + hashlib.sha256(
                    canonical_path(path).encode(UTF8, "surrogateescape")).hexdigest() + ".config"
                source_label = include(path, label, required=True)
                if source_label not in origins:
                    origins.append(source_label)
            # An included empty file emits no origin row of its own, but its
            # literal bytes are still a recovery dependency. Preserve optional
            # existing inactive includeIf files too, without enabling them.
            if (path := _include_target(root, value)) is not None:
                label = "dependencies/" + hashlib.sha256(
                    canonical_path(path).encode(UTF8, "surrogateescape")).hexdigest() + ".config"
                source_label = include(path, label)
                if source_label and source_label not in origins:
                    origins.append(source_label)
        exclude = _resolved_config_path(root, "core.excludesfile")
        if exclude is None:
            exclude = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))) / "git/ignore"
        labels["globalExclude"] = include(exclude, f"worktrees/{index:03d}/global-exclude")
        attributes = _resolved_config_path(root, "core.attributesfile")
        if attributes is None:
            attributes = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))) / "git/attributes"
        labels["globalAttributes"] = include(attributes, f"worktrees/{index:03d}/global-attributes")
        hooks_path = Path(text(root, "rev-parse", "--path-format=absolute", "--git-path", "hooks"))
        if not hooks_path.is_absolute():
            hooks_path = root / hooks_path
        _regular_ancestors(hooks_path)
        hooks = inventory_tree(hooks_path, f"worktrees/{index:03d}/hooks")
        for item in hooks:
            if item["kind"] not in ("directory", "file"):
                raise RuntimeError("Hook link requires separate recovery: " + item["path"])
            if item["kind"] == "file":
                relative = item["path"].removeprefix(f"worktrees/{index:03d}/hooks/")
                item["packageFile"] = include(hooks_path / relative, item["path"], required=True)
        items.append(dict(index=index, layout=record, files=labels,
                          configuration=configuration, configurationFiles=origins,
                          effective=[[value["key"], value["value"]] for value in configuration],
                          hooks=dict(source=str(hooks_path), entries=hooks)))
    return dict(schemaVersion=LAYOUT_SCHEMA, repo=str(Path(repo).resolve()),
                worktrees=items, files=files)


def capture_layout(repo, worktrees, output):
    output = io_path(output)
    snapshot = inspect_layout(repo, worktrees)
    output.mkdir(parents=True, exist_ok=False)
    for name, entry in snapshot["files"].items():
        destination = path_within(output, name)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(io_path(entry["source"]).read_bytes())
        if sha256_file(destination) != entry["sha256"]:
            raise RuntimeError("Layout file changed while capturing: " + name)
    if inspect_layout(repo, worktrees) != snapshot:
        raise RuntimeError("Git layout/configuration changed while capturing")
    (output / "layout.json").write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n",
                                       encoding=UTF8, newline="\n")
    return snapshot


def verify_layout(root):
    root = io_path(root)
    if kind_at(root)[0] != "directory" or kind_at(root / "layout.json")[0] != "file":
        raise RuntimeError("Git layout manifest is missing or linked")
    layout = json.loads((root / "layout.json").read_text(encoding=UTF8))
    if layout.get("schemaVersion") != LAYOUT_SCHEMA:
        raise RuntimeError("Unsupported Git layout schema")
    if not isinstance(layout.get("files"), dict) or not isinstance(layout.get("worktrees"), list):
        raise RuntimeError("Invalid Git layout manifest")
    expected = {canonical_rel(name) for name in layout["files"]} | {"layout.json"}
    if set(package_files(root)) != expected:
        raise RuntimeError("Sealed layout file-set mismatch")
    for name, entry in layout["files"].items():
        path = path_within(root, name)
        if (entry.get("path") != name or entry.get("kind") != "file" or
                kind_at(path)[0] != "file" or path.stat().st_size != entry["size"] or
                sha256_file(path) != entry["sha256"]):
            raise RuntimeError("Sealed layout hash mismatch: " + name)
    for index, item in enumerate(layout["worktrees"]):
        if item.get("index") != index or item.get("layout", {}).get("index") != index:
            raise RuntimeError("Invalid Git layout worktree identity")
        for label in list(item["files"].values()) + item["configurationFiles"]:
            if label is not None and label not in layout["files"]:
                raise RuntimeError("Missing layout dependency: " + str(label))
        for entry in item["hooks"]["entries"]:
            if entry["kind"] not in ("directory", "file"):
                raise RuntimeError("Invalid sealed hook entry")
            if entry["kind"] == "file" and entry.get("packageFile") not in layout["files"]:
                raise RuntimeError("Missing sealed hook dependency")
    return layout


def _set_config(repo, key, value, *, worktree=False, worktree_override=None):
    scope = "--worktree" if worktree else "--local"
    run(repo, "config", scope, "--replace-all", key,
        "true" if value is None else value, recovery=True, worktree_override=worktree_override)


def prepare_restore(layout_root, bare, index):
    """Call before worktree add; never install raw/action-producing config."""
    layout = verify_layout(layout_root)
    item = layout["worktrees"][index]
    # Each checkout can have a distinct EOL/core policy. Do not carry settings
    # from the preceding checkout when the next effective view lacks them.
    for key in REPLAY_KEYS:
        run(bare, "config", "--local", "--unset-all", key, check=False, recovery=True)
    for key, value in item["effective"]:
        if key.lower() in REPLAY_KEYS:
            _set_config(bare, key, value)
    disabled = io_path(bare) / "hooks-disabled"
    disabled.mkdir(exist_ok=True)
    _set_config(bare, "core.hooksPath", plain_path(disabled))
    _set_config(bare, "core.fsmonitor", "false")
    _set_config(bare, "core.bare", "true")
    _set_config(bare, "extensions.worktreeConfig", "true")
    # Avoid templates and global/shell actions before configure_restore too.
    _set_config(bare, "init.templateDir", "")
    bootstrap = io_path(bare) / "sealed-bootstrap"
    bootstrap.mkdir(exist_ok=True)
    for key, label_name in (("core.attributesfile", "globalAttributes"),
                            ("core.excludesfile", "globalExclude")):
        label = item["files"].get(label_name)
        target = bootstrap / label_name
        target.write_bytes(path_within(layout_root, label).read_bytes() if label else b"")
        _set_config(bare, key, plain_path(target))
    info = io_path(bare) / "info"
    info.mkdir(exist_ok=True)
    for label_name, name in (("commonAttributes", "attributes"), ("commonExclude", "exclude")):
        label = item["files"].get(label_name)
        (info / name).write_bytes(path_within(layout_root, label).read_bytes() if label else b"")
    return dict(index=index, hooksExecuted=False, filtersExecuted=False,
                sourceConfigFiles=item["configurationFiles"])


def configure_restore(layout_root, bare, worktree, index, *, relocate=False):
    """Remap only from sealed data; retain raw and remapped hashes separately."""
    root, destination = io_path(layout_root), io_path(worktree)
    layout = verify_layout(root)
    item = layout["worktrees"][index]
    # Compare sealed old path lexically: package-only restore must not query the
    # old worktree even for a realpath/lstat lookup.
    old_identity = os.path.normcase(os.path.abspath(item["layout"]["worktree"]))
    if os.path.normcase(plain_path(destination)) == old_identity:
        raise RuntimeError("Refusing to reconfigure the original checkout")
    # A contained linked checkout moved with its parent still has the old
    # core.worktree in config.worktree. Override discovery with --work-tree
    # until its saved bytes have been checked; do not rewrite before that gate.
    override = destination if relocate else None
    common = Path(text(destination, "rev-parse", "--path-format=absolute", "--git-common-dir", recovery=True,
                       worktree_override=override))
    if canonical_path(common) != canonical_path(bare):
        raise RuntimeError("Restored checkout belongs to another Git directory")
    _set_config(bare, "extensions.worktreeConfig", "true")
    admin = io_path(text(destination, "rev-parse", "--absolute-git-dir", recovery=True,
                         worktree_override=override))
    saved = admin / "sealed-layout"
    prior = None
    raw_hashes = {name: value["sha256"] for name, value in layout["files"].items()}
    if relocate:
        if kind_at(saved)[0] != "directory" or kind_at(saved / "remapping.json")[0] != "file":
            raise RuntimeError("Relocation requires the previous sealed remapping record")
        prior = json.loads((saved / "remapping.json").read_text(encoding=UTF8))
        if prior.get("source") != item["layout"] or prior.get("savedRawFiles") != raw_hashes:
            raise RuntimeError("Relocation package differs from the original remapping")
        if sha256_file(admin / "config.worktree") != prior.get("remappedFiles", {}).get("config.worktree"):
            raise RuntimeError("Restored configuration drifted before relocation")
        for name, digest in prior.get("savedFiles", {}).items():
            if sha256_file(path_within(saved, name)) != digest:
                raise RuntimeError("Restored layout dependency drifted before relocation: " + name)
    else:
        saved.mkdir(exist_ok=False)
    remapped = []
    for key, value in item["effective"]:
        if key.lower() in REPLAY_KEYS:
            _set_config(destination, key, value, worktree=True, worktree_override=override)
            remapped.append(dict(key=key, original=value, restored=value, action="retained"))
        else:
            remapped.append(dict(key=key, original=value, restored=None, action="sealed-only"))
    for setting, label_name in (("core.excludesfile", "globalExclude"),
                                ("core.attributesfile", "globalAttributes")):
        label = item["files"].get(label_name)
        # Always supply an explicit empty file when the source default did not
        # exist, so recovery cannot read the host's ~/.config/git/{ignore,attributes}.
        target = saved / label_name
        target.write_bytes(path_within(root, label).read_bytes() if label else b"")
        _set_config(destination, setting, plain_path(target), worktree=True, worktree_override=override)
        remapped.append(dict(key=setting, originalFile=label, restored=plain_path(target), action="remapped"))
    for label_name, relative in (("commonExclude", "info/exclude"),
                                  ("commonAttributes", "info/attributes")):
        label = item["files"].get(label_name)
        target = io_path(text(destination, "rev-parse", "--path-format=absolute", "--git-path", relative, recovery=True,
                              worktree_override=override))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(path_within(root, label).read_bytes() if label else b"")
    # Preserve the admin-specific file too, even when Git uses the common one.
    admin_exclude = item["files"].get("adminExclude")
    if admin_exclude:
        (saved / "admin-info-exclude").write_bytes(path_within(root, admin_exclude).read_bytes())
    disabled = io_path(bare) / "hooks-disabled"
    disabled.mkdir(exist_ok=True)
    for key, value in (("core.worktree", plain_path(destination)), ("core.bare", "false"),
                       ("core.hooksPath", plain_path(disabled)), ("core.fsmonitor", "false")):
        _set_config(destination, key, value, worktree=True, worktree_override=override)
        remapped.append(dict(key=key, restored=value, action="remapped"))
    hooks_saved = saved / "hooks"
    hooks_saved.mkdir(exist_ok=relocate)
    prefix = f"worktrees/{index:03d}/hooks/"
    for entry in item["hooks"]["entries"]:
        if entry["kind"] == "directory" and entry["path"] != prefix.rstrip("/"):
            path_within(hooks_saved, entry["path"].removeprefix(prefix)).mkdir(parents=True, exist_ok=relocate)
        if entry["kind"] == "file":
            label = entry["packageFile"]
            target = path_within(hooks_saved, entry["path"].removeprefix(prefix))
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(path_within(root, label).read_bytes())
    config = admin / "config.worktree"
    pointer = destination / ".git"
    report = dict(
        source=item["layout"], destination=plain_path(destination),
        adminDir=plain_path(admin), commonDir=plain_path(common),
        configRemapped=True, hooksExecuted=False, filtersExecuted=False,
        savedRawFiles=raw_hashes,
        remappedFiles={"config.worktree": sha256_file(config),
                       ".git": sha256_file(pointer) if kind_at(pointer)[0] == "file" else None},
        configuration=remapped,
        savedFiles={name: sha256_file(path) for name, path in package_files(saved).items()
                    if name != "remapping.json"},
        relocations=(prior.get("relocations", []) + [dict(destination=prior["destination"],
                                                        remappedFiles=prior["remappedFiles"])]) if prior else [],
    )
    (saved / "remapping.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                                         encoding=UTF8, newline="\n")
    return report
