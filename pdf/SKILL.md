---
name: pdf
description: 读取、创建、检查和加工 PDF，包括扫描件、混合页面、损坏文字层、OCR、全文提取、合并拆页、旋转、水印、加密、图片提取、精确字段修改及按参考版式拼版。根据问题选择文字搜索、原页图像或 OCR；普通查询不默认生成新 PDF。Office 源文件由 docx、pptx、xlsx 处理，本技能检查转换后的 PDF。PDF 表单填写不在本技能范围内。
---

# 本地 PDF 处理

保留 Windows PDF 与 OCR 工具，按任务读取必要参考。复用当前文件、任务上下文和已有授权；只读请求交付回答，明确要求加工时完成修改和检查。

## 阅读与问答

- 先看文字层是否可信、正文是否为图像，以及问题所在位置。少量可提取字符可能只是页码或水印，不能据此认定整页可搜索。
- 根据问题选择文字搜索、相关页面图像或 OCR。位置未知、搜索未命中或内容不足时扩大读取范围，必要时处理全文，不设固定页数。
- 回到相关原页核对答案；表格、公式、批注、印章和复杂排版不能只凭 OCR 文本解释。说明实际页码及识别不清之处。
- 查询所需的预览或识别结果留在过程目录，不默认交付新的可搜索 PDF。

## 加工与交付

- 可搜索 PDF、可靠全文或文字层修复使用 [OCR 流程](references/ocr-workflow.md)，保留现有自动路由、语言选择和成品检查。
- 合并、拆页、旋转、水印、加密和创建按实际要求使用 pypdf、PyMuPDF、pdfplumber 或 ReportLab 等已有工具；检查页数、顺序、裁切、文字和受影响页面。创建时核对字体字形，尤其中文、上下标与数学符号。
- 精确修改字段或按参考拼版前，读取 [精确编辑与拼版](references/precise-editing.md)，检查原字体、局部背景、关联字段及最终页面。
- 字体、扫描背景或版式遇到困难时，在已授权范围内查找可行方法并在副本验证。确实达不到要求时说明具体差异，只暂停受影响部分，有未解决问题的版本标为草稿。
- 保留原稿和用户手工修改；续做读取当前文件。过程材料按共享规则放入同一任务目录，检查后只交付用户需要的 PDF、文本或其他成果，日志和辅助文件保留在过程目录。

## Office 分工

Word、PPT、Excel 源文件分别交给 [docx](../docx/SKILL.md)、[pptx](../pptx/SKILL.md)、[xlsx](../xlsx/SKILL.md) 读取、修改和转换；本技能检查生成 PDF 的页面、文字、裁切与排版。沿用已确定的目标应用和授权，不重复询问。

旧桥接、隔离及修复脚本保留兼容，必要调用见 [Windows 工具与桥接](references/windows-tools.md)。转换通过不等于 Office 原生验证通过；明确要求而未完成的原生检查如实标注。保护用户窗口，必要的 LibreOffice 调用沿用 `libreoffice-runner`。

## 按需参考

- [OCR 加工、路由及参数](references/ocr-workflow.md)
- [现有 OCR 运行环境记录](references/ocr-runtime.md)：历史安装版本和哈希，使用前核对实际可用性。
- [精确编辑与拼版检查](references/precise-editing.md)
- [Windows 工具与旧 Office 接口](references/windows-tools.md)

## 来源与许可

沿用原有 `anthropics/skills` PDF 文本来源说明（历史记录约 2025-10），保留 Windows 工具适配、OCR 路由与验证、精确编辑和矢量拼版等本地能力。本次删除基础代码教程，没有新增上游吸收。

原先排除的上游 Proprietary 文件 `LICENSE.txt`、`forms.md`、`reference.md`、`scripts/` 继续排除，PDF 表单填写不在本技能范围内。现有 [来源登记](references/upstream-sources.md) 保持原状态，历史来源说明不等同于新增已确认登记。
