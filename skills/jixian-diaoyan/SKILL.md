---
name: jixian-diaoyan
description: 分阶段执行项目基线调研，包含 sample-first 取样、证据链补齐和用户复核关口。Use when 用户要启动、继续或审查一项持续性的项目基线研究，而不是做一次性的零散查询。
---

# 基线调研

## 作用

这份 skill 把基线研究做成“可继续、可暂停、可复核”的项目工作流，而不是一次性抓取。

## 核心产物

在当前项目目录内，优先维护这些结果：

- `task pool`
- `design sheet`
- `baseline brief`
- `evidence workbook`
- `source-links record`
- `PPT-ready phrase shortlist`

如果项目已经有稳定命名，延续原文件，不强制改名。

## 流程

1. 先检查 `task pool` 和 `design sheet` 是否已存在。
2. 如果不存在，就用模板初始化：
   - [references/task_pool_template.md](references/task_pool_template.md)
   - [references/design_sheet_template.md](references/design_sheet_template.md)
3. 在大规模搜索前，先把 `design sheet` 补到可用。
   至少写清目标、范围、比较维度、关键指标、证据优先级，以及是否必须做浏览器复核。
4. 先做 sample-first 取样，再决定是否扩展。
5. sample 完成后要先暂停，等用户确认指标口径和证据标准，再继续扩展剩余类别。
6. 扩展阶段，对每条关键指标执行 source closure，尽量把证据链补闭。

## 证据规则

- URL 不是证据本身。
- 每条关键记录尽量落到可访问页面、页面标题和支持摘录。
- 证据链未闭合时，明确标为待复核，不假装已验证。

## 浏览器复核

静态抓取弱、受阻或页面逻辑复杂时，切到 [../../vendor/playwright-interactive/SKILL.md](../../vendor/playwright-interactive/SKILL.md)。

常见触发信号：

- `403`
- `404`
- 只落到首页
- JS 渲染导致静态内容缺失
- 跳转异常
- 指标记录和引用页面互相冲突

## 边界

- 不用于持续监控。
- 不用于没有项目产物承接的泛文献综述。
- 不把它当成一次性查事实的普通 skill。
- 证据标准未定前，不跳过 sample 阶段。

## 汇报方式

每轮结束时，至少说明：

- 当前阶段
- 新建或更新了哪些文件
- 哪些记录仍有来源冲突或证据缺口
- 用户下一步最需要确认什么

## 维护

- 保持它专注于分阶段基线调研，不外溢成泛用研究 skill。
- 如果项目模板变化，优先改模板，再回到这里保持正文简洁。
