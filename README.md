# agents-skills

Personal skill library for Claude Code and Codex CLI, distributed via [cc-switch](https://github.com/farion1231/cc-switch).

## What This Is

This repo keeps one skill per top-level directory. Each skill directory contains a `SKILL.md` and may also include `references/`, `scripts/`, `assets/`, or `agents/`.

The layout follows the flat root convention expected by `cc-switch`.

## Who This Is For

This repo primarily exists for the author's own cross-machine skill sync.

It is published because the current `cc-switch` release can consume public GitHub skill repos directly, while private repo auth is not yet available in the same workflow.

Third parties are welcome to browse or fork it, but no compatibility or support guarantees are promised.

## How To Use

1. Install `cc-switch`.
2. In repo management, add `SanAntonio021/agents-skills` and branch `main`.
3. Let `cc-switch` install skills into `%USERPROFILE%\.claude\skills\` and/or `%USERPROFILE%\.codex\skills\`.

## Conventions

- Public docs use placeholders such as `%USERPROFILE%`, `<agents-root>`, and `<projects-root>` instead of hardcoded local paths.
- Cross-skill references use bare skill names or local relative links within this repo, not references into old private directory layouts.
- Some Word-formatting presets ship only style profiles in the public repo; original sample `.docx` files are intentionally omitted.
