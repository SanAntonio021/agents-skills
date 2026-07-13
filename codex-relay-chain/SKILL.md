---
name: codex-relay-chain
disable-model-invocation: true
description: >
  Windows 上维护 Codex 的多层中转链路。遇到 CodexCont、CC Switch/Cockpit、
  中转站切换、aijws/CodeRelay/聪明 AI 这类 OpenAI 兼容接口、Codex 配置被切回去、
  API key 被旧值覆盖、127.0.0.1:8787/15721 本地代理、Responses SSE 兼容性验证、
  provider 地址误指本地端口形成回环、上游 502/503/524 归因、三层链路对照、
  reasoning/encrypted_content/
  reasoning_tokens 丢失、用户要求改直连/跳过本地代理/停用监视链路且 base_url
  改了又被自动改回本地端口时，优先使用本技能。
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
- 用户要求跳过本地链路、Codex 直连真实上游，且 `base_url` 手动改了又被自动改回本地端口。

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

读 `%USERPROFILE%\.codex\config.toml`，确认当前 provider（provider 名以 `model_provider` 实际值为准，本机常见为 `custom`）：

```toml
model_provider = "custom"

[model_providers.custom]
base_url = "http://127.0.0.1:8787/v1"
wire_api = "responses"
requires_openai_auth = true
```

如果用户用 CC Switch 切换后这里变成 `http://127.0.0.1:15721/v1` 或远端 URL，说明钩子没接住。先运行：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$env:USERPROFILE\.codexcont\Apply-CodexContHook.ps1"
```

再看 `%USERPROFILE%\.codexcont\logs\hook.log`。合格信号（`<provider>` 为当前 provider 名）：

```text
hooked: <provider> -> http://127.0.0.1:8787/v1
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

#### 切换前检查目标 provider 地址

新版 CC Switch 不一定有独立的 `providers.base_url` 列。真实地址可能位于
`providers.settings_config` 的 JSON 内，再嵌套在 `config` TOML 字符串中。用 JSON 和
TOML 解析器读取，不要假设列名，也不要用字符串拼接读取 API key。

切换目标 provider 前确认它的远端 `base_url`：

- 远端 provider 不应指向 `http://127.0.0.1:8787/v1` 或 `http://127.0.0.1:15721/v1`。
- 如果目标 provider 指向 `8787`，链路会变成 `8787 -> 15721 -> 8787`，最终超时或返回 502/504。
- 修复前备份 `cc-switch.db`；只恢复该 provider 的远端地址，保留原 API key。
- 远端地址必须来自历史配置、备份或 provider 官方信息，不凭名称猜测。

切换完成后同时核对：

- `%USERPROFILE%\.cc-switch\settings.json` 的 `currentProviderCodex`。
- `providers.is_current`。
- 两者都指向目标 provider，且目标 provider 的远端地址没有被 watcher 改成本地端口。

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

### 7. 拆链路 / 改直连

用户明确要求跳过本地链路、Codex 直连真实上游时用本节。目标：`base_url` 稳定停在真实上游地址，不再被改回本地端口，且改动可逆。

#### 两类致病根因，必须都查

`base_url` 被强制改回本地端口，通常是下面两类原因之一在起作用，**两者相互独立，只关掉一个不够**：

- **(a) 外部 watcher 脚本 + Windows 计划任务**：某个第三方脚本（不一定是 CodexCont 官方的 `Watch-CodexConfigForCodexCont.ps1`，也可能是用户自己写的、路径已经失效但进程还在内存里跑的孤儿脚本）持续监视并强制改写 `config.toml`。排查：
  ```powershell
  Get-CimInstance Win32_Process | Where-Object {
    $_.CommandLine -match "Watch-Codex|watch-ccswitch|CodexCont.*run\.py"
  } | Select-Object ProcessId, CommandLine
  Get-ScheduledTask | Where-Object { $_.TaskName -match "Codex|CC.?Switch" } | Select-Object TaskName, State
  ```
  即使脚本源文件已被删除、路径不存在，进程仍可能常驻并继续生效——不要只看计划任务，也要看当前运行进程的命令行。
- **(b) cc-switch 自身的"本地代理接管"开关**：`proxy_config` 表里对应 `app_type` 的 `proxy_enabled`/`enabled` 为 1 时，cc-switch 会持续把 `config.toml` 改写指向自己的本地代理端口（通常 15721），这与 (a) 无关，即使 watcher 已经彻底停掉也会继续发生。排查：
  ```python
  import sqlite3
  con = sqlite3.connect(r"%USERPROFILE%\.cc-switch\cc-switch.db")
  cur = con.cursor()
  cur.execute("SELECT app_type, proxy_enabled, enabled FROM proxy_config")
  print(cur.fetchall())
  ```

实测教训：先停掉 (a)，改完文件后短时间内看似稳定，但那只是因为还没到 (b) 的下一次改写周期；几十秒后又被改回去，才发现 (b) 才是这次真正生效的那条路径。**验证要隔 30~60 秒复查多次，不能改完看一眼就下结论。**

#### 落地顺序

1. 备份：DB (`%USERPROFILE%\.cc-switch\cc-switch.db`) 和 `.codex/config.toml` 都先复制一份到带时间戳的文件名。
2. 停 (a)：跑 `Stop-CodexContChain.ps1`（或手动 `Stop-Process` 杀掉命中的进程），确认 8787 端口不再监听。
3. 关 (b)：把对应 `app_type` 的 `proxy_config.proxy_enabled` 和 `enabled` 都置 0。
4. **DB 和磁盘文件必须同步改，只改一处会被另一处覆盖回去**：
   - DB 侧：`providers.settings_config` 里 JSON 的 `config` 字段（一个内嵌的 TOML 字符串），把其中 `base_url` 一行替换成真实上游地址，`experimental_bearer_token` 换成真实 key（不要留 `PROXY_MANAGED` 占位符）。
   - 磁盘侧：`.codex/config.toml` 的 `[model_providers.custom]` 块做同样替换。
5. 检查 `proxy_live_backup` 表：确认它当前存的 `original_config` 就是要保留的直连配置（`base_url` 是真实地址），不是旧的代理占位符。如果不是，cc-switch 异常退出后走恢复流程时会把旧配置写回来，等于白改。
6. 永久停用 (a) 用 `Disable-ScheduledTask -TaskName "<task name>"`（不要 `Unregister`，保留可逆性，需要恢复时用 `Enable-ScheduledTask`）。
7. 验证：`.codex/config.toml` 隔 10 秒查一次，连续 5~6 次不变才算稳定；再用真实 `stream=true` 的 `/v1/responses` 端到端测试一次（见下节 SSE 验证标准），不要只看 `base_url` 字符串对不对。

#### 代价，必须明确告知用户

- 失去 CodexCont 的推理截断自动修复（`reasoning_tokens == 518*n-2` 场景），长推理任务理论上有恢复截断的风险。
- 失去 cc-switch GUI 的切换/管理能力：以后在 GUI 里点这个 provider 的"切换"，大概率会把 (b) 重新打开、把 `base_url` 写回本地端口。之后要改 key 或模型，只能手动改 DB+文件，或者明确告知用户这个后果并重新走一遍本节。

### 8. 重建链路 / 从直连恢复代理

用户明确要求从直连切回本地代理链路时用本节。目标：恢复 `Codex → CodexCont(8787) → CC Switch(15721) → 远端` 的完整链路。

#### 前置条件

- CC Switch 进程正在运行（如果没有，先启动 `cc-switch.exe`）。
- CodexCont 目录完好：`%USERPROFILE%\.codexcont\CodexCont\.venv\Scripts\python.exe` 存在。

#### 落地顺序

1. 备份 DB：
   ```powershell
   $ts = Get-Date -Format "yyyyMMdd_HHmmss"
   Copy-Item "$env:USERPROFILE\.cc-switch\cc-switch.db" "$env:USERPROFILE\.cc-switch\cc-switch.db.bak_$ts"
   ```

2. 开启 CC Switch 代理——修改 `proxy_config` 表：
   ```python
   import sqlite3, os
   db = os.path.expanduser(r"~\.cc-switch\cc-switch.db")
   conn = sqlite3.connect(db)
   conn.execute("UPDATE proxy_config SET proxy_enabled=1 WHERE app_type='codex'")
   conn.commit()
   conn.close()
   ```

3. 重启 CC Switch 让代理在 15721 生效：
   ```powershell
   Get-Process cc-switch -ErrorAction SilentlyContinue | Stop-Process -Force
   Start-Sleep -Seconds 2
   Start-Process 'D:\Users\SanAn\AppData\Local\Programs\CC Switch\cc-switch.exe' -WindowStyle Hidden
   Start-Sleep -Seconds 5
   ```

4. 确认 15721 已监听：
   ```powershell
   Get-NetTCPConnection -State Listen -LocalPort 15721 -ErrorAction SilentlyContinue
   ```
   如果没有，检查 CC Switch 启动日志或 DB 是否被覆盖。

5. 启动 CodexCont 链路：
   ```powershell
   powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$env:USERPROFILE\.codexcont\Start-CodexContChain.ps1"
   ```
   合格信号：输出 `codexcont_listening: true`、`ccswitch_proxy_listening: true`、`watcher_running: true`。

6. 确认 8787 监听：
   ```powershell
   Get-NetTCPConnection -State Listen -LocalPort 8787 -ErrorAction SilentlyContinue
   ```

7. 确认 `config.toml` 已被 hook 改为 8787：
   ```powershell
   Select-String -Path "$env:USERPROFILE\.codex\config.toml" -Pattern "base_url"
   ```
   预期：`base_url = "http://127.0.0.1:8787/v1"`。

#### 常见卡点

- **15721 起不来**：最常见原因是 `proxy_config.proxy_enabled` 仍为 0。可能是之前改直连时留下的残留（2026-07-13 实例），或 CC Switch 重启时从旧备份恢复了状态。再查一遍 DB 确认值为 1。
- **CodexCont 启动后立即退出**：查 `%USERPROFILE%\.codexcont\logs\codexcont.err.log` 尾部。常见：venv 依赖缺失（重装 `pip install -r requirements.txt`）或端口被占用。
- **Codex 更新后链路自动断开**：不要仅凭更新时间和 CodexCont 消失时间就认定存在因果。先保存 Windows 更新事件、CodexCont/CC Switch 的进程启动/退出时间、端口 PID 和日志尾部；只有找到明确的终止或异常退出证据才归因。`proxy_enabled=0` 是独立问题：它会让 CC Switch 重启后不启动 15721，但不能据此证明是 Codex 更新写入。优先使用会话启动、恢复和提交消息前的健康检查做自愈，不把“登录触发的计划任务”当作进程级监视器。

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
  "store": false
}
```

除非目标 provider 已单独验证，否则最小健康探测不要加入 `max_output_tokens`；部分中转会直接返回不支持参数的 `400`。

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

### 上游 502/503/524 的归因

本地返回 `502`、`503` 或 `524` 时，不要先把错误归因给 CodexCont 或 CC Switch。
先区分“本机进程不可用”和“本地代理转发了远端错误”：

1. 测试前后记录 `8787`、`15721` 的监听 PID、进程启动时间，以及 Codex 和 CodexCont 的固定 URL。
2. 从当前 provider 的结构化配置解析真实远端 `base_url`，不要从 provider 名称猜地址。
3. 用同一模型、同一 list-form input、`stream=true`、`store=false` 的最小请求，交替测试三层：
   - `http://127.0.0.1:8787/v1/responses`：完整本地链路；
   - `http://127.0.0.1:15721/v1/responses`：绕过 CodexCont；
   - 当前 provider 的远端 `/v1/responses`：绕过两个本地代理。
4. 间歇性问题建议交替执行 3 轮。每次只报告 HTTP 状态、耗时、`Content-Type`、`Server`、
   `cf-ray` 是否存在、`cf-error-type`/`cf-error-origin` 是否存在和最短错误类型，不输出完整 key 或 SSE body。

如果 CC Switch 已开启自动故障转移，同时读取 `proxy_config.auto_failover_enabled`、
`providers.in_failover_queue` 和 `proxy_request_logs`，记录每次本地请求实际使用的 provider；
否则备用 provider 可能把主 provider 的故障隐藏掉。诊断期间不要为了“证明故障”临时改写故障转移状态。

判断规则：

- `8787` 或 `15721` 未监听、连接被拒绝：本机服务故障。此时还没有到达远端，不能写成上游 `502/524`。
- 本地和远端直连返回同一 `503`：上游 provider 故障。
- 远端直连返回 `524`，响应是 Cloudflare 错误页且耗时接近默认 `120` 秒：远端源站响应超时；可参考 [Cloudflare Error 524](https://developers.cloudflare.com/support/troubleshooting/http-status-codes/cloudflare-5xx-errors/error-524/)。
- 远端直连出现 `524`，而本地 `8787`/`15721` 返回 `200`：上游存在间歇性故障，本地转发路径在该次测试中可用；不能因为一次本地成功就否定远端超时。
- CC Switch 日志写明“上游 HTTP 502/524”，同时记录远端 URL 和 HTML 错误页：优先判定为远端错误被转发。本轮远端直连未复现时，只写“高度疑似”，不要写成已完全证实。
- 远端直连正常、本地链路失败：继续查 CodexCont、CC Switch 转发、live backup、回环地址和本机代理配置。
- 本地链路返回 `200` 但 SSE 字段缺失：继续按 Responses 兼容性检查，不把它归为可用。

目标 provider 故障时，切回最后一个通过完整 SSE 验证的 provider。切回后再次核对
`currentProviderCodex`、`is_current`、Codex `base_url = "http://127.0.0.1:8787/v1"`，
并重跑完整 SSE 验证，避免把 Codex 留在不可用状态。

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
- 停用计划任务优先 `Disable-ScheduledTask`，不用 `Unregister-ScheduledTask`——保留可逆性，用户改主意时能直接 `Enable-ScheduledTask` 恢复，不用重新注册任务。

## 常见坑

- 页面表格里的 `sk-xxx...xxxx` 是遮罩 key，不是真实 key。
- provider 的远端地址可能嵌在 `settings_config.config` TOML 中，不要先假设数据库存在 `base_url` 列。
- 远端 provider 指向 `8787/15721` 会形成本地代理回环；先修地址再切换。
- CC Switch 运行中退出可能写回旧内存状态；必要时修 live backup。
- `settings.json` 的 `currentProviderCodex` 和 `providers.is_current` 都要和目标 provider 对上。
- CodexCont 的 auth mode 是 `passthrough` 时，Codex 当前 token 仍会被传给 CC Switch。
- 字符串形式的 Responses `input` 可能导致代理误处理；测试用 list-form input。
- 看到 Codex 正常回复仍要看日志字段；有回复不等于 reasoning/encrypted_content 没丢。
- 改直连时改完文件立刻复查会误判"已稳定"——两类致病根因的改写周期不同，必须隔 30~60 秒复查多次。
- watcher 脚本源文件被删除不代表它失效；进程可能仍在内存里常驻运行，要查当前进程命令行，不能只看文件是否存在。
- 关掉 watcher/计划任务后配置仍被改写，通常是 cc-switch 自身的本地代理接管开关（`proxy_config.proxy_enabled`/`enabled`）在起作用，这条路径独立于 watcher，必须单独检查。
