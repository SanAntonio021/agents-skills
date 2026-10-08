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

面向导师讲清本期值得关注的科研推进。先决定讲什么、讲到什么程度，再写文字和排版；资料多、文件多或检查多不构成增加页面的理由。

## 资料入口

| 阶段 | 读取内容 |
|---|---|
| 首次使用或依赖异常 | [安装与使用](README.md)，运行 `python scripts/check_dependencies.py` |
| 核实材料、选择工作与详略 | [资料与选材](references/materials.md) |
| 写总览、组织展开页与下一步 | [内容与中文表达](references/chinese-style.md) |
| 制作及文件验收 | [制作与验证](references/rendering.md) |
| 使用或更换本地模板 | [模板适配](references/local-template.md) |

实际读取后再执行。同一任务中未变化的材料直接复用；可选技能未安装时使用随附规则。

## 1. 核实本期工作

日报按 `Asia/Shanghai` 当天，周报为截至请求日期的最近七个日历日；用户指定的范围优先。读取会话、项目记录和真实产物，后续可靠证据及用户更正优先。区分本期进展、历史背景、方案、仿真、离线验证和实测，不从文件时间或计划推断完成。

先了解各项实际工作，再选代表材料。采集与来源记录留在任务过程目录，原始资料保持原位。选用的信息必须准确，取舍方法按资料参考执行。

## 2. 选定汇报内容

范围尚未确定时，给出编号科研候选清单：名称、本期实质进展、状态及可用材料，并简短建议哪些值得展开。用户可以删选或补充线下工作。听众、日期或模板明确不等于内容已选；纠正一项状态也不等于批准全部候选。

已明确指定的工作直接沿用，不重复确认、不加入范围外项目。对入选材料在已有过程记录中记下来源和取舍：展开、总览简述或留在项目记录。盘点用于防遗漏，页面安排服从汇报重点。没有适合科研汇报的实质内容时说明情况，询问停止还是改为私人工作记录，不凑页数。

## 3. 确认总览

展示完整总览正文，讲清各项工作在研究什么、本期具体推进了什么及结果或状态。论文和方案要说出研究内容，不能仅报“写完引言、确定路线”。写法见中文表达参考；必要时随总览说明主要展开内容，不增加独立提纲审批。

沿用用户已经确认的范围、总览和详略。用户明确要求直接生成时直接制作，不插入中间确认；只确认候选而未确认总览时仍完成本阶段。只有用户要求逐页讨论才逐页确认。

## 4. 先定每页重点，再制作整套

总览确认后，智能体自行完成内容组织、选图、写作、排版与检查，不再补问详略或是否开始。每个拟展开主题先在已有过程记录中写清：这页要让导师知道什么，以及哪些材料支持它。这是内部规划，不交给用户逐页审批。按中文表达参考选择必要图、数据和条件；没有值得单独讲的内容就合并或留在总览。

首页覆盖全部入选工作。展开页可以讲结果、研究内容的实质变化、关键问题或实验能力的进展；不按产物数量分配页面，也不为了少页漏掉已确认必须讲的内容。最后一页汇总已确定的近期行动；不补造安排，不强制每项重述总体目标或展开整套验证流程。

已有制作工程、用户模板及项目约定优先。尚无模板选择时询问一次内置样式或本地模板；等待期间继续核实素材，不把未回答视为选择。模板及个人配置留在当前项目，有效适配直接复用，具体见模板参考。

简单日报用随附生成器；指定已有工程则继续该工程。复用真实图件，不以生成图片替代实验或文献曲线。使用 `pptx` 等工具时复用文件检查，沿用本技能的整套制作授权。分工、对话管理和工具调用服从宿主规则，不为制作额外索取许可。

## 5. 分别验收内容与文件

先审内容：通读最终 PPT 的全部可见文字，包括图片内文字，检查每页重点是否清楚、证据是否足够、细节是否必要，以及全套是否体现本期主要推进。重要方法、结果和解决的问题应有对应表达，影响判断的条件不能因精简而丢失。不能用词表零命中、材料完整或格式通过代替内容验收。检查方法见中文表达参考。

再按制作参考检查结构、原生文字、独立图片及实际逐页渲染；内容检查与文件/排版检查分别记录。PowerPoint 原生打开与导出独立记录，不以 LibreOffice 替代，不接管或关闭用户实例。已知错误先修复，未完成检查如实说明。

在约定正式目录交付完整 PPTX，保留旧稿与原始素材、不覆盖同名文件；预览和制作过程按制作参考存放。默认不额外交付 PDF/HTML，不主动清理过程材料。项目文档维护沿用共享规则，不因生成一次日报追加流水记录。

## 后续修改

先读取用户当前稿，按本次要求改动。保护手工修改，不恢复用户删掉的页面，也不用旧生成稿覆盖当前稿。用户删改可用于理解其重点和表达偏好；本次不展开某项目不构成长期排除该项目的规则。
