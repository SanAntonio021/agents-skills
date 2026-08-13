---
name: claude-relay-chain
description: >
  Windows 上诊断和配置 Claude Code、VS Code 中的 Claude Code 扩展、Claude Desktop on 3P
  内置 Code、CC Switch 的 Claude/Claude Desktop 双入口，以及第三方中转站。用户提到
  Developer Mode、Configure Third-Party Inference、ANTHROPIC_BASE_URL、Anthropic Messages
  API、/v1/messages、/v1/models、127.0.0.1:15721、Claude Desktop 模型发现、CC Switch
  直连模式或本地路由/模型映射模式、OpenAI/Gemini 接口转换、配置能回复但另一入口失败，
  或要求导入/切换/排查 Claude 中转供应商时，优先使用本技能。
compatibility: Windows PowerShell 5.1 or later; Python 3 is optional for read-only CC Switch database inspection.
---

# Claude 中转链排障

## 目标

诊断以下两条相互独立的链路，并在得到明确批准后完成最小配置变更：

```text
独立 Claude Code / VS Code 扩展 -> CC Switch Claude -> 第三方中转站
Claude Desktop Cowork / 内置 Code -> Desktop 3P profile -> 直连供应商或 CC Switch Claude Desktop -> 第三方中转站
```

不要因为其中一条能回复，就断言另一条也已配置成功。

## 强制边界

1. 默认只读。先检查，再给判断和修改方案。
2. 修改方案必须写清：修改对象、备份位置、改动内容、是否需要重启、验证方法和回滚方法。
3. 用户明确同意前，不备份、不修改、不切换 provider、不重启、不运行带凭据或可能计费的验证请求。
4. 用户批准的对象与方案发生变化时，重新说明差异并再次确认。
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

### 1. 运行默认只读审计

优先运行：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\audit-claude-relay.ps1"
```

需要机器可读结果时加 `-AsJson`。脚本只读取配置、注册表存在性、监听端口和 CC Switch DB 的脱敏字段；不会发送网络请求或修改文件。

审计至少确认：

- CC Switch 版本、进程和 `15721` 监听状态。
- `currentProviderClaude` 与 `currentProviderClaudeDesktop`。
- `%USERPROFILE%\.claude\settings.json` 的 base URL、模型和凭据是否存在；只报存在性。
- Desktop 3P 是否由 HKLM/HKCU managed policy 管理，还是使用本地 `configLibrary`。
- `_meta.json` 的 `appliedId`、实际 profile、gateway base URL、认证方案和凭据存在性。
- CC Switch 当前 Claude Desktop provider 的 `meta.claudeDesktopMode`、`meta.apiFormat` 和模型映射数量。

若 Python 3 不存在，脚本仍完成文件、注册表和端口检查，但把 CC Switch DB 检查标为 `UNAVAILABLE`，不能据此猜测模式。

### 2. 自动判断 CC Switch 模式

以 CC Switch DB 当前 `app_type = 'claude-desktop'` provider 的结构化字段为准：

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
2. 分开检查根 `/v1/models` 与本地路由 `/claude-desktop/v1/models`。未获 HTTP 批准时，只检查 profile、二进制路由、日志和既有响应记录，并把实时接口状态写为 `未验证`。
3. 明确核对 [CC Switch #4540](https://github.com/farion1231/cc-switch/issues/4540) 与 [#4415](https://github.com/farion1231/cc-switch/issues/4415)：
   - `#4540`：关注 namespace 和返回结构不一致，例如根路径返回 `{"models":[]}`，而 Desktop 需要可识别的模型数组或正确 `data` 结构。
   - `#4415`：关注从模型 route 合成列表失败、空列表，以及 `supports1m` 没有正确反映到 1M model variant 或 `context_window`。
4. 重新核对 issue 当前状态和本机版本。issue 仍开放不证明本机必然命中；issue 已关闭或有修复提交也不证明当前安装版本已经包含修复。
5. 报告每个 issue 为 `证据吻合`、`证据不吻合` 或 `未验证`，并给出本机日志、profile、route 或版本证据。不要只列 issue 编号。

更完整的通过标准和当前 issue 状态见 [references/verification-and-known-issues.md](references/verification-and-known-issues.md)。

### 4. 给出修改方案并停在确认门

方案用以下格式：

```text
当前判断：
证据：
拟修改对象：
备份：
具体改动：
需要重启：
验证：
回滚：
等待确认：是
```

只给一个推荐方案。存在关键取舍时，说明取舍后一次只问一个问题。

### 5. 得到批准后执行

执行顺序固定：

1. 重新读取目标文件和 DB 状态，确认没有从审计后发生变化。
2. 备份这次将修改的具体对象；数据库备份必须可打开，文件备份记录 SHA-256。
3. 做最小改动。优先使用 Claude Desktop 的 in-app configuration 或 CC Switch provider 设置，不手写整份 profile。
4. 只重启受影响的应用。Desktop profile 变化需要完全退出并重开 Claude Desktop；独立 Claude Code/VS Code 还要新建会话或重载扩展进程。
5. 按批准过的验证范围验证；失败时停止扩大修改，先报告新证据。

### 6. 分层验证

验证顺序：

1. 静态一致性：配置源、applied profile、provider 模式、base URL、模型映射、凭据存在性。
2. 本地服务：预期端口和进程。
3. 模型列表：`GET /v1/models` 或明确的 `inferenceModels`。这是独立检查项。
4. Messages API：真实 `POST /v1/messages`，包括 `stream=true`。
5. Claude Code 能力：至少一次 tool use；需要时检查 gateway 是否接受实验性 beta headers。
6. 用户可见端到端：在目标表面新建会话并得到指定短回复。Desktop 内置 Code 与独立 CLI 分开验证。

具体请求与通过标准见 [references/verification-and-known-issues.md](references/verification-and-known-issues.md)。

## 输出格式

默认报告：

```text
目标表面：
当前链路：
CC Switch 模式：direct / proxy / unknown
已确认：
异常：
相关已知问题：#4540 = 证据吻合 / 证据不吻合 / 未验证；#4415 = 证据吻合 / 证据不吻合 / 未验证
仍未验证：
建议修改：
是否等待批准：是 / 否
```

把“配置存在”“接口可达”“目标应用端到端成功”分开写。未知项写 `未验证`，不要写成成功。

## 常见错误

- 把 Claude Desktop 的 Developer Mode 当成独立 Claude Code 的设置入口。
- 把 CC Switch 的 `Claude` provider 导入成功，当成 `Claude Desktop` 已切换。
- 直连模式使用非 Anthropic API 或非 Claude 模型映射。
- 本地路由模式把 base URL 写成根地址，遗漏 `/claude-desktop` namespace。
- 只测 `/v1/models`，没有测 `/v1/messages`；或反过来。
- 只写“可能是已知问题”，却没有分别核对 `#4540`、`#4415`、当前版本和本机证据。
- 把 issue 已关闭或出现修复提交，当成当前安装版本已经修复。
- 看到一次文本回复，就跳过 streaming、tool use 和目标表面验证。
- 手改 `.claude\settings.json` 的任何字段（模型、effort、permissions、enabledPlugins 等），却忽略 CC Switch 会全量重新渲染该文件——实测渲染后只保留 `env` 块，其余字段全部丢失。
- 输出完整 key、完整 profile、完整 DB JSON 或把 key 放进命令行参数。
