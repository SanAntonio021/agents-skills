#!/usr/bin/env node
// Adapted from ConardLi/garden-skills gpt-image-2 v1.0.4 under the MIT License.
import process from "node:process";
import {
  buildDefaultImagePath,
  executeImageRequest,
  printJson,
  readPromptInput,
  resolveOutput,
  saveImage,
  savePrompt,
  serializeImageRouteError,
  slugify,
} from "./shared.js";

function help() {
  console.log(`Usage:
  node scripts/generate.js --prompt <text> [options]
  node scripts/generate.js --promptfile <path> [options]

Options:
  --prompt <text>
  --promptfile <path>
  --prompt-output <path>
  --image <path>
  --provider <registered-alias>
  --backend <ccswitch|direct>
  --model <name>
  --size <WxH>
  --quality <auto|high|medium|low>
  --background <transparent|opaque|auto>
  --moderation <low|auto>
  --json
  -h, --help`);
}

function parse(argv) {
  const cfg = { json: false };
  const valued = new Map([
    ["--prompt", "prompt"],
    ["--promptfile", "promptFile"],
    ["--prompt-output", "promptOutput"],
    ["--image", "image"],
    ["--provider", "provider"],
    ["--backend", "backend"],
    ["--model", "model"],
    ["--size", "size"],
    ["--quality", "quality"],
    ["--background", "background"],
    ["--moderation", "moderation"],
  ]);
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === "-h" || arg === "--help") cfg.help = true;
    else if (arg === "--json") cfg.json = true;
    else if (valued.has(arg)) {
      const value = argv[++i];
      if (!value) throw new Error(`Missing value for ${arg}`);
      cfg[valued.get(arg)] = value;
    } else throw new Error(`Unknown option: ${arg}`);
  }
  return cfg;
}

async function run() {
  const cfg = parse(process.argv.slice(2));
  if (cfg.help) return help();
  const prompt = await readPromptInput(cfg.prompt, cfg.promptFile);
  const hint = slugify(prompt.split(/\s+/).slice(0, 8).join(" "), "scientific-schematic");
  const promptPath = await savePrompt(prompt, cfg.promptOutput, hint);
  const outputPath = resolveOutput(cfg.image, buildDefaultImagePath("generate", hint));
  const execution = await executeImageRequest({
    backend: cfg.backend,
    providerAlias: cfg.provider,
    model: cfg.model,
    buildRequest: ({ baseUrl, apiKey, model }) => {
      const payload = { model, prompt, output_format: "png" };
      if (cfg.size) payload.size = cfg.size;
      if (cfg.quality) payload.quality = cfg.quality;
      if (cfg.background) payload.background = cfg.background;
      if (cfg.moderation) payload.moderation = cfg.moderation;
      return {
        url: `${baseUrl}/images/generations`,
        init: {
          method: "POST",
          headers: { authorization: `Bearer ${apiKey}`, "content-type": "application/json" },
          body: JSON.stringify(payload),
        },
      };
    },
  });
  await saveImage(outputPath, execution.bytes);
  const result = {
    savedImage: outputPath,
    savedPrompt: promptPath,
    model: execution.model,
    requestUrl: execution.requestUrl,
    backend: execution.route_mode === "direct" ? "direct" : "ccswitch",
    provider_alias: execution.selected_alias,
    selected_alias: execution.selected_alias,
    route_mode: execution.route_mode,
    route_source: execution.route_source,
    provider_candidates: execution.provider_candidates,
    attempted_aliases: execution.attempted_aliases,
    failover_count: execution.failover_count,
    billable_requests_sent: execution.billable_requests_sent,
    duplicate_billing_risk: execution.duplicate_billing_risk,
  };
  if (execution.duplicate_billing_risk) {
    result.billing_warning = "More than one formal image request was sent; providers may charge more than once.";
  }
  if (cfg.json) printJson(result);
  else console.log(outputPath);
}

const jsonRequested = process.argv.includes("--json");
run().catch((error) => {
  if (jsonRequested) printJson(serializeImageRouteError(error));
  else console.error(error instanceof Error ? error.message : String(error));
  process.exit(1);
});
