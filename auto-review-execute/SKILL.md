---
name: auto-review-execute
description: >
  在 Claude Code VS Code 插件或 CLI 中把已退出 Plan Mode 的明确计划交给统一 claude-codex-bridge MCP，由 Codex
  按本地计划文件路径进行只读审查，最多三轮；Claude 根据审查意见修改计划、验收回执、向用户展示
  最终计划，并在用户
  明确确认后按 allowlist 执行。默认跨模型复核只发生在正式计划阶段；执行结果由 Claude 按验收
  标准检查，不自动再次调用 Codex。Claude 作者任务在同一回合等待回执、修订并继续下一轮，不需要
  Codex Desktop continuation；只有任务退出后的宿主级唤醒目前不适用于 Claude。不能把 Codex 的审查
  意见未经作者验收直接写入 Claude 主项目。缺少明确计划路径、MCP、用户确认或完整验收证据时停止，
  不猜测路径、不调用旧 codex@openai-codex 插件。
compatibility: Requires Windows, Node.js 24+, the CC Switch-registered claude-codex-bridge MCP, and the sibling cross-model-orchestration skill. Legacy orchestration scripts are offline state helpers only.
---

# Auto Review Execute

## 目标和边界

本 Skill 只在 Claude Code VS Code 插件或 CLI 主会话中运行。Claude 是作者和最终验收者；Codex 是 bridge
调度的隔离审查者。正式计划已有明确路径，因此默认使用 workspace 只读审查：只传文件路径、字节数
和哈希，不把整篇正文塞进 MCP 请求，也不写入主项目。审查通过仍不等于执行授权。

旧 `codex@openai-codex` companion、`orchestration-control.mjs` claim 和隐藏 Hook 不再是运行时入口。
保留的 Node 脚本维护本地状态、快照和用户确认哈希。正式计划互审必须由当前 Claude 作者任务直接
使用共享 MCP 的 `v2_*` 工具；旧 bridge CLI 适配器只保留给已有运行状态和显式执行任务兼容，不再作为
正式计划互审入口。

运行根目录为 `%LOCALAPPDATA%\auto-review-execute\<runId>\`：

```text
plan-original.md / plan-working.md / plan-final.md
state.json / run.lock
round-<n>/review-input/plan-working.md (本轮只读快照)
round-<n>/ (审查包、快照、结果)
execution/ 或 rework-attempt-<n>/
```

## 入口与计划路径

只接受 `CLAUDE_PLAN_FILE` 明确指向的常规文件。环境变量不存在、路径不存在、符号链接、字节数或
哈希无法读取时停止；不扫描“最新 Markdown”。ExitPlanMode hook 只复制计划、写入 `ready_for_review`
状态并退出，不启动模型。

Claude 继续流程时，先把当前 `plan-working.md` 逐字复制到本轮独立的 `review-input` 目录，重新核对
UTF-8 字节数和 SHA-256，再使用 `cross-model-orchestration` 的路径审查包调用共享入口：

```text
v2_review_peer(
  author=claude, artifactType=plan, artifactMode=workspace,
  artifactId=auto-review-execute:<runId>,
  targetRoot=<round-n/review-input 的绝对路径>, artifactPath=plan-working.md,
  artifactBytes=<当前 UTF-8 字节数>, artifactSha256=<当前正文 SHA-256>,
  acceptanceCriteria=<非空>, taskProfile=knowledge_work,
  seriesId/seriesVersion/latestJobId=<续轮 CAS 字段>)
```

路径审查省略 `artifactContent`、`repairTargets` 和 `testCommands`。提交前必须确认
`workspaceReviews=true`、`workspaceRepairs=true` 和 `workspaceProbeState=available`；能力未就绪时停止，
不把长计划静默改成 inline。只有用户明确要求 Codex 返回完整替换稿时，才另按
`cross-model-orchestration` 使用 `v2_review_repair_peer artifactMode=inline`；这不是本 Skill 的默认路径。

`knowledge_work` 当前默认解析为 `gpt-5.6-sol/max`。如调用方明确给出其他 Codex 白名单模型/强度，
必须保存并按 bridge 的 route audit 验收；恢复时不能换模型、强度或 profile，也不能失败后回退。

当前 Claude 作者任务必须在同一回合循环同一 job 的 `v2_await_peer`/`v2_peer_result` 直到终态。
workspace `v2_review_peer` 返回包含结论、已确认事项、问题与理由、必须修改和剩余风险的完整
`PLAN_REVIEW`，不返回 `repairedArtifact`，也不产生工作区同步。Claude 根据 findings 修改 run-local
`plan-working.md`，并负责修订与完整性验收。

## 审查阶段

审查包必须包含 `author=claude`、`artifactMode=workspace`、最小 `targetRoot`、相对 `artifactPath`、
`artifactBytes`、`artifactSha256`、前轮 findings、验收标准和续轮 CAS 字段，并且不含正文。
权限由 `v2_review_peer` 固定，请求不得自行传入 `reviewerAccess`。Claude 收到 bridge 结果后先检查
`completion_receipt`、模型、只读工作区证据以及作者文件未变化，再验收审查正文：

- `通过`：保存 `PLAN_REVIEW`，进入 `done_phase1`；
- `需修改`：当前 Claude 作者任务根据 findings 更新 run-local `plan-working.md`、UTF-8 字节数、
  SHA-256 和前轮 findings，生成新的本轮只读快照，再用同一 series CAS 进入下一轮，最多三轮。正常任务内继续不需要
  `continuation`；只有 Claude 任务已经退出时，bridge 才因没有可验证的 Claude Code 宿主任务外唤醒
  接口而停止自动恢复。无论哪条路径，都不会自动替用户确认执行或未经作者验收写入主项目。
- `实质分歧` 或第 3 轮仍需修改：输出 `DISAGREEMENT_REPORT`，等待用户裁决。

格式错误、bridge 不可用、超时、CAS/完整性不匹配、模型回执缺失、路径只读隔离失败或审查者写入时写入
`PEER_REVIEW_FAILURE_REPORT` 并停止，不换模型、不静默降级。旧的
`orchestration-control.mjs` 和 `check-resume-candidate.mjs` 仅在显式归档诊断标志下可运行，不能作为
模型调度入口。

## 确认、执行和验收

`finalize` 只生成 `plan-final.md`，不会启动执行。Claude 必须向用户展示最终计划、每轮结论、已解决
项、剩余风险和范围；用户明确确认后才记录确认人及 `plan-final.md` SHA-256：

```powershell
node scripts/execute-plan.mjs confirm --run-dir "<run-dir>" --confirmed-by "user"
node scripts/execute-plan.mjs start --run-dir "<run-dir>"
node scripts/execute-plan.mjs poll --run-dir "<run-dir>"
node scripts/execute-plan.mjs validate --run-dir "<run-dir>"
```

执行作者可以在确认的 `targetRoots`/`allowedPaths` 内写入。Claude 按计划中的验收标准、只读验证
命令和前后快照独立验收；执行完成、返工和最终交付都不自动发起第二次 peer review。用户明确要求
审查交付物时，才另按 `cross-model-orchestration` 的显式 `artifactType=deliverable` 流程处理。
验收失败最多允许三次“返工 -> 独立验收”，第三次仍失败进入 `awaiting_user`，不发第四次。

计划元数据的 `verifyCommand` 只允许无副作用的 `Test-Path`、`Get-Content` 和 `node --version`，并要求
退出码为 0 且输出包含 `expectedOutput`。执行前后快照记录所有目录项；符号链接、范围外新增/删除/重命名
或计划确认哈希变化均停止，不生成纯文本补丁。

## 验证与发布

```powershell
node --test tests/*.test.mjs
```

源码修改后从 `D:\BaiduSyncdisk\.agents\skills` 精确暂存 `auto-review-execute`，提交并推送。推送
成功后按全局规则调用定向 `Invoke-CcSwitchSkillSync.ps1`，传入 Skill 名和 40 位远端提交 SHA；只有
四层文件集合和 SHA-256 一致才报告运行时已生效，否则报告“源码已推送，运行时未生效”。
