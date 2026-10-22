# 受管浏览器生命周期与任务隔离

先读 [CDP 文档入口](cdp-api.md)。本页处理浏览器启动、恢复、并行对话、登录交接与收尾；端点字段见 [协议参考](cdp-protocol.md)，页面动作见 [交互参考](cdp-interaction.md)。

## 启动与浏览器选择

CDP 路径需要 Node.js 22+。Windows 首次使用默认创建独立、受管的 Edge Profile；沿用用户明确指定的浏览器，没有指定时使用已配置的默认浏览器。受管浏览器不可用时，先处理对应原因，不静默换成日常 Edge、Chrome 或另一个端口。

以下示例使用已核实的技能目录；若宿主没有提供 `CLAUDE_SKILL_DIR`，将其替换为实际技能路径，不把变量名当作已展开路径。

```bash
# Windows 默认：受管 Edge，按需启动并复用同一实例
node "${CLAUDE_SKILL_DIR}/scripts/check-deps.mjs" --browser edge --mode managed --json
# 只诊断，不创建或迁移配置，也不启动或修复
node "${CLAUDE_SKILL_DIR}/scripts/check-deps.mjs" --browser edge --mode managed --status-only --json
# 只有人工明确要求时才使用日常 Edge；失败不回退
node "${CLAUDE_SKILL_DIR}/scripts/check-deps.mjs" --browser edge --mode existing --json
```

- `exit 0`：使用返回的 `proxyUrl`，核对 `protocolVersion: 2` 和所需能力后继续。
- `exit 2`：生产配置或端口覆盖冲突，按输出处理，不以备用端口绕过。
- `exit 1`：按具体原因恢复。受管模式会区分 `managed_profile_busy`、`managed_cdp_port_conflict`、`managed_browser_launch_failed`、`proxy_version_mismatch`、`control_probe_failed` 和 `task_capacity_reached`。只自动修复已核验属于受管 Edge/Proxy 的对象；端口或 Profile 被其他程序占用时停止并报告。

所有生产副本读取 `%LOCALAPPDATA%\web-access\config.env`，缺失时由普通启动路径原子创建；`--status-only` 不创建或迁移配置。现有配置升级时只补充 `WEB_ACCESS_BROWSER_MODE=managed`，保留其他键。

默认模式为 `managed`，使用 `%LOCALAPPDATA%\web-access\managed-edge-profile`、CDP `9222` 和 Proxy `3456`。日常 Edge 只能显式指定 `--mode existing`，以 Edge/Chrome Proxy `3456/3457` 连接用户已开启的调试实例；它不参与受管模式的前检、自动修复或自动回退。

受管启动和修复由全局锁串行化，正常页面操作不加全局锁。多个对话共享同一受管 Edge、CDP 连接和 Proxy，但各自创建独立 task/token/tab；第二次调用应返回 `reused:true`，不建立第二条调试授权连接。

受管 Edge 由 `check-deps.mjs` 启动，不需要用户在日常 Edge 的 `edge://inspect` 页勾选调试开关。首次启动可能显示浏览器窗口；登录 Cookie 存在独立 Profile 中，学校/CARSI/OpenAthens/MFA 仍由用户在页面完成。`check-deps` 完成真实控制探针后才返回 `ready:true`。

## 状态恢复与实例身份

受管 Broker 以当前 `/json/version` 返回的 WebSocket 路径判断浏览器实例，并原子刷新 Profile 内的 `DevToolsActivePort`。旧端点文件不能让 Broker 误连上一实例。

关闭受管 Edge 后再次执行普通 `ensure`，会使用同一 Profile 重启；关闭 Proxy 只重启 Proxy，不关闭浏览器页面。Proxy 或 Edge 重启会清空 task、token、归属、session 和 ref，遗留页面降为用户 tab，不能重新接管。

发现旧 Proxy、协议或 Broker 版本不一致时，按 [迁移指南](migration-dual-proxy.2.md#旧-proxy-处理) 核对浏览器、端口、模式和 PID；只有命令行明确标记为同一受管实例的 Proxy 才允许自动修复。普通旧 Proxy 或日常 Edge Proxy 只报告，不自动结束。

## 并行 task 与收尾

多个目标独立且分工有益时可交给子 Agent，说明所需结果、材料和约束，并要求加载 `web-access`；不为简单单页任务强行分工。每个对话或子 Agent 创建独立 task，只使用其 token、自有 tab 和 popup；受管 Edge 与长期 Proxy 复用同一 CDP 连接，任务之间不共享 token，跨浏览器 token 不通用。单个 Proxy 最多同时保留 32 个非终态 task。

任务完成或终止前，先记录并核实用户可重新打开的结果与验收链接，再调用 [complete](cdp-protocol.md#post-v2taskstaskidcomplete)，使用 `keep:false` 关闭自有 tab 和 popup；仅用户明确要求保留时用 `keep:true`。核对关闭回执，超时或未知结果按协议如实报告，不能把 task 已终结当作全部页面已关闭。

handoff 状态先按用户接管流程恢复，不能用 complete 绕开屏障。active task 30 分钟无操作、handoff 30 分钟未恢复都会过期并把尚存 tab 释放给用户。保留长期 Proxy、受管 Edge 和用户原有页面，不把停止 Proxy 或关闭用户浏览器作为收尾步骤。

## 登录与用户接管

复用浏览器已有会话，先判断目标内容是否已可读取。确需登录时核对站点和预期账号，浏览器已自动填充或显示匹配保存账号时可选用并提交。提交前核对常规登录的必选阅读/同意复选框：未选中则在宿主允许的已有授权内勾选，已选中则保持，回读选中状态后提交并验证目标页面。非必选的订阅、记住新凭据、额外权限及新增法律承诺按各自授权处理。

机构下载按 [paper-download 的公开机构访问模块](../../paper-download/references/publisher-download-playbook.md#公开机构访问模块) 执行；该模块只在唯一可核验的 HTTPS 自动填充登录表单内提交一次，不向模型返回字段值。原生凭据选择器不在 DOM 中且无法自动填充时，交给用户完成；模型和通用网页脚本不读取密码框值、密码管理器内容或导出凭据。

任何自动登录路径在提交前都核对 HTTPS origin、路径、字段归属、同源表单目标与唯一可见登录控件；未知执行结果先查原任务状态，不清提交标记、不盲重填或重复提交。需要用户录入、系统解锁、MFA、扫码、短信/邮件验证码或动态口令、账号歧义或变化的 SSO 发布范围时才交接。

页面上的普通字母或数字图形验证码无需先 handoff：先读当前页面和截图，只依据实际显示的图像识别字符；用最新输入框引用填写，点击提交，再回读通过提示、页面跳转或目标内容。辨认不清时先重取截图或点击刷新验证码；仍无法识别或服务端反复拒绝时才说明原因并交接。短信、邮件验证码及动态口令属于身份验证，继续按用户接管步骤处理。

1. 调用 [handoff](cdp-protocol.md#post-v2taskstaskidhandoff)，指定准确 `targetId`。Proxy 阻止新操作、取消 wait、等待在途操作结束，再激活该 tab。
2. 告知用户需要完成的实际动作。handoff 期间不读取、截图或修改页面。
3. 用户完成后调用 [resume](cdp-protocol.md#post-v2taskstaskidresume)，重新 snapshot，验证目标内容是否可用。

接管超时、激活结果不明和终态恢复按 [Task 契约](cdp-protocol.md#task) 处理，不通过新 task 接管遗留的用户 tab。只需读取时，不因页面显示登录提示而自动发起与目标无关的登录。
