---
name: fangzhen-zhixing-moshi
description: 进入“改代码、重跑仿真或实验、看结果、继续迭代”的执行模式，并默认联动实验记录。Use when the user wants to rerun after code changes, continue a simulation or experiment, do ablation or parameter sweeps, or iterate while keeping a running record; prefer this over `codex-workflow-coach` when the goal is immediate execution rather than workflow advice.
---

# 仿真执行模式

## 作用

这个 skill 负责判断当前任务是否已经进入“边改边跑”的闭环，并在进入后默认联动记录层和执行层。

它不替代下游 skill，主要做两件事：

- 判断当前任务是不是迭代执行型仿真或实验
- 一旦成立，默认进入“执行中持续记录”的工作方式

## 触发场景

下面这些情况默认应触发本 skill：

- 改完代码立刻重跑仿真或实验
- 继续某轮实验、参数扫描或消融
- 跑一轮看看结果再决定下一步
- 继续调某个模型、脚本、测试链或流程
- 需要连续产生命令、日志、图表、截图或摘要文件

如果同一线程上一轮已经在跑仿真或实验，后面再次出现“继续”“再跑”“再扫”“再试”这类指令时，也默认继续使用本 skill。

## 进入后动作

1. 先确认当前任务是否属于“改代码并重复运行”的闭环。
2. 默认联动 [../fangzhen-shiyan-jilu/SKILL.md](../fangzhen-shiyan-jilu/SKILL.md)。
   - 有现成主记录就沿用。
   - 没有就建立一份稳定主记录，默认可用 `labbook.md`。
3. 对需要终端执行的步骤，优先参考：
   - [../command-pattern-memory/SKILL.md](../command-pattern-memory/SKILL.md)
   - [../zhongduan-zhixing-hulan/SKILL.md](../zhongduan-zhixing-hulan/SKILL.md)
4. 按“小步执行 + 小步记录”的节奏推进：
   - 动手前记本轮意图
   - 改完后记涉及文件和原因
   - 跑完后记命令、参数、结果和下一步
5. 本线程一旦进入该模式，默认继续更新同一份主记录，直到用户明确说停止记录。

## 默认行为

- 默认继续维护同一份主记录，不每轮新建一个 `.md`
- 默认把记录视为执行产物的一部分，而不是最后补写
- 默认优先落盘命令、参数、关键指标、图表路径和下一步动作

## 边界

- 不把所有编码任务都升级成仿真执行模式。
- 不要求用户每轮重复说“继续记录”。
- 不覆盖用户显式反指令。
- 不替代 [../fangzhen-shiyan-jilu/SKILL.md](../fangzhen-shiyan-jilu/SKILL.md) 的记录细则。
- 不替代正式论文写作、周报、跨项目复盘或 Word 排版 skill。

## 相关技能

- 执行期实验主记录：[../fangzhen-shiyan-jilu/SKILL.md](../fangzhen-shiyan-jilu/SKILL.md)
- Windows 命令模式复用：[../command-pattern-memory/SKILL.md](../command-pattern-memory/SKILL.md)
- Windows 终端执行护栏：[../zhongduan-zhixing-hulan/SKILL.md](../zhongduan-zhixing-hulan/SKILL.md)
- 工作流建议器：[../codex-workflow-coach/SKILL.md](../codex-workflow-coach/SKILL.md)

## 维护

- 触发稳定性优先依赖 frontmatter 里的 `description`。
- 如果未来误触发过多，优先收紧触发句和触发场景。
- 如果未来漏触发较多，优先补真实高频中文说法，不无限加正文解释。
