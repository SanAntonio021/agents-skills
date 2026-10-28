import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import http from 'node:http';
import crypto from 'node:crypto';
import { startPageDownload, downloadUrlAllowed } from '../scripts/download-page.mjs';

const pdf = Buffer.from('%PDF-1.7\n1 0 obj <<>> endobj\n%%EOF\n');
class FileReader {
  readAsDataURL(blob) {
    blob.arrayBuffer().then(buffer => { this.result = 'data:application/pdf;base64,' + Buffer.from(buffer).toString('base64'); this.onload(); }, error => { this.error = error; this.onerror(); });
  }
}
class DOMParser {
  parseFromString(html) {
    return { querySelectorAll: () => [...html.matchAll(/(?:src|data)="([^"]+)"/g)].map(match => ({ getAttribute: key => key === 'src' ? match[1] : null })) };
  }
}
async function fixture() {
  let forbiddenHits = 0;
  const server = http.createServer((req, res) => {
    if (req.url === '/timeout') return;
    if (req.url === '/forbidden-target') forbiddenHits++;
    if (req.url.startsWith('/status/')) { res.writeHead(Number(req.url.split('/').at(-1))); return res.end('denied'); }
    if (req.url === '/redirect') { res.writeHead(302, { Location: '/ok' }); return res.end(); }
    if (req.url === '/wrapper') { res.setHeader('Content-Type', 'text/html'); return res.end('<iframe src="/ok"></iframe>'); }
    if (req.url === '/wrapper-large') { res.setHeader('Content-Type', 'text/html'); return res.end('x'.repeat(2048)); }
    if (req.url === '/html') { res.setHeader('Content-Type', 'text/html'); return res.end('<h1>Login</h1>'); }
    if (req.url === '/truncated') { res.writeHead(200, { 'Content-Type': 'application/pdf', 'Content-Length': pdf.length + 100 }); res.flushHeaders(); res.write(pdf); return setTimeout(() => res.destroy(), 10); }
    if (req.url === '/no-eof') { res.setHeader('Content-Type', 'application/pdf'); return res.end('%PDF-1.7 broken'); }
    res.setHeader('Content-Type', 'application/pdf'); res.end(pdf);
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  return { base: `http://127.0.0.1:${server.address().port}`, server, hits: () => forbiddenHits };
}
async function run(base, pathname, extra = {}, customFetch = fetch) {
  const window = {};
  const ctx = vm.createContext({ window, fetch: customFetch, URL, AbortController, setTimeout, clearTimeout,
    Uint8Array, TextDecoder, Blob, FileReader, DOMParser, crypto: crypto.webcrypto });
  const options = { key: '__job', startUrl: base + pathname, pageOrigin: base, allowedHosts: [], maxBytes: 4096, timeoutMs: 150, maxDepth: 2, ...extra };
  vm.runInContext(`(${startPageDownload.toString()})(${JSON.stringify(options)})`, ctx);
  const deadline = Date.now() + 2500;
  while (window.__job.state === 'pending' && Date.now() < deadline) await new Promise(resolve => setTimeout(resolve, 5));
  assert.notEqual(window.__job.state, 'pending');
  return window.__job;
}

test('exact origin, confirmed HTTPS host only; no scheme/port/subdomain credential widening', () => {
  const policy = { pageOrigin: 'https://publisher.test', allowedHosts: ['pdf.test'] };
  assert.equal(downloadUrlAllowed('https://publisher.test/p', policy), true);
  assert.equal(downloadUrlAllowed('https://pdf.test/p', policy), true);
  for (const url of ['http://publisher.test/p', 'https://publisher.test:444/p', 'https://sub.publisher.test/p', 'http://pdf.test/p', 'https://sub.pdf.test/p', 'https://u:p@pdf.test/p']) assert.equal(downloadUrlAllowed(url, policy), false, url);
});

test('executes the actual page download function against HTTP streams', async t => {
  const f = await fixture();
  t.after(() => { f.server.closeAllConnections(); f.server.close(); });
  for (const route of ['/ok', '/redirect', '/wrapper']) {
    const job = await run(f.base, route);
    assert.equal(job.state, 'done', route + ':' + job.code);
    assert.equal(job.bytes, pdf.length);
    assert.equal(job.sha256, crypto.createHash('sha256').update(pdf).digest('hex'));
    assert.deepEqual(Buffer.from(job.data, 'base64'), pdf);
    assert.equal(job.finalUrl, f.base + '/ok');
  }
  for (const [route, code, options] of [
    ['/html', 'not_pdf', {}], ['/wrapper-large', 'too_large', { maxBytes: 128 }],
    ['/ok', 'too_large', { maxBytes: 10 }], ['/no-eof', 'incomplete', {}],
    ['/truncated', 'incomplete', {}], ['/timeout', 'download_timeout', {}],
    ...[401, 403, 418, 429].map(status => ['/status/' + status, 'http_' + status, {}]),
  ]) {
    const job = await run(f.base, route, options);
    assert.equal(job.state, 'error', route);
    assert.equal(job.code, code, route);
    assert.equal(job.data, undefined, 'no partial bytes returned');
  }
});

test('page-side final URL revalidation rejects unexpected redirects', async () => {
  const job = await run('https://publisher.test', '/redirect', {}, async () => ({ ok: true, url: 'https://unconfirmed.test/pdf' }));
  assert.equal(job.code, 'unexpected_final_origin');
  assert.equal(job.data, undefined);
});
