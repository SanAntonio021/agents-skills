---
name: chat-notes
description: 用户要求从当前对话整理可复用经验、维护项目说明或改进已有技能时使用。先核对事实和现有规则，优先复用既有文件；一次性经验留在项目，不默认新建技能或扩展成清理任务。
---

# 对话经验整理

## 判断与执行

1. 读取当前请求、项目规则和实际修改。核实事实与现役入口，不能凭历史报错或单次失败推断规则缺口。
2. 优先更新已有文件。区分缺少规则、规则不完整与规则明确但未执行；最后一种不再增加同义规则。
3. 跨项目稳定复用的知识归入最相关的现有 Skill；一次性事实留在项目。只有现有文件确实不能承载时才新建。
4. 仅在本地依据不足或用户需要外部比较时检索上游，不强制每次查技能市场。
5. 给出具体可审阅的改动或差异。已有准确修改授权直接实施，不再请求一次“批准候选”；只讨论或缺少实质决定时先呈现建议。
6. 修改技能时使用 `skill-creator` 做与变更相称的检查。按 [skill-edit-followup.md](references/skill-edit-followup.md) 处理必要提交、定向同步和真实生效验证。

## 范围保护

- 只修改权威源码与本次准确文件；无关暂存、未提交内容及用户手工改动保持原样。
- 出现共享仓库并发或同文件混合改动时，按现有发布参考使用隔离工作区；不通过 stash、reset 或覆盖原工作区抽离内容。
- 整理经验不自动授权清理。用户已要求本轮清理且范围明确时，按 [cleanup-protocol.md](references/cleanup-protocol.md) 复用授权；模糊或任务外材料留在原处。
- 宿主生成的 MEMORY、rollout 等记忆文件只读；用户明确要求更新时仅使用宿主规定的输入入口。
- 已有准确授权持续有效；恢复、重试及辅助操作不另设固定口令或无信息的确认关口。

## 按需参考

- 经验落点：[skill-upgrade-review.md](references/skill-upgrade-review.md)
- 影响范围：[change-impact-mapping.md](references/change-impact-mapping.md)
- 项目入口：[project-entry-standard.md](references/project-entry-standard.md)
- 发布与并发：[skill-edit-followup.md](references/skill-edit-followup.md)
- 简短汇报：[report-format.md](references/report-format.md)

完成后说明实际改动和验证结果。没有值得记录的新信息时直接说明，不为完成整理而新增文件。
