import crypto from 'node:crypto';
import http from 'node:http';

const WS_GUID = '258EAFA5-E914-47DA-95CA-C5AB0DC85B11';
const ONE_PIXEL_PNG = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9Z5ZkAAAAASUVORK5CYII=';

function encodeTextFrame(value) {
  const payload = Buffer.from(JSON.stringify(value));
  let header;
  if (payload.length < 126) {
    header = Buffer.from([0x81, payload.length]);
  } else if (payload.length <= 0xffff) {
    header = Buffer.alloc(4);
    header[0] = 0x81;
    header[1] = 126;
    header.writeUInt16BE(payload.length, 2);
  } else {
    header = Buffer.alloc(10);
    header[0] = 0x81;
    header[1] = 127;
    header.writeBigUInt64BE(BigInt(payload.length), 2);
  }
  return Buffer.concat([header, payload]);
}

function readFrames(state, chunk, onText) {
  state.buffer = Buffer.concat([state.buffer, chunk]);
  while (state.buffer.length >= 2) {
    const first = state.buffer[0];
    const second = state.buffer[1];
    const opcode = first & 0x0f;
    const masked = Boolean(second & 0x80);
    let length = second & 0x7f;
    let offset = 2;

    if (length === 126) {
      if (state.buffer.length < 4) return;
      length = state.buffer.readUInt16BE(2);
      offset = 4;
    } else if (length === 127) {
      if (state.buffer.length < 10) return;
      length = Number(state.buffer.readBigUInt64BE(2));
      offset = 10;
    }

    const maskLength = masked ? 4 : 0;
    if (state.buffer.length < offset + maskLength + length) return;
    const mask = masked ? state.buffer.subarray(offset, offset + 4) : null;
    offset += maskLength;
    const payload = Buffer.from(state.buffer.subarray(offset, offset + length));
    state.buffer = state.buffer.subarray(offset + length);

    if (mask) {
      for (let i = 0; i < payload.length; i++) payload[i] ^= mask[i % 4];
    }
    if (opcode === 0x1) onText(payload.toString('utf8'));
    if (opcode === 0x8) return;
  }
}

function axProperty(name, value, type = 'boolean') {
  return { name, value: { type, value } };
}

function createDocumentState(browserId, targetId) {
  return {
    generation: 1,
    title: 'Mock Page',
    text: 'Mock page Ready Submit Remember Choice',
    focusedBackendNodeId: null,
    selectAll: false,
    dialog: null,
    elements: new Map([
      [101, { role: 'textbox', name: 'Name', value: '', tag: 'INPUT', visible: true, enabled: true, obscured: false }],
      [102, { role: 'button', name: 'Submit', value: '', tag: 'BUTTON', visible: true, enabled: true, obscured: false }],
      [103, { role: 'checkbox', name: 'Remember', value: false, tag: 'INPUT', visible: true, enabled: true, obscured: false }],
      [104, { role: 'combobox', name: 'Choice', value: 'one', tag: 'SELECT', visible: true, enabled: true, obscured: false, multiple: false }],
      [105, { role: 'textbox', name: 'Notes', value: '', tag: 'DIV', visible: true, enabled: true, obscured: false, contentEditable: true }],
      [106, { role: 'combobox', name: 'Multi Choice', value: ['one'], tag: 'SELECT', visible: true, enabled: true, obscured: false, multiple: true }],
    ]),
    frameId: `${browserId}-frame-${targetId}`,
  };
}

function createAxNodes(targetId, document) {
  const prefix = `${targetId}-ax-${document.generation}`;
  const childIds = [...document.elements.keys()].map((backendId) => `${prefix}-${backendId}`);
  const nodes = [{
    nodeId: `${prefix}-root`,
    ignored: false,
    role: { type: 'role', value: 'RootWebArea' },
    name: { type: 'computedString', value: document.title },
    backendDOMNodeId: 1,
    childIds,
  }];
  for (const [backendDOMNodeId, element] of document.elements) {
    const properties = [
      axProperty('focusable', true),
      axProperty('disabled', !element.enabled),
      axProperty('hidden', !element.visible),
    ];
    if (element.role === 'checkbox') properties.push(axProperty('checked', element.value, 'tristate'));
    nodes.push({
      nodeId: `${prefix}-${backendDOMNodeId}`,
      ignored: false,
      role: { type: 'role', value: element.role },
      name: { type: 'computedString', value: element.name },
      value: { type: typeof element.value === 'boolean' ? 'boolean' : 'computedString', value: element.value },
      backendDOMNodeId,
      parentId: `${prefix}-root`,
      childIds: [],
      properties,
    });
  }
  return nodes;
}

export async function startMockCdpServer(browserId, options = {}) {
  const targets = new Map();
  const documents = new Map();
  const sessions = new Map();
  const commands = [];
  const sockets = new Set();
  let targetSequence = 0;
  let sessionSequence = 0;
  let popupSequence = 0;
  let totalConnections = 0;
  let activeTargetId = null;
  const commandDelays = options.commandDelays || {};

  if (options.includeUserTarget !== false) {
    const targetId = `${browserId}-user-target`;
    targets.set(targetId, {
      targetId,
      type: 'page',
      title: 'Existing User Tab',
      url: 'https://user-existing.test/',
      attached: false,
    });
    documents.set(targetId, createDocumentState(browserId, targetId));
  }

  function sessionTarget(sessionId) {
    return sessions.get(sessionId) || null;
  }

  function targetDocument(sessionId, explicitTargetId = null) {
    const targetId = explicitTargetId || sessionTarget(sessionId);
    return targetId ? documents.get(targetId) : null;
  }

  function send(socket, message) {
    if (!socket.destroyed) socket.write(encodeTextFrame(message));
  }

  function broadcast(message) {
    for (const socket of sockets) send(socket, message);
  }

  function emit(method, params = {}, sessionId = null) {
    const event = { method, params };
    if (sessionId) event.sessionId = sessionId;
    broadcast(event);
  }

  function removeTarget(targetId, deferEvent = false) {
    targets.delete(targetId);
    documents.delete(targetId);
    for (const [sid, attachedTargetId] of sessions) {
      if (attachedTargetId === targetId) sessions.delete(sid);
    }
    const notify = () => emit('Target.targetDestroyed', { targetId });
    if (deferEvent) queueMicrotask(notify);
    else notify();
  }

  function elementFromObjectId(objectId) {
    const match = /^node:(.+):(\d+)$/.exec(objectId || '');
    if (!match) return null;
    const targetId = match[1];
    const backendDOMNodeId = Number(match[2]);
    const document = documents.get(targetId);
    const element = document?.elements.get(backendDOMNodeId);
    return element ? { targetId, backendDOMNodeId, document, element } : null;
  }

  function evaluateExpression(expression, sessionId) {
    const targetId = sessionTarget(sessionId);
    const target = targets.get(targetId);
    const document = documents.get(targetId);
    if (expression.includes('never-appears')) return false;
    if (expression.includes('document.readyState') && expression.includes('===')) {
      if (expression.includes('interactive')) return true;
      return expression.includes('complete');
    }
    if (expression === 'document.readyState' || expression.includes('document.readyState')) return 'complete';
    if (expression === 'document.title') return document?.title || 'Mock Page';
    if (expression === 'location.href' || expression === 'document.URL') return target?.url || 'about:blank';
    if (expression.includes('JSON.stringify({title:')) {
      return JSON.stringify({ title: document?.title || 'Mock Page', url: target?.url || 'about:blank', ready: 'complete' });
    }
    if (expression.includes('getBoundingClientRect')) {
      return { x: 10, y: 10, width: 100, height: 30, tag: 'BUTTON', text: 'Mock' };
    }
    if (expression.includes('document.querySelector')) {
      if (expression.includes('?.click') || expression.includes('.click()')) {
        return { clicked: true, tag: 'BUTTON', text: 'Mock' };
      }
      return true;
    }
    if (expression.includes('document.body') && (expression.includes('innerText') || expression.includes('textContent'))) {
      if (expression.includes('.includes(')) return !expression.includes('Missing');
      return document?.text || '';
    }
    if (expression.includes('location.href')) return target?.url || 'about:blank';
    return 'mock-result';
  }

  function callFunction(params) {
    const resolved = elementFromObjectId(params.objectId);
    if (!resolved) return { result: { type: 'undefined' } };
    const { document, element, backendDOMNodeId } = resolved;
    const source = params.functionDeclaration || '';
    const args = (params.arguments || []).map((arg) => arg.value);

    if (source.includes('getBoundingClientRect') || source.includes('isConnected')) {
      return {
        result: {
          type: 'object',
          value: {
            ok: element.visible && element.enabled && !element.obscured,
            attached: true,
            visible: element.visible,
            enabled: element.enabled,
            disabled: !element.enabled,
            unobscured: !element.obscured,
            obscured: Boolean(element.obscured),
            x: 10,
            y: 10,
            width: 100,
            height: 30,
            tag: element.tag,
            tagName: element.tag,
            type: element.role === 'checkbox' ? 'checkbox' : '',
            contentEditable: Boolean(element.contentEditable),
            value: element.value,
            checked: element.role === 'checkbox' ? element.value : undefined,
          },
        },
      };
    }
    if (source.includes('.focus')) {
      document.focusedBackendNodeId = backendDOMNodeId;
      return { result: { type: 'boolean', value: true } };
    }
    if (source.includes("'value' in this") || source.includes('this.isContentEditable')) {
      return { result: { type: typeof element.value, value: element.value } };
    }
    if (source.includes('HTMLInputElement') && source.includes("['checkbox', 'radio']")) {
      return { result: { type: 'object', value: { supported: element.role === 'checkbox', checked: Boolean(element.value) } } };
    }
    if (source.includes('return Boolean(this.checked)')) {
      return { result: { type: 'boolean', value: Boolean(element.value) } };
    }
    if (source.includes('HTMLSelectElement')) {
      const values = Array.isArray(args[0]) ? args[0].map(String) : [];
      const selected = element.multiple ? values : values.slice(0, 1);
      element.value = element.multiple ? selected : (selected[0] || '');
      return { result: { type: 'object', value: { supported: element.role === 'combobox', multiple: Boolean(element.multiple), selected } } };
    }
    if (source.includes('.click')) element.clicked = true;
    if (source.includes('checked')) element.value = source.includes('false') ? false : (args[0] ?? true);
    if (source.includes('value')) {
      const nextValue = args.find((arg) => typeof arg === 'string');
      if (nextValue !== undefined) element.value = nextValue;
    }
    if (source.includes('selected')) {
      const nextValue = args.find((arg) => typeof arg === 'string' || Array.isArray(arg));
      if (nextValue !== undefined) element.value = nextValue;
    }
    return { result: { type: 'object', value: { ok: true, value: element.value, checked: element.value } } };
  }

  function resultFor(message) {
    const { method, params = {}, sessionId } = message;
    commands.push({ method, params, sessionId: sessionId || null });

    switch (method) {
      case 'Target.setDiscoverTargets':
      case 'Target.setAutoAttach':
      case 'Page.enable':
      case 'Runtime.enable':
      case 'DOM.enable':
      case 'Accessibility.enable':
      case 'Fetch.enable':
      case 'DOM.scrollIntoViewIfNeeded':
      case 'Runtime.releaseObject':
        return {};
      case 'Target.getTargets':
        return { targetInfos: [...targets.values()] };
      case 'Target.getTargetInfo':
        return { targetInfo: targets.get(params.targetId) };
      case 'Target.createTarget': {
        const targetId = `${browserId}-target-${++targetSequence}`;
        const targetInfo = {
          targetId,
          type: 'page',
          title: 'Mock Page',
          url: params.url || 'about:blank',
          attached: false,
        };
        targets.set(targetId, targetInfo);
        documents.set(targetId, createDocumentState(browserId, targetId));
        queueMicrotask(() => emit('Target.targetCreated', { targetInfo }));
        return { targetId };
      }
      case 'Target.attachToTarget': {
        const newSessionId = `${browserId}-session-${++sessionSequence}`;
        sessions.set(newSessionId, params.targetId);
        const targetInfo = targets.get(params.targetId);
        if (targetInfo) targetInfo.attached = true;
        return { sessionId: newSessionId };
      }
      case 'Target.activateTarget':
        activeTargetId = params.targetId;
        return {};
      case 'Target.closeTarget': {
        const targetId = params.targetId;
        removeTarget(targetId, true);
        return { success: true };
      }
      case 'Page.navigate': {
        const targetId = sessionTarget(sessionId);
        const target = targets.get(targetId);
        if (target) target.url = params.url;
        const frameId = documents.get(targetId)?.frameId || `${browserId}-frame`;
        queueMicrotask(() => {
          emit('Page.frameNavigated', { frame: { id: frameId, url: params.url } }, sessionId);
          emit('Page.domContentEventFired', { timestamp: Date.now() / 1000 }, sessionId);
          emit('Page.loadEventFired', { timestamp: Date.now() / 1000 }, sessionId);
        });
        return { frameId };
      }
      case 'Page.getNavigationHistory':
        return { currentIndex: 1, entries: [{ id: 1, url: 'https://example.test/previous' }, { id: 2, url: targets.get(sessionTarget(sessionId))?.url }] };
      case 'Page.navigateToHistoryEntry':
        return {};
      case 'Runtime.evaluate':
        return { result: { type: 'object', value: evaluateExpression(params.expression || '', sessionId) } };
      case 'Runtime.callFunctionOn':
        return callFunction(params);
      case 'Accessibility.getFullAXTree':
      case 'Accessibility.getPartialAXTree':
      case 'Accessibility.queryAXTree': {
        const targetId = sessionTarget(sessionId);
        const document = documents.get(targetId);
        return { nodes: document ? createAxNodes(targetId, document) : [] };
      }
      case 'DOM.getDocument':
        return { root: { nodeId: 1, backendNodeId: 1, nodeName: '#document' } };
      case 'DOM.querySelector':
        return { nodeId: 101 };
      case 'DOM.describeNode': {
        const targetId = sessionTarget(sessionId);
        const document = documents.get(targetId);
        const element = document?.elements.get(params.backendNodeId);
        return {
          node: {
            nodeId: params.nodeId || params.backendNodeId || 1,
            backendNodeId: params.backendNodeId || 1,
            nodeName: element?.tag || 'DIV',
            localName: (element?.tag || 'div').toLowerCase(),
            nodeType: 1,
            attributes: [],
            frameId: document?.frameId,
          },
        };
      }
      case 'DOM.resolveNode': {
        const targetId = sessionTarget(sessionId);
        const backendDOMNodeId = params.backendNodeId || params.nodeId;
        return { object: { type: 'object', subtype: 'node', objectId: `node:${targetId}:${backendDOMNodeId}` } };
      }
      case 'DOM.getBoxModel':
        return { model: { content: [10, 10, 110, 10, 110, 40, 10, 40], width: 100, height: 30 } };
      case 'DOM.getContentQuads':
        return { quads: [[10, 10, 110, 10, 110, 40, 10, 40]] };
      case 'DOM.getNodeForLocation':
        return { backendNodeId: 102, frameId: targetDocument(sessionId)?.frameId };
      case 'DOM.focus': {
        const document = targetDocument(sessionId);
        if (document) document.focusedBackendNodeId = params.backendNodeId || params.nodeId;
        return {};
      }
      case 'DOM.setFileInputFiles':
        return {};
      case 'Input.insertText': {
        const document = targetDocument(sessionId);
        const element = document?.elements.get(document.focusedBackendNodeId);
        if (element) {
          element.value = document.selectAll ? (params.text || '') : `${element.value || ''}${params.text || ''}`;
          document.selectAll = false;
        }
        return {};
      }
      case 'Input.dispatchKeyEvent': {
        const document = targetDocument(sessionId);
        const element = document?.elements.get(document.focusedBackendNodeId);
        if (document && params.type === 'rawKeyDown' && params.code === 'KeyA' && params.modifiers) document.selectAll = true;
        if (element && params.type === 'keyDown' && params.text) element.value = `${element.value || ''}${params.text}`;
        return {};
      }
      case 'Input.dispatchMouseEvent': {
        if (params.type === 'mouseReleased') {
          const document = targetDocument(sessionId);
          const element = document?.elements.get(document.focusedBackendNodeId);
          if (element?.role === 'checkbox') element.value = !element.value;
        }
        return {};
      }
      case 'Page.captureScreenshot':
        return { data: ONE_PIXEL_PNG };
      case 'Page.handleJavaScriptDialog': {
        const document = targetDocument(sessionId);
        const targetId = sessionTarget(sessionId);
        const nextDialog = document?.nextDialog || null;
        if (document) {
          document.dialog = null;
          document.nextDialog = null;
        }
        emit('Page.javascriptDialogClosed', { result: Boolean(params.accept), userInput: params.promptText || '' }, sessionId);
        if (document && nextDialog) {
          document.dialog = nextDialog;
          emit('Page.javascriptDialogOpening', {
            url: targets.get(targetId)?.url,
            type: nextDialog.type,
            message: nextDialog.message,
            defaultPrompt: nextDialog.defaultPrompt || '',
          }, sessionId);
        }
        return {};
      }
      default:
        return {};
    }
  }

  const server = http.createServer((req, res) => {
    res.statusCode = 404;
    res.end();
  });

  server.on('upgrade', (req, socket) => {
    const key = req.headers['sec-websocket-key'];
    const accept = crypto.createHash('sha1').update(`${key}${WS_GUID}`).digest('base64');
    socket.write([
      'HTTP/1.1 101 Switching Protocols',
      'Upgrade: websocket',
      'Connection: Upgrade',
      `Sec-WebSocket-Accept: ${accept}`,
      '',
      '',
    ].join('\r\n'));

    totalConnections++;
    sockets.add(socket);
    const state = { buffer: Buffer.alloc(0) };
    socket.on('data', (chunk) => {
      readFrames(state, chunk, (text) => {
        const message = JSON.parse(text);
        const result = resultFor(message);
        const delayMs = Number(commandDelays[message.method] || 0);
        if (delayMs > 0) setTimeout(() => send(socket, { id: message.id, result }), delayMs);
        else send(socket, { id: message.id, result });
      });
    });
    socket.on('close', () => sockets.delete(socket));
    socket.on('error', () => sockets.delete(socket));
  });

  await new Promise((resolve, reject) => {
    server.once('error', reject);
    server.listen(0, '127.0.0.1', resolve);
  });

  const port = server.address().port;
  return {
    browserId,
    port,
    targets,
    documents,
    commands,
    get activeTargetId() { return activeTargetId; },
    get totalConnections() { return totalConnections; },
    createPopup(openerId, url = 'https://popup.test/', { delayMs = 0, emitEvent = true } = {}) {
      const targetId = `${browserId}-popup-${++popupSequence}`;
      const targetInfo = {
        targetId,
        type: 'page',
        title: 'Mock Popup',
        url,
        openerId,
        attached: false,
      };
      const create = () => {
        targets.set(targetId, targetInfo);
        documents.set(targetId, createDocumentState(browserId, targetId));
        if (emitEvent) emit('Target.targetCreated', { targetInfo });
      };
      if (delayMs > 0) setTimeout(create, delayMs);
      else create();
      return targetId;
    },
    destroyTarget(targetId) {
      removeTarget(targetId, false);
    },
    openDialog(targetId, { type = 'confirm', message = 'Continue?', defaultPrompt = '' } = {}) {
      const document = documents.get(targetId);
      if (!document) throw new Error(`未知 target: ${targetId}`);
      document.dialog = { type, message, defaultPrompt };
      const sessionId = [...sessions].find(([, attachedTargetId]) => attachedTargetId === targetId)?.[0] || null;
      emit('Page.javascriptDialogOpening', { url: targets.get(targetId)?.url, type, message, defaultPrompt }, sessionId);
    },
    queueDialogAfterHandle(targetId, { type = 'confirm', message = 'Next dialog', defaultPrompt = '' } = {}) {
      const document = documents.get(targetId);
      if (!document) throw new Error(`未知 target: ${targetId}`);
      document.nextDialog = { type, message, defaultPrompt };
    },
    redraw(targetId) {
      const document = documents.get(targetId);
      if (!document) throw new Error(`未知 target: ${targetId}`);
      document.generation++;
      emit('DOM.documentUpdated', {}, [...sessions].find(([, attachedTargetId]) => attachedTargetId === targetId)?.[0] || null);
    },
    setElementState(targetId, backendDOMNodeId, patch) {
      const element = documents.get(targetId)?.elements.get(backendDOMNodeId);
      if (!element) throw new Error(`unknown element: ${targetId}/${backendDOMNodeId}`);
      Object.assign(element, patch);
    },
    setText(targetId, text) {
      const document = documents.get(targetId);
      if (!document) throw new Error(`未知 target: ${targetId}`);
      document.text = text;
    },
    disconnectAll() {
      for (const socket of sockets) socket.destroy();
    },
    async close() {
      for (const socket of sockets) socket.destroy();
      await new Promise((resolve) => server.close(resolve));
    },
  };
}
