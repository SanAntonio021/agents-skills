// Adapted from eze-is/web-access d173a75978ceb2c63fa0b27f7408cd2bf7fe4310 (MIT).
// Local scope: direct frame listing and isolated context only; no coordinate actions.
// 页面直属 iframe 的列举和隔离读取上下文。唯一 CDP 连接仍由本地 Proxy 持有。
// DOM.describeNode 返回 frameId；跨进程 iframe 的 frameId 同时对应 iframe targetId。
// Page.getFrameTree 不包含 OOPIF，当前 URL 从 Target.getTargets 读取。
// 同名隔离 world 复用，DOM 原型与页面脚本隔离；对象组按每次调用单独释放。
// 范围：只覆盖主文档直接 iframe/frame，不遍历嵌套 frame 或 shadow root。

import { randomUUID } from 'node:crypto';

// 调用方参数问题（frameId 格式不对、该页面没有这个 iframe），由调用方映射为 400
export class FrameError extends Error {}

const FRAME_ID = /^[A-Za-z0-9._-]{1,128}$/;
const WORLD_NAME = 'web-access';

export function createPageFrames({ send, ensureSession }) {
  // CDP 错误一律抛出，带上方法名
  async function call(method, params, sessionId) {
    const resp = await send(method, params, sessionId);
    if (resp.error) throw new Error(`${method}: ${resp.error.message}`);
    return resp.result;
  }

  // 用对象组承载临时远程对象，结束后整组释放。组名每次调用唯一：
  // 同一标签页上重叠的请求共用 session，固定组名会让先结束的请求释放另一个请求还在用的对象。
  async function withObjectGroup(sessionId, prefix, fn) {
    const group = `${prefix}-${randomUUID()}`;
    try { return await fn(group); }
    finally { await send('Runtime.releaseObjectGroup', { objectGroup: group }, sessionId).catch(() => {}); }
  }

  // frame 的隔离环境（同名复用同一个上下文）
  async function isolatedWorld(sessionId, frameId) {
    const world = await call('Page.createIsolatedWorld', { frameId, worldName: WORLD_NAME }, sessionId);
    if (!world.executionContextId) throw new Error('iframe 执行环境不可用');
    return world.executionContextId;
  }

  // session 根 frame 的 id 与 frame 树
  async function frameTree(sessionId) {
    return (await call('Page.getFrameTree', {}, sessionId)).frameTree;
  }

  async function iframeTargets() {
    const { targetInfos } = await call('Target.getTargets');
    return new Map(targetInfos.filter(info => info.type === 'iframe').map(info => [info.targetId, info]));
  }

  // 列出页面主文档中的 iframe：[{ index, frameId, crossProcess, url, id?, name?, src? }]
  // frameId 为 null 表示该 iframe 尚未加载出文档
  async function listFrames(targetId) {
    const sessionId = await ensureSession(targetId);
    const tree = await frameTree(sessionId);
    const contextId = await isolatedWorld(sessionId, tree.frame.id);
    return withObjectGroup(sessionId, 'web-access-frames', async group => {
      const list = await call('Runtime.evaluate', {
        expression: "document.querySelectorAll('iframe, frame')", objectGroup: group, contextId,
      }, sessionId);
      if (list.exceptionDetails || !list.result?.objectId) throw new Error('无法读取页面中的 iframe');
      const { result: props } = await call('Runtime.getProperties', {
        objectId: list.result.objectId, ownProperties: true,
      }, sessionId);
      const elements = props.filter(prop => /^\d+$/.test(prop.name))
        .sort((a, b) => Number(a.name) - Number(b.name))
        .map(prop => prop.value.objectId);
      if (!elements.length) return [];

      const oopifs = await iframeTargets();
      const local = new Map();
      const walk = node => { for (const child of node?.childFrames || []) { local.set(child.frame.id, child.frame); walk(child); } };
      walk(tree);

      const frames = [];
      for (const [index, objectId] of elements.entries()) {
        const { node } = await call('DOM.describeNode', { objectId }, sessionId);
        const attrs = {};
        for (let i = 0; i + 1 < (node.attributes || []).length; i += 2) attrs[node.attributes[i]] = node.attributes[i + 1];
        const frameId = node.frameId || null;
        const oopif = frameId ? oopifs.get(frameId) : undefined;
        frames.push({
          index,
          frameId,
          crossProcess: Boolean(oopif),
          url: oopif?.url ?? local.get(frameId)?.url ?? attrs.src ?? null,
          ...(attrs.id ? { id: attrs.id } : {}),
          ...(attrs.name ? { name: attrs.name } : {}),
          ...(attrs.src ? { src: attrs.src } : {}),
        });
      }
      return frames;
    });
  }

  // 为 /eval 准备 iframe 的执行环境：{ sessionId, contextId, frame }
  // 在 iframe 的隔离环境中执行：DOM 与页面共享，看不到页面自己的 JS 全局变量
  async function frameContext(targetId, frameId) {
    if (!FRAME_ID.test(frameId || '')) throw new FrameError('frame 参数应为 /frames 返回的 frameId');
    const frame = (await listFrames(targetId)).find(item => item.frameId === frameId);
    if (!frame) throw new FrameError(`该页面没有 frameId 为 ${frameId} 的 iframe，请先用 /frames 查看`);
    // 跨进程 iframe 只能在它自己的子 session 里执行；同进程 iframe 用页面 session 加 frameId
    const sessionId = frame.crossProcess ? await ensureSession(frameId) : await ensureSession(targetId);
    const world = await call('Page.createIsolatedWorld', { frameId, worldName: WORLD_NAME }, sessionId);
    if (!world.executionContextId) throw new Error('iframe 执行环境不可用');
    return { sessionId, contextId: world.executionContextId, frame };
  }

  return { listFrames, frameContext };
}
