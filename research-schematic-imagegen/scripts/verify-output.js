#!/usr/bin/env node
import path from "node:path";
import process from "node:process";
import { readdir, readFile } from "node:fs/promises";

function parse(argv) {
  const cfg = { json: false };
  const valued = new Map([
    ["--dir", "dir"],
    ["--manifest", "manifest"],
    ["--expected-count", "expectedCount"],
    ["--width", "width"],
    ["--height", "height"],
  ]);
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === "--json") cfg.json = true;
    else if (valued.has(arg)) {
      const value = argv[++i];
      if (!value) throw new Error(`Missing value for ${arg}`);
      cfg[valued.get(arg)] = value;
    } else throw new Error(`Unknown option: ${arg}`);
  }
  if (!cfg.dir) throw new Error("--dir is required");
  for (const key of ["expectedCount", "width", "height"]) {
    if (cfg[key] !== undefined) cfg[key] = Number(cfg[key]);
  }
  return cfg;
}

async function readManifest(manifestPath) {
  const raw = JSON.parse(await readFile(path.resolve(manifestPath), "utf8"));
  const files = Array.isArray(raw) ? raw : raw?.files;
  if (!Array.isArray(files) || files.some((item) => typeof item !== "string" || !item.trim())) {
    throw new Error("manifest must be a JSON array or an object with a string files array");
  }
  const normalized = files.map((item) => item.trim());
  if (new Set(normalized).size !== normalized.length) {
    throw new Error("manifest contains duplicate file names");
  }
  return normalized;
}

function resolveManifestFile(dir, fileName) {
  if (path.basename(fileName) !== fileName) {
    throw new Error(`manifest file must be a direct child of --dir: ${fileName}`);
  }
  const resolvedDir = path.resolve(dir);
  const resolvedFile = path.resolve(resolvedDir, fileName);
  const relative = path.relative(resolvedDir, resolvedFile);
  if (!relative || relative.startsWith(".." + path.sep) || path.isAbsolute(relative)) {
    throw new Error(`manifest file is outside --dir: ${fileName}`);
  }
  if (!resolvedFile.toLowerCase().endsWith(".png")) {
    throw new Error(`manifest file is not a PNG: ${fileName}`);
  }
  return { relative, resolvedFile };
}

async function pngDimensions(filePath) {
  const bytes = await readFile(filePath);
  const signature = Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]);
  if (bytes.length < 24 || !bytes.subarray(0, 8).equals(signature)) {
    throw new Error("not a valid PNG file");
  }
  return { width: bytes.readUInt32BE(16), height: bytes.readUInt32BE(20) };
}

async function run() {
  const cfg = parse(process.argv.slice(2));
  const dir = path.resolve(cfg.dir);
  const directoryFiles = (await readdir(dir, { withFileTypes: true }))
    .filter((entry) => entry.isFile() && entry.name.toLowerCase().endsWith(".png"))
    .map((entry) => entry.name)
    .sort();
  const manifestFiles = cfg.manifest ? await readManifest(cfg.manifest) : null;
  const files = manifestFiles
    ? manifestFiles.map((fileName) => resolveManifestFile(dir, fileName))
    : directoryFiles.map((relative) => ({ relative, resolvedFile: path.join(dir, relative) }));
  const checks = [];
  const missingFiles = [];
  for (const file of files) {
    const item = { name: file.relative, ok: true };
    try {
      Object.assign(item, await pngDimensions(file.resolvedFile));
      if (cfg.width !== undefined && item.width !== cfg.width) item.ok = false;
      if (cfg.height !== undefined && item.height !== cfg.height) item.ok = false;
    } catch (error) {
      item.ok = false;
      item.error = error instanceof Error ? error.message : String(error);
      if (error?.code === "ENOENT") missingFiles.push(file.relative);
    }
    checks.push(item);
  }
  const selectedNames = new Set(files.map((file) => file.relative));
  const extraFiles = manifestFiles
    ? directoryFiles.filter((file) => !selectedNames.has(file))
    : [];
  const countOk = cfg.expectedCount === undefined || files.length === cfg.expectedCount;
  const result = {
    directory: dir,
    manifest: cfg.manifest ? path.resolve(cfg.manifest) : null,
    expected_count: cfg.expectedCount ?? null,
    actual_count: files.length,
    directory_png_count: directoryFiles.length,
    extra_files: extraFiles,
    missing_files: missingFiles,
    expected_width: cfg.width ?? null,
    expected_height: cfg.height ?? null,
    count_ok: countOk,
    files: checks,
    ok: countOk && checks.every((item) => item.ok),
  };
  if (cfg.json) console.log(JSON.stringify(result, null, 2));
  else {
    console.log(`directory: ${result.directory}`);
    console.log(`count: ${result.actual_count}${cfg.expectedCount === undefined ? "" : ` / ${cfg.expectedCount}`}`);
    if (result.extra_files.length) console.log(`unmanaged PNGs: ${result.extra_files.join(", ")}`);
    for (const item of checks) console.log(`${item.ok ? "OK" : "FAIL"} ${item.name} ${item.width || "?"}x${item.height || "?"}`);
  }
  if (!result.ok) process.exitCode = 1;
}

run().catch((error) => {
  console.error(error instanceof Error ? error.message : String(error));
  process.exit(2);
});
