---
name: cross-model-orchestration
description: >
  Codex 与 Claude 的正式计划互审、用户明确要求的对端审查或执行，以及跨模型科研循环。
  科研循环仅在用户明确要求其他模型参与多轮科研监督、仿真或实验流水线、论文流水线、逐里程碑互审时启用。
  已落盘材料通过 claude-codex-bridge v3 在真实项目中审查并可直接修改，作者修改后只追加一次终审。
  普通分析、单次或批量仿真、论文润色、计划执行、测试、提交和交付不自动触发；单次互审不扩展成科研循环。
compatibility: >
  Requires the CC Switch-registered claude-codex-bridge MCP on the current host. Protocol v3 is the
  normal saved-file route; protocol v2 remains only for unsaved inline content and old callers.
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
`artifactContentAccepted=false`。不要调用原生 `claude -p`、`codex exec` 或旧 companion 绕过
bridge。角色端点仅兼容旧配置；新流程使用共享 `/mcp`。

## v3 请求

正式文件调用 `v3_review_peer`：

```text
author, target
projectRoot = 当前真实项目的现有绝对目录
artifactPath = projectRoot 下主文件的相对路径
artifactId = 可选稳定标识
artifactType = plan | deliverable
task
acceptanceCriteria = 非空
constraints = 可选
model = 目标侧精确模型
reasoningEffort = 可选；默认使用质量档
```

不传 `artifactContent`、文件字节数、正文哈希、文件白名单、sandbox 或工具列表。bridge 会解析
`projectRoot` 的真实路径、确认主文件存在，并在每轮自行读取和记录最新 SHA-256。
`artifactPath` 只标识主文件，不限制对端读取或修改项目中的其他内容。

如果文件不在所选真实项目根下，先把正式稿保存到项目内的明确路径。不能可靠落盘时才使用下文的
v2 inline 兼容流程；不要为了绕过 v3 路径校验猜路径、扫描“最新 Markdown”或把长文伪装进 `task`。

## 固定流程

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

## 权限与历史审批兼容

v3 默认拥有完整工具、项目规则、技能、插件、MCP 和网络能力，可直接修改真实项目。新任务不产生
桥接器审批记录，不因批量删除、目录删除等命令形式进入 `awaiting_approval`。执行模型仍按任务授权、
实际目标和文件保护规则行动；超出授权时由执行模型询问用户。不要额外加只读、快照、文件白名单或
sandbox 限制；终审仍只检查，不修改。

历史审批记录、类型及 `v3_resolve_approval` 接口保持兼容，不自动批准旧的待审批动作。若恢复旧 job，
沿用其 action、完整 targets、approval ID、fingerprint 和失效时间；用户明确决定后原样提交，不改写
目标。审批拒绝或过期本身不是 job 终态，继续查询同一 job；只有实际终态失败才按失败报告。
发布切换前等待活动任务结束，不为取消新任务审批而推进旧任务。

## 重试、并发和记录

502/503/504/524 使整轮失败时，bridge 在同一 job 和会话中额外重试一次，并要求对端重读最新文件。
调用方不再额外重试、不切供应商、不换模型。同一真实 `projectRoot` 一次只运行一个 v3 修改任务；
不同项目可按 bridge 全局上限并行。

对端会话只保留到当前轮和内部重试结束（旧任务还包括历史审批），随后删除。长期记录只保留清理后的任务、路径、哈希、
模型、耗时、重试、历史审批、结果和错误，不保存文件正文、prompt、transcript 或原始工具输出。

密码、API key、token、Cookie、session、私钥、认证头和设备登录值不得主动复制到请求说明、报告或
诊断中。若任务或模型结果意外带入，必须使用 bridge 的脱敏结果，不能转述原文。

## v2 inline 兼容

只有内容尚未落盘、没有可靠项目内路径，或旧调用方必须兼容时，才使用
`v2_review_peer author=<作者> artifactMode=inline`，传完整 `artifactContent`、UTF-8 字节数和
SHA-256。v2 inline 固定 zero-tool、只读，不代表 v3 权限。旧 v2 workspace、repair、同步、三轮 CAS
继续兼容，但新保存文件不再默认使用。

v2 调用仍按 `v2_await_peer -> v2_peer_result` 等待原 job，并只接受 bridge 的
`completion_receipt`。不要在 v3 失败后静默降级成 v2 inline，不得扩大旧协议的执行能力。

## 用户确认和失败

计划互审完成只表示可交给用户判断，不等于执行授权。向用户说明对端是否改过、作者是否改过、最终
哈希是否有效、结论和剩余问题，然后等待用户确认；已经确认当前计划时直接复用授权。确认后原作者继续正常执行和验证，不启用另一套调度器、全局锁、工作稿副本或独立返工状态机。

bridge 不可达、路径无效、模型不匹配、会话清理失败或结果 schema 错误时，保留原 job/series 状态
并直说失败边界；只暂停依赖本次审查的步骤，继续其他独立的已授权工作。用户明确改变本次互审要求时按其指令处理，不改变以后默认要求。审批拒绝或过期本身不是 job 终态；继续查询同一 job，只有它随后确实失败才按该
终态报告。不要伪造通过、扫描其他 job、降低模型、另开重复任务或把 pending 写成终态。

完整字段和状态契约见 [workflow-contract.md](references/workflow-contract.md)。

## 维护与发布

修改本 Skill 后检查 `evals/evals.json`、`evals/trigger-evals.json` 和
`evals/integration-cases.md`，至少覆盖两方向路径读写、完整工具、新任务无额外审批、历史审批兼容、作者 checkpoint、
只检查终审、主模型收尾、哈希失效、上游重试、并发、脱敏和 v2 inline 兼容。源码推送后只对本次修改的 Skill
执行定向 CC Switch 同步，并核对 source、CC Switch、Claude、Codex 四层文件集合与 SHA-256。


旧执行器的历史计划、状态、哈希、job ID、回执和锁留在原处，不自动迁移或清理。维护时若发现活动旧 run，只暂缓其退役，不清锁、不重复提交；恢复当前 bridge 任务仍使用原 job/series。
