import { spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

import { sha256Text } from "./common.mjs";
import { cmdRelease } from "../../cross-model-orchestration/scripts/orchestration-control.mjs";

const SKILL_ROOT = path.resolve(path.dirname(new URL(import.meta.url).pathname.replace(/^\/([A-Z]:)/, "$1")), "..");
const ORCHESTRATION_CONTROL = path.resolve(
  SKILL_ROOT,
  "..",
  "cross-model-orchestration",
  "scripts",
  "orchestration-control.mjs"
);
const RESUME_CANDIDATE = path.resolve(
  SKILL_ROOT,
  "..",
  "cross-model-orchestration",
  "scripts",
  "check-resume-candidate.mjs"
);

function runNode(script, args, cwd) {
  const result = spawnSync(process.execPath, [script, ...args], {
    cwd,
    encoding: "utf8",
    shell: false,
    windowsHide: true,
    env: process.env
  });
  if (result.error || result.status !== 0) {
    throw new Error(`${path.basename(script)} failed (exit ${result.status ?? -1}): ${(result.stderr || result.stdout).trim()}`);
  }
  try {
    return JSON.parse(result.stdout);
  } catch {
    throw new Error(`${path.basename(script)} returned invalid JSON: ${result.stdout}`);
  }
}

export function resolveCompanionPath() {
  const result = runNode(RESUME_CANDIDATE, ["--companion-path"], process.cwd());
  if (!result.ok || !result.companionPath) throw new Error(result.message || "Could not resolve Codex companion path");
  return result.companionPath;
}

export function launchCodexJob({ cwd, targetRoots, prompt, companionPath = resolveCompanionPath() }) {
  process.env.AUTO_REVIEW_EXECUTE = "1";
  if (!fs.existsSync(ORCHESTRATION_CONTROL)) {
    throw new Error(`Missing cross-model orchestration helper: ${ORCHESTRATION_CONTROL}`);
  }
  const args = [
    "launch",
    "--companion-path", companionPath,
    "--cwd", path.resolve(cwd),
    "--target-roots", targetRoots.map((entry) => path.resolve(entry)).join(","),
    "--write",
    "true",
    prompt
  ];
  const result = runNode(ORCHESTRATION_CONTROL, args, cwd);
  if (!result.ok || !result.jobId || !result.ownerToken) throw new Error("Codex launch did not return jobId and ownerToken");
  return { ...result, companionPath, promptSha256: sha256Text(prompt), promptBytes: Buffer.byteLength(prompt, "utf8") };
}

export function pollCodexJob({ cwd, jobId, companionPath = resolveCompanionPath() }) {
  const result = runNode(
    ORCHESTRATION_CONTROL,
    ["status", jobId, "--companion-path", companionPath, "--cwd", path.resolve(cwd)],
    cwd
  );
  const status = result.job?.status;
  if (!status) throw new Error(`Codex status response has no job.status for ${jobId}`);
  return { ...result, status, companionPath };
}

export function readCodexResult({ cwd, jobId, companionPath = resolveCompanionPath() }) {
  const result = runNode(
    ORCHESTRATION_CONTROL,
    ["result", jobId, "--companion-path", companionPath, "--cwd", path.resolve(cwd)],
    cwd
  );
  if (!result.rendered) throw new Error(`Codex result has no rendered output for ${jobId}`);
  return result;
}

export function cancelCodexJob({ cwd, jobId, companionPath = resolveCompanionPath() }) {
  const result = spawnSync(process.execPath, [companionPath, "cancel", jobId, "--cwd", path.resolve(cwd)], {
    cwd,
    encoding: "utf8",
    shell: false,
    windowsHide: true,
    env: process.env
  });
  if (result.error || result.status !== 0) {
    throw new Error(`Codex cancel failed (exit ${result.status ?? -1}): ${(result.stderr || result.stdout).trim()}`);
  }
  return result.stdout.trim();
}

export function releaseCodexClaim({ ownerToken, cwd = process.cwd() }) {
  // orchestration-control exposes cmdRelease as a module API but not as a CLI
  // subcommand. Importing it keeps release tied to the same registry protocol.
  return cmdRelease({ ownerToken, cwd });
}

export function commandMetadata() {
  return {
    orchestrationControl: ORCHESTRATION_CONTROL,
    companionResolver: RESUME_CANDIDATE,
    node: process.execPath,
    host: os.hostname()
  };
}
