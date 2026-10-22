#!/usr/bin/env node

import crypto from 'node:crypto';
import { execFileSync, spawn } from 'node:child_process';
import fs from 'node:fs';
import http from 'node:http';
import net from 'node:net';
import os from 'node:os';
import path from 'node:path';
import { BROKER_VERSION } from './broker-version.mjs';
import { runtimeEnvironment } from './runtime-config.mjs';

export const MANAGED_EDGE_CDP_PORT = 9222;

const STATE_SCHEMA_VERSION = 1;
const LOCK_WAIT_MS = 30_000;
const LOCK_POLL_MS = 250;
const LOCK_STALE_MS = 60_000;
const ENDPOINT_WAIT_MS = 30_000;

export class ManagedBrowserError extends Error {
  constructor(code, message, details = {}) {
    super(message);
    this.name = 'ManagedBrowserError';
    this.code = code;
    this.details = details;
  }
}

export function managedEdgeCdpPort() {
  const raw = process.env.WEB_ACCESS_TEST_MODE === '1'
    ? process.env.WEB_ACCESS_MANAGED_EDGE_CDP_PORT
    : null;
  if (!raw) return MANAGED_EDGE_CDP_PORT;
  const port = Number(raw);
  if (!Number.isInteger(port) || port < 1 || port > 65535) {
    throw new ManagedBrowserError(
      'managed_browser_test_config_invalid',
      'WEB_ACCESS_MANAGED_EDGE_CDP_PORT must be an integer from 1 to 65535.',
    );
  }
  return port;
}

export function managedBrowserPaths() {
  const root = runtimeEnvironment().configRoot;
  const profilePath = path.join(root, 'managed-edge-profile');
  return {
    root,
    profilePath,
    statePath: path.join(root, 'managed-edge-state.json'),
    lockPath: path.join(root, 'locks', 'managed-edge.lock'),
    logPath: path.join(root, 'logs', 'managed-edge.log'),
  };
}

export function parseDevToolsActivePort(content) {
  const lines = String(content || '').trim().split(/\r?\n/).filter(Boolean);
  const port = Number(lines[0]);
  const wsPath = lines[1] || '';
  if (!Number.isInteger(port) || port < 1 || port > 65535) return null;
  if (!wsPath.startsWith('/devtools/browser/')) return null;
  return { port, wsPath };
}

export function readDevToolsActivePort(profilePath) {
  try {
    return parseDevToolsActivePort(
      fs.readFileSync(path.join(profilePath, 'DevToolsActivePort'), 'utf8'),
    );
  } catch {
    return null;
  }
}

async function fetchDevToolsEndpoint(cdpPort) {
  const value = await new Promise((resolve) => {
    const request = http.get(`http://127.0.0.1:${cdpPort}/json/version`, { agent: false }, (response) => {
      if (response.statusCode !== 200) {
        response.resume();
        resolve(null);
        return;
      }
      const chunks = [];
      let total = 0;
      response.on('data', (chunk) => {
        total += chunk.length;
        if (total > 64 * 1024) {
          request.destroy();
          resolve(null);
          return;
        }
        chunks.push(chunk);
      });
      response.on('end', () => {
        try {
          resolve(JSON.parse(Buffer.concat(chunks).toString('utf8')));
        } catch {
          resolve(null);
        }
      });
    });
    request.setTimeout(2000, () => {
      request.destroy();
      resolve(null);
    });
    request.on('error', () => resolve(null));
  });
  if (!value) return null;
  try {
    const browser = String(value?.Browser || '');
    const socketUrl = String(value?.webSocketDebuggerUrl || '');
    const parsed = new URL(socketUrl);
    if (
      !browser.startsWith('Edg/') ||
      parsed.protocol !== 'ws:' ||
      !['127.0.0.1', 'localhost'].includes(parsed.hostname) ||
      Number(parsed.port) !== cdpPort ||
      !parsed.pathname.startsWith('/devtools/browser/')
    ) {
      return null;
    }
    return {
      port: cdpPort,
      wsPath: parsed.pathname + parsed.search,
      browserVersion: browser,
    };
  } catch {
    return null;
  }
}

async function readManagedEndpoint(profilePath, cdpPort) {
  const endpoint = await fetchDevToolsEndpoint(cdpPort);
  if (endpoint) {
    try {
      fs.mkdirSync(profilePath, { recursive: true });
      const temporary = path.join(profilePath, 'DevToolsActivePort.paper-download.tmp');
      fs.writeFileSync(
        temporary,
        `${endpoint.port}\n${endpoint.wsPath}\n`,
        'utf8',
      );
      fs.renameSync(temporary, path.join(profilePath, 'DevToolsActivePort'));
    } catch {}
    return endpoint;
  }
  const fileEndpoint = readDevToolsActivePort(profilePath);
  if (fileEndpoint?.port === cdpPort && await checkPort(fileEndpoint.port)) {
    return fileEndpoint;
  }
  return fileEndpoint;
}

export function managedInstanceId(endpoint) {
  if (!endpoint?.wsPath) return null;
  return crypto.createHash('sha256').update(endpoint.wsPath).digest('hex').slice(0, 24);
}

export function edgeExecutableCandidates() {
  const candidates = [];
  if (process.env.WEB_ACCESS_MANAGED_EDGE_EXECUTABLE) {
    candidates.push(process.env.WEB_ACCESS_MANAGED_EDGE_EXECUTABLE);
  }
  if (process.env.ProgramFiles) {
    candidates.push(path.join(process.env.ProgramFiles, 'Microsoft', 'Edge', 'Application', 'msedge.exe'));
  }
  if (process.env['ProgramFiles(x86)']) {
    candidates.push(path.join(process.env['ProgramFiles(x86)'], 'Microsoft', 'Edge', 'Application', 'msedge.exe'));
  }
  if (process.env.LOCALAPPDATA) {
    candidates.push(path.join(process.env.LOCALAPPDATA, 'Microsoft', 'Edge', 'Application', 'msedge.exe'));
  }
  return [...new Set(candidates.map((value) => path.resolve(value)))];
}

export function findEdgeExecutable() {
  const executable = edgeExecutableCandidates().find((candidate) => {
    try {
      return fs.statSync(candidate).isFile();
    } catch {
      return false;
    }
  });
  if (!executable) {
    throw new ManagedBrowserError(
      'managed_browser_launch_failed',
      'Microsoft Edge executable was not found.',
    );
  }
  return executable;
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function readJson(filePath, fallback = null) {
  try {
    return JSON.parse(fs.readFileSync(filePath, 'utf8'));
  } catch {
    return fallback;
  }
}

function atomicWriteJson(filePath, value) {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  const temporary = `${filePath}.${process.pid}.${crypto.randomBytes(4).toString('hex')}.tmp`;
  fs.writeFileSync(temporary, `${JSON.stringify(value, null, 2)}\n`, 'utf8');
  fs.renameSync(temporary, filePath);
}

export function checkPort(port, host = '127.0.0.1', timeoutMs = 1500) {
  return new Promise((resolve) => {
    const socket = net.createConnection(port, host);
    const timer = setTimeout(() => {
      socket.destroy();
      resolve(false);
    }, timeoutMs);
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
}

function runPowerShell(script) {
  if (os.platform() !== 'win32') return '';
  try {
    return execFileSync(
      'powershell.exe',
      ['-NoProfile', '-NonInteractive', '-Command', script],
      {
        encoding: 'utf8',
        timeout: 8000,
        windowsHide: true,
        stdio: ['ignore', 'pipe', 'ignore'],
      },
    ).trim();
  } catch {
    return '';
  }
}

export function getPortOwner(port = managedEdgeCdpPort()) {
  const output = runPowerShell(
    `$c=Get-NetTCPConnection -LocalPort ${Number(port)} -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1; if($c){[string]$c.OwningProcess}`,
  );
  const value = Number(output);
  return Number.isInteger(value) && value > 0 ? value : null;
}

export function getProcessCommandLine(pid) {
  if (!Number.isInteger(pid) || pid < 1) return '';
  return runPowerShell(
    `$p=Get-CimInstance Win32_Process -Filter "ProcessId=${Number(pid)}" -ErrorAction SilentlyContinue; if($p){[string]$p.CommandLine}`,
  );
}

export function getManagedEdgeProcesses(profilePath) {
  const normalizedProfile = path.resolve(profilePath).toLowerCase().replaceAll('/', '\\');
  const output = runPowerShell(
    `$p=Get-CimInstance Win32_Process -Filter "Name='msedge.exe'" -ErrorAction SilentlyContinue | Select-Object ProcessId,CommandLine; if($p){$p | ConvertTo-Json -Compress}`,
  );
  if (!output) return [];
  try {
    const parsed = JSON.parse(output);
    const rows = Array.isArray(parsed) ? parsed : [parsed];
    return rows
      .filter((row) => {
        const command = String(row.CommandLine || '').toLowerCase().replaceAll('/', '\\');
        return command.includes(normalizedProfile);
      })
      .map((row) => ({
        pid: Number(row.ProcessId),
        commandLine: String(row.CommandLine || ''),
      }))
      .filter((row) => Number.isInteger(row.pid) && row.pid > 0);
  } catch {
    return [];
  }
}

export function commandMatchesManagedEdge(commandLine, profilePath, cdpPort = managedEdgeCdpPort()) {
  const normalized = String(commandLine || '').toLowerCase().replaceAll('/', '\\');
  const normalizedProfile = path.resolve(profilePath).toLowerCase().replaceAll('/', '\\');
  return normalized.includes(`--user-data-dir=${normalizedProfile}`) &&
    normalized.includes(`--remote-debugging-port=${cdpPort}`) &&
    !normalized.includes('--type=');
}

export function proxyCommandMatchesManaged(commandLine, instanceId) {
  const normalized = String(commandLine || '').replaceAll('/', '\\');
  return normalized.includes('cdp-proxy.mjs') &&
    normalized.includes('--browser edge') &&
    normalized.includes('--broker-profile-mode managed') &&
    normalized.includes(`--managed-instance-id ${String(instanceId || '')}`);
}

function managedProcessFor(profilePath, state = null) {
  const processes = getManagedEdgeProcesses(profilePath);
  const matching = processes.filter((row) => commandMatchesManagedEdge(row.commandLine, profilePath));
  if (state?.browserPid) {
    const exact = matching.find((row) => row.pid === state.browserPid);
    if (exact) return exact;
  }
  return matching[0] || null;
}

async function inspectState() {
  const paths = managedBrowserPaths();
  const cdpPort = managedEdgeCdpPort();
  const state = readJson(paths.statePath);
  const endpoint = await readManagedEndpoint(paths.profilePath, cdpPort);
  const portListening = await checkPort(cdpPort);
  const profileProcesses = getManagedEdgeProcesses(paths.profilePath);
  const mainProfileProcesses = profileProcesses.filter((row) =>
    !String(row.commandLine).toLowerCase().includes('--type=')
  );
  const matchingProcesses = profileProcesses.filter((row) =>
    commandMatchesManagedEdge(row.commandLine, paths.profilePath, cdpPort)
  );
  const process = state?.browserPid
    ? matchingProcesses.find((row) => row.pid === state.browserPid) || matchingProcesses[0] || null
    : matchingProcesses[0] || null;
  const profileProcess = mainProfileProcesses[0] || null;
  const portOwner = portListening ? getPortOwner() : null;
  const validEndpoint = endpoint?.port === cdpPort &&
    portListening &&
    process &&
    (!portOwner || portOwner === process.pid);

  return {
    paths,
    cdpPort,
    state,
    endpoint,
    portListening,
    portOwner,
    process,
    profileProcess,
    ready: Boolean(validEndpoint),
    instanceId: validEndpoint ? managedInstanceId(endpoint) : null,
  };
}

function managedSummary(inspection, extra = {}) {
  return {
    status: inspection.ready ? 'ready' : 'not_running',
    ready: inspection.ready,
    reused: false,
    managed: true,
    profilePath: inspection.paths.profilePath,
    cdpPort: inspection.cdpPort,
    instanceId: inspection.instanceId,
    pid: inspection.process?.pid || inspection.portOwner || null,
    userActionRequired: null,
    ...extra,
  };
}

function lockOwnerAlive(owner) {
  return Number.isInteger(owner?.pid) &&
    owner.pid > 0 &&
    (() => {
      try {
        process.kill(owner.pid, 0);
        return true;
      } catch {
        return false;
      }
    })();
}

export async function acquireManagedLock(paths = managedBrowserPaths()) {
  fs.mkdirSync(path.dirname(paths.lockPath), { recursive: true });
  const deadline = Date.now() + LOCK_WAIT_MS;
  while (Date.now() < deadline) {
    try {
      fs.mkdirSync(paths.lockPath);
      atomicWriteJson(path.join(paths.lockPath, 'owner.json'), {
        pid: process.pid,
        startedAt: new Date().toISOString(),
      });
      return () => {
        try {
          fs.rmSync(paths.lockPath, { recursive: true, force: true });
        } catch {}
      };
    } catch (error) {
      if (error?.code !== 'EEXIST') throw error;
      const owner = readJson(path.join(paths.lockPath, 'owner.json'), {});
      const age = Date.now() - Date.parse(owner.startedAt || '');
      if (!lockOwnerAlive(owner) && (!Number.isFinite(age) || age > Math.min(LOCK_STALE_MS, 2000))) {
        fs.rmSync(paths.lockPath, { recursive: true, force: true });
        continue;
      }
      await sleep(LOCK_POLL_MS);
    }
  }
  throw new ManagedBrowserError(
    'managed_profile_busy',
    'Another web-access process is starting or repairing managed Edge.',
  );
}

function launchManagedEdge(paths, executable) {
  fs.mkdirSync(paths.profilePath, { recursive: true });
  fs.mkdirSync(path.dirname(paths.logPath), { recursive: true });
  const logFd = fs.openSync(paths.logPath, 'a');
  const cdpPort = managedEdgeCdpPort();
  const testArgs = process.env.WEB_ACCESS_TEST_MODE === '1' &&
    process.env.WEB_ACCESS_MANAGED_EDGE_HEADLESS === '1'
    ? ['--headless=new', '--disable-gpu']
    : [];
  try {
    const child = spawn(
      executable,
      [
        `--remote-debugging-port=${cdpPort}`,
        `--user-data-dir=${paths.profilePath}`,
        ...testArgs,
        '--no-first-run',
        '--no-default-browser-check',
        'about:blank',
      ],
      {
        detached: true,
        stdio: ['ignore', logFd, logFd],
        windowsHide: process.env.WEB_ACCESS_TEST_MODE === '1',
      },
    );
    child.unref();
    return child.pid;
  } finally {
    fs.closeSync(logFd);
  }
}

async function waitForEndpoint(paths, diagnostics) {
  const deadline = Date.now() + ENDPOINT_WAIT_MS;
  while (Date.now() < deadline) {
    const inspection = await inspectState();
    if (inspection.ready) return inspection;
    const ownerPid = inspection.portOwner;
    if (ownerPid) {
      const command = getProcessCommandLine(ownerPid);
      if (!commandMatchesManagedEdge(command, paths.profilePath, inspection.cdpPort)) {
        throw new ManagedBrowserError(
          'managed_cdp_port_conflict',
          `Port ${inspection.cdpPort} is used by another process.`,
          { pid: ownerPid },
        );
      }
    }
    diagnostics?.('managed-edge: waiting for browser endpoint...');
    await sleep(500);
  }
  const inspection = await inspectState();
  return inspection;
}

function writeReadyState(inspection, executable) {
  const value = {
    schemaVersion: STATE_SCHEMA_VERSION,
    brokerVersion: BROKER_VERSION,
    browserPid: inspection.process.pid,
    cdpPort: inspection.cdpPort,
    endpointPort: inspection.endpoint.port,
    profilePath: inspection.paths.profilePath,
    executablePath: executable,
    instanceId: inspection.instanceId,
    startedAt: inspection.state?.browserPid === inspection.process.pid
      ? inspection.state.startedAt
      : new Date().toISOString(),
    updatedAt: new Date().toISOString(),
  };
  atomicWriteJson(inspection.paths.statePath, value);
  return value;
}

export async function stopManagedEdge() {
  const inspection = await inspectState();
  if (!inspection.process) {
    return { stopped: false, reason: 'not_running' };
  }
  if (!commandMatchesManagedEdge(
    inspection.process.commandLine,
    inspection.paths.profilePath,
    inspection.cdpPort,
  )) {
    throw new ManagedBrowserError(
      'managed_profile_busy',
      'The process using the managed profile was not verified as the expected Edge instance.',
      { pid: inspection.process.pid },
    );
  }
  runPowerShell(`taskkill.exe /PID ${inspection.process.pid} /T /F | Out-Null`);
  const deadline = Date.now() + 15_000;
  while (Date.now() < deadline) {
    if (!(await checkPort(inspection.cdpPort))) break;
    await sleep(250);
  }
  if (await checkPort(inspection.cdpPort)) {
    throw new ManagedBrowserError(
      'managed_browser_stop_failed',
      'Managed Edge did not release its debugging port after the stop request.',
      { pid: inspection.process.pid, cdpPort: inspection.cdpPort },
    );
  }
  try {
    fs.rmSync(inspection.paths.statePath, { force: true });
  } catch {}
  return { stopped: true, pid: inspection.process.pid };
}

export async function statusManagedEdge() {
  if (os.platform() !== 'win32') {
    throw new ManagedBrowserError(
      'managed_browser_unsupported',
      'Managed Edge mode is supported only on Windows.',
    );
  }
  const inspection = await inspectState();
  if (inspection.ready) {
    return managedSummary(inspection, {
      reused: true,
      brokerVersion: BROKER_VERSION,
      userActionRequired: null,
    });
  }
  if (inspection.portListening && !inspection.process) {
    throw new ManagedBrowserError(
      'managed_cdp_port_conflict',
      `Port ${inspection.cdpPort} is already occupied.`,
      { pid: inspection.portOwner },
    );
  }
  if (inspection.profileProcess && !inspection.process) {
    throw new ManagedBrowserError(
      'managed_profile_busy',
      'The managed Edge profile is open without the expected debugging endpoint.',
      { pid: inspection.profileProcess.pid },
    );
  }
  return managedSummary(inspection, {
    brokerVersion: BROKER_VERSION,
    userActionRequired: 'managed_browser_start',
  });
}

export async function ensureManagedEdge({
  statusOnly = false,
  allowRestart = true,
  lockHeld = false,
  diagnostics = null,
} = {}) {
  if (os.platform() !== 'win32') {
    throw new ManagedBrowserError(
      'managed_browser_unsupported',
      'Managed Edge mode is supported only on Windows.',
    );
  }
  if (statusOnly) return statusManagedEdge();

  const paths = managedBrowserPaths();
  let inspection = await inspectState();
  if (inspection.ready) {
    writeReadyState(
      inspection,
      inspection.state?.executablePath || findEdgeExecutable(),
    );
    return managedSummary(inspection, {
      reused: true,
      launched: false,
      brokerVersion: BROKER_VERSION,
    });
  }

  const release = lockHeld ? () => {} : await acquireManagedLock(paths);
  try {
    inspection = await inspectState();
    if (inspection.ready) {
      writeReadyState(
        inspection,
        inspection.state?.executablePath || findEdgeExecutable(),
      );
      return managedSummary(inspection, {
        reused: true,
        launched: false,
        brokerVersion: BROKER_VERSION,
      });
    }

    if (inspection.portListening && !inspection.process) {
      throw new ManagedBrowserError(
        'managed_cdp_port_conflict',
        `Port ${inspection.cdpPort} is already occupied.`,
        { pid: inspection.portOwner },
      );
    }

    if (inspection.profileProcess) {
      if (!inspection.process) {
        throw new ManagedBrowserError(
          'managed_profile_busy',
          'The managed Edge profile is open without the expected debugging endpoint.',
          { pid: inspection.profileProcess.pid },
        );
      }
      inspection = await waitForEndpoint(paths, diagnostics);
      if (inspection.ready) {
        const executable = findEdgeExecutable();
        writeReadyState(inspection, executable);
        return managedSummary(inspection, {
          reused: true,
          launched: false,
          brokerVersion: BROKER_VERSION,
        });
      }
      if (!allowRestart) {
        throw new ManagedBrowserError(
          'managed_browser_unhealthy',
          'Managed Edge is running but its debugging endpoint is unavailable.',
          { pid: inspection.process.pid },
        );
      }
      diagnostics?.('managed-edge: restarting unresponsive managed browser...');
      await stopManagedEdge();
    }

    const executable = findEdgeExecutable();
    const launchedPid = launchManagedEdge(paths, executable);
    inspection = await waitForEndpoint(paths, diagnostics);
    if (!inspection.ready) {
      throw new ManagedBrowserError(
        'managed_browser_launch_failed',
        'Managed Edge did not expose its debugging endpoint.',
        { pid: launchedPid },
      );
    }
    writeReadyState(inspection, executable);
    return managedSummary(inspection, {
      reused: false,
      launched: true,
      brokerVersion: BROKER_VERSION,
    });
  } finally {
    release();
  }
}
