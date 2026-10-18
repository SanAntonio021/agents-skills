import fs from 'node:fs';
import path from 'node:path';
import { spawn } from 'node:child_process';
import { randomUUID } from 'node:crypto';
import { fileURLToPath } from 'node:url';

const root = path.dirname(fileURLToPath(import.meta.url));
const runtime = JSON.parse(fs.readFileSync(path.join(root, 'client-runtime.json'), 'utf8'));
const [session, operation, ...args] = process.argv.slice(2);
if (!session || !/^[a-zA-Z0-9_-]{1,80}$/.test(session)) throw new Error('A unique alphanumeric SESSION is required.');
const sessionRoot = path.join(runtime.tempRoot, 'sessions', session);
fs.mkdirSync(sessionRoot, { recursive: true });
const authFile = path.join(sessionRoot, 'auth.private.json');
const logFile = path.join(sessionRoot, 'traffic.jsonl');
const auth = fs.existsSync(authFile) ? JSON.parse(fs.readFileSync(authFile, 'utf8')) : {};
const startedAt = new Date().toISOString();
function sanitize(value, key = '') {
  if (/^(taskToken|token|authorization|cookie|set-cookie|secret|password)$/i.test(key)) return '[REDACTED]';
  if (Array.isArray(value)) return value.map(item => sanitize(item));
  if (value && typeof value === 'object') return Object.fromEntries(Object.entries(value).map(([k, v]) => [k, sanitize(v, k)]));
  if (typeof value === 'string') {
    let text = value;
    if (auth.taskToken) text = text.split(auth.taskToken).join('[REDACTED]');
    return text.replace(/("(?:taskToken|token|authorization|cookie|secret|password)"\s*:\s*")[^"]*(")/gi, '$1[REDACTED]$2').replace(/Bearer\s+[^\s"']+/gi, 'Bearer [REDACTED]');
  }
  return value;
}
function record(value) {
  const result = sanitize({ session, operation, startedAt, endedAt: new Date().toISOString(), ...value });
  fs.appendFileSync(logFile, JSON.stringify(result) + '\n');
  fs.appendFileSync(path.join(root, 'client-traffic.jsonl'), JSON.stringify(result) + '\n');
  return result;
}
function output(value) { process.stdout.write(JSON.stringify(value, null, 2) + '\n'); }
async function performFetch(url, options) {
  const response = await fetch(url, { ...options, redirect: 'manual', signal: AbortSignal.timeout(35000) });
  const rawBody = await response.text();
  let body; try { body = JSON.parse(rawBody); } catch { body = rawBody; }
  return { status: response.status, finalUrl: response.url, headers: Object.fromEntries(response.headers), rawBody, body };
}
try {
  if (operation === 'read') {
    const url = new URL(args[0]);
    if (url.origin !== runtime.fixtureBase || url.username || url.password) throw new Error('read is restricted to the listed fixture origin');
    const request = { method: 'GET', url: url.href, headers: {} };
    const response = await performFetch(url, { method: 'GET' });
    const result = record({ request, response });
    output({ ...result, logFile });
  } else if (operation === 'check') {
    if (session === 'browser-unavailable') {
      output(record({ request: { tool: 'check-deps', mode: 'explicit unavailable simulation; no process or network call' }, response: { exitCode: 1, body: { ok: false, ready: false, status: 'browser_unavailable', browser: 'edge', reason: '此隔离测试会话没有可用浏览器或 Proxy。未连接生产浏览器接口。' } } }));
    } else {
      const env = { ...process.env, WEB_ACCESS_TEST_MODE: '1', WEB_ACCESS_TEST_ROOT: runtime.tempRoot, LOCALAPPDATA: runtime.localAppData, CDP_PROXY_PORT: String(runtime.proxyPort), WEB_ACCESS_EDGE_PORT: String(runtime.proxyPort), WEB_ACCESS_CHROME_PORT: String(runtime.chromePort) };
      const script = path.join(runtime.skillRoot, 'scripts/check-deps.mjs');
      const result = await new Promise((resolve, reject) => {
        const child = spawn(process.execPath, [script, '--browser', 'edge', '--json'], { env, stdio: ['ignore', 'pipe', 'pipe'], windowsHide: true });
        let stdout = '', stderr = '';
        child.stdout.on('data', data => stdout += data); child.stderr.on('data', data => stderr += data);
        child.on('error', reject); child.on('exit', exitCode => { let body; try { body = JSON.parse(stdout); } catch { body = stdout; } resolve({ exitCode, stdout, stderr, body }); });
      });
      output(record({ request: { executable: process.execPath, script, args: ['--browser', 'edge', '--json'], isolatedTestMode: true }, response: result }));
    }
  } else if (operation === 'request') {
    const [rawMethod, endpoint, bodyArgument = '{}'] = args;
    const method = rawMethod?.toUpperCase();
    if (!['GET', 'POST', 'DELETE'].includes(method)) throw new Error('Use a Proxy GET, POST, or DELETE method');
    if (!endpoint?.startsWith('/') || endpoint.startsWith('//') || !/^\/(health|capabilities|v2\/)/.test(endpoint)) throw new Error('Use an existing Proxy API path');
    const url = new URL(endpoint, runtime.proxyUrl);
    if (url.origin !== runtime.proxyUrl) throw new Error('Proxy request escaped isolated origin');
    let bodyText;
    if (method !== 'GET') bodyText = bodyArgument.startsWith('@') ? fs.readFileSync(bodyArgument.slice(1), 'utf8') : bodyArgument;
    if (bodyText !== undefined) JSON.parse(bodyText);
    const explicitKey = args.find(value => value.startsWith('--key='))?.slice(6);
    const headers = {};
    if (auth.taskToken) headers.Authorization = `Bearer ${auth.taskToken}`;
    if (method !== 'GET') { headers['Content-Type'] = 'application/json'; headers['Idempotency-Key'] = explicitKey || randomUUID(); }
    const request = { method, url: url.href, path: endpoint, headers, rawBody: bodyText };
    if (session === 'browser-unavailable') {
      output(record({ request, response: { status: null, body: { ok: false, status: 'browser_unavailable', reason: 'This session has no browser endpoint; no connection was attempted.' } } }));
    } else {
      const response = await performFetch(url, { method, headers, ...(bodyText === undefined ? {} : { body: bodyText }) });
      if (method === 'POST' && endpoint === '/v2/tasks' && response.status === 201 && response.body.taskToken) {
        auth.taskId = response.body.taskId; auth.taskToken = response.body.taskToken;
        fs.writeFileSync(authFile, JSON.stringify(auth), { mode: 0o600 });
      }
      output({ ...record({ request, response }), logFile });
    }
  } else throw new Error('Usage: client.mjs SESSION read URL | check | request METHOD PATH [JSON_BODY|@BODY_FILE] [--key=KEY]');
} catch (error) {
  output(record({ error: error.message })); process.exitCode = 1;
}
