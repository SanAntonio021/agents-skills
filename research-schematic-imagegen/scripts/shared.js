// Adapted from ConardLi/garden-skills gpt-image-2 v1.0.4 under the MIT License.
import path from "node:path";
import os from "node:os";
import process from "node:process";
import { access, mkdir, readFile, writeFile } from "node:fs/promises";

export const DEFAULT_OUTPUT_ROOT = process.env.RESEARCH_IMAGE_OUTPUT_ROOT || "research-schematic-imagegen";
export const DEFAULT_WORKING_DIR = path.join(DEFAULT_OUTPUT_ROOT, "working");
export const DEFAULT_PROMPT_DIR = path.join(DEFAULT_OUTPUT_ROOT, "prompt");
export const DEFAULT_MODEL = "gpt-image-2";
export const DEFAULT_CONFIG_DIR = process.env.RESEARCH_IMAGE_CONFIG_DIR || path.join(os.homedir(), ".config", "research-schematic-imagegen");
export const DEFAULT_PROVIDER_REGISTRY = process.env.RESEARCH_IMAGE_PROVIDER_REGISTRY || path.join(DEFAULT_CONFIG_DIR, "providers.json");
let runtimeState = { backend: "ccswitch", env_file: null, registry_path: null, provider_alias: null, provider: null };

const TRUTHY = new Set(["1", "true", "yes", "on", "y"]);

export function isTruthy(value) {
  return TRUTHY.has(String(value || "").trim().toLowerCase());
}

export async function readEnvFile(filePath) {
  const text = await readFile(filePath, "utf8");
  const result = {};
  for (const line of text.split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) continue;
    const pivot = trimmed.indexOf("=");
    if (pivot === -1) continue;
    const key = trimmed.slice(0, pivot).trim();
    let value = trimmed.slice(pivot + 1).trim();
    if ((value.startsWith('"') && value.endsWith('"')) || (value.startsWith("'") && value.endsWith("'"))) {
      value = value.slice(1, -1);
    }
    result[key] = value;
  }
  return result;
}

async function loadDirectEnv(configDir, explicitFile) {
  let envFile = explicitFile ? path.resolve(explicitFile) : "";
  if (!envFile) {
    const candidate = path.join(configDir, "image-api.env");
    try {
      await access(candidate);
      envFile = candidate;
    } catch {
      // Direct mode may also rely entirely on the parent process environment.
    }
  }
  if (envFile) {
    const pairs = await readEnvFile(envFile);
    for (const [key, value] of Object.entries(pairs)) {
      if (!process.env[key]) process.env[key] = value;
    }
  }
  return envFile || null;
}

export async function loadRuntimeEnv({
  backend = process.env.RESEARCH_IMAGE_BACKEND || "ccswitch",
  providerAlias = process.env.RESEARCH_IMAGE_PROVIDER || "",
  model = "",
  configDir = DEFAULT_CONFIG_DIR,
  registryPath = process.env.RESEARCH_IMAGE_PROVIDER_REGISTRY || path.join(configDir, "providers.json"),
  dbPath = process.env.RESEARCH_IMAGE_CCSWITCH_DB,
  fetchImpl = fetch,
  timeoutMs = 10000,
} = {}) {
  const normalizedBackend = String(backend || "").trim().toLowerCase();
  if (normalizedBackend === "direct") {
    const envFile = await loadDirectEnv(path.resolve(configDir), process.env.RESEARCH_IMAGE_ENV_FILE);
    runtimeState = { backend: "direct", env_file: envFile, registry_path: null, provider_alias: null, provider: null };
    return envFile;
  }
  if (normalizedBackend !== "ccswitch") throw new Error(`Unsupported RESEARCH_IMAGE_BACKEND: ${normalizedBackend}`);
  if (process.env.RESEARCH_IMAGE_CC_SWITCH_PROVIDER_ID || process.env.RESEARCH_IMAGE_CC_SWITCH_PROVIDER_NAME) {
    throw new Error("RESEARCH_IMAGE_CC_SWITCH_PROVIDER_ID and RESEARCH_IMAGE_CC_SWITCH_PROVIDER_NAME are no longer supported. Use a registered --provider alias.");
  }
  const { loadRegisteredCcSwitchImageProvider } = await import("./provider-registry.js");
  const selected = await loadRegisteredCcSwitchImageProvider({
    registryPath,
    dbPath,
    alias: providerAlias,
    model: model || process.env.RESEARCH_IMAGE_MODEL || "",
    fetchImpl,
    timeoutMs,
  });
  process.env.ENABLE_RESEARCH_IMAGEGEN = "1";
  process.env.RESEARCH_IMAGE_BASE_URL = selected.provider.base_url;
  process.env.RESEARCH_IMAGE_API_KEY = selected.provider.api_key;
  process.env.RESEARCH_IMAGE_MODEL = selected.model;
  runtimeState = {
    backend: "ccswitch",
    env_file: null,
    registry_path: path.resolve(registryPath),
    provider_alias: selected.alias,
    provider: selected.public_provider,
  };
  return null;
}

export function runtimeInfo() {
  return { ...runtimeState };
}

export function imageApiEnabled() {
  return isTruthy(process.env.ENABLE_RESEARCH_IMAGEGEN);
}

export function apiKey() {
  return process.env.RESEARCH_IMAGE_API_KEY || process.env.OPENAI_API_KEY || "";
}

export function imageModel() {
  return process.env.RESEARCH_IMAGE_MODEL || process.env.OPENAI_IMAGE_MODEL || DEFAULT_MODEL;
}

export function buildBaseUrl() {
  return (process.env.RESEARCH_IMAGE_BASE_URL || process.env.OPENAI_BASE_URL || "https://api.openai.com/v1").replace(/\/$/, "");
}

export function requireLocalApiEnabled() {
  if (!imageApiEnabled()) {
    throw new Error("Local image API calls are disabled. Set ENABLE_RESEARCH_IMAGEGEN=1 only after user approval.");
  }
  if (!apiKey()) {
    throw new Error("RESEARCH_IMAGE_API_KEY or OPENAI_API_KEY is required.");
  }
}

export async function readPromptInput(prompt, promptFile) {
  if (prompt) return prompt.trim();
  if (promptFile) return (await readFile(path.resolve(promptFile), "utf8")).trim();
  throw new Error("Prompt is required. Use --prompt or --promptfile.");
}

export function slugify(value, fallback = "image-task") {
  const base = String(value || "").trim().toLowerCase();
  const ascii = base
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 48);
  return ascii || fallback;
}

export function makeTimestamp() {
  const now = new Date();
  const parts = [
    now.getFullYear(),
    String(now.getMonth() + 1).padStart(2, "0"),
    String(now.getDate()).padStart(2, "0"),
    "-",
    String(now.getHours()).padStart(2, "0"),
    String(now.getMinutes()).padStart(2, "0"),
    String(now.getSeconds()).padStart(2, "0"),
  ];
  return parts.join("");
}

export function buildDefaultImagePath(kind, hint) {
  const slug = slugify(hint, kind === "edit" ? "edited-image" : "generated-image");
  return path.join(DEFAULT_WORKING_DIR, `${slug}-${makeTimestamp()}.png`);
}

export function buildDefaultPromptPath(hint) {
  return path.join(DEFAULT_PROMPT_DIR, `${slugify(hint, "prompt")}-${makeTimestamp()}.md`);
}

export function resolveOutput(raw, fallbackPath) {
  const full = path.resolve(raw || fallbackPath);
  return path.extname(full) ? full : `${full}.png`;
}

export async function savePrompt(promptText, rawPath, hint) {
  const finalPath = path.resolve(rawPath || buildDefaultPromptPath(hint));
  await mkdir(path.dirname(finalPath), { recursive: true });
  await writeFile(finalPath, `${promptText.trim()}\n`, "utf8");
  return finalPath;
}

export function mimeFor(filePath) {
  const ext = path.extname(filePath).toLowerCase();
  if (ext === ".jpg" || ext === ".jpeg") return "image/jpeg";
  if (ext === ".webp") return "image/webp";
  if (ext === ".gif") return "image/gif";
  return "image/png";
}

export async function ensureFilesExist(files, label) {
  for (const item of files) {
    try {
      await readFile(path.resolve(item));
    } catch {
      throw new Error(`${label} not found: ${path.resolve(item)}`);
    }
  }
}

function safeErrorBody(text) {
  const key = apiKey();
  const redacted = key ? String(text).replaceAll(key, "[REDACTED]") : String(text);
  return redacted.slice(0, 2000);
}

export async function postJson(url, payload) {
  requireLocalApiEnabled();
  const response = await fetch(url, {
    method: "POST",
    headers: {
      authorization: `Bearer ${apiKey()}`,
      "content-type": "application/json",
    },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error(`Image API error (${response.status}): ${safeErrorBody(await response.text())}`);
  }
  return response.json();
}

export async function postMultipart(url, form) {
  requireLocalApiEnabled();
  const response = await fetch(url, {
    method: "POST",
    headers: { authorization: `Bearer ${apiKey()}` },
    body: form,
  });
  if (!response.ok) {
    throw new Error(`Image API error (${response.status}): ${safeErrorBody(await response.text())}`);
  }
  return response.json();
}

async function fetchBytesFromUrl(url) {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Failed to download generated image (${response.status}): ${safeErrorBody(await response.text())}`);
  }
  return Buffer.from(await response.arrayBuffer());
}

export async function extractGeneratedBytes(json) {
  const first = json?.data?.[0];
  if (!first) throw new Error("API response did not include data[0].");
  if (first.b64_json) return Buffer.from(first.b64_json, "base64");
  if (first.url) return fetchBytesFromUrl(first.url);
  throw new Error("API response did not include b64_json or url.");
}

export async function saveImage(outputPath, bytes) {
  await mkdir(path.dirname(outputPath), { recursive: true });
  await writeFile(outputPath, bytes);
}

export function appendIfPresent(target, key, value) {
  if (value === undefined || value === null || value === "") return;
  target.append(key, String(value));
}

export function printJson(data) {
  console.log(JSON.stringify(data, null, 2));
}
