---
name: codex-relay-chain
description: >
  Windows 上维护 Codex 的多层中转链路。遇到 CodexCont、CC Switch/Cockpit、
  中转站切换、aijws/CodeRelay/聪明 AI 这类 OpenAI 兼容接口、Codex 配置被切回去、
  API key 被旧值覆盖、127.0.0.1:8787/15721 本地代理、Responses SSE 兼容性验证、
  provider 地址误指本地端口形成回环、上游 502/503/524 归因、三层链路对照、
  Sub2API 等兼容网关对 Codex Desktop delegation 首包或 `call_id` 的协议兼容缺陷、
  CC Switch provider 熔断、官网页面正常但 Codex 请求失败、健康探测与实际模型不一致、
  reasoning/encrypted_content/
  reasoning_tokens 丢失、用户要求改直连/跳过本地代理/停用监视链路且 base_url
  改了又被自动改回本地端口、只停用 CodexCont 但保留 CC Switch，或 Codex 更新后
  `.codex-global-state.json` 被 watcher 高频重写、需要保留 ChatGPT OAuth 登录但实际请求走
  CC Switch、`codex login` 报 Windows `10013`、CC Switch 生成保留 provider 覆盖、同一旧任务在
  登录或 provider 切换后持续报 OAuth 刷新/`INVALID_API_KEY` 而新任务正常，或需要用 Codex
  对话分叉保留历史继续工作，或要求 CC Switch 统一管理 provider、认证和 Common Config 基线，
  同时区分 Codex Desktop 的新任务默认值与任务级覆盖，并把 watcher 限制为桌面权限恢复、退出审计和启动后漂移记录时，优先使用本技能。
---

# Codex 中转链维护

## 目标

处理这类链路：

```text
Codex -> CodexCont 127.0.0.1:8787/v1 -> CC Switch 127.0.0.1:15721/v1 -> 当前中转站
```

技能按最终服务对象“Codex 请求链路”命名，而不是按某个中间软件命名。CC Switch、CodexCont
以及会改写这条链路的本地 Agent 配置都属于排查范围；通用 `AGENTS.md`、技能目录和其他 Agent
规则维护仍由对应维护技能处理。

重点不是泛讲代理原理，而是先确认“谁有权写配置”，再检查对应链路。配置所有权与请求链路是两个维度：

- `ccswitch-owned`：当前默认。provider、认证、provider 固定模型和 Common Config 基线只通过
  CC Switch 配置；Codex Desktop 仍可按用户操作更新新任务默认值和任务级设置。本地 watcher 不写
  `config.toml`、`auth.json` 或 CC Switch 数据库，只管理 Codex Desktop 的两个 `full-access`
  权限字段，并记录退出与启动后漂移。
- `legacy-writer`：历史配置 writer。只有用户明确要求回滚旧架构并接受争用风险时才进入；不能因为
  检测到漂移就自行启用。

请求链路模式仍按以下三类判断：

- `full`：Codex 是否固定打到 CodexCont，CodexCont 是否固定上游到 CC Switch。
- `ccswitch-only`：Codex 是否直连 CC Switch，CodexCont 是否保持停用。
- `disabled`：本地两层都不由 hook 自动启动。
- 当前 provider、key、live backup 是否一致，并且真实 Responses SSE 能通过。

本机当前默认组合是 `ccswitch-owned + ccswitch-only`。不要把“只监听 15721”误解成允许 watcher
接管配置；15721 是请求入口。provider、认证和 Common Config 基线仍由 CC Switch 管理，Codex
Desktop 自己维护的新任务默认值和任务级设置不属于 watcher 接管。

## 适用场景

用本技能处理：

- 用户让你切换 Codex 当前中转站后验证是否可用。
- CodexCont 安装后，用户问它是不是正常运行。
- CC Switch/Cockpit 切 provider 后，Codex 配置被改成 `15721` 或远端 URL。
- 上游返回 `Invalid API key`，但页面余额和 key 看起来正常。
- 需要判断中转是否支持 Codex 需要的 Responses 流式字段。
- 已定位为中转网关或远端协议实现问题，但用户只有账号管理页，仍要求直接升级、修复或创建监控。
- CC Switch 页面显示 provider 熔断，但中转站官网、余额页或用量页看起来正常；需要区分
  `provider + app_type` 的本地健康状态、手动可达性检查和真实 Responses API 请求。
- 用户怀疑熔断探测使用了某个固定模型，或想把探测模型、故障阈值改成 Terra/其他模型。
- 用户要求跳过本地链路、Codex 直连真实上游，且 `base_url` 手动改了又被自动改回本地端口。
- 用户只想取消 CodexCont，但仍通过 CC Switch 切换中转站。
- Codex 更新后，能力 watcher 因全局状态 JSON 的格式或 App 自管字段而反复写回。
- 用户要求核对 watcher、计划任务 XML 和运行进程，确保 provider、认证和 Common Config 基线只经
  CC Switch 配置，同时区分 Desktop 的新任务默认值写回，保留 `show-context-window-usage = true`、
  禁用 `CodexCapabilityCheck` 且不改 `CodexAutoContinue`。

不用本技能处理：

- Clash Verge、Mihomo、系统网络代理链路；走 `clash-verge-chain-proxy`。
- 单纯 PowerShell 编码、路径或命令失败；走 `command-memory`。
- skill 目录、AGENTS/CLAUDE/GEMINI 维护；走对应维护 skill。

## 默认本机约定

先按当前机器常见位置检查，实际不存在时再搜索：

- Codex 配置：`%USERPROFILE%\.codex\config.toml`
- 链路模式：`%USERPROFILE%\.codex\relay-chain.mode`
- Codex 全局状态：`%USERPROFILE%\.codex\.codex-global-state.json`
- 当前生命周期日志：`%USERPROFILE%\.codex\state\codex-preference-restore\lifecycle.log`
- 历史能力 watcher 日志：`%USERPROFILE%\.codex\state\codex-capability-ccswitch-watch.log`（只作旧状态取证）
- CC Switch DB：`%USERPROFILE%\.cc-switch\cc-switch.db`
- CodexCont 根目录：`%USERPROFILE%\.codexcont\`
- CodexCont 服务目录：`%USERPROFILE%\.codexcont\CodexCont\`
- CodexCont 配置：`%USERPROFILE%\.codexcont\CodexCont\config.toml`
- CodexCont 日志：`%USERPROFILE%\.codexcont\logs\codexcont.out.log`
- 钩子日志：`%USERPROFILE%\.codexcont\logs\hook.log`
- CC Switch 程序：运行中用 `(Get-Process -Name cc-switch -ErrorAction Stop).Path` 读取；未运行时从已确认的快捷方式或安装记录解析，启动前不猜路径。

## 工作顺序

### 0. 先确认配置所有权、源码、任务和运行态

用户要求切换到 `ccswitch-owned` 或排查“配置又被改回去”时，先只读检查，再实施：

1. 读取当前 hook 源码、项目 README、计划任务 XML 和相关进程命令行；不能只看任务名称或 `Ready`。
2. 对 `config.toml`、`auth.json`、`requirements.toml`、浏览器配置、CC Switch Common Config 和数据库
   关键表建立哈希或结构化基线。provider、key、token 只输出名称、空值状态或掩码。
3. 确认没有遗留进程调用 `Apply-CodexContHook.ps1`、配置 writer 或旧版 watcher。脚本文件已删除不代表
   进程已退出；以进程命令行为准。
4. 当前任务边界应为：`CodexPreferenceRestoreAtLogon`、`CodexPreferenceRestoreOnAppUpdate` 和
   `CodexPreferenceRestoreOnExit` 启用；`CodexPreferenceRestoreMigration` 与
   `CodexCapabilityCheck` 禁用；`CodexAutoContinue` 保持原状态和原 XML，不纳入配置迁移。
5. 生命周期 watcher 只允许读写 `.codex-global-state.json` 中
   `electron-persisted-atom-state.agent-mode-by-host-id.local` 和
   `electron-persisted-atom-state.permission-selection-by-host-id:local` 两个权限字段。运行中的 Codex
   只做 `AuditOnly`；确认退出后才恢复权限；快速重启时记录竞态而不写运行中状态。

CC Switch 的 Common Config 与 provider 模型固定值要分开理解。CC Switch 3.19.2 生成 Common Config
时排除根级 `model`；`model` 属于 provider 记录。官方 provider 的模型为空表示未固定模型、由 Codex
采用默认值，不是 watcher 应补的缺口。`model_reasoning_effort` 和
`[desktop].show-context-window-usage = true` 可以由 Common Config 设定共同基线，但 Common Config
不是阻止 Codex Desktop 后续更新新任务默认值的锁。

#### 区分 Common Config、新任务默认值和任务级覆盖

看到 `config.toml` 的模型或推理强度与 Common Config 不一致时，不要仅凭差异判定配置漂移：

1. Common Config 是 CC Switch 保存和重新渲染时使用的共同基线；切换 provider 或重新应用 Common
   Config 后，相关根级默认值可能再次按该基线输出。
2. 用户在空白新任务草稿中选择模型或 effort 时，Codex Desktop 可以把该选择作为后续新任务默认值
   写入 `config.toml`。这是预期的 App 写入，不是 watcher、provider 覆盖或 Common Config 丢失。
3. 用户进入已存在的任务后再切换模型或 effort，优先按任务级设置理解；它不应被反推为 Common
   Config 或全局默认值已经改变。
4. 取证时对齐 `config.toml` 写入时间、新任务创建时间和对应 session/rollout 的首个
   `turn_context`。只有在没有 provider 切换、Common Config 重渲染、新任务草稿设置或其他明确 App
   操作的受控空闲窗口里，出现无法解释的改写，才继续排查外部 writer。

如果希望个别任务使用 `max`、但后续新任务仍默认 `xhigh`，先用默认值创建并进入任务，再在该已存在
任务内切换；不要把空白新任务草稿中的选择误当作一次性任务覆盖。

#### Common Config 的上下文窗口字段

如果已从当前模型或客户端确认可用上限，需要扩大 Codex 的上下文窗口时，只在 CC Switch 的
Common Config 中写入对应的 `model_context_window`。例如上限已确认是 `272000` 时，内容只保留：

```toml
model_context_window = 272000
```

不要把 `model_auto_compact_*` 当作窗口容量设置；它们改变自动压缩的触发时机，可能让内容更早被
压缩。除非用户另有明确目的，否则不要添加这两个字段。保存必须通过 CC Switch 完成，并让 CC Switch
重新渲染最终 `config.toml`；不得直接改 Common Config 文件、`config.toml` 或数据库。

保存后至少复核：`currentProviderCodex`、`providers.is_current`、当前 provider 的远端 `base_url`、
Codex 最终入口和链路模式仍正确；再用本技能的真实 Responses SSE 验证，并至少等待 60 秒比较
`config.toml` 哈希，确认没有被其他进程改回去。上下文窗口数值只对已核实的模型/客户端组合成立，不能
从 provider 名称或一次普通回复反推。

在 `ccswitch-owned` 下，provider、认证、provider 固定模型和 Common Config 基线变更都通过 CC
Switch 完成；Codex Desktop 的新任务默认值和任务级设置由其自身 UI/协议正常维护。本技能可以只读
核对数据库与最终 `config.toml`，但不得直接写数据库、`auth.json` 或 `config.toml`；用户明确要求
不修改 provider/认证数据库时，这一边界没有应急例外。

### 0.1 区分登录身份与请求线路

`Logged in using ChatGPT` 只说明 Codex 本地持有 ChatGPT OAuth 身份；它不要求模型请求官方
直连，也不证明账号有官方付费模型权限。下面这组状态可以同时成立：

- `%USERPROFILE%\.codex\auth.json` 的 `auth_mode` 为 `chatgpt`，
  `.tokens.{id_token,access_token,refresh_token,account_id}` 四项非空；`OPENAI_API_KEY`
  缺失、为 `null` 或为空字符串都可接受。
- `model_provider = "custom"`，入口为 `127.0.0.1:15721/v1`，实际模型由 CC Switch 当前
  provider 提供。
- `requires_openai_auth = true`，Codex 仍使用 OAuth 登录态；CC Switch 接管请求并使用当前
  provider 的上游凭据。

如果 `codex login` 在本地回调监听阶段报 Windows `10013`，先查排除端口，不要归因于账号订阅：

```powershell
netsh interface ipv4 show excludedportrange protocol=tcp
```

当前 Codex 版本使用的回调端口 `1455` 落入排除范围时，含义是本地 socket 绑定被拒绝。优先使用
`codex login --device-auth`；不要在未确认排除范围来源前删除系统端口保留。

CC Switch 的 `preserveCodexOfficialAuthOnSwitch = true` 只防止后续切换覆盖 `auth.json`，不会
重建已经丢失的 OAuth 数据。若当前已变成 API key 登录：先备份现状，再从可信备份恢复。可信
备份必须能确认属于同一用户、生成于本次覆盖之前，且 `auth_mode = "chatgpt"`、
`.tokens.{id_token,access_token,refresh_token,account_id}` 四项均非空；`OPENAI_API_KEY` 应缺失、
为 `null` 或为空字符串。只检查结构和空值，不输出 token。

恢复顺序固定为：暂停会改写 `auth.json` 的 CC Switch Codex 接管或切换流程，先开启
`preserveCodexOfficialAuthOnSwitch`，再恢复可信备份，最后重新启用原请求线路。恢复后要求：

1. `codex login status` 返回 `Logged in using ChatGPT`。
2. `config.toml` 仍指向当前中转入口。
3. 记录 `auth.json` 和 `config.toml` 的 SHA-256，至少等待 60 秒后再次计算并比较。
   `auth.json` 哈希变化时不要直接判为覆盖：只复核 `auth_mode`、四项 token 是否非空和
   `OPENAI_API_KEY` 空值状态。OAuth 结构仍完整可能只是正常 token 刷新；变成 API key 结构才判失败。

#### 单个旧任务仍报旧认证错误

恢复 OAuth 或切换 provider 后，如果只有同一个旧任务继续失败，而新任务和 `codex exec` 正常，
不要立即改 provider key。Codex Desktop 的旧任务可能仍保留此前的认证或 provider 上下文；此时错误
可能先是 `access token could not be refreshed`，恢复 OAuth 后又变成某个旧上游的
`401 INVALID_API_KEY`。错误文字变化只说明请求推进到了下一层，不能单独证明当前 key 已失效。

按以下证据顺序判断：

1. 用任务读取工具或对应 `sessions/**/*.jsonl` 找到失败 turn 的时间、错误类型和错误 URL。
2. 对照当前 `config.toml`、`settings.json.currentProviderCodex`、`providers.is_current`，以及同一时段
   CC Switch 转发日志中的真实目标 URL。不要用 provider 名称猜线路。
3. 对错误 URL 所属 provider 的已保存 key 做一次最小 Responses 直连探测；只报告 key 指纹、HTTP
   状态和 SSE 事件，不输出 key 或完整响应。
4. 用当前配置运行新任务或 `codex exec`，确认当前线路能返回预期文本，并在 CC Switch 日志中留下
   当前 provider 的 HTTP 200。

以下证据同时成立时，判为“旧任务上下文失效”，不改 key：当前线路和新任务正常；被怀疑的
provider key 直连也为 200；只有旧任务失败；旧任务报告的 URL 与当前转发目标不一致，或本地代理
日志中没有对应失败请求。若同一 provider 的当前 key 直连也返回 401，再按第 5 节处理真实 key 问题。

需要保留历史继续工作时，优先使用 Codex 的同目录对话分叉：

- 只有用户已经授权新任务或分叉时才执行；否则先说明判断并询问。
- `fork_thread` 使用 `same-directory`，不是 Git branch，也不创建 worktree，也不复制项目文件。
- 分叉只复制已完成历史，不复制正在运行的 turn 或未完成回复；向子任务发送用户最后一条未完成指令，
  不要只发含义不明的“继续”。
- 用 `wait_threads` 验证子任务完成且没有认证错误；需要时为子任务设置可识别标题。
- 不反复重试已确认失效的旧任务。只有用户明确要求保留旧任务 ID 并接受中断其他活动任务时，才考虑
  完全重启 Codex Desktop；重启也不保证清除持久化的任务上下文。

### 1. 先确认模式和监听

先读 `%USERPROFILE%\.codex\relay-chain.mode`。文件不存在时按 `full` 处理：

- `full` / `codexcont`：应同时监听 `8787` 和 `15721`。
- `ccswitch-only` / `ccswitch`：只要求 `15721`；`8787` 不监听才是正确状态。
- `disabled` / `off`：hook 不自动管理两层代理。

```powershell
Get-NetTCPConnection -State Listen |
  Where-Object { $_.LocalPort -in 8787,15721 } |
  Select-Object LocalAddress,LocalPort,OwningProcess
```

`full` 模式的合格信号：

- `127.0.0.1:8787` 在监听，通常是 CodexCont。
- `127.0.0.1:15721` 在监听，通常是 CC Switch 本地代理。

只有 `full` 模式下 `8787` 不在时才启动：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$env:USERPROFILE\.codexcont\Start-CodexContChain.ps1"
```

### 2. 检查 Codex 是否指向当前模式的入口

读 `%USERPROFILE%\.codex\config.toml`，确认 CC Switch 的最终输出和当前 provider（provider 名以
`model_provider` 实际值为准，本机常见为 `custom`）。在 `ccswitch-owned` 下这里只读验证，不直接修复。
历史 `full` 模式应为：

```toml
model_provider = "custom"

[model_providers.custom]
base_url = "http://127.0.0.1:8787/v1"
wire_api = "responses"
requires_openai_auth = true
```

`ccswitch-only` 模式应为 `http://127.0.0.1:15721/v1`；不能把这个正确状态误判成 hook 失效。
如果当前是官方 provider 且没有固定 `model`，不要把缺少根级 `model` 判为漂移。

#### CC Switch 3.18 保留 provider ID 兼容

保留 OAuth 时，CC Switch 3.18 可能同时写出 `model_provider = "openai"` 和
`[model_providers.openai]` 本地代理块。Codex 0.144.1 会以
`reserved built-in provider IDs: openai` 拒绝加载。只有同时满足以下条件才自动修复：

- 当前链路模式是 `ccswitch-only`。
- 当前 `model_provider = "openai"`。
- `custom` provider 指向 `127.0.0.1:15721`，使用 Responses API 和 `PROXY_MANAGED`。
- 非法 `openai` 覆盖也指向 `127.0.0.1:15721`。

在 `ccswitch-owned` 下只记录这种兼容性漂移，并通过 CC Switch 重新选择或修正 provider；watcher
不得自动把当前 provider 选回 `custom`，也不得删除覆盖块。官方 `model_provider = "openai"` 且没有
非法覆盖块时保持不动。只有用户明确批准回滚到历史恢复流程时，才把旧自动修复作为独立操作评估。

只有用户明确选择历史 `legacy-writer + full` 模式时，CC Switch 切换后这里变成 `15721` 或远端 URL，
才说明旧 CodexCont hook 没接住。下面的命令是回滚旧架构的兼容入口，当前默认不得由 watcher 调用：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$env:USERPROFILE\.codexcont\Apply-CodexContHook.ps1"
```

执行前必须再次确认用户确实要离开 `ccswitch-owned`。执行后再看
`%USERPROFILE%\.codexcont\logs\hook.log`。历史合格信号（`<provider>` 为当前 provider 名）：

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
- 更正前记录 `cc-switch.db` 哈希；在 CC Switch 中只修正该 provider 的远端地址并保留原 API key，
  不直接写数据库。
- 远端地址必须来自历史配置、备份或 provider 官方信息，不凭名称猜测。

切换完成后同时核对：

- `%USERPROFILE%\.cc-switch\settings.json` 的 `currentProviderCodex`。
- `providers.is_current`。
- 两者都指向目标 provider，且目标 provider 的远端地址没有被 watcher 改成本地端口。

#### 官网状态、健康探测和熔断状态不是同一件事

CC Switch 的 provider 健康记录按 `provider_id + app_type` 保存。Codex 的 `codex` 记录、
Claude 的 `claude` 记录和 Claude Desktop 的 `claude-desktop` 记录彼此独立；同一家中转站的
官网、余额页或 Claude 页面正常，不能自动清除 Codex provider 的熔断。

排查时把证据分成三层，避免把“网页能打开”当成“Codex 接口可用”：

1. **官网/余额页**：只证明网页登录态、账户或余额页面能访问，不证明当前 API key、当前
   `app_type` 或当前模型能完成 Responses 请求。
2. **手动可达性检查**：`stream_check_logs` 可能只记录 `Reachable`，且 `model_used` 为空；
   这只能说明地址或基础连接可达，不能证明具体 Codex 模型和 Responses SSE 兼容。
3. **真实请求健康**：以 `proxy_request_logs` 和 `provider_health` 为准，对齐同一个
   `provider_id + app_type`、实际 `request_model/model`、HTTP 状态、错误时间和熔断状态，再用
   本技能“Responses SSE 验证”中的真实 `stream=true /v1/responses` 复核。不要为了诊断临时改写
   自动故障转移或清空健康记录。

`providers.settings_config` 保存的默认模型不一定等于失败请求实际使用的模型；旧任务上下文或
请求级模型覆盖仍可能发送另一个模型。两者不一致时，以同一时段 `proxy_request_logs` 的
`request_model/model` 解释该次失败，并把默认配置只作为差异线索。

CC Switch 的熔断恢复通常是自动的：`HalfOpen`/半开状态表示等待下一次放行请求验证，
不是一个可在技能里指定的固定“探测模型”。当前没有证据表明后台固定使用 Luna、Terra 或其他
单一模型；半开尝试和后续健康记录应与实际放行请求的模型对齐。因此，不能通过把故障转移模型
改成 Terra low 来改变熔断探测逻辑。若要判断“为什么熔断”，先读取实际日志，而不是猜探测模型。

按错误类型解释熔断原因：

- `404 model_not_found` 或响应明确写“模型不支持”：优先判为当前 provider/账号不支持该
  `request_model` 的兼容性问题。它可以触发该 `provider + app_type` 的失败计数，但不等于整个
  网站宕机；应换一个已验证模型做独立 SSE 检查，并保留原记录。
- `429`：限流或额度策略候选；需要结合响应头、请求时间和 provider 日志判断。
- `502/503/504/524`、连接错误或超时：真实 API、上游源站或中转服务故障候选；按本节日志和
  “上游 502/503/524 的归因”做三层对照。
- 页面显示 `Circuit Open`/熔断时，记录 `consecutive_failures`、`last_failure_at`、
  `last_error`、`updated_at` 和 `circuit_failure_threshold`。2026-08-12 在本机 CC Switch 3.19.2
  实时核到连续失败 4 次、半开成功 2 次、60 秒后进入半开；以后诊断仍以 `proxy_config` 当前值为准。
  这些参数属于 CC Switch 的运行配置，本机 3.19.2 未发现独立的探测模型字段或界面入口。
  除非用户明确要求改配置，不要直接写数据库。

同一 provider 可能存在多条相同名称但不同 `provider_id` 的 Codex 记录。查询时必须使用日志
里的实际 `provider_id`，不能只按页面显示名称合并；也不能把 `claude`/`claude-desktop`
的正常记录拿来证明 `codex` 记录正常。若页面仍显示熔断但最近真实请求已经成功，先核对是否查看了
错误的 `app_type`、旧的 provider ID 或旧时间段，再判断缓存/状态刷新问题。

### 5. 处理 key 被旧值覆盖

本节只用于预期认证方式就是 API key 的配置。目标是保留 ChatGPT OAuth 时，不要把 provider
key 写入 `auth.json`；上游 key 由 CC Switch provider 管理，OAuth 恢复按第 0 节执行。

如果测试返回：

```text
Invalid API key
Provider: <current provider>
```

如果 401 只发生在一个旧任务，而当前 provider、新任务和对应 key 直连均正常，先按第 0 节的
“单个旧任务仍报旧认证错误”处理；不要用当前有效 key 覆盖数据库或备份。

在 `ccswitch-owned` 下，`providers`、`proxy_live_backup`、`auth.json` 和 `config.toml` 都只读诊断：

1. 从 CC Switch 当前 provider、请求日志和结构化配置确认错误属于哪个 provider 与 `app_type`。
2. 只比较 key 指纹、长度和空值状态，不在回复、日志或命令输出中打印完整 key。
3. 需要修正时在 CC Switch 的对应 provider 页面完成，再复核数据库、live backup 与最终
   `config.toml` 的结构化结果和哈希稳定性。
4. 如果 CC Switch UI 无法修复、用户又要求直接恢复数据库，把它视为退出当前所有权方案的高风险
   独立任务：展示精确表、字段和备份/回滚方案并重新取得授权。本技能不得把直接写库当作默认修复。

如果需要从已登录网页取 key，使用浏览器/CDP 前按 `web-access` 的安全提示执行。优先从页面明确展示的配置块读取，避免把遮罩 key 当成真实 key。

### 6. 重启 CC Switch 时避免被旧 backup 覆盖

如果 CC Switch 日志出现：

```text
检测到上次异常退出
Live 配置已恢复
已同步 Codex Token 到数据库
```

这说明它可能正在用 `proxy_live_backup` 恢复旧配置。在 `ccswitch-owned` 下先只读比较当前 provider、
live backup 和磁盘输出，保留异常时间与哈希证据；通过 CC Switch 修正源记录后再重启。不得为了
消除漂移而由 watcher 抢写 `proxy_live_backup` 或 `config.toml`。重启也属于显式维护动作，不能由
漂移审计自动触发；重启后重新检查 provider、live backup、`auth.json` 语义和 `config.toml` 哈希。

### 7. 仅停用 CodexCont，保留 CC Switch

用户只取消 CodexCont 时，不要套用“直连真实上游”流程。目标是：

```text
Codex -> CC Switch 127.0.0.1:15721/v1 -> 当前中转站
```

按以下顺序执行：

1. 先记录源码、计划任务 XML、进程命令行、8787/15721 监听和配置哈希；确认没有未识别的 writer。
2. 把 `%USERPROFILE%\.codex\relay-chain.mode` 写为 `ccswitch-only`。
3. 用 `Disable-ScheduledTask -TaskName 'CodexCont Chain'` 禁用旧任务，不注销任务。
4. 运行 `%USERPROFILE%\.codexcont\Stop-CodexContChain.ps1`，保留安装文件便于恢复；确认它没有改写
   provider、认证、模型或 `config.toml`。
5. 确认 `8787` 不监听、`15721` 监听，且 CC Switch 输出的 Codex `base_url` 为
   `http://127.0.0.1:15721/v1`；这里只读核验最终文件。
6. 至少等待 60 秒后复查，确认 SessionStart、UserPromptSubmit 或常驻 watcher 没有重新启动
   CodexCont，也没有改写 `config.toml`。
7. 对 `15721/v1/responses` 做真实 `stream=true` 测试；要求 HTTP 200、SSE created/completed 和预期 usage 字段。

此模式绕过 CodexCont，所以 `proxy_rounds` 缺失是预期结果，不应据此判失败。用户仍保留 CC Switch GUI 切换能力，但失去 CodexCont 的推理截断续跑能力。

#### 全局状态 watcher 的写入边界

当前 watcher 只能管理第 0 节列出的两个桌面权限字段。监视 `.codex-global-state.json` 时，只在
受管理字段的语义值确实变化后写文件。不要把整份 JSON 重新序列化后与原文本比较；Codex App 的
属性顺序、压缩格式、结尾换行或原子替换方式不同，会形成 App 写入、hook 格式化、watcher 再触发的循环。

`selected-project` 和 `hotkey-window-projectless-default-enabled` 默认交给 Codex App 管理。除非用户明确要求并接受争用风险，否则 hook 不应删除或强制设置这些字段。

它不得监听或写入 `config.toml`、`auth.json`、`requirements.toml`、浏览器配置、provider、模型、
推理强度或 CC Switch 数据库；也不得修改 `copilot-default-model`、`seen-model-upgrade-list` 等 Codex
Desktop 自管状态。

验证至少包括：PowerShell 语法检查；权限恢复、集成、生命周期和配置所有权四项离线测试；安装脚本
`-WhatIf -SkipMigration`；逐项解析任务 XML 的动作、启用状态和参数；核对
`CodexCapabilityCheck` 与迁移任务禁用；核对 `CodexAutoContinue` XML/源码哈希不变；至少 60 秒比较
`config.toml` 哈希不变。该 60 秒必须是没有 provider 切换、Common Config 重渲染或新任务草稿设置
变化的受控空闲窗口；否则先按本节的三层区别解释。`auth.json` 哈希变化时按 OAuth 结构语义复核，
避免把正常 token 刷新误判为覆盖。

### 8. 拆链路 / 改直连

用户明确要求跳过本地链路、Codex 直连真实上游时用本节。先区分两种含义：

- 仍保留 `ccswitch-owned`：在 CC Switch 中创建或选择直连上游的 Codex provider，所有 provider、
  key、模型和 Common Config 仍由 CC Switch 配置。本技能只核对最终输出。
- 完全绕过 CC Switch：这会改变已确认的配置所有权和 GUI 切换能力，必须作为单独架构变更再次确认；
  不得沿用本节旧脚本直接改数据库与 `config.toml`。

#### 两类致病根因，必须都查

`base_url` 被改回本地端口，通常有两类独立来源；先只读确认，不把正常 CC Switch 接管误判成恶意覆盖：

- **(a) 外部 watcher 脚本 + Windows 计划任务**：某个第三方脚本（不一定是 CodexCont 官方的 `Watch-CodexConfigForCodexCont.ps1`，也可能是用户自己写的、路径已经失效但进程还在内存里跑的孤儿脚本）持续监视并强制改写 `config.toml`。排查：
  ```powershell
  Get-CimInstance Win32_Process | Where-Object {
    $_.CommandLine -match "Watch-Codex|watch-ccswitch|CodexCont.*run\.py"
  } | Select-Object ProcessId, CommandLine
  Get-ScheduledTask | Where-Object { $_.TaskName -match "Codex|CC.?Switch" } | Select-Object TaskName, State
  ```
  即使脚本源文件已被删除、路径不存在，进程仍可能常驻并继续生效——不要只看计划任务，也要看当前运行进程的命令行。
- **(b) CC Switch 自身的本地代理接管**：`proxy_config` 表里对应 `app_type` 的
  `proxy_enabled`/`enabled` 为 1 时，CC Switch 会把 `config.toml` 输出为自己的本地代理端口
  （通常 15721）。这与 (a) 无关，在 `ccswitch-owned` 下属于 CC Switch 的正常职责。只读排查：
  ```python
  import sqlite3
  con = sqlite3.connect(r"%USERPROFILE%\.cc-switch\cc-switch.db")
  cur = con.cursor()
  cur.execute("SELECT app_type, proxy_enabled, enabled FROM proxy_config")
  print(cur.fetchall())
  ```

先停掉 (a) 后短时间稳定，不代表 (b) 不存在；验证至少等待 60 秒。但如果目标仍是
`ccswitch-owned`，发现 (b) 后不应关闭或直接改库，而应回到 CC Switch 设置目标 provider 与代理模式。

#### `ccswitch-owned` 落地顺序

1. 保存 DB、Common Config、`config.toml`、`auth.json` 语义和任务 XML 的只读基线。
2. 停用已确认的外部 writer 或 CodexCont 任务；保留安装文件和可逆任务定义。
3. 在 CC Switch 中选择直连上游的 provider，设置该 provider 的认证与模型；通用推理强度和
   `show-context-window-usage` 继续由 Common Config 管理。
4. 核对当前 provider、最终 `config.toml`、15721/8787 监听和请求日志；不要直接改
   `providers`、`proxy_live_backup` 或磁盘配置。
5. 至少 60 秒比较 `config.toml` 哈希；`auth.json` 只做 OAuth 语义复核。最后用真实
   `stream=true /v1/responses` 做端到端测试。

#### 代价，必须明确告知用户

- 失去 CodexCont 的推理截断自动修复（`reasoning_tokens == 518*n-2` 场景），长推理任务理论上有恢复截断的风险。
- 如果完全绕过 CC Switch，将失去 CC Switch 的 provider、认证、模型和 Common Config 单一入口；
  这不是本节的默认动作，也不能在同一次“修复漂移”授权中顺带执行。

### 9. 重建链路 / 从直连恢复代理

用户明确要求从完全直连恢复到 CC Switch 时用本节。当前默认目标是
`Codex → CC Switch(15721) → 远端`；不要自动恢复历史 CodexCont 配置 writer。

#### 前置条件

- 已取得当前配置、认证、数据库和任务 XML 的只读基线。
- CC Switch 进程与程序路径已确认；启动或重启前不猜路径。

#### 落地顺序

1. 通过 CC Switch 启用 Codex 本地代理并选择目标 provider；不直接更新 `proxy_config` 或 provider 表。
2. 把 `relay-chain.mode` 设为 `ccswitch-only`，保持 `CodexCont Chain` 与
   `CodexCapabilityCheck` 禁用，保持 `CodexAutoContinue` 原样。
3. 确认 15721 监听、8787 不监听，且 CC Switch 输出的 `config.toml` 指向 15721。
4. 解析生命周期任务 XML，确认 watcher 只调用权限恢复、退出审计和启动后漂移记录入口。
5. 运行四项离线测试、60 秒稳定性核验和真实 Responses SSE；失败时回到 CC Switch 修正，不启用旧 writer。

只有用户另行明确要求恢复 `legacy-writer + full`，才评估启动 CodexCont、8787 和旧 hook；这会改变
当前所有权方案，不能从“恢复 CC Switch”自动推导。

#### 常见卡点

- **15721 起不来**：只读核对 `proxy_config`、进程和日志，再通过 CC Switch 调整；不要直接写数据库。
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
  "include": ["reasoning.encrypted_content"],
  "stream": true,
  "store": false
}
```

除非目标 provider 已单独验证，否则最小健康探测不要加入 `max_output_tokens`；部分中转会直接返回不支持参数的 `400`。
简单回显任务可能不生成 reasoning item，即使线路正常也看不到 `encrypted_content`。验证这两个字段时使用
上面的非平凡小题，并显式加入 `include = ["reasoning.encrypted_content"]`。

#### 严格校验流式文本与终态文本

不能只检查 HTTP 状态、事件名和字段是否存在。对本节预期返回文本的探测，按 SSE 事件顺序收集全部
`response.output_text.delta` 的 `delta` 并直接拼接；再从 `response.completed` 的
`response.output` 中按顺序提取全部 `output_text.text` 并拼接。两侧必须逐字符完全一致，不能先
`Trim`、折叠空白、去重句段或只做包含关系比较。

任一侧缺失或两侧冲突时，即使 HTTP 为 `200` 且 `response.created`、`response.completed` 都存在，
仍判为 Responses SSE 协议不一致，并保留最短错误类型，例如
`SSE terminal output conflicts with streamed text`。不要为了提高有效样本数而放宽解析器。

#### 并发和探针内容的控制实验

批量探测无有效样本时，不要先归因于并发数或探针内容。先保留失败请求的端点、模型、prompt、
reasoning effort、`include`、`stream`、`store`、超时和其他请求形态，关闭重试，以 `worker = 1`
重复取得原始样本：

1. 单 worker 仍稳定出现同类 HTTP、SSE 或文本一致性错误时，不能写成“8 并发限制”；优先归为
   上游或中转的协议/传输异常，再按三层链路定位。
2. 只有单 worker 对照通过，而提高 worker 后可重复失败，并且状态码、连接重置、超时或限流证据
   随并发变化时，才把并发容量列为候选原因。
3. 判断探针内容是否触发异常时，先完成上述同请求对照，再把 prompt 换成最简单的固定回显，其他字段
   保持不变。简单回显仍出现同类终态/增量冲突时，不能归因于原探针题目；HTTP `200` 也不能推翻该结论。

合格信号：

- HTTP `200`
- `Content-Type` 包含 `text/event-stream`
- SSE 里有 `event: response.created`
- SSE 里有 `event: response.completed`
- body 里有 `"type":"reasoning"`
- body 里有 `encrypted_content`
- body 里有 `reasoning_tokens`
- `full` 模式下 body 里有 CodexCont 注入的 `proxy_rounds`；`ccswitch-only` 缺失是预期结果
- 如可见，body 里有 `proxy_billed_usage`

不合格信号和含义：

- `401 Invalid API key`：优先查 provider key 和 `proxy_live_backup`。
- `reasoning_tokens` 缺失：中转可能没有完整保留 Responses usage。
- `encrypted_content` 缺失：中转或代理可能过滤了 reasoning 加密内容。
- `proxy_rounds` 缺失：请求可能没经过 CodexCont，或 CodexCont 没正常处理。
- `response.completed` 终态文本与全部 `response.output_text.delta` 拼接文本不一致：中转返回了
  自相矛盾的 Responses SSE，不能计为有效样本。

目标是“OAuth 登录 + 中转请求”时，SSE 通过后还要运行一次真实 `codex exec`。只有
`codex login status` 为 ChatGPT、CLI 显示目标 `custom` provider、返回预期文本，且 CC Switch
请求日志记录当前 provider HTTP 200，才证明身份和请求线路同时成立。

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

### 上游修复权限与可完成性

确定故障在中转站、网关程序或远端协议实现后，在承诺“直接升级”“修复”或“监控后自动处理”前，
先确认当前实际能操作哪一类控制面。能管理账号不代表能改变正在运行的服务：

1. **账号管理面**：例如 `/admin/users`、余额、分组、额度和 key 页面。它只能证明可以管理租户或账号，
   不能证明可以替换服务版本、重启实例或回滚。
2. **服务部署面**：例如服务器 SSH、Docker/Kubernetes、部署面板、CI/CD、镜像版本、运行日志和回滚入口。
   把上游修复部署到实际中转站至少需要这一层权限。
3. **源码维护面**：例如目标仓库、fork、PR、合并和 release 权限。能准备补丁或跟踪 issue，仍不等于
   已把修复部署到用户正在使用的服务。

只有当前代理或用户能进入所需控制面、能确认目标版本或提交，并能在升级后重跑真实 Codex/Responses
请求时，才可以说能够直接完成上游升级。只有账号管理页时，不把它描述为服务器管理入口，也不通过修改
无关的本地 provider、用户分组或额度配置来掩盖协议实现缺陷。

缺少部署或源码发布权限时，把终态写成“诊断完成，修复受外部部署或源码权限阻塞”，并说明应由谁部署
哪个修复、部署后用什么请求验收。上游 issue 已关闭也不等于用户正在使用的实例已经升级。

监控只能发现 issue、release 或服务版本的状态变化，并在触发后提醒或续接诊断；它不会获得服务器权限，
也不能代替部署和验收。只有用户明确认可“仅提醒”的价值并同意触发条件与续接方式后才创建。用户认为
提醒没有价值或明确结束任务时，不创建或继续监控，更不能把监控包装成后续自动修复。

## 输出给用户

给用户只报关键判断：

- 当前配置所有权：`ccswitch-owned` 或已明确批准的 `legacy-writer`。
- 当前模式：`full`、`ccswitch-only` 或 `disabled`。
- Codex 登录方式、`.tokens` 下 OAuth 四项是否非空、`OPENAI_API_KEY` 是否缺失/`null`/空，
  以及保留官方认证开关状态。
- 当前 provider 名称和 key mask。
- `8787` / `15721` 是否符合当前模式。
- Codex `base_url` 是否指向当前模式的正确入口。
- SSE 是否 HTTP 200。
- 是否看到 `reasoning`、`encrypted_content`、`reasoning_tokens`；仅 `full` 模式要求 `proxy_rounds`。
- `codex exec` 是否经当前 provider 返回预期结果。
- `CodexCapabilityCheck`、迁移任务、生命周期任务和 `CodexAutoContinue` 的 XML/状态是否符合边界。
- 60 秒内 `config.toml` 是否稳定；`auth.json` 若变更，OAuth 结构是否仍完整。
- 单个旧任务失败时，其错误 URL 是否与当前转发目标一致；如已分叉，子任务是否完成。
- 上游归因后，当前具备账号管理、服务部署或源码维护中的哪类权限；无修复入口时明确报告外部权限阻塞。
- 如果失败，报最短错误原因和下一步。

不要输出完整 API key、完整 auth JSON、完整 SSE body。

## 安全边界

- 不打印完整 API key。
- 不打印 OAuth token、完整 `auth.json` 或带 token 的命令行。
- 不把真实 key 写进 skill、README、提交信息或日志摘要。
- 不把某一家中转站硬编码成唯一方案。
- 不直接改 `%USERPROFILE%\.cc-switch\skills` 或 `%USERPROFILE%\.codex\skills` 里的 skill 运行时副本。
- `ccswitch-owned` 下不由技能、脚本或 watcher 直接写 CC Switch 数据库、`config.toml`、`auth.json`、
  provider 或 Common Config；provider 与共同基线通过 CC Switch 变更，Desktop 新任务默认值和任务级
  设置只通过 Codex Desktop 自身交互维护。
- 不让 watcher 或兼容入口修改 `CodexAutoContinue`，也不重新启用 `CodexCapabilityCheck`。
- 不把 `/v1/models` 当作最终通过信号。
- 不在存在无关 git 改动时把它们一起提交。
- 停用计划任务优先 `Disable-ScheduledTask`，不用 `Unregister-ScheduledTask`——保留可逆性，用户改主意时能直接 `Enable-ScheduledTask` 恢复，不用重新注册任务。

## 常见坑

- 页面表格里的 `sk-xxx...xxxx` 是遮罩 key，不是真实 key。
- provider 的远端地址可能嵌在 `settings_config.config` TOML 中，不要先假设数据库存在 `base_url` 列。
- 远端 provider 指向 `8787/15721` 会形成本地代理回环；先修地址再切换。
- CC Switch 运行中退出可能写回旧内存状态；先比较 live backup 与当前 provider，再通过 CC Switch
  修正源记录，不由 watcher 直接改 live backup。
- `settings.json` 的 `currentProviderCodex` 和 `providers.is_current` 都要和目标 provider 对上。
- CodexCont 的 auth mode 是 `passthrough` 时，Codex 当前 token 仍会被传给 CC Switch。
- `preserveCodexOfficialAuthOnSwitch` 不能恢复已经被 API key 覆盖的 OAuth 数据，必须使用可信备份。
- Windows `10013` 若发生在回调端口绑定阶段，优先查排除端口；它和 ChatGPT 是否付费是两回事。
- OAuth 恢复后，旧任务从刷新失败变成旧上游 401，不等于当前 provider key 失效；先比较错误 URL、
  同时段代理日志和 key 直连结果。
- Codex 对话分叉不是 Git 分支。它保留已完成对话历史并使用新任务上下文，适合绕过单个旧任务缓存。
- 字符串形式的 Responses `input` 可能导致代理误处理；测试用 list-form input。
- 看到 Codex 正常回复仍要看日志字段；有回复不等于 reasoning/encrypted_content 没丢。
- 改直连时改完文件立刻复查会误判"已稳定"——两类致病根因的改写周期不同，必须至少等待 60 秒，
  再比较 `auth.json` 和 `config.toml` 的 SHA-256；`auth.json` 哈希变化时按 OAuth 结构做语义复核，
  避免把正常 token 刷新误判为 CC Switch 覆盖。
- watcher 脚本源文件被删除不代表它失效；进程可能仍在内存里常驻运行，要查当前进程命令行，不能只看文件是否存在。
- 关掉 watcher/计划任务后配置仍被改写，通常是 cc-switch 自身的本地代理接管开关（`proxy_config.proxy_enabled`/`enabled`）在起作用，这条路径独立于 watcher，必须单独检查。
- 不要因 JSON 格式、属性顺序或结尾换行不同而重写整份 `.codex-global-state.json`；只按受管理字段的语义变化写入。
- Common Config 不含根级 `model` 不代表模型配置丢失；模型固定值属于 provider。官方 provider 的模型为空可以是有意未固定，不得由 watcher 猜测并补写。
- Common Config 中的 effort 与 `config.toml` 不一致不自动等于漂移；先确认用户是否在空白新任务草稿中
  改过 effort。该操作会更新后续新任务默认值，而已存在任务内的切换属于任务级覆盖。
