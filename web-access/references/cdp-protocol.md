# CDP Proxy v2 协议参考

先读 [CDP 文档入口](cdp-api.md)。本页定义连接、task、tab、健康检查、错误码和隔离边界；启动恢复见 [生命周期参考](cdp-lifecycle.md)，页面动作见 [交互参考](cdp-interaction.md)。

## 连接与通用规则

- 受管 Edge Proxy：`http://127.0.0.1:3456`（浏览器 CDP：`127.0.0.1:9222`）
- 日常 Edge 显式模式：`http://127.0.0.1:3456`；Chrome 显式模式：`http://127.0.0.1:3457`
- `paper-download` 机构模块只接受受管 Edge，不接受日常 Edge 或 Chrome 的 `existing` 模式。
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
  "profileMode": "managed",
  "managedProfile": true,
  "managedInstanceId": "0123456789abcdef01234567",
  "brokerVersion": "managed-edge.1",
  "activeTasks": 1,
  "managedTabs": 2
}
```

### `GET /capabilities`

返回协议版本、snapshot/action/wait 能力、任务上限、Broker 版本、Profile 模式和明确不支持项。调用方必须确认 `protocolVersion === 2`、`brokerVersion` 与当前源码一致；受管模式还必须确认 `profileMode === "managed"`。

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

如果 `Target.activateTarget` 在 CDP 命令开始后超时，请求返回 `504 UNKNOWN_RESULT`，但 task 保持 `handoff`，不会退回 `active`。这是 fail-closed 行为：不得读取或修改页面；先查看 task 状态，由用户完成接管后再 `resume`。操作边界见 [登录与用户接管](cdp-lifecycle.md#登录与用户接管)。

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

只允许 `http:`、`https:` 和 `about:` URL。Proxy 固定先以 `about:blank` 创建 target，归属当前 task 并完成 attach/session 初始化后，才用 `Page.navigate` 前往请求 URL；返回 `201` 时该显式导航命令已经被浏览器接收。调用方仍应按需要用 `/wait` 与页面回读确认加载结果。Popup 按 `openerId` 自动继承 opener 的 task。

`Target.createTarget` 超时后可能晚到。task 仍为 `active` 或 `handoff` 时，晚到 tab 继续归入原 task 并继续导航到原请求 URL；task 已按默认 `keep:false` 完成时，Proxy 关闭晚到 tab。`expired` 或 `keep:true` 的其他终态不再建立归属，但 Proxy 仍先尝试导航到原请求 URL，再释放给用户，不能遗留无意的空白页。首次返回 `UNKNOWN_RESULT` 后不得换 key 原样重试。

### `GET /v2/tabs`

只返回当前 task 创建的 tab 和 popup。用户已有 tab、其他 task tab 完全隐藏。

### `GET /v2/tabs/{targetId}`

返回当前 task tab 的 `type`、`title`、`url`、`kind`、snapshot `generation` 和待处理 `dialog`（没有时为 `null`）。猜中其他 task 或用户 targetId 仍统一返回 `404 TARGET_NOT_FOUND`。

### `DELETE /v2/tabs/{targetId}`

关闭当前 task 自有 tab。DELETE 仍须携带 JSON content type、空 body `{}` 和 idempotency key。

截图和资源取回见 [内容提取参考](cdp-content.md)。

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

task token 用于减少多个对话之间的误操作，不是本机安全边界。其他本地进程仍可能直接访问浏览器 CDP。受管 Edge 使用独立 Profile 和 Cookie 目录，与日常 Edge 分开；同一受管 Profile 内的多个 task 仍共享登录态、Cookie 和浏览器上下文，task/tab 隔离不等于站点权限隔离。

Proxy 重启或 CDP 断线时，task、token、归属、session 和 ref 全部清空；浏览器 tab 不关闭，遗留 tab 降为用户 tab 且不能被重新接管。首版不提供网络抓包、HAR、trace、下载管理或跨域 OOPIF ref。
