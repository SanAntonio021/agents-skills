import { createHash, randomBytes } from "node:crypto";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

export function dataRoot() {
  return path.resolve(
    process.env.AUTO_REVIEW_EXECUTE_HOME ||
      path.join(process.env.LOCALAPPDATA || path.join(os.homedir(), "AppData", "Local"), "auto-review-execute")
  );
}

export function nowIso() {
  return new Date().toISOString();
}

export function makeRunId(date = new Date()) {
  const stamp = date.toISOString().replace(/[-:]/g, "").replace(/\.\d{3}Z$/, "").replace("T", "-");
  return `run-${stamp}-${randomBytes(3).toString("hex")}`;
}

export function sha256Text(value) {
  return createHash("sha256").update(value, "utf8").digest("hex");
}

export function sha256Buffer(value) {
  return createHash("sha256").update(value).digest("hex");
}

export function sha256File(filePath) {
  return sha256Buffer(fs.readFileSync(filePath));
}

export function fileBytes(filePath) {
  return fs.statSync(filePath).size;
}

export function ensureDirectory(directory) {
  fs.mkdirSync(directory, { recursive: true });
  return directory;
}

export function atomicWriteFile(filePath, content, encoding = "utf8") {
  const directory = path.dirname(filePath);
  ensureDirectory(directory);
  const tempPath = path.join(
    directory,
    `.${path.basename(filePath)}.${process.pid}.${randomBytes(6).toString("hex")}.tmp`
  );
  try {
    fs.writeFileSync(tempPath, content, encoding);
    fs.renameSync(tempPath, filePath);
  } finally {
    try {
      if (fs.existsSync(tempPath)) fs.unlinkSync(tempPath);
    } catch {
      // A failed cleanup must not hide the primary write error.
    }
  }
}

export function atomicWriteJson(filePath, value) {
  atomicWriteFile(filePath, `${JSON.stringify(value, null, 2)}\n`);
}

export function readJson(filePath) {
  return JSON.parse(fs.readFileSync(filePath, "utf8"));
}

export function normalizeForComparison(value) {
  let resolved = path.resolve(value);
  if (process.platform === "win32") resolved = resolved.toLowerCase();
  return resolved.replace(/[\\/]+$/, "") || resolved;
}

export function isSameOrDescendant(candidate, root) {
  const candidatePath = normalizeForComparison(candidate);
  const rootPath = normalizeForComparison(root);
  return candidatePath === rootPath || candidatePath.startsWith(`${rootPath}${path.sep}`);
}

export function assertRegularFile(filePath, label = "file") {
  const stat = fs.lstatSync(filePath);
  if (stat.isSymbolicLink()) throw new Error(`${label} must not be a symbolic link: ${filePath}`);
  if (!stat.isFile()) throw new Error(`${label} must be a regular file: ${filePath}`);
  return stat;
}

export function assertDirectoryNotLink(directory, label = "directory") {
  const stat = fs.lstatSync(directory);
  if (stat.isSymbolicLink()) throw new Error(`${label} must not be a symbolic link: ${directory}`);
  if (!stat.isDirectory()) throw new Error(`${label} must be a directory: ${directory}`);
  return stat;
}

export function assertNoSymlinkSegments(candidate, root) {
  const absoluteCandidate = path.resolve(candidate);
  const absoluteRoot = path.resolve(root);
  if (!isSameOrDescendant(absoluteCandidate, absoluteRoot)) {
    throw new Error(`Path is outside its declared root: ${absoluteCandidate}`);
  }
  assertDirectoryNotLink(absoluteRoot, "target root");
  const relative = path.relative(absoluteRoot, absoluteCandidate);
  if (!relative) return;
  let cursor = absoluteRoot;
  for (const component of relative.split(path.sep)) {
    cursor = path.join(cursor, component);
    if (!fs.existsSync(cursor)) break;
    const stat = fs.lstatSync(cursor);
    if (stat.isSymbolicLink()) throw new Error(`Symbolic-link path segment is not allowed: ${cursor}`);
  }
}

export function commonAncestor(paths) {
  if (!Array.isArray(paths) || paths.length === 0) throw new Error("commonAncestor requires at least one path");
  const split = paths.map((item) => path.resolve(item).split(path.sep));
  const common = [];
  for (let index = 0; ; index += 1) {
    const value = split[0][index];
    if (value == null || split.some((parts) => parts[index] !== value)) break;
    common.push(value);
  }
  const result = common.join(path.sep);
  if (!result) return path.parse(path.resolve(paths[0])).root;
  return result.endsWith(":") ? `${result}${path.sep}` : result;
}

export function ensureWithinCwd(targetRoots, cwd = process.cwd()) {
  const normalizedCwd = path.resolve(cwd);
  for (const targetRoot of targetRoots) {
    if (!isSameOrDescendant(targetRoot, normalizedCwd)) {
      throw new Error(`Target root is outside the current Claude session cwd: ${targetRoot}`);
    }
  }
  return normalizedCwd;
}

export function singleLineJson(value) {
  return JSON.stringify(value).replace(/[\r\n]/g, "");
}
