#!/usr/bin/env node
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import http from 'node:http';
import net from 'node:net';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const testsRoot = path.dirname(fileURLToPath(import.meta.url));
const skillRoot = path.resolve(process.argv[2] || path.join(testsRoot, '..'));
const outputPath = process.argv[3] ? path.resolve(process.argv[3]) : null;
const proxyScript = path.join(skillRoot, 'scripts', 'cdp-proxy.mjs');
const fixturePath = path.join(testsRoot, 'fixtures', 'interactive.html');
const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'web-access-real-edge-'));
let keySequence = 0;
let edgeProcess = null;
let proxyProcess = null;
let fixtureServer = null;
let browserWebSocketUrl = null;

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function freePort() {
  const server = net.createServer();
  await new Promise((resolve, reject) => {
    server.once('error', reject);
    server.listen(0, '127.0.0.1', resolve);
  });
  const port = server.address().port;
  await new Promise((resolve) => server.close(resolve));
  return port;
}

function edgeExecutable() {
  const candidates = [
    process.env['PROGRAMFILES(X86)'] && path.join(process.env['PROGRAMFILES(X86)'], 'Microsoft', 'Edge', 'Application', 'msedge.exe'),
    process.env.PROGRAMFILES && path.join(process.env.PROGRAMFILES, 'Microsoft', 'Edge', 'Application', 'msedge.exe'),
    process.env.LOCALAPPDATA && path.join(process.env.LOCALAPPDATA, 'Microsoft', 'Edge', 'Application', 'msedge.exe'),
  ].filter(Boolean);
  const found = candidates.find((candidate) => fs.existsSync(candidate));
  if (!found) throw new Error('Microsoft Edge executable was not found.');
  return found;
}

async function waitForJson(url, timeoutMs = 15_000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(url, { signal: AbortSignal.timeout(1000) });
      if (response.ok) return await response.json();
    } catch {}
    await delay(50);
  }
  throw new Error(`Timed out waiting for ${url}`);
}

async function api(base, pathname, { method = 'GET', token, body, key, binary = false } = {}) {
  const headers = {};
  if (token) headers.Authorization = `Bearer ${token}`;
  if (method === 'POST' || method === 'DELETE') {
    headers['Content-Type'] = 'application/json';
    headers['Idempotency-Key'] = key || `real-${++keySequence}`;
  }
  const response = await fetch(`${base}${pathname}`, {
    method,
    headers,
    ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
    signal: AbortSignal.timeout(35_000),
  });
  const raw = Buffer.from(await response.arrayBuffer());
  if (binary) return { status: response.status, raw, contentType: response.headers.get('content-type') };
  let value;
  try { value = JSON.parse(raw.toString('utf8')); }
  catch { value = raw.toString('utf8'); }
  return { status: response.status, body: value };
}

function findRef(snapshot, name) {
  const normalize = (value) => String(value || '').replace(/\s+/g, ' ').trim();
  const node = snapshot.nodes.find((candidate) => normalize(candidate.name) === normalize(name) && candidate.ref);
  const available = snapshot.nodes.filter((candidate) => candidate.ref).map((candidate) => `${candidate.role}:${normalize(candidate.name)}`);
  assert.ok(node, `AX snapshot did not contain ref for ${name}; available=${JSON.stringify(available)}`);
  return node.ref;
}

async function closeBrowser() {
  if (!browserWebSocketUrl || typeof WebSocket === 'undefined') return;
  await new Promise((resolve) => {
    const socket = new WebSocket(browserWebSocketUrl);
    const timer = setTimeout(resolve, 2000);
    socket.addEventListener('open', () => socket.send(JSON.stringify({ id: 1, method: 'Browser.close' })));
    socket.addEventListener('message', () => {
      clearTimeout(timer);
      try { socket.close(); } catch {}
      resolve();
    });
    socket.addEventListener('error', () => {
      clearTimeout(timer);
      resolve();
    });
  });
}

async function stopChild(child) {
  if (!child || child.exitCode !== null) return;
  try { child.kill('SIGTERM'); } catch {}
  const deadline = Date.now() + 2000;
  while (child.exitCode === null && Date.now() < deadline) await delay(25);
  if (child.exitCode === null) {
    try { child.kill('SIGKILL'); } catch {}
  }
}

const report = { generatedAt: new Date().toISOString(), passed: false, checks: [] };

try {
  const fixture = fs.readFileSync(fixturePath);
  fixtureServer = http.createServer((req, res) => {
    if (req.url === '/' || req.url === '/interactive.html') {
      res.setHeader('Content-Type', 'text/html; charset=utf-8');
      res.end(fixture);
      return;
    }
    res.statusCode = 404;
    res.end();
  });
  await new Promise((resolve, reject) => {
    fixtureServer.once('error', reject);
    fixtureServer.listen(0, '127.0.0.1', resolve);
  });
  const fixturePort = fixtureServer.address().port;
  const fixtureUrl = `http://127.0.0.1:${fixturePort}/interactive.html`;

  const fakeLocalAppData = path.join(tempRoot, 'LocalAppData');
  const edgeUserData = path.join(fakeLocalAppData, 'Microsoft', 'Edge', 'User Data');
  fs.mkdirSync(edgeUserData, { recursive: true });
  const cdpPort = await freePort();
  edgeProcess = spawn(edgeExecutable(), [
    `--user-data-dir=${edgeUserData}`,
    `--remote-debugging-port=${cdpPort}`,
    '--headless=new',
    '--disable-gpu',
    '--no-first-run',
    '--no-default-browser-check',
    '--disable-features=msEdgeFirstRunExperience',
    'about:blank',
  ], { stdio: 'ignore', windowsHide: true });

  const version = await waitForJson(`http://127.0.0.1:${cdpPort}/json/version`);
  browserWebSocketUrl = version.webSocketDebuggerUrl;
  assert.ok(browserWebSocketUrl, 'Edge did not expose webSocketDebuggerUrl');
  const wsPath = new URL(browserWebSocketUrl).pathname;
  fs.writeFileSync(path.join(edgeUserData, 'DevToolsActivePort'), `${cdpPort}\n${wsPath}\n`);

  const proxyPort = await freePort();
  proxyProcess = spawn(process.execPath, [proxyScript, '--browser', 'edge'], {
    env: {
      ...process.env,
      WEB_ACCESS_TEST_MODE: '1',
      WEB_ACCESS_TEST_ROOT: tempRoot,
      LOCALAPPDATA: fakeLocalAppData,
      CDP_PROXY_PORT: String(proxyPort),
      WEB_ACCESS_EDGE_PORT: String(proxyPort),
    },
    stdio: ['ignore', 'pipe', 'pipe'],
    windowsHide: true,
  });
  let proxyLog = '';
  proxyProcess.stdout.on('data', (chunk) => { proxyLog += chunk; });
  proxyProcess.stderr.on('data', (chunk) => { proxyLog += chunk; });
  const base = `http://127.0.0.1:${proxyPort}`;
  const health = await waitForJson(`${base}/health`);
  const deadline = Date.now() + 10_000;
  let connected = health.connected;
  while (!connected && Date.now() < deadline) {
    connected = (await waitForJson(`${base}/health`, 1000)).connected;
    if (!connected) await delay(50);
  }
  assert.equal(connected, true, proxyLog);

  const taskResult = await api(base, '/v2/tasks', { method: 'POST', body: {} });
  assert.equal(taskResult.status, 201, JSON.stringify(taskResult.body));
  const task = taskResult.body;
  const tabResult = await api(base, '/v2/tabs', { method: 'POST', token: task.taskToken, body: { url: fixtureUrl } });
  assert.equal(tabResult.status, 201, JSON.stringify(tabResult.body));
  const targetId = tabResult.body.targetId;
  const targetPath = `/v2/tabs/${encodeURIComponent(targetId)}`;

  const createdUrl = await api(base, `${targetPath}/eval`, {
    method: 'POST', token: task.taskToken, body: { expression: 'location.href' },
  });
  assert.equal(createdUrl.status, 200, JSON.stringify(createdUrl.body));
  assert.equal(createdUrl.body.value, fixtureUrl, JSON.stringify(createdUrl.body));
  report.checks.push('real-created-tab-requested-url');

  const load = await api(base, `${targetPath}/wait`, { method: 'POST', token: task.taskToken, body: { state: 'load', timeoutMs: 10_000 } });
  assert.equal(load.status, 200, JSON.stringify(load.body));
  let snapshot = (await api(base, `${targetPath}/snapshot?refresh=true`, { token: task.taskToken })).body;
  assert.ok(snapshot.nodes.length >= 6);
  report.checks.push('real-ax-tree');

  const nameFill = await api(base, `${targetPath}/action`, {
    method: 'POST', token: task.taskToken,
    body: { action: 'fill', ref: findRef(snapshot, 'Name'), value: 'Alice' },
  });
  assert.equal(nameFill.status, 200, JSON.stringify(nameFill.body));
  const controlled = await api(base, `${targetPath}/eval`, {
    method: 'POST', token: task.taskToken,
    body: { expression: `({value: document.querySelector('#name').value, controlled: document.querySelector('#name').dataset.controlledValue})` },
  });
  assert.deepEqual(controlled.body.value, { value: 'Alice', controlled: 'Alice' });
  report.checks.push('react-style-input-events');

  snapshot = (await api(base, `${targetPath}/snapshot?refresh=true`, { token: task.taskToken })).body;
  const notesFill = await api(base, `${targetPath}/action`, {
    method: 'POST', token: task.taskToken,
    body: { action: 'fill', ref: findRef(snapshot, 'Notes'), value: 'Editable text' },
  });
  assert.equal(notesFill.status, 200, JSON.stringify(notesFill.body));
  report.checks.push('contenteditable-fill');

  snapshot = (await api(base, `${targetPath}/snapshot?refresh=true`, { token: task.taskToken })).body;
  const check = await api(base, `${targetPath}/action`, {
    method: 'POST', token: task.taskToken,
    body: { action: 'check', ref: findRef(snapshot, 'Remember') },
  });
  assert.equal(check.status, 200, JSON.stringify(check.body));

  snapshot = (await api(base, `${targetPath}/snapshot?refresh=true`, { token: task.taskToken })).body;
  const select = await api(base, `${targetPath}/action`, {
    method: 'POST', token: task.taskToken,
    body: { action: 'select', ref: findRef(snapshot, 'Choices'), values: ['two', 'one'] },
  });
  assert.equal(select.status, 200, JSON.stringify(select.body));
  assert.deepEqual(new Set(select.body.values), new Set(['one', 'two']));
  report.checks.push('checkbox-and-multiselect');

  snapshot = (await api(base, `${targetPath}/snapshot?refresh=true`, { token: task.taskToken })).body;
  const staleRef = findRef(snapshot, 'Submit');
  const redraw = await api(base, `${targetPath}/eval`, { method: 'POST', token: task.taskToken, body: { expression: 'window.replaceSubmit(); true' } });
  assert.equal(redraw.status, 200, JSON.stringify(redraw.body));
  const stale = await api(base, `${targetPath}/action`, { method: 'POST', token: task.taskToken, body: { action: 'click', ref: staleRef } });
  assert.equal(stale.status, 409, JSON.stringify(stale.body));
  assert.equal(stale.body.code, 'STALE_REF');
  report.checks.push('dynamic-stale-ref');

  const schedule = await api(base, `${targetPath}/eval`, { method: 'POST', token: task.taskToken, body: { expression: 'window.scheduleSaved(); true' } });
  assert.equal(schedule.status, 200);
  const textWait = await api(base, `${targetPath}/wait`, { method: 'POST', token: task.taskToken, body: { text: 'Saved', timeoutMs: 3000 } });
  assert.equal(textWait.status, 200, JSON.stringify(textWait.body));
  report.checks.push('real-wait');

  snapshot = (await api(base, `${targetPath}/snapshot?refresh=true`, { token: task.taskToken })).body;
  const dialogAction = await api(base, `${targetPath}/action`, {
    method: 'POST', token: task.taskToken,
    body: { action: 'click', ref: findRef(snapshot, 'Open dialog') },
  });
  assert.equal(dialogAction.status, 200, JSON.stringify(dialogAction.body));
  await delay(50);
  const tabInfo = await api(base, targetPath, { token: task.taskToken });
  assert.equal(tabInfo.body.dialog?.type, 'confirm', JSON.stringify(tabInfo.body));
  const dismiss = await api(base, `${targetPath}/dialog`, { method: 'POST', token: task.taskToken, body: { action: 'dismiss' } });
  assert.equal(dismiss.status, 200, JSON.stringify(dismiss.body));
  report.checks.push('dialog-default-pending-and-dismiss');

  const screenshot = await api(base, `${targetPath}/screenshot`, { token: task.taskToken, binary: true });
  assert.equal(screenshot.status, 200);
  assert.equal(screenshot.contentType, 'image/png');
  assert.ok(screenshot.raw.length > 100);
  report.checks.push('real-screenshot');

  const complete = await api(base, `/v2/tasks/${encodeURIComponent(task.taskId)}/complete`, {
    method: 'POST', token: task.taskToken, body: { keep: false },
  });
  assert.equal(complete.status, 200, JSON.stringify(complete.body));
  report.passed = true;
} catch (error) {
  report.error = error.stack || error.message;
} finally {
  await stopChild(proxyProcess);
  await closeBrowser();
  await stopChild(edgeProcess);
  if (fixtureServer) await new Promise((resolve) => fixtureServer.close(resolve));
  try {
    await fs.promises.rm(tempRoot, { recursive: true, force: true, maxRetries: 10, retryDelay: 100 });
  } catch (error) {
    report.passed = false;
    report.cleanupError = error.stack || error.message;
    report.error ||= `Failed to remove isolated Edge test directory: ${tempRoot}`;
  }
}

if (outputPath) {
  fs.mkdirSync(path.dirname(outputPath), { recursive: true });
  fs.writeFileSync(outputPath, `${JSON.stringify(report, null, 2)}\n`);
}
process.stdout.write(`${JSON.stringify(report, null, 2)}\n`);
process.exitCode = report.passed ? 0 : 1;
