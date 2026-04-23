---
name: skill-hygiene-audit
description: 审计本地 synced skill 目录的结构卫生、重复候选、边界重叠、路径漂移和归档候选。Use when 用户要复核 `D:\BaiduSyncdisk\.agents\skills` 的整体健康度、查重、查坏链路或做只读盘点；prefer this over `agent-maintenance-handbook` when 目标是执行一次具体审计，而不是阅读维护规则。
---

# Skill 卫生审计

## 作用

这份 skill 把 `skills/` 目录的卫生检查收成一个稳定的只读入口。

它负责产出以下几类结果：

- 结构卫生问题
- 真重复候选
- 本地补充关系排除说明
- 边界重叠候选
- 路径漂移
- 空壳或损坏项

## 流程

1. 先运行审计脚本：

```powershell
python scripts/audit_skill_tree.py scan --root D:/BaiduSyncdisk/.agents/skills --reports-root D:/BaiduSyncdisk/.agents/reports/skill-hygiene --date <YYYY-MM-DD>
```

2. 再读取本轮产物：
   - `manifests/<date>/summary.json`
   - `weekly/<date>.md`
3. 优先看 `blockers`、`建议动作` 和 `路径漂移`，再决定是否把具体修补工作交给 [../skill-creator-local/SKILL.md](../skill-creator-local/SKILL.md)。
4. 如果报告把 `custom + vendor` 判成本地补充关系，就保留两层，不把它误当成重复副本。

## 结果类型

- `结构卫生`
  指根目录遗留活跃 skill、`docs/` 里误放 skill、层级异常等问题。
- `真重复候选`
  指归一化名称冲突，或 `SKILL.md` 正文高度相似且职责也重合。
- `本地补充关系排除`
  指 `custom` 对 `vendor` 的本地补充、本地路由或接入层，这类不计入重复。
- `边界重叠候选`
  指描述和正文相似，但更像职责没收紧，而不是同一份 skill。
- `路径漂移`
  指绝对路径、相对链接、Related Skills 链接或工作流引用失效。
- `空壳或损坏项`
  指缺 `SKILL.md`、frontmatter 空、正文空，或关键结构损坏。

详细分级和报告模板见：

- [references/finding-severity.md](references/finding-severity.md)
- [references/report-template.md](references/report-template.md)
- [references/skill-hygiene.md](references/skill-hygiene.md)

## 边界

- 只读审计，不自动移动、归档、删除或改写任何 `SKILL.md`。
- `archive/` 只作为辅助判断来源，不当作活跃 skill 来源。
- `boundary overlap` 默认只聚焦至少一侧属于本地活跃层的 pair；纯 `vendor <-> vendor` 相似度通常不作为本轮修补对象。
- 不自动跑市场搜索，也不替代 [../agent-maintenance-handbook/SKILL.md](../agent-maintenance-handbook/SKILL.md) 的规则说明角色。
- 不替代 [../skill-creator-local/SKILL.md](../skill-creator-local/SKILL.md) 的创建和改写工作。

## 输出

固定输出到 `D:\BaiduSyncdisk\.agents\reports\skill-hygiene`：

- `manifests/<date>/summary.json`
- `weekly/<date>.md`

建议动作只使用这些标签：

- `保留`
- `补边界`
- `补引用`
- `归档候选`
- `合并候选`
- `人工复核`

## 维护

- 如果 `custom/vendor/archive/docs` 的目录规则变化，先更新 [references/skill-hygiene.md](references/skill-hygiene.md) 和脚本，再同步这里。
- 如果本地补充层写法变化，优先回查脚本里的识别规则和关键字，不先膨胀正文。
- 如果以后接 automation，优先复用现有 CLI 入口，不把调度信息写进 `SKILL.md`。
