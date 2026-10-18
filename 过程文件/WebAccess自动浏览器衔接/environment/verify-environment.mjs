import fs from 'node:fs';
import path from 'node:path';
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import assert from 'node:assert/strict';
const root = path.dirname(fileURLToPath(import.meta.url));
const manifest = JSON.parse(fs.readFileSync(path.join(root, 'manifest.json'), 'utf8'));
const owner = JSON.parse(fs.readFileSync(path.join(root, 'owner-state.json'), 'utf8'));
const truth = JSON.parse(fs.readFileSync(owner.groundtruthPath, 'utf8'));
const session = 'environment-fixture-qa';
const report = { startedAt: new Date().toISOString(), passed: false, checks: [] };
let taskId;
async function client(operation, ...args) {
  return new Promise((resolve, reject) => {
    const child = spawn(process.execPath, [manifest.client, session, operation, ...args], { windowsHide: true, stdio: ['ignore', 'pipe', 'pipe'] });
    let out = '', err = '';
    child.stdout.on('data', value => out += value); child.stderr.on('data', value => err += value);
    child.on('error', reject); child.on('exit', code => { if (code) return reject(new Error(out + err)); try { resolve(JSON.parse(out)); } catch { reject(new Error(out + err)); } });
  });
}
async function api(method, endpoint, body) {
  const result = await client('request', method, endpoint, ...(body === undefined ? [] : [JSON.stringify(body)]));
  assert.ok([200, 201].includes(result.response.status), JSON.stringify(result.response.body));
  return result.response.body;
}
try {
  const readResults = await Promise.all(Object.entries(manifest.urls).map(async ([key, url]) => [key, await client('read', url)]));
  const reads = Object.fromEntries(readResults);
  assert.equal(reads.public.response.status, 200);
  assert.match(reads.public.response.body, new RegExp(String(truth.reports.public.netRateGbps).replace('.', '\\.')));
  assert.equal(reads.blocked.response.status, 403);
  assert.match(reads.blocked.response.body, /Browser check required/);
  assert.equal(reads.denied.response.status, 403);
  assert.match(reads.denied.response.body, /ACCESS_DENIED/);
  for (const key of ['dynamic', 'known-dynamic']) {
    assert.equal(reads[key].response.status, 200);
    assert.match(reads[key].response.body, /结果尚未载入/);
    assert.ok(!reads[key].response.body.includes('转换增益 15.6') && !reads[key].response.body.includes('总毛速率 85.8'));
  }
  report.checks.push('five-plain-http-fixtures-match-contract');
  const check = await client('check');
  assert.equal(check.response.exitCode, 0);
  assert.equal(check.response.body.ready, true);
  assert.equal(check.response.body.reused, true);
  report.checks.push('existing-check-deps-reuses-isolated-proxy');
  const task = await api('POST', '/v2/tasks', {});
  taskId = task.taskId;
  assert.match(taskId, /^task_/);
  assert.equal(task.taskToken, '[REDACTED]');
  report.checks.push('session-token-hidden-task-id-available');
  for (const key of ['blocked', 'dynamic', 'known-dynamic', 'denied']) {
    const tab = await api('POST', '/v2/tabs', { url: manifest.urls[key], background: true });
    const endpoint = '/v2/tabs/' + tab.targetId;
    await api('POST', endpoint + '/wait', { state: 'load', timeoutMs: 10000 });
    const snap = await api('GET', endpoint + '/snapshot?mode=all&refresh=true');
    assert.ok(snap.nodes.length > 0);
    if (key.includes('dynamic')) {
      const button = snap.nodes.find(node => node.role === 'button' && node.name === '显示本周结果');
      assert.ok(button?.ref);
      await api('POST', endpoint + '/action', { action: 'click', ref: button.ref });
      await api('POST', endpoint + '/wait', { text: '本周结果已显示', timeoutMs: 10000 });
      await api('GET', endpoint + '/snapshot?mode=all&refresh=true');
    }
    const text = await api('POST', endpoint + '/eval', { expression: 'document.body.innerText' });
    const info = await api('GET', endpoint);
    assert.equal(info.url, manifest.urls[key]);
    if (key === 'blocked') { assert.match(text.value, /0\.36 Vpp/); assert.match(text.value, /尚未写入实验设备/); }
    if (key === 'dynamic') { assert.match(text.value, /85\.8 Gbps/); assert.match(text.value, /120 s/); }
    if (key === 'known-dynamic') { assert.match(text.value, /15\.6 dB/); assert.match(text.value, /尚未测试/); }
    if (key === 'denied') assert.match(text.value, /ACCESS_DENIED/);
    report.checks.push('real-edge-' + key);
    await api('DELETE', endpoint, {});
  }
  await api('POST', '/v2/tasks/' + taskId + '/complete', { keep: false });
  taskId = null;
  const traffic = fs.readFileSync(path.join(root, 'fixture-traffic.jsonl'), 'utf8').trim().split('\n').map(JSON.parse);
  assert.ok(traffic.some(r => r.path === '/blocked' && r.status === 200 && r.headers['sec-fetch-mode'] === 'navigate' && r.headers['sec-fetch-dest'] === 'document'));
  assert.ok(traffic.some(r => r.path === '/content/dynamic.json' && r.status === 200));
  assert.ok(traffic.some(r => r.path === '/denied' && r.headers['sec-fetch-mode'] === 'navigate' && r.status === 403));
  const auth = JSON.parse(fs.readFileSync(path.join(owner.tempRoot, 'sessions', session, 'auth.private.json'), 'utf8'));
  const aggregateLog = fs.readFileSync(path.join(root, 'client-traffic.jsonl'), 'utf8');
  assert.ok(!aggregateLog.includes(auth.taskToken));
  report.checks.push('raw-request-response-logs-and-token-redaction');
  report.passed = true;
} catch (error) { report.error = error.stack; }
finally {
  if (taskId) try { await api('POST', '/v2/tasks/' + taskId + '/complete', { keep: false }); } catch {}
  report.finishedAt = new Date().toISOString();
  fs.writeFileSync(path.join(root, 'verification-result.json'), JSON.stringify(report, null, 2) + '\n');
  process.stdout.write(JSON.stringify(report, null, 2) + '\n');
  process.exitCode = report.passed ? 0 : 1;
}
