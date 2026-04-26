---
name: skill-hygiene-audit
description: 审计本地 skill 树的结构卫生、重复候选、名字漂移、路径漂移和加载来源。Use when 用户要确认当前到底加载了哪些 skill、查同名冲突、查目录名和 `name:` 对不上、分清 GitHub 源码、cc-switch 同步目录和 Codex 运行时目录，或做只读盘点；prefer this over `agent-maintenance-handbook` when 目标是执行一次具体审计，而不是阅读维护规则。
---

# Skill 卫生审计

## 作用

这份 skill 用来把本地 skill 环境查清楚，尤其是下面几类问题：

- 当前活跃 skill 列表
- 结构卫生问题
- 真重复候选
- 名字漂移
- 本地补充关系排除说明
- 边界重叠候选
- 路径漂移
- 空壳或损坏项

## 先分清三层

在这台机器上，排查 skill 问题时默认先区分这三层：

- 运行时入口：`C:\Users\SanAn\.codex\skills`
- 同步目录：`C:\Users\SanAn\.cc-switch\skills`
- 源码目录：`D:\BaiduSyncdisk\.agents\agents-skills-src`

如果用户问“现在到底加载了什么”，先看运行时入口；不要直接把源码目录当成当前已加载。

## 流程

1. 先判断用户到底想查哪一层：
   - 查“当前真的加载了哪些 skill”时，优先看运行时入口。
   - 查“面板里更新了，为什么没生效”时，再看同步目录和 `cc-switch.db`。
   - 查“以后该改哪一份”时，最后再回到源码目录。
2. 对目标根目录运行审计脚本：

```powershell
python scripts/audit_skill_tree.py scan --root <target-root> --reports-root <reports-root> --date <YYYY-MM-DD>
```

3. 再读取本轮产物：
   - `manifests/<date>/summary.json`
   - `weekly/<date>.md`
4. 汇报时先给出：
   - 当前活跃 skill
   - 真重复候选
   - 名字漂移
   - 路径漂移
   - 空壳或损坏项
5. 优先看 `blockers`、`建议动作` 和 `路径漂移`，再决定是否把具体修补工作交给 `skill-creator`。
6. 如果报告把 `custom + vendor` 判成本地补充关系，就保留两层，不把它误当成重复副本。

## 结果类型

- `当前活跃 skill`
  指本次扫描根目录里，实际会参与当前路由或加载判断的 skill。
- `结构卫生`
  指目录层级不对、`docs/` 里误放 skill、工作区快照混进活跃树等问题。
- `真重复候选`
  指活跃 skill 的 `name:` 归一化后冲突，或 `SKILL.md` 正文高度相似且职责也重合。
- `名字漂移`
  指目录名、数据库里的 `directory`、数据库里的显示名，和 `SKILL.md` 里的 `name:` 对不上。
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
- 不把源码目录直接当成“当前已加载 skill 列表”。
- 不把 cc-switch 面板显示名直接当成磁盘目录名。
- `archive/` 只作为辅助判断来源，不当作活跃 skill 来源。
- `boundary overlap` 默认只聚焦至少一侧属于本地活跃层的 pair；纯 `vendor <-> vendor` 相似度通常不作为本轮修补对象。
- 不自动跑市场搜索，也不替代 [../agent-maintenance-handbook/SKILL.md](../agent-maintenance-handbook/SKILL.md) 的规则说明角色。
- 不替代 `skill-creator` 的创建和改写工作。

## 输出

固定输出到 `<reports-root>`：

- `manifests/<date>/summary.json`
- `weekly/<date>.md`

默认汇报顺序是：

- 扫描范围
- 当前活跃 skill
- 真重复候选
- 名字漂移
- 路径漂移
- 空壳或损坏项
- 建议动作

建议动作只使用这些标签：

- `保留`
- `补边界`
- `补引用`
- `归档候选`
- `合并候选`
- `人工复核`

## 维护

- 如果路径、同步方式或启用链路变化，先更新 [references/skill-hygiene.md](references/skill-hygiene.md) 和脚本，再同步这里。
- 如果本地补充层写法变化，优先回查脚本里的识别规则和关键字，不先膨胀正文。
- 如果以后接 automation，优先复用现有 CLI 入口，不把调度信息写进 `SKILL.md`。
