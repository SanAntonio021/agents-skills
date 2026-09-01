import assert from "node:assert/strict";
import { execFile } from "node:child_process";
import { mkdtemp, mkdir, readFile, rm, stat, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { promisify } from "node:util";
import test from "node:test";

const execFileAsync = promisify(execFile);
const skillRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const verifier = path.join(skillRoot, "scripts", "verify-output.js");

function minimalPng(width, height) {
  const bytes = Buffer.alloc(24);
  Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]).copy(bytes, 0);
  bytes.writeUInt32BE(width, 16);
  bytes.writeUInt32BE(height, 20);
  return bytes;
}

test("manifest verifies current deliverables without touching existing PNGs", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "research-schematic-verify-"));
  const finalDir = path.join(root, "final");
  const manifestPath = path.join(root, "manifest.json");
  try {
    await mkdir(finalDir, { recursive: true });
    await writeFile(path.join(finalDir, "legacy.png"), minimalPng(640, 480));
    await writeFile(path.join(finalDir, "fig-a.png"), minimalPng(1536, 1024));
    await writeFile(path.join(finalDir, "fig-b.png"), minimalPng(1536, 1024));
    await writeFile(manifestPath, JSON.stringify({ files: ["fig-a.png", "fig-b.png"] }));
    const before = await readFile(path.join(finalDir, "legacy.png"));
    const beforeStat = await stat(path.join(finalDir, "legacy.png"));

    const { stdout } = await execFileAsync(process.execPath, [
      verifier,
      "--dir", finalDir,
      "--manifest", manifestPath,
      "--expected-count", "2",
      "--width", "1536",
      "--height", "1024",
      "--json",
    ], { cwd: skillRoot });
    const result = JSON.parse(stdout);

    assert.equal(result.ok, true);
    assert.equal(result.actual_count, 2);
    assert.equal(result.directory_png_count, 3);
    assert.deepEqual(result.extra_files, ["legacy.png"]);
    assert.deepEqual(await readFile(path.join(finalDir, "legacy.png")), before);
    const afterStat = await stat(path.join(finalDir, "legacy.png"));
    assert.equal(afterStat.size, beforeStat.size);
    assert.equal(afterStat.mtimeMs, beforeStat.mtimeMs);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("manifest object entries distinguish original and processed files with their own dimensions", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "research-schematic-mixed-size-"));
  const finalDir = path.join(root, "final");
  const manifestPath = path.join(root, "manifest.json");
  try {
    await mkdir(finalDir, { recursive: true });
    const originalPath = path.join(finalDir, "scene-original.png");
    const processedPath = path.join(finalDir, "scene-processed.png");
    await writeFile(originalPath, minimalPng(1672, 941));
    await writeFile(processedPath, minimalPng(2048, 1152));
    await writeFile(manifestPath, JSON.stringify({
      files: [
        { name: "scene-original.png", role: "original", width: 1672, height: 941 },
        { name: "scene-processed.png", role: "processed", width: 2048, height: 1152 },
      ],
    }));
    const originalBefore = await readFile(originalPath);
    const processedBefore = await readFile(processedPath);

    const { stdout } = await execFileAsync(process.execPath, [
      verifier,
      "--dir", finalDir,
      "--manifest", manifestPath,
      "--expected-count", "2",
      "--json",
    ], { cwd: skillRoot });
    const result = JSON.parse(stdout);

    assert.equal(result.ok, true);
    assert.equal(result.actual_count, 2);
    assert.equal(result.files[0].role, "original");
    assert.equal(result.files[0].expected_width, 1672);
    assert.equal(result.files[0].expected_height, 941);
    assert.equal(result.files[1].role, "processed");
    assert.equal(result.files[1].expected_width, 2048);
    assert.equal(result.files[1].expected_height, 1152);
    assert.deepEqual(await readFile(originalPath), originalBefore);
    assert.deepEqual(await readFile(processedPath), processedBefore);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("manifest object dimensions reject a processed file with the wrong actual size", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "research-schematic-size-mismatch-"));
  const finalDir = path.join(root, "final");
  const manifestPath = path.join(root, "manifest.json");
  try {
    await mkdir(finalDir, { recursive: true });
    await writeFile(path.join(finalDir, "scene-processed.png"), minimalPng(1672, 941));
    await writeFile(manifestPath, JSON.stringify({
      files: [
        { name: "scene-processed.png", role: "processed", width: 2048, height: 1152 },
      ],
    }));

    await assert.rejects(
      execFileAsync(process.execPath, [
        verifier,
        "--dir", finalDir,
        "--manifest", manifestPath,
        "--expected-count", "1",
        "--json",
      ], { cwd: skillRoot }),
      (error) => {
        const result = JSON.parse(error.stdout);
        assert.equal(result.ok, false);
        assert.equal(result.files[0].role, "processed");
        assert.equal(result.files[0].width, 1672);
        assert.equal(result.files[0].height, 941);
        assert.equal(result.files[0].expected_width, 2048);
        assert.equal(result.files[0].expected_height, 1152);
        return true;
      },
    );
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});
