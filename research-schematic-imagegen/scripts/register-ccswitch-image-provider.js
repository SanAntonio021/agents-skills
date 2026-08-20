#!/usr/bin/env node
import process from "node:process";
import { DEFAULT_CCSWITCH_DB } from "./ccswitch.js";
import { defaultProviderRegistryPath, registerCcSwitchImageProvider } from "./provider-registry.js";

function help() {
  console.log(`Usage:
  node scripts/register-ccswitch-image-provider.js --alias <alias> --provider-id <id> [options]

Options:
  --alias <registered-alias>
  --provider-id <cc-switch-provider-id>
  --default-model <model>          Default: gpt-image-2
  --registry <private-registry-path>
  --db <cc-switch-db-path>
  --replace                         Replace the same alias or provider registration
  --json
  -h, --help`);
}

function parse(argv) {
  const config = {
    dbPath: DEFAULT_CCSWITCH_DB,
    registryPath: defaultProviderRegistryPath(),
    defaultModel: "gpt-image-2",
    replace: false,
    json: false,
  };
  const valued = new Map([
    ["--alias", "alias"],
    ["--provider-id", "providerId"],
    ["--default-model", "defaultModel"],
    ["--registry", "registryPath"],
    ["--db", "dbPath"],
  ]);
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (arg === "--replace") config.replace = true;
    else if (arg === "--json") config.json = true;
    else if (arg === "-h" || arg === "--help") config.help = true;
    else if (valued.has(arg)) {
      const value = argv[++index];
      if (!value) throw new Error(`Missing value for ${arg}`);
      config[valued.get(arg)] = value;
    } else throw new Error(`Unknown option: ${arg}`);
  }
  return config;
}

async function run() {
  const config = parse(process.argv.slice(2));
  if (config.help) return help();
  if (!config.alias) throw new Error("--alias is required");
  if (!config.providerId) throw new Error("--provider-id is required");
  const result = await registerCcSwitchImageProvider(config);
  if (config.json) console.log(JSON.stringify(result, null, 2));
  else console.log(`Registered ${result.entry.alias} in ${result.registry_path}`);
}

run().catch((error) => {
  console.error(error instanceof Error ? error.message : String(error));
  process.exit(1);
});
