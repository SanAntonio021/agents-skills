---
name: codex-workflow-coach
description: 根据当前任务、已暴露的使用习惯和本地可见证据，给出少量高收益的 Codex 工作流建议，并在需要时生成周度复盘。Use when the user asks how to use Codex more effectively, whether to stay in the current chat or switch to `codex exec/review/resume`, or wants a recurring Codex workflow review; prefer this over `codex-cli-local` when the goal is workflow advice rather than direct CLI execution.
---

# Codex 工作流教练

## 作用

这个 skill 面向“怎么更省力地使用 Codex”，而不是直接帮用户执行某条命令。

目标不是堆一堆提示词技巧，而是基于真实证据给出 1 到 3 条最值得优先调整的工作流建议。

## 证据顺序

默认按下面的顺序取证，并说明证据强弱：

1. 当前对话里用户自己暴露的习惯、卡点和偏好
2. `%USERPROFILE%/.codex/sessions/` 与 `archived_sessions/` 里的本地会话
3. `session_index.jsonl` 与 `history.jsonl`
4. 本地可见的运行产物、报告、失败日志和相关文件
5. 已稳定重复出现的工作流模式
6. 轻量推断

证据不足时，要直接说“不足”，不要假装已经看出了长期规律。

## 流程

1. 先识别当前摩擦点，比如：
   - 反复新开线程导致上下文丢失
   - 明明适合 `resume --last` 却总是重开
   - 明明适合 `review` 却仍在当前线程手工审
   - Windows 命令、路径或编码问题反复拖慢执行
2. 只收集这次判断必要的最小证据，不做重型盘点。
3. 用 [references/feature-map.md](references/feature-map.md) 把问题映射到合适的 Codex 能力或相邻 skill。
4. 默认只输出 1 到 3 条建议，按“收益高且最容易采纳”排序。
5. 如果用户要周度复盘，再进入周检模式，而不是默认切成长期回顾。

## 周检模式

当用户想看每周的高频问题时，优先这样做：

1. 明确这次看哪些证据范围。
2. 识别重复摩擦点，而不是堆流水账。
3. 给出“高概率问题点”，不把推断写成定论。
4. 报告里保留“待你确认”部分。

默认周报脚本：

- [scripts/generate_weekly_review.py](scripts/generate_weekly_review.py)

默认周报目录：

- `<agents-root>/reports/codex-workflow-coach/`

## 输出格式

交互式建议默认回答：

- 我看到了什么
- 最值得优先改的地方
- 为什么适合你
- 下一步怎么做
- 下次可以直接怎么说

周度复盘默认回答：

- 这次看了哪些内容
- 这周反复卡住的地方
- 下周最容易再出问题的地方
- 建议怎么调整工作流
- 哪些地方还需要你确认

## 边界

- 不把这里做成“提示词大全”。
- 不把这里当 `codex-cli-local` 的替身。
- 证据不足时，不声称已经掌握用户的长期习惯。
- 不自动改其他 `SKILL.md`、automation 或工作区文件，除非用户明确要我动手。
- 用户只是想立刻完成当前任务时，优先直接解决任务，不强行切成复盘对话。

## 相关技能

- 直接 CLI 执行入口：[../codex-cli-local/SKILL.md](../codex-cli-local/SKILL.md)
- Windows 命令模式复用：[../command-pattern-memory/SKILL.md](../command-pattern-memory/SKILL.md)
- 跨项目运行产物复盘：[../jineng-fupan/SKILL.md](../jineng-fupan/SKILL.md)
- 当前对话经验沉淀：[../duihua-jingyan-tiqu/SKILL.md](../duihua-jingyan-tiqu/SKILL.md)

## 相关文件

- 决策映射表：[references/feature-map.md](references/feature-map.md)
- 周报脚本：[scripts/generate_weekly_review.py](scripts/generate_weekly_review.py)

## 维护

- 保持它是“个人工作流教练”，不是通用效率工具箱。
- `review`、`resume`、automation 或本地产物形态变化时，优先复查映射表。
- 新建议模式优先补到 `references/feature-map.md`，不把主文件堆成话术清单。
