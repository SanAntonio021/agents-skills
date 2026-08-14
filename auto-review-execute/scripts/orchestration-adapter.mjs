import { spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

import { sha256Text } from "./common.mjs";

function bridgeCliPath() {
  const configured = process.env.CLAUDE_CODEX_BRIDGE_CLI;
  const root = process.env.CLAUDE_CODEX_BRIDGE_ROOT;
  const candidates = [
    configured,
    root ? path.join(root, "dist", "src", "cli", "main.js") : null,
    "D:/BaiduSyncdisk/.agents/mcp/claude-codex-bridge/dist/src/cli/main.js"
  ].filter(Boolean);
  const found = candidates.find((candidate) => fs.existsSync(candidate));
  if (!found) {
    throw new Error(
      "claude-codex-bridge CLI is unavailable; register/build the unified bridge MCP or set CLAUDE_CODEX_BRIDGE_CLI"
    );
  }
  return path.resolve(found);
}

function runBridge(args, cwd) {
  const cli = bridgeCliPath();
  const result = spawnSync(process.execPath, [cli, ...args], {
    cwd,
    encoding: "utf8",
    shell: false,
    windowsHide: true,
    env: process.env
  });
  if (result.error || result.status !== 0) {
    throw new Error(`claude-codex-bridge failed (exit ${result.status ?? -1}): ${(result.stderr || result.stdout).trim()}`);
  }
  let envelope;
  try {
    envelope = JSON.parse(result.stdout);
  } catch {
    throw new Error(`claude-codex-bridge returned invalid JSON: ${result.stdout}`);
  }
  if (!envelope.ok) {
    const message = envelope.error?.message || envelope.error || "bridge request failed";
    throw new Error(String(message));
  }
  return envelope.data;
}

function commonAncestor(paths) {
  const absolute = paths.map((entry) => path.resolve(entry));
  if (!absolute.length) return path.resolve(process.cwd());
  let candidate = absolute[0];
  for (const entry of absolute.slice(1)) {
    while (candidate !== path.dirname(candidate) && !isInside(candidate, entry)) {
      candidate = path.dirname(candidate);
    }
  }
  return candidate;
}

function isInside(root, candidate) {
  const relative = path.relative(root, candidate);
  return relative === "" || (!relative.startsWith(`..${path.sep}`) && relative !== ".." && !path.isAbsolute(relative));
}

function bridgeScope(targetRoots, explicitAllowedPaths = null) {
  const roots = targetRoots.map((entry) => path.resolve(entry));
  const ancestor = commonAncestor(roots);
  const targetRoot = ancestor;
  const candidates = explicitAllowedPaths ? explicitAllowedPaths.map((entry) => path.resolve(entry)) : roots;
  const allowedPaths = candidates.map((entry) => {
    const relative = path.relative(targetRoot, entry);
    if (relative.startsWith(`..${path.sep}`) || relative === ".." || path.isAbsolute(relative)) {
      throw new Error(`Could not express target root inside bridge scope: ${entry}`);
    }
    return relative || ".";
  });
  return { targetRoot, allowedPaths };
}

function createRequestFile({ cwd, targetRoots, allowedPaths, prompt, operation, artifactId, artifactType, round, artifactPath, acceptanceCriteria }) {
  const scope = bridgeScope(targetRoots, allowedPaths);
  const request = {
    question: prompt,
    route: "headless",
    operation,
    ...(operation === "review_repair" ? { reviewerAccess: "isolated_write" } : {}),
    targetRoot: scope.targetRoot,
    allowedPaths: scope.allowedPaths,
    ...(artifactId ? { artifactId } : {}),
    ...(artifactType ? { artifactType } : {}),
    ...(round ? { round } : {}),
    ...(Array.isArray(acceptanceCriteria) && acceptanceCriteria.length
      ? { acceptanceCriteria }
      : operation === "review_repair"
        ? { acceptanceCriteria: ["Return the complete matching review contract and keep every change within allowedPaths."] }
        : {}),
    ...(artifactPath && fs.existsSync(artifactPath)
      ? {
          artifactPath: path.resolve(artifactPath),
          artifactBytes: fs.statSync(artifactPath).size,
          artifactSha256: sha256Text(fs.readFileSync(artifactPath, "utf8")),
          artifactContent: fs.readFileSync(artifactPath, "utf8")
        }
      : {})
  };
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "auto-review-bridge-"));
  const requestFile = path.join(directory, "request.json");
  fs.writeFileSync(requestFile, JSON.stringify(request), "utf8");
  return { requestFile, directory };
}

export function resolveCompanionPath() {
  // Compatibility name retained for the state machine; this is the bridge CLI,
  // never the retired codex@openai-codex companion.
  return bridgeCliPath();
}

export function launchCodexJob({
  cwd,
  targetRoots,
  allowedPaths,
  prompt,
  artifactId,
  artifactType = "deliverable",
  round = 1,
  artifactPath,
  acceptanceCriteria,
  operation = "task"
}) {
  process.env.AUTO_REVIEW_EXECUTE = "1";
  const request = createRequestFile({
    cwd,
    targetRoots,
    allowedPaths,
    prompt,
    operation,
    artifactId,
    artifactType,
    round,
    artifactPath,
    acceptanceCriteria
  });
  try {
    const data = runBridge(["submit", "--target", "codex", "--request-file", request.requestFile], cwd);
    if (!data?.job_id) throw new Error("bridge submit did not return a job_id");
    return {
      jobId: data.job_id,
      ownerToken: null,
      companionPath: bridgeCliPath(),
      bridge: true,
      promptSha256: sha256Text(prompt),
      promptBytes: Buffer.byteLength(prompt, "utf8")
    };
  } finally {
    fs.rmSync(request.directory, { recursive: true, force: true });
  }
}

export function pollCodexJob({ cwd, jobId }) {
  const data = runBridge(["status", jobId], cwd);
  const state = data?.state;
  const status = ["queued", "dispatching", "transport_delivered", "running"].includes(state)
    ? (state === "queued" ? "queued" : "running")
    : state === "succeeded"
      ? "completed"
      : state === "needs_attention"
        ? "needs_attention"
        : state || "failed";
  return { ...data, job: data, status, bridge: true };
}

export function readCodexResult({ cwd, jobId }) {
  const data = runBridge(["result", jobId], cwd);
  if (data?.status === "pending") throw new Error(`Bridge result is still pending for ${jobId}`);
  const job = data?.job || data;
  if (!job) throw new Error(`Bridge result has no job for ${jobId}`);
  return {
    rendered: typeof job.result === "string" ? job.result : JSON.stringify(job.result ?? job),
    job,
    bridge: true
  };
}

export function cancelCodexJob({ cwd, jobId }) {
  return runBridge(["cancel", jobId], cwd);
}

export function approvePeerSync({ cwd, jobId, approvedChangeIds }) {
  if (!Array.isArray(approvedChangeIds) || approvedChangeIds.length === 0) {
    throw new Error("approvedChangeIds must be a non-empty exact ID list");
  }
  return runBridge(["approve-sync", jobId, "--change-ids", approvedChangeIds.join(",")], cwd);
}

export function releaseCodexClaim() {
  // The bridge daemon owns its lock and releases it at job termination.
  return { ok: true, skipped: "bridge-owned-lock" };
}

export function commandMetadata() {
  return {
    bridgeCli: bridgeCliPath(),
    node: process.execPath,
    host: os.hostname(),
    runtimeDependency: "claude-codex-bridge"
  };
}

// Kept for callers that still use the old helper name. It resolves only the
// unified bridge executable; it never consults the retired plugin registry.
export const resolveBridgeCliPath = bridgeCliPath;
