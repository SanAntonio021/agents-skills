// Broker-side reader for the OS login credential store (see login-credential.ps1).
// The secret only travels through the child process stdout pipe into Broker
// memory; it is never logged, returned to callers or written to disk.
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const HELPER_SCRIPT = fileURLToPath(new URL('./login-credential.ps1', import.meta.url));
const READ_TIMEOUT_MS = 20000;
const MAX_OUTPUT_BYTES = 65536;
const PUBLIC_STATUSES = new Set(['not_configured', 'account_not_configured', 'account_ambiguous',
  'invalid_request', 'store_unavailable']);

export function credentialStoreInfo() {
  return { store: process.platform === 'win32' ? 'windows-credential-manager' : 'unavailable',
    key: 'origin+account', enrollment: 'scripts/login-credential.ps1 -Action Add' };
}

export async function readLoginCredential(origin, account = null) {
  if (process.platform !== 'win32' || process.env.WEB_ACCESS_TEST_MODE === '1') return { status: 'store_unavailable' };
  let normalized;
  try {
    const url = new URL(origin);
    if (url.protocol !== 'https:' || url.origin !== origin) return { status: 'invalid_request' };
    normalized = url.origin;
  } catch { return { status: 'invalid_request' }; }
  const request = JSON.stringify({ origin: normalized, ...(account ? { account: String(account) } : {}) });
  const output = await new Promise((resolve) => {
    let child;
    try {
      child = spawn('powershell.exe', ['-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
        '-File', HELPER_SCRIPT, '-Action', 'BrokerRead'], { windowsHide: true, stdio: ['pipe', 'pipe', 'ignore'] });
    } catch { resolve(null); return; }
    const chunks = [];
    let size = 0;
    const timer = setTimeout(() => { try { child.kill(); } catch {} resolve(null); }, READ_TIMEOUT_MS);
    child.stdout.on('data', (chunk) => {
      size += chunk.length;
      if (size > MAX_OUTPUT_BYTES) { try { child.kill(); } catch {} return; }
      chunks.push(chunk);
    });
    child.on('error', () => { clearTimeout(timer); resolve(null); });
    child.on('close', (code) => {
      clearTimeout(timer);
      const buffer = Buffer.concat(chunks);
      chunks.length = 0;
      resolve(code === 0 && size <= MAX_OUTPUT_BYTES ? buffer : null);
    });
    child.stdin.on('error', () => {});
    child.stdin.end(request);
  });
  if (!output) return { status: 'store_unavailable' };
  let parsed;
  try { parsed = JSON.parse(output.toString('utf8').trim().split(/\r?\n/).pop()); }
  catch { return { status: 'store_unavailable' }; }
  finally { output.fill(0); }
  if (parsed?.status === 'ok' && typeof parsed.secret === 'string' && typeof parsed.account === 'string' && parsed.account) {
    const bytes = Buffer.from(parsed.secret, 'base64');
    const secret = bytes.toString('utf8');
    bytes.fill(0);
    parsed.secret = null;
    if (!secret) return { status: 'not_configured' };
    return { status: 'ok', account: parsed.account, secret };
  }
  return { status: PUBLIC_STATUSES.has(parsed?.status) ? parsed.status : 'store_unavailable' };
}
