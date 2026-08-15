# 工作流契约

## 基本约束

本契约用于同一个 `claude-codex-bridge` MCP 的两个方向：`Codex -> Claude` 和
`Claude -> Codex`。每一轮的作者、审查者、产物、哈希、bridge job ID 和同步状态都必须可追溯。

- 每个 `artifactId` 最多三轮，`round` 只能为 `1`、`2` 或 `3`，`maxRounds` 固定为 `3`。
- 已有活动 job 时只能查询该 job；不得重发、猜测最新线程、使用 `--resume-last` 或绕过 bridge。
- `review_repair` 是一次调用：审查者在固定副本中检查、修复、测试并返回结论；作者主项目不直接暴露。
- 审查结果不是执行授权。正式计划通过互审后仍须用户明确确认。
- 通道异常、模型不匹配、格式错误、越界写入、基线漂移、超时或取消立即失败关闭，不算“需修改”。
- `review_repair` 的结果在 bridge 同步前必须包含对应的 `PLAN_REVIEW` 或 `DELIVERABLE_REVIEW`
  标记和明确的 `结论`（`通过`、`需修改` 或 `实质分歧`）。模型明确报告阻塞/未完成、认证或权限失败，
  或把失败测试/未满足验收写成“通过”时，job 进入 `failed`，错误码为 `peer_contract_error`，并返回
  `PEER_REVIEW_FAILURE_REPORT`；审查副本的变更不得同步回作者主项目。

## 审查包

每轮发送如下对象（MCP 工具可以使用 camelCase，bridge 会保存等价 snake_case）：

```json
{
  "artifactId": "stable-logical-artifact-id",
  "artifactType": "plan | deliverable",
  "author": "Codex | Claude",
  "reviewer": "Claude Opus 5 | Claude Opus 4.6 | Claude Sonnet 5 | Codex",
  "taskProfile": "quality | writing | creative_writing | coding | research | knowledge_work | balanced | high_volume",
  "model": "optional allowlisted target model",
  "reasoningEffort": "optional supported effort",
  "round": 1,
  "maxRounds": 3,
  "artifactName": "logical name or relative path",
  "artifactBytes": 0,
  "artifactSha256": "64 lower-case hex characters",
  "artifactContent": "full reviewable content and evidence",
  "artifactPath": "optional controlled path",
  "targetRoot": "absolute project root when a copy is required",
  "allowedPaths": ["relative/file"],
  "priorRounds": [],
  "priorFindings": [],
  "openItems": [],
  "acceptanceCriteria": ["objective criterion"],
  "testCommands": ["npm.cmd test"],
  "constraints": ["scope or safety boundary"],
  "reviewerAccess": "read_only | isolated_write"
}
```

`artifactBytes` 和 `artifactSha256` 必须对应当前内容；`priorRounds.length === round - 1`，轮次连续且
不重复。`review_repair` 必须提供稳定 `artifactId`、`artifactType`、`round`、`targetRoot` 和非空
`allowedPaths`。Claude 的 `ask` 审查没有工具，必须把完整可审查内容放在 `artifactContent`。
需要 Bash 验证时，作者必须在 `testCommands` 中逐条给出精确命令。bridge 拒绝含引号、变量、
通配符、重定向、管道、命令串联或重复项的命令，只把通过校验的精确命令写入 Claude 的固定
`--allowed-tools`；任何 permission denial 都使该轮失败关闭。

## 发起与快照

两端统一调用：

```text
submit_peer(target, operation=review_repair, artifact envelope, targetRoot, allowedPaths)
await_peer(job_id, timeout_ms <= 45000)
peer_result(job_id)
```

发起前记录目标根内普通文件的相对路径、字节数、SHA-256 和 Git 状态；bridge 把完整目标根复制到
固定副本供审查者读取（排除 `.git`），并保存 baseline/result manifest。`allowedPaths` 只约束可变更
文件，不缩小可读上下文。job 终态后比较整个文件集合和全部哈希。审查者写入副本以外、作者主项目
在审查期间漂移、出现符号链接、路径穿越或 `.git` 都直接生成 `PEER_REVIEW_FAILURE_REPORT`。

同一 `artifactId + targetRoot` 使用一个固定副本和持久锁。下一轮先核对作者当前主项目，再由 bridge
刷新同一路径；不另开逻辑产物，不猜测线程。取消后只可用明确 job ID 的 `resume_peer`。
恢复必须沿用已记录的 model、reasoning effort、task profile、routing source 和 rule ID；任一缺失或
调用方试图覆盖时停止。需要换路由时建立新的 `bridge_thread_id`，不能在旧会话中切换。

## 模型解析

`taskProfile`、`model` 和 `reasoningEffort` 都可省略。bridge 按“显式模型/强度 > 显式 profile >
质量默认”解析，并把 `requested_model`、`requested_reasoning_effort`、`task_profile`、
`routing_source`、`routing_rule_id` 写入 job。调用方必须按这些解析结果验收，不能继续使用硬编码常量。

质量默认是 Claude `claude-opus-5` / `max` 和 Codex `gpt-5.6-sol` / `max`。profile 路由和依据见
[model-routing.md](model-routing.md)。`writing` 与 `creative_writing` 仍默认 Opus 5；Opus 4.6 只允许
显式选择。bridge 不改变 `target`，不提供 fallback，也不在失败时自动降档。

## Codex -> Claude

调用方可以通过公开路由字段选择白名单模型和强度，但不能传入原始 CLI 参数或覆盖工具、权限参数。
bridge 固定并验证：

```text
--model <resolved selected model>
--effort <resolved selected effort>
ask: --tools "" --permission-mode default
review_repair: --tools Read,Edit,Write,Bash --permission-mode acceptEdits
review_repair Bash: --allowed-tools 只含作者 testCommands 对应的精确 Bash(...) 项
system/init.model == resolved selected model
ask init.tools.length == 0
public result.review_model == resolved selected model
cwd and --add-dir == the fixed bridge workspace for review_repair
```

`--model`/`--effort` 缺失、重复或与解析结果不同，出现 alternate/fallback 参数，init 回执缺失或
实际模型不是所选模型，均停止；没有
fallback model。只有终态 `succeeded`、结果契约合法且模型证据精确匹配时才接受。

## Claude -> Codex

此方向也只能使用 bridge 的 `target=codex`，不直接运行 `codex exec`、旧 companion 或控制脚本。
bridge 必须记录并返回：

```text
requested model = resolved selected Codex model (default gpt-5.6-sol)
requested reasoning effort = resolved selected effort (default max)
sandbox = workspace-write
approvalPolicy = never
network = disabled
web/search = disabled
additional directories = none
requested model, requested reasoning effort, CLI version, and recorded thread ID
```

`requested_model` 或 `requested_reasoning_effort` 与本 job 的解析结果不同时停止。
SDK 没有独立运行时模型回执时，`requested_model` 仍只能表示请求参数，不能写成“已验证模型”。
`review_repair` 的 Codex 审查者可在固定副本中修复，主项目只由 allowlist、manifest、基线漂移和
哈希同步门控制。

Codex 的 `ask` 使用专用空只读目录，不以作者项目、daemon 状态、token 目录或保留 workspace 为 cwd。
SDK 的 `requested_sandbox_mode` 只证明 bridge 请求了相应模式；外层宿主仍可能进一步收紧权限，写入
是否真实生效必须由隔离材料和同步哈希证明。

Windows bridge 子进程固定 `include_environment_context=true` 和
`windows.sandbox="unelevated"`，因为只启用环境上下文仍可能被用户级 elevated sandbox 忽略 cwd；
这些参数不得改写用户全局 Codex 配置。Codex 原生补丁工具明确失败后，才允许用本地 shell 写入
固定副本中的 `allowedPaths`，其他路径仍由 manifest 与同步门拒绝。同一精确命令的所有执行事件都
保留，但终态测试证据按最后一次执行计算；后来通过只覆盖该命令此前的失败，未复测或最终失败仍
产生 `peer_contract_error`。

## 三轮与用户确认

1. 作者发起第 1 轮，保存 job ID 和 manifest。
2. `通过`：交付物进入独立验收；正式计划进入用户确认门。
3. `需修改`：作者检查同步结果并修订，更新内容、哈希、前轮 findings 和 open items，再发第 2/3 轮。
4. 第 3 轮仍需修改，或出现无法由新证据消除的冲突：停止并输出 `DISAGREEMENT_REPORT`。
5. 不发第 4 轮。计划互审通过不代表用户已授权执行。

执行和返工最多三次“返工 -> 独立验收”循环。每次不通过必须指出文件、证据和通过判据；第三次仍不
通过时停止，等待用户决定。审查通道失败不能伪装成普通验收失败。

## 同步授权

普通新增/修改在主项目基线未漂移、结果格式正确且仍在 allowlist 内时自动同步。删除、重命名、权限
变化、类型替换或整目录覆盖进入：

```text
state = needs_attention
sync_status = awaiting_user
pending_high_risk = [{ id, action, path, ... }]
```

用户明确接受完整且精确的 `pending_high_risk[].id` 集合后，才调用 `approve_peer_sync`。该调用创建
新的 `sync_request_id`，重新验证主项目 baseline 和保留副本 result manifest，然后只做原子同步，不再
唤起模型。ID 不匹配、工作区被改动、主项目漂移、超出 allowlist 或同步故障均停止；不得生成纯文本
补丁或覆盖作者的新改动。

`awaiting_user` 期间固定副本和锁继续占用目标根；任何活动任务或新的重叠目标根请求都以
`retained_workspace_conflict` 停止，直到原高风险变更被明确授权同步或按记录处理。

## 输出格式

### PLAN_REVIEW

保留五段结构以兼容既有调用：

```text
PLAN_REVIEW
结论：通过 | 需修改 | 实质分歧
已确认事项：
- ...
问题与理由：
- <问题；理由；证据或待核事实>
必须修改：
- <作者可执行的修订>
剩余风险：
- ...
```

### DELIVERABLE_REVIEW

与 `PLAN_REVIEW` 同构，但必须具体到文件、结果、测试和验收标准：

```text
DELIVERABLE_REVIEW
结论：通过 | 需修改 | 实质分歧
已确认事项：
- ...
问题与理由：
- <问题；理由；文件或证据>
必须修改：
- <作者可执行的修订>
剩余风险：
- ...
```

### DISAGREEMENT_REPORT

只整理双方已有判断和证据，不推荐折中方案：

```text
DISAGREEMENT_REPORT
产物：<artifactId / 名称>
阶段：计划复核 | 交付物复核
轮次：<1 | 2 | 3>
共识：<已确认事项>
作者判断：<角色、模型、结论、理由和证据>
审查者判断：<角色、模型、结论、理由和证据>
待用户裁决：<一个明确问题>
```

### PEER_REVIEW_FAILURE_REPORT

```text
PEER_REVIEW_FAILURE_REPORT
方向：Codex -> Claude (<selected model>) | Claude -> Codex (<selected model>)
阶段：计划复核 | 交付物复核 | 同步
jobId：<bridge job id or unavailable>
请求模型：<model or unavailable>
实际模型：<reported model or unavailable>
decisiveError：<model_mismatch | timeout | reviewer_write_detected | baseline_drift | ...>
已完成：<审查包、快照和已保留证据>
未完成：<未执行的修订、同步或验收>
恢复条件：<用户需重新提交、授权或创建新 artifactId 的条件>
```

`peer_contract_error` 属于格式/完成状态失败，不得改写成普通“需修改”。错误、失败报告和用户已裁决的分歧报告不再递归触发互审。任何模型不可用或身份不匹配都暂停，
不得选择 fallback。
