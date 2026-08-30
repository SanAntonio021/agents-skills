#!/usr/bin/env node
// web-access dual-proxy.2: task-scoped CDP proxy protocol v2.

import crypto from 'node:crypto';
import http from 'node:http';
import os from 'node:os';
import { URL } from 'node:url';
import { selectBrowser, findFallbackPort } from './browser-discovery.mjs';

const PROTOCOL_VERSION = 2;
const PORT = parsePort(process.env.CDP_PROXY_PORT || '3456', 'CDP_PROXY_PORT');
const BROWSER_OVERRIDE = parseBrowserArg();
const TASK_LIMIT = parsePositiveInt(process.env.CDP_TASK_LIMIT, 32);
const TASK_IDLE_TIMEOUT = parsePositiveInt(process.env.CDP_TASK_IDLE_TIMEOUT || process.env.CDP_TASK_ACTIVE_TIMEOUT, 30 * 60_000);
const HANDOFF_TIMEOUT = parsePositiveInt(process.env.CDP_HANDOFF_TIMEOUT || process.env.CDP_TASK_HANDOFF_TIMEOUT, 30 * 60_000);
const TAB_IDLE_TIMEOUT = parsePositiveInt(process.env.CDP_TAB_IDLE_TIMEOUT, 15 * 60_000);
const TERMINAL_RETENTION = parsePositiveInt(process.env.CDP_TERMINAL_RETENTION, 5 * 60_000);
const SNAPSHOT_CACHE_TIMEOUT = parsePositiveInt(process.env.CDP_SNAPSHOT_CACHE_TIMEOUT, 60_000);
const CDP_COMMAND_TIMEOUT = parsePositiveInt(process.env.CDP_COMMAND_TIMEOUT, 30_000);
const CLEANUP_INTERVAL = Math.min(60_000, Math.max(250, Math.floor(Math.min(
  TASK_IDLE_TIMEOUT,
  HANDOFF_TIMEOUT,
  TAB_IDLE_TIMEOUT,
  TERMINAL_RETENTION,
) / 4)));
const MAX_BODY_BYTES = 2 * 1024 * 1024;
const LEGACY_PATHS = new Set([
  '/targets', '/new', '/close', '/navigate', '/back', '/eval', '/click',
  '/clickAt', '/setFiles', '/scroll', '/screenshot', '/info',
]);
const INTERACTIVE_ROLES = new Set([
  'button', 'checkbox', 'combobox', 'gridcell', 'link', 'listbox', 'menuitem',
  'menuitemcheckbox', 'menuitemradio', 'option', 'radio', 'scrollbar', 'searchbox',
  'slider', 'spinbutton', 'switch', 'tab', 'textbox', 'treeitem',
]);

let WS;
if (typeof globalThis.WebSocket !== 'undefined') {
  WS = globalThis.WebSocket;
} else {
  try {
    WS = (await import('ws')).default;
  } catch {
    console.error('[CDP Proxy] Node.js 22+ or the ws package is required.');
    process.exit(1);
  }
}

let ws = null;
let connectingPromise = null;
let chromePort = null;
let chromeWsPath = null;
let connectedBrowser = null;
let pinnedBrowserId = null;
let commandSequence = 0;
let dialogSequence = 0;
let shutdownStarted = false;
let cleanupRunning = false;

const pendingCommands = new Map();
const sessions = new Map();
const sessionTargets = new Map();
const initializedSessions = new Set();
const guardedSessions = new Set();
const tasks = new Map();
const tokenTasks = new Map();
const tabOwners = new Map();
const targetLocks = new Map();
const snapshots = new Map();
const dialogs = new Map();
const dialogOpenWaiters = new Map();
const lifecycle = new Map();
const startupIdempotency = new Map();
const lateCommandHandlers = new Map();
const terminalOpeners = new Map();

class ApiError extends Error {
  constructor(status, code, message, details = undefined) {
    super(message);
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

class CdpTimeoutError extends Error {
  constructor(method) {
    super(`CDP command timed out: ${method}`);
    this.method = method;
  }
}

function parsePort(raw, name) {
  const value = Number(raw);
  if (!Number.isInteger(value) || value < 1 || value > 65535) {
    console.error(`[CDP Proxy] ${name} must be an integer from 1 to 65535; received ${JSON.stringify(raw)}.`);
    process.exit(1);
  }
  return value;
}

function parsePositiveInt(raw, fallback) {
  if (raw === undefined || raw === '') return fallback;
  const value = Number(raw);
  return Number.isFinite(value) && value > 0 ? Math.floor(value) : fallback;
}

function parseBrowserArg() {
  const argv = process.argv.slice(2);
  for (let index = 0; index < argv.length; index++) {
    if (argv[index] === '--browser' && argv[index + 1]) return argv[index + 1];
    if (argv[index].startsWith('--browser=')) return argv[index].slice('--browser='.length);
  }
  return null;
}

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function delayOrAbort(ms, signal) {
  if (signal.aborted) return Promise.resolve();
  return new Promise((resolve) => {
    const finish = () => {
      clearTimeout(timer);
      signal.removeEventListener('abort', finish);
      resolve();
    };
    const timer = setTimeout(finish, ms);
    signal.addEventListener('abort', finish, { once: true });
  });
}

function digest(value) {
  return crypto.createHash('sha256').update(value).digest('hex');
}

function randomId(prefix, bytes = 16) {
  return `${prefix}_${crypto.randomBytes(bytes).toString('base64url')}`;
}

function websocketOpen() {
  return ws && (ws.readyState === WS.OPEN || ws.readyState === 1);
}

function websocketUrl(port, wsPath) {
  return wsPath ? `ws://127.0.0.1:${port}${wsPath}` : `ws://127.0.0.1:${port}/devtools/browser`;
}

async function discoverBrowser() {
  const result = await selectBrowser(BROWSER_OVERRIDE);
  if (result.kind === 'ok') {
    if (pinnedBrowserId && pinnedBrowserId !== result.browser.id) {
      throw new Error(`Proxy is pinned to ${pinnedBrowserId}; refusing ${result.browser.id}.`);
    }
    pinnedBrowserId = result.browser.id;
    connectedBrowser = {
      id: result.browser.id,
      label: result.browser.label,
      source: result.source,
    };
    return { port: result.browser.port, wsPath: result.browser.wsPath };
  }
  if (result.kind === 'mismatch') {
    const expected = result.override || result.configured;
    throw new Error(
      `${expected} is not available. Open the browser, then enable Allow remote debugging at ` +
      `${expected}://inspect/#remote-debugging.`,
    );
  }
  if (pinnedBrowserId) {
    throw new Error(`Pinned browser ${pinnedBrowserId} is no longer available.`);
  }
  const fallbackPort = await findFallbackPort();
  if (fallbackPort !== null) {
    connectedBrowser = { id: 'unknown', label: 'Manual debugging port', source: 'fallback' };
    return { port: fallbackPort, wsPath: null };
  }
  throw new Error('No browser remote-debugging endpoint is available.');
}

function addWsListener(socket, event, listener) {
  if (socket.on) socket.on(event, listener);
  else socket.addEventListener(event, listener);
}

function rejectPendingCommands(error) {
  for (const { reject, timer } of pendingCommands.values()) {
    clearTimeout(timer);
    reject(error);
  }
  pendingCommands.clear();
  lateCommandHandlers.clear();
}

function clearLogicalOwnership() {
  for (const task of tasks.values()) {
    for (const controller of task.waits.keys()) controller.abort('proxy_disconnected');
  }
  tasks.clear();
  tokenTasks.clear();
  tabOwners.clear();
  targetLocks.clear();
  snapshots.clear();
  dialogs.clear();
  for (const waiters of dialogOpenWaiters.values()) for (const finish of waiters) finish(false);
  dialogOpenWaiters.clear();
  lifecycle.clear();
  startupIdempotency.clear();
  terminalOpeners.clear();
  sessions.clear();
  sessionTargets.clear();
  initializedSessions.clear();
  guardedSessions.clear();
}

async function connect() {
  if (websocketOpen()) return;
  if (connectingPromise) return connectingPromise;
  connectingPromise = (async () => {
    if (!chromePort) {
      const discovered = await discoverBrowser();
      chromePort = discovered.port;
      chromeWsPath = discovered.wsPath;
    }
    const socket = new WS(websocketUrl(chromePort, chromeWsPath));
    ws = socket;
    await new Promise((resolve, reject) => {
      let opened = false;
      addWsListener(socket, 'open', () => {
        opened = true;
        resolve();
      });
      addWsListener(socket, 'error', (event) => {
        const message = event?.message || event?.error?.message || 'WebSocket connection failed';
        if (!opened) reject(new Error(message));
        else console.error('[CDP Proxy] WebSocket error:', message);
      });
      addWsListener(socket, 'close', () => {
        if (ws !== socket) return;
        ws = null;
        chromePort = null;
        chromeWsPath = null;
        connectingPromise = null;
        rejectPendingCommands(new Error('Browser connection closed.'));
        clearLogicalOwnership();
        console.log('[CDP Proxy] Browser connection closed; task ownership was cleared.');
      });
      addWsListener(socket, 'message', (event) => {
        try {
          const raw = typeof event === 'string' ? event : (event.data ?? event);
          const message = JSON.parse(typeof raw === 'string' ? raw : raw.toString());
          handleCdpMessage(message);
        } catch (error) {
          console.error('[CDP Proxy] Ignored malformed CDP message:', error.message);
        }
      });
    });
    await sendCDP('Target.setDiscoverTargets', { discover: true });
    console.log(`[CDP Proxy] Connected to browser CDP port ${chromePort}.`);
  })();
  const attempt = connectingPromise;
  try {
    await attempt;
  } catch (error) {
    if (ws) {
      try { ws.close(); } catch {}
    }
    ws = null;
    chromePort = null;
    chromeWsPath = null;
    throw error;
  } finally {
    if (connectingPromise === attempt) connectingPromise = null;
  }
}

function handleCdpMessage(message) {
  if (message.id && pendingCommands.has(message.id)) {
    const pending = pendingCommands.get(message.id);
    clearTimeout(pending.timer);
    pendingCommands.delete(message.id);
    if (message.error) pending.reject(new Error(`${pending.method}: ${message.error.message || 'CDP error'}`));
    else pending.resolve(message.result || {});
    return;
  }
  if (message.id && lateCommandHandlers.has(message.id)) {
    const late = lateCommandHandlers.get(message.id);
    lateCommandHandlers.delete(message.id);
    if (!message.error) {
      void Promise.resolve(late.onResult(message.result || {})).catch((error) => {
        console.error(`[CDP Proxy] Late ${late.method} result handling failed:`, error.message);
      });
    }
    return;
  }
  if (!message.method) return;
  const { method, params = {}, sessionId } = message;
  if (method === 'Target.attachedToTarget') {
    const targetId = params.targetInfo?.targetId;
    if (targetId && tabOwners.has(targetId)) {
      sessions.set(targetId, params.sessionId);
      sessionTargets.set(params.sessionId, targetId);
    }
    return;
  }
  if (method === 'Target.detachedFromTarget') {
    const targetId = sessionTargets.get(params.sessionId);
    if (targetId) sessions.delete(targetId);
    sessionTargets.delete(params.sessionId);
    initializedSessions.delete(params.sessionId);
    guardedSessions.delete(params.sessionId);
    return;
  }
  if (method === 'Target.targetCreated') {
    const info = params.targetInfo;
    if (info?.type === 'page' && info.openerId) void handlePopupCreated(info);
    return;
  }
  if (method === 'Target.targetInfoChanged') {
    const info = params.targetInfo;
    const owner = info?.targetId ? tabOwners.get(info.targetId) : null;
    if (!owner) return;
    const entry = owner;
    if (entry.url !== undefined && entry.url !== info.url) invalidateTarget(info.targetId, 'navigation');
    entry.url = info.url;
    entry.title = info.title;
    return;
  }
  if (method === 'Target.targetDestroyed') {
    removeOwnedTab(params.targetId);
    return;
  }
  const targetId = sessionId ? sessionTargets.get(sessionId) : null;
  if (!targetId || !tabOwners.has(targetId)) return;
  if (method === 'Page.domContentEventFired') {
    lifecycleState(targetId).domcontentloaded = true;
  } else if (method === 'Page.loadEventFired') {
    lifecycleState(targetId).domcontentloaded = true;
    lifecycleState(targetId).load = true;
  } else if (method === 'Page.frameNavigated' && !params.frame?.parentId) {
    lifecycle.set(targetId, { domcontentloaded: false, load: false });
    invalidateTarget(targetId, 'navigation');
  } else if (method === 'Page.javascriptDialogOpening') {
    dialogs.set(targetId, {
      generation: ++dialogSequence,
      type: params.type,
      message: params.message,
      defaultPrompt: params.defaultPrompt || '',
      url: params.url || '',
    });
    const waiters = dialogOpenWaiters.get(targetId);
    if (waiters) for (const finish of [...waiters]) finish(true);
  } else if (method === 'Page.javascriptDialogClosed') {
    dialogs.delete(targetId);
    invalidateTarget(targetId, 'dialog');
  } else if (method === 'DOM.documentUpdated') {
    invalidateTarget(targetId, 'document_updated');
  } else if (method === 'Fetch.requestPaused') {
    void sendCDP('Fetch.failRequest', {
      requestId: params.requestId,
      errorReason: 'ConnectionRefused',
    }, sessionId).catch(() => {});
  }
}

function sendCDP(method, params = {}, sessionId = null, timeoutMs = CDP_COMMAND_TIMEOUT, options = {}) {
  return new Promise((resolve, reject) => {
    if (!websocketOpen()) return reject(new Error('Browser WebSocket is not connected.'));
    const id = ++commandSequence;
    const payload = { id, method, params };
    if (sessionId) payload.sessionId = sessionId;
    const timer = setTimeout(() => {
      pendingCommands.delete(id);
      if (typeof options.onLateResult === 'function') {
        lateCommandHandlers.set(id, {
          method,
          onResult: options.onLateResult,
          expiresAt: Date.now() + TERMINAL_RETENTION,
        });
      }
      reject(new CdpTimeoutError(method));
    }, timeoutMs);
    pendingCommands.set(id, { resolve, reject, timer, method });
    try {
      ws.send(JSON.stringify(payload));
    } catch (error) {
      clearTimeout(timer);
      pendingCommands.delete(id);
      reject(error);
    }
  });
}

async function ensureSession(targetId) {
  if (sessions.has(targetId)) return sessions.get(targetId);
  const result = await sendCDP('Target.attachToTarget', { targetId, flatten: true });
  if (!result.sessionId) throw new Error('Target.attachToTarget returned no sessionId.');
  sessions.set(targetId, result.sessionId);
  sessionTargets.set(result.sessionId, targetId);
  await initializeSession(result.sessionId);
  return result.sessionId;
}

async function initializeSession(sessionId) {
  if (initializedSessions.has(sessionId)) return;
  await Promise.all([
    sendCDP('Page.enable', {}, sessionId),
    sendCDP('Runtime.enable', {}, sessionId),
    sendCDP('DOM.enable', {}, sessionId),
    sendCDP('Accessibility.enable', {}, sessionId),
  ]);
  initializedSessions.add(sessionId);
  if (chromePort && !guardedSessions.has(sessionId)) {
    try {
      await sendCDP('Fetch.enable', { patterns: [
        { urlPattern: `http://127.0.0.1:${chromePort}/*`, requestStage: 'Request' },
        { urlPattern: `http://localhost:${chromePort}/*`, requestStage: 'Request' },
      ] }, sessionId);
      guardedSessions.add(sessionId);
    } catch {}
  }
}

function newTask() {
  const now = Date.now();
  const taskId = randomId('task', 16);
  const taskToken = crypto.randomBytes(32).toString('base64url');
  const tokenDigest = digest(taskToken);
  const task = {
    id: taskId,
    tokenDigest,
    state: 'active',
    stateSince: now,
    lastActivity: now,
    transitioning: null,
    tabs: new Set(),
    waits: new Map(),
    inFlight: 0,
    drainWaiters: new Set(),
    mutex: Promise.resolve(),
    idempotency: new Map(),
    terminalAt: null,
    completion: null,
  };
  tasks.set(taskId, task);
  tokenTasks.set(tokenDigest, taskId);
  return { task, taskToken };
}

function isTerminal(state) {
  return state === 'completed' || state === 'expired';
}

function activeTaskCount() {
  let count = 0;
  for (const task of tasks.values()) if (!isTerminal(task.state)) count++;
  return count;
}

async function withTaskMutex(task, operation) {
  const previous = task.mutex;
  let release;
  task.mutex = new Promise((resolve) => { release = resolve; });
  await previous;
  try {
    return await operation();
  } finally {
    release();
  }
}

function requireActive(task) {
  if (task.transitioning) {
    throw new ApiError(409, 'TASK_TRANSITIONING', `Task is entering ${task.transitioning}.`);
  }
  if (task.state === 'handoff') {
    throw new ApiError(409, 'TASK_IN_HANDOFF', 'Page access is disabled during handoff.');
  }
  if (isTerminal(task.state)) {
    throw new ApiError(410, 'TASK_TERMINAL', `Task is ${task.state}.`);
  }
  if (task.state !== 'active') throw new ApiError(409, 'INVALID_TASK_STATE', `Task is ${task.state}.`);
}

function ownTab(task, targetId, kind, openerId = null, info = {}) {
  const entry = {
    taskId: task.id,
    targetId,
    kind,
    openerId,
    createdAt: Date.now(),
    lastAccessed: Date.now(),
    generation: 0,
    title: info.title || '',
    url: info.url || 'about:blank',
  };
  tabOwners.set(targetId, entry);
  task.tabs.add(targetId);
  lifecycle.set(targetId, { domcontentloaded: false, load: false });
  return entry;
}

function rememberTerminalOpener(targetId, taskId) {
  terminalOpeners.set(targetId, {
    taskId,
    closeDescendants: true,
    expiresAt: Date.now() + TERMINAL_RETENTION,
  });
}

async function closeLateTaskTarget(info, taskId) {
  if (!info?.targetId) return;
  rememberTerminalOpener(info.targetId, taskId);
  try { await sendCDP('Target.closeTarget', { targetId: info.targetId }); }
  catch (error) { console.error('[CDP Proxy] Failed to close a late task popup:', error.message); }
}

async function handlePopupCreated(info) {
  if (tabOwners.has(info.targetId)) return;
  const openerOwner = tabOwners.get(info.openerId);
  if (openerOwner) {
    const task = tasks.get(openerOwner.taskId);
    if (!task) return;
    await withTaskMutex(task, async () => {
      if (tabOwners.has(info.targetId)) return;
      if (task.state === 'completed') {
        if (task.completion?.keep === false) await closeLateTaskTarget(info, task.id);
        return;
      }
      if (task.state === 'expired') return;
      ownTab(task, info.targetId, 'popup', info.openerId, info);
    });
    return;
  }
  const terminal = terminalOpeners.get(info.openerId);
  if (!terminal) return;
  if (terminal.expiresAt <= Date.now()) {
    terminalOpeners.delete(info.openerId);
    return;
  }
  if (terminal.closeDescendants) await closeLateTaskTarget(info, terminal.taskId);
}

async function reconcileTaskPopups(task) {
  const result = await sendCDP('Target.getTargets');
  const targetInfos = Array.isArray(result.targetInfos) ? result.targetInfos : [];
  let changed = true;
  let adopted = 0;
  while (changed) {
    changed = false;
    for (const info of targetInfos) {
      if (info?.type !== 'page' || !info.openerId || tabOwners.has(info.targetId)) continue;
      const openerOwner = tabOwners.get(info.openerId);
      if (!openerOwner || openerOwner.taskId !== task.id) continue;
      ownTab(task, info.targetId, 'popup', info.openerId, info);
      adopted++;
      changed = true;
    }
  }
  return adopted;
}

async function navigateCreatedTarget(targetId, url) {
  const sessionId = await ensureSession(targetId);
  invalidateTarget(targetId);
  lifecycle.set(targetId, { domcontentloaded: false, load: false });
  return sendCDP('Page.navigate', { url }, sessionId);
}

async function navigateAndReleaseLateTarget(targetId, url) {
  try {
    await navigateCreatedTarget(targetId, url);
  } finally {
    // This task no longer owns the late tab, so leave it navigated for the user.
    await detachAndReleaseTab(targetId);
  }
}

async function handleLateCreatedTarget(task, result, url) {
  const targetId = result?.targetId;
  if (!targetId) return;
  await withTaskMutex(task, async () => {
    if (tabOwners.has(targetId)) return;
    if (task.state === 'active' || task.state === 'handoff') {
      ownTab(task, targetId, 'created', null, { url: 'about:blank' });
      await navigateCreatedTarget(targetId, url);
      return;
    }
    if (task.state === 'completed' && task.completion?.keep === false) {
      await closeLateTaskTarget({ targetId }, task.id);
      return;
    }
    await navigateAndReleaseLateTarget(targetId, url);
  });
}

function clearDialogOpenWaiters(targetId) {
  const waiters = dialogOpenWaiters.get(targetId);
  if (waiters) for (const finish of [...waiters]) finish(false);
  dialogOpenWaiters.delete(targetId);
}

function cancelTargetWaits(task, targetId, reason) {
  for (const [controller, waitingTargetId] of task.waits) {
    if (waitingTargetId === targetId) controller.abort(reason);
  }
}

function removeOwnedTab(targetId) {
  const owner = tabOwners.get(targetId);
  if (owner) {
    const task = tasks.get(owner.taskId);
    task?.tabs.delete(targetId);
    if (task) cancelTargetWaits(task, targetId, 'target_removed');
  }
  tabOwners.delete(targetId);
  targetLocks.delete(targetId);
  snapshots.delete(targetId);
  dialogs.delete(targetId);
  clearDialogOpenWaiters(targetId);
  lifecycle.delete(targetId);
  const sessionId = sessions.get(targetId);
  if (sessionId) {
    sessionTargets.delete(sessionId);
    initializedSessions.delete(sessionId);
    guardedSessions.delete(sessionId);
  }
  sessions.delete(targetId);
}

async function detachAndReleaseTab(targetId, { strict = false } = {}) {
  const sessionId = sessions.get(targetId);
  if (sessionId && websocketOpen()) {
    try { await sendCDP('Target.detachFromTarget', { sessionId }); }
    catch (error) { if (strict && error instanceof CdpTimeoutError) throw error; }
  }
  removeOwnedTab(targetId);
}

function assertOwned(task, targetId) {
  const owner = tabOwners.get(targetId);
  if (!owner || owner.taskId !== task.id) {
    throw new ApiError(404, 'TARGET_NOT_FOUND', 'Target was not found.');
  }
  return owner;
}

function acquireTarget(task, targetId) {
  requireActive(task);
  const owner = assertOwned(task, targetId);
  if (targetLocks.has(targetId)) {
    throw new ApiError(409, 'TARGET_BUSY', 'Another operation is active on this target.');
  }
  targetLocks.set(targetId, task.id);
  task.inFlight++;
  task.lastActivity = Date.now();
  owner.lastAccessed = Date.now();
  let released = false;
  return () => {
    if (released) return;
    released = true;
    const completedAt = Date.now();
    const currentOwner = tabOwners.get(targetId);
    if (currentOwner?.taskId === task.id) currentOwner.lastAccessed = completedAt;
    task.lastActivity = completedAt;
    if (targetLocks.get(targetId) === task.id) targetLocks.delete(targetId);
    task.inFlight = Math.max(0, task.inFlight - 1);
    if (task.inFlight === 0) {
      for (const resolve of task.drainWaiters) resolve();
      task.drainWaiters.clear();
    }
  };
}

function waitForTaskIdle(task) {
  if (task.inFlight === 0) return Promise.resolve();
  return new Promise((resolve) => task.drainWaiters.add(resolve));
}

function cancelTaskWaits(task, reason) {
  for (const controller of task.waits.keys()) controller.abort(reason);
}

function lifecycleState(targetId) {
  if (!lifecycle.has(targetId)) lifecycle.set(targetId, { domcontentloaded: false, load: false });
  return lifecycle.get(targetId);
}

function invalidateTarget(targetId) {
  const owner = tabOwners.get(targetId);
  if (owner) owner.generation++;
  snapshots.delete(targetId);
}

function waitForDialogOpen(targetId, timeoutMs = 1000) {
  let settled = false;
  let timer;
  let finish;
  const promise = new Promise((resolve) => {
    finish = (opened) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      const waiters = dialogOpenWaiters.get(targetId);
      waiters?.delete(finish);
      if (waiters?.size === 0) dialogOpenWaiters.delete(targetId);
      resolve(opened);
    };
    if (!dialogOpenWaiters.has(targetId)) dialogOpenWaiters.set(targetId, new Set());
    dialogOpenWaiters.get(targetId).add(finish);
    timer = setTimeout(() => finish(false), timeoutMs);
  });
  return { promise, cancel: () => finish(false) };
}

function authenticate(req, expectedTaskId = null) {
  const header = req.headers.authorization || '';
  const match = /^Bearer ([A-Za-z0-9_-]+)$/.exec(header);
  if (!match) throw new ApiError(401, 'UNAUTHORIZED', 'A Bearer task token is required.');
  const taskId = tokenTasks.get(digest(match[1]));
  const task = taskId ? tasks.get(taskId) : null;
  if (!task || (expectedTaskId && task.id !== expectedTaskId)) {
    throw new ApiError(401, 'UNAUTHORIZED', 'Task token is invalid.');
  }
  return task;
}

async function readBody(req) {
  const chunks = [];
  let total = 0;
  for await (const chunk of req) {
    total += chunk.length;
    if (total > MAX_BODY_BYTES) throw new ApiError(413, 'BODY_TOO_LARGE', 'Request body is too large.');
    chunks.push(chunk);
  }
  return Buffer.concat(chunks).toString('utf8');
}

function parseJsonBody(raw, { allowEmpty = false } = {}) {
  if (!raw.trim()) {
    if (allowEmpty) return {};
    throw new ApiError(400, 'INVALID_JSON', 'A JSON request body is required.');
  }
  try {
    const value = JSON.parse(raw);
    if (!value || Array.isArray(value) || typeof value !== 'object') {
      throw new Error('object required');
    }
    return value;
  } catch {
    throw new ApiError(400, 'INVALID_JSON', 'Request body must be a JSON object.');
  }
}

function jsonResponse(status, value, headers = {}) {
  return {
    status,
    headers: { 'Content-Type': 'application/json; charset=utf-8', ...headers },
    body: Buffer.from(JSON.stringify(value)),
  };
}

function binaryResponse(status, body, contentType) {
  return { status, headers: { 'Content-Type': contentType }, body };
}

function errorResponse(error, { mutation = false } = {}) {
  if (error instanceof CdpTimeoutError) {
    if (!mutation) {
      return jsonResponse(504, {
        error: 'CDP_TIMEOUT',
        code: 'CDP_TIMEOUT',
        message: 'The browser did not answer the read operation before the timeout.',
      });
    }
    return jsonResponse(504, {
      error: 'UNKNOWN_RESULT',
      code: 'UNKNOWN_RESULT',
      message: 'The CDP action started but its result is unknown. Do not retry with a new idempotency key.',
    });
  }
  if (error instanceof ApiError) {
    const body = { error: error.code, code: error.code, message: error.message };
    if (error.details !== undefined) body.details = error.details;
    return jsonResponse(error.status, body);
  }
  return jsonResponse(500, { error: 'INTERNAL_ERROR', code: 'INTERNAL_ERROR', message: error.message || 'Internal error.' });
}

function writeResponse(res, response) {
  res.statusCode = response.status;
  for (const [name, value] of Object.entries(response.headers || {})) res.setHeader(name, value);
  res.setHeader('Cache-Control', 'no-store');
  res.setHeader('Content-Length', response.body.length);
  res.end(response.body);
}

function mutationRequest(req, pathname) {
  if (!pathname.startsWith('/v2/')) return false;
  return req.method === 'POST' || req.method === 'DELETE';
}

function requireIdempotencyKey(req) {
  const key = req.headers['idempotency-key'];
  if (typeof key !== 'string' || !key.trim() || key.length > 200) {
    throw new ApiError(400, 'IDEMPOTENCY_KEY_REQUIRED', 'A valid Idempotency-Key header is required.');
  }
  return key;
}

async function idempotent(cache, key, fingerprint, operation) {
  const existing = cache.get(key);
  if (existing) {
    if (existing.fingerprint !== fingerprint) {
      throw new ApiError(409, 'IDEMPOTENCY_CONFLICT', 'This idempotency key was used for a different request.');
    }
    return existing.promise;
  }
  const record = { fingerprint, createdAt: Date.now(), promise: null, taskId: null };
  record.promise = (async () => {
    try {
      const response = await operation();
      if (cache === startupIdempotency && response?.status === 201) {
        try { record.taskId = JSON.parse(response.body.toString('utf8')).taskId || null; } catch {}
      }
      return response;
    }
    catch (error) { return errorResponse(error, { mutation: true }); }
  })();
  cache.set(key, record);
  return record.promise;
}

function validateHostAndOrigin(req) {
  const host = String(req.headers.host || '').toLowerCase();
  if (host !== `127.0.0.1:${PORT}` && host !== `localhost:${PORT}`) {
    throw new ApiError(403, 'INVALID_HOST', 'Host header is not allowed.');
  }
  if (req.headers.origin !== undefined) {
    throw new ApiError(403, 'ORIGIN_FORBIDDEN', 'Browser-originated requests are not allowed.');
  }
}

function capabilities() {
  return {
    protocolVersion: PROTOCOL_VERSION,
    taskIsolation: true,
    userTabsVisible: false,
    maxActiveTasks: TASK_LIMIT,
    snapshot: { source: 'cdp-ax', modes: ['interactive', 'all'], defaultDepth: 12, defaultMaxNodes: 300, hardMaxNodes: 1000 },
    actions: ['click', 'fill', 'type', 'press', 'check', 'uncheck', 'select', 'hover'],
    waits: ['selector', 'text', 'url', 'domcontentloaded', 'load'],
    fallbacks: ['eval', 'click', 'navigate', 'back', 'scroll', 'set-files'],
    unsupported: ['cross-origin-oopif-refs', 'network-capture', 'har', 'trace', 'download-management', 'networkidle', 'javascript-wait'],
    security: { bind: '127.0.0.1', cors: false, taskTokenIsLocalSecurityBoundary: false },
  };
}

function requestedBrowserInfo() {
  if (!BROWSER_OVERRIDE) return null;
  const labels = { edge: 'Microsoft Edge', chrome: 'Chrome', chromium: 'Chromium', 'chrome-canary': 'Chrome Canary' };
  return { id: BROWSER_OVERRIDE, label: labels[BROWSER_OVERRIDE] || BROWSER_OVERRIDE, source: 'override' };
}

async function targetInfo(targetId) {
  try {
    const result = await sendCDP('Target.getTargetInfo', { targetId });
    return result.targetInfo || null;
  } catch (error) {
    if (error instanceof CdpTimeoutError) throw error;
    return null;
  }
}

async function listTaskTabs(task) {
  const output = [];
  for (const targetId of [...task.tabs]) {
    const owner = tabOwners.get(targetId);
    if (!owner || owner.taskId !== task.id) continue;
    const release = acquireTarget(task, targetId);
    try {
      const info = await targetInfo(targetId);
      if (!info) {
        removeOwnedTab(targetId);
        continue;
      }
      owner.title = info.title || owner.title;
      owner.url = info.url || owner.url;
      output.push({
        targetId,
        type: info.type || 'page',
        title: info.title || '',
        url: info.url || '',
        kind: owner.kind,
        openerId: owner.openerId,
      });
    } finally {
      release();
    }
  }
  return output;
}

function axValue(value) {
  return value && typeof value === 'object' && Object.hasOwn(value, 'value') ? value.value : undefined;
}

function axProperties(node) {
  const result = {};
  for (const property of node.properties || []) result[property.name] = axValue(property.value);
  return result;
}

function interactiveAxNode(node, properties) {
  const role = String(axValue(node.role) || '').toLowerCase();
  return INTERACTIVE_ROLES.has(role) || properties.focusable === true || properties.editable === true;
}

async function buildSnapshot(task, targetId, query) {
  const owner = assertOwned(task, targetId);
  const mode = query.get('mode') || 'interactive';
  if (!['interactive', 'all'].includes(mode)) throw new ApiError(400, 'INVALID_SNAPSHOT_MODE', 'mode must be interactive or all.');
  const depth = boundedInteger(query.get('depth'), 12, 1, 50, 'depth');
  const maxNodes = boundedInteger(query.get('maxNodes'), 300, 1, 1000, 'maxNodes');
  const cacheKey = `${mode}:${depth}:${maxNodes}`;
  const cached = snapshots.get(targetId);
  const sessionId = await ensureSession(targetId);
  let source;
  let axFetchedAt;
  if (query.get('refresh') !== 'true' && cached && cached.taskId === task.id && cached.cacheKey === cacheKey && Date.now() - cached.axFetchedAt <= SNAPSHOT_CACHE_TIMEOUT) {
    source = cached.axNodes;
    axFetchedAt = cached.axFetchedAt;
  } else {
    const result = await sendCDP('Accessibility.getFullAXTree', { depth }, sessionId);
    source = Array.isArray(result.nodes) ? result.nodes : [];
    axFetchedAt = Date.now();
  }
  owner.generation++;
  const generation = owner.generation;
  const refs = new Map();
  const nodes = [];
  let candidateCount = 0;
  for (const node of source) {
    if (node.ignored) continue;
    const properties = axProperties(node);
    const interactive = interactiveAxNode(node, properties);
    if (mode === 'interactive' && !interactive) continue;
    candidateCount++;
    if (nodes.length >= maxNodes) continue;
    const item = {
      role: axValue(node.role) || 'unknown',
      name: axValue(node.name) || '',
    };
    const value = axValue(node.value);
    const description = axValue(node.description);
    if (value !== undefined) item.value = value;
    if (description !== undefined) item.description = description;
    for (const name of ['checked', 'disabled', 'expanded', 'level', 'pressed', 'selected']) {
      if (properties[name] !== undefined) item[name] = properties[name];
    }
    if (node.backendDOMNodeId && (interactive || mode === 'all')) {
      const ref = `r${generation}_${nodes.length + 1}_${crypto.randomBytes(4).toString('hex')}`;
      item.ref = ref;
      refs.set(ref, { backendDOMNodeId: node.backendDOMNodeId, generation });
    }
    nodes.push(item);
  }
  const payload = {
    targetId,
    generation,
    mode,
    depth,
    maxNodes,
    truncated: candidateCount > maxNodes,
    nodes,
  };
  snapshots.set(targetId, { taskId: task.id, cacheKey, createdAt: Date.now(), axFetchedAt, generation, refs, payload, axNodes: source });
  return payload;
}

function boundedInteger(raw, fallback, minimum, maximum, name) {
  if (raw === null || raw === undefined || raw === '') return fallback;
  const value = Number(raw);
  if (!Number.isInteger(value) || value < minimum || value > maximum) {
    throw new ApiError(400, 'INVALID_ARGUMENT', `${name} must be an integer from ${minimum} to ${maximum}.`);
  }
  return value;
}

async function resolveRef(task, targetId, ref, { required = true } = {}) {
  if (!ref) {
    if (required) throw new ApiError(400, 'REF_REQUIRED', 'A snapshot ref is required.');
    return null;
  }
  const snapshot = snapshots.get(targetId);
  const owner = assertOwned(task, targetId);
  const record = snapshot?.refs.get(ref);
  if (!snapshot || snapshot.taskId !== task.id || snapshot.generation !== owner.generation || !record) {
    throw new ApiError(409, 'STALE_REF', 'Ref is not from the latest snapshot. Take a new snapshot.');
  }
  const sessionId = await ensureSession(targetId);
  let resolved;
  try {
    resolved = await sendCDP('DOM.resolveNode', { backendNodeId: record.backendDOMNodeId }, sessionId);
  } catch {
    invalidateTarget(targetId);
    throw new ApiError(409, 'STALE_REF', 'Referenced node is detached. Take a new snapshot.');
  }
  const objectId = resolved.object?.objectId;
  if (!objectId) {
    invalidateTarget(targetId);
    throw new ApiError(409, 'STALE_REF', 'Referenced node cannot be resolved. Take a new snapshot.');
  }
  const preflight = await callOnObject(sessionId, objectId, `function () {
    const el = this;
    if (!(el instanceof Element) || !el.isConnected) return { ok: false, reason: 'detached' };
    const style = getComputedStyle(el);
    const rect = el.getBoundingClientRect();
    const visible = style.display !== 'none' && style.visibility !== 'hidden' && Number(style.opacity || 1) > 0 && rect.width > 0 && rect.height > 0;
    const disabled = Boolean(el.disabled) || el.getAttribute('aria-disabled') === 'true';
    const x = rect.left + rect.width / 2;
    const y = rect.top + rect.height / 2;
    const hit = document.elementFromPoint(x, y);
    const unobscured = Boolean(hit && (hit === el || el.contains(hit)));
    return { ok: visible && !disabled && unobscured, visible, disabled, unobscured, x, y, tag: el.tagName, type: el.type || '', contentEditable: el.isContentEditable };
  }`);
  if (!preflight?.ok) {
    try { await sendCDP('Runtime.releaseObject', { objectId }, sessionId); } catch {}
    invalidateTarget(targetId);
    throw new ApiError(409, 'STALE_REF', 'Referenced element is detached, hidden, disabled, or obscured.', preflight || undefined);
  }
  return { sessionId, objectId, preflight };
}

async function callOnObject(sessionId, objectId, functionDeclaration, args = []) {
  const result = await sendCDP('Runtime.callFunctionOn', {
    objectId,
    functionDeclaration,
    arguments: args.map((value) => ({ value })),
    returnByValue: true,
    awaitPromise: true,
  }, sessionId);
  if (result.exceptionDetails) throw new Error(result.exceptionDetails.text || 'Runtime.callFunctionOn failed.');
  return result.result?.value;
}

async function mouseClick(sessionId, x, y, targetId = null) {
  await sendCDP('Input.dispatchMouseEvent', { type: 'mousePressed', x, y, button: 'left', clickCount: 1 }, sessionId);
  if (!targetId) {
    await sendCDP('Input.dispatchMouseEvent', { type: 'mouseReleased', x, y, button: 'left', clickCount: 1 }, sessionId);
    return false;
  }
  const dialogWaiter = waitForDialogOpen(targetId);
  const releasePromise = sendCDP('Input.dispatchMouseEvent', { type: 'mouseReleased', x, y, button: 'left', clickCount: 1 }, sessionId);
  const outcome = await Promise.race([
    releasePromise.then(() => 'released'),
    dialogWaiter.promise.then((opened) => opened ? 'dialog' : 'no-dialog-event'),
  ]);
  if (outcome === 'dialog') {
    releasePromise.catch(() => {});
    return true;
  }
  dialogWaiter.cancel();
  if (outcome === 'no-dialog-event') await releasePromise;
  return false;
}

async function focusObject(sessionId, objectId) {
  await callOnObject(sessionId, objectId, 'function () { this.focus(); return document.activeElement === this; }');
}

async function readControlValue(sessionId, objectId) {
  return callOnObject(sessionId, objectId, `function () {
    if (this.isContentEditable) return this.textContent || '';
    if ('value' in this) return String(this.value ?? '');
    return this.textContent || '';
  }`);
}

async function dispatchSelectAll(sessionId) {
  const modifiers = os.platform() === 'darwin' ? 4 : 2;
  await sendCDP('Input.dispatchKeyEvent', { type: 'rawKeyDown', key: 'a', code: 'KeyA', windowsVirtualKeyCode: 65, modifiers }, sessionId);
  await sendCDP('Input.dispatchKeyEvent', { type: 'keyUp', key: 'a', code: 'KeyA', windowsVirtualKeyCode: 65, modifiers }, sessionId);
}

const KEY_DATA = {
  Enter: { code: 'Enter', windowsVirtualKeyCode: 13 },
  Tab: { code: 'Tab', windowsVirtualKeyCode: 9 },
  Escape: { code: 'Escape', windowsVirtualKeyCode: 27 },
  Backspace: { code: 'Backspace', windowsVirtualKeyCode: 8 },
  Delete: { code: 'Delete', windowsVirtualKeyCode: 46 },
  ArrowDown: { code: 'ArrowDown', windowsVirtualKeyCode: 40 },
  ArrowUp: { code: 'ArrowUp', windowsVirtualKeyCode: 38 },
  ArrowLeft: { code: 'ArrowLeft', windowsVirtualKeyCode: 37 },
  ArrowRight: { code: 'ArrowRight', windowsVirtualKeyCode: 39 },
  Home: { code: 'Home', windowsVirtualKeyCode: 36 },
  End: { code: 'End', windowsVirtualKeyCode: 35 },
  PageUp: { code: 'PageUp', windowsVirtualKeyCode: 33 },
  PageDown: { code: 'PageDown', windowsVirtualKeyCode: 34 },
  Space: { code: 'Space', windowsVirtualKeyCode: 32, text: ' ' },
};

async function dispatchPress(sessionId, input) {
  if (typeof input !== 'string' || input.length === 0) throw new ApiError(400, 'KEY_REQUIRED', 'key is required.');
  const parts = input.length === 1 ? [input] : input.split('+').map((value) => value.trim()).filter(Boolean);
  const key = parts.pop();
  let modifiers = 0;
  for (const modifier of parts) {
    const normalized = modifier.toLowerCase();
    if (normalized === 'alt') modifiers |= 1;
    else if (normalized === 'control' || normalized === 'ctrl') modifiers |= 2;
    else if (normalized === 'meta' || normalized === 'command' || normalized === 'cmd') modifiers |= 4;
    else if (normalized === 'shift') modifiers |= 8;
    else throw new ApiError(400, 'INVALID_KEY', `Unknown modifier: ${modifier}`);
  }
  const known = KEY_DATA[key] || {};
  const printable = [...key].length === 1;
  const params = {
    key: key === 'Space' ? ' ' : key,
    code: known.code || (printable && /^[A-Za-z]$/.test(key) ? `Key${key.toUpperCase()}` : key),
    windowsVirtualKeyCode: known.windowsVirtualKeyCode || (printable ? key.toUpperCase().charCodeAt(0) : 0),
    modifiers,
  };
  if ((known.text || printable) && modifiers === 0) {
    params.text = known.text || key;
    params.unmodifiedText = known.text || key;
  }
  await sendCDP('Input.dispatchKeyEvent', { type: params.text ? 'keyDown' : 'rawKeyDown', ...params }, sessionId);
  await sendCDP('Input.dispatchKeyEvent', { type: 'keyUp', ...params, text: undefined, unmodifiedText: undefined }, sessionId);
}

async function performAction(task, targetId, body) {
  const action = body.action;
  if (!['click', 'fill', 'type', 'press', 'check', 'uncheck', 'select', 'hover'].includes(action)) {
    throw new ApiError(400, 'INVALID_ACTION', 'Unsupported action.');
  }
  let resolved = null;
  if (action !== 'press' || body.ref) resolved = await resolveRef(task, targetId, body.ref);
  const sessionId = resolved?.sessionId || await ensureSession(targetId);
  try {
    if (action === 'click') {
      const dialogOpened = await mouseClick(sessionId, resolved.preflight.x, resolved.preflight.y, targetId);
      return { ok: true, action, ...(dialogOpened ? { dialogOpened: true } : {}) };
    }
    if (action === 'hover') {
      await sendCDP('Input.dispatchMouseEvent', { type: 'mouseMoved', x: resolved.preflight.x, y: resolved.preflight.y }, sessionId);
      return { ok: true, action };
    }
    if (action === 'fill') {
      if (typeof body.value !== 'string') throw new ApiError(400, 'VALUE_REQUIRED', 'fill requires string value.');
      await focusObject(sessionId, resolved.objectId);
      await dispatchSelectAll(sessionId);
      await sendCDP('Input.insertText', { text: body.value }, sessionId);
      const actual = await readControlValue(sessionId, resolved.objectId);
      if (actual !== body.value) throw new ApiError(409, 'ACTION_VERIFY_FAILED', 'Filled value did not match.', { expected: body.value, actual });
      return { ok: true, action, value: actual };
    }
    if (action === 'type') {
      if (typeof body.value !== 'string') throw new ApiError(400, 'VALUE_REQUIRED', 'type requires string value.');
      await focusObject(sessionId, resolved.objectId);
      for (const character of body.value) await dispatchPress(sessionId, character);
      return { ok: true, action, value: await readControlValue(sessionId, resolved.objectId) };
    }
    if (action === 'press') {
      if (resolved) await focusObject(sessionId, resolved.objectId);
      await dispatchPress(sessionId, body.key);
      return { ok: true, action, key: body.key };
    }
    if (action === 'check' || action === 'uncheck') {
      const desired = action === 'check';
      await focusObject(sessionId, resolved.objectId);
      const before = await callOnObject(sessionId, resolved.objectId, `function () {
        return { supported: this instanceof HTMLInputElement && ['checkbox', 'radio'].includes(this.type), checked: Boolean(this.checked) };
      }`);
      if (!before?.supported) throw new ApiError(400, 'UNSUPPORTED_ELEMENT', 'check/uncheck requires a native checkbox or radio input.');
      if (before.checked !== desired) await mouseClick(sessionId, resolved.preflight.x, resolved.preflight.y, targetId);
      const checked = await callOnObject(sessionId, resolved.objectId, 'function () { return Boolean(this.checked); }');
      if (checked !== desired) throw new ApiError(409, 'ACTION_VERIFY_FAILED', 'Checked state did not match.', { expected: desired, actual: checked });
      return { ok: true, action, checked };
    }
    const values = Array.isArray(body.values) ? body.values.map(String) : (body.value !== undefined ? [String(body.value)] : []);
    if (!values.length) throw new ApiError(400, 'VALUE_REQUIRED', 'select requires value or values.');
    const selection = await callOnObject(sessionId, resolved.objectId, `function (values) {
      if (!(this instanceof HTMLSelectElement)) return { supported: false };
      const wanted = new Set(values.map(String));
      for (const option of this.options) option.selected = wanted.has(option.value);
      this.dispatchEvent(new Event('input', { bubbles: true }));
      this.dispatchEvent(new Event('change', { bubbles: true }));
      return { supported: true, multiple: this.multiple, selected: Array.from(this.selectedOptions, option => option.value) };
    }`, [values]);
    if (!selection?.supported) throw new ApiError(400, 'UNSUPPORTED_ELEMENT', 'select requires a native select element.');
    const expected = selection.multiple ? [...new Set(values)].sort() : values.slice(0, 1);
    const actual = selection.multiple ? [...new Set(selection.selected)].sort() : selection.selected;
    if (JSON.stringify(actual) !== JSON.stringify(expected)) {
      throw new ApiError(409, 'ACTION_VERIFY_FAILED', 'Selected values did not match.', { expected, actual: selection.selected });
    }
    return { ok: true, action, values: selection.selected };
  } finally {
    if (resolved?.objectId && !dialogs.has(targetId)) {
      try { await sendCDP('Runtime.releaseObject', { objectId: resolved.objectId }, sessionId); } catch {}
    }
  }
}

function waitCondition(body) {
  const keys = ['selector', 'text', 'url'].filter((name) => body[name] !== undefined);
  if (body.state !== undefined) keys.push('state');
  if (keys.length !== 1) throw new ApiError(400, 'INVALID_WAIT', 'Specify exactly one of selector, text, url, or state.');
  if (body.state !== undefined && !['domcontentloaded', 'load'].includes(body.state)) {
    throw new ApiError(400, 'INVALID_WAIT', 'state must be domcontentloaded or load.');
  }
  return keys[0];
}

async function waitForCondition(task, targetId, body) {
  const kind = waitCondition(body);
  const timeoutMs = boundedInteger(body.timeoutMs, 15_000, 1, 30_000, 'timeoutMs');
  const controller = new AbortController();
  task.waits.set(controller, targetId);
  const deadline = Date.now() + timeoutMs;
  try {
    if (task.transitioning || task.state !== 'active') controller.abort('task_transition');
    let sessionId;
    try {
      sessionId = await ensureSession(targetId);
    } catch (error) {
      if (controller.signal.aborted) {
        throw new ApiError(409, 'WAIT_CANCELLED', 'Wait was cancelled by a task state transition.');
      }
      throw error;
    }
    while (Date.now() <= deadline) {
      if (controller.signal.aborted) throw new ApiError(409, 'WAIT_CANCELLED', 'Wait was cancelled by a task state transition.');
      if (dialogs.has(targetId)) throw new ApiError(409, 'DIALOG_OPEN', 'A JavaScript dialog must be handled explicitly before waiting.');
      let matched = false;
      if (kind === 'selector') {
        if (typeof body.selector !== 'string' || !body.selector) throw new ApiError(400, 'INVALID_WAIT', 'selector must be a non-empty string.');
        const expression = `Boolean(document.querySelector(${JSON.stringify(body.selector)}))`;
        const result = await sendCDP('Runtime.evaluate', { expression, returnByValue: true }, sessionId);
        matched = result.result?.value === true;
      } else if (kind === 'text') {
        if (typeof body.text !== 'string' || !body.text) throw new ApiError(400, 'INVALID_WAIT', 'text must be a non-empty string.');
        const expression = `(document.body?.innerText || '').includes(${JSON.stringify(body.text)})`;
        const result = await sendCDP('Runtime.evaluate', { expression, returnByValue: true }, sessionId);
        matched = result.result?.value === true;
      } else if (kind === 'url') {
        if (typeof body.url !== 'string' || !body.url) throw new ApiError(400, 'INVALID_WAIT', 'url must be a non-empty string.');
        const result = await sendCDP('Runtime.evaluate', { expression: 'location.href', returnByValue: true }, sessionId);
        matched = typeof result.result?.value === 'string' && result.result.value.includes(body.url);
      } else {
        const state = lifecycleState(targetId);
        if (state[body.state]) matched = true;
        else {
          const result = await sendCDP('Runtime.evaluate', { expression: 'document.readyState', returnByValue: true }, sessionId);
          const ready = result.result?.value;
          matched = body.state === 'load' ? ready === 'complete' : ['interactive', 'complete'].includes(ready);
        }
      }
      if (controller.signal.aborted) throw new ApiError(409, 'WAIT_CANCELLED', 'Wait was cancelled by a task state transition.');
      if (matched) {
        invalidateTarget(targetId);
        return { ok: true, condition: kind === 'state' ? body.state : kind };
      }
      await delayOrAbort(250, controller.signal);
    }
    throw new ApiError(408, 'WAIT_TIMEOUT', `Condition was not met within ${timeoutMs} ms.`);
  } finally {
    task.waits.delete(controller);
  }
}

async function taskHandoff(task, body) {
  return withTaskMutex(task, async () => {
    requireActive(task);
    if (!body.targetId) throw new ApiError(400, 'TARGET_REQUIRED', 'handoff requires targetId.');
    assertOwned(task, body.targetId);
    task.transitioning = 'handoff';
    cancelTaskWaits(task, 'handoff');
    await waitForTaskIdle(task);
    try {
      if (!await targetInfo(body.targetId)) {
        removeOwnedTab(body.targetId);
        throw new ApiError(404, 'TARGET_NOT_FOUND', 'Target was not found.');
      }
      task.state = 'handoff';
      task.stateSince = Date.now();
      task.lastActivity = Date.now();
      try {
        await sendCDP('Target.activateTarget', { targetId: body.targetId });
      } catch (error) {
        if (!(error instanceof CdpTimeoutError)) {
          task.state = 'active';
          task.stateSince = Date.now();
        }
        throw error;
      }
      return { taskId: task.id, state: task.state, targetId: body.targetId };
    } finally {
      task.transitioning = null;
    }
  });
}

async function taskResume(task) {
  return withTaskMutex(task, async () => {
    if (task.transitioning) throw new ApiError(409, 'TASK_TRANSITIONING', 'Task is transitioning.');
    if (task.state !== 'handoff') throw new ApiError(409, 'INVALID_TASK_STATE', 'Only a handoff task can resume.');
    const remaining = [];
    for (const targetId of [...task.tabs]) {
      if (await targetInfo(targetId)) remaining.push(targetId);
      else removeOwnedTab(targetId);
    }
    if (!remaining.length) throw new ApiError(409, 'NO_OWNED_TABS', 'No task-created tab remains open.');
    for (const targetId of remaining) invalidateTarget(targetId);
    task.state = 'active';
    task.stateSince = Date.now();
    task.lastActivity = Date.now();
    return { taskId: task.id, state: task.state, snapshotRequired: true, targetIds: remaining };
  });
}

async function taskComplete(task, keep) {
  return withTaskMutex(task, async () => {
    if (task.state === 'completed') return task.completion;
    if (task.state === 'expired') throw new ApiError(410, 'TASK_EXPIRED', 'Task has expired.');
    if (task.transitioning) throw new ApiError(409, 'TASK_TRANSITIONING', 'Task is transitioning.');
    if (task.state !== 'active') {
      throw new ApiError(409, 'INVALID_TASK_STATE', 'Complete is allowed only while the task is active. Resume a handoff task first.');
    }
    task.transitioning = 'completed';
    cancelTaskWaits(task, 'complete');
    await waitForTaskIdle(task);
    let closed = 0;
    let released = 0;
    try {
      await reconcileTaskPopups(task);
      const targetIds = [...task.tabs];
      for (const targetId of targetIds) {
        if (keep) {
          await detachAndReleaseTab(targetId, { strict: true });
          released++;
        } else {
          rememberTerminalOpener(targetId, task.id);
          try { await sendCDP('Target.closeTarget', { targetId }); }
          catch (error) { if (error instanceof CdpTimeoutError) throw error; }
          removeOwnedTab(targetId);
          closed++;
        }
      }
      task.state = 'completed';
      task.stateSince = Date.now();
      task.terminalAt = Date.now();
      task.completion = { taskId: task.id, state: task.state, keep: Boolean(keep), closed, released };
      return task.completion;
    } catch (error) {
      if (error instanceof CdpTimeoutError) {
        const retained = [...task.tabs];
        for (const targetId of retained) removeOwnedTab(targetId);
        task.state = 'completed';
        task.stateSince = Date.now();
        task.terminalAt = Date.now();
        task.completion = {
          taskId: task.id,
          state: task.state,
          keep: Boolean(keep),
          closed,
          released,
          unknownResult: true,
          retainedAsUserTabs: retained.length,
        };
      }
      throw error;
    } finally {
      task.transitioning = null;
    }
  });
}

async function fallbackEval(sessionId, expression) {
  const result = await sendCDP('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true }, sessionId);
  if (result.exceptionDetails) throw new ApiError(400, 'EVAL_FAILED', result.exceptionDetails.text || 'Evaluation failed.');
  return { value: result.result?.value };
}

async function handleRoute(req, parsed, rawBody) {
  const pathname = parsed.pathname;
  if (pathname === '/health' && req.method === 'GET') {
    return jsonResponse(200, {
      service: 'web-access-cdp-proxy',
      status: 'ok',
      protocolVersion: PROTOCOL_VERSION,
      connected: websocketOpen(),
      proxyPort: PORT,
      requestedBrowser: BROWSER_OVERRIDE,
      browser: connectedBrowser || requestedBrowserInfo(),
      sessions: sessions.size,
      managedTabs: tabOwners.size,
      activeTasks: activeTaskCount(),
      chromePort,
      pid: process.pid,
    });
  }
  if (pathname === '/capabilities' && req.method === 'GET') return jsonResponse(200, capabilities());
  if (LEGACY_PATHS.has(pathname)) {
    return jsonResponse(410, {
      error: 'LEGACY_API_DISABLED',
      code: 'LEGACY_API_DISABLED',
      message: 'Unversioned browser operation APIs are disabled.',
      migration: 'references/migration-dual-proxy.2.md',
    });
  }
  if (!pathname.startsWith('/v2/')) throw new ApiError(404, 'NOT_FOUND', 'Endpoint was not found.');
  await connect();

  if (pathname === '/v2/tasks' && req.method === 'POST') {
    parseJsonBody(rawBody, { allowEmpty: true });
    if (activeTaskCount() >= TASK_LIMIT) throw new ApiError(429, 'TASK_LIMIT_REACHED', `At most ${TASK_LIMIT} active tasks are allowed.`);
    const { task, taskToken } = newTask();
    return jsonResponse(201, { taskId: task.id, taskToken, state: task.state });
  }

  const taskStateMatch = /^\/v2\/tasks\/([^/]+)$/.exec(pathname);
  if (taskStateMatch && req.method === 'GET') {
    const task = authenticate(req, decodeURIComponent(taskStateMatch[1]));
    return jsonResponse(200, { taskId: task.id, state: task.state, tabCount: task.tabs.size, lastActivity: new Date(task.lastActivity).toISOString() });
  }

  const taskActionMatch = /^\/v2\/tasks\/([^/]+)\/(handoff|resume|complete)$/.exec(pathname);
  if (taskActionMatch && req.method === 'POST') {
    const task = authenticate(req, decodeURIComponent(taskActionMatch[1]));
    const body = parseJsonBody(rawBody, { allowEmpty: true });
    const action = taskActionMatch[2];
    if (action === 'handoff') return jsonResponse(200, await taskHandoff(task, body));
    if (action === 'resume') return jsonResponse(200, await taskResume(task));
    return jsonResponse(200, await taskComplete(task, Boolean(body.keep)));
  }

  const deleteTaskMatch = /^\/v2\/tasks\/([^/]+)$/.exec(pathname);
  if (deleteTaskMatch && req.method === 'DELETE') {
    const task = authenticate(req, decodeURIComponent(deleteTaskMatch[1]));
    return jsonResponse(200, await taskComplete(task, false));
  }

  if (pathname === '/v2/tabs' && req.method === 'POST') {
    const task = authenticate(req);
    const body = parseJsonBody(rawBody, { allowEmpty: true });
    return withTaskMutex(task, async () => {
      requireActive(task);
      const url = body.url === undefined ? 'about:blank' : String(body.url);
      let validated;
      try { validated = new URL(url); } catch { throw new ApiError(400, 'INVALID_URL', 'url must be an absolute URL.'); }
      if (!['http:', 'https:', 'about:'].includes(validated.protocol)) throw new ApiError(400, 'INVALID_URL', 'Only http, https, and about URLs are allowed.');
      const result = await sendCDP(
        'Target.createTarget',
        { url: 'about:blank', background: body.background !== false },
        null,
        CDP_COMMAND_TIMEOUT,
        { onLateResult: (late) => handleLateCreatedTarget(task, late, url) },
      );
      if (!result.targetId) throw new Error('Target.createTarget returned no targetId.');
      ownTab(task, result.targetId, 'created', null, { url: 'about:blank' });
      await navigateCreatedTarget(result.targetId, url);
      task.lastActivity = Date.now();
      return jsonResponse(201, { targetId: result.targetId, kind: 'created' });
    });
  }

  if (pathname === '/v2/tabs' && req.method === 'GET') {
    const task = authenticate(req);
    requireActive(task);
    task.lastActivity = Date.now();
    return jsonResponse(200, await listTaskTabs(task));
  }

  const tabMatch = /^\/v2\/tabs\/([^/]+)(?:\/(snapshot|action|wait|dialog|navigate|back|eval|click|set-files|setFiles|scroll|screenshot))?$/.exec(pathname);
  if (!tabMatch) throw new ApiError(404, 'NOT_FOUND', 'Endpoint was not found.');
  const targetId = decodeURIComponent(tabMatch[1]);
  const operation = tabMatch[2] || null;
  const task = authenticate(req);
  requireActive(task);
  assertOwned(task, targetId);

  if (!operation && req.method === 'GET') {
    const release = acquireTarget(task, targetId);
    try {
      const info = await targetInfo(targetId);
      if (!info) {
        removeOwnedTab(targetId);
        throw new ApiError(404, 'TARGET_NOT_FOUND', 'Target was not found.');
      }
      return jsonResponse(200, {
        targetId,
        type: info.type,
        title: info.title,
        url: info.url,
        kind: tabOwners.get(targetId)?.kind,
        generation: tabOwners.get(targetId)?.generation || 0,
        dialog: dialogs.get(targetId) || null,
      });
    } finally { release(); }
  }

  if (!operation && req.method === 'DELETE') {
    const release = acquireTarget(task, targetId);
    try {
      const result = await sendCDP('Target.closeTarget', { targetId });
      removeOwnedTab(targetId);
      return jsonResponse(200, { targetId, closed: result.success !== false });
    } finally { release(); }
  }

  if (operation === 'snapshot' && req.method === 'GET') {
    const release = acquireTarget(task, targetId);
    try {
      if (dialogs.has(targetId)) throw new ApiError(409, 'DIALOG_OPEN', 'Handle the JavaScript dialog before taking a snapshot.');
      return jsonResponse(200, await buildSnapshot(task, targetId, parsed.searchParams));
    }
    finally { release(); }
  }

  if (operation === 'screenshot' && req.method === 'GET') {
    if (parsed.searchParams.has('file')) throw new ApiError(400, 'OUTPUT_PATH_DISABLED', 'Proxy does not accept local screenshot paths.');
    const format = parsed.searchParams.get('format') || 'png';
    if (!['png', 'jpeg'].includes(format)) throw new ApiError(400, 'INVALID_FORMAT', 'format must be png or jpeg.');
    const release = acquireTarget(task, targetId);
    try {
      if (dialogs.has(targetId)) throw new ApiError(409, 'DIALOG_OPEN', 'Handle the JavaScript dialog before taking a screenshot.');
      const sessionId = await ensureSession(targetId);
      const result = await sendCDP('Page.captureScreenshot', { format, ...(format === 'jpeg' ? { quality: 80 } : {}) }, sessionId);
      return binaryResponse(200, Buffer.from(result.data || '', 'base64'), `image/${format}`);
    } finally { release(); }
  }

  if (req.method !== 'POST') throw new ApiError(405, 'METHOD_NOT_ALLOWED', 'Method is not allowed.');
  const body = parseJsonBody(rawBody, { allowEmpty: operation === 'back' });
  const release = acquireTarget(task, targetId);
  try {
    if (operation !== 'dialog' && dialogs.has(targetId)) {
      throw new ApiError(409, 'DIALOG_OPEN', 'Handle the JavaScript dialog before continuing.');
    }
    if (operation === 'action') return jsonResponse(200, await performAction(task, targetId, body));
    if (operation === 'wait') return jsonResponse(200, await waitForCondition(task, targetId, body));
    const sessionId = await ensureSession(targetId);
    if (operation === 'dialog') {
      const current = dialogs.get(targetId);
      if (!current) throw new ApiError(409, 'NO_DIALOG', 'No JavaScript dialog is open.');
      if (!['accept', 'dismiss'].includes(body.action)) throw new ApiError(400, 'INVALID_DIALOG_ACTION', 'dialog action must be accept or dismiss.');
      await sendCDP('Page.handleJavaScriptDialog', {
        accept: body.action === 'accept',
        ...(body.promptText !== undefined ? { promptText: String(body.promptText) } : {}),
      }, sessionId);
      if (dialogs.get(targetId)?.generation === current.generation) {
        dialogs.delete(targetId);
        invalidateTarget(targetId);
      }
      return jsonResponse(200, { ok: true, action: body.action, type: current.type });
    }
    if (operation === 'navigate') {
      if (typeof body.url !== 'string' || !body.url) throw new ApiError(400, 'URL_REQUIRED', 'navigate requires url.');
      let url;
      try { url = new URL(body.url); } catch { throw new ApiError(400, 'INVALID_URL', 'url must be absolute.'); }
      if (!['http:', 'https:', 'about:'].includes(url.protocol)) throw new ApiError(400, 'INVALID_URL', 'Only http, https, and about URLs are allowed.');
      invalidateTarget(targetId);
      lifecycle.set(targetId, { domcontentloaded: false, load: false });
      const result = await sendCDP('Page.navigate', { url: body.url }, sessionId);
      return jsonResponse(200, { ok: true, frameId: result.frameId, loaderId: result.loaderId });
    }
    if (operation === 'back') {
      invalidateTarget(targetId);
      lifecycle.set(targetId, { domcontentloaded: false, load: false });
      await sendCDP('Runtime.evaluate', { expression: 'history.back()' }, sessionId);
      return jsonResponse(200, { ok: true });
    }
    if (operation === 'eval') {
      if (typeof body.expression !== 'string') throw new ApiError(400, 'EXPRESSION_REQUIRED', 'eval requires expression.');
      return jsonResponse(200, await fallbackEval(sessionId, body.expression));
    }
    if (operation === 'click') {
      if (typeof body.selector !== 'string' || !body.selector) throw new ApiError(400, 'SELECTOR_REQUIRED', 'click requires selector.');
      const expression = `(() => { const el = document.querySelector(${JSON.stringify(body.selector)}); if (!el) return { found: false }; el.scrollIntoView({ block: 'center' }); el.click(); return { found: true, clicked: true }; })()`;
      const result = await fallbackEval(sessionId, expression);
      if (result.value?.found === false) throw new ApiError(404, 'ELEMENT_NOT_FOUND', 'Selector did not match an element.');
      return jsonResponse(200, result.value);
    }
    if (operation === 'set-files' || operation === 'setFiles') {
      if (typeof body.selector !== 'string' || !Array.isArray(body.files) || !body.files.length || body.files.some((file) => typeof file !== 'string')) {
        throw new ApiError(400, 'INVALID_FILES', 'set-files requires selector and a non-empty files array.');
      }
      const documentResult = await sendCDP('DOM.getDocument', {}, sessionId);
      const nodeResult = await sendCDP('DOM.querySelector', { nodeId: documentResult.root.nodeId, selector: body.selector }, sessionId);
      if (!nodeResult.nodeId) throw new ApiError(404, 'ELEMENT_NOT_FOUND', 'File input was not found.');
      await sendCDP('DOM.setFileInputFiles', { nodeId: nodeResult.nodeId, files: body.files }, sessionId);
      return jsonResponse(200, { ok: true, files: body.files.length });
    }
    if (operation === 'scroll') {
      const y = Number.isFinite(Number(body.y)) ? Number(body.y) : 1000;
      const x = Number.isFinite(Number(body.x)) ? Number(body.x) : 0;
      const direction = body.direction || 'down';
      if (!['down', 'up', 'top', 'bottom'].includes(direction)) throw new ApiError(400, 'INVALID_DIRECTION', 'direction must be down, up, top, or bottom.');
      const expression = direction === 'top'
        ? 'window.scrollTo(0, 0)'
        : direction === 'bottom'
          ? 'window.scrollTo(0, document.documentElement.scrollHeight)'
          : `window.scrollBy(${x}, ${direction === 'up' ? -Math.abs(y) : Math.abs(y)})`;
      await sendCDP('Runtime.evaluate', { expression }, sessionId);
      return jsonResponse(200, { ok: true, direction, x, y });
    }
    throw new ApiError(404, 'NOT_FOUND', 'Endpoint was not found.');
  } finally {
    release();
  }
}

async function processRequest(req) {
  validateHostAndOrigin(req);
  const parsed = new URL(req.url, `http://127.0.0.1:${PORT}`);
  const rawBody = (req.method === 'POST' || req.method === 'DELETE') ? await readBody(req) : '';
  if (!mutationRequest(req, parsed.pathname)) {
    try { return await handleRoute(req, parsed, rawBody); }
    catch (error) { return errorResponse(error, { mutation: false }); }
  }
  const contentType = String(req.headers['content-type'] || '').toLowerCase();
  if (!contentType.startsWith('application/json')) {
    return errorResponse(new ApiError(415, 'JSON_REQUIRED', 'Mutations require Content-Type: application/json.'));
  }
  let cache = startupIdempotency;
  if (!(parsed.pathname === '/v2/tasks' && req.method === 'POST')) {
    const expected = /^\/v2\/tasks\/([^/]+)/.exec(parsed.pathname)?.[1];
    try {
      const task = authenticate(req, expected ? decodeURIComponent(expected) : null);
      cache = task.idempotency;
    } catch (error) {
      return errorResponse(error);
    }
  }
  let key;
  try { key = requireIdempotencyKey(req); }
  catch (error) { return errorResponse(error); }
  const fingerprint = digest(`${req.method}\n${parsed.pathname}${parsed.search}\n${rawBody}`);
  try {
    return await idempotent(cache, key, fingerprint, () => handleRoute(req, parsed, rawBody));
  } catch (error) {
    return errorResponse(error, { mutation: true });
  }
}

async function expireTask(task, reason) {
  if (isTerminal(task.state) || task.transitioning) return;
  await withTaskMutex(task, async () => {
    if (isTerminal(task.state) || task.transitioning) return;
    const now = Date.now();
    if (reason === 'active_idle_timeout' && (task.state !== 'active' || now - task.lastActivity < TASK_IDLE_TIMEOUT)) return;
    if (reason === 'handoff_timeout' && (task.state !== 'handoff' || now - task.stateSince < HANDOFF_TIMEOUT)) return;
    task.transitioning = 'expired';
    cancelTaskWaits(task, reason);
    await waitForTaskIdle(task);
    try {
      for (const targetId of [...task.tabs]) await detachAndReleaseTab(targetId);
      task.state = 'expired';
      task.stateSince = Date.now();
      task.terminalAt = Date.now();
      task.completion = { taskId: task.id, state: task.state, reason };
    } finally {
      task.transitioning = null;
    }
  });
}

function tryAcquireIdleTarget(task, targetId, now) {
  if (!task || task.state !== 'active' || task.transitioning || targetLocks.has(targetId)) return null;
  const owner = tabOwners.get(targetId);
  if (!owner || owner.taskId !== task.id || now - owner.lastAccessed < TAB_IDLE_TIMEOUT) return null;
  targetLocks.set(targetId, task.id);
  task.inFlight++;
  let released = false;
  return () => {
    if (released) return;
    released = true;
    if (targetLocks.get(targetId) === task.id) targetLocks.delete(targetId);
    task.inFlight = Math.max(0, task.inFlight - 1);
    if (task.inFlight === 0) {
      for (const resolve of task.drainWaiters) resolve();
      task.drainWaiters.clear();
    }
  };
}

async function cleanupState() {
  if (cleanupRunning) return;
  cleanupRunning = true;
  try {
    const now = Date.now();
    for (const task of tasks.values()) {
      if (task.state === 'active' && now - task.lastActivity >= TASK_IDLE_TIMEOUT) await expireTask(task, 'active_idle_timeout');
      else if (task.state === 'handoff' && now - task.stateSince >= HANDOFF_TIMEOUT) await expireTask(task, 'handoff_timeout');
    }
    for (const [key, record] of startupIdempotency) {
      const task = record.taskId ? tasks.get(record.taskId) : null;
      if (task && !isTerminal(task.state)) continue;
      const retainedSince = task?.terminalAt || record.createdAt;
      if (now - retainedSince >= TERMINAL_RETENTION) startupIdempotency.delete(key);
    }
    for (const [targetId, owner] of [...tabOwners]) {
      const task = tasks.get(owner.taskId);
      const release = tryAcquireIdleTarget(task, targetId, now);
      if (!release) continue;
      try {
        const result = await sendCDP('Target.closeTarget', { targetId });
        if (result.success !== false) removeOwnedTab(targetId);
      } catch {}
      finally { release(); }
    }
    for (const [taskId, task] of [...tasks]) {
      if (!isTerminal(task.state) || !task.terminalAt || now - task.terminalAt < TERMINAL_RETENTION) continue;
      tasks.delete(taskId);
      tokenTasks.delete(task.tokenDigest);
    }
    for (const [targetId, policy] of terminalOpeners) {
      if (policy.expiresAt <= now) terminalOpeners.delete(targetId);
    }
    for (const [id, late] of lateCommandHandlers) {
      if (late.expiresAt <= now) lateCommandHandlers.delete(id);
    }
  } finally {
    cleanupRunning = false;
  }
}

const server = http.createServer(async (req, res) => {
  let response;
  try { response = await processRequest(req); }
  catch (error) { response = errorResponse(error); }
  writeResponse(res, response);
});

function getExistingProxyHealth(port, timeoutMs = 2000) {
  return new Promise((resolve) => {
    const request = http.get(`http://127.0.0.1:${port}/health`, (response) => {
      let data = '';
      response.on('data', (chunk) => { data += chunk; });
      response.on('end', () => {
        try { resolve(JSON.parse(data)); } catch { resolve(null); }
      });
    });
    request.setTimeout(timeoutMs, () => { request.destroy(); resolve(null); });
    request.on('error', () => resolve(null));
  });
}

function isWebAccessProxy(health) {
  return health?.status === 'ok' && health?.service === 'web-access-cdp-proxy';
}

function existingBrowserId(health) {
  return health?.browser?.id || null;
}

function existingProxyMatchesBrowser(health) {
  const runningId = existingBrowserId(health);
  const requestedId = health?.requestedBrowser || null;
  if (!runningId) return false;
  if (!BROWSER_OVERRIDE) return true;
  return runningId === BROWSER_OVERRIDE && (!requestedId || requestedId === BROWSER_OVERRIDE);
}

async function main() {
  let cleanupTimer = null;
  server.once('error', async (error) => {
    if (error.code === 'EADDRINUSE') {
      const health = await getExistingProxyHealth(PORT);
      if (isWebAccessProxy(health) && health.protocolVersion !== PROTOCOL_VERSION) {
        console.error(`[CDP Proxy] LEGACY_PROXY_DETECTED on port ${PORT}; restart it explicitly to load protocol v2.`);
        process.exit(2);
      }
      const runningId = existingBrowserId(health);
      const compatible = existingProxyMatchesBrowser(health);
      if (isWebAccessProxy(health) && health.protocolVersion === PROTOCOL_VERSION && compatible) {
        console.log(`[CDP Proxy] Compatible protocol v2 proxy already runs on port ${PORT}.`);
        process.exit(0);
      }
      console.error(`[CDP Proxy] Port ${PORT} is occupied by another service or browser proxy.`);
      process.exit(1);
    }
    console.error(`[CDP Proxy] HTTP listen failed: ${error.code || error.message}`);
    process.exit(1);
  });
  server.listen(PORT, '127.0.0.1', () => {
    console.log(`[CDP Proxy] Protocol v2 listening on http://127.0.0.1:${PORT}`);
    cleanupTimer = setInterval(() => cleanupState().catch((error) => console.error('[CDP Proxy] Cleanup failed:', error.message)), CLEANUP_INTERVAL);
    cleanupTimer.unref();
    connect().catch((error) => console.error('[CDP Proxy] Initial browser connection failed:', error.message));
  });
  const shutdown = async (signal) => {
    if (shutdownStarted) return;
    shutdownStarted = true;
    console.log(`[CDP Proxy] ${signal}; releasing proxy state without closing browser tabs.`);
    if (cleanupTimer) clearInterval(cleanupTimer);
    clearLogicalOwnership();
    try { ws?.close(); } catch {}
    server.close(() => process.exit(0));
    setTimeout(() => process.exit(0), 1000).unref();
  };
  process.on('SIGINT', () => void shutdown('SIGINT'));
  process.on('SIGTERM', () => void shutdown('SIGTERM'));
}

process.on('uncaughtException', (error) => {
  console.error('[CDP Proxy] Uncaught exception:', error.message);
  process.exit(1);
});
process.on('unhandledRejection', (error) => {
  console.error('[CDP Proxy] Unhandled rejection:', error?.message || error);
  process.exit(1);
});

await main();
