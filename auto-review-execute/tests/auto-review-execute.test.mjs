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
import { buildReviewPrompt, initializeReviewRun, launchReview, pollReview, recordClaudeEvaluation, finalizeReview, approveReviewSync } from "../scripts/review-loop.mjs";
import { readState } from "../scripts/run-state.mjs";
import {
  cancelCodexJob,
  launchCodexJob,
  pollCodexJob,
  readCodexResult,
  approvePeerSync
} from "../scripts/orchestration-adapter.mjs";
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

test("published skill uses project-local v3 review and preserves the user execution gate", () => {
  const skillPath = path.resolve(new URL("../SKILL.md", import.meta.url).pathname.replace(/^\/([A-Z]:)/, "$1"));
  const skill = fs.readFileSync(skillPath, "utf8");
  assert.match(skill, /Claude Code VS Code 插件或 CLI/u);
  assert.match(skill, /v3_review_peer/u);
  assert.match(skill, /v3_author_checkpoint/u);
  assert.match(skill, /真实项目/u);
  assert.match(skill, /完整工具/u);
  assert.match(skill, /可直接修改/u);
  assert.match(skill, /不传 `artifactContent`/u);
  assert.match(skill, /author_modified=true/u);
  assert.match(skill, /final_check/u);
  assert.match(skill, /用户明确确认后/u);
  assert.match(skill, /一个普通文件/u);
  assert.doesNotMatch(skill, /Claude Desktop continuation API/u);
  assert.doesNotMatch(skill, /submit_peer\(target=codex/u);
  assert.doesNotMatch(skill, /reviewerAccess=isolated_write/u);
  assert.doesNotMatch(skill, /workspaceReviews=true/u);
});

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

test("review prompt requires the complete PLAN_REVIEW contract without a legacy sentinel", () => {
  const root = tempDir();
  const planFile = path.join(root, "plan-working.md");
  writePlan(planFile);
  const prompt = buildReviewPrompt(planFile, root, 1);
  assert.match(prompt, /complete PLAN_REVIEW/);
  assert.match(prompt, /已确认事项/);
  assert.match(prompt, /问题与理由/);
  assert.match(prompt, /必须修改/);
  assert.match(prompt, /剩余风险/);
  assert.doesNotMatch(prompt, /REVIEW_COMPLETE/);
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
    resultReader: () => ({
      rendered: [
        "PLAN_REVIEW",
        "结论：通过",
        "已确认事项：",
        "- 计划完整。",
        "问题与理由：",
        "- 无。",
        "必须修改：",
        "- 无。",
        "剩余风险：",
        "- 无。"
      ].join("\n")
    }),
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

test("review polling preserves high-risk approval and never starts a replacement model turn", () => {
  const root = tempDir();
  const source = path.join(root, "source-plan.md");
  writePlan(source, "# Original\n");
  const globalLock = acquireGlobalRunLock({ runId: "run-attention", stateFile: path.join(root, "run-attention", "state.json"), root });
  const state = initializeReviewRun({ root, runId: "run-attention", sourcePlanFile: source, globalLock });
  const launched = launchReview(state, {
    launcher: () => ({ jobId: "attention-job", ownerToken: null, companionPath: "bridge", promptSha256: "x", promptBytes: 1 })
  });
  const changeId = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb";
  const awaiting = pollReview(state.runDir, {
    poller: () => ({
      status: "needs_attention",
      sync_status: "awaiting_user",
      pending_high_risk: [{ id: changeId, action: "delete", path: "old.md" }]
    }),
    resultReader: () => ({ job: { pending_high_risk: [{ id: changeId, action: "delete", path: "old.md" }] }, rendered: "review" }),
    releaser: () => ({ ok: true })
  });
  assert.equal(awaiting.state, "awaiting_user");
  assert.equal(awaiting.peerSync.pendingHighRisk[0].id, changeId);
  assert.throws(
    () => approveReviewSync(state.runDir, ["cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc"], { approver: () => ({}) }),
    /exactly match/
  );
  const approved = approveReviewSync(state.runDir, [changeId], {
    approver: ({ jobId, approvedChangeIds }) => {
      assert.equal(jobId, "attention-job");
      assert.deepEqual(approvedChangeIds, [changeId]);
      return { sync_status: "synced", sync_request_id: "sync-1" };
    }
  });
  assert.equal(approved.state, "evaluating");
  assert.equal(approved.peerSync.syncResult.sync_request_id, "sync-1");
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

test("bridge adapter routes to Codex without plugin registry and preserves review scope", () => {
  const root = tempDir("bridge-adapter-project-");
  const sourceDir = path.join(root, "src");
  fs.mkdirSync(sourceDir, { recursive: true });
  const artifact = path.join(sourceDir, "artifact.md");
  fs.writeFileSync(artifact, "artifact\n", "utf8");
  const fakeHome = tempDir("bridge-adapter-home-");
  const fakeCli = path.join(root, "fake-bridge-cli.mjs");
  const log = path.join(root, "bridge-request.json");
  fs.writeFileSync(
    fakeCli,
    [
      "import fs from 'node:fs';",
      "const [command, ...args] = process.argv.slice(2);",
      "const pick = (name) => { const index = args.indexOf(name); return index < 0 ? undefined : args[index + 1]; };",
      `const log = ${JSON.stringify(log)};`,
      "if (command === 'submit') { const request = JSON.parse(fs.readFileSync(pick('--request-file'), 'utf8')); fs.writeFileSync(log, JSON.stringify({ command, args, request })); process.stdout.write(JSON.stringify({ ok: true, data: { job_id: '11111111-1111-4111-8111-111111111111', state: 'queued', created: true } })); }",
      "else if (command === 'status') { process.stdout.write(JSON.stringify({ ok: true, data: { job_id: args[0], state: 'needs_attention', sync_status: 'awaiting_user', pending_high_risk: [{ id: 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', action: 'delete', path: 'src/old.md' }] } })); }",
      "else if (command === 'result') { process.stdout.write(JSON.stringify({ ok: true, data: { job_id: args[0], state: 'needs_attention', pending_high_risk: [{ id: 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', action: 'delete', path: 'src/old.md' }] } })); }",
      "else if (command === 'cancel') { process.stdout.write(JSON.stringify({ ok: true, data: { job_id: args[0], cancellation_requested: true } })); }",
      "else if (command === 'approve-sync') { process.stdout.write(JSON.stringify({ ok: true, data: { job_id: args[0], sync_request_id: '22222222-2222-4222-8222-222222222222', sync_status: 'synced' } })); }",
      "else { process.exitCode = 2; }"
    ].join("\n"),
    "utf8"
  );
  const previousCli = process.env.CLAUDE_CODEX_BRIDGE_CLI;
  const previousRoot = process.env.CLAUDE_CODEX_BRIDGE_ROOT;
  const previousHome = process.env.USERPROFILE;
  try {
    process.env.CLAUDE_CODEX_BRIDGE_CLI = fakeCli;
    delete process.env.CLAUDE_CODEX_BRIDGE_ROOT;
    process.env.USERPROFILE = fakeHome;
    const launched = launchCodexJob({
      cwd: root,
      targetRoots: [root],
      allowedPaths: [artifact],
      prompt: "review and repair",
      artifactId: "adapter-artifact",
      artifactType: "deliverable",
      round: 2,
      artifactPath: artifact,
      operation: "review_repair"
    });
    assert.equal(launched.jobId, "11111111-1111-4111-8111-111111111111");
    const submitted = JSON.parse(fs.readFileSync(log, "utf8"));
    assert.equal(submitted.command, "submit");
    assert.deepEqual(submitted.args.slice(0, 2), ["--target", "codex"]);
    assert.equal(submitted.request.operation, "review_repair");
    assert.equal(submitted.request.reviewerAccess, "isolated_write");
    assert.equal(submitted.request.artifactId, "adapter-artifact");
    assert.equal(submitted.request.artifactType, "deliverable");
    assert.equal(submitted.request.round, 2);
    assert.ok(submitted.request.targetRoot);
    assert.deepEqual(submitted.request.allowedPaths, [path.relative(submitted.request.targetRoot, artifact)]);
    assert.equal(submitted.request.artifactBytes, fs.statSync(artifact).size);
    assert.equal(typeof submitted.request.artifactSha256, "string");
    assert.equal(typeof submitted.request.artifactContent, "string");

    const status = pollCodexJob({ cwd: root, jobId: launched.jobId });
    assert.equal(status.status, "needs_attention");
    assert.equal(status.sync_status, "awaiting_user");
    assert.equal(status.pending_high_risk[0].action, "delete");
    const result = readCodexResult({ cwd: root, jobId: launched.jobId });
    assert.equal(result.job.pending_high_risk[0].id, "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa");
    assert.deepEqual(cancelCodexJob({ cwd: root, jobId: launched.jobId }), {
      job_id: launched.jobId,
      cancellation_requested: true
    });
    assert.deepEqual(
      approvePeerSync({
        cwd: root,
        jobId: launched.jobId,
        approvedChangeIds: ["aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"]
      }),
      { job_id: launched.jobId, sync_request_id: "22222222-2222-4222-8222-222222222222", sync_status: "synced" }
    );
  } finally {
    if (previousCli === undefined) delete process.env.CLAUDE_CODEX_BRIDGE_CLI;
    else process.env.CLAUDE_CODEX_BRIDGE_CLI = previousCli;
    if (previousRoot === undefined) delete process.env.CLAUDE_CODEX_BRIDGE_ROOT;
    else process.env.CLAUDE_CODEX_BRIDGE_ROOT = previousRoot;
    if (previousHome === undefined) delete process.env.USERPROFILE;
    else process.env.USERPROFILE = previousHome;
    fs.rmSync(root, { recursive: true, force: true });
    fs.rmSync(fakeHome, { recursive: true, force: true });
  }
});
