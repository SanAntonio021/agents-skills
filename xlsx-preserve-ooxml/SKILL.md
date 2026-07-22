---
name: xlsx-preserve-ooxml
description: 高保真修改和交付复杂现有 XLSX 模板，保留绘图、图片、批注、样式、数据验证、公式缓存、计算链和打印设置。凡用户要求“不覆盖原件”“只改指定单元格”“不得启动 Excel/Office COM”“LibreOffice 无界面重算”“比较前后 OOXML 包”“逐页检查 PDF”，或工作簿含复杂模板对象且整包重写风险不可接受时，必须使用本 skill。新建普通表格、CSV 清洗、常规数据分析或可接受整包重写的简单工作簿，使用通用 spreadsheets/xlsx skill，不使用本 skill。
---

# XLSX Preserve OOXML

对复杂既有工作簿做最小、可审计、可回退的修改。目标不是“文件能打开”，而是业务值正确、公式有缓存、包内对象未误改、打印版完整可读。

## 先读

1. 开始任务前读取项目和上级规则文件，确认源文件、允许变化、输出路径、Office/LibreOffice 边界。
2. 完整读取 [references/workflow.md](references/workflow.md)。
3. 使用定点补丁时读取 [references/patch-spec.md](references/patch-spec.md)。
4. 需要解释能力来源或维护边界时读取 [references/design-provenance.md](references/design-provenance.md)。

## 适用边界

使用本 skill：

- 修改带绘图、图片、批注、复杂样式、数据验证、打印定义或计算链的现有 `.xlsx`。
- 用户限定只改某些单元格、行高、分页或打印设置，并要求证明没有其他变化。
- 公式修改后需要无界面重算，但不能把 LibreOffice 整体改写后的包直接交付。
- 交付必须同时通过公式检查和 PDF 逐页版面检查。

不用本 skill：

- 从零创建普通工作簿、做常规分析、清洗 CSV/TSV。
- Google Sheets 或实时控制已打开的 Excel。
- `.xlsb`、加密文件。先报告不支持。
- 带数字签名的工作簿。任何修改都会使签名失效，先停下说明。

`.xlsm` 只能在明确保留 VBA 二进制和签名风险已处理时做包级定点修改；默认不交给 LibreOffice 重算。

## 不可破坏的边界

- 源文件只读。输出使用新文件名或递增版本号；脚本拒绝覆盖已有输出。
- 未获本次明确许可，不启动、连接或控制 Excel，不使用 Office COM 或 GUI 自动化。
- 不把 `data_only=True` 读取结果保存回工作簿。
- 不把 LibreOffice 重写的工作簿直接当高保真正式件。它只作为隔离重算源；将公式缓存合并回权威补丁版本。
- 不根据常识补业务字段。缺少来源的内容保持空白，并在报告中列明。
- 不把“ZIP 可解压”“公式无错误”当成版面已通过。公式与视觉验证缺一不可。

## 工作流

1. **冻结底稿**
   - 记录源文件绝对路径、大小、SHA-256、工作表、ZIP 条目和公式统计。
   - 识别外部链接、宏、数字签名、绘图、媒体、批注、数据验证、合并、打印定义和计算链。

2. **建立允许变化清单**
   - 明确允许修改的单元格、公式、行高、验证范围、分页和打印设置。
   - 明确锁定值、必须保持空白的字段、合计、唯一性和文本规则。
   - 没有清单时不开始写入。

3. **选择最小修改方式**
   - 已有单元格值、行高、验证范围和打印属性：优先 `scripts/patch_ooxml.py`。
   - 大规模插行或复杂结构变化：先在隔离副本使用适合的结构化库，再用本 skill 做包级审计；发现绘图、批注、关系或样式意外变化时，改为任务专用 OOXML 变换。
   - 不对既有模板做全表重排、全局自动列宽或无关样式统一。

4. **重算公式**
   - 用 `scripts/libreoffice_headless.py recalc` 生成隔离重算副本。
   - 用 `scripts/merge_formula_caches.py` 只把匹配公式的缓存结果合并回权威补丁版本。
   - 公式签名不一致、缓存缺失或出现错误值时停止交付。

5. **数据与包级验证**
   - 用 `scripts/verify_xlsx.py` 检查 ZIP、公式数、缓存数、错误数、允许变化和受保护条目。
   - 另做任务特定检查：金额、数量、总价、唯一资产、编号序列、必填/留空、关键词和文本长度。

6. **打印与视觉验证**
   - 用 `scripts/libreoffice_headless.py pdf` 导出隔离 PDF。
   - 用 `scripts/verify_pdf.py` 检查页数、方向、空白页和必需文本，并渲染高分辨率 PNG。
   - 逐页查看 PNG，确认所有目标列完整、无空白页、窄页、重叠、跨格和末尾裁切。自动检查不能替代逐页查看。

7. **交付**
   - 再跑一次最终只读检查。
   - 报告输出路径、允许变化、实际差异、公式/缓存/错误数、关键合计、PDF 页数、未填字段及原因。

## 推荐命令顺序

```powershell
python <skill-root>\scripts\verify_xlsx.py source.xlsx --json-out baseline.json
python <skill-root>\scripts\patch_ooxml.py source.xlsx draft.xlsx --spec patch.json
python <skill-root>\scripts\libreoffice_headless.py recalc draft.xlsx recalculated.xlsx
python <skill-root>\scripts\merge_formula_caches.py draft.xlsx recalculated.xlsx final.xlsx
python <skill-root>\scripts\verify_xlsx.py final.xlsx --baseline source.xlsx --policy policy.json --json-out verification.json
python <skill-root>\scripts\libreoffice_headless.py pdf final.xlsx final.pdf
python <skill-root>\scripts\verify_pdf.py final.pdf --render-dir rendered --json-out pdf-verification.json
```

在 Windows 上运行已保存的 `.py` 文件。不要把含中文路径或文本的 PowerShell here-string 管道到 `python -`。

## 工具说明

- `scripts/patch_ooxml.py`：按 JSON 规范定点修改现有单元格、行高、数据验证范围和打印设置。
- `scripts/libreoffice_headless.py`：使用隔离用户配置执行无界面 XLSX 重算或 PDF 导出，不依赖 Office COM。
- `scripts/merge_formula_caches.py`：核对公式签名后合并缓存，拒绝错误缓存和缺失缓存。
- `scripts/verify_xlsx.py`：检查包完整性、公式缓存、单元格语义差异和受保护条目。
- `scripts/verify_pdf.py`：检查 PDF 页数、方向、空白页、必需文本并调用 `pdftoppm` 渲染。

## 停止条件

遇到以下情况先报告，不静默换方案：

- 输出路径已存在或与源文件相同。
- 文件不是有效 OOXML ZIP，或已加密。
- 发现数字签名、无法解析的外部链接、宏重算风险。
- LibreOffice 改写了公式文本，或公式缓存不全、含错误值。
- 前后差异超出允许清单。
- PDF 自动检查或逐页检查未通过。

## 完成标准

- 源文件哈希未变，正式输出为独立版本。
- 差异只落在获准单元格、公式缓存或必要版式项。
- 公式缓存全部存在，错误为 0；关键业务合计与锁定值一致。
- 绘图、媒体、批注、样式、关系、验证和计算链按政策保持。
- PDF 全页覆盖目标范围，无空白页、窄页、重叠或裁切。
- 复核记录能让另一名审查者独立复现结论。
