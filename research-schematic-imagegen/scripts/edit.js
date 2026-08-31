#!/usr/bin/env node
// Adapted from ConardLi/garden-skills gpt-image-2 v1.0.4 under the MIT License.
import process from "node:process";
import { readFile } from "node:fs/promises";
import {
  appendIfPresent,
  buildDefaultImagePath,
  ensureFilesExist,
  executeImageRequest,
  mimeFor,
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
  node scripts/edit.js --image <source> --prompt <text> [options]
  node scripts/edit.js --image <source> --promptfile <path> [options]

Options:
  --image <path>               Required source image
  --mask <path>
  --prompt <text>
  --promptfile <path>
  --prompt-output <path>
  --output <path>
  --provider <registered-alias>
  --backend <ccswitch|direct>
  --model <name>
  --size <WxH|auto>
  --quality <auto|high|medium|low>
  --background <transparent|opaque|auto>
  --input-fidelity <low|high>
  --moderation <low|auto>
  --json
  -h, --help`);
}

function parse(argv) {
  const cfg = { json: false };
  const valued = new Map([
    ["--image", "image"],
    ["--mask", "mask"],
    ["--prompt", "prompt"],
    ["--promptfile", "promptFile"],
    ["--prompt-output", "promptOutput"],
    ["--output", "output"],
    ["--provider", "provider"],
    ["--backend", "backend"],
    ["--model", "model"],
    ["--size", "size"],
    ["--quality", "quality"],
    ["--background", "background"],
    ["--input-fidelity", "inputFidelity"],
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

async function buildForm(cfg, prompt, model) {
  const form = new FormData();
  const imageBytes = await readFile(cfg.image);
  form.append("image", new Blob([imageBytes], { type: mimeFor(cfg.image) }), cfg.image.split(/[\\/]/).pop());
  if (cfg.mask) {
    const maskBytes = await readFile(cfg.mask);
    form.append("mask", new Blob([maskBytes], { type: mimeFor(cfg.mask) }), cfg.mask.split(/[\\/]/).pop());
  }
  form.append("prompt", prompt);
  form.append("model", model);
  appendIfPresent(form, "size", cfg.size);
  appendIfPresent(form, "quality", cfg.quality);
  appendIfPresent(form, "background", cfg.background);
  appendIfPresent(form, "input_fidelity", cfg.inputFidelity);
  appendIfPresent(form, "moderation", cfg.moderation);
  form.append("output_format", "png");
  return form;
}

async function run() {
  const cfg = parse(process.argv.slice(2));
  if (cfg.help) return help();
  if (!cfg.image) throw new Error("--image is required");
  await ensureFilesExist([cfg.image, ...(cfg.mask ? [cfg.mask] : [])], "Image file");
  const prompt = await readPromptInput(cfg.prompt, cfg.promptFile);
  const hint = slugify(prompt.split(/\s+/).slice(0, 8).join(" "), "scientific-schematic-edit");
  const promptPath = await savePrompt(prompt, cfg.promptOutput, hint);
  const outputPath = resolveOutput(cfg.output, buildDefaultImagePath("edit", hint));
  const execution = await executeImageRequest({
    backend: cfg.backend,
    providerAlias: cfg.provider,
    model: cfg.model,
    buildRequest: async ({ baseUrl, apiKey, model }) => ({
      url: `${baseUrl}/images/edits`,
      init: {
        method: "POST",
        headers: { authorization: `Bearer ${apiKey}` },
        body: await buildForm(cfg, prompt, model),
      },
    }),
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
