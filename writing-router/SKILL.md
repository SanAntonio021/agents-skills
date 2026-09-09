---
name: writing-router
description: 中文写作与通用编辑的默认入口。Use when 用户要撰写、重写、润色或审查项目书、技术方案、会前技术交流稿、系统说明、测试与结果分析、调研报告、会议纪要、中文或英文论文，普通中文去 AI 味、删废话，以及无法直接归类的中文材料；也用于先讨论结构、分批确认正文、选择本地或飞书主稿，以及确定写作模式、修改范围、语言和实际加载规则。投稿事务、论文停稿审查、文献检索和单纯文件排版仍转给对应专门技能。
---

# 中文正式写作总路由

## 目标

先确定文稿类型、本轮改动边界和协作方式，再加载一个主文体技能。不要把所有写作规则一次性塞进上下文，也不要用同一套“去 AI 味”规则处理所有正式文稿。

## 原文保留操作

用户明确要求正文逐字不动、仅在开头加标题或末尾追加给定文字时，按[原文保留编辑](references/exact-edit.md)直接拼接并校验。本地 UTF-8 文稿使用其中的工具生成新文件，不重新生成或润色受保护正文；其他写作任务沿用下列流程。

## 写作上下文

开始正文工作前，在任务内部记录以下字段；当前任务未换文稿或阶段时沿用。普通交付不展示这段记录。评测提示包含 `TRACE_WRITING_CONTEXT=1` 时，才在文末输出同名 JSON 对象。

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

正文中的冲突按以下顺序处理：

1. 用户要求、权威源材料、指定模板和受保护事实；
2. 当前文体与 `mode` 的规则；
3. [共同质量规则](../writing-router/references/common-quality.md)；
4. 已批准的个人样稿。

个人样稿只用于句子密度、信息顺序和语气。样稿不能覆盖事实、模板、术语、证据边界或当前任务的文体规则。

摘要与结论、申报表规定栏目、会议行动项可以为不同章节功能复述同一论点。复述必须服务于新的章节功能，不能整段复制，也不能改变事实、适用范围或完成状态。

## 最小加载规则

1. 只加载当前文体对应的一个主技能；`general_edit` 不加载另一个写作入口。
2. 五类正式文稿的主技能都读取 [共同质量规则](../writing-router/references/common-quality.md)。形成完整草稿、结构重写、终稿审校或 `audit_only` 时，再读取 [AI 气味目录](../writing-router/references/ai-smell-catalog.md)。
3. 个人样稿入口固定为 `D:\BaiduSyncdisk\.agents\writing-profile\index.md`。只有入口和对应样稿都标为 `approved` 时才读取；一次只读当前文体的样稿。未读取的文件不能写入 `loaded_refs`。
4. 完整正式文稿交付前使用 `style-vocab` 检查术语和个人用词。若当前文体技能已经完成共同质量与 AI 气味审校，向 `style-vocab` 传递这一状态，不再重复通用改写。
5. 中文论文不加载英文写作细则；英文论文不加载中文写作细则。`final_audit` 只加载当前稿件语言对应的细则和终稿规则。

## 通用流程

1. 锁定当前主稿、来源、模板、交付范围和受保护片段。批量编辑多篇文章时，先列清获准处理的文件；语言镜像仅在授权范围内纳入。结束时核对每篇已修改、无需修改或无法处理，避免漏篇。
2. 建立写作上下文后、处理正文前，读取[文稿协作](references/collaborative-writing.md)，将实际路径记入 `loaded_refs`，再选择主技能。先识别会议整理、运行日志和明确整篇处理等例外；其余 `draft/structural` 默认分批确认，`bounded` 按实际改动判断，`in_place` 直接编辑，`audit_only` 保持只读。同一任务已读且处理方式未变时沿用。
3. 材料不足时只写材料能支持的部分，明确列出阻塞正文成立的缺项，不用常识或套话补篇幅。
4. 按当前文体、模式和协作方式起草、重构、局部修改或审查。协作起草先讨论结构和思路，再展示待确认正文；确认后写回当前主稿，并直接衔接后续正文。
5. 用共同质量规则检查事实漂移、段落职责、信息推进、全文重复和停笔条件；需要时再按气味目录复核。
6. 完整正式稿再做术语与个人用词检查。修改理由只说一次；正文、审计记录和交付说明分开。
7. 实际写入工作区内的 `.md` 或 `.tex` 时，读取 [文稿版本保护](references/document-version-protection.md)。只读审查和聊天内改句不触发。
8. 需要 Word 时，正文先按当前协作方式完成本轮内容处理与审校，再按 [Markdown 到 DOCX 交接契约](references/markdown-docx-contract.md) 交给 `docx`。飞书主稿直接回读，不额外维护本地副本；交付流程不再自行运行第二遍通用风格改写。
   恢复交付或复用检查结果时，由 Word 工具核对主稿、模板、图片和 Word 版本；变化后的材料重新检查，保留用户手工修改。

## 普通中文编辑

已有普通中文的 `general_edit` 默认 `in_place`：保留结构、含义和作者声音；新建文档使用 `draft`，用户要求重搭结构时使用 `structural`，均按文稿协作处理。只看问题时使用 `audit_only`，不顺手改稿。清楚自然的原文可以不改。

读取 [共同质量规则](references/common-quality.md)，需要完整审校时再读 [AI 气味目录](references/ai-smell-catalog.md)。先保护事实、数字、单位、公式、引用、因果、比较、否定和完成状态；优先删无信息句、合并重复，再修句式。关键词命中只能帮助定位，不能单独判错。不注入虚构细节、第一人称、情绪或幽默，不把专业术语当 AI 词替换。普通文章中作者已表达的真实情绪及其强度也是内容，不能仅因措辞抽象就删去感谢、愤怒或失望，也不替作者新增感受或立场。

默认给本轮请求范围内的修改文本；只有事实缺口或实质取舍需要决定时再附简短说明。继续改写不能带来明确收益时停止。

## 私有样稿

仅在用户要求维护样稿时更新，不在业务交付后自动追问。运行时只读取 `approved` 样稿；候选与批准内容分开，用户已明确的替换范围和选择可复用。样稿只提供表达参考，事实必须重新取证。

## `audit_only` 审查输出

按 [共同质量规则](references/common-quality.md) 直接在对话中分点列出问题，每点以加粗关键词开头，保持用户指定的审查范围。

整段无理由重复、跨节事实矛盾、虚构数据或把“计划/设计/测试”升级成更高完成状态，直接判 `fail`。`audit_only` 不顺手改正文。

## 相邻任务

- 指标是否可实现：`target-feasibility`。
- 研究取样和补证据：`baseline-research`。
- 论文整体停稿审查或最终 Submit 门：`paper-review`。
- 投稿系统与返修事务：`journal-submission`。
- 文献检索、下载和总结：`paper-search`、`paper-download`、`paper-summary`。
- Word、PDF、LaTeX 工程：`docx`、`pdf`、`latex-paper`。

需要判断完整学术流程时，按需读取 [学术流程地图](references/academic-workflow-map.md)，不要因此加载所有下游技能。

## 完成条件

- 写作上下文字段已经确定，`loaded_refs` 与实际读取一致。
- 事实、数值、公式、引用关系和状态没有漂移。
- 每段承担明确功能，并推进新信息。
- 必要复述有新的章节功能；无意义重复已删除。
- 没有未处理的阻断项；继续改写已经不能带来明确收益。
