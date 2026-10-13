---
name: lab-report-slides
description: >
  Generate Chinese advisor daily/weekly research PPTs from recent sessions, project records,
  experiments and real figures. Use for 生成今日汇报, 生成每日汇报, 生成本周组会汇报,
  生成组会 PPT, or turning recent research work into an advisor report.
  Select the advances worth reporting, confirm projects and overview text, then make the full
  deck without per-slide approval. Decide each page's point before writing or layout;
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

## 1. 核实并选定工作

日报取 `Asia/Shanghai` 当天，周报取截至请求日期的最近七个日历日；用户指定范围优先。按资料参考读取会话、项目记录和真实产物。

范围未定时给编号候选：名称、本期实质进展、状态、可用材料及展开建议，让用户删选或补充。听众、日期、模板已定或纠正一项状态，不等于选定全部内容。已指定工作直接沿用，不加入范围外项目。

没有适合科研汇报的实质进展时，询问停止还是改做私人工作记录。

## 2. 确认总览

展示完整总览正文，必要时附主要展开内容，不另设提纲审批。沿用已确认的范围、总览和详略；用户明确要求直接生成时跳过中间确认。只确认候选时仍完成总览确认，只有用户要求逐页讨论才逐页确认。

## 3. 核对图文并制作

总览确认后自行完成整套，不再询问是否开始。先做[内部逐页素材核对](references/materials.md#排版前逐页素材核对)，再做[表达审校](references/chinese-style.md#排版前表达审校)，之后排版。仅补问无法核实且影响页面含义的缺口，其他明确页面继续制作。

沿用已有工程、用户模板及项目约定；模板未选时询问一次内置或本地模板，等待期间继续核实素材。未回答不视为选择，有效模板适配可复用。

简单日报用随附生成器，指定工程继续原工程。直接制作可编辑 PPTX，供用户查看和修改；不先做 HTML 页面稿。HTML 默认关闭，显式选项见制作参考。调用其他制作工具仍沿用本技能的整套制作授权，分工和工具调用服从宿主规则。

## 4. 验收与交付

按[内容验收](references/chinese-style.md#内容验收)检查最终全部可见文字与图件，再按[文件验收](references/rendering.md#验证)检查可编辑对象、结构和实际渲染，两类结果分别记录。已知错误修复后交付，未验证项如实说明。

按制作参考在约定目录交付完整 PPTX；默认不额外交付 PDF/HTML，不主动清理过程文件。项目记录沿用共享规范，不追加制作流水。

## 后续修改

先读用户当前稿，只改本次要求，保留手工修改和删除。不用旧生成稿覆盖当前稿；一次不展开某项目不构成长期排除规则。
