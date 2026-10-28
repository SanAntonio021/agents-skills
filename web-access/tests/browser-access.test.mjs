import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import http from 'node:http';
import crypto from 'node:crypto';
import os from 'node:os';
import { EventEmitter, once } from 'node:events';
import { readFile } from 'node:fs/promises';
import { accessProbe, loginAutofillExpression } from '../scripts/browser-access.mjs';
import * as downloads from '../scripts/download-page.mjs';
import * as frames from '../scripts/page-frames.mjs';
import * as version from '../scripts/broker-version.mjs';

// Run: node --experimental-vm-modules --test --test-concurrency=1 tests/browser-access.test.mjs
// Real production functions and the complete production HTTP router execute.
// OS/runtime configuration, browser discovery, CDP transport and DOM are doubles. No browser process,
// profile, credential store, mailbox or external network endpoint is accessed.
// The in-memory module footer exposes existing symbols; it does not repair routes.
const scriptUrl = new URL('../scripts/cdp-proxy.mjs', import.meta.url);
const protectedUrls = [scriptUrl, new URL('../scripts/browser-access.mjs', import.meta.url)];
const originals = await Promise.all(protectedUrls.map(url => readFile(url)));
const fingerprint = bytes => crypto.createHash('sha256').update(bytes).digest('hex');
const records = [];
const CANARIES = ['synthetic_identity_canary', 'synthetic_password_canary',
  'synthetic_query_canary', 'synthetic_fragment_canary', 'synthetic_mail_canary'];

function record(name, layer, output, fixture, extra = {}) {
  const entry = { name, layer, output, actions: [...(fixture?.actions || [])],
    sensitiveReads: fixture?.sensitiveReads || 0, ...extra };
  records.push(entry);
  assert.equal(CANARIES.some(value => JSON.stringify(entry).includes(value)), false,
    'Fixture secret appeared in public action/result log');
  console.log('ACCESS_ACTION ' + JSON.stringify(entry));
}
function plain(value) { return JSON.parse(JSON.stringify(value)); }
function redacted(value) {
  assert.equal(CANARIES.some(secret => JSON.stringify(value).includes(secret)), false,
    'Production return value leaked a fixture secret');
  return value;
}

// Generic selector/DOM doubles implement browser primitives, not access policy.
function fixture(options = {}) {
  const actions = [];
  let sensitiveReads = 0;
  const elements = [];
  const location = new URL(options.url ||
    'https://service.example.test/login?session=synthetic_query_canary#synthetic_fragment_canary');
  function element(tagName, attrs = {}, flags = {}) {
    const e = { tagName: tagName.toUpperCase(), type: attrs.type ||
      (tagName === 'button' ? 'submit' : 'text'), name: attrs.name || '', id: attrs.id || '',
      autocomplete: attrs.autocomplete || '', disabled: !!flags.disabled,
      checked: !!flags.checked, form: null, ...flags,
      getClientRects: () => flags.hidden ? [] : [{}],
      getAttribute: key => {
        if (key === 'value') { sensitiveReads++; throw new Error('Forbidden value read'); }
        return Object.hasOwn(attrs, key) ? String(attrs[key]) : null;
      },
      matches(selector) {
        if (selector === ':-webkit-autofill' || selector === ':autofill') return !!flags.autofilled;
        return selector.split(',').some(piece => {
          const part = piece.trim();
          const tag = part.match(/^[a-z]+/i)?.[0];
          if (tag && tag.toUpperCase() !== e.tagName) return false;
          const attributes = [...part.matchAll(/\[([^\]=*]+)(\*?=)?(?:"([^"]*)"|'([^']*)'|([^\]]*))?\]/g)];
          if (part.startsWith('.') && !(attrs.class || '').split(/\s+/).includes(part.slice(1))) return false;
          return attributes.every(([, key, op, a, b, c]) => {
            if (!Object.hasOwn(attrs, key)) return false;
            if (!op) return true;
            const expected = a ?? b ?? c ?? '';
            return op === '*=' ? String(attrs[key]).includes(expected) : String(attrs[key]) === expected;
          });
        });
      },
    };
    Object.defineProperty(e, 'value', {
      get() { sensitiveReads++; throw new Error('Forbidden credential/verification value read'); },
      set() { sensitiveReads++; throw new Error('Forbidden credential/verification value write'); },
    });
    elements.push(e);
    return e;
  }
  const forms = [];
  function addLoginForm(index = 0) {
    const controls = [];
    const form = {
      method: options.method || 'post', target: options.target || '',
      getAttribute: key => key === 'action' ? (options.action || '/session') : null,
      querySelectorAll: selector => controls.filter(e => e.matches(selector)),
      requestSubmit(control) {
        if (options.submitThrows) throw new Error('Synthetic submit exception');
        const destination = new URL(control.getAttribute('formaction') || options.action || '/session', location);
        const method = control.getAttribute('formmethod') || form.method;
        const target = control.getAttribute('formtarget') || form.target;
        actions.push({ action: 'requestSubmit', method: method.toUpperCase(),
          sameOrigin: destination.origin === location.origin, https: destination.protocol === 'https:', target });
        if (options.preventSubmit || options.invalidRequired) return;
        if (options.afterSubmitText) document.body.innerText = options.afterSubmitText;
      },
    };
    function attach(e) { e.form = form; controls.push(e); return e; }
    attach(element('input', { type: 'email', name: `account${index}`, autocomplete: 'username' },
      { autofilled: options.identityFilled !== false }));
    if (options.identities === 2) attach(element('input', { type: 'text', name: 'username2' }, { autofilled: true }));
    attach(element('input', { type: 'password', name: 'password', autocomplete: 'current-password' },
      { autofilled: options.passwordFilled !== false }));
    if (options.consent !== undefined) attach(element('input', { type: 'checkbox', required: '' }, { checked: options.consent }));
    if (options.radioGroup) {
      attach(element('input', { type: 'radio', name: 'consent', required: '' }, { checked: true }));
      attach(element('input', { type: 'radio', name: 'consent', required: '' }, { checked: false }));
    }
    if (options.invalidRequired) attach(element('input', { type: 'text', name: 'department', required: '' }));
    const submitAttrs = { type: 'submit', ...(options.submitter || {}) };
    attach(element('button', submitAttrs));
    if (options.submits === 2) attach(element('button', { type: 'submit' }));
    forms.push(form);
  }
  if (options.login !== false) {
    addLoginForm();
    if (options.forms === 2) addLoginForm(1);
  }
  for (const attrs of options.extraInputs || []) element('input', attrs);
  if (options.captchaIframe) element('iframe', { src: 'https://www.google.com/recaptcha/api2/anchor' });
  const document = {
    title: options.title || (options.login === false ? 'Example service' : 'Login'),
    body: { innerText: options.text ?? (options.login === false ? 'Content available' : 'Sign in') },
    querySelectorAll: selector => elements.filter(e => e.matches(selector)),
    querySelector: selector => elements.find(e => e.matches(selector)) || null,
  };
  const context = vm.createContext({ document, location, URL });
  return { context, document, actions, forms,
    get sensitiveReads() { return sensitiveReads; },
    evaluate(expression) { return plain(vm.runInContext(expression, context, { timeout: 1000 })); },
  };
}
function probe(f) { return redacted(f.evaluate(`(${accessProbe.toString()})()`)); }
function autofill(f, submit) { return redacted(f.evaluate(loginAutofillExpression(submit))); }

async function productionProxy() {
  assert.equal(typeof vm.SourceTextModule, 'function', 'Run Node with --experimental-vm-modules');
  const reservation = http.createServer();
  reservation.listen(0, '127.0.0.1'); await once(reservation, 'listening');
  const port = reservation.address().port;
  await new Promise(resolve => reservation.close(resolve));
  const pages = new Map();
  const sessions = new Map();
  const commands = [];
  const proxyLogs = [];
  let sequence = 0;
  let server;
  let context;
  class MockWebSocket extends EventEmitter {
    static OPEN = 1;
    constructor(url) {
      super();
      assert.equal(url, 'ws://127.0.0.1:9/devtools/browser/isolated-no-network');
      this.readyState = 1;
      queueMicrotask(() => this.emit('open'));
    }
    send(payload) {
      const message = JSON.parse(payload);
      commands.push(message.method); // Deliberately never log expression values or tokens.
      queueMicrotask(() => {
        try {
          let result = {};
          const p = message.params || {};
          switch (message.method) {
            case 'Browser.getVersion': result = { product: 'IsolatedFixture/1.0' }; break;
            case 'Target.getTargets': result = { targetInfos: [...pages.keys()].map(targetId =>
              ({ targetId, type: 'page', url: 'about:blank' })) }; break;
            case 'Target.createTarget': {
              const targetId = `fixture_tab_${++sequence}`;
              pages.set(targetId, fixture({ login: false })); result = { targetId }; break;
            }
            case 'Target.attachToTarget': {
              const sessionId = `fixture_session_${++sequence}`;
              sessions.set(sessionId, p.targetId); result = { sessionId }; break;
            }
            case 'Runtime.evaluate': {
              const page = pages.get(sessions.get(message.sessionId));
              assert.ok(page, 'Evaluation must target an owned synthetic fixture');
              try { result = { result: { type: 'object', value: page.evaluate(p.expression) } }; }
              catch (error) { result = { exceptionDetails: { text: error.message } }; }
              break;
            }
            case 'Target.closeTarget': pages.delete(p.targetId); result = { success: true }; break;
            case 'Target.detachFromTarget': sessions.delete(p.sessionId); break;
            case 'Page.navigate': result = { frameId: 'fixture_frame' }; break;
            case 'Target.setDiscoverTargets': case 'Page.enable': case 'Runtime.enable':
            case 'DOM.enable': case 'Accessibility.enable': case 'Fetch.enable': break;
            default: throw new Error(`Unimplemented isolated CDP command: ${message.method}`);
          }
          this.emit('message', JSON.stringify({ id: message.id, result }));
        } catch (error) { this.emit('message', JSON.stringify({ id: message.id, error: { message: error.message } })); }
      });
    }
    close() { this.readyState = 3; }
  }
  const fakeHttp = { ...http, createServer(handler) { server = http.createServer(handler); return server; },
    get() { throw new Error('Outbound HTTP from production proxy is prohibited in this test'); } };
  context = vm.createContext({ console: { log: text => proxyLogs.push(String(text)),
    error: text => proxyLogs.push(String(text)) }, Buffer, URL, WebSocket: MockWebSocket,
    setTimeout, clearTimeout, setInterval, clearInterval, AbortController,
    process: { argv: ['node', scriptUrl.pathname, '--browser', 'edge'], env: {},
      on() {}, exit(code) { throw new Error(`Unexpected production exit ${code}`); } },
  });
  const boundaryModules = new Map([
    ['node:crypto', { default: crypto }], ['node:http', { default: fakeHttp }],
    ['node:os', { default: os }], ['node:url', { URL }],
    ['./browser-access.mjs', { accessProbe, loginAutofillExpression }],
    ['./download-page.mjs', downloads], ['./page-frames.mjs', frames], ['./broker-version.mjs', version],
    ['./runtime-config.mjs', { getProxyPort: () => port, readConfig: () => ({ WEB_ACCESS_BROWSER: 'edge' }),
      RuntimeConfigError: class RuntimeConfigError extends Error {} }],
    ['./browser-discovery.mjs', { selectBrowser: async () => ({ kind: 'ok', source: 'isolated-test',
      browser: { id: 'edge', label: 'Synthetic CDP (not Edge)', port: 9, wsPath: '/devtools/browser/isolated-no-network' } }),
      findFallbackPort: async () => { throw new Error('Real browser discovery prohibited'); } }],
  ]);
  const source = originals[0].toString('utf8');
  const module = new vm.SourceTextModule(source + '\nexport { handleBrowserAccess, connect, server };\n',
    { context, identifier: scriptUrl.href });
  await module.link(async specifier => {
    const exports = boundaryModules.get(specifier);
    assert.ok(exports, `Unexpected production dependency: ${specifier}`);
    const names = Object.keys(exports);
    const dependency = new vm.SyntheticModule(names, function () {
      for (const name of names) this.setExport(name, exports[name]);
    }, { context, identifier: specifier });
    return dependency;
  });
  await module.evaluate();
  if (!server.listening) await once(server, 'listening');
  await module.namespace.connect();
  async function post(path, body = {}, token, key = crypto.randomUUID()) {
    const response = await fetch(`http://127.0.0.1:${port}${path}`, { method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Idempotency-Key': key,
        ...(token ? { Authorization: `Bearer ${token}` } : {}) },
      body: JSON.stringify(body), signal: AbortSignal.timeout(3000) });
    return { status: response.status, body: await response.json() };
  }
  async function ownedPage(f) {
    const created = await post('/v2/tasks'); assert.equal(created.status, 201);
    const token = created.body.taskToken;
    const opened = await post('/v2/tabs', { url: 'about:blank' }, token); assert.equal(opened.status, 201);
    pages.set(opened.body.targetId, f);
    return { taskId: created.body.taskId, token, targetId: opened.body.targetId, fixture: f };
  }
  return { post, ownedPage, commands, proxyLogs,
    access: (owner, allowAutofill = true) => module.namespace.handleBrowserAccess(
      { id: owner.taskId }, owner.targetId, { allowAutofill }),
    async release(owner) {
      const result = await post(`/v2/tasks/${owner.taskId}/complete`, { keep: false }, owner.token);
      assert.equal(result.status, 200, 'Owned fixture cleanup failed: ' + JSON.stringify(result.body));
    },
    async close() {
      assert.equal(pages.size, 0, 'Owned synthetic tabs were not all closed');
      console.log('ACCESS_CLEANUP ' + JSON.stringify({ remainingOwnedTabs: pages.size }));
      server.closeAllConnections(); await new Promise(resolve => server.close(resolve));
      assert.equal(CANARIES.some(value => proxyLogs.join('\n').includes(value)), false, 'Proxy log leaked fixture data');
    },
  };
}

const normalCases = [
  ['HTTPS same-origin POST unique autofilled form', {}, 'ready'],
  ['identity not autofilled', { identityFilled: false }, 'identity_not_filled'],
  ['password not autofilled', { passwordFilled: false }, 'password_not_filled'],
  ['multiple identity/account inputs', { identities: 2 }, 'ambiguous_identity'],
  ['multiple password forms', { forms: 2 }, 'ambiguous_form'],
  ['required consent unchecked', { consent: false }, 'consent_required'],
  ['required consent checked', { consent: true }, 'ready'],
  ['HTTP rejected', { url: 'http://service.example.test/login' }, 'not_https'],
  ['cross-origin form rejected', { action: 'https://other.example.test/session' }, 'insecure_form'],
  ['GET form rejected', { method: 'get' }, 'insecure_form'],
  ['new-window form rejected', { target: '_blank' }, 'insecure_form'],
  ['multiple submit controls', { submits: 2 }, 'ambiguous_submit'],
];
for (const [name, options, status] of normalCases) {
  test(`autofill: ${name}`, () => {
    const f = fixture(options);
    const observation = autofill(f, false);
    assert.equal(observation.status, status);
    assert.equal(f.actions.length, 0, 'Probe must not submit');
    const result = autofill(f, true);
    record(name, 'actual-loginAutofillExpression', result, f);
    assert.equal(result.status, status === 'ready' ? 'submitted' : status);
    assert.equal(f.actions.length, status === 'ready' ? 1 : 0);
    assert.equal(f.sensitiveReads, 0);
    if (f.actions.length) assert.equal(f.actions[0].sameOrigin && f.actions[0].https, true);
  });
}

const verificationCases = [
  ['graphic CAPTCHA', { text: '请输入图形验证码' }, 'verification_required', 'visual_verification'],
  ['slider challenge', { text: '拖动滑块完成验证' }, 'verification_required', 'visual_verification'],
  ['reCAPTCHA iframe', { captchaIframe: true, text: 'Verification' }, 'verification_required', 'visual_verification'],
  ['email one-time code', { text: '请输入发送至邮箱的验证码 synthetic_mail_canary',
    extraInputs: [{ type: 'text', name: 'email_code', autocomplete: 'one-time-code' }] }, 'verification_required', 'email_code'],
  ['SMS code', { text: '请输入短信验证码' }, 'user_handoff_required', 'strong_authentication'],
  ['dynamic TOTP', { text: '输入动态口令', extraInputs: [{ type: 'text', name: 'totp' }] }, 'user_handoff_required', 'strong_authentication'],
  ['face verification', { text: '请刷脸进行人脸识别' }, 'user_handoff_required', 'strong_authentication'],
  ['system security prompt', { text: 'Windows Security 系统安全验证' }, 'user_handoff_required', 'strong_authentication'],
  ['access denied', { text: '403 Access denied. Automated access is forbidden.' }, 'access_denied', 'site_denied'],
  ['rate limited', { text: '429 Too many requests; rate limit exceeded.' }, 'challenge', 'site_challenge'],
  ['browser anti-bot check', { text: 'Cloudflare: Checking your browser' }, 'challenge', 'site_challenge'],
  ['ready content', { text: 'Requested content available' }, 'ready', undefined],
];
for (const [name, options, state, reason] of verificationCases) {
  test(`accessProbe: ${name}`, () => {
    const f = fixture({ login: false, ...options });
    const result = probe(f);
    record(name, 'actual-accessProbe', result, f);
    assert.equal(result.state, state); assert.equal(result.reason, reason);
    assert.equal(result.handoffRequired, state === 'user_handoff_required');
    assert.equal(f.actions.length, 0); assert.equal(f.sensitiveReads, 0);
  });
}

test('production HTTP access router and original handler (separate layers)', async t => {
  const proxy = await productionProxy();
  try {
    await t.test('public /access endpoint must reach advertised handler', async () => {
      const f = fixture(); const owner = await proxy.ownedPage(f);
      try {
        const result = await proxy.post(`/v2/tabs/${owner.targetId}/access`, { allowAutofill: true }, owner.token);
        record('public POST /access', 'actual-production-HTTP-router', result, f);
        assert.equal(result.status, 200, 'Advertised /access endpoint is unreachable');
        assert.equal(result.body.state, 'login_submitted');
      } finally { await proxy.release(owner); }
    });
    await t.test('handler submits only once and returns no credential/query data', async () => {
      const f = fixture(); const owner = await proxy.ownedPage(f);
      try {
        const first = redacted(plain(await proxy.access(owner)));
        const second = redacted(plain(await proxy.access(owner)));
        record('handler login then repeat', 'actual-original-handler-not-HTTP', { first, second }, f);
        assert.equal(first.state, 'login_submitted'); assert.equal(second.autofillStatus, 'already_attempted');
        assert.equal(f.actions.length, 1); assert.equal(f.sensitiveReads, 0);
      } finally { await proxy.release(owner); }
    });
    await t.test('explicit allowAutofill=false probes without submitting', async () => {
      const f = fixture(); const owner = await proxy.ownedPage(f);
      try {
        const result = redacted(plain(await proxy.access(owner, false)));
        record('autofill disabled', 'actual-original-handler-not-HTTP', result, f);
        assert.equal(result.state, 'auth_required'); assert.equal(f.actions.length, 0);
      } finally { await proxy.release(owner); }
    });
    await t.test('post-submit second probe sees ready content', async () => {
      const f = fixture({ afterSubmitText: 'Requested content available' });
      const originalSubmit = f.forms[0].requestSubmit;
      f.forms[0].requestSubmit = control => {
        originalSubmit(control);
        f.document.title = 'Requested content';
        f.document.querySelectorAll = () => [];
        f.document.querySelector = () => null;
      };
      const owner = await proxy.ownedPage(f);
      try {
        const submitted = redacted(plain(await proxy.access(owner)));
        const readback = redacted(plain(await proxy.access(owner)));
        record('submit then content readback', 'actual-original-handler-not-HTTP', { submitted, readback }, f);
        assert.equal(submitted.state, 'login_submitted'); assert.equal(readback.state, 'ready');
        assert.equal(f.actions.length, 1);
      } finally { await proxy.release(owner); }
    });
    for (const [name, options] of normalCases.filter(([, , status]) => status !== 'ready')) {
      await t.test(`handler respects ${name}`, async () => {
        const f = fixture(options); const owner = await proxy.ownedPage(f);
        try {
          const result = redacted(plain(await proxy.access(owner)));
          record(name, 'actual-original-handler-not-HTTP', result, f);
          assert.notEqual(result.state, 'login_submitted'); assert.equal(f.actions.length, 0);
          assert.equal(f.sensitiveReads, 0);
        } finally { await proxy.release(owner); }
      });
    }
    for (const [name, options] of verificationCases.filter(([, , state]) => state !== 'ready')) {
      await t.test(`handler does not submit on ${name}`, async () => {
        const f = fixture({ login: true, ...options }); const owner = await proxy.ownedPage(f);
        try {
          const result = redacted(plain(await proxy.access(owner)));
          record(name, 'actual-original-handler-not-HTTP', result, f);
          assert.notEqual(result.state, 'login_submitted'); assert.equal(f.actions.length, 0);
          assert.equal(f.sensitiveReads, 0);
        } finally { await proxy.release(owner); }
      });
    }
    await t.test('HTTP /eval remains a working control and endpoint failures are not broken harness', async () => {
      const f = fixture({ login: false }); const owner = await proxy.ownedPage(f);
      try {
        const result = await proxy.post(`/v2/tabs/${owner.targetId}/eval`,
          { expression: `(${accessProbe.toString()})()` }, owner.token);
        record('HTTP /eval control', 'actual-production-HTTP-router', result, f);
        assert.equal(result.status, 200); assert.equal(result.body.value.state, 'ready');
      } finally { await proxy.release(owner); }
    });
    console.log('ACCESS_CDP_COMMAND_COUNTS ' + JSON.stringify(proxy.commands.reduce((o, x) =>
      (o[x] = (o[x] || 0) + 1, o), {})));
  } finally { await proxy.close(); }
});

for (const [name, submitter] of [
  ['submitter cross-origin formaction', { formaction: 'https://other.example.test/collect' }],
  ['submitter formmethod GET', { formmethod: 'get' }],
  ['submitter formtarget new window', { formtarget: '_blank' }],
]) {
  test(`safety regression: ${name}`, () => {
    const f = fixture({ submitter }); const result = autofill(f, true);
    record(name, 'actual-loginAutofillExpression', result, f);
    assert.equal(result.status, 'insecure_form', 'Submitter overrides must not bypass form security');
    assert.equal(f.actions.length, 0, 'Unsafe form must never submit');
  });
}
test('consent regression: valid required radio group with one selected', () => {
  const f = fixture({ radioGroup: true }); const result = autofill(f, false);
  record('valid radio consent group', 'actual-loginAutofillExpression', result, f);
  assert.equal(result.status, 'ready', 'A selected radio group already meets required consent');
});
test('priority regression: explicit anti-bot denial containing CAPTCHA', () => {
  const f = fixture({ login: false, text: '403 Access denied: automated access forbidden. CAPTCHA challenge failed.' });
  const result = probe(f); record('denied plus CAPTCHA', 'actual-accessProbe', result, f);
  assert.equal(result.state, 'access_denied', 'An explicit access denial remains a site denial even when CAPTCHA text is present');
});
test('classification regression: optional passkey link on ordinary autofilled login', () => {
  const f = fixture({ text: 'Sign in with password. Alternatively use a passkey.' });
  const result = probe(f); record('password login with optional passkey', 'actual-accessProbe', result, f);
  assert.equal(result.state, 'auth_required', 'Optional alternative must not be classified as active strong auth');
});

test.after(async () => {
  for (let i = 0; i < protectedUrls.length; i++) {
    assert.equal(fingerprint(await readFile(protectedUrls[i])), fingerprint(originals[i]),
      'Production source changed while independent tests ran');
  }
  console.log('ACCESS_SOURCE_UNCHANGED ' + JSON.stringify(protectedUrls.map((url, i) =>
    ({ file: url.pathname.split('/').at(-1), sha256: fingerprint(originals[i]) }))));
  console.log('ACCESS_TOTAL_RECORDED_ACTIONS ' + JSON.stringify({ scenarios: records.length,
    submits: records.reduce((n, r) => n + r.actions.length, 0),
    sensitiveReads: records.reduce((n, r) => n + r.sensitiveReads, 0),
    actualBrowserUsed: false, actualMailboxUsed: false, realCredentialsUsed: false }));
});