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
   not found）。核验发起会话 cwd 所在目录的 `.claude/settings.json`（本任务即
   `D:\BaiduSyncdisk\.claude\settings.json`），确认 `enabledPlugins["codex@openai-codex"]`
   为 `true`。判据锚定 cwd，不锚定 skill 源码所在项目。该键缺失或为 `false` 按宿主不兼容
   处理：退出本 Skill、不输出 `CODEX_FAILURE_REPORT`（协作任务尚未启动），告知用户需在该
   项目启用插件。如果在启动任何 Plugin companion 或 Agent job 前发现宿主不兼容，退出本
   Skill，返回宿主的正常处理流程；这不是 Codex 调用失败，不输出 `CODEX_FAILURE_REPORT`。
   只有用户明确要求使用本 Skill 时，才说明需要改在 Claude Code CLI 会话运行并等待用户
   切换，不改用其他调用方式绕过。
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
   并行启动多个 Codex 后台任务。跨 session 并行不禁止，但并发写同一批文件的风险
   由"计划已授权的范围"约束控制。后台任务完成后 `result <jobId>` 精确读取，不依赖
   线程续接。helper 对 job ID 做精确匹配；找不到或状态非 completed 时按失败处理。
   **判活判据**：helper 依据 `<state-dir>/jobs/<jobId>.json` 的 `status` 字段判定活动
   状态，不按 sessionId 隔离（同一 workspace 的所有 Claude session 共享状态池）。
   `queued`/`running` 即活动，`completed`/`failed`/`cancelled` 即终态（已完成或已归档）。
   未完成时 `.log` 可能仍在增长，禁止按字节不增作为收工信号。
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

启动一次后台 Codex 任务（`--background --fresh --write`）专门进行计划复核。Claude 先
在主会话通过 Bash 运行 helper 取得 companion 路径：

```bash
node “$USERPROFILE/.claude/skills/cross-model-orchestration/scripts/check-resume-candidate.mjs” --companion-path
```

取得 `companionHomeRelative` 后，以如下形式启动后台任务（`$USERPROFILE` 由 shell 展开）：

```bash
node “$USERPROFILE/<companionHomeRelative>” task --background --fresh --write --cwd “<共同祖先目录>” “<复核提示词（单行序列化）>”
```

明确要求只读计划复核、禁止修改文件，并套用参考文件中的 `PLAN_REVIEW` 输出契约。

**等待与轮询**：后台任务启动后，Claude 主会话使用 `status <jobId>` 轮询，直到状态变为
终态（`completed`/`failed`/`cancelled`）。`result <jobId>` 取 `rendered` 字段作为
Codex 的复核输出；**任何情况下不以 `.log` 作为正文兜底**。

**快照约束**：Claude 在启动后台任务前为复核范围内每个普通文件记录相对路径、字节数和
SHA256；Git 项目还要记录 Git 状态。任务完成后逐项比较文件集合与内容快照。发现任何变化
时停止，不接受该复核结果，也不由 Claude 回滚或继续执行。

**一次一链**：同一 Claude session 内最多运行一条 Codex 工作链。后台任务返回结果前，禁止
再次启动 helper、发起第二个后台任务或直接调用 companion。

**辅助 helper**：`$USERPROFILE` 必须原样写入命令，由 shell 本地展开，不得替换成含用户名
的绝对路径（2026-08-10 实测：路径在工具参数传输中被改写，导致 `MODULE_NOT_FOUND`）。
POSIX 宿主用 `$HOME` 替换 `$USERPROFILE`，其余不变。

Plugin 1.0.8 以 `--background` 模式启动，不再依赖同步前台等待。后台任务与索引写入均
已解耦，不存在持锁死锁风险（Plugin 1.0.6 `--wait` 模式的限制已通过异步化消除）。

任何 Codex 任务报告认证、权限、sandbox、timeout、额度或 runtime 失败时，立即输出
`CODEX_FAILURE_REPORT` 并暂停。不得先重试，不得把失败包装成计划问题，不得改用新任务或
其他执行方式绕过，也不得让 Claude 接管。

- `通过`：进入执行；
- `需修改`：Claude 只修订计划，以 `--fresh` 启动新后台任务进行第二轮复核（无法定向续接，
  见前置检查第 7 条）；
- `实质分歧`：停止执行，向用户提交分歧报告。

如果同一异议重复出现且双方都没有新证据，不继续空转，按实质分歧处理。

#### 2a. 独立复核变体（双盲，仅召回类审计）

当任务本身是”查有没有遗漏/有无覆盖不足”的召回类审计（典型：对若干贡献点逐条做范围核
对），且用户明确要求双盲时，改用本变体：Claude 与 Codex 各自独立产出清单，互不见对方
结论；只对两份清单的**差异项**做串行比对和取舍，不在各自的完整结论上逐条争论。调
Codex 时，只给它任务定义本身，**剥离 Claude 自己的结论**，防止它的注意范围被
Claude 的清单框定（锚定）。召回类之外（精度类：某项结论是否成立、怎么修、修到哪），
仍走上面的串行路径，不做双盲。

### 3. Codex 执行

计划通过后，以 `--background --fresh --write` 启动新后台任务执行。任务提示词包含最终
计划、验收标准、允许修改的范围和高风险停止条件。Claude 主会话持续轮询 `status`，直到
终态；`result <jobId>` 取 `rendered` 字段，不以 `.log` 作为正文兜底。

**无定向续接**：`--resume` / `--resume-last` 在本 Skill 中一律不使用，各阶段均 `--fresh`。
证否依据：companion 的 `--resume` 只能绑定最近一个 session 内的 thread，跨轮次和跨
session 不能可靠定向续接（`check-resume-candidate.mjs:87-88` 全等比对、不符退出 2）。
正文来源是 job JSON 的 `rendered`（完整响应体），不依赖 thread 连续性。

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

验收不通过时，列出具体文件、问题、证据和通过判据。以 `--background --fresh --write`
启动新后台任务（无定向续接，各阶段均 `--fresh`），在提示词中包含返工说明和通过判据。
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
