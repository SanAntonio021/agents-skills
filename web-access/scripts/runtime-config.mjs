import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

const DEFAULTS = Object.freeze({
  WEB_ACCESS_BROWSER: 'edge',
  WEB_ACCESS_EDGE_PORT: '3456',
  WEB_ACCESS_CHROME_PORT: '3457',
});

const DEFAULT_CONFIG = `# web-access canonical user configuration\n` +
  `# Production copies all read this file. Edge and Chrome ports must stay distinct.\n` +
  `WEB_ACCESS_BROWSER=${DEFAULTS.WEB_ACCESS_BROWSER}\n` +
  `WEB_ACCESS_EDGE_PORT=${DEFAULTS.WEB_ACCESS_EDGE_PORT}\n` +
  `WEB_ACCESS_CHROME_PORT=${DEFAULTS.WEB_ACCESS_CHROME_PORT}\n`;

const warned = new Set();

export class RuntimeConfigError extends Error {
  constructor(code, message) {
    super(message);
    this.name = 'RuntimeConfigError';
    this.code = code;
    this.exitCode = 2;
  }
}

function parseEnvFile(content) {
  const config = {};
  for (const line of content.split(/\r?\n/)) {
    const value = line.trim();
    if (!value || value.startsWith('#')) continue;
    const separator = value.indexOf('=');
    if (separator < 1) continue;
    const key = value.slice(0, separator).trim();
    const item = value.slice(separator + 1).trim();
    if (key && item) config[key] = item;
  }
  return config;
}

function parsePort(raw, key) {
  const port = Number(raw);
  if (!Number.isInteger(port) || port < 1 || port > 65535) {
    throw new RuntimeConfigError('config_invalid', `${key} must be an integer from 1 to 65535; received ${JSON.stringify(raw)}.`);
  }
  return port;
}

function normalizedRealPath(target, label) {
  let stat;
  try {
    stat = fs.lstatSync(target);
  } catch {
    throw new RuntimeConfigError('test_isolation_invalid', `${label} does not exist: ${target}`);
  }
  if (!stat.isDirectory() || stat.isSymbolicLink()) {
    throw new RuntimeConfigError('test_isolation_invalid', `${label} must be a real directory: ${target}`);
  }
  return path.resolve(fs.realpathSync(target));
}

function isStrictChild(parent, child) {
  const relative = path.relative(parent, child);
  return relative !== '' && !relative.startsWith('..') && !path.isAbsolute(relative);
}

export function runtimeEnvironment() {
  const testMode = process.env.WEB_ACCESS_TEST_MODE === '1';
  if (!testMode && process.env.WEB_ACCESS_TEST_ROOT) {
    throw new RuntimeConfigError('test_isolation_invalid', 'WEB_ACCESS_TEST_ROOT requires WEB_ACCESS_TEST_MODE=1.');
  }

  if (testMode) {
    const requestedRoot = process.env.WEB_ACCESS_TEST_ROOT;
    if (!requestedRoot || !path.isAbsolute(requestedRoot)) {
      throw new RuntimeConfigError('test_isolation_invalid', 'WEB_ACCESS_TEST_ROOT must be an absolute directory.');
    }
    const testRoot = normalizedRealPath(requestedRoot, 'WEB_ACCESS_TEST_ROOT');
    const temporaryRoot = normalizedRealPath(os.tmpdir(), 'os.tmpdir()');
    if (!isStrictChild(temporaryRoot, testRoot)) {
      throw new RuntimeConfigError('test_isolation_invalid', `WEB_ACCESS_TEST_ROOT must be below ${temporaryRoot}.`);
    }
    const expectedLocalAppData = path.join(testRoot, 'LocalAppData');
    const actualLocalAppData = process.env.LOCALAPPDATA;
    if (!actualLocalAppData || path.resolve(actualLocalAppData) !== path.resolve(expectedLocalAppData)) {
      throw new RuntimeConfigError(
        'test_isolation_invalid',
        `LOCALAPPDATA must equal ${expectedLocalAppData} while WEB_ACCESS_TEST_MODE=1.`,
      );
    }
    const localAppData = normalizedRealPath(actualLocalAppData, 'test LOCALAPPDATA');
    if (!isStrictChild(testRoot, localAppData)) {
      throw new RuntimeConfigError('test_isolation_invalid', 'test LOCALAPPDATA escaped WEB_ACCESS_TEST_ROOT.');
    }
    return {
      testMode: true,
      testRoot,
      localAppData,
      configRoot: path.join(localAppData, 'web-access'),
    };
  }

  const localAppData = process.env.LOCALAPPDATA;
  if (os.platform() === 'win32' && (!localAppData || !path.isAbsolute(localAppData))) {
    throw new RuntimeConfigError('config_unavailable', 'LOCALAPPDATA is required for the canonical web-access configuration.');
  }
  const configRoot = os.platform() === 'win32'
    ? path.join(path.resolve(localAppData), 'web-access')
    : path.join(os.homedir(), '.config', 'web-access');
  return { testMode: false, testRoot: null, localAppData: localAppData || null, configRoot };
}

export function canonicalConfigPath() {
  return path.join(runtimeEnvironment().configRoot, 'config.env');
}

function validateConfig(config, configPath) {
  const browser = config.WEB_ACCESS_BROWSER;
  if (!['edge', 'chrome'].includes(browser)) {
    throw new RuntimeConfigError('config_invalid', `WEB_ACCESS_BROWSER in ${configPath} must be edge or chrome.`);
  }
  const edgePort = parsePort(config.WEB_ACCESS_EDGE_PORT, 'WEB_ACCESS_EDGE_PORT');
  const chromePort = parsePort(config.WEB_ACCESS_CHROME_PORT, 'WEB_ACCESS_CHROME_PORT');
  if (edgePort === chromePort) {
    throw new RuntimeConfigError('config_invalid', `Edge and Chrome Proxy ports must differ; both are ${edgePort}.`);
  }
  if (edgePort !== Number(DEFAULTS.WEB_ACCESS_EDGE_PORT) || chromePort !== Number(DEFAULTS.WEB_ACCESS_CHROME_PORT)) {
    throw new RuntimeConfigError(
      'config_invalid',
      `Production Proxy ports are fixed at Edge ${DEFAULTS.WEB_ACCESS_EDGE_PORT} and Chrome ${DEFAULTS.WEB_ACCESS_CHROME_PORT}; ${configPath} differs.`,
    );
  }
  return {
    WEB_ACCESS_BROWSER: browser,
    WEB_ACCESS_EDGE_PORT: String(edgePort),
    WEB_ACCESS_CHROME_PORT: String(chromePort),
  };
}

export function ensureCanonicalConfig(diagnostic = null) {
  const configPath = canonicalConfigPath();
  fs.mkdirSync(path.dirname(configPath), { recursive: true });
  let created = false;
  try {
    fs.writeFileSync(configPath, DEFAULT_CONFIG, { encoding: 'utf8', flag: 'wx' });
    created = true;
  } catch (error) {
    if (error?.code !== 'EEXIST') {
      throw new RuntimeConfigError('config_unavailable', `Unable to create ${configPath}: ${error.message}`);
    }
  }

  let content;
  try {
    content = fs.readFileSync(configPath, 'utf8');
  } catch (error) {
    throw new RuntimeConfigError('config_unavailable', `Unable to read ${configPath}: ${error.message}`);
  }
  const config = validateConfig(parseEnvFile(content), configPath);
  diagnostic?.(`config: ${created ? 'canonical_created' : 'canonical_reused'} (${configPath})`);
  return { config, configPath, created, environment: runtimeEnvironment() };
}

export function readConfig() {
  return ensureCanonicalConfig().config;
}

function warnOnce(message, diagnostic) {
  if (warned.has(message)) return;
  warned.add(message);
  diagnostic?.(message);
}

export function getProxyPort(browserId, { includeLegacyCdpPort = false, diagnostic = null } = {}) {
  const { config, environment } = ensureCanonicalConfig();
  const key = `WEB_ACCESS_${browserId.toUpperCase().replaceAll('-', '_')}_PORT`;
  if (!Object.hasOwn(config, key)) {
    throw new RuntimeConfigError('config_invalid', `Browser ${browserId} has no canonical Proxy port.`);
  }
  const canonical = parsePort(config[key], key);
  const overrides = [];
  if (process.env[key]) overrides.push({ key, value: parsePort(process.env[key], key) });
  if (includeLegacyCdpPort && process.env.CDP_PROXY_PORT) {
    overrides.push({ key: 'CDP_PROXY_PORT', value: parsePort(process.env.CDP_PROXY_PORT, 'CDP_PROXY_PORT') });
  }
  if (overrides.length === 0) return canonical;
  const unique = new Set(overrides.map((entry) => entry.value));
  if (unique.size !== 1) {
    throw new RuntimeConfigError('port_override_conflict', `Port overrides disagree for ${browserId}.`);
  }
  const override = overrides[0].value;
  if (environment.testMode) return override;
  if (override !== canonical) {
    throw new RuntimeConfigError(
      'port_override_conflict',
      `Production ${browserId} Proxy port is fixed at ${canonical}; refusing override ${override}.`,
    );
  }
  warnOnce(`config: port_override_redundant (${browserId}=${canonical})`, diagnostic);
  return canonical;
}

export const canonicalDefaults = DEFAULTS;
