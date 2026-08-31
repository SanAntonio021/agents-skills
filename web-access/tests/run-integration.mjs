#!/usr/bin/env node
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import http from 'node:http';
import net from 'node:net';
import os from 'node:os';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import { startMockCdpServer } from './mock-cdp-server.mjs';

const skillRoot = path.resolve(process.argv[2] || '');
const outputPath = process.argv[3] ? path.resolve(process.argv[3]) : null;
const proxyScript = path.join(skillRoot, 'scripts', 'cdp-proxy.mjs');
const checkDepsScript = path.join(skillRoot, 'scripts', 'check-deps.mjs');
const runtimeConfigUrl = pathToFileURL(path.join(skillRoot, 'scripts', 'runtime-config.mjs')).href;

if (!fs.existsSync(proxyScript) || !fs.existsSync(checkDepsScript)) {
  throw new Error(`无效 skill 路径: ${skillRoot}`);
}

const proxySource = fs.readFileSync(proxyScript, 'utf8');
const checkDepsSource = fs.readFileSync(checkDepsScript, 'utf8');
const results = [];
const ownedChildren = new Set();
const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'web-access-dual-proxy-2-'));
let requestSequence = 0;

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

function nextKey(prefix = 'test') {
  return `${prefix}-${++requestSequence}`;
}

function spawnNode(args, env, options = {}) {
  const child = spawn(process.execPath, args, {
    env,
    windowsHide: true,
    stdio: ['ignore', 'pipe', 'pipe'],
    ...options,
  });
  child.stdoutText = '';
  child.stderrText = '';
  child.stdout?.on('data', (chunk) => { child.stdoutText += chunk; });
  child.stderr?.on('data', (chunk) => { child.stderrText += chunk; });
  ownedChildren.add(child);
  child.once('exit', () => ownedChildren.delete(child));
  return child;
}

function productionEnv(localAppData, extra = {}) {
  const env = { ...process.env, LOCALAPPDATA: localAppData, ...extra };
  delete env.WEB_ACCESS_TEST_MODE;
  delete env.WEB_ACCESS_TEST_ROOT;
  delete env.CDP_PROXY_PORT;
  return env;
}

function waitForExit(child, timeoutMs = 20000) {
  return new Promise((resolve, reject) => {
    if (child.exitCode !== null) return resolve(child.exitCode);
    const timer = setTimeout(() => reject(new Error(`进程超时: ${child.spawnargs.join(' ')}`)), timeoutMs);
    child.once('exit', (code) => {
      clearTimeout(timer);
      resolve(code);
    });
  });
}

async function request(url, options = {}, timeoutMs = 5000) {
  const response = await fetch(url, { ...options, signal: AbortSignal.timeout(timeoutMs) });
  const contentType = response.headers.get('content-type') || '';
  const raw = Buffer.from(await response.arrayBuffer());
  let body = raw;
  if (contentType.includes('json')) {
    try { body = JSON.parse(raw.toString('utf8')); }
    catch { body = raw.toString('utf8'); }
  } else if (contentType.startsWith('text/')) {
    body = raw.toString('utf8');
  }
  return { status: response.status, headers: response.headers, body, raw };
}

function jsonHeaders({ token, key, extra = {} } = {}) {
  const headers = { 'Content-Type': 'application/json', ...extra };
  if (token) headers.Authorization = `Bearer ${token}`;
  if (key) headers['Idempotency-Key'] = key;
  return headers;
}

function postJson(base, pathname, body, { token, key = nextKey(), headers, timeoutMs } = {}) {
  return request(`${base}${pathname}`, {
    method: 'POST',
    headers: jsonHeaders({ token, key, extra: headers }),
    body: JSON.stringify(body ?? {}),
  }, timeoutMs);
}

function getJson(base, pathname, token, headers = {}) {
  return request(`${base}${pathname}`, {
    headers: jsonHeaders({ token, extra: headers }),
  });
}

function assertStatus(result, ...allowed) {
  assert.ok(allowed.includes(result.status), `HTTP ${result.status}: ${JSON.stringify(result.body)}`);
}

function errorCode(body) {
  if (!body || typeof body !== 'object') return null;
  if (body.code) return body.code;
  if (typeof body.error === 'object') return body.error.code || null;
  return body.errorCode || null;
}

function assertError(result, status, code) {
  assert.equal(result.status, status, JSON.stringify(result.body));
  assert.equal(errorCode(result.body), code, JSON.stringify(result.body));
}

async function waitForHealth(port, timeoutMs = 10000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      const result = await request(`http://127.0.0.1:${port}/health`);
      if (result.status === 200 && result.body?.status === 'ok') return result.body;
    } catch {}
    await delay(50);
  }
  throw new Error(`Proxy ${port} 未在 ${timeoutMs}ms 内就绪`);
}

async function getHealth(port) {
  try {
    const result = await request(`http://127.0.0.1:${port}/health`);
    return result.status === 200 && result.body?.status === 'ok' ? result.body : null;
  } catch {
    return null;
  }
}

async function waitForNoHealth(port, timeoutMs = 5000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (!(await getHealth(port))) return;
    await delay(50);
  }
  throw new Error(`Proxy ${port} 未停止`);
}

async function waitUntil(predicate, description, timeoutMs = 4000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const value = await predicate();
    if (value) return value;
    await delay(25);
  }
  throw new Error(`等待超时: ${description}`);
}

function writeDevToolsPort(localAppData, browserId, port) {
  const relative = browserId === 'edge'
    ? path.join('Microsoft', 'Edge', 'User Data', 'DevToolsActivePort')
    : path.join('Google', 'Chrome', 'User Data', 'DevToolsActivePort');
  const target = path.join(localAppData, relative);
  fs.mkdirSync(path.dirname(target), { recursive: true });
  fs.writeFileSync(target, `${port}\n/devtools/browser/${browserId}\n`);
}

async function stopPid(pid) {
  if (!pid) return;
  try { process.kill(pid, 'SIGTERM'); }
  catch {}
}

async function stopChild(child) {
  if (!child || child.exitCode !== null) return;
  try { child.kill('SIGTERM'); }
  catch {}
  try { await waitForExit(child, 3000); }
  catch {
    try { child.kill('SIGKILL'); }
    catch {}
  }
}

async function runTest(name, fn) {
  const started = Date.now();
  try {
    const evidence = await fn();
    results.push({ name, passed: true, durationMs: Date.now() - started, evidence });
  } catch (error) {
    results.push({ name, passed: false, durationMs: Date.now() - started, evidence: error.stack || error.message });
  }
}

function tokenBytes(token) {
  if (/^[0-9a-f]{64}$/i.test(token)) return Buffer.from(token, 'hex').length;
  try { return Buffer.from(token, 'base64url').length; }
  catch { return 0; }
}

async function createTask(base, key = nextKey('task')) {
  const result = await postJson(base, '/v2/tasks', {}, { key });
  assertStatus(result, 200, 201);
  assert.equal(typeof result.body.taskId, 'string');
  assert.equal(tokenBytes(result.body.taskToken), 32, 'taskToken 必须包含 256-bit 随机值');
  return { taskId: result.body.taskId, taskToken: result.body.taskToken, key, response: result };
}

async function createTab(base, task, url, key = nextKey('tab')) {
  const result = await postJson(base, '/v2/tabs', { url }, { token: task.taskToken, key });
  assertStatus(result, 200, 201);
  assert.equal(typeof result.body.targetId, 'string');
  return { targetId: result.body.targetId, key, response: result };
}

function tabsFrom(body) {
  return Array.isArray(body) ? body : body?.tabs;
}

async function listTabs(base, task) {
  const result = await getJson(base, '/v2/tabs', task.taskToken);
  assert.equal(result.status, 200, JSON.stringify(result.body));
  const tabs = tabsFrom(result.body);
  assert.ok(Array.isArray(tabs), JSON.stringify(result.body));
  return tabs;
}

async function getSnapshot(base, task, targetId, query = '') {
  const result = await getJson(base, `/v2/tabs/${encodeURIComponent(targetId)}/snapshot${query}`, task.taskToken);
  assert.equal(result.status, 200, JSON.stringify(result.body));
  assert.ok(Number.isInteger(result.body.generation));
  assert.ok(Array.isArray(result.body.nodes));
  return result.body;
}

function valueOf(field) {
  return field && typeof field === 'object' && Object.hasOwn(field, 'value') ? field.value : field;
}

function findNode(snapshot, role, name = null) {
  const node = snapshot.nodes.find((candidate) => {
    const candidateRole = valueOf(candidate.role);
    const candidateName = valueOf(candidate.name);
    return candidateRole === role && (name === null || candidateName === name);
  });
  assert.ok(node, `snapshot 缺少 ${role}${name ? `:${name}` : ''}`);
  assert.equal(typeof node.ref, 'string', 'interactive node 必须含 ref');
  return node;
}

async function doAction(base, task, targetId, body, key = nextKey('action')) {
  return postJson(base, `/v2/tabs/${encodeURIComponent(targetId)}/action`, body, {
    token: task.taskToken,
    key,
  });
}

async function taskTransition(base, task, transition, body = {}, key = nextKey(transition)) {
  return postJson(base, `/v2/tasks/${encodeURIComponent(task.taskId)}/${transition}`, body, {
    token: task.taskToken,
    key,
  });
}

function rawHostRequest(port, host) {
  return new Promise((resolve, reject) => {
    const req = http.request({
      hostname: '127.0.0.1',
      port,
      path: '/health',
      method: 'GET',
      headers: { Host: host },
    }, (res) => {
      let text = '';
      res.setEncoding('utf8');
      res.on('data', (chunk) => { text += chunk; });
      res.on('end', () => {
        let body = text;
        try { body = JSON.parse(text); } catch {}
        resolve({ status: res.statusCode, body });
      });
    });
    req.once('error', reject);
    req.end();
  });
}

async function startIsolatedProxy(mock, extraEnv = {}) {
  const proxyPort = await freePort();
  const isolatedTestRoot = path.join(tempRoot, `isolated-${proxyPort}`);
  const isolatedLocalAppData = path.join(isolatedTestRoot, 'LocalAppData');
  fs.mkdirSync(isolatedTestRoot, { recursive: true });
  writeDevToolsPort(isolatedLocalAppData, 'edge', mock.port);
  const env = {
    ...process.env,
    WEB_ACCESS_TEST_MODE: '1',
    WEB_ACCESS_TEST_ROOT: isolatedTestRoot,
    LOCALAPPDATA: isolatedLocalAppData,
    CDP_PROXY_PORT: String(proxyPort),
    WEB_ACCESS_EDGE_PORT: String(proxyPort),
    WEB_ACCESS_CHROME_PORT: String(await freePort()),
    ...extraEnv,
  };
  const child = spawnNode([proxyScript, '--browser', 'edge'], env);
  await waitForHealth(proxyPort);
  await waitUntil(async () => (await getHealth(proxyPort))?.connected, 'isolated proxy CDP connection');
  return { child, port: proxyPort, base: `http://127.0.0.1:${proxyPort}`, env };
}

async function stopIsolatedProxy(instance) {
  const health = await getHealth(instance.port);
  if (health?.pid) await stopPid(health.pid);
  await stopChild(instance.child);
}

async function startProxyStub(port, health, capabilitiesResponse = null) {
  const requests = [];
  const stub = http.createServer((req, res) => {
    requests.push({ method: req.method, url: req.url });
    if (req.url === '/health') {
      res.setHeader('Content-Type', 'application/json');
      res.end(JSON.stringify(health));
      return;
    }
    if (req.url === '/capabilities' && capabilitiesResponse) {
      res.statusCode = capabilitiesResponse.status || 200;
      res.setHeader('Content-Type', capabilitiesResponse.contentType || 'application/json');
      if (Object.hasOwn(capabilitiesResponse, 'rawBody')) res.end(capabilitiesResponse.rawBody);
      else res.end(JSON.stringify(capabilitiesResponse.body));
      return;
    }
    res.statusCode = 404;
    res.end();
  });
  await new Promise((resolve, reject) => {
    stub.once('error', reject);
    stub.listen(port, '127.0.0.1', resolve);
  });
  stub.requests = requests;
  return stub;
}

function startLegacyProxyStub(port) {
  return startProxyStub(port, {
    service: 'web-access-cdp-proxy',
    status: 'ok',
    protocolVersion: 1,
    connected: true,
    browser: { id: 'edge' },
  });
}

const edgeMock = await startMockCdpServer('edge');
const chromeMock = await startMockCdpServer('chrome');
const localAppData = path.join(tempRoot, 'LocalAppData');
writeDevToolsPort(localAppData, 'edge', edgeMock.port);
writeDevToolsPort(localAppData, 'chrome', chromeMock.port);

const edgeProxyPort = await freePort();
let chromeProxyPort = await freePort();
while (chromeProxyPort === edgeProxyPort) chromeProxyPort = await freePort();
const baseEnv = {
  ...process.env,
  WEB_ACCESS_TEST_MODE: '1',
  WEB_ACCESS_TEST_ROOT: tempRoot,
  LOCALAPPDATA: localAppData,
  WEB_ACCESS_EDGE_PORT: String(edgeProxyPort),
  WEB_ACCESS_CHROME_PORT: String(chromeProxyPort),
  CDP_PROXY_PORT: String(edgeProxyPort),
  CDP_TAB_IDLE_TIMEOUT: '300000',
  CDP_TASK_ACTIVE_TIMEOUT: '1800000',
  CDP_TASK_HANDOFF_TIMEOUT: '1800000',
};
const edgeBase = `http://127.0.0.1:${edgeProxyPort}`;
const chromeBase = `http://127.0.0.1:${chromeProxyPort}`;

let edgeHealth = null;
let chromeHealth = null;
let edgeProxyChild = null;
let chromeProxyChild = null;

try {
  await runTest('canonical-config-created-once-and-equal-production-override-is-compatible', async () => {
    const productionRoot = path.join(tempRoot, 'production-equal');
    const productionLocalAppData = path.join(productionRoot, 'LocalAppData');
    fs.mkdirSync(productionLocalAppData, { recursive: true });
    const legacyConfig = path.join(productionRoot, 'skill-copy', 'config.env');
    fs.mkdirSync(path.dirname(legacyConfig), { recursive: true });
    fs.writeFileSync(legacyConfig, 'WEB_ACCESS_BROWSER=edge\nWEB_ACCESS_EDGE_PORT=10056\nWEB_ACCESS_CHROME_PORT=10057\n');
    const script = `import { canonicalConfigPath, getProxyPort } from ${JSON.stringify(runtimeConfigUrl)}; ` +
      `console.log(JSON.stringify({ port: getProxyPort('edge'), configPath: canonicalConfigPath() }));`;
    const child = spawnNode(
      ['--input-type=module', '--eval', script],
      productionEnv(productionLocalAppData, { WEB_ACCESS_EDGE_PORT: '3456' }),
    );
    const code = await waitForExit(child, 10000);
    assert.equal(code, 0, `${child.stdoutText}\n${child.stderrText}`);
    const result = JSON.parse(child.stdoutText);
    assert.equal(result.port, 3456);
    assert.equal(result.configPath, path.join(productionLocalAppData, 'web-access', 'config.env'));
    const canonical = fs.readFileSync(result.configPath, 'utf8');
    assert.match(canonical, /WEB_ACCESS_EDGE_PORT=3456/);
    assert.match(canonical, /WEB_ACCESS_CHROME_PORT=3457/);
    assert.match(fs.readFileSync(legacyConfig, 'utf8'), /10056/);
    return { port: result.port, legacyIgnored: true, canonicalCreated: true };
  });

  await runTest('different-production-port-override-fails-before-browser-connection', async () => {
    const productionRoot = path.join(tempRoot, 'production-conflict');
    const productionLocalAppData = path.join(productionRoot, 'LocalAppData');
    fs.mkdirSync(productionLocalAppData, { recursive: true });
    const child = spawnNode(
      [proxyScript, '--browser', 'edge'],
      productionEnv(productionLocalAppData, { WEB_ACCESS_EDGE_PORT: String(await freePort()) }),
    );
    const code = await waitForExit(child, 10000);
    assert.equal(code, 2, `${child.stdoutText}\n${child.stderrText}`);
    assert.match(child.stderrText, /port_override_conflict/);
    return { rejectedBeforeListen: true, status: 'port_override_conflict' };
  });

  await runTest('tampered-canonical-production-ports-fail-closed', async () => {
    const productionRoot = path.join(tempRoot, 'production-tampered');
    const productionLocalAppData = path.join(productionRoot, 'LocalAppData');
    const configPath = path.join(productionLocalAppData, 'web-access', 'config.env');
    fs.mkdirSync(path.dirname(configPath), { recursive: true });
    fs.writeFileSync(configPath, 'WEB_ACCESS_BROWSER=edge\nWEB_ACCESS_EDGE_PORT=10056\nWEB_ACCESS_CHROME_PORT=10057\n');
    const child = spawnNode([proxyScript, '--browser', 'edge'], productionEnv(productionLocalAppData));
    const code = await waitForExit(child, 10000);
    assert.equal(code, 2, `${child.stdoutText}\n${child.stderrText}`);
    assert.match(child.stderrText, /config_invalid/);
    assert.match(child.stderrText, /Production Proxy ports are fixed/);
    return { rejectedBeforeListen: true, status: 'config_invalid' };
  });

  await runTest('test-mode-rejects-nonisolated-localappdata-before-browser-connection', async () => {
    const wrongLocalAppData = path.join(tempRoot, 'wrong-local-app-data');
    fs.mkdirSync(wrongLocalAppData, { recursive: true });
    const child = spawnNode([proxyScript, '--browser', 'edge'], {
      ...process.env,
      WEB_ACCESS_TEST_MODE: '1',
      WEB_ACCESS_TEST_ROOT: tempRoot,
      LOCALAPPDATA: wrongLocalAppData,
      CDP_PROXY_PORT: String(await freePort()),
      WEB_ACCESS_EDGE_PORT: String(await freePort()),
    });
    const code = await waitForExit(child, 10000);
    assert.equal(code, 2, `${child.stdoutText}\n${child.stderrText}`);
    assert.match(child.stderrText, /test_isolation_invalid/);
    return { rejectedBeforeListen: true, status: 'test_isolation_invalid' };
  });

  await runTest('dual-browser-check-deps-json', async () => {
    assert.ok(checkDepsSource.includes("'--json'") || checkDepsSource.includes('"--json"'), 'check-deps 缺少 --json');
    const child = spawnNode([checkDepsScript, '--all', '--json'], baseEnv);
    const code = await waitForExit(child, 30000);
    assert.equal(code, 0, `check-deps --all --json exit=${code}\n${child.stdoutText}\n${child.stderrText}`);
    let report;
    assert.doesNotThrow(() => { report = JSON.parse(child.stdoutText); }, `stdout 不是纯 JSON: ${child.stdoutText}`);
    assert.equal(report.expectedProtocolVersion, 2);
    assert.equal(report.mode, 'all');
    assert.equal(report.ok, true);
    assert.equal(report.results?.length, 2);
    const browserIds = new Set(report.results.map((item) => item.browser?.id));
    assert.deepEqual(browserIds, new Set(['edge', 'chrome']));
    for (const item of report.results) {
      assert.equal(item.ready, true, JSON.stringify(item));
      assert.equal(item.proxy?.protocolVersion, 2, JSON.stringify(item));
      assert.equal(item.capabilities?.protocolVersion, 2, 'ready result 必须包含已验证的 /capabilities 响应');
    }
    edgeHealth = await waitForHealth(edgeProxyPort);
    chromeHealth = await waitForHealth(chromeProxyPort);
    return { edgeProxyPort, chromeProxyPort, results: report.results };
  });

  const capabilityHealth = {
    service: 'web-access-cdp-proxy',
    status: 'ok',
    protocolVersion: 2,
    connected: true,
    requestedBrowser: 'edge',
    browser: { id: 'edge', label: 'Microsoft Edge' },
    sessions: 0,
    managedTabs: 0,
    activeTasks: 0,
    chromePort: edgeMock.port,
    pid: process.pid,
  };
  const validCapabilities = {
    protocolVersion: 2,
    taskIsolation: true,
    userTabsVisible: false,
    maxActiveTasks: 32,
    actions: ['click'],
  };
  const injectedCapabilitySecret = 'capability-secret-must-not-be-reported';
  const untrustedCapabilities = {
    ...validCapabilities,
    taskToken: injectedCapabilitySecret,
    credentials: { password: injectedCapabilitySecret },
  };

  await runTest('check-deps-fetches-capabilities-before-reusing-ready-proxy', async () => {
    const proxyPort = await freePort();
    const expectedHealth = { ...capabilityHealth, proxyPort };
    const stub = await startProxyStub(proxyPort, expectedHealth, { body: untrustedCapabilities });
    try {
      const env = { ...baseEnv, CDP_PROXY_PORT: String(proxyPort), WEB_ACCESS_EDGE_PORT: String(proxyPort) };
      const child = spawnNode([checkDepsScript, '--browser', 'edge', '--json'], env);
      const code = await waitForExit(child, 10000);
      assert.equal(code, 0, `${child.stdoutText}\n${child.stderrText}`);
      const report = JSON.parse(child.stdoutText);
      assert.equal(report.status, 'ready');
      assert.equal(report.results?.[0]?.ready, true);
      assert.equal(report.results?.[0]?.reused, true);
      assert.deepEqual(report.results?.[0]?.capabilities, validCapabilities);
      assert.ok(!child.stdoutText.includes(injectedCapabilitySecret), '未知 capabilities 字段不得进入 JSON 输出');

      const healthIndex = stub.requests.findIndex((entry) => entry.method === 'GET' && entry.url === '/health');
      const capabilitiesIndex = stub.requests.findIndex((entry) => entry.method === 'GET' && entry.url === '/capabilities');
      assert.ok(healthIndex >= 0, 'check-deps 必须先读取 /health');
      assert.ok(capabilitiesIndex > healthIndex, 'ready 前必须完成 GET /capabilities');
      assert.equal(stub.requests.filter((entry) => entry.url === '/health').length, 1, '复用现有 Proxy 不得启动竞争进程');
      assert.equal(stub.listening, true);
      return { requestOrder: ['/health', '/capabilities'], capabilities: validCapabilities, reused: true };
    } finally {
      await new Promise((resolve) => stub.close(resolve));
    }
  });

  const capabilityFailureScenarios = [
    {
      name: 'missing-endpoint',
      response: null,
      expectedCapabilities: null,
      expectedStatus: 'capabilities_unavailable',
    },
    {
      name: 'non-json-response',
      response: { contentType: 'text/plain', rawBody: 'not-json' },
      expectedCapabilities: null,
      expectedStatus: 'capabilities_unavailable',
    },
    {
      name: 'json-with-wrong-content-type',
      response: { contentType: 'text/plain', rawBody: JSON.stringify(untrustedCapabilities) },
      expectedCapabilities: null,
      expectedStatus: 'capabilities_unavailable',
    },
    {
      name: 'http-error-with-valid-looking-json',
      response: { status: 500, body: untrustedCapabilities },
      expectedCapabilities: null,
      expectedStatus: 'capabilities_unavailable',
    },
    {
      name: 'oversized-json-response',
      response: { rawBody: JSON.stringify({ ...untrustedCapabilities, padding: 'x'.repeat(70 * 1024) }) },
      expectedCapabilities: null,
      expectedStatus: 'capabilities_unavailable',
    },
    {
      name: 'protocol-version-mismatch',
      response: { body: { ...untrustedCapabilities, protocolVersion: 1 } },
      expectedCapabilities: { ...validCapabilities, protocolVersion: 1 },
      expectedStatus: 'capabilities_mismatch',
    },
  ];
  for (const scenario of capabilityFailureScenarios) {
    await runTest(`check-deps-capabilities-${scenario.name}-fails-closed`, async () => {
      const proxyPort = await freePort();
      const expectedHealth = { ...capabilityHealth, proxyPort };
      const stub = await startProxyStub(proxyPort, expectedHealth, scenario.response);
      try {
        const env = { ...baseEnv, CDP_PROXY_PORT: String(proxyPort), WEB_ACCESS_EDGE_PORT: String(proxyPort) };
        const child = spawnNode([checkDepsScript, '--browser', 'edge', '--json'], env);
        const code = await waitForExit(child, 10000);
        assert.equal(code, 1, `${child.stdoutText}\n${child.stderrText}`);
        const report = JSON.parse(child.stdoutText);
        const result = report.results?.[0];
        assert.equal(report.ok, false, JSON.stringify(report));
        assert.equal(result?.ok, false, JSON.stringify(result));
        assert.equal(result?.ready, false, JSON.stringify(result));
        assert.equal(result?.status, scenario.expectedStatus);
        assert.ok(Object.hasOwn(result || {}, 'capabilities'), '失败 result 也必须记录 capabilities 握手结果');
        assert.deepEqual(result.capabilities, scenario.expectedCapabilities);
        assert.ok(!child.stdoutText.includes(injectedCapabilitySecret), '失败结果也不得透传 capabilities 未知字段');
        assert.ok(stub.requests.some((entry) => entry.method === 'GET' && entry.url === '/capabilities'));

        await delay(150);
        assert.equal(stub.requests.filter((entry) => entry.url === '/health').length, 1, 'capabilities 失败不得启动第二个 Proxy');
        assert.equal(stub.listening, true, 'capabilities 失败不得停止或覆盖现有 Proxy');
        const preserved = await request(`http://127.0.0.1:${proxyPort}/health`);
        assert.equal(preserved.status, 200);
        assert.deepEqual(preserved.body, expectedHealth);
        return { scenario: scenario.name, failedClosed: true, existingProxyPreserved: true };
      } finally {
        await new Promise((resolve) => stub.close(resolve));
      }
    });
  }

  if (!(await getHealth(edgeProxyPort))) {
    edgeProxyChild = spawnNode([proxyScript, '--browser', 'edge'], baseEnv);
    edgeHealth = await waitForHealth(edgeProxyPort);
  }
  if (!(await getHealth(chromeProxyPort))) {
    chromeProxyChild = spawnNode([proxyScript, '--browser', 'chrome'], { ...baseEnv, CDP_PROXY_PORT: String(chromeProxyPort) });
    chromeHealth = await waitForHealth(chromeProxyPort);
  }

  await runTest('protocol-capabilities-and-http-guards', async () => {
    edgeHealth = await waitForHealth(edgeProxyPort);
    assert.equal(edgeHealth.protocolVersion, 2);
    assert.equal(edgeHealth.browser?.id, 'edge');
    const capabilities = await getJson(edgeBase, '/capabilities');
    assert.equal(capabilities.status, 200, JSON.stringify(capabilities.body));
    assert.equal(capabilities.body.protocolVersion, 2);

    const origin = await postJson(edgeBase, '/v2/tasks', {}, {
      key: nextKey('origin'),
      headers: { Origin: 'https://untrusted-page.test' },
    });
    assertStatus(origin, 403);
    assert.ok(!JSON.stringify(origin.body).includes('taskToken'));

    const host = await rawHostRequest(edgeProxyPort, 'untrusted-page.test');
    assertStatus(host, 403);
    return { protocolVersion: 2, originRejected: true, hostRejected: true };
  });

  await runTest('legacy-routes-disabled', async () => {
    const probes = [
      await getJson(edgeBase, '/targets'),
      await postJson(edgeBase, '/new', { url: 'https://example.test/' }, { key: nextKey('legacy') }),
      await getJson(edgeBase, '/info?target=guessed-target'),
    ];
    for (const probe of probes) {
      assertError(probe, 410, 'LEGACY_API_DISABLED');
      assert.match(JSON.stringify(probe.body), /migration/i);
    }
    return { routes: ['/targets', '/new', '/info'], status: 410 };
  });

  await runTest('task-token-and-idempotency-contract', async () => {
    const missingKey = await postJson(edgeBase, '/v2/tasks', {}, { key: null });
    assertStatus(missingKey, 400, 428);

    const key = nextKey('task-replay');
    const first = await createTask(edgeBase, key);
    const replay = await postJson(edgeBase, '/v2/tasks', {}, { key });
    assertStatus(replay, 200, 201);
    assert.equal(replay.body.taskId, first.taskId);
    assert.equal(replay.body.taskToken, first.taskToken);

    const tabKey = nextKey('tab-replay');
    const tab = await createTab(edgeBase, first, 'https://example.test/idempotent', tabKey);
    const same = await postJson(edgeBase, '/v2/tabs', { url: 'https://example.test/idempotent' }, {
      token: first.taskToken,
      key: tabKey,
    });
    assert.equal(same.status, tab.response.status);
    assert.equal(same.body.targetId, tab.targetId);
    const conflict = await postJson(edgeBase, '/v2/tabs', { url: 'https://example.test/different' }, {
      token: first.taskToken,
      key: tabKey,
    });
    assertStatus(conflict, 409);
    assert.ok(!JSON.stringify(conflict.body).includes(first.taskToken));
    return { tokenBytes: tokenBytes(first.taskToken), replayedTask: first.taskId, replayedTarget: tab.targetId };
  });

  await runTest('created-tab-attaches-and-initializes-before-requested-navigation', async () => {
    const task = await createTask(edgeBase);
    const url = 'https://example.test/create-order';
    const before = edgeMock.commands.length;
    const tab = await createTab(edgeBase, task, url);
    const commands = edgeMock.commands.slice(before);
    const createIndex = commands.findIndex((command) => command.method === 'Target.createTarget');
    const attachIndex = commands.findIndex((command) => command.method === 'Target.attachToTarget' && command.params.targetId === tab.targetId);
    const navigateIndex = commands.findIndex((command) => command.method === 'Page.navigate' && command.params.url === url);
    const initialized = commands.filter((command) => command.sessionId && [
      'Page.enable', 'Runtime.enable', 'DOM.enable', 'Accessibility.enable',
    ].includes(command.method));
    assert.ok(createIndex >= 0 && attachIndex > createIndex && navigateIndex > attachIndex, JSON.stringify(commands));
    assert.equal(commands[createIndex].params.url, 'about:blank');
    assert.equal(initialized.length, 4, JSON.stringify(commands));
    assert.ok(initialized.every((command) => commands.indexOf(command) < navigateIndex), JSON.stringify(commands));
    assert.equal(edgeMock.targets.get(tab.targetId)?.url, url);
    return { createUrl: 'about:blank', attachedBeforeNavigate: true, initializedBeforeNavigate: true };
  });

  await runTest('task-tab-isolation-popup-and-browser-scope', async () => {
    const taskA = await createTask(edgeBase);
    const taskB = await createTask(edgeBase);
    const [tabA, tabB] = await Promise.all([
      createTab(edgeBase, taskA, 'https://example.test/task-a'),
      createTab(edgeBase, taskB, 'https://example.test/task-b'),
    ]);

    const tabsA = await listTabs(edgeBase, taskA);
    const tabsB = await listTabs(edgeBase, taskB);
    assert.deepEqual(tabsA.map((tab) => tab.targetId), [tabA.targetId]);
    assert.deepEqual(tabsB.map((tab) => tab.targetId), [tabB.targetId]);
    assert.ok(!tabsA.some((tab) => tab.targetId === 'edge-user-target'), '用户已有 tab 不得枚举');

    const crossRead = await getJson(edgeBase, `/v2/tabs/${encodeURIComponent(tabA.targetId)}/snapshot`, taskB.taskToken);
    assert.equal(crossRead.status, 404, JSON.stringify(crossRead.body));
    const crossBrowser = await getJson(chromeBase, '/v2/tabs', taskA.taskToken);
    assertStatus(crossBrowser, 401, 404);

    const popupId = edgeMock.createPopup(tabA.targetId);
    const popupTabs = await waitUntil(async () => {
      const tabs = await listTabs(edgeBase, taskA);
      return tabs.some((tab) => tab.targetId === popupId) ? tabs : null;
    }, 'popup 继承 task');
    assert.ok(popupTabs.some((tab) => tab.targetId === popupId));
    assert.ok(!(await listTabs(edgeBase, taskB)).some((tab) => tab.targetId === popupId));
    assert.equal(edgeMock.totalConnections, 1, '同一 Proxy 应只建立一个 CDP WebSocket');
    return { taskATabs: popupTabs.map((tab) => tab.targetId), taskBTabs: [tabB.targetId], cdpWebSockets: edgeMock.totalConnections };
  });

  await runTest('popup-lineage-reconciles-and-late-popups-follow-complete-policy', async () => {
    const reconciledTask = await createTask(edgeBase);
    const reconciledTab = await createTab(edgeBase, reconciledTask, 'https://example.test/popup-reconcile');
    const hiddenParent = edgeMock.createPopup(reconciledTab.targetId, 'https://popup.test/hidden-parent', { emitEvent: false });
    const hiddenChild = edgeMock.createPopup(hiddenParent, 'https://popup.test/hidden-child', { emitEvent: false });
    const reconciledComplete = await taskTransition(edgeBase, reconciledTask, 'complete', { keep: false });
    assert.equal(reconciledComplete.status, 200, JSON.stringify(reconciledComplete.body));
    await waitUntil(() => !edgeMock.targets.has(hiddenParent) && !edgeMock.targets.has(hiddenChild), 'complete 对账并关闭嵌套 popup');

    const lateTask = await createTask(edgeBase);
    const lateTab = await createTab(edgeBase, lateTask, 'https://example.test/popup-late');
    const lateParent = edgeMock.createPopup(lateTab.targetId, 'https://popup.test/late-parent', { delayMs: 75 });
    const lateChild = edgeMock.createPopup(lateParent, 'https://popup.test/late-child', { delayMs: 125 });
    const lateComplete = await taskTransition(edgeBase, lateTask, 'complete', { keep: false });
    assert.equal(lateComplete.status, 200, JSON.stringify(lateComplete.body));
    await waitUntil(() => !edgeMock.targets.has(lateParent) && !edgeMock.targets.has(lateChild), '终态墓碑关闭晚到 popup', 3000);
    return { reconciledNested: true, lateNestedClosed: true };
  });

  await runTest('handoff-resume-complete-and-wait-cancellation', async () => {
    const task = await createTask(edgeBase);
    const tab = await createTab(edgeBase, task, 'https://example.test/handoff');
    const firstSnapshot = await getSnapshot(edgeBase, task, tab.targetId);
    const oldRef = findNode(firstSnapshot, 'button', 'Submit').ref;

    const waitStarted = Date.now();
    const pendingWait = postJson(edgeBase, `/v2/tabs/${encodeURIComponent(tab.targetId)}/wait`, {
      text: 'never-appears',
      timeoutMs: 30000,
    }, { token: task.taskToken, key: nextKey('wait-cancel'), timeoutMs: 35000 });
    await delay(100);
    const busy = await doAction(edgeBase, task, tab.targetId, { action: 'click', ref: oldRef });
    assertError(busy, 409, 'TARGET_BUSY');

    const handoff = await taskTransition(edgeBase, task, 'handoff', { targetId: tab.targetId });
    assert.equal(handoff.status, 200, JSON.stringify(handoff.body));
    assert.equal(edgeMock.activeTargetId, tab.targetId);
    const cancelled = await pendingWait;
    assertStatus(cancelled, 409, 410, 499);
    assert.ok(Date.now() - waitStarted < 5000, 'handoff 应取消进行中的 wait');

    const blockedRead = await getJson(edgeBase, `/v2/tabs/${encodeURIComponent(tab.targetId)}/snapshot`, task.taskToken);
    assertStatus(blockedRead, 409);
    const blockedComplete = await taskTransition(edgeBase, task, 'complete', { keep: false });
    assertError(blockedComplete, 409, 'INVALID_TASK_STATE');
    assert.ok(edgeMock.targets.has(tab.targetId), 'handoff 期间 complete 不得关闭用户正在操作的 tab');
    const resume = await taskTransition(edgeBase, task, 'resume');
    assert.equal(resume.status, 200, JSON.stringify(resume.body));
    const staleAfterResume = await doAction(edgeBase, task, tab.targetId, { action: 'click', ref: oldRef });
    assertError(staleAfterResume, 409, 'STALE_REF');
    await getSnapshot(edgeBase, task, tab.targetId);

    const completeKey = nextKey('complete');
    const complete = await taskTransition(edgeBase, task, 'complete', { keep: false }, completeKey);
    assert.equal(complete.status, 200, JSON.stringify(complete.body));
    await waitUntil(() => !edgeMock.targets.has(tab.targetId), 'complete 关闭 task tab');
    const completeReplay = await taskTransition(edgeBase, task, 'complete', { keep: false }, completeKey);
    assert.equal(completeReplay.status, complete.status);
    assert.deepEqual(completeReplay.body, complete.body);
    const resumeCompleted = await taskTransition(edgeBase, task, 'resume');
    assertStatus(resumeCompleted, 409, 410);

    const keepTask = await createTask(edgeBase);
    const keptTab = await createTab(edgeBase, keepTask, 'https://example.test/keep');
    const keepComplete = await taskTransition(edgeBase, keepTask, 'complete', { keep: true });
    assert.equal(keepComplete.status, 200, JSON.stringify(keepComplete.body));
    assert.ok(edgeMock.targets.has(keptTab.targetId), 'keep=true 应释放而非关闭 tab');
    return { handoffTarget: tab.targetId, waitCancelledMs: Date.now() - waitStarted, completed: true, keptTarget: keptTab.targetId };
  });

  await runTest('handoff-activation-timeout-is-fail-closed', async () => {
    const timeoutMock = await startMockCdpServer('edge', { commandDelays: { 'Target.activateTarget': 250 } });
    const timeoutProxy = await startIsolatedProxy(timeoutMock, { CDP_COMMAND_TIMEOUT: '50' });
    try {
      const task = await createTask(timeoutProxy.base);
      const tab = await createTab(timeoutProxy.base, task, 'https://example.test/handoff-timeout');
      const handoff = await taskTransition(timeoutProxy.base, task, 'handoff', { targetId: tab.targetId });
      assertError(handoff, 504, 'UNKNOWN_RESULT');
      const state = await getJson(timeoutProxy.base, `/v2/tasks/${encodeURIComponent(task.taskId)}`, task.taskToken);
      assert.equal(state.status, 200, JSON.stringify(state.body));
      assert.equal(state.body.state, 'handoff');
      const blocked = await getJson(timeoutProxy.base, `/v2/tabs/${encodeURIComponent(tab.targetId)}/snapshot`, task.taskToken);
      assertError(blocked, 409, 'TASK_IN_HANDOFF');
      const resume = await taskTransition(timeoutProxy.base, task, 'resume');
      assert.equal(resume.status, 200, JSON.stringify(resume.body));
      return { unknownResult: true, stateAfterTimeout: state.body.state, readBlocked: true };
    } finally {
      await stopIsolatedProxy(timeoutProxy);
      await timeoutMock.close();
    }
  });

  await runTest('ax-snapshot-ref-generation-and-actions', async () => {
    const task = await createTask(edgeBase);
    const tab = await createTab(edgeBase, task, 'https://example.test/actions');
    const first = await getSnapshot(edgeBase, task, tab.targetId);
    assert.ok(first.nodes.length >= 4);
    const firstButtonRef = findNode(first, 'button', 'Submit').ref;
    const second = await getSnapshot(edgeBase, task, tab.targetId);
    assert.ok(second.generation > first.generation);
    const stale = await doAction(edgeBase, task, tab.targetId, { action: 'click', ref: firstButtonRef });
    assertError(stale, 409, 'STALE_REF');

    const cases = [
      { action: 'click', role: 'button', name: 'Submit' },
      { action: 'fill', role: 'textbox', name: 'Name', value: 'Alice' },
      { action: 'type', role: 'textbox', name: 'Name', value: ' B' },
      { action: 'press', role: 'textbox', name: 'Name', key: 'Tab' },
      { action: 'check', role: 'checkbox', name: 'Remember' },
      { action: 'uncheck', role: 'checkbox', name: 'Remember' },
      { action: 'select', role: 'combobox', name: 'Choice', values: ['two'] },
      { action: 'hover', role: 'button', name: 'Submit' },
    ];
    for (const testCase of cases) {
      const snapshot = await getSnapshot(edgeBase, task, tab.targetId);
      const node = findNode(snapshot, testCase.role, testCase.name);
      const action = await doAction(edgeBase, task, tab.targetId, { ...testCase, role: undefined, name: undefined, ref: node.ref });
      assert.equal(action.status, 200, `${testCase.action}: ${JSON.stringify(action.body)}`);
    }

    const redrawSnapshot = await getSnapshot(edgeBase, task, tab.targetId);
    const redrawRef = findNode(redrawSnapshot, 'button', 'Submit').ref;
    edgeMock.redraw(tab.targetId);
    await delay(25);
    const staleAfterRedraw = await doAction(edgeBase, task, tab.targetId, { action: 'click', ref: redrawRef });
    assertError(staleAfterRedraw, 409, 'STALE_REF');

    assert.ok(edgeMock.commands.some((command) => command.method === 'Accessibility.getFullAXTree'));
    assert.ok(edgeMock.commands.some((command) => command.method === 'DOM.resolveNode'));
    assert.ok(edgeMock.commands.some((command) => command.method === 'Input.dispatchMouseEvent'));
    assert.ok(edgeMock.commands.some((command) => command.method === 'Input.dispatchKeyEvent' || command.method === 'Input.insertText'));
    return { nodes: first.nodes.length, actions: cases.map((item) => item.action), staleRefChecked: true };
  });

  await runTest('wait-contract', async () => {
    const task = await createTask(edgeBase);
    const tab = await createTab(edgeBase, task, 'https://example.test/wait');
    const conditions = [
      { selector: '#ready', timeoutMs: 1000 },
      { text: 'Ready', timeoutMs: 1000 },
      { url: 'https://example.test/wait', timeoutMs: 1000 },
      { state: 'domcontentloaded', timeoutMs: 1000 },
      { state: 'load', timeoutMs: 1000 },
    ];
    for (const condition of conditions) {
      const result = await postJson(edgeBase, `/v2/tabs/${encodeURIComponent(tab.targetId)}/wait`, condition, {
        token: task.taskToken,
        key: nextKey('wait'),
      });
      assert.equal(result.status, 200, JSON.stringify({ condition, response: result.body }));
    }
    const invalid = await postJson(edgeBase, `/v2/tabs/${encodeURIComponent(tab.targetId)}/wait`, {
      selector: '#ready',
      text: 'Ready',
    }, { token: task.taskToken, key: nextKey('wait-invalid') });
    assertStatus(invalid, 400);

    const removedTask = await createTask(edgeBase);
    const removedTab = await createTab(edgeBase, removedTask, 'https://example.test/wait-removed');
    const waitStarted = Date.now();
    const removedWait = postJson(edgeBase, `/v2/tabs/${encodeURIComponent(removedTab.targetId)}/wait`, {
      text: 'never-appears',
      timeoutMs: 30000,
    }, { token: removedTask.taskToken, key: nextKey('wait-removed'), timeoutMs: 5000 });
    await delay(100);
    edgeMock.destroyTarget(removedTab.targetId);
    const cancelled = await removedWait;
    assertError(cancelled, 409, 'WAIT_CANCELLED');
    assert.ok(Date.now() - waitStarted < 3000, 'target 销毁应定向取消 wait');
    return { conditions: ['selector', 'text', 'url', 'domcontentloaded', 'load'], ambiguousRejected: true, targetRemovalCancelled: true };
  });

  await runTest('dialog-default-deny-explicit-resolution-and-ref-invalidation', async () => {
    const task = await createTask(edgeBase);
    const tab = await createTab(edgeBase, task, 'https://example.test/dialog');
    const snapshot = await getSnapshot(edgeBase, task, tab.targetId);
    const oldRef = findNode(snapshot, 'button', 'Submit').ref;
    const before = edgeMock.commands.filter((command) => command.method === 'Page.handleJavaScriptDialog').length;
    edgeMock.openDialog(tab.targetId, { type: 'confirm', message: 'Delete?' });
    await delay(50);
    assert.equal(edgeMock.commands.filter((command) => command.method === 'Page.handleJavaScriptDialog').length, before, 'dialog 不得自动接受');

    const dismiss = await postJson(edgeBase, `/v2/tabs/${encodeURIComponent(tab.targetId)}/dialog`, { action: 'dismiss' }, {
      token: task.taskToken,
      key: nextKey('dialog-dismiss'),
    });
    assert.equal(dismiss.status, 200, JSON.stringify(dismiss.body));
    const dismissCommand = edgeMock.commands.filter((command) => command.method === 'Page.handleJavaScriptDialog').at(-1);
    assert.equal(dismissCommand?.params.accept, false);
    const stale = await doAction(edgeBase, task, tab.targetId, { action: 'click', ref: oldRef });
    assertError(stale, 409, 'STALE_REF');

    await getSnapshot(edgeBase, task, tab.targetId);
    edgeMock.openDialog(tab.targetId, { type: 'prompt', message: 'Name?', defaultPrompt: '' });
    await delay(25);
    const accept = await postJson(edgeBase, `/v2/tabs/${encodeURIComponent(tab.targetId)}/dialog`, {
      action: 'accept',
      promptText: 'Alice',
    }, { token: task.taskToken, key: nextKey('dialog-accept') });
    assert.equal(accept.status, 200, JSON.stringify(accept.body));
    const acceptCommand = edgeMock.commands.filter((command) => command.method === 'Page.handleJavaScriptDialog').at(-1);
    assert.equal(acceptCommand?.params.accept, true);
    assert.equal(acceptCommand?.params.promptText, 'Alice');
    return { defaultAccepted: false, explicitDismiss: true, explicitAccept: true, refInvalidated: true };
  });

  await runTest('consecutive-dialogs-preserve-the-new-dialog-generation', async () => {
    const task = await createTask(edgeBase);
    const tab = await createTab(edgeBase, task, 'https://example.test/consecutive-dialogs');
    await getSnapshot(edgeBase, task, tab.targetId);
    const before = edgeMock.commands.filter((command) => command.method === 'Page.handleJavaScriptDialog').length;

    edgeMock.openDialog(tab.targetId, { type: 'confirm', message: 'First dialog' });
    edgeMock.queueDialogAfterHandle(tab.targetId, { type: 'prompt', message: 'Second dialog', defaultPrompt: 'next' });
    await delay(25);

    const first = await postJson(edgeBase, `/v2/tabs/${encodeURIComponent(tab.targetId)}/dialog`, {
      action: 'dismiss',
    }, { token: task.taskToken, key: nextKey('dialog-first') });
    assert.equal(first.status, 200, JSON.stringify(first.body));

    const between = await getJson(edgeBase, `/v2/tabs/${encodeURIComponent(tab.targetId)}`, task.taskToken);
    assert.equal(between.status, 200, JSON.stringify(between.body));
    assert.equal(between.body.dialog?.message, 'Second dialog', '处理首个 dialog 不得清除同步打开的新 dialog');
    assert.equal(between.body.dialog?.defaultPrompt, 'next');

    const second = await postJson(edgeBase, `/v2/tabs/${encodeURIComponent(tab.targetId)}/dialog`, {
      action: 'accept',
      promptText: 'confirmed',
    }, { token: task.taskToken, key: nextKey('dialog-second') });
    assert.equal(second.status, 200, JSON.stringify(second.body));

    const after = await getJson(edgeBase, `/v2/tabs/${encodeURIComponent(tab.targetId)}`, task.taskToken);
    assert.equal(after.status, 200, JSON.stringify(after.body));
    assert.equal(after.body.dialog, null);
    const handled = edgeMock.commands.filter((command) => command.method === 'Page.handleJavaScriptDialog').slice(before);
    assert.equal(handled.length, 2);
    assert.equal(handled[0].params.accept, false);
    assert.equal(handled[1].params.accept, true);
    assert.equal(handled[1].params.promptText, 'confirmed');
    return { dialogsHandled: 2, secondGenerationPreserved: true };
  });

  await runTest('authenticated-fallback-api-regression', async () => {
    const task = await createTask(edgeBase);
    const tab = await createTab(edgeBase, task, 'https://example.test/fallback');
    const targetPath = `/v2/tabs/${encodeURIComponent(tab.targetId)}`;
    const navigateUrl = 'https://example.test/next?a=1&b=2';
    const navigate = await postJson(edgeBase, `${targetPath}/navigate`, { url: navigateUrl }, { token: task.taskToken });
    assert.equal(navigate.status, 200, JSON.stringify(navigate.body));
    const evaluate = await postJson(edgeBase, `${targetPath}/eval`, { expression: 'document.title' }, { token: task.taskToken });
    assert.equal(evaluate.status, 200, JSON.stringify(evaluate.body));
    assert.equal(evaluate.body.value, 'Mock Page');
    const click = await postJson(edgeBase, `${targetPath}/click`, { selector: 'button' }, { token: task.taskToken });
    assert.equal(click.status, 200, JSON.stringify(click.body));

    const uploadPath = path.join(tempRoot, 'upload.txt');
    fs.writeFileSync(uploadPath, 'fixture');
    const upload = await postJson(edgeBase, `${targetPath}/set-files`, {
      selector: 'input[type=file]',
      files: [uploadPath],
    }, { token: task.taskToken });
    assert.equal(upload.status, 200, JSON.stringify(upload.body));
    const scroll = await postJson(edgeBase, `${targetPath}/scroll`, { direction: 'down', y: 120 }, { token: task.taskToken });
    assert.equal(scroll.status, 200, JSON.stringify(scroll.body));
    const back = await postJson(edgeBase, `${targetPath}/back`, {}, { token: task.taskToken });
    assert.equal(back.status, 200, JSON.stringify(back.body));

    const screenshot = await getJson(edgeBase, `${targetPath}/screenshot`, task.taskToken);
    assert.equal(screenshot.status, 200);
    assert.equal(screenshot.headers.get('content-type'), 'image/png');
    assert.ok(screenshot.raw.length > 0);
    assert.ok(edgeMock.commands.some((command) => command.method === 'DOM.setFileInputFiles'));
    assert.ok(edgeMock.commands.some((command) => command.method === 'Page.captureScreenshot'));
    return { apiChecks: ['navigate', 'eval', 'click', 'set-files', 'scroll', 'back', 'screenshot'], screenshotBytes: screenshot.raw.length };
  });

  await runTest('element-state-guards-react-contenteditable-and-multiselect', async () => {
    const task = await createTask(edgeBase);
    const tab = await createTab(edgeBase, task, 'https://example.test/interactive-states');
    const assertBlocked = async (patch) => {
      const snapshot = await getSnapshot(edgeBase, task, tab.targetId);
      const ref = findNode(snapshot, 'button', 'Submit').ref;
      edgeMock.setElementState(tab.targetId, 102, patch);
      const result = await doAction(edgeBase, task, tab.targetId, { action: 'click', ref });
      assertError(result, 409, 'STALE_REF');
      edgeMock.setElementState(tab.targetId, 102, { visible: true, enabled: true, obscured: false });
    };
    await assertBlocked({ visible: false });
    await assertBlocked({ enabled: false });
    await assertBlocked({ obscured: true });

    const reactSnapshot = await getSnapshot(edgeBase, task, tab.targetId);
    const input = findNode(reactSnapshot, 'textbox', 'Name');
    const fill = await doAction(edgeBase, task, tab.targetId, { action: 'fill', ref: input.ref, value: 'React controlled value' });
    assert.equal(fill.status, 200, JSON.stringify(fill.body));
    assert.equal(fill.body.value, 'React controlled value');

    const notesSnapshot = await getSnapshot(edgeBase, task, tab.targetId);
    const notes = findNode(notesSnapshot, 'textbox', 'Notes');
    const contenteditable = await doAction(edgeBase, task, tab.targetId, { action: 'fill', ref: notes.ref, value: 'Editable text' });
    assert.equal(contenteditable.status, 200, JSON.stringify(contenteditable.body));
    assert.equal(contenteditable.body.value, 'Editable text');

    const selectSnapshot = await getSnapshot(edgeBase, task, tab.targetId);
    const multi = findNode(selectSnapshot, 'combobox', 'Multi Choice');
    const multiSelect = await doAction(edgeBase, task, tab.targetId, { action: 'select', ref: multi.ref, values: ['one', 'two'] });
    assert.equal(multiSelect.status, 200, JSON.stringify(multiSelect.body));
    assert.deepEqual(multiSelect.body.values, ['one', 'two']);
    return { guarded: ['hidden', 'disabled', 'obscured'], inputEvents: true, contenteditable: true, multiSelect: true };
  });

  await runTest('concurrent-idempotency-key-executes-once', async () => {
    const task = await createTask(edgeBase);
    const key = nextKey('concurrent-tab');
    const before = edgeMock.commands.filter((command) => command.method === 'Target.createTarget').length;
    const requests = await Promise.all([
      postJson(edgeBase, '/v2/tabs', { url: 'https://example.test/concurrent' }, { token: task.taskToken, key }),
      postJson(edgeBase, '/v2/tabs', { url: 'https://example.test/concurrent' }, { token: task.taskToken, key }),
    ]);
    assert.equal(requests[0].status, 201, JSON.stringify(requests[0].body));
    assert.equal(requests[1].status, 201, JSON.stringify(requests[1].body));
    assert.equal(requests[0].body.targetId, requests[1].body.targetId);
    const after = edgeMock.commands.filter((command) => command.method === 'Target.createTarget').length;
    assert.equal(after - before, 1);
    return { targetId: requests[0].body.targetId, cdpCreates: 1 };
  });

  await runTest('active-task-idempotency-survives-terminal-retention-window', async () => {
    const retentionMock = await startMockCdpServer('edge');
    const retentionProxy = await startIsolatedProxy(retentionMock, {
      CDP_TASK_IDLE_TIMEOUT: '5000',
      CDP_HANDOFF_TIMEOUT: '5000',
      CDP_TAB_IDLE_TIMEOUT: '5000',
      CDP_TERMINAL_RETENTION: '300',
    });
    try {
      const taskKey = nextKey('retained-task');
      const task = await createTask(retentionProxy.base, taskKey);
      const tabKey = nextKey('retained-tab');
      const before = retentionMock.commands.filter((command) => command.method === 'Target.createTarget').length;
      const tab = await createTab(retentionProxy.base, task, 'https://example.test/retained-idempotency', tabKey);

      await delay(800);

      const taskReplay = await postJson(retentionProxy.base, '/v2/tasks', {}, { key: taskKey });
      assert.equal(taskReplay.status, task.response.status, JSON.stringify(taskReplay.body));
      assert.deepEqual(taskReplay.body, task.response.body);
      const tabReplay = await postJson(retentionProxy.base, '/v2/tabs', {
        url: 'https://example.test/retained-idempotency',
      }, { token: task.taskToken, key: tabKey });
      assert.equal(tabReplay.status, tab.response.status, JSON.stringify(tabReplay.body));
      assert.deepEqual(tabReplay.body, tab.response.body);

      const after = retentionMock.commands.filter((command) => command.method === 'Target.createTarget').length;
      assert.equal(after - before, 1, 'active task 的 tab 幂等记录不得按终态 retention 回收');
      const health = await getHealth(retentionProxy.port);
      assert.equal(health?.activeTasks, 1, 'startup key 重放不得创建第二个 active task');
      return { retentionMs: 300, waitedMs: 800, startupReplayStable: true, tabReplayStable: true };
    } finally {
      await stopIsolatedProxy(retentionProxy);
      await retentionMock.close();
    }
  });

  await runTest('task-expiry-releases-tabs-and-enforces-task-limit', async () => {
    const ttlMock = await startMockCdpServer('edge');
    const ttlProxy = await startIsolatedProxy(ttlMock, {
      CDP_TASK_IDLE_TIMEOUT: '300',
      CDP_TASK_HANDOFF_TIMEOUT: '300',
      CDP_TAB_IDLE_TIMEOUT: '5000',
      CDP_TERMINAL_RETENTION: '2500',
    });
    try {
      const activeTask = await createTask(ttlProxy.base);
      const activeTab = await createTab(ttlProxy.base, activeTask, 'https://example.test/active-expiry');
      await delay(700);
      const activeState = await getJson(ttlProxy.base, `/v2/tasks/${encodeURIComponent(activeTask.taskId)}`, activeTask.taskToken);
      assert.equal(activeState.status, 200, JSON.stringify(activeState.body));
      assert.equal(activeState.body.state, 'expired');
      assert.ok(ttlMock.targets.has(activeTab.targetId), 'expired active task must release, not close, its tab');

      const handoffTask = await createTask(ttlProxy.base);
      const handoffTab = await createTab(ttlProxy.base, handoffTask, 'https://example.test/handoff-expiry');
      const handoff = await taskTransition(ttlProxy.base, handoffTask, 'handoff', { targetId: handoffTab.targetId });
      assert.equal(handoff.status, 200, JSON.stringify(handoff.body));
      await delay(700);
      const handoffState = await getJson(ttlProxy.base, `/v2/tasks/${encodeURIComponent(handoffTask.taskId)}`, handoffTask.taskToken);
      assert.equal(handoffState.status, 200, JSON.stringify(handoffState.body));
      assert.equal(handoffState.body.state, 'expired');
      assert.ok(ttlMock.targets.has(handoffTab.targetId), 'expired handoff task must leave its tab to the user');
    } finally {
      await stopIsolatedProxy(ttlProxy);
      await ttlMock.close();
    }

    const limitMock = await startMockCdpServer('edge');
    const limitProxy = await startIsolatedProxy(limitMock, { CDP_TASK_IDLE_TIMEOUT: '30000' });
    try {
      for (let index = 0; index < 32; index++) await createTask(limitProxy.base);
      const overflow = await postJson(limitProxy.base, '/v2/tasks', {}, { key: nextKey('task-overflow') });
      assertError(overflow, 429, 'TASK_LIMIT_REACHED');
    } finally {
      await stopIsolatedProxy(limitProxy);
      await limitMock.close();
    }
    return { activeAndHandoffExpired: true, taskLimit: 32 };
  });

  await runTest('expiry-waits-for-in-flight-action-and-cancels-in-flight-wait', async () => {
    const barrierMock = await startMockCdpServer('edge', {
      commandDelays: {
        'Runtime.callFunctionOn': 1000,
        'Runtime.evaluate': 1000,
      },
    });
    const barrierProxy = await startIsolatedProxy(barrierMock, {
      CDP_TASK_IDLE_TIMEOUT: '200',
      CDP_HANDOFF_TIMEOUT: '200',
      CDP_TAB_IDLE_TIMEOUT: '5000',
      CDP_TERMINAL_RETENTION: '3000',
      CDP_COMMAND_TIMEOUT: '3000',
    });
    try {
      const actionTask = await createTask(barrierProxy.base);
      const actionTab = await createTab(barrierProxy.base, actionTask, 'https://example.test/expiry-action');
      const actionSnapshot = await getSnapshot(barrierProxy.base, actionTask, actionTab.targetId);
      const actionRef = findNode(actionSnapshot, 'button', 'Submit').ref;
      const actionCommandsBefore = barrierMock.commands.filter((command) => command.method === 'Runtime.callFunctionOn').length;
      const action = doAction(barrierProxy.base, actionTask, actionTab.targetId, { action: 'click', ref: actionRef });
      await waitUntil(
        () => barrierMock.commands.filter((command) => command.method === 'Runtime.callFunctionOn').length > actionCommandsBefore,
        'delayed action entered CDP',
      );
      await delay(650);

      const actionDuringExpiry = await getJson(
        barrierProxy.base,
        `/v2/tasks/${encodeURIComponent(actionTask.taskId)}`,
        actionTask.taskToken,
      );
      assert.equal(actionDuringExpiry.status, 200, JSON.stringify(actionDuringExpiry.body));
      assert.equal(actionDuringExpiry.body.state, 'active', 'expiry 屏障结束前不得先发布终态');
      assert.equal(actionDuringExpiry.body.tabCount, 1, 'expiry 屏障结束前不得释放 ownership');
      const actionBlocked = await getJson(barrierProxy.base, '/v2/tabs', actionTask.taskToken);
      assertError(actionBlocked, 409, 'TASK_TRANSITIONING');

      const actionResult = await action;
      assert.equal(actionResult.status, 200, JSON.stringify(actionResult.body));
      const expiredActionTask = await waitUntil(async () => {
        const state = await getJson(
          barrierProxy.base,
          `/v2/tasks/${encodeURIComponent(actionTask.taskId)}`,
          actionTask.taskToken,
        );
        return state.body?.state === 'expired' ? state : null;
      }, 'action task expiry after in-flight drain');
      assert.equal(expiredActionTask.body.tabCount, 0);
      assert.ok(barrierMock.targets.has(actionTab.targetId), 'expired action tab must remain as a user tab');

      const waitTask = await createTask(barrierProxy.base);
      const waitTab = await createTab(barrierProxy.base, waitTask, 'https://example.test/expiry-wait');
      const waitCommandsBefore = barrierMock.commands.filter((command) => command.method === 'Runtime.evaluate').length;
      const waiting = postJson(barrierProxy.base, `/v2/tabs/${encodeURIComponent(waitTab.targetId)}/wait`, {
        text: 'never-appears',
        timeoutMs: 30000,
      }, { token: waitTask.taskToken, key: nextKey('expiry-wait'), timeoutMs: 5000 });
      await waitUntil(
        () => barrierMock.commands.filter((command) => command.method === 'Runtime.evaluate').length > waitCommandsBefore,
        'delayed wait entered CDP',
      );
      await delay(650);

      const waitDuringExpiry = await getJson(
        barrierProxy.base,
        `/v2/tasks/${encodeURIComponent(waitTask.taskId)}`,
        waitTask.taskToken,
      );
      assert.equal(waitDuringExpiry.status, 200, JSON.stringify(waitDuringExpiry.body));
      assert.equal(waitDuringExpiry.body.state, 'active', 'wait 排空前不得先发布 expired');
      assert.equal(waitDuringExpiry.body.tabCount, 1, 'wait 排空前不得释放 ownership');
      const waitBlocked = await getJson(barrierProxy.base, '/v2/tabs', waitTask.taskToken);
      assertError(waitBlocked, 409, 'TASK_TRANSITIONING');

      const waitResult = await waiting;
      assertError(waitResult, 409, 'WAIT_CANCELLED');
      const expiredWaitTask = await waitUntil(async () => {
        const state = await getJson(
          barrierProxy.base,
          `/v2/tasks/${encodeURIComponent(waitTask.taskId)}`,
          waitTask.taskToken,
        );
        return state.body?.state === 'expired' ? state : null;
      }, 'wait task expiry after cancellation');
      assert.equal(expiredWaitTask.body.tabCount, 0);
      assert.ok(barrierMock.targets.has(waitTab.targetId), 'expired wait tab must remain as a user tab');

      const matchedTask = await createTask(barrierProxy.base);
      const matchedTab = await createTab(barrierProxy.base, matchedTask, 'https://example.test/expiry-matched-wait');
      const matchedCommandsBefore = barrierMock.commands.filter((command) => command.method === 'Runtime.evaluate').length;
      const matchedWait = postJson(barrierProxy.base, `/v2/tabs/${encodeURIComponent(matchedTab.targetId)}/wait`, {
        text: 'Ready',
        timeoutMs: 30000,
      }, { token: matchedTask.taskToken, key: nextKey('expiry-matched-wait'), timeoutMs: 5000 });
      await waitUntil(
        () => barrierMock.commands.filter((command) => command.method === 'Runtime.evaluate').length > matchedCommandsBefore,
        'matching wait entered delayed CDP evaluation',
      );
      await delay(650);
      const matchedWaitResult = await matchedWait;
      assertError(matchedWaitResult, 409, 'WAIT_CANCELLED');
      const expiredMatchedTask = await waitUntil(async () => {
        const state = await getJson(
          barrierProxy.base,
          `/v2/tasks/${encodeURIComponent(matchedTask.taskId)}`,
          matchedTask.taskToken,
        );
        return state.body?.state === 'expired' ? state : null;
      }, 'matched wait task expiry after cancellation');
      assert.equal(expiredMatchedTask.body.tabCount, 0);
      assert.ok(barrierMock.targets.has(matchedTab.targetId), 'cancelled matching wait tab must remain as a user tab');
      return {
        actionDrainedBeforeExpiry: true,
        waitCancelledBeforeExpiry: true,
        cancellationWinsDelayedMatch: true,
        ownershipHeldByBarrier: true,
      };
    } finally {
      await stopIsolatedProxy(barrierProxy);
      await barrierMock.close();
    }
  });

  await runTest('handoff-cancels-wait-that-is-still-in-session-initialization', async () => {
    const initializationMock = await startMockCdpServer('edge', {
      commandDelays: { 'Target.attachToTarget': 700 },
    });
    const initializationProxy = await startIsolatedProxy(initializationMock, {
      CDP_TASK_IDLE_TIMEOUT: '5000',
      CDP_HANDOFF_TIMEOUT: '5000',
      CDP_TAB_IDLE_TIMEOUT: '5000',
      CDP_COMMAND_TIMEOUT: '3000',
    });
    try {
      const task = await createTask(initializationProxy.base);
      const tab = await createTab(initializationProxy.base, task, 'https://example.test/wait-initializing');
      const popupId = initializationMock.createPopup(tab.targetId, 'https://example.test/wait-initializing-popup');
      await waitUntil(async () => {
        const tabs = await listTabs(initializationProxy.base, task);
        return tabs.some((candidate) => candidate.targetId === popupId);
      }, 'popup ownership before initialization wait');
      const attachBefore = initializationMock.commands.filter((command) => command.method === 'Target.attachToTarget').length;
      const started = Date.now();
      const waiting = postJson(initializationProxy.base, `/v2/tabs/${encodeURIComponent(popupId)}/wait`, {
        text: 'never-appears',
        timeoutMs: 2500,
      }, { token: task.taskToken, key: nextKey('initializing-wait'), timeoutMs: 5000 });
      await waitUntil(
        () => initializationMock.commands.filter((command) => command.method === 'Target.attachToTarget').length > attachBefore,
        'wait entered Target.attachToTarget',
      );

      const handoff = taskTransition(initializationProxy.base, task, 'handoff', { targetId: popupId });
      const waitResult = await waiting;
      assertError(waitResult, 409, 'WAIT_CANCELLED');
      const handoffResult = await handoff;
      assert.equal(handoffResult.status, 200, JSON.stringify(handoffResult.body));
      assert.equal(handoffResult.body.state, 'handoff');
      assert.ok(Date.now() - started < 1800, 'handoff 应取消初始化中的 wait，不得等待业务 timeout');
      return { cancelledDuringInitialization: true, attachDelayMs: 700 };
    } finally {
      await stopIsolatedProxy(initializationProxy);
      await initializationMock.close();
    }
  });

  await runTest('idle-gc-locks-in-flight-action-and-restarts-idle-window-after-release', async () => {
    const idleMock = await startMockCdpServer('edge', {
      commandDelays: { 'Runtime.callFunctionOn': 900 },
    });
    const idleProxy = await startIsolatedProxy(idleMock, {
      CDP_TASK_IDLE_TIMEOUT: '5000',
      CDP_HANDOFF_TIMEOUT: '5000',
      CDP_TAB_IDLE_TIMEOUT: '400',
      CDP_TERMINAL_RETENTION: '3000',
      CDP_COMMAND_TIMEOUT: '3000',
    });
    try {
      const task = await createTask(idleProxy.base);
      const tab = await createTab(idleProxy.base, task, 'https://example.test/idle-gc-action');
      const snapshot = await getSnapshot(idleProxy.base, task, tab.targetId);
      const ref = findNode(snapshot, 'button', 'Submit').ref;
      const callBefore = idleMock.commands.filter((command) => command.method === 'Runtime.callFunctionOn').length;
      const action = doAction(idleProxy.base, task, tab.targetId, { action: 'click', ref });
      await waitUntil(
        () => idleMock.commands.filter((command) => command.method === 'Runtime.callFunctionOn').length > callBefore,
        'idle GC action entered CDP',
      );
      await delay(650);
      assert.ok(idleMock.targets.has(tab.targetId), 'target lock 持有期间 idle GC 不得关闭 tab');

      const actionResult = await action;
      assert.equal(actionResult.status, 200, JSON.stringify(actionResult.body));
      assert.ok(idleMock.targets.has(tab.targetId), 'action 返回时 tab 必须仍存在');
      await delay(250);
      assert.ok(idleMock.targets.has(tab.targetId), 'idle 窗口必须从 action 完成后重新计算');
      await waitUntil(() => !idleMock.targets.has(tab.targetId), 'tab GC after post-action idle window', 2000);
      const closeCommands = idleMock.commands.filter(
        (command) => command.method === 'Target.closeTarget' && command.params.targetId === tab.targetId,
      );
      assert.equal(closeCommands.length, 1);
      return { protectedWhileBusy: true, postActionIdleMs: 400, closedOnce: true };
    } finally {
      await stopIsolatedProxy(idleProxy);
      await idleMock.close();
    }
  });

  await runTest('mutation-timeout-is-unknown-result-and-replay-is-safe', async () => {
    const timeoutMock = await startMockCdpServer('edge', { commandDelays: { 'Target.createTarget': 250 } });
    const timeoutProxy = await startIsolatedProxy(timeoutMock, { CDP_COMMAND_TIMEOUT: '50' });
    try {
      const task = await createTask(timeoutProxy.base);
      const key = nextKey('unknown-result');
      const first = await postJson(timeoutProxy.base, '/v2/tabs', { url: 'https://example.test/slow-create' }, { token: task.taskToken, key, timeoutMs: 2000 });
      assertError(first, 504, 'UNKNOWN_RESULT');
      const replay = await postJson(timeoutProxy.base, '/v2/tabs', { url: 'https://example.test/slow-create' }, { token: task.taskToken, key, timeoutMs: 2000 });
      assertError(replay, 504, 'UNKNOWN_RESULT');
      assert.deepEqual(replay.body, first.body);
      await waitUntil(
        () => [...timeoutMock.targets.values()].some((target) => target.url === 'https://example.test/slow-create'),
        'late-created target navigation',
      );
    } finally {
      await stopIsolatedProxy(timeoutProxy);
      await timeoutMock.close();
    }
    return { unknownResult: true, replayedWithoutSecondMutation: true };
  });

  await runTest('late-create-target-is-owned-while-active-and-closed-after-complete', async () => {
    const lateMock = await startMockCdpServer('edge', { commandDelays: { 'Target.createTarget': 250 } });
    const lateProxy = await startIsolatedProxy(lateMock, {
      CDP_COMMAND_TIMEOUT: '50',
      CDP_TASK_IDLE_TIMEOUT: '5000',
      CDP_TAB_IDLE_TIMEOUT: '5000',
    });
    try {
      const activeTask = await createTask(lateProxy.base);
      const activeKey = nextKey('late-active-create');
      const activeUrl = 'https://example.test/late-active';
      const activeCreate = await postJson(lateProxy.base, '/v2/tabs', { url: activeUrl }, {
        token: activeTask.taskToken,
        key: activeKey,
        timeoutMs: 2000,
      });
      assertError(activeCreate, 504, 'UNKNOWN_RESULT');
      const activeTabs = await waitUntil(async () => {
        const listed = await getJson(lateProxy.base, '/v2/tabs', activeTask.taskToken);
        if (listed.status !== 200) return null;
        const tabs = tabsFrom(listed.body) || [];
        return tabs.some((tab) => lateMock.targets.get(tab.targetId)?.url === activeUrl) ? tabs : null;
      }, 'late create target ownership');
      const activeTargetId = activeTabs.find((tab) => lateMock.targets.get(tab.targetId)?.url === activeUrl)?.targetId;
      assert.ok(activeTargetId, 'mock 必须已创建并导航等待晚到结果的 target');
      assert.ok(activeTabs.some((tab) => tab.targetId === activeTargetId));
      const activeCreates = lateMock.commands.filter(
        (command) => command.method === 'Target.createTarget' && command.params.url === 'about:blank',
      );
      assert.equal(activeCreates.length, 1);

      const completedTask = await createTask(lateProxy.base);
      const completedUrl = 'https://example.test/late-completed';
      const completedCreate = await postJson(lateProxy.base, '/v2/tabs', { url: completedUrl }, {
        token: completedTask.taskToken,
        key: nextKey('late-completed-create'),
        timeoutMs: 2000,
      });
      assertError(completedCreate, 504, 'UNKNOWN_RESULT');
      const completedTargetId = [...lateMock.targets.values()].find((target) => target.url === 'about:blank')?.targetId;
      assert.ok(completedTargetId, 'mock 必须已创建待回收的晚到 target');
      assert.ok(lateMock.targets.has(completedTargetId));

      const complete = await taskTransition(lateProxy.base, completedTask, 'complete');
      assert.equal(complete.status, 200, JSON.stringify(complete.body));
      assert.equal(complete.body.state, 'completed');
      assert.equal(complete.body.keep, false);
      await waitUntil(() => !lateMock.targets.has(completedTargetId), 'late target closed after task completion');
      const lateClose = lateMock.commands.filter(
        (command) => command.method === 'Target.closeTarget' && command.params.targetId === completedTargetId,
      );
      assert.equal(lateClose.length, 1, '终态晚到 target 必须且只能关闭一次');

      const keptTask = await createTask(lateProxy.base);
      const keptUrl = 'https://example.test/late-kept';
      const keptCreate = await postJson(lateProxy.base, '/v2/tabs', { url: keptUrl }, {
        token: keptTask.taskToken,
        key: nextKey('late-kept-create'),
        timeoutMs: 2000,
      });
      assertError(keptCreate, 504, 'UNKNOWN_RESULT');
      const keptTargetId = [...lateMock.targets.values()].find((target) => target.url === 'about:blank')?.targetId;
      assert.ok(keptTargetId, 'mock 必须已创建待保留的晚到 target');
      const keep = await taskTransition(lateProxy.base, keptTask, 'complete', { keep: true });
      assert.equal(keep.status, 200, JSON.stringify(keep.body));
      assert.equal(keep.body.keep, true);
      await waitUntil(() => lateMock.targets.get(keptTargetId)?.url === keptUrl, 'kept late target navigation');
      assert.ok(lateMock.targets.has(keptTargetId), 'keep:true 必须保留晚到 target');
      assert.equal(lateMock.commands.filter(
        (command) => command.method === 'Target.closeTarget' && command.params.targetId === keptTargetId,
      ).length, 0);
      const terminalRead = await getJson(lateProxy.base, '/v2/tabs', completedTask.taskToken);
      assertError(terminalRead, 410, 'TASK_TERMINAL');
      return { activeLateTargetOwned: true, completedLateTargetClosed: true, keptLateTargetNavigated: true };
    } finally {
      await stopIsolatedProxy(lateProxy);
      await lateMock.close();
    }
  });

  await runTest('expired-late-create-target-keeps-original-navigation', async () => {
    const expiredMock = await startMockCdpServer('edge', { commandDelays: { 'Target.createTarget': 500 } });
    const expiredProxy = await startIsolatedProxy(expiredMock, {
      CDP_COMMAND_TIMEOUT: '50',
      CDP_TASK_IDLE_TIMEOUT: '100',
      CDP_TAB_IDLE_TIMEOUT: '5000',
      CDP_TERMINAL_RETENTION: '2000',
    });
    try {
      const task = await createTask(expiredProxy.base);
      const url = 'https://example.test/late-expired';
      const create = await postJson(expiredProxy.base, '/v2/tabs', { url }, {
        token: task.taskToken,
        key: nextKey('late-expired-create'),
        timeoutMs: 2000,
      });
      assertError(create, 504, 'UNKNOWN_RESULT');
      const targetId = [...expiredMock.targets.values()].find((target) => target.url === 'about:blank')?.targetId;
      assert.ok(targetId, 'mock 必须已创建等待过期的 target');
      await waitUntil(async () => {
        const state = await getJson(expiredProxy.base, `/v2/tasks/${encodeURIComponent(task.taskId)}`, task.taskToken);
        return state.status === 200 && state.body.state === 'expired';
      }, 'task expiry before late create result');
      await waitUntil(() => expiredMock.targets.get(targetId)?.url === url, 'expired late target navigation');
      assert.ok(expiredMock.targets.has(targetId), 'expired task 的晚到 target 应作为用户 tab 保留');
      return { expiredBeforeLateResult: true, originalUrlPreserved: true };
    } finally {
      await stopIsolatedProxy(expiredProxy);
      await expiredMock.close();
    }
  });

  await runTest('complete-close-timeout-is-terminal-and-idempotently-replayed', async () => {
    const closeMock = await startMockCdpServer('edge', { commandDelays: { 'Target.closeTarget': 250 } });
    const closeProxy = await startIsolatedProxy(closeMock, {
      CDP_COMMAND_TIMEOUT: '50',
      CDP_TASK_IDLE_TIMEOUT: '5000',
      CDP_TAB_IDLE_TIMEOUT: '5000',
      CDP_TERMINAL_RETENTION: '3000',
    });
    try {
      const task = await createTask(closeProxy.base);
      const tab = await createTab(closeProxy.base, task, 'https://example.test/slow-complete-close');
      const key = nextKey('complete-close-timeout');
      const before = closeMock.commands.filter(
        (command) => command.method === 'Target.closeTarget' && command.params.targetId === tab.targetId,
      ).length;

      const first = await taskTransition(closeProxy.base, task, 'complete', {}, key);
      assertError(first, 504, 'UNKNOWN_RESULT');
      const state = await getJson(closeProxy.base, `/v2/tasks/${encodeURIComponent(task.taskId)}`, task.taskToken);
      assert.equal(state.status, 200, JSON.stringify(state.body));
      assert.equal(state.body.state, 'completed', 'closeTarget 超时后 complete 仍必须进入终态');
      const terminalRead = await getJson(closeProxy.base, '/v2/tabs', task.taskToken);
      assertError(terminalRead, 410, 'TASK_TERMINAL');
      const terminalWrite = await postJson(closeProxy.base, '/v2/tabs', { url: 'https://example.test/blocked' }, {
        token: task.taskToken,
        key: nextKey('terminal-write'),
      });
      assertError(terminalWrite, 410, 'TASK_TERMINAL');

      const replay = await taskTransition(closeProxy.base, task, 'complete', {}, key);
      assert.equal(replay.status, first.status);
      assert.deepEqual(replay.body, first.body);
      await delay(300);
      const after = closeMock.commands.filter(
        (command) => command.method === 'Target.closeTarget' && command.params.targetId === tab.targetId,
      ).length;
      assert.equal(after - before, 1, '相同 complete 幂等键不得重复 closeTarget');
      return { unknownResult: true, terminalState: 'completed', closeCommands: 1, exactReplay: true };
    } finally {
      await stopIsolatedProxy(closeProxy);
      await closeMock.close();
    }
  });

  await runTest('old-proxy-is-rejected-without-stop-or-overwrite', async () => {
    const legacyPort = await freePort();
    const legacy = await startLegacyProxyStub(legacyPort);
    try {
      const env = { ...baseEnv, CDP_PROXY_PORT: String(legacyPort), WEB_ACCESS_EDGE_PORT: String(legacyPort) };
      const child = spawnNode([checkDepsScript, '--browser', 'edge', '--json'], env);
      const code = await waitForExit(child, 10000);
      assert.equal(code, 1, `${child.stdoutText}\n${child.stderrText}`);
      const report = JSON.parse(child.stdoutText);
      assert.equal(report.status, 'protocol_mismatch');
      assert.equal(report.results?.[0]?.status, 'protocol_mismatch');
      assert.equal(legacy.listening, true, 'check-deps must not stop an old proxy');
    } finally {
      await new Promise((resolve) => legacy.close(resolve));
    }
    return { legacyPreserved: true, status: 'protocol_mismatch' };
  });

  await runTest('protocol-v2-proxy-with-unknown-browser-is-rejected-and-preserved', async () => {
    const unknownPort = await freePort();
    const unknown = await startProxyStub(unknownPort, {
      service: 'web-access-cdp-proxy',
      status: 'ok',
      protocolVersion: 2,
      connected: true,
      requestedBrowser: 'unknown',
      proxyPort: unknownPort,
      browser: { id: 'unknown', label: 'Unknown browser' },
      sessions: 0,
      managedTabs: 0,
      activeTasks: 0,
      chromePort: null,
      pid: process.pid,
    }, { body: validCapabilities });
    try {
      const env = { ...baseEnv, CDP_PROXY_PORT: String(unknownPort), WEB_ACCESS_EDGE_PORT: String(unknownPort) };
      const check = spawnNode([checkDepsScript, '--browser', 'edge', '--json'], env);
      const checkCode = await waitForExit(check, 10000);
      assert.equal(checkCode, 1, `${check.stdoutText}\n${check.stderrText}`);
      const report = JSON.parse(check.stdoutText);
      assert.equal(report.status, 'browser_proxy_mismatch');
      assert.equal(report.results?.[0]?.status, 'browser_proxy_mismatch');
      assert.equal(report.results?.[0]?.actualBrowserId, 'unknown');
      assert.equal(unknown.listening, true, 'check-deps 不得停止 browser=unknown 的 v2 Proxy');

      const direct = spawnNode([proxyScript, '--browser', 'edge'], env);
      const directCode = await waitForExit(direct, 10000);
      assert.equal(directCode, 1, `${direct.stdoutText}\n${direct.stderrText}`);
      assert.ok(!direct.stdoutText.includes('Compatible protocol v2 proxy already runs'));
      assert.equal(unknown.listening, true, '直接启动也不得停止或替换 browser=unknown 的 Proxy');
      return { checkDepsRejected: true, directStartRejected: true, existingProxyPreserved: true };
    } finally {
      await new Promise((resolve) => unknown.close(resolve));
    }
  });

  const browserIdentityScenarios = [
    {
      name: 'missing-browser-id',
      health: { ...capabilityHealth, browser: null },
      expectedIssue: 'browser_id_missing',
      directStartMustReject: true,
    },
    {
      name: 'requested-browser-conflict',
      health: { ...capabilityHealth, requestedBrowser: 'chrome' },
      expectedIssue: 'requested_browser_conflict',
      directStartMustReject: true,
    },
    {
      name: 'cdp-port-mismatch',
      health: { ...capabilityHealth, chromePort: edgeMock.port + 1000 },
      expectedIssue: 'cdp_port_mismatch',
      directStartMustReject: false,
    },
  ];
  for (const scenario of browserIdentityScenarios) {
    await runTest(`protocol-v2-proxy-${scenario.name}-is-rejected-and-preserved`, async () => {
      const proxyPort = await freePort();
      const stub = await startProxyStub(proxyPort, { ...scenario.health, proxyPort }, { body: untrustedCapabilities });
      try {
        const env = { ...baseEnv, CDP_PROXY_PORT: String(proxyPort), WEB_ACCESS_EDGE_PORT: String(proxyPort) };
        const check = spawnNode([checkDepsScript, '--browser', 'edge', '--json'], env);
        const checkCode = await waitForExit(check, 10000);
        assert.equal(checkCode, 1, `${check.stdoutText}\n${check.stderrText}`);
        const report = JSON.parse(check.stdoutText);
        assert.equal(report.status, 'browser_proxy_mismatch');
        assert.equal(report.results?.[0]?.status, 'browser_proxy_mismatch');
        assert.equal(report.results?.[0]?.identityIssue, scenario.expectedIssue);
        assert.equal(stub.requests.filter((entry) => entry.url === '/capabilities').length, 0, '身份无效时不得继续能力握手');
        assert.ok(!check.stdoutText.includes(injectedCapabilitySecret));

        if (scenario.directStartMustReject) {
          const direct = spawnNode([proxyScript, '--browser', 'edge'], env);
          const directCode = await waitForExit(direct, 10000);
          assert.equal(directCode, 1, `${direct.stdoutText}\n${direct.stderrText}`);
        }

        assert.equal(stub.listening, true, '身份检查失败不得停止或替换现有 Proxy');
        return {
          identityIssue: scenario.expectedIssue,
          existingProxyPreserved: true,
          directStartRejected: scenario.directStartMustReject,
        };
      } finally {
        await new Promise((resolve) => stub.close(resolve));
      }
    });
  }

  await runTest('proxy-restart-keeps-tabs-but-clears-task-tokens-and-ownership', async () => {
    const task = await createTask(edgeBase);
    const tab = await createTab(edgeBase, task, 'https://example.test/restart');
    const before = await waitForHealth(edgeProxyPort);
    await stopPid(before.pid);
    await waitForNoHealth(edgeProxyPort);
    assert.ok(edgeMock.targets.has(tab.targetId), 'stopping a proxy must not close browser tabs');
    edgeProxyChild = spawnNode([proxyScript, '--browser', 'edge'], baseEnv);
    await waitForHealth(edgeProxyPort);
    await waitUntil(async () => (await getHealth(edgeProxyPort))?.connected, 'restarted Edge proxy connection');
    const oldToken = await getJson(edgeBase, '/v2/tabs', task.taskToken);
    assertError(oldToken, 401, 'UNAUTHORIZED');
    assert.ok(edgeMock.targets.has(tab.targetId), 'old task tab remains as a user tab after restart');
    return { tabPreserved: true, oldTokenRejected: true };
  });

  await runTest('stopping-edge-does-not-affect-chrome', async () => {
    edgeHealth = await waitForHealth(edgeProxyPort);
    chromeHealth = await waitForHealth(chromeProxyPort);
    assert.ok(edgeHealth.pid, 'health 应暴露 Edge Proxy PID');
    assert.ok(chromeHealth.pid, 'health 应暴露 Chrome Proxy PID');
    await stopPid(edgeHealth.pid);
    await waitForNoHealth(edgeProxyPort);
    const after = await waitForHealth(chromeProxyPort);
    assert.equal(after.browser?.id, 'chrome');
    assert.equal(after.protocolVersion, 2);
    const capabilities = await getJson(chromeBase, '/capabilities');
    assert.equal(capabilities.status, 200);
    return { stopped: 'edge', unaffected: 'chrome', chromePid: after.pid };
  });

  await runTest('concurrent-start-has-one-live-proxy', async () => {
    const proxyPort = await freePort();
    const env = { ...baseEnv, CDP_PROXY_PORT: String(proxyPort), WEB_ACCESS_EDGE_PORT: String(proxyPort) };
    const connectionsBefore = edgeMock.totalConnections;
    const children = Array.from({ length: 20 }, () => spawnNode([proxyScript, '--browser', 'edge'], env));
    const health = await waitForHealth(proxyPort);
    await delay(1500);
    const alive = children.filter((child) => child.exitCode === null);
    assert.equal(alive.length, 1, `同一端口仍有 ${alive.length} 个存活 Proxy 进程`);
    assert.equal(edgeMock.totalConnections - connectionsBefore, 1, '并发输家不得连接浏览器 CDP');
    assert.equal(health.browser?.id, 'edge');
    assert.equal(health.protocolVersion, 2);
    await Promise.all(children.map(stopChild));
    return {
      attempted: children.length,
      liveProcesses: alive.length,
      newCdpWebSockets: edgeMock.totalConnections - connectionsBefore,
      proxyPid: health.pid || null,
    };
  });

  await runTest('atomic-bind-and-fatal-error-guard', async () => {
    assert.ok(!proxySource.includes('function checkPortAvailable'), '仍存在先探测端口再监听的竞态窗口');
    assert.match(proxySource, /server\.once\('error',[\s\S]*EADDRINUSE/);
    assert.match(proxySource, /uncaughtException[\s\S]*process\.exit\(1\)/);
    return { atomicListen: true, eaddrinuseHandled: true, fatalErrorsExit: true };
  });
} finally {
  const liveEdge = await getHealth(edgeProxyPort);
  const liveChrome = await getHealth(chromeProxyPort);
  if (liveEdge?.pid) await stopPid(liveEdge.pid);
  if (liveChrome?.pid) await stopPid(liveChrome.pid);
  await stopChild(edgeProxyChild);
  await stopChild(chromeProxyChild);
  for (const child of [...ownedChildren]) await stopChild(child);
  await edgeMock.close();
  await chromeMock.close();
  fs.rmSync(tempRoot, { recursive: true, force: true });
}

const report = {
  skillRoot,
  generatedAt: new Date().toISOString(),
  passed: results.filter((result) => result.passed).length,
  failed: results.filter((result) => !result.passed).length,
  results,
};

if (outputPath) {
  fs.mkdirSync(path.dirname(outputPath), { recursive: true });
  fs.writeFileSync(outputPath, `${JSON.stringify(report, null, 2)}\n`);
}
process.stdout.write(`${JSON.stringify(report, null, 2)}\n`);
process.exitCode = report.failed ? 1 : 0;
