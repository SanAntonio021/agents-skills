#!/usr/bin/env node
// Adapted from ConardLi/garden-skills gpt-image-2 v1.0.4 under the MIT License.
import process from "node:process";
import { apiKey, buildBaseUrl, imageApiEnabled, imageModel, loadRuntimeEnv } from "./shared.js";

await loadRuntimeEnv();

let mode;
let recommendation;
let summary;

if (imageApiEnabled() && apiKey()) {
  mode = "A";
  recommendation = "local-api-enabled";
  summary = "Local OpenAI-compatible image generation is enabled. Use generate.js or edit.js only within the approved scope.";
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
  summary,
};

if (process.argv.includes("--json")) {
  console.log(JSON.stringify(result, null, 2));
} else {
  for (const [key, value] of Object.entries(result)) console.log(`${key}: ${value}`);
}
