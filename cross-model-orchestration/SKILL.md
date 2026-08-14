---
name: cross-model-orchestration
description: >
  Codex Desktop/CLI 与 Claude Code CLI 的全局双向互审流程。除纯聊天、简单解释和一条
  明确只读命令外，任何需要阅读或检查本地材料、制定正式计划、形成重要结论、修改文件、
  运行命令、调研、比较、写作或多步骤推进的任务都自动使用。Codex 产物由固定的 Claude
  Opus 5 只读审查；Claude 产物由 Codex 只读审查。审查失败、超时、模型不匹配或宿主没有
  已验证通道时必须暂停报告，不能静默降级或跳过。
compatibility: >
  Codex Desktop/CLI requires the CC Switch-registered claude-codex-bridge MCP. Claude Code CLI
  requires codex@openai-codex, an authenticated Codex CLI, and this Skill's precise companion
  permissions. Claude Desktop/Cowork has no verified peer-review route in this workflow.
allowed-tools:
  - Read
  - Glob
  - Grep
  - Bash
  - AskUserQuestion
  - Agent
---

# Codex / Claude 双向互审

## 目标

把跨模型复核变成所有符合条件的未来实质任务的默认质量门：作者负责计划、交付和返工，
审查者只检查，不代写、不改文件。不要把模型之间的转述、完成声明或旧日志当成证据。

本 Skill 不依赖 `ExitPlanMode`、拒绝理由或关键词触发。用户明确说“审查计划”时当然进入，
但符合范围的任务即使没有这句话也自动进入。

## 何时进入

以下任一情况进入：

- 需要读取、检查、合并或比较本地材料；
- 需要制定正式计划、形成重要结论、调研、写作、修改文件或运行命令；
- 需要多步骤推进、审计、复核、仿真、维护 Skill 或完成项目交付物；
- 已经产出正式计划、重要结论、代码、文档、报告或其他重要交付物，准备交付或执行。

以下情况跳过：

- 纯聊天；
- 不依赖材料的简单解释；
- 一条明确、只读、无需分析后续结果的命令。

若边界不清，进入互审。不要为了省一次调用把实质任务归类成简单任务。

审查报告本身、一次失败报告和用户已经裁决的分歧报告不再递归触发审查。

## 宿主与方向

| 作者所在宿主 | 作者 | 只读审查者 | 已验证通道 |
| --- | --- | --- | --- |
| Codex Desktop / Codex CLI | Codex | Claude Opus 5 | `claude-codex-bridge` MCP |
| Claude Code CLI | Claude | Codex | `codex@openai-codex` companion |
| Claude Code CLI 派发的 Codex 执行任务 | Codex | Claude Opus 5 | Codex 已注册的 bridge MCP |
| Claude Desktop / Cowork 或其他未验证宿主 | 当前作者 | 无 | 停止并输出失败报告 |

不要把“当前主会话是 Claude Code CLI”误当作唯一入口。Codex Desktop/CLI 的实质任务同样
自动进入。反过来，Claude Desktop/Cowork 没有已验证通道时也不得假装已经互审，或私下用
未登记的命令绕过宿主边界。

## Claude 计划模式入口

Claude Code 的 `ExitPlanMode` 权限对话框不是本 Skill 可订阅的 hook，也不能把拒绝理由当作未记录的
环境变量或工具参数。用户在该对话框拒绝并写出“让 Codex 审查计划”“审计计划”或同义请求时，Claude
把这条理由当作普通、明确的互审请求，立即走本 Skill 已有的正式计划审查状态机。

这只是方便用户表达当前意图的入口，不是关键词唯一触发器：任何符合“何时进入”的正式计划本来就要
互审。不要维护一个容易漂移的关键词白名单，也不要假设可以从 `ExitPlanMode` 调用隐式取得计划路径。
审查包的 `artifactPath` 由作者明确填写；没有可靠文件路径时使用稳定 `artifactName` 和完整
`artifactContent`，而不是猜测路径或执行。

## 作者与审查者边界

- 作者维护同一个 `artifactId`，根据审查意见更新产物、证据和 SHA-256。
- 审查者只读。审查阶段没有写权限、没有执行计划的权限，也不替作者修文件。
- Codex 的执行或返工阶段可以有写权限，但那是作者执行，不是审查；其重要产物仍要在交付前
  走 Codex -> Opus 5 的只读审查。
- 正式计划即使通过互审，也只表示“可以请求执行授权”。展示最终计划、已解决意见和剩余风险，
  等用户明确确认后才执行。

## 审查包与快照

在每一轮发起前，作者先读取
[workflow-contract.md](references/workflow-contract.md)，生成可审计的审查包。审查包必须有：

```text
artifactId: 同一逻辑产物跨轮不变
artifactType: plan | deliverable
author / reviewer: 实际角色和模型
round: 1 | 2 | 3
maxRounds: 3
artifactName 或受控路径
artifactBytes 和 artifactSha256
可审查的全文或完整、可定位的内容
前轮 findings、仍未解决项、验收标准和限制
reviewerAccess: read_only
```

对于 Codex -> Opus 5，必须把足够的全文、证据和上下文放进包中；Opus 5 的 bridge 会强制
空工具，不能把“请自行读文件”当作审查输入。对于 Claude -> Codex，仍给出完整包和文件定位，
但 Codex 只可读取包中允许的材料。

审查前记录审查范围内每个普通文件的相对路径、字节数和 SHA-256；Git 项目再记录 Git 状态。
审查后逐项比较文件集合和内容，不能只看 `git status`。任何意外写入都使该轮结果无效，按
`PEER_REVIEW_FAILURE_REPORT` 停止；作者不得回滚审查者的写入后继续接受该结果。

同一 `artifactId` 同时只能有一轮活动审查。已有 job 未到终态时只能轮询它，不能重发、另开
新 job 或把新会话当作续接。Claude -> Codex 方向必须由 `orchestration-control.mjs` 取得按目标
路径的互斥声明；它在 `CLAUDE_PLUGIN_DATA/orchestration/claims.json` 中记录 `phase`、`artifactId`、
`artifactSha256`、`round`、`jobId` 和目标根。该文件只由脚本维护，作者只读 `active` 查询状态。
每一轮都使用新的、可追溯的审查 job；不要使用不可靠的 `--resume` 或 `--resume-last` 猜测上下文。

## 三轮状态机

1. 作者发起第 1 轮只读审查，并保存审查包、快照和 job ID。
2. 审查者必须按 `PLAN_REVIEW` 或 `DELIVERABLE_REVIEW` 返回结构化结果。
3. `通过`：计划进入用户确认门；交付物进入独立验收或交付。
4. `需修改`：作者修订产物，更新 SHA-256、前轮 findings 和未解决项，再发下一轮。
5. `实质分歧`：立即输出 `DISAGREEMENT_REPORT`，等待用户裁决。
6. 第 3 轮仍为 `需修改`：不发第 4 轮，输出 `DISAGREEMENT_REPORT`，说明最后意见、已完成
   修订和需要用户决定的一个问题。

格式错误、审查者写入、通道不可用、认证/权限/sandbox/运行时错误、超时、取消、模型缺失或
不匹配都不是“需修改”。这些情况直接输出 `PEER_REVIEW_FAILURE_REPORT` 并暂停。不得重试、
换模型、换审查者或由当前作者假称审查已通过。

## Codex -> Claude Opus 5

只在 Codex Desktop/CLI 或已经获得 Codex MCP 的 Codex 执行任务中进行。先确认 MCP 有且仅按
现有名称提供 `submit_claude`、`await_claude`、`claude_result`、`bridge_status` 和
`cancel_bridge_job`；不改工具名，不直接编辑 `.cc-switch`、`.codex`、`.claude` 或数据库。

1. 用 `submit_claude` 提交审查包。只使用 `route: "headless"`，不传模型、工具或权限参数。
   模型锁定属于 bridge：它固定启动 `--model claude-opus-5 --tools "" --permission-mode default`。
2. 用 `await_claude` 轮询现有 job；45 秒未完成时用 `claude_result` 查询同一 job，不新建请求。
3. 仅当终态是 `succeeded`、审查正文满足对应契约，且公共结果 `review_model` **精确等于**
   `claude-opus-5` 时，才接受该轮。
4. `review_model` 缺失、不同、bridge 返回 `model_mismatch`、任何失败或超时，记录 expected model、
   reported model 和 job ID，输出失败报告并暂停。不存在 fallback model。

Opus 5 只收到审查包，不能使用工具；它不是执行者。作者 Codex 根据意见进行下一轮修改，随后
重新构造完整包。不要让 Opus 5 直接改文件，也不要把“它说可以改”解释成写权限。

## Claude -> Codex

只在 Claude Code CLI 中进行。先确认 `codex@openai-codex` 已启用、Codex CLI 已登录、启动 cwd
覆盖全部目标路径，并读取本 Skill 的 `workflow-contract.md`。Claude Desktop/Cowork 的 Agent
不注册这个 companion；这不是许可去调用未登记的本地命令，而是失败关闭。

启动前还要确认 Claude 的权威权限配置允许本 Skill 的 `orchestration-control.mjs` 和它启动的
`codex@openai-codex` companion；cc-switch 环境只改其权威配置来源，绝不手改 `.claude/settings.json`
运行时副本。共同 cwd 必须覆盖全部目标根。以上任一项不成立时输出 `PEER_REVIEW_FAILURE_REPORT`，
不得用旧的直接 companion 命令绕过控制器。

审查调用必须由控制脚本启动，带 `--review` 且不得带 `--write`。脚本会校验完整审查包、拒绝第 4 轮、
锁住重叠目标根，并在活动声明中持久化轮次、计划/交付物哈希和 job ID：

```bash
node "$USERPROFILE/.claude/skills/cross-model-orchestration/scripts/orchestration-control.mjs" launch --review --cwd "<共同祖先目录>" --target-roots "<逗号分隔的受控目标根>" "<含完整 ```json 审查包的单行只读提示词>"
```

启动后以返回的 `ownerToken` 和 `jobId` 先运行 `verify-request --review`，校验传输的 prompt 字节数、
SHA-256 与审查包未被改写；随后只轮询 `status <jobId>`，再用 `result <jobId>` 的 `rendered` 字段读取
正文，不以 `.log` 兜底。job 到终态后运行 `candidate`，完成前后快照对比后再以匹配的 job ID 运行
`release --owner-token`；控制器会再次验证 job 已到终态才释放声明。
前后快照完全一致且输出符合 `PLAN_REVIEW`/`DELIVERABLE_REVIEW` 才接受。控制脚本、权限、锁、包校验或
状态查询失败均为 `PEER_REVIEW_FAILURE_REPORT`，不能退回为直接 companion 调用。Claude 是作者时由
Claude 修订计划、文本或其授权范围内的产物；Codex 审查者不改文件。

如果后续用户确认执行，Codex 才作为执行作者以 `--background --fresh --write` 接手明确授权的
范围。执行 prompt 必须要求 Codex 在返回每个重要产物前使用其已注册的 bridge MCP 取得 Opus 5
只读审查，并把 `review_model: claude-opus-5`、轮次和对应审查结果带回。bridge 不可用时停止，
不能把 Claude 的验收当成 Opus 5 的替代品。

## 正式计划、执行与验收

正式计划必须先完成上述三轮以内的互审，再向用户展示：最终计划、每轮结论、已解决项、剩余风险
和明确的执行范围。只有用户明确确认后，执行作者才可以写入、运行命令或生成交付物。

执行后，作者或独立验收者仍须核验实际文件、命令、测试、Git 提交和验收标准。对已经提交的
改动，空 `git diff` 不能代替 `git show --stat <commit>`、目标文件内容、远端祖先关系和本轮测试
证据。重要交付物在最终交付前必须进入对应方向的 `DELIVERABLE_REVIEW`；验收者只读，不自行修补。

执行返工只在执行作者已成功运行且独立验收发现明确不通过项时发生。返工 prompt 写出问题、证据、
通过判据和允许修改范围；完成后重新验收并重新审查新的重要交付物。同一确认计划最多三次
“返工 -> 独立验收”循环；第三次仍不通过时停止，报告未满足的验收标准、证据和未完成范围，等待用户
决定。审查通道失败不能伪装成普通验收不通过，也不能进入无限返工循环。

## 失败、分歧与安全

- `PEER_REVIEW_FAILURE_REPORT` 同时覆盖 Codex -> Opus 5 和 Claude -> Codex；保留既有
  `CODEX_FAILURE_REPORT` 兼容执行阶段的历史调用。格式见参考契约。
- `DISAGREEMENT_REPORT` 只整理作者和实际审查者已有的判断、理由和证据，不替用户选方案、
  不新增未经双方评估的折中方案。
- 不用 `--yolo`、`--dangerously-skip-permissions` 或其他绕过权限的参数。
- 删除、覆盖、重置、权限变更、付费、对外发送、硬件操作和会丢失既有内容的整文件替换，仍按
  项目规则征得用户同意；互审通过不扩大这些授权。
- 审查包、快照和失败报告只记录必要的内容、路径、哈希和错误；bridge 的原始 prompt/结果继续
  留在受保护 job detail，不写入普通审计日志或 Git。

## 评测与发布

修改本 Skill 后，读取 `evals/evals.json`、`evals/trigger-evals.json` 和
`evals/integration-cases.md`，至少覆盖两条方向、简单任务跳过、只读快照、三轮上限、用户确认门、
bridge 不可用和非 Opus 5 模型停止。运行本 Skill 的 focused control tests 与 JSON 校验。

Skill 源码推送后，只用 `Invoke-CcSwitchSkillSync.ps1` 定向同步本次实际改动的 Skill，并用同一
个 40 位远端提交 SHA 验证源码、CC Switch、Claude、Codex 四层文件集合和 SHA-256。不得直接
改运行时副本、CC Switch 数据库或其他客户端配置。
