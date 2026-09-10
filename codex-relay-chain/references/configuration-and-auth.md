# 配置、认证与云端恢复

按 [技能入口](../SKILL.md) 的范围和授权执行，仅阅读当前问题相关小节。历史版本观察需结合当前版本核对。

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


### CC Switch 云端备份恢复

遇到 WebDAV/坚果云下载转圈、结束后配置未变，或用户询问恢复是否成功时，先核对以下证据：

1. **区分历史错误与本次失败。** 读取当前运行程序的版本、`settings.json` 中的
   `webdavSync.status` 和本次操作时段的日志。`lastError` 可能是旧记录，`lastSyncAt` 是上次
   成功时间，不能据此认定刚才失败的原因。必要时通过已配置的 WebDAV 只读获取云端 manifest
   和 SQL，校验文件大小与摘要，只提取 `PRAGMA user_version`；不执行远端 SQL，不输出凭据或
   备份正文。manifest 的 `dbCompatVersion` 与 SQL 的 `user_version` 不是同一个版本号。
2. **区分下载等待与导入失败。** 转圈时长不能直接证明网络故障。核对当前版本的下载顺序、
   文件大小和超时设置，分别判断网络传输、校验与本地导入。2026-09-06 的案例中，3.19.2
   先下载数据库和约 64 MB 的技能包，再导入数据库；云端 `user_version=18` 超出该应用支持的
   16，升级到支持 18 的 3.20.1 后恢复成功。约两分钟是否都用于下载、界面为何没有显示错误，
   当时没有完整证据，不能写成已确认机制；后续版本也不能照搬这组版本号或等待时间。
3. **分项确认恢复结果。** 结合本次同步记录、数据库版本和预期配置变化确认快照是否应用，
   再检查 `post-download sync warning` 等后续同步结果。数据库恢复成功后，提示词仍可能因
   `AGENTS.md` 是符号链接而原子替换失败（Windows `os error 1464`）；应报告“备份已恢复，
   对应提示词未写入”，并按规则维护流程处理实际目标，不能为消除告警直接覆盖链接。
   保存的 `lastLocalManifestHash` 与 `lastRemoteManifestHash` 相等只反映那次同步记录，
   不证明当前云端、数据库、技能和提示词仍全部一致，也不代替 Codex 请求链路验收。

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

#### 审批策略与桌面权限必须成组核对

看到“完全访问已经开启，但删除或其他命令仍在 PowerShell 启动前被 `blocked by policy` 拒绝”时，
不要把 `danger-full-access` 当成自动批准。依次核对五层：CC Switch Common Config、当前 provider 的
`commonConfigEnabled`、最终生成的 `config.toml`、Codex Desktop 当前激活的权限模式与 permission
selection，以及当前任务 `turn_context` 中实际生效的 `sandbox_policy`、`approval_policy` 和
`approvals_reviewer`。前四层说明配置来源和选择，第五层才是当前任务的运行态依据。

需要自动审批时，推荐共同基线为：

```toml
approval_policy = "on-request"
approvals_reviewer = "auto_review"
sandbox_mode = "danger-full-access"
```

Codex Desktop 26.831 的内置权限模式映射为：

| Desktop 模式 | sandbox | approval policy | reviewer |
| --- | --- | --- | --- |
| `full-access` | `danger-full-access` | `never` | `user` |
| `guardian-approvals` | `workspace-write` | `on-request` | `guardian_subagent` |
| `custom` | 从当前配置解析 | 从当前配置解析 | 从当前配置解析 |

因此，上述显式组合必须把 `agent-mode-by-host-id.local` 设为 `custom`，并让当前 permission selection
为 `{"kind":"custom"}`；不能把 `guardian-approvals` 当作该组合的别名。Codex Desktop 升级后若映射可能
变化，先核对实际加载版本，再沿用结论。`sandbox_mode` 只决定底层访问范围；
`approval_policy = "never"` 会关闭审批交接，即使磁盘配置仍写着
`approvals_reviewer = "auto_review"`，以 `full-access` 启动的新任务也会得到 `never + user`，不会交给
自动审批器判断。

通过 CC Switch 支持的后台服务或 CLI 更新 Common Config，并确认当前 provider 已启用
`commonConfigEnabled`；不得直接改 `cc-switch.db` 或生成的 `config.toml`。审批策略由任务启动时读取，
旧任务仍可能沿用原值；配置落盘只证明输入正确。必须新建任务，先核对首个 `turn_context` 已是
`danger-full-access + on-request + auto_review`，再用一个原先会触发审批的窄范围动作确认审批器确实
接管。动作成功本身不是自动审批证据：如果 `turn_context` 仍是 `never + user`，或没有任何 reviewer
介入证据，只能说明动作被当前策略允许。若当前旧任务仍拒绝删除任务自产生的无害临时文件，保留并报告
准确路径，继续不依赖该清理的工作，不换 `cmd`、.NET 或其他 API
绕过宿主策略。

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
Codex 最终入口和链路模式仍正确。要求实际链路验收时再做 Responses SSE；有反复覆盖线索时至少等待 60 秒比较
`config.toml` 哈希。上下文窗口数值只对已核实的模型/客户端组合成立，不能
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
`preserveCodexOfficialAuthOnSwitch`，再通过支持恢复认证的入口应用可信备份，最后重新启用原请求线路；接口不支持时只暂停该恢复，不直接覆盖认证文件。恢复后要求：

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
3. 优先复用错误 URL 所属 provider 的适用直连记录；资料不足且已有测试授权时做最小 Responses 探测，
   只报告 key 指纹、HTTP 状态和 SSE 事件，不输出 key 或完整响应。
4. 优先查当前线路已有的新任务或 `codex exec` 结果及对应 CC Switch 日志；需要新增验证时按测试授权执行，
   新建任务或分叉也须沿用用户明确请求。确认当前线路返回预期文本和目标 provider 的 HTTP 200。

以下证据同时成立时，判为“旧任务上下文失效”，不改 key：当前线路和新任务正常；被怀疑的
provider key 直连也为 200；只有旧任务失败；旧任务报告的 URL 与当前转发目标不一致，或本地代理
日志中没有对应失败请求。若同一 provider 的当前 key 直连也返回 401，再按 [key 覆盖检查](relay-modes-and-providers.md#5-处理-key-被旧值覆盖) 处理。

需要保留历史继续工作时，优先使用 Codex 的同目录对话分叉：

- 只有用户已经授权新任务或分叉时才执行；否则先说明判断并询问。
- `fork_thread` 使用 `same-directory`，不是 Git branch，也不创建 worktree，也不复制项目文件。
- 分叉只复制已完成历史，不复制正在运行的 turn 或未完成回复；向子任务发送用户最后一条未完成指令，
  不要只发含义不明的“继续”。
- 用 `wait_threads` 验证子任务完成且没有认证错误；需要时为子任务设置可识别标题。
- 不反复重试已确认失效的旧任务。只有用户明确要求保留旧任务 ID 并接受中断其他活动任务时，才考虑
  完全重启 Codex Desktop；重启也不保证清除持久化的任务上下文。
