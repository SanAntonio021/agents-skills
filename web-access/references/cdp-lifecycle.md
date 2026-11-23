# 受管浏览器生命周期与任务隔离

先读 [CDP 文档入口](cdp-api.md)。本页处理浏览器启动、恢复、并行对话、登录交接与收尾；端点字段见 [协议参考](cdp-protocol.md)，页面动作见 [交互参考](cdp-interaction.md)。

## 启动与浏览器选择

CDP 路径需要 Node.js 22+。Windows 默认 `existing`，连接当前运行且已开启远程调试的 Edge，复用其登录态。运行时从 Edge 的 `DevToolsActivePort` 发现 CDP 端口；`managed` 仅供用户显式要求隔离任务，不作为默认或自动回退。

以下示例使用已核实的技能目录；若宿主没有提供 `CLAUDE_SKILL_DIR`，将其替换为实际技能路径，不把变量名当作已展开路径。

```bash
# 默认：连接当前 Edge 并检查后台控制能力
node "${CLAUDE_SKILL_DIR}/scripts/check-deps.mjs" --browser edge --mode existing --json
# 只读查看状态，跳过创建后台标签的控制探针
node "${CLAUDE_SKILL_DIR}/scripts/check-deps.mjs" --browser edge --mode existing --status-only --no-probe --json
# 仅在明确需要隔离时选择受管 Profile
node "${CLAUDE_SKILL_DIR}/scripts/check-deps.mjs" --browser edge --mode managed --json
```

- `exit 0`：使用返回的 `proxyUrl`，核对 `protocolVersion: 2` 和所需能力后继续。
- `exit 2`：生产配置或端口覆盖冲突，按输出处理，不以备用端口绕过。
- `exit 1`：按具体原因恢复。existing 模式保留 `cdp_unreachable`、`tab_create_failed`、`action_timeout`、`proxy_version_mismatch`、`control_probe_failed` 和 `task_capacity_reached` 等状态；不得报告成学校权限问题。

所有生产副本读取 `%LOCALAPPDATA%\web-access\config.env`，缺失时由普通启动路径原子创建；`--status-only` 不创建或迁移配置。Windows 默认模式为 `existing`；`managed` 必须明确指定。

`existing` 使用当前 Edge 的调试端口和 Proxy `3456`；端口从 `DevToolsActivePort` 读取，不硬编码。`managed` 使用 `%LOCALAPPDATA%\web-access\managed-edge-profile` 的独立实例。每个任务都在后台创建自有 tab，不修改现有用户页面；任务完成只关闭自有 tab/popup。

正常页面操作不加全局锁。多个对话共享当前 Edge、CDP 连接和 Proxy，但各自创建独立 task/token/tab；后续调用复用现有连接。若当前任务的旧目标 tab 无法可靠读取，可按技能正文用可信完整网址新建后台 tab；新页核实成功后，当前 task 可清理自有旧 tab。CDP 不允许当前 task 关闭其他 task 或用户 tab；非本 task 的旧页只有宿主另有获准的精确句柄关闭接口时才处理，不能用原始 CDP 绕过；不具备该能力时保留旧页。

`check-deps` 只有在 Broker、浏览器身份和真实后台 task/tab 控制探针都通过后才返回 `ready:true`。任务创建使用 `background:true`，不主动激活或抢占用户当前页面。

## 状态恢复与实例身份

CDP 恢复按固定顺序执行：重新读取 `DevToolsActivePort`；校验其端口监听进程与 Edge 身份；尝试 WebSocket 握手和 `Browser.getVersion`；必要时先记录用户原有页面，再正常关闭并重启 Edge，恢复原有页面与任务页并重新验证。HTTP `/json/version` 或 `/json` 返回 404 仅表示 HTTP 发现接口不可用，不能单独判定 CDP 失败。

Proxy 或 Edge 重启会清空 task、token、归属、session 和 ref；浏览器 tab 不会因 Proxy 重启而自动关闭，遗留页面降为用户 tab，不能由新 task 重新接管。CDP 恢复仍失败时，只有在可用且获准的情况下才切 Browser Use 扩展；最后才使用 Computer Use，并在完成后恢复原窗口。

## 维护和版本切换

常规前检复用浏览器身份、端口和协议能力均通过检查的 `existing` Broker，空闲时也保留连接。`check-deps` 的 `brokerVersion` 是当前前检脚本对应的版本，`runningBrokerVersion` 是健康接口返回的运行版本。两者不同时，以运行版本实际声明的能力为准。任务需要的能力缺失时，报告版本差异及缺少的能力。

修改和回归测试使用 `tests/run-integration.mjs` 的隔离进程与模拟 CDP。发布更新安装文件。验收用 `--status-only --no-probe` 和 `/health` 读回在用 Broker 的 PID 与 `lastHandshakeAt`，确认连接继续复用。新版本在 Broker 下次启动时加载。用户明确要求立即切换时，核对 PID、Broker 归属和任务状态，待活动任务与 Broker 自有标签全部清理后，切换一次到正式安装副本。Edge 可能要求授权这条新连接。旧协议按[迁移指南](migration-dual-proxy.2.md#旧-proxy-处理)处理。

## 并行 task 与收尾

多个目标独立且分工有益时可交给子 Agent，说明所需结果、材料和约束，并要求加载 `web-access`；不为简单单页任务强行分工。每个对话或子 Agent 创建独立 task，只使用其 token、自有 tab 和 popup；受管 Edge 与长期 Proxy 复用同一 CDP 连接，任务之间不共享 token，跨浏览器 token 不通用。单个 Proxy 最多同时保留 32 个非终态 task。

任务完成或终止前，先记录并核实用户可重新打开的结果与验收链接，再调用 [complete](cdp-protocol.md#post-v2taskstaskidcomplete)，使用 `keep:false` 关闭自有 tab 和 popup；仅用户明确要求保留时用 `keep:true`。核对关闭回执，超时或未知结果按协议如实报告，不能把 task 已终结当作全部页面已关闭。

handoff 状态先按用户接管流程恢复，不能用 complete 绕开屏障。active task 30 分钟无操作、handoff 30 分钟未恢复都会过期并把尚存 tab 释放给用户。保留长期 Proxy、受管 Edge 和用户原有页面，不把停止 Proxy 或关闭用户浏览器作为收尾步骤。

## 登录与用户接管

复用浏览器已有会话，先判断目标内容是否已可读取。确需登录时核对站点和预期账号，浏览器已自动填充或显示匹配保存账号时可选用并提交。提交前核对常规登录的必选阅读/同意复选框：未选中则在宿主允许的已有授权内勾选，已选中则保持，回读选中状态后提交并验证目标页面。非必选的订阅、记住新凭据、额外权限及新增法律承诺按各自授权处理。

机构下载按 [paper-download 的公开机构访问模块](../../paper-download/references/publisher-download-playbook.md#公开机构访问模块) 执行；登录由 Broker `/access` 完成，不向模型返回字段值。浏览器原生账号下拉框不在 DOM 中、CDP 也碰不到，这时由下面的本机凭据助手接手，不改用 Computer Use；模型和通用网页脚本不读取密码框值、密码管理器内容或导出凭据。

任何自动登录路径在提交前都核对 HTTPS origin、路径、字段归属、同源表单目标与唯一可见登录控件；未知执行结果先查原任务状态，不清提交标记、不盲重填或重复提交。需要系统解锁、MFA、扫码、短信/动态口令、账号歧义或变化的 SSO 发布范围时才交接；邮箱验证码在已有且获授权的邮箱页面或邮件连接器可访问时由 web-access 读取并提交一次。

### 本机凭据助手

同一站点在 Edge 里保存了多个账号时，Edge 只弹原生下拉框、不自动填密码，`/access` 返回 `autofillStatus:"password_not_filled"`。这时 Broker 改用用户自己录入的本机凭据，全程在本任务后台标签里完成，不激活窗口、不抢焦点。浏览器已自动填充时仍优先用浏览器的，凭据助手只作后备。

- **存放**：Windows 凭据管理器的普通凭据，只存本机当前用户、不漫游；键是登录页 origin 加账号（目标名 `web-access/login|<origin>|<account>`）。不读取、不导出 Edge 的密码库、Profile 或 Cookie。
- **首次录入**：用户在自己的 PowerShell 窗口运行 `powershell -NoProfile -ExecutionPolicy Bypass -File "<web-access技能目录>\scripts\login-credential.ps1" -Action Add -Origin https://<登录页主机> -Account <账号>`，在弹出的系统凭据窗口里输入密码。origin 以登录页地址栏为准，只写 `https://主机[:端口]`。`-Action Check` 只报告是否已录入，`List` 只显示打码账号，`Remove` 删除，`SelfTest` 用临时合成条目验证存取。模型不代用户录入，不调用 `BrokerRead`（Broker 内部读取通道）。
- **填写条件**：页面 origin 必须与 Broker 从标签读到的 HTTPS origin 一致；唯一可见的密码框和账号框在同一个表单里；表单的提交目标是同源 HTTPS，且只有一个可用的登录按钮。原生提交按钮须是同源 POST。没有原生提交按钮、由页面脚本提交（如 `<a href="javascript:…">登录</a>`）时，只认唯一的“登录/Sign in”按钮，并在提交窗口内打开网络防护：同源请求放行；跨源请求只放行不带密码的 GET/HEAD；任何 URL 里带密码的请求一律拦截。防护在首个顶层导航或 5 秒后结束，不影响之后的 SSO 跳转。
- **一次提交**：密码由 Broker 作为函数参数传给页面，写入后提交一次；同一 task、标签和登录路径不重放。同一 origin 存了多个账号时，调用方须在请求里给 `account`，否则返回 `account_ambiguous`。
- **可选项不动**：“7天免登录”“记住我”这类可选复选框不属于常规登录必需项，默认不勾选；必选的同意项未勾选时返回 `consent_required`。
- **对外结果**：只返回 `loginMethod`、`credentialStatus`、`submitMode`、`networkGuard` 等脱敏状态，不返回密码或账号。`not_configured` 等状态表示需要用户先录入，不等于学校无权限；提交后仍须回读目标页面。

### 机构联合登录与属性释放

出版商机构登录常经过 SAML/Shibboleth/CARSI：服务提供商 → 发现服务 → 学校 IdP → 统一身份认证密码页 → IdP 属性释放同意页 → 回到服务提供商。用户已授权把“只释放身份类别、所属机构、匿名标识给名单内学术服务商”作为常规登录步骤：Broker 在本任务后台标签里同意（使用条款声明页则勾选同意框）、只记住本服务并提交，回读确认已离开同意页。服务方优先按 SAML 请求里的 SP entityID 核实，页面上不显示服务名也能判断。请求个人属性、服务商不在名单或解析不出属性时停下，返回 `attribute_consent_required`。调用 `/access` 时带 `maxSteps`（如 4）可一次走完整条链路，同意页在密码页之前或之后都能处理。判断条件、名单和状态见[机构联合登录](federated-login.md)。

页面上的“验证码登录”“短信登录”“扫码登录”是切换到其他登录方式的入口，不算当前表单的验证要求。只有激活的表单出现可见验证码输入框，或页面明确要求“请输入……验证码”时，才按验证码或强认证处理。

页面上的普通图形验证码和交互验证可在当前 task 内尝试一次并回读；拒绝后不反复尝试、不切换工具绕过反爬限制。邮箱验证码只有在已授权的邮箱页面或邮件连接器可用时才由 web-access 自动读取最新匹配邮件并提交一次；短信/动态口令、刷脸、系统安全弹窗、账号歧义或邮箱不可访问时保留当前 task 并交接。完成后恢复原 task 并重新取得页面状态。

1. 调用 [handoff](cdp-protocol.md#post-v2taskstaskidhandoff)，指定准确 `targetId`。Proxy 阻止新操作、取消 wait、等待在途操作结束，再激活该 tab。
2. 告知用户需要完成的实际动作。handoff 期间不读取、截图或修改页面。
3. 用户完成后调用 [resume](cdp-protocol.md#post-v2taskstaskidresume)，重新 snapshot，验证目标内容是否可用。

接管超时、激活结果不明和终态恢复按 [Task 契约](cdp-protocol.md#task) 处理，不通过新 task 接管遗留的用户 tab。只需读取时，不因页面显示登录提示而自动发起与目标无关的登录。
