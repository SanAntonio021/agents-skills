import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import { sha256File } from "../scripts/common.mjs";
import { generateCodexReviewBlock, removeLeadingCodexReviewBlock, parseLeadingCodexReviewBlock } from "../scripts/codex-block.mjs";
import { acquireGlobalRunLock, ActiveRunError, releaseGlobalRunLock } from "../scripts/lock.mjs";
import { parsePlanMetadata, validatePlanMetadata, classifyReadOnlyVerifyCommand } from "../scripts/plan-metadata.mjs";
import { diffSnapshots, findOutOfScopeChanges, findSymlinkViolations, takeSnapshot } from "../scripts/snapshot.mjs";
import { initializeReviewRun, launchReview, pollReview, recordClaudeEvaluation, finalizeReview } from "../scripts/review-loop.mjs";
import { readState } from "../scripts/run-state.mjs";
import {
  pollExecution,
  recordExecutionConfirmation,
  runReadOnlyVerifyCommand,
  startExecution,
  validateExecution
} from "../scripts/execute-plan.mjs";

function tempDir(prefix = "auto-review-test-") {
  return fs.mkdtempSync(path.join(os.tmpdir(), prefix));
}

function writePlan(filePath, body = "# Plan\n") {
  fs.writeFileSync(filePath, body, "utf8");
}

function validMetadata() {
  return {
    targetRoots: [tempDir("target-")],
    allowedPaths: [],
    acceptanceCriteria: []
  };
}

test("trigger contract rejects missing CLAUDE_PLAN_FILE without guessing recent markdown", () => {
  const root = tempDir();
  const recent = path.join(root, "newest.md");
  writePlan(recent);
  const testEnv = { ...process.env, AUTO_REVIEW_EXECUTE_HOME: root };
  delete testEnv.CLAUDE_PLAN_FILE;
  const result = spawnSync(process.execPath, [
    path.resolve(new URL("../scripts/trigger-review.mjs", import.meta.url).pathname.replace(/^\/([A-Z]:)/, "$1"))
  ], { cwd: root, env: testEnv, encoding: "utf8" });
  assert.equal(result.status, 0);
  assert.match(result.stdout, /CLAUDE_PLAN_FILE is not set/);
  assert.equal(fs.existsSync(path.join(root, "global.lock")), false);
});

test("global lock rejects active run and can take over an expired run only after callback", () => {
  const root = tempDir();
  const first = acquireGlobalRunLock({ runId: "run-one", stateFile: path.join(root, "one", "state.json"), root, leaseMs: 60_000 });
  assert.throws(
    () => acquireGlobalRunLock({ runId: "run-two", stateFile: path.join(root, "two", "state.json"), root, leaseMs: 60_000 }),
    ActiveRunError
  );
  fs.writeFileSync(path.join(root, "global.lock"), JSON.stringify({ runId: "run-one", stateFile: path.join(root, "one", "state.json"), leaseExpiresAt: new Date(Date.now() - 1000).toISOString() }));
  let callbackValue = null;
  const second = acquireGlobalRunLock({
    runId: "run-two",
    stateFile: path.join(root, "two", "state.json"),
    root,
    onExpired: (old) => { callbackValue = old.runId; }
  });
  assert.equal(callbackValue, "run-one");
  assert.equal(second.runId, "run-two");
  releaseGlobalRunLock(second);
  releaseGlobalRunLock(first);
});

test("CODEX-REVIEW is singular, leading, parseable, and removable", () => {
  const block = generateCodexReviewBlock({ round: 2, changes: ["Fix order"], reasons: ["Dependency was reversed"] });
  const text = `${block}\n\n# Body\n`;
  const parsed = parseLeadingCodexReviewBlock(text);
  assert.equal(parsed.fields.round, "2");
  assert.equal(parsed.fields.status, "reviewed");
  assert.equal(removeLeadingCodexReviewBlock(text), "# Body\n");
});

test("front matter and verifyCommand validation enforce read-only criteria", () => {
  const root = tempDir();
  const metadata = parsePlanMetadata(`---\nauto-review-execute:\n  targetRoots:\n    - "${root.replaceAll("\\", "\\\\")}"\n  allowedPaths:\n    - "${root.replaceAll("\\", "\\\\")}\\src"\n  acceptanceCriteria:\n    - id: ac-1\n      description: "source exists"\n      verifyCommand: "Test-Path src/index.js"\n      expectedOutput: "True"\n---\n# Plan\n`);
  assert.equal(classifyReadOnlyVerifyCommand("Test-Path src/index.js"), "Test-Path");
  assert.equal(classifyReadOnlyVerifyCommand('Test-Path "src/index.js"'), "Test-Path");
  assert.equal(classifyReadOnlyVerifyCommand("Test-Path src/index.js -or Test-Path other.js"), null);
  assert.equal(classifyReadOnlyVerifyCommand("npm test"), null);
  assert.throws(() => validatePlanMetadata({ ...metadata, acceptanceCriteria: [{ ...metadata.acceptanceCriteria[0], verifyCommand: "npm test" }] }, { cwd: root }), /read-only allowlist/);
});

test("verify execution requires both exitCode zero and expected output", () => {
  const root = tempDir();
  const marker = path.join(root, "marker.txt");
  fs.writeFileSync(marker, "expected\n", "utf8");
  const result = runReadOnlyVerifyCommand("Get-Content marker.txt", { cwd: root, targetRoots: [root] });
  assert.equal(result.exitCode, 0);
  assert.match(result.output, /expected/);
  const missing = runReadOnlyVerifyCommand("Test-Path missing.txt", { cwd: root, targetRoots: [root] });
  assert.equal(missing.exitCode, 0);
  assert.match(missing.output, /False/);
});

test("snapshot diff detects additions, deletions, renames, and symlink changes", () => {
  const root = tempDir();
  const oldFile = path.join(root, "old.txt");
  fs.writeFileSync(oldFile, "old", "utf8");
  const before = takeSnapshot([root]);
  fs.renameSync(oldFile, path.join(root, "new.txt"));
  const external = tempDir();
  fs.writeFileSync(path.join(external, "escape.txt"), "escape", "utf8");
  fs.symlinkSync(path.join(external, "escape.txt"), path.join(root, "escape-link"), "file");
  const after = takeSnapshot([root]);
  const diff = diffSnapshots(before, after);
  assert.ok(diff.added.some((entry) => entry.path === "new.txt"));
  assert.ok(diff.deleted.some((entry) => entry.path === "old.txt"));
  assert.ok(diff.renamed.some((entry) => entry.before.path === "old.txt" && entry.after.path === "new.txt"));
  assert.ok(findSymlinkViolations(diff).length > 0);
  assert.ok(findOutOfScopeChanges(diff, [path.join(root, "new.txt")]).length > 0);
});

test("review hook state is resumable and uses plan-working.md as planFile", () => {
  const root = tempDir();
  const source = path.join(root, "source-plan.md");
  writePlan(source, "# Original\n");
  const globalLock = acquireGlobalRunLock({ runId: "run-review", stateFile: path.join(root, "run-review", "state.json"), root });
  const state = initializeReviewRun({ root, runId: "run-review", sourcePlanFile: source, globalLock });
  assert.equal(path.basename(state.planFile), "plan-working.md");
  assert.equal(fs.readFileSync(state.planFile, "utf8"), fs.readFileSync(source, "utf8"));
  const launched = launchReview(state, {
    launcher: ({ cwd, targetRoots, prompt }) => {
      assert.equal(path.dirname(state.planFile), cwd);
      assert.deepEqual(targetRoots, [cwd]);
      const block = generateCodexReviewBlock({ round: 1, changes: ["None"], reasons: ["Checked"] });
      fs.writeFileSync(state.planFile, `${block}\n\n# Original\n`, "utf8");
      fs.writeFileSync(path.join(state.runDir, "round-1", "codex-output.md"), fs.readFileSync(state.planFile));
      return { jobId: "review-job", ownerToken: "review-owner", promptSha256: "x", promptBytes: Buffer.byteLength(prompt) };
    }
  });
  assert.equal(launched.state, "reviewing");
  const evaluating = pollReview(state.runDir, {
    poller: () => ({ status: "completed" }),
    resultReader: () => ({ rendered: "REVIEW_COMPLETE" }),
    releaser: () => ({ ok: true })
  });
  assert.equal(evaluating.state, "evaluating");
  const finalizing = recordClaudeEvaluation(state.runDir, { decision: "agree", rationale: "Accepted" });
  assert.equal(finalizing.state, "finalizing");
  const finalized = finalizeReview(state.runDir);
  assert.equal(finalized.state, "done_phase1");
  assert.equal(fs.readFileSync(source, "utf8"), "# Original\n");
  releaseGlobalRunLock(globalLock);
});

test("execution confirmation binds plan-final SHA-256 and rejects post-confirmation mutation", () => {
  const root = tempDir();
  const runDir = path.join(root, "run");
  fs.mkdirSync(runDir);
  const finalFile = path.join(runDir, "plan-final.md");
  writePlan(finalFile);
  const state = {
    schemaVersion: 1,
    runId: "run",
    runDir,
    planFile: path.join(runDir, "plan-working.md"),
    sourcePlanFile: path.join(root, "source.md"),
    planOriginalFile: path.join(runDir, "plan-original.md"),
    planFileHash: "x",
    state: "done_phase1",
    round: 1,
    maxRounds: 3,
    reworkAttempts: 0,
    finalPlanFile: finalFile,
    globalLock: { ownerToken: "owner", path: path.join(root, "global.lock") }
  };
  fs.writeFileSync(path.join(runDir, "state.json"), JSON.stringify(state));
  const confirmed = recordExecutionConfirmation(runDir, { confirmedBy: "user" });
  assert.equal(confirmed.executionAuthorization.planFinalSha256, sha256File(finalFile));
  fs.appendFileSync(finalFile, "changed\n");
  const started = startExecution(runDir, { launcher: () => { throw new Error("must not launch"); } });
  assert.equal(started.state, "awaiting_user");
  assert.match(started.executionAuthorizationInvalidated.message, /SHA-256 changed/);
});

test("execution runs within declared roots and independent validation passes", () => {
  const root = tempDir("execution-project-");
  const orchestrationRoot = tempDir("execution-state-");
  const sourceDir = path.join(root, "src");
  fs.mkdirSync(sourceDir);
  const runDir = path.join(orchestrationRoot, "run");
  fs.mkdirSync(runDir);
  const finalFile = path.join(runDir, "plan-final.md");
  const escapedRoot = root.replaceAll("\\", "\\\\");
  writePlan(finalFile, [
    "---",
    "auto-review-execute:",
    "  targetRoots:",
    `    - "${escapedRoot}"`,
    "  allowedPaths:",
    `    - "${escapedRoot}\\\\src"`,
    "  acceptanceCriteria:",
    "    - id: ac-file",
    "      description: \"created file contains result\"",
    "      verifyCommand: \"Get-Content src/result.txt\"",
    "      expectedOutput: \"PASS\"",
    "---",
    "# Execute",
    ""
  ].join("\n"));
  const globalLock = acquireGlobalRunLock({ runId: "execution-run", stateFile: path.join(runDir, "state.json"), root: orchestrationRoot });
  const state = {
    schemaVersion: 1,
    runId: "execution-run",
    runDir,
    planFile: path.join(runDir, "plan-working.md"),
    sourcePlanFile: path.join(root, "source.md"),
    planOriginalFile: path.join(runDir, "plan-original.md"),
    planFileHash: "x",
    state: "done_phase1",
    round: 1,
    maxRounds: 3,
    reworkAttempts: 0,
    finalPlanFile: finalFile,
    globalLock: { ownerToken: globalLock.ownerToken, path: globalLock.path },
    finalPlanSha256: sha256File(finalFile)
  };
  fs.writeFileSync(path.join(runDir, "state.json"), JSON.stringify(state));
  const confirmed = recordExecutionConfirmation(runDir, { confirmedBy: "user" });
  const started = startExecution(runDir, {
    cwd: root,
    launcher: ({ cwd, targetRoots }) => {
      assert.equal(cwd, root);
      assert.equal(targetRoots.length, 1);
      assert.equal(targetRoots[0], root.toLowerCase());
      fs.writeFileSync(path.join(sourceDir, "result.txt"), "PASS\n", "utf8");
      return { jobId: "execution-job", ownerToken: "execution-owner" };
    }
  });
  assert.equal(started.state, "executing");
  const validating = pollExecution(runDir, {
    poller: () => ({ status: "completed" }),
    resultReader: () => ({ rendered: "EXECUTION_COMPLETE" }),
    releaser: () => ({ ok: true })
  });
  assert.equal(validating.state, "validating");
  const done = validateExecution(runDir, { cwd: root });
  assert.equal(done.state, "done");
  assert.equal(done.validation.passed, true);
  assert.equal(confirmed.executionAuthorization.planFinalSha256, sha256File(finalFile));
  releaseGlobalRunLock(globalLock);
});
