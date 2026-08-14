---
name: auto-review-execute
description: >
  在 Claude Code CLI 中把已退出 Plan Mode 的明确计划交给统一 claude-codex-bridge MCP，由 Codex
  在固定副本中审查、修复和测试，最多三轮；Claude 复核同步结果、向用户展示最终计划，并在用户
  明确确认后按 allowlist 执行。也用于重要交付物的 Claude to Codex review_repair。缺少明确计划
  路径、MCP、用户确认或完整验收证据时停止，不猜测路径、不调用旧 codex@openai-codex 插件。
compatibility: Requires Windows, Node.js 24+, the CC Switch-registered claude-codex-bridge MCP, and the sibling cross-model-orchestration skill. Legacy orchestration scripts are offline state helpers only.
---

# Auto Review Execute

## 目标和边界

本 Skill 只在 Claude Code CLI 主会话中运行。Claude 是作者和最终验收者；Codex 是 bridge 固定副本
中的审查/修复者。它不把审查者写入主项目，也不把审查通过当成执行授权。

旧 `codex@openai-codex` companion、`orchestration-control.mjs` claim 和隐藏 Hook 不再是运行时入口。
保留的 Node 脚本只维护本地状态、快照和用户确认哈希；模型调度必须通过同一个 MCP，或通过源码中
明确标记的 bridge CLI 兼容适配器。

运行根目录为 `%LOCALAPPDATA%\auto-review-execute\<runId>\`：

```text
plan-original.md / plan-working.md / plan-final.md
state.json / run.lock
round-<n>/ (审查包、快照、结果)
execution/ 或 rework-attempt-<n>/
```

## 入口与计划路径

只接受 `CLAUDE_PLAN_FILE` 明确指向的常规文件。环境变量不存在、路径不存在、符号链接、字节数或
哈希无法读取时停止；不扫描“最新 Markdown”。ExitPlanMode hook 只复制计划、写入 `ready_for_review`
状态并退出，不启动模型。

Claude 继续流程时，使用 `cross-model-orchestration` 的完整审查包调用：

```text
submit_peer(target=codex, operation=review_repair,
  artifactType=plan, artifactId=auto-review-execute:<runId>,
  round=<1..3>, targetRoot=<受控共同根>, allowedPaths=<计划和本轮输出文件>)
```

轮询只能使用同一 job 的 `await_peer`/`peer_result`。bridge 的 `review_repair` 会在固定副本中一次
完成审查、修复、测试并返回包含结论、已确认事项、问题与理由、必须修改和剩余风险的完整
`PLAN_REVIEW`；普通变更自动同步，删除/重命名/权限/类型变化必须停在
`awaiting_user`，由用户明确批准完整的 `pending_high_risk[].id` 集合后再调用 `approve_peer_sync`。
授权只重新核对基线和副本哈希并同步，不重新调用 Codex；ID 不匹配、主项目漂移或副本变化都输出
`PEER_REVIEW_FAILURE_REPORT` 并关闭本轮。
待授权期间 bridge 保留固定副本和目标根锁；重叠任务必须停止，不能换 `artifactId` 绕过。

## 审查阶段

审查包必须包含 `artifactBytes`、`artifactSha256`、完整内容或明确路径、前轮 findings、验收标准和
`reviewerAccess=isolated_write`。Claude 收到 bridge 结果后先检查主项目快照和同步状态，再作语义判断：

- `通过`：保存 `PLAN_REVIEW`，进入 `done_phase1`；
- `需修改`：由 Claude 修订 `plan-working.md`，更新哈希和 `priorFindings`，最多进入下一轮；
- `实质分歧` 或第 3 轮仍需修改：输出 `DISAGREEMENT_REPORT`，等待用户裁决。

格式错误、bridge 不可用、超时、Codex 越界写入、主项目漂移或同步冲突写入
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

执行作者可以在确认的 `targetRoots`/`allowedPaths` 内写入，但重要交付物返回前必须再次走
`submit_peer(target=codex, operation=review_repair, artifactType=deliverable)`；作者检查同步后才算交付。
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
