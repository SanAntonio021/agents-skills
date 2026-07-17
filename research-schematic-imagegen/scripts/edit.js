#!/usr/bin/env node
// Adapted from ConardLi/garden-skills gpt-image-2 v1.0.4 under the MIT License.
import process from "node:process";
import { readFile } from "node:fs/promises";
import {
  appendIfPresent,
  buildBaseUrl,
  buildDefaultImagePath,
  ensureFilesExist,
  extractGeneratedBytes,
  imageModel,
  loadRuntimeEnv,
  mimeFor,
  postMultipart,
  printJson,
  readPromptInput,
  requireLocalApiEnabled,
  resolveOutput,
  saveImage,
  savePrompt,
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

async function buildForm(cfg, prompt) {
  const form = new FormData();
  const imageBytes = await readFile(cfg.image);
  form.append("image", new Blob([imageBytes], { type: mimeFor(cfg.image) }), cfg.image.split(/[\\/]/).pop());
  if (cfg.mask) {
    const maskBytes = await readFile(cfg.mask);
    form.append("mask", new Blob([maskBytes], { type: mimeFor(cfg.mask) }), cfg.mask.split(/[\\/]/).pop());
  }
  form.append("prompt", prompt);
  form.append("model", cfg.model || imageModel());
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
  await loadRuntimeEnv();
  requireLocalApiEnabled();
  await ensureFilesExist([cfg.image, ...(cfg.mask ? [cfg.mask] : [])], "Image file");
  const prompt = await readPromptInput(cfg.prompt, cfg.promptFile);
  const hint = slugify(prompt.split(/\s+/).slice(0, 8).join(" "), "scientific-schematic-edit");
  const promptPath = await savePrompt(prompt, cfg.promptOutput, hint);
  const outputPath = resolveOutput(cfg.output, buildDefaultImagePath("edit", hint));
  const requestUrl = `${buildBaseUrl()}/images/edits`;
  const bytes = await extractGeneratedBytes(await postMultipart(requestUrl, await buildForm(cfg, prompt)));
  await saveImage(outputPath, bytes);
  const result = { savedImage: outputPath, savedPrompt: promptPath, model: cfg.model || imageModel(), requestUrl };
  if (cfg.json) printJson(result);
  else console.log(outputPath);
}

run().catch((error) => {
  console.error(error instanceof Error ? error.message : String(error));
  process.exit(1);
});
