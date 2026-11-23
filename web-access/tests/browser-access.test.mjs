import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import http from 'node:http';
import crypto from 'node:crypto';
import os from 'node:os';
import { EventEmitter, once } from 'node:events';
import { readFile } from 'node:fs/promises';
import { accessProbe, loginAutofillExpression, loginFormProgram } from '../scripts/browser-access.mjs';
import * as downloads from '../scripts/download-page.mjs';
import * as frames from '../scripts/page-frames.mjs';
import * as version from '../scripts/broker-version.mjs';
import * as federated from '../scripts/federated-access.mjs';

// Run: node --experimental-vm-modules --test --test-concurrency=1 tests/browser-access.test.mjs
// Real production functions and the complete production HTTP router execute.
// OS/runtime configuration, browser discovery, CDP transport and DOM are doubles. No browser process,
// profile, credential store, mailbox or external network endpoint is accessed.
// The in-memory module footer exposes existing symbols; it does not repair routes.
// Keeps the federated provider loader away from any real local override file.
process.env.WEB_ACCESS_TEST_MODE = '1';
const scriptUrl = new URL('../scripts/cdp-proxy.mjs', import.meta.url);
const protectedUrls = [scriptUrl, new URL('../scripts/browser-access.mjs', import.meta.url),
  new URL('../scripts/login-credentials.mjs', import.meta.url)];
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
  // Values written by the credential helper. Kept out of `actions`/records so a
  // leak into any public log or return value is detectable via CANARIES.
  const written = new Map();
  const pendingRequests = [];
  const location = new URL(options.url ||
    'https://service.example.test/login?session=synthetic_query_canary#synthetic_fragment_canary');
  function element(tagName, attrs = {}, flags = {}) {
    const e = { tagName: tagName.toUpperCase(), type: attrs.type ||
      (tagName === 'button' ? 'submit' : 'text'), name: attrs.name || '', id: attrs.id || '',
      autocomplete: attrs.autocomplete || '', disabled: !!flags.disabled,
      checked: !!flags.checked, form: null, ...flags, innerText: flags.text,
      click() {
        actions.push({ action: 'click', tag: tagName });
        if (typeof flags.onClick === 'function') flags.onClick();
      },
      getClientRects: () => flags.hidden ? [] : [{}],
      getAttribute: key => {
        // Only explicitly public value attributes (e.g. consent radio values) are readable.
        if (key === 'value' && !Object.hasOwn(attrs, 'value')) { sensitiveReads++; throw new Error('Forbidden value read'); }
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
      set(value) {
        if (!options.allowCredentialWrite) { sensitiveReads++; throw new Error('Forbidden credential/verification value write'); }
        written.set(e.name || e.type, String(value));
        actions.push({ action: 'setValue', field: e.type === 'password' ? 'password' : 'identity' });
      },
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
        pendingRequests.push({ url: destination.href, method: method.toUpperCase(), resourceType: 'Document',
          postData: `password=${encodeURIComponent(written.get('password') || '')}` });
        if (options.afterSubmitText) document.body.innerText = options.afterSubmitText;
        if (typeof options.onSubmitted === 'function') options.onSubmitted();
      },
    };
    function attach(e) { e.form = form; controls.push(e); return e; }
    attach(element('input', { type: 'email', name: `account${index}`, autocomplete: 'username' },
      { autofilled: options.identityFilled !== false }));
    if (options.identities === 2) attach(element('input', { type: 'text', name: 'username2' }, { autofilled: true }));
    attach(element('input', { type: 'password', name: 'password', autocomplete: 'current-password' },
      { autofilled: options.passwordFilled !== false }));
    if (options.rememberMe) attach(element('input', { type: 'checkbox', name: 'rememberMe' }, { checked: false }));
    if (options.consent !== undefined) attach(element('input', { type: 'checkbox', required: '' }, { checked: options.consent }));
    if (options.radioGroup) {
      attach(element('input', { type: 'radio', name: 'consent', required: '' }, { checked: true }));
      attach(element('input', { type: 'radio', name: 'consent', required: '' }, { checked: false }));
    }
    if (options.invalidRequired) attach(element('input', { type: 'text', name: 'department', required: '' }));
    if (options.scriptSubmit) {
      // Script-owned login: an <a> that the page's JS turns into a submission.
      attach(element('a', { href: 'javascript:void(0)', id: 'login_submit' }, { text: options.scriptLabel || '登录',
        onClick() {
          const secret = written.get('password') || '';
          for (const request of options.scriptRequests || [{ url: '/session', method: 'POST', resourceType: 'Document' }]) {
            const url = new URL(request.url.replace('{secret}', encodeURIComponent(secret)), location).href;
            pendingRequests.push({ ...request, url,
              postData: request.method === 'GET' ? undefined : `pwd=${encodeURIComponent(secret)}` });
          }
          if (typeof options.onSubmitted === 'function') options.onSubmitted();
        } }));
    } else {
      const submitAttrs = { type: 'submit', ...(options.submitter || {}) };
      attach(element('button', submitAttrs));
    }
    if (options.submits === 2) attach(element('button', { type: 'submit' }));
    forms.push(form);
  }
  if (options.login !== false) {
    addLoginForm();
    if (options.forms === 2) addLoginForm(1);
  }
  if (options.consent) {
    // Shibboleth-style attribute-release form (structure only; values are
    // synthetic and must never reach a public result).
    const c = options.consent;
    const controls = [];
    const consentForm = element('form', { action: c.action || '/idp/profile/SAML2/Redirect/SSO?execution=e1s2' }, {
      method: c.method || 'post', target: '',
      querySelectorAll: selector => controls.filter(node => node.matches(selector)),
      requestSubmit(control) {
        actions.push({ action: 'consentSubmit', accept: control.getAttribute('name') || control.innerText || 'accept',
          remember: controls.filter(node => node.type === 'radio' && node.checked).map(node => node.getAttribute('value')) });
        pendingRequests.push({ url: new URL(c.action || '/idp/profile/SAML2/Redirect/SSO?execution=e1s2', location).href,
          method: 'POST', resourceType: 'Document' });
        if (typeof options.onSubmitted === 'function') options.onSubmitted();
      } });
    const add = node => { controls.push(node); return node; };
    for (const item of c.attributes || []) {
      const cell = { innerText: item.label || '' };
      const valueCell = { innerText: item.value || 'synthetic value' };
      const row = add(element('tr', {}, { text: `${item.label || ''} ${item.value || 'synthetic value'}`,
        querySelectorAll: selector => selector === 'td' ? [cell, valueCell] : [],
        querySelector: () => cell }));
      if (item.id !== undefined && c.consentIds !== false) {
        add(element('input', { type: 'hidden', name: '_shib_idp_consentIds' }, { hidden: true, consentId: item.id, closest: () => row }));
      }
    }
    for (const option of c.options || []) {
      add(element('input', { type: c.optionType || 'radio', name: c.optionName || '_shib_idp_consentOptions', value: option.value },
        { checked: !!option.checked, labels: [{ innerText: option.label }] }));
    }
    add(element('input', { type: 'submit', name: '_eventId_AttributeReleaseRejected' }, { defaultValue: c.rejectLabel || 'Reject' }));
    if (c.accept !== false) add(element('input', { type: 'submit', name: c.acceptName || '_eventId_proceed' }, { defaultValue: c.acceptLabel || 'Accept' }));
  }
  for (const { hidden, ...attrs } of options.extraInputs || []) element('input', attrs, { hidden: !!hidden });
  for (const item of options.extraElements || []) element(item.tag, item.attrs || {}, { text: item.text, hidden: !!item.hidden });
  if (options.captchaIframe) element('iframe', { src: options.captchaIframeSrc || 'https://www.google.com/recaptcha/api2/anchor' });
  const document = {
    title: options.title || (options.login === false ? 'Example service' : 'Login'),
    body: { innerText: options.text ?? (options.login === false ? 'Content available' : 'Sign in') },
    querySelectorAll: selector => elements.filter(e => e.matches(selector)),
    querySelector: selector => elements.find(e => e.matches(selector)) || null,
  };
  const context = vm.createContext({ document, location, URL });
  return { context, document, actions, forms, location, written, pendingRequests,
    get sensitiveReads() { return sensitiveReads; },
    evaluate(expression) { return plain(vm.runInContext(expression, context, { timeout: 1000 })); },
    call(functionDeclaration, args) {
      const fn = vm.runInContext(`(${functionDeclaration})`, context, { timeout: 1000 });
      return plain(fn(...args));
    },
  };
}
function probe(f) { return redacted(f.evaluate(`(${accessProbe.toString()})()`)); }
function autofill(f, submit, options) { return redacted(f.evaluate(loginAutofillExpression(submit, options))); }
function credentialProgram(f, options) {
  return redacted(f.call(loginFormProgram.toString(), [{ mode: 'credential', allowScriptSubmit: true,
    expectedOrigin: f.location.origin, ...options }]));
}
// Synthetic OS credential store double. Real Windows Credential Manager access
// is exercised only by login-credential.ps1 -Action SelfTest.
const credentialStore = { entries: new Map(), calls: [] };
async function readLoginCredentialStub(origin, account) {
  credentialStore.calls.push({ origin, account: account || null });
  const list = credentialStore.entries.get(origin) || [];
  const chosen = account ? list.find(item => item.account === account) : (list.length === 1 ? list[0] : null);
  if (account && !chosen) return { status: 'account_not_configured' };
  if (!list.length) return { status: 'not_configured' };
  if (!chosen) return { status: 'account_ambiguous' };
  return { status: 'ok', account: chosen.account, secret: chosen.secret };
}

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
  const fetchDecisions = [];
  const pausedRequests = [];
  let sequence = 0;
  let server;
  let context;
  let socketRef = null;
  const emitEvent = message => socketRef?.emit('message', JSON.stringify(message));
  class MockWebSocket extends EventEmitter {
    static OPEN = 1;
    constructor(url) {
      super();
      socketRef = this;
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
              if (p.returnByValue === false && p.expression === 'globalThis') {
                result = { result: { type: 'object', objectId: 'fixture_global' } }; break;
              }
              try { result = { result: { type: 'object', value: page.evaluate(p.expression) } }; }
              catch (error) { result = { exceptionDetails: { text: error.message } }; }
              break;
            }
            case 'Runtime.callFunctionOn': {
              const page = pages.get(sessions.get(message.sessionId));
              assert.ok(page, 'Call must target an owned synthetic fixture');
              assert.equal(p.objectId, 'fixture_global');
              assert.equal(p.functionDeclaration, loginFormProgram.toString(),
                'Only the reviewed login program may receive a credential argument');
              try { result = { result: { type: 'object', value: page.call(p.functionDeclaration, p.arguments.map(a => a.value)) } }; }
              catch (error) { result = { exceptionDetails: { text: 'synthetic exception' } }; }
              break;
            }
            case 'Target.getTargetInfo': {
              const page = pages.get(p.targetId);
              result = { targetInfo: { targetId: p.targetId, type: 'page', url: page?.location?.href || 'about:blank' } }; break;
            }
            case 'Fetch.continueRequest': case 'Fetch.failRequest':
              fetchDecisions.push({ requestId: p.requestId, decision: message.method === 'Fetch.continueRequest' ? 'continue' : 'fail' });
              break;
            case 'Runtime.releaseObject': break;
            case 'Target.closeTarget': pages.delete(p.targetId); result = { success: true }; break;
            case 'Target.detachFromTarget': sessions.delete(p.sessionId); break;
            case 'Page.navigate': result = { frameId: 'fixture_frame' }; break;
            case 'Target.setDiscoverTargets': case 'Page.enable': case 'Runtime.enable':
            case 'DOM.enable': case 'Accessibility.enable': case 'Fetch.enable': break;
            default: throw new Error(`Unimplemented isolated CDP command: ${message.method}`);
          }
          this.emit('message', JSON.stringify({ id: message.id, result }));
          // Requests a synthetic page started during this command reach the
          // Broker as Fetch.requestPaused events, as Chromium would send them.
          const page = message.sessionId ? pages.get(sessions.get(message.sessionId)) : null;
          for (const request of page?.pendingRequests?.splice(0) || []) {
            const requestId = `fixture_request_${++sequence}`;
            pausedRequests.push({ requestId, method: request.method, resourceType: request.resourceType,
              sameOrigin: new URL(request.url).origin === page.location.origin });
            this.emit('message', JSON.stringify({ method: 'Fetch.requestPaused', sessionId: message.sessionId,
              params: { requestId, frameId: sessions.get(message.sessionId), resourceType: request.resourceType,
                request: { url: request.url, method: request.method, ...(request.postData ? { postData: request.postData } : {}) } } }));
          }
          // A page chain advanced: report the navigation like Chromium does.
          if (page?.pendingNavigation) {
            const url = page.pendingNavigation; page.pendingNavigation = null;
            const targetId = sessions.get(message.sessionId);
            this.emit('message', JSON.stringify({ method: 'Target.targetInfoChanged', params: { targetInfo: { targetId, type: 'page', url, title: '' } } }));
            this.emit('message', JSON.stringify({ method: 'Page.frameNavigated', sessionId: message.sessionId, params: { frame: { id: targetId, url } } }));
            this.emit('message', JSON.stringify({ method: 'Page.loadEventFired', sessionId: message.sessionId, params: {} }));
          }
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
    process: { argv: ['node', scriptUrl.pathname, '--browser', 'edge'],
      env: { WEB_ACCESS_LOGIN_GUARD_MS: '300', WEB_ACCESS_ACCESS_SETTLE_MS: '600', WEB_ACCESS_TEST_MODE: '1' },
      on() {}, exit(code) { throw new Error(`Unexpected production exit ${code}`); } },
  });
  const boundaryModules = new Map([
    ['node:crypto', { default: crypto }], ['node:http', { default: fakeHttp }],
    ['node:os', { default: os }], ['node:url', { URL }],
    ['./browser-access.mjs', { accessProbe, loginAutofillExpression, loginFormProgram }],
    ['./federated-access.mjs', federated],
    ['./login-credentials.mjs', { readLoginCredential: readLoginCredentialStub,
      credentialStoreInfo: () => ({ store: 'synthetic-double', key: 'origin+account' }) }],
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
  return { post, ownedPage, commands, proxyLogs, fetchDecisions, pausedRequests,
    // Record that this tab visited `url` before the page under test.
    visit: (owner, url) => emitEvent({ method: 'Target.targetInfoChanged',
      params: { targetInfo: { targetId: owner.targetId, type: 'page', url, title: '' } } }),
    access: (owner, allowAutofill = true, extra = {}) => module.namespace.handleBrowserAccess(
      { id: owner.taskId }, owner.targetId, { allowAutofill, ...extra }),
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

// --- Active-form classification: switch entries are not requirements ---------
const uestcLikeText = '统一身份认证\n账号登录\n验证码登录\n扫码登录\n请输入学号/工号\n7天免登录\n忘记密码\n登录\n微信扫码';
const activeFormCases = [
  ['verification-code login tab beside active account form', {
    text: uestcLikeText,
    extraElements: [{ tag: 'a', attrs: { role: 'tab' }, text: '验证码登录' }, { tag: 'li', text: '扫码登录' }],
    extraInputs: [{ type: 'text', name: 'captcha', placeholder: '请输入验证码', hidden: true },
      { type: 'text', name: 'dynamicCode', placeholder: '请输入短信验证码', hidden: true }] }, 'auth_required', 'login'],
  ['inline SMS-code tab label on one line', { text: '账号登录  短信验证码登录  扫码登录\n登录',
    extraElements: [{ tag: 'span', text: '短信验证码登录' }] }, 'auth_required', 'login'],
  ['English one-time-code sign-in link', { text: 'Sign in\nSign in with a one-time code\nForgot password?' }, 'auth_required', 'login'],
  ['help text mentioning SMS login is not an instruction', { text: '账号登录\n忘记密码？也可使用短信验证码找回' }, 'auth_required', 'login'],
  ['invisible reCAPTCHA badge does not block', { captchaIframe: true,
    captchaIframeSrc: 'https://www.google.com/recaptcha/api2/anchor?k=x&size=invisible' }, 'auth_required', 'login'],
  ['visible captcha input in the active form', { text: uestcLikeText + '\n请输入验证码',
    extraInputs: [{ type: 'text', name: 'captcha', placeholder: '验证码' }] }, 'verification_required', 'visual_verification'],
  ['visible code input in the active form', { text: '登录\n验证码',
    extraInputs: [{ type: 'text', name: 'code', placeholder: '请输入验证码' }] }, 'verification_required', 'verification_method_unresolved'],
  ['explicit SMS instruction on a password page', { text: '登录\n请输入短信验证码' }, 'user_handoff_required', 'strong_authentication'],
  ['active SMS form without password', { login: false, text: '账号登录\n短信验证码登录\n请输入手机号',
    extraInputs: [{ type: 'tel', name: 'mobile' }, { type: 'text', name: 'smsCode', placeholder: '短信验证码' }] },
    'user_handoff_required', 'strong_authentication'],
];
for (const [name, options, state, reason] of activeFormCases) {
  test(`accessProbe active form: ${name}`, () => {
    const f = fixture({ identityFilled: true, passwordFilled: false, ...options });
    const result = probe(f);
    record(name, 'actual-accessProbe', result, f);
    assert.equal(result.state, state); assert.equal(result.reason, reason);
    assert.equal(f.actions.length, 0); assert.equal(f.sensitiveReads, 0);
  });
}

// --- Script-submitted forms and the credential program ----------------------
test('script-submitted login needs explicit opt-in and is clicked, not requestSubmit', () => {
  const f = fixture({ scriptSubmit: true });
  assert.equal(autofill(f, false).status, 'ambiguous_submit', 'Without the Broker guard no script click is allowed');
  const ready = autofill(f, false, { allowScriptSubmit: true });
  assert.equal(ready.status, 'ready'); assert.equal(ready.submitMode, 'script');
  const result = autofill(f, true, { allowScriptSubmit: true });
  record('script submit autofill', 'actual-loginAutofillExpression', result, f);
  assert.equal(result.status, 'submitted');
  assert.deepEqual(f.actions, [{ action: 'click', tag: 'a' }]);
});
test('script-submitted GET form is rejected for browser autofill', () => {
  const f = fixture({ scriptSubmit: true, method: 'get' });
  assert.equal(autofill(f, true, { allowScriptSubmit: true }).status, 'insecure_form');
  assert.equal(f.actions.length, 0);
});
test('script button with cross-origin href is rejected', () => {
  const f = fixture({ scriptSubmit: true });
  f.forms[0].querySelectorAll('a')[0].getAttribute = key => key === 'href' ? 'https://other.example.test/login' : null;
  assert.equal(autofill(f, true, { allowScriptSubmit: true }).status, 'insecure_form');
});
test('credential program writes only into the verified form and never reads values', () => {
  const f = fixture({ allowCredentialWrite: true, identityFilled: true, passwordFilled: false, rememberMe: true });
  const check = credentialProgram(f, { submit: false });
  assert.equal(check.status, 'ready');
  assert.equal(f.actions.length, 0, 'Readiness check must not write');
  const result = credentialProgram(f, { submit: true, account: 'synthetic_identity_canary', secret: 'synthetic_password_canary' });
  record('credential program submit', 'actual-loginFormProgram', result, f);
  assert.equal(result.status, 'submitted');
  assert.equal(f.written.get('password'), 'synthetic_password_canary');
  assert.equal(f.written.get('account0'), 'synthetic_identity_canary');
  assert.equal(f.sensitiveReads, 0);
  const remember = f.forms[0].querySelectorAll('input[type="checkbox"]')[0];
  assert.equal(remember.checked, false, 'Optional remember-me / 7-day boxes stay unchecked');
});
test('credential program refuses an unexpected origin, HTTP and missing secret', () => {
  const f = fixture({ allowCredentialWrite: true });
  assert.equal(credentialProgram(f, { submit: true, expectedOrigin: 'https://other.example.test',
    secret: 'synthetic_password_canary' }).status, 'origin_mismatch');
  assert.equal(credentialProgram(f, { submit: true }).status, 'credential_missing');
  const plainHttp = fixture({ allowCredentialWrite: true, url: 'http://service.example.test/login' });
  assert.equal(credentialProgram(plainHttp, { submit: true, secret: 'synthetic_password_canary' }).status, 'not_https');
  assert.equal(f.written.size + plainHttp.written.size, 0);
});

// --- Broker handler: Edge autofill first, OS credential helper as fallback ---
const ORIGIN = 'https://service.example.test';
test('production handler: credential helper fallback and network guard', async t => {
  const proxy = await productionProxy();
  const withStore = async (entries, fn) => {
    credentialStore.entries = new Map(entries); credentialStore.calls = [];
    try { await fn(); } finally { credentialStore.entries = new Map(); }
  };
  try {
    await t.test('Edge account picker (password not filled) uses the stored credential in the background tab', async () => {
      await withStore([[ORIGIN, [{ account: 'synthetic_identity_canary', secret: 'synthetic_password_canary' }]]], async () => {
        const f = fixture({ allowCredentialWrite: true, identityFilled: true, passwordFilled: false, text: uestcLikeText,
          extraElements: [{ tag: 'a', attrs: { role: 'tab' }, text: '验证码登录' }], rememberMe: true });
        const owner = await proxy.ownedPage(f);
        try {
          const result = await proxy.post(`/v2/tabs/${owner.targetId}/access`, { allowAutofill: true }, owner.token);
          record('credential helper via HTTP', 'actual-production-HTTP-router', result, f);
          assert.equal(result.status, 200);
          assert.equal(result.body.state, 'login_submitted');
          assert.equal(result.body.loginMethod, 'credential_helper');
          assert.equal(result.body.autofillStatus, 'password_not_filled');
          assert.equal(result.body.credentialStatus, 'submitted');
          assert.equal(result.body.networkGuard.navigated, true);
          assert.equal(f.written.get('password'), 'synthetic_password_canary');
          assert.deepEqual(credentialStore.calls, [{ origin: ORIGIN, account: null }]);
          assert.equal(proxy.commands.includes('Target.activateTarget'), false, 'Must not activate the tab or steal focus');
          const repeat = redacted(plain(await proxy.access(owner)));
          assert.equal(repeat.credentialStatus, 'already_attempted');
          assert.equal(f.actions.filter(a => a.action === 'requestSubmit').length, 1, 'Never replays a login');
        } finally { await proxy.release(owner); }
      });
    });
    await t.test('browser autofill keeps priority; the store is not consulted', async () => {
      await withStore([[ORIGIN, [{ account: 'synthetic_identity_canary', secret: 'synthetic_password_canary' }]]], async () => {
        const f = fixture(); const owner = await proxy.ownedPage(f);
        try {
          const result = redacted(plain(await proxy.access(owner)));
          assert.equal(result.loginMethod, 'browser_autofill'); assert.equal(result.state, 'login_submitted');
          assert.equal(credentialStore.calls.length, 0);
        } finally { await proxy.release(owner); }
      });
    });
    for (const [name, entries, extra, status] of [
      ['not configured', [], {}, 'not_configured'],
      ['several accounts, none chosen', [[ORIGIN, [{ account: 'a1', secret: 'synthetic_password_canary' },
        { account: 'a2', secret: 'synthetic_password_canary' }]]], {}, 'account_ambiguous'],
      ['chosen account not stored', [[ORIGIN, [{ account: 'a1', secret: 'synthetic_password_canary' }]]], { account: 'a3' }, 'account_not_configured'],
    ]) {
      await t.test(`no submit when ${name}`, async () => {
        await withStore(entries, async () => {
          const f = fixture({ allowCredentialWrite: true, passwordFilled: false }); const owner = await proxy.ownedPage(f);
          try {
            const result = redacted(plain(await proxy.access(owner, true, extra)));
            record(name, 'actual-original-handler-not-HTTP', result, f);
            assert.equal(result.state, 'auth_required'); assert.equal(result.credentialStatus, status);
            assert.equal(f.actions.length, 0); assert.equal(f.written.size, 0);
          } finally { await proxy.release(owner); }
        });
      });
    }
    await t.test('allowCredentialHelper:false never reads the store', async () => {
      await withStore([[ORIGIN, [{ account: 'a1', secret: 'synthetic_password_canary' }]]], async () => {
        const f = fixture({ allowCredentialWrite: true, passwordFilled: false }); const owner = await proxy.ownedPage(f);
        try {
          const result = redacted(plain(await proxy.access(owner, true, { allowCredentialHelper: false })));
          assert.equal(result.autofillStatus, 'password_not_filled'); assert.equal(credentialStore.calls.length, 0);
          assert.equal(f.actions.length, 0);
        } finally { await proxy.release(owner); }
      });
    });
    await t.test('verification tab on the page does not stop the account login', async () => {
      await withStore([[ORIGIN, [{ account: 'a1', secret: 'synthetic_password_canary' }]]], async () => {
        const f = fixture({ allowCredentialWrite: true, passwordFilled: false, scriptSubmit: true, text: uestcLikeText,
          extraElements: [{ tag: 'a', attrs: { role: 'tab' }, text: '验证码登录' }],
          extraInputs: [{ type: 'text', name: 'captcha', placeholder: '请输入验证码', hidden: true }] });
        const owner = await proxy.ownedPage(f);
        try {
          const result = redacted(plain(await proxy.access(owner)));
          record('UESTC-like script login', 'actual-original-handler-not-HTTP', result, f);
          assert.equal(result.state, 'login_submitted'); assert.equal(result.submitMode, 'script');
          assert.equal(result.networkGuard.navigated, true);
        } finally { await proxy.release(owner); }
      });
    });
    for (const [name, requests] of [
      ['cross-origin POST carrying the secret', [{ url: 'https://other.example.test/collect', method: 'POST', resourceType: 'XHR' }]],
      ['same-origin GET with the secret in the URL', [{ url: '/session?pwd={secret}', method: 'GET', resourceType: 'Document' }]],
      ['cross-origin top-level POST navigation', [{ url: 'https://other.example.test/session', method: 'POST', resourceType: 'Document' }]],
    ]) {
      await t.test(`network guard blocks ${name}`, async () => {
        await withStore([[ORIGIN, [{ account: 'a1', secret: 'synthetic_password_canary' }]]], async () => {
          const f = fixture({ allowCredentialWrite: true, passwordFilled: false, scriptSubmit: true, scriptRequests: requests });
          const owner = await proxy.ownedPage(f);
          const decisionsBefore = proxy.fetchDecisions.length;
          try {
            const result = redacted(plain(await proxy.access(owner)));
            record(name, 'actual-original-handler-not-HTTP', result, f);
            assert.equal(result.credentialStatus, 'blocked_by_network_guard');
            assert.notEqual(result.state, 'login_submitted');
            assert.equal(result.networkGuard.credentialRequestBlocked, true);
            assert.deepEqual(proxy.fetchDecisions.slice(decisionsBefore).map(d => d.decision), ['fail']);
          } finally { await proxy.release(owner); }
        });
      });
    }
    await t.test('cross-origin GET assets are allowed; guard ends at the same-origin navigation', async () => {
      await withStore([[ORIGIN, [{ account: 'a1', secret: 'synthetic_password_canary' }]]], async () => {
        const f = fixture({ allowCredentialWrite: true, passwordFilled: false, scriptSubmit: true, scriptRequests: [
          { url: 'https://cdn.example.test/app.js', method: 'GET', resourceType: 'Script' },
          { url: '/session', method: 'POST', resourceType: 'Document' }] });
        const owner = await proxy.ownedPage(f);
        const decisionsBefore = proxy.fetchDecisions.length;
        try {
          const result = redacted(plain(await proxy.access(owner)));
          assert.equal(result.state, 'login_submitted'); assert.equal(result.networkGuard.blockedRequests, 0);
          assert.deepEqual(proxy.fetchDecisions.slice(decisionsBefore).map(d => d.decision), ['continue', 'continue']);
        } finally { await proxy.release(owner); }
      });
    });
    assert.equal(CANARIES.some(value => proxy.proxyLogs.join('\n').includes(value)), false);
  } finally { await proxy.close(); }
});

// --- SAML / Shibboleth attribute-release consent and the full login chain ----
const SP_URL = 'https://ieeexplore.ieee.org/Xplore/home.jsp';
const IDP_URL = 'https://idp-lib.uestc.edu.cn/idp/profile/SAML2/Redirect/SSO?execution=e1s2';
const CAS_URL = 'https://idas.uestc.edu.cn/authserver/login?service=https%3A%2F%2Fidp-lib.uestc.edu.cn%2Fidp';
const SHIB_OPTIONS = [
  { value: '_shib_idp_doNotRememberConsent', label: 'Ask me again at next login', checked: true },
  { value: '_shib_idp_rememberConsent', label: 'Ask me again if information to be provided to this service changes' },
  { value: '_shib_idp_globalConsent', label: 'Do not ask me again' },
];
function consentFixture({ attributes, spName = 'IEEE Xplore', url = IDP_URL, extra = {}, consent = {} } = {}) {
  return fixture({ login: false, url, title: 'Information Release',
    text: `You are about to access the service: ${spName}\nInformation to be Provided to Service`,
    consent: { attributes: attributes || [
      { id: 'eduPersonScopedAffiliation', label: '身份类别', value: 'member@uestc.edu.cn' },
      { id: 'o', label: '所属机构', value: '电子科技大学' }], options: SHIB_OPTIONS, ...consent }, ...extra });
}
function pageChain() {
  const pages = [];
  const c = { pages, index: 0, pendingNavigation: null,
    get current() { return pages[c.index]; },
    get location() { return c.current.location; },
    get pendingRequests() { return pages.flatMap(page => page.pendingRequests.splice(0)); },
    get actions() { return pages.flatMap(page => page.actions); },
    get sensitiveReads() { return pages.reduce((n, page) => n + page.sensitiveReads, 0); },
    evaluate: expression => c.current.evaluate(expression),
    call: (fn, args) => c.current.call(fn, args),
    advance() { if (c.index < pages.length - 1) { c.index++; c.pendingNavigation = c.current.location.href; } },
  };
  return c;
}

test('consent classification: only non-personal categories are auto-releasable', () => {
  const policy = ['affiliation', 'organization', 'pseudonymous_id'];
  assert.equal(federated.classifyReleaseAttributes([{ label: '身份类别' }, { label: '所属机构' }], policy).autoConsent, true);
  assert.equal(federated.classifyReleaseAttributes([{ id: 'eduPersonTargetedID' }, { id: 'schacHomeOrganization' }], policy).autoConsent, true);
  for (const [attribute, category] of [[{ id: 'mail' }, 'email'], [{ label: '姓名' }, 'name'], [{ id: 'uid', label: '学号' }, 'person_id'],
    [{ id: 'mobile' }, 'phone'], [{ id: 'eduPersonPrincipalName' }, 'person_id'], [{ id: 'o', label: '姓名' }, 'name'],
    [{ id: 'customThing', label: '所属机构' }, 'unknown'], [{ id: 'eduPersonEntitlement' }, 'entitlement']]) {
    const result = federated.classifyReleaseAttributes([{ id: 'eduPersonScopedAffiliation' }, attribute], policy);
    assert.equal(result.autoConsent, false, JSON.stringify(attribute));
    assert.ok(result.blocked.includes(category), `${JSON.stringify(attribute)} -> ${JSON.stringify(result)}`);
  }
  const providers = federated.loadFederatedProviders({ localFile: null });
  assert.deepEqual(providers.autoConsentCategories, policy);
  for (const id of ['ieee', 'elsevier', 'springer-nature', 'wiley', 'acm', 'iop', 'optica'])
    assert.ok(providers.serviceProviders.some(entry => entry.id === id), id);
});

test('production handler: attribute-release consent and the SP -> IdP -> CAS -> SP chain', async t => {
  const proxy = await productionProxy();
  const consentOwner = async (f, history = [SP_URL]) => {
    const owner = await proxy.ownedPage(f);
    for (const url of history) proxy.visit(owner, url);
    await new Promise(resolve => setTimeout(resolve, 20));
    return owner;
  };
  try {
    await t.test('institutional attributes for IEEE: accept and remember for this service only', async () => {
      const f = consentFixture(); const owner = await consentOwner(f);
      try {
        const result = await proxy.post(`/v2/tabs/${owner.targetId}/access`, { allowAutofill: true }, owner.token);
        record('consent auto accept', 'actual-production-HTTP-router', result, f);
        assert.equal(result.status, 200);
        assert.equal(result.body.state, 'attribute_consent_submitted');
        assert.deepEqual(result.body.consent, { serviceProvider: 'ieee', attributeCategories: ['affiliation', 'organization'], rememberMode: 'service' });
        const submit = f.actions.find(a => a.action === 'consentSubmit');
        assert.equal(submit.accept, '_eventId_proceed');
        assert.ok(submit.remember.includes('_shib_idp_rememberConsent'));
        assert.ok(!submit.remember.includes('_shib_idp_globalConsent'), 'Never choose global consent');
        assert.ok(!JSON.stringify(result.body).includes('member@uestc.edu.cn'), 'Attribute values never leave the page');
        assert.equal(f.sensitiveReads, 0);
      } finally { await proxy.release(owner); }
    });
    await t.test('label-only rows (身份类别 / 所属机构) are also accepted', async () => {
      const f = consentFixture({ consent: { consentIds: false } }); const owner = await consentOwner(f);
      try {
        const result = redacted(plain(await proxy.access(owner)));
        assert.equal(result.state, 'attribute_consent_submitted');
      } finally { await proxy.release(owner); }
    });
    for (const [name, attributes, category] of [
      ['email requested', [{ id: 'eduPersonScopedAffiliation', label: '身份类别' }, { id: 'mail', label: '邮箱', value: 'synthetic_mail_canary' }], 'email'],
      ['name requested', [{ label: '身份类别' }, { label: '姓名', value: 'synthetic_identity_canary' }], 'name'],
      ['student number requested', [{ id: 'uid', label: '学号', value: 'synthetic_identity_canary' }], 'person_id'],
    ]) {
      await t.test(`stops and hands over when ${name}`, async () => {
        const f = consentFixture({ attributes }); const owner = await consentOwner(f);
        try {
          const result = redacted(plain(await proxy.access(owner)));
          record(name, 'actual-original-handler-not-HTTP', result, f);
          assert.equal(result.state, 'attribute_consent_required');
          assert.equal(result.failureCode, 'attribute_consent_required');
          assert.equal(result.reason, 'personal_attributes');
          assert.equal(result.handoffRequired, true);
          assert.ok(result.blockedCategories.includes(category));
          assert.equal(f.actions.length, 0);
        } finally { await proxy.release(owner); }
      });
    }
    await t.test('stops when the SP is not on the list', async () => {
      const f = consentFixture({ spName: 'Example Vendor Portal' }); const owner = await consentOwner(f, ['https://vendor.example.test/']);
      try {
        const result = redacted(plain(await proxy.access(owner)));
        assert.equal(result.reason, 'sp_unverified'); assert.equal(f.actions.length, 0);
      } finally { await proxy.release(owner); }
    });
    await t.test('stops when the SP name matches but the tab never came from that SP', async () => {
      const f = consentFixture(); const owner = await consentOwner(f, ['https://vendor.example.test/']);
      try {
        const result = redacted(plain(await proxy.access(owner)));
        assert.equal(result.reason, 'sp_unverified'); assert.equal(f.actions.length, 0);
      } finally { await proxy.release(owner); }
    });
    await t.test('stops when the attribute list cannot be parsed', async () => {
      const f = consentFixture({ attributes: [{ id: undefined, label: '' }], consent: { consentIds: false } });
      const owner = await consentOwner(f);
      try {
        const result = redacted(plain(await proxy.access(owner)));
        assert.equal(result.reason, 'attributes_unparsed'); assert.equal(f.actions.length, 0);
      } finally { await proxy.release(owner); }
    });
    await t.test('only a global "never ask" option: accept without remembering', async () => {
      const f = consentFixture({ consent: { options: [{ value: '_shib_idp_globalConsent', label: 'Do not ask me again' }] } });
      const owner = await consentOwner(f);
      try {
        const result = redacted(plain(await proxy.access(owner)));
        assert.equal(result.state, 'attribute_consent_submitted');
        assert.equal(result.consent.rememberMode, 'global_only_skipped');
        assert.deepEqual(f.actions.find(a => a.action === 'consentSubmit').remember, []);
      } finally { await proxy.release(owner); }
    });
    await t.test('allowAutofill:false only observes an eligible consent page', async () => {
      const f = consentFixture(); const owner = await consentOwner(f);
      try {
        const result = redacted(plain(await proxy.access(owner, false)));
        assert.equal(result.reason, 'observe_only'); assert.equal(result.handoffRequired, false);
        assert.equal(result.consentEligible, true); assert.equal(f.actions.length, 0);
      } finally { await proxy.release(owner); }
    });
    for (const order of ['consent-then-password', 'password-then-consent']) {
      await t.test(`maxSteps chain ${order} reaches the SP`, async () => {
        credentialStore.entries = new Map([['https://idas.uestc.edu.cn', [{ account: 'a1', secret: 'synthetic_password_canary' }]]]);
        credentialStore.calls = [];
        const c = pageChain();
        const advance = () => c.advance();
        const consentPage = consentFixture({ extra: { onSubmitted: advance } });
        const passwordPage = fixture({ url: CAS_URL, allowCredentialWrite: true, passwordFilled: false, scriptSubmit: true,
          text: uestcLikeText, extraElements: [{ tag: 'a', attrs: { role: 'tab' }, text: '验证码登录' }], onSubmitted: advance,
          scriptRequests: [{ url: '/authserver/login', method: 'POST', resourceType: 'Document' }] });
        const spPage = fixture({ login: false, url: 'https://ieeexplore.ieee.org/document/123', text: 'Access provided by: UESTC' });
        c.pages.push(...(order === 'consent-then-password' ? [consentPage, passwordPage] : [passwordPage, consentPage]), spPage);
        const owner = await consentOwner(c);
        try {
          const result = await proxy.post(`/v2/tabs/${owner.targetId}/access`, { allowAutofill: true, maxSteps: 4 }, owner.token);
          record(`chain ${order}`, 'actual-production-HTTP-router', result, c);
          assert.equal(result.status, 200, JSON.stringify(result.body));
          assert.equal(result.body.state, 'ready', JSON.stringify(result.body));
          const states = result.body.steps.map(step => step.state);
          assert.deepEqual(states, order === 'consent-then-password'
            ? ['attribute_consent_submitted', 'login_submitted', 'ready']
            : ['login_submitted', 'attribute_consent_submitted', 'ready']);
          assert.equal(c.index, 2, 'The chain ended on the service provider page');
          assert.equal(passwordPage.written.get('password'), 'synthetic_password_canary');
          assert.deepEqual(credentialStore.calls, [{ origin: 'https://idas.uestc.edu.cn', account: null }]);
          assert.equal(proxy.commands.includes('Target.activateTarget'), false);
        } finally { await proxy.release(owner); credentialStore.entries = new Map(); }
      });
    }
    assert.equal(CANARIES.some(value => proxy.proxyLogs.join('\n').includes(value)), false);
  } finally { await proxy.close(); }
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