---
name: fangzhen-shiyan-jilu
description: 在改代码、跑仿真、做实验或调参迭代时，同步维护一份 Markdown 主记录，并把命令、参数、关键结果、图表和下一步一起落盘。Use when the user wants Codex to 边做边记, 新建或续写实验记录、仿真日志、labbook 或 run report, or keep one running record active through the current thread; prefer this over `codex-workflow-coach` when the goal is execution-time recording, and over `jineng-fupan` when the goal is a single task log rather than a later retrospective.
---

# 仿真实验记录

## 作用

这个 skill 把“改代码”和“跑仿真或实验”的执行过程，持续沉淀成一份可追溯的 Markdown 主记录，而不是等任务快结束时再补回忆录。

核心目标有 3 个：

1. 让记录在执行期就是正式产物，而不是收尾附件。
2. 让命令、参数、代码改动、图表和解释落在同一条时间线上。
3. 让后续接力时先读记录再行动，而不是重新猜上一轮做了什么。

## 流程

1. 先确定本次任务的主记录文件和产物目录。
   - 用户已经给了 `.md` 路径，就直接续写。
   - 项目里已有实验记录、`runs/` 或 `reports/` 约定，就沿用。
   - 如果没有，默认建立一份稳定主记录，可用 `labbook.md`。
2. 如果本线程前面已经启用了记录模式，默认继续写同一份主记录；只有用户明确说停止记录时才停。
3. 如果主记录不存在，优先用 [assets/labbook-template.md](assets/labbook-template.md) 起一个最小骨架。
4. 在第一次有意义的动作前，先写一条 kickoff：
   - 当前目标
   - 当前判断
   - 计划改哪些文件或跑什么命令
   - 预期产物是什么
5. 进入“小步执行 + 小步记录”循环：
   - 动手前记这一小步要验证什么
   - 改完后记涉及文件和改动原因
   - 跑完后记命令、关键参数、退出状态、核心结果和下一步
6. 对图表或截图一律按“文件 + 插图 + 短注释”处理：
   - 先保存实际文件，再插入 Markdown
   - 说明它由哪个命令、脚本或步骤产生
   - 说明它支持了什么判断

## 记录规则

- 默认维护一份主记录，不为每一步新建一个 `.md`
- 记录“有决策意义的步骤”，不把每个微小按键都写进去
- 连续几次极小改动可以合并记录，但不要跨越不同结论
- 代码改动很大时，优先总结行为变化和涉及文件，不贴大段 diff
- 图很多时，只保留最关键的 1 到 3 张，其他用列表或链接
- 结论还不稳定时，明确写“暂时判断”或“待下一轮验证”

## Markdown 约定

默认按下面这个骨架组织；如果用户已有现成格式，就保留原结构，只把关键字段补齐。

```markdown
# <任务标题>

## Goal

## Scope and Success Criteria

## Key Paths
- Workspace root:
- Main script or entrypoint:
- Primary report:
- Artifact root:

## Working Log
### <YYYY-MM-DD HH:MM> - <step title>
- Intent:
- Action:
- Files:
- Command:
- Result:
- Interpretation:
- Next:

## Key Figures

## Current Best State

## Open Issues

## Next Step
```

## 边界

- 不把这个 skill 用成周报、跨项目复盘或工作流建议器；那属于 [../codex-workflow-coach/SKILL.md](../codex-workflow-coach/SKILL.md) 或 [../jineng-fupan/SKILL.md](../jineng-fupan/SKILL.md)。
- 不为了“日志完整”而打断正常执行节奏。
- 不自动伪造图、表、结论或实验解释。
- 不忽略用户显式停止记录。
- 不强行改造用户已经在用的目录结构；只有缺失时才补最小约定。

## 相关技能

- 工作流建议与周度复盘：[../codex-workflow-coach/SKILL.md](../codex-workflow-coach/SKILL.md)
- 跨项目执行复盘：[../jineng-fupan/SKILL.md](../jineng-fupan/SKILL.md)
- Word 模板落地：[../word-muban-geshihua/SKILL.md](../word-muban-geshihua/SKILL.md)

## 资源

- 主记录模板：[assets/labbook-template.md](assets/labbook-template.md)

## 维护

- 保持它聚焦“执行期主记录”，不要膨胀成通用科研写作 skill。
- 如果后续反复出现同一类初始化、图表整理或日志汇总动作，再考虑补到 `scripts/`，不要先堆复杂自动化。
- 如果以后你更常说“实验记录”“边跑边记”“仿真日志”，优先调 frontmatter 和触发句，不先改主体流程。
