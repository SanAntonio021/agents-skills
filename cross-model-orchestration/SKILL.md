---
name: cross-model-orchestration
description: >
  Codex Desktop/CLI 与 Claude Code CLI 的正式计划双向互审流程。当任一端准备向用户提交一份
  需要确认后才执行的正式计划时，自动使用同一个 protocol-v2 claude-codex-bridge MCP，让对方模型
  在固定副本中审查、修订和测试；普通读取、分析、修改、测试、提交、交付和内部 Todo 不自动调用。
  用户明确要求对方审查交付物、让对方执行或启用专用跨模型循环时仍可显式使用。质量优先默认使用
  claude-opus-5/max 与 gpt-5.6-sol/max；调用方可选任务 profile 或目标侧模型/强度，bridge
  严格校验且不回退。失败、超时、模型不匹配、越界写入或同步冲突必须暂停。
compatibility: >
  Requires the CC Switch-registered claude-codex-bridge MCP to be available to the current host.
  The legacy codex@openai-codex companion and its hooks are archived references only and are not
  a runtime dependency. Hosts without a verified MCP route fail closed.
allowed-tools:
  - Read
  - Glob
  - Grep
  - Bash
  - AskUserQuestion
  - Agent
---

# Codex / Claude 双向互审

## 目标与触发

把跨模型复核限定为正式计划的默认质量门。作者先形成将要提交给用户确认的计划草案；对方模型
在 bridge 创建的固定副本中检查、允许范围内修订并运行必要测试。审查者不能直接写作者主项目，
作者必须检查 bridge 同步后的计划状态，再向用户展示最终计划。

只有以下情况自动进入：

- 当前处于 Plan Mode，准备退出并向用户提交正式计划；
- 即将展示一份多步骤实施方案，而且后续执行明确需要用户确认；
- 已有稳定的计划文件或完整计划正文，正在进入计划确认门。

以下情况不自动进入：读取或分析材料、调研、写作、代码/文档修改、运行命令、测试、提交、执行
已经确认的计划、验收和最终汇报。内部 Todo、`update_plan`、执行清单、简短步骤说明也不算正式
计划。任务复杂、耗时或交付物重要都不是触发理由。边界不清时只判断“是否正准备提交一份需要
用户确认的正式计划”，不能按复杂度扩大触发范围。

用户明确要求“让 Opus/Codex 审查”、明确指定 `review_repair`、明确要求对方执行，或明确启用跨模型
执行/科研循环等专用流程时，可以显式审查或使用 `task`；已确认计划中明确约定的对方执行也可以
继续。这些属于用户点名能力，不是全局自动复核门。审查报告、失败报告和用户已裁决的分歧报告不
递归触发。

`ExitPlanMode` 的拒绝理由只是 Claude 表达“先审查计划”的一种方式，不是唯一触发器，也不是
可信的计划路径来源。没有可靠路径时，使用稳定 `artifactName` 和完整 `artifactContent`，
绝不猜测“最新计划”。

## 统一入口

两端使用同一个共享 loopback MCP：`http://127.0.0.1:43123/mcp`，认证环境变量都是
`CLAUDE_CODEX_BRIDGE_TOKEN`。共享入口保留 v1 工具名；正式 protocol-v2 只能使用加 `v2_` 前缀的
工具，避免与 v1 同名工具混淆。

| 当前作者 | 共享 URL | v2 必填 `author` | bridge reviewer |
| --- | --- | --- | --- |
| Codex Desktop / Codex CLI | `http://127.0.0.1:43123/mcp` | `"codex"` | Claude |
| Claude Code CLI | `http://127.0.0.1:43123/mcp` | `"claude"` | Codex |

共享 v2 的 `author` 是调用方声明，bridge 由它派生相反 reviewer，并在 job 中记录
`author_source=caller_declared`。共享 URL 或 token 只认证本机访问，不能写成作者身份已认证；不得把
`author` 当作外部安全边界。`target`、`operation`、`round` 和权限仍由工具/bridge 固定，调用方不能覆盖。

`/mcp/codex`、`/mcp/claude` 以及 `CLAUDE_CODEX_BRIDGE_CODEX_TOKEN`、
`CLAUDE_CODEX_BRIDGE_CLAUDE_TOKEN` 保留为兼容和回滚入口。它们继续使用未加前缀的 v2 工具名，且只有
该路径可以把 endpoint + 独立 token 记为 `author_source=role_endpoint_token`；新的正式互审不默认切回它们。

For the Codex shared record, CC Switch may render both `headers` and `env_http_headers`. Treat that
combination as invalid: keep URL `/mcp`, retain only
`env_http_headers.X-Bridge-Token = CLAUDE_CODEX_BRIDGE_TOKEN`, and remove the static or interpolated
`headers.X-Bridge-Token` sibling. After the CC Switch change, verify the rendered `.codex/config.toml`
has no `[mcp_servers.claude-codex-bridge.http_headers]` table and that `codex mcp get
claude-codex-bridge` reports the shared environment header, `http_headers=-`, and
`transport=streamable_http`. This is a Codex-only rendering rule; do not apply it to Claude without
separate evidence. Do not edit `.cc-switch`, `.codex`, or other rendered runtime copies directly.

正式互审的调用顺序固定为 `v2_review_peer` 或 `v2_review_repair_peer`，随后在同一回合循环执行
`v2_await_peer`（单次最多 45 秒）-> `v2_peer_result`，直到原 job 形成终态；即使
`v2_await_peer` 已返回终态也要取一次 `v2_peer_result`。首次进入或考虑 workspace 模式时，先用
`v2_peer_status` 读取能力；第三轮用户裁决用 `v2_adjudicate_peer_series`。不得扫描最新线程、调用未加
前缀的 v1 工具、`codex exec`、`claude -p` 或 `codex@openai-codex` 绕过 bridge。
`orchestration-control.mjs` 与 `check-resume-candidate.mjs` 只用于历史状态测试和输入诊断，不是运行时入口。

每个终态公开 job 都必须带 bridge 持久化的 `completion_receipt`：

```text
schema_version=1
delivery_required=true
disposition
report_type=PLAN_REVIEW | DELIVERABLE_REVIEW | DISAGREEMENT_REPORT | PEER_REVIEW_FAILURE_REPORT
report
```

终态一经获得，立即原样向用户呈现 `completion_receipt.report`；它是 bridge 根据持久化状态和
renderer 生成的唯一用户报告，不能改用原始模型正文、自己的摘要或无结果的“已完成”表述。
若一次 45 秒 `v2_await_peer` 后 `v2_peer_result` 仍为 pending，只能在 commentary 更新非终态状态，
保留同一 `jobId`、`state`、首次记录的 `hard_deadline_at`、`elapsed_ms` 和 `remaining_ms`，然后在当前
回合继续下一次 `v2_await_peer` -> `v2_peer_result`。pending 不是最终答复、不是
`PEER_REVIEW_FAILURE_REPORT`，也不能成为结束当前回合并等待用户再次提醒的理由。整个循环必须复用
原 `jobId`、解析后的 model/effort/profile 和首次提交的十分钟硬截止；`hard_deadline_at` 发生变化时按
协议错误停止，绝不重试、换模型、降档、另开 job 或重置截止时间。bridge 到达原硬截止时会请求取消
同行任务并持久化 `decisiveError=peer_wait_timeout` 的失败回执；迟到结果不能覆盖该终态。

若提交调用在获得 `jobId` 前即不可达，立即输出 `jobId=unavailable`、
`decisiveError=bridge_unreachable` 的 `PEER_REVIEW_FAILURE_REPORT`，不猜测 job。若已经取得 `jobId`
后共享 `/mcp` 短暂断连，保留原硬截止并只恢复该入口、查询或等待同一个 job；不得重新提交。断连期间
继续在 commentary 报告恢复状态；到原硬截止仍无法读取该 job 时，输出带原 `jobId` 的
`bridge_unreachable` 失败报告。除这种无法取得 bridge 终态回执的传输故障外，所有终态只呈现 bridge
持久化的 `completion_receipt.report`。

能力门固定如下：`v2_peer_status.active=true` 和 `capabilities.inlineReviews=true` 是所有 v2 inline
审查的前提；`v2_review_repair_peer artifactMode=workspace` 还必须同时满足
`capabilities.workspaceRepairs=true` 与 `workspaceProbeState=available`。`pending` 或 `unavailable`
只表示当前进程尚未证明 Windows workspace sandbox，不影响零工具 inline 审查。

`loopbackState` 与 `childLoopbackState` 测量的是 sandbox 对临时 `127.0.0.1` fixture 的连通性，
不是 bridge daemon 的固定 loopback 绑定。`reachable_residual_risk` 或 `unverified` 必须连同
`loopbackResidualRisk` 和 `activationState` 作为能力证据原样保留；它们表示已披露的残余风险，
不能写成 sandbox 已隔离或 loopback 通过。只要 workspace 写入、工作区外写入拒绝、外网拒绝、
子进程文件/外网边界继承和超时后的进程树清理等硬门都合格，
`eligible_with_loopback_residual_risk` 仍允许 v2 调用；任一硬门失败则不创建 job。

`v2_review_peer` 固定为 `review_only + inline`：只读、零工具、不得声明工作区或测试命令。它是纯文字
正式计划和普通审查在 workspace 能力不可用时的默认入口。若请求带有符合下节门槛的
`continuation`，bridge 会在 `needs_changes` 终态后唤醒原作者任务；bridge 本身不替作者作语义修改，
而是由被唤醒的原 Codex 任务采纳意见、重算身份并提交下一轮。
protocol-v2 的 Claude/Codex 两个方向都不发送 provider-native transport schema；模型返回不透明文本，
bridge 再执行同一严格 JSON/Zod 校验，不补默认值、不接受额外字段、不降档或自动重试。v2 审查中出现
`StructuredOutput` 或任何其他工具记录都按隔离/传输异常处理，不能当作允许的零工具验证器。
需要完整替换正文时使用 `v2_review_repair_peer artifactMode=inline`；它也不使用工具，返回完整
`repairedArtifact`。workspace 修复只允许显式 `repairTargets`，并由 bridge 检查、同步和回滚。
如果用户明确要求 workspace 修订或结构化测试而能力为 `pending`/`unavailable`，不得提交该请求、
不得创建 job、不得重启或改用其他 sandbox；输出 `PEER_REVIEW_FAILURE_REPORT`，
`decisiveError=v2_workspace_capability_unavailable`。未经用户重新选择，不把 workspace 请求静默改成
inline 修订。旧 `submit_peer(operation=review_repair)` 只保留一版兼容，正式流程不得继续使用；兼容调用
缺字段时必须在创建 job 前返回 `missing_fields`。

Codex 的只读 `v2_review_peer` 使用 bridge 内部零工具执行。需要读取项目材料时不要伪装成普通 `ask`，
应使用完整审查包；协议 v2 不把作者项目、daemon 状态、token 或保留 job 副本作为 Codex `ask` 的 cwd。

## 模型路由

每次调用可选传 `taskProfile`、`model`、`reasoningEffort`。优先级为：显式模型/强度 > 显式
profile > 质量默认。路由只在既定 `target` 内选择模型，不能把异族互审改成同源自审。

- 质量默认：Claude `claude-opus-5` / `max`；Codex `gpt-5.6-sol` / `max`。
- `writing`、`creative_writing`、`coding`、`research`、`knowledge_work`：仍走质量默认。
- `balanced`：Claude `claude-sonnet-5` / `high`；Codex `gpt-5.6-terra` / `max`。
- `high_volume`：Claude `claude-sonnet-5` / `medium`；Codex `gpt-5.6-luna` / `max`。
- `claude-opus-4-6` / `max` 可显式选择，但不作为文字任务自动路由。

详细得分、来源和取舍见 [model-routing.md](references/model-routing.md)。当前 Creative Writing v3、
Longform 和 EQ-Bench 4 均显示 Opus 5 高于 Opus 4.6，因此不能依据旧印象自动降级。

bridge 返回并持久化 `requested_model`、`requested_reasoning_effort`、`task_profile`、
`routing_source` 和 `routing_rule_id`。恢复只能沿用原 job 的完整路由；缺证据或试图换模型/强度/profile
时停止。要换路由必须建立新的 `seriesId`/逻辑产物（不能在同一 v2 series 中切换）。任何选择不可用都失败关闭，不换模型、不降档。

## 审查包

每一轮先读取 [workflow-contract.md](references/workflow-contract.md)，再构造 protocol-v2 审查包。
全局自动触发时 `artifactType` 必须为 `plan`；`deliverable` 只接受用户明确要求或专用工作流的显式调用。
公共字段如下。共享入口必须带 `author`；它是 caller-declared，并由 bridge 记录来源。工具固定未列出的
`target`、`operation` 和权限：

```text
author ("codex" | "claude"), question, artifactId, artifactType, artifactName
artifactContent, artifactBytes, artifactSha256
artifactPath (正式文件建议提供，必须是正斜杠相对路径)
acceptanceCriteria (非空), constraints (可选)
taskProfile / model / reasoningEffort (可选)
seriesId / seriesVersion / latestJobId (续轮按 CAS 提供)
continuation (Codex Desktop 作者方向可选；必须使用当前任务的精确线程 ID)
```

`v2_review_peer` 只接受上述 inline 字段；`v2_review_repair_peer` 还必须提供 `artifactMode`：

```text
artifactMode=inline:
  不提供 targetRoot、repairTargets、testCommands；结果必须含完整 repairedArtifact。
artifactMode=workspace:
  targetRoot 为绝对路径；repairTargets 为非空的 {path, action} 数组；
  计划必须只有一个与 artifactPath 相同的 modify 目标；testCommands 可为 [] 或结构化命令数组。
  仅当 v2_peer_status 同时报告 workspaceRepairs=true 和 workspaceProbeState=available 时允许提交。
```

结构化 `testCommands` 的每项是 `{program, programBytes, programSha256, args, timeoutMs}`：`program`
必须是作者提供的绝对普通 `.exe`，字节数与 SHA-256 在发起时固定；命令由 bridge 的 Codex sandbox
执行，网络关闭、工作目录为固定副本，不向 Claude 暴露 Bash。不得把旧版字符串命令、shell 片段、
引号、变量、通配符、管道、重定向或命令串联塞进该字段。

不要复用上一轮、文件元数据或先前消息中的字节数和哈希。先确定最终 `artifactContent`，再按它的
UTF-8 编码计算两项身份并立即调用；内容发生任何变化都重新计算。正式文件还要给出 `artifactPath`，
workspace 能力已经通过时才给出最小 `repairTargets`。bridge 会把目标根完整复制到固定副本并排除 `.git`，
由 manifest、路径/链接检查和基线快照保护主项目。

## 三轮状态机

1. 作者用同一 `artifactId`（默认也是 `seriesId`）调用 `v2_review_peer` 或 `v2_review_repair_peer` 发起第 1 轮，保存 job ID、模式和（仅 workspace 时的）基线/结果 manifest。
2. 只接受带 `completion_receipt.schema_version=1` 和 `delivery_required=true` 的终态；先向用户呈现其
   `report`，再检查方向/模型/权限证据。inline 由作者检查审查正文或 `repairedArtifact`，workspace 才检查同步后的主项目。
3. `通过`：正式计划进入用户确认门；显式交付物审查则返回原作者独立验收。
4. `需修改`：inline 不发生主项目同步，workspace 先检查同步内容。满足自动续接门槛时，bridge 将同一
   Codex Desktop 任务唤醒；该原任务必须读取同一 job 的 findings，修订主项目，重新计算 UTF-8 字节数和
   SHA-256，把上一轮 findings/未决项放入下一轮 `question`、`constraints` 或 `artifactContent`，并携带
   上一轮返回的 `seriesVersion` 与 `latestJobId`。没有可验证 continuation（包括 Claude-authored 任务）时，
   作者侧按同一 CAS 流程继续；不要另开逻辑产物或猜测新线程。
5. 第 3 轮仍需修改，或双方出现实质分歧：输出 `DISAGREEMENT_REPORT`，等待用户裁决，不发第 4 轮。

审查通道不可用、超时、取消、认证/权限/sandbox 错误、格式错误、所选模型缺失或回执不匹配都不是
“需修改”，直接呈现 `completion_receipt.report` 中的 `PEER_REVIEW_FAILURE_REPORT` 并暂停；不换模型、不静默跳过、不回退。bridge
还会在同步前拒绝缺少对应审查标记/结论、明确 blocked/incomplete，或把失败测试/未满足验收写成“通过”的
`review_repair` 结果，并使用 `peer_contract_error` 记录原因。

## `needs_changes` 自动续接

`continuation` 是可选的请求字段，形式为：

```text
continuation = { host: "codex_desktop", threadId: "<当前 Codex Desktop task/thread ID>" }
```

在 Codex Desktop 中，调用方先读取当前任务进程的 `$env:CODEX_THREAD_ID`，并把该值原样填入
`continuation.threadId`；不得改用旧任务 ID、扫描最近任务或猜测线程。环境变量缺失、为空或无法核对时，
省略 `continuation` 并明确记录“自动续接不可用”，由作者侧继续处理，不能假装已经启用自动闭环。

bridge 只有在以下条件全部满足时才自动续接：`author=codex`、`artifactType=plan`、目标为 Claude、
请求模型与运行时回执完整匹配、当前轮次小于 3、没有 `pending_high_risk`，且普通 workspace 同步、测试、
基线和权限门均通过。此时 bridge 将已持久化的 `needs_changes` 结果写入 outbox，并通过 Desktop IPC
唤醒同一个任务；它不会直接改写计划正文。原 Codex 任务负责查询同一 `jobId`、采纳审查意见、重新计算
UTF-8 bytes/SHA-256，并以同一 `seriesId` 携带 `seriesVersion`/`latestJobId` 做 CAS 提交下一轮。

删除、重命名、权限或类型变化、目录覆盖、基线漂移、测试/模型证据缺失、超时、断连或不确定 IPC 回执
都会停止自动闭环。高风险变更先进入 `awaiting_user_decision`，完整展示稳定的
`pending_high_risk[].id`；用户精确批准后调用 `approve_peer_sync`，bridge 只重新核验并同步，不重跑模型，
同步成功后才再次唤醒原任务。Claude-authored 任务目前没有可验证的 Claude Desktop continuation API，
因此 bridge 不会擅自自动修改该方向，仍由 Claude/用户按作者侧流程处理。

续接 outbox 的状态为 `queued`、`dispatching`、`delivered` 或 `uncertain`。重启、断连或超时中断
`dispatching` 时必须转为 `uncertain`，且永不自动重发；调用方只能向用户报告该状态并等待明确恢复决定。

## 模型与权限验收

Codex -> Claude 方向只接受共享 `v2_*` 调用中的 `author=codex`：

```text
author = codex; author_source = caller_declared; derived reviewer = claude
v2_review_peer: review_only + inline + zero tools
v2_review_repair_peer + artifactMode=inline: ask-style zero tools; repairedArtifact required
v2_review_repair_peer + artifactMode=workspace: acceptEdits + native file changes only; no Bash
requested model / effort = bridge 解析出的目标侧白名单组合
workspace cwd/--add-dir 仅为固定副本
public reported model = selected requested model
```

`--model`/`--effort` 缺失、重复或不是解析结果，`system/init.model` 缺失或不等于所选模型，
端点角色、工具模式、`system/init.model` 或结果 schema 不匹配时停止。workspace 的测试命令由 bridge
单独执行；超时、退出码非零、程序身份变化或漏测都是失败证据，即使模型写“通过”也不得同步。

Claude -> Codex 方向只接受 bridge 返回的 SDK 记录与本次解析结果一致（共享调用中 `author=claude`）：默认是
`requested_model=gpt-5.6-sol`、`requested_reasoning_effort=max`；另有显式/profile 路由时按其
已记录值验收。其余固定项为 `workspace-write`、`approvalPolicy=never`、
网络和搜索关闭、无额外目录；记录请求模型、请求强度、CLI 版本和线程 ID，但没有运行时回执时不得把模型
身份写成“已验证”。固定副本中的 workspace `v2_review_repair_peer` 允许对方修复，主项目同步仍由 `repairTargets`、manifest、
基线漂移和逐文件哈希门控制。

Windows 下 bridge 子进程还固定 `include_environment_context=true` 与
`windows.sandbox="unelevated"`；两者共同保证命令工具实际使用固定副本 cwd，且不修改用户全局
Codex 配置。Codex 先用原生补丁工具；只有该工具明确写入失败后，才可用本地 shell 写入固定副本中的
`repairTargets`。同一结构化测试命令多次执行时，受保护事件保留全部尝试，但验收按最后一次状态判断：
后来通过只清除该命令此前的失败，未复测或最后仍失败继续停止同步。

## 同步与用户授权

普通新增/修改在基线未漂移且仍在 allowlist 内时由 bridge 使用同卷 staging、备份、原子替换、
逐文件哈希复核和逆序回滚自动同步。删除、重命名、权限变化、类型替换或整目录变化进入
`needs_attention`/`sync_status=awaiting_user`，列出稳定 `pending_high_risk[].id`。

只有用户明确接受完整且精确的 ID 集合后，才调用 `approve_peer_sync`。它创建新的同步请求 ID，
重新检查主项目基线和保留副本结果，不再调用任何模型；ID 缺失、多余、过期或基线漂移均失败关闭。
不能用授权扩大 `repairTargets`，也不能授权覆盖作者在审查期间产生的新改动。
待授权期间固定副本和持久锁继续保留；任何重叠目标根的新任务必须以
`retained_workspace_conflict` 失败，不能用另一个 `artifactId` 绕过待处理变更。

正式计划互审通过不等于执行授权。作者必须向用户展示最终计划、轮次结论、已解决项和剩余风险，
获得明确确认后才执行。已确认计划明确约定的对方 `task` 执行仍可通过 bridge 完成；执行作者自行
按任务验收标准检查，执行、返工和最终交付不自动再走相反方向互审。只有用户明确提出交付物互审，
或事先明确启用以里程碑互审为核心的专用工作流时，才发起对应的显式审查调用。

## 失败与发布

`PEER_REVIEW_FAILURE_REPORT` 至少包含方向、阶段、请求/实际模型、job ID、决定性错误、已完成内容、
未完成范围和恢复条件。实际模型无独立运行时回执时必须明确写“未验证”，不能把请求参数写成已验证。
`DISAGREEMENT_REPORT` 只整理双方已有判断和证据，不替用户选折中方案。

不要使用 `--yolo`、`--dangerously-skip-permissions`、直接改 `.cc-switch`/`.claude`/`.codex` 或
数据库。旧 `codex@openai-codex` 源码、许可证和测试可以留作行为参考，但不得作为运行时前置条件。

修改本 Skill 后，至少检查 `evals/evals.json`、`evals/trigger-evals.json`、`evals/integration-cases.md`，
覆盖两方向正式计划自动触发、普通实质任务和内部清单跳过、显式交付物调用、共享 `author` 的缺失/非法值、
caller-declared 来源记录、`v2_review_peer` 零工具、`v2_review_repair_peer` 的 inline/workspace 两种模式、workspace capability pending/unavailable 时的无 job
失败关闭、repair target/manifest 边界、三轮 CAS、用户确认门、审批同步、默认/显式/profile 路由、恢复时
换模型被拒绝、结构化/空 `testCommands`、正文身份重算、通道不可用和非所选模型停止。源码推送后，只对
本次改动的 Skill 使用定向 CC Switch
同步，并核对源码、CC Switch、Claude、Codex 四层文件集合和 SHA-256。
