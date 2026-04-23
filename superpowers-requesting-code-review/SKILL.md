---
name: superpowers-requesting-code-review
description: 以 Superpowers 的 `requesting-code-review` 为基线，接到当前本地 Codex 环境中。Use when 用户明确要 Superpowers 风格 review handoff，或一轮实现已完成、准备在合并或交接前做结构化审查；prefer this over 随手“帮我看看”，但除非用户明确要求，否则不默认进入子代理或额外 review 进程。
---

# Superpowers 代码审查交接

## 作用

这份 skill 以 Superpowers 的 `requesting-code-review` 为基线，但改成适合当前 Codex 约束的本地代码审查入口。

## 流程

1. 先读上游基线：
   `requesting-code-review`
2. 进入后先选最窄的审查路径：
   - 默认留在当前会话内做 review
   - 用户明确要新开本地 Codex 子对话时，转到 [../ziduihua-diaodu/SKILL.md](../ziduihua-diaodu/SKILL.md)
   - 用户明确要新的 `codex exec review` 进程时，转到 [../codex-cli-local/SKILL.md](../codex-cli-local/SKILL.md)
3. 准备审查输入时，尽量补齐：
   - 需求或验收标准
   - 本次改动范围
   - 如能拿到，再补 base/head 或 diff 范围
4. 默认按当前本地 review 规则输出：
   - findings first
   - 按严重程度排序
   - 带文件和行号引用
   - 没发现时明确写 `未发现实质问题`
5. 不默认沿用上游的子代理 review 路线；只有用户明确要求分流或委托时才进入。

## 边界

- 不输出“我已经启动 reviewer 子代理”这类与当前事实不符的话。
- 不把普通“帮我看看”自动升级成多代理审查。
- 不把顺手扫一眼包装成正式 review 结论。
- 如果用户要的是调试过程里的 fresh look，而不是正式 review，优先看 [../superpowers-systematic-debugging/SKILL.md](../superpowers-systematic-debugging/SKILL.md)。

## 相关技能

- 上游基线：`requesting-code-review`
- 本地 Codex CLI：[../codex-cli-local/SKILL.md](../codex-cli-local/SKILL.md)
- 子对话分流：[../ziduihua-diaodu/SKILL.md](../ziduihua-diaodu/SKILL.md)
- 系统化调试：[../superpowers-systematic-debugging/SKILL.md](../superpowers-systematic-debugging/SKILL.md)

## 维护

- 上游 `requesting-code-review` 更新后，优先回查这里和当前 Codex 约束是否仍一致。
- 如果以后本地允许稳定的默认分流审查，再单独收紧路由，不直接把上游子代理假设搬回来。
