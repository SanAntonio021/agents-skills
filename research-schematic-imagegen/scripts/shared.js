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
export const DEFAULT_PROBE_TIMEOUT_MS = 10000;
export const DEFAULT_REQUEST_TIMEOUT_MS = 600000;
export const DEFAULT_DOWNLOAD_TIMEOUT_MS = 60000;
export const DEFAULT_OPERATION_TIMEOUT_MS = 900000;
let runtimeState = {
  backend: "ccswitch",
  env_file: null,
  registry_path: null,
  provider_alias: null,
  provider: null,
  route_mode: null,
  provider_candidates: [],
  attempted_aliases: [],
  failover_count: 0,
  billable_requests_sent: 0,
};

const TRUTHY = new Set(["1", "true", "yes", "on", "y"]);

export class ImageRouteError extends Error {
  constructor(message, details = {}) {
    super(message);
    this.name = "ImageRouteError";
    Object.assign(this, details);
  }
}

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

function effectiveProviderAlias(providerAlias) {
  const cliAlias = String(providerAlias || "").trim();
  if (cliAlias) return { alias: cliAlias, source: "cli" };
  const envAlias = String(process.env.RESEARCH_IMAGE_PROVIDER || "").trim();
  if (envAlias) return { alias: envAlias, source: "environment" };
  return { alias: "", source: "registry" };
}

function setCcSwitchRuntime({ registryPath, route, selected, attemptedAliases, billableRequestsSent = 0 }) {
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
    route_mode: route.mode,
    route_source: route.source,
    provider_candidates: [...route.aliases],
    attempted_aliases: [...attemptedAliases],
    failover_count: Math.max(0, attemptedAliases.length - 1),
    billable_requests_sent: billableRequestsSent,
  };
}

function routeError(message, details) {
  return new ImageRouteError(message, {
    code: "image_route_failed",
    route_mode: details.routeMode,
    route_source: details.routeSource,
    provider_candidates: [...details.providerCandidates],
    attempted_aliases: [...details.attemptedAliases],
    failover_count: Math.max(0, details.attemptedAliases.length - 1),
    billable_requests_sent: details.billableRequestsSent || 0,
    attempts: [...(details.attempts || [])],
    duplicate_billing_risk: Boolean(details.duplicateBillingRisk),
    ...details.extra,
  });
}

async function prepareCcSwitchRoute({
  providerAlias,
  model,
  registryPath,
  dbPath,
  fetchImpl,
  timeoutMs,
}) {
  const { readProviderRegistry, resolveProviderRoute, probeRegisteredCcSwitchImageProvider } = await import("./provider-registry.js");
  const { registry } = await readProviderRegistry(registryPath);
  const selection = effectiveProviderAlias(providerAlias);
  const route = { ...resolveProviderRoute(registry, selection.alias), source: selection.source };
  const requestedModel = String(model || process.env.RESEARCH_IMAGE_MODEL || "").trim();
  return {
    registry,
    route,
    probe: (entry, remainingMs = timeoutMs) => probeRegisteredCcSwitchImageProvider({
      registry,
      entry,
      dbPath,
      model: requestedModel,
      fetchImpl,
      timeoutMs: Math.max(1, Math.min(timeoutMs, remainingMs)),
    }),
  };
}

export async function loadRuntimeEnv({
  backend = process.env.RESEARCH_IMAGE_BACKEND || "ccswitch",
  providerAlias,
  model = "",
  configDir = DEFAULT_CONFIG_DIR,
  registryPath = process.env.RESEARCH_IMAGE_PROVIDER_REGISTRY || path.join(configDir, "providers.json"),
  dbPath = process.env.RESEARCH_IMAGE_CCSWITCH_DB,
  fetchImpl = fetch,
  timeoutMs = DEFAULT_PROBE_TIMEOUT_MS,
} = {}) {
  const normalizedBackend = String(backend || "").trim().toLowerCase();
  if (normalizedBackend === "direct") {
    const envFile = await loadDirectEnv(path.resolve(configDir), process.env.RESEARCH_IMAGE_ENV_FILE);
    runtimeState = {
      backend: "direct",
      env_file: envFile,
      registry_path: null,
      provider_alias: null,
      provider: null,
      route_mode: "direct",
      route_source: "direct",
      provider_candidates: [],
      attempted_aliases: [],
      failover_count: 0,
      billable_requests_sent: 0,
    };
    return envFile;
  }
  if (normalizedBackend !== "ccswitch") throw new Error(`Unsupported RESEARCH_IMAGE_BACKEND: ${normalizedBackend}`);
  if (process.env.RESEARCH_IMAGE_CC_SWITCH_PROVIDER_ID || process.env.RESEARCH_IMAGE_CC_SWITCH_PROVIDER_NAME) {
    throw new Error("RESEARCH_IMAGE_CC_SWITCH_PROVIDER_ID and RESEARCH_IMAGE_CC_SWITCH_PROVIDER_NAME are no longer supported. Use a registered --provider alias.");
  }
  const prepared = await prepareCcSwitchRoute({
    providerAlias,
    model,
    registryPath,
    dbPath,
    fetchImpl,
    timeoutMs,
  });
  const attemptedAliases = [];
  const attempts = [];
  let lastFailure = null;
  for (const entry of prepared.route.entries) {
    attemptedAliases.push(entry.alias);
    let selected;
    try {
      selected = await prepared.probe(entry);
    } catch {
      lastFailure = { code: "provider_registration_mismatch", failoverEligible: false };
      attempts.push({ alias: entry.alias, stage: "preflight", code: lastFailure.code, status: null });
      break;
    }
    if (selected.ok) {
      setCcSwitchRuntime({ registryPath, route: prepared.route, selected, attemptedAliases });
      return null;
    }
    lastFailure = classifyPreflightFailure(selected.status);
    attempts.push({ alias: entry.alias, stage: "preflight", code: lastFailure.code, status: selected.status });
    if (!lastFailure.failoverEligible) break;
  }
  const message = lastFailure?.code === "provider_registration_mismatch"
    ? "当前渠道的登记信息与 CC Switch 当前记录不一致，需要重新登记后再试。"
    : lastFailure && !lastFailure.failoverEligible
      ? "当前渠道的接入配置、账号或权限状态有问题，需要先修复该渠道。"
      : "已按顺序检查候选渠道，但没有找到当前可用的生图渠道。";
  throw routeError(message, {
    routeMode: prepared.route.mode,
    routeSource: prepared.route.source,
    providerCandidates: prepared.route.aliases,
    attemptedAliases,
    attempts,
    extra: { code: lastFailure?.code || "provider_preflight_failed" },
  });
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
  let redacted = key ? String(text).replaceAll(key, "[REDACTED]") : String(text);
  redacted = redacted
    .replace(/Bearer\s+[A-Za-z0-9._~+\/-]+/gi, "Bearer [REDACTED]")
    .replace(/("(?:api[_-]?key|authorization|token)"\s*:\s*")[^"]+(")/gi, "$1[REDACTED]$2")
    .replace(/\bsk-[A-Za-z0-9_-]{8,}\b/g, "[REDACTED]");
  return redacted.replace(/\s+/g, " ").trim().slice(0, 400);
}

function errorDetailsFromBody(text) {
  let payload = null;
  try {
    payload = JSON.parse(text);
  } catch {
    payload = null;
  }
  const error = payload?.error && typeof payload.error === "object" ? payload.error : payload;
  return {
    type: typeof error?.type === "string" ? safeErrorBody(error.type) : "",
    code: typeof error?.code === "string" ? safeErrorBody(error.code) : "",
    message: typeof error?.message === "string" ? safeErrorBody(error.message) : safeErrorBody(text),
  };
}

function classifyApiFailure(status, details) {
  const semantic = `${details.type} ${details.code} ${details.message}`.toLowerCase();
  const contentFailure = /(content[_ -]?(policy|filter|moderation)|moderation[_ -]?(blocked|rejected)|safety[_ -]?(policy|violation)|policy[_ -]?violation|审核|安全策略|内容违规)/i.test(semantic);
  if (contentFailure) return { code: "content_policy_rejected", failoverEligible: false };
  const accountFailure = status === 401
    || status === 402
    || status === 403
    || /(invalid[_ -]?(api[_ -]?key|token)|authentication|unauthorized|forbidden|permission|insufficient[_ -]?(quota|credit|balance)|billing|payment|subscription|plan[_ -]?(expired|required|inactive)|余额|额度|套餐|权限|密钥失效)/i.test(semantic);
  if (accountFailure) return { code: "provider_account_problem", failoverEligible: false };
  const modelUnavailable = status === 404
    || /(model[_ -]?(not[_ -]?found|unavailable|unsupported)|unknown[_ -]?model|no[_ -]?such[_ -]?model|模型不可用|没有.*模型)/i.test(semantic);
  if (modelUnavailable) return { code: "provider_model_unavailable", failoverEligible: true };
  const explicitRequestFailure = status === 400
    || status === 422
    || /(invalid|bad[_ -]?request|validation|unsupported|malformed|parameter|missing[_ -]?required)/i.test(semantic);
  if (explicitRequestFailure) return { code: "invalid_image_request", failoverEligible: false };
  const availabilityFailure = status === 405
    || status === 408
    || status === 429
    || status >= 500;
  if (availabilityFailure) return { code: "provider_request_unavailable", failoverEligible: true };
  return { code: "image_api_rejected", failoverEligible: false };
}

function classifyPreflightFailure(status) {
  const failoverEligible = status === "timeout"
    || status === "network-error"
    || status === "model-unavailable"
    || status === 404
    || status === 405
    || status === 408
    || status === 429
    || (typeof status === "number" && status >= 500);
  if (status === "model-unavailable") return { code: "provider_model_unavailable", failoverEligible: true };
  return {
    code: failoverEligible ? "provider_preflight_unavailable" : "provider_preflight_rejected",
    failoverEligible,
  };
}

function plainApiFailureMessage(classification, status) {
  if (classification.code === "content_policy_rejected") return "当前渠道明确拒绝了这次生成，需要先调整图片要求。";
  if (classification.code === "provider_account_problem") return "当前渠道的密钥、账号权限、余额或套餐状态有问题，需要先修复该渠道。";
  if (classification.code === "provider_model_unavailable") return "当前渠道没有提供所需的生图模型。";
  if (classification.code === "invalid_image_request") return "这次图片要求或设置有问题，需要先修改请求。";
  if (classification.failoverEligible) return `当前渠道暂时不可用（状态 ${status}）。`;
  return `当前渠道拒绝了这次图片请求（状态 ${status}），需要先检查原因。`;
}

function remainingMs(deadline) {
  return Math.max(0, deadline - Date.now());
}

async function fetchWithTimeout(fetchImpl, url, init, timeoutMs, deadline, stage) {
  const allowedMs = Math.min(timeoutMs, remainingMs(deadline));
  if (allowedMs <= 0) {
    throw new ImageRouteError("The overall image operation timeout was exhausted.", {
      code: "operation_timeout",
      failoverEligible: false,
      stage,
    });
  }
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), allowedMs);
  try {
    return await fetchImpl(url, { ...init, signal: controller.signal });
  } catch (error) {
    const timedOut = error?.name === "AbortError";
    throw new ImageRouteError(timedOut ? `Image ${stage} timed out.` : `Image ${stage} failed because of a network error.`, {
      code: timedOut ? `${stage}_timeout` : `${stage}_network_error`,
      failoverEligible: true,
      stage,
    });
  } finally {
    clearTimeout(timer);
  }
}

async function performFormalImageRequest({
  candidate,
  buildRequest,
  fetchImpl,
  requestTimeoutMs,
  downloadTimeoutMs,
  deadline,
  onRequestSent,
}) {
  let request;
  try {
    request = await buildRequest({
      alias: candidate.alias,
      baseUrl: candidate.provider.base_url,
      apiKey: candidate.provider.api_key,
      model: candidate.model,
    });
  } catch (error) {
    throw new ImageRouteError(`Image request could not be constructed: ${safeErrorBody(error?.message || error)}`, {
      code: "request_build_failed",
      failoverEligible: false,
      stage: "request-build",
    });
  }
  if (!request?.url || !request?.init) {
    throw new ImageRouteError("Image request factory did not return a URL and request options.", {
      code: "request_build_failed",
      failoverEligible: false,
      stage: "request-build",
    });
  }
  if (remainingMs(deadline) <= 0) {
    throw new ImageRouteError("The overall image operation timeout was exhausted before the request was sent.", {
      code: "operation_timeout",
      failoverEligible: false,
      stage: "request",
    });
  }
  onRequestSent();
  const response = await fetchWithTimeout(fetchImpl, request.url, request.init, requestTimeoutMs, deadline, "request");
  if (!response.ok) {
    const details = errorDetailsFromBody(await response.text());
    const classification = classifyApiFailure(response.status, details);
    throw new ImageRouteError(plainApiFailureMessage(classification, response.status), {
      ...classification,
      status: response.status,
      stage: "request",
    });
  }
  let json;
  try {
    json = await response.json();
  } catch {
    throw new ImageRouteError("Image API returned a non-JSON success response.", {
      code: "invalid_image_response",
      failoverEligible: true,
      stage: "result",
    });
  }
  const bytes = await extractGeneratedBytes(json, { fetchImpl, timeoutMs: downloadTimeoutMs, deadline });
  return { bytes, requestUrl: request.url };
}

export function serializeImageRouteError(error) {
  if (!(error instanceof ImageRouteError)) {
    return {
      status: "failed",
      error_code: "image_operation_failed",
      error: safeErrorBody(error?.message || error),
      route_mode: null,
      route_source: null,
      provider_candidates: [],
      attempted_aliases: [],
      failover_count: 0,
      billable_requests_sent: 0,
      attempts: [],
      duplicate_billing_risk: false,
    };
  }
  const result = {
    status: "failed",
    error_code: error.code || "image_route_failed",
    error: safeErrorBody(error.message),
    route_mode: error.route_mode || null,
    route_source: error.route_source || null,
    provider_candidates: error.provider_candidates || [],
    attempted_aliases: error.attempted_aliases || [],
    failover_count: error.failover_count || 0,
    billable_requests_sent: error.billable_requests_sent || 0,
    attempts: error.attempts || [],
    duplicate_billing_risk: Boolean(error.duplicate_billing_risk),
  };
  if (result.duplicate_billing_risk) {
    result.billing_warning = "More than one formal image request was sent; providers may charge more than once.";
  }
  return result;
}

export async function executeImageRequest({
  backend = process.env.RESEARCH_IMAGE_BACKEND || "ccswitch",
  providerAlias,
  model = "",
  configDir = DEFAULT_CONFIG_DIR,
  registryPath = process.env.RESEARCH_IMAGE_PROVIDER_REGISTRY || path.join(configDir, "providers.json"),
  dbPath = process.env.RESEARCH_IMAGE_CCSWITCH_DB,
  fetchImpl = fetch,
  buildRequest,
  probeTimeoutMs = DEFAULT_PROBE_TIMEOUT_MS,
  requestTimeoutMs = DEFAULT_REQUEST_TIMEOUT_MS,
  downloadTimeoutMs = DEFAULT_DOWNLOAD_TIMEOUT_MS,
  operationTimeoutMs = DEFAULT_OPERATION_TIMEOUT_MS,
} = {}) {
  const normalizedBackend = String(backend || "").trim().toLowerCase();
  const deadline = Date.now() + operationTimeoutMs;
  let billableRequestsSent = 0;
  const attempts = [];

  if (normalizedBackend === "direct") {
    await loadRuntimeEnv({ backend: "direct", configDir });
    requireLocalApiEnabled();
    const candidate = {
      alias: null,
      model: model || imageModel(),
      provider: { base_url: buildBaseUrl(), api_key: apiKey() },
    };
    try {
      const formal = await performFormalImageRequest({
        candidate,
        buildRequest,
        fetchImpl,
        requestTimeoutMs,
        downloadTimeoutMs,
        deadline,
        onRequestSent: () => { billableRequestsSent += 1; },
      });
      runtimeState.billable_requests_sent = billableRequestsSent;
      return {
        ...formal,
        model: candidate.model,
        selected_alias: null,
        route_mode: "direct",
        route_source: "direct",
        provider_candidates: [],
        attempted_aliases: [],
        failover_count: 0,
        billable_requests_sent: billableRequestsSent,
        duplicate_billing_risk: false,
      };
    } catch (error) {
      attempts.push({ alias: null, stage: error.stage || "request", code: error.code || "image_operation_failed", status: error.status || null });
      throw routeError("The direct image request failed.", {
        routeMode: "direct",
        routeSource: "direct",
        providerCandidates: [],
        attemptedAliases: [],
        attempts,
        billableRequestsSent,
        extra: { code: error.code || "image_operation_failed" },
      });
    }
  }

  if (normalizedBackend !== "ccswitch") throw new Error(`Unsupported RESEARCH_IMAGE_BACKEND: ${normalizedBackend}`);
  if (process.env.RESEARCH_IMAGE_CC_SWITCH_PROVIDER_ID || process.env.RESEARCH_IMAGE_CC_SWITCH_PROVIDER_NAME) {
    throw new Error("RESEARCH_IMAGE_CC_SWITCH_PROVIDER_ID and RESEARCH_IMAGE_CC_SWITCH_PROVIDER_NAME are no longer supported. Use a registered --provider alias.");
  }
  const prepared = await prepareCcSwitchRoute({
    providerAlias,
    model,
    registryPath,
    dbPath,
    fetchImpl,
    timeoutMs: probeTimeoutMs,
  });
  const attemptedAliases = [];
  let lastError = null;
  for (const entry of prepared.route.entries) {
    if (remainingMs(deadline) <= 0) {
      lastError = new ImageRouteError("The overall image operation timeout was exhausted before another provider could be tried.", {
        code: "operation_timeout",
        failoverEligible: false,
        stage: "route",
      });
      break;
    }
    attemptedAliases.push(entry.alias);
    let candidate;
    try {
      candidate = await prepared.probe(entry, remainingMs(deadline));
    } catch (error) {
      lastError = new ImageRouteError(`渠道 ${entry.alias} 的登记信息与 CC Switch 当前记录不一致，需要重新登记后再试。`, {
        code: "provider_registration_mismatch",
        failoverEligible: false,
        stage: "preflight",
      });
      attempts.push({ alias: entry.alias, stage: "preflight", code: lastError.code, status: null });
      break;
    }
    if (!candidate.ok) {
      const classification = classifyPreflightFailure(candidate.status);
      const message = classification.failoverEligible
        ? `渠道 ${entry.alias} 当前未通过生图模型检查，准备尝试下一渠道。`
        : `渠道 ${entry.alias} 的接入配置、账号或权限状态有问题，需要先修复该渠道。`;
      lastError = new ImageRouteError(message, {
        ...classification,
        stage: "preflight",
        status: candidate.status,
      });
      attempts.push({ alias: entry.alias, stage: "preflight", code: lastError.code, status: candidate.status });
      if (!lastError.failoverEligible) break;
      continue;
    }
    setCcSwitchRuntime({ registryPath, route: prepared.route, selected: candidate, attemptedAliases, billableRequestsSent });
    try {
      const formal = await performFormalImageRequest({
        candidate,
        buildRequest,
        fetchImpl,
        requestTimeoutMs,
        downloadTimeoutMs,
        deadline,
        onRequestSent: () => { billableRequestsSent += 1; },
      });
      setCcSwitchRuntime({ registryPath, route: prepared.route, selected: candidate, attemptedAliases, billableRequestsSent });
      return {
        ...formal,
        model: candidate.model,
        selected_alias: candidate.alias,
        route_mode: prepared.route.mode,
        route_source: prepared.route.source,
        provider_candidates: [...prepared.route.aliases],
        attempted_aliases: [...attemptedAliases],
        failover_count: Math.max(0, attemptedAliases.length - 1),
        billable_requests_sent: billableRequestsSent,
        duplicate_billing_risk: billableRequestsSent > 1,
      };
    } catch (error) {
      lastError = error instanceof ImageRouteError ? error : new ImageRouteError(safeErrorBody(error?.message || error), {
        code: "image_operation_failed",
        failoverEligible: false,
        stage: "request",
      });
      attempts.push({ alias: entry.alias, stage: lastError.stage || "request", code: lastError.code, status: lastError.status || null });
      if (!lastError.failoverEligible) break;
    }
  }
  const message = lastError && !lastError.failoverEligible
    ? lastError.message
    : "已按顺序尝试候选渠道，但仍未获得可用图片。";
  throw routeError(message, {
    routeMode: prepared.route.mode,
    routeSource: prepared.route.source,
    providerCandidates: prepared.route.aliases,
    attemptedAliases,
    attempts,
    billableRequestsSent,
    duplicateBillingRisk: billableRequestsSent > 1,
    extra: { code: lastError?.code || "image_route_failed" },
  });
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

function isRecognizedImageBytes(bytes) {
  if (!Buffer.isBuffer(bytes) || bytes.length < 8) return false;
  const png = bytes.subarray(0, 8).equals(Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]));
  const jpeg = bytes[0] === 0xff && bytes[1] === 0xd8 && bytes[2] === 0xff;
  const gif = bytes.subarray(0, 6).toString("ascii") === "GIF87a" || bytes.subarray(0, 6).toString("ascii") === "GIF89a";
  const webp = bytes.subarray(0, 4).toString("ascii") === "RIFF" && bytes.subarray(8, 12).toString("ascii") === "WEBP";
  return png || jpeg || gif || webp;
}

async function fetchBytesFromUrl(url, { fetchImpl = fetch, timeoutMs = DEFAULT_DOWNLOAD_TIMEOUT_MS, deadline = Date.now() + timeoutMs } = {}) {
  const response = await fetchWithTimeout(fetchImpl, url, {}, timeoutMs, deadline, "download");
  if (!response.ok) {
    throw new ImageRouteError(`Failed to download generated image (${response.status}).`, {
      code: "image_download_failed",
      failoverEligible: true,
      status: response.status,
      stage: "download",
    });
  }
  const bytes = Buffer.from(await response.arrayBuffer());
  if (!isRecognizedImageBytes(bytes)) {
    throw new ImageRouteError("Downloaded image bytes were empty or not a recognized image format.", {
      code: "invalid_image_data",
      failoverEligible: true,
      stage: "result",
    });
  }
  return bytes;
}

export async function extractGeneratedBytes(json, options = {}) {
  const first = json?.data?.[0];
  if (!first) {
    throw new ImageRouteError("API response did not include data[0].", {
      code: "invalid_image_response",
      failoverEligible: true,
      stage: "result",
    });
  }
  if (typeof first.b64_json === "string" && first.b64_json.trim()) {
    const encoded = first.b64_json.replace(/\s+/g, "");
    const base64Pattern = /^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/;
    const bytes = base64Pattern.test(encoded) ? Buffer.from(encoded, "base64") : Buffer.alloc(0);
    if (!isRecognizedImageBytes(bytes)) {
      throw new ImageRouteError("API returned base64 data that is not a recognized image.", {
        code: "invalid_image_data",
        failoverEligible: true,
        stage: "result",
      });
    }
    return bytes;
  }
  if (typeof first.url === "string" && first.url.trim()) return fetchBytesFromUrl(first.url, options);
  throw new ImageRouteError("API response did not include b64_json or url.", {
    code: "invalid_image_response",
    failoverEligible: true,
    stage: "result",
  });
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
