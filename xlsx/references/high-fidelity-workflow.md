# 高保真 XLSX 工作流

## 1. 先判断风险

先把 `.xlsx` 当 ZIP 包检查。出现以下任一对象时，不应默认用常规库整包保存：

- `xl/drawings/`、`xl/media/`、批注、VML；
- `xl/calcChain.xml`；
- 数据验证、条件格式、复杂合并、手动分页；
- 自定义打印区域、重复标题行、页面缩放；
- 外部链接、宏、数字签名。

普通值表没有这些对象，且用户不要求包级保真时，改用本 skill 的常规路线。

## 2. 冻结基线

对源文件做只读清点：

```powershell
Get-FileHash -Algorithm SHA256 source.xlsx
python <skill-root>\scripts\verify_xlsx.py source.xlsx --json-out baseline.json
```

基线至少记录：

- 文件哈希和 ZIP 完整性；
- 工作表名称与对应 XML；
- 包条目列表及每个条目 SHA-256；
- 公式数、缓存数、错误数；
- 绘图、媒体、批注、样式、计算链和工作表关系是否存在。

## 3. 写允许变化政策

`verify_xlsx.py` 的政策文件示例：

```json
{
  "allowed_cells": ["成信大!W6:W18", "成信大!Z6:Z18", "成信大!V17:V18"],
  "allowed_row_heights": ["成信大!17:18"],
  "allowed_package_entries": [],
  "required_unchanged_entries": [
    "xl/styles.xml",
    "xl/calcChain.xml",
    "xl/comments1.xml",
    "xl/drawings/drawing1.xml",
    "xl/media/image1.png"
  ],
  "allow_formula_cache_changes": true,
  "expected": {
    "formula_count": 37,
    "formula_cache_count": 37,
    "formula_error_count": 0
  }
}
```

允许范围必须来自用户要求或已批准整改清单。不要为了让检查通过而扩大范围。

## 4. 修改

### 4.1 定点补丁

读取 [patch-spec.md](patch-spec.md)，建立补丁 JSON：

```powershell
python <skill-root>\scripts\patch_ooxml.py source.xlsx draft.xlsx --spec patch.json
```

脚本保留未修改 ZIP 条目的内容和元数据，只重写确有变化的 XML 条目。它适合已有单元格、行高、验证范围和打印定义；不负责通用插行、公式平移或图表重构。

### 4.2 结构变化

需要插入多行时：

1. 先列明所有受影响公式、合并、验证、分页、打印区和绘图锚点。
2. 在独立中间文件完成结构变化。
3. 用前后语义差异和包条目差异判断常规库是否误改对象。
4. 如果误改超出允许范围，停止使用该中间文件，编写任务专用 OOXML 变换。

不要把“能打开”当作结构变化成功。

## 5. 重算与缓存回填

重算分三份文件：

- `draft.xlsx`：权威内容和格式版本；
- `recalculated.xlsx`：LibreOffice 隔离重算副本；
- `final.xlsx`：从 `draft.xlsx` 复制并回填公式缓存的正式版本。

```powershell
python <skill-root>\scripts\libreoffice_headless.py recalc draft.xlsx recalculated.xlsx
python <skill-root>\scripts\merge_formula_caches.py draft.xlsx recalculated.xlsx final.xlsx
```

回填前必须满足：

- 工作表集合一致；
- 每个目标公式单元格在重算副本中仍有公式；
- 公式文本和关键属性一致；
- 每个公式都有缓存；
- 缓存中没有 `#REF!`、`#DIV/0!`、`#VALUE!`、`#NAME?`、`#N/A` 等错误。

公式签名不同意味着 LibreOffice 可能重写了语义，不继续合并。

## 6. 包级复核

```powershell
python <skill-root>\scripts\verify_xlsx.py final.xlsx --baseline source.xlsx --policy policy.json --json-out verification.json
```

检查结果分三类：

- `cell_changes`：值、公式、样式或公式缓存变化；
- `sheet_feature_changes`：行高、合并、验证、分页、页面设置等；
- `package_changes`：工作表以外的 ZIP 条目变化。

只有变化在政策内且预期公式统计满足时，`ok` 才为 `true`。

业务检查另写任务脚本或断言，不塞进通用包级工具。例如金额合计、编号序列、唯一资产、必填/留空字段和文本禁词。

## 7. PDF 与视觉复核

```powershell
python <skill-root>\scripts\libreoffice_headless.py pdf final.xlsx final.pdf
python <skill-root>\scripts\verify_pdf.py final.pdf `
  --expected-pages 7 `
  --landscape `
  --expect-every-page "室外" `
  --render-dir rendered `
  --json-out pdf-verification.json
```

然后逐页查看 `rendered` 中的 PNG。重点看：

- 每页是否包含目标最右列；
- 是否出现仅表头页、仅少数列的窄页或空白页；
- 长文本末尾、编号列表末项是否完整；
- 行高、换行、边框和分页是否使一条记录跨页或被裁切；
- 页边距内是否有重叠、跨格和异常缩放。

文本提取能发现缺字和空白页，但不能证明视觉无裁切。若 PDF 字体缺少可靠的 Unicode 映射，脚本会把中文关键词标为 `required_text_unverifiable` 警告，不误报为实际缺字；此时必须在渲染图中人工确认。最终始终查看全部渲染页。

## 8. 最终报告

报告顺序：

1. 正式 XLSX、PDF、复核记录路径；
2. 实际修改范围；
3. 公式数、缓存数、错误数；
4. 关键合计、数量、唯一性、空白字段；
5. 包级未改对象；
6. PDF 页数和逐页结论；
7. 仍需人工确认的事实。
