import assert from "node:assert/strict";
import { DatabaseSync } from "node:sqlite";
import { mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { executeImageRequest, serializeImageRouteError } from "../shared.js";

const PROVIDERS = [
  { alias: "UESTC", id: "provider-uestc", name: "UESTC", baseUrl: "https://uestc.test/v1", key: "uestc-secret-key" },
  { alias: "贾维斯", id: "provider-jarvis", name: "Jarvis Image", baseUrl: "https://jarvis.test/v1", key: "jarvis-secret-key" },
  { alias: "夯炸了", id: "provider-hangzhale", name: "Hangzhale Image", baseUrl: "https://hangzhale.test/v1", key: "hangzhale-secret-key" },
];

const VALID_PNG = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 0x00]);

function createDatabase(root) {
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
    const insert = db.prepare(`
      INSERT INTO providers (id, name, app_type, website_url, provider_type, settings_config, is_current)
      VALUES (?, ?, ?, ?, ?, ?, ?)
    `);
    for (const provider of PROVIDERS) {
      insert.run(
        provider.id,
        provider.name,
        "codex",
        provider.baseUrl,
        null,
        JSON.stringify({
          config: `base_url = "${provider.baseUrl}"\nmodel = "gpt-image-2"`,
          auth: { OPENAI_API_KEY: provider.key },
        }),
        0,
      );
    }
  } finally {
    db.close();
  }
  return dbPath;
}

async function createFixture() {
  const root = await mkdtemp(path.join(os.tmpdir(), "research-image-route-"));
  const dbPath = createDatabase(root);
  const registryPath = path.join(root, "config", "providers.json");
  await mkdir(path.dirname(registryPath), { recursive: true });
  await writeFile(registryPath, JSON.stringify({
    version: 2,
    providers: PROVIDERS.map((provider) => ({
      alias: provider.alias,
      provider_id: provider.id,
      app_type: "codex",
      expected_name: provider.name,
      default_model: "gpt-image-2",
    })),
    routing: { default_alias: "UESTC", fallback_aliases: ["贾维斯", "夯炸了"] },
  }, null, 2));
  return { root, dbPath, registryPath };
}

function providerForUrl(url) {
  return PROVIDERS.find((provider) => String(url).startsWith(provider.baseUrl)) || null;
}

function jsonResponse(payload, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function modelsResponse() {
  return jsonResponse({ data: [{ id: "gpt-image-2" }] });
}

function imageResponse() {
  return jsonResponse({ data: [{ b64_json: VALID_PNG.toString("base64") }] });
}

function generationRequest() {
  return ({ baseUrl, apiKey, model }) => ({
    url: `${baseUrl}/images/generations`,
    init: {
      method: "POST",
      headers: { authorization: `Bearer ${apiKey}`, "content-type": "application/json" },
      body: JSON.stringify({ model, prompt: "test", output_format: "png" }),
    },
  });
}

function saveEnvironment() {
  const keys = [
    "ENABLE_RESEARCH_IMAGEGEN",
    "RESEARCH_IMAGE_API_KEY",
    "RESEARCH_IMAGE_BASE_URL",
    "RESEARCH_IMAGE_MODEL",
    "RESEARCH_IMAGE_PROVIDER",
    "RESEARCH_IMAGE_BACKEND",
  ];
  return { keys, values: Object.fromEntries(keys.map((key) => [key, process.env[key]])) };
}

function restoreEnvironment(snapshot) {
  for (const key of snapshot.keys) {
    if (snapshot.values[key] === undefined) delete process.env[key];
    else process.env[key] = snapshot.values[key];
  }
}

async function withFixture(fn) {
  const fixture = await createFixture();
  const environment = saveEnvironment();
  try {
    delete process.env.RESEARCH_IMAGE_PROVIDER;
    delete process.env.RESEARCH_IMAGE_MODEL;
    return await fn(fixture);
  } finally {
    restoreEnvironment(environment);
    await rm(fixture.root, { recursive: true, force: true });
  }
}

test("default routing skips a failed preflight without sending a billable request", () => withFixture(async ({ dbPath, registryPath }) => {
  const fetchImpl = async (url) => {
    const provider = providerForUrl(url);
    if (String(url).endsWith("/models")) {
      return provider.alias === "UESTC" ? jsonResponse({ error: { message: "offline" } }, 401) : modelsResponse();
    }
    return imageResponse();
  };
  const result = await executeImageRequest({ dbPath, registryPath, fetchImpl, buildRequest: generationRequest() });
  assert.equal(result.selected_alias, "贾维斯");
  assert.deepEqual(result.attempted_aliases, ["UESTC", "贾维斯"]);
  assert.equal(result.failover_count, 1);
  assert.equal(result.billable_requests_sent, 1);
}));

test("retryable /models failures are retried once before the route advances", () => withFixture(async ({ dbPath, registryPath }) => {
  let uestcModelCalls = 0;
  const fetchImpl = async (url) => {
    const provider = providerForUrl(url);
    if (String(url).endsWith("/models")) {
      if (provider.alias === "UESTC") {
        uestcModelCalls += 1;
        return jsonResponse({ error: { message: "temporary" } }, 503);
      }
      return modelsResponse();
    }
    return imageResponse();
  };
  const result = await executeImageRequest({ dbPath, registryPath, fetchImpl, buildRequest: generationRequest() });
  assert.equal(uestcModelCalls, 2);
  assert.equal(result.selected_alias, "贾维斯");
  assert.equal(result.billable_requests_sent, 1);
}));

test("a formal availability failure falls back once and discloses duplicate billing risk", () => withFixture(async ({ dbPath, registryPath }) => {
  const fetchImpl = async (url) => {
    const provider = providerForUrl(url);
    if (String(url).endsWith("/models")) return modelsResponse();
    if (provider.alias === "UESTC") return jsonResponse({ error: { message: provider.key } }, 503);
    return imageResponse();
  };
  const result = await executeImageRequest({ dbPath, registryPath, fetchImpl, buildRequest: generationRequest() });
  assert.equal(result.selected_alias, "贾维斯");
  assert.equal(result.billable_requests_sent, 2);
  assert.equal(result.duplicate_billing_risk, true);
  assert.equal(JSON.stringify(result).includes("uestc-secret-key"), false);
}));

test("content-policy 403 and invalid request 400 stop the default route", async (t) => {
  for (const scenario of [
    { name: "content", status: 403, error: { type: "content_policy_violation", message: "blocked by safety policy" }, code: "content_policy_rejected" },
    { name: "parameter", status: 400, error: { type: "invalid_request_error", message: "bad size" }, code: "invalid_image_request" },
  ]) {
    await t.test(scenario.name, () => withFixture(async ({ dbPath, registryPath }) => {
      const fetchImpl = async (url) => String(url).endsWith("/models")
        ? modelsResponse()
        : jsonResponse({ error: scenario.error }, scenario.status);
      await assert.rejects(
        executeImageRequest({ dbPath, registryPath, fetchImpl, buildRequest: generationRequest() }),
        (error) => {
          const result = serializeImageRouteError(error);
          assert.equal(result.error_code, scenario.code);
          assert.deepEqual(result.attempted_aliases, ["UESTC"]);
          assert.equal(result.billable_requests_sent, 1);
          return true;
        },
      );
    }));
  }
});

test("a non-content 403 falls back and each edit attempt receives a fresh FormData", () => withFixture(async ({ dbPath, registryPath }) => {
  const forms = [];
  const fetchImpl = async (url) => {
    const provider = providerForUrl(url);
    if (String(url).endsWith("/models")) return modelsResponse();
    if (provider.alias === "UESTC") return jsonResponse({ error: { type: "authentication_error", message: "forbidden" } }, 403);
    return imageResponse();
  };
  const result = await executeImageRequest({
    dbPath,
    registryPath,
    fetchImpl,
    buildRequest: ({ baseUrl, apiKey, model }) => {
      const form = new FormData();
      form.append("prompt", "test");
      form.append("model", model);
      forms.push(form);
      return { url: `${baseUrl}/images/edits`, init: { method: "POST", headers: { authorization: `Bearer ${apiKey}` }, body: form } };
    },
  });
  assert.equal(result.selected_alias, "贾维斯");
  assert.equal(forms.length, 2);
  assert.notEqual(forms[0], forms[1]);
  assert.equal(result.billable_requests_sent, 2);
}));

test("empty or malformed image results and failed URL downloads move to the next provider", async (t) => {
  for (const scenario of ["missing-data", "invalid-base64", "download-failure"]) {
    await t.test(scenario, () => withFixture(async ({ dbPath, registryPath }) => {
      const fetchImpl = async (url) => {
        const provider = providerForUrl(url);
        if (String(url).endsWith("/models")) return modelsResponse();
        if (String(url) === "https://download.test/fail.png") return new Response("unavailable", { status: 502 });
        if (provider.alias === "UESTC") {
          if (scenario === "missing-data") return jsonResponse({ data: [] });
          if (scenario === "invalid-base64") return jsonResponse({ data: [{ b64_json: Buffer.from("not an image").toString("base64") }] });
          return jsonResponse({ data: [{ url: "https://download.test/fail.png" }] });
        }
        return imageResponse();
      };
      const result = await executeImageRequest({ dbPath, registryPath, fetchImpl, buildRequest: generationRequest() });
      assert.equal(result.selected_alias, "贾维斯");
      assert.equal(result.billable_requests_sent, 2);
    }));
  }
});

test("CLI provider overrides the environment and pinned failures never fall back", () => withFixture(async ({ dbPath, registryPath }) => {
  process.env.RESEARCH_IMAGE_PROVIDER = "贾维斯";
  const urls = [];
  const fetchImpl = async (url) => {
    urls.push(String(url));
    if (String(url).endsWith("/models")) return modelsResponse();
    return jsonResponse({ error: { message: `temporary outage ${PROVIDERS[0].key}` } }, 503);
  };
  await assert.rejects(
    executeImageRequest({ providerAlias: "UESTC", dbPath, registryPath, fetchImpl, buildRequest: generationRequest() }),
    (error) => {
      const result = serializeImageRouteError(error);
      assert.equal(result.route_mode, "pinned");
      assert.equal(result.route_source, "cli");
      assert.deepEqual(result.provider_candidates, ["UESTC"]);
      assert.deepEqual(result.attempted_aliases, ["UESTC"]);
      assert.equal(result.billable_requests_sent, 1);
      assert.equal(JSON.stringify(result).includes(PROVIDERS[0].key), false);
      return true;
    },
  );
  assert.equal(urls.some((url) => url.startsWith("https://jarvis.test")), false);
}));

test("the overall budget can stop the route before any formal request", () => withFixture(async ({ dbPath, registryPath }) => {
  const fetchImpl = async () => modelsResponse();
  await assert.rejects(
    executeImageRequest({ dbPath, registryPath, fetchImpl, buildRequest: generationRequest(), operationTimeoutMs: 0 }),
    (error) => {
      const result = serializeImageRouteError(error);
      assert.equal(result.error_code, "operation_timeout");
      assert.equal(result.billable_requests_sent, 0);
      assert.deepEqual(result.attempted_aliases, []);
      return true;
    },
  );
}));

test("direct backend remains a single pinned request without provider fallback", () => withFixture(async () => {
  process.env.ENABLE_RESEARCH_IMAGEGEN = "1";
  process.env.RESEARCH_IMAGE_API_KEY = "direct-test-key";
  process.env.RESEARCH_IMAGE_BASE_URL = "https://direct.test/v1";
  process.env.RESEARCH_IMAGE_MODEL = "gpt-image-2";
  let formalCalls = 0;
  const result = await executeImageRequest({
    backend: "direct",
    fetchImpl: async (url, init) => {
      formalCalls += 1;
      assert.equal(url, "https://direct.test/v1/images/generations");
      assert.equal(init.headers.authorization, "Bearer direct-test-key");
      return imageResponse();
    },
    buildRequest: generationRequest(),
  });
  assert.equal(formalCalls, 1);
  assert.equal(result.route_mode, "direct");
  assert.equal(result.billable_requests_sent, 1);
  assert.deepEqual(result.provider_candidates, []);
}));
