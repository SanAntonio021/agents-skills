#!/usr/bin/env python3
"""Validate Humanizer's portable package surfaces without external dependencies."""

from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
def read_package_file(relative_path: str) -> str:
    try:
        return (ROOT / relative_path).read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise SystemExit(f"Cannot read {relative_path} as UTF-8: {error}") from None


SKILL = read_package_file("SKILL.md")
README = read_package_file("README.md")
try:
    PLUGIN = json.loads(read_package_file(".claude-plugin/plugin.json"))
except json.JSONDecodeError as error:
    raise SystemExit(
        f"Invalid JSON in .claude-plugin/plugin.json at line {error.lineno}, "
        f"column {error.colno}: {error.msg}"
    ) from None
if not isinstance(PLUGIN, dict):
    raise SystemExit(".claude-plugin/plugin.json must contain a JSON object")


def require(match: re.Match[str] | None, message: str) -> re.Match[str]:
    if match is None:
        raise SystemExit(message)
    return match


frontmatter = require(
    re.match(r"\A---\n(.*?)\n---\n", SKILL, re.DOTALL),
    "SKILL.md must start with YAML frontmatter",
).group(1)

for nonportable_key in ("version:", "compatibility:", "allowed-tools:"):
    if re.search(rf"(?m)^{re.escape(nonportable_key)}", frontmatter):
        raise SystemExit(f"Remove nonportable frontmatter key: {nonportable_key[:-1]}")

skill_version = require(
    re.search(r'(?m)^\s+version:\s*["\']([^"\']+)["\']\s*$', frontmatter),
    "SKILL.md metadata.version is missing",
).group(1)
readme_version = require(
    re.search(r"(?m)^- \*\*([0-9]+\.[0-9]+\.[0-9]+)\*\*", README),
    "README version history is missing",
).group(1)

versions = {skill_version, readme_version, str(PLUGIN.get("version", ""))}
if len(versions) != 1:
    raise SystemExit(f"Version mismatch: {sorted(versions)}")

pattern_numbers = [
    int(number)
    for number in re.findall(r"(?m)^### ([0-9]+)\. ", SKILL)
]
if pattern_numbers != list(range(1, 34)):
    raise SystemExit(f"Expected patterns 1-33, found {pattern_numbers}")

readme_numbers = [
    int(number) for number in re.findall(r"(?m)^\| ([0-9]+) \|", README)
]
if sorted(readme_numbers) != pattern_numbers:
    raise SystemExit("README pattern table must contain patterns 1-33 exactly once each")

if len(SKILL.splitlines()) > 500:
    raise SystemExit("SKILL.md exceeds the 500-line portability budget")

print(f"Humanizer package v{skill_version} is valid")
