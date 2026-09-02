# CDP Proxy protocol v2

## 连接与通用规则

- Edge 默认地址：`http://127.0.0.1:3456`
- Chrome 默认地址：`http://127.0.0.1:3457`
- Proxy 只绑定 `127.0.0.1`，只接受匹配端口的 `127.0.0.1`/`localhost` Host。
- 带 `Origin` 的请求被拒绝；Proxy 不返回 CORS 许可头。
- `/health`、`/capabilities` 和创建 task 之外的 `/v2` 请求都要发送 `Authorization: Bearer <taskToken>`。
- 所有 POST/DELETE 都要发送 `Content-Type: application/json` 和 `Idempotency-Key`。
- token 不能进入 URL、日志、错误信息或交付文本。

同一个 `Idempotency-Key` 与完全相同的 method、path、query、body 组合只执行一次。相同 key 配不同请求返回 `409 IDEMPOTENCY_CONFLICT`。mutation 的 CDP 命令开始后超时返回 `504 UNKNOWN_RESULT`；同 key 可重放该结果，但不得换 key 原样重试。

## 协议探测

### `GET /health`

不连接浏览器即可读取进程状态。关键字段：

```json
{
  "service": "web-access-cdp-proxy",
  "status": "ok",
  "protocolVersion": 2,
  "connected": true,
  "browser": {"id": "edge", "label": "Microsoft Edge"},
  "activeTasks": 1,
  "managedTabs": 2
}
```

### `GET /capabilities`

返回协议版本、snapshot/action/wait 能力、任务上限和明确不支持项。调用方必须确认 `protocolVersion === 2`。

## Task

### `POST /v2/tasks`

请求 body 为 `{}` 或调用方自用的元数据对象。Proxy 当前不持久化元数据。返回：

```json
{
  "taskId": "task_...",
  "taskToken": "256-bit-base64url-token",
  "state": "active"
}
```

单个 Proxy 最多同时保留 32 个非终态 task。

### `GET /v2/tasks/{taskId}`

返回 task 的 `state`、`tabCount` 和 `lastActivity`。只能使用同一 task 的 token。

### `POST /v2/tasks/{taskId}/handoff`

```json
{"targetId":"TARGET_ID"}
```

Proxy 先阻止新操作、取消 wait、等待在途 target 操作结束，再激活准确 tab。状态变为 `handoff` 后，所有页面读取和修改都返回 `409 TASK_IN_HANDOFF`。Agent 在 handoff 期间不得读取页面。

如果 `Target.activateTarget` 在 CDP 命令开始后超时，请求返回 `504 UNKNOWN_RESULT`，但 task 保持 `handoff`，不会退回 `active`。这是 fail-closed 行为：不得读取或修改页面；先查看 task 状态，由用户完成接管后再 `resume`。

### `POST /v2/tasks/{taskId}/resume`

Body 为 `{}`。只有 `handoff` task 可以恢复，且至少一个自建 tab/popup 必须仍存在。响应含 `snapshotRequired: true`；所有旧 ref 都已失效。

### `POST /v2/tasks/{taskId}/complete`

```json
{"keep":false}
```

- `keep:false`：关闭该 task 创建的 tab 和继承的 popup。
- `keep:true`：从 Proxy 释放这些 tab，保留给用户。
- `completed` 是终态；重复完成返回相同终态结果。

`complete` 只允许在 `active` 状态调用。处于 `handoff` 时必须先 `resume`；不能用 `complete` 绕过 handoff 的页面禁读屏障。

如果关闭或释放 tab 的 CDP 命令超时，task 仍进入终态 `completed`，请求返回 `504 UNKNOWN_RESULT`，同一幂等 key 重放仍返回同一结果。Proxy 会移除所有剩余归属；对应 tab 可能因晚到关闭结果而关闭，也可能作为用户 tab 保留，调用方不得假设其最终开关状态。

`DELETE /v2/tasks/{taskId}` 等价于 `complete` 的 `keep:false`。

状态机为 `active -> handoff -> active -> completed`，另有终态 `expired`。active 30 分钟无操作、handoff 30 分钟未恢复都会过期并把尚存 tab 释放给用户。终态幂等记录默认保留 5 分钟。

## Tab

### `POST /v2/tabs`

```json
{"url":"https://example.com","background":true}
```

只允许 `http:`、`https:` 和 `about:` URL。Proxy 固定先以 `about:blank` 创建 target，归属当前 task 并完成
attach/session 初始化后，才用 `Page.navigate` 前往请求 URL；返回 `201` 时该显式导航命令已经被浏览器接收。调用方
仍应按需要用 `/wait` 与页面回读确认加载结果。Popup 按 `openerId` 自动继承 opener 的 task。

`Target.createTarget` 超时后可能晚到。task 仍为 `active` 或 `handoff` 时，晚到 tab 继续归入原 task 并继续导航到原请求 URL；task 已按默认 `keep:false` 完成时，Proxy 关闭晚到 tab。`expired` 或 `keep:true` 的其他终态不再建立归属，但 Proxy 仍先尝试导航到原请求 URL，再释放给用户，不能遗留无意的空白页。首次返回 `UNKNOWN_RESULT` 后不得换 key 原样重试。

### `GET /v2/tabs`

只返回当前 task 创建的 tab 和 popup。用户已有 tab、其他 task tab 完全隐藏。

### `GET /v2/tabs/{targetId}`

返回当前 task tab 的 `type`、`title`、`url`、`kind`、snapshot `generation` 和待处理 `dialog`（没有时为 `null`）。猜中其他 task 或用户 targetId 仍统一返回 `404 TARGET_NOT_FOUND`。

### `DELETE /v2/tabs/{targetId}`

关闭当前 task 自有 tab。DELETE 仍须携带 JSON content type、空 body `{}` 和 idempotency key。

### `GET /v2/tabs/{targetId}/screenshot`

Query 可选 `format=png|jpeg`。响应是图片二进制；`file` query 被拒绝，保存位置由调用方决定。

### 同源服务器文件字节提取

task 自有 tab 已到达 PDF 或其他二进制文件 URL、但浏览器没有产生可用的本地下载时，可以通过 `/eval` 在页面同源上下文中取回响应体。该流程不是下载管理，也不能用来跨越登录、付费或站点权限；只用于公开资源或用户当前已授权访问的内容。

固定顺序：

1. 用 `GET /v2/tabs/{targetId}` 和只读 `/eval` 复核最终 `location.href`、页面 origin 与预期文件名。完整 URL 的 query 必须原样保留给浏览器，但签名或会话参数不进入日志和交付文本。页面没有实际到达目标文件、需要跨 origin 请求、授权状态不清或响应仍受访问控制时停止。
2. 在本地生成任务级随机键，例如 `__waFile_<random>`；首次 `/eval` 先把该键置为 `pending`，再 fetch 当前准确 URL。公开资源优先使用 `credentials: 'omit'`；用户已授权的内容只允许在同一 origin 使用 `same-origin` 凭据。不要读取或导出 Cookie、Authorization 或无关响应头。
3. 先检查 HTTP 状态、`Content-Type` 和可用的 `Content-Length`。非 2xx、预期 PDF/二进制却返回 HTML/JSON，或类型与目标明显不符时停止。默认原始响应体上限为 `50331648` 字节，对应 Base64 总上限 `67108864` 字符；`Content-Length` 缺失或不可信时按流累计，超过上限立即取消，不使用无界 `arrayBuffer()`。
4. 在页面内计算响应体 SHA-256，按小块编码 Base64，把 `state`、HTTP 状态、MIME、字节数、Base64 长度、SHA-256 和文件头暂存在随机键下。首次调用只返回这些元数据，不返回整段 Base64。
5. 首次 `/eval` 返回 `UNKNOWN_RESULT` 时，用新的只读表达式检查同一随机键。`pending` 时只做有界状态探测，`done` 时继续，`error` 时停止；随机键不存在且结果仍不确定时也停止。不得换幂等 key 原样重跑创建或 fetch 动作。
6. `done` 后按固定偏移读取 Base64，每块最多 `262144` 个字符，总量不得超过上述上限。每个新的分块读取使用独立幂等 key；某一块结果不确定时只用原 key 重放。调用方在本地缓冲，不把块内容输出到终端、聊天、日志或错误信息，并核对每块长度、偏移、总长度和结尾。
7. 在本地一次解码，复核文件头、字节数和 SHA-256；PDF 至少检查 `%PDF-`，再按任务需要用 `pdfinfo` 核对页数，并抽取文本或渲染页面确认内容。全部通过后才保存到目标位置。随后清除页面随机键并完成 task；缺块、长度或哈希不一致时丢弃候选文件。

这种方式取得的是浏览器收到的完整服务器响应字节，可以按服务器文件交付。它与 canvas 重新编码、视口截图仍要明确区分。

### 自然尺寸图片像素导出

仅在服务器文件字节无法取得、但目标图片已经在 task 自有页面中完整加载时使用。它通过 `/eval` 读取页面已解码像素，不是下载管理，也不能绕过资源权限。

固定顺序：

1. 用只读表达式返回目标元素的 `currentSrc`、`complete`、`naturalWidth`、`naturalHeight` 和解析后的资源 origin。`complete !== true` 或自然尺寸为 0 时先等待，不导出占位图。
2. 同源图片可以进入 canvas。跨域图片只有页面已使用明确 CORS 且探测画布保持 origin-clean 时才可继续；`drawImage` 或 `toDataURL` 抛出 `SecurityError` 时立即停止，不修改浏览器安全策略、不代理凭据。
3. 创建与自然尺寸相同的 canvas，执行 `drawImage(img, 0, 0)` 和 `toDataURL('image/png')`。把去掉前缀后的 Base64 暂存在页面内一个任务级随机键下；首次 `/eval` 只返回 MIME、宽高、编码字符数和可选 SHA-256，不返回整段内容。
4. 调用前固定边界。默认每块最多 `262144` 个 Base64 字符，总量最多 `67108864` 个字符；超过上限先停止并报告，不能无界取回。按偏移量逐块读取，校验块序号、总字符数和结尾，不把块内容打印到用户可见输出。
5. 在本地按顺序拼接并一次解码，复核 PNG 签名、宽高、文件大小和 SHA-256；随后用 `/eval` 清除页面暂存值。缺块、重复块、长度或哈希不符时丢弃候选，不用不完整数据补图。

canvas 结果必须标为“浏览器像素导出并重新编码”。只有直接取得服务器响应字节时，才可标为原始文件字节。`/eval` 返回 `UNKNOWN_RESULT` 时，先用新的只读表达式检查随机键和已生成元数据；不得换幂等 key 原样重跑创建动作。分块读取的不确定结果使用原幂等 key 重放，仍无法确认时停止。

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

文件上传属于最终外部写操作，调用前必须按 SKILL.md 取得用户确认。

## 主要错误码

| HTTP | Code | 处理 |
|---|---|---|
| 400 | `IDEMPOTENCY_KEY_REQUIRED` | 为 logical mutation 生成 key |
| 401 | `UNAUTHORIZED` | token 无效、跨 Proxy 或 Proxy 已重启 |
| 403 | `INVALID_HOST` / `ORIGIN_FORBIDDEN` | 不从网页 origin 调用 Proxy |
| 404 | `TARGET_NOT_FOUND` | 不探测其他 task；检查自己的 tab |
| 408 | `WAIT_TIMEOUT` | 重新判断条件或流程 |
| 409 | `TARGET_BUSY` | 等当前 target 操作结束 |
| 409 | `STALE_REF` | 重新 snapshot |
| 409 | `TASK_IN_HANDOFF` | 等用户完成并 resume |
| 409 | `TASK_TRANSITIONING` | 等当前 handoff/complete/expiry 屏障结束 |
| 409 | `INVALID_TASK_STATE` | 按状态机恢复；handoff 先 resume |
| 409 | `WAIT_CANCELLED` | task 已开始转换，不继续等待 |
| 409 | `IDEMPOTENCY_CONFLICT` | 不复用不同 logical request 的 key |
| 410 | `TASK_TERMINAL` / `TASK_EXPIRED` | 新建 task |
| 410 | `LEGACY_API_DISABLED` | 迁移到 `/v2` |
| 415 | `JSON_REQUIRED` | 使用 `application/json` |
| 429 | `TASK_LIMIT_REACHED` | 完成或等待旧 task 回收 |
| 504 | `UNKNOWN_RESULT` | 先读取状态，不得换 key 原样重试 |

## 隔离边界

task token 用于减少多个对话之间的误操作，不是本机安全边界。其他本地进程仍可能直接访问浏览器 CDP。Task/tab 逻辑隔离也不是独立 Profile、Cookie 或浏览器上下文隔离。

Proxy 重启或 CDP 断线时，task、token、归属、session 和 ref 全部清空；浏览器 tab 不关闭，遗留 tab 降为用户 tab且不能被重新接管。首版不提供网络抓包、HAR、trace、下载管理或跨域 OOPIF ref。
