---
name: xlsx
description: 处理以电子表格为主要输入或输出的全部任务，包括读取、问答、创建、编辑、修复、分析、清洗、重构、公式、格式、图表、数据验证、CSV/TSV 转换，以及复杂既有 XLSX/XLSM 模板的 OOXML 高保真修改、LibreOffice 无界面重算、公式缓存回填和 PDF 版面验证。用户只要提到 `.xlsx`、`.xlsm`、`.xltx`、`.xls`、`.csv`、`.tsv` 或“表格/工作簿”，并希望读取、修改或产出表格，就使用本 skill。不要用于实时控制已打开的 Excel、Google Sheets API，或主要交付物是 Word、PPT、网页、数据库管道而非表格的任务。
---

# XLSX

这是完整的表格技能，不依赖另一个通用 xlsx skill。先判断任务属于常规路线还是高保真路线，再用最小风险工具完成并验证交付。

## OfficeCLI route

常规工作簿的只读检查、文本化查看、结构查询和小批量结构编辑，优先经过本 skill 内的
OfficeCLI bridge；这样 Codex 和 Claude 使用同一套 CLI 接口和安全边界：

```powershell
python <skill-root>\scripts\officecli_bridge.py view input.xlsx text
python <skill-root>\scripts\officecli_bridge.py view input.xlsx stats
python <skill-root>\scripts\verify_xlsx.py input.xlsx --json-out baseline.json
python <skill-root>\scripts\officecli_bridge.py mutate input.xlsx draft.xlsx batch --input commands.json
```

桥接器固定使用 OfficeCLI `1.0.144`，每次调用都会先核对文件存在、SHA-256 和报告版本。普通
表格任务不会联网下载或自动修复；只有用户明确运行
`python <skill-root>\scripts\repair_officecli.py --repair` 才会修复默认本机路径。设置
`OFFICECLI_EXE` 时也必须通过相同校验，路径错误应自行修正或取消环境变量；修复脚本不会改写
覆盖路径。

桥接器会复制到新候选文件并拒绝覆盖已有输出。OfficeCLI 不负责公式重算、复杂样式保真、
宏签名或打印版面验收，也不作为 XLSX schema 校验器：OfficeCLI `1.0.144` 会把有效的
`styles.xml` 字体颜色节点误报为 schema 错误，bridge 因此提前拒绝 XLSX `validate`，正式校验
统一使用 `verify_xlsx.py`。遇到高保真模板、公式缓存、外部链接、图表/验证/VML 或精确 OOXML
差异要求时，继续使用本技能的 `openpyxl`/OOXML 工具和 `libreoffice-runner` 重算路径。
OfficeCLI 仅提供诊断预览，不能把 Excel 截图当作其原生验收能力。OfficeCLI
`--render native` 的失败统一记录为 `officecli_native_diagnostic_failed`，保留原始 stderr
和退出码，不能据此判断 Excel 未安装；HTML 截图仅能显式传入
`--render html --non-fidelity-preview` 作为诊断预览，不能用于正式图像、PDF 版面、打印/分页
验收或论文图。OfficeCLI `validate` 或 `verify_xlsx.py` 通过也不等于 Excel 原生可打开。

## Acceptance layers

Keep these records separate:

- `STATIC_PASS`: `verify_xlsx.py`、公式/结构/源文件哈希检查。
- `LO_RENDER_PASS`: 默认的 LibreOffice 重算/兼容渲染和视觉检查。
- `NATIVE_OPEN_PASS`: 仅在任务明确需要 Excel 兼容性时，独立 gate 只读打开隔离副本并读取
  工作簿/工作表结构。
- `NATIVE_RENDER_PASS`: XLSX 不提供此门禁；`--require-render` 会被拒绝。

Excel 原生打开是可选门禁，不是默认动作。需要时运行：

```powershell
python <skill-root>\scripts\office_native_gate.py check input.xlsx `
  --format xlsx --json --allow-office-com
```

该 gate 返回 `PASS`、`FAIL_OPEN`、`FAIL_RENDER`、`APP_UNAVAILABLE`、`UNVERIFIED` 或
`UNSAFE_PROCESS`，并记录真实阶段和异常。它要求当前任务显式传入 `--allow-office-com`，发现
`EXCEL.EXE` 即停止，使用 `DispatchEx` 和隔离副本，只读打开，不重算、不保存、不覆盖源文件，
并仅在确认任务创建且 `Workbooks.Count == 0` 时退出实例。默认 XLSX 发布门禁是
`STATIC_PASS` + `LO_RENDER_PASS`；只有任务声明需要 Excel 兼容性时才追加 `NATIVE_OPEN_PASS`。

`verify_xlsx.py` 除公式、筛选和 ZIP 完整性外，还检查 `workbook.xml` 的工作表名称、
`sheetId`、关系、可见工作表和活动页。半角禁用字符，以及名称经 NFKC 归一化后出现的禁用
字符，均为 Excel 兼容硬错误；这能在生成阶段拦住某些 OOXML schema 本身接受、但 Excel 会要求
修复的工作簿。它仍不能替代本机 Excel 原生打开复测。

## 先读

1. 读取项目和上级规则，确认输入、输出、覆盖限制、允许变化和 Office 边界。
2. 完整读取 [references/general-workflow.md](references/general-workflow.md)。
3. 任务会产生文件时完整读取 [references/output-lifecycle.md](references/output-lifecycle.md)。
4. 创建或常规编辑工作簿时读取 [references/formatting-and-formulas.md](references/formatting-and-formulas.md)。
5. 复杂既有模板、严格差异或公式缓存任务，完整读取 [references/high-fidelity-workflow.md](references/high-fidelity-workflow.md)。
6. 使用定点 OOXML 补丁时读取 [references/patch-spec.md](references/patch-spec.md)。

## 路由

### 工程产品调研工作簿

当工作簿承载工程技术产品的调研、产品库、设备/竞品参数比较或采购渠道，并需要 sample-first 字段、证据与正式表分离、稳定产品编号或采购一对多关联时，同时加载 `product-research-workbook`。本技能继续负责通用 XLSX 作者工具、OOXML、超链接、公式和视觉验收，不复制产品研究语义规则。

### 只读问答或审计

- 不保存、不导出、不改源文件。
- 同时读取公式和缓存值，按工作表、单元格和单位追溯答案。
- 用户问结果原因时，继续追到输入或假设，不停在中间合计。

### 新建工作簿

- 使用当前环境规定的表格作者工具；没有强制工具时使用 `openpyxl`，批量分析可配合 `pandas`。
- 将输入、公式和输出分清，保持数字、日期、百分比为真实类型。
- Excel Table 自带该表范围的筛选；不得再设置与任何 Table 范围相交的工作表级 `autoFilter`（例如 `openpyxl` 的 `ws.auto_filter.ref`）。
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
- `scripts/publish_output.py` 负责把已验证候选发布到正式路径；其他作者工具仍只能写不存在的候选路径。

## 基本边界

- 用户原文件、任务开始前已存在的文件、已交付文件和归属不明文件默认受保护，不覆盖。
- 当前任务创建、尚未交付且未被用户接管的草稿，只有在上次记录的 SHA-256 仍匹配时，才可通过 `publish_output.py` 复用原路径。
- 文件首次在最终回复中正式链接后即为已交付；后续修正默认生成递增版本。用户提前查看、打开、编辑或接管草稿时，先转为受保护状态再链接。
- OfficeCLI、OOXML 和 `libreoffice-runner` 继续只生成不存在的候选路径，不直接覆盖任何已有文件。
- 候选、重算副本、渲染结果和中间 JSON 放入任务独占临时目录；正式文件发布并验证后，在最终回复前只清理当前任务明确拥有的临时产物。
- 未获本次明确许可，不启动、连接或控制 Excel，不使用 Office COM 或 GUI 自动化。
- 不保存以 `data_only=True` 加载的工作簿；那会把公式替换成缓存值。
- 公式结果用公式表达，不用脚本计算后硬写静态结果，除非用户明确要求静态值。
- 不把标识符误写成数字；不把数字、日期、金额或百分比预格式化成普通文本。
- 既有模板优先级高于默认风格。不全表重排、不无关改色、不随意自动列宽。
- 无来源字段保持空白。外部事实记录来源，不根据常识补填。
- 草稿不在 commentary 中链接。用户要求提前查看时，链接动作本身会结束草稿的可替换状态。

## 通用工作流

1. **确认任务**：区分只读、创建、常规编辑、高保真编辑、格式转换。
2. **检查输入**：读取工作表、已用范围、公式、缓存、样式、对象、合并和打印设置。
3. **建立约束**：列出允许变化、锁定字段、关键合计、公式和输出路径。
4. **实现**：选择常规作者工具或高保真 OOXML 路线，在任务独占临时目录生成不存在的候选文件。
5. **重算**：含公式的交付文件必须生成有效缓存；外部链接、宏或复杂公式先判断兼容性。
6. **数据验证**：检查公式错误、范围、合计、唯一性、类型、空白、排序和文本规则。
7. **视觉验证**：渲染全部相关工作表或导出 PDF，检查裁切、重叠、空白页、图表和打印范围。
8. **发布与交付**：按 [references/output-lifecycle.md](references/output-lifecycle.md) 通过受控发布器落位；只在最终回复链接正式文件，并报告实际变化、公式检查、关键数值和仍未确认的事实。

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
python <skill-root>\scripts\verify_xlsx.py source.xlsx --json-out <task-temp>\baseline.json
python <skill-root>\scripts\patch_ooxml.py source.xlsx <task-temp>\draft.xlsx --spec <task-temp>\patch.json
python <skill-root>\scripts\libreoffice_headless.py recalc <task-temp>\draft.xlsx <task-temp>\recalculated.xlsx
python <skill-root>\scripts\merge_formula_caches.py <task-temp>\draft.xlsx <task-temp>\recalculated.xlsx <task-temp>\candidate-final.xlsx
python <skill-root>\scripts\verify_xlsx.py <task-temp>\candidate-final.xlsx --baseline source.xlsx --policy <task-temp>\policy.json
python <skill-root>\scripts\libreoffice_headless.py pdf <task-temp>\candidate-final.xlsx <task-temp>\candidate-final.pdf
python <skill-root>\scripts\verify_pdf.py <task-temp>\candidate-final.pdf --render-dir <task-temp>\rendered --pdftoppm <absolute-pdftoppm-executable>
python <skill-root>\scripts\publish_output.py <task-temp>\candidate-final.xlsx <formal-destination.xlsx>
```

Windows 下显式解析带 `.exe` 的 Poppler 程序，避免无扩展名命令命中运行时里的失效包装器：

```powershell
$pdftoppm = (Get-Command pdftoppm.exe -ErrorAction Stop).Source
python <skill-root>\scripts\verify_pdf.py final.pdf --render-dir rendered --pdftoppm $pdftoppm
```

Windows 下运行已保存的 `.py` 文件。不要把含中文路径或文本的 PowerShell here-string 管道到 `python -`。

## 完成标准

只读任务：答案有单元格依据，源文件未变化。

创建或编辑任务：

- 正式文件通过受控发布器落位，源文件哈希未变；
- 内容、类型、公式、合计和引用正确；
- 所有公式都有有效缓存，错误为 0；
- 格式与模板一致，图表和关键文本完整可见；
- 高保真任务的差异只落在获准范围，受保护 OOXML 条目保持；
- PDF 或渲染检查无空白页、窄页、重叠和裁切；
- 最终报告说明输出路径、变化范围、验证结果和未确认项；首次链接后将该路径视为已交付、受保护文件；
- 发送最终回复前，任务独占临时目录中由当前任务拥有的候选、重算副本、渲染结果和中间 JSON 已清理。
