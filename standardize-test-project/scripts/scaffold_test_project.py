#!/usr/bin/env python3
"""Create a test-project scaffold without touching instruments or old results."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path


DIRECTORIES = (
    "code/experiments/single_point",
    "code/experiments/frequency_sweep",
    "code/experiments/power_sweep",
    "code/instrument_control",
    "code/acquisition",
    "code/signal_processing",
    "code/plotting",
    "code/result_management",
    "code/analysis",
    "code/simulation",
    "code/tests",
    "config",
    "data",
    "docs",
    "results/single_point",
    "results/scan",
    "results/dry_run",
    "results/simulation",
    "results/analysis",
    "archive",
)

TEXT_TEMPLATES = {
    "README.md.template": "README.md",
    "AGENTS.md.template": "AGENTS.md",
    "CLAUDE.md.template": "CLAUDE.md",
    "GEMINI.md.template": "GEMINI.md",
    "gitignore.template": ".gitignore",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a standardized experimental test project."
    )
    parser.add_argument("project", type=Path, help="New project directory")
    parser.add_argument("--name", required=True, help="Human-readable project name")
    parser.add_argument(
        "--language",
        choices=("matlab", "python", "both"),
        default="both",
        help="Helper and entry-point language",
    )
    return parser.parse_args()


def ensure_target(target: Path) -> None:
    if target.exists() and not target.is_dir():
        raise FileExistsError(f"Target exists and is not a directory: {target}")
    if target.exists() and any(target.iterdir()):
        raise FileExistsError(f"Refusing to overwrite nonempty directory: {target}")
    target.mkdir(parents=True, exist_ok=True)


def render_text(source: Path, destination: Path, project_name: str) -> None:
    text = source.read_text(encoding="utf-8")
    destination.write_text(
        text.replace("{{PROJECT_NAME}}", project_name), encoding="utf-8"
    )


def copy_language_files(
    template_root: Path, target: Path, language: str, project_name: str
) -> None:
    suffixes = {".m"} if language == "matlab" else {".py"}
    if language == "both":
        suffixes = {".m", ".py"}

    code_root = template_root / "code"
    for source in code_root.rglob("*"):
        if not source.is_file() or source.suffix.lower() not in suffixes:
            continue
        relative = source.relative_to(template_root)
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)

    entry_sources = []
    if language in {"matlab", "both"}:
        entry_sources.append((template_root / "Run_Test.m.template", target / "Run_Test.m"))
    if language in {"python", "both"}:
        entry_sources.append((template_root / "run_test.py.template", target / "run_test.py"))
    for source, destination in entry_sources:
        render_text(source, destination, project_name)


def scaffold(target: Path, project_name: str, language: str) -> None:
    target = target.resolve()
    ensure_target(target)
    template_root = Path(__file__).resolve().parents[1] / "assets" / "project-template"
    for relative in DIRECTORIES:
        (target / relative).mkdir(parents=True, exist_ok=True)
    for source_name, destination_name in TEXT_TEMPLATES.items():
        render_text(
            template_root / source_name,
            target / destination_name,
            project_name,
        )
    copy_language_files(template_root, target, language, project_name)


def main() -> int:
    args = parse_args()
    scaffold(args.project, args.name.strip(), args.language)
    print(f"Created standardized test project: {args.project.resolve()}")
    print("No instrument connection, query, or write was performed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
