import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
const root = path.dirname(fileURLToPath(import.meta.url));
const state = JSON.parse(fs.readFileSync(path.join(root, 'owner-state.json'), 'utf8'));
const url = new URL('/stop', state.controlUrl);
if (url.hostname !== '127.0.0.1' || [3456, 3457].includes(Number(url.port))) throw new Error('Invalid owner control endpoint');
const response = await fetch(url, { method: 'POST', headers: { 'X-Environment-Owner': state.shutdownSecret }, signal: AbortSignal.timeout(5000) });
process.stdout.write(JSON.stringify({ status: response.status, body: await response.json(), ownPids: { manager: state.managerPid, edge: state.edgePid, proxy: state.proxyPid } }) + '\n');
