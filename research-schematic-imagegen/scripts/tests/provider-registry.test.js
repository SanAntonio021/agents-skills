import assert from "node:assert/strict";
import { DatabaseSync } from "node:sqlite";
import { mkdtemp, mkdir, readdir, readFile, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import {
  defaultProviderRegistryPath,
  loadRegisteredCcSwitchImageProvider,
  registerCcSwitchImageProvider,
} from "../provider-registry.js";
import { inspectCcSwitchImageProviderCandidate } from "../ccswitch.js";
import { apiKey, loadRuntimeEnv, runtimeInfo } from "../shared.js";

const PROVIDER_ID = "provider-jarvis";
const PROVIDER_NAME = "Jarvis Image";
const TEST_KEY = "cc-switch-test-key";

function createProviderDatabase(root) {
  const dbPath = path.join(root, "cc-switch.db");
  const db = new DatabaseSync(dbPath);
  try {
    db.exec(`
      CREATE TABLE providers (
        id TEXT,
        name TEXT,
        app_type TEXT,
        website_url TEXT,
        provider_type TEXT,
        settings_config TEXT,
        is_current INTEGER
      )
    `);
    db.prepare(`
      INSERT INTO providers (id, name, app_type, website_url, provider_type, settings_config, is_current)
      VALUES (?, ?, ?, ?, ?, ?, ?)
    `).run(
      PROVIDER_ID,
      PROVIDER_NAME,
      "codex",
      "https://example.test",
      null,
      JSON.stringify({
        config: 'base_url = "https://example.test/v1"\nmodel = "gpt-image-2"',
        auth: { OPENAI_API_KEY: TEST_KEY },
      }),
      0,
    );
  } finally {
    db.close();
  }
  return dbPath;
}

function modelFetch(modelIds = ["gpt-image-2"]) {
  return async (url, options) => {
    assert.equal(url, "https://example.test/v1/models");
    assert.equal(options.headers.authorization, `Bearer ${TEST_KEY}`);
    return {
      ok: true,
      status: 200,
      json: async () => ({ data: modelIds.map((id) => ({ id })) }),
    };
  };
}

function registry(alias = "贾维斯", expectedName = PROVIDER_NAME) {
  return {
    version: 1,
    providers: [{
      alias,
      provider_id: PROVIDER_ID,
      app_type: "codex",
      expected_name: expectedName,
      default_model: "gpt-image-2",
    }],
  };
}

async function writeRegistry(root, value = registry()) {
  const registryPath = defaultProviderRegistryPath(path.join(root, "config"));
  await mkdir(path.dirname(registryPath), { recursive: true });
  await writeFile(registryPath, JSON.stringify(value, null, 2));
  return registryPath;
}

test("registration validates a CC Switch candidate and writes only public registry fields", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "research-schematic-registry-"));
  try {
    const dbPath = createProviderDatabase(root);
    const registryPath = path.join(root, "config", "providers.json");
    const result = await registerCcSwitchImageProvider({
      alias: "贾维斯",
      providerId: PROVIDER_ID,
      registryPath,
      dbPath,
      fetchImpl: modelFetch(),
      timeoutMs: 1,
    });
    assert.equal(result.entry.expected_name, PROVIDER_NAME);
    assert.equal(Object.hasOwn(result.provider, "api_key"), false);
    const saved = JSON.parse(await readFile(registryPath, "utf8"));
    assert.deepEqual(saved, registry());
    const temporaryFiles = (await readdir(path.dirname(registryPath))).filter((name) => name.endsWith(".tmp"));
    assert.deepEqual(temporaryFiles, []);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("candidate inspection is restricted to one explicit provider ID", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "research-schematic-candidate-"));
  try {
    const dbPath = createProviderDatabase(root);
    const result = await inspectCcSwitchImageProviderCandidate({
      dbPath,
      providerId: PROVIDER_ID,
      fetchImpl: modelFetch(),
      timeoutMs: 1,
    });
    assert.equal(result.provider.id, PROVIDER_ID);
    assert.equal(result.provider.name, PROVIDER_NAME);
    assert.equal(Object.hasOwn(result.provider, "api_key"), false);
    await assert.rejects(
      inspectCcSwitchImageProviderCandidate({ dbPath, providerId: "not-registered", fetchImpl: modelFetch(), timeoutMs: 1 }),
      /CC Switch provider not found: not-registered/,
    );
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("normal Cici Switch routing requires a registered alias and validates the requested model", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "research-schematic-routing-"));
  try {
    const dbPath = createProviderDatabase(root);
    const registryPath = await writeRegistry(root);
    const selected = await loadRegisteredCcSwitchImageProvider({
      registryPath,
      dbPath,
      alias: "贾维斯",
      fetchImpl: modelFetch(["gpt-image-2", "gpt-image-2-cf"]),
      timeoutMs: 1,
    });
    assert.equal(selected.alias, "贾维斯");
    assert.equal(selected.model, "gpt-image-2");
    assert.equal(selected.public_provider.name, PROVIDER_NAME);
    assert.equal(Object.hasOwn(selected.public_provider, "api_key"), false);
    const cfSelected = await loadRegisteredCcSwitchImageProvider({
      registryPath,
      dbPath,
      alias: "贾维斯",
      model: "gpt-image-2-cf",
      fetchImpl: modelFetch(["gpt-image-2", "gpt-image-2-cf"]),
      timeoutMs: 1,
    });
    assert.equal(cfSelected.model, "gpt-image-2-cf");
    await assert.rejects(
      loadRegisteredCcSwitchImageProvider({ registryPath, dbPath, fetchImpl: modelFetch(), timeoutMs: 1 }),
      /Available aliases: 贾维斯/,
    );
    await assert.rejects(
      loadRegisteredCcSwitchImageProvider({
        registryPath,
        dbPath,
        alias: "贾维斯",
        model: "gpt-image-2-cf",
        fetchImpl: modelFetch(["gpt-image-2"]),
        timeoutMs: 1,
      }),
      /does not currently expose gpt-image-2-cf/,
    );
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("normal routing does not auto-load the legacy direct env file", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "research-schematic-runtime-"));
  const envKeys = [
    "ENABLE_RESEARCH_IMAGEGEN",
    "RESEARCH_IMAGE_API_KEY",
    "RESEARCH_IMAGE_BASE_URL",
    "RESEARCH_IMAGE_MODEL",
    "RESEARCH_IMAGE_BACKEND",
    "RESEARCH_IMAGE_PROVIDER",
    "RESEARCH_IMAGE_ENV_FILE",
    "RESEARCH_IMAGE_CC_SWITCH_PROVIDER_ID",
    "RESEARCH_IMAGE_CC_SWITCH_PROVIDER_NAME",
  ];
  const before = Object.fromEntries(envKeys.map((key) => [key, process.env[key]]));
  try {
    for (const key of envKeys) delete process.env[key];
    const dbPath = createProviderDatabase(root);
    const configDir = path.join(root, "config");
    const registryPath = await writeRegistry(root);
    await writeFile(path.join(configDir, "hangzhale.env"), "RESEARCH_IMAGE_API_KEY=legacy-direct-key\nRESEARCH_IMAGE_BASE_URL=https://legacy.example/v1\n");
    await loadRuntimeEnv({
      configDir,
      registryPath,
      dbPath,
      providerAlias: "贾维斯",
      fetchImpl: modelFetch(),
      timeoutMs: 1,
    });
    assert.equal(apiKey(), TEST_KEY);
    assert.equal(runtimeInfo().backend, "ccswitch");
    assert.equal(runtimeInfo().env_file, null);
    assert.equal(runtimeInfo().provider_alias, "贾维斯");
  } finally {
    for (const key of envKeys) {
      if (before[key] === undefined) delete process.env[key];
      else process.env[key] = before[key];
    }
    await rm(root, { recursive: true, force: true });
  }
});
