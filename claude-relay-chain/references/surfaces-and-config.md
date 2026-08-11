# 配置表面与优先级

## 四个配置对象

### 独立 Claude Code CLI

- 常见用户配置：`%USERPROFILE%\.claude\settings.json`。
- CC Switch 的 app 类型是 `claude`，界面名称通常是 `Claude`。
- 常见字段在 `env` 中：`ANTHROPIC_BASE_URL`、`ANTHROPIC_AUTH_TOKEN`、默认模型映射。
- CC Switch 接管时，`settings.json` 可能被当前 provider 重新渲染。不要把手改文件当成稳定配置源。

VS Code 中的 Claude Code 扩展属于同一类推理配置，但扩展进程可能保留启动时环境。修改后用新会话验证；必要时重载扩展宿主。

### Claude Desktop 内置 Code

Claude Desktop on 3P 的 Code tab 是内置 Claude Code。Desktop 启动 Code 会话时，把 3P profile 转换为 Claude Code 设置并传入会话。以下内容自动继承：

- inference provider
- endpoint
- credentials
- inference model list
- Desktop 管理的工具、MCP、workspace 和网络策略

因此，不要为内置 Code 单独修改 `%USERPROFILE%\.claude\settings.json`。

### Claude Desktop 3P profile

Windows 本地 profile：

```text
%LOCALAPPDATA%\Claude-3p\configLibrary\
```

- `_meta.json` 保存配置条目与 `appliedId`。
- `<id>.json` 保存一份 profile。
- 配置只在启动时读取；变更后完整退出并重开应用。

Windows managed policy：

```text
HKLM\SOFTWARE\Policies\Claude
HKCU\SOFTWARE\Policies\Claude
```

优先级：

1. HKLM machine policy 存在时，HKCU 和本地 profile 通常被忽略。
2. 没有 HKLM 时，HKCU managed policy 优先于本地 profile。
3. 没有 managed source 时，使用 `configLibrary` 的 applied profile。

审计只报告 managed policy 是否存在和字段名，不输出凭据值。

### 独立 Claude Code 的 managed policy

Claude Code CLI 的策略键与上面的 Desktop 键**不同**，是独立路径：

```text
HKLM\SOFTWARE\Policies\ClaudeCode    ← 机器级，优先级最高
HKCU\SOFTWARE\Policies\ClaudeCode    ← 用户级（HKCU\SOFTWARE\Policies 受 SYSTEM ACL 保护，普通进程不可写）
```

格式：单个 `REG_SZ` 值，值名 `Settings`，数据是完整 JSON 字符串，结构与 `~/.claude/settings.json` 相同：

```json
{"permissions":{"defaultMode":"auto"}}
```

`defaultMode` 合法值：`default`（别名 `manual`）/ `acceptEdits` / `plan` / `auto` / `dontAsk` / `bypassPermissions`。

**CC Switch 渲染边界**：CC Switch 全量渲染 `~/.claude/settings.json`，但实测只保留 `env` 块，其余字段（`permissions`、`enabledPlugins`、`extraKnownMarketplaces`、`$schema`、`effortLevel`、`model`）一律被裁掉。往 `common_config_claude` 加新字段不会渲染进文件。要全局持久化 Claude Code 设置，用 managed policy 键而不是直改 `settings.json`（2026-08-11 实测）。

### CC Switch 双入口

CC Switch 3.18 的 DB 中是不同 `app_type`：

- `claude`：独立 Claude Code / 扩展。
- `claude-desktop`：Claude Desktop 3P。

对应当前 provider 也分开保存：

- `currentProviderClaude`
- `currentProviderClaudeDesktop`

两个名称相同也不代表记录相同；按 provider ID 和 `app_type` 判断。

## Developer Mode 正式入口

Windows Claude Desktop 登录页左上角应用菜单：

```text
Help -> Troubleshooting -> Enable Developer Mode
Developer -> Configure Third-Party Inference...
```

配置窗口负责字段校验、endpoint 测试、`Apply locally` 和 `.reg` 导出。单机配置优先使用 `Apply locally`，不手写注册表或整份 profile。

## Gateway 关键字段

- `inferenceProvider = gateway`
- `inferenceGatewayBaseUrl`
- `inferenceGatewayApiKey`
- `inferenceGatewayAuthScheme = bearer | x-api-key`
- `inferenceModels`（可选，覆盖自动发现）
- `modelDiscoveryEnabled`（可选）

gateway 必须实现 Anthropic Messages API：

- `POST /v1/messages`：必须，且需支持 streaming 和 tool use。
- `GET /v1/models`：可选；没有时显式配置完整 `inferenceModels`。

## 官方资料

- [In-app configuration](https://claude.com/docs/third-party/claude-desktop/in-app-configuration)
- [Gateway provider](https://claude.com/docs/third-party/claude-desktop/gateway)
- [Configuration reference](https://claude.com/docs/third-party/claude-desktop/configuration)
- [Code tab](https://claude.com/docs/third-party/claude-desktop/code)

资料核对日期：2026-07-23。字段和应用行为可能随版本变化；修改前刷新官方文档和本机版本。
