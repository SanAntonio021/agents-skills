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
