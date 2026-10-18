import assert from 'node:assert/strict';
import test from 'node:test';
import { createPageFrames, FrameError } from './page-frames.mjs';

// 进程内假浏览器：按 CDP 方法返回固定结构，记录每次调用（方法、参数、session），不连接任何浏览器。
// 页面 page-1 主文档里有三个 iframe：同进程 local-frame、跨进程 oopif-frame、尚未加载的第三个。
function fakeBrowser({ hit = null, errors = {} } = {}) {
  const calls = [];
  const attached = [];
  const ensureSession = async targetId => {
    attached.push(targetId);
    return targetId === 'page-1' ? 'page-session' : `${targetId}-session`;
  };
  const send = async (method, params = {}, sessionId = null) => {
    calls.push({ method, params, sessionId });
    if (errors[method]) return { error: { message: errors[method] } };
    switch (method) {
      case 'Runtime.evaluate':
        // 主环境里页面改写了 DOM API（返回空），只有隔离环境能看到真实结果
        if (params.expression.includes('querySelectorAll')) {
          return { result: { result: params.contextId ? { objectId: 'node-list' } : { type: 'object', subtype: 'null' } } };
        }
        if (params.expression.includes('elementFromPoint')) {
          return { result: { result: hit && params.contextId ? { objectId: hit } : { type: 'object', subtype: 'null' } } };
        }
        if (params.expression.includes('innerWidth')) return { result: { result: { value: [300, 250] } } };
        break;
      case 'Runtime.getProperties':
        // 故意乱序，并混入非下标属性
        return { result: { result: [
          { name: '2', value: { objectId: 'el-unloaded' } },
          { name: 'length', value: { value: 3 } },
          { name: '0', value: { objectId: 'el-local' } },
          { name: '1', value: { objectId: 'el-oopif' } },
        ] } };
      case 'Target.getTargets':
        return { result: { targetInfos: [
          { targetId: 'page-1', type: 'page', url: 'http://localhost/p' },
          { targetId: 'oopif-frame', type: 'iframe', url: 'http://127.0.0.1/child' },
          { targetId: 'page-2', type: 'page', url: 'http://other/' },
        ] } };
      case 'Page.getFrameTree':
        return { result: { frameTree: { frame: { id: 'page-1' }, childFrames: [
          { frame: { id: 'local-frame', url: 'http://localhost/same-now', name: 'kid' } },
        ] } } };
      case 'DOM.describeNode': {
        const nodes = {
          'el-local': { frameId: 'local-frame', attributes: ['name', 'kid', 'src', '/same'] },
          'el-oopif': { frameId: 'oopif-frame', attributes: ['id', 'pay', 'src', 'http://127.0.0.1/child', 'style', 'x'] },
          'el-unloaded': { attributes: ['src', 'about:blank#later'] },
          'el-button': { attributes: ['id', 'b'] },
        };
        return { result: { node: nodes[params.objectId] } };
      }
      case 'Page.createIsolatedWorld':
        return { result: { executionContextId: sessionId === 'page-session' ? 11 : 22 } };
      case 'Runtime.callFunctionOn':
        return { result: { result: { value: { x: 55, y: 65 } } } };
      case 'Page.captureScreenshot':
        return { result: { data: 'AA==' } };
    }
    return { result: {} };
  };
  return { frames: createPageFrames({ send, ensureSession }), calls, attached };
}

const methods = calls => calls.map(call => call.method);
// 释放的对象组：返回前缀，并断言每个被释放的组都是本次调用创建临时对象时用的那个（组名唯一）
const releasedGroups = calls => {
  const created = new Set(calls.map(call => call.params?.objectGroup).filter(group => group && calls.some(c => c.method !== 'Runtime.releaseObjectGroup' && c.params?.objectGroup === group)));
  const released = calls.filter(call => call.method === 'Runtime.releaseObjectGroup').map(call => call.params.objectGroup);
  for (const group of released) {
    assert.match(group, /^web-access-(frames|click)-[0-9a-f-]{36}$/);
    assert.ok(created.size === 0 || created.has(group), `释放了未创建的组 ${group}`);
  }
  return released.map(group => group.replace(/-[0-9a-f-]{36}$/, ''));
};

test('listFrames 按文档顺序列出主文档 iframe：跨进程标记、当前网址与定位线索，用完释放临时对象', async () => {
  const { frames, calls, attached } = fakeBrowser();
  assert.deepEqual(await frames.listFrames('page-1'), [
    { index: 0, frameId: 'local-frame', crossProcess: false, url: 'http://localhost/same-now', name: 'kid', src: '/same' },
    { index: 1, frameId: 'oopif-frame', crossProcess: true, url: 'http://127.0.0.1/child', id: 'pay', src: 'http://127.0.0.1/child' },
    { index: 2, frameId: null, crossProcess: false, url: 'about:blank#later', src: 'about:blank#later' },
  ]);
  assert.deepEqual(attached, ['page-1']);
  assert.ok(calls.filter(call => call.method !== 'Target.getTargets').every(call => call.sessionId === 'page-session'));
  assert.deepEqual(releasedGroups(calls), ['web-access-frames']);
});

test('页面没有 iframe 时返回空数组，不查询 iframe target', async () => {
  const calls = [];
  const frames = createPageFrames({
    ensureSession: async () => 'page-session',
    send: async (method, params, sessionId) => {
      calls.push({ method, params, sessionId });
      if (method === 'Runtime.evaluate') return { result: { result: { objectId: 'node-list' } } };
      if (method === 'Runtime.getProperties') return { result: { result: [{ name: 'length', value: { value: 0 } }] } };
      if (method === 'Page.getFrameTree') return { result: { frameTree: { frame: { id: 'page-1' } } } };
      if (method === 'Page.createIsolatedWorld') return { result: { executionContextId: 1 } };
      return { result: {} };
    },
  });
  assert.deepEqual(await frames.listFrames('page-1'), []);
  assert.ok(!methods(calls).includes('Target.getTargets'));
  assert.deepEqual(releasedGroups(calls), ['web-access-frames']);
});

test('frameContext：跨进程 iframe 在它的子 session 中建隔离环境，同进程 iframe 用页面 session', async () => {
  const oop = fakeBrowser();
  const remote = await oop.frames.frameContext('page-1', 'oopif-frame');
  assert.equal(remote.sessionId, 'oopif-frame-session');
  assert.equal(remote.contextId, 22);
  assert.equal(remote.frame.crossProcess, true);
  const world = oop.calls.find(call => call.method === 'Page.createIsolatedWorld' && call.params.frameId === 'oopif-frame');
  assert.deepEqual(world, { method: 'Page.createIsolatedWorld', params: { frameId: 'oopif-frame', worldName: 'web-access' }, sessionId: 'oopif-frame-session' });

  const same = fakeBrowser();
  const local = await same.frames.frameContext('page-1', 'local-frame');
  assert.equal(local.sessionId, 'page-session');
  assert.equal(local.contextId, 11);
  assert.ok(!same.attached.includes('local-frame'));
});

for (const [frameId, pattern] of [
  ['', /应为 \/frames 返回的 frameId/],
  ['#pay', /应为 \/frames 返回的 frameId/],
  ['a b', /应为 \/frames 返回的 frameId/],
  [undefined, /应为 \/frames 返回的 frameId/],
  ['page-2', /该页面没有 frameId 为 page-2/],
  ['page-1', /该页面没有 frameId 为 page-1/],
]) {
  test(`frameContext 拒绝 ${JSON.stringify(frameId)}：只接受本页面主文档里 iframe 的 frameId，不 attach 其他目标`, async () => {
    const { frames, attached, calls } = fakeBrowser();
    await assert.rejects(frames.frameContext('page-1', frameId), error => error instanceof FrameError && pattern.test(error.message));
    assert.ok(attached.every(id => id === 'page-1'), attached.join(','));
    // 只为页面根 frame 建过隔离环境（用于列举），没有进入任何其他 frame
    assert.ok(calls.filter(call => call.method === 'Page.createIsolatedWorld').every(call => call.params.frameId === 'page-1'));
  });
}

