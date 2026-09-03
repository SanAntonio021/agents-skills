---
name: ieee-manuscript-edit
description: 中文或英文科学与工程论文的起草、精修和终稿文字审校，也处理摘要、引言、方法、结果、结论、图注、Cover Letter 与 Response Letter 的正文。Use when 用户要改中文论文、英文 SCI/IEEE 论文、中文改英文、删论文套话、保护实验事实，或做终稿规范检查；先区分 zh_paper、en_paper、final_audit，只加载当前语言规则。整体投稿前停稿审查转 paper-review，LaTeX 工程转 latex-paper，投稿事务转 journal-submission 或 ieee-journal-submission。
metadata:
  version: "2.0.0"
---

# 科学与工程论文写作

## 入口与加载

从 [writing-router](../writing-router/SKILL.md) 接收：

- `document_type=paper`
- `mode=zh_paper|en_paper|final_audit`
- `edit_scope`、`language`、`loaded_refs`

所有模式读取 [共同质量规则](../humanizer-zh/references/common-quality.md)。完整草稿、结构重写、终稿审校和 `audit_only` 再读取 [AI 气味目录](../humanizer-zh/references/ai-smell-catalog.md)。

| 模式 | 必读 |
|---|---|
| `zh_paper` | [中文论文](references/chinese-paper.md) |
| `en_paper` | [英文论文](references/english-paper.md) |
| `final_audit` | [终稿审校](references/final-audit.md) + 当前正文语言对应的上面一份 |

中文论文不得加载英文写作细则，英文论文不得加载中文写作细则。只有用户明确要求同时核对中英文两版时，`language=mixed` 才读取两份，并分别记录范围。

私有样稿入口为 `D:\BaiduSyncdisk\.agents\writing-profile\index.md`。只有 `paper` 样稿获批时才读；中文任务只看其中中文样稿，英文任务只看英文样稿。公开技能不保存个人论文段落。

## 共同红线

- 数值、单位、公式、变量、LaTeX 命令、设备、频率、带宽、误码率、EVM、SNR、相位噪声、样本量和统计量保持可回查。
- 文献、DOI、citation key、实验条件和性能比较不得补造。
- 引用与它支撑的论点保持相邻关系。
- 结论强度跟数据一致。单一装置、单次实验或有限条件不能改成普遍结论。
- 摘要、正文、图注和表注是不同缩写作用域；是否需要定义按当前作用域实际复用判断。
- 术语先固定再润色，不为避重更换同一技术对象的名称。
- 否定和限定可能承担科学边界。气味命中后先判断，不能自动删除或反转。

## 流程

1. 锁定当前文件、语言、章节、目标期刊或通用文体以及用户允许的改动范围。
2. 建立受保护事实清单和“论点—证据—章节功能”关系。
3. 材料不足时只修能确认的表达；缺实验事实、比较条件或引用时列出缺项，不替作者补结论。
4. 按中文或英文规则处理章节职责、信息顺序和句子。
5. 核对公式、数字、单位、引用、图表和缩写。
6. 完整稿再按气味目录检查空话、同义反复、伪转折、状态升级和机械对称；学术结构本身不算 AI 味。
7. 交付前用 `style-vocab` 检查对应语言的通用表、论文表和术语表。该步骤只做软审计，不重复调用通用改写。

## 按需参考

只有当前任务确实需要时才加载：

- 独立英文句子审查：[Sainani 五轮检查](references/sainani-sentence-review.md)。
- IEEE 结构、引用和图表：[IEEE 结构与风格](references/ieee-structure-and-style.md)。
- 目标 IEEE 模板：[官方模板缓存](references/ieee-official-template-cache.md)。
- 术语长期维护：[写作记忆结构](references/writing-memory-schema.md)。
- 分节重写：[分节审查](references/section-by-section-review.md)。

目标期刊或会议未知时，只能称“通用科学与工程论文精修”。具体模板符合性必须依据用户给出的模板、官方作者指南或技能内对应官方模板。

## `audit_only`

保持只读，先输出“论点—证据—章节功能”表，再按影响列问题。至少检查：

- 摘要、正文和结论是否无理由重复整段内容；
- 方法条件是否足以支撑结果和比较；
- 图表中的数字与正文是否一致；
- 引用是否实际支撑附近论点；
- 计划、仿真、计算和实测状态是否被升级；
- 中英文版本是否在用户要求的范围内保持事实一致。

虚构数据或引用、公式含义变化、跨节事实矛盾、无理由整段重复和状态升级直接判 `fail`。不要在只审任务中顺手生成全文改写。

## 输出

- 文件任务：在用户指定范围内修改文件，回复只写修改位置、关键变化和仍需确认的事实。
- 局部文本：给修改稿；理由只保留会影响事实、术语或作者选择的项目。
- 对比审查：按位置给原文、建议和事实风险，不为展示工作量列纯偏好修改。
- `TRACE_WRITING_CONTEXT=1` 时附实际 `loaded_refs`；普通交付不展示内部加载记录。

## 文件与投稿边界

实际写入 `.md` 或 `.tex` 前执行 [文稿版本保护](../writing-router/references/document-version-protection.md)。Word 在执行 [Markdown 到 DOCX 交接契约](../writing-router/references/markdown-docx-contract.md) 后交给 `docx`；LaTeX 模板、BibTeX 和编译交给 `latex-paper`。整体投稿前审查和最终 Submit 门交给 `paper-review`；投稿系统操作交给对应投稿技能。

## 完成条件

- 科学事实、结论强度、公式、数字、单位和引用关系未漂移；
- 当前章节完成自己的功能，没有靠摘要式重复填充；
- 术语和缩写作用域一致；
- 只加载当前语言和任务需要的参考；
- `loaded_refs` 与实际读取一致，继续改写已无明确收益。
