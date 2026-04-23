---
name: superpowers-writing-plans
description: 把 `vendor/writing-plans` 接到当前本地 Codex 环境中，用于把已确认的设计和 spec 写成可执行实施计划。Use when 用户明确要 Superpowers 风格实施计划，或需求和方案已基本敲定，下一步需要拆成文件级执行步骤；prefer this over 含糊的“先列个计划” when 多步编码任务需要明确文件、命令、测试和交接，但不强制要求专用 worktree 或上游的子代理假设。
---

# Superpowers 实施计划

## 作用

这份 skill 以 `writing-plans` 为上游基线，但只保留当前本地环境真正需要的实施计划纪律。

目标不是照搬上游，而是把“如何把已确认方案拆成可执行计划”这件事落到当前 Codex、Windows 和本地同步技能目录里。

## 进入条件

只在下面这些条件满足时进入：

- 需求、设计或 spec 已经基本确认
- 下一步需要把工作拆成可执行的实施计划
- 任务明显是多步编码工作，而不是一句 TODO 就够

如果还在澄清需求，优先回到 `brainstorming` 或其他前置澄清技能。

## 流程

1. 先读上游基线：
   `writing-plans`
2. 进入前先补齐最小输入：
   - 已确认的目标、范围和非目标
   - 目标仓库或工作目录
   - 已知测试入口、构建命令和验收口径
   - 如果 spec 跨多个独立子系统，先拆成多份计划
3. 默认保留这些核心做法：
   - 先做 file map，再拆 tasks
   - 尽量精确到文件路径、命令和预期结果
   - 每个任务尽量可以单独验证
   - 不写 placeholder
   - 写完后做一次 coverage、placeholder 和一致性自查
4. 本地执行时做这些调整：
   - 默认留在当前对话里产出计划，不强制要求 dedicated worktree
   - 默认把计划落到 `docs/plans/YYYY-MM-DD-<topic>-implementation.md`
   - 如果项目已有稳定计划目录或命名规则，沿用现有规则
   - 不强制要求上游的 `subagent-driven-development` 或 `executing-plans`
5. 写步骤时优先具体、可验证、基于现有证据。
   能确定时就给精确路径、命令、测试和预期输出；还没读到相关文件时，不为了凑格式去虚构代码块。
6. 如果用户明确要求：
   - 新开本地 Codex 子对话做 handoff：转到 [../ziduihua-diaodu/SKILL.md](../ziduihua-diaodu/SKILL.md)
   - 新开 `codex exec` 进程执行或续跑：转到 [../codex-cli-local/SKILL.md](../codex-cli-local/SKILL.md)

## 边界

- 不把需求仍模糊的阶段误判成实施计划阶段。
- 不为很小的任务强写重型计划。
- 不强制沿用上游的 dedicated worktree、子代理或执行交接假设。
- 不为了满足格式虚构未验证的代码、测试或命令。
- 不把“计划写完”说成“实现已经开始”或“执行已经委托”。

## 相关技能

- 上游基线：`writing-plans`
- 前置澄清：`brainstorming`
- 本地 Codex CLI：[../codex-cli-local/SKILL.md](../codex-cli-local/SKILL.md)
- 本地子对话分流：[../ziduihua-diaodu/SKILL.md](../ziduihua-diaodu/SKILL.md)
- 完工前核验：[../superpowers-verification-before-completion/SKILL.md](../superpowers-verification-before-completion/SKILL.md)

## 维护

- 上游 `writing-plans` 更新后，优先回查这里保留的本地差异是否仍只集中在路径、路由和执行边界。
- 保持它是本地接入层，不复制上游正文。
