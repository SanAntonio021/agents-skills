import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import http from 'node:http';
import net from 'node:net';
import { spawn } from 'node:child_process';
import { randomUUID, createHash } from 'node:crypto';
import { fileURLToPath } from 'node:url';

const outputRoot = path.dirname(fileURLToPath(import.meta.url));
const skillRoot = 'D:/BaiduSyncdisk/.agents/skills/web-access';
const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'web-access-behavior-'));
const unavailableRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'web-access-unavailable-'));
const localAppData = path.join(tempRoot, 'LocalAppData');
const edgeUserData = path.join(localAppData, 'Microsoft', 'Edge', 'User Data');
fs.mkdirSync(edgeUserData, { recursive: true });
fs.mkdirSync(path.join(unavailableRoot, 'LocalAppData'), { recursive: true });
fs.mkdirSync(path.join(tempRoot, 'sessions'), { recursive: true });
const privateRoot = path.join(tempRoot, 'private');
fs.mkdirSync(privateRoot);
let edgeProcess, proxyProcess, fixtureServer, controlServer, browserWebSocketUrl;
let stopping = false;
const delay = ms => new Promise(r => setTimeout(r, ms));
const save = (name, value) => fs.writeFileSync(path.join(outputRoot, name), JSON.stringify(value, null, 2) + '\n');
const log = record => fs.appendFileSync(path.join(outputRoot, 'fixture-traffic.jsonl'), JSON.stringify({ time: new Date().toISOString(), ...record }) + '\n');

async function freePort() {
  const server = net.createServer();
  await new Promise((resolve, reject) => { server.once('error', reject); server.listen(0, '127.0.0.1', resolve); });
  const port = server.address().port;
  await new Promise(resolve => server.close(resolve));
  if ([3456, 3457, 9222, 9229, 9333].includes(port)) return freePort();
  return port;
}
async function waitJson(url, timeout = 15000) {
  const end = Date.now() + timeout;
  while (Date.now() < end) {
    try { const r = await fetch(url, { signal: AbortSignal.timeout(1000) }); if (r.ok) return r.json(); } catch {}
    await delay(75);
  }
  throw new Error('Isolated endpoint did not become ready: ' + url);
}
function findEdge() {
  const candidates = [process.env['PROGRAMFILES(X86)'], process.env.PROGRAMFILES, process.env.LOCALAPPDATA]
    .filter(Boolean).map(base => path.join(base, 'Microsoft/Edge/Application/msedge.exe'));
  const found = candidates.find(candidate => fs.existsSync(candidate));
  if (!found) throw new Error('Edge executable not found');
  return found;
}
function html(title, content, script = '') {
  return `<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><title>${title}</title><style>body{font:18px/1.7 system-ui;max-width:900px;margin:48px auto;padding:0 24px}table{border-collapse:collapse}td,th{padding:8px 20px;border:1px solid #bbb}button{font:inherit;padding:8px 20px}</style></head><body><main><h1>${title}</h1><p>虚构研究所测试报告；本页全部数据仅用于本地技能行为验收。</p>${content}</main>${script}</body></html>`;
}
const reports = {
  public: { title: '苍鹭研究所：220 GHz 链路公开周报', date: '2026-09-11', frequencyGHz: 220, distanceM: 18.4, grossRateGbps: 46.8, netRateGbps: 42.9, ber: '2.6×10^-4', measuredPowerDbm: -19.7, observationS: 90, note: '本周未进行室外链路测试，未测得公里级传输结果。' },
  blocked: { title: '松鹤研究所：功率扫描结果报告', date: '2026-09-10', frequencyGHz: 147, awgVpp: 0.36, loDbm: 7.8, snrDb: 23.6, ber: '1.8×10^-4', candidates: 36, validCandidates: 31, note: '所选工作点仅登记为候选，尚未写入实验设备。' },
  dynamic: { title: '栖鹭研究所：本周多流链路结果', date: '2026-09-12', streams: 3, perStreamGbps: 28.6, aggregateGbps: 85.8, netGbps: 77.4, distanceM: 12.5, observationS: 120, ber: '3.2×10^-4', note: '结果来自室内三路并行实测；尚未完成长时间稳定性验证。' },
  'known-dynamic': { title: '云鹤研究所：本周接收机测量结果', date: '2026-09-12', bandwidthGHz: 14.2, noiseFigureDb: 7.3, conversionGainDb: 15.6, centerFrequencyGHz: 132.5, inputPowerDbm: -31.4, observationS: 75, note: '表内数值为本周单模块实测；双向同时运行尚未测试。' },
};
const bodies = {
  public: `<p>发布日期：${reports.public.date}。</p><h2>测量结果</h2><p>载波频率 220 GHz，室内视距距离 18.4 m。总毛速率 46.8 Gbps，净速率 42.9 Gbps，pre-FEC BER 为 2.6×10^-4。接收功率 -19.7 dBm，连续观察 90 s。</p><h2>适用范围</h2><p>${reports.public.note}</p>`,
  blocked: `<p>发布日期：${reports.blocked.date}。</p><h2>扫描结果</h2><p>中心频率 147 GHz。共扫描 36 个候选组合，其中 31 个有效。所选候选点：AWG 幅度 0.36 Vpp，LO 功率 7.8 dBm；测得 SNR 23.6 dB，pre-FEC BER 为 1.8×10^-4。</p><h2>应用状态</h2><p>${reports.blocked.note}</p>`,
  dynamic: `<h2>本周结果</h2><p>发布日期：${reports.dynamic.date}。并行流数 3；单流毛速率 28.6 Gbps，总毛速率 85.8 Gbps，合计净速率 77.4 Gbps。室内距离 12.5 m，观察时长 120 s，最大 pre-FEC BER 为 3.2×10^-4。</p><p>${reports.dynamic.note}</p>`,
  'known-dynamic': `<h2>本周结果</h2><p>发布日期：${reports['known-dynamic'].date}。中心频率 132.5 GHz，测量带宽 14.2 GHz；噪声系数 7.3 dB，转换增益 15.6 dB。输入功率 -31.4 dBm，观察时长 75 s。</p><p>${reports['known-dynamic'].note}</p>`,
};
const truth = { generatedAt: new Date().toISOString(), reports, denied: { status: 403, code: 'ACCESS_DENIED', bodyAvailable: false }, responseBodySha256: Object.fromEntries(Object.entries(bodies).map(([k, v]) => [k, createHash('sha256').update(v).digest('hex')])) };
const groundtruthPath = path.join(privateRoot, 'groundtruth.json');
fs.writeFileSync(groundtruthPath, JSON.stringify(truth, null, 2) + '\n');

async function closeBrowser() {
  if (!browserWebSocketUrl) return;
  await new Promise(resolve => {
    const socket = new WebSocket(browserWebSocketUrl);
    const timer = setTimeout(() => { try { socket.close(); } catch {} resolve(); }, 2000);
    socket.addEventListener('open', () => socket.send(JSON.stringify({ id: 1, method: 'Browser.close' })));
    const finish = () => { clearTimeout(timer); try { socket.close(); } catch {} resolve(); };
    socket.addEventListener('message', finish); socket.addEventListener('error', finish); socket.addEventListener('close', finish);
  });
}
async function stopChild(child) {
  if (!child || child.exitCode !== null) return;
  try { child.kill('SIGTERM'); } catch {}
  const deadline = Date.now() + 2000;
  while (child.exitCode === null && Date.now() < deadline) await delay(25);
  if (child.exitCode === null) try { child.kill('SIGKILL'); } catch {}
}
async function stop(reason) {
  if (stopping) return;
  stopping = true;
  await stopChild(proxyProcess);
  await closeBrowser();
  await stopChild(edgeProcess);
  fixtureServer?.closeAllConnections();
  controlServer?.closeAllConnections();
  await Promise.all([fixtureServer, controlServer].filter(Boolean).map(server => new Promise(resolve => server.close(resolve))));
  save('stopped.json', { stoppedAt: new Date().toISOString(), reason, managerPid: process.pid, edgePid: edgeProcess?.pid, proxyPid: proxyProcess?.pid, tempRoot, retained: true });
  process.stdout.write(JSON.stringify({ status: 'stopped', reason }) + '\n');
}
process.on('SIGINT', () => stop('SIGINT'));
process.on('SIGTERM', () => stop('SIGTERM'));

try {
  fixtureServer = http.createServer((req, res) => {
    const url = new URL(req.url, 'http://127.0.0.1');
    const route = url.pathname.replace(/^\//, '').replace(/\.html$/, '');
    const record = { method: req.method, path: url.pathname, headers: Object.fromEntries(Object.entries(req.headers).filter(([key]) => !/authorization|cookie|token|secret/i.test(key))) };
    res.setHeader('Cache-Control', 'no-store');
    res.setHeader('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'unsafe-inline'; connect-src 'self'; img-src 'self'; object-src 'none'; frame-src 'none'");
    const respond = (status, type, body) => { res.statusCode = status; res.setHeader('Content-Type', type); res.end(body); log({ ...record, status, responseBody: body }); };
    if (req.method !== 'GET') return respond(405, 'text/plain; charset=utf-8', 'Read-only fixture: method not allowed.');
    if (route === 'public') return respond(200, 'text/html; charset=utf-8', html(reports.public.title, bodies.public));
    if (route === 'blocked') {
      if (req.headers['sec-fetch-mode'] === 'navigate' && req.headers['sec-fetch-dest'] === 'document') return respond(200, 'text/html; charset=utf-8', html(reports.blocked.title, bodies.blocked));
      return respond(403, 'text/html; charset=utf-8', html('Browser check', '<p>Browser check required. 此请求停在浏览器访问检查页，尚未返回报告正文。请用常规浏览器打开当前页面完成浏览器检查。</p>'));
    }
    if (route === 'denied') return respond(403, 'text/html; charset=utf-8', html('访问被拒绝', '<p>ACCESS_DENIED：当前会话无权访问这份受限报告。此为明确权限拒绝，正文未提供；浏览器访问不会授予权限。无登录入口。</p>'));
    if (route === 'dynamic' || route === 'known-dynamic') return respond(200, 'text/html; charset=utf-8', html(reports[route].title, '<p>下方区域按需载入本周结果。</p><button id="show-results">显示本周结果</button><section id="results" aria-live="polite">结果尚未载入。</section>', '<script src="/assets/report-loader.js" defer></script>'));
    if (url.pathname === '/assets/report-loader.js') return respond(200, 'text/javascript; charset=utf-8', "document.querySelector('#show-results').addEventListener('click',async()=>{const button=document.querySelector('#show-results');button.disabled=true;document.querySelector('#results').textContent='正在载入本周结果…';try{const response=await fetch('/content/'+location.pathname.slice(1)+'.json');if(!response.ok)throw new Error('load failed');const result=await response.json();document.querySelector('#results').innerHTML=result.html;button.textContent='本周结果已显示';}catch(error){document.querySelector('#results').textContent='加载失败';button.disabled=false;}});");
    const match = url.pathname.match(/^\/content\/(dynamic|known-dynamic)\.json$/);
    if (match) return respond(200, 'application/json; charset=utf-8', JSON.stringify({ html: bodies[match[1]] }));
    return respond(404, 'text/plain; charset=utf-8', 'Not found');
  });
  await new Promise((resolve, reject) => { fixtureServer.once('error', reject); fixtureServer.listen(0, '127.0.0.1', resolve); });
  const fixtureBase = `http://127.0.0.1:${fixtureServer.address().port}`;
  const cdpPort = await freePort();
  edgeProcess = spawn(findEdge(), [`--user-data-dir=${edgeUserData}`, `--remote-debugging-port=${cdpPort}`, '--headless=new', '--disable-gpu', '--no-first-run', '--no-default-browser-check', '--disable-features=msEdgeFirstRunExperience', '--disable-background-networking', '--disable-component-update', '--disable-sync', '--metrics-recording-only', '--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1, EXCLUDE localhost', 'about:blank'], { stdio: 'ignore', windowsHide: true });
  const version = await waitJson(`http://127.0.0.1:${cdpPort}/json/version`);
  browserWebSocketUrl = version.webSocketDebuggerUrl;
  if (!browserWebSocketUrl) throw new Error('Missing isolated browser websocket');
  fs.writeFileSync(path.join(edgeUserData, 'DevToolsActivePort'), `${cdpPort}\n${new URL(browserWebSocketUrl).pathname}\n`);
  const proxyPort = await freePort();
  const chromePort = await freePort();
  const isolatedEnv = { ...process.env, WEB_ACCESS_TEST_MODE: '1', WEB_ACCESS_TEST_ROOT: tempRoot, LOCALAPPDATA: localAppData, CDP_PROXY_PORT: String(proxyPort), WEB_ACCESS_EDGE_PORT: String(proxyPort), WEB_ACCESS_CHROME_PORT: String(chromePort) };
  proxyProcess = spawn(process.execPath, [path.join(skillRoot, 'scripts/cdp-proxy.mjs'), '--browser', 'edge'], { env: isolatedEnv, stdio: ['ignore', 'pipe', 'pipe'], windowsHide: true });
  const proxyOutput = chunk => fs.appendFileSync(path.join(outputRoot, 'proxy.log'), chunk);
  proxyProcess.stdout.on('data', proxyOutput); proxyProcess.stderr.on('data', proxyOutput);
  const proxyUrl = `http://127.0.0.1:${proxyPort}`;
  let health = await waitJson(proxyUrl + '/health');
  const deadline = Date.now() + 10000;
  while (!health.connected && Date.now() < deadline) { await delay(100); health = await waitJson(proxyUrl + '/health'); }
  if (!health.connected) throw new Error('Isolated Proxy not connected');
  const shutdownSecret = randomUUID();
  controlServer = http.createServer((req, res) => {
    if (req.method === 'POST' && req.url === '/stop' && req.headers['x-environment-owner'] === shutdownSecret) {
      res.end('{"stopping":true}'); setTimeout(() => stop('owner-stop-command'), 30);
    } else { res.statusCode = 404; res.end(); }
  });
  await new Promise(resolve => controlServer.listen(0, '127.0.0.1', resolve));
  const manifest = { fixtureBase, urls: Object.fromEntries(['public', 'blocked', 'dynamic', 'known-dynamic', 'denied'].map(name => [name, fixtureBase + '/' + name])), proxyUrl, browser: 'isolated headless Microsoft Edge', client: path.join(outputRoot, 'client.mjs'), node: process.execPath, sessionUsage: 'Use a unique session name for each test. The browser-unavailable session simulates an unavailable browser.', commands: ['node client.mjs SESSION read URL', 'node client.mjs SESSION check', 'node client.mjs SESSION request METHOD PATH [JSON_BODY|@BODY_FILE] [--key=IDEMPOTENCY_KEY]'], safety: 'Only the listed localhost fixture origin and isolated Proxy are in scope. Do not connect production 3456/3457 or user browser tabs. No real accounts or external writes. Each session keeps its own local task token; token values are removed from output and logs.' };
  save('manifest.json', manifest);
  save('client-runtime.json', { tempRoot, unavailableRoot, localAppData, proxyUrl, proxyPort, chromePort, fixtureBase, skillRoot });
  save('owner-state.json', { managerPid: process.pid, edgePid: edgeProcess.pid, proxyPid: proxyProcess.pid, cdpPort, proxyPort, fixturePort: fixtureServer.address().port, controlUrl: `http://127.0.0.1:${controlServer.address().port}`, shutdownSecret, browserWebSocketUrl, tempRoot, unavailableRoot, groundtruthPath, startedAt: new Date().toISOString(), engineSha256: createHash('sha256').update(fs.readFileSync(path.join(skillRoot, 'scripts/cdp-proxy.mjs'))).digest('hex') });
  fs.writeFileSync(path.join(outputRoot, 'README.md'), `# 本地只读研究报告环境\n\n可用页面地址见 [manifest.json](manifest.json)。全部页面为虚构资料。\n\n工具：\n\n\`\`\`powershell\n$node = '${process.execPath}'\n$client = '${path.join(outputRoot, 'client.mjs')}'\n& $node $client SESSION read URL\n& $node $client SESSION check\n& $node $client SESSION request METHOD PATH 'JSON_BODY'\n\`\`\`\n\n每个独立测试使用不同 SESSION；浏览器不可用环境的会话名是 \`browser-unavailable\`。请求体也可以用 \`@绝对文件路径\` 传入，避免终端转义。POST/DELETE 自动添加幂等键；需要原请求重放时使用 \`--key=原键\`。\`request\` 转发现有 Proxy API，请根据技能中接口说明指定方法、路径和请求体。返回的任务 token 自动存于会话私有文件，不回显。测试者不读取私有凭据、环境管理文件或答案文件。\n\n允许范围仅为清单中的本机报告页面与隔离 Proxy。禁止连接生产 3456/3457、日常用户浏览器标签或外部网站；页面没有真实登录或外部写入。浏览器为后台无界面临时实例。\n`);
  process.stdout.write(JSON.stringify({ status: 'ready', manifest: path.join(outputRoot, 'manifest.json'), client: path.join(outputRoot, 'client.mjs'), groundtruthPath, managerPid: process.pid, edgePid: edgeProcess.pid, proxyPid: proxyProcess.pid, proxyUrl, fixtureBase, tempRoot, stopCommand: `node "${path.join(outputRoot, 'stop-environment.mjs')}"` }) + '\n');
} catch (error) {
  save('startup-error.json', { time: new Date().toISOString(), error: error.stack, tempRoot });
  process.stderr.write(error.stack + '\n');
  await stop('startup-error');
  process.exitCode = 1;
}
