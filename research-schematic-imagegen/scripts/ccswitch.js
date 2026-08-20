// Read-only discovery of OpenAI-compatible image providers stored in CC Switch.
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

export async function readCcSwitchImageProvider(providerId, dbPath = DEFAULT_CCSWITCH_DB) {
  const normalizedId = String(providerId || "").trim();
  if (!normalizedId) throw new Error("A CC Switch provider ID is required.");
  const db = await openDatabase(path.resolve(dbPath));
  try {
    const row = db.prepare("SELECT id,name,app_type,website_url,provider_type,settings_config,is_current FROM providers WHERE id = ?").get(normalizedId);
    return row ? providerFromRow(row) : null;
  } finally {
    db.close();
  }
}

async function probeModelsOnce(provider, { fetchImpl = fetch, timeoutMs = 10000 } = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetchImpl(`${provider.base_url}/models`, {
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

export async function probeCcSwitchProviderModels(provider, { fetchImpl = fetch, timeoutMs = 10000, retry = true } = {}) {
  const first = await probeModelsOnce(provider, { fetchImpl, timeoutMs });
  const retryable = first.status === "timeout" || first.status === "network-error" || first.status === 429 || (typeof first.status === "number" && first.status >= 500);
  if (!retry || !retryable) return first;
  await new Promise((resolve) => setTimeout(resolve, 250));
  return probeModelsOnce(provider, { fetchImpl, timeoutMs });
}

export function toPublicCcSwitchProvider(provider, probe) {
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

export async function inspectCcSwitchImageProviderCandidate({
  dbPath = DEFAULT_CCSWITCH_DB,
  providerId,
  fetchImpl = fetch,
  timeoutMs = 10000,
} = {}) {
  const provider = await readCcSwitchImageProvider(providerId, dbPath);
  if (!provider) throw new Error(`CC Switch provider not found: ${String(providerId || "").trim()}.`);
  const probe = await probeCcSwitchProviderModels(provider, { fetchImpl, timeoutMs });
  return {
    db_path: path.resolve(dbPath),
    provider: toPublicCcSwitchProvider(provider, probe),
  };
}
