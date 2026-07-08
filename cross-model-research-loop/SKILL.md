---
name: cross-model-research-loop
description: 跨模型科研自动循环：监督者模型通过无头 CLI 调度异族执行者模型跑仿真/研究任务，在里程碑评审门把关，实现"睡觉时跑研究"。Use when 用户要让 Codex 或 Claude 自动执行多轮仿真、实验计划、论文流水线并由另一个模型监督评审，要搭自动科研循环、监督 codex exec 后台任务，或排查 codex exec / claude -p 无头调用问题（sandbox 权限拒写、Desktop 会话 resume 失败、后台任务通知）。不负责执行者侧的科研技能本身（实验设计、查新、论文写作归项目内 ARIS skill，见"与 ARIS 的边界"）。
---

# 跨模型科研自动循环

## 作用

把研究任务拆成"监督者 + 执行者"双角色循环：执行者（便宜模型）跑仿真、写代码、出结果；监督者（贵模型）发任务、卡里程碑、做物理和逻辑评审。已在多子带 THz 仿真项目完整验证（M0-M6 七个里程碑 + 论文初稿，2026-07-06/07）。

## 角色与分工原则

1. **监督者**：发任务、收结果、评审、决定下一步。token 消耗小、判断价值高，用贵模型。
2. **执行者**：读计划、写代码、跑实验、产出数据和文档。token 消耗大，用便宜模型。
3. **红线：监督者与执行者必须异族模型**（Claude↔GPT/Codex 等）。同族自监督会漏掉循环验证、口径漂移这类"自己骗自己"的问题。
4. 默认形态：**Claude 监督 + Codex 执行**（成本最优：贵模型在低 token 位置）。镜像形态（Codex 监督 + `claude -p` 执行）用于 Claude 侧额度受限时，见 references/cli-adapters.md。

## 循环流程

1. 任务以里程碑（milestone）为单位下发，每个任务结尾写明"跑完停下等评审"；
2. 监督者用无头 CLI 后台调用执行者（命令模板见 references/cli-adapters.md），等完成通知；
3. 收到通知后先**验证产出真实存在**（目录、文件、行数），再做内容评审——执行者说"跑完了"不算数，见过声称完成实际只跑了旧回归脚本的案例；
4. 评审通过 → 发下一个里程碑；不通过 → 打回并附具体修订要求（指名文件、指名判据）；
5. 三种情况停下问用户：方向性决策（选题/期刊/故事线）、高风险操作（删除/覆盖成果）、需要花钱或动硬件。

评审抓手清单见 references/review-gates.md——这是本 skill 的核心资产。

## 与 ARIS 的边界

执行者侧的科研工作流（`experiment-plan`、`novelty-check`、`paper-plan`、`paper-write`、`auto-review-loop` 等）属于项目内安装的 ARIS skill（仓库 `C:\Users\SanAn\aris_repo`，项目级安装见各项目 `AGENTS.md` 的 ARIS 管理块），由执行者在会话内自行调用。本 skill 只管监督者侧：调度、验证、评审、推进。ARIS 的 `auto-review-loop` 是执行者会话内的自循环审稿，与本 skill 的外部监督循环互补，不互相替代。

## 维护

- 适配器命令或坑位变化（CLI 升级、参数变更）→ 更新 references/cli-adapters.md 并注日期；
- 评审中抓到新的通用问题模式 → 追加到 references/review-gates.md，一条一个模式；
- 本 skill 不存放任何项目专属参数（口径数值、路径），项目专属内容写进该项目的 AGENTS.md；
- ARIS 仓库路径（当前 `C:\Users\SanAn\aris_repo`）若随工作流重构迁移，需同步更新本文件"与 ARIS 的边界"节及各项目的 reconcile。
