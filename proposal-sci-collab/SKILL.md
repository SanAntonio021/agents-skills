---
name: proposal-sci-collab
description: 作为申报书与论文文章类任务的默认写作总路由，先判断任务类型和当前步骤，再把任务分流到最小必要的下游 skill。Use when 用户自然表达为写申报书、准备申报材料、写文章、准备论文、摘要、综述或投稿材料，且当前任务还没有被更具体的 custom skill 明确覆盖；明显属于工程建设类申报时优先转给 `engineering-proposal-scribe`，若目标是按严重程度审查现有文稿或判断是否继续修改，转给 `tinggao-shencha`。
---

# 学术与申报写作总路由

## 作用

这份 skill 是申报书与论文文章类任务的默认轻量入口。

它先判断“当前在写什么、现在做到哪一步”，再把任务分流到最小必要的下游 skill，而不是一上来全量展开相关能力。

## 路由

- 主写作层：
  - 中文工程申报：[../engineering-proposal-scribe/SKILL.md](../engineering-proposal-scribe/SKILL.md)
  - SCI 或科研写作：`scientific-writing`
- 过程层：
  - 讨论澄清与逐步确认：`brainstorming`
  - 前期调研与样本先行：[../jixian-diaoyan/SKILL.md](../jixian-diaoyan/SKILL.md)
  - 指标论证：[../zhibiao-lunzheng/SKILL.md](../zhibiao-lunzheng/SKILL.md)
  - 研究批判与证据强度判断：`scientific-critical-thinking`
  - 停稿审查：[../tinggao-shencha/SKILL.md](../tinggao-shencha/SKILL.md)
  - 初稿精修：[../caogao-jingxiu/SKILL.md](../caogao-jingxiu/SKILL.md)
- 支持层：
  - 论文下载：[../lunwen-xiazai/SKILL.md](../lunwen-xiazai/SKILL.md)
  - Word 模板格式化：[../word-muban-geshihua/SKILL.md](../word-muban-geshihua/SKILL.md)

## 流程

1. 先判断任务类型：工程申报、一般申报、论文文章，还是仅处在下载文献、指标论证、停稿审查、初稿精修、Word 格式化这些局部步骤。
2. 再判断当前步骤：前期调研、结构搭建、正文写作、指标收紧、审查停稿、精修抛光，还是格式交付。
3. 如果表达还不足以区分任务类型或当前步骤，只追问一个最阻塞的问题；如果已经够清楚，直接路由，不为稳妥重复开场。
4. 路由时默认只带一个主写作 skill；过程层和支持层 skill 只在当前步骤明显需要时再补。
5. 一旦当前线程已经确定任务类型和当前步骤，后续默认沿用，不要求用户每轮重复声明；只有用户明确换任务或换步骤时才切换。
6. 如果对象是已有专利草稿，且用户意图是“审查 / 评审 / 是否继续修改 / 按严重程度分类指出问题”，优先转到 [../tinggao-shencha/SKILL.md](../tinggao-shencha/SKILL.md)。
7. 只有在任务口径和当前步骤已形成共识，或用户明确要求直接起草时，才进入正式文本输出。
8. 对老师修改稿、标黄文档或批注 `Word`，先提取标注内容并形成“原文 + 建议补写”的对照稿，不直接改正文。
9. 多轮修订优先保持单一主稿和单一对照稿，减少版本分叉；文字未确认前，不反复导出多个 `Word` 版本。
10. 需要回填 `Word` 时，先确认文字，再处理颜色标记和版式；默认另存新文件，保留原始标注内容不动。
11. 如果任务已经缩到论文某个实验结果、图注或方法小节的多轮收口，且证据边界和技术口径已经定住，优先转入 [../caogao-jingxiu/SKILL.md](../caogao-jingxiu/SKILL.md) 做局部精修，不再把它当成重新起草整节。
12. 对实验结果类小节，转入精修前先检查 6 件事：论题是否已经收紧、结果段和方法段是否分工、关键参数是否与图中可观测量一一对应、代表性指标是否说明选择依据、术语是否按层级分工统一、英文是否需要按目标期刊口气二次重写。

## 边界

- 不替代已明确命中的更具体下游 skill。
- 任务已明显属于工程申报时，优先转到 [../engineering-proposal-scribe/SKILL.md](../engineering-proposal-scribe/SKILL.md)。
- 如果当前任务只是在补文献、下载 PDF 或整理 Word 模板，不接管支持层 skill 的主场。
- 核心任务是指标论证本身时，优先转到 [../zhibiao-lunzheng/SKILL.md](../zhibiao-lunzheng/SKILL.md)。
- 用户显式使用 `/21`、`二一` 或 `Consultant / Critic / Scribe` 这类说法时，也仍在当前任务里直接做高压缩收方向、压方案或定向写作，不再切独立模式 skill。
- 只有润色已有初稿时，不接管 [../caogao-jingxiu/SKILL.md](../caogao-jingxiu/SKILL.md)。
- 不把“相关 skill 很多”理解成“一次全带上”；默认只补当前步骤最相关的少量 skill。
- 任务类型已经确定后，不因为用户后续一句短话就擅自改写整个任务方向；确有歧义时，再补问一句。
- 不把老师批注直接当成最终正文；需先与用户确认补写口径，再决定是否并回主稿。
- 不在未确认前覆盖原始 `Word`；回填默认使用新文件保存补写结果。
- 对已经确定证据边界的实验段落，不反复回到“重搭结构”模式；优先做局部收口、术语统一和图文对齐。
- 不把局部实验段落的成熟收口经验再拆成新的写作主 skill；优先并入这里和 [../caogao-jingxiu/SKILL.md](../caogao-jingxiu/SKILL.md)。

## 维护

- 保持它是轻量总路由，不把具体写作细则和单项目结论堆进来。
- 当默认学术协作路由变化时，优先更新这里的分流边界。
- 写作入口词、持续状态和步骤分流规则优先收口在这里；具体写作细节继续放在下游写作 skill。
- 老师修改稿的提取、对照确认、回填标色流程，只保留编排层规则，不把局部经验扩成第二套写作主流程。
- 论文实验段落、图注和方法小节的多轮收口经验，优先沉淀成“何时转精修、精修前检查什么”的路由规则，不在这里堆具体句式。
