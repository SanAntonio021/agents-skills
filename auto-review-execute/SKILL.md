---
name: auto-review-execute
description: >
  在 Claude Code VS Code 插件或 CLI 中，把已退出 Plan Mode 且已保存到真实项目内的正式计划交给
  claude-codex-bridge v3，由 Codex 在同一项目中使用完整工具审查并可直接修改。Claude 随后重读、
  验收并按需修改；只有 Claude 又改过主计划时才追加一次 Codex 只检查终审。互审完成后仍需用户明确
  确认才能执行。高风险动作只使用 bridge 返回的精确审批目标，不自行缩减成只读、快照、文件白名单
  或 sandbox。旧 v2 适配器仅用于既有运行状态和未落盘内容兼容。
compatibility: Requires Windows, Node.js 24+, the CC Switch-registered claude-codex-bridge MCP, and the sibling cross-model-orchestration skill.
---

# Auto Review Execute

## 边界

本 Skill 只在 Claude Code VS Code 插件或 CLI 作者任务中运行。Claude 是原作者和执行验收者，Codex 是
异族审查者。正式计划互审使用 `v3_review_peer`；审查通过只表示可以向用户呈现，不代表用户已经授权
执行。

`codex@openai-codex`、原生 `codex exec`、隐藏 Hook 和旧 `orchestration-control.mjs` 不作为新的互审
入口。保留的本地脚本只维护运行记录、最终计划哈希、用户确认和执行验收；旧 bridge 适配器只供已有
v2 状态兼容。

## 计划必须位于真实项目

先确定当前真实项目根 `projectRoot`。正式审查的主计划必须是该根目录下的普通文件，并有明确相对
`artifactPath`。如果 `CLAUDE_PLAN_FILE` 已在项目内，直接以它为主计划；如果它位于 Claude 的用户级
计划目录，先把当前正式稿保存为项目内明确文件，例如 `.claude/plans/<runId>.md`，并从此把该文件作为
权威工作稿。不要让 bridge 审查 `%LOCALAPPDATA%` 下的副本，也不要扫描“最新 Markdown”。

长期运行记录可继续位于 `%LOCALAPPDATA%\auto-review-execute\<runId>\`，但其中只保存流程状态、哈希、
回执和用户确认，不把它当成 v3 的项目根。

如果计划确实无法可靠落盘，才按 `cross-model-orchestration` 明确使用 v2 inline 兼容流程；v3 失败后
不能自动回退 v2，也不能把正文塞进 `task`。

## v3 互审

先调用 `v3_peer_status`，确认 protocol 3 已启用并报告真实 cwd、完整原生工具、直接项目写入和
`artifactContentAccepted=false`。随后调用：

```text
v3_review_peer(
  author=claude, target=codex,
  projectRoot=<真实项目绝对路径>, artifactPath=<项目内相对计划路径>,
  artifactType=plan, artifactId=auto-review-execute:<runId>,
  task=<审查任务>, acceptanceCriteria=<非空>, constraints=<可选>,
  model=gpt-5.6-sol, reasoningEffort=max
)
```

不传 `artifactContent`、字节数、哈希、`targetRoot`、`repairTargets`、`allowedPaths`、sandbox 或工具列表。
Codex 以真实项目为 cwd，加载完整工具、项目规则、技能、插件、MCP 和网络能力，并可直接修改项目。

当前 Claude 作者任务在同一回合循环同一 job 的
`v3_await_peer(job_id, timeout_ms<=45000)` 和 `v3_peer_result(job_id)`，直到终态。软等待返回 pending 时
继续原 job，不创建替代 job、不换模型、不降档。

首轮成功后，Claude 必须重新读取主计划和 review 结果，核对 Codex 的实际改动并可自行修改，然后用
首轮最新的 `series_id`、`series_version`、`latest_job_id` 调用 `v3_author_checkpoint`：

- `author_modified=false`：直接向用户展示最新计划、结论和未决项；
- `author_modified=true`：以完全相同的任务、项目、路径、验收、约束和模型字段，再调用一次
  `v3_review_peer`。该轮是 `final_check`，Codex 只能检查，不能修改；
- 终审无论通过、仍需修改或存在分歧，都交给用户，不继续循环。

呈现前再次查询 `v3_peer_result`。只有 `conclusion_valid=true` 时才能引用结论；计划哈希变化或文件消失
会使旧结论失效。

## 权限与审批

v3 对端默认拥有完整权限。普通操作自动执行，包括删除项目内一个普通文件。批量、递归、通配符、
目录、项目外或远程删除，丢弃 Git 修改及清空数据库时，job 进入 `awaiting_approval`。

此时只向用户展示 bridge 返回的 action、完整 targets、approval ID、fingerprint 和到期时间；用户
决定后把这些字段原样传给 `v3_resolve_approval`。一次确认只覆盖该精确动作，24 小时后失效；拒绝或
超时取消动作。不要自行扩大或缩小审批目标，也不要声称能发现普通程序内部没有显式暴露的删除。

## 用户确认、执行和验收

互审结束后，Claude 向用户展示最终计划、对端是否改过、Claude 是否改过、是否运行终审、有效哈希、
结论和剩余问题。用户明确确认后，才记录 `plan-final.md` 的 SHA-256 并开始执行：

```powershell
node scripts/execute-plan.mjs confirm --run-dir "<run-dir>" --confirmed-by "user"
node scripts/execute-plan.mjs start --run-dir "<run-dir>"
node scripts/execute-plan.mjs poll --run-dir "<run-dir>"
node scripts/execute-plan.mjs validate --run-dir "<run-dir>"
```

这里的执行范围来自用户确认的计划，与 v3 审查者权限无关。Claude 按验收标准、文件快照和验证命令
独立检查执行结果；执行和交付完成后不自动再发互审，除非用户明确要求审查交付物。验收失败最多三次
返工，第三次仍失败就交给用户。

## 失败与发布

路径无效、bridge 不可达、模型回执不匹配、结果 schema 错误、审批拒绝或过期、会话清理失败和终审
写入都按实际状态报告。不要伪造通过、猜测路径、扫描其他 job、重启 daemon、自动降级或替用户裁决。

修改后运行 `node --test tests/*.test.mjs`。源码推送后按全局规则定向同步本 Skill，并核对 source、
CC Switch、Claude、Codex 四层文件集合与 SHA-256；未完全一致时只能报告运行时未生效。
