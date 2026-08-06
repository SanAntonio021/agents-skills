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

export async function startMockCdpServer(browserId) {
  const targets = new Map();
  const sessions = new Map();
  const commands = [];
  const sockets = new Set();
  let targetSequence = 0;
  let sessionSequence = 0;
  let totalConnections = 0;

  function resultFor(message) {
    const { method, params = {}, sessionId } = message;
    commands.push({ method, params, sessionId: sessionId || null });

    switch (method) {
      case 'Target.getTargets':
        return { targetInfos: [...targets.values()] };
      case 'Target.createTarget': {
        const targetId = `${browserId}-target-${++targetSequence}`;
        targets.set(targetId, { targetId, type: 'page', title: 'Mock Page', url: params.url });
        return { targetId };
      }
      case 'Target.attachToTarget': {
        const newSessionId = `${browserId}-session-${++sessionSequence}`;
        sessions.set(newSessionId, params.targetId);
        return { sessionId: newSessionId };
      }
      case 'Target.closeTarget':
        targets.delete(params.targetId);
        return { success: true };
      case 'Page.navigate': {
        const targetId = sessions.get(sessionId);
        const target = targets.get(targetId);
        if (target) target.url = params.url;
        return { frameId: `${browserId}-frame` };
      }
      case 'Runtime.evaluate': {
        const expression = params.expression || '';
        if (expression === 'document.readyState') return { result: { value: 'complete' } };
        if (expression.includes('JSON.stringify({title:')) {
          return { result: { value: JSON.stringify({ title: 'Mock Page', url: 'https://example.test/', ready: 'complete' }) } };
        }
        if (expression.includes('getBoundingClientRect')) {
          return { result: { value: { x: 10, y: 10, tag: 'BUTTON', text: 'Mock' } } };
        }
        if (expression.includes('document.querySelector')) {
          return { result: { value: { clicked: true, tag: 'BUTTON', text: 'Mock' } } };
        }
        return { result: { value: expression === 'document.title' ? 'Mock Page' : 'mock-result' } };
      }
      case 'DOM.getDocument':
        return { root: { nodeId: 1 } };
      case 'DOM.querySelector':
        return { nodeId: 2 };
      case 'Page.captureScreenshot':
        return { data: ONE_PIXEL_PNG };
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
        socket.write(encodeTextFrame({ id: message.id, result: resultFor(message) }));
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
    commands,
    get totalConnections() { return totalConnections; },
    async close() {
      for (const socket of sockets) socket.destroy();
      await new Promise((resolve) => server.close(resolve));
    },
  };
}
