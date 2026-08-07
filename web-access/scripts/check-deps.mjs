#!/usr/bin/env node
// 环境检查 + 确保浏览器专用 CDP Proxy 就绪
//
// 用法：
//   node check-deps.mjs                  使用 config.env 偏好（模板默认 Edge）
//   node check-deps.mjs --browser chrome 使用 Chrome 专用 Proxy
//   node check-deps.mjs --all            同时确保 Edge 和 Chrome Proxy 就绪
//   node check-deps.mjs --json           stdout 仅输出机器可读 JSON

import { spawn } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { getProxyPort, knownBrowsers, selectBrowser } from './browser-discovery.mjs';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const PROXY_SCRIPT = path.join(ROOT, 'scripts', 'cdp-proxy.mjs');
const CONFIG_PATH = path.join(ROOT, 'config.env');
const CONFIG_TEMPLATE = path.join(ROOT, 'templates', 'config.env.template');
const PERSISTENT_BROWSERS = ['edge', 'chrome'];
const EXPECTED_PROTOCOL_VERSION = 2;
const MAX_JSON_RESPONSE_BYTES = 64 * 1024;

let jsonMode = process.argv.slice(2).includes('--json');
let jsonWritten = false;

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
  const opts = { browser: null, all: false, json: false };
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
    }
  }

  if (opts.all && opts.browser) {
    throw new Error('--all 与 --browser 不能同时使用');
  }
  if (opts.browser && !PERSISTENT_BROWSERS.includes(opts.browser)) {
    throw new Error(`--browser 仅支持 ${PERSISTENT_BROWSERS.join(' / ')}`);
  }
  return opts;
}

function ensureConfigExists() {
  if (fs.existsSync(CONFIG_PATH)) return;
  try {
    fs.copyFileSync(CONFIG_TEMPLATE, CONFIG_PATH);
    diagnostic(`config: 已从模板创建 ${CONFIG_PATH}`);
  } catch {
    // 模板不存在或拷贝失败不阻塞，browser-discovery 会返回明确状态。
  }
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
  if (!response.body) return Buffer.alloc(0);
  const reader = response.body.getReader();
  const chunks = [];
  let total = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      total += value.byteLength;
      if (total > maxBytes) {
        await reader.cancel();
        throw new Error('response_too_large');
      }
      chunks.push(Buffer.from(value));
    }
  } finally {
    reader.releaseLock();
  }
  return Buffer.concat(chunks, total);
}

function isJsonContentType(value) {
  const mediaType = String(value || '').split(';', 1)[0].trim().toLowerCase();
  return mediaType === 'application/json' || mediaType.endsWith('+json');
}

async function httpGetJsonResponse(url, timeoutMs = 3000, maxBytes = MAX_JSON_RESPONSE_BYTES) {
  try {
    const response = await fetch(url, { signal: AbortSignal.timeout(timeoutMs) });
    const contentLength = Number(response.headers.get('content-length'));
    if (Number.isFinite(contentLength) && contentLength > maxBytes) {
      await response.body?.cancel();
      return { ok: false, status: response.status, reason: 'response_too_large', value: null };
    }
    if (!response.ok) {
      await response.body?.cancel();
      return { ok: false, status: response.status, reason: 'http_status', value: null };
    }
    if (!isJsonContentType(response.headers.get('content-type'))) {
      await response.body?.cancel();
      return { ok: false, status: response.status, reason: 'content_type', value: null };
    }
    const raw = await readLimitedBody(response, maxBytes);
    try {
      return { ok: true, status: response.status, reason: null, value: JSON.parse(raw.toString('utf8')) };
    } catch {
      return { ok: false, status: response.status, reason: 'invalid_json', value: null };
    }
  } catch (error) {
    return { ok: false, status: null, reason: error.message || 'request_failed', value: null };
  }
}

async function httpGetJson(url, timeoutMs = 3000) {
  const response = await httpGetJsonResponse(url, timeoutMs);
  return response.ok ? response.value : null;
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
    capabilities,
    exitCode,
    ...extra,
  };
}

function proxyLogPath(browserId, proxyPort) {
  return path.join(os.tmpdir(), `web-access-${browserId}-${proxyPort}.log`);
}

function startProxyDetached(browserId, proxyPort) {
  const logFile = proxyLogPath(browserId, proxyPort);
  const logFd = fs.openSync(logFile, 'a');
  try {
    const child = spawn(process.execPath, [PROXY_SCRIPT, '--browser', browserId], {
      detached: true,
      stdio: ['ignore', logFd, logFd],
      env: { ...process.env, CDP_PROXY_PORT: String(proxyPort) },
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
  if (actualProtocolVersion !== EXPECTED_PROTOCOL_VERSION) {
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

async function ensureProxy(browserId, proxyPort) {
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
    if (initialHealth.connected) {
      return completeCapabilityHandshake({
        browser,
        proxyPort,
        health: initialHealth,
        reused: true,
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
    diagnostic(`proxy[${browserId}]: connecting (${proxyUrl})...`);
    try {
      startProxyDetached(browserId, proxyPort);
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
    status: 'timeout',
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

async function resolveAndReport(override) {
  const result = await selectBrowser(override);

  switch (result.kind) {
    case 'ok': {
      const proxyPort = getProxyPort(result.browser.id);
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
      try { proxyPort = getProxyPort(expected); } catch {}
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

async function ensureOneBrowser(override) {
  const resolved = await resolveAndReport(override);
  if (!resolved.proceed) return resolved.result;
  return ensureProxy(resolved.browser, resolved.proxyPort);
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
    protocolVersion: EXPECTED_PROTOCOL_VERSION,
    expectedProtocolVersion: EXPECTED_PROTOCOL_VERSION,
    ready: ok && results.every((result) => result.ready),
    reused: ok && results.every((result) => result.reused),
    node: node || null,
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

  ensureConfigExists();
  const node = checkNode();

  let results;
  if (opts.all) {
    try {
      const edgePort = getProxyPort('edge');
      const chromePort = getProxyPort('chrome');
      if (edgePort === chromePort) {
        throw new Error(`Edge 与 Chrome Proxy 端口不能相同（当前均为 ${edgePort}）`);
      }
    } catch (error) {
      diagnosticError(`config: error — ${error.message}`);
      finish(opts, [], node, 1, 'config_error');
      return;
    }
    results = await Promise.all(PERSISTENT_BROWSERS.map((browserId) => ensureOneBrowser(browserId)));
  } else {
    results = [await ensureOneBrowser(opts.browser)];
  }

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

try {
  await main();
} catch (error) {
  diagnosticError(`check-deps: unexpected error — ${error.message}`);
  finish(null, [makeResult({ status: 'internal_error', error: error.message })], null, 1, 'internal_error');
}
