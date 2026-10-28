# 受管浏览器生命周期与任务隔离

先读 [CDP 文档入口](cdp-api.md)。本页处理浏览器启动、恢复、并行对话、登录交接与收尾；端点字段见 [协议参考](cdp-protocol.md)，页面动作见 [交互参考](cdp-interaction.md)。

## 启动与浏览器选择

CDP 路径需要 Node.js 22+。Windows 默认 `existing`，连接当前运行且已开启远程调试的 Edge，复用其登录态。运行时从 Edge 的 `DevToolsActivePort` 发现 CDP 端口；`managed` 仅供用户显式要求隔离任务，不作为默认或自动回退。

以下示例使用已核实的技能目录；若宿主没有提供 `CLAUDE_SKILL_DIR`，将其替换为实际技能路径，不把变量名当作已展开路径。

```bash
# 默认：连接当前 Edge 并检查后台控制能力
node "${CLAUDE_SKILL_DIR}/scripts/check-deps.mjs" --browser edge --mode existing --json
# 只诊断，不创建或迁移配置，也不启动或修复
node "${CLAUDE_SKILL_DIR}/scripts/check-deps.mjs" --browser edge --mode existing --status-only --json
# 仅在明确需要隔离时选择受管 Profile
node "${CLAUDE_SKILL_DIR}/scripts/check-deps.mjs" --browser edge --mode managed --json
```

- `exit 0`：使用返回的 `proxyUrl`，核对 `protocolVersion: 2` 和所需能力后继续。
- `exit 2`：生产配置或端口覆盖冲突，按输出处理，不以备用端口绕过。
- `exit 1`：按具体原因恢复。existing 模式保留 `cdp_unreachable`、`tab_create_failed`、`action_timeout`、`proxy_version_mismatch`、`control_probe_failed` 和 `task_capacity_reached` 等状态；不得报告成学校权限问题。

所有生产副本读取 `%LOCALAPPDATA%\web-access\config.env`，缺失时由普通启动路径原子创建；`--status-only` 不创建或迁移配置。Windows 默认模式为 `existing`；`managed` 必须明确指定。

`existing` 使用当前 Edge 的调试端口和 Proxy `3456`；端口从 `DevToolsActivePort` 读取，不硬编码。`managed` 使用 `%LOCALAPPDATA%\web-access\managed-edge-profile` 的独立实例。每个任务都在后台创建自有 tab，不修改现有用户页面；任务完成只关闭自有 tab/popup。

正常页面操作不加全局锁。多个对话共享当前 Edge、CDP 连接和 Proxy，但各自创建独立 task/token/tab；后续调用复用现有连接。

`check-deps` 只有在 Broker、浏览器身份和真实后台 task/tab 控制探针都通过后才返回 `ready:true`。任务创建使用 `background:true`，不主动激活或抢占用户当前页面。

## 状态恢复与实例身份

CDP 恢复按固定顺序执行：重新读取 `DevToolsActivePort`；校验其端口监听进程与 Edge 身份；尝试 WebSocket 握手和 `Browser.getVersion`；必要时先记录用户原有页面，再正常关闭并重启 Edge，恢复原有页面与任务页并重新验证。HTTP `/json/version` 或 `/json` 返回 404 仅表示 HTTP 发现接口不可用，不能单独判定 CDP 失败。

Proxy 或 Edge 重启会清空 task、token、归属、session 和 ref；浏览器 tab 不会因 Proxy 重启而自动关闭，遗留页面降为用户 tab，不能由新 task 重新接管。CDP 恢复仍失败时，只有在可用且获准的情况下才切 Browser Use 扩展；最后才使用 Computer Use，并在完成后恢复原窗口。

发现旧 Proxy、协议或 Broker 版本不一致时，按 [迁移指南](migration-dual-proxy.2.md#旧-proxy-处理) 核对浏览器、端口、模式和 PID；只停止可证实属于本技能且无活动任务的 Proxy。不得结束用户 Edge 进程来修复 Proxy 版本。

## 并行 task 与收尾

多个目标独立且分工有益时可交给子 Agent，说明所需结果、材料和约束，并要求加载 `web-access`；不为简单单页任务强行分工。每个对话或子 Agent 创建独立 task，只使用其 token、自有 tab 和 popup；受管 Edge 与长期 Proxy 复用同一 CDP 连接，任务之间不共享 token，跨浏览器 token 不通用。单个 Proxy 最多同时保留 32 个非终态 task。

任务完成或终止前，先记录并核实用户可重新打开的结果与验收链接，再调用 [complete](cdp-protocol.md#post-v2taskstaskidcomplete)，使用 `keep:false` 关闭自有 tab 和 popup；仅用户明确要求保留时用 `keep:true`。核对关闭回执，超时或未知结果按协议如实报告，不能把 task 已终结当作全部页面已关闭。

handoff 状态先按用户接管流程恢复，不能用 complete 绕开屏障。active task 30 分钟无操作、handoff 30 分钟未恢复都会过期并把尚存 tab 释放给用户。保留长期 Proxy、受管 Edge 和用户原有页面，不把停止 Proxy 或关闭用户浏览器作为收尾步骤。

## 登录与用户接管

复用浏览器已有会话，先判断目标内容是否已可读取。确需登录时核对站点和预期账号，浏览器已自动填充或显示匹配保存账号时可选用并提交。提交前核对常规登录的必选阅读/同意复选框：未选中则在宿主允许的已有授权内勾选，已选中则保持，回读选中状态后提交并验证目标页面。非必选的订阅、记住新凭据、额外权限及新增法律承诺按各自授权处理。

机构下载按 [paper-download 的公开机构访问模块](../../paper-download/references/publisher-download-playbook.md#公开机构访问模块) 执行；该模块只在唯一可核验的 HTTPS 自动填充登录表单内提交一次，不向模型返回字段值。原生凭据选择器不在 DOM 中且无法自动填充时，交给用户完成；模型和通用网页脚本不读取密码框值、密码管理器内容或导出凭据。

任何自动登录路径在提交前都核对 HTTPS origin、路径、字段归属、同源表单目标与唯一可见登录控件；未知执行结果先查原任务状态，不清提交标记、不盲重填或重复提交。需要用户录入、系统解锁、MFA、扫码、短信/动态口令、账号歧义或变化的 SSO 发布范围时才交接；邮箱验证码在已有且获授权的邮箱页面或邮件连接器可访问时由 web-access 读取并提交一次。

页面上的普通图形验证码和交互验证可在当前 task 内尝试一次并回读；拒绝后不反复尝试、不切换工具绕过反爬限制。邮箱验证码只有在已授权的邮箱页面或邮件连接器可用时才由 web-access 自动读取最新匹配邮件并提交一次；短信/动态口令、刷脸、系统安全弹窗、账号歧义或邮箱不可访问时保留当前 task 并交接。完成后恢复原 task 并重新取得页面状态。

1. 调用 [handoff](cdp-protocol.md#post-v2taskstaskidhandoff)，指定准确 `targetId`。Proxy 阻止新操作、取消 wait、等待在途操作结束，再激活该 tab。
2. 告知用户需要完成的实际动作。handoff 期间不读取、截图或修改页面。
3. 用户完成后调用 [resume](cdp-protocol.md#post-v2taskstaskidresume)，重新 snapshot，验证目标内容是否可用。

接管超时、激活结果不明和终态恢复按 [Task 契约](cdp-protocol.md#task) 处理，不通过新 task 接管遗留的用户 tab。只需读取时，不因页面显示登录提示而自动发起与目标无关的登录。
