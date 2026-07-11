# Integration Results - 2026-07-11

## Environment

- Claude Code: 2.1.207
- Plugin: `codex@openai-codex` 1.0.6, enabled
- Codex CLI: 0.144.1, authenticated
- Official stop-time review gate: disabled
- Persistent Claude permissions: exact current Plugin companion `task` prefix, exact Skill helper path, and exact read access to the Skill directories

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

## Post-Sync Findings

- CC Switch installed the Skill and enabled both Claude and Codex; source, CC Switch, Claude, and Codex runtime hashes match.
- A clean new Claude session automatically loaded the global Skill and read `workflow-contract.md` without falling back to a project copy.
- The first clean post-sync canary stopped before Codex because Claude expanded the helper to a Windows backslash path while the exact permission only matched the forward-slash form. Fixture hashes stayed unchanged. The Skill now requires a resolved forward-slash helper path and forbids PowerShell/settings fallbacks; both exact Windows path forms are covered by user permissions before retest.
- A second clean canary reached `codex:codex-rescue` but the legacy exact companion rule ending in `task:*` did not match a command with a multiline task argument. Claude emitted `CODEX_FAILURE_REPORT`, paused, and did not take over.
- The exact wildcard form `Bash(node "<companionPath>" task *)` passed a direct-agent canary. Codex thread `019f50c9-f49e-7002-91c8-2792b256e31b` returned `PERMISSION_CANARY_OK` without file access.
- A clean full-workflow retest used the synced Skill and passed helper resolution, but the long PLAN_REVIEW task contained literal newlines; Claude Code denied the otherwise exact `task *` rule. Claude paused with a failure report and did not take over. The workflow now serializes plan review, execution, and revision prompts as one-line XML/semicolon arguments with no literal CR/LF.

## Deferred Until Runtime Sync

- Full write, Claude verification, and Codex revision loop on a disposable fixture.
- Git and non-Git full workflow comparison.
- Authentication failure, timeout, and real disagreement injection.
- Successful new-session global trigger through helper, Codex plan review, read-only execution, and Claude verification after the Windows path fix.

These tests remain rollout gates. Do not use the workflow for real write tasks until the read-only post-sync canary passes.
