import fs from "node:fs";
import path from "node:path";
import { randomBytes } from "node:crypto";

import { atomicWriteJson, dataRoot, ensureDirectory, nowIso, readJson } from "./common.mjs";

export const DEFAULT_LEASE_MS = 60 * 60 * 1000;
export const RUN_MUTEX_LEASE_MS = 2 * 60 * 1000;

export class ActiveRunError extends Error {
  constructor(lock) {
    super(`auto-review-execute already has an active run: ${lock.runId}`);
    this.name = "ActiveRunError";
    this.lock = lock;
  }
}

function lockFile(root = dataRoot()) {
  return path.join(root, "global.lock");
}

function token() {
  return randomBytes(16).toString("hex");
}

function isExpired(lock, at = Date.now()) {
  return !lock?.leaseExpiresAt || Number.isNaN(Date.parse(lock.leaseExpiresAt)) || Date.parse(lock.leaseExpiresAt) <= at;
}

function unreadableLockIsExpired(lockPath, leaseMs, at = Date.now()) {
  try {
    return at - fs.statSync(lockPath).mtimeMs >= leaseMs;
  } catch (error) {
    if (error.code === "ENOENT") return true;
    throw error;
  }
}

function readLock(lockPath) {
  try {
    return readJson(lockPath);
  } catch {
    return null;
  }
}

function writeNewExclusive(lockPath, content) {
  const descriptor = fs.openSync(lockPath, "wx");
  try {
    fs.writeFileSync(descriptor, `${JSON.stringify(content, null, 2)}\n`, "utf8");
  } finally {
    fs.closeSync(descriptor);
  }
}

function safelyArchive(lockPath, suffix) {
  const archived = `${lockPath}.${suffix}.${Date.now()}.${randomBytes(4).toString("hex")}`;
  fs.renameSync(lockPath, archived);
  return archived;
}

/**
 * Acquire the persistent admission lock for one run. The lock intentionally
 * outlives trigger-review.mjs: the Claude session owns progression by polling
 * state.json, so PID liveness is not a valid expiration signal.
 */
export function acquireGlobalRunLock({
  runId,
  stateFile,
  root = dataRoot(),
  leaseMs = DEFAULT_LEASE_MS,
  onExpired = null
}) {
  ensureDirectory(root);
  const target = lockFile(root);
  const ownerToken = token();
  const createdAt = nowIso();
  const lock = {
    schemaVersion: 1,
    runId,
    stateFile: path.resolve(stateFile),
    ownerToken,
    pid: process.pid,
    createdAt,
    leaseExpiresAt: new Date(Date.now() + leaseMs).toISOString()
  };

  for (let attempt = 0; attempt < 3; attempt += 1) {
    try {
      writeNewExclusive(target, lock);
      return { ...lock, path: target, acquired: true };
    } catch (error) {
      if (error.code !== "EEXIST") throw error;
    }

    const existing = readLock(target);
    if (existing?.runId === runId && existing?.stateFile === lock.stateFile) {
      const renewed = {
        ...existing,
        leaseExpiresAt: new Date(Date.now() + leaseMs).toISOString(),
        lastRenewedAt: nowIso()
      };
      atomicWriteJson(target, renewed);
      return { ...renewed, path: target, acquired: false };
    }

    if (!existing) {
      if (unreadableLockIsExpired(target, leaseMs)) {
        throw new Error(`global.lock is corrupt; manual recovery is required before takeover: ${target}`);
      }
      throw new Error(`global.lock is unreadable and has not expired: ${target}`);
    }
    if (existing && !isExpired(existing)) {
      throw new ActiveRunError(existing);
    }

    // Cancel stale Codex work before admitting a replacement run. The callback
    // is synchronous so a crash cannot leave a newly admitted run behind it.
    if (typeof onExpired === "function") onExpired(existing);
    try {
      safelyArchive(target, "expired");
    } catch (error) {
      if (error.code !== "ENOENT") throw error;
    }
  }
  throw new Error("Could not acquire global.lock after stale-lock takeover attempts");
}

export function renewGlobalRunLock(lock, { leaseMs = DEFAULT_LEASE_MS } = {}) {
  const current = readLock(lock.path);
  if (!current || current.runId !== lock.runId || current.ownerToken !== lock.ownerToken) {
    throw new Error("Cannot renew a global lock that is no longer owned by this run");
  }
  const renewed = {
    ...current,
    leaseExpiresAt: new Date(Date.now() + leaseMs).toISOString(),
    lastRenewedAt: nowIso()
  };
  atomicWriteJson(lock.path, renewed);
  return { ...renewed, path: lock.path };
}

export function releaseGlobalRunLock({ runId, ownerToken, root = dataRoot() }) {
  const target = lockFile(root);
  if (!fs.existsSync(target)) return false;
  const current = readLock(target);
  if (!current || current.runId !== runId || current.ownerToken !== ownerToken) return false;
  const archived = safelyArchive(target, "released");
  try {
    fs.unlinkSync(archived);
  } catch {
    // The archived lock is inert; retain it if deletion is temporarily denied.
  }
  return true;
}

function mutexPath(runDir) {
  return path.join(runDir, "run.lock");
}

/** Serialise short state transitions. Never hold this mutex while polling or launching Codex. */
export function withRunMutex(runDir, callback, { leaseMs = RUN_MUTEX_LEASE_MS } = {}) {
  ensureDirectory(runDir);
  const target = mutexPath(runDir);
  const ownerToken = token();
  let descriptor;
  try {
    descriptor = fs.openSync(target, "wx");
  } catch (error) {
    if (error.code !== "EEXIST") throw error;
    const existing = readLock(target);
    if (existing && !isExpired(existing)) {
      throw new Error(`run state transition is already in progress for ${runDir}`);
    }
    try {
      safelyArchive(target, "stale");
    } catch (archiveError) {
      if (archiveError.code !== "ENOENT") throw archiveError;
    }
    descriptor = fs.openSync(target, "wx");
  }

  const lock = {
    schemaVersion: 1,
    pid: process.pid,
    ownerToken,
    createdAt: nowIso(),
    leaseExpiresAt: new Date(Date.now() + leaseMs).toISOString()
  };
  try {
    fs.writeFileSync(descriptor, `${JSON.stringify(lock)}\n`, "utf8");
  } finally {
    fs.closeSync(descriptor);
  }

  try {
    return callback();
  } finally {
    const current = readLock(target);
    if (current?.ownerToken === ownerToken) {
      try {
        fs.unlinkSync(target);
      } catch {
        // A later transition will recover an expired mutex if necessary.
      }
    }
  }
}
