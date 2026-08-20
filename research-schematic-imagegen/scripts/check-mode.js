#!/usr/bin/env node
// Adapted from ConardLi/garden-skills gpt-image-2 v1.0.4 under the MIT License.
import process from "node:process";
import { apiKey, buildBaseUrl, imageApiEnabled, imageModel, loadRuntimeEnv, runtimeInfo } from "./shared.js";

function parse(argv) {
  const config = { json: false };
  const valued = new Map([
    ["--provider", "provider"],
    ["--backend", "backend"],
    ["--model", "model"],
  ]);
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (arg === "--json") config.json = true;
    else if (arg === "-h" || arg === "--help") config.help = true;
    else if (valued.has(arg)) {
      const value = argv[++index];
      if (!value) throw new Error(`Missing value for ${arg}`);
      config[valued.get(arg)] = value;
    } else throw new Error(`Unknown option: ${arg}`);
  }
  return config;
}

const config = parse(process.argv.slice(2));
if (config.help) {
  console.log("Usage: node scripts/check-mode.js [--provider registered-alias] [--backend ccswitch|direct] [--model model] [--json]");
  process.exit(0);
}

let envFile = null;
try {
  envFile = await loadRuntimeEnv({ backend: config.backend, providerAlias: config.provider, model: config.model });
} catch (error) {
  const message = error instanceof Error ? error.message : String(error);
  const result = {
    mode: "blocked",
    recommendation: message.startsWith("Choose a registered Cici Switch image provider") || message.startsWith("Unknown registered image provider alias")
      ? "select-registered-provider"
      : "image-backend-error",
    error: message,
  };
  console.log(config.json ? JSON.stringify(result, null, 2) : Object.entries(result).map(([key, value]) => `${key}: ${value}`).join("\n"));
  process.exit(1);
}

let mode;
let recommendation;
let summary;

if (imageApiEnabled() && apiKey()) {
  mode = "A";
  recommendation = runtimeInfo().backend === "ccswitch" ? "registered-ccswitch-provider-enabled" : "direct-api-enabled";
  summary = "Image generation is enabled for the selected backend. Use generate.js or edit.js only within the approved scope.";
} else if (imageApiEnabled()) {
  mode = "A?";
  recommendation = "missing-key";
  summary = "Local image generation is enabled, but no API key is available.";
} else {
  mode = "B-or-C";
  recommendation = "host-native-or-advisor";
  summary = "Local API calls are disabled. Use a host-native image tool, or produce prompts only.";
}

const result = {
  mode,
  recommendation,
  local_api_enabled: imageApiEnabled(),
  has_api_key: Boolean(apiKey()),
  base_url: buildBaseUrl(),
  model: imageModel(),
  env_file: envFile,
  backend: runtimeInfo().backend,
  provider: runtimeInfo().provider,
  summary,
};

if (config.json) {
  console.log(JSON.stringify(result, null, 2));
} else {
  for (const [key, value] of Object.entries(result)) console.log(`${key}: ${value}`);
}
