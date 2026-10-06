---
name: writing-router
description: 统一写作协作流程，并处理普通中文编辑。Use when 用户要撰写、重写、润色或审查项目书、技术方案、会前技术交流稿、系统说明、测试与结果分析、调研报告、会议纪要、中文或英文论文，先确定主稿、修改范围和协作方式，再结合对应专业技能完成正文、检查与写回；也直接处理界面文案、普通中文去 AI 味、删废话和无法直接归类的中文材料。投稿事务、论文停稿审查、文献检索和单纯文件排版由对应专门技能处理。
---

# 通用写作流程与编辑

## 目标

统一管理如何协作、确认和交付；专业技能负责具体文体的结构、论证、证据和检查要求。进入专业技能后，共同流程继续有效；普通中文编辑由本技能直接完成。已有决定与准确授权继续沿用。

## 工作流程

1. 确定当前主稿、来源、模板、本轮修改范围和受保护片段，建立或沿用下方写作上下文。批量编辑时列清获准处理的文件，语言镜像仅在授权范围内纳入。
2. 按[文稿协作](references/collaborative-writing.md)选择直接处理、结构讨论、分批确认或只读审查；具体条件和正文循环由该参考统一维护。原文保留操作和界面短文案沿用下方专门分支。
3. 按文体对应表加载专业技能，并按最小加载规则准备共同质量要求与本轮所需资料，处理正文。共同流程贯穿专业写作，不因切换技能重复确认或重新改写。
4. 按共同质量规则完成必要检查，再按已选协作方式交付、写回并回读。材料缺口只暂停依赖未决事实的内容；批量任务核对每篇已修改、无需修改或无法处理。默认只交付正文或审查意见，不附检查记录和改写理由；用户要求解释时与正文分开。

## 原文保留操作

用户明确要求正文逐字不动、仅在开头加标题或末尾追加给定文字时，按[原文保留编辑](references/exact-edit.md)直接拼接并校验。本地 UTF-8 文稿使用其中的工具生成新文件，不重新生成或润色受保护正文；其他写作任务沿用共同流程。

## 界面文案

中文 GUI、网页或上位机的标题、按钮、字段名、状态和操作提示也属于润色范围，包括源代码里的用户可见字符串。创建或修改界面时进入此分支，先读 [界面文案检查](references/ui-copy.md)，再实际读取 [style-vocab](../style-vocab/SKILL.md) 及其适用词表；当前任务已经加载且内容未变时复用。界面入口仍负责布局、运行和截图核验。

这类短文案按 `document_type=general`、`mode=general_edit` 和已有修改范围处理；只审不改时为 `audit_only`。本分支替代长文稿流程，不要求确认提纲、分批正文或形成完整正式稿，不自动运行整份代码的文稿审计。复用现有授权，检查通过后继续原界面任务。

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

## 专业写作衔接

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

按表应用对应文体技能的专业要求，共同协作与质量规则持续适用；普通中文直接在本技能完成，不另找写作入口。

## 规则优先级

按共同质量规则的“优先级”处理冲突；事实与关系保护、必要复述、审查输出和停笔条件均以该参考为准，文体技能补充专业要求。

## 最小加载规则

以下要求同样适用于直接调用文体技能；按其现有引用复用共同参考，不必先返回本入口。实际读取的路径记入 `loaded_refs`；同任务材料与规则未变时复用，已变化或无法确认读过时补读必要文件。

1. 建立写作上下文后、处理正文前，读取[文稿协作](references/collaborative-writing.md)，将实际路径记入 `loaded_refs`，据此选择直接处理或分批协作，不另加确认关口。
2. 实际读取文体对应表选定的主技能及本轮所需参考；对应表不能代替专业规则。`general_edit` 不加载另一个写作入口。论文和 `final_audit` 只读当前稿件语言对应的细则。
3. 各类正文都读取[共同质量规则](references/common-quality.md)。中文正文首次起草、续写、局部修改或审查前，按其中“中文正文展示前检查”读取 [AI 气味目录](references/ai-smell-catalog.md)和 `style-vocab` 适用词表，逐批检查；混合稿只对中文部分执行。英文在完整草稿、结构重写、终稿审校或 `audit_only` 时读取气味目录，沿用当前文体的检查时机。
4. 个人样稿按共同质量规则的“个人样稿”读取当前文体已批准的材料；完整正式稿按 `style-vocab` 执行术语与正式词表审计。已经完成的共同质量检查传递给后续技能，不重复通用改写。
   跨技能交接沿用当前请求范围、准确授权、材料版本及已完成检查；材料变化时重读并检查受影响部分，影响不明时扩大必要检查。接入下游工具不重置协作方式，也不把局部任务扩成整稿审查；只读限制继续有效。
5. 实际写入本地 `.md`、`.tex` 及必要源文件前读取[文稿版本保护](references/document-version-protection.md)；只读审查和聊天内改句不触发。Word 转换时读取[Markdown 到 DOCX 交接契约](references/markdown-docx-contract.md)，由 `docx` 核对当前材料并处理交付。

## 普通中文编辑

已有普通中文的 `general_edit` 默认 `in_place`：以原文为底稿，先定位具体问题，再只替换必要片段；没有具体问题就原样交付，不从头另写一版。新建文档使用 `draft`，用户要求重搭结构时使用 `structural`，均按文稿协作处理。只看问题时使用 `audit_only`，不顺手改稿。

按最小加载规则准备，再按共同质量规则的“中文正文展示前检查”和“修改强度”处理；普通讨论回复不进入文稿检查。

## 私有样稿

仅在用户要求维护样稿时更新，不在业务交付后自动追问。候选与批准内容分开，复用已明确的替换范围和选择；读取规则见最小加载规则及共同质量参考。

## `audit_only` 审查输出

保持只读，按共同质量规则的同名章节在对话中分点报告问题；不生成替换稿，不因先前授权过修改而越过本轮只读范围。

## 相邻任务边界

- 工程判断：申报指标由 `project-writing` 处理；技术方案、独立指标、实验设计和结果解释由 `technical-writing` 处理，按需共用[指标可行性判断](../technical-writing/references/metric-feasibility.md)。仅问判断时直接回答，不自动写报告或改项目。
- 调研与资料：报告由 `research-report` 连续完成调研和写作；仅检索、下载论文用 `paper-search`、`paper-download`，持续产品库用 `product-research-workbook`，Zotero 笔记读写用现有插件。调用资料工具不自动扩大为报告任务。
- 论文审查：技术内容、论证、结论、原文及笔记准确性核对和明确要求的模拟审稿由 `paper-review` 处理，局部疑问只检查相关内容；文字与语言审校由 `ieee-manuscript-edit` 处理。
- 投稿与制作：投稿合规和事务由 `journal-submission` 处理；按实际产物使用 `docx`、`pdf`、`latex-paper`、`paper-figure-review` 或 `pptx` 的现有流程。准备投稿不自动触发全文审稿，排版不自动授权改写；同时要求内容与格式检查时复用当前稿件和已有检查，仅在范围不明且明显影响工作量时询问。

需要判断完整学术流程时，按需读取 [学术流程地图](references/academic-workflow-map.md)，不要因此加载所有下游技能。

## 完成条件

- 写作上下文字段已经确定，`loaded_refs` 与实际读取一致。
- 本轮范围及适用的协作、质量和交付检查已完成，满足共同质量规则的停笔条件。
- 写入已回读核验；未完成或受阻的部分如实说明，不把待确认内容算作已保存。
