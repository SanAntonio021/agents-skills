# 学术与申报工作流地图

更新时间：2026-04-27

这份文件给 `writing-router` 做路由参考。它不替代下游 skill，也不要求一次改多个 skill。

## 基本判断

先判断用户当前处在哪个阶段：

| 阶段 | 用户常见说法 | 推荐去向 |
|---|---|---|
| 问题澄清 | 不知道从哪写、方向还乱、帮我想清楚 | `brainstorming` 或 `baseline-research` |
| 前期调研 | 找材料、做基线、查代表作、补证据 | `baseline-research` |
| 文献下载 | 下载论文、补 PDF、维护 `paper_index.md` 论文索引 | `paper-download` |
| 单篇论文总结 | 读已有 PDF、整理单篇文献笔记、提取术语和关键信息 | `paper-summary` |
| 指标论证 | 这个指标站不站得住、口径怎么写 | `target-feasibility` |
| 工程申报正文 | 工程本子、建设内容、产业化、卡点 | `project-writing` |
| SCI/IEEE 草稿精修 | 中文改英文、图注、引用、单位、结论强度、润色 SCI 论文 | `ieee-manuscript-edit` |
| 纯英文句子质量审查 | 删废话、改被动、精简句子、检查用词一致 | `sentence-polish` |
| 停稿审查 | 帮我按严重程度审、还要不要改 | `paper-review` |
| 实验设计/证据评估 | 实验设计有没有问题、证据够不够、结论说过头没 | `rigor-check` |
| 局部精修 | 这一段怎么收口、老师批注怎么补 | `ieee-manuscript-edit` |
| 论文配图检查 | 图的标注不规范、配色不对、IEEE 图件规范 | `paper-figure-review` |
| 去 AI 写作痕迹 | 去掉 AI 味、让文字更自然 | `Humanizer-zh` |
| 在线搜文献 | 搜论文、查最新进展、找相关工作 | `research-lookup` |
| Word/模板交付 | 回填 Word、标黄、格式、目录 | `word-template` / `docx` |
| LaTeX 转换与投稿工程 | 转 LaTeX、IEEEtran、套期刊模板、BibTeX、编译报错、投稿打包 | `latex-paper` |

**ieee-manuscript-edit 和 sentence-polish 怎么分：**
- "润色这段 SCI 论文英文"或"帮我改英文还要校准术语" → `ieee-manuscript-edit`（涉及内容）
- "这段英文太冗余，帮我精简句子" → `sentence-polish`（只管句子质量）
- "这段英文太冗余，而且术语也要校准" → `ieee-manuscript-edit`（内容 + 句子同时有问题，优先大粒度）

若一句话同时命中多个阶段，优先选最阻塞阶段。通常顺序是：事实和证据未定先调研，指标不清先论证，已有稿件先审查，再进入精修。

## Imbad0202/academic-research-skills

本地镜像：
`D:\BaiduSyncdisk\04-agents\upstream\Imbad0202-academic-research-skills`

适合作为轻量学术流程样板。

### 建议吸收

| 上游模块 | 可吸收内容 | 本地承接 |
|---|---|---|
| `academic-pipeline` | 阶段门控、完整性检查、审稿-修改-复审闭环 | `writing-router` 做路由；必要时分发到下游 |
| `deep-research` | Socratic 问题澄清、source verification、gap analysis | `baseline-research` |
| `academic-paper` | 先大纲再成文、引用/图表一致性、修改回应 | `ieee-manuscript-edit` |
| `academic-paper-reviewer` | 多视角审稿、Devil's Advocate、re-review | `paper-review` |

### 不直接照搬

- 不直接引入它的完整 10 阶段流水线作为本地强制流程。
- 不把所有阶段门控写进 `writing-router` 正文。
- 不把台湾高教或通用学术写作口径套到工程申报。

## K-Dense-AI/scientific-agent-skills

本地镜像：
`D:\BaiduSyncdisk\04-agents\upstream\K-Dense-AI-scientific-agent-skills`

这是综合科学技能库，范围很大。默认只挑和太赫兹通信、工程硬件、科研写作、申报论证接近的部分。

### 第一批可参考

| 上游模块 | 可吸收内容 | 本地承接 |
|---|---|---|
| `peer-review` | 方法、统计、可复现性、报告规范检查表 | `paper-review` |
| `hypothesis-generation` | 现象 -> 假设 -> 预测 -> 验证实验 | `target-feasibility`、`lab-notebook` |
| `citation-management` | 引用元数据核验、DOI/BibTeX 一致性 | `paper-download`、`ieee-manuscript-edit` |
| `paper-lookup` | 数据库选择和跨库检索思路 | `paper-download`、`baseline-research` |
| `scientific-writing` | IMRaD、先大纲再成文、图表引用一致性 | `ieee-manuscript-edit` |
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

## 外部 skill 参考（暂不安装，留作扩展参考）

更新时间：2026-05-20

以下外部 skill 在市场搜索中值得关注，不是现在要用，是以后想扩展时知道去哪里找。

| 外部来源 | 值得关注的内容 | 适合补充本地哪一块 |
|----------|---------------|-------------------|
| Imbad0202/academic-research-skills | 4 个 skill 的写-审全链路，12-agent 写作 + 7-agent 审稿 | paper-review 的多视角审稿、ieee-manuscript-edit 的修改回应 |
| claesbackman/AI-research-feedback | 6-agent 期刊定向审稿 + grant review | paper-review 的期刊定向评审、未来的基金申请 skill |
| wanshuiyin grant-proposal | 9 个国际基金机构（NSF/NIH/NSFC/ERC 等）、3 种语言的基金申请 | 未来独立的 grant-writing skill |
| kgraph57/paper-writer-skill | 10 阶段全流程写稿，18 项 AI 写作痕迹清除模式 | Humanizer-zh 的英文版扩展 |

## 推荐节奏

第一步只维护本文件和 `writing-router` 的路由规则。

后续按真实任务触发：

- 调研收敛差：改 `baseline-research`
- 审稿不够狠：改 `paper-review`
- 英文论文精修不够稳：改 `ieee-manuscript-edit`
- 指标/实验解释不清：改 `target-feasibility` 或 `lab-notebook`
- 纯英文句子不够干净：改 `sentence-polish`
- 实验设计/证据评估不够深：改 `rigor-check`
