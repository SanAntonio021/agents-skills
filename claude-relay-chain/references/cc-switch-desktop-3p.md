# CC Switch 与 Claude Desktop 3P

## 数据归属

默认数据库：

```text
%USERPROFILE%\.cc-switch\cc-switch.db
```

只读审计关注：

- `providers.app_type = 'claude-desktop'`
- `providers.is_current`
- `providers.settings_config`
- `providers.meta`
- `proxy_config` 中 `app_type = 'claude'` 的监听地址和端口
- `%USERPROFILE%\.cc-switch\settings.json` 的 `currentProviderClaudeDesktop`

不要假设数据库有独立 `base_url` 列。远端地址通常在 `settings_config.env.ANTHROPIC_BASE_URL`；模式、接口格式和模型映射通常在 `meta`。

## 直连模式

结构化判据：

```text
meta.claudeDesktopMode = direct
meta.apiFormat = anthropic
```

行为：

```text
Claude Desktop -> 远端 Anthropic Messages API
```

Desktop applied profile 的 `inferenceGatewayBaseUrl` 应与 provider 的远端 `ANTHROPIC_BASE_URL` 一致。

限制：

- 只支持原生 Anthropic Messages API。
- 模型名应为 `claude-*` 或 `anthropic/claude-*`。
- 不能把 Claude tier 映射到非 Claude 模型。
- 需要接口转换或模型映射时，使用本地路由模式。

## 本地路由/模型映射模式

结构化判据：

```text
meta.claudeDesktopMode = proxy
meta.claudeDesktopModelRoutes = {...}
```

行为：

```text
Claude Desktop -> http://127.0.0.1:15721/claude-desktop -> CC Switch -> 上游
```

CC Switch 3.18 本地二进制暴露：

```text
/claude-desktop/v1/messages
/claude-desktop/v1/models
```

使用非默认监听地址或端口时，以 `proxy_config` 为准。模型映射至少包含一个 route；每个 route 的输入是 Desktop 可识别的 Claude model ID，输出是上游实际模型。

本地路由模式可使用 CC Switch 已实现转换的上游格式，包括 Anthropic Messages、OpenAI 和 Gemini。不要只看界面下拉框；以当前版本实际 `apiFormat`、route 和端到端结果为准。

## provider 导入规则

把 CC Switch `Claude` 下的 provider 导入到 `Claude Desktop` 时：

1. 原生 Anthropic provider 且模型名兼容：可用直连模式。
2. OpenAI/Gemini 格式、非 Claude 模型或需要模型改名：必须用本地路由/模型映射模式。
3. 导入只是创建候选 provider；还要确认 `currentProviderClaudeDesktop`、`providers.is_current` 和 Desktop `appliedId`。
4. 独立 Claude Code 的当前 provider 不应被导入动作隐式切换。

## 漂移判断

### 直连模式

- DB 当前 provider 是 `direct`。
- applied profile 却指向 `127.0.0.1:15721`。
- 判断：profile 未重新应用、旧 profile 仍生效，或 managed policy 覆盖。

### 本地路由模式

- DB 当前 provider 是 `proxy`。
- applied profile 却指向远端，或只指向 `http://127.0.0.1:15721` 而没有 `/claude-desktop`。
- 判断：namespace 不一致；先核对 CC Switch 版本和 profile 生成逻辑，不直接手改。

### 当前 provider 不一致

- `settings.json.currentProviderClaudeDesktop` 与 DB `is_current = 1` 不同。
- 判断：切换未完整落盘或状态漂移；用户批准后重新应用目标 provider，再复查。

## 版本相关已知问题

- [CC Switch #4540](https://github.com/farion1231/cc-switch/issues/4540)：2026-07-24 仍为 `Open`。Claude Desktop model discovery 与根 `/v1/models`、`/claude-desktop/v1/models` 的返回格式或 namespace 可能不一致；`/v1/messages` 可用时，Code 仍可能无模型。
- [CC Switch #4415](https://github.com/farion1231/cc-switch/issues/4415)：2026-07-24 为 `Closed`，标记为 `Duplicate of #4353`。涉及 proxy 模型列表合成、空列表和 `supports1m` 到 1M context/model variant 的转换。关闭或出现修复提交不证明当前安装版本已修复。

模型发现症状出现时，必须分别判断两个 issue 与本机证据是否吻合。完整检查项见 [verification-and-known-issues.md](verification-and-known-issues.md)。
