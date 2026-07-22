---
name: xlsx
description: 处理以电子表格为主要输入或输出的全部任务，包括读取、问答、创建、编辑、修复、分析、清洗、重构、公式、格式、图表、数据验证、CSV/TSV 转换，以及复杂既有 XLSX/XLSM 模板的 OOXML 高保真修改、LibreOffice 无界面重算、公式缓存回填和 PDF 版面验证。用户只要提到 `.xlsx`、`.xlsm`、`.xltx`、`.xls`、`.csv`、`.tsv` 或“表格/工作簿”，并希望读取、修改或产出表格，就使用本 skill。不要用于实时控制已打开的 Excel、Google Sheets API，或主要交付物是 Word、PPT、网页、数据库管道而非表格的任务。
---

# XLSX

这是完整的表格技能，不依赖另一个通用 xlsx skill。先判断任务属于常规路线还是高保真路线，再用最小风险工具完成并验证交付。

## 先读

1. 读取项目和上级规则，确认输入、输出、覆盖限制、允许变化和 Office 边界。
2. 完整读取 [references/general-workflow.md](references/general-workflow.md)。
3. 创建或常规编辑工作簿时读取 [references/formatting-and-formulas.md](references/formatting-and-formulas.md)。
4. 复杂既有模板、严格差异或公式缓存任务，完整读取 [references/high-fidelity-workflow.md](references/high-fidelity-workflow.md)。
5. 使用定点 OOXML 补丁时读取 [references/patch-spec.md](references/patch-spec.md)。

## 路由

### 只读问答或审计

- 不保存、不导出、不改源文件。
- 同时读取公式和缓存值，按工作表、单元格和单位追溯答案。
- 用户问结果原因时，继续追到输入或假设，不停在中间合计。

### 新建工作簿

- 使用当前环境规定的表格作者工具；没有强制工具时使用 `openpyxl`，批量分析可配合 `pandas`。
- 将输入、公式和输出分清，保持数字、日期、百分比为真实类型。
- 创建后必须重算公式并做视觉检查。

### 常规编辑

- 先检查相邻值、公式、样式和既有约定。
- 只改用户要求的范围；新增行列时同步公式、表格范围、验证、条件格式和图表数据源。
- 简单工作簿可用结构化库保存为新版本，再做公式和版面检查。

### 高保真编辑

以下任一条件成立，进入高保真路线：

- 工作簿含绘图、图片、批注、VML、复杂验证、计算链、外部关系或精细打印设置；
- 用户要求“只改指定单元格”“其他内容全部保持”“比较 OOXML 包”；
- LibreOffice 重算后不能接受整包重写；
- 交付必须证明公式缓存、包对象和 PDF 分页同时正确。

高保真路线使用本 skill 的 OOXML 工具，不把常规库或 LibreOffice 整包输出直接当正式件。

### CSV/TSV

- 只保留表格数据语义；CSV/TSV 本身不承载样式、公式和多工作表。
- 明确编码、分隔符、引号、换行、日期和小数规则。
- 用户要求可编辑工作簿时再转换为 `.xlsx`，不要假装 CSV 能保留 Excel 功能。

## 工具选择

- 当前环境若提供带强制契约的表格 API，常规创建和编辑遵守该契约。
- 没有强制作者工具时：`openpyxl` 负责 `.xlsx/.xltx/.xlsm`；`pandas` 或标准库负责批量数据与 CSV/TSV。
- `scripts/patch_ooxml.py` 负责高保真定点补丁。
- `scripts/libreoffice_headless.py` 负责隔离重算和 PDF 导出，不使用 Office COM。
- `scripts/merge_formula_caches.py` 负责公式签名核对与缓存回填。
- `scripts/verify_xlsx.py`、`scripts/verify_pdf.py` 负责机器检查；最终仍需查看渲染结果。

## 基本边界

- 源文件默认只读。输出使用新文件名、递增版本或用户指定的新路径。
- 未获本次明确许可，不启动、连接或控制 Excel，不使用 Office COM 或 GUI 自动化。
- 不保存以 `data_only=True` 加载的工作簿；那会把公式替换成缓存值。
- 公式结果用公式表达，不用脚本计算后硬写静态结果，除非用户明确要求静态值。
- 不把标识符误写成数字；不把数字、日期、金额或百分比预格式化成普通文本。
- 既有模板优先级高于默认风格。不全表重排、不无关改色、不随意自动列宽。
- 无来源字段保持空白。外部事实记录来源，不根据常识补填。
- 输出路径已存在时先停下，不静默覆盖。

## 通用工作流

1. **确认任务**：区分只读、创建、常规编辑、高保真编辑、格式转换。
2. **检查输入**：读取工作表、已用范围、公式、缓存、样式、对象、合并和打印设置。
3. **建立约束**：列出允许变化、锁定字段、关键合计、公式和输出路径。
4. **实现**：选择常规作者工具或高保真 OOXML 路线。
5. **重算**：含公式的交付文件必须生成有效缓存；外部链接、宏或复杂公式先判断兼容性。
6. **数据验证**：检查公式错误、范围、合计、唯一性、类型、空白、排序和文本规则。
7. **视觉验证**：渲染全部相关工作表或导出 PDF，检查裁切、重叠、空白页、图表和打印范围。
8. **交付**：只链接正式文件；报告实际变化、公式检查、关键数值和仍未确认的事实。

## 公式规则

- 使用清楚、可追溯的引用；跨表引用正确处理工作表名称。
- 复制公式前确认绝对与相对引用方向。
- 范围扩展后检查首尾行、合计行、查找范围、条件格式和图表范围。
- 公式“无错误”不等于公式“正确”；抽查代表性输入和结果，核对业务合计。
- `<v/>` 为空不算有效公式缓存；必须有可解释的缓存值，字符串空结果除外。
- 出现 `#REF!`、`#DIV/0!`、`#VALUE!`、`#NAME?`、`#N/A` 等错误时不交付。

## 文件格式边界

- `.xlsx/.xltx`：完整支持。
- `.xlsm`：常规库加载时保留 VBA；高保真修改不触碰 `vbaProject.bin`。数字签名会因修改失效，先说明。
- `.xls`：先在隔离路径转换为 `.xlsx` 或只读提取；不覆盖原文件。
- `.xlsb`、加密文件：默认停止并说明当前工具限制。
- 外部链接工作簿：重算可能改变或丢失链接；未验证依赖文件前不整包重算。

## 高保真命令顺序

```powershell
python <skill-root>\scripts\verify_xlsx.py source.xlsx --json-out baseline.json
python <skill-root>\scripts\patch_ooxml.py source.xlsx draft.xlsx --spec patch.json
python <skill-root>\scripts\libreoffice_headless.py recalc draft.xlsx recalculated.xlsx
python <skill-root>\scripts\merge_formula_caches.py draft.xlsx recalculated.xlsx final.xlsx
python <skill-root>\scripts\verify_xlsx.py final.xlsx --baseline source.xlsx --policy policy.json
python <skill-root>\scripts\libreoffice_headless.py pdf final.xlsx final.pdf
python <skill-root>\scripts\verify_pdf.py final.pdf --render-dir rendered
```

Windows 下运行已保存的 `.py` 文件。不要把含中文路径或文本的 PowerShell here-string 管道到 `python -`。

## 完成标准

只读任务：答案有单元格依据，源文件未变化。

创建或编辑任务：

- 正式文件为独立输出，源文件哈希未变；
- 内容、类型、公式、合计和引用正确；
- 所有公式都有有效缓存，错误为 0；
- 格式与模板一致，图表和关键文本完整可见；
- 高保真任务的差异只落在获准范围，受保护 OOXML 条目保持；
- PDF 或渲染检查无空白页、窄页、重叠和裁切；
- 最终报告说明输出路径、变化范围、验证结果和未确认项。
