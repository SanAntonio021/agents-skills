#!/usr/bin/env node
import process from "node:process";
import { DEFAULT_CCSWITCH_DB, discoverCcSwitchImageProviders } from "./ccswitch.js";

function parse(argv) {
  const config = { dbPath: DEFAULT_CCSWITCH_DB, providerId: "", providerName: "" };
  for (let i = 2; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === "--db") config.dbPath = argv[++i];
    else if (arg === "--provider-id") config.providerId = argv[++i];
    else if (arg === "--provider-name") config.providerName = argv[++i];
    else if (arg === "-h" || arg === "--help") config.help = true;
  }
  return config;
}

const config = parse(process.argv);
if (config.help) {
  console.log("Usage: node scripts/discover-ccswitch-image-providers.js [--db path] [--provider-id id] [--provider-name name] [--json]");
  process.exit(0);
}

try {
  console.log(JSON.stringify(await discoverCcSwitchImageProviders(config), null, 2));
} catch (error) {
  console.error(error.message);
  process.exitCode = 1;
}
