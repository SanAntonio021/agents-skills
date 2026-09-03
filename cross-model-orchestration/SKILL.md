---
name: cross-model-orchestration
description: >
  Codex Desktop/CLI 与 Claude Code VS Code 插件/CLI 的正式计划双向互审流程。正式计划或用户明确要求
  审查的已落盘交付物默认通过 claude-codex-bridge protocol v3：只传真实 projectRoot 和相对
  artifactPath，由异族模型在真实项目中使用完整工具读取、审查并可直接修改。作者复查后，只有作者
  又改过文件才追加一次对端只检查终审。没有可靠落盘路径的旧调用才使用 v2 inline zero-tool 并传正文。
  普通读取、分析、修改、测试、提交、交付和内部 Todo 不自动调用。质量默认使用
  claude-opus-5/max 与 gpt-5.6-sol/max；bridge 不换模型或降档。
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

# Codex / Claude 双向互审

## 何时触发

仅在以下情况自动进入：

- 正准备向用户提交一份需要确认后才执行的正式计划；
- 已有稳定的正式计划文件，正在进入用户确认门；
- 用户明确要求 Claude、Codex 或指定对端审查计划或交付物。

普通调研、读取、写作、代码修改、测试、提交、已确认计划的执行、内部 Todo 和简短步骤说明不自动
触发。执行和交付完成后也不自动追加审查，除非用户明确要求交付物互审。

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
5. 若 `author_modified=false`，直接把最新文件、结论和未决项交给用户。
6. 若 `author_modified=true`，使用与首轮完全相同的项目、文件、任务、验收、约束和模型字段，加上
   checkpoint 返回的 `seriesId/seriesVersion/latestJobId`，再次调用 `v3_review_peer`。这一轮对端
   只检查，不修改。
7. 终审通过、仍有问题或双方分歧都交给用户；不发第四个阶段，也不替用户裁决。

终审完成后再次调用 `v3_peer_result` 检查 `conclusion_valid`。若文件哈希后来变化，
`stale=true`，旧结论失效，不能继续作为用户确认依据。

## 权限和逐项确认

v3 默认拥有完整工具、项目规则、技能、插件、MCP 和网络能力，可直接修改真实项目。普通操作自动
执行，包括删除项目内一个普通文件。不要额外加只读、快照、文件白名单或 sandbox 限制。

以下工具名或参数中明确可见的动作进入 `awaiting_approval`：

- 批量、递归、通配符、目录或项目外删除；
- 远程删除；
- 丢弃 Git 修改；
- 清空数据库。

向用户只展示 bridge 返回的 action、完整 targets、approval ID、fingerprint 和失效时间，一次只问这
一个实际动作。用户明确批准或拒绝后，原样调用 `v3_resolve_approval`；不能删减、扩展或重写目标
清单。批准仅对该精确动作有效 24 小时；拒绝或超时取消该动作。bridge 只识别明确工具调用，不能声称
发现普通程序内部隐藏的删除。

## 重试、并发和记录

502/503/504/524 使整轮失败时，bridge 在同一 job 和会话中额外重试一次，并要求对端重读最新文件。
调用方不再额外重试、不切供应商、不换模型。同一真实 `projectRoot` 一次只运行一个 v3 修改任务；
不同项目可按 bridge 全局上限并行。

对端会话只保留到当前轮、内部重试和审批结束，随后删除。长期记录只保留清理后的任务、路径、哈希、
模型、耗时、重试、审批、结果和错误，不保存文件正文、prompt、transcript 或原始工具输出。

密码、API key、token、Cookie、session、私钥、认证头和设备登录值不得主动复制到请求说明、报告或
诊断中。若任务或模型结果意外带入，必须使用 bridge 的脱敏结果，不能转述原文。

## v2 inline 兼容

只有内容尚未落盘、没有可靠项目内路径，或旧调用方必须兼容时，才使用
`v2_review_peer author=<作者> artifactMode=inline`，传完整 `artifactContent`、UTF-8 字节数和
SHA-256。v2 inline 固定 zero-tool、只读，不代表 v3 权限。旧 v2 workspace、repair、同步、三轮 CAS
继续兼容，但新保存文件不再默认使用。

v2 调用仍按 `v2_await_peer -> v2_peer_result` 等待原 job，并只接受 bridge 的
`completion_receipt`。不要在 v3 失败后静默降级成 v2 inline，也不要为了避免审批改用旧协议。

## 用户确认和失败

计划互审完成只表示可交给用户判断，不等于执行授权。向用户说明对端是否改过、作者是否改过、最终
哈希是否有效、结论和剩余问题，然后等待用户确认。

bridge 不可达、路径无效、模型不匹配、会话清理失败、审批拒绝/过期或结果 schema 错误时，保留原
job/series 状态并直说失败边界。不要伪造通过、扫描其他 job、降低模型、另开重复任务或把 pending
写成终态。

完整字段和状态契约见 [workflow-contract.md](references/workflow-contract.md)。

## 维护与发布

修改本 Skill 后检查 `evals/evals.json`、`evals/trigger-evals.json` 和
`evals/integration-cases.md`，至少覆盖两方向路径读写、完整工具、高风险审批、作者 checkpoint、
只检查终审、哈希失效、上游重试、并发、脱敏和 v2 inline 兼容。源码推送后只对本次修改的 Skill
执行定向 CC Switch 同步，并核对 source、CC Switch、Claude、Codex 四层文件集合与 SHA-256。
