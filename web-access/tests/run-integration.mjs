#!/usr/bin/env node
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import net from 'node:net';
import os from 'node:os';
import path from 'node:path';
import { startMockCdpServer } from './mock-cdp-server.mjs';

const skillRoot = path.resolve(process.argv[2] || '');
const outputPath = process.argv[3] ? path.resolve(process.argv[3]) : null;
const proxyScript = path.join(skillRoot, 'scripts', 'cdp-proxy.mjs');
const checkDepsScript = path.join(skillRoot, 'scripts', 'check-deps.mjs');
const proxySource = fs.readFileSync(proxyScript, 'utf8');
const checkDepsSource = fs.readFileSync(checkDepsScript, 'utf8');
const supportsDualProxy = checkDepsSource.includes("argv[i] === '--all'") &&
  checkDepsSource.includes('getProxyPort');
const results = [];
const ownedChildren = new Set();
const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'web-access-eval-'));

if (!fs.existsSync(proxyScript) || !fs.existsSync(checkDepsScript)) {
  throw new Error(`无效 skill 路径: ${skillRoot}`);
}

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

async function fetchJson(url, options) {
  const response = await fetch(url, { ...options, signal: AbortSignal.timeout(4000) });
  const text = await response.text();
  let body;
  try { body = JSON.parse(text); }
  catch { body = text; }
  return { status: response.status, body };
}

async function waitForHealth(port, timeoutMs = 8000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      const result = await fetchJson(`http://127.0.0.1:${port}/health`);
      if (result.status === 200 && result.body?.status === 'ok') return result.body;
    } catch {}
    await delay(50);
  }
  throw new Error(`Proxy ${port} 未在 ${timeoutMs}ms 内就绪`);
}

async function getHealth(port) {
  try {
    const result = await fetchJson(`http://127.0.0.1:${port}/health`);
    return result.status === 200 && result.body?.status === 'ok' ? result.body : null;
  } catch {
    return null;
  }
}

async function waitForNoHealth(port, timeoutMs = 5000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try { await fetchJson(`http://127.0.0.1:${port}/health`); }
    catch { return; }
    await delay(50);
  }
  throw new Error(`Proxy ${port} 未停止`);
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
    results.push({ name, passed: false, durationMs: Date.now() - started, evidence: error.message });
  }
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
  LOCALAPPDATA: localAppData,
  WEB_ACCESS_EDGE_PORT: String(edgeProxyPort),
  WEB_ACCESS_CHROME_PORT: String(chromeProxyPort),
  CDP_PROXY_PORT: String(edgeProxyPort),
  CDP_TAB_IDLE_TIMEOUT: '300000',
};

let edgeHealth = null;
let chromeHealth = null;
let regressionEdgeChild = null;

await runTest('dual-browser-check-deps-all', async () => {
  assert.ok(supportsDualProxy, '旧版不支持 --all 和浏览器专用端口');
  const child = spawnNode([checkDepsScript, '--all'], baseEnv);
  const code = await waitForExit(child, 25000);
  assert.equal(code, 0, `check-deps --all exit=${code}\n${child.stdoutText}\n${child.stderrText}`);
  edgeHealth = await waitForHealth(edgeProxyPort);
  chromeHealth = await waitForHealth(chromeProxyPort);
  assert.equal(edgeHealth.browser?.id, 'edge');
  assert.equal(chromeHealth.browser?.id, 'chrome');
  assert.match(child.stdoutText, new RegExp(`proxy-url\\[edge\\]: http://127\\.0\\.0\\.1:${edgeProxyPort}`));
  assert.match(child.stdoutText, new RegExp(`proxy-url\\[chrome\\]: http://127\\.0\\.0\\.1:${chromeProxyPort}`));
  return {
    edgeProxyPort,
    chromeProxyPort,
    edgePid: edgeHealth.pid || null,
    chromePid: chromeHealth.pid || null,
    edgeConnections: edgeMock.totalConnections,
    chromeConnections: chromeMock.totalConnections,
  };
});

if (!(await getHealth(edgeProxyPort))) {
  regressionEdgeChild = spawnNode([proxyScript, '--browser', 'edge'], baseEnv);
  await waitForHealth(edgeProxyPort);
}

await runTest('same-browser-multi-client-and-api-regression', async () => {
  edgeHealth = await waitForHealth(edgeProxyPort);
  const base = `http://127.0.0.1:${edgeProxyPort}`;
  const urls = ['https://example.test/a?x=1&y=2', 'https://example.test/b?x=3&y=4'];
  const created = await Promise.all(urls.map((url) => fetchJson(`${base}/new`, { method: 'POST', body: url })));
  const targetIds = created.map((item) => item.body.targetId);
  assert.equal(new Set(targetIds).size, 2);
  assert.equal(edgeMock.totalConnections, 1, '同一 Proxy 应只建立一个 CDP WebSocket');

  const target = targetIds[0];
  const navigateUrl = 'https://example.test/next?a=1&b=2';
  const navigate = await fetchJson(`${base}/navigate?target=${target}`, { method: 'POST', body: navigateUrl });
  assert.equal(navigate.status, 200);
  const evaluate = await fetchJson(`${base}/eval?target=${target}`, { method: 'POST', body: 'document.title' });
  assert.equal(evaluate.body.value, 'Mock Page');
  const upload = await fetchJson(`${base}/setFiles?target=${target}`, {
    method: 'POST',
    body: JSON.stringify({ selector: 'input[type=file]', files: [path.join(tempRoot, 'upload.txt')] }),
  });
  assert.deepEqual(upload.body, { success: true, files: 1 });

  const screenshotPath = path.join(tempRoot, 'shot.png');
  const screenshot = await fetchJson(`${base}/screenshot?target=${target}&file=${encodeURIComponent(screenshotPath)}`);
  assert.equal(screenshot.body.saved, screenshotPath);
  assert.ok(fs.statSync(screenshotPath).size > 0);
  assert.ok(edgeMock.commands.some((command) => command.method === 'Page.navigate' && command.params.url === navigateUrl));
  assert.ok(edgeMock.commands.some((command) => command.method === 'DOM.setFileInputFiles'));

  await Promise.all(targetIds.map((targetId) => fetchJson(`${base}/close?target=${targetId}`)));
  const health = await waitForHealth(edgeProxyPort);
  assert.equal(health.managedTabs, 0);
  return { clients: 2, cdpWebSockets: edgeMock.totalConnections, apiChecks: ['new', 'navigate', 'eval', 'setFiles', 'screenshot', 'close'] };
});

await runTest('stopping-edge-does-not-affect-chrome', async () => {
  assert.ok(supportsDualProxy, '旧版只有一个全局 Proxy，无法验证浏览器间隔离');
  edgeHealth = await waitForHealth(edgeProxyPort);
  chromeHealth = await waitForHealth(chromeProxyPort);
  assert.ok(edgeHealth.pid, 'health 应暴露 Edge Proxy PID');
  assert.ok(chromeHealth.pid, 'health 应暴露 Chrome Proxy PID');
  await stopPid(edgeHealth.pid);
  await waitForNoHealth(edgeProxyPort);
  const targets = await fetchJson(`http://127.0.0.1:${chromeProxyPort}/targets`);
  assert.equal(targets.status, 200);
  assert.ok(Array.isArray(targets.body));
  const after = await waitForHealth(chromeProxyPort);
  assert.equal(after.browser?.id, 'chrome');
  return { stopped: 'edge', unaffected: 'chrome', chromePid: after.pid };
});

await runTest('concurrent-start-has-one-live-proxy', async () => {
  const proxyPort = await freePort();
  const env = { ...baseEnv, CDP_PROXY_PORT: String(proxyPort) };
  const children = Array.from({ length: 20 }, () => spawnNode([proxyScript, '--browser', 'edge'], env));
  await waitForHealth(proxyPort);
  await delay(1500);
  const alive = children.filter((child) => child.exitCode === null);
  assert.equal(alive.length, 1, `同一端口仍有 ${alive.length} 个存活 Proxy 进程`);
  const health = await waitForHealth(proxyPort);
  assert.equal(health.browser?.id, 'edge');
  await Promise.all(children.map(stopChild));
  return { attempted: children.length, liveProcesses: alive.length, proxyPid: health.pid || null };
});

await runTest('atomic-bind-and-fatal-error-guard', async () => {
  assert.ok(!proxySource.includes('function checkPortAvailable'), '仍存在先探测端口再监听的竞态窗口');
  assert.match(proxySource, /server\.once\('error',[\s\S]*EADDRINUSE/);
  assert.match(proxySource, /uncaughtException[\s\S]*process\.exit\(1\)/);
  return { atomicListen: true, eaddrinuseHandled: true, fatalErrorsExit: true };
});

try {
  if (edgeHealth?.pid) await stopPid(edgeHealth.pid);
  if (chromeHealth?.pid) await stopPid(chromeHealth.pid);
  await stopChild(regressionEdgeChild);
  for (const child of [...ownedChildren]) await stopChild(child);
  await edgeMock.close();
  await chromeMock.close();
} finally {
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
