# Integration Results - 2026-07-11

## Environment

- Claude Code: 2.1.207
- Plugin: `codex@openai-codex` 1.0.6, enabled
- Codex CLI: 0.144.1, authenticated
- Official stop-time review gate: disabled
- Persistent Claude permissions: exact current Plugin companion `task` prefix and exact Skill helper path

## Passed

- `evals.json` and `trigger-evals.json` parse as JSON.
- Helper script passes `node --check`.
- Helper resolves the installed companion path and fails closed when no Claude session ID is available.
- Simple explanation skips the orchestration Skill and Codex.
- A substantive Skill audit automatically loads `cross-model-orchestration`.
- When child Bash permission is denied, Claude emits a failure report and does not take over.
- Skill-level `allowed-tools` alone does not propagate to `codex:codex-rescue`; user-level permission is required.
- With the exact current Plugin companion permission, one direct `node` command, and a 600000 ms Bash timeout, `codex:codex-rescue` returns a valid `PLAN_REVIEW` without permission denial.
- The sample audit canary produced a read-only `PLAN_REVIEW` and did not modify fixture files.
- A direct agent canary returned `PLAN_REVIEW / 通过` with no permission denials.
- The versioned exact companion `task` permission passed a direct agent canary; broad `Bash(node:*)` is not required.
- No Plugin jobs were left running after the tests.

## Deferred Until Runtime Sync

- Full write, Claude verification, and Codex revision loop on a disposable fixture.
- Git and non-Git full workflow comparison.
- Authentication failure, timeout, and real disagreement injection.
- New-session global trigger check after cc-switch installs the Skill and Claude Code restarts.

These tests remain rollout gates. Do not use the workflow for real write tasks until the read-only post-sync canary passes.
