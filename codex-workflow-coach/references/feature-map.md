# Codex Workflow Coach Feature Map

## Purpose

把用户常见的 Codex 使用摩擦点，映射到最省脑力、最容易落地的动作。

## Decision Map

| 场景 | 优先动作 | 为什么 | 备注 |
| --- | --- | --- | --- |
| 只是当前这件事要做完，而且上下文已经在当前聊天里 | 留在当前聊天 | 少切换、少重复描述、上下文损失最小 | 除非明显需要隔离执行环境 |
| 想做只读审查、找风险、看相对 `main` 的变化 | `codex exec review` | 入口清晰，适合“找问题不改代码” | 更偏独立审查而不是对话式协作 |
| 上一轮已经做了一半，现在只是继续 | `codex exec resume --last` | 比重新描述需求更省认知负担 | 特别适合补测试、补收尾、补说明 |
| 任务会反复出现，而且判断标准相对稳定 | 建议 Codex app automation | 把重复解释变成周期任务 | 默认输出 `.md` 供用户确认，不要直接替用户做高影响修改 |
| 想做零额外负担的对话复盘 | 读取 `C:\Users\SanAn\.codex\sessions` 和 `archived_sessions` | 这是被动 transcript 来源，不要求用户手写 session note | 优先读 thread 名、用户消息和工具失败 |
| Windows / PowerShell / CLI 命令易因路径、编码或 quoting 出错 | 转 [../command-pattern-memory/SKILL.md](../command-pattern-memory/SKILL.md) | 先复用已经验证过的命令形态，比现场重写更稳 | 命令高风险时优先走这层 |
| 想看跨周、跨项目的重复问题 | 转 [../jineng-fupan/SKILL.md](../jineng-fupan/SKILL.md) | 它更适合基于 `runs/` 和报告做二层归纳 | 不要在当前 skill 里硬做重型复盘 |

## Weekly Review Heuristics

适合建议周度自动复盘的信号：

- 同类任务一周内反复出现 2 次以上
- 用户反复说“不想记提示词”“又忘了怎么说”
- 经常需要重新解释工作区、路径、输出格式
- 经常出现“本来应该续跑，却又从头开始”
- 经常在 Windows 命令、编码或路径上损失时间

## Report Guidance

周度报告优先写成短而可确认的 Markdown，而不是长篇流水账。

建议结构：

```text
# Codex 工作流周检 - <YYYY-MM-DD>
## 这次看了哪些内容
- 我看到了什么
- 我没看到什么

## 这周反复卡住的地方
- 反复出现的操作摩擦

## 下周最容易再出问题的地方
- 高概率容易再次出错的点

## 建议怎么调整工作流
- 只给 1 到 3 条建议

## 哪些重复任务值得以后定时处理
- 哪些任务值得做成定时检查

## 需要你确认的地方
- 哪些判断只是推断
```

## Evidence Limits

- `.codex/sessions` 与 `archived_sessions` 可作为被动对话证据源，不需要用户手写会话摘记。
- 只在本地 transcript 或其他产物里有可见证据时，才做较强结论。
- 如果某些工作发生在没有本地 transcript 的外部环境里，就降低置信度并明确说明。
- 周报的价值在于“提醒用户注意盲区”，不是伪装成完整审计。
