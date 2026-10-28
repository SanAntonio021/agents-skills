# dual-proxy.2 迁移指南：无版本 API 改为 task-scoped `/v2`

## 迁移结论

dual-proxy.2 不兼容旧无版本操作路由。旧调用统一收到：

```json
{
  "error": "LEGACY_API_DISABLED",
  "migration": "references/migration-dual-proxy.2.md"
}
```

HTTP 状态为 `410 Gone`。不要自动降级或临时恢复旧路由；创建 task、使用 Bearer token，并把 tab 操作迁移到 `/v2`。

## 最小调用流程

1. 运行 `check-deps.mjs --browser edge --mode existing --json`，确认 `ready:true`、协议 `2`、当前 Edge 身份和控制探针。CDP 地址从 `DevToolsActivePort` 动态发现；HTTP `/json/version` 404 不等于 WebSocket CDP 不可用。
2. `POST /v2/tasks` 创建 task，安全保存一次性返回的 `taskToken`。
3. 所有后续请求发送 `Authorization: Bearer <taskToken>`。
4. `POST /v2/tabs` 用 `background:true` 新建自有 tab，不改变用户原活动页；不得寻找、导航、接管或关闭用户已有 tab。
5. 读取 snapshot，用最新 generation 的 ref 执行 action；页面变化后重新 snapshot。
6. 通过 Broker `/access` 取得脱敏状态；常规保存账号登录归 Broker，图形/滑块验证由 `web-access` 页面动作、邮箱验证码由获授权邮件工具按实际能力处理。真正短信、动态口令、刷脸或系统验证才 handoff，完成后 resume 并重新 snapshot；不把所有登录或验证码都默认交给用户。PDF 只调用 `/download`，完整字节与身份/版本核验后才保存。
7. 最后 `POST /v2/tasks/{taskId}/complete`。默认关闭 task 创建的 tab；`keep:true` 才保留并释放。

所有 POST/DELETE 请求都使用 JSON body，并带唯一 `Idempotency-Key`。

## 路由对照

| dual-proxy.1 及更早 | dual-proxy.2 |
|---|---|
| `GET /targets` | `GET /v2/tabs` + Bearer token；只列当前 task tab |
| `POST /new`，body 为裸 URL | `POST /v2/tabs`，body 为 `{"url":"..."}` |
| `GET /close?target=ID` | `DELETE /v2/tabs/ID`，body 为 `{}` |
| `GET /info?target=ID` | `GET /v2/tabs/ID` |
| `GET /screenshot?target=ID&file=...` | `GET /v2/tabs/ID/screenshot`；响应为图片数据，调用方自行保存 |
| `POST /navigate?target=ID`，body 为裸 URL | `POST /v2/tabs/ID/navigate`，body 为 `{"url":"..."}` |
| `GET /back?target=ID` | `POST /v2/tabs/ID/back`，body 为 `{}` |
| `POST /eval?target=ID`，body 为 JS 字符串 | `POST /v2/tabs/ID/eval`，body 为 `{"expression":"..."}` |
| `POST /click?target=ID`，body 为 selector | `POST /v2/tabs/ID/click`，body 为 `{"selector":"..."}` |
| `POST /clickAt?target=ID` | `GET snapshot` 后 `POST /v2/tabs/ID/action`，body 使用 `{"action":"click","ref":"..."}` |
| `POST /setFiles?target=ID` | `POST /v2/tabs/ID/set-files` |
| `GET /scroll?target=ID&...` | `POST /v2/tabs/ID/scroll`，参数放 JSON body |
| 业务技能内登录/验证探测 | `POST /v2/tabs/ID/access`，body 为 `{"allowAutofill":true}`；返回脱敏状态 |
| 业务技能内 CDP/fetch/Base64 PDF 下载 | `POST /v2/tabs/ID/download`，body 含 `url`、`timeoutMs`、`maxBytes`；完整二进制与元数据 |

新主路径不是 CSS 或 `/eval`，而是：

```text
GET snapshot -> POST action(ref) -> GET snapshot 或 GET tab 验证
```

CSS click 仅作次级兜底，`/eval` 最后使用；不能因此在 `paper-download` 中保留第二套登录、验证码、浏览器启动或 PDF 字节提取。新接口契约见 [协议参考](cdp-protocol.md)，调用前核对 `/capabilities`，缺接口按版本/环境缺口报告，不用旧逻辑补洞。文档迁移不等于实现、真实站点验收或发布通过。

## 调用示例

旧：

```bash
curl -s -X POST --data-raw 'https://example.com?a=1&b=2' \
  "http://127.0.0.1:3456/new"
curl -s -X POST "http://127.0.0.1:3456/click?target=ID" \
  -d 'button.submit'
```

新：

```bash
curl -s -X POST "http://127.0.0.1:3456/v2/tasks" \
  -H "Content-Type: application/json" -H "Idempotency-Key: create-task-1" \
  -d '{"label":"current-user-request"}'

curl -s -X POST "http://127.0.0.1:3456/v2/tabs" \
  -H "Authorization: Bearer TASK_TOKEN" \
  -H "Content-Type: application/json" -H "Idempotency-Key: create-tab-1" \
  -d '{"url":"https://example.com?a=1&b=2","background":true}'

curl -s -H "Authorization: Bearer TASK_TOKEN" \
  "http://127.0.0.1:3456/v2/tabs/ID/snapshot?mode=interactive"

curl -s -X POST "http://127.0.0.1:3456/v2/tabs/ID/action" \
  -H "Authorization: Bearer TASK_TOKEN" \
  -H "Content-Type: application/json" -H "Idempotency-Key: click-submit-1" \
  -d '{"action":"click","ref":"r4"}'
```

## 行为变化

### tab 可见性

- 旧 `/targets` 可列出浏览器全部页面；新 `/v2/tabs` 只返回当前 task 创建的 tab 和 popup。
- 其他 task 或用户 tab 即使 targetId 被猜中，也返回 `404 TARGET_NOT_FOUND`。
- 首版没有 attach/import 接口。不能把遗留 tab 重新纳入 task。

### task 与 token

- Edge task token 不能用于 Chrome，反之亦然。
- active task 30 分钟无操作后过期；handoff 30 分钟超时后过期。
- handoff 的 tab 激活命令若超时，task 仍保持 handoff，禁止页面读取或修改；这是 fail-closed，不会自动退回 active。
- handoff task 不能直接 complete；用户接管结束后必须先 resume，并重新 snapshot。
- Proxy 重启保留浏览器 tab，但清空 task、token、所有权和 ref；遗留 tab 降为用户 tab。
- task token 只防止多个对话误操作，不是本机安全边界，也不提供独立 Cookie/Profile。

### ref 与重试

- ref 只属于最近 snapshot 的 generation。导航、动态重绘、dialog 和 resume 后重新 snapshot。
- `STALE_REF` 不重试旧 ref。
- `UNKNOWN_RESULT` 表示动作可能已执行。先读取页面状态，不得原样重试。
- 幂等 key 只能复用在完全相同的 method/path/body 上。
- 建 tab 的结果若晚到，active/handoff task 会继续接管该 tab；task 已按默认 `keep:false` 完成时会关闭它。
- complete 中关闭 tab 若超时，task 仍终结为 completed，剩余 tab 解除归属；它们可能随后关闭，也可能保留为用户 tab。
- handoff、complete 或 expiry 会取消 wait；取消在 attach 前或查询结果晚到时仍优先。长操作完成后，task/tab 空闲计时从完成时重新开始。

### 用户接管与确认

- handoff 状态禁止读取、截图和修改页面。
- 浏览器内已有会话优先复用；匹配账号的常规自动填充与提交归 Broker，业务技能不接触凭据。`interactionRequired:true` 不等于 `handoffRequired:true`；图形/滑块/邮箱验证由 `web-access` 按实际工具能力处理，不保证全自动通过。真正短信、动态口令、刷脸、系统验证才交还用户；账号歧义、工具限制或能力缺口单独说明，不冒充强验证。
- 敏感信息输入及最终提交、发送、发布、上传、付款、删除、授权和账号变更按当前任务的准确授权处理；核对目标、账号、动作和内容，缺少授权或实际要素变化时才询问，不重复确认同一范围。

## 旧 Proxy 处理

所有生产副本统一读取 `%LOCALAPPDATA%\web-access\config.env`。Windows 默认 `existing`，复用当前 Edge；CDP 端口动态发现，不硬编码 `14151` 或 `9222`，Edge Broker 使用 `3456`。`managed` 仅显式隔离任务使用，不自动回退；不复制 Profile，不读取或导出 Cookie、密码库或认证令牌。不要让源码副本、CC Switch 副本或不同 Agent 目录各自创建生产 Broker。Broker 生产端口保持统一；临时端口仅供系统临时目录隔离根下显式 `WEB_ACCESS_TEST_MODE=1` 的测试。

启动过程先绑定 Proxy 端口，再连接浏览器 CDP。并发启动只有端口胜者能连接浏览器；收到 `EADDRINUSE` 的进程最多等待现有监听者就绪，并严格核验协议版本、浏览器、Proxy 端口、CDP 端口和 task 隔离能力。核验通过后退出，让调用方复用现有 Proxy；核验失败则失败关闭，不停止占用者、不改用备用端口。

同一 Edge 进程与 `3456` 上的正式 Proxy 都保持存活时，只应存在一条正式 Proxy 到该 Edge CDP 的连接，通常只需授权一次。反复出现“允许对此浏览器实例进行远程调试”时，优先排查第二个 Proxy 端口或进程；关闭浏览器、停止正式 Proxy、迁移旧 Proxy 或连接断开后重建，下一次连接仍可能再次提示。

迁移只由 `web-access` 前检负责。旧 managed 默认遗留的 Proxy 占用正式端口时，只有 `/health`、进程命令行和实例 ID 能证明归属、且无活动 task，才在已有授权内更换该 Proxy；不为切模式关闭对应浏览器。协议/版本不符、归属不明或有活动 task 时保留状态并报告，不终止未知进程或换备用端口。`paper-download` 只消费前检结果，不实现启动、探测或修复。

停止已获授权的旧 PID 后，如果同一端口已由不同 PID 监听，不要把它直接判作停止失败，也不要继续终止新 PID。先重新读取新进程的创建时间和命令行，确认脚本路径、浏览器和端口；再检查 `/health` 与 `/capabilities`。只有目标身份一致、`protocolVersion: 2` 且能力握手成功时，才把它视为迁移完成。否则停止后续操作，并针对新的准确 PID 重新取得授权。

不要同时让旧、新 Proxy 争用同一端口。Edge 与 Chrome 分别处理；重启其中一个不应影响另一个。

控制失败恢复依次为：重读 `DevToolsActivePort` → 校验监听进程 → WebSocket `Browser.getVersion` 与后台建 tab 探针 → 确认页面现场可保全和恢复后才必要地正常关闭/重启 Edge → 恢复页面现场并复核控制。原 task/token 失效时不接管已释放的遗留页，用保存的业务元数据重建后台自有任务，不重放结果未知动作。仍失败才使用已可用 Browser Use 扩展，最后才 Computer Use；可能切前台时说明并在结束后恢复原窗口。HTTP 发现 404 本身不启动此恢复流程。

控制层、站点层和文件层错误分别保留，完整分类见 [协议参考](cdp-protocol.md#主要错误码)。401/403/429/418、访问检查或挑战不触发无界重试；有实际控制故障时最多一次控制恢复，仍失败记录站点原因，不误报学校无权限。`paper-download` 的 CLI 命令和既有业务状态保持兼容，新增失败码不替换旧状态。

## 与 v2.5.3 迁移的关系

`migration-2.5.3.md` 只解释裸 URL 从 query 改 POST body 的历史变化。dual-proxy.2 再次改为 JSON `/v2` 协议；当前调用以本文为准。普通业务遇到旧站点经验时按当前接口完成任务；只有用户已授权维护技能或站点经验时才更新对应源码，不追加维护关口。


已完成 CDP 初始化的连接意外断开后，原 Proxy 等待 250 ms 后仅自动重连一次；该次失败不进行后台循环重试，初次启动失败也不自动循环。显式停止 Proxy 会取消尚未执行的重连。恢复仍使用原浏览器配置和独立 Proxy 端口，不创建或替换服务；浏览器可能再次要求用户授权。断线时原 task token 和标签页归属仍失效，不因重连恢复，浏览器标签页本身保留。恢复连接不等于恢复中断的业务操作，不自动重放命令。
