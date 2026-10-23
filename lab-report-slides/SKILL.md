---
name: lab-report-slides
description: >
  Generate Chinese advisor daily/weekly research PPTs from recent sessions, project records,
  experiments and real figures. Use for 生成今日汇报, 生成每日汇报, 生成本周组会汇报,
  生成组会 PPT, or turning recent research work into an advisor report.
  For daily reports, inventory the period, then show a tentative first-page overview draft in
  the same turn as the single prompt for unrecorded work, revise and confirm the overview,
  then confirm only the items to expand, and then confirm source materials and any proposed
  cropped, redrawn or generated visuals before producing the deck;
  for group meetings, discuss and confirm each section before making the full deck.
  Neither mode requires per-slide approval by default. Give each detail page one core point;
  keep routine editing, execution and validation details in project records.
  Preserve research substance, essential evidence and user edits. Deliver editable text and
  independent images after content review and actual PPTX rendering. Do not use for turning
  a single paper PDF or DOI into a literature presentation.
compatibility: Windows with local Codex or Claude Code sessions; Python 3.10+, requirements.txt and PowerPoint for native daily-report checks. LibreOffice, Poppler and the sibling libreoffice-runner skill support the unchanged group-meeting render path and explicit PDF/HTML exports. Node.js/sharp is optional for SVG input.
---

# 科研日报与组会汇报

面向导师讲清本期科研推进，按内容价值确定详略。

## 按阶段读取

| 阶段 | 参考 |
|---|---|
| 首次安装或依赖异常 | [安装与配置](references/installation.md)，运行 `python scripts/check_dependencies.py` |
| 核实工作、选材及图文核对 | [资料与选材](references/materials.md) |
| 组织文字及内容验收 | [中文表达](references/chinese-style.md) |
| 制作及文件验收 | [制作与验证](references/rendering.md) |
| 使用或更换本地模板 | [模板适配](references/local-template.md) |

执行相应阶段前实际读取；同一任务中未变化的材料和检查可复用。可选技能缺失时执行随附规则。

## 1. 盘点本期工作

日报取 `Asia/Shanghai` 当天，周报取截至请求日期的最近七个日历日；用户指定范围优先。

日报严格按顺序推进：先只盘点本期会话和项目记录，并保存本次摘要。盘点完成后，先读取[总览页规则](references/chinese-style.md#总览页工作缘由与实际推进)，再在同一轮中完成三件事：用一句话说明记录范围与摘要位置；展示清楚标注“待补充”的第一页完整草稿，按当前记录逐项写工作对象、本期具体工作和已经完成的结果；用一句话询问遗漏：**“还有记录里没提到、但本期需要汇报的工作吗？比如帮老师做的事？也可以直接对上面的第一页草稿提出增删改意见。”** 用户已主动补充过时不再重复询问遗漏，但仍展示草稿并请其对草稿增删改。此时不查图、不打开飞书素材、不索要缺失文件，也不做详细事实核验。用户答复后，只更新受影响项；若答复包含补充或修改但未明确接受，重示完整第一页草稿并请确认；答复明确接受，或明确表示无补充并继续时，视为总览确认。总览确认后才展示拟展开事项清单；第二次确认前仍不查图、不开始制作。第二道确认后，只收集并核实这些事项的素材，在对话中直接显示原始图片、文档页或数据预览，接着展示拟用方式和派生内容提案，供第三道确认；不能只给文件路径。第三道确认前不生成最终图表、示意图或 PPTX。范围、项目或日期明确时尊重其边界；口头补充可作为工作来源，不要求必须有会话或文件证据。

组会按原流程执行：范围不明确时先问范围；选定后逐部分讨论和确认。

没有适合科研汇报的实质进展时，询问停止还是改做私人工作记录。

## 2. 按汇报类型讨论内容

- **每日汇报**：盘点后在同一轮展示标注“待补充”的第一页完整草稿，并只问一次遗漏；用户可同时补充遗漏和对草稿增删改。草稿每项写清工作对象、本期具体工作和已经完成的结果，不能只列项目名或空状态。更新受影响项并确认总览后，再展示“拟展开事项”清单。该清单只列需要展开的事项，不列总览简述项。用户确认后，按展开事项展示原始素材、拟用方式和派生内容提案，供素材确认。第一页总览、拟展开事项和素材与生成方式是三道独立确认，任何“直接生成”请求都不替代任何一道确认。素材确认后不再逐页审批。
- **组会汇报（含周组会）**：先明确各部分及顺序，再逐部分讨论研究问题、主要内容、结果或判断、证据图和必要展开程度。各部分全部确认后，自行安排分页并生成整套，不再增加总览、提纲或逐页的重复审批。

已经在本期对话完成的口头补充问题、总览确认、展开清单确认和素材确认持续有效；局部更正只更新受影响项，不重启整套讨论。用户明确要求逐页讨论或提前制作已确认部分时，沿用相应授权；尚未确认的日报阶段不得跳过。

## 3. 核实素材并制作

日报三道确认完成后，只对确认纳入的内容集中做一次事实和素材核实，再按[内部逐页素材核对](references/materials.md#排版前逐页素材核对)和获批方式准备图件；定向查找相关飞书文档中的测试照片、结果图和系统框图，展开页优先使用核实过的真实图件。未获批的裁切、数据重绘、概括示意图或新绘内容不得生成或进入 PPTX。口头补充可作为事实来源，仅在关键事实不清且影响页面含义时追问。完成一次排版前表达检查后制作，不在成稿后重复完整语义审校。组会继续按既有逐页素材核对及表达流程。

沿用已有工程、用户模板及项目约定；模板未选时询问一次内置或本地模板，等待期间继续核实素材。未回答不视为选择，有效模板适配可复用。

简单日报用随附生成器，指定工程继续原工程。直接制作可编辑 PPTX，供用户查看和修改；不先做 HTML 页面稿。HTML 默认关闭，显式选项见制作参考。内容讨论与确认节奏由本技能统一负责，调用其他制作工具不重启确认，也不自动要求新建独立制作对话；已有制作安排和用户指定方式继续沿用。工具选择、文件保护与共同文件验收沿用 `pptx`，分工和工具调用服从宿主规则。

## 4. 验收与交付

**日报**只做轻量文件检查（PPTX 包可读、页数与预期相符、输出非空），随后对隔离副本运行一次 PowerPoint 原生打开并导出全部页面 PNG；快速扫查全部页面，只检查内容遗漏、错图、不可读文字、裁切和严重遮挡，不作审美评判。默认不调用 LibreOffice、不生成 PDF 或 LibreOffice 页面图、不重复完整 OOXML/字体审计或成稿语义审校。出现异常、复杂模板或结构改动时，才升级静态检查。原生检查受阻时不操作用户 PowerPoint；完成轻量检查后可交付候选稿，并明确标记“PowerPoint 原生打开与导出未验证”。修复后只复查受影响项目。

**组会汇报**仍按[内容验收](references/chinese-style.md#内容验收)及[文件验收](references/rendering.md#验证)完成既有验收流程。两类结果分别记录；已知错误修复后交付，未验证项如实说明。

按制作参考在约定目录交付 PPTX；默认不额外交付 PDF/HTML。只有用户明确要求 PDF 时才生成 PDF；不主动清理过程文件。项目记录沿用共享规范，不追加制作流水。

## 后续修改

先读用户当前稿，只改本次要求，保留手工修改和删除。不用旧生成稿覆盖当前稿；一次不展开某项目不构成长期排除规则。
