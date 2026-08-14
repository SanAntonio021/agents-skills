#!/usr/bin/env node
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

import {
  assertNoSymlinkSegments,
  assertRegularFile,
  atomicWriteFile,
  atomicWriteJson,
  commonAncestor,
  isSameOrDescendant,
  nowIso,
  sha256File,
  sha256Text,
  singleLineJson
} from "./common.mjs";
import { releaseGlobalRunLock, renewGlobalRunLock } from "./lock.mjs";
import {
  assertReadOnlyVerifyCommand,
  classifyReadOnlyVerifyCommand,
  readPlanMetadata,
  validatePlanMetadata
} from "./plan-metadata.mjs";
import {
  cancelCodexJob,
  launchCodexJob,
  pollCodexJob,
  readCodexResult,
  releaseCodexClaim,
  approvePeerSync
} from "./orchestration-adapter.mjs";
import { readState, setErrorState, transitionState, writeState } from "./run-state.mjs";
import {
  assertSnapshotHasNoSymlinks,
  diffSnapshots,
  findOutOfScopeChanges,
  findSymlinkViolations,
  takeSnapshot
} from "./snapshot.mjs";

function snapshotPath(runDir) {
  return path.join(runDir, "pre-execute-snapshot.json");
}

function validationPath(runDir, attempt) {
  return path.join(runDir, `validation-attempt-${attempt}.json`);
}

function executionDirectory(runDir, attempt) {
  return attempt > 0 ? path.join(runDir, `rework-attempt-${attempt}`) : path.join(runDir, "execution");
}

function renderedOutputPath(runDir, attempt) {
  return path.join(executionDirectory(runDir, attempt), "codex-rendered.md");
}

function currentPlanHash(state) {
  assertRegularFile(state.finalPlanFile, "plan-final.md");
  return sha256File(state.finalPlanFile);
}

function invalidAuthorization(runDir, message) {
  return transitionState(runDir, "awaiting_execution_confirmation", (before) => ({
    ...before,
    state: "awaiting_user",
    executionAuthorizationInvalidated: { message, at: nowIso() }
  }));
}

function safeConfirmationActor(actor) {
  if (typeof actor !== "string" || !actor.trim()) throw new Error("confirmedBy is required to record user confirmation");
  return actor.replace(/[\r\n]+/g, " ").trim();
}

/**
 * This is called only after Claude has shown plan-final.md and received an
 * affirmative answer. The recorded hash binds that exact reviewed plan to the
 * later execution attempt.
 */
export function recordExecutionConfirmation(runDir, { confirmedBy, note = "" }) {
  const state = readState(runDir);
  if (state.state !== "done_phase1") throw new Error(`Cannot record execution confirmation from ${state.state}`);
  const hash = currentPlanHash(state);
  return transitionState(runDir, "done_phase1", (before) => ({
    ...before,
    state: "awaiting_execution_confirmation",
    executionAuthorization: {
      confirmedBy: safeConfirmationActor(confirmedBy),
      note: String(note).replace(/[\r\n]+/g, " ").trim(),
      confirmedAt: nowIso(),
      planFinalSha256: hash
    }
  }));
}

function extractVerifyPath(command) {
  const match = /^(?:Test-Path|Get-Content)(?:\s+-LiteralPath)?\s+(.+)$/i.exec(command.trim());
  if (!match) return null;
  const candidate = match[1].trim();
  if ((candidate.startsWith('"') && candidate.endsWith('"')) || (candidate.startsWith("'") && candidate.endsWith("'"))) {
    return candidate.slice(1, -1);
  }
  return candidate;
}

function validateVerifyReadScope(command, { cwd, targetRoots }) {
  const type = assertReadOnlyVerifyCommand(command);
  if (type === "node --version") return type;
  const requested = extractVerifyPath(command);
  if (!requested || /[*?\[\]]/.test(requested)) {
    throw new Error(`verifyCommand must name one concrete project path without wildcards: ${command}`);
  }
  const resolved = path.resolve(cwd, requested);
  const root = targetRoots.find((targetRoot) => isSameOrDescendant(resolved, targetRoot));
  if (!root) throw new Error(`verifyCommand reads outside targetRoots: ${command}`);
  if (fs.existsSync(resolved)) assertNoSymlinkSegments(resolved, root);
  return type;
}

export function runReadOnlyVerifyCommand(command, { cwd, targetRoots }) {
  const type = validateVerifyReadScope(command, { cwd, targetRoots });
  let child;
  if (type === "node --version") {
    child = spawnSync(process.execPath, ["--version"], {
      cwd,
      encoding: "utf8",
      shell: false,
      windowsHide: true,
      env: process.env
    });
  } else {
    child = spawnSync("powershell.exe", ["-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", command], {
      cwd,
      encoding: "utf8",
      shell: false,
      windowsHide: true,
      env: { ...process.env, OutputEncoding: "utf-8" }
    });
  }
  return {
    command,
    commandType: type,
    exitCode: child.status ?? -1,
    output: `${child.stdout || ""}${child.stderr || ""}`.trim(),
    error: child.error?.message || null
  };
}

export function buildExecutionPrompt({ state, metadata }) {
  const planText = fs.readFileSync(state.finalPlanFile, "utf8");
  const contract = {
    identity: "auto-review-execute/execute",
    planFinalSha256: state.executionAuthorization.planFinalSha256,
    allowedPaths: metadata.allowedPaths,
    targetRoots: metadata.targetRoots,
    acceptanceCriteria: metadata.acceptanceCriteria.map((criterion) => ({ id: criterion.id, description: criterion.description })),
    highRiskStop: [
      "Any write outside allowedPaths",
      "Paid service, external API, hardware or instrument action",
      "A material plan error or an unplanned key decision"
    ],
    completionReport: "List modified files, command exit codes, acceptance IDs with output summaries, failed criteria and remaining issues.",
    planText
  };
  return `标识=auto-review-execute/执行；契约=${singleLineJson(contract)}`;
}

function releasePersistentLock(state) {
  if (!state.globalLock?.ownerToken || !state.globalLock?.path) return false;
  return releaseGlobalRunLock({
    runId: state.runId,
    ownerToken: state.globalLock.ownerToken,
    root: path.dirname(state.globalLock.path)
  });
}

function failCodexRun(runDir, state, message, releaser = releaseCodexClaim) {
  try {
    if (state.codexJob?.ownerToken) releaser({ ownerToken: state.codexJob.ownerToken, cwd: state.codexJob.cwd });
  } catch {
    // State still retains evidence of the failure.
  }
  const errored = setErrorState(runDir, message);
  releasePersistentLock(errored);
  return errored;
}

function verifyAuthorization(state, runDir) {
  const authorization = state.executionAuthorization;
  if (!authorization?.planFinalSha256) throw new Error("Execution has no recorded user confirmation hash");
  const currentHash = currentPlanHash(state);
  if (currentHash !== authorization.planFinalSha256) {
    return invalidAuthorization(
      runDir,
      `plan-final.md SHA-256 changed after user confirmation (confirmed ${authorization.planFinalSha256}, current ${currentHash})`
    );
  }
  return null;
}

export function startExecution(runDir, { cwd = null, launcher = launchCodexJob } = {}) {
  const state = readState(runDir);
  if (state.state !== "awaiting_execution_confirmation") {
    throw new Error(`Cannot start execution from ${state.state}`);
  }
  const invalid = verifyAuthorization(state, runDir);
  if (invalid) return invalid;

  let metadata;
  try {
    const rawMetadata = readPlanMetadata(state.finalPlanFile);
    const requestedCwd = cwd ? path.resolve(cwd) : commonAncestor(rawMetadata.targetRoots);
    metadata = validatePlanMetadata(rawMetadata, { cwd: requestedCwd, requireExistingRoots: true });
    const snapshot = takeSnapshot(metadata.targetRoots);
    assertSnapshotHasNoSymlinks(snapshot);
    atomicWriteJson(snapshotPath(runDir), snapshot);
  } catch (error) {
    return invalidAuthorization(runDir, `Execution preflight failed: ${error.message}`);
  }

  const prompt = buildExecutionPrompt({ state, metadata });
  const beforeLaunch = transitionState(runDir, "awaiting_execution_confirmation", (previous) => ({
      ...previous,
      state: "executing",
      execution: {
      cwd: metadata.targetRoots.length ? (cwd ? path.resolve(cwd) : commonAncestor(metadata.targetRoots)) : path.resolve(cwd || process.cwd()),
      targetRoots: metadata.targetRoots,
      allowedPaths: metadata.allowedPaths,
      acceptanceCriteria: metadata.acceptanceCriteria,
      snapshotFile: snapshotPath(runDir),
      startedAt: nowIso(),
      promptSha256: sha256Text(prompt)
    }
  }));
  try {
    const executionCwd = beforeLaunch.execution.cwd;
    const launched = launcher({
      cwd: executionCwd,
      targetRoots: metadata.targetRoots,
      allowedPaths: metadata.allowedPaths,
      prompt,
      operation: "task",
      artifactId: `auto-review-execute:${state.runId}`,
      artifactType: "deliverable",
      round: 1,
      artifactPath: state.finalPlanFile,
      acceptanceCriteria: metadata.acceptanceCriteria.map((criterion) => criterion.description)
    });
    return transitionState(runDir, "executing", (previous) => ({
      ...previous,
      codexJob: {
        id: launched.jobId,
        ownerToken: launched.ownerToken,
        cwd: executionCwd,
        companionPath: launched.companionPath || null,
        kind: "execution",
        launchedAt: nowIso()
      }
    }));
  } catch (error) {
    return failCodexRun(runDir, beforeLaunch, error.message);
  }
}

export function pollExecution(runDir, {
  poller = pollCodexJob,
  resultReader = readCodexResult,
  releaser = releaseCodexClaim
} = {}) {
  const state = readState(runDir);
  if (state.state !== "executing" && state.state !== "reworking") return state;
  if (!state.codexJob?.id) {
    return failCodexRun(runDir, state, "Execution state has no Codex job id", releaser);
  }
  try {
    if (state.globalLock?.path && state.globalLock?.ownerToken) {
      renewGlobalRunLock({ runId: state.runId, ownerToken: state.globalLock.ownerToken, path: state.globalLock.path });
    }
    const status = poller({
      cwd: state.codexJob.cwd,
      jobId: state.codexJob.id,
      companionPath: state.codexJob.companionPath || undefined
    });
    if (status.status === "queued" || status.status === "running") return state;
    if (status.status === "needs_attention") {
      const result = resultReader({
        cwd: state.codexJob.cwd,
        jobId: state.codexJob.id,
        companionPath: state.codexJob.companionPath || undefined
      });
      try { releaser({ ownerToken: state.codexJob.ownerToken, cwd: state.codexJob.cwd }); } catch { /* bridge owns the durable lock */ }
      return transitionState(runDir, ["executing", "reworking"], (previous) => ({
        ...previous,
        state: "awaiting_user",
        peerSync: {
          jobId: state.codexJob.id,
          syncStatus: status.sync_status || "awaiting_user",
          pendingHighRisk: status.pending_high_risk || result.job?.pending_high_risk || [],
          result: result.job || null,
          resumeState: state.state,
          recordedAt: nowIso()
        },
        codexJob: null
      }));
    }
    if (status.status !== "completed") return failCodexRun(runDir, state, `Codex ${state.codexJob.kind} ended with ${status.status}`, releaser);
    const result = resultReader({
      cwd: state.codexJob.cwd,
      jobId: state.codexJob.id,
      companionPath: state.codexJob.companionPath || undefined
    });
    const attempt = state.reworkAttempts || 0;
    fs.mkdirSync(executionDirectory(runDir, attempt), { recursive: true });
    atomicWriteFile(renderedOutputPath(runDir, attempt), `${result.rendered}\n`);
    try { releaser({ ownerToken: state.codexJob.ownerToken, cwd: state.codexJob.cwd }); } catch { /* claim expiry remains independently recoverable */ }
    return transitionState(runDir, ["executing", "reworking"], (previous) => ({
      ...previous,
      state: "validating",
      codexJob: null,
      lastCodexResult: { attempt, renderedFile: renderedOutputPath(runDir, attempt), completedAt: nowIso() }
    }));
  } catch (error) {
    return failCodexRun(runDir, state, error.message, releaser);
  }
}

/** Synchronize an explicitly approved high-risk result without another model turn. */
export function approveExecutionSync(runDir, approvedChangeIds, { approver = approvePeerSync } = {}) {
  const state = readState(runDir);
  if (state.state !== "awaiting_user" || !state.peerSync?.jobId) {
    throw new Error(`No peer synchronization is awaiting approval in ${state.state}`);
  }
  const expected = (state.peerSync.pendingHighRisk || []).map((change) => change.id).sort();
  const supplied = [...new Set(approvedChangeIds || [])].sort();
  if (expected.length !== supplied.length || expected.some((id, index) => id !== supplied[index])) {
    throw new Error("approvedChangeIds must exactly match pendingHighRisk IDs");
  }
  const synced = approver({
    cwd: state.execution?.cwd || process.cwd(),
    jobId: state.peerSync.jobId,
    approvedChangeIds: supplied
  });
  return transitionState(runDir, "awaiting_user", (before) => ({
    ...before,
    state: "validating",
    peerSync: { ...before.peerSync, approvedChangeIds: supplied, syncResult: synced, approvedAt: nowIso() }
  }));
}

export function validateExecution(runDir, { cwd = null } = {}) {
  const state = readState(runDir);
  if (state.state !== "validating") throw new Error(`Cannot validate execution from ${state.state}`);
  const execution = state.execution;
  const verifyCwd = cwd ? path.resolve(cwd) : path.resolve(execution.cwd);
  const before = JSON.parse(fs.readFileSync(execution.snapshotFile, "utf8"));
  const current = takeSnapshot(execution.targetRoots);
  const fileDiff = diffSnapshots(before, current);
  const outOfScope = findOutOfScopeChanges(fileDiff, execution.allowedPaths);
  const symlinkViolations = findSymlinkViolations(fileDiff);
  const results = [];
  results.push({
    id: "scope-check",
    passed: outOfScope.length === 0 && symlinkViolations.length === 0,
    outOfScope,
    symlinkViolations
  });
  for (const criterion of execution.acceptanceCriteria) {
    let executionResult;
    try {
      executionResult = runReadOnlyVerifyCommand(criterion.verifyCommand, { cwd: verifyCwd, targetRoots: execution.targetRoots });
    } catch (error) {
      executionResult = {
        command: criterion.verifyCommand,
        commandType: classifyReadOnlyVerifyCommand(criterion.verifyCommand),
        exitCode: -1,
        output: error.message,
        error: error.message
      };
    }
    results.push({
      id: criterion.id,
      description: criterion.description,
      expectedOutput: criterion.expectedOutput,
      ...executionResult,
      passed: executionResult.exitCode === 0 && executionResult.output.includes(criterion.expectedOutput)
    });
  }
  const report = {
    schemaVersion: 1,
    validatedAt: nowIso(),
    allPassed: results.every((result) => result.passed),
    results,
    fileDiff
  };
  atomicWriteJson(validationPath(runDir, state.reworkAttempts || 0), report);
  if (report.allPassed) {
    const done = transitionState(runDir, "validating", (beforeState) => ({
      ...beforeState,
      state: "done",
      validation: { passed: true, reportFile: validationPath(runDir, beforeState.reworkAttempts || 0), completedAt: nowIso() }
    }));
    releasePersistentLock(done);
    return done;
  }
  if ((state.reworkAttempts || 0) >= 2) {
    return transitionState(runDir, "validating", (beforeState) => ({
      ...beforeState,
      state: "awaiting_user",
      validation: { passed: false, reportFile: validationPath(runDir, beforeState.reworkAttempts || 0), exhaustedAt: nowIso() }
    }));
  }
  return transitionState(runDir, "validating", (beforeState) => ({
    ...beforeState,
    state: "reworking",
    validation: { passed: false, reportFile: validationPath(runDir, beforeState.reworkAttempts || 0), failedAt: nowIso() },
    reworkReady: true
  }));
}

export function launchRework(runDir, { cwd = null, launcher = launchCodexJob } = {}) {
  const state = readState(runDir);
  if (state.state !== "reworking" || !state.reworkReady) throw new Error(`Cannot launch rework from ${state.state}`);
  const attempt = (state.reworkAttempts || 0) + 1;
  if (attempt > 2) throw new Error("Rework limit is exhausted");
  const failedValidation = JSON.parse(fs.readFileSync(state.validation.reportFile, "utf8"));
  const prompt = `标识=auto-review-execute/返工；契约=${singleLineJson({
    attempt,
    allowedPaths: state.execution.allowedPaths,
    targetRoots: state.execution.targetRoots,
    failures: failedValidation.results.filter((result) => !result.passed),
    passCondition: "Correct only the reported failures inside allowedPaths; do not change scope or acceptance metadata."
  })}`;
  fs.mkdirSync(executionDirectory(runDir, attempt), { recursive: false });
  const preparing = transitionState(runDir, "reworking", (before) => ({
    ...before,
    reworkAttempts: attempt,
    reworkReady: false,
    reworkStartedAt: nowIso()
  }));
  try {
    const executionCwd = cwd ? path.resolve(cwd) : path.resolve(preparing.execution.cwd);
    const launched = launcher({
      cwd: executionCwd,
      targetRoots: preparing.execution.targetRoots,
      allowedPaths: preparing.execution.allowedPaths,
      prompt,
      operation: "task",
      artifactId: `auto-review-execute:${preparing.runId}`,
      artifactType: "deliverable",
      round: 1,
      artifactPath: preparing.finalPlanFile,
      acceptanceCriteria: preparing.execution.acceptanceCriteria.map((criterion) => criterion.description)
    });
    return transitionState(runDir, "reworking", (before) => ({
      ...before,
      codexJob: {
        id: launched.jobId,
        ownerToken: launched.ownerToken,
        cwd: executionCwd,
        companionPath: launched.companionPath || null,
        kind: "rework",
        launchedAt: nowIso()
      }
    }));
  } catch (error) {
    return failCodexRun(runDir, preparing, error.message);
  }
}

export function abortExecution(runDir, message, { cancel = cancelCodexJob } = {}) {
  const state = readState(runDir);
  if (state.codexJob?.id && ["executing", "reworking"].includes(state.state)) {
    try { cancel({ cwd: state.codexJob.cwd, jobId: state.codexJob.id, companionPath: state.codexJob.companionPath || undefined }); } catch { /* retained in final state */ }
  }
  return failCodexRun(runDir, state, message);
}

function parseArgs(argv) {
  const [command, ...rest] = argv.slice(2);
  const options = {};
  for (let index = 0; index < rest.length; index += 1) {
    const arg = rest[index];
    if (!arg.startsWith("--")) throw new Error(`Unexpected argument: ${arg}`);
    const key = arg.slice(2);
    const value = rest[index + 1];
    if (value == null || value.startsWith("--")) throw new Error(`Missing value for --${key}`);
    options[key] = value;
    index += 1;
  }
  return { command, options };
}

function cli() {
  const { command, options } = parseArgs(process.argv);
  if (!options["run-dir"]) throw new Error("--run-dir is required");
  const runDir = path.resolve(options["run-dir"]);
  let result;
  switch (command) {
    case "confirm":
      result = recordExecutionConfirmation(runDir, { confirmedBy: options["confirmed-by"], note: options.note || "" });
      break;
    case "start": result = startExecution(runDir, { cwd: options.cwd || null }); break;
    case "poll": result = pollExecution(runDir); break;
    case "validate": result = validateExecution(runDir, { cwd: options.cwd || null }); break;
    case "rework": result = launchRework(runDir, { cwd: options.cwd || null }); break;
    case "abort": result = abortExecution(runDir, options.message || "Execution aborted by Claude session"); break;
    case "status": result = readState(runDir); break;
    default: throw new Error("Usage: execute-plan.mjs <confirm|start|poll|validate|rework|abort|status> --run-dir <path> [options]");
  }
  process.stdout.write(`${JSON.stringify(result, null, 2)}\n`);
}

const isMain = process.argv[1] && path.resolve(process.argv[1]) === path.resolve(new URL(import.meta.url).pathname.replace(/^\/([A-Z]:)/, "$1"));
if (isMain) {
  try {
    cli();
  } catch (error) {
    process.stderr.write(`${error.message}\n`);
    process.exitCode = 1;
  }
}
