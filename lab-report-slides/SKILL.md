---
name: lab-report-slides
description: >
  Generate Chinese advisor daily/weekly research PPTs from recent sessions, project records,
  experiments and real figures. Use for 生成今日汇报, 生成每日汇报, 生成本周组会汇报,
  生成组会 PPT, or turning recent research work into an advisor report.
  Daily reports cover work since the previous delivered report, including gap days.
  Reuse existing figures and document screenshots instead of drawing replacement diagrams.
  For daily reports, inventory the period and verify first-page facts against local records,
  then show a first-page draft plus reportable work not placed on it, ask once for unrecorded
  work and draft edits, revise and confirm the overview, then confirm only the items to expand,
  and then confirm source materials and any proposed
  cropped, redrawn or generated visuals before producing the deck;
  for group meetings, discuss and confirm each section before making the full deck.
  Neither mode requires per-slide approval by default. Give each detail page one core point;
  keep routine editing, execution and validation details in project records.
  Preserve research substance, essential evidence and user edits. Deliver editable text and
  independent images after content review and actual PPTX rendering. Do not use for turning
  a single paper PDF or DOI into a literature presentation.
compatibility: Windows with local Codex, Claude Code or Cursor sessions; Python 3.10+, requirements.txt and PowerPoint for native daily-report checks. LibreOffice, Poppler and the sibling libreoffice-runner skill support the unchanged group-meeting render path and explicit PDF/HTML exports. Node.js/sharp is optional for SVG input.
---

# 科研日报与组会汇报

面向导师讲清本期科研推进，按内容价值确定详略。日报第一页按[第一页怎么写](references/chinese-style.md#第一页怎么写)起草。展开页和组会页面首次起草前按[主张与入页信息](references/chinese-style.md#起草前确定主张与入页信息)确定证据能支持的主张和必要条件，只生成选定内容；核查过程及重复的未做事项说明默认不入页，表达检查只纠正漏网偏差。

## 按阶段读取

| 阶段 | 参考 |
|---|---|
| 首次安装或依赖异常 | [安装与配置](references/installation.md)，运行 `python scripts/check_dependencies.py` |
| 核实工作、选材及图文核对 | [资料与选材](references/materials.md) |
| 组织文字及内容验收 | [中文表达](references/chinese-style.md) |
| 制作及文件验收 | [制作与验证](references/rendering.md) |
| 使用或更换本地模板 | [模板适配](references/local-template.md) |

执行相应阶段前实际读取；同一任务中未变化的材料和检查可复用。可选技能缺失时执行随附规则。

## 0. 定位正式交付目录

盘点工作前，先读取用户本轮指定及当前项目的目录约定；需要本机默认汇报位置时，读取实际用户主目录下 `.agent-rules/local.md` 的相关段落，不把临时聊天目录当成用户主目录。按[文件存放](references/rendering.md#文件存放)的优先级定位正式目录，再读取该目录已有的 `AGENTS.md`、`README.md`，核对归档和命名要求。已有明确约定就直接采用，不再询问位置；同一任务中已确认且未变化的结果复用。

## 1. 日报流程

日报按下面八步依次做，不跳步、不换序。第一页就是首页“今日工作总览”。第一页、拟展开事项、素材与生成方式是三道独立确认，任何“直接生成”请求都不替代其中任何一道；素材确认后不再逐页审批。

1. **确定统计范围。** 默认累计**上一次已交付汇报的统计截止点至本次统计截止点**之间的工作，覆盖中间没有做汇报的日期，不默认只取当天。先读取上一份汇报、已有统计范围和未汇报事项，按[本期起止与去重](references/materials.md#本期起止与去重)确定边界。用户指定了范围、项目或日期时，以用户指定的为准。
2. **盘点全部候选。** 按[采集本期记录](references/materials.md#采集本期记录)检查本期会话、相关本地项目记录及相关飞书文档/任务的本期文字或更新信息，建立候选账目，并保存本次摘要和检查过的来源范围。飞书此时只读文字和更新状态，不查图片、附件或完整数据。不能因为采集摘要短、已有一项显眼工作、候选多或第一页空间有限而停止搜集。
3. **筛选第一页并核实事实。** 全部候选盘点完后，按[首页准入](references/materials.md#首页准入)判断哪些上第一页，再按[核实事实与状态](references/materials.md#核实事实与状态)核对这些工作属于哪个项目、为什么做、本期做了什么、结果或交付，以及支持它的记录。此时不查图、不索要缺失文件，也不做完整图文或数据复核。
4. **展示第一页草稿，问一次。** 先读取[第一页怎么写](references/chinese-style.md#第一页怎么写)，本机登记了个人样稿时一并读取，再起草。在同一轮展示：
   - 检查过的来源范围和摘要保存位置；
   - “第一页草稿”的完整可见文案；
   - “未放入首页”：全部有汇报价值但没上第一页的候选，逐项写明状态、依据来源、没上第一页的原因和建议去向（首页简述、展开或留记录），不设数量上限。纯操作、工具维护和无关记录不列，可按类别归并说明。

   最后只问一次，并以这个问题结束本轮：**“还有记录里没提到、但这次需要汇报的工作吗？比如帮老师做的事。也可以直接对上面的第一页草稿和候选取舍提出增删改意见。”** 有某项查不到项目或原因时，把那一个具体问题并入这次提问。用户在当前对话已经主动补充过时不再问遗漏，但仍展示草稿和完整候选取舍，请其增删改。
5. **第一道确认：第一页。** 用户的回答是本期工作的来源和修改依据。口头补充的工作可以直接采用；放入第一页前核对它涉及的本地状态和产物，不要求另外提供文件证明。只对新加入或修改的内容重新核实，并更新受影响项。草稿只要有变化，就重新展示完整第一页并等待明确接受；草稿没有变化，用户明确接受或表示没有补充并要求继续时，视为第一页已确认。确认前不展示拟展开事项。
6. **第二道确认：拟展开事项。** 第一页确认后，展示“拟展开事项”清单，只列需要展开的事项，不列第一页简述项。第二道确认完成前，不查图、不打开附件、不制作。
7. **第三道确认：素材与生成方式。** 拟展开事项确认后，补齐第一页核实未覆盖的事实，按[复用与核对素材](references/materials.md#复用与核对素材)只收集、核实这些事项的素材，再按[素材确认](references/materials.md#素材确认日报第三道确认)逐项展示原始素材、拟用方式和派生内容提案。原始图片、文档页或数据预览直接显示在对话里，不能只给文件路径。确认前不生成最终图表、示意图或 PPTX。
8. **制作与验收。** 按[核实素材并制作](#3-核实素材并制作)和[验收与交付](#4-验收与交付)完成。

**已完成的确认持续有效。** 已经在本期对话完成的口头补充问题、总览确认、展开清单确认和素材确认持续有效；局部更正只更新受影响项，不重启整套讨论。用户明确要求逐页讨论或提前制作已确认部分时，沿用相应授权；尚未确认的日报阶段不得跳过。

**跨日累计稿。** 用户要求在昨天稿上追加今天内容时，按跨日累计稿处理：今日总览替换旧总览，同一项目的各天进展按主题合并，统计日期在过程记录说明，首页日期按用户要求显示；旧展开页保留，与今日同主题页面相邻排列，页标题保留原始日期。合并后的完整首页须经总览确认。

**没有实质进展。** 没有适合科研汇报的实质进展时，不强行生成空白或工具维护草稿；先确认是否有记录外科研补充，仍没有时询问停止还是改做私人工作记录。

## 2. 组会流程

周报取截至请求日期的最近七个日历日。组会范围不明确时先问范围；选定后逐部分讨论和确认。

组会汇报（含周组会）先确定各部分及顺序，再逐部分讨论研究问题、主要内容、结果或判断、证据图和必要展开程度。每部分正文都写明所属项目，即使标题已经标注；按“项目名、直接前因、本次具体动作、结果或当前状态”讲清进展。前因只采用材料中已有的具体问题、需求或前序发现；缺少且影响听众理解时只追问一个问题，不从常识补造。相关的连续动作合并表述，删去抽象套话和解释性操作过程。各部分全部确认后，自行安排分页并生成整套，不再增加总览、提纲或逐页的重复审批。

已确认的部分同样持续有效，局部更正和已有授权的处理与日报相同。

## 3. 核实素材并制作

日报三道确认完成后，只对确认纳入的内容按[内部逐页素材核对](references/materials.md#排版前逐页素材核对)和获批方式准备图件；展开页优先直接使用核实过的原图、原表和现有文档页，不默认新绘系统框图、流程图或概念图。已有图件能表达本页内容时，不因统一风格或可编辑性而重画；确实缺少不可替代的材料时先说明缺口，新绘仅按用户明确要求或同意执行。未获批的裁切、数据重绘、概括示意图或新绘内容不得生成或进入 PPTX。口头补充可作为事实来源，仅在关键事实不清且影响页面含义时追问。完成一次排版前表达检查后制作，不在成稿后重复完整语义审校。组会继续按既有逐页素材核对及表达流程。

沿用已有工程、用户模板及项目约定；模板未选时询问一次内置或本地模板，等待期间继续核实素材。未回答不视为选择，有效模板适配可复用。

简单日报用随附生成器，指定工程继续原工程。直接制作可编辑 PPTX，供用户查看和修改；不先做 HTML 页面稿。HTML 默认关闭，显式选项见制作参考。内容讨论与确认节奏由本技能统一负责，调用其他制作工具不重启确认，也不自动要求新建独立制作对话；已有制作安排和用户指定方式继续沿用。工具选择、文件保护与共同文件验收沿用 `pptx`，分工和工具调用服从宿主规则。

## 4. 验收与交付

**日报**只做轻量文件检查（PPTX 包可读、页数与预期相符、输出非空），随后对隔离副本运行一次 PowerPoint 原生打开并导出全部页面 PNG；快速扫查全部页面，只检查内容遗漏、错图、不可读文字、裁切和严重遮挡，不作审美评判。默认不调用 LibreOffice、不生成 PDF 或 LibreOffice 页面图、不重复完整 OOXML/字体审计或成稿语义审校。出现异常、复杂模板或结构改动时，才升级静态检查。原生检查受阻时不操作用户 PowerPoint；完成轻量检查后可交付候选稿，并明确标记“PowerPoint 原生打开与导出未验证”。修复后只复查受影响项目。

**组会汇报**仍按[内容验收](references/chinese-style.md#内容验收)及[文件验收](references/rendering.md#验证)完成既有验收流程。两类结果分别记录；已知错误修复后交付，未验证项如实说明。

按制作参考在约定目录交付 PPTX；默认不额外交付 PDF/HTML。只有用户明确要求 PDF 时才生成 PDF；不主动清理过程文件。项目记录沿用共享规范，不追加制作流水。

## 后续修改

先读用户当前稿，只改本次要求，保留手工修改和删除。不用旧生成稿覆盖当前稿；一次不展开某项目不构成长期排除规则。
