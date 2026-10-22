#!/usr/bin/env node
import assert from 'node:assert/strict';
import fs from 'node:fs';
import http from 'node:http';
import net from 'node:net';
import os from 'node:os';
import path from 'node:path';

const report = {
  generatedAt: new Date().toISOString(),
  passed: false,
  checks: [],
};

if (os.platform() !== 'win32') {
  report.skipped = 'Managed Edge lifecycle tests require Windows.';
  report.passed = true;
  process.stdout.write(`${JSON.stringify(report, null, 2)}\n`);
  process.exit(0);
}

function sleep(ms) {
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

async function waitForJson(url, timeoutMs = 20_000) {
  const deadline = Date.now() + timeoutMs;
  let lastError = null;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(url, { signal: AbortSignal.timeout(1500) });
      if (response.ok) return await response.json();
      lastError = new Error(`HTTP ${response.status}`);
    } catch (error) {
      lastError = error;
    }
    await sleep(100);
  }
  throw new Error(`Timed out waiting for ${url}: ${lastError?.message || 'unknown'}`);
}

async function waitForPortClosed(port, timeoutMs = 15_000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const listening = await new Promise((resolve) => {
      const socket = net.createConnection(port, '127.0.0.1');
      const timer = setTimeout(() => {
        socket.destroy();
        resolve(false);
      }, 500);
      socket.once('connect', () => {
        clearTimeout(timer);
        socket.destroy();
        resolve(true);
      });
      socket.once('error', () => {
        clearTimeout(timer);
        resolve(false);
      });
    });
    if (!listening) return;
    await sleep(200);
  }
  throw new Error(`Port ${port} remained open.`);
}

function openCdp(url) {
  return new Promise((resolve, reject) => {
    const socket = new WebSocket(url);
    const pending = new Map();
    let sequence = 0;
    socket.addEventListener('message', (event) => {
      let message;
      try {
        message = JSON.parse(String(event.data));
      } catch {
        return;
      }
      if (!message.id || !pending.has(message.id)) return;
      const item = pending.get(message.id);
      pending.delete(message.id);
      clearTimeout(item.timer);
      if (message.error) item.reject(new Error(message.error.message || 'CDP command failed'));
      else item.resolve(message.result || {});
    });
    socket.addEventListener('error', () => {
      reject(new Error('CDP WebSocket failed.'));
    });
    socket.addEventListener('open', () => {
      resolve({
        send(method, params = {}, sessionId = null, timeoutMs = 10_000) {
          return new Promise((resolveCommand, rejectCommand) => {
            const id = ++sequence;
            const timer = setTimeout(() => {
              pending.delete(id);
              rejectCommand(new Error(`CDP command timed out: ${method}`));
            }, timeoutMs);
            pending.set(id, { resolve: resolveCommand, reject: rejectCommand, timer });
            socket.send(JSON.stringify({
              id,
              method,
              params,
              ...(sessionId ? { sessionId } : {}),
            }));
          });
        },
        close() {
          try {
            socket.close();
          } catch {}
        },
      });
    }, { once: true });
  });
}

async function evaluatePage(client, targetId, expression) {
  const attached = await client.send('Target.attachToTarget', { targetId, flatten: true });
  const sessionId = attached.sessionId;
  await client.send('Page.enable', {}, sessionId);
  await client.send('Runtime.enable', {}, sessionId);
  const deadline = Date.now() + 10_000;
  while (Date.now() < deadline) {
    const result = await client.send('Runtime.evaluate', {
      expression: `({readyState:document.readyState,href:location.href})`,
      returnByValue: true,
    }, sessionId);
    if (
      result.result?.value?.readyState === 'complete' &&
      String(result.result?.value?.href || '').startsWith('http://127.0.0.1:')
    ) {
      break;
    }
    await sleep(100);
  }
  const result = await client.send('Runtime.evaluate', {
    expression,
    returnByValue: true,
    awaitPromise: true,
  }, sessionId);
  if (result.exceptionDetails) {
    throw new Error(result.exceptionDetails.text || 'Page evaluation failed.');
  }
  return result.result?.value;
}

const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'web-access-managed-edge-'));
const localAppData = path.join(tempRoot, 'LocalAppData');
fs.mkdirSync(localAppData, { recursive: true });
const cdpPort = await freePort();
let fixtureServer = null;
let cdp = null;
let managedModule = null;
let browserStarted = false;

process.env.WEB_ACCESS_TEST_MODE = '1';
process.env.WEB_ACCESS_TEST_ROOT = tempRoot;
process.env.LOCALAPPDATA = localAppData;
process.env.WEB_ACCESS_MANAGED_EDGE_CDP_PORT = String(cdpPort);
process.env.WEB_ACCESS_MANAGED_EDGE_HEADLESS = '1';

try {
  const fixtureHtml = [
    '<!doctype html>',
    '<html><head><title>Managed profile fixture</title></head>',
    '<body><p>managed profile fixture</p></body></html>',
  ].join('');
  fixtureServer = http.createServer((request, response) => {
    response.setHeader('Content-Type', 'text/html; charset=utf-8');
    response.end(fixtureHtml);
  });
  await new Promise((resolve, reject) => {
    fixtureServer.once('error', reject);
    fixtureServer.listen(0, '127.0.0.1', resolve);
  });
  const fixturePort = fixtureServer.address().port;
  const fixtureUrl = `http://127.0.0.1:${fixturePort}/`;

  managedModule = await import('../scripts/managed-browser.mjs');
  const first = await managedModule.ensureManagedEdge();
  browserStarted = true;
  assert.equal(first.ready, true);
  assert.equal(first.launched, true);
  assert.equal(first.cdpPort, cdpPort);
  assert.equal(fs.existsSync(first.profilePath), true);
  report.checks.push('first-launch-created-managed-profile');

  let version = await waitForJson(`http://127.0.0.1:${cdpPort}/json/version`);
  cdp = await openCdp(version.webSocketDebuggerUrl);
  const created = await cdp.send('Target.createTarget', { url: fixtureUrl });
  const firstValue = await evaluatePage(
    cdp,
    created.targetId,
    `(() => {
      document.cookie = 'managed_test=keep; path=/; max-age=3600';
      localStorage.setItem('managed_test', 'keep');
      return {cookie: document.cookie, local: localStorage.getItem('managed_test')};
    })()`,
  );
  assert.match(firstValue.cookie, /managed_test=keep/);
  assert.equal(firstValue.local, 'keep');
  report.checks.push('profile-state-written');

  try {
    await cdp.send('Browser.close', {}, null, 2000);
  } catch {}
  cdp.close();
  cdp = null;
  await waitForPortClosed(cdpPort);
  browserStarted = false;
  report.checks.push('managed-edge-closed');

  const [second, concurrentReuse] = await Promise.all([
    managedModule.ensureManagedEdge(),
    managedModule.ensureManagedEdge(),
  ]);
  browserStarted = true;
  assert.equal(second.ready, true);
  assert.equal(concurrentReuse.ready, true);
  assert.equal(second.profilePath, first.profilePath);
  assert.equal(concurrentReuse.profilePath, first.profilePath);
  assert.equal(second.instanceId, concurrentReuse.instanceId);
  assert.equal(second.cdpPort, cdpPort);
  report.checks.push('same-profile-restarted');
  report.checks.push('concurrent-ensure-reused-same-instance');

  version = await waitForJson(`http://127.0.0.1:${cdpPort}/json/version`);
  cdp = await openCdp(version.webSocketDebuggerUrl);
  const recreated = await cdp.send('Target.createTarget', { url: fixtureUrl });
  const secondValue = await evaluatePage(
    cdp,
    recreated.targetId,
    `({cookie: document.cookie, local: localStorage.getItem('managed_test')})`,
  );
  assert.match(secondValue.cookie, /managed_test=keep/);
  assert.equal(secondValue.local, 'keep');
  report.checks.push('cookie-and-local-storage-persisted');
  report.passed = true;
} catch (error) {
  report.error = error.stack || error.message;
} finally {
  try {
    if (cdp) {
      try {
        await cdp.send('Browser.close', {}, null, 2000);
      } catch {}
      cdp.close();
    }
  } catch {}
  if (browserStarted && managedModule) {
    try {
      await managedModule.stopManagedEdge();
    } catch {}
  }
  if (fixtureServer) await new Promise((resolve) => fixtureServer.close(resolve));
  try {
    await waitForPortClosed(cdpPort, 5000);
  } catch {}
  try {
    await fs.promises.rm(tempRoot, { recursive: true, force: true, maxRetries: 10, retryDelay: 100 });
  } catch (error) {
    report.passed = false;
    report.cleanupError = error.stack || error.message;
  }
}

process.stdout.write(`${JSON.stringify(report, null, 2)}\n`);
process.exitCode = report.passed ? 0 : 1;
