---
name: codex-relay-chain
description: >
  Windows 上维护 Codex 的多层中转链路。遇到 CodexCont、CC Switch/Cockpit、
  中转站切换、aijws/CodeRelay/聪明 AI 这类 OpenAI 兼容接口、Codex 配置被切回去、
  API key 被旧值覆盖、127.0.0.1:8787/15721 本地代理、Responses SSE 兼容性验证、
  reasoning/encrypted_content/reasoning_tokens 丢失时，优先使用本技能。
---

# Codex 中转链维护

## 目标

处理这类链路：

```text
Codex -> CodexCont 127.0.0.1:8787/v1 -> CC Switch 127.0.0.1:15721/v1 -> 当前中转站
```

重点不是泛讲代理原理，而是确认三件事：

- Codex 是否固定打到 CodexCont。
- CodexCont 是否固定上游到 CC Switch 本地代理。
- CC Switch 当前 provider、key、live backup 是否一致，并且真实 Responses SSE 能通过。

## 适用场景

用本技能处理：

- 用户让你切换 Codex 当前中转站后验证是否可用。
- CodexCont 安装后，用户问它是不是正常运行。
- CC Switch/Cockpit 切 provider 后，Codex 配置被改成 `15721` 或远端 URL。
- 上游返回 `Invalid API key`，但页面余额和 key 看起来正常。
- 需要判断中转是否支持 Codex 需要的 Responses 流式字段。

不用本技能处理：

- Clash Verge、Mihomo、系统网络代理链路；走 `clash-verge-chain-proxy`。
- 单纯 PowerShell 编码、路径或命令失败；走 `command-memory`。
- skill 目录、AGENTS/CLAUDE/GEMINI 维护；走对应维护 skill。

## 默认本机约定

先按当前机器常见位置检查，实际不存在时再搜索：

- Codex 配置：`%USERPROFILE%\.codex\config.toml`
- CC Switch DB：`%USERPROFILE%\.cc-switch\cc-switch.db`
- CodexCont 根目录：`%USERPROFILE%\.codexcont\`
- CodexCont 服务目录：`%USERPROFILE%\.codexcont\CodexCont\`
- CodexCont 配置：`%USERPROFILE%\.codexcont\CodexCont\config.toml`
- CodexCont 日志：`%USERPROFILE%\.codexcont\logs\codexcont.out.log`
- 钩子日志：`%USERPROFILE%\.codexcont\logs\hook.log`
- CC Switch 默认程序：`D:\Users\SanAn\AppData\Local\Programs\CC Switch\cc-switch.exe`

## 工作顺序

### 1. 先确认两端监听

```powershell
Get-NetTCPConnection -State Listen |
  Where-Object { $_.LocalPort -in 8787,15721 } |
  Select-Object LocalAddress,LocalPort,OwningProcess
```

合格信号：

- `127.0.0.1:8787` 在监听，通常是 CodexCont。
- `127.0.0.1:15721` 在监听，通常是 CC Switch 本地代理。

如果 `8787` 不在，先启动：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$env:USERPROFILE\.codexcont\Start-CodexContChain.ps1"
```

### 2. 检查 Codex 是否固定走 CodexCont

读 `%USERPROFILE%\.codex\config.toml`，确认当前 provider：

```toml
model_provider = "codex_local_access"

[model_providers.codex_local_access]
base_url = "http://127.0.0.1:8787/v1"
wire_api = "responses"
requires_openai_auth = true
```

如果用户用 CC Switch 切换后这里变成 `http://127.0.0.1:15721/v1` 或远端 URL，说明钩子没接住。先运行：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$env:USERPROFILE\.codexcont\Apply-CodexContHook.ps1"
```

再看 `%USERPROFILE%\.codexcont\logs\hook.log`。合格信号：

```text
codex_local_access -> http://127.0.0.1:8787/v1
```

### 3. 检查 CodexCont 上游是否固定到 CC Switch

读 `%USERPROFILE%\.codexcont\CodexCont\config.toml`，确认：

```toml
[upstream]
url = "http://127.0.0.1:15721/v1/responses"
mode = "fixed"

[auth]
mode = "passthrough"
```

这里不写某一家中转商。中转选择交给 CC Switch，Codex 和 CodexCont 只认本地入口。

### 4. 检查 CC Switch 当前 provider

用 SQLite 读 `%USERPROFILE%\.cc-switch\cc-switch.db`。只输出 key mask，不输出完整 key。

重点表：

- `providers`：当前 provider、配置和 key。
- `proxy_config`：本地代理和 live takeover 状态。
- `proxy_live_backup`：CC Switch 接管 Codex 配置时保存的备份。

`providers.settings_config` 里通常有：

```json
{
  "auth": {
    "OPENAI_API_KEY": "...",
    "auth_mode": "apikey"
  },
  "config": "model_provider = ..."
}
```

### 5. 处理 key 被旧值覆盖

如果测试返回：

```text
Invalid API key
Provider: <current provider>
```

不要只改 `providers`。CC Switch 启动或恢复 live takeover 时可能从 `proxy_live_backup` 把旧 Codex 配置和旧 key 写回来。

修复顺序：

1. 从中转站页面或可信本地配置取真实 key。
2. 不在回复、日志和命令输出里打印完整 key。
3. 备份 `cc-switch.db` 和 `.codex/config.toml`。
4. 同步更新：
   - `providers.settings_config.auth.OPENAI_API_KEY`
   - `proxy_live_backup.original_config.auth.OPENAI_API_KEY`
   - `proxy_live_backup.original_config.config` 里的 `experimental_bearer_token`
   - `.codex/config.toml` 当前 provider 的 `experimental_bearer_token`
5. 确保 `.codex/config.toml` 的 `base_url` 仍是 `http://127.0.0.1:8787/v1`。

如果需要从已登录网页取 key，使用浏览器/CDP 前按 `web-access` 的安全提示执行。优先从页面明确展示的配置块读取，避免把遮罩 key 当成真实 key。

### 6. 重启 CC Switch 时避免被旧 backup 覆盖

如果 CC Switch 日志出现：

```text
检测到上次异常退出
Live 配置已恢复
已同步 Codex Token 到数据库
```

这说明它可能正在用 `proxy_live_backup` 恢复旧配置。此时要先修 `proxy_live_backup`，再重启 CC Switch。只修 provider 往往会被覆盖。

重启命令：

```powershell
Get-Process cc-switch -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 2
Start-Process 'D:\Users\SanAn\AppData\Local\Programs\CC Switch\cc-switch.exe' -WindowStyle Hidden
```

重启后重新检查 `providers`、`proxy_live_backup` 和 `.codex/config.toml` 的 key mask 是否一致。

## Responses SSE 验证

不要用 `/v1/models` 判断 Codex 是否可用。它只能初筛，不能证明 Responses 流和 reasoning 字段可用。

使用真实 `stream=true` 的 `/v1/responses`，并用 list-form input，避免 CodexCont 把字符串 input 拆成字符。

请求形态：

```json
{
  "model": "gpt-5.5",
  "input": [
    {
      "role": "user",
      "content": [
        {
          "type": "input_text",
          "text": "解这个小题，最后只给答案和极简验证：三个正整数互不相同，和为 41，乘积为 1716。求这三个数。"
        }
      ]
    }
  ],
  "reasoning": {
    "effort": "high"
  },
  "stream": true,
  "store": false,
  "max_output_tokens": 512
}
```

合格信号：

- HTTP `200`
- `Content-Type` 包含 `text/event-stream`
- SSE 里有 `event: response.created`
- body 里有 `"type":"reasoning"`
- body 里有 `encrypted_content`
- body 里有 `reasoning_tokens`
- body 里有 CodexCont 注入的 `proxy_rounds`
- 如可见，body 里有 `proxy_billed_usage`

不合格信号和含义：

- `401 Invalid API key`：优先查 provider key 和 `proxy_live_backup`。
- `reasoning_tokens` 缺失：中转可能没有完整保留 Responses usage。
- `encrypted_content` 缺失：中转或代理可能过滤了 reasoning 加密内容。
- `proxy_rounds` 缺失：请求可能没经过 CodexCont，或 CodexCont 没正常处理。

## 输出给用户

给用户只报关键判断：

- 当前 provider 名称和 key mask。
- `8787` / `15721` 是否监听。
- Codex 是否仍指向 `8787`。
- SSE 是否 HTTP 200。
- 是否看到 `reasoning`、`encrypted_content`、`reasoning_tokens`、`proxy_rounds`。
- 如果失败，报最短错误原因和下一步。

不要输出完整 API key、完整 auth JSON、完整 SSE body。

## 安全边界

- 不打印完整 API key。
- 不把真实 key 写进 skill、README、提交信息或日志摘要。
- 不把某一家中转站硬编码成唯一方案。
- 不直接改 `%USERPROFILE%\.cc-switch\skills` 或 `%USERPROFILE%\.codex\skills` 里的 skill 运行时副本。
- 不把 `/v1/models` 当作最终通过信号。
- 不在存在无关 git 改动时把它们一起提交。

## 常见坑

- 页面表格里的 `sk-xxx...xxxx` 是遮罩 key，不是真实 key。
- CC Switch 运行中退出可能写回旧内存状态；必要时修 live backup。
- `settings.json` 的 `currentProviderCodex` 和 `providers.is_current` 都要和目标 provider 对上。
- CodexCont 的 auth mode 是 `passthrough` 时，Codex 当前 token 仍会被传给 CC Switch。
- 字符串形式的 Responses `input` 可能导致代理误处理；测试用 list-form input。
- 看到 Codex 正常回复仍要看日志字段；有回复不等于 reasoning/encrypted_content 没丢。
