# 外部方法来源登记

## 作用

本页记录设计 `research-report` 技能时参考过的外部方法来源，以及实际采纳和排除的部分。它不是调研报告的参考资料，也不向正式报告提供事实、数字或引用。

这些来源不构成本技能的运行依赖。使用本技能时，不下载、不安装外部 CLI，也不照搬任何固定章节、页数、图件数量或咨询框架。

## 已采纳的方法

| 来源 | 参考内容 | 本技能中的处理 |
|---|---|---|
| [K-Dense market-research-reports](https://github.com/K-Dense-AI/scientific-agent-skills/blob/main/skills/market-research-reports/SKILL.md) | 来源记录、断言与证据范围的对应、冲突处理、引用审计 | 建立内部“来源—断言台账”；正式稿只显示与真实来源条目对应的脚注、尾注或 `[n]` 引用。 |
| [K-Dense literature-review](https://github.com/K-Dense-AI/scientific-agent-skills/blob/main/skills/literature-review/SKILL.md) | 检索记录、来源质量和主题综合 | 将来源质量、适用范围和冲突状态留在内部台账；多篇学术检索仍由 `paper-search` 负责。 |
| [199 Biotechnologies deep-research](https://github.com/199-biotechnologies/claude-deep-research-skill/blob/main/SKILL.md) | 逐断言核验和证据持久化 | 把每个关键事实或判断与具体来源、支持范围和正式引用位置对应起来。 |
| [ByteDance DeerFlow systematic-literature-review](https://github.com/bytedance/deer-flow/blob/main/skills/public/systematic-literature-review/SKILL.md) | 主题化综合与保留来源分歧 | 来源冲突未闭合时不进入正式报告，不用流畅措辞掩盖分歧。 |
| [Firecrawl deep-research](https://github.com/firecrawl/firecrawl-workflows/blob/main/skills/deep-research/SKILL.md) | 按资料类型路由和检查反证 | 把持续取证和资料路由交给 `baseline-research`；不引入 Firecrawl API 作为依赖。 |

## 明确不采用的做法

| 来源 | 不采用的原因 |
|---|---|
| [davila7 market-research-reports](https://github.com/davila7/claude-code-templates/blob/main/cli-tool/components/skills/scientific/market-research-reports/SKILL.md) | 强制长篇幅、固定图表、SWOT/PESTLE/Porter 和行动方案，会把报告重新推向模板化表达。 |
| [Weizhena research-report](https://github.com/Weizhena/Deep-Research-skills/blob/master/skills/research-codex-zh/research-report/SKILL.md) | 用不确定值占位会掩盖研究未闭合状态；本技能改为转入内部台账并继续取证。 |
| [ECC deep-research](https://github.com/affaan-m/ECC/blob/main/skills/deep-research/SKILL.md) | 固定执行摘要和行动要点不符合本技能“正式稿只写已闭合结论”的边界。 |

## 使用边界

- 以上链接仅用于追溯方法来源，不能作为某份调研报告的正式证据或参考文献。
- 外部仓库的 Star、安装量和内容会变化；需要再次比较候选技能时，应重新联网核验，而不是把本页当作实时排行榜。
- 吸收的是证据管理和写作边界，不是外部技能的措辞、模板或输出格式。
