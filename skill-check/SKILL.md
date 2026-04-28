---
name: skill-check
description: 检查本地技能目录，确认 Codex 实际读取哪些技能，发现目录结构问题、重复或可合并技能、名字不一致、链接失效、空技能或坏技能。Use when 用户要确认当前加载了哪些 skill、查同名冲突、判断技能是否该合并、检查目录名和 `name:` 是否一致、分清 GitHub 源码、cc-switch 同步出来的目录和 Codex 实际读取的技能目录，或做只读盘点；prefer this over `agent-rules` when 目标是执行一次具体审计，而不是阅读维护规则。
---

# Skill 卫生审计

## 作用

这份 skill 用来查清本地技能目录，重点看这些问题：

- 当前实际会用到哪些技能
- 目录结构问题
- 真的重复技能
- 名字不一致
- 本地补充关系，不算重复
- 职责相近但不该直接合并
- 链接或路径失效
- 空技能或坏技能

## 先分清三类目录

在这台机器上，排查技能问题时先分清这三类目录：

- Codex 实际读取的技能目录：`C:\Users\SanAn\.codex\skills`
- cc-switch 同步出来的目录：`C:\Users\SanAn\.cc-switch\skills`
- 真正应该修改的源文件目录：`D:\BaiduSyncdisk\.agents\agents-skills-src`

用户问“现在到底加载了什么”时，先看 Codex 实际读取的技能目录；不要把源文件目录当成当前已加载列表。

## 流程

1. 先判断用户到底想查哪一层：
   - 查“当前真的加载了哪些 skill”时，优先看 Codex 实际读取的技能目录。
   - 查“面板里更新了，为什么没生效”时，再看 cc-switch 同步出来的目录和 `cc-switch.db`。
   - 查“以后该改哪一份”时，最后再回到源文件目录。
2. 扫描目标根目录：

```powershell
python scripts/audit_skill_tree.py scan --root <target-root> --reports-root <reports-root> --date <YYYY-MM-DD>
```

3. 再读取本轮产物：
   - `manifests/<date>/summary.json`
   - `weekly/<date>.md`
4. 如果还要查市场安装清单、残留目录或全局安装情况，再调用补充脚本；不要把这一步默认塞进每次审计。
5. 汇报时先给出：
   - 当前实际会用到的技能
   - 真的重复技能
   - 名字不一致
   - 链接或路径失效
   - 空技能或坏技能
6. 优先看严重问题、建议动作和链接失效，再决定是否把具体修补工作交给 `skill-creator`。
7. 如果报告显示“自建技能 + 外部技能”只是本地补充关系，就保留两层，不把它误当成重复副本。

## 结果类型

- `当前实际会用到的技能`
  指本次扫描目录里，实际会参与当前路由或加载判断的技能。
- `目录结构问题`
  指目录层级不对、`docs/` 里误放 skill、工作区快照混进活跃树等问题。
- `真的重复技能`
  指当前会用到的技能里，`name:` 归一化后冲突，或 `SKILL.md` 正文高度相似且职责也重合。
- `名字不一致`
  指目录名、数据库里的 `directory`、数据库里的显示名，和 `SKILL.md` 里的 `name:` 对不上。
- `本地补充关系，不算重复`
  指 `custom` 对 `vendor` 的本地补充、本地路由或接入层，这类不计入重复。
- `职责相近但不该直接合并`
  指描述和正文相似，但职责没有完全重合，不能直接当重复。
- `链接或路径失效`
  指绝对路径、相对链接、Related Skills 链接或工作流引用失效。
- `空技能或坏技能`
  指缺 `SKILL.md`、文件开头配置为空、正文为空，或关键结构损坏。

## 合并候选判断

判断两个 skill 是否该合并时，不只看主题是否相近。

只有目标、输入、输出产物、执行方式和触发场景都高度重合，才标为 `合并候选`。

如果只是同属一个大主题，但产物或执行方式不同，标为 `职责相近但不该直接合并` 或 `保留`。例如：

- 论文文本精修和论文图件重画都属于论文工作，但一个处理文本，一个处理图件，不应直接合并。
- 台架测试和实验记录都属于实验工作，但一个执行测试，一个同步记录，不应直接合并。
- 指标论证和工程申报都可能服务同一项目，但一个判断指标是否站得住，一个写申报正文，不应直接合并。

`合并候选` 只用于两件事明显重复、合并后又不会伤害触发准确性的情况。

详细分级和报告模板见：

- [references/finding-severity.md](references/finding-severity.md)
- [references/report-template.md](references/report-template.md)
- [references/skill-hygiene.md](references/skill-hygiene.md)
- [scripts/manage_market_skills.ps1](scripts/manage_market_skills.ps1)
- [scripts/run_codex_skill_ecosystem_audit.py](scripts/run_codex_skill_ecosystem_audit.py)

## 边界

- 只读审计，不自动移动、归档、删除或改写任何 `SKILL.md`。
- 不把源文件目录直接当成“当前已加载技能列表”。
- 不把 cc-switch 面板显示名直接当成磁盘目录名。
- `archive/` 只作为辅助判断来源，不当作活跃 skill 来源。
- `职责相近但不该直接合并` 默认只看至少一侧属于本地活跃层的组合；两个外部技能之间的相似通常不作为本轮修补对象。
- 不自动跑市场搜索，也不替代 [../agent-rules/SKILL.md](../agent-rules/SKILL.md) 的规则说明角色。
- 不替代 `skill-creator` 的创建和改写工作。
- 这里保留市场安装检查脚本，但不把自己改成“自动更新器”；默认仍以只读审计为主。

## 输出

固定输出到 `<reports-root>`：

- `manifests/<date>/summary.json`
- `weekly/<date>.md`

默认汇报顺序是：

- 扫描范围
- 当前实际会用到的技能
- 真的重复技能
- 名字不一致
- 链接或路径失效
- 空技能或坏技能
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
