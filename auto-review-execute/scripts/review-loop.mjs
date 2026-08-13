import fs from "node:fs";
import path from "node:path";

import { atomicWriteFile, atomicWriteJson, nowIso, sha256File, sha256Text, singleLineJson } from "./common.mjs";
import { generateCodexReviewBlock, parseLeadingCodexReviewBlock, removeLeadingCodexReviewBlock } from "./codex-block.mjs";
import { diffFiles } from "./diff-utils.mjs";
import { releaseGlobalRunLock, renewGlobalRunLock } from "./lock.mjs";
import {
  cancelCodexJob,
  launchCodexJob,
  pollCodexJob,
  readCodexResult,
  releaseCodexClaim
} from "./orchestration-adapter.mjs";
import { createInitialState, readState, setErrorState, transitionState, writeState } from "./run-state.mjs";
import {
  assertSnapshotHasNoSymlinks,
  diffSnapshots,
  findOutOfScopeChanges,
  findSymlinkViolations,
  takeSnapshot
} from "./snapshot.mjs";

export function runDirectory(root, runId) {
  return path.join(root, runId);
}

function reviewDirectory(runDir, round) {
  return path.join(runDir, `round-${round}`);
}

function reviewOutputPath(runDir, round) {
  return path.join(reviewDirectory(runDir, round), "codex-output.md");
}

function reviewDiffPath(runDir, round) {
  return path.join(reviewDirectory(runDir, round), "diff.json");
}

function reviewTextPath(runDir, round) {
  return path.join(reviewDirectory(runDir, round), "codex-review-block.txt");
}

function reviewSnapshotPath(runDir, round) {
  return path.join(reviewDirectory(runDir, round), "pre-review-snapshot.json");
}

function failureReportPath(runDir) {
  return path.join(runDir, "CODEX_FAILURE_REPORT.md");
}

function reviewSummaryPath(runDir) {
  return path.join(runDir, "review-summary.md");
}

function renewPersistentLock(state) {
  if (!state.globalLock?.path || !state.globalLock?.ownerToken) return state;
  const renewed = renewGlobalRunLock({
    runId: state.runId,
    ownerToken: state.globalLock.ownerToken,
    path: state.globalLock.path
  });
  return { ...state, globalLock: { ...state.globalLock, leaseExpiresAt: renewed.leaseExpiresAt } };
}

export function buildReviewPrompt(planFile, runDir, round) {
  const contract = {
    identity: "auto-review-execute/writable-plan-audit",
    allowedWrites: [path.resolve(planFile), reviewOutputPath(runDir, round)],
    protocol: [
      "The only mutable plan is planFile, which is the run-local plan-working.md.",
      "Remove an existing leading CODEX-REVIEW block before writing exactly one replacement block.",
      "Audit and directly edit the plan body only when a concrete defect is found.",
      "Copy the final planFile bytes to codexOutput after edits.",
      "Do not modify sourcePlanFile, git state, configuration, or any file outside allowedWrites.",
      "Do not run external, hardware, network, install, git, or system-changing commands.",
      "End with REVIEW_COMPLETE and a one-sentence summary."
    ],
    round,
    planFile: path.resolve(planFile),
    codexOutput: reviewOutputPath(runDir, round),
    generatedAt: nowIso()
  };
  return `标识=auto-review-execute/可写审计；契约=${singleLineJson(contract)}`;
}

function writeFailureReport(runDir, state, message) {
  atomicWriteFile(
    failureReportPath(runDir),
    [
      "# CODEX_FAILURE_REPORT",
      "",
      `runId: ${state.runId}`,
      `state: ${state.state}`,
      `round: ${state.round}`,
      `message: ${message}`,
      `time: ${nowIso()}`
    ].join("\n") + "\n"
  );
}

export function initializeReviewRun({ root, runId, sourcePlanFile, globalLock }) {
  const runDir = runDirectory(root, runId);
  const original = path.join(runDir, "plan-original.md");
  const working = path.join(runDir, "plan-working.md");
  const source = path.resolve(sourcePlanFile);
  const sourceStat = fs.lstatSync(source);
  if (sourceStat.isSymbolicLink() || !sourceStat.isFile()) throw new Error(`CLAUDE_PLAN_FILE must be a regular non-symlink file: ${source}`);
  fs.mkdirSync(runDir, { recursive: false });
  const copyAtomic = (destination) => {
    const temporary = `${destination}.${process.pid}.${Date.now()}.tmp`;
    try {
      fs.copyFileSync(source, temporary, fs.constants.COPYFILE_EXCL);
      fs.renameSync(temporary, destination);
    } finally {
      try {
        if (fs.existsSync(temporary)) fs.unlinkSync(temporary);
      } catch {
        // Preserve the primary copy error; the next trigger can recover the run directory.
      }
    }
  };
  try {
    copyAtomic(original);
    copyAtomic(working);
  } catch (error) {
    fs.rmSync(runDir, { recursive: true, force: true });
    throw error;
  }
  const state = createInitialState({
    runId,
    runDir,
    sourcePlanFile: source,
    planOriginalFile: original,
    planFile: working,
    planFileHash: sha256File(working),
    globalLock
  });
  return writeState(runDir, state);
}

export function launchReview(state, { cwd = process.cwd(), launcher = launchCodexJob } = {}) {
  if (state.state !== "ready_for_review") throw new Error(`Cannot launch review from ${state.state}`);
  const roundDir = reviewDirectory(state.runDir, state.round);
  fs.mkdirSync(roundDir, { recursive: false });
  const prompt = buildReviewPrompt(state.planFile, state.runDir, state.round);
  // The review workspace is intentionally the run-local plan directory, never
  // the source plan directory. orchestration-control requires target roots to
  // be under cwd, so both point to the run directory.
  const reviewCwd = path.resolve(path.dirname(state.planFile));
  transitionState(state.runDir, "ready_for_review", (before) => ({
    ...before,
    state: "launching_review",
    reviewLaunchRequest: {
      cwd: reviewCwd,
      promptSha256: sha256Text(prompt),
      snapshotFile: reviewSnapshotPath(state.runDir, state.round),
      requestedAt: nowIso()
    }
  }));
  // Snapshot only after the state transition has settled. The poller captures
  // artifacts before its next state write, so the diff then contains Codex's
  // plan/output changes rather than this coordinator's state bookkeeping.
  const preLaunchSnapshot = takeSnapshot([reviewCwd]);
  assertSnapshotHasNoSymlinks(preLaunchSnapshot);
  atomicWriteJson(reviewSnapshotPath(state.runDir, state.round), preLaunchSnapshot);
  let launch;
  try {
    launch = launcher({ cwd: reviewCwd, targetRoots: [reviewCwd], prompt });
  } catch (error) {
    writeFailureReport(state.runDir, readState(state.runDir), error.message);
    return setErrorState(state.runDir, error.message, { codexFailureReport: failureReportPath(state.runDir) });
  }
  return transitionState(state.runDir, "launching_review", (before) => ({
    ...before,
    state: "reviewing",
    codexJob: {
      id: launch.jobId,
      ownerToken: launch.ownerToken,
      cwd: reviewCwd,
      companionPath: launch.companionPath || null,
      promptSha256: launch.promptSha256,
      promptBytes: launch.promptBytes,
      launchedAt: nowIso()
    }
  }));
}

function captureReviewArtifacts(state, result) {
  const output = reviewOutputPath(state.runDir, state.round);
  if (!fs.existsSync(output)) {
    // A strict companion completion result is not evidence that it copied the
    // artifact. Preserve the working plan for diagnosis, but make it explicit.
    throw new Error(`Codex completed without required review output: ${output}`);
  }
  const preLaunchSnapshot = JSON.parse(fs.readFileSync(state.reviewLaunchRequest.snapshotFile, "utf8"));
  const postLaunchSnapshot = takeSnapshot([path.dirname(state.planFile)]);
  const rawFilesystemDiff = diffSnapshots(preLaunchSnapshot, postLaunchSnapshot);
  const coordinatorOnly = new Set(["state.json", "run.lock"]);
  const isCoordinatorPath = (entryPath) => coordinatorOnly.has(entryPath) || entryPath.endsWith("/pre-review-snapshot.json");
  const isCoordinatorEntry = (change) => {
    const entry = change.after || change.before;
    return entry && isCoordinatorPath(entry.path);
  };
  const filesystemDiff = {
    added: rawFilesystemDiff.added.filter((entry) => !isCoordinatorPath(entry.path)),
    deleted: rawFilesystemDiff.deleted.filter((entry) => !isCoordinatorPath(entry.path)),
    modified: rawFilesystemDiff.modified.filter((change) => !isCoordinatorEntry(change)),
    symlinkChanges: rawFilesystemDiff.symlinkChanges.filter((change) => !isCoordinatorEntry(change))
  };
  const permittedChanges = [state.planFile, output];
  const outOfScope = findOutOfScopeChanges(filesystemDiff, permittedChanges);
  const links = findSymlinkViolations(filesystemDiff);
  if (outOfScope.length || links.length) {
    throw new Error(`Codex review changed files outside its two-file contract: ${JSON.stringify({ outOfScope, links })}`);
  }
  const workingBytes = fs.readFileSync(state.planFile);
  const outputBytes = fs.readFileSync(output);
  if (!workingBytes.equals(outputBytes)) throw new Error("codex-output.md must byte-match plan-working.md");
  const workingText = workingBytes.toString("utf8");
  const block = parseLeadingCodexReviewBlock(workingText);
  if (!block) throw new Error("Codex completed without a leading CODEX-REVIEW block");
  if (Number(block.fields.round) !== state.round) throw new Error("CODEX-REVIEW block has the wrong round");
  atomicWriteFile(reviewTextPath(state.runDir, state.round), `${block.block}\n`);
  atomicWriteJson(reviewDiffPath(state.runDir, state.round), {
    planDiff: diffFiles(state.planOriginalFile, output),
    reviewFilesystemDiff: filesystemDiff
  });
  atomicWriteFile(path.join(reviewDirectory(state.runDir, state.round), "codex-rendered.md"), `${result.rendered}\n`);
}

/**
 * Called by the Claude session on every polling turn. The hook itself never
 * waits here: it only creates the run and returns, leaving ownership to Claude.
 */
export function pollReview(runDir, {
  poller = pollCodexJob,
  resultReader = readCodexResult,
  releaser = releaseCodexClaim,
  cwd = process.cwd()
} = {}) {
  const state = readState(runDir);
  if (state.state !== "reviewing") return state;
  const job = state.codexJob;
  try {
    renewPersistentLock(state);
    const status = poller({ cwd: job.cwd || cwd, jobId: job.id, companionPath: job.companionPath || undefined });
    if (status.status === "queued" || status.status === "running") return state;
    if (status.status !== "completed") {
      throw new Error(`Codex review ended with ${status.status}`);
    }
    const result = resultReader({ cwd: job.cwd || cwd, jobId: job.id, companionPath: job.companionPath || undefined });
    captureReviewArtifacts(state, result);
    try { releaser({ ownerToken: job.ownerToken, cwd: job.cwd || cwd }); } catch { /* caller will still own persistent lock */ }
    return transitionState(runDir, "reviewing", (before) => ({ ...before, state: "evaluating", reviewedAt: nowIso() }));
  } catch (error) {
    try { releaser({ ownerToken: job.ownerToken, cwd: job.cwd || cwd }); } catch { /* best effort */ }
    writeFailureReport(runDir, state, error.message);
    const errored = setErrorState(runDir, error.message, { codexFailureReport: failureReportPath(runDir) });
    if (errored.globalLock) {
      releaseGlobalRunLock({ runId: errored.runId, ownerToken: errored.globalLock.ownerToken, root: path.dirname(errored.globalLock.path) });
    }
    return errored;
  }
}

export function recordClaudeEvaluation(runDir, {
  decision,
  rationale,
  changes = [],
  adjustedPlanText = null
}) {
  const state = readState(runDir);
  if (state.state !== "evaluating") throw new Error(`Cannot record evaluation from ${state.state}`);
  if (!["agree", "minor", "major", "diverge"].includes(decision)) {
    throw new Error(`Unknown review decision: ${decision}`);
  }
  if (decision === "minor") {
    if (typeof adjustedPlanText !== "string") throw new Error("Minor adjustment requires adjustedPlanText");
    const withoutBlock = removeLeadingCodexReviewBlock(adjustedPlanText);
    const block = generateCodexReviewBlock({
      round: state.round,
      status: "reviewed",
      changes: ["Claude minor adjustment", ...changes],
      reasons: [rationale]
    });
    atomicWriteFile(state.planFile, `${block}\n\n${withoutBlock}`);
    atomicWriteFile(path.join(reviewDirectory(runDir, state.round), "claude-adjusted.md"), fs.readFileSync(state.planFile));
    return transitionState(runDir, "evaluating", (before) => ({ ...before, state: "finalizing", evaluation: { decision, rationale, at: nowIso() } }));
  }
  if (decision === "agree") {
    return transitionState(runDir, "evaluating", (before) => ({ ...before, state: "finalizing", evaluation: { decision, rationale, at: nowIso() } }));
  }
  if (decision === "diverge" || state.round >= state.maxRounds) {
    atomicWriteFile(reviewSummaryPath(runDir), `# Review divergence\n\n${rationale}\n`);
    return transitionState(runDir, "evaluating", (before) => ({ ...before, state: "diverged", evaluation: { decision, rationale, at: nowIso() } }));
  }
  return transitionState(runDir, "evaluating", (before) => ({
    ...before,
    state: "ready_for_review",
    round: before.round + 1,
    evaluation: { decision, rationale, at: nowIso() }
  }));
}

export function finalizeReview(runDir) {
  const state = readState(runDir);
  if (state.state !== "finalizing") throw new Error(`Cannot finalize from ${state.state}`);
  const workingStat = fs.lstatSync(state.planFile);
  if (workingStat.isSymbolicLink() || !workingStat.isFile()) throw new Error("plan-working.md must remain a regular file before finalization");
  const withoutBlock = removeLeadingCodexReviewBlock(fs.readFileSync(state.planFile, "utf8"));
  atomicWriteFile(state.planFile, withoutBlock);
  const finalPath = path.join(runDir, "plan-final.md");
  atomicWriteFile(finalPath, fs.readFileSync(state.planFile));
  const finalText = fs.readFileSync(finalPath, "utf8");
  if (finalText.includes("<!-- CODEX-REVIEW")) throw new Error("finalize left a CODEX-REVIEW block in plan-final.md");
  return transitionState(runDir, "finalizing", (before) => ({
    ...before,
    state: "done_phase1",
    finalPlanFile: finalPath,
    finalPlanSha256: sha256File(finalPath),
    finalizedAt: nowIso()
  }));
}

export function abandonRun(runDir, message, { cancel = cancelCodexJob } = {}) {
  const state = readState(runDir);
  if (state.codexJob?.id && state.state === "reviewing") {
    try { cancel({ cwd: state.codexJob.cwd, jobId: state.codexJob.id, companionPath: state.codexJob.companionPath || undefined }); } catch { /* evidence goes into state */ }
  }
  const errored = setErrorState(runDir, message);
  if (state.globalLock) {
    releaseGlobalRunLock({
      runId: state.runId,
      ownerToken: state.globalLock.ownerToken,
      root: path.dirname(state.globalLock.path)
    });
  }
  return errored;
}

function parseArgs(argv) {
  const [command, ...rest] = argv.slice(2);
  const options = {};
  for (let index = 0; index < rest.length; index += 1) {
    const argument = rest[index];
    if (!argument.startsWith("--")) throw new Error(`Unexpected argument: ${argument}`);
    const key = argument.slice(2);
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
    case "status": result = readState(runDir); break;
    case "launch": result = launchReview(readState(runDir)); break;
    case "poll": result = pollReview(runDir); break;
    case "evaluate": {
      let adjustedPlanText = null;
      if (options["adjusted-plan-file"]) adjustedPlanText = fs.readFileSync(path.resolve(options["adjusted-plan-file"]), "utf8");
      result = recordClaudeEvaluation(runDir, {
        decision: options.decision,
        rationale: options.rationale || "No rationale supplied",
        adjustedPlanText
      });
      break;
    }
    case "finalize": result = finalizeReview(runDir); break;
    case "abort": result = abandonRun(runDir, options.message || "Review abandoned by Claude session"); break;
    default:
      throw new Error("Usage: review-loop.mjs <status|launch|poll|evaluate|finalize|abort> --run-dir <path> [options]");
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
