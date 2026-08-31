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
const ROUTING_FIELDS = new Set(["default_alias", "fallback_aliases"]);

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

function normalizeRouting(routing, providers) {
  if (!routing || typeof routing !== "object" || Array.isArray(routing)) {
    throw registryError("routing must be an object for version 2.");
  }
  for (const key of Object.keys(routing)) {
    if (!ROUTING_FIELDS.has(key)) throw registryError(`routing contains unsupported field ${key}.`);
  }
  const defaultAlias = requireString(routing.default_alias, "default_alias", "routing");
  if (!Array.isArray(routing.fallback_aliases)) throw registryError("routing.fallback_aliases must be an array.");
  const fallbackAliases = routing.fallback_aliases.map((alias, index) => requireString(alias, String(index), "routing.fallback_aliases"));
  const route = [defaultAlias, ...fallbackAliases];
  if (route.length < 1 || route.length > 3) throw registryError("routing must contain between 1 and 3 aliases.");
  if (new Set(route).size !== route.length) throw registryError("routing aliases must be unique.");
  const knownAliases = new Set(providers.map((provider) => provider.alias));
  for (const alias of route) {
    if (!knownAliases.has(alias)) throw registryError(`routing references unknown alias ${alias}.`);
  }
  return { default_alias: defaultAlias, fallback_aliases: fallbackAliases };
}

export function validateProviderRegistry(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw registryError("root must be an object.");
  const keys = Object.keys(value);
  if (keys.some((key) => key !== "version" && key !== "providers" && key !== "routing")) throw registryError("root contains unsupported fields.");
  if (value.version !== 1 && value.version !== 2) throw registryError("version must be 1 or 2.");
  if (value.version === 1 && Object.hasOwn(value, "routing")) throw registryError("version 1 must not contain routing.");
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
  if (value.version === 1) return { version: 1, providers };
  return { version: 2, providers, routing: normalizeRouting(value.routing, providers) };
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

function findRegistryEntry(registry, alias) {
  const aliases = registeredAliases(registry);
  const requested = String(alias || "").trim();
  const entry = registry.providers.find((provider) => provider.alias === requested);
  if (!entry) {
    const choices = aliases.length > 0 ? aliases.join(", ") : "none";
    throw new Error(`Unknown registered image provider alias: ${requested}. Available aliases: ${choices}.`);
  }
  return entry;
}

export function resolveProviderRoute(registryValue, explicitAlias = "") {
  const registry = validateProviderRegistry(registryValue);
  if (registry.version !== 2) {
    throw new Error("Image provider routing is not configured. Upgrade the private registry to version 2 with a default route.");
  }
  const defaultAliases = [registry.routing.default_alias, ...registry.routing.fallback_aliases];
  const requested = String(explicitAlias || "").trim();
  if (requested) {
    findRegistryEntry(registry, requested);
    const aliases = [requested, ...defaultAliases.filter((alias) => alias !== requested)];
    return { mode: "default", aliases, entries: aliases.map((alias) => findRegistryEntry(registry, alias)) };
  }
  return { mode: "default", aliases: defaultAliases, entries: defaultAliases.map((alias) => findRegistryEntry(registry, alias)) };
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
  const entry = resolveProviderRoute(registry, alias).entries[0];
  const result = await probeRegisteredCcSwitchImageProvider({
    registry,
    entry,
    dbPath,
    model,
    fetchImpl,
    timeoutMs,
  });
  if (!result.ok) {
    if (result.status === "model-unavailable") {
      throw new Error(`Registered image provider ${entry.alias} does not currently expose ${result.model}.`);
    }
    throw new Error(`Registered image provider ${entry.alias} failed its /models check (${result.status}).`);
  }
  return result;
}

export async function probeRegisteredCcSwitchImageProvider({
  registry: registryValue,
  entry: rawEntry,
  dbPath = DEFAULT_CCSWITCH_DB,
  model = "",
  fetchImpl = fetch,
  timeoutMs = 10000,
} = {}) {
  const registry = validateProviderRegistry(registryValue);
  const entry = findRegistryEntry(registry, rawEntry?.alias);
  const candidate = await readCcSwitchImageProvider(entry.provider_id, dbPath);
  const provider = providerForEntry(candidate, entry);
  const probe = await probeCcSwitchProviderModels(provider, { fetchImpl, timeoutMs });
  if (!probe.ok) {
    return {
      ok: false,
      alias: entry.alias,
      status: probe.status,
      image_models: probe.image_models,
      public_provider: toPublicCcSwitchProvider(provider, probe),
    };
  }
  const requestedModel = String(model || entry.default_model).trim();
  if (!probe.image_models.includes(requestedModel)) {
    return {
      ok: false,
      alias: entry.alias,
      status: "model-unavailable",
      model: requestedModel,
      image_models: probe.image_models,
      public_provider: toPublicCcSwitchProvider(provider, probe),
    };
  }
  return {
    ok: true,
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
  setDefault = false,
  fallbackAliases = [],
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
  if (!Array.isArray(fallbackAliases)) throw new Error("fallbackAliases must be an array.");
  if (fallbackAliases.length > 0 && !setDefault) throw new Error("--fallback-alias requires --set-default.");
  let updatedRegistry;
  if (setDefault) {
    updatedRegistry = {
      version: 2,
      providers: providersAfterRegistration,
      routing: {
        default_alias: entry.alias,
        fallback_aliases: fallbackAliases,
      },
    };
  } else if (registry.version === 2) {
    updatedRegistry = { version: 2, providers: providersAfterRegistration, routing: registry.routing };
  } else {
    updatedRegistry = { version: 1, providers: providersAfterRegistration };
  }
  const validatedRegistry = validateProviderRegistry(updatedRegistry);
  const savedPath = await writeProviderRegistry(registryPath, validatedRegistry);
  return {
    registry_path: savedPath,
    entry,
    routing: validatedRegistry.version === 2 ? validatedRegistry.routing : null,
    provider: toPublicCcSwitchProvider(provider, probe),
  };
}
