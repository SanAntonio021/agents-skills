---
name: cross-model-research-loop
description: 跨模型科研自动循环：监督者通过统一 claude-codex-bridge MCP 调度异族执行者跑仿真、实验或论文流水线，在每个里程碑用 review_repair 审查、修复和测试，实现可暂停、可追溯的后台研究循环。Use when 用户要自动执行多轮仿真、实验计划或论文流水线，需要长期后台运行和科研里程碑评审；在两端叠加 cross-model-orchestration。旧 codex@openai-codex、codex exec 和 claude -p 仅作历史排错资料，不作为运行时入口。
---

# 跨模型科研自动循环

## 作用

把科研任务拆成“监督者 + 执行者 + 里程碑验收”循环。执行者在 bridge 固定副本中跑仿真、写代码、
产出数据和文档；监督者按 `review_repair` 检查证据、修复允许范围内的问题、运行测试并决定是否推进。
文件系统、manifest、job ID 和验收报告是证据，不能用执行者的完成声明替代。

## 角色与通道

1. 监督者负责拆分里程碑、发任务、收结果、做物理和逻辑评审、决定下一步。
2. 执行者负责在明确 `targetRoot`/`allowedPaths` 内运行任务并保存可复核产物。
3. 监督者和执行者必须是异族模型；同族自监督不算互审。
4. 两端都通过同一个 `claude-codex-bridge` MCP：Claude 监督时 `target=codex`，Codex 监督时
   `target=claude`。默认采用 `research` profile（当前为 Opus 5/max 与 Sol/max）；如任务明确选择
   其他白名单 profile/模型，按 bridge 解析结果验收。不直接调用旧 companion、`codex exec`、`claude -p` 或隐藏 Hook。

## 循环流程

1. 先把研究问题拆成里程碑，每个里程碑写清输入、精确 `testCommands`、输出文件、物理验收判据和“跑完停下等评审”。
2. 用 `submit_peer(operation=task, taskProfile=research)` 提交执行任务；任务需要写入时必须给最小 allowlist 和固定工作区。
   Claude 方向的 `testCommands` 不得含引号、变量、通配符、重定向、管道或命令串联；权限拒绝即失败。
3. 用 `await_peer`/`peer_result` 轮询同一 job，确认目录、文件、字节数、哈希、命令退出码和结果时间戳。
4. 用 `submit_peer(operation=review_repair, artifactType=deliverable)` 把里程碑产物交给对方模型；
   审查者在固定副本中检查证据、直接修复允许范围内的问题并运行测试，返回含五个固定组成部分的
   `DELIVERABLE_REVIEW`。
5. 作者检查 bridge 同步后的主项目。普通新增/修改自动同步；删除、重命名、权限、类型变化先停在
   `awaiting_user`，用户明确批准精确 `pending_high_risk` ID 后才调用 `approve_peer_sync`。
   待授权期间固定副本和目标根锁继续保留，不能用重叠任务绕过。
6. 通过才进入下一个里程碑；不通过则把具体文件、证据、判据和 allowlist 发回执行者返工。
7. 同一确认计划最多三次“返工 -> 独立验收”；第三次仍不通过输出报告并等待用户。

## 研究专用评审门

评审抓手清单见 `references/review-gates.md`，至少检查：

- 输入材料和参数是否真实存在、版本和单位是否一致；
- 仿真/离线/Mock/硬件结果是否明确区分，不能把 dry-run 写成硬件 PASS；
- 物理边界、SNR、带宽、采样率、时钟、温漂、Doppler、误码和统计重复是否满足验收判据；
- 图表、日志、随机种子、环境版本和脚本是否能复现结果；
- 结论是否超出证据，失败结果和未完成范围是否保留。

监督者不得因“结果目录存在”就认定完成，也不得让执行者扩大 allowlist 或覆盖作者新改动。

## 长任务与恢复

每个里程碑保存 `artifactId`、round、job ID、目标根、模型、推理强度、profile、路由规则、
基线/结果 manifest、测试结果和错误原因。
不要猜测最新线程；恢复只使用指定 job 的 `resume_peer`，或在用户裁决后创建新的 `artifactId`。
取消、超时、MCP 不可用、模型不匹配、sandbox/权限错误和主项目漂移都输出
`PEER_REVIEW_FAILURE_REPORT` 并暂停，不换模型、不静默降级。

## 与通用编排和 ARIS 的边界

- `cross-model-orchestration` 负责宿主方向、审查包、三轮状态机、计划确认门、同步和失败报告。
- 本 Skill 只增加科研里程碑拆分、物理验收抓手和长任务恢复，不另起并行调度协议。
- 执行者侧的 `experiment-plan`、`novelty-check`、`paper-plan`、`paper-write` 等项目 Skill 仍由
  执行者在其固定副本中调用；本 Skill 不存放项目专属参数或路径。

## 维护与验证

适配器变化、SDK/CLI 版本证据和新的科研风险模式分别追加到 `references/cli-adapters.md`、
`references/review-gates.md` 并标注日期。评测至少覆盖两方向自动触发、简单任务跳过、一次
`review_repair` 直接修复、三轮止损、用户确认门、审批同步、取消/恢复、模型不可用和 Codex Desktop
可见性人工检查。源码推送后按全局规则定向同步并核对四层哈希。
