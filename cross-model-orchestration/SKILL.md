---
name: cross-model-orchestration
description: >
  Claude Code 与 Codex 的全局跨模型编排。凡任务需要检查本地材料、制定计划、
  调研、写作、修改文件、运行命令或多步执行时都必须使用，即使用户没有点名
  Codex；适用于代码和非代码任务，包括文档、仿真、目录审计和 Skill 维护。
  Claude 负责规划与验收，Codex 先复核计划再执行，验收失败后续接返工，
  实质分歧交用户裁决。纯聊天、简单解释和单条只读命令不触发。
compatibility: Requires Claude Code plugin codex@openai-codex, an authenticated Codex CLI, exact user-level Bash permissions for the Plugin companion and this Skill helper, and read access to this Skill directory.
allowed-tools:
  - Read
  - Glob
  - Grep
  - AskUserQuestion
  - Agent
---

# Claude-Codex 跨模型编排

## 目标

让 Claude Code 默认担任规划者和验收者，让 Codex 担任计划复核者和执行者。
两边必须基于同一任务目标、证据和验收标准协作，不把模型之间的转述当成完成证据。

## 何时进入

以下任务进入本流程：

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

### Codex

- 先以只读方式检查 Claude 的计划；
- 计划通过后读取、修改文件、运行命令并生成交付物；
- 收到验收意见后在同一 thread 中返工；
- 给出可核查的文件、命令、结果和剩余问题。

## 前置检查

1. 确认 `codex@openai-codex` 已启用，Codex CLI 已安装且已登录。
2. 确认 Claude 用户级权限只放行当前 Plugin companion 的 `task` 命令、本 Skill
   helper，以及本 Skill 目录的只读访问。Windows 需要同时兼容 helper 的正斜杠和
   反斜杠绝对路径。Skill frontmatter 的 `allowed-tools` 不会传给
   `codex:codex-rescue` subagent，不能替代用户级权限；不得用全局
   `Bash(node:*)` 代替精确规则。Claude Code 2.1.207 对带多行 task 参数使用
   `Bash(node "<companionPath>" task *)`，不要只写旧式 `task:*`。
3. 保持官方 stop-time `review gate` 关闭。本 Skill 自己管理复核和返工闭环。
4. 一次协作流程只运行一条 Codex 工作链；不要在同一项目里并行启动会混淆
   `--resume` 目标的任务。
5. 禁止当前 Claude session 在闭环期间插入任何其他同项目 Codex task。
6. 读取 [workflow-contract.md](references/workflow-contract.md)，使用其中的提示词和报告格式。

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

使用 `Agent` 工具调用 `subagent_type: "codex:codex-rescue"`。默认把整个 Agent
调用设为后台运行，并在请求中使用 `--fresh --wait`，让 companion 在该 Agent 内
等待 Codex 完成；Claude 收到 Agent 完成通知后才继续。明确要求只读计划复核、
禁止修改文件，并套用参考文件中的 `PLAN_REVIEW` 输出契约。

`--fresh`、`--resume` 和 `--wait` 是交给 subagent 的控制词。subagent 按官方
runtime 处理并从实际 task 文本中移除，不强制把 `--wait` 写进 companion 命令。

调用 Agent 前使用 Skill 加载消息已经给出的 `Base directory for this skill`，不要
扫描 `.claude/skills` 父目录。把该目录下的 helper 拼成绝对路径并统一成正斜杠，
然后只用 Bash 运行一条直接命令：

```bash
node "<helperPath>" --companion-path
```

必须把 `<helperPath>` 替换为已解析的正斜杠绝对路径；不得把占位符、环境变量或
`${CLAUDE_SKILL_DIR}` 原样交给 shell。不得改用 PowerShell，不得先读取
`settings.json`，也不得把路径查询和 helper 调用拼成复合命令。helper 调用被权限
拒绝时，直接按调用失败暂停。

把返回的 `companionPath` 原样注入 Agent prompt。Plugin 更新后路径会变化；若新路径
不在用户级权限中，按调用失败暂停，先更新精确权限，不扩大成 `Bash(node:*)`。

每次 Agent prompt 都要重申：subagent 只能进行一次直接的
`node "<Claude 注入的 companionPath>" task ...` 调用。实际命令里不得保留 `$`、
`${CLAUDE_PLUGIN_ROOT}` 或其他环境变量引用。不得先运行
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

首次复核完成后，运行：

```bash
node "<helperPath>"
```

仍使用前面记录的同一个正斜杠绝对 `helperPath`，不重新探测或改换命令形式。

记录输出的 `candidateThreadId`。找不到候选 thread 时按 Codex 调用失败暂停。
该候选只在同一个仍存活的 Claude session 内有效；session 结束后 Plugin 会清理
session job，不能在新 session 中假定可续接。

- `通过`：进入执行；
- `需修改`：Claude 只修订计划，先用记录的 `helperPath` 和 thread ID 核对 resume
  candidate，再用 `--resume --wait` 交给同一 Codex thread 复核；
- `实质分歧`：停止执行，向用户提交分歧报告。

如果同一异议重复出现且双方都没有新证据，不继续空转，按实质分歧处理。

### 3. Codex 执行

每次续接前，运行下列检查，其中 `<thread-id>` 是首次记录值：

```bash
node "<helperPath>" "<thread-id>"
```

`helperPath` 必须沿用首次复核前记录的正斜杠绝对路径，不重新扫描或展开环境变量。

只有 `ok: true` 才能调用同一 `codex:codex-rescue` subagent，使用
`--resume --wait --write`。候选 ID 不同、候选缺失或检查失败时，按
`CODEX_FAILURE_REPORT` 暂停，不猜测续接。

任务指令包含最终计划、验收标准、允许修改的范围和高风险停止条件。

默认将整个 `Agent` 调用置于 Claude Code 后台；只有确认能很快完成的调用才放在
前台。仍让 companion 以前台方式完成该 Codex turn，等待 Agent 完成通知后再验收。
不要另开新的 Codex thread，也不要在等待时启动另一条 Codex 工作链。等待期间
不得创建 Cron、automation、提醒或定时任务，只依赖 Agent 完成通知。

### 4. Claude 验收

Claude 必须独立核验：

- 交付物是否真实存在；
- 修改范围是否符合计划；
- 关键命令、测试或数据是否真实运行；
- 每条验收标准是否有证据；
- 是否存在未披露的失败、假设或副作用。

验收时只读文件和运行只读或验证命令，不自行修补产出。

### 5. 自动返工

验收不通过时，列出具体文件、问题、证据和通过判据。先再次核对 resume candidate
与记录的 thread ID 一致，再用 `--resume --wait --write` 退回同一 Codex thread。
返工后重新执行完整验收。

循环持续到：

- 所有验收标准通过；或
- 出现实质分歧；或
- Codex 调用失败、超时、额度耗尽或无法可靠续接。

### 6. 完成或停止

双方一致时，由 Claude 汇总最终交付物、验证结果和残余风险。

出现分歧时，使用 `DISAGREEMENT_REPORT`。Codex 不可用时，使用
`CODEX_FAILURE_REPORT`，暂停等待用户处理。不得改由 Claude 接管执行。

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
