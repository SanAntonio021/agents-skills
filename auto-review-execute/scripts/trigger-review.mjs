#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";

import { atomicWriteFile, dataRoot, ensureDirectory, makeRunId, nowIso, readJson } from "./common.mjs";
import { acquireGlobalRunLock, ActiveRunError, releaseGlobalRunLock } from "./lock.mjs";
import { cancelCodexJob } from "./orchestration-adapter.mjs";
import { initializeReviewRun } from "./review-loop.mjs";
import { statePath } from "./run-state.mjs";

function writeTriggerError(root, message) {
  ensureDirectory(root);
  atomicWriteFile(path.join(root, "trigger-errors.log"), `[${nowIso()}] ${message}\n`);
}

function cancelExpiredCodexJob(expired, root) {
  try {
    const stale = readJson(expired.stateFile);
    if (!stale?.codexJob?.id || !stale?.codexJob?.cwd) return;
    cancelCodexJob({
      cwd: stale.codexJob.cwd,
      jobId: stale.codexJob.id,
      companionPath: stale.codexJob.companionPath || undefined
    });
    writeTriggerError(root, `Cancelled expired Codex job ${stale.codexJob.id} from run ${expired.runId} before takeover.`);
  } catch (error) {
    // Refuse admission when stale work cannot be cancelled. The trigger never
    // starts a replacement that could race an unknown old writer.
    throw new Error(`Expired run ${expired.runId} could not be safely cancelled: ${error.message}`);
  }
}

function main() {
  process.env.AUTO_REVIEW_EXECUTE = "1";
  const root = dataRoot();
  const planFile = process.env.CLAUDE_PLAN_FILE;
  // Do not guess from recent Markdown files. A wrong plan is worse than a
  // skipped automated review, and Claude can explicitly provide this variable.
  if (!planFile) {
    writeTriggerError(root, "CLAUDE_PLAN_FILE is not set; review was not started.");
    process.stdout.write(JSON.stringify({ ok: false, state: "not_started", reason: "CLAUDE_PLAN_FILE is not set" }) + "\n");
    return;
  }
  const absolutePlan = path.resolve(planFile);
  let stat;
  try {
    stat = fs.lstatSync(absolutePlan);
  } catch {
    writeTriggerError(root, `CLAUDE_PLAN_FILE does not exist: ${absolutePlan}`);
    process.stdout.write(JSON.stringify({ ok: false, state: "not_started", reason: "plan file does not exist" }) + "\n");
    return;
  }
  if (stat.isSymbolicLink() || !stat.isFile()) {
    writeTriggerError(root, `CLAUDE_PLAN_FILE is not a regular non-symlink file: ${absolutePlan}`);
    process.stdout.write(JSON.stringify({ ok: false, state: "not_started", reason: "plan file is not regular" }) + "\n");
    return;
  }

  const runId = makeRunId();
  const runDir = path.join(root, runId);
  let lock;
  try {
    lock = acquireGlobalRunLock({
      runId,
      stateFile: statePath(runDir),
      root,
      onExpired: (expired) => cancelExpiredCodexJob(expired, root)
    });
    const state = initializeReviewRun({ root, runId, sourcePlanFile: absolutePlan, globalLock: lock });
    // The hook has completed its sole job. Claude's session polls this state;
    // it deliberately does not launch or wait for a Codex background task.
    process.stdout.write(JSON.stringify({ ok: true, runId, stateFile: statePath(state.runDir), state: state.state }) + "\n");
  } catch (error) {
    if (error instanceof ActiveRunError) {
      process.stdout.write(JSON.stringify({ ok: false, state: "already_active", runId: error.lock.runId }) + "\n");
      return;
    }
    if (lock) {
      releaseGlobalRunLock({ runId, ownerToken: lock.ownerToken, root });
    }
    writeTriggerError(root, error.message);
    process.stderr.write(`${error.message}\n`);
    process.exitCode = 1;
  }
}

main();
