import assert from 'node:assert/strict';
import http from 'node:http';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';

import {
  acquireManagedLock,
  commandMatchesManagedEdge,
  managedBrowserPaths,
  managedInstanceId,
  parseDevToolsActivePort,
  proxyCommandMatchesManaged,
} from '../scripts/managed-browser.mjs';
import {
  managedProxyIssue,
  probeBrowserControl,
} from '../scripts/check-deps.mjs';
import { ensureCanonicalConfig } from '../scripts/runtime-config.mjs';
import { BROKER_VERSION } from '../scripts/broker-version.mjs';

test('parseDevToolsActivePort accepts Chrome endpoint files and rejects unsafe values', () => {
  assert.deepEqual(
    parseDevToolsActivePort('9222\n/devtools/browser/browser-guid\n'),
    { port: 9222, wsPath: '/devtools/browser/browser-guid' },
  );
  assert.equal(parseDevToolsActivePort('not-a-port\n/devtools/browser/x'), null);
  assert.equal(parseDevToolsActivePort('9222\nhttps://example.test/'), null);
});

test('managed browser identity requires the exact profile and debugging port', () => {
  const profilePath = path.join('C:\\', 'Users', 'Example', 'managed-edge-profile');
  assert.equal(
    commandMatchesManagedEdge(
      '"C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe" ' +
        '--remote-debugging-port=9222 --user-data-dir=C:\\Users\\Example\\managed-edge-profile',
      profilePath,
    ),
    true,
  );
  assert.equal(
    commandMatchesManagedEdge(
      '"C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe" ' +
        '--user-data-dir=C:\\Users\\Example\\daily-profile',
      profilePath,
    ),
    false,
  );
  assert.equal(
    commandMatchesManagedEdge(
      '"C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe" ' +
        '--type=renderer --remote-debugging-port=9222 ' +
        '--user-data-dir=C:\\Users\\Example\\managed-edge-profile',
      profilePath,
    ),
    false,
  );
});

test('only a verified managed proxy process is eligible for automatic repair', () => {
  const instanceId = '0123456789abcdef01234567';
  assert.equal(
    proxyCommandMatchesManaged(
      'node cdp-proxy.mjs --browser edge --broker-profile-mode managed ' +
        `--managed-instance-id ${instanceId}`,
      instanceId,
    ),
    true,
  );
  assert.equal(
    proxyCommandMatchesManaged(
      'node cdp-proxy.mjs --browser edge',
      instanceId,
    ),
    false,
  );
});

test('managed proxy health distinguishes version, mode, browser, port, and instance mismatches', () => {
  const instanceId = '0123456789abcdef01234567';
  const health = {
    status: 'ok',
    service: 'web-access-cdp-proxy',
    protocolVersion: 2,
    brokerVersion: BROKER_VERSION,
    profileMode: 'managed',
    requestedBrowser: 'edge',
    browser: { id: 'edge' },
    proxyPort: 3456,
    connected: true,
    chromePort: 9222,
    managedInstanceId: instanceId,
  };
  const managed = { instanceId, cdpPort: 9222 };
  assert.equal(managedProxyIssue(health, managed, 3456), null);
  assert.equal(
    managedProxyIssue({ ...health, brokerVersion: 'old' }, managed, 3456),
    'proxy_version_mismatch',
  );
  assert.equal(
    managedProxyIssue({ ...health, profileMode: 'existing' }, managed, 3456),
    'proxy_mode_mismatch',
  );
  assert.equal(
    managedProxyIssue({ ...health, browser: { id: 'chrome' } }, managed, 3456),
    'proxy_browser_mismatch',
  );
  assert.equal(
    managedProxyIssue({ ...health, proxyPort: 3457 }, managed, 3456),
    'proxy_port_mismatch',
  );
  assert.equal(
    managedProxyIssue({ ...health, managedInstanceId: 'stale' }, managed, 3456),
    'proxy_instance_mismatch',
  );
});

test('managed instance IDs are stable and do not expose the websocket path', () => {
  const endpoint = { wsPath: '/devtools/browser/example-guid' };
  const first = managedInstanceId(endpoint);
  assert.match(first, /^[0-9a-f]{24}$/);
  assert.equal(first, managedInstanceId(endpoint));
  assert.ok(!first.includes('example-guid'));
});

test('canonical config migration preserves existing keys and adds managed mode', () => {
  const testRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'web-access-config-'));
  const localAppData = path.join(testRoot, 'LocalAppData');
  const configRoot = path.join(localAppData, 'web-access');
  fs.mkdirSync(configRoot, { recursive: true });
  const configPath = path.join(configRoot, 'config.env');
  fs.writeFileSync(
    configPath,
    [
      'WEB_ACCESS_BROWSER=edge',
      'WEB_ACCESS_EDGE_PORT=3456',
      'WEB_ACCESS_CHROME_PORT=3457',
      'CUSTOM_SETTING=keep-me',
      '',
    ].join('\n'),
    'utf8',
  );
  const previous = {
    testMode: process.env.WEB_ACCESS_TEST_MODE,
    testRoot: process.env.WEB_ACCESS_TEST_ROOT,
    localAppData: process.env.LOCALAPPDATA,
  };
  try {
    process.env.WEB_ACCESS_TEST_MODE = '1';
    process.env.WEB_ACCESS_TEST_ROOT = testRoot;
    process.env.LOCALAPPDATA = localAppData;
    const result = ensureCanonicalConfig();
    assert.equal(result.migrated, true);
    assert.equal(result.config.WEB_ACCESS_BROWSER_MODE, 'managed');
    const updated = fs.readFileSync(configPath, 'utf8');
    assert.match(updated, /^WEB_ACCESS_BROWSER_MODE=managed$/m);
    assert.match(updated, /^CUSTOM_SETTING=keep-me$/m);
  } finally {
    for (const [name, value] of Object.entries(previous)) {
      const envName = {
        testMode: 'WEB_ACCESS_TEST_MODE',
        testRoot: 'WEB_ACCESS_TEST_ROOT',
        localAppData: 'LOCALAPPDATA',
      }[name];
      if (value === undefined) delete process.env[envName];
      else process.env[envName] = value;
    }
    fs.rmSync(testRoot, { recursive: true, force: true });
  }
});

test('control probe reports task capacity and a successful round trip', async () => {
  const requests = [];
  const server = http.createServer((request, response) => {
    requests.push(`${request.method} ${request.url}`);
    response.setHeader('Content-Type', 'application/json');
    if (request.url === '/v2/tasks' && request.method === 'POST') {
      response.statusCode = 201;
      response.end(JSON.stringify({ taskId: 'task_test', taskToken: 'token_test' }));
      return;
    }
    if (request.url === '/v2/tabs' && request.method === 'POST') {
      response.statusCode = 201;
      response.end(JSON.stringify({ targetId: 'tab_test' }));
      return;
    }
    if (request.url === '/v2/tabs/tab_test/eval' && request.method === 'POST') {
      response.statusCode = 200;
      response.end(JSON.stringify({ value: { href: 'about:blank', readyState: 'complete' } }));
      return;
    }
    if (request.url === '/v2/tasks/task_test/complete' && request.method === 'POST') {
      response.statusCode = 200;
      response.end(JSON.stringify({ state: 'completed' }));
      return;
    }
    response.statusCode = 404;
    response.end('{}');
  });
  await new Promise((resolve, reject) => {
    server.once('error', reject);
    server.listen(0, '127.0.0.1', resolve);
  });
  try {
    const port = server.address().port;
    const result = await probeBrowserControl(port);
    assert.equal(result.passed, true);
    assert.deepEqual(requests, [
      'POST /v2/tasks',
      'POST /v2/tabs',
      'POST /v2/tabs/tab_test/eval',
      'POST /v2/tasks/task_test/complete',
    ]);
  } finally {
    await new Promise((resolve) => server.close(resolve));
  }
});

test('control probe fails closed when task capacity is reached', async () => {
  const server = http.createServer((request, response) => {
    response.statusCode = 429;
    response.setHeader('Content-Type', 'application/json');
    response.end(JSON.stringify({ error: { code: 'TASK_LIMIT' } }));
  });
  await new Promise((resolve, reject) => {
    server.once('error', reject);
    server.listen(0, '127.0.0.1', resolve);
  });
  try {
    const result = await probeBrowserControl(server.address().port);
    assert.equal(result.passed, false);
    assert.equal(result.code, 'task_capacity_reached');
  } finally {
    await new Promise((resolve) => server.close(resolve));
  }
});

test('managed lock is isolated under the canonical runtime root', async () => {
  const testRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'web-access-lock-'));
  const localAppData = path.join(testRoot, 'LocalAppData');
  fs.mkdirSync(localAppData, { recursive: true });
  const previous = {
    testMode: process.env.WEB_ACCESS_TEST_MODE,
    testRoot: process.env.WEB_ACCESS_TEST_ROOT,
    localAppData: process.env.LOCALAPPDATA,
  };
  try {
    process.env.WEB_ACCESS_TEST_MODE = '1';
    process.env.WEB_ACCESS_TEST_ROOT = testRoot;
    process.env.LOCALAPPDATA = localAppData;
    const paths = managedBrowserPaths();
    const release = await acquireManagedLock(paths);
    assert.equal(fs.statSync(paths.lockPath).isDirectory(), true);
    release();
    assert.equal(fs.existsSync(paths.lockPath), false);
  } finally {
    if (previous.testMode === undefined) delete process.env.WEB_ACCESS_TEST_MODE;
    else process.env.WEB_ACCESS_TEST_MODE = previous.testMode;
    if (previous.testRoot === undefined) delete process.env.WEB_ACCESS_TEST_ROOT;
    else process.env.WEB_ACCESS_TEST_ROOT = previous.testRoot;
    if (previous.localAppData === undefined) delete process.env.LOCALAPPDATA;
    else process.env.LOCALAPPDATA = previous.localAppData;
    fs.rmSync(testRoot, { recursive: true, force: true });
  }
});
