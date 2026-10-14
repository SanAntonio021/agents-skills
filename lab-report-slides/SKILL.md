---
name: lab-report-slides
description: >
  Generate Chinese advisor daily/weekly research PPTs from recent sessions, project records,
  experiments and real figures. Use for 生成今日汇报, 生成每日汇报, 生成本周组会汇报,
  生成组会 PPT, or turning recent research work into an advisor report.
  Ask for the work scope first when unspecified. For daily reports, confirm the overview;
  for group meetings, discuss and confirm each section before making the full deck.
  Neither mode requires per-slide approval by default. Give each detail page one core point;
  keep routine editing, execution and validation details in project records.
  Preserve research substance, essential evidence and user edits. Deliver editable text and
  independent images after content review and actual PPTX rendering. Do not use for turning
  a single paper PDF or DOI into a literature presentation.
compatibility: Windows with local Codex or Claude Code sessions; Python 3.10+, requirements.txt, LibreOffice, Poppler and the sibling libreoffice-runner skill. Node.js/sharp is optional for SVG input.
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

## 1. 选定工作，再核实材料

日报取 `Asia/Shanghai` 当天，周报取截至请求日期的最近七个日历日；用户指定范围优先。

范围未定时先问要汇报哪些工作，不先扫描会话并自行选材。用户要求帮助盘点时，再按资料参考读取本期记录，给编号候选：名称、本期实质进展、状态、可用材料及展开建议，让用户删选或补充。已指定工作直接沿用，随后深入核实对应会话、项目记录和真实产物，不加入范围外项目。听众、日期、模板已定或纠正一项状态，不等于选定全部内容。

“帮我做 PPT”授权制作，不等于授权自行决定汇报范围。“直接生成”可跳过中间内容确认，但范围不明时仍先询问；明确授权自行选材并直接生成时，才可自行选定范围并制作。

没有适合科研汇报的实质进展时，询问停止还是改做私人工作记录。

## 2. 按汇报类型讨论内容

- **每日汇报**：展示完整工作总览正文，必要时附主要展开内容。讨论并确认总览后自行安排展开页，直接制作整套；只选定工作不等于确认总览，不另设提纲或逐页审批。
- **组会汇报（含周组会）**：先明确各部分及顺序，再逐部分讨论研究问题、主要内容、结果或判断、证据图和必要展开程度。各部分全部确认后，自行安排分页并生成整套，不再增加总览、提纲或逐页的重复审批。

已有范围、总览、各部分内容及详略确认持续有效；局部更正只处理受影响内容，不重启整套讨论。用户明确要求逐页讨论、提前制作已确认部分或直接生成时，沿用相应授权；直接生成的范围边界见上一节。

## 3. 核对图文并制作

日报总览或组会各部分确认后自行完成整套，不再询问是否开始。先做[内部逐页素材核对](references/materials.md#排版前逐页素材核对)，再做[表达审校](references/chinese-style.md#排版前表达审校)，之后排版。仅补问无法核实且影响页面含义的缺口，其他明确页面继续制作。

沿用已有工程、用户模板及项目约定；模板未选时询问一次内置或本地模板，等待期间继续核实素材。未回答不视为选择，有效模板适配可复用。

简单日报用随附生成器，指定工程继续原工程。直接制作可编辑 PPTX，供用户查看和修改；不先做 HTML 页面稿。HTML 默认关闭，显式选项见制作参考。内容讨论与确认节奏由本技能统一负责，调用其他制作工具不重启确认，也不自动要求新建独立制作对话；已有制作安排和用户指定方式继续沿用。工具选择、文件保护与共同文件验收沿用 `pptx`，分工和工具调用服从宿主规则。

## 4. 验收与交付

按[内容验收](references/chinese-style.md#内容验收)检查最终全部可见文字与图件，再按[文件验收](references/rendering.md#验证)检查可编辑对象、结构和实际渲染，两类结果分别记录。已知错误修复后交付，未验证项如实说明。

按制作参考在约定目录交付完整 PPTX；默认不额外交付 PDF/HTML，不主动清理过程文件。项目记录沿用共享规范，不追加制作流水。

## 后续修改

先读用户当前稿，只改本次要求，保留手工修改和删除。不用旧生成稿覆盖当前稿；一次不展开某项目不构成长期排除规则。
