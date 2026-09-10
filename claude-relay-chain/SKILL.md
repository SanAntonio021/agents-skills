---
name: claude-relay-chain
description: >
  Windows 上诊断和配置 Claude Code、VS Code 中的 Claude Code 扩展、Claude Desktop on 3P
  内置 Code、CC Switch 的 Claude/Claude Desktop 双入口，以及第三方中转站。用户提到
  Developer Mode、Configure Third-Party Inference、ANTHROPIC_BASE_URL、Anthropic Messages
  API、/v1/messages、/v1/models、127.0.0.1:15721、Claude Desktop 模型发现、CC Switch
  直连模式或本地路由/模型映射模式、OpenAI/Gemini 接口转换、配置能回复但另一入口失败，
  或要求导入/切换/排查 Claude 中转供应商时，优先使用本技能。
  需要核对 CC Switch 的 Claude 后台工具就绪状态并继续只读链路诊断时，也使用本技能。
compatibility: Windows PowerShell 5.1 or later; Python 3 is optional for read-only CC Switch database inspection.
---

# Claude 中转链排障

## CC Switch 后台入口与现有诊断

先读取启动用户主目录下 `.agent-rules/local.md` 的“规则维护目录”字段，再读取该目录下
`automation/ccswitch-background/README.md`；入口为同目录 `Invoke-CcSwitchBackground.ps1`。
使用已经展开并核验的绝对路径；字段、组件或固定 CLI 校验缺失时报告不可用，不猜路径、不从 PATH
替换同名程序。步骤以共用指南为准，此处不复制配置维护实现。

共用入口本轮仅支持 `-App claude -Mode Inspect`，用于确认固定后台工具就绪；不提供 Claude 配置
写入能力，也不代替下文 `audit-claude-relay.ps1` 的供应商、双入口、模型映射及请求链路审计。
保留现有诊断和已授权配置维护职责；不能把 Codex 的 Preview/Apply 用于 Claude 配置。
CC Switch 操作全程不切换窗口、不模拟键鼠、不驱动交互式终端。未覆盖的修改先查受支持后台接口；
后台无法完成时报告具体缺口，只暂停依赖该接口的修改，不转用界面脚本、手工数据库写入或覆盖生成配置。

## 目标

按问题诊断以下链路，已有准确修复授权时完成必要配置变更及验证：

```text
独立 Claude Code / VS Code 扩展 -> CC Switch Claude -> 第三方中转站
Claude Desktop Cowork / 内置 Code -> Desktop 3P profile -> 直连供应商或 CC Switch Claude Desktop -> 第三方中转站
```

不要因为其中一条能回复，就断言另一条也已配置成功。

## 强制边界

1. 先检查当前证据；诊断请求覆盖必要的只读检查和本地备份。按已有准确授权推进修改。
2. 修改前简短说明具体对象、改动和必要影响，保存相应备份与恢复依据；沿用已确认方案，不重复生成批准模板。
3. 本地备份和受支持的非计费只读检查无需另问。配置修改、provider 切换、重启或收费验证按当前准确授权执行，缺少授权时只暂停该动作。
4. 实质目标、范围或风险改变时重新判断授权；同范围重试和工具实现调整不自动要求再次确认。
5. 不输出 API key、OAuth token、gateway token、完整认证 JSON、带凭据的命令行或完整响应正文。
6. 不直接修改 `%USERPROFILE%\.cc-switch\skills`、`.claude\skills` 或 `.codex\skills` 中的运行时副本。

## 先区分四个对象

| 对象 | 配置入口 | 关键事实 |
|---|---|---|
| 独立 Claude Code CLI | `%USERPROFILE%\.claude\settings.json`，通常由 CC Switch 的 `Claude` provider 渲染 | 这里的成功不能证明 Desktop 3P 成功 |
| VS Code Claude Code 扩展 | Claude Code 设置和扩展进程环境 | 通常与独立 Claude Code 同类排查，但还要检查扩展是否重载旧环境 |
| Claude Desktop 内置 Code | Claude Desktop 3P profile | 自动继承 Desktop 的 provider、endpoint、credentials 和 model list |
| CC Switch | `Claude` 与 `Claude Desktop` 是两个独立 app/provider 集合 | 不能把第一个入口当前 provider 当成第二个入口当前 provider |

表面不明确时，只问一个问题：失败发生在独立 Claude Code/VS Code，还是 Claude Desktop 的 Cowork/内置 Code？已有对话和本机证据能回答时，不重复询问。

完整配置归属和优先级见 [references/surfaces-and-config.md](references/surfaces-and-config.md)。

## Claude Code 模型角色、兜底与 1M

用户问 VS Code Claude Code 的 `Default`、`opus`、供应商页面的“默认兜底模型”或 `1M` 时，先限定在 `app_type = 'claude'` 的链路；不要把 Claude Desktop 的模型路由混进判断。

1. 把当前 provider 的 `settings_config.env` 中以下字段分开读取，且只报告模型 ID、是否存在凭据和安全的 endpoint，不输出完整 JSON 或密钥：
   - 角色实际请求模型：`ANTHROPIC_DEFAULT_SONNET_MODEL`、`ANTHROPIC_DEFAULT_OPUS_MODEL`、`ANTHROPIC_DEFAULT_FABLE_MODEL`、`ANTHROPIC_DEFAULT_HAIKU_MODEL`。
   - 角色显示名：对应的 `*_MODEL_NAME`。显示名只影响 `/model` 菜单呈现，不是实际请求的充分证据。
   - 默认兜底：`ANTHROPIC_MODEL`。它用于未明确指定 Sonnet、Opus、Fable、Haiku 角色的请求；它不是自动故障转移，也不会替代一个已明确选择的角色。
2. `model: "opus"`、`/model` 的 `Default` 或 `Opus` 走 `ANTHROPIC_DEFAULT_OPUS_MODEL`，而不是 `ANTHROPIC_MODEL`。因此，若用户把兜底设为 `claude-opus-4-6`，但 Opus 角色仍指向另一模型，Default/Opus 不会自动改为 4.6。以当前 Claude Code 的本地变更记录和实际请求日志为准，不凭界面文案猜测。
3. CC Switch 的 Sonnet、Opus、Fable、Haiku 是独立角色槽位。不要为了保留第二个 Opus 变体而擅自占用 Fable；若用户同时要保留 Fable 和两个 Opus 变体，说明当前角色菜单没有额外槽位，建议另建明确用途的 provider/configuration，或仅在目标客户端确实支持时使用直接模型 ID。
4. 判断有效映射时，按三个层次对照：当前 `providers.is_current` 记录、CC Switch 渲染出的 `%USERPROFILE%\.claude\settings.json`、以及本地代理日志或 `proxy_request_logs` 的 `request_model` 与实际 `model`。三者不一致是配置漂移；不能因数据库或截图其中之一正确，就声称端到端使用了该模型。
5. `1M` 复选框、`[1m]` 模型后缀或网关接受该 ID，只表示客户端/网关接受了 1M 变体请求，不证明上游实际提供 1M 上下文。优先查返回元数据中的 `context_window`；没有该字段时，只有经用户同意且成本可接受的超过 200K token 受控边界测试才能确认。模型列表出现、请求成功，或后端静默改写为另一模型，均不能替代该验证。

## 工作流程

### 1. 按故障选择只读检查

先从当前对话、文件和日志查明失败对象：局部模型映射问题只看对应 provider、渲染配置及必要请求日志；
Desktop 模型发现问题看对应 profile、路由和模型列表。只有相关线索指向另一入口时才只读扩查。
明确要求完整审计或现有线索不足以定位链路时，可运行现有全量只读脚本：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\audit-claude-relay.ps1"
```

需要机器可读结果时加 `-AsJson`。脚本只读取配置、注册表存在性、监听端口和 CC Switch DB 的脱敏字段；不会发送网络请求或修改文件。

完整审计覆盖以下项目；局部检查只取与当前问题有关的项目，不修改脚本接口：

- CC Switch 版本、进程和 `15721` 监听状态。
- `currentProviderClaude` 与 `currentProviderClaudeDesktop`。
- `%USERPROFILE%\.claude\settings.json` 的 base URL、模型和凭据是否存在；只报存在性。
- Desktop 3P 是否由 HKLM/HKCU managed policy 管理，还是使用本地 `configLibrary`。
- `_meta.json` 的 `appliedId`、实际 profile、gateway base URL、认证方案和凭据存在性。
- CC Switch 当前 Claude Desktop provider 的 `meta.claudeDesktopMode`、`meta.apiFormat` 和模型映射数量。

若 Python 3 不存在，脚本仍完成文件、注册表和端口检查，但把 CC Switch DB 检查标为 `UNAVAILABLE`，不能据此猜测模式。

#### 自动故障转移专项审计

用户询问自动切换，或日志提示故障转移与当前问题有关时执行本节。不能把“当前 provider 没变”当成“期间没有发生切换”。记录所查时段；现场观察时记下 `audit_started_at`（使用本机北京时间），并核对以下资料：

1. `proxy_config.auto_failover_enabled`：报告当前开关；字段缺失时写 `未验证`。
2. 当前 Claude provider 的 `providers.in_failover_queue`、`provider_health` 和 `proxy_request_logs`：只读出 provider ID、`app_type`、状态/错误类别、时间和模型等脱敏字段，不输出凭据或完整请求内容。表或列不存在时记录 `UNAVAILABLE`，不得用缺失当作“没有故障”。
3. CC Switch 日志中的 `[FO-001]`：把它作为实际发生的 provider 切换证据，记录事件时间、脱敏的源/目标 provider 和结果。

按 `audit_started_at` 将 `[FO-001]` 和请求日志分成“审计前历史”和“审计窗口新增”。即使 provider 后来切回原值，只要窗口内出现过 `[FO-001]`，仍必须报告实际发生过自动切换；最终 provider 只描述当前状态，不能覆盖事件证据。若只能确认配置开关、不能确认事件，分别写清“配置状态已证实、实际切换未证实”，不要推断。

### 2. 自动判断 CC Switch 模式

问题涉及 Desktop 时，以 CC Switch DB 当前 `app_type = 'claude-desktop'` provider 的结构化字段为准：

- `meta.claudeDesktopMode = direct`：直连模式。Desktop profile 应指向供应商远端 `ANTHROPIC_BASE_URL`。只支持原生 Anthropic Messages API；`meta.apiFormat` 应为 `anthropic`。
- `meta.claudeDesktopMode = proxy`：本地路由/模型映射模式。Desktop profile 应指向 `http://127.0.0.1:<port>/claude-desktop`，CC Switch 再按模型映射转发或转换接口。
- 字段缺失、DB 无当前 provider、profile 与预期地址不一致：状态不明确或配置漂移。不要靠 provider 名称推断。

本地路由模式可承接 CC Switch 支持转换的 Anthropic、OpenAI、Gemini 等上游格式；是否可用仍必须由该版本 CC Switch 的实际 provider `apiFormat`、模型映射和端到端请求证明。

CC Switch 3.18 的结构、限制和地址规则见 [references/cc-switch-desktop-3p.md](references/cc-switch-desktop-3p.md)。

### 3. 按证据归因

| 现象 | 首要检查 | 不足以证明 |
|---|---|---|
| 独立 Claude Code 能回复，Desktop 失败 | Desktop applied profile、managed policy、Desktop provider | `.claude\settings.json` 正常不证明 Desktop 正常 |
| Desktop 能回复，独立 Claude Code 失败 | CC Switch `Claude` provider、`.claude\settings.json`、扩展进程环境 | Desktop profile 正常不证明 CLI 正常 |
| Cowork 正常，内置 Code 无模型 | `/v1/models`、`inferenceModels`、模型 ID、已知 prefix 问题 | `/v1/messages` 成功不证明 model discovery 成功 |
| 能聊天但 tool use 失败 | 请求/响应 tool blocks、streaming、beta headers | 普通文本回复不证明 Claude Code 可用 |
| 直连模式选择 OpenAI/Gemini 上游失败 | `claudeDesktopMode`、`apiFormat` | provider 能被导入不证明直连模式支持 |
| 修改 profile 后仍用旧值 | managed policy 优先级、完整退出重开 | 文件时间变化不证明应用已重载 |

#### 模型发现专项检查

出现以下任一现象时必须执行本节：普通聊天或 Cowork 能回复，但内置 Code 没有模型；配置页显示 `Invalid: Model list`；模型选择器为空；1M context 选项消失。

1. 先记录当前 Claude Desktop、内置 Code 与 CC Switch 版本，以及当前 Desktop provider 的 `direct`/`proxy`、applied base URL、`inferenceModels` 和 route 数量。用户描述的模式若与实时状态不同，以实时结构化证据为准并明确纠正前提。
2. 分开检查根 `/v1/models` 与本地路由 `/claude-desktop/v1/models`。诊断范围内可执行受支持的非计费只读请求，不泄露凭据；无法验证的接口如实标为 `未验证`。
3. 现有资料不能解释故障且症状吻合时，定向核对历史问题候选：
   - `#4540`：关注 namespace 和返回结构不一致，例如根路径返回 `{"models":[]}`，而 Desktop 需要可识别的模型数组或正确 `data` 结构。
   - `#4415`：关注从模型 route 合成列表失败、空列表，以及 `supports1m` 没有正确反映到 1M model variant 或 `context_window`。
4. 使用这些候选作判断时，重新核对对应 issue 当前状态和本机版本。issue 仍开放不证明本机必然命中；issue 已关闭也不证明当前安装版本已经包含修复。
5. 只报告实际相关的候选及本机依据，无关或未查询的历史编号不列为必填项。

通过标准与带日期的历史问题记录见 [references/verification-and-known-issues.md](references/verification-and-known-issues.md)。

### 4. 准备准确改动并按已有授权执行

只读请求交付原因和建议；明确要求修复时，准备可核对的具体改动并复用授权继续。
存在无法查明且影响功能、范围或正在进行工作的取舍时，只问该问题；其余工作继续。

### 5. 执行已授权修改

执行顺序固定：

1. 重新读取目标文件和 DB 状态，确认没有从审计后发生变化。
2. 备份这次将修改的具体对象；数据库备份必须可打开，文件备份记录 SHA-256。
3. 通过当前确实支持该动作的后台接口做最小改动，保持 CC Switch 的配置归属；Inspect 不能用于写入，接口不可用时按开头规定报告。
4. 需要重新加载配置时，只处理受影响的应用。先核对运行任务与未保存工作及已有授权，避免中断用户工作；具备条件才正常重载或退出重开，不强停进程。暂不能重载时先完成静态检查，标明运行态尚未验证。
5. 按本次目标验证；失败先查原因，在原范围内修正和必要重试，超出范围的修改单独处理。

### 6. 分层验证

按问题与改动影响选择验证，不要求每次全做。只读诊断不自动变成修复或计费测试；已有适用结果可复用。

1. 静态一致性：配置源、applied profile、provider 模式、base URL、模型映射、凭据存在性。
2. 本地服务：预期端口和进程。
3. 模型列表：`GET /v1/models` 或明确的 `inferenceModels`。这是独立检查项。
4. Messages API：真实 `POST /v1/messages`，包括 `stream=true`。
5. Claude Code 能力：工具调用故障或完整 Code 链路验收时验证 tool use；需要时检查 beta headers。
6. 用户可见端到端：在目标表面新建会话并得到指定短回复。Desktop 内置 Code 与独立 CLI 分开验证。

例如模型菜单问题先验证对应映射与发现结果；接口故障验证相关请求；明确要求整条 Code 链路可用时覆盖
流式、工具调用及目标应用。收费验证复用已确定的范围和费用上限，缺少时仅暂停该测试。
具体请求与通过标准见 [references/verification-and-known-issues.md](references/verification-and-known-issues.md)。

## 输出格式

直接说明目标对象、结论、依据及已做修改；只列影响当前交付的受阻或未验证项，省略无关模式、历史编号和空栏目。
把配置保存、接口可达与目标应用实际成功分开写。完成请求和适用检查即可结束，不等待最终签字；
只完成静态检查时不能声称整条链路可用。

## 常见错误

- 把 Claude Desktop 的 Developer Mode 当成独立 Claude Code 的设置入口。
- 把 CC Switch 的 `Claude` provider 导入成功，当成 `Claude Desktop` 已切换。
- 直连模式使用非 Anthropic API 或非 Claude 模型映射。
- 本地路由模式把 base URL 写成根地址，遗漏 `/claude-desktop` namespace。
- 把 `/v1/models` 成功当作 `/v1/messages` 成功，或反过来。
- 引用已知问题作结论，却没有核对对应版本和本机现象。
- 把 issue 已关闭或出现修复提交，当成当前安装版本已经修复。
- 仅看到一次文本回复就声称已完成包含 streaming、tool use 和目标应用的整条链路验收。
- 直接改生成的 `.claude\settings.json`，忽略 CC Switch 重新渲染造成的字段丢失；历史观察及当前归属核对见配置参考。
- 输出完整 key、完整 profile、完整 DB JSON 或把 key 放进命令行参数。
