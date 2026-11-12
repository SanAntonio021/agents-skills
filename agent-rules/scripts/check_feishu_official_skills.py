#!/usr/bin/env python3
"""Read-only weekly check of Feishu official well-known skill packages.

Downloads the official package index and files, then compares them file by file:

* officially installed packages (recorded in the installer lock) against the
  installed entity and the other runtime layers;
* locally taken-over packages (``status = "localized"`` in the source registry)
  against their accepted official baseline, never against the installed entity,
  which carries local additions.

The script only writes inside ``--out``. It never installs, never edits skill
sources, runtime copies, the installer lock or any baseline, and it does not
decide whether a difference changes behaviour.

Exit codes: 0 = complete, no differences; 10 = complete, differences found;
20 = incomplete (something could not be checked; never read this as "no update").
"""
from __future__ import annotations

import argparse
import concurrent.futures
import datetime
import difflib
import hashlib
import json
import re
import shutil
import sys
import time
import tomllib
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, Callable

TOOL = "check_feishu_official_skills"
SCHEMA_VERSION = 1
DEFAULT_INDEX_URL = "https://open.feishu.cn/.well-known/skills/index.json"
DEFAULT_LOCK_SOURCE = "open.feishu.cn"
EXIT_NO_CHANGES = 0
EXIT_CHANGES = 10
EXIT_INCOMPLETE = 20
SKILL_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")
RETRY_HTTP_CODES = {502, 503, 504}

Fetch = Callable[[str], bytes]


class CheckError(Exception):
    """A condition that prevents the whole check from producing a result."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class Config:
    agents_root: Path
    out: Path
    home: Path
    index_url: str = DEFAULT_INDEX_URL
    lock_source: str = DEFAULT_LOCK_SOURCE
    registries: list[Path] = field(default_factory=list)
    baselines_dir: Path | None = None
    source_roots: list[Path] = field(default_factory=list)
    lock_path: Path | None = None
    entity_root: Path | None = None
    layers: dict[str, Path] = field(default_factory=dict)
    retry_waits: tuple[float, ...] = (10.0, 30.0)
    refetch: int = 6
    workers: int = 8
    timeout: float = 30.0
    overwrite: bool = False

    def resolved(self) -> "Config":
        root = self.agents_root
        if not self.registries:
            self.registries = [root / "upstream" / "skill-sources.toml"]
            private = root / "upstream" / "private-skill-sources.toml"
            if private.is_file():
                self.registries.append(private)
        if self.baselines_dir is None:
            self.baselines_dir = root / "upstream" / "official-baselines"
        if not self.source_roots:
            self.source_roots = [root / "skills", root / "private-skills"]
        if self.lock_path is None:
            self.lock_path = self.home / ".agents" / ".skill-lock.json"
        if self.entity_root is None:
            self.entity_root = self.home / ".agents" / "skills"
        if not self.layers:
            self.layers = {
                "cc_switch": self.home / ".cc-switch" / "skills",
                "claude": self.home / ".claude" / "skills",
                "codex": self.home / ".codex" / "skills",
            }
        return self


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def normalize_eol(data: bytes) -> bytes:
    return data.replace(b"\r\n", b"\n")


def make_fetch(timeout: float) -> Fetch:
    def fetch(url: str) -> bytes:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return response.read()

    return fetch


def fetch_with_retry(fetch: Fetch, url: str, waits: tuple[float, ...]) -> bytes:
    attempts = len(waits) + 1
    for attempt in range(attempts):
        last = attempt == attempts - 1
        try:
            return fetch(url)
        except urllib.error.HTTPError as exc:
            if exc.code not in RETRY_HTTP_CODES or last:
                raise
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            if last:
                raise
        time.sleep(waits[attempt])
    raise AssertionError("unreachable")


def is_safe_rel(rel: Any) -> bool:
    if not isinstance(rel, str) or not rel or "\\" in rel or ":" in rel:
        return False
    path = PurePosixPath(rel)
    return not path.is_absolute() and all(part not in ("", ".", "..") for part in path.parts)


def manifest_dir(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for item in sorted(path.rglob("*")):
        if not item.is_file():
            continue
        rel = item.relative_to(path).as_posix()
        if "__pycache__" in item.parts and item.suffix == ".pyc":
            continue
        result[rel] = sha256(item.read_bytes())
    return result


def delta(target: dict[str, str], official: dict[str, str]) -> dict[str, list[str]]:
    return {
        "official_added": sorted(official.keys() - target.keys()),
        "official_removed": sorted(target.keys() - official.keys()),
        "changed": sorted(p for p in target.keys() & official.keys() if target[p] != official[p]),
    }


def load_json(path: Path, code: str) -> Any:
    try:
        return json.loads(path.read_bytes().decode("utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise CheckError(code, f"{path}: {exc}") from exc


def load_index(raw: bytes) -> dict[str, list[str]]:
    try:
        data = json.loads(raw.decode("utf-8-sig"))
        skills = data["skills"]
        packages: dict[str, list[str]] = {}
        for entry in skills:
            name, files = entry["name"], entry["files"]
            if not isinstance(name, str) or not SKILL_NAME.match(name):
                raise CheckError("index_unsafe_name", f"unsafe skill name in index: {name!r}")
            if name in packages:
                raise CheckError("index_duplicate_skill", f"duplicate skill in index: {name}")
            if not isinstance(files, list) or not files:
                raise CheckError("index_invalid_files", f"{name}: index lists no files")
            for rel in files:
                if not is_safe_rel(rel):
                    raise CheckError("index_unsafe_path", f"{name}: unsafe file path in index: {rel!r}")
            if len(set(files)) != len(files):
                raise CheckError("index_duplicate_path", f"{name}: duplicate file path in index")
            packages[name] = list(files)
        return packages
    except CheckError:
        raise
    except (ValueError, KeyError, TypeError) as exc:
        raise CheckError("index_invalid", f"official index is not in the expected format: {exc}") from exc


def load_registry_status(paths: list[Path]) -> dict[str, str]:
    status: dict[str, str] = {}
    for path in paths:
        try:
            data = tomllib.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, tomllib.TOMLDecodeError) as exc:
            raise CheckError("registry_unreadable", f"{path}: {exc}") from exc
        for entry in data.get("skill", []):
            name = entry.get("name")
            if isinstance(name, str):
                status[name] = str(entry.get("status", ""))
    return status


def load_official_lock(path: Path, source: str) -> tuple[dict[str, Any], bytes]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise CheckError("lock_unreadable", f"{path}: {exc}") from exc
    data = load_json(path, "lock_unreadable")
    try:
        entries = data["skills"]
        official = {
            name: value
            for name, value in entries.items()
            if value.get("sourceType") == "well-known" and value.get("source") == source
        }
    except (KeyError, AttributeError, TypeError) as exc:
        raise CheckError("lock_invalid", f"{path}: unexpected lock structure: {exc}") from exc
    return official, raw


def load_baseline(directory: Path, name: str, index_url: str) -> dict[str, Any]:
    path = directory / name / "baseline.json"
    data = load_json(path, "baseline_unreadable")
    files = data.get("files") if isinstance(data, dict) else None
    if not isinstance(data, dict) or data.get("skill") != name:
        raise CheckError("baseline_invalid", f"{path}: skill name does not match directory")
    if not isinstance(files, dict) or not files:
        raise CheckError("baseline_invalid", f"{path}: files must be a non-empty object")
    for rel, digest in files.items():
        if not is_safe_rel(rel) or not isinstance(digest, str) or not SHA256_HEX.match(digest):
            raise CheckError("baseline_invalid", f"{path}: invalid entry {rel!r}")
    if data.get("index_url") != index_url:
        raise CheckError("baseline_index_mismatch", f"{path}: baseline index_url differs from the checked index")
    return data


def self_owned_skills(roots: list[Path]) -> dict[str, str]:
    owned: dict[str, str] = {}
    for root in roots:
        if not root.is_dir():
            continue
        for entry in sorted(root.glob("*/SKILL.md")):
            owned.setdefault(entry.parent.name, str(entry.parent))
    return owned


def prepare_out(out: Path, overwrite: bool) -> None:
    out.mkdir(parents=True, exist_ok=True)
    for name in ("official", "diffs"):
        sub = out / name
        if not sub.exists():
            continue
        if not overwrite:
            raise CheckError("output_exists", f"{sub} already exists; pass --overwrite to replace this run's snapshot")
        if sub.resolve().parent != out.resolve():
            raise CheckError("output_unsafe", f"{sub} does not resolve inside the output directory")
        shutil.rmtree(sub)


def write_diff(out: Path, name: str, rel: str, before: bytes, after: bytes, label: str) -> str | None:
    if b"\0" in before or b"\0" in after:
        return None
    old = normalize_eol(before).decode("utf-8", errors="replace").splitlines(True)
    new = normalize_eol(after).decode("utf-8", errors="replace").splitlines(True)
    patch = "".join(
        difflib.unified_diff(old, new, fromfile=f"{label}/{name}/{rel}", tofile=f"official/{name}/{rel}")
    )
    target = out / "diffs" / name / (rel + ".diff")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(patch.encode("utf-8"))
    return target.relative_to(out).as_posix()


def run_check(cfg: Config, fetch: Fetch | None = None) -> tuple[dict[str, Any], int]:
    cfg = cfg.resolved()
    fetch = fetch or make_fetch(cfg.timeout)
    checked_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
    try:
        report = _run(cfg, fetch, checked_at)
    except CheckError as exc:
        report = {
            "tool": TOOL,
            "schema_version": SCHEMA_VERSION,
            "checked_at": checked_at,
            "official_index_url": cfg.index_url,
            "status": "incomplete",
            "complete": False,
            "differences_found": False,
            "errors": [{"code": exc.code, "message": exc.message}],
            "read_only": True,
        }
    report["exit_code"] = (
        EXIT_INCOMPLETE if not report["complete"] else EXIT_CHANGES if report["differences_found"] else EXIT_NO_CHANGES
    )
    try:
        cfg.out.mkdir(parents=True, exist_ok=True)
        (cfg.out / "comparison.json").write_bytes(json.dumps(report, ensure_ascii=False, indent=2).encode("utf-8"))
        report["comparison"] = str(cfg.out / "comparison.json")
    except OSError as exc:
        report.setdefault("errors", []).append({"code": "report_write_failed", "message": str(exc)})
        report["status"], report["complete"], report["exit_code"] = "incomplete", False, EXIT_INCOMPLETE
    return report, report["exit_code"]


def _run(cfg: Config, fetch: Fetch, checked_at: str) -> dict[str, Any]:
    assert cfg.baselines_dir and cfg.lock_path and cfg.entity_root
    prepare_out(cfg.out, cfg.overwrite)
    base_url = cfg.index_url.rsplit("/", 1)[0]

    try:
        index_raw = fetch_with_retry(fetch, cfg.index_url, cfg.retry_waits)
    except Exception as exc:  # network, HTTP or file errors: nothing can be checked
        raise CheckError("index_download_failed", f"{cfg.index_url}: {exc}") from exc
    (cfg.out / "index.json").write_bytes(index_raw)
    packages = load_index(index_raw)

    official_lock, lock_raw = load_official_lock(cfg.lock_path, cfg.lock_source)
    registry_status = load_registry_status(cfg.registries)
    localized_registered = {name for name, status in registry_status.items() if status == "localized"}
    owned = self_owned_skills(cfg.source_roots)
    with_baseline = (
        {p.parent.name for p in cfg.baselines_dir.glob("*/baseline.json")} if cfg.baselines_dir.is_dir() else set()
    )

    errors: list[dict[str, Any]] = []
    for name in sorted(with_baseline - localized_registered):
        errors.append({"code": "baseline_not_registered_localized", "skill": name,
                       "message": "a baseline exists but the registry does not mark this skill as localized"})

    # Locally taken-over official packages: compared with their accepted baseline.
    baselines: dict[str, dict[str, Any]] = {}
    for name in sorted(localized_registered):
        relevant = name in packages or name in official_lock or name in with_baseline
        if not relevant:
            continue
        if name not in with_baseline:
            errors.append({"code": "baseline_missing", "skill": name,
                           "message": f"localized skill has no accepted baseline under {cfg.baselines_dir}"})
            continue
        try:
            baselines[name] = load_baseline(cfg.baselines_dir, name, cfg.index_url)
        except CheckError as exc:
            errors.append({"code": exc.code, "skill": name, "message": exc.message})
    localized = set(baselines)

    # Officially installed packages: compared with the installed entity.
    installed_official: set[str] = set()
    lock_without_entity: list[str] = []
    for name in sorted(set(official_lock) - localized_registered):
        if not (cfg.entity_root / name / "SKILL.md").is_file():
            lock_without_entity.append(name)
        elif name in owned:
            errors.append({"code": "unregistered_takeover", "skill": name,
                           "message": f"lock says official but a self-owned source exists at {owned[name]} "
                                      "and the registry does not mark it as localized"})
        else:
            installed_official.add(name)

    excluded_self_built = sorted((set(owned) & set(packages)) - localized_registered - set(official_lock))
    scope = installed_official | localized
    for name in sorted(scope - set(packages)):
        errors.append({"code": "missing_from_index", "skill": name,
                       "message": "skill is in scope but the official index no longer lists it"})

    tasks = [(name, rel) for name in sorted(scope & set(packages)) for rel in packages[name]]

    def download(item: tuple[str, str]) -> dict[str, Any]:
        name, rel = item
        url = f"{base_url}/{name}/{urllib.parse.quote(rel, safe='/')}"
        try:
            data = fetch_with_retry(fetch, url, cfg.retry_waits)
        except Exception as exc:
            return {"skill": name, "path": rel, "url": url, "error": f"{type(exc).__name__}: {exc}"}
        target = cfg.out / "official" / name / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        return {"skill": name, "path": rel, "url": url, "bytes": len(data), "sha256": sha256(data)}

    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, cfg.workers)) as pool:
        files = list(pool.map(download, tasks))
    download_errors = [f for f in files if "error" in f]

    def target_bytes(name: str, rel: str) -> bytes | None:
        path = (cfg.baselines_dir / name / "files" / rel) if name in localized else (cfg.entity_root / name / rel)
        try:
            return path.read_bytes()
        except OSError:
            return None

    def inspect_changed(name: str, rel: str, target_digest: str, official_digest: str) -> dict[str, Any]:
        url = f"{base_url}/{name}/{urllib.parse.quote(rel, safe='/')}"
        variants = {official_digest}
        refetch_errors: list[str] = []
        for _ in range(max(0, cfg.refetch)):
            try:
                variants.add(sha256(fetch_with_retry(fetch, url, cfg.retry_waits)))
            except Exception as exc:
                refetch_errors.append(f"{type(exc).__name__}: {exc}")
        record: dict[str, Any] = {
            "path": rel,
            "target_sha256": target_digest,
            "official_sha256": official_digest,
            "unstable_response": len(variants) > 1,
            "variants": sorted(variants),
            "matches_target": target_digest in variants,
        }
        if refetch_errors:
            record["refetch_errors"] = refetch_errors
        # The diff is written even when a later response matched the target, so that an
        # unstable response can be confirmed from the report without ad-hoc comparison.
        before = target_bytes(name, rel)
        after = (cfg.out / "official" / name / rel).read_bytes()
        if before is None:
            record.update({"eol_only": None, "diff": None, "diff_unavailable": "target content not available"})
        else:
            record["eol_only"] = normalize_eol(before) == normalize_eol(after)
            record["diff"] = write_diff(cfg.out, name, rel, before, after,
                                        "baseline" if name in localized else "installed")
            if record["diff"] is None:
                record["diff_unavailable"] = "binary content"
        return record

    skills: list[dict[str, Any]] = []
    for name in sorted(scope & set(packages)):
        kind = "localized" if name in localized else "official_installed"
        official = {f["path"]: f["sha256"] for f in files if f["skill"] == name and "sha256" in f}
        failed = sorted(f["path"] for f in files if f["skill"] == name and "error" in f)
        target = dict(baselines[name]["files"]) if kind == "localized" else manifest_dir(cfg.entity_root / name)
        row: dict[str, Any] = {
            "skill": name,
            "kind": kind,
            "compared_with": "accepted_baseline" if kind == "localized" else "installed_entity",
            "official_manifest": official,
            "target_manifest": target,
            "download_failed": failed,
        }
        if kind == "localized":
            row["baseline"] = {
                "path": str(cfg.baselines_dir / name / "baseline.json"),
                "accepted_at": baselines[name].get("accepted_at"),
            }
        else:
            row["source_lock"] = official_lock[name]
        if failed:
            # A partial download cannot tell added/removed apart from failures.
            row.update({"status": "incomplete", "official_added": [], "official_removed": [], "changed": [],
                        "unstable_matching_target": []})
        else:
            diff = delta(target, official)
            inspected = [inspect_changed(name, rel, target[rel], official[rel]) for rel in diff["changed"]]
            changed = [r for r in inspected if not r["matches_target"]]
            row.update({
                "official_added": diff["official_added"],
                "official_removed": diff["official_removed"],
                "changed": changed,
                "unstable_matching_target": [r for r in inspected if r["matches_target"]],
            })
            row["status"] = (
                "changed" if diff["official_added"] or diff["official_removed"] or changed else "unchanged"
            )
        if kind == "official_installed":
            entity = cfg.entity_root / name
            layers: dict[str, Any] = {}
            for label, root in cfg.layers.items():
                path = root / name
                if not path.exists():
                    layers[label] = {"present": False}
                elif path.resolve() == entity.resolve():
                    layers[label] = {"present": True, "same_as_entity": True, "drift": False}
                else:
                    other = manifest_dir(path)
                    drift = {
                        "missing": sorted(target.keys() - other.keys()),
                        "extra": sorted(other.keys() - target.keys()),
                        "changed": sorted(p for p in target.keys() & other.keys() if target[p] != other[p]),
                    }
                    layers[label] = {"present": True, "same_as_entity": False,
                                     "drift": any(drift.values()), **drift}
            row["layers"] = layers
            row["layer_drift"] = any(layer.get("drift") for layer in layers.values())
        skills.append(row)

    changed_skills = {
        row["skill"]: {
            "kind": row["kind"],
            "official_added": row["official_added"],
            "official_removed": row["official_removed"],
            "changed": [r["path"] for r in row["changed"]],
            "eol_only": [r["path"] for r in row["changed"] if r.get("eol_only")],
        }
        for row in skills if row["status"] == "changed"
    }
    layer_drift = {
        row["skill"]: {label: layer for label, layer in row["layers"].items() if layer.get("drift")}
        for row in skills if row.get("layer_drift")
    }
    unstable = {
        row["skill"]: [r["path"] for r in row["unstable_matching_target"]]
        for row in skills if row["unstable_matching_target"]
    }
    complete = not errors and not download_errors
    differences = bool(changed_skills or layer_drift)
    return {
        "tool": TOOL,
        "schema_version": SCHEMA_VERSION,
        "checked_at": checked_at,
        "official_index_url": cfg.index_url,
        "index_sha256": sha256(index_raw),
        "status": "incomplete" if not complete else "changes_found" if differences else "no_changes",
        "complete": complete,
        "differences_found": differences,
        "counts": {
            "index_skills": len(packages),
            "index_files": sum(len(v) for v in packages.values()),
            "official_installed": len(installed_official),
            "localized": len(localized),
            "downloaded_files": sum("sha256" in f for f in files),
            "download_errors": len(download_errors),
        },
        "official_installed": sorted(installed_official),
        "localized": sorted(localized),
        "changed_skills": changed_skills,
        "unstable_matching_target": unstable,
        "layer_drift": layer_drift,
        "incomplete_skills": sorted(row["skill"] for row in skills if row["status"] == "incomplete"),
        "errors": errors,
        "download_errors": download_errors,
        "excluded_self_built": excluded_self_built,
        "not_installed_candidates": sorted(set(packages) - installed_official - localized_registered - set(owned)),
        "lock_without_entity": lock_without_entity,
        "lock_sha256": sha256(lock_raw),
        "lock_unchanged": cfg.lock_path.read_bytes() == lock_raw,
        "read_only": True,
        "baseline_advanced": False,
        "skills": skills,
        "files": files,
    }


SUMMARY_KEYS = (
    "tool", "status", "exit_code", "complete", "differences_found", "checked_at", "index_sha256", "counts",
    "changed_skills", "unstable_matching_target", "layer_drift", "incomplete_skills", "errors",
    "excluded_self_built", "not_installed_candidates", "lock_without_entity", "lock_unchanged", "comparison",
)


def parse_layer(value: str) -> tuple[str, Path]:
    label, sep, path = value.partition("=")
    if not sep or not label or not path:
        raise argparse.ArgumentTypeError("layer must be given as name=path")
    return label, Path(path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--agents-root", type=Path, required=True, help="Maintenance root holding upstream/ and skills/.")
    parser.add_argument("--out", type=Path, required=True, help="Report directory for this run, e.g. <reports-root>/<date>/feishu.")
    parser.add_argument("--overwrite", action="store_true", help="Replace an existing official/ and diffs/ snapshot in --out.")
    parser.add_argument("--home", type=Path, default=Path.home(), help="User home used to locate the lock, entity and runtime layers.")
    parser.add_argument("--index-url", default=DEFAULT_INDEX_URL)
    parser.add_argument("--lock-source", default=DEFAULT_LOCK_SOURCE)
    parser.add_argument("--registry", type=Path, action="append", default=[], help="Source registry; repeatable. Defaults to the public and private registries under upstream/.")
    parser.add_argument("--baselines-dir", type=Path, help="Accepted official baselines; defaults to upstream/official-baselines.")
    parser.add_argument("--source-root", type=Path, action="append", default=[], help="Self-owned skill source root; repeatable.")
    parser.add_argument("--lock", type=Path, help="Installer lock; defaults to <home>/.agents/.skill-lock.json.")
    parser.add_argument("--entity-root", type=Path, help="Installed entity root; defaults to <home>/.agents/skills.")
    parser.add_argument("--layer", type=parse_layer, action="append", default=[], help="Runtime layer to compare with the entity, as name=path; repeatable. Replaces the default cc_switch/claude/codex layers.")
    parser.add_argument("--retry-waits", default="10,30", help="Seconds to wait before each retry, comma separated.")
    parser.add_argument("--refetch", type=int, default=6, help="Extra downloads of a differing file to detect unstable responses.")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--timeout", type=float, default=30.0)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    waits = tuple(float(v) for v in args.retry_waits.split(",") if v.strip())
    cfg = Config(
        agents_root=args.agents_root, out=args.out, home=args.home, index_url=args.index_url,
        lock_source=args.lock_source, registries=list(args.registry), baselines_dir=args.baselines_dir,
        source_roots=list(args.source_root), lock_path=args.lock, entity_root=args.entity_root,
        layers=dict(args.layer), retry_waits=waits, refetch=args.refetch, workers=args.workers,
        timeout=args.timeout, overwrite=args.overwrite,
    )
    report, code = run_check(cfg)
    summary = {key: report[key] for key in SUMMARY_KEYS if key in report}
    sys.stdout.buffer.write(json.dumps(summary, ensure_ascii=False, indent=2).encode("utf-8") + b"\n")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
