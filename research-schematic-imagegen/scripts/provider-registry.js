// Private Cici Switch image-provider registry. Registry entries never contain API keys.
import path from "node:path";
import os from "node:os";
import { access, mkdir, readFile, rename, rm, writeFile } from "node:fs/promises";
import {
  DEFAULT_CCSWITCH_DB,
  probeCcSwitchProviderModels,
  readCcSwitchImageProvider,
  toPublicCcSwitchProvider,
} from "./ccswitch.js";

export const PROVIDER_REGISTRY_FILENAME = "providers.json";
export const DEFAULT_PROVIDER_CONFIG_DIR = process.env.RESEARCH_IMAGE_CONFIG_DIR
  || path.join(os.homedir(), ".config", "research-schematic-imagegen");

const ENTRY_FIELDS = new Set(["alias", "provider_id", "app_type", "expected_name", "default_model"]);

export function defaultProviderRegistryPath(configDir = DEFAULT_PROVIDER_CONFIG_DIR) {
  return path.resolve(configDir, PROVIDER_REGISTRY_FILENAME);
}

function registryError(message) {
  return new Error(`Invalid image provider registry: ${message}`);
}

function requireString(value, field, context) {
  if (typeof value !== "string" || !value.trim()) throw registryError(`${context}.${field} must be a non-empty string.`);
  return value.trim();
}

function normalizeEntry(entry, index) {
  const context = `providers[${index}]`;
  if (!entry || typeof entry !== "object" || Array.isArray(entry)) throw registryError(`${context} must be an object.`);
  for (const key of Object.keys(entry)) {
    if (!ENTRY_FIELDS.has(key)) throw registryError(`${context} contains unsupported field ${key}.`);
  }
  return {
    alias: requireString(entry.alias, "alias", context),
    provider_id: requireString(entry.provider_id, "provider_id", context),
    app_type: requireString(entry.app_type, "app_type", context),
    expected_name: requireString(entry.expected_name, "expected_name", context),
    default_model: requireString(entry.default_model, "default_model", context),
  };
}

export function validateProviderRegistry(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw registryError("root must be an object.");
  const keys = Object.keys(value);
  if (keys.some((key) => key !== "version" && key !== "providers")) throw registryError("root contains unsupported fields.");
  if (value.version !== 1) throw registryError("version must be 1.");
  if (!Array.isArray(value.providers)) throw registryError("providers must be an array.");
  const providers = value.providers.map(normalizeEntry);
  const aliases = new Set();
  const ids = new Set();
  for (const provider of providers) {
    if (aliases.has(provider.alias)) throw registryError(`duplicate alias ${provider.alias}.`);
    if (ids.has(provider.provider_id)) throw registryError(`duplicate provider_id ${provider.provider_id}.`);
    aliases.add(provider.alias);
    ids.add(provider.provider_id);
  }
  return { version: 1, providers };
}

async function fileExists(filePath) {
  try {
    await access(filePath);
    return true;
  } catch {
    return false;
  }
}

export async function readProviderRegistry(registryPath = defaultProviderRegistryPath(), { allowMissing = false } = {}) {
  const resolved = path.resolve(registryPath);
  if (!(await fileExists(resolved))) {
    if (allowMissing) return { path: resolved, registry: { version: 1, providers: [] } };
    throw new Error(`No private image provider registry found at ${resolved}. Register a Cici Switch image provider first.`);
  }
  let parsed;
  try {
    parsed = JSON.parse(await readFile(resolved, "utf8"));
  } catch (error) {
    throw registryError(`${resolved} cannot be read as JSON (${error.message}).`);
  }
  return { path: resolved, registry: validateProviderRegistry(parsed) };
}

export function registeredAliases(registry) {
  return registry.providers.map((provider) => provider.alias);
}

function chooseRegistryEntry(registry, alias) {
  const aliases = registeredAliases(registry);
  const requested = String(alias || "").trim();
  if (!requested) {
    const choices = aliases.length > 0 ? aliases.join(", ") : "none";
    throw new Error(`Choose a registered Cici Switch image provider with --provider. Available aliases: ${choices}.`);
  }
  const entry = registry.providers.find((provider) => provider.alias === requested);
  if (!entry) {
    const choices = aliases.length > 0 ? aliases.join(", ") : "none";
    throw new Error(`Unknown registered image provider alias: ${requested}. Available aliases: ${choices}.`);
  }
  return entry;
}

function providerForEntry(provider, entry) {
  if (!provider) throw new Error(`Registered image provider ${entry.alias} is no longer present in CC Switch.`);
  if (provider.name !== entry.expected_name) {
    throw new Error(`Registered image provider ${entry.alias} changed name in CC Switch. Re-register it before use.`);
  }
  if (provider.app_type !== entry.app_type) {
    throw new Error(`Registered image provider ${entry.alias} changed app type in CC Switch. Re-register it before use.`);
  }
  return provider;
}

export async function loadRegisteredCcSwitchImageProvider({
  registryPath = defaultProviderRegistryPath(),
  dbPath = DEFAULT_CCSWITCH_DB,
  alias = "",
  model = "",
  fetchImpl = fetch,
  timeoutMs = 10000,
} = {}) {
  const { registry } = await readProviderRegistry(registryPath);
  const entry = chooseRegistryEntry(registry, alias);
  const candidate = await readCcSwitchImageProvider(entry.provider_id, dbPath);
  const provider = providerForEntry(candidate, entry);
  const probe = await probeCcSwitchProviderModels(provider, { fetchImpl, timeoutMs });
  if (!probe.ok) {
    throw new Error(`Registered image provider ${entry.alias} failed its /models check (${probe.status}).`);
  }
  const requestedModel = String(model || entry.default_model).trim();
  if (!probe.image_models.includes(requestedModel)) {
    throw new Error(`Registered image provider ${entry.alias} does not currently expose ${requestedModel}.`);
  }
  return {
    alias: entry.alias,
    model: requestedModel,
    image_models: probe.image_models,
    provider,
    public_provider: toPublicCcSwitchProvider(provider, probe),
  };
}

async function writeProviderRegistry(registryPath, registry) {
  const resolved = path.resolve(registryPath);
  await mkdir(path.dirname(resolved), { recursive: true });
  const temporary = path.join(
    path.dirname(resolved),
    `.${path.basename(resolved)}.${process.pid}.${Date.now()}.tmp`,
  );
  try {
    await writeFile(temporary, `${JSON.stringify(validateProviderRegistry(registry), null, 2)}\n`, { encoding: "utf8", mode: 0o600 });
    await rename(temporary, resolved);
  } finally {
    await rm(temporary, { force: true });
  }
  return resolved;
}

export async function registerCcSwitchImageProvider({
  registryPath = defaultProviderRegistryPath(),
  dbPath = DEFAULT_CCSWITCH_DB,
  alias,
  providerId,
  defaultModel = "gpt-image-2",
  replace = false,
  fetchImpl = fetch,
  timeoutMs = 10000,
} = {}) {
  const normalizedAlias = requireString(alias, "alias", "registration");
  const normalizedProviderId = requireString(providerId, "providerId", "registration");
  const normalizedModel = requireString(defaultModel, "defaultModel", "registration");
  const provider = await readCcSwitchImageProvider(normalizedProviderId, dbPath);
  if (!provider) throw new Error(`CC Switch provider not found: ${normalizedProviderId}.`);
  const probe = await probeCcSwitchProviderModels(provider, { fetchImpl, timeoutMs });
  if (!probe.ok) throw new Error(`CC Switch provider ${provider.name} failed its /models check (${probe.status}).`);
  if (!probe.image_models.includes(normalizedModel)) {
    throw new Error(`CC Switch provider ${provider.name} does not expose ${normalizedModel}.`);
  }
  const { registry } = await readProviderRegistry(registryPath, { allowMissing: true });
  const entry = {
    alias: normalizedAlias,
    provider_id: provider.id,
    app_type: provider.app_type,
    expected_name: provider.name,
    default_model: normalizedModel,
  };
  const aliasIndex = registry.providers.findIndex((candidate) => candidate.alias === entry.alias);
  const idIndex = registry.providers.findIndex((candidate) => candidate.provider_id === entry.provider_id);
  if (aliasIndex !== -1 && !replace) throw new Error(`Registry alias already exists: ${entry.alias}. Use --replace to update it.`);
  if (idIndex !== -1 && idIndex !== aliasIndex && !replace) {
    throw new Error(`CC Switch provider is already registered as ${registry.providers[idIndex].alias}.`);
  }
  const providersAfterRegistration = registry.providers.filter((candidate) => candidate.alias !== entry.alias && candidate.provider_id !== entry.provider_id);
  providersAfterRegistration.push(entry);
  const savedPath = await writeProviderRegistry(registryPath, { version: 1, providers: providersAfterRegistration });
  return { registry_path: savedPath, entry, provider: toPublicCcSwitchProvider(provider, probe) };
}
