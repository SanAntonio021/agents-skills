# Office COM

用途：PowerShell / Python COM 自动化 PowerPoint、Word、Excel 时，避免误关用户正在编辑的 Office 文档。

## 先判断

- 能用文件级检查就别启动 Office：PPTX/DOCX/XLSX 先按 zip/XML 结构检查。
- 只处理本次生成或用户明确指定的文件。
- 如果桌面可能已有未保存 Office 文档，先说明风险，再启动 COM。

## 最小护栏

- 启动前检查相关进程：`Get-Process POWERPNT,WINWORD,EXCEL -ErrorAction SilentlyContinue`。
- 如果连接到已有 Office 实例，只关闭自己打开的 document/presentation/workbook。
- 不确定是否独占实例时，不调用 `Quit()`。
- 导出预览或 PDF 后，先验证输出文件存在且非零长度，再考虑关闭对象。

## PowerPoint 导出预览

- 优先：zip 完整性检查 -> XML 结构检查 -> 必要时 COM 导出。
- COM 只打开目标 PPTX。
- 结束时关闭自己打开的 Presentation；不要关闭整个 PowerPoint 应用，除非确认本次创建的是独立实例且没有其他文档。

## Word 特例

如果 Word COM 报 `gen_py` / `pywin32` cache 问题，转读 [word-com-genpy-recovery.md](word-com-genpy-recovery.md)。
