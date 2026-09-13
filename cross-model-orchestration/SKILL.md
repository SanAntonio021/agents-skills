---
name: cross-model-orchestration
description: >
  Codex 与 Claude 的正式计划互审、用户明确要求的对端审查或执行，以及跨模型科研循环。
  科研循环仅在用户明确要求其他模型参与多轮科研监督、仿真或实验流水线、论文流水线、逐里程碑互审时启用。
  文件与消息材料统一通过 claude-codex-bridge v3；消息单轮交流，文件审查可直接修改，作者修改后只追加一次终审。
  普通分析、单次或批量仿真、论文润色、计划执行、测试、提交和交付不自动触发；单次互审不扩展成科研循环。
compatibility: >
  Requires the CC Switch-registered claude-codex-bridge MCP on the current host. Protocol v3 is the
  normal file and message route; protocol v2 remains only for explicitly requested legacy callers.
allowed-tools:
  - Read
  - Glob
  - Grep
  - Bash
  - AskUserQuestion
  - Agent
---

# Codex / Claude 互审与科研循环

## 适用范围

正式计划的触发条件以共享全局规则为准。用户明确要求对端审查或执行时使用本技能；普通业务不自动进入。

单次互审按下文处理。只有用户明确要求其他模型参与科研监督、流水线或逐里程碑互审时，才读取
[科研循环](references/research-loop.md)，复用同一套协议；不为普通任务加载科研检查清单。

## 统一入口和方向

两端使用共享 MCP `http://127.0.0.1:43123/mcp` 与
`CLAUDE_CODEX_BRIDGE_TOKEN`。共享 token 只认证本机访问，`author` 是调用方声明：

| 原作者 | `author` | `target` | 默认模型 |
| --- | --- | --- | --- |
| Codex | `codex` | `claude` | `claude-opus-5/max` |
| Claude | `claude` | `codex` | `gpt-5.6-sol/max` |

先调用 `v3_peer_status`，要求 `active=true`、`fullNativeTools=true`、
`realProjectCwd=true`、`directProjectWrites=true` 和
`artifactContentAccepted=true`。不要调用原生 `claude -p`、`codex exec` 或旧 companion 绕过
bridge。角色端点仅兼容旧配置；新流程使用共享 `/mcp`。

## v3 请求

文件与消息均调用 `v3_review_peer`：

```text
author, target
projectRoot = 当前真实项目的现有绝对目录
artifactPath = 可选；projectRoot 下现有主文件的相对路径
artifactContent = 可选；直接传入的材料正文
context = 可选；补充上下文
artifactId = 可选稳定标识
artifactType = plan | deliverable；默认 deliverable
task
acceptanceCriteria = 可选；省略或空数组均可
constraints = 可选
model = 目标侧精确模型
reasoningEffort = 可选；默认使用质量档
```

`author`、`target`、`projectRoot`、`task`、`model` 仍必填。不传文件字节数、正文哈希、文件白名单、
sandbox 或工具列表。提供 `artifactPath` 时走 file 分支：bridge 解析真实项目、确认主文件存在，
自行读取和记录最新 SHA-256；`artifactContent/context` 可作为补充，但不替代磁盘文件。
`artifactPath` 只标识主文件，不限制对端读取或修改项目中的其他内容。

省略 `artifactPath` 时走 message 分支，直接传 `artifactContent/context`，也可只提供完整 `task`。
消息只交流一轮，不为满足桥格式建文件，不生成主文件哈希、不调用 checkpoint、不追加终审。
若提供了无效路径，应修正本次请求，不能悄悄改成消息模式。未落盘内容默认使用 v3，不回退 v2。

## 文件流程

1. 原作者先完成可审查的落盘文件，再提交 `v3_review_peer`。
2. 在当前任务中循环 `v3_await_peer(job_id, timeout_ms<=45000)`，并用
   `v3_peer_result(job_id)` 读取最新状态。单次等待超时只是 pending，不另开 job。
3. 首轮对端使用完整原生工具读取真实项目、审查并可直接修改。终态必须记录精确请求模型；模型回执
   缺失或不匹配按失败处理。
4. 原作者重新读取最新文件和 review 结果，检查对端改动，并可自行修改。完成后用首轮返回的
   `series_id`、`series_version` 和 `latest_job_id` 调用 `v3_author_checkpoint`。
5. 若 `author_modified=false`，不再调用模型，交付最新文件、结论和未决项；科研里程碑按科研分支判断是否继续。
6. 若 `author_modified=true`，使用与首轮完全相同的项目、文件、任务、验收、约束和模型字段，加上
   checkpoint 返回的 `seriesId/seriesVersion/latestJobId`，再次调用 `v3_review_peer`。这一轮对端
   只检查，不修改。
7. 终审后原作者重读最新文件和结果，依据证据采纳、修正或不采纳意见，并完成相关验证。小问题和
   技术分歧自行处理；只有目标、范围或重要取舍需要用户决定时暂停依赖步骤。保留现有轮次，
   不追加对端轮次，也不另开 series 绕过终审。科研里程碑按科研分支判断是否继续。

终审完成后再次调用 `v3_peer_result` 检查 `conclusion_valid`。若文件哈希后来变化，
`stale=true`，旧结论失效，不能继续作为用户确认依据。分别报告“对端结论”和“主模型修正及验证结果”；
主模型修正后不得把旧结论写成对端对最新文件通过。验证失败如实保留，不强行宣布完成。

## 自由回复与消息收尾

两分支均接受中文、Markdown、代码块和不完整 JSON；不要求对端使用固定字段，不为格式问题返工、
重试、补建文件或询问审批。bridge 返回清理后的完整 `responseText` 和 `interpretationRequired`；
可提取的结构化结论仅作兼容信息。主模型必须阅读回复、判断实际意见并核对证据，交互 `succeeded`
不等于审查通过，不能凭“通过”字样或缺少字段自动补造 pass。

message 在同一 job 等待终态后直接收尾，没有文件结论有效性承诺；file 仍按上述 checkpoint 和
哈希规则收尾。格式宽松不改变模型回执、真实上游失败、空回复、权限和会话清理的验证边界。

## 权限与历史审批兼容

v3 默认拥有完整工具、项目规则、技能、插件、MCP 和网络能力，可直接修改真实项目。新任务不产生
桥接器审批记录，不因批量删除、目录删除等命令形式进入 `awaiting_approval`。执行模型仍按任务授权、
实际目标和文件保护规则行动；超出授权时由执行模型询问用户。不要额外加只读、快照、文件白名单或
sandbox 限制；终审仍只检查，不修改。

历史审批记录、类型及 `v3_resolve_approval` 接口保持兼容，不自动批准旧的待审批动作。沿用其 action、
完整 targets、approval ID、fingerprint 和失效时间；用户明确决定后原样提交，不改写目标。
迁移后明确 resolve 只在 schema 4 记录中保存决策，不恢复旧任务执行；切换前旧 daemon 的审批拒绝或
过期本身不是 job 终态，继续查询同一 job，只有实际终态失败才按失败报告。
发布切换前等待活动任务结束，不为取消新任务审批而推进旧任务。
新版读取或迁移 schema 3 不改写原存储；允许显式 resolve 迁移后的历史审批，但不恢复旧活动 job。

## 重试、并发和记录

502/503/504/524 使整轮失败时，bridge 在同一 job 和会话中额外重试一次，并要求对端重读最新文件。
调用方不再额外重试、不切供应商、不换模型。同一真实 `projectRoot` 一次只运行一个 v3 修改任务；
不同项目可按 bridge 全局上限并行。

对端会话只保留到当前轮和内部重试结束（旧任务还包括历史审批），随后删除。长期记录可保留清理后的
输入元数据、路径、哈希、模型、耗时、重试、历史审批、结果和错误，以及完整最终回复（可含正文、代码或修订稿）。
新输入 `task/acceptanceCriteria/constraints/artifactContent/context` 的正文只在当前会话使用，长期只存
`inputMetadata`；完整 prompt、transcript、原始工具参数和输出不长期留存，旧记录原样保留。

密码、API key、token、Cookie、session、私钥、认证头和设备登录值不得主动复制到请求说明、报告或
诊断中。若任务或模型结果意外带入，必须使用 bridge 的脱敏结果，不能转述原文。
只遮盖真实凭据或明确认证值，不因 `session`、`token` 等普通词或字段名遮掉技术论述、路径、公式和代码；
普通字段和最终回复不静默截断。总请求与输出资源上限仍有效，超限明确失败。

新 v3 持久化使用独立 schema 4 存储。旧 schema 3 记录只读保留，可读取、展示或显式迁移至新存储，
不原地改写，不恢复旧活动任务，不自动批准历史动作。协议名称和工具前缀仍为 v3。

## v2 inline 兼容

只有用户明确指定旧协议，或旧调用方必须兼容时，才使用
`v2_review_peer author=<作者> artifactMode=inline`，传完整 `artifactContent`、UTF-8 字节数和
SHA-256。v2 inline 固定 zero-tool、只读，不代表 v3 权限。旧 v2 workspace、repair、同步、三轮 CAS
继续兼容，但新保存文件不再默认使用。

v2 调用仍按 `v2_await_peer -> v2_peer_result` 等待原 job，并只接受 bridge 的
`completion_receipt`。不要在 v3 失败后静默降级成 v2 inline，不得扩大旧协议的执行能力。

## 用户确认和失败

计划互审完成只表示可交给用户判断，不等于执行授权。向用户说明对端是否改过、作者是否改过、最终
file 哈希是否有效（message 不适用）、结论和剩余问题，然后等待用户确认；已经确认当前计划时直接复用授权。确认后原作者继续正常执行和验证，不启用另一套调度器、全局锁、工作稿副本或独立返工状态机。

bridge 不可达、路径无效、模型不匹配、会话清理失败或真实运行错误时，保留原 job/series 状态
并直说失败边界；只暂停依赖本次审查的步骤，继续其他独立的已授权工作。用户明确改变本次互审要求时按其指令处理，不改变以后默认要求。审批拒绝或过期本身不是 job 终态；继续查询同一 job，只有它随后确实失败才按该
终态报告。不要伪造通过、扫描其他 job、降低模型、另开重复任务或把 pending 写成终态。

完整字段和状态契约见 [workflow-contract.md](references/workflow-contract.md)。

## 维护与发布

修改本 Skill 后检查 `evals/evals.json`、`evals/trigger-evals.json` 和
`evals/integration-cases.md`，至少覆盖两方向路径读写、完整工具、新任务无额外审批、历史审批兼容、作者 checkpoint、
只检查终审、消息单轮、自由回复不伪造通过、主模型收尾、哈希失效、上游重试、并发、精准脱敏、完整最终回复、
输入不留存、schema 4 与旧 schema 3 隔离和 v2 inline 兼容。源码推送后只对本次修改的 Skill
执行定向 CC Switch 同步，并核对 source、CC Switch、Claude、Codex 四层文件集合与 SHA-256。


旧执行器的历史计划、状态、哈希、job ID、回执和锁留在原处，不自动迁移或清理。维护时若发现活动旧 run，只暂缓其退役，不清锁、不重复提交；恢复当前 bridge 任务仍使用原 job/series。
