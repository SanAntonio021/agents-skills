---
name: duihua-jingyan-tiqu
description: 从当前对话中提炼可复用经验，判断应新建 skill、扩展现有 skill，还是无需落盘，并在创建前完成本地重合检查与 `find-skills-local` 外部复核。短触发词包括“经验提取”“提取经验”“沉淀经验”“经验转skill”。Use when 用户要从当前对话提炼经验、判断值不值得做成 skill，或比较新建和扩展哪个更合适；prefer this over `skill-creator-local` when 还停留在“先判断要不要做成 skill”阶段。
---

# 对话经验提取

## 作用

这份 skill 用来把一次对话里已经验证过的做法、边界、模板和触发词，沉淀成一个候选 skill。

它先做提炼和查重，再给出“值不值得新建”的判断。只有用户明确批准后，才进入正式创建或修改 skill。

## 流程

1. 从当前对话中抽取候选 skill 的最小事实集：
   - 反复出现的目标、输入、输出和成功标准
   - 已证明有复用价值的步骤、判断规则、触发短语和边界
   - 是否需要沉淀到 `scripts/`、`references/`、`assets/`
2. 先做本地重合检查：
   - 优先查 `skills/custom/`
   - 再查 `skills/vendor/`
   - 最后查根目录遗留 skill
   - 比较目标、触发条件、流程和边界，不只看名字
3. 再做外部复核：
   - 读取并遵循 [../find-skills-local/SKILL.md](../find-skills-local/SKILL.md)
   - 参考 `find-skills`
- 按 `<agents-root>\workflows\find-skills-local.md` 做官方基线查询和 GitHub 广域搜索
4. 给出决策：
   - `值得新建`
   - `更适合扩展现有 skill`
   - `暂不建议新建`
   - `无需新建，也无需落盘`
5. 创建前必须先向用户交付审查稿并暂停，至少包括：
   - 候选 skill 名称
   - 触发短语
   - frontmatter `description`
   - 主体结构提纲
   - 是否需要 `scripts/`、`references/`、`assets/`
   - 与本地和外部 skill 的重合结论
6. 只有用户明确批准后，才转入正式创建或更新：
   - 新建时遵循 `skill-creator` 规范，在 `skills/custom/` 下创建
   - 若更适合扩展现有 skill，就更新对应 skill，而不是重复新建
   - 如果动作已进入“本地同步 skill 正式创建、重构或校验”，再转到 `skill-creator-local`

## 决策口径

- `值得新建`
  本地和外部都没有足够覆盖，且本轮对话已经形成稳定可复用流程。
- `更适合扩展现有 skill`
  已有 skill 覆盖主流程，只缺局部规则、别名或边界补充。
- `暂不建议新建`
  经验仍然一次性、强依赖上下文，或与现有 skill 高度重复。
- `无需新建，也无需落盘`
  当前只是一般性判断，尚未形成稳定重复流程，现有本地 skill 或规则已经足够覆盖。

## 审核输出

默认按下面结构汇报：

```text
Candidate skill: <name>
Decision: 值得新建 | 更适合扩展现有 skill | 暂不建议新建 | 无需新建，也无需落盘

Why:
- <reason 1>
- <reason 2>

Duplicate check:
- Local overlap: <none / existing skill + difference>
- External overlap: <none / existing skill + difference>

Proposed triggers:
- <phrase 1>
- <phrase 2>

Proposed frontmatter description:
<description>

Proposed sections:
- <section 1>
- <section 2>
- <section 3>

Resources:
- scripts: <needed / no>
- references: <needed / no>
- assets: <needed / no>
```

如果结论是“无需新建，也无需落盘”，默认直接给一句明确结论，再补 1 到 2 句必要理由，不进入批准环节。

## 边界

- 不把一次性临时措辞直接包装成 skill，除非它已形成稳定可复用流程。
- 不因名字不同就判定值得新建，重点看目标、步骤和边界。
- 用户没批准前，不创建新目录，不写正式 skill 正文，也不改现有 skill 主体流程。
- 不跳过本地查重直接跑外部搜索，也不只做外部搜索忽略本地技能树。

## 维护

- 这份 skill 只负责提炼、查重、建议和审查，不替代 `find-skills-local` 的外部复核职责，也不替代 `skill-creator` 的创建规范。
- 当稳定触发短语、审查模板或判定标准变化时，优先更新这里和 `AGENTS.md` 的默认触发规则。
