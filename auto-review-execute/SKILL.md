---
name: auto-review-execute
description: >
  在 Claude Code CLI 中把已退出 Plan Mode 的明确计划交给 Codex 进行最多三轮可写审计，
  再由 Claude 复核、向用户展示最终计划并在用户确认后受限执行。仅当计划文件由
  CLAUDE_PLAN_FILE 明确提供、任务需要计划审计或按确认计划执行本地改动时使用；任何
  缺少计划路径、元数据、用户确认或运行环境不兼容的情况都停止并报告，绝不猜测计划文件。
compatibility: Requires Windows, Node.js 24+, an authenticated codex@openai-codex Claude plugin, and the sibling cross-model-orchestration skill. No npm dependencies.
---

# Auto Review Execute

## 目标和边界

本 Skill 只在 Claude Code CLI 主会话中运行。Claude 负责调度、语义判断、最终验收和向用户提问；
Codex 负责在明确授权的范围内审计或执行。它是 `cross-model-orchestration` 的可写计划审计变体，
不改变后者的只读复核契约。

运行根目录为 `%LOCALAPPDATA%\auto-review-execute\<runId>\`。所有审计版本都在这里：

```text
<runId>/
  plan-original.md
  plan-working.md
  plan-final.md
  state.json
  global-lock linkage and run.lock
  round-<n>/
  pre-execute-snapshot.json
  execution/ or rework-attempt-<n>/
```

`plan-working.md` 是审计阶段唯一可修改的计划文件。`planFile` 永远指向它；不要把修改同步回
原始 `CLAUDE_PLAN_FILE`，也不要另造一个工作版本。

## 前置条件

1. 先完成 `cross-model-orchestration` 的宿主、插件、cwd 和权限预检。
2. 只接受 `CLAUDE_PLAN_FILE` 指向的常规非符号链接文件。环境变量不存在、路径不存在或为链接时，
   hook 仅向 `trigger-errors.log` 记录错误并停止。绝不扫描“最新 Markdown”。
3. 运行目录和锁根目录由 `AUTO_REVIEW_EXECUTE_HOME` 覆盖（仅测试），默认 `%LOCALAPPDATA%\auto-review-execute`。
4. 不直接修改 `%USERPROFILE%\.claude\settings.json`。Hook 安装属于 cc-switch 权威配置的单独部署操作，
   只有用户明确允许改配置时才按本仓库规则执行。

## Hook 协议

ExitPlanMode hook 调用：

```text
node "D:/BaiduSyncdisk/.agents/skills/auto-review-execute/scripts/trigger-review.mjs"
```

hook 只做以下工作：验证 `CLAUDE_PLAN_FILE`，复制为 `plan-original.md` 和 `plan-working.md`，写入
`state.json`（`ready_for_review`），获取持久 `global.lock`，然后退出。它不启动、不轮询、不等待
Codex。Claude 会话读取并轮询 `state.json` 继续流程。

过期锁接管前必须从旧 `state.json` 找到并取消活跃 Codex job；不能安全取消时拒绝接管，避免两条
写链并发。

## 阶段一：审计

Claude 按以下命令推进。`<run-dir>` 必须来自 hook 输出的 `stateFile` 父目录。

```powershell
node scripts/review-loop.mjs status --run-dir "<run-dir>"
node scripts/review-loop.mjs launch --run-dir "<run-dir>"
node scripts/review-loop.mjs poll --run-dir "<run-dir>"
```

`launch` 仅授权 Codex 写 run 内的 `plan-working.md` 和本轮 `codex-output.md`。它不能写源计划、Git、
配置或系统文件。Claude 轮询到 `evaluating` 后必须基于 `diff.json` 和审计结果做语义判断：

- 同意：`evaluate --decision agree`，再 `finalize`；
- 轻微调整：Claude 提供调整后的工作版本，`evaluate --decision minor --adjusted-plan-file ...`，再 `finalize`；
- 重大异议：`evaluate --decision major`，最多三轮；
- 三轮仍无法收敛：`evaluate --decision diverge`，状态进入 `diverged`，由用户裁决。

```powershell
node scripts/review-loop.mjs evaluate --run-dir "<run-dir>" --decision agree --rationale "..."
node scripts/review-loop.mjs finalize --run-dir "<run-dir>"
```

`finalize` 先从工作版本删除唯一的 `CODEX-REVIEW` 块，再原子写入 `plan-final.md`，并确认最终文件无残留块。

## 阶段二：确认、执行、独立验收

Claude 先展示 `plan-final.md` 和执行摘要，明确询问是否执行。用户确认后记录确认人和当时
`plan-final.md` 的 SHA-256：

```powershell
node scripts/execute-plan.mjs confirm --run-dir "<run-dir>" --confirmed-by "user"
node scripts/execute-plan.mjs start --run-dir "<run-dir>"
node scripts/execute-plan.mjs poll --run-dir "<run-dir>"
node scripts/execute-plan.mjs validate --run-dir "<run-dir>"
```

执行前重新计算哈希；只要与确认记录不同，状态转为 `awaiting_user`，不执行。该绑定防止用户确认后
计划被替换。

`plan-final.md` 必须有严格的 YAML front matter：

```markdown
---
auto-review-execute:
  targetRoots:
    - "D:\\BaiduSyncdisk\\my-project"
  allowedPaths:
    - "D:\\BaiduSyncdisk\\my-project\\src"
  acceptanceCriteria:
    - id: ac-1
      description: "入口文件存在"
      verifyCommand: "Test-Path src/index.js"
      expectedOutput: "True"
---
```

允许的 `verifyCommand` 只有无副作用的：`Test-Path`、`Get-Content`、`node --version`。每条命令同时要求
退出码为 0 且输出包含 `expectedOutput`。`Test-Path` / `Get-Content` 仅能读取 `targetRoots` 内的具体路径，
禁止通配符、管道、重定向、变量展开和命令连接符。

执行前后快照记录所有目录项：新增、删除、内容或类型变更、符号链接新增/变更，以及根目录被替换。快照
不跟随符号链接；目标根或变更集合中任何符号链接均使范围校验失败。范围外新增、删除或重命名都按失败处理。

验收失败时可启动最多两次返工：

```powershell
node scripts/execute-plan.mjs rework --run-dir "<run-dir>"
```

每次返工后必须重新运行完整 `validate`。两次仍失败转 `awaiting_user`。

## 状态和停止条件

- `ready_for_review`：hook 已建立工作版本；
- `reviewing`：Codex 审计任务正在运行；
- `evaluating`：等待 Claude 判断；
- `done_phase1`：最终计划已生成，尚未执行；
- `awaiting_execution_confirmation`：用户确认哈希已记录；
- `executing` / `reworking`：Codex 正在写受限项目范围；
- `validating`：Claude 独立检查快照和命令；
- `done`：所有独立验收通过；
- `error`、`diverged`、`awaiting_user`：停止，保留状态和证据，不自动接管或重试。

认证、权限、sandbox、超时、额度或 runtime 失败一律写 `CODEX_FAILURE_REPORT.md` 并停止。不得让 Claude
静默改由自己执行。

## 验证与发布

本技能的聚焦测试：

```powershell
node --test tests/*.test.mjs
```

完成源码修改后，从 `D:\BaiduSyncdisk\.agents\skills` 精确暂存 `auto-review-execute`，执行 `git commit` 和
`git push`。推送成功后，按仓库全局规则调用：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "D:\BaiduSyncdisk\.agents\automation\ccswitch-skill-sync\Invoke-CcSwitchSkillSync.ps1" -Skills "auto-review-execute" -ExpectedRemoteCommit "<40-character-remote-commit>"
```

只有该脚本返回 `runtime_active`，才可报告运行时已生效；否则只能报告“源码已推送，运行时未生效”。
