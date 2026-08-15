---
name: cross-model-orchestration
description: >
  Codex Desktop/CLI 与 Claude Code CLI 的全局双向互审流程。除纯聊天、简单解释和一条
  明确只读命令外，任何需要阅读本地材料、制定正式计划、形成重要结论、修改文件、运行命令、
  调研、比较、写作或多步骤推进的任务都自动使用同一个 claude-codex-bridge MCP，把产物交给
  对方模型在固定副本中审查、修复和测试。Claude 方向固定使用 claude-opus-5；Codex 方向记录
  SDK 请求模型但不伪造运行时身份。失败、超时、模型不匹配、越界写入或同步冲突必须暂停。
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

把跨模型复核变成所有符合条件的实质任务的默认质量门。作者负责计划、交付和返工；对方模型
在 bridge 创建的固定副本中检查、允许范围内修复并运行测试。审查者不能直接写作者主项目，
作者必须检查 bridge 同步后的主项目状态。

以下任一情况自动进入：

- 需要读取、检查、合并或比较本地材料；
- 需要正式计划、重要结论、调研、写作、代码、文档、报告、仿真或多步骤命令；
- 已经产出重要交付物，准备执行、提交或交付。

以下情况跳过：纯聊天、不依赖材料的简单解释、一条明确只读且无需分析后续结果的命令。
边界不清时进入互审。审查报告、失败报告和用户已裁决的分歧报告不递归触发。

`ExitPlanMode` 的拒绝理由只是 Claude 表达“先审查计划”的一种方式，不是唯一触发器，也不是
可信的计划路径来源。没有可靠路径时，使用稳定 `artifactName` 和完整 `artifactContent`，
绝不猜测“最新计划”。

## 统一入口

两端都使用同一个 MCP，不调用旧插件、未登记命令或隐藏 Hook：

| 当前作者 | `submit_peer.target` | 固定审查/执行通道 |
| --- | --- | --- |
| Codex Desktop / Codex CLI | `claude` | bridge 启动并验证 `claude-opus-5` |
| Claude Code CLI | `codex` | bridge 的 `@openai/codex-sdk` 适配器 |

调用顺序固定为 `submit_peer` -> `await_peer`（单次最多 45 秒）-> `peer_result`；需要状态时用
`peer_status`，取消用 `cancel_peer`，恢复只用指定 job 的 `resume_peer`。不得扫描最新线程，
不得用 `codex exec`、`claude -p` 或 `codex@openai-codex` 绕过 bridge。兼容的 Claude 命名工具
仍可用，但新流程优先使用对称工具。仓库中保留的 `orchestration-control.mjs` 与
`check-resume-candidate.mjs` 只用于历史状态测试；没有显式归档诊断标志时直接失败关闭，不读取旧插件注册表。

`review_repair` 是一次完整调用：对方在固定副本中审查、修复、运行测试并返回结构化结论和变更
元数据。`ask` 只读；`task` 只有在明确允许写副本时使用。`reviewerAccess` 与操作必须一致：
`ask` 为 `read_only`，`review_repair` 为 `isolated_write`。任何写入都不能越过 `targetRoot`、
`allowedPaths` 或副本边界。

Codex 方向的 `ask` 使用 bridge 专用的空只读目录，不把作者项目、daemon 状态、token 或保留 job
副本暴露为 cwd。需要读取项目材料时不要伪装成 `ask`，应构造完整审查包并使用受控固定副本。

## 审查包

每一轮先读取 [workflow-contract.md](references/workflow-contract.md)，再构造完整审查包：

```text
artifactId: 同一逻辑产物跨轮不变
artifactType: plan | deliverable
author / reviewer: 实际角色和模型
round: 1 | 2 | 3
maxRounds: 3
artifactName 或受控 artifactPath
artifactBytes 和 artifactSha256
artifactContent: 对无工具审查者足够的全文、证据和上下文
priorRounds / priorFindings / openItems
acceptanceCriteria / constraints
testCommands: 需要 Bash 验证时逐条给出精确命令；不得含引号、变量、通配符、重定向、管道或命令串联
reviewerAccess: read_only | isolated_write
```

文件型交付物还要给出目标根和最小文件级 `allowedPaths`。bridge 会把目标根的完整上下文复制到
固定副本并排除 `.git`，供审查者读取；`allowedPaths` 限制的是可变更文件，不是可读上下文。发起前
记录普通文件相对路径、字节数、SHA-256 和 Git 状态；发起后比较整个集合和全部哈希。主项目基线漂移、审查副本越界写入、符号
链接、路径穿越、`.git` 或结果哈希不一致都使该轮失败。

## 三轮状态机

1. 作者用同一 `artifactId` 发起第 1 轮 `review_repair`，保存 job ID、基线 manifest 和结果 manifest。
2. 只接受终态 `succeeded`、契约合法且方向/模型/权限证据匹配的结果；作者检查同步后的主项目。
3. `通过`：交付物进入验收；正式计划进入用户确认门。
4. `需修改`：作者确认同步内容，修订主项目，更新字节数、SHA-256、`priorFindings` 和 `openItems`，
   然后发第 2 或第 3 轮。不要另开逻辑产物或猜测新线程。
5. 第 3 轮仍需修改，或双方出现实质分歧：输出 `DISAGREEMENT_REPORT`，等待用户裁决，不发第 4 轮。

审查通道不可用、超时、取消、认证/权限/sandbox 错误、格式错误、模型缺失或模型不匹配都不是
“需修改”，直接输出 `PEER_REVIEW_FAILURE_REPORT` 并暂停；不换模型、不静默跳过、不回退。bridge
还会在同步前拒绝缺少对应审查标记/结论、明确 blocked/incomplete，或把失败测试/未满足验收写成“通过”的
`review_repair` 结果，并使用 `peer_contract_error` 记录原因。

## 模型与权限验收

Codex -> Claude 方向只接受：

```text
target = claude
operation = review_repair 或 ask
requested model = claude-opus-5（由 bridge 固定，不由调用方覆盖）
read-only ask: --tools "" --permission-mode default
review_repair: Read,Edit,Write,Bash + acceptEdits，cwd/--add-dir 仅为固定副本
public review_model = claude-opus-5
```

`system/init.model` 缺失或不是 `claude-opus-5`、工具列表不符合操作、出现 fallback 参数或
结果未报告精确模型时停止。`review_repair` 的 Bash 不做通配授权；bridge 只把作者在
`testCommands` 中逐条给出的安全精确命令写入固定 `--allowed-tools`。命令被拒绝本身就是失败证据，
即使模型随后写“通过”也不得同步。Opus 5 无工具的 `ask` 审查必须把完整内容放进 `artifactContent`。

Claude -> Codex 方向只接受 bridge 返回的 SDK 记录：`workspace-write`、`approvalPolicy=never`、
网络和搜索关闭、无额外目录；记录请求模型、CLI 版本和线程 ID，但没有运行时回执时不得把模型
身份写成“已验证”。固定副本中的 `review_repair` 允许对方修复，主项目同步仍由 allowlist、manifest、
基线漂移和逐文件哈希门控制。

Windows 下 bridge 子进程还固定 `include_environment_context=true` 与
`windows.sandbox="unelevated"`；两者共同保证命令工具实际使用固定副本 cwd，且不修改用户全局
Codex 配置。Codex 先用原生补丁工具；只有该工具明确写入失败后，才可用本地 shell 写入固定副本中的
`allowedPaths`。同一精确测试命令多次执行时，受保护事件保留全部尝试，但验收按最后一次状态判断：
后来通过只清除该命令此前的失败，未复测或最后仍失败继续停止同步。

## 同步与用户授权

普通新增/修改在基线未漂移且仍在 allowlist 内时由 bridge 使用同卷 staging、备份、原子替换、
逐文件哈希复核和逆序回滚自动同步。删除、重命名、权限变化、类型替换或整目录变化进入
`needs_attention`/`sync_status=awaiting_user`，列出稳定 `pending_high_risk[].id`。

只有用户明确接受完整且精确的 ID 集合后，才调用 `approve_peer_sync`。它创建新的同步请求 ID，
重新检查主项目基线和保留副本结果，不再调用任何模型；ID 缺失、多余、过期或基线漂移均失败关闭。
不能用授权扩大 `allowedPaths`，也不能授权覆盖作者在审查期间产生的新改动。
待授权期间固定副本和持久锁继续保留；任何重叠目标根的新任务必须以
`retained_workspace_conflict` 失败，不能用另一个 `artifactId` 绕过待处理变更。

正式计划互审通过不等于执行授权。作者必须向用户展示最终计划、轮次结论、已解决项和剩余风险，
获得明确确认后才执行。执行作者仍需做独立验收；重要交付物在交付前再次走相反方向的互审。

## 失败与发布

`PEER_REVIEW_FAILURE_REPORT` 至少包含方向、阶段、请求/实际模型、job ID、决定性错误、已完成内容、
未完成范围和恢复条件。`DISAGREEMENT_REPORT` 只整理双方已有判断和证据，不替用户选折中方案。

不要使用 `--yolo`、`--dangerously-skip-permissions`、直接改 `.cc-switch`/`.claude`/`.codex` 或
数据库。旧 `codex@openai-codex` 源码、许可证和测试可以留作行为参考，但不得作为运行时前置条件。

修改本 Skill 后，至少检查 `evals/evals.json`、`evals/trigger-evals.json`、`evals/integration-cases.md`，
覆盖两方向自动触发、简单任务跳过、`review_repair` 一次修复、只读/隔离写边界、三轮上限、用户确认
门、审批同步、通道不可用和非 Opus 5 停止。源码推送后，只对本次改动的 Skill 使用定向 CC Switch
同步，并核对源码、CC Switch、Claude、Codex 四层文件集合和 SHA-256。
