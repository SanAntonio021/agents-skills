#!/usr/bin/env node
// 环境检查 + 确保浏览器专用 CDP Proxy 就绪
//
// 用法：
//   node check-deps.mjs                  使用 config.env 偏好（模板默认 Edge）
//   node check-deps.mjs --browser chrome 使用 Chrome 专用 Proxy
//   node check-deps.mjs --all            同时确保 Edge 和 Chrome Proxy 就绪

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

function parseArgs(argv) {
  const opts = { browser: null, all: false };
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === '--browser' && argv[i + 1]) {
      opts.browser = argv[i + 1];
      i++;
    } else if (argv[i].startsWith('--browser=')) {
      opts.browser = argv[i].slice('--browser='.length);
    } else if (argv[i] === '--all') {
      opts.all = true;
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
    console.log(`config: 已从模板创建 ${CONFIG_PATH}`);
  } catch {
    // 模板不存在或拷贝失败不阻塞，browser-discovery 会返回明确状态。
  }
}

function checkNode() {
  const major = Number(process.versions.node.split('.')[0]);
  const version = `v${process.versions.node}`;
  if (major >= 22) console.log(`node: ok (${version})`);
  else console.log(`node: warn (${version}, 建议升级到 22+)`);
}

function httpGetJson(url, timeoutMs = 3000) {
  return fetch(url, { signal: AbortSignal.timeout(timeoutMs) })
    .then(async (res) => {
      try { return JSON.parse(await res.text()); }
      catch { return null; }
    })
    .catch(() => null);
}

function isWebAccessProxy(health) {
  if (health?.status !== 'ok') return false;
  if (health.service === 'web-access-cdp-proxy') return true;
  return Object.hasOwn(health, 'sessions') &&
    Object.hasOwn(health, 'managedTabs') &&
    Object.hasOwn(health, 'chromePort');
}

function healthBrowserId(health) {
  return health?.browser?.id || health?.requestedBrowser || null;
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

async function ensureProxy(browserId, proxyPort) {
  const proxyUrl = `http://127.0.0.1:${proxyPort}`;
  const healthUrl = `${proxyUrl}/health`;
  const targetsUrl = `${proxyUrl}/targets`;
  const initialHealth = await httpGetJson(healthUrl);

  if (isWebAccessProxy(initialHealth)) {
    const runningId = healthBrowserId(initialHealth);
    const runningLabel = initialHealth.browser?.label || runningId || 'unknown';
    if (runningId && runningId !== 'unknown' && runningId !== browserId) {
      console.log(`proxy[${browserId}]: 端口 ${proxyPort} 已连接 ${runningLabel}，与专用浏览器不一致`);
      console.log('  不会停止现有 Proxy；请为两个浏览器配置不同端口。');
      return { ok: false, exitCode: 1, browserId, proxyPort, proxyUrl };
    }
    if (initialHealth.connected) {
      console.log(`proxy[${browserId}]: ready (${runningLabel}, ${proxyUrl})`);
      return { ok: true, browserId, proxyPort, proxyUrl, reused: true };
    }
    console.log(`proxy[${browserId}]: 已在 ${proxyUrl} 启动，等待浏览器连接...`);
  } else {
    console.log(`proxy[${browserId}]: connecting (${proxyUrl})...`);
    startProxyDetached(browserId, proxyPort);
    await new Promise((resolve) => setTimeout(resolve, 250));
  }

  for (let i = 1; i <= 20; i++) {
    const targets = await httpGetJson(targetsUrl, 3000);
    if (Array.isArray(targets)) {
      const health = await httpGetJson(healthUrl);
      const runningId = healthBrowserId(health);
      if (runningId && runningId !== 'unknown' && runningId !== browserId) {
        console.log(`proxy[${browserId}]: 连接结果不一致，实际为 ${runningId}`);
        return { ok: false, exitCode: 1, browserId, proxyPort, proxyUrl };
      }
      const label = health?.browser?.label || browserId;
      console.log(`proxy[${browserId}]: ready (${label}, ${proxyUrl})`);
      return { ok: true, browserId, proxyPort, proxyUrl, reused: false };
    }
    if (i === 1) {
      console.log(`proxy[${browserId}]: 浏览器可能有授权弹窗，请点击「允许」后等待连接...`);
    }
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }

  const logFile = proxyLogPath(browserId, proxyPort);
  console.log(`proxy[${browserId}]: 连接超时，请检查浏览器调试设置`);
  console.log(`  日志：${logFile}`);
  return { ok: false, exitCode: 1, browserId, proxyPort, proxyUrl, logFile };
}

function printAvailableHint(detected) {
  const detectedIds = new Set(detected.map((browser) => browser.id));
  const configurable = knownBrowsers().filter((browser) => !detectedIds.has(browser.id));
  if (detected.length) {
    console.log(`  已开启远程调试：${detected.map((browser) => `${browser.label} (${browser.id}, port ${browser.port})`).join('、')}`);
  }
  if (configurable.length) {
    console.log(`  其他可配置：${configurable.map((browser) => `${browser.label} (${browser.id})`).join('、')}`);
  }
}

async function resolveAndReport(override) {
  const result = await selectBrowser(override);

  switch (result.kind) {
    case 'ok': {
      const proxyPort = getProxyPort(result.browser.id);
      const sourceTag = result.source === 'override' ? '[--browser 指定]' : '[config.env 偏好]';
      console.log(`browser: ok (${result.browser.label}, CDP ${result.browser.port} -> Proxy ${proxyPort}) ${sourceTag}`);
      return { proceed: true, browserId: result.browser.id, proxyPort };
    }

    case 'ambiguous': {
      console.log('browser: needs decision — 用户尚未在 config.env 设置偏好');
      printAvailableHint(result.detected);
      console.log('  请设置 WEB_ACCESS_BROWSER=edge（推荐）或 chrome');
      console.log('  若仅本次使用，可重跑：node check-deps.mjs --browser <edge|chrome>');
      return { proceed: false, exitCode: 2 };
    }

    case 'mismatch': {
      const expected = result.override || result.configured;
      const expectedLabel = knownBrowsers().find((browser) => browser.id === expected)?.label || expected;
      const sourceDesc = result.source === 'override' ? '本次指定' : '默认偏好';
      console.log(`browser: error — ${sourceDesc}的浏览器是 "${expected}" (${expectedLabel})，但没连上`);
      console.log('  Agent 处理顺序：');
      console.log(`    1. 先打开 ${expectedLabel}，再重新运行 node check-deps.mjs${override ? ` --browser ${expected}` : ''}`);
      console.log(`    2. 若仍失败，在 ${expected}://inspect/#remote-debugging 勾选 "Allow remote debugging for this browser instance"`);
      printAvailableHint(result.detected);
      return { proceed: false, exitCode: 1 };
    }

    case 'empty': {
      console.log('browser: 未连接 — 没有任何浏览器打开远程调试开关');
      console.log(`  支持的浏览器：${knownBrowsers().map((browser) => browser.label).join('、')}`);
      console.log('  打开 edge://inspect/#remote-debugging 或 chrome://inspect/#remote-debugging，并勾选允许');
      return { proceed: false, exitCode: 1 };
    }
  }
}

async function ensureOneBrowser(override) {
  const resolved = await resolveAndReport(override);
  if (!resolved.proceed) return { ok: false, exitCode: resolved.exitCode || 1, browserId: override };
  return ensureProxy(resolved.browserId, resolved.proxyPort);
}

function listSitePatterns() {
  const patternsDir = path.join(ROOT, 'references', 'site-patterns');
  try {
    const sites = fs.readdirSync(patternsDir)
      .filter((file) => file.endsWith('.md'))
      .map((file) => file.replace(/\.md$/, ''));
    if (sites.length) console.log(`\nsite-patterns: ${sites.join(', ')}`);
  } catch {}
}

async function main() {
  let opts;
  try {
    opts = parseArgs(process.argv.slice(2));
  } catch (error) {
    console.error(`参数错误：${error.message}`);
    process.exitCode = 2;
    return;
  }

  ensureConfigExists();
  checkNode();

  let results;
  if (opts.all) {
    try {
      const edgePort = getProxyPort('edge');
      const chromePort = getProxyPort('chrome');
      if (edgePort === chromePort) {
        throw new Error(`Edge 与 Chrome Proxy 端口不能相同（当前均为 ${edgePort}）`);
      }
    } catch (error) {
      console.error(`config: error — ${error.message}`);
      process.exitCode = 1;
      return;
    }
    results = await Promise.all(PERSISTENT_BROWSERS.map((browserId) => ensureOneBrowser(browserId)));
  } else {
    results = [await ensureOneBrowser(opts.browser)];
  }

  const failed = results.filter((result) => !result.ok);
  if (failed.length) {
    process.exitCode = failed.some((result) => result.exitCode === 2) ? 2 : 1;
    return;
  }

  for (const result of results) {
    console.log(`proxy-url[${result.browserId}]: ${result.proxyUrl}`);
  }
  listSitePatterns();
}

await main();
