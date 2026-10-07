"""Read-only resolution of the registered official Presentations package.

Exit 0 means package files are located, not that authoring/runtime QA has passed.
Exit 1 means unavailable. --plugin-list-json is only for isolated fixtures.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from urllib.parse import unquote

PLUGIN_ID = "presentations@openai-primary-runtime"
REQUIRED = (
    "references/implementation.md",
    "references/finalization.md",
    "artifact_tool_docs/API_QUICK_START.md",
    "artifact_tool_docs/api/API_DOCS.md",
    "container_tools/mark_artifact_operation_started.mjs",
    "container_tools/artifact_tool_utils.mjs",
    "container_tools/inspect_presentation_package_integrity.py",
    "container_tools/inspect_presentation_layout_geometry.py",
)


class Unavailable(Exception):
    pass


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def contained(root: Path, relative: str) -> Path:
    if not isinstance(relative, str) or not relative.strip():
        raise Unavailable("invalid_relative_path")
    path = (root / relative).resolve()
    if Path(relative).is_absolute() or not path.is_relative_to(root.resolve()):
        raise Unavailable("path_outside_package")
    return path


def existing_home(env, key):
    value = env.get(key, "")
    path = Path(value)
    return path.resolve() if value and path.is_absolute() and path.is_dir() else None


def find_codex(env=None) -> Path:
    """Prefer explicit Codex home, then the actual user's npm native binary.

    Do not execute PowerShell/cmd shims or search plugin caches for executables.
    """
    env = os.environ if env is None else env
    user = existing_home(env, "USERPROFILE" if os.name == "nt" else "HOME")
    home = existing_home(env, "CODEX_HOME")
    if env.get("CODEX_HOME") and home is None:
        raise Unavailable("invalid_codex_home")
    candidates = []
    if home:
        candidates.append(home / "bin" / ("codex.exe" if os.name == "nt" else "codex"))
    if user:
        candidates.append(user / ".codex/bin" / ("codex.exe" if os.name == "nt" else "codex"))
        if os.name == "nt":
            npm = user / "AppData/Roaming/npm/node_modules/@openai/codex/node_modules/@openai"
            arch = "arm64" if env.get("PROCESSOR_ARCHITECTURE", "").lower() == "arm64" else "x64"
            triple = "aarch64" if arch == "arm64" else "x86_64"
            candidates.append(npm / f"codex-win32-{arch}/vendor/{triple}-pc-windows-msvc/bin/codex.exe")
    on_path = shutil.which("codex.exe" if os.name == "nt" else "codex", path=env.get("PATH", ""))
    if on_path:
        candidates.append(Path(on_path))
    for candidate in candidates:
        if candidate.is_absolute() and candidate.is_file():
            return candidate.resolve()
    raise Unavailable("codex_executable_not_found")


def load_registry(executable: Path):
    try:
        result = subprocess.run(
            [str(executable), "plugin", "list", "--json"],
            stdin=subprocess.DEVNULL, capture_output=True, text=True,
            encoding="utf-8", timeout=60,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise Unavailable("plugin_list_failed") from exc
    if result.returncode != 0:
        # Do not copy CLI stderr/configuration into a public locator receipt.
        raise Unavailable("plugin_list_failed")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise Unavailable("plugin_list_invalid_json") from exc


def resolve(registry):
    if not isinstance(registry, dict) or not isinstance(registry.get("installed"), list):
        raise Unavailable("plugin_list_invalid_schema")
    matches = [item for item in registry["installed"]
               if isinstance(item, dict) and item.get("pluginId") == PLUGIN_ID]
    if len(matches) != 1:
        raise Unavailable("plugin_missing" if not matches else "plugin_ambiguous")
    entry = matches[0]
    if entry.get("installed") is not True or entry.get("enabled") is not True:
        raise Unavailable("plugin_not_installed_or_enabled")
    source = entry.get("source")
    if not isinstance(source, dict) or source.get("source") != "local":
        raise Unavailable("local_source_unavailable")
    raw_path = source.get("path")
    if not isinstance(raw_path, str) or not Path(raw_path).is_absolute():
        raise Unavailable("invalid_source_path")
    root = Path(raw_path).resolve()
    manifest_path = contained(root, ".codex-plugin/plugin.json")
    if not manifest_path.is_file():
        raise Unavailable("plugin_manifest_missing")
    manifest = read_json(manifest_path)
    if not isinstance(manifest, dict) or manifest.get("name") != "presentations":
        raise Unavailable("plugin_manifest_identity_mismatch")
    version = entry.get("version")
    if not isinstance(version, str) or not version or manifest.get("version") != version:
        raise Unavailable("plugin_version_mismatch")
    skills = manifest.get("skills")
    if not isinstance(skills, str):
        raise Unavailable("unsupported_skills_manifest")
    skills_root = contained(root, skills)
    if not skills_root.is_dir():
        raise Unavailable("skills_directory_missing")
    # Only the registered package's declared skill root, never sibling caches.
    candidates = []
    for path in skills_root.glob("*/SKILL.md"):
        if not path.resolve().is_relative_to(root):
            raise Unavailable("path_outside_package")
        content = path.read_text(encoding="utf-8-sig")
        frontmatter = re.match(r"\A---\s*\n(.*?)\n---(?:\s*\n|$)", content, re.S)
        if frontmatter and re.search(r"^name:\s*['\"]?Presentations['\"]?\s*$", frontmatter[1], re.M):
            candidates.append((path.resolve(), content))
    if len(candidates) != 1:
        raise Unavailable("skill_missing" if not candidates else "skill_ambiguous")
    skill, content = candidates[0]
    dependencies = set(REQUIRED)
    # Check all actual local Markdown links declared by the skill entrypoint.
    for link in re.findall(r"\]\(([^\s)]+)\)", content):
        if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", link) or link.startswith("#"):
            continue
        dependencies.add(unquote(link.split("#", 1)[0]))
    for relative in re.findall(r"`((?:references|artifact_tool_docs|container_tools|routing)/[^`\s]+)`", content):
        dependencies.add(relative.split("#", 1)[0])
    resolved = {}
    for relative in sorted(dependencies):
        path = contained(skill.parent, relative)
        if not path.is_file():
            raise Unavailable("required_dependency_missing:" + relative)
        resolved[relative] = str(path)
    return {
        "status": "available", "reason": "registered_package_resolved",
        "plugin_id": PLUGIN_ID, "version": version,
        "plugin_root": str(root), "manifest_path": str(manifest_path),
        "skill_path": str(skill), "skill_dir": str(skill.parent),
        "skill_sha256": hashlib.sha256(skill.read_bytes()).hexdigest(),
        "dependencies": resolved,
        "runtime_check": "required_via_load_workspace_dependencies_before_authoring",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plugin-list-json", type=Path, help="isolated registry fixture; not live evidence")
    args = parser.parse_args(argv)
    mode = "fixture" if args.plugin_list_json else "live"
    try:
        executable = None if args.plugin_list_json else find_codex()
        registry = read_json(args.plugin_list_json) if args.plugin_list_json else load_registry(executable)
        result = resolve(registry)
        if executable:
            result["codex_executable"] = str(executable)
    except Unavailable as exc:
        result = {"status": "unavailable", "reason": str(exc)}
    except (OSError, ValueError, TypeError) as exc:
        result = {"status": "unavailable", "reason": "unreadable_or_invalid_package_data",
                  "error_type": type(exc).__name__}
    result["evidence_mode"] = mode
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "available" else 1


if __name__ == "__main__":
    sys.exit(main())
