#!/usr/bin/env node
import process from "node:process";
import { DEFAULT_CCSWITCH_DB, inspectCcSwitchImageProviderCandidate } from "./ccswitch.js";

function parse(argv) {
  const config = { dbPath: DEFAULT_CCSWITCH_DB, providerId: "", json: false };
  for (let i = 2; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === "--db" || arg === "--provider-id") {
      const value = argv[++i];
      if (!value) throw new Error(`Missing value for ${arg}`);
      config[arg === "--db" ? "dbPath" : "providerId"] = value;
    } else if (arg === "--json") config.json = true;
    else if (arg === "-h" || arg === "--help") config.help = true;
    else throw new Error(`Unknown option: ${arg}`);
  }
  return config;
}

try {
  const config = parse(process.argv);
  if (config.help) {
    console.log("Usage: node scripts/discover-ccswitch-image-providers.js --provider-id <id> [--db path] [--json]");
    process.exit(0);
  }
  if (!config.providerId) throw new Error("--provider-id is required; this command only inspects one targeted CC Switch candidate.");
  const result = await inspectCcSwitchImageProviderCandidate(config);
  console.log(JSON.stringify(result, null, 2));
} catch (error) {
  console.error(error.message);
  process.exitCode = 1;
}
