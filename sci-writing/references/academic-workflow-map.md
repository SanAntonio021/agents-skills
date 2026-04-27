# 学术与申报工作流地图

更新时间：2026-04-27

这份文件给 `sci-writing` 做路由参考。它不替代下游 skill，也不要求一次改多个 skill。

## 基本判断

先判断用户当前处在哪个阶段：

| 阶段 | 用户常见说法 | 推荐去向 |
|---|---|---|
| 问题澄清 | 不知道从哪写、方向还乱、帮我想清楚 | `brainstorming` 或 `baseline-check` |
| 前期调研 | 找材料、做基线、查代表作、补证据 | `baseline-check` |
| 文献下载与单篇总结 | 下载论文、补 PDF、整理索引、整理单篇文献笔记 | `paper-reading` |
| 指标论证 | 这个指标站不站得住、口径怎么写 | `target-check` |
| 工程申报正文 | 工程本子、建设内容、产业化、卡点 | `project-writing` |
| SCI/IEEE 草稿精修 | 中文改英文、图注、引用、单位、结论强度 | `sci-paper-edit` |
| 停稿审查 | 帮我按严重程度审、还要不要改 | `paper-review` |
| 局部精修 | 这一段怎么收口、老师批注怎么补 | `sci-paper-edit` |
| Word/模板交付 | 回填 Word、标黄、格式、目录 | `word-template` / `docx` |

若一句话同时命中多个阶段，优先选最阻塞阶段。通常顺序是：事实和证据未定先调研，指标不清先论证，已有稿件先审查，再进入精修。

## Imbad0202/academic-research-skills

本地镜像：
`D:\BaiduSyncdisk\.agents\upstream-skill-sources\Imbad0202-academic-research-skills`

适合作为轻量学术流程样板。

### 建议吸收

| 上游模块 | 可吸收内容 | 本地承接 |
|---|---|---|
| `academic-pipeline` | 阶段门控、完整性检查、审稿-修改-复审闭环 | `sci-writing` 做路由；必要时分发到下游 |
| `deep-research` | Socratic 问题澄清、source verification、gap analysis | `baseline-check` |
| `academic-paper` | 先大纲再成文、引用/图表一致性、修改回应 | `sci-paper-edit` |
| `academic-paper-reviewer` | 多视角审稿、Devil's Advocate、re-review | `paper-review` |

### 不直接照搬

- 不直接引入它的完整 10 阶段流水线作为本地强制流程。
- 不把所有阶段门控写进 `sci-writing` 正文。
- 不把台湾高教或通用学术写作口径套到工程申报。

## K-Dense-AI/scientific-agent-skills

本地镜像：
`D:\BaiduSyncdisk\.agents\upstream-skill-sources\K-Dense-AI-scientific-agent-skills`

这是综合科学技能库，范围很大。默认只挑和太赫兹通信、工程硬件、科研写作、申报论证接近的部分。

### 第一批可参考

| 上游模块 | 可吸收内容 | 本地承接 |
|---|---|---|
| `peer-review` | 方法、统计、可复现性、报告规范检查表 | `paper-review` |
| `hypothesis-generation` | 现象 -> 假设 -> 预测 -> 验证实验 | `target-check`、`simulation-log` |
| `citation-management` | 引用元数据核验、DOI/BibTeX 一致性 | `paper-reading`、`sci-paper-edit` |
| `paper-lookup` | 数据库选择和跨库检索思路 | `paper-reading`、`baseline-check` |
| `scientific-writing` | IMRaD、先大纲再成文、图表引用一致性 | `sci-paper-edit` |
| `research-grants` | significance / innovation / feasibility 框架 | `project-writing`，需改成国内工程申报口径 |
| `matlab`、`matplotlib`、`statistical-analysis` | 实验数据处理、绘图、统计报告模板 | 暂存，等有太赫兹实验数据处理 skill 时再用 |

### 默认不吸收

- 生物、医学、化学、云实验室、药物筛选、基因组学等远离当前学科的技能。
- 需要云端计算、外部 API、安装复杂依赖、读取环境变量或上传数据的技能。
- 强制生成大量 AI 图片、图形摘要或装饰性图的规则。

## 吸收规则

1. 先判断这次任务卡在哪个阶段。
2. 只改一个最相关的本地 skill。
3. 上游内容只吸收结构、检查清单和边界判断；不要整段照搬。
4. 直接复制或深度改写时，保留来源和许可证说明。
5. 如果只是未来可能有用，记录在这份地图里，不马上改下游。

## 推荐节奏

第一步只维护本文件和 `sci-writing` 的路由规则。

后续按真实任务触发：

- 调研收敛差：改 `baseline-check`
- 审稿不够狠：改 `paper-review`
- 英文论文精修不够稳：改 `sci-paper-edit`
- 指标/实验解释不清：改 `target-check` 或 `simulation-log`
