#!/usr/bin/env node
// 环境检查 + 确保浏览器专用 CDP Proxy 就绪
//
// 用法：
//   node check-deps.mjs                  使用 config.env 偏好（模板默认 Edge）
//   node check-deps.mjs --browser chrome 使用 Chrome 专用 Proxy
//   node check-deps.mjs --all            同时确保 Edge 和 Chrome Proxy 就绪
//   node check-deps.mjs --json           stdout 仅输出机器可读 JSON

import { spawn } from 'node:child_process';
import crypto from 'node:crypto';
import fs from 'node:fs';
import http from 'node:http';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { getProxyPort, knownBrowsers, selectBrowser } from './browser-discovery.mjs';
import {
  ensureCanonicalConfig,
  inspectCanonicalConfig,
  RuntimeConfigError,
} from './runtime-config.mjs';
import { BROKER_VERSION } from './broker-version.mjs';
import {
  ManagedBrowserError,
  acquireManagedLock,
  ensureManagedEdge,
  getProcessCommandLine,
  managedBrowserPaths,
  proxyCommandMatchesManaged,
  statusManagedEdge,
} from './managed-browser.mjs';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const PROXY_SCRIPT = path.join(ROOT, 'scripts', 'cdp-proxy.mjs');
const PERSISTENT_BROWSERS = ['edge', 'chrome'];
const EXPECTED_PROTOCOL_VERSION = 2;
const MAX_JSON_RESPONSE_BYTES = 64 * 1024;

let jsonMode = process.argv.slice(2).includes('--json');
let jsonWritten = false;

function canonicalInvocationPath(value) {
  const resolved = path.resolve(value);
  try {
    return fs.realpathSync.native(resolved);
  } catch {
    return resolved;
  }
}

// Availability judgement for the current Edge instance.
//
// HTTP /json/version (and /json/list) may return 404 while the WebSocket CDP
// endpoint is perfectly usable. A 404 from the HTTP discovery endpoint is NOT
// evidence that CDP is down. Only an actual WebSocket handshake failure (or a
// failed background tab creation) means the control channel is unavailable.
export function judgeCdpAvailability({
  devToolsActivePort = null,
  portListening = false,
  httpDiscoveryStatus = null,
  websocketHandshake = null,
  tabCreateOk = null,
} = {}) {
  const port = Number.isInteger(devToolsActivePort?.port) ? devToolsActivePort.port : null;
  const wsPath = devToolsActivePort?.wsPath || null;
  const httpDiscoveryUnavailable = httpDiscoveryStatus === 404
    || httpDiscoveryStatus === null
    || httpDiscoveryStatus === undefined;

  if (!port) {
    return {
      available: false,
      code: 'cdp_unreachable',
      reason: 'no_devtools_active_port',
      port: null,
      httpDiscoveryUnavailable,
    };
  }
  if (!portListening) {
    return {
      available: false,
      code: 'cdp_unreachable',
      reason: 'port_not_listening',
      port,
      httpDiscoveryUnavailable,
    };
  }
  if (websocketHandshake === false || tabCreateOk === false) {
    return {
      available: false,
      code: websocketHandshake === false ? 'cdp_unreachable' : 'tab_create_failed',
      reason: websocketHandshake === false ? 'websocket_handshake_failed' : 'tab_create_failed',
      port,
      httpDiscoveryUnavailable,
    };
  }
  if (websocketHandshake === true) {
    return {
      available: true,
      code: 'ready',
      // HTTP discovery being 404 is explicitly not a failure.
      reason: httpDiscoveryUnavailable ? 'websocket_ok_http_discovery_unavailable' : 'websocket_ok',
      port,
      wsPathAvailable: Boolean(wsPath),
      httpDiscoveryUnavailable,
    };
  }
  return {
    available: null,
    code: 'cdp_unknown',
    reason: 'handshake_not_attempted',
    port,
    httpDiscoveryUnavailable,
  };
}

export function invokedAsMain(importMetaUrl, argvPath) {
  if (!argvPath) return false;
  const modulePath = canonicalInvocationPath(fileURLToPath(importMetaUrl));
  const invokedPath = canonicalInvocationPath(argvPath);
  if (os.platform() === 'win32') {
    return modulePath.toLowerCase() === invokedPath.toLowerCase();
  }
  return modulePath === invokedPath;
}

function diagnostic(message = '') {
  const stream = jsonMode ? process.stderr : process.stdout;
  stream.write(`${message}\n`);
}

function diagnosticError(message) {
  process.stderr.write(`${message}\n`);
}

function emitJson(payload) {
  if (jsonWritten) return;
  jsonWritten = true;
  process.stdout.write(`${JSON.stringify(payload)}\n`);
}

function parseArgs(argv) {
  const opts = {
    browser: null,
    all: false,
    json: false,
    mode: null,
    statusOnly: false,
    probe: true,
  };
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === '--browser' && argv[i + 1]) {
      opts.browser = argv[i + 1];
      i++;
    } else if (argv[i].startsWith('--browser=')) {
      opts.browser = argv[i].slice('--browser='.length);
    } else if (argv[i] === '--all') {
      opts.all = true;
    } else if (argv[i] === '--json') {
      opts.json = true;
    } else if (argv[i] === '--mode' && argv[i + 1]) {
      opts.mode = argv[i + 1];
      i++;
    } else if (argv[i].startsWith('--mode=')) {
      opts.mode = argv[i].slice('--mode='.length);
    } else if (argv[i] === '--status-only') {
      opts.statusOnly = true;
    } else if (argv[i] === '--no-probe') {
      opts.probe = false;
    }
  }

  if (opts.all && opts.browser) {
    throw new Error('--all 与 --browser 不能同时使用');
  }
  if (opts.browser && !PERSISTENT_BROWSERS.includes(opts.browser)) {
    throw new Error(`--browser 仅支持 ${PERSISTENT_BROWSERS.join(' / ')}`);
  }
  if (opts.mode && !['managed', 'existing'].includes(opts.mode)) {
    throw new Error('--mode 仅支持 managed / existing');
  }
  if (opts.statusOnly) opts.probe = false;
  return opts;
}

function checkNode() {
  const major = Number(process.versions.node.split('.')[0]);
  const version = `v${process.versions.node}`;
  const recommended = major >= 22;
  if (recommended) diagnostic(`node: ok (${version})`);
  else diagnostic(`node: warn (${version}, 建议升级到 22+)`);
  return { version, major, recommended };
}

async function readLimitedBody(response, maxBytes) {
  if (!response) return Buffer.alloc(0);
  const chunks = [];
  let total = 0;
  for await (const chunk of response) {
    total += chunk.length;
    if (total > maxBytes) throw new Error('response_too_large');
    chunks.push(Buffer.from(chunk));
  }
  return Buffer.concat(chunks, total);
}

function isJsonContentType(value) {
  const mediaType = String(value || '').split(';', 1)[0].trim().toLowerCase();
  return mediaType === 'application/json' || mediaType.endsWith('+json');
}

function rawHttpRequest(url, {
  method = 'GET',
  headers = {},
  body = null,
  timeoutMs = 3000,
  maxBytes = MAX_JSON_RESPONSE_BYTES,
} = {}) {
  return new Promise((resolve) => {
    let request;
    let timer;
    let settled = false;
    const finish = (result) => {
      if (settled) return;
      settled = true;
      if (timer) clearTimeout(timer);
      resolve(result);
    };
    try {
      request = http.request(url, { method, headers, agent: false }, async (response) => {
        try {
          const contentLength = Number(response.headers['content-length']);
          if (Number.isFinite(contentLength) && contentLength > maxBytes) {
            response.resume();
            finish({
              ok: false,
              status: response.statusCode || null,
              reason: 'response_too_large',
              contentType: response.headers['content-type'] || null,
              value: null,
            });
            return;
          }
          const raw = await readLimitedBody(response, maxBytes);
          finish({
            ok: response.statusCode >= 200 && response.statusCode < 300,
            status: response.statusCode || null,
            reason: null,
            contentType: response.headers['content-type'] || null,
            raw,
            value: null,
          });
        } catch (error) {
          response.resume();
          finish({
            ok: false,
            status: response.statusCode || null,
            reason: error.message || 'response_read_failed',
            contentType: response.headers['content-type'] || null,
            value: null,
          });
        }
      });
    } catch (error) {
      finish({ ok: false, status: null, reason: error.message || 'request_failed', value: null });
      return;
    }
    request.on('error', (error) => {
      finish({ ok: false, status: null, reason: error.code || error.message || 'request_failed', value: null });
    });
    timer = setTimeout(() => {
      request.destroy(new Error('request_timeout'));
    }, timeoutMs);
    timer.unref?.();
    if (body !== null) request.write(body);
    request.end();
  });
}

export async function httpGetJsonResponse(url, timeoutMs = 3000, maxBytes = MAX_JSON_RESPONSE_BYTES) {
  const response = await rawHttpRequest(url, { timeoutMs, maxBytes });
  if (!response.ok) {
    return {
      ok: false,
      status: response.status,
      reason: response.reason || 'http_status',
      value: null,
    };
  }
  if (!isJsonContentType(response.contentType)) {
    return { ok: false, status: response.status, reason: 'content_type', value: null };
  }
  try {
    return {
      ok: true,
      status: response.status,
      reason: null,
      value: JSON.parse(response.raw.toString('utf8')),
    };
  } catch {
    return { ok: false, status: response.status, reason: 'invalid_json', value: null };
  }
}

async function httpGetJson(url, timeoutMs = 3000) {
  const response = await httpGetJsonResponse(url, timeoutMs);
  return response.ok ? response.value : null;
}

async function httpJsonRequest(url, { method = 'GET', body = null, token = null, key = null, timeoutMs = 5000 } = {}) {
  const headers = { Accept: 'application/json' };
  if (token) headers.Authorization = `Bearer ${token}`;
  if (method !== 'GET') {
    headers['Content-Type'] = 'application/json';
    headers['Idempotency-Key'] = key || crypto.randomUUID();
  }
  const serialized = body === null ? null : JSON.stringify(body);
  const response = await rawHttpRequest(url, {
    method,
    headers,
    body: serialized,
    timeoutMs,
  });
  if (response.reason) {
    return { ok: false, status: response.status, value: null, error: response.reason };
  }
  let value = null;
  try {
    value = response.raw.length ? JSON.parse(response.raw.toString('utf8')) : null;
  } catch {}
  return { ok: response.ok, status: response.status, value };
}

export async function probeBrowserControl(proxyPort) {
  const proxyUrl = `http://127.0.0.1:${proxyPort}`;
  const started = performance.now();
  let task = null;
  let failure = null;
  try {
    const created = await httpJsonRequest(`${proxyUrl}/v2/tasks`, {
      method: 'POST',
      body: { label: 'web-access control probe' },
    });
    if (!created.ok || !created.value?.taskId || !created.value?.taskToken) {
      failure = created.status === 429
        ? { code: 'task_capacity_reached', status: created.status }
        : { code: 'control_probe_failed', status: created.status, stage: 'create_task' };
      return { passed: false, ...failure, durationMs: Math.round(performance.now() - started) };
    }
    task = created.value;
    const tab = await httpJsonRequest(`${proxyUrl}/v2/tabs`, {
      method: 'POST',
      token: task.taskToken,
      body: { url: 'about:blank', background: true },
    });
    const targetId = tab.value?.targetId || tab.value?.id;
    if (!tab.ok || !targetId) {
      failure = { code: 'control_probe_failed', status: tab.status, stage: 'create_tab' };
      return { passed: false, ...failure, durationMs: Math.round(performance.now() - started) };
    }
    const evaluated = await httpJsonRequest(
      `${proxyUrl}/v2/tabs/${encodeURIComponent(targetId)}/eval`,
      {
        method: 'POST',
        token: task.taskToken,
        body: {
          expression: "({readyState:document.readyState,href:location.href,title:document.title})",
        },
      },
    );
    if (!evaluated.ok || evaluated.value?.value?.href !== 'about:blank') {
      failure = { code: 'control_probe_failed', status: evaluated.status, stage: 'eval' };
      return { passed: false, ...failure, durationMs: Math.round(performance.now() - started) };
    }
    return {
      passed: true,
      durationMs: Math.round(performance.now() - started),
      pageReadyState: evaluated.value.value.readyState || null,
    };
  } finally {
    if (task?.taskId && task?.taskToken) {
      await httpJsonRequest(
        `${proxyUrl}/v2/tasks/${encodeURIComponent(task.taskId)}/complete`,
        {
          method: 'POST',
          token: task.taskToken,
          body: { keep: false },
          timeoutMs: 5000,
        },
      ).catch(() => null);
    }
  }
}

function looksLikeWebAccessProxy(health) {
  if (!health || typeof health !== 'object' || Array.isArray(health)) return false;
  if (health.service === 'web-access-cdp-proxy') return true;
  return Object.hasOwn(health, 'sessions') &&
    Object.hasOwn(health, 'managedTabs') &&
    Object.hasOwn(health, 'chromePort');
}

function isWebAccessProxy(health) {
  return health?.status === 'ok' &&
    looksLikeWebAccessProxy(health) &&
    health.protocolVersion === EXPECTED_PROTOCOL_VERSION;
}

function healthBrowserId(health) {
  return health?.browser?.id || null;
}

function browserIdentityIssue(health, browser) {
  const expectedId = browser?.id || null;
  const actualId = healthBrowserId(health);
  const requestedId = health?.requestedBrowser || null;

  if (requestedId && requestedId !== expectedId) return 'requested_browser_conflict';
  if (!health?.connected) return null;
  if (!actualId) return 'browser_id_missing';
  if (actualId !== expectedId) return 'browser_id_mismatch';
  if (!Number.isInteger(browser?.port)) return 'expected_cdp_port_missing';
  if (!Number.isInteger(health?.chromePort)) return 'cdp_port_missing';
  if (health.chromePort !== browser.port) return 'cdp_port_mismatch';
  return null;
}

function proxyPortIssue(health, proxyPort) {
  if (!Number.isInteger(health?.proxyPort)) return 'proxy_port_missing';
  if (health.proxyPort !== proxyPort) return 'proxy_port_mismatch';
  return null;
}

function protocolVersionOf(health) {
  return Object.hasOwn(health || {}, 'protocolVersion') ? health.protocolVersion : null;
}

function sanitizeStringArray(value, maxItems = 64) {
  if (!Array.isArray(value)) return undefined;
  return value
    .filter((item) => typeof item === 'string')
    .slice(0, maxItems)
    .map((item) => item.slice(0, 128));
}

function sanitizeCapabilities(value) {
  const output = { protocolVersion: protocolVersionOf(value) };
  if (typeof value.taskIsolation === 'boolean') output.taskIsolation = value.taskIsolation;
  if (typeof value.userTabsVisible === 'boolean') output.userTabsVisible = value.userTabsVisible;
  if (Number.isInteger(value.maxActiveTasks)) output.maxActiveTasks = value.maxActiveTasks;

  if (value.snapshot && typeof value.snapshot === 'object' && !Array.isArray(value.snapshot)) {
    output.snapshot = {};
    if (typeof value.snapshot.source === 'string') output.snapshot.source = value.snapshot.source.slice(0, 128);
    const modes = sanitizeStringArray(value.snapshot.modes);
    if (modes) output.snapshot.modes = modes;
    for (const key of ['defaultDepth', 'defaultMaxNodes', 'hardMaxNodes']) {
      if (Number.isInteger(value.snapshot[key])) output.snapshot[key] = value.snapshot[key];
    }
  }

  for (const key of ['actions', 'waits', 'fallbacks', 'unsupported']) {
    const items = sanitizeStringArray(value[key]);
    if (items) output[key] = items;
  }

  if (value.download && typeof value.download === 'object' && !Array.isArray(value.download)) {
    output.download = {};
    if (typeof value.download.endpoint === 'string') output.download.endpoint = value.download.endpoint.slice(0, 128);
    const modes = sanitizeStringArray(value.download.modes);
    if (modes) output.download.modes = modes;
    for (const key of ['maxBytesDefault', 'maxBytesHard']) {
      if (Number.isInteger(value.download[key])) output.download[key] = value.download[key];
    }
    for (const key of ['verifiesPdfSignature', 'returnsSha256', 'writesPartialFiles']) {
      if (typeof value.download[key] === 'boolean') output.download[key] = value.download[key];
    }
  }

  if (value.security && typeof value.security === 'object' && !Array.isArray(value.security)) {
    output.security = {};
    if (typeof value.security.bind === 'string') output.security.bind = value.security.bind.slice(0, 128);
    if (typeof value.security.cors === 'boolean') output.security.cors = value.security.cors;
    if (typeof value.security.taskTokenIsLocalSecurityBoundary === 'boolean') {
      output.security.taskTokenIsLocalSecurityBoundary = value.security.taskTokenIsLocalSecurityBoundary;
    }
  }
  return output;
}

function capabilityIssue(capabilities) {
  if (capabilities?.protocolVersion !== EXPECTED_PROTOCOL_VERSION) return 'protocol_version_mismatch';
  if (capabilities?.taskIsolation !== true) return 'task_isolation_missing';
  if (capabilities?.userTabsVisible !== false) return 'user_tabs_visibility_unsafe';
  if (!Number.isInteger(capabilities?.maxActiveTasks) || capabilities.maxActiveTasks < 1) return 'task_limit_missing';
  return null;
}

function browserDetails(browser, health = null) {
  if (!browser && !health) return null;
  const cdpPort = Number.isInteger(health?.chromePort)
    ? health.chromePort
    : (Number.isInteger(browser?.port) ? browser.port : null);
  const id = browser?.id || healthBrowserId(health);
  return {
    id: id || null,
    label: browser?.label || health?.browser?.label || id || null,
    url: cdpPort ? `http://127.0.0.1:${cdpPort}` : null,
    cdpPort,
  };
}

function proxyDetails(proxyPort, health = null) {
  if (!proxyPort) return null;
  return {
    url: `http://127.0.0.1:${proxyPort}`,
    port: proxyPort,
    protocolVersion: protocolVersionOf(health),
  };
}

function cdpDetails(health) {
  if (!health || typeof health !== 'object') return null;
  const cdp = health.cdp && typeof health.cdp === 'object' ? health.cdp : null;
  const port = cdp && Number.isInteger(cdp.port) ? cdp.port : (Number.isInteger(health.chromePort) ? health.chromePort : null);
  const connected = cdp && typeof cdp.connected === 'boolean' ? cdp.connected : (typeof health.connected === 'boolean' ? health.connected : null);
  return {
    connected,
    port,
    wsPathAvailable: cdp && typeof cdp.wsPathAvailable === 'boolean' ? cdp.wsPathAvailable : null,
    lastHandshakeAt: cdp && typeof cdp.lastHandshakeAt === 'string' ? cdp.lastHandshakeAt : null,
    // HTTP /json discovery is optional and is not the availability authority.
    httpDiscoveryRequired: false,
  };
}

function makeResult({
  ok = false,
  status,
  browser = null,
  proxyPort = null,
  health = null,
  capabilities = null,
  ready = false,
  reused = false,
  exitCode = ok ? 0 : 1,
  ...extra
}) {
  return {
    ok,
    status,
    ready,
    reused,
    browser: browserDetails(browser, health),
    proxy: proxyDetails(proxyPort, health),
    cdp: cdpDetails(health),
    capabilities,
    exitCode,
    ...extra,
  };
}

function proxyLogPath(browserId, proxyPort) {
  return path.join(os.tmpdir(), `web-access-${browserId}-${proxyPort}.log`);
}

function startProxyDetached(browserId, proxyPort, extraEnv = {}, extraArgs = []) {
  const logFile = proxyLogPath(browserId, proxyPort);
  const logFd = fs.openSync(logFile, 'a');
  try {
    const child = spawn(process.execPath, [PROXY_SCRIPT, '--browser', browserId, ...extraArgs], {
      detached: true,
      stdio: ['ignore', logFd, logFd],
      env: {
        ...process.env,
        CDP_PROXY_PORT: String(proxyPort),
        ...extraEnv,
      },
      ...(os.platform() === 'win32' ? { windowsHide: true } : {}),
    });
    child.unref();
    return { pid: child.pid, logFile };
  } finally {
    fs.closeSync(logFd);
  }
}

async function completeCapabilityHandshake({ browser, proxyPort, health, reused }) {
  const browserId = browser.id;
  const proxyUrl = `http://127.0.0.1:${proxyPort}`;
  const capabilityResponse = await httpGetJsonResponse(`${proxyUrl}/capabilities`);
  const rawCapabilities = capabilityResponse.value;
  if (!capabilityResponse.ok || !rawCapabilities || typeof rawCapabilities !== 'object' || Array.isArray(rawCapabilities)) {
    diagnostic(`proxy[${browserId}]: capabilities_unavailable (${proxyUrl}/capabilities)`);
    diagnostic('  不会停止或覆盖现有 Proxy；协议能力握手失败，不能继续。');
    return makeResult({
      status: 'capabilities_unavailable',
      browser,
      proxyPort,
      health,
      reused,
      existing: true,
      capabilityStatus: capabilityResponse.status,
      capabilityFailure: capabilityResponse.reason,
    });
  }

  const capabilities = sanitizeCapabilities(rawCapabilities);
  const actualProtocolVersion = protocolVersionOf(capabilities);
  const issue = capabilityIssue(capabilities);
  if (issue) {
    diagnostic(
      `proxy[${browserId}]: capabilities_mismatch ` +
      `(实际 ${actualProtocolVersion ?? 'missing'}，期望 ${EXPECTED_PROTOCOL_VERSION}，${proxyUrl}/capabilities)`
    );
    diagnostic('  不会停止或覆盖现有 Proxy；请显式处理协议版本后重试。');
    return makeResult({
      status: 'capabilities_mismatch',
      browser,
      proxyPort,
      health,
      capabilities,
      reused,
      expectedProtocolVersion: EXPECTED_PROTOCOL_VERSION,
      capabilityIssue: issue,
      existing: true,
    });
  }

  const label = health.browser?.label || browser.label || browserId;
  diagnostic(`proxy[${browserId}]: ready (${label}, ${proxyUrl}, protocol v${EXPECTED_PROTOCOL_VERSION})`);
  return makeResult({
    ok: true,
    status: 'ready',
    browser,
    proxyPort,
    health,
    capabilities,
    ready: true,
    reused,
  });
}

async function stopVerifiedProxy(health, proxyPort, instanceId) {
  const pid = Number(health?.pid);
  if (!Number.isInteger(pid) || pid < 1) return false;
  if (health?.profileMode !== 'managed' || health?.managedProfile !== true) return false;
  const commandLine = getProcessCommandLine(pid);
  const acceptedInstanceIds = new Set(
    [instanceId, health.managedInstanceId].filter((value) => typeof value === 'string' && value),
  );
  if (![...acceptedInstanceIds].some((value) => proxyCommandMatchesManaged(commandLine, value))) {
    return false;
  }
  try {
    process.kill(pid, 'SIGTERM');
  } catch {
    return false;
  }
  const deadline = Date.now() + 8000;
  while (Date.now() < deadline) {
    const healthNow = await httpGetJson(`http://127.0.0.1:${proxyPort}/health`, 500);
    if (!healthNow) return true;
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  return false;
}

export function managedProxyIssue(health, managed, proxyPort) {
  if (!looksLikeWebAccessProxy(health)) return 'proxy_unhealthy';
  if (health.protocolVersion !== EXPECTED_PROTOCOL_VERSION) return 'proxy_protocol_mismatch';
  if (health.brokerVersion !== BROKER_VERSION) return 'proxy_version_mismatch';
  if (health.profileMode !== 'managed') return 'proxy_mode_mismatch';
  if (health.requestedBrowser !== 'edge' || health.browser?.id !== 'edge') return 'proxy_browser_mismatch';
  if (health.proxyPort !== proxyPort) return 'proxy_port_mismatch';
  if (!health.connected) return 'proxy_disconnected';
  if (health.chromePort !== managed.cdpPort) return 'proxy_cdp_port_mismatch';
  if (health.managedInstanceId !== managed.instanceId) return 'proxy_instance_mismatch';
  return null;
}

async function ensureManagedProxy(managed, opts) {
  const browser = {
    id: 'edge',
    label: 'Microsoft Edge',
    source: 'managed',
    profileMode: 'managed',
  };
  let proxyPort;
  try {
    proxyPort = getProxyPort('edge', {
      diagnostic,
      readOnly: opts.statusOnly,
    });
  } catch (error) {
    return makeResult({
      status: error instanceof RuntimeConfigError ? error.code : 'config_error',
      browser,
      error: error.message,
      exitCode: 2,
      managedBrowser: managed,
    });
  }
  const proxyUrl = `http://127.0.0.1:${proxyPort}`;
  const healthResponse = await httpGetJsonResponse(`${proxyUrl}/health`);
  let health = healthResponse.ok ? healthResponse.value : null;
  if (!healthResponse.ok) {
    diagnostic(
      `proxy[edge]: health_unavailable (${healthResponse.reason || 'unknown'}, status ${healthResponse.status ?? 'none'})`,
    );
  }

  if (health) {
    const issue = managedProxyIssue(health, managed, proxyPort);
    if (issue) {
      const activeTasks = Number.isInteger(health.activeTasks) ? health.activeTasks : 0;
      if (opts.statusOnly) {
        return makeResult({
          status: issue,
          browser,
          proxyPort,
          health,
          managedBrowser: managed,
          brokerVersion: BROKER_VERSION,
          instanceId: managed.instanceId,
          userActionRequired: 'proxy_restart',
        });
      }
      if (activeTasks > 0) {
        return makeResult({
          status: 'proxy_repair_blocked_active_tasks',
          browser,
          proxyPort,
          health,
          managedBrowser: managed,
          brokerVersion: BROKER_VERSION,
          instanceId: managed.instanceId,
          userActionRequired: 'wait_for_active_tasks',
        });
      }
      if (!(await stopVerifiedProxy(health, proxyPort, managed.instanceId))) {
        return makeResult({
          status: 'proxy_repair_unverified',
          browser,
          proxyPort,
          health,
          managedBrowser: managed,
          brokerVersion: BROKER_VERSION,
          instanceId: managed.instanceId,
          userActionRequired: 'inspect_proxy',
        });
      }
      health = null;
    } else {
      const capabilities = await httpGetJson(`${proxyUrl}/capabilities`);
      if (
        capabilities?.brokerVersion === BROKER_VERSION &&
        capabilities?.profileMode === 'managed' &&
        capabilityIssue(capabilities) === null
      ) {
        const result = await completeCapabilityHandshake({
          browser,
          proxyPort,
          health,
          reused: Boolean(managed.reused),
        });
        result.managedBrowser = managed;
        result.brokerVersion = BROKER_VERSION;
        result.instanceId = managed.instanceId;
        result.userActionRequired = null;
        return result;
      }
      if (opts.statusOnly) {
        return makeResult({
          status: 'proxy_capabilities_mismatch',
          browser,
          proxyPort,
          health,
          capabilities,
          managedBrowser: managed,
        });
      }
      const activeTasks = Number.isInteger(health.activeTasks) ? health.activeTasks : 0;
      if (activeTasks > 0) {
        return makeResult({
          status: 'proxy_repair_blocked_active_tasks',
          browser,
          proxyPort,
          health,
          capabilities,
          managedBrowser: managed,
          userActionRequired: 'wait_for_active_tasks',
        });
      }
      if (!(await stopVerifiedProxy(health, proxyPort, managed.instanceId))) {
        return makeResult({
          status: 'proxy_repair_unverified',
          browser,
          proxyPort,
          health,
          managedBrowser: managed,
        });
      }
      health = null;
    }
  }

  if (!health) {
    if (opts.statusOnly) {
      return makeResult({
        status: 'proxy_not_running',
        browser,
        proxyPort,
        managedBrowser: managed,
        userActionRequired: 'run_ensure',
      });
    }
    diagnostic(`proxy[edge]: connecting managed Edge on CDP ${managed.cdpPort}...`);
    try {
      startProxyDetached('edge', proxyPort, {
        WEB_ACCESS_EDGE_DEVTOOLS_PATH: path.join(managed.profilePath, 'DevToolsActivePort'),
        WEB_ACCESS_PROFILE_MODE: 'managed',
        WEB_ACCESS_MANAGED_INSTANCE_ID: managed.instanceId,
      }, [
        '--broker-profile-mode',
        'managed',
        '--managed-instance-id',
        managed.instanceId,
      ]);
    } catch (error) {
      return makeResult({
        status: 'start_failed',
        browser,
        proxyPort,
        error: error.message,
        managedBrowser: managed,
      });
    }
  }

  const deadline = Date.now() + 30_000;
  let lastHealth = health;
  while (Date.now() < deadline) {
    lastHealth = await httpGetJson(`${proxyUrl}/health`);
    if (lastHealth) {
      const issue = managedProxyIssue(lastHealth, managed, proxyPort);
      if (!issue) {
        const result = await completeCapabilityHandshake({
          browser,
          proxyPort,
          health: lastHealth,
          reused: Boolean(managed.reused),
        });
        result.managedBrowser = managed;
        result.brokerVersion = BROKER_VERSION;
        result.instanceId = managed.instanceId;
        result.userActionRequired = null;
        return result;
      }
      if (
        !looksLikeWebAccessProxy(lastHealth) ||
        issue === 'proxy_protocol_mismatch' ||
        issue === 'proxy_version_mismatch' ||
        issue === 'proxy_mode_mismatch' ||
        issue === 'proxy_browser_mismatch'
      ) {
        return makeResult({
          status: issue,
          browser,
          proxyPort,
          health: lastHealth,
          managedBrowser: managed,
          brokerVersion: BROKER_VERSION,
          instanceId: managed.instanceId,
        });
      }
    }
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  return makeResult({
    status: 'proxy_timeout',
    browser,
    proxyPort,
    health: lastHealth,
    managedBrowser: managed,
    brokerVersion: BROKER_VERSION,
    instanceId: managed.instanceId,
    logFile: proxyLogPath('edge', proxyPort),
  });
}

async function ensureManagedBroker(opts) {
  const browser = {
    id: 'edge',
    label: 'Microsoft Edge',
    source: 'managed',
    profileMode: 'managed',
  };
  const proxyPort = getProxyPort('edge', {
    diagnostic,
    readOnly: opts.statusOnly,
  });
  const proxyUrl = `http://127.0.0.1:${proxyPort}`;
  const initialManaged = await statusManagedEdge();
  const initialHealthResponse = await httpGetJsonResponse(`${proxyUrl}/health`);
  const initialHealth = initialHealthResponse.ok ? initialHealthResponse.value : null;

  if (initialManaged.ready && initialHealth) {
    const issue = managedProxyIssue(initialHealth, initialManaged, proxyPort);
    if (!issue) {
      const capabilities = await httpGetJson(`${proxyUrl}/capabilities`);
      if (
        capabilities?.brokerVersion === BROKER_VERSION &&
        capabilities?.profileMode === 'managed' &&
        capabilityIssue(capabilities) === null
      ) {
        const result = await completeCapabilityHandshake({
          browser,
          proxyPort,
          health: initialHealth,
          reused: true,
        });
        result.managedBrowser = initialManaged;
        result.brokerVersion = BROKER_VERSION;
        result.instanceId = initialManaged.instanceId;
        result.userActionRequired = null;
        return result;
      }
    }
  }

  if (opts.statusOnly) {
    if (!initialManaged.ready) {
      return makeResult({
        status: 'managed_browser_start_required',
        browser,
        proxyPort,
        managedBrowser: initialManaged,
        brokerVersion: BROKER_VERSION,
        userActionRequired: 'start_managed_browser',
      });
    }
    return ensureManagedProxy(initialManaged, opts);
  }

  const activeTasks = Number.isInteger(initialHealth?.activeTasks) ? initialHealth.activeTasks : 0;
  if (
    activeTasks > 0 &&
    initialHealth &&
    (initialHealth.profileMode !== 'managed' ||
      initialHealth.brokerVersion !== BROKER_VERSION ||
      initialHealth.managedInstanceId !== initialManaged.instanceId)
  ) {
    return makeResult({
      status: 'proxy_repair_blocked_active_tasks',
      browser,
      proxyPort,
      health: initialHealth,
      managedBrowser: initialManaged,
      brokerVersion: BROKER_VERSION,
      instanceId: initialManaged.instanceId,
      userActionRequired: 'wait_for_active_tasks',
    });
  }

  const release = await acquireManagedLock(managedBrowserPaths());
  try {
    const latestHealth = await httpGetJson(`${proxyUrl}/health`);
    const latestActiveTasks = Number.isInteger(latestHealth?.activeTasks)
      ? latestHealth.activeTasks
      : 0;
    const managed = await ensureManagedEdge({
      statusOnly: false,
      allowRestart: latestActiveTasks === 0,
      lockHeld: true,
      diagnostics: diagnostic,
    });
    if (!managed.ready) {
      return makeResult({
        status: 'browser_not_running',
        browser,
        proxyPort,
        managedBrowser: managed,
        brokerVersion: BROKER_VERSION,
        userActionRequired: 'start_managed_browser',
      });
    }
    return ensureManagedProxy(managed, opts);
  } finally {
    release();
  }
}

async function ensureProxy(browserId, proxyPort, { statusOnly = false } = {}) {
  const browser = typeof browserId === 'string'
    ? knownBrowsers().find((item) => item.id === browserId) || { id: browserId, label: browserId }
    : browserId;
  browserId = browser.id;
  const proxyUrl = `http://127.0.0.1:${proxyPort}`;
  const healthUrl = `${proxyUrl}/health`;
  const initialHealth = await httpGetJson(healthUrl);
  let reused = false;
  let lastHealth = initialHealth;

  if (initialHealth && looksLikeWebAccessProxy(initialHealth)) {
    const actualProtocolVersion = protocolVersionOf(initialHealth);
    if (actualProtocolVersion !== EXPECTED_PROTOCOL_VERSION) {
      diagnostic(
        `proxy[${browserId}]: protocol_mismatch ` +
        `(实际 ${actualProtocolVersion ?? 'missing'}，期望 ${EXPECTED_PROTOCOL_VERSION}，${proxyUrl})`
      );
      diagnostic('  不会停止现有 Proxy；请显式重启 Proxy 后重试。');
      return makeResult({
        status: 'protocol_mismatch',
        browser,
        proxyPort,
        health: initialHealth,
        expectedProtocolVersion: EXPECTED_PROTOCOL_VERSION,
        existing: true,
      });
    }
    if (!isWebAccessProxy(initialHealth)) {
      diagnostic(`proxy[${browserId}]: Proxy 健康状态异常 (${proxyUrl})`);
      diagnostic('  不会停止现有 Proxy；请检查其日志后显式处理。');
      return makeResult({
        status: 'proxy_unhealthy',
        browser,
        proxyPort,
        health: initialHealth,
        existing: true,
      });
    }

    reused = true;
    const runningId = healthBrowserId(initialHealth);
    const runningLabel = initialHealth.browser?.label || runningId || 'unknown';

    // Migration: a proxy left over from the old managed default occupies the
    // canonical port. Only a proxy verified as this machine's own managed
    // instance may be replaced, and never while it owns active tasks.
    if (
      initialHealth.profileMode === 'managed' &&
      initialHealth.managedProfile === true &&
      initialHealth.requestedBrowser === 'edge' &&
      initialHealth.browser?.id === 'edge' &&
      initialHealth.proxyPort === proxyPort
    ) {
      const activeTasks = Number.isInteger(initialHealth.activeTasks) ? initialHealth.activeTasks : 0;
      if (statusOnly) {
        return makeResult({
          status: activeTasks > 0 ? 'managed_proxy_blocks_existing_mode' : 'managed_proxy_migration_available',
          browser,
          proxyPort,
          health: initialHealth,
          userActionRequired: activeTasks > 0 ? 'wait_for_active_tasks' : 'run_ensure',
          existing: true,
        });
      }
      if (activeTasks > 0 && Number(initialHealth.sessions || 0) === 0 && Number(initialHealth.managedTabs || 0) === 0) {
        diagnostic('proxy[edge]: 旧 managed Proxy 只有遗留 activeTasks 计数、没有 session/tab；按安全回收处理');
        if (await stopVerifiedProxy(initialHealth, proxyPort, initialHealth.managedInstanceId)) {
          reused = false;
          lastHealth = null;
          return ensureProxy(browser, proxyPort, { statusOnly });
        }
      }
      if (activeTasks > 0) {
        diagnostic(`proxy[${browserId}]: managed 模式 Proxy 仍有 ${activeTasks} 个活动任务，暂不迁移`);
        return makeResult({
          status: 'proxy_repair_blocked_active_tasks',
          browser,
          proxyPort,
          health: initialHealth,
          userActionRequired: 'wait_for_active_tasks',
          existing: true,
        });
      }
      diagnostic(`proxy[${browserId}]: 迁移旧 managed 默认 → existing（停止经验证的旧 Proxy 后重启）`);
      if (await stopVerifiedProxy(initialHealth, proxyPort, initialHealth.managedInstanceId)) {
        reused = false;
        lastHealth = null;
        return ensureProxy(browser, proxyPort, { statusOnly });
      }
      diagnostic('  旧 Proxy 未被确认为本机受管实例，不停止；请显式处理。');
      return makeResult({
        status: 'proxy_repair_unverified',
        browser,
        proxyPort,
        health: initialHealth,
        userActionRequired: 'inspect_proxy',
        existing: true,
      });
    }

    const identityIssue = browserIdentityIssue(initialHealth, browser);
    if (identityIssue) {
      diagnostic(`proxy[${browserId}]: 端口 ${proxyPort} 已连接 ${runningLabel}，与专用浏览器不一致`);
      diagnostic('  不会停止现有 Proxy；请为两个浏览器配置不同端口。');
      return makeResult({
        status: 'browser_proxy_mismatch',
        browser,
        proxyPort,
        health: initialHealth,
        actualBrowserId: runningId,
        actualRequestedBrowserId: initialHealth.requestedBrowser || null,
        actualCdpPort: Number.isInteger(initialHealth.chromePort) ? initialHealth.chromePort : null,
        identityIssue,
        existing: true,
      });
    }
    const portIssue = proxyPortIssue(initialHealth, proxyPort);
    if (portIssue) {
      diagnostic(`proxy[${browserId}]: 端口身份不一致 (${portIssue})`);
      return makeResult({
        status: 'browser_proxy_mismatch',
        browser,
        proxyPort,
        health: initialHealth,
        identityIssue: portIssue,
        existing: true,
      });
    }
    if (initialHealth.connected) {
      return completeCapabilityHandshake({
        browser,
        proxyPort,
        health: initialHealth,
        reused: true,
      });
    }
    if (statusOnly) {
      return makeResult({
        status: 'stale_proxy',
        browser,
        proxyPort,
        health: initialHealth,
        reused: true,
        userActionRequired: 'run_ensure',
      });
    }
    diagnostic(`proxy[${browserId}]: 已在 ${proxyUrl} 启动，等待浏览器连接...`);
  } else if (initialHealth) {
    diagnostic(`proxy[${browserId}]: 端口 ${proxyPort} 返回了非 web-access 服务`);
    diagnostic('  不会停止或覆盖现有服务；请检查端口配置。');
    return makeResult({
      status: 'port_conflict',
      browser,
      proxyPort,
      health: initialHealth,
      existing: true,
    });
  } else {
    if (statusOnly) {
      return makeResult({
        status: 'proxy_not_running',
        browser,
        proxyPort,
        userActionRequired: 'run_ensure',
      });
    }
    diagnostic(`proxy[${browserId}]: connecting (${proxyUrl})...`);
    try {
      startProxyDetached(browserId, proxyPort, { WEB_ACCESS_PROFILE_MODE: 'existing' });
    } catch (error) {
      diagnosticError(`proxy[${browserId}]: 启动失败 — ${error.message}`);
      return makeResult({
        status: 'start_failed',
        browser,
        proxyPort,
        error: error.message,
      });
    }
    await new Promise((resolve) => setTimeout(resolve, 250));
  }

  for (let i = 1; i <= 20; i++) {
    const health = await httpGetJson(healthUrl);
    if (health) {
      lastHealth = health;
      if (!looksLikeWebAccessProxy(health)) {
        diagnostic(`proxy[${browserId}]: 端口 ${proxyPort} 被非 web-access 服务占用`);
        diagnostic('  不会停止或覆盖现有服务；请检查端口配置。');
        return makeResult({
          status: 'port_conflict',
          browser,
          proxyPort,
          health,
          existing: true,
        });
      }
      const actualProtocolVersion = protocolVersionOf(health);
      if (actualProtocolVersion !== EXPECTED_PROTOCOL_VERSION) {
        diagnostic(
          `proxy[${browserId}]: protocol_mismatch ` +
          `(实际 ${actualProtocolVersion ?? 'missing'}，期望 ${EXPECTED_PROTOCOL_VERSION}，${proxyUrl})`
        );
        diagnostic('  不会停止现有 Proxy；请显式重启 Proxy 后重试。');
        return makeResult({
          status: 'protocol_mismatch',
          browser,
          proxyPort,
          health,
          expectedProtocolVersion: EXPECTED_PROTOCOL_VERSION,
          existing: true,
        });
      }
      if (!isWebAccessProxy(health)) {
        diagnostic(`proxy[${browserId}]: Proxy 健康状态异常 (${proxyUrl})`);
        return makeResult({
          status: 'proxy_unhealthy',
          browser,
          proxyPort,
          health,
          existing: true,
        });
      }
      const runningId = healthBrowserId(health);
      const identityIssue = browserIdentityIssue(health, browser);
      if (identityIssue) {
        diagnostic(`proxy[${browserId}]: 连接结果不一致，实际为 ${runningId}`);
        return makeResult({
          status: 'browser_proxy_mismatch',
          browser,
          proxyPort,
          health,
          actualBrowserId: runningId,
          actualRequestedBrowserId: health.requestedBrowser || null,
          actualCdpPort: Number.isInteger(health.chromePort) ? health.chromePort : null,
          identityIssue,
          existing: true,
        });
      }
      const portIssue = proxyPortIssue(health, proxyPort);
      if (portIssue) {
        return makeResult({
          status: 'browser_proxy_mismatch',
          browser,
          proxyPort,
          health,
          identityIssue: portIssue,
          existing: true,
        });
      }
      if (health.connected) {
        return completeCapabilityHandshake({ browser, proxyPort, health, reused });
      }
    }
    if (i === 1) {
      diagnostic(`proxy[${browserId}]: 浏览器可能有授权弹窗，请点击「允许」后等待连接...`);
    }
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }

  const logFile = proxyLogPath(browserId, proxyPort);
  diagnostic(`proxy[${browserId}]: 连接超时，请检查浏览器调试设置`);
  diagnostic(`  日志：${logFile}`);
  return makeResult({
    status: reused ? 'stale_proxy' : 'timeout',
    browser,
    proxyPort,
    health: lastHealth,
    logFile,
  });
}

function printAvailableHint(detected) {
  const detectedIds = new Set(detected.map((browser) => browser.id));
  const configurable = knownBrowsers().filter((browser) => !detectedIds.has(browser.id));
  if (detected.length) {
    diagnostic(`  已开启远程调试：${detected.map((browser) => `${browser.label} (${browser.id}, port ${browser.port})`).join('、')}`);
  }
  if (configurable.length) {
    diagnostic(`  其他可配置：${configurable.map((browser) => `${browser.label} (${browser.id})`).join('、')}`);
  }
}

async function resolveAndReport(override, opts = {}) {
  const result = await selectBrowser(override);

  switch (result.kind) {
    case 'ok': {
      const proxyPort = getProxyPort(result.browser.id, {
        diagnostic,
        readOnly: opts.statusOnly,
      });
      const sourceTag = result.source === 'override' ? '[--browser 指定]' : '[config.env 偏好]';
      diagnostic(`browser: ok (${result.browser.label}, CDP ${result.browser.port} -> Proxy ${proxyPort}) ${sourceTag}`);
      return { proceed: true, browser: result.browser, proxyPort };
    }

    case 'ambiguous': {
      diagnostic('browser: needs decision — 用户尚未在 config.env 设置偏好');
      printAvailableHint(result.detected);
      diagnostic('  请设置 WEB_ACCESS_BROWSER=edge（推荐）或 chrome');
      diagnostic('  若仅本次使用，可重跑：node check-deps.mjs --browser <edge|chrome>');
      return {
        proceed: false,
        result: makeResult({ status: 'browser_ambiguous', exitCode: 2 }),
      };
    }

    case 'mismatch': {
      const expected = result.override || result.configured;
      const expectedBrowser = knownBrowsers().find((browser) => browser.id === expected) || {
        id: expected,
        label: expected,
      };
      const expectedLabel = expectedBrowser.label;
      const sourceDesc = result.source === 'override' ? '本次指定' : '默认偏好';
      diagnostic(`browser: error — ${sourceDesc}的浏览器是 "${expected}" (${expectedLabel})，但没连上`);
      diagnostic('  Agent 处理顺序：');
      diagnostic(`    1. 先打开 ${expectedLabel}，再重新运行 node check-deps.mjs${override ? ` --browser ${expected}` : ''}`);
      diagnostic(`    2. 若仍失败，在 ${expected}://inspect/#remote-debugging 勾选 "Allow remote debugging for this browser instance"`);
      printAvailableHint(result.detected);
      let proxyPort = null;
      try {
        proxyPort = getProxyPort(expected, {
          diagnostic,
          readOnly: opts.statusOnly,
        });
      } catch {}
      return {
        proceed: false,
        result: makeResult({
          status: 'browser_mismatch',
          browser: expectedBrowser,
          proxyPort,
        }),
      };
    }

    case 'empty': {
      diagnostic('browser: 未连接 — 没有任何浏览器打开远程调试开关');
      diagnostic(`  支持的浏览器：${knownBrowsers().map((browser) => browser.label).join('、')}`);
      diagnostic('  打开 edge://inspect/#remote-debugging 或 chrome://inspect/#remote-debugging，并勾选允许');
      return {
        proceed: false,
        result: makeResult({ status: 'browser_unavailable' }),
      };
    }
  }
}

async function ensureOneBrowser(override, opts = {}) {
  const resolved = await resolveAndReport(override, opts);
  if (!resolved.proceed) return resolved.result;
  return ensureProxy(resolved.browser, resolved.proxyPort, { statusOnly: opts.statusOnly });
}

async function applyControlProbe(results, opts) {
  if (!opts.probe) {
    for (const result of results) result.controlProbe = { passed: null, skipped: true };
    return results;
  }
  for (const result of results) {
    if (!result.ok || !result.ready || !result.proxy?.port) continue;
    const probe = await probeBrowserControl(result.proxy.port);
    result.controlProbe = probe;
    if (!probe.passed) {
      result.ok = false;
      result.ready = false;
      result.status = probe.code;
      result.exitCode = 1;
      result.userActionRequired = 'browser_control';
    }
  }
  return results;
}

function listSitePatterns() {
  const patternsDir = path.join(ROOT, 'references', 'site-patterns');
  try {
    const sites = fs.readdirSync(patternsDir)
      .filter((file) => file.endsWith('.md'))
      .map((file) => file.replace(/\.md$/, ''));
    if (sites.length) diagnostic(`\nsite-patterns: ${sites.join(', ')}`);
  } catch {}
}

function summaryStatus(results, ok, override = null) {
  if (override) return override;
  if (ok) return 'ready';
  if (results.some((result) => result.status === 'protocol_mismatch')) {
    return 'protocol_mismatch';
  }
  if (results.length === 1) return results[0].status;
  return 'failed';
}

function jsonSummary(opts, results, node, statusOverride = null) {
  const ok = results.length > 0 && results.every((result) => result.ok);
  return {
    ok,
    status: summaryStatus(results, ok, statusOverride),
    mode: opts?.all ? 'all' : 'single',
    browserMode: opts?.mode || null,
    brokerVersion: BROKER_VERSION,
    protocolVersion: EXPECTED_PROTOCOL_VERSION,
    expectedProtocolVersion: EXPECTED_PROTOCOL_VERSION,
    ready: ok && results.every((result) => result.ready),
    reused: ok && results.every((result) => result.reused),
    node: node || null,
    cdpPort: results.length === 1 ? (results[0].browser?.cdpPort || results[0].cdp?.port || null) : null,
    proxyUrl: results.length === 1 ? (results[0].proxy?.url || null) : null,
    browser: results.length === 1 ? results[0].browser || null : null,
    controlProbe: results.length === 1 ? results[0].controlProbe || null : null,
    results,
  };
}

function finish(opts, results, node, exitCode, statusOverride = null) {
  if (jsonMode) emitJson(jsonSummary(opts, results, node, statusOverride));
  process.exitCode = exitCode;
}

async function main() {
  let opts;
  try {
    opts = parseArgs(process.argv.slice(2));
    jsonMode = opts.json;
  } catch (error) {
    diagnosticError(`参数错误：${error.message}`);
    finish(null, [], null, 2, 'invalid_arguments');
    return;
  }

  let configInfo;
  try {
    configInfo = opts.statusOnly
      ? inspectCanonicalConfig(diagnostic)
      : ensureCanonicalConfig(diagnostic);
  } catch (error) {
    const status = error instanceof RuntimeConfigError ? error.code : 'config_error';
    diagnosticError(`config: error — ${error.message}`);
    finish(opts, [], null, error?.exitCode || 1, status);
    return;
  }
  const node = checkNode();
  opts.mode = opts.mode || configInfo.config.WEB_ACCESS_BROWSER_MODE || 'existing';

  let results;
  if (opts.mode === 'managed') {
    const browserId = opts.browser || configInfo.config.WEB_ACCESS_BROWSER;
    if (opts.all || browserId !== 'edge') {
      finish(opts, [], node, 2, 'managed_mode_requires_edge');
      return;
    }
    opts.browser = 'edge';
    try {
      const proxyPort = getProxyPort('edge', {
        diagnostic,
        readOnly: opts.statusOnly,
      });
      results = [await ensureManagedBroker(opts)];
    } catch (error) {
      const status = error instanceof ManagedBrowserError ? error.code : 'managed_browser_error';
      results = [makeResult({
        status,
        browser: { id: 'edge', label: 'Microsoft Edge', source: 'managed' },
        error: error.message,
        managedBrowser: error instanceof ManagedBrowserError ? error.details : null,
        brokerVersion: BROKER_VERSION,
      })];
    }
  } else if (opts.all) {
    try {
      const edgePort = getProxyPort('edge', {
        diagnostic,
        readOnly: opts.statusOnly,
      });
      const chromePort = getProxyPort('chrome', {
        diagnostic,
        readOnly: opts.statusOnly,
      });
      if (edgePort === chromePort) {
        throw new Error(`Edge 与 Chrome Proxy 端口不能相同（当前均为 ${edgePort}）`);
      }
    } catch (error) {
      diagnosticError(`config: error — ${error.message}`);
      finish(opts, [], node, 1, 'config_error');
      return;
    }
    results = await Promise.all(PERSISTENT_BROWSERS.map((browserId) => ensureOneBrowser(browserId, opts)));
  } else {
    results = [await ensureOneBrowser(opts.browser, opts)];
  }

  results = await applyControlProbe(results, opts);

  const failed = results.filter((result) => !result.ok);
  if (failed.length) {
    const exitCode = failed.some((result) => result.exitCode === 2) ? 2 : 1;
    finish(opts, results, node, exitCode);
    return;
  }

  if (!jsonMode) {
    for (const result of results) {
      diagnostic(`proxy-url[${result.browser.id}]: ${result.proxy.url}`);
    }
    listSitePatterns();
  }
  finish(opts, results, node, 0);
}

if (invokedAsMain(import.meta.url, process.argv[1])) {
  try {
    await main();
  } catch (error) {
    diagnosticError(`check-deps: unexpected error — ${error.message}`);
    const status = error instanceof RuntimeConfigError ? error.code : 'internal_error';
    finish(null, [makeResult({ status, error: error.message, exitCode: error?.exitCode || 1 })], null, error?.exitCode || 1, status);
  }
}
