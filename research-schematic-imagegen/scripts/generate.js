#!/usr/bin/env node
// Adapted from ConardLi/garden-skills gpt-image-2 v1.0.4 under the MIT License.
import process from "node:process";
import {
  buildBaseUrl,
  buildDefaultImagePath,
  extractGeneratedBytes,
  imageModel,
  loadRuntimeEnv,
  postJson,
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
  node scripts/generate.js --prompt <text> [options]
  node scripts/generate.js --promptfile <path> [options]

Options:
  --prompt <text>
  --promptfile <path>
  --prompt-output <path>
  --image <path>
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
  await loadRuntimeEnv();
  requireLocalApiEnabled();
  const prompt = await readPromptInput(cfg.prompt, cfg.promptFile);
  const hint = slugify(prompt.split(/\s+/).slice(0, 8).join(" "), "scientific-schematic");
  const promptPath = await savePrompt(prompt, cfg.promptOutput, hint);
  const outputPath = resolveOutput(cfg.image, buildDefaultImagePath("generate", hint));
  const payload = {
    model: cfg.model || imageModel(),
    prompt,
    output_format: "png",
  };
  if (cfg.size) payload.size = cfg.size;
  if (cfg.quality) payload.quality = cfg.quality;
  if (cfg.background) payload.background = cfg.background;
  if (cfg.moderation) payload.moderation = cfg.moderation;
  const requestUrl = `${buildBaseUrl()}/images/generations`;
  const bytes = await extractGeneratedBytes(await postJson(requestUrl, payload));
  await saveImage(outputPath, bytes);
  const result = { savedImage: outputPath, savedPrompt: promptPath, model: payload.model, requestUrl };
  if (cfg.json) printJson(result);
  else console.log(outputPath);
}

run().catch((error) => {
  console.error(error instanceof Error ? error.message : String(error));
  process.exit(1);
});
