---
name: paper-review
description: >-
  核对论文原文中的具体技术疑问及笔记表述，也负责 A/B/C 停稿审查、作者投稿前预检与模拟审稿，以及受邀审稿人的外部同行评审。用户问“这段总结准确吗”“这个指标对应哪里”“图表或公式是什么意思”时，按 source_check 只核对相关内容；普通论文总结和 Zotero 笔记读写由现有 Zotero 插件承接。用户要求按严重程度审稿、判断是否继续润色、投稿前预判审稿意见，或填写 EDAS/审稿表时进入对应完整审查模式。作者回复审稿意见或操作投稿系统不属于本 skill。最终 Submit 前的作者侧审查仍需可定位的 `pre_submission_review: pass`。
---

# 论文审查

## 作用

根据当前请求选择局部原文核对、停稿审查、投稿前把关或外部同行评审。

只有停稿审查把问题分成三类，再给出是否继续修改的结论：

- `A 类`：必须修改
- `B 类`：建议优化
- `C 类`：风格偏好

## 流程

1. 先读取请求和已有材料，确定是论文局部疑问还是完整文稿审查。
2. 判断用户角色和模式，不能把真实外部审稿当成普通原文核对或作者侧模拟审稿：
   - 原文核对（`source_check`）：用户要解释或核实论文中的技术关系、图表、公式、数值，或校正已有阅读笔记时，读取 [references/source-check.md](references/source-check.md)。直接回答相关问题；跳过第 3-6 步、A/B/C 输出和投稿审查门。需要 Zotero 读写时使用现有 Zotero 插件。
   - 日常审查（默认）：读取 [references/stopline-checklist.md](references/stopline-checklist.md) 作为统一审查口径，走下面第 3-6 步。
   - 投稿前把关：用户提到投稿检查、预判审稿、模拟审稿人，或投稿技能请求 `pre_submission_review` 时，改走 [references/submission-gauntlet.md](references/submission-gauntlet.md)（先 9 维预检后模拟审稿），目标刊口径参考 `journal-submission` 的期刊画像及当前官方说明。
   - 外部同行评审：用户是受邀审稿人，要评价他人投稿、填写 EDAS/评审表或生成作者可见与 TPC 意见时，读取 [references/external-peer-review.md](references/external-peer-review.md)，按会务表单和评分说明完成真实审稿草稿。
3. 先按独立根因聚类，再做 `A/B/C` 分类，避免同一问题重复记多次。
4. 优先识别 `A 类`，不要把单纯措辞偏好包装成严重问题，也不要把同一根因拆成多个新 `A`。
5. 审查结束后，明确给出：
   - `结论：继续修改`
   - 或 `结论：建议停止润色`
6. 如果用户随后要求继续改，只优先处理 `A 类` 和必要的 `B 类`，不要被 `C 类` 带进无休止润色。

当用户要求“无上下文读者测试”、稿件面向陌生读者，或文稿依赖大量前文背景时，可选读取
[references/reader-test.md](references/reader-test.md)。这是审查方法，不是自动阻断项；不把
用户材料发送到外部服务，也不把读者测试结果伪装成事实核查或投稿通过。

投稿前把关另输出机器可记录的审查门结果：存在阻断项或必要维度无法核验时为 `blocked`；只有全部阻断项关闭后才为 `pass`。`pass` 必须同时给出 `checked_at` 和能定位到稿件、报告或官方要求的非空 `evidence`，不得输出无证据的通过结论。

外部同行评审不使用 `A/B/C` 停稿结论，也不输出作者侧 `pre_submission_review`。先核对审稿授权、会务的 AI/保密政策、实际评分说明和可用材料；政策不允许 AI 辅助或尚未确认时，在读取或分析未公开稿件前停止。默认只在本地处理稿件，不把未公开内容、公式或可识别片段发送到搜索引擎或其他外部服务。

外部同行评审默认先生成中文审阅稿。用户确认评分和技术意见后，才把已确认内容译成英文；翻译阶段保持评分、事实、意见数量和严重程度不变，不重新开启技术评审。需要网页提交时，在完整英文记录之外再生成无 LaTeX、无段内硬换行的粘贴版。可复制并按会务字段调整的骨架位于：

- [assets/external-review-zh-template.md](assets/external-review-zh-template.md)
- [assets/external-review-en-template.md](assets/external-review-en-template.md)
- [assets/external-review-paste-ready-template.md](assets/external-review-paste-ready-template.md)

如果 Submission Policy 要求确认登记页与论文 PDF 的题目、作者或摘要一致，按
[references/external-peer-review.md](references/external-peer-review.md) 的逐字段方法核对。
只消除网页复制和 PDF 排版产生的差异；不能凭整体观感回答 `yes`，也不能用宽松归一化掩盖真实文字差异。

## 输出结构

停稿审查按下面结构输出；`source_check` 按问题给出简短结论、原文位置及必要的修订句：

```text
A 类：必须修改
- ...

B 类：建议优化
- ...

C 类：风格偏好
- ...

结论：继续修改 / 建议停止润色
理由：1 到 3 句
```

如果某一类没有问题，直接写 `无`。

如果 `A 类` 里有一个明显高于其他问题的首要阻塞项，可以额外写一行 `优先处理：...`；没有就不要机械补这行。

只有当用户明确要求与上一轮比较时，才讨论“是否新增 A 类”；如果当前上下文看不到上一轮 `A 类` 清单，就不要擅自做“新增/未新增”的结论。

## 审查规则

- `A 类` 指会影响目标达成、准确性、逻辑一致性、证据支撑、结构完整性或执行安全的问题。
- `B 类` 指能明显提升表达质量，但不影响当前正式交付的问题。
- `C 类` 指措辞、节奏、文风和口味差异。
- 只报告值得作者花时间处理的问题，不为显得细而堆低价值意见。
- 每条 `A 类` 至少要说明：问题本体、原文定位、对应的审查标准，以及为什么它是 `A` 而不是 `B`。
- 如果风险判断依赖外部法规、专利原文或其他未核验材料，要标清“需外部核验”，不要包装成已证实结论。
- 如果连续两轮都没有新增 `A 类`，而新增意见主要落在 `C 类`，默认倾向给出 `建议停止润色`。
- 如果问题根源是事实未定、证据不足、章节缺失或任务口径未统一，就不要继续做表层润色。

## 边界

- 不用于从零起草文稿。
- 不把“还能更顺”都算成继续修改的理由。
- 原文核对说明论文实际写了什么及其适用条件；独立科学论证按需转 `rigor-check`，合规或代理师审阅仍由相应专业流程承担。
- 用户如果只要求直接改稿，不强制先做长篇审查；这时做一个简短分级后即可进入改写。
- 作者收到审稿意见后要写 rebuttal 或 response letter 时，转到 `ieee-manuscript-edit`；处理投稿页面、决定信或返修提交时转到对应投稿 skill。
- 外部审稿意见始终是供用户本人核验的草稿；不代替用户的独立专业判断，不代填独立性声明，也不代为提交审稿表。
- 日常论文解读沿用 Zotero 工作流，不自动开展完整审稿、生成本地总结或整篇付费重跑。局部核对完成即可交付。

## 相关技能

- 学术协作总控：[../writing-router/SKILL.md](../writing-router/SKILL.md)
- 工程申报写作：[../project-writing/SKILL.md](../project-writing/SKILL.md)
- SCI/IEEE 论文精修与初稿收口：[../ieee-manuscript-edit/SKILL.md](../ieee-manuscript-edit/SKILL.md)
- 指标论证：[../target-feasibility/SKILL.md](../target-feasibility/SKILL.md)
- 选刊定位（投稿前把关的期刊口径参考）：[../journal-submission/references/journal-selection.md](../journal-submission/references/journal-selection.md)
- 通用投稿系统、决定信、返修提交和录用后事务：[../journal-submission/SKILL.md](../journal-submission/SKILL.md)
- 明确 IEEE 的投稿事务：[../journal-submission/SKILL.md](../journal-submission/SKILL.md)

## 相关文件

- 论文原文与笔记核对：[references/source-check.md](references/source-check.md)
- 停稿清单：[references/stopline-checklist.md](references/stopline-checklist.md)
- 投稿前把关（预检+模拟审稿）：[references/submission-gauntlet.md](references/submission-gauntlet.md)
- 外部同行评审：[references/external-peer-review.md](references/external-peer-review.md)
- 无上下文读者测试（可选）：[references/reader-test.md](references/reader-test.md)
- 触发边界测试：[references/trigger-evals.json](references/trigger-evals.json)
- 外部审稿行为回归：[evals/evals.json](evals/evals.json)

## 维护

- 这份 skill 只沉淀通用审查口径和停稿规则，不沉淀单项目事实或一次性结论。
- 如果它和 `ieee-manuscript-edit`、`writing-router` 等 skill 出现边界漂移，优先先改 `description` 和触发测试，再考虑扩正文。
