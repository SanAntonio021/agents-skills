import fs from "node:fs";
import path from "node:path";

import { atomicWriteJson, nowIso, readJson } from "./common.mjs";
import { withRunMutex } from "./lock.mjs";

export const STATES = new Set([
  "initializing",
  "ready_for_review",
  "launching_review",
  "reviewing",
  "evaluating",
  "minor_adjusting",
  "major_adjusting",
  "finalizing",
  "done_phase1",
  "awaiting_execution_confirmation",
  "executing",
  "validating",
  "reworking",
  "awaiting_user",
  "diverged",
  "done",
  "error"
]);

export function statePath(runDir) {
  return path.join(runDir, "state.json");
}

export function readState(runDir) {
  const file = statePath(runDir);
  if (!fs.existsSync(file)) throw new Error(`state.json does not exist: ${file}`);
  const state = readJson(file);
  if (!state || typeof state !== "object" || !STATES.has(state.state)) {
    throw new Error(`state.json is invalid or has an unknown state: ${file}`);
  }
  if (!state.runId || !state.runDir || !state.planFile) {
    throw new Error(`state.json is missing run identity fields: ${file}`);
  }
  return state;
}

export function writeState(runDir, state) {
  if (!STATES.has(state.state)) throw new Error(`Cannot write unknown workflow state: ${state.state}`);
  const updated = { ...state, updatedAt: nowIso() };
  atomicWriteJson(statePath(runDir), updated);
  return updated;
}

export function createInitialState({ runId, runDir, sourcePlanFile, planOriginalFile, planFile, planFileHash, globalLock }) {
  return {
    schemaVersion: 1,
    runId,
    runDir: path.resolve(runDir),
    sourcePlanFile: path.resolve(sourcePlanFile),
    planOriginalFile: path.resolve(planOriginalFile),
    // planFile is deliberately the only mutable plan. It is never synced back
    // to sourcePlanFile during audit rounds.
    planFile: path.resolve(planFile),
    planFileHash,
    autoReviewExecute: true,
    state: "ready_for_review",
    round: 1,
    maxRounds: 3,
    reworkAttempts: 0,
    globalLock: {
      ownerToken: globalLock.ownerToken,
      path: globalLock.path,
      leaseExpiresAt: globalLock.leaseExpiresAt
    },
    createdAt: nowIso(),
    updatedAt: nowIso()
  };
}

/** Atomically read, validate the predecessor state, and persist a transition. */
export function transitionState(runDir, expectedStates, transition) {
  const expected = new Set(Array.isArray(expectedStates) ? expectedStates : [expectedStates]);
  return withRunMutex(runDir, () => {
    const before = readState(runDir);
    if (!expected.has(before.state)) {
      throw new Error(`Invalid state transition: expected ${[...expected].join(" or ")}, found ${before.state}`);
    }
    const after = transition({ ...before });
    if (!after || typeof after !== "object") throw new Error("State transition must return an object");
    return writeState(runDir, after);
  });
}

export function setErrorState(runDir, message, extra = {}) {
  return withRunMutex(runDir, () => {
    const before = readState(runDir);
    return writeState(runDir, {
      ...before,
      ...extra,
      state: "error",
      error: { message, at: nowIso() }
    });
  });
}
