---
name: skill-check
description: 审计本地 skill 树的结构卫生、重复候选、名字漂移、路径漂移和加载来源。Use when 用户要确认当前到底加载了哪些 skill、查同名冲突、查目录名和 `name:` 对不上、分清 GitHub 源码、cc-switch 同步目录和 Codex 运行时目录，或做只读盘点；prefer this over `agent-rules` when 目标是执行一次具体审计，而不是阅读维护规则。
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
4. 如果还要补充“市场安装 skill 的清单、残留目录或全局安装情况”，再按需调用补充脚本，不要把这一步默认混进每次审计。
5. 汇报时先给出：
   - 当前活跃 skill
   - 真重复候选
   - 名字漂移
   - 路径漂移
   - 空壳或损坏项
6. 优先看 `blockers`、`建议动作` 和 `路径漂移`，再决定是否把具体修补工作交给 `skill-creator`。
7. 如果报告把 `custom + vendor` 判成本地补充关系，就保留两层，不把它误当成重复副本。

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

## 合并候选判断

判断两个 skill 是否该合并时，不只看主题是否相近。

只有目标、输入、输出产物、执行方式和触发场景都高度重合，才标为 `合并候选`。

如果只是同属一个大主题，但产物或执行方式不同，优先标为 `边界重叠候选` 或 `保留`。例如：

- 论文文本精修和论文图件重画都属于论文工作，但一个处理文本，一个处理图件，不应直接合并。
- 台架测试和实验记录都属于实验工作，但一个执行测试，一个同步记录，不应直接合并。
- 指标论证和工程申报都可能服务同一项目，但一个判断指标是否站得住，一个写申报正文，不应直接合并。

`合并候选` 只用于真正减少重复且不会明显伤害触发准确性的情况。

详细分级和报告模板见：

- [references/finding-severity.md](references/finding-severity.md)
- [references/report-template.md](references/report-template.md)
- [references/skill-hygiene.md](references/skill-hygiene.md)
- [scripts/manage_market_skills.ps1](scripts/manage_market_skills.ps1)
- [scripts/run_codex_skill_ecosystem_audit.py](scripts/run_codex_skill_ecosystem_audit.py)

## 边界

- 只读审计，不自动移动、归档、删除或改写任何 `SKILL.md`。
- 不把源码目录直接当成“当前已加载 skill 列表”。
- 不把 cc-switch 面板显示名直接当成磁盘目录名。
- `archive/` 只作为辅助判断来源，不当作活跃 skill 来源。
- `boundary overlap` 默认只聚焦至少一侧属于本地活跃层的 pair；纯 `vendor <-> vendor` 相似度通常不作为本轮修补对象。
- 不自动跑市场搜索，也不替代 [../agent-rules/SKILL.md](../agent-rules/SKILL.md) 的规则说明角色。
- 不替代 `skill-creator` 的创建和改写工作。
- 这里保留市场安装检查脚本，但不把自己改成“自动更新器”；默认仍以只读审计为主。

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
