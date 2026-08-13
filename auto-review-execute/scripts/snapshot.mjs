import fs from "node:fs";
import path from "node:path";

import { isSameOrDescendant, normalizeForComparison, sha256File } from "./common.mjs";

function relativeKey(root, candidate) {
  return path.relative(root, candidate).split(path.sep).join("/");
}

function recordFor(filePath, root) {
  const stat = fs.lstatSync(filePath);
  const relativePath = relativeKey(root, filePath);
  if (stat.isSymbolicLink()) {
    return {
      path: relativePath,
      type: "symlink",
      linkTarget: fs.readlinkSync(filePath)
    };
  }
  if (stat.isDirectory()) {
    return { path: relativePath, type: "directory" };
  }
  if (stat.isFile()) {
    return {
      path: relativePath,
      type: "file",
      size: stat.size,
      sha256: sha256File(filePath)
    };
  }
  return { path: relativePath, type: "other" };
}

function walk(root, candidate, entries) {
  const record = recordFor(candidate, root);
  entries.push(record);
  if (record.type !== "directory") return;
  const children = fs.readdirSync(candidate, { withFileTypes: true }).sort((a, b) => a.name.localeCompare(b.name));
  for (const child of children) walk(root, path.join(candidate, child.name), entries);
}

/**
 * Capture every entry, including directories and symlinks. Symlinks are
 * represented but never followed; this catches link introduction and escape.
 */
export function takeSnapshot(targetRoots) {
  if (!Array.isArray(targetRoots) || targetRoots.length === 0) throw new Error("Snapshot needs at least one target root");
  const roots = [];
  for (const item of targetRoots) {
    const root = path.resolve(item);
    let rootStat;
    try {
      rootStat = fs.lstatSync(root);
    } catch (error) {
      if (error.code === "ENOENT") {
        roots.push({ root: normalizeForComparison(root), rootStatus: "missing", entries: [] });
        continue;
      }
      throw error;
    }
    if (rootStat.isSymbolicLink()) {
      roots.push({
        root: normalizeForComparison(root),
        rootStatus: "symlink",
        rootLinkTarget: fs.readlinkSync(root),
        entries: []
      });
      continue;
    }
    if (!rootStat.isDirectory()) {
      roots.push({ root: normalizeForComparison(root), rootStatus: "other", entries: [] });
      continue;
    }
    const entries = [];
    const children = fs.readdirSync(root, { withFileTypes: true }).sort((a, b) => a.name.localeCompare(b.name));
    for (const child of children) walk(root, path.join(root, child.name), entries);
    roots.push({ root: normalizeForComparison(root), rootStatus: "directory", entries });
  }
  return { schemaVersion: 1, createdAt: new Date().toISOString(), roots };
}

function mapEntries(snapshot) {
  const map = new Map();
  for (const root of snapshot.roots || []) {
    map.set(`${root.root}/`, {
      root: root.root,
      path: "",
      type: "root",
      rootStatus: root.rootStatus,
      rootLinkTarget: root.rootLinkTarget ?? null
    });
    for (const entry of root.entries || []) {
      map.set(`${root.root}/${entry.path}`, { root: root.root, ...entry });
    }
  }
  return map;
}

function sameEntry(before, after) {
  return JSON.stringify(before) === JSON.stringify(after);
}

/** Detect creations, deletions, modifications, type changes and symlink changes. */
export function diffSnapshots(before, after) {
  const beforeEntries = mapEntries(before);
  const afterEntries = mapEntries(after);
  const added = [];
  const deleted = [];
  const modified = [];
  const symlinkChanges = [];

  for (const [key, previous] of beforeEntries) {
    const current = afterEntries.get(key);
    if (!current) {
      deleted.push(previous);
      continue;
    }
    if (!sameEntry(previous, current)) {
      const item = { before: previous, after: current };
      modified.push(item);
      if (previous.type === "symlink" || current.type === "symlink") symlinkChanges.push(item);
    }
  }
  for (const [key, current] of afterEntries) {
    if (!beforeEntries.has(key)) {
      added.push(current);
      if (current.type === "symlink") symlinkChanges.push({ before: null, after: current });
    }
  }
  const renamed = [];
  const consumedAdded = new Set();
  const consumedDeleted = new Set();
  for (let deletedIndex = 0; deletedIndex < deleted.length; deletedIndex += 1) {
    const previous = deleted[deletedIndex];
    if (previous.type !== "file" && previous.type !== "symlink") continue;
    const matchIndex = added.findIndex((current, index) => {
      if (consumedAdded.has(index) || current.type !== previous.type) return false;
      if (previous.type === "symlink") return current.linkTarget === previous.linkTarget;
      return current.size === previous.size && current.sha256 === previous.sha256;
    });
    if (matchIndex !== -1) {
      consumedAdded.add(matchIndex);
      consumedDeleted.add(deletedIndex);
      renamed.push({ before: previous, after: added[matchIndex] });
    }
  }
  return { added, deleted, modified, renamed, symlinkChanges };
}

export function changedEntries(diff) {
  return [
    ...diff.added.map((entry) => ({ before: null, after: entry })),
    ...diff.deleted.map((entry) => ({ before: entry, after: null })),
    ...diff.modified
  ];
}

export function changedEntryPath(change) {
  const entry = change.after || change.before;
  return path.join(entry.root, ...entry.path.split("/"));
}

export function findOutOfScopeChanges(diff, allowedPaths) {
  return changedEntries(diff).filter((change) => {
    const candidate = changedEntryPath(change);
    return !allowedPaths.some((allowedPath) => isSameOrDescendant(candidate, allowedPath));
  });
}

/** A symlink anywhere in the changed set fails validation, even within scope. */
export function findSymlinkViolations(diff) {
  return [
    ...diff.symlinkChanges,
    ...changedEntries(diff).filter((change) => change.before?.rootStatus === "symlink" || change.after?.rootStatus === "symlink")
  ];
}

/** Reject pre-existing links too: they could otherwise route a permitted write outside a target root. */
export function assertSnapshotHasNoSymlinks(snapshot) {
  const links = [];
  for (const root of snapshot.roots || []) {
    if (root.rootStatus === "symlink") links.push(root.root);
    for (const entry of root.entries || []) {
      if (entry.type === "symlink") links.push(path.join(root.root, ...entry.path.split("/")));
    }
  }
  if (links.length > 0) throw new Error(`Target roots contain symbolic links and cannot be used for execution: ${links.join(", ")}`);
}
