---
name: jineng-fupan
description: 围绕本周新增的 Codex 本地对话 transcript 做跨项目技能复盘编排。Use when 用户要扫描 `%USERPROFILE%/.codex/sessions` 里的周内新对话、按项目归类、维护复盘索引、生成项目周报，或提炼跨项目可复用观察。
---

# 技能复盘

## 作用

这份 skill 把“本周新开的对话”变成可追踪、可提醒、可跨项目归纳的复盘入口。

它处理的是 transcript 周报编排，不是直接扫描代码运行产物。

## 流程

1. 先运行扫描脚本，建立本周清单：

```powershell
python scripts/retro_scan.py scan --root <projects-root> --reports-root <agents-root>/reports/skill-improver --date <YYYY-MM-DD>
```

脚本会读取：

- `%USERPROFILE%/.codex/sessions/`
- `%USERPROFILE%/.codex/archived_sessions/`

并筛出本周新增 session，再按 `cwd` 映射回 `<projects-root>` 下的项目。这里的 `--root` 表示你平时存放项目的总根目录，不预设固定盘符。

2. 读取本轮产物：
   - `manifests/<date>/analysis_queue.json`
   - `manifests/<date>/pending_queue.json`
   - `weekly/<date>.md`
3. 对 `analysis_queue.json` 里的每个 session，只读它自身 transcript，优先看：
   - `session_meta.cwd`
   - 用户消息
   - 工具失败样例
   - 线程名称
4. 按项目汇总本周重复出现的问题、高风险点、值得采纳的改法，以及仍需继续观察的事项。
5. 更新项目周报：
   `projects/<project-slug>/<date>/summary.md`
6. 只基于项目摘要生成跨项目观察：
   `cross-project/<date>.md`
7. 报告完成后执行收尾：

```powershell
python scripts/retro_scan.py finalize --reports-root <agents-root>/reports/skill-improver --date <YYYY-MM-DD>
```

8. 如果要更新处理状态，可执行：

```powershell
python scripts/retro_scan.py mark-action --reports-root <agents-root>/reports/skill-improver --run-dir <session_path> --status reviewed
python scripts/retro_scan.py mark-action --reports-root <agents-root>/reports/skill-improver --run-dir <session_path> --status adopted
python scripts/retro_scan.py mark-action --reports-root <agents-root>/reports/skill-improver --run-dir <session_path> --status dismissed
```

## 规则

- 不跨项目混读原始对话。
- `<projects-root>` 外的 session 不纳入本轮复盘。
- `pending_review` 且未变化的项，只做提醒，不重复长篇分析。
- 只有 2 个及以上项目重复出现的模式，才进入跨项目候选。
- 不自动修改任何 `SKILL.md`；这里只做整理、汇总和候选判断。

## 相关文件

- 工作流说明：[references/workflow.md](references/workflow.md)
- 扫描脚本：[scripts/retro_scan.py](scripts/retro_scan.py)

## 相关技能

- Codex 工作流教练：[../codex-workflow-coach/SKILL.md](../codex-workflow-coach/SKILL.md)
- 本地 skill 维护：[../skill-creator-local/SKILL.md](../skill-creator-local/SKILL.md)

## 维护

- 如果 transcript 结构变化，优先回查脚本对 `session_meta`、用户消息和工具输出的字段假设。
- 如果以后需要更正式的人审流，再扩状态字段，不把大量过程状态写回周报正文。
