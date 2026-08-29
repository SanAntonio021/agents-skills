# Word 权威验收清单

这份清单是 Markdown 到 Word 工作流的格式验收基线。它与四层门禁一一对应；渲染预览、OfficeCLI 诊断或任意 MCP 输出都不能替代清单中的证据。

## 验收项目

| 项目 ID | 检查内容 | 责任层 | 对比基线 | 硬阻断规则 |
|---|---|---|---|---|
| `fonts_and_fallback` | 中文、西文、数字、符号字体及字体回退一致 | `STATIC_PASS` | 批准的模板/样式配置与 OOXML 字体声明 | 发现未批准字体、意外回退或字体缺失 |
| `paragraph_formatting` | 段落样式、首行缩进、行距、段前段后、对齐方式一致 | `STATIC_PASS` | 批准的段落样式和直接格式审计 | 发现未批准的缩进、行距、对齐或样式漂移 |
| `table_formatting` | 表头、首列、单元格对齐、字体、列宽和边框一致 | `STATIC_PASS` | 批准的表格样式、列宽和 OOXML 属性 | 表头/首列未按基线对齐、字体不一致或列宽漂移 |
| `header_footer_geometry` | 页眉页脚文字、宽度、边界、距边和裁切状态 | `LO_RENDER_PASS` | LibreOffice 固定参数渲染页与页面边界 | 出现越界、遮挡、裁切或页眉页脚异常变形 |
| `pagination` | 页数、分页、表格跨页、空白页和编号连续性 | `LO_RENDER_PASS` | 批准栅格基线及页数记录 | 页数不一致、表格断裂、空白页或编号不连续 |
| `word_native_open` | Word 原生只读打开成功且页数可读取 | `NATIVE_OPEN_PASS` | 当前任务隔离副本和 Word 报告 | 打开失败、页数缺失或出现未处理恢复提示 |
| `word_native_render` | Word 原生导出 PDF，页数与栅格页数一致 | `NATIVE_RENDER_PASS` | 批准基线、固定 Poppler 命令和逐页检查 | 导出失败、页数不一致、栅格缺页或逐页检查失败 |

## 记录格式

机器清单中的每一项使用以下字段：

- `id`：上表项目 ID，七项必须全部出现且不得重复；
- `owner_layer`：对应责任层，不得跨层填写；
- `result`：`PASS`、`WARN` 或 `FAIL`；
- `severity`：`hard_block` 或 `warning`；`FAIL` 只能是硬阻断，`WARN` 只能是提示；
- `baseline`：实际采用的模板、样式、渲染或 Word 基线；
- `comparison`：实际执行的比较规则；
- `evidence_path`：证据文件路径，暂时没有独立文件时填写 `null`。

缺少项目、字段、基线、比较规则或责任层时，验收结果为 `UNVERIFIED`。允许带警告的技术通过，但在用户确认 Word 为最终版本前，必须把警告逐项展示。

## 人工逐页检查

每一页仍需填写原有的裁切、重叠、缺字、公式/表格断裂和分页异常项目，并与页面截图或渲染证据关联。人工逐页检查通过后，`NATIVE_RENDER_PASS` 才能写入 `PASS`。
