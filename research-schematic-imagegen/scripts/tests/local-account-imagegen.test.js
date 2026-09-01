import assert from "node:assert/strict";
import { mkdtemp, mkdir, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import {
  buildCodexArgs,
  inspectPng,
  parseThreadId,
  resolveGeneratedImage,
} from "../generate-local-account.js";

const ONE_PIXEL_PNG = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=",
  "base64",
);

test("forces the signed-in image session onto the official provider", () => {
  const args = buildCodexArgs();
  assert.deepEqual(args.slice(0, 4), ["exec", "--ignore-user-config", "--ignore-rules", "--ephemeral"]);
  assert.ok(args.includes("--json"));
  assert.equal(args.at(-1), "-");
});

test("extracts the isolated task ID from Codex JSONL", () => {
  const threadId = "01a05ab0-9e95-7e72-ab67-19bc197abe1a";
  const jsonl = `diagnostic before json\n${JSON.stringify({ type: "thread.started", thread_id: threadId })}\n`;
  assert.equal(parseThreadId(jsonl), threadId);
});

test("accepts exactly one valid PNG from the isolated generated-images directory", async (t) => {
  const root = await mkdtemp(path.join(os.tmpdir(), "local-account-imagegen-"));
  t.after(() => rm(root, { recursive: true, force: true }));
  const threadId = "01a05ab0-9e95-7e72-ab67-19bc197abe1a";
  const threadDir = path.join(root, "generated_images", threadId);
  const imagePath = path.join(threadDir, "generated.png");
  await mkdir(threadDir, { recursive: true });
  await writeFile(imagePath, ONE_PIXEL_PNG);

  assert.equal(await resolveGeneratedImage({ codexHome: root, threadId }), imagePath);
  const info = await inspectPng(imagePath);
  assert.equal(info.width, 1);
  assert.equal(info.height, 1);
  assert.equal(info.bytes, ONE_PIXEL_PNG.length);
  assert.match(info.sha256, /^[0-9A-F]{64}$/);
});

test("fails closed when an isolated task produces more than one PNG", async (t) => {
  const root = await mkdtemp(path.join(os.tmpdir(), "local-account-imagegen-"));
  t.after(() => rm(root, { recursive: true, force: true }));
  const threadId = "01a05ab0-9e95-7e72-ab67-19bc197abe1a";
  const threadDir = path.join(root, "generated_images", threadId);
  await mkdir(threadDir, { recursive: true });
  await writeFile(path.join(threadDir, "first.png"), ONE_PIXEL_PNG);
  await writeFile(path.join(threadDir, "second.png"), ONE_PIXEL_PNG);

  await assert.rejects(
    resolveGeneratedImage({ codexHome: root, threadId }),
    /Expected one generated PNG but found 2/,
  );
});
