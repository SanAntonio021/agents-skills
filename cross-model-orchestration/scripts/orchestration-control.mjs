#!/usr/bin/env node
/**
 * orchestration-control.mjs — Claude-Codex cross-model orchestration helper.
 *
 * Sub-commands:
 *   launch       Start a background Codex task under the orchestration lock.
 *   status       Poll the status of a running job.
 *   result       Read the rendered output of a completed job.
 *   candidate    Verify that a finished job's output is trustworthy.
 *   active       Check whether any orchestration claim is currently live.
 *   verify-request  Verify that a launched job received the intended prompt.
 *   recover-lock Four-shape manual recovery for stuck registry/claim state.
 *
 * All subprocess calls use argv arrays + shell:false + UTF-8 encoding.
 * No $USERPROFILE literal paths — use os.homedir() or $USERPROFILE in the shell.
 */

import { createHash, randomBytes } from "node:crypto";
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import process from "node:process";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

/** Total orchestration time limit in milliseconds (60 minutes). */
const ORCHESTRATION_TIMEOUT_MS = 60 * 60 * 1000;

/** Registry lock stale timeout in milliseconds (60 seconds). */
const LOCK_STALE_MS = 60 * 1000;

const PLUGIN_DATA_ENV = "CLAUDE_PLUGIN_DATA";

// ---------------------------------------------------------------------------
// Clock injection (allows tests to override Date.now)
// ---------------------------------------------------------------------------
let _now = () => Date.now();
export function _injectClock(fn) { _now = fn; }
export function _resetClock() { _now = () => Date.now(); }

// ---------------------------------------------------------------------------
// Path helpers
// ---------------------------------------------------------------------------

function resolveOrchestrationDir() {
  const base = process.env[PLUGIN_DATA_ENV];
  if (!base) throw new Error(`${PLUGIN_DATA_ENV} is not set. Start from a Claude Code session.`);
  return path.join(base, "orchestration");
}

function lockPath(orchDir) { return path.join(orchDir, "registry.lock"); }
function recoverLockPath(orchDir) { return path.join(orchDir, "recover.lock"); }
function claimsPath(orchDir) { return path.join(orchDir, "claims.json"); }

function ensureOrchDir(orchDir) {
  fs.mkdirSync(orchDir, { recursive: true });
}

// ---------------------------------------------------------------------------
// Registry mutex (wx-based, token + ino/dev identity)
// ---------------------------------------------------------------------------

/** Try to acquire the registry mutex. Returns ownerToken on success, null on EEXIST. */
function tryAcquireRegistryMutex(orchDir) {
  ensureOrchDir(orchDir);
  const lp = lockPath(orchDir);
  const ownerToken = randomBytes(16).toString("hex");
  let fd;
  try {
    fd = fs.openSync(lp, "wx");
  } catch (err) {
    if (err.code === "EEXIST") return null;
    throw err;
  }
  try {
    fs.writeSync(fd, JSON.stringify({ ownerToken, acquiredAt: new Date().toISOString() }));
  } finally {
    fs.closeSync(fd);
  }
  // Record ino/dev for identity verification on release.
  const stat = fs.statSync(lp);
  return { ownerToken, ino: stat.ino, dev: stat.dev };
}

/**
 * Acquire the registry mutex, handling stale locks.
 * Three-state takeover: alive → never, dead → may take over, unknown → never.
 */
function acquireRegistryMutex(orchDir, maxWaitMs = 5000, intervalMs = 100) {
  const deadline = _now() + maxWaitMs;
  while (_now() < deadline) {
    const result = tryAcquireRegistryMutex(orchDir);
    if (result) return result;

    // Lock exists — check if it's stale.
    const lp = lockPath(orchDir);
    let stat;
    try { stat = fs.statSync(lp); } catch { /* disappeared, retry */ continue; }
    const age = _now() - stat.mtimeMs;
    if (age < LOCK_STALE_MS) {
      // Not stale yet — wait and retry.
      const wait = Math.min(intervalMs, deadline - _now());
      if (wait > 0) spawnSync(process.execPath, ["-e", `setTimeout(()=>{},${wait})`], { shell: false });
      continue;
    }

    // Stale lock — attempt takeover.
    let content;
    try { content = JSON.parse(fs.readFileSync(lp, "utf8")); } catch { content = null; }
    if (!content) {
      // Corrupted — attempt rename-based takeover.
      const takeover = lp + ".takeover-" + randomBytes(8).toString("hex");
      try {
        fs.renameSync(lp, takeover);
        // We "won" the rename — now acquire fresh.
        const fresh = tryAcquireRegistryMutex(orchDir);
        if (fresh) return fresh;
      } catch { /* another thread won, retry */ }
      continue;
    }

    // Check if the process owning the lock is still alive.
    // We cannot reliably identify ownership by pid here (lock doesn't store pid),
    // so stale + mtime threshold is the only signal. Treat as dead → take over.
    const takeover = lp + ".takeover-" + content.ownerToken;
    try {
      fs.renameSync(lp, takeover);
      const fresh = tryAcquireRegistryMutex(orchDir);
      if (fresh) return fresh;
    } catch { /* another thread won */ }
  }
  throw new Error("Timed out acquiring orchestration registry lock.");
}

/**
 * Release the registry mutex.  Verifies token + ino/dev identity before rename.
 * Safe to call even if the lock file has already been taken over.
 */
function releaseRegistryMutex(orchDir, ownerToken, ino, dev) {
  const lp = lockPath(orchDir);
  let stat;
  try { stat = fs.statSync(lp); } catch { return; } // already gone
  if (stat.ino !== ino || stat.dev !== dev) return; // taken over by someone else
  let content;
  try { content = JSON.parse(fs.readFileSync(lp, "utf8")); } catch { content = null; }
  if (!content || content.ownerToken !== ownerToken) return;
  const dest = lp + ".takeover-" + ownerToken;
  try { fs.renameSync(lp, dest); } catch { /* already gone */ }
}

// ---------------------------------------------------------------------------
// Claims
// ---------------------------------------------------------------------------

function loadClaims(orchDir) {
  const cp = claimsPath(orchDir);
  if (!fs.existsSync(cp)) return [];
  try { return JSON.parse(fs.readFileSync(cp, "utf8")); } catch { return []; }
}

function saveClaims(orchDir, claims) {
  const cp = claimsPath(orchDir);
  const tmp = cp + ".tmp." + randomBytes(4).toString("hex");
  fs.writeFileSync(tmp, JSON.stringify(claims, null, 2) + "\n", "utf8");
  fs.renameSync(tmp, cp);
}

/** Check if the orchestration timeout has elapsed for a claim. */
function claimTimedOut(claim) {
  return (_now() - claim.startedAt) > ORCHESTRATION_TIMEOUT_MS;
}

// ---------------------------------------------------------------------------
// Companion helpers
// ---------------------------------------------------------------------------

function resolveCompanionPath() {
  const companionHomeRelative = runNode(
    `
const { spawnSync } = require('child_process');
const res = spawnSync(process.execPath, [
  require('path').join(require('os').homedir(), '.claude/skills/cross-model-orchestration/scripts/check-resume-candidate.mjs'),
  '--companion-path'
], { encoding: 'utf8', shell: false });
if (res.status !== 0) { process.stderr.write(res.stderr || res.stdout); process.exit(1); }
const data = JSON.parse(res.stdout);
process.stdout.write(data.companionHomeRelative);
`
  );
  return path.join(os.homedir(), companionHomeRelative.trim());
}

/** Run a Node.js expression inline and return stdout. */
function runNode(expr) {
  const result = spawnSync(process.execPath, ["-e", expr], {
    encoding: "utf8",
    shell: false,
    env: process.env
  });
  if (result.error) throw result.error;
  if (result.status !== 0) throw new Error(`node eval failed: ${result.stderr || result.stdout}`);
  return result.stdout;
}

/** Run the companion CLI and return { status, stdout, stderr }. */
function runCompanion(companionPath, args, cwd) {
  const result = spawnSync(process.execPath, [companionPath, ...args], {
    cwd: cwd || process.cwd(),
    encoding: "utf8",
    shell: false,
    env: process.env
  });
  return { status: result.status ?? -1, stdout: result.stdout ?? "", stderr: result.stderr ?? "", error: result.error ?? null };
}

// ---------------------------------------------------------------------------
// Windows process liveness (A4 spec)
// ---------------------------------------------------------------------------

function isProcessAlive(pid) {
  if (!Number.isFinite(pid)) return false;
  if (process.platform === "win32") {
    const result = spawnSync("tasklist", ["/FI", `PID eq ${pid}`, "/NH", "/FO", "CSV"], {
      encoding: "utf8",
      shell: false
    });
    if (result.error) return "unknown";
    const out = `${result.stdout}\n${result.stderr}`.toLowerCase();
    if (out.includes("no tasks") || out.includes("no running")) return false;
    if (out.includes(String(pid))) return true;
    return "unknown";
  }
  // Unix
  try { process.kill(pid, 0); return true; }
  catch (err) {
    if (err?.code === "ESRCH") return false;
    if (err?.code === "EPERM") return true;
    return "unknown";
  }
}

// ---------------------------------------------------------------------------
// targetRoots normalisation
// ---------------------------------------------------------------------------

function normaliseRoot(p) {
  // Resolve, lower-case drive letter on Windows, trailing-slash strip.
  let resolved = path.resolve(p);
  if (process.platform === "win32") {
    // Lower the drive letter only.
    resolved = resolved.replace(/^([A-Za-z]:)/, (m) => m.toLowerCase());
  }
  return resolved.replace(/[\\/]+$/, "") || resolved;
}

/** Returns true if candidate is an ancestor of or equal to target. */
function isAncestorOf(ancestor, target) {
  const a = normaliseRoot(ancestor) + path.sep;
  const t = normaliseRoot(target) + path.sep;
  return t.startsWith(a) || normaliseRoot(ancestor) === normaliseRoot(target);
}

// ---------------------------------------------------------------------------
// Sub-command: launch
// ---------------------------------------------------------------------------

/**
 * Launch a background Codex task under the orchestration lock.
 *
 * Steps (in order, must not change):
 *   1. Acquire registry lock
 *   2. Within critical section: check for overlapping active claims + workspace
 *   3. Register placeholder claim (jobId=null)
 *   4. Release lock immediately
 *   5. Launch companion WITHOUT holding the lock (avoids deadlock)
 *   6. Acquire short lock again to bind the real jobId
 *   7. Release
 *
 * Returns JSON: { ok, jobId, ownerToken, claimIndex }
 */
export function cmdLaunch({ companionPath, cwd, prompt, targetRoots, write, model, effort }) {
  const orchDir = resolveOrchestrationDir();
  const normTargets = (targetRoots || [cwd]).map(normaliseRoot);
  const startedAt = _now();
  const ownerToken = randomBytes(16).toString("hex");

  // Step 1 + 2 + 3: acquire lock, check overlaps, register placeholder
  {
    const mutex = acquireRegistryMutex(orchDir);
    try {
      const claims = loadClaims(orchDir);
      // GC terminated claims
      const liveClaims = claims.filter((c) => !claimTimedOut(c));

      // Check for workspace overlap
      for (const claim of liveClaims) {
        const claimRoots = (claim.targetRoots || []).map(normaliseRoot);
        for (const target of normTargets) {
          for (const claimRoot of claimRoots) {
            if (isAncestorOf(target, claimRoot) || isAncestorOf(claimRoot, target)) {
              throw new Error(
                `Orchestration conflict: workspace "${target}" overlaps with active claim owned by session "${claim.sessionId}" (token ${claim.ownerToken}).`
              );
            }
          }
        }
      }

      // Register placeholder
      liveClaims.push({ ownerToken, sessionId: process.env.CODEX_COMPANION_SESSION_ID ?? null, jobId: null, targetRoots: normTargets, startedAt });
      saveClaims(orchDir, liveClaims);
    } finally {
      releaseRegistryMutex(orchDir, mutex.ownerToken, mutex.ino, mutex.dev);
    }
  }

  // Step 5: launch (no lock held)
  const args = ["task", "--background", "--fresh", `--cwd`, cwd];
  if (write) args.push("--write");
  if (model) args.push("--model", model);
  if (effort) args.push("--effort", effort);
  args.push(prompt);

  const launched = runCompanion(companionPath, args, cwd);
  if (launched.error || launched.status !== 0) {
    // Clean up claim on launch failure
    try {
      const mutex2 = acquireRegistryMutex(orchDir);
      try {
        const claims = loadClaims(orchDir);
        saveClaims(orchDir, claims.filter((c) => c.ownerToken !== ownerToken));
      } finally {
        releaseRegistryMutex(orchDir, mutex2.ownerToken, mutex2.ino, mutex2.dev);
      }
    } catch { /* ignore cleanup errors */ }
    throw new Error(`companion launch failed (exit ${launched.status}): ${launched.stderr || launched.stdout}`);
  }

  let jobId;
  try {
    const payload = JSON.parse(launched.stdout);
    jobId = payload.jobId;
  } catch {
    throw new Error(`companion returned non-JSON: ${launched.stdout}`);
  }

  // Step 6 + 7: bind real jobId
  {
    const mutex = acquireRegistryMutex(orchDir);
    try {
      const claims = loadClaims(orchDir);
      const idx = claims.findIndex((c) => c.ownerToken === ownerToken);
      if (idx !== -1) {
        claims[idx].jobId = jobId;
        saveClaims(orchDir, claims);
      }
    } finally {
      releaseRegistryMutex(orchDir, mutex.ownerToken, mutex.ino, mutex.dev);
    }
  }

  return { ok: true, jobId, ownerToken };
}

// ---------------------------------------------------------------------------
// Sub-command: status
// ---------------------------------------------------------------------------

/** Poll job status via the companion. Returns the raw JSON payload. */
export function cmdStatus({ companionPath, cwd, jobId }) {
  const args = ["status", jobId, "--json", "--cwd", cwd];
  const result = runCompanion(companionPath, args, cwd);
  if (result.error || result.status !== 0) {
    throw new Error(`status failed (exit ${result.status}): ${result.stderr || result.stdout}`);
  }
  return JSON.parse(result.stdout);
}

// ---------------------------------------------------------------------------
// Sub-command: result
// ---------------------------------------------------------------------------

/**
 * Read the rendered output of a completed job.
 * Requires the job to be completed; throws if still active.
 */
export function cmdResult({ companionPath, cwd, jobId }) {
  const args = ["result", jobId, "--json", "--cwd", cwd];
  const result = runCompanion(companionPath, args, cwd);
  if (result.error || result.status !== 0) {
    throw new Error(`result failed (exit ${result.status}): ${result.stderr || result.stdout}`);
  }
  const payload = JSON.parse(result.stdout);
  const storedJob = payload.storedJob ?? payload.job ?? {};
  const rendered = storedJob.rendered ?? payload.job?.rendered ?? null;
  if (!rendered) {
    throw new Error(`Job ${jobId} completed but rendered output is empty — cannot use as authoritative response.`);
  }
  return { rendered, result: storedJob.result ?? null, job: payload.job };
}

// ---------------------------------------------------------------------------
// Sub-command: candidate
// ---------------------------------------------------------------------------

/**
 * Verify that a finished job's output is trustworthy (source validation).
 *
 * Three checks per D3:
 *   1. workspaceRoot matches resolveWorkspaceRoot(cwd)
 *   2. All targetRoots[] are descendants of cwd
 *   3. targetRoots[] matches the registered claim
 */
export function cmdCandidate({ companionPath, cwd, jobId, ownerToken, targetRoots }) {
  // Get job metadata
  const statusPayload = cmdStatus({ companionPath, cwd, jobId });
  const job = statusPayload.job;
  if (!job) throw new Error(`Job ${jobId} not found.`);

  const jobWorkspaceRoot = job.workspaceRoot ? normaliseRoot(job.workspaceRoot) : null;
  const sessionCwd = normaliseRoot(cwd);

  const issues = [];

  // Check 1: workspaceRoot matches cwd
  if (jobWorkspaceRoot && jobWorkspaceRoot !== sessionCwd) {
    issues.push(`workspaceRoot mismatch: job has "${jobWorkspaceRoot}", expected "${sessionCwd}"`);
  }

  // Check 2: all targetRoots are descendants of cwd
  const normTargets = (targetRoots || []).map(normaliseRoot);
  for (const target of normTargets) {
    if (!isAncestorOf(sessionCwd, target)) {
      issues.push(`targetRoot "${target}" is not under cwd "${sessionCwd}"`);
    }
  }

  // Check 3: targetRoots matches registered claim
  if (ownerToken) {
    const orchDir = resolveOrchestrationDir();
    const claims = loadClaims(orchDir);
    const claim = claims.find((c) => c.ownerToken === ownerToken);
    if (!claim) {
      issues.push(`No active claim found for ownerToken ${ownerToken}`);
    } else {
      const claimRoots = (claim.targetRoots || []).map(normaliseRoot);
      const claimSet = new Set(claimRoots);
      const targetSet = new Set(normTargets);
      for (const t of targetSet) { if (!claimSet.has(t)) issues.push(`targetRoot "${t}" not in registered claim`); }
      for (const t of claimSet) { if (!targetSet.has(t)) issues.push(`claim root "${t}" missing from provided targetRoots`); }
    }
  }

  return { ok: issues.length === 0, issues, job };
}

// ---------------------------------------------------------------------------
// Sub-command: active
// ---------------------------------------------------------------------------

/** Check whether any live orchestration claim currently exists. */
export function cmdActive() {
  const orchDir = resolveOrchestrationDir();
  const claims = loadClaims(orchDir);
  const live = claims.filter((c) => !claimTimedOut(c));
  return { active: live.length > 0, claims: live };
}

// ---------------------------------------------------------------------------
// Sub-command: verify-request
// ---------------------------------------------------------------------------

/**
 * Verify that a launched job received the intended prompt unchanged.
 *
 * Reads request.prompt from the job JSON via companion result, hashes it,
 * and compares against --expect-sha256 and --expect-bytes.
 *
 * On mismatch, signals the caller to cancel and abort.
 */
export function cmdVerifyRequest({ companionPath, cwd, jobId, expectSha256, expectBytes }) {
  const args = ["status", jobId, "--json", "--cwd", cwd];
  const r = runCompanion(companionPath, args, cwd);
  if (r.error || r.status !== 0) throw new Error(`status failed: ${r.stderr || r.stdout}`);

  const payload = JSON.parse(r.stdout);
  const job = payload.job;
  const prompt = job?.request?.prompt ?? null;
  if (!prompt) {
    return { ok: false, reason: "request.prompt is absent or empty — cannot verify what Codex received", cancel: true };
  }

  const actualBytes = Buffer.byteLength(prompt, "utf8");
  const actualSha256 = createHash("sha256").update(prompt, "utf8").digest("hex");

  if (expectBytes != null && actualBytes !== Number(expectBytes)) {
    return { ok: false, reason: `byte count mismatch: expected ${expectBytes}, got ${actualBytes}`, cancel: true };
  }
  if (expectSha256 && actualSha256 !== expectSha256.toLowerCase()) {
    return { ok: false, reason: `SHA-256 mismatch: expected ${expectSha256}, got ${actualSha256}`, cancel: true };
  }

  return { ok: true, actualBytes, actualSha256 };
}

// ---------------------------------------------------------------------------
// Sub-command: recover-lock
// ---------------------------------------------------------------------------

/**
 * Manual recovery helper for stuck lock/claim state.
 *
 * Shapes:
 *   A  – Force-release a registry.lock whose holder is dead/unknown.
 *        Requires --owner-token + --fingerprint + --force
 *   B  – Force-release a corrupted (unparseable) registry.lock.
 *        Requires --owner-token + --fingerprint + --force
 *   C  – Remove a specific entry from claims.json by ownerToken.
 *        Requires --owner-token + --force
 *   D  – Clear all entries from claims.json.
 *        Requires --force
 *
 * Fingerprint is: "${ino}:${dev}:${size}:${mtime}"
 */
export function cmdRecoverLock({ shape, ownerToken, fingerprint, force }) {
  if (!force) throw new Error("--force is required for recover-lock to prevent accidental use.");
  const orchDir = resolveOrchestrationDir();

  if (shape === "A" || shape === "B") {
    if (!ownerToken || !fingerprint) {
      throw new Error(`recover-lock ${shape} requires --owner-token and --fingerprint.`);
    }

    // Use recover.lock as the gate lock (avoids self-locking on registry.lock).
    const recLock = recoverLockPath(orchDir);
    const gateStat = { ino: null, dev: null };
    let gateFd;
    try {
      gateFd = fs.openSync(recLock, "wx");
    } catch (err) {
      if (err.code !== "EEXIST") throw err;
      // recover.lock itself may be stale
      let rs;
      try { rs = fs.statSync(recLock); } catch { throw new Error("recover.lock disappeared; retry."); }
      if ((_now() - rs.mtimeMs) < LOCK_STALE_MS) {
        throw new Error("recover.lock is held by another recovery operation. Wait or delete it manually.");
      }
      // Stale — try to take over
      const dest = recLock + ".stale." + randomBytes(4).toString("hex");
      fs.renameSync(recLock, dest);
      gateFd = fs.openSync(recLock, "wx");
    }
    const gStat = fs.statSync(recLock);
    gateStat.ino = gStat.ino;
    gateStat.dev = gStat.dev;
    fs.closeSync(gateFd);

    try {
      const lp = lockPath(orchDir);
      let stat;
      try { stat = fs.statSync(lp); } catch {
        return { ok: false, reason: "registry.lock no longer exists; nothing to recover." };
      }

      // Verify fingerprint
      const fp = `${stat.ino}:${stat.dev}:${stat.size}:${stat.mtime.getTime()}`;
      if (fp !== fingerprint) {
        return { ok: false, reason: `Fingerprint mismatch. Current: "${fp}", expected: "${fingerprint}". Lock may have changed.` };
      }

      if (shape === "A") {
        // Confirm the lock is still stale/dead
        if ((_now() - stat.mtimeMs) < LOCK_STALE_MS) {
          return { ok: false, reason: "Lock is no longer stale; recover-lock A is not needed." };
        }
        let content;
        try { content = JSON.parse(fs.readFileSync(lp, "utf8")); } catch { content = null; }
        if (!content) return { ok: false, reason: "Lock content is unparseable. Use shape B instead." };
        const dest = lp + ".takeover-" + ownerToken;
        fs.renameSync(lp, dest);
        return { ok: true, shape: "A", renamed: dest };
      }

      if (shape === "B") {
        // Confirm content is still unparseable
        let parseable = false;
        try { JSON.parse(fs.readFileSync(lp, "utf8")); parseable = true; } catch { /* expected */ }
        if (parseable) return { ok: false, reason: "Lock content is now valid JSON. Use shape A if stale." };
        const dest = lp + ".takeover-" + ownerToken;
        fs.renameSync(lp, dest);
        return { ok: true, shape: "B", renamed: dest };
      }
    } finally {
      // Release gate lock
      try {
        const rs = fs.statSync(recLock);
        if (rs.ino === gateStat.ino && rs.dev === gateStat.dev) {
          fs.unlinkSync(recLock);
        }
      } catch { /* ignore */ }
    }
  }

  if (shape === "C") {
    if (!ownerToken) throw new Error("recover-lock C requires --owner-token.");
    const mutex = acquireRegistryMutex(orchDir);
    try {
      const claims = loadClaims(orchDir);
      const before = claims.length;
      const after = claims.filter((c) => c.ownerToken !== ownerToken);
      saveClaims(orchDir, after);
      return { ok: true, shape: "C", removed: before - after.length };
    } finally {
      releaseRegistryMutex(orchDir, mutex.ownerToken, mutex.ino, mutex.dev);
    }
  }

  if (shape === "D") {
    const mutex = acquireRegistryMutex(orchDir);
    try {
      const before = loadClaims(orchDir).length;
      saveClaims(orchDir, []);
      return { ok: true, shape: "D", removed: before };
    } finally {
      releaseRegistryMutex(orchDir, mutex.ownerToken, mutex.ino, mutex.dev);
    }
  }

  throw new Error(`Unknown recover-lock shape: "${shape}". Must be A, B, C, or D.`);
}

// ---------------------------------------------------------------------------
// Release claim
// ---------------------------------------------------------------------------

/** Remove a specific claim (call after Codex task completes). */
export function releaseClaim(ownerToken) {
  const orchDir = resolveOrchestrationDir();
  const mutex = acquireRegistryMutex(orchDir);
  try {
    const claims = loadClaims(orchDir);
    saveClaims(orchDir, claims.filter((c) => c.ownerToken !== ownerToken));
  } finally {
    releaseRegistryMutex(orchDir, mutex.ownerToken, mutex.ino, mutex.dev);
  }
}

// ---------------------------------------------------------------------------
// CLI entry point
// ---------------------------------------------------------------------------

function parseCliArgs(argv) {
  const args = argv.slice(2);
  const subcommand = args[0];
  const opts = {};
  const positionals = [];
  for (let i = 1; i < args.length; i++) {
    if (args[i].startsWith("--")) {
      const key = args[i].slice(2);
      const val = args[i + 1] && !args[i + 1].startsWith("--") ? args[++i] : true;
      opts[key] = val;
    } else {
      positionals.push(args[i]);
    }
  }
  return { subcommand, opts, positionals };
}

async function main() {
  const { subcommand, opts, positionals } = parseCliArgs(process.argv);
  const cwd = opts.cwd || process.cwd();

  let companionPath = opts["companion-path"] || null;
  if (!companionPath && subcommand !== "recover-lock" && subcommand !== "active") {
    companionPath = resolveCompanionPath();
  }

  try {
    let result;
    switch (subcommand) {
      case "launch":
        result = cmdLaunch({
          companionPath,
          cwd,
          prompt: positionals[0] || opts.prompt,
          targetRoots: opts["target-roots"] ? opts["target-roots"].split(",") : null,
          write: opts.write === true || opts.write === "true",
          model: opts.model || null,
          effort: opts.effort || null
        });
        break;
      case "status":
        result = cmdStatus({ companionPath, cwd, jobId: positionals[0] || opts["job-id"] });
        break;
      case "result":
        result = cmdResult({ companionPath, cwd, jobId: positionals[0] || opts["job-id"] });
        break;
      case "candidate":
        result = cmdCandidate({
          companionPath,
          cwd,
          jobId: positionals[0] || opts["job-id"],
          ownerToken: opts["owner-token"] || null,
          targetRoots: opts["target-roots"] ? opts["target-roots"].split(",") : []
        });
        break;
      case "active":
        result = cmdActive();
        break;
      case "verify-request":
        result = cmdVerifyRequest({
          companionPath,
          cwd,
          jobId: positionals[0] || opts["job-id"],
          expectSha256: opts["expect-sha256"] || null,
          expectBytes: opts["expect-bytes"] ? Number(opts["expect-bytes"]) : null
        });
        break;
      case "recover-lock":
        result = cmdRecoverLock({
          shape: positionals[0] || opts.shape,
          ownerToken: opts["owner-token"] || null,
          fingerprint: opts.fingerprint || null,
          force: opts.force === true || opts.force === "true"
        });
        break;
      default:
        process.stderr.write(`Unknown subcommand: ${subcommand}\n`);
        process.stderr.write("Usage: orchestration-control.mjs <launch|status|result|candidate|active|verify-request|recover-lock> [options]\n");
        process.exitCode = 1;
        return;
    }
    process.stdout.write(JSON.stringify(result, null, 2) + "\n");
  } catch (err) {
    process.stderr.write(`${err.message}\n`);
    process.exitCode = 1;
  }
}

// Only run main when executed directly (not imported as a module in tests).
const isMain = process.argv[1] && path.resolve(process.argv[1]) === path.resolve(new URL(import.meta.url).pathname.replace(/^\/([A-Z]:)/, "$1"));
if (isMain) { main(); }

