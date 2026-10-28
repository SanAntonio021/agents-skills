# CDP Proxy v2 协议参考

先读 [CDP 文档入口](cdp-api.md)。本页定义连接、task、tab、健康检查、错误码和隔离边界；启动恢复见 [生命周期参考](cdp-lifecycle.md)，页面动作见 [交互参考](cdp-interaction.md)。

## 连接与通用规则

- 默认 `existing`：当前运行的 Edge，HTTP Broker 为 `http://127.0.0.1:3456`；CDP 从 `DevToolsActivePort` 动态发现，不硬编码 `14151` 或 `9222`。
- `managed` 仅用于明确指定的隔离任务，不作为 Windows 默认或自动回退；Chrome 仅显式选择时使用对应 Broker。
- `web-access` 是唯一浏览器执行层；`paper-download` 通过 HTTP Broker 创建后台任务、探测访问及下载，不自行启动或修复浏览器。
- Proxy 只绑定 `127.0.0.1`，只接受匹配端口的 `127.0.0.1`/`localhost` Host。
- 带 `Origin` 的请求被拒绝；Proxy 不返回 CORS 许可头。
- `/health`、`/capabilities` 和创建 task 之外的 `/v2` 请求都要发送 `Authorization: Bearer <taskToken>`。
- 所有 POST/DELETE 都要发送 `Content-Type: application/json` 和 `Idempotency-Key`。
- token 不能进入 URL、日志、错误信息或交付文本。

同一个 `Idempotency-Key` 与完全相同的 method、path、query、body 组合只执行一次。相同 key 配不同请求返回 `409 IDEMPOTENCY_CONFLICT`。mutation 的 CDP 命令开始后超时返回 `504 UNKNOWN_RESULT`；同 key 可重放该结果，但不得换 key 原样重试。

## 协议探测

### `GET /health`

读取 Broker 进程及其已知连接状态，本身不证明目标站点可访问。下面是字段形状示例，不是本机验收记录；探针未执行时 `passed` 可为 `null`：

```json
{
  "service": "web-access-cdp-proxy",
  "status": "ok",
  "protocolVersion": 2,
  "connected": true,
  "browser": {"id": "edge", "label": "Microsoft Edge"},
  "profileMode": "existing",
  "managedProfile": false,
  "managedInstanceId": null,
  "brokerVersion": "<current-broker-version>",
  "cdp": {"connected": true, "port": 0, "wsPathAvailable": true},
  "httpDiscovery": {"required": false},
  "controlProbe": {"passed": true, "checkedAt": "<probe-time>", "background": true},
  "activeTasks": 1,
  "managedTabs": 2
}
```

示例中 `cdp.port` 的 `0` 仅为占位，实际必须使用运行时发现的端口。主前检为 `check-deps.mjs --browser edge --mode existing --json`，要求 `ready:true`、实际 CDP/Proxy 地址、Edge 身份和控制探针通过。`status:"ok"` 只表示 Broker 存活。HTTP `/json/version` 返回 404 仅表示 HTTP 发现接口不可用；继续用发现的 WebSocket 执行 `Browser.getVersion` 和后台建 tab 探针，不能据此单独判定 CDP 失效或重启 Edge。

### `GET /capabilities`

返回协议版本、snapshot/action/wait、`download`、`access` 能力、任务上限、Broker 版本、Profile 模式和明确不支持项。调用方必须确认 `protocolVersion === 2`、`brokerVersion` 与所用源码相符、浏览器身份为请求目标且 `profileMode` 与请求模式一致，默认是 `existing`。新增接口须先核对能力声明；接口缺失属于环境/版本缺口，不回退到业务技能的第二套实现。

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

每个任务新建 `background:true` 的自有 tab，不导航或激活用户原有页面；只有确需用户接管才激活本任务页面。只允许 `http:`、`https:` 和 `about:` URL。Proxy 固定先以 `about:blank` 创建 target，归属当前 task 并完成 attach/session 初始化后，才用 `Page.navigate` 前往请求 URL；返回 `201` 时该显式导航命令已经被浏览器接收。调用方仍应按需要用 `/wait` 与页面回读确认加载结果。Popup 按 `openerId` 自动继承 opener 的 task。

`Target.createTarget` 超时后可能晚到。task 仍为 `active` 或 `handoff` 时，晚到 tab 继续归入原 task 并继续导航到原请求 URL；task 已按默认 `keep:false` 完成时，Proxy 关闭晚到 tab。`expired` 或 `keep:true` 的其他终态不再建立归属，但 Proxy 仍先尝试导航到原请求 URL，再释放给用户，不能遗留无意的空白页。首次返回 `UNKNOWN_RESULT` 后不得换 key 原样重试。

### `GET /v2/tabs`

只返回当前 task 创建的 tab 和 popup。用户已有 tab、其他 task tab 完全隐藏。

### `GET /v2/tabs/{targetId}`

返回当前 task tab 的 `type`、`title`、`url`、`kind`、snapshot `generation` 和待处理 `dialog`（没有时为 `null`）。猜中其他 task 或用户 targetId 仍统一返回 `404 TARGET_NOT_FOUND`。

### `DELETE /v2/tabs/{targetId}`

关闭当前 task 自有 tab。DELETE 仍须携带 JSON content type、空 body `{}` 和 idempotency key。

### `POST /v2/tabs/{targetId}/access`

新增访问契约，仍须 Bearer task token、JSON body 和幂等键：

```json
{"allowAutofill":true}
```

返回脱敏的 `state`、`failureCode`、`handoffRequired`、`interactionRequired`，可附 `reason`、`autofillStatus`；不返回密码、Cookie、认证头或验证码值。`allowAutofill:false` 仅观察，`true` 允许 Broker 在目标账号/HTTPS 同源表单明确、浏览器已自动填充时尝试一次常规登录提交；未知提交结果不能重放。`ready` 只表示访问探针未发现阻碍，`login_submitted` 只表示已尝试提交，均不证明机构订阅或 PDF 已取得。

- 常规登录自动填充与提交归 Broker；业务客户端只消费状态，不另写登录脚本。
- `interactionRequired:true` 不等于人工接管：图形/滑块验证由 `web-access` 页面动作、邮箱验证码由获授权邮件工具按实际能力处理，不承诺全部自动成功。
- 真正短信、动态口令、刷脸或系统级验证才进入 `handoffRequired` 流程；工具限制、账号歧义或能力缺口另行说明，不伪报强验证。handoff 期间禁读、禁截图、禁修改，resume 后回读。
- 发送消息、提交申请、扩大权限或付款不是常规登录，须核对明确目标与授权。

此处规定接口行为；源码存在、能力声明、独立行为验收和真实站点验收应分别核对，不能互相替代。

### `POST /v2/tabs/{targetId}/download`

```json
{"url":"https://publisher.example/article.pdf","timeoutMs":120000,"maxBytes":50000000}
```

可选 `allowedHosts` 仅列已经确认属于该出版物的 PDF 主机；不是任意域名通配许可。同源按 scheme、host、port 一致判定，重定向和 wrapper 内层 URL 逐步按同一策略校验，不为发现主机先请求未确认地址。只取公开或当前已授权的资源，不读取/导出 Cookie，也不绕过付费或站点访问控制。

成功返回完整 PDF 二进制及 `X-Download-Final-Url`（URL 编码）、`X-Download-Bytes`、`X-Download-Sha256`、`X-Download-Is-Pdf` 响应头；客户端解码最终 URL 并复核 `%PDF-`、完整长度和 SHA-256，再做出版物身份/版本验证。响应体和已检查的 HTML wrapper 受大小与超时约束，重定向不重置预算；HTML 本身和半截文件不能成为成功响应。Broker 不写部分文件，调用方全部核验通过后才保存。当前上限取 `/capabilities.download`，不复制另一份页内 fetch/Base64 下载逻辑。

截图、下载细节及非 PDF 媒体取回见 [内容提取参考](cdp-content.md)。

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

业务失败另附分类，不覆盖上述协议状态或既有 CLI 状态：

- 控制层：`cdp_unreachable`、`tab_create_failed`、`action_timeout`、`browser_restart_required`。
- 站点层：`auth_required`、`verification_required`、`access_denied`、`challenge`、`user_handoff_required`。
- 文件层：`not_pdf`、`incomplete`、`identity_mismatch`、`too_large`、`download_timeout`。

401/403/429/418、访问检查页和挑战不做无界重试；仅在控制证据失败时恢复控制层，仍受阻则保留站点原因。不能把它们直接写成学校无订阅，也不能把控制恢复当作下载成功。

## 隔离边界

task token 用于减少多个对话之间的误操作，不是本机安全边界。默认任务共享当前 Edge 内的既有登录态；task/tab 隔离不等于账号、Cookie 或站点权限隔离。不复制 Profile，不读取或导出 Cookie、密码库或认证令牌。显式 `managed` 使用独立上下文，也不把日常 Profile 拷入其中。

Proxy 重启或 CDP 断线时，task、token、归属、session 和 ref 全部清空；浏览器 tab 不关闭，遗留 tab 降为用户 tab 且不能被重新接管。这里的 PDF 下载接口不等于完整浏览器下载管理；网络抓包、HAR、trace 或跨域 OOPIF ref 以实际能力声明为准。控制恢复归 `web-access`：重读端口文件、核对监听进程、WebSocket 探测后才判断是否需要在保全并可恢复页面现场的前提下正常重启；不能恢复归属的遗留页不重新接管，业务任务用已保存元数据重建后台自有页，不自动重放未知动作。
