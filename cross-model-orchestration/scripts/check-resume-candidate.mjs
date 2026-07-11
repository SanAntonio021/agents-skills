#!/usr/bin/env node

import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";

function fail(message, detail = null, status = 1) {
  console.log(JSON.stringify({ ok: false, message, detail }, null, 2));
  process.exit(status);
}

const expectedThreadId = process.argv[2] || null;
const registryPath = path.join(os.homedir(), ".claude", "plugins", "installed_plugins.json");

if (!fs.existsSync(registryPath)) {
  fail("Claude plugin registry not found.", registryPath);
}

let registry;
try {
  registry = JSON.parse(fs.readFileSync(registryPath, "utf8"));
} catch (error) {
  fail("Claude plugin registry is not valid JSON.", error.message);
}

const installs = registry.plugins?.["codex@openai-codex"] ?? [];
const install = installs.find((item) => item.scope === "user") ?? installs.at(-1);
if (!install?.installPath) {
  fail("codex@openai-codex is not installed.");
}

const companion = path.join(install.installPath, "scripts", "codex-companion.mjs");
if (!fs.existsSync(companion)) {
  fail("Codex companion script not found.", companion);
}

const child = spawnSync(
  process.execPath,
  [companion, "task-resume-candidate", "--json", "--cwd", process.cwd()],
  { encoding: "utf8", env: process.env, windowsHide: true }
);

if (child.status !== 0) {
  fail("Unable to query the Codex resume candidate.", (child.stderr || child.stdout).trim());
}

let payload;
try {
  payload = JSON.parse(child.stdout);
} catch (error) {
  fail("Codex resume candidate returned invalid JSON.", error.message);
}

const candidateThreadId = payload.candidate?.threadId ?? null;
const matches = Boolean(candidateThreadId) &&
  (expectedThreadId === null || candidateThreadId === expectedThreadId);

const result = {
  ok: matches,
  available: Boolean(payload.available),
  expectedThreadId,
  candidateThreadId,
  candidateJobId: payload.candidate?.id ?? null,
  candidateStatus: payload.candidate?.status ?? null,
  pluginVersion: install.version ?? null
};

if (!matches) {
  result.message = candidateThreadId
    ? "Codex resume candidate does not match the recorded orchestration thread."
    : "No resumable Codex task thread is available for this Claude session.";
}

console.log(JSON.stringify(result, null, 2));
process.exit(matches ? 0 : 2);

