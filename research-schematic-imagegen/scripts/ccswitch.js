// Read-only discovery of OpenAI-compatible image providers stored in CC Switch.
import crypto from "node:crypto";
import os from "node:os";
import path from "node:path";
import process from "node:process";

export const DEFAULT_CCSWITCH_DB = process.env.RESEARCH_IMAGE_CCSWITCH_DB || path.join(os.homedir(), ".cc-switch", "cc-switch.db");

function normalizeBaseUrl(value) {
  const raw = String(value || "").trim().replace(/\/+$/, "");
  if (!raw) return "";
  if (/\/v1$/i.test(raw)) return raw;
  return `${raw}/v1`;
}

function parseTomlAssignment(config, key) {
  const prefix = `${key} =`;
  for (const line of String(config || "").split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed.startsWith(prefix)) continue;
    const raw = trimmed.slice(prefix.length).trim();
    if (!raw) return "";
    if (raw.startsWith("\"") || raw.startsWith("'")) {
      const quote = raw[0];
      const end = raw.lastIndexOf(quote);
      return end > 0 ? raw.slice(1, end) : "";
    }
    return raw.split(" #", 1)[0].trim();
  }
  return "";
}

function getApiKey(auth) {
  if (!auth || typeof auth !== "object") return "";
  for (const keyName of ["RESEARCH_IMAGE_API_KEY", "OPENAI_API_KEY", "experimental_bearer_token"]) {
    const value = auth[keyName];
    if (typeof value !== "string" || !value.trim()) continue;
    if (value.trim() === "PROXY_MANAGED") continue;
    return value.trim();
  }
  return "";
}

function providerFromRow(row) {
  let settings = {};
  try {
    settings = JSON.parse(row.settings_config || "{}");
  } catch {
    return null;
  }
  const baseUrl = normalizeBaseUrl(parseTomlAssignment(settings.config, "base_url"));
  const apiKey = getApiKey(settings.auth);
  if (!baseUrl || !apiKey) return null;
  return {
    id: String(row.id || ""),
    name: String(row.name || ""),
    app_type: String(row.app_type || ""),
    website_url: row.website_url || null,
    provider_type: row.provider_type || null,
    is_current: Boolean(row.is_current),
    base_url: baseUrl,
    configured_model: parseTomlAssignment(settings.config, "model"),
    api_key: apiKey,
  };
}

async function openDatabase(dbPath) {
  let sqlite;
  try {
    sqlite = await import("node:sqlite");
  } catch {
    throw new Error("CC Switch provider discovery requires Node.js 22+ with node:sqlite.");
  }
  try {
    return new sqlite.DatabaseSync(dbPath, { readOnly: true });
  } catch (error) {
    throw new Error(`Cannot open CC Switch database: ${dbPath} (${error.message})`);
  }
}

export async function readCcSwitchImageProviders(dbPath = DEFAULT_CCSWITCH_DB) {
  const db = await openDatabase(path.resolve(dbPath));
  try {
    const rows = db.prepare("SELECT id,name,app_type,website_url,provider_type,settings_config,is_current FROM providers").all();
    return rows.map(providerFromRow).filter(Boolean);
  } finally {
    db.close();
  }
}

async function probeModelsOnce(provider, timeoutMs = 10000) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(`${provider.base_url}/models`, {
      headers: { authorization: `Bearer ${provider.api_key}` },
      signal: controller.signal,
    });
    let payload = null;
    try {
      payload = await response.json();
    } catch {
      payload = null;
    }
    const modelIds = Array.isArray(payload?.data) ? payload.data.map((item) => String(item?.id || "")).filter(Boolean) : [];
    const imageModels = modelIds.filter((id) => /gpt[-_]?image|dall[-_]?e|image/i.test(id));
    return { ok: response.ok, status: response.status, image_models: imageModels };
  } catch (error) {
    return { ok: false, status: error.name === "AbortError" ? "timeout" : "network-error", image_models: [] };
  } finally {
    clearTimeout(timer);
  }
}

async function probeModels(provider, timeoutMs = 10000) {
  const first = await probeModelsOnce(provider, timeoutMs);
  const retryable = first.status === "timeout" || first.status === "network-error" || first.status === 429 || (typeof first.status === "number" && first.status >= 500);
  if (!retryable) return first;
  await new Promise((resolve) => setTimeout(resolve, 250));
  return probeModelsOnce(provider, timeoutMs);
}

function fingerprint(provider) {
  return crypto.createHash("sha256").update(`${provider.base_url}\0${provider.api_key}`).digest("hex");
}

function publicProvider(provider, probe) {
  return {
    id: provider.id,
    name: provider.name,
    app_type: provider.app_type,
    website_url: provider.website_url,
    provider_type: provider.provider_type,
    is_current: provider.is_current,
    base_url: provider.base_url,
    configured_model: provider.configured_model || null,
    status: probe?.status ?? null,
    image_models: probe?.image_models ?? [],
  };
}

function groupProviders(probed) {
  const groups = new Map();
  for (const item of probed) {
    if (!item.probe.ok || item.probe.image_models.length === 0) continue;
    const key = fingerprint(item.provider);
    const existing = groups.get(key);
    if (existing) {
      existing.providers.push(item.provider);
      existing.image_models = [...new Set([...existing.image_models, ...item.probe.image_models])];
    } else {
      groups.set(key, { provider: item.provider, providers: [item.provider], image_models: item.probe.image_models });
    }
  }
  return [...groups.values()];
}

async function probeCandidates(providers) {
  return Promise.all(providers.map(async (provider) => ({ provider, probe: await probeModels(provider) })));
}

export async function discoverCcSwitchImageProviders({
  dbPath = DEFAULT_CCSWITCH_DB,
  providerId = "",
  providerName = "",
} = {}) {
  const all = await readCcSwitchImageProviders(dbPath);
  let candidates = all;
  if (providerId) candidates = all.filter((provider) => provider.id === providerId);
  if (providerName) candidates = all.filter((provider) => provider.name.toLowerCase() === providerName.toLowerCase());
  const probed = await probeCandidates(candidates);
  const groups = groupProviders(probed);
  return {
    db_path: path.resolve(dbPath),
    scanned_count: all.length,
    candidate_count: candidates.length,
    providers: probed.map((item) => publicProvider(item.provider, item.probe)),
    image_providers: groups.map((group) => ({
      ...publicProvider(group.provider, { status: 200, image_models: group.image_models }),
      provider_ids: group.providers.map((provider) => provider.id),
      provider_names: [...new Set(group.providers.map((provider) => provider.name))],
    })),
  };
}

export async function loadCcSwitchImageProvider({
  dbPath = process.env.RESEARCH_IMAGE_CCSWITCH_DB || DEFAULT_CCSWITCH_DB,
  providerId = process.env.RESEARCH_IMAGE_CC_SWITCH_PROVIDER_ID || "",
  providerName = process.env.RESEARCH_IMAGE_CC_SWITCH_PROVIDER_NAME || "",
} = {}) {
  const allProviders = await readCcSwitchImageProviders(dbPath);
  let candidates = allProviders;
  if (providerId) candidates = allProviders.filter((provider) => provider.id === providerId);
  if (providerName) candidates = allProviders.filter((provider) => provider.name.toLowerCase() === providerName.toLowerCase());
  const probed = await probeCandidates(candidates);
  const failed = probed.filter((item) => !item.probe.ok);
  if (failed.length > 0 && !(providerId && candidates.length === 1)) {
    const summary = failed.map((item) => `${item.provider.name} (${item.provider.id}): ${item.probe.status}`).join(", ");
    throw new Error(`CC Switch provider probe incomplete: ${summary}. Automatic selection stopped.`);
  }
  const groups = groupProviders(probed);
  if (groups.length === 0) throw new Error("No CC Switch provider exposed an image model through /models.");
  if (groups.length > 1) {
    const summary = groups.map((group) => `${group.provider.name} (${group.provider.id})`).join(", ");
    throw new Error(`Multiple CC Switch image providers found: ${summary}. Set RESEARCH_IMAGE_CC_SWITCH_PROVIDER_ID or RESEARCH_IMAGE_CC_SWITCH_PROVIDER_NAME.`);
  }
  const selected = groups[0];
  const model = process.env.RESEARCH_IMAGE_MODEL && selected.image_models.includes(process.env.RESEARCH_IMAGE_MODEL)
    ? process.env.RESEARCH_IMAGE_MODEL
    : selected.image_models.includes("gpt-image-2")
      ? "gpt-image-2"
      : selected.image_models[0];
  process.env.ENABLE_RESEARCH_IMAGEGEN = "1";
  process.env.RESEARCH_IMAGE_BASE_URL = selected.provider.base_url;
  process.env.RESEARCH_IMAGE_API_KEY = selected.provider.api_key;
  process.env.RESEARCH_IMAGE_MODEL = model;
  return {
    provider: publicProvider(selected.provider, { status: 200, image_models: selected.image_models }),
    provider_ids: selected.providers.map((provider) => provider.id),
    provider_names: [...new Set(selected.providers.map((provider) => provider.name))],
  };
}
