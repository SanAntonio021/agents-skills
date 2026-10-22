# 页面导航、观察与交互

先读 [CDP 文档入口](cdp-api.md)。本页说明页面状态、AX snapshot/ref、结构化动作、等待、dialog、兜底 API 与本地历史；登录交接见 [生命周期参考](cdp-lifecycle.md#登录与用户接管)，文件内容见 [内容提取参考](cdp-content.md)。

## 页面观察与导航

先用 [snapshot](#ax-snapshotref) 读取结构，再以最新 ref 调用 [action](#结构化-action)，动作后回读页面确认结果。导航、动态重绘、dialog 或 `resume` 后重新 snapshot；`STALE_REF` 不用旧 ref 反复重试。加载等待用 [wait](#wait-与-dialog) 的 selector、text、URL 或 load 条件。

结构化动作遵循固定的快速执行契约：页面状态先转换为可引用的交互元素，planner 只选择受限动作及其当前 ref，执行器再从当前 DOM/AX 状态重新定位目标并检查元素存在、可交互且未被遮挡，动作完成后回读 URL、文本或结构状态确认预期变化。planner 不直接输出 CSS、坐标、任意 JavaScript 或外部请求；ref 过期、动作不合规、页面发生未预期变化或校验失败时，丢弃该动作并回到最新 snapshot 的通用路径。

规划器仅输出 `click`、`fill`、`type`、`press`、`check`、`uncheck`、`select`、`hover`、`wait` 标准动作，由本地执行器处理；不得读取或填写密码，也不负责 MFA、短信/邮件验证码、动态口令、SSO 信息发布核对、付款、删除、发布、账号变更或用户接管步骤。凭据步骤由浏览器原生自动填充或已有获准的本机安全助手负责，不把凭据传给规划器。

此契约吸收 jev-ultrafast 的设计，默认沿用现有通用模型或本地确定性逻辑，不依赖其专用模型服务。专用 planner 仅预留为可插拔、默认关闭的实现；不可用、输出不合规、页面复杂或动作校验失败时回退通用模型路径。

snapshot/ref 不足时使用 CSS `/click`，必要时才用 `/eval`。结构化交互可以执行页面脚本并保留会话上下文，但仍可能遇到站点检测、验证码或访问限制，不保证优于每一种直接读取方式。通过实际页面交互了解地址与参数，比猜测 URL 更可靠；保留观察到的完整 URL，不自行补造会话参数。

当结构化路径无法表达视觉关系、复杂拖拽、特殊控件或 Windows 原生窗口操作时，才切换到 `computer-use` 后备能力；切换前保留已取得的页面状态和授权边界，完成后重新回到可核验的页面状态。不要因为单次 ref 失效就直接切换后备能力。

连续浏览用 ref 点击；并行读取时，在同一 task 用 `POST /v2/tabs` 和完整 URL 新建自有 tab。Proxy 先创建空白页并初始化，再导航；popup 按 `openerId` 继承 task。带签名或会话参数的 URL 只在任务内部使用，不写入交付文本。

折叠内容可能已在 DOM 中，也可能尚未加载，按实际状态判断。懒加载时按需滚动再读取。snapshot/ref 不支持跨域 OOPIF；iframe 正文按 [内容提取参考](cdp-content.md#iframe-正文读取) 在隔离上下文中提取。同源 Shadow DOM/iframe 必要时可用 CSS 或 `/eval`，不宣称可穿越所有 frame。

## AX snapshot/ref

### `GET /v2/tabs/{targetId}/snapshot`

Query：

- `mode=interactive|all`，默认 `interactive`
- `depth=1..50`，默认 12
- `maxNodes=1..1000`，默认 300
- `refresh=true` 强制重新取得 AX tree

AX tree 最多缓存 60 秒，但每次 snapshot 请求都会签发新的 generation/ref。示例：

```json
{
  "targetId": "TARGET_ID",
  "generation": 7,
  "mode": "interactive",
  "depth": 12,
  "maxNodes": 300,
  "truncated": false,
  "nodes": [
    {"role":"textbox","name":"Name","value":"","ref":"r7_1_ab12cd34"},
    {"role":"button","name":"Submit","ref":"r7_2_ef56ab78"}
  ]
}
```

ref 在 Proxy 内绑定 `taskId + targetId + generation + backendDOMNodeId`，只对最近 snapshot 有效。动作前重新解析节点并检查 attached、visible、enabled 和未遮挡。失败返回 `409 STALE_REF`，随后必须重新 snapshot。

首版不支持跨域 OOPIF ref。

## 结构化 action

### `POST /v2/tabs/{targetId}/action`

统一 body 字段名是 `action`：

```json
{"action":"click","ref":"REF"}
{"action":"fill","ref":"REF","value":"replacement"}
{"action":"type","ref":"REF","value":"append one key at a time"}
{"action":"press","ref":"REF","key":"Control+A"}
{"action":"press","key":"Enter"}
{"action":"check","ref":"REF"}
{"action":"uncheck","ref":"REF"}
{"action":"select","ref":"REF","value":"one"}
{"action":"select","ref":"REF","values":["one","two"]}
{"action":"hover","ref":"REF"}
```

- `fill`：focus、全选、`Input.insertText`，再回读验证。
- `type`：逐键派发输入事件。
- `press`：有 ref 时先 focus；没有 ref 时作用于当前焦点。
- `check`/`uncheck`：只支持原生 checkbox/radio，并验证最终状态。
- `select`：只支持原生 `<select>`；`values` 支持 multi-select。

同一 target 同时只能有一个读写操作；冲突返回 `409 TARGET_BUSY`。

## Wait 与 dialog

### `POST /v2/tabs/{targetId}/wait`

四类条件只能选一个：

```json
{"selector":"#ready","timeoutMs":15000}
{"text":"Saved","timeoutMs":15000}
{"url":"/success","timeoutMs":15000}
{"state":"domcontentloaded","timeoutMs":15000}
{"state":"load","timeoutMs":15000}
```

默认 15 秒，最长 30 秒，250 ms 轮询。URL 条件按当前完整 URL 是否包含给定字符串判断。不支持 JS wait 或 `networkidle`。handoff、complete 和 task 过期会取消 wait；即使取消发生在首次 attach 前或条件查询结果晚到，取消仍优先并返回 `409 WAIT_CANCELLED`。

target 操作结束时刷新 task 与 tab 的最后活动时间；空闲过期和 15 分钟 tab 清理从操作完成时重新计时，不从长操作开始时计时。已经进入 task 终态转换的操作仍按该转换完成。

### `POST /v2/tabs/{targetId}/dialog`

JavaScript dialog 默认保持待处理，不自动接受：

```json
{"action":"dismiss"}
{"action":"accept","promptText":"Alice"}
```

不存在 dialog 时返回 `409 NO_DIALOG`。处理后当前 ref 全部失效。

## 表单与外部写入

已有准确授权时，核对目标、账号、动作及内容后执行并回读，不因进入表单或最终提交而再次确认。没有授权外发时，仅将用户提供的非敏感内容、且不存在 autosave、live chat 或输入即外发的填写作为普通草稿操作。敏感内容或即时外发按相应写入授权处理，缺失授权或实际要素变化时询问。

JavaScript dialog 的处理按上文执行；接口要求确认参数时依据真实请求填写，不伪造用户答复。处理后重新 snapshot。

## 鉴权兜底 API

调用顺序固定为 snapshot/ref、CSS click、最后 `/eval`：

| Method | Path | JSON body |
|---|---|---|
| POST | `/v2/tabs/{id}/navigate` | `{"url":"https://example.com"}` |
| POST | `/v2/tabs/{id}/back` | `{}` |
| POST | `/v2/tabs/{id}/click` | `{"selector":"button.submit"}` |
| POST | `/v2/tabs/{id}/eval` | `{"expression":"document.title"}` |
| POST | `/v2/tabs/{id}/scroll` | `{"direction":"bottom"}` 或 `{"y":3000}` |
| POST | `/v2/tabs/{id}/set-files` | `{"selector":"input[type=file]","files":["C:\\\\path\\\\file.png"]}` |

文件上传属于外部写操作，调用前按 [技能入口](../SKILL.md) 核对准确授权、目标和文件；已有授权且范围一致时继续，缺少授权或实际范围变化时才询问。

## 本地历史与站点参考

用户要找本人访问过的页面或公网不可检索的内部入口时，按目标关键词查询本地书签或历史；不为普通联网查询扫描无关浏览记录。

```bash
node "${CLAUDE_SKILL_DIR}/scripts/find-url.mjs" [关键词...] [--only bookmarks|history] [--browser chrome|edge] [--limit N] [--since 1d|7h|YYYY-MM-DD] [--sort recent|visits]
```

多词按 AND 匹配 title 与 URL，默认查询已安装 Chromium 系浏览器；`--browser` 限定来源。`--since` 与 `--sort` 只作用于历史，默认按最近访问倒序。

目标站点存在 `site-patterns/{domain}.md` 时按需读取；前检也会列出已有站点参考。记录中的发现日期和条件保留，经验失效时重新判断。业务任务不自动回写站点经验；仅在用户要求维护时记录已验证事实。
