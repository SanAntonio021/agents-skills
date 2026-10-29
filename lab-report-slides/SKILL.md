---
name: lab-report-slides
description: >
  Generate Chinese advisor daily/weekly research PPTs from recent sessions, project records,
  experiments and real figures. Use for 生成今日汇报, 生成每日汇报, 生成本周组会汇报,
  生成组会 PPT, or turning recent research work into an advisor report.
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

日报严格按顺序推进：先只盘点本期会话和项目记录，并保存本次摘要。盘点后按[资料与选材](references/materials.md#首页准入)判断首页候选：本期已经形成科研结论或可用交付、且值得导师知道的工作进入首页，包括帮老师撰写的申报书正文和资料检索结果；只完成操作、调整格式或入库整理的工作留在项目记录。再按[资料与选材](references/materials.md#核实事实与状态)做首页事实级核实：核对拟入首页的对象、本期动作、结论或交付，以及支持它的记录；不查图、不打开飞书素材、不索要缺失文件，也不做完整图文或数据复核。核实后再读取[总览页规则](references/chinese-style.md#总览页本期结果)，并在同一轮中展示记录范围与摘要位置、“第一页草稿”的完整可见文案，以及“未放入首页”的可汇报工作及原因，最后只问一次：**“还有记录里没提到、但本期需要汇报的工作吗？比如帮老师做的事？也可以直接对上面的第一页草稿提出增删改意见。”** 草稿按入选工作写成完整句子，包含工作对象、本期具体工作和得出的结论；整项记录还不足以写成结论或交付时，只在未放入首页说明原因。影响结论的条件写进同一句。用户已主动补充过时不重复询问遗漏，但仍展示草稿并请其增删改。用户答复后，只对新加入或修改的内容重新做首页事实级核实并更新受影响项；只要草稿发生变化，就重示完整第一页并等待明确接受，答复未变化且明确接受或表示无补充并继续时，视为总览确认。口头补充可作为工作来源；随后放入首页时再核对该事项涉及的本地状态和产物，不要求额外文件证明其存在。总览确认后才展示拟展开事项清单；第二次确认前仍不查图、不开始制作。第二道确认后，补齐首页未覆盖的事实并只收集、核实这些事项的素材，在对话中直接显示原始图片、文档页或数据预览，接着展示拟用方式和派生内容提案，供第三道确认；不能只给文件路径。第三道确认前不生成最终图表、示意图或 PPTX。范围、项目或日期明确时尊重其边界。

组会按原流程执行：范围不明确时先问范围；选定后逐部分讨论和确认。用户要求在昨天稿上追加今天内容时，按跨日累计稿处理：今日总览替换旧总览，同一项目的两天进展按主题合并并在项内标注日期范围；旧展开页保留，与今日同主题页面相邻排列，页标题保留原始日期。合并后的完整首页须经总览确认。

没有适合科研汇报的实质进展时，不强行生成空白或工具维护草稿；先确认是否有记录外科研补充，仍没有时询问停止还是改做私人工作记录。

## 2. 按汇报类型讨论内容

- **每日汇报**：盘点后先做首页事实级核实，再在同一轮展示“第一页草稿”、紧凑列出“未放入首页”的可汇报工作及原因，并只问一次遗漏与修改。草稿不设固定项数，按已形成的结论和交付自然成项；每项一句结论句，写清对象、本期做了什么、得出了什么判断或选定方案。每项最多保留一个支撑结论的关键数值，批次、采样率、调制方式、完整 BER 组等移入展开页。首页一页放不下时新增“总览（续）”页，不缩字号、不压段距、不删结论。未放入首页最多 3 项，每项一句原因，只列有科研价值但未占首页的工作。用户补充或调整后，重新核实受影响事实；草稿发生变化就重示完整第一页并等待明确接受。确认总览后，再展示“拟展开事项”清单。该清单只列需要展开的事项，不列总览简述项。用户确认后，按展开事项展示原始素材、拟用方式和派生内容提案，供素材确认。第一页总览、拟展开事项和素材与生成方式是三道独立确认，任何“直接生成”请求都不替代任何一道确认。素材确认后不再逐页审批。
- **组会汇报（含周组会）**：先明确各部分及顺序，再逐部分讨论研究问题、主要内容、结果或判断、证据图和必要展开程度。各部分全部确认后，自行安排分页并生成整套，不再增加总览、提纲或逐页的重复审批。

已经在本期对话完成的口头补充问题、总览确认、展开清单确认和素材确认持续有效；局部更正只更新受影响项，不重启整套讨论。用户明确要求逐页讨论或提前制作已确认部分时，沿用相应授权；尚未确认的日报阶段不得跳过。

## 3. 核实素材并制作

日报三道确认完成后，只对确认纳入的内容补齐首页未覆盖的事实并完成素材核实，再按[内部逐页素材核对](references/materials.md#排版前逐页素材核对)和获批方式准备图件；定向查找相关飞书文档中的测试照片、结果图和系统框图，展开页优先使用核实过的真实图件。未获批的裁切、数据重绘、概括示意图或新绘内容不得生成或进入 PPTX。口头补充可作为事实来源，仅在关键事实不清且影响页面含义时追问。完成一次排版前表达检查后制作，不在成稿后重复完整语义审校。组会继续按既有逐页素材核对及表达流程。

沿用已有工程、用户模板及项目约定；模板未选时询问一次内置或本地模板，等待期间继续核实素材。未回答不视为选择，有效模板适配可复用。

简单日报用随附生成器，指定工程继续原工程。直接制作可编辑 PPTX，供用户查看和修改；不先做 HTML 页面稿。HTML 默认关闭，显式选项见制作参考。内容讨论与确认节奏由本技能统一负责，调用其他制作工具不重启确认，也不自动要求新建独立制作对话；已有制作安排和用户指定方式继续沿用。工具选择、文件保护与共同文件验收沿用 `pptx`，分工和工具调用服从宿主规则。

## 4. 验收与交付

**日报**只做轻量文件检查（PPTX 包可读、页数与预期相符、输出非空），随后对隔离副本运行一次 PowerPoint 原生打开并导出全部页面 PNG；快速扫查全部页面，只检查内容遗漏、错图、不可读文字、裁切和严重遮挡，不作审美评判。默认不调用 LibreOffice、不生成 PDF 或 LibreOffice 页面图、不重复完整 OOXML/字体审计或成稿语义审校。出现异常、复杂模板或结构改动时，才升级静态检查。原生检查受阻时不操作用户 PowerPoint；完成轻量检查后可交付候选稿，并明确标记“PowerPoint 原生打开与导出未验证”。修复后只复查受影响项目。

**组会汇报**仍按[内容验收](references/chinese-style.md#内容验收)及[文件验收](references/rendering.md#验证)完成既有验收流程。两类结果分别记录；已知错误修复后交付，未验证项如实说明。

按制作参考在约定目录交付 PPTX；默认不额外交付 PDF/HTML。只有用户明确要求 PDF 时才生成 PDF；不主动清理过程文件。项目记录沿用共享规范，不追加制作流水。

## 后续修改

先读用户当前稿，只改本次要求，保留手工修改和删除。不用旧生成稿覆盖当前稿；一次不展开某项目不构成长期排除规则。


