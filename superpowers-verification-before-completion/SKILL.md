---
name: superpowers-verification-before-completion
description: 以 Superpowers 的 `verification-before-completion` 为基线，接到当前本地 Codex 环境中。Use when 任务已经接近交付、准备汇报完成或准备停手，需要基于证据做一次完工前核验；prefer this over 松散的 “done” 表述，但保持显式进入，不做默认常驻闸门。
---

# Superpowers 完工前核验

## 作用

这份 skill 以上游 `verification-before-completion` 为基线，但改成当前工作流里的“完工前核验闸门”。

## 流程

1. 先读上游基线：
   `verification-before-completion`
2. 只在这些时刻进入：
   - 接近交付
   - 准备汇报“已完成”
   - 准备停手
   - 准备交给下一步 review 或 handoff
3. 进入后先把信息分成三类：
   - 已实际执行的验证
   - 理论上应该做但尚未执行的验证
   - 当前无法验证的阻塞
4. 汇报时必须说清证据来源：
   - 跑了哪些命令或测试
   - 看到了哪些文件、日志或产物
   - 哪些判断只是推断，不是实测
5. 如果关键验证没做，不把任务表述成“已经完成”；应改成“修改已完成，但尚未完成验证”或“受阻于某条件，尚未完成验证”。

## 边界

- 不把“看起来没问题”当成验证。
- 不为形式完整而伪造已运行的测试或检查。
- 如果任务还在设计、讨论或资料整理阶段，不强行进入这份 skill。
- 代码审查需求优先参考 [../superpowers-requesting-code-review/SKILL.md](../superpowers-requesting-code-review/SKILL.md)。

## 相关技能

- 上游基线：`verification-before-completion`
- 代码审查交接：[../superpowers-requesting-code-review/SKILL.md](../superpowers-requesting-code-review/SKILL.md)
- Codex 工作流建议：[../codex-workflow-coach/SKILL.md](../codex-workflow-coach/SKILL.md)

## 维护

- 上游 `verification-before-completion` 更新后，优先回查这里保留的证据表达和停手条件。
- 这里沉淀的是本地交付闸门，不是通用测试教程。
