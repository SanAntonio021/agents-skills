---
name: cross-model-orchestration
description: >
  Claude Code CLI 与 Codex 的跨模型编排。仅当当前主会话是 Claude Code CLI，且任务
  需要检查或合并本地材料、制定计划、调研、比较、写作、修改文件、运行命令或多步
  执行时自动使用，即使用户没有点名 Codex。Codex Desktop、Codex CLI、Claude Desktop
  （Cowork）及其他宿主不自动触发；纯聊天、不依赖材料的简单解释和一条明确只读命令
  也不触发。
compatibility: Requires Claude Code plugin codex@openai-codex, an authenticated Codex CLI, exact user-level Bash permissions for the Plugin companion and this Skill helper, and read access to this Skill directory.
allowed-tools:
  - Read
  - Glob
  - Grep
  - Bash
  - AskUserQuestion
  - Agent
---

# Claude-Codex 跨模型编排

## 目标

让 Claude Code 默认担任规划者和验收者，让 Codex 担任计划复核者和执行者。
两边必须基于同一任务目标、证据和验收标准协作，不把模型之间的转述当成完成证据。

## 何时进入

先判断当前主会话：

- Claude Code CLI：继续按下面的任务范围判断；
- Codex Desktop、Codex CLI、Claude Desktop（Cowork）或其他宿主：不进入本流程，
  由当前宿主按自身能力直接处理任务；
- 用户在不兼容宿主中明确点名本 Skill：说明它只能在 Claude Code CLI 中运行，等待
  用户切换；由于协作任务尚未启动，不输出 `CODEX_FAILURE_REPORT`。

在 Claude Code CLI 中，以下任务进入本流程：

- 需要读取或检查本地材料；
- 需要调研、写作、修改文件或运行命令；
- 需要多步骤推进、比较方案或形成重要结论；
- 用户要求审计、复核、仿真、整理目录、维护 Skill 或处理项目交付物。

以下任务直接由 Claude 回答，不调用 Codex：

- 纯聊天；
- 不依赖材料的简单解释；
- 一条明确、只读、无需分析后续结果的命令。

如果边界不清，优先进入本流程。用户希望能调用时尽量调用 Codex。

## 角色边界

### Claude

- 做开始规划所需的最小只读探索；
- 明确目标、范围、约束、交付物和验收标准；
- 根据 Codex 的复核意见修订计划；
- 只读核验 Codex 的实际产出；
- 组织返工意见或分歧报告。

Claude 不代替 Codex 修改文件或完成执行阶段。Codex 失败时也不静默接管。

上述"不静默接管"适用于**执行失败**（认证超时、sandbox 拦截、额度耗尽、runtime 错误等偶发可恢复情形，完整列表见 §2 的 `CODEX_FAILURE_REPORT` 触发条件）。若某项能力是 Codex **结构上从未具备**（非执行失败，而是运行时永远不给该能力、且无合法开关可打开），需向用户提交**能力缺口报告**，列出至少三层独立证据后请用户裁定；用户显式授权 Claude 承接后，Claude 方可执行，且授权边界须明确记录在任务计划里、不得向外扩展。

### Codex

- 先以只读方式检查 Claude 的计划；
- 计划通过后读取、修改文件、运行命令并生成交付物；
- 收到验收意见后在同一 thread 中返工；
- 给出可核查的文件、命令、结果和剩余问题。

## 前置检查

1. 确认 `codex@openai-codex` 已启用，Codex CLI 已安装且已登录。
2. 再次确认主会话是 Claude Code CLI。Claude Desktop（Cowork）会话的 Agent 工具
   不注册插件子代理，`codex:codex-rescue` 不可用（2026-07-26 实测报 Agent type
   not found）。如果在启动任何 Plugin companion 或 Agent job 前发现宿主不兼容，
   退出本 Skill，返回宿主的正常处理流程；这不是 Codex 调用失败，不输出
   `CODEX_FAILURE_REPORT`。只有用户明确要求使用本 Skill 时，才说明需要改在
   Claude Code CLI 会话运行并等待用户切换，不改用其他调用方式绕过。
3. Windows 下确认 Codex 全局配置包含
   `[sandbox_workspace_write] exclude_slash_tmp = true`。保留用户 `TMPDIR`，不要把
   当前盘根目录下的 `C:\tmp` 或 `D:\tmp` 加入 workspace-write；否则 elevated
   helper 可能因无权刷新这些目录的 ACL 而报 `setup refresh had errors`。这不需要
   启用 Windows 可选的 Windows Sandbox 虚拟机功能。
4. 确认发起会话的 cwd 是本次全部目标路径的共同祖先目录。目标为多个仓库时取它们的
   共同祖先，该目录本身不必是 git 仓库。cwd 与目标同级的旁系跨越会被命令允许列表
   拦截：`git add` 报 `blocked by policy`，`git -C ..`、读父目录规则文件、companion
   探测一并 `declined`，只有 `git status` 系放行。**改 job 的 `workspaceRoot` 参数
   无法绕过**，闸门跟启动会话的 cwd 走，不跟 job 参数走（2026-08-10 实测：已把
   `workspaceRoot` 正确设为目标仓库且 `write=true`，`git add` 仍被拒）。不满足时
   停止并要求改在覆盖目标路径的会话运行，不重试、不改用其他调用方式绕过，也不
   缩小任务范围。这属于发起环境不合规，不输出 `CODEX_FAILURE_REPORT`。
5. 确认 Claude 用户级权限只放行当前 Plugin companion 的 `task` 命令、本 Skill
   helper，以及本 Skill 目录的只读访问。权限规则按 shell 展开**前**的原始命令串
   匹配，因此 Windows 规则要写成含 `$USERPROFILE` 字面量的形态，例如
   `Bash(node "$USERPROFILE/.claude/skills/cross-model-orchestration/scripts/check-resume-candidate.mjs"*)`
   与 `Bash(node "$USERPROFILE/.claude/plugins/cache/openai-codex/*" task *)`；同时
   保留旧的绝对路径规则以兼容尚未升级的运行时副本。Skill frontmatter 的
   `allowed-tools` 不会传给 `codex:codex-rescue` subagent，不能替代用户级权限；
   不得用全局 `Bash(node:*)` 代替精确规则。Claude Code 2.1.207 对带多行 task 参数
   使用 `task *` 通配，不要只写旧式 `task:*`。
   本机使用 cc-switch 时，精确权限必须写入 `common_config_claude` 与全部
   claude/claude-desktop provider 快照；`%USERPROFILE%\.claude\settings.json`
   是按当前 provider 渲染的快照产物，只改它会在 provider 切换或重渲染时丢失
   （2026-07-11 打通后失效的根因；2026-07-26 写入全部快照并验证渲染存活）。
6. 保持官方 stop-time `review gate` 关闭。本 Skill 自己管理复核和返工闭环。
7. 同一 Claude session 内一次协作流程只运行一条 Codex 工作链，不在同一 session 里
   并行启动多个 Codex 任务。跨 session 并行不禁止：helper 按 sessionId 隔离候选，
   缺 sessionId 直接拒绝（scripts/check-resume-candidate.mjs 83-85 行），并对记录的
   thread ID 全等比对、不符退出 2（87-88 行），不会静默接错另一条链；跨 session 的
   真实风险是并发写同一批文件，由"计划已授权的范围"约束控制。
8. 禁止当前 Claude session 在闭环期间插入任何其他同项目 Codex task。
9. 读取 [workflow-contract.md](references/workflow-contract.md)，使用其中的提示词和报告格式。

## 工作流

### 1. Claude 制定计划

先做最小只读探索，然后形成任务计划。计划至少包含：

- 目标与不做什么；
- 输入材料和证据来源；
- 执行步骤及顺序；
- 交付物；
- 可验证的验收标准；
- 权限、安全和失败边界。

此阶段不修改用户交付物。

### 2. Codex 复核计划

使用 `Agent` 工具调用 `subagent_type: "codex:codex-rescue"`。整个 Agent 调用必须前台
等待，并在请求中使用 `--fresh --wait --write`，让 companion 在该 Agent 内等待 Codex
完成。每个阶段最多发起一次 Agent 调用；Agent 未返回时，只能等待原调用，禁止再次
运行 helper、核对 resume candidate 或发起第二个 Agent。明确要求只读计划复核、禁止
修改文件，并套用参考文件中的 `PLAN_REVIEW` 输出契约。

Plugin 1.0.6 不能把一个仍在 broker 中的只读 thread 在续接时可靠升级为
`workspace-write`；即使后续传入 `--write`，实际 turn 仍可能保持只读。为兼顾同一
thread 与后续执行，首次创建 thread 时就使用 `--write`。这只代表运行时具备写入
能力，计划复核行为仍必须只读。Claude 在调用前为复核范围内每个普通文件记录相对
路径、字节数和 SHA256；Git 项目还要记录 Git 状态，但不能用状态代替内容快照。
内容快照排除 `.git` 内部元数据，Git 与非 Git 目录使用同一标准。复核返回后逐项
比较文件集合和内容快照。无法建立完整快照时不启动复核；发现任何变化时停止，不接受
该复核结果，也不由 Claude 回滚或继续执行。

`--fresh`、`--resume` 和 `--wait` 是交给 subagent 的控制词。subagent 按官方
runtime 处理并从实际 task 文本中移除，不强制把 `--wait` 写进 companion 命令。

调用 Agent 前不要扫描 `.claude/skills` 父目录，也不要使用 Skill 加载消息给出的
`Base directory for this skill`——那是展开后的绝对路径，含被改写的用户名段。
helper 路径固定，只用 Bash 运行一条直接命令：

```bash
node "$USERPROFILE/.claude/skills/cross-model-orchestration/scripts/check-resume-candidate.mjs" --companion-path
```

`$USERPROFILE` 由 shell 本地展开，必须原样写入命令，不得替换成展开后的绝对路径。
Windows 用户目录名会在工具参数传输中被改写：写进参数的用户名段到达 node 进程时已
变成另一个字符串，指向一个不存在的目录，因而任何含用户名的字面绝对路径都会报
`MODULE_NOT_FOUND`（2026-08-10 实测，主会话与 subagent 两端一致；同一次调用内
`os.homedir()` 返回真名而参数里的用户名段被改写，即判定性证据）。POSIX 宿主用
`$HOME` 替换 `$USERPROFILE`，其余部分不变。不得改用 PowerShell，不得先读取
`settings.json`，也不得把路径查询和 helper 调用拼成复合命令。helper 调用被权限
拒绝时，直接按调用失败暂停。

记录返回的 `companionHomeRelative`，它是相对用户主目录的路径，不含用户名，可以安全
穿过工具参数传输层。同时返回的 `companionPath` 是展开后的绝对路径，只用于人工阅读
和排错，**不得注入 Agent prompt**。Plugin 更新后路径会变化；若新路径不在用户级权限
中，按调用失败暂停，先更新精确权限，不扩大成 `Bash(node:*)`。

每次 Agent prompt 都要重申：subagent 只能进行一次直接的
`node "$USERPROFILE/<Claude 注入的 companionHomeRelative>" task ...` 调用，其中
`$USERPROFILE` 原样保留由 subagent 的 shell 展开，只有 `companionHomeRelative` 部分
由 Claude 替换成实际值。除这一个 `$USERPROFILE` 外，实际命令里不得保留其他 `$`、
`${CLAUDE_PLUGIN_ROOT}` 或环境变量引用。不得先运行
`--help`，不得创建临时文件，不得使用管道、重定向、here-doc、命令替换、`cd` 或
复合 shell 命令，也不得设置 `dangerouslyDisableSandbox`。该 Bash tool call 必须
设置至少 `600000` ms 的 timeout，并保持前台等待，不得设置 `run_in_background`。
把参考文件中的多行任务模板序列化成单行“字段名=值；”文本，完整保留所有字段；
实际 Bash `command` 字符串不得含字面 CR/LF。Windows 的任务参数内部不得使用 XML
结束标签或 `C:/` 绝对路径；优先使用相对当前 Codex cwd 的路径，必须写绝对路径时
使用反斜杠。任务文本仍作为一个参数传入。如果无法在不丢信息的前提下安全序列化，
则返回失败，不重试、不改用其他命令。

如果 subagent 内的 `Bash(node:*)` 被权限规则拒绝，按 Codex 调用失败暂停。Claude
不得在主会话直接运行 companion，也不得改用其他方式绕过 subagent。

首次复核完成后，先核对复核前后的文件集合、字节数和 SHA256；Git 项目同时核对
Git 状态。确认 Codex 没有修改文件，再运行：

```bash
node "$USERPROFILE/.claude/skills/cross-model-orchestration/scripts/check-resume-candidate.mjs"
```

仍保持 `$USERPROFILE` 未展开，不改换命令形式。

记录输出的 `candidateThreadId`。找不到候选 thread 时按 Codex 调用失败暂停。
该候选只在同一个仍存活的 Claude session 内有效；session 结束后 Plugin 会清理
session job，不能在新 session 中假定可续接。

任何 Codex turn 报告认证、权限、sandbox、timeout、额度或 runtime 失败时，立即
输出 `CODEX_FAILURE_REPORT` 并暂停。不得先重试，不得把失败包装成计划问题，不得
改用新 thread 或其他执行方式绕过，也不得让 Claude 接管。

- `通过`：进入执行；
- `需修改`：Claude 只修订计划，先用同一条 helper 命令和记录的 thread ID 核对 resume
  candidate，再用 `--resume --wait` 交给同一 Codex thread 复核；
- `实质分歧`：停止执行，向用户提交分歧报告。

如果同一异议重复出现且双方都没有新证据，不继续空转，按实质分歧处理。

#### 2a. 独立复核变体（双盲，仅召回类审计）

当任务本身是"查有没有遗漏/有无覆盖不足"的召回类审计（典型：对若干贡献点逐条做范围核
对），且用户明确要求双盲时，改用本变体：Claude 与 Codex 各自独立产出清单，互不见对方
结论；只对两份清单的**差异项**做串行比对和取舍，不在各自的完整结论上逐条争论。调
Codex 时，只给它任务定义本身，**剥离 Claude 自己的结论**，防止它的注意范围被
Claude 的清单框定（锚定）。召回类之外（精度类：某项结论是否成立、怎么修、修到哪），
仍走上面的串行路径，不做双盲。

### 3. Codex 执行

每次续接前，运行下列检查，其中 `<thread-id>` 是首次记录值：

```bash
node "$USERPROFILE/.claude/skills/cross-model-orchestration/scripts/check-resume-candidate.mjs" "<thread-id>"
```

helper 路径始终保持 `$USERPROFILE` 未展开，不重新扫描、不改写成绝对路径。

只有 `ok: true` 才能调用同一 `codex:codex-rescue` subagent，使用
`--resume --wait --write`。候选 ID 不同、候选缺失或检查失败时，按
`CODEX_FAILURE_REPORT` 暂停，不猜测续接。

任务指令包含最终计划、验收标准、允许修改的范围和高风险停止条件。

整个 `Agent` 调用与 companion 都以前台方式完成该 Codex turn。每个执行或返工阶段
最多发起一次 Agent 调用；没有拿到该调用的最终结果前，不得重复核对 candidate、重发
Agent、另开 Codex thread 或启动另一条 Codex 工作链。等待期间不得创建 Cron、
automation、提醒或定时任务。

### 4. Claude 验收

Claude 必须独立核验：

- 交付物是否真实存在；
- 修改范围是否符合计划；
- 关键命令、测试或数据是否真实运行；
- 每条验收标准是否有证据；
- 是否存在未披露的失败、假设或副作用。

验收前先按拟验收文件逐个确定 Git 根目录，使用
`git -C "<文件所在目录>" rev-parse --show-toplevel` 建立文件与仓库的对应关系。
同一任务可能同时修改父仓库、嵌套仓库或并列的独立仓库，不能只检查当前工作目录。
每个独立仓库分别核对分支、remote、HEAD 和工作区状态。

对已经提交的改动，空的 `git diff` 只表示当前工作区相对 HEAD 干净，不能据此判断
文件没有修改或任务没有实施。至少联合核对：

- 当前文件内容或 SHA256；
- `git show --stat <commit>` 和 `git show <commit> -- <path>` 是否包含目标改动；
- `git merge-base --is-ancestor <commit> origin/<branch>` 是否确认提交已进入远端分支；
- 验收要求中的实际命令、测试和产物是否在当前版本上通过。

如果交付包含本机自建 Skill，源码以
`D:\BaiduSyncdisk\.agents\skills\<name>\` 为准。提交并推送后，Codex 执行者取得
`agents-skills` 的 40 位远端提交 SHA，并在同一执行 turn 调用：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File "D:\BaiduSyncdisk\.agents\automation\ccswitch-skill-sync\Invoke-CcSwitchSkillSync.ps1" `
  -Skills "<本次提交实际修改的逗号分隔 Skill 名称>" `
  -ExpectedRemoteCommit "<40 位远端提交 SHA>"
```

目标集合必须与该提交实际修改且仍存在的 Skill 集合完全一致。helper 只执行一次“检查更新”
和过滤后的单项“更新”，禁止“全部更新”；不建 watcher 或计划任务，不修改 CC Switch 源码、
EXE、数据库、配置或运行时目录。Claude 验收者核对 helper 的单个 JSON、退出码、远端祖先关系，
以及提交源码、`.cc-switch\skills`、`.claude\skills`、`.codex\skills` 四层全部目标文件集合和
SHA-256。只有退出码 `0`、状态 `runtime_active` 且四层完全一致才算生效；任一自动更新或验收
失败时，只能报告“源码已推送，运行时未生效”，不得直接修改运行时副本或把部分成功写成完成。

验收标准明确要求真实集成测试时，Claude 必须在本轮验收中使用规定的环境开关和命令
重新运行，并记录命令、退出状态、通过/失败/跳过数量和耗时。代码存在、旧测试日志或
Codex 的完成声明都不能替代本轮真实结果。

验收时只读文件和运行只读或验证命令，不自行修补产出。

### 5. 自动返工

验收不通过时，列出具体文件、问题、证据和通过判据。先再次核对 resume candidate
与记录的 thread ID 一致，再用 `--resume --wait --write` 退回同一 Codex thread。
返工后重新执行完整验收。

循环持续到：

- 所有验收标准通过；或
- 出现实质分歧；或
- Codex 调用失败、超时、额度耗尽或无法可靠续接。

上述失败条件不是验收不通过，不能进入自动返工。只有 Codex 已成功执行、Claude
检查实际产出后发现未满足验收标准，才进入返工循环。

### 6. 完成或停止

双方一致时，由 Claude 汇总最终交付物、验证结果和残余风险。

出现分歧时，使用 `DISAGREEMENT_REPORT`。Codex 不可用时，使用
`CODEX_FAILURE_REPORT`，暂停等待用户处理。不得改由 Claude 接管执行。
分歧报告只整理双方已有判断、理由、证据、争议点和选项影响；不得推荐或代选方案，
也不得新增双方尚未评估的折中方案。用户裁决后再继续。

## 安全边界

- 不使用 `--yolo`、`--dangerously-skip-permissions` 或其他绕过权限的参数；
- Codex 的写入和命令能力仍受当前项目、sandbox 和用户授权约束；
- 删除、覆盖、重置、权限变更、付费、对外发送、硬件操作，以及会丢失既有内容的
  整文件替换前必须询问用户；计划已授权的局部修改不重复询问；
- 复核阶段必须只读；
- 无法确认 `--resume` 指向本流程的 thread 时停止，不猜测续接。

## 与专业 Skill 的关系

本 Skill 只管 Claude 与 Codex 的角色、交接、复核和返工。论文、申报、文档、
仿真、Skill 审计等专业做法继续由对应 Skill 决定。长期科研里程碑任务在本流程
之上加载 `cross-model-research-loop`，使用其里程碑和研究评审门。
