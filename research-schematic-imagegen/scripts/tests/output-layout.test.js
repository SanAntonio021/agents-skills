import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdtemp, readFile, readdir, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";

const shared = new URL("../shared.js", import.meta.url).href;

test("default prompt and image writes stay inside one Chinese process directory", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "图件目录-"));
  const env = { ...process.env };
  delete env.RESEARCH_IMAGE_OUTPUT_ROOT;
  try {
    execFileSync(process.execPath, ["--input-type=module", "-e", `
      const { savePrompt, saveImage, buildDefaultImagePath } = await import(${JSON.stringify(shared)});
      await savePrompt("技术合同", null, "sample");
      await saveImage(buildDefaultImagePath("generate", "sample"), Buffer.from("offline fixture"));
    `], { cwd: root, env });
    assert.deepEqual(await readdir(root), ["过程文件"]);
    assert.deepEqual((await readdir(path.join(root, "过程文件", "科研示意图"))).sort(), ["prompt", "working"]);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("explicit shared task directory is reused across separate generation sessions", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "跨技能图件-"));
  const taskRoot = path.join(root, "过程文件", "系统图_20260908_02");
  try {
    for (const hint of ["first", "continued"]) {
      execFileSync(process.execPath, ["--input-type=module", "-e", `
        const { savePrompt } = await import(${JSON.stringify(shared)});
        await savePrompt("合同", null, ${JSON.stringify(hint)});
      `], { cwd: root, env: { ...process.env, RESEARCH_IMAGE_OUTPUT_ROOT: taskRoot } });
    }
    assert.equal((await readdir(path.join(taskRoot, "prompt"))).length, 2);
    assert.deepEqual(await readdir(path.join(root, "过程文件")), ["系统图_20260908_02"]);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});
