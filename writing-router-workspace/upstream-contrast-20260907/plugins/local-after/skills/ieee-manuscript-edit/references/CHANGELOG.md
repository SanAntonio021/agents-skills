# Changelog

## 1.0.0 - 2026-08-16

- 新增英文 Markdown 和单文件 LaTeX 的“终稿规范化”模式。
- 新增只读 `audit_manuscript_conventions.py`，输出稳定 JSON 或 Markdown 报告。
- 将 Abstract、正文、每个图注和每个表注作为独立缩写作用域。
- 区分安全修复、人工复核、受保护科学限定和未解析结构。
- 增加图注自解释、防御性元话语和重复内容的保守检查。
- 增加否定链和间接否定的 review-only 审计，覆盖配对结构、固定短语、原子否定及编号屏蔽。
- 明确 `fail...to` 的长距离匹配、嵌套 `neither...nor`、小数点和面板 caption 的分句边界，并屏蔽 Setext/原始 HTML Markdown 结构、扩展 LaTeX 表格和行内代码。
- 否定链仍只生成人工复核候选；科学限定（包括 `cannot be ruled out` 和 `cannot be excluded`）不自动改写。
- 明确 `paper-review`、`latex-paper` 和 `style-vocab` 的职责边界。
