---
name: superpowers-systematic-debugging
description: 以 Superpowers 的 `systematic-debugging` 为基线，接到当前本地 Codex 环境中。Use when 用户明确要 Superpowers 风格的系统化排障，或排错已经变得反复试错、证据薄弱、假设过多；prefer this over 临时拍脑袋试错 for 复杂故障，但不自动进入简单一次性修复。
---

# Superpowers 系统化调试

## 作用

这份 skill 以 Superpowers 的 `systematic-debugging` 为基线，但只保留适合当前本地工作流的显式排障入口。

## 进入条件

下面这些信号明显时再进入：

- 同一问题已经反复试错，仍没有稳定结论
- 现象、复现条件和最近改动之间关系不清
- 需要把“现象 / 假设 / 验证 / 证据 / 下一步”压成清楚链路

## 流程

1. 先读上游基线：
   `systematic-debugging`
2. 进入后先补齐最小事实：
   - 观察到的现象
   - 当前可用的复现方式
   - 最近改动或高风险区域
   - 已经排除的方向
3. 默认留在当前对话里做系统化排查，不默认拉起子代理、子对话或额外 `codex exec` 进程。
4. 输出时优先按下面结构组织：
   - `现象`
   - `假设`
   - `验证步骤`
   - `证据`
   - `结论`
   - `下一步`

## 边界

- 不把很小、肉眼可见的小错误包装成系统化调试。
- 不把“列几个猜想”冒充成证据驱动的排障。
- 不默认触发多代理编排或市场级技能搜索。
- 命令风险仍优先服从 [../command-pattern-memory/SKILL.md](../command-pattern-memory/SKILL.md) 和 [../zhongduan-zhixing-hulan/SKILL.md](../zhongduan-zhixing-hulan/SKILL.md)。

## 相关技能

- 上游基线：`systematic-debugging`
- Windows 命令复用：[../command-pattern-memory/SKILL.md](../command-pattern-memory/SKILL.md)
- Windows 命令护栏：[../zhongduan-zhixing-hulan/SKILL.md](../zhongduan-zhixing-hulan/SKILL.md)

## 维护

- 上游 `systematic-debugging` 更新后，优先回查这里的进入条件和边界，不复制上游全文。
- 如果以后稳定需要自动触发，再收紧 `description`，不要先把口子开大。
