---
name: writing-router
description: 中文写作与通用编辑的默认入口。Use when 用户要撰写、重写、润色或审查项目书、技术方案、会前技术交流稿、系统说明、测试与结果分析、调研报告、会议纪要、中文或英文论文，普通中文去 AI 味、删废话，以及无法直接归类的中文材料；也用于先讨论结构、分批确认正文、选择本地或飞书主稿，以及确定写作模式、修改范围、语言和实际加载规则。投稿事务、论文停稿审查、文献检索和单纯文件排版仍转给对应专门技能。
---

# 中文正式写作总路由

## 目标

确定文稿类型、本轮修改范围和协作方式，选择一个主文体技能；普通中文由本入口直接处理。已有决定与准确授权继续沿用。

## 原文保留操作

用户明确要求正文逐字不动、仅在开头加标题或末尾追加给定文字时，按[原文保留编辑](references/exact-edit.md)直接拼接并校验。本地 UTF-8 文稿使用其中的工具生成新文件，不重新生成或润色受保护正文；其他写作任务沿用下列流程。

## 写作上下文

开始正文工作前，在任务内部确定以下字段；文稿、范围和阶段未变时沿用，变化时只更新相关项，不另建记录文件。普通交付不展示这段记录。评测提示包含 `TRACE_WRITING_CONTEXT=1` 时，才在文末输出同名 JSON 对象。

| 字段 | 允许值 |
|---|---|
| `document_type` | `project`、`technical`、`research_report`、`meeting_notes`、`paper`、`general` |
| `mode` | 使用下表中与文稿类型对应的值 |
| `edit_scope` | `draft`、`structural`、`bounded`、`in_place`、`audit_only` |
| `language` | `zh`、`en`、`mixed` |
| `loaded_refs` | 本轮实际读取过的规则和样稿路径；不得登记“准备读取”或凭规则名称猜测 |

`edit_scope` 的含义：

- `draft`：从材料起草正文。
- `structural`：允许调整章节、段落职责和信息顺序。
- `bounded`：只改用户指定章节、段落或问题。
- `in_place`：保留结构和作者声音，只做必要的原位修改。
- `audit_only`：只审不改，按共同质量规则在对话中分点报告问题。

## 两级路由

| `document_type` | `mode` | 主技能 |
|---|---|---|
| `project` | `proposal`、`expert_reply`、`final_audit` | [project-writing](../project-writing/SKILL.md) |
| `technical` | `technical_scheme`、`technical_exchange`、`system_description`、`test_result_analysis` | [technical-writing](../technical-writing/SKILL.md) |
| `research_report` | `evidence_report`、`decision_report`、`final_audit` | [research-report](../research-report/SKILL.md) |
| `meeting_notes` | `discussion`、`action`、`mixed` | [meeting-notes](../meeting-notes/SKILL.md) |
| `paper` | `zh_paper`、`en_paper`、`final_audit` | [ieee-manuscript-edit](../ieee-manuscript-edit/SKILL.md) |
| `general` | `general_edit` | 本技能的通用编辑流程 |

判断顺序：

1. 用户明确说出的文稿类型、用途和读者。
2. 原文件的栏目、模板和内容职责。
3. 仍无法区分且会改变产物时，只问一个最关键的问题；不影响实质结果时按最窄范围继续。

会前方案讨论稿、技术交流材料或待讨论问题清单，目标是区分已有条件、会上决定和另行工作时，使用 `document_type=technical`、`mode=technical_exchange`。会议已经结束，任务是整理实际发言、结论和行动项时，使用 `meeting_notes`。

正式文稿进入对应文体技能；普通中文直接在本技能完成，不递归路由。

## 规则优先级

按共同质量规则的“优先级”处理冲突；事实与关系保护、必要复述、审查输出和停笔条件均以该参考为准，文体技能补充专业要求。

## 最小加载规则

以下要求同样适用于直接调用文体技能；按其现有引用进入共同参考，不必再绕回总路由。实际读取的路径记入 `loaded_refs`；同任务材料与规则未变时复用，已变化或无法确认读过时补读必要文件。

1. 建立写作上下文后、处理正文前，读取[文稿协作](references/collaborative-writing.md)，将实际路径记入 `loaded_refs`，据此选择直接处理或分批协作，不另加确认关口。
2. 实际读取路由表选定的主技能及本轮所需参考；路由表不能代替文体规则。`general_edit` 不加载另一个写作入口。论文和 `final_audit` 只读当前稿件语言对应的细则。
3. 各类正文都读取[共同质量规则](references/common-quality.md)。中文正文首次起草、续写、局部修改或审查前，按其中“中文正文展示前检查”读取 [AI 气味目录](references/ai-smell-catalog.md)和 `style-vocab` 适用词表，逐批检查；混合稿只对中文部分执行。英文在完整草稿、结构重写、终稿审校或 `audit_only` 时读取气味目录，沿用当前文体的检查时机。
4. 个人样稿按共同质量规则的“个人样稿”读取当前文体已批准的材料；完整正式稿按 `style-vocab` 执行术语与正式词表审计。已经完成的共同质量检查传递给后续技能，不重复通用改写。
5. 实际写入本地 `.md`、`.tex` 及必要源文件前读取[文稿版本保护](references/document-version-protection.md)；只读审查和聊天内改句不触发。Word 转换时读取[Markdown 到 DOCX 交接契约](references/markdown-docx-contract.md)，由 `docx` 核对当前材料并处理交付。

## 通用流程

1. 锁定当前主稿、来源、模板、交付范围和受保护片段。批量编辑多篇文章时，先列清获准处理的文件；语言镜像仅在授权范围内纳入。结束时核对每篇已修改、无需修改或无法处理，避免漏篇。
2. 按最小加载规则完成本轮准备，再按当前文体和文稿协作流程处理正文。直接处理的例外、结构讨论、正文确认、原样写入和回读均按该流程执行。
3. 按共同质量规则处理材料缺口、逐批检查及全篇收尾。仅暂停依赖未决事实的内容，保留其余已确认工作。
4. 交付本轮请求的正文或审查意见；默认不附检查记录和改写理由，用户要求解释时与正文分开。文件写回、飞书主稿及 Word 转接沿用已加载的协作和交付说明。

## 普通中文编辑

已有普通中文的 `general_edit` 默认 `in_place`：以原文为底稿，先定位具体问题，再只替换必要片段；没有具体问题就原样交付，不从头另写一版。新建文档使用 `draft`，用户要求重搭结构时使用 `structural`，均按文稿协作处理。只看问题时使用 `audit_only`，不顺手改稿。

按最小加载规则准备，再按共同质量规则的“中文正文展示前检查”和“修改强度”处理；普通讨论回复不进入文稿检查。

## 私有样稿

仅在用户要求维护样稿时更新，不在业务交付后自动追问。候选与批准内容分开，复用已明确的替换范围和选择；读取规则见最小加载规则及共同质量参考。

## `audit_only` 审查输出

保持只读，按共同质量规则的同名章节在对话中分点报告问题；不生成替换稿，不因先前授权过修改而越过本轮只读范围。

## 相邻任务

- 指标是否可实现：申报指标由 `project-writing` 处理，技术方案和独立工程指标问题由 `technical-writing` 处理；两者按需共用[指标可行性判断](../technical-writing/references/metric-feasibility.md)。仅问可行性时直接回答，未要求写稿不启动文稿流程。
- 为报告开展调研、资料比较和来源补齐：`research-report` 连续完成调研与报告内容；Word 交 `docx`，PPT 交 `pptx` 的现有制作路由。仅检索论文用 `paper-search`，持续产品库用 `product-research-workbook`；不因调用专业工具自动扩大为报告任务。
- 独立实验设计、比较方法与结果解释：`technical-writing`，仅判断时直接回答，不自动写报告或改项目。
- 论文全文技术内容、论证和结论审查，以及明确要求的模拟审稿：`paper-review`；论文局部科学疑问只检查相关内容，终稿文字和语言审校仍用 `ieee-manuscript-edit`。
- 投稿格式、材料合规、投稿系统与返修事务：`journal-submission`，按实际文件交给 `latex-paper`、`docx` 或 `paper-figure-review` 处理格式。准备投稿或点击 Submit 不自动触发全文审稿；同时要求内容与格式检查时分别完成并复用当前稿件和已有检查结果。结合上下文判断，只有范围无法确定且会明显改变工作量时才询问。
- 文献检索和下载：`paper-search`、`paper-download`；原文及笔记准确性核对：`paper-review`；Zotero 笔记读写：现有 Zotero 插件。
- Word、PDF、LaTeX 工程：`docx`、`pdf`、`latex-paper`。

需要判断完整学术流程时，按需读取 [学术流程地图](references/academic-workflow-map.md)，不要因此加载所有下游技能。

## 完成条件

- 写作上下文字段已经确定，`loaded_refs` 与实际读取一致。
- 本轮范围及适用的协作、质量和交付检查已完成，满足共同质量规则的停笔条件。
- 写入已回读核验；未完成或受阻的部分如实说明，不把待确认内容算作已保存。
