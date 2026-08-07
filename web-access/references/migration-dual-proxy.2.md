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

1. 运行 `check-deps.mjs --json`，确认 `protocolVersion` 为 `2`。
2. `POST /v2/tasks` 创建 task，安全保存一次性返回的 `taskToken`。
3. 所有后续请求发送 `Authorization: Bearer <taskToken>`。
4. `POST /v2/tabs` 创建自有 tab。不得寻找或接管用户已有 tab。
5. 读取 snapshot，用最新 generation 的 ref 执行 action；页面变化后重新 snapshot。
6. 需要密码、MFA、验证码或 SSO consent 时 handoff；用户完成后 resume 并重新 snapshot。
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

新主路径不是 CSS 或 `/eval`，而是：

```text
GET snapshot -> POST action(ref) -> GET snapshot 或 GET tab 验证
```

CSS click 仅作次级兜底，`/eval` 最后使用。

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
  -d '{"url":"https://example.com?a=1&b=2"}'

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
- 密码、MFA、验证码、SSO consent 和歧义账号选择由用户完成。
- 敏感信息首次输入，以及最终提交、发送、发布、文件上传、付款、删除、授权和账号变更前确认。

## 旧 Proxy 处理

`check-deps.mjs --json` 发现 `protocolVersion` 不是 `2` 时只报告迁移，不自动结束旧进程。先按输出核对准确浏览器、端口和 PID，再针对这一次停止或重启单独取得用户明确授权；批准候选、安装技能或允许后续测试都不等于授权运行时重启。获得授权后才显式重启对应 Proxy；浏览器保持打开。首次由新 Proxy 重新连接时，浏览器仍可能再显示一次远程调试授权提示。

不要同时让旧、新 Proxy 争用同一端口。Edge 与 Chrome 分别处理；重启其中一个不应影响另一个。

## 与 v2.5.3 迁移的关系

`migration-2.5.3.md` 只解释裸 URL 从 query 改 POST body 的历史变化。dual-proxy.2 再次改为 JSON `/v2` 协议；当前调用以本文为准。旧站点经验中发现无版本路由时，应更新源文件，而不是只修正单次命令。
