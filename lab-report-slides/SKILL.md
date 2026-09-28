---
name: lab-report-slides
description: >
  Generate concise Chinese advisor daily/weekly research PPTs from local Codex and Claude
  sessions. Use for 生成今日汇报, 生成每日汇报, 生成本周组会汇报, 生成组会 PPT,
  or turning recent experiments, instrument tests, plots and results into slides.
  Verify research candidates, confirm the selected projects and overview text, then produce
  the full deck without per-slide approval;
  reuse confirmed choices and exclude non-research tool maintenance. Inventory all substantive
  work and outputs within selected projects before choosing representative real figures.
  Explain current progress with background where needed, collect confirmed next steps on the
  final slide, and polish Chinese prose. Create editable text and independent pictures with
  short titles, one result summary per page and flexible typography; inspect actual PPTX renders.
  Do not use for paper PDF/DOI-to-slides work.
compatibility: Windows with local Codex or Claude Code sessions; Python 3.10+, requirements.txt, LibreOffice, Poppler and the sibling libreoffice-runner skill. Node.js/sharp is optional for SVG input.
---

# 实验工作汇报幻灯片

将会话、项目记录与实际产物整理成导师能理解的中文日报或周报。主入口规定流程；资料、写作与制作细节按下表读取，不能只看链接就声称已加载。

## 按阶段读取

| 时机 | 必读资料 |
|---|---|
| 首次使用、依赖异常 | [安装与使用说明](README.md)，运行 `python scripts/check_dependencies.py` |
| 开始采集、筛选和核实素材 | [资料采集、筛选与复用](references/materials.md) |
| 起草总览、页面文字与末页 | [中文表达规则](references/chinese-style.md)，按其中要求加载通用写作检查 |
| 总览确认后制作、交付前验证 | [页面制作、渲染与验证](references/rendering.md) |
| 使用或更换本地 PPT/POTX 模板 | [本地模板适配](references/local-template.md) |

同一任务已实际读取且未变的材料直接复用，不重复加载。未安装的可选技能不视为可用。

## 1. 采集并核实工作

- 日报按 `Asia/Shanghai` 当天采集；周报为截至所请求日期的最近七个日历日。用户指定项目时只采集该项目及子目录，否则采集时间窗口内发现的项目，再筛选汇报范围。
- 读取实际记录和产物，区分已完成、进行中、实测、仿真、离线验证及方案；后来的可靠证据和用户更正优先。历史材料可解释背景，不算当天新成果。
- 优先复用现有实验结果与分析、飞书正文和表格、飞书画板及已有报告；先核对实际版本和适用性，再决定是否需要加工，具体见资料参考。
- 优先纳入科研结果、有价值的科研或项目交付物，以及直接解除科研阻塞且已验证的支撑工作。一般账号、代理、软件和技能维护不进入科研汇报。
- 没有实质科研进展、只剩常规支撑工作时，说明材料情况，询问停止还是改为私人工作记录，不凑页数。

## 2. 确认汇报项目

给出编号候选清单，每项包括项目或工作名称、当前状态、当期主要结果和可用图件，允许用户选择、删减或补充线下工作。仅日期、目录、听众或模板确定，不等于项目已选定；“生成今日汇报”不跳过选项讨论。

用户已明确指定的项目直接沿用，不重复确认，不擅自加入新项目。仅纠正一项状态不等于批准全部候选。入选后盘点该项目各项独立工作和产物，形成“工作项—结果/状态—来源与图件—详略及依据—页码”的覆盖清单，避免几张醒目图片替代完整进展。

## 3. 讨论并确认今日工作总览

项目确定后，下一条内容讨论直接展示完整总览正文，不只重复项目名称，也不先单独追问详略。周报采用对应的本周总览。

每项连接“项目总体目标 → 今天为此做了什么 → 已有结果或当前状态”。前因不能只停在“为进行下一步测试”等局部目的；不为缩成一行动作清单省掉必要对象和因果。总体目标缺失时先回查项目说明与相关讨论，仍无法核实才询问该缺口，不凭常识补造。

可随总览提出哪些简述、哪些展开的建议，由用户结合正文调整。已有详略或排除决定必须保留；未单独指定时按已确认总览、成果和图件自行安排，不机械把全部入选等同于全部展开。

## 4. 总览确认后直接制作整套

总览讨论并确认后，直接完成内容组织、选图、排版、检查和交付，不再逐页确认、单独批准提纲、补问详略或另行询问是否开始。仅确认项目清单尚不等于总览确认；用户已确认总览或明确要求直接生成时，沿用授权。只有用户明确要求逐页讨论时才采用逐页方式。

当前对话可直接制作，或按授权交给同一个子智能体或已有制作对话并跟进验收；不强制新建用户可见对话。创建对话和子智能体服从宿主规则，不为制作额外索取许可。使用 `pptx` 时复用工具和文件检查，本技能的整套制作流程优先于通用逐页讨论要求。

首页覆盖全部入选工作；已指定仅简述的项目不再展开。展开页按真实材料安排，每页围绕一个结果或问题，用图文讲清方法、条件与结果，不按固定页数压缩独立成果。一般措辞、页数、选图和排版由智能体处理；无法自行查明且会改变事实或范围的关键缺口才补问，同时继续其他页面。

最后一页为“下一步工作”，连接“项目总体目标 → 当前待解决的问题 → 下一步行动及目的”。只用已确定的安排，不补造任务或把预期目的写成既有结果；具体写法见中文表达参考。末页随整套完成，不另设讨论或确认环节。

## 模板与制作入口

本轮已指定的模板、工具或制作工程优先；项目已有模板选择直接沿用并提醒可更换。尚无选择时询问一次内置模板或用户本地模板，等待选择期间继续采集与核实，不能把未回答视为选用内置模板。选择记入项目已有说明，不写进公开技能。

本地模板先核对路径与哈希，变化或失效时按本地模板参考重新适配；不改原模板、不静默换模板。模板的尺寸、母版和版式优先于内置样式。首次适配测试及必要字号缺口按参考执行，不增加每日样页审批。

简单实验日报使用随附生成器；指定已有工程则继续该工程，不另生成平行稿。复杂场景按已安装工具处理，生成图不能替代真实曲线、仪器截图或实物照片。模板设置、JSON、命令和失败恢复见制作参考。

## 5. 检查、交付与后续修改

交付前按中文表达参考通读全部可见文字和图片内文字，核对事实、数字、状态、来源、图文对应与覆盖清单。总览和末页都应讲清因果，不能仅列动作；保留理解结果所需的条件，删除空话、重复和无关操作细节。

按制作参考检查文件结构、原生文字、独立图片与实际逐页渲染；内容检查和文件/排版检查分别记录。PowerPoint 原生打开与导出是独立验证项，不能用 LibreOffice 冒充，不能接管或关闭用户实例。未完成项如实报告，已知错误先修复。

在约定的正式目录交付完整 PPTX，保留旧稿与原始素材，不覆盖同名文件；过程材料和来源记录留在本任务过程目录，具体命名及依赖归位见制作参考。用户未要求时不额外交付 PDF/HTML，不主动清理过程文件。

后续修改先回读用户当前稿，按本次指定范围改动；不恢复用户删掉的页面，不用旧生成稿覆盖手工修改，也不把本次取舍升级成所有后续汇报的默认排除规则。
