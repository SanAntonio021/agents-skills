---
name: daochu-geshi-zhengli
description: 将 Markdown-rich 文本安全导出到 Excel、Word 表格或纯文本介质。Use when 用户要把 Markdown 内容清洗成目标介质可直接承载的文本；如果最终要求是继承现有 Word 模板、`Normal.dotm` 或自动 Word 端样式，优先转到 `word-muban-geshihua`。
---

# 导出格式整理

## 作用

这份 skill 负责把 Markdown 内容变成目标介质能直接承载的干净文本，不把 Markdown 标记原样带过去。

## 流程

1. 先确认目标介质：
   Excel、Word 表格、数据库字段、表单系统，或其他纯文本输入框。
2. 如果目标是 `.docx`，且用户提到模板、默认 Word 格式、自动套用样式或 `Normal.dotm`，不要停在通用导出，直接转到 [../word-muban-geshihua/SKILL.md](../word-muban-geshihua/SKILL.md)。
3. 识别源文本里的 Markdown 语法：
   标题、列表、强调、引用和代码围栏等。
4. 导出前先做语法降噪，只保留干净文本和必要结构。
5. 真正需要样式时，在目标文件层实现样式，不在文本里残留 Markdown 记号。
6. 写入后抽样复核，确认没有残留 Markdown 符号或版式脏数据。

## 边界

- 不做通用文档写作或报告成稿。
- 不追求把 Markdown 样式逐像素复制到 Excel 或 Word。
- 不把 `**加粗**`、`# 标题` 或代码围栏原样写进目标单元格。
- 目标系统只支持纯文本时，优先保证内容干净，而不是勉强保样式。

## 相关技能

- Word 模板格式化：[../word-muban-geshihua/SKILL.md](../word-muban-geshihua/SKILL.md)

## 参考文件

- [references/guide.md](references/guide.md)

## 维护

- 维护重点是语法清洗和介质适配，不是通用写作。
- 新增导出目标时，先补规则，再补示例。
