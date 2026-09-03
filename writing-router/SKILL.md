---
name: writing-router
description: 中文正式写作的默认总路由。Use when 用户要撰写、重写、润色或审查项目书、技术方案、系统说明、测试与结果分析、调研报告、会议纪要、中文或英文论文，以及无法直接归类的中文材料；也用于确定写作模式、修改范围、语言和实际加载规则。投稿事务、论文停稿审查、文献检索和单纯文件排版仍转给对应专门技能。
---

# 中文正式写作总路由

## 目标

先确定文稿类型和本轮改动边界，再加载一个主文体技能。不要把所有写作规则一次性塞进上下文，也不要用同一套“去 AI 味”规则处理所有正式文稿。

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
- `audit_only`：只审不改；必须建立“论点—证据—章节功能”表。

## 两级路由

| `document_type` | `mode` | 主技能 |
|---|---|---|
| `project` | `proposal`、`expert_reply`、`final_audit` | [project-writing](../project-writing/SKILL.md) |
| `technical` | `technical_scheme`、`system_description`、`test_result_analysis` | [technical-writing](../technical-writing/SKILL.md) |
| `research_report` | `evidence_report`、`decision_report`、`final_audit` | [research-report](../research-report/SKILL.md) |
| `meeting_notes` | `discussion`、`action`、`mixed` | [meeting-notes](../meeting-notes/SKILL.md) |
| `paper` | `zh_paper`、`en_paper`、`final_audit` | [ieee-manuscript-edit](../ieee-manuscript-edit/SKILL.md) |
| `general` | `general_edit` | [humanizer-zh](../humanizer-zh/SKILL.md) |

判断顺序：

1. 用户明确说出的文稿类型、用途和读者。
2. 原文件的栏目、模板和内容职责。
3. 仍无法区分且会改变产物时，只问一个最关键的问题；不影响实质结果时按最窄范围继续。

项目书、技术文档、调研报告、会议纪要和论文都属于正式文稿。直接调用 `humanizer-zh` 处理这些材料时，也要回到本路由，再进入对应文体技能。

## 规则优先级

正文中的冲突按以下顺序处理：

1. 用户要求、权威源材料、指定模板和受保护事实；
2. 当前文体与 `mode` 的规则；
3. [共同质量规则](../humanizer-zh/references/common-quality.md)；
4. 已批准的个人样稿。

个人样稿只用于句子密度、信息顺序和语气。样稿不能覆盖事实、模板、术语、证据边界或当前任务的文体规则。

摘要与结论、申报表规定栏目、会议行动项可以为不同章节功能复述同一论点。复述必须服务于新的章节功能，不能整段复制，也不能改变事实、适用范围或完成状态。

## 最小加载规则

1. 只加载路由表中的一个主技能。
2. 五类正式文稿的主技能都读取 [共同质量规则](../humanizer-zh/references/common-quality.md)。形成完整草稿、结构重写、终稿审校或 `audit_only` 时，再读取 [AI 气味目录](../humanizer-zh/references/ai-smell-catalog.md)。
3. 个人样稿入口固定为 `D:\BaiduSyncdisk\.agents\writing-profile\index.md`。只有入口和对应样稿都标为 `approved` 时才读取；一次只读当前文体的样稿。未读取的文件不能写入 `loaded_refs`。
4. 完整正式文稿交付前使用 `style-vocab` 检查术语和个人用词。若当前文体技能已经完成共同质量与 AI 气味审校，向 `style-vocab` 传递这一状态，不再调用 `humanizer-zh` 做第二遍通用改写。
5. 中文论文不加载英文写作细则；英文论文不加载中文写作细则。`final_audit` 只加载当前稿件语言对应的细则和终稿规则。

## 通用流程

1. 锁定当前主稿、来源、模板、交付范围和受保护片段。
2. 建立写作上下文并选择主技能。
3. 材料不足时只写材料能支持的部分，明确列出阻塞正文成立的缺项，不用常识或套话补篇幅。
4. 按当前文体和模式起草、重构、局部修改或审查。
5. 用共同质量规则检查事实漂移、段落职责、信息推进、全文重复和停笔条件；需要时再按气味目录复核。
6. 完整正式稿再做术语与个人用词检查。修改理由只说一次；正文、审计记录和交付说明分开。
7. 实际写入工作区内的 `.md` 或 `.tex` 时，读取 [文稿版本保护](references/document-version-protection.md)。只读审查和聊天内改句不触发。
8. 需要 Word 时，正文先完成审校和冻结，再按 [Markdown 到 DOCX 交接契约](references/markdown-docx-contract.md) 交给 `docx`。交付流程不再自行运行第二遍通用风格改写。

## 样稿更新提醒

个人样稿允许随正式文稿迭代，但不能自动吸收新稿。

1. 只有用户明确表示“这版可以”“定稿”“可以交付”或给出同义确认后，才对照当前文体已经批准的样稿。是否达到可交付状态由用户确定；审校通过、文件已保存或已经导出都不能代替用户确认。
2. 用户确认可交付后，如果新稿中有一段明显更清楚、更紧凑，或补上了现有样稿没有覆盖的写法，必须单独问用户是否用它替换现有样稿。明确指出新段落、建议替换的旧段落和一条具体理由，不笼统询问“是否更新样稿”。
3. 用户说“先作为候选”时，只在私有样稿记录中标为 `candidate`；运行时仍只读取 `approved` 内容。
4. 只有用户明确同意替换，才能修改 `approved` 样稿。用户拒绝、没有回答或只同意列为候选时，保留原样稿。
5. 每类维持两至三个短段落和一个结构小样。新段落更好时优先替换较弱的旧段落，不整篇收录，也不持续累加相同写法。
6. 新样稿只提供表达参考；其中的项目名称、事实、数字、结论和证据不能迁移到其他文稿。

## `audit_only` 的最低产物

五类正式文稿一律先列内部审计表：

| 字段 | 含义 |
|---|---|
| 论点 | 文稿实际声称的最小事实、判断、决定或任务 |
| 证据 | 来源、数据、原始发言、公式或“缺失” |
| 章节功能 | 该处负责背景、方法、结果、判断、决定、行动等哪一项 |
| 状态 | `supported`、`review_required`、`fail` |

整段无理由重复、跨节事实矛盾、虚构数据或把“计划/设计/测试”升级成更高完成状态，直接判 `fail`。`audit_only` 不顺手改正文。

## 相邻任务

- 指标是否可实现：`target-feasibility`。
- 研究取样和补证据：`baseline-research`。
- 论文整体停稿审查或最终 Submit 门：`paper-review`。
- 投稿系统与返修事务：`journal-submission` 或 `ieee-journal-submission`。
- 文献检索、下载和总结：`paper-search`、`paper-download`、`paper-summary`。
- Word、PDF、LaTeX 工程：`docx`、`pdf`、`latex-paper`。

需要判断完整学术流程时，按需读取 [学术流程地图](references/academic-workflow-map.md)，不要因此加载所有下游技能。

## 完成条件

- 写作上下文字段已经确定，`loaded_refs` 与实际读取一致。
- 事实、数值、公式、引用关系和状态没有漂移。
- 每段承担明确功能，并推进新信息。
- 必要复述有新的章节功能；无意义重复已删除。
- 没有未处理的阻断项；继续改写已经不能带来明确收益。
