---
name: xlsx
description: 处理独立电子表格文件，包括读取、问答、创建、编辑、修复、分析、清洗、重构、公式、格式、图表、数据验证、CSV/TSV 转换，以及复杂既有 XLSX/XLSM 模板的 OOXML 高保真修改、LibreOffice 无界面重算、公式缓存回填和 PDF 版面验证。用户提到 `.xlsx`、`.xlsm`、`.xltx`、`.xls`、`.csv`、`.tsv` 或本地表格/工作簿文件，并希望读取、修改或产出文件时使用。不要用于已打开或当前活动的 Excel 工作簿、当前选区、ChatGPT Excel 加载项或已连接 Excel 会话；这些实时操作交给 `spreadsheets:excel-live-control`。也不要用于 Google Sheets API，或主要交付物是 Word、PPT、网页、数据库管道而非表格的任务。
---

# XLSX

这是完整的表格技能，不依赖另一个通用 xlsx skill。先读当前任务和文件，复用已确定的范围与授权；按实际影响选择常规或高保真路线，以及需要的重算和版面检查。

## 文件存放与交付

- 项目根目录只放正式成果；候选、脚本、预览、核验记录和工具内部工程统一放在 `项目/过程文件/任务主题/`。同一任务续做及跨技能协作复用该目录；独立同名任务追加 `_YYYYMMDD`，仍重名追加 `_02`。只创建实际需要的目录，不搬动已有项目文件。
- 沿用项目命名习惯；没有约定时用 `内容主题_v01.扩展名`，同名递增版本。生成并通过必要检查后，由智能体在最终回复前自动复制正式成果到根目录，复核复制后的哈希、可打开性及必要依赖，并给出正式路径链接。需要用户挑选时，选定后再交付；不另设确认环节。
- 使用工具的显式输出参数或将工作目录设到任务过程目录，保留工具所需内部结构；正文命令中的相对输出路径均以该目录为基准，技能脚本及输入路径使用绝对路径。不修改上游插件缓存。可编辑源、正式工程及原始数据保留其用途，不一律当作临时文件。
- 普通任务结束后保留过程材料，只有用户显式触发 ChatNote（`chat-notes`）才进入可恢复清理；不自动清空过程目录。工具用于进程隔离、安全回滚的内部暂存清理不等于任务清场，仍遵守原有保护门。

## 边界路由

- 输入或交付物是独立 `.xlsx`、`.xlsm`、`.xltx`、`.xls`、`.csv`、`.tsv` 文件时，使用本 skill。
- 目标是已打开或当前活动的 Microsoft Excel 工作簿、当前选区、ChatGPT Excel 加载项或已连接 Excel 会话时，停止本地文件工作流，改用 `spreadsheets:excel-live-control`。
- 同一任务从独立文件切换到已连接 Excel 会话后，重新确认目标，不把本 skill 的 OfficeCLI、OOXML、LibreOffice 或 Office COM 路线用于实时会话。

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
差异要求时，继续使用本技能的 `openpyxl`/OOXML 工具；需要重算时使用现有 `libreoffice-runner` 隔离路径。
OfficeCLI 仅提供诊断预览，不能把 Excel 截图当作其原生验收能力。OfficeCLI
`--render native` 的失败统一记录为 `officecli_native_diagnostic_failed`，保留原始 stderr
和退出码，不能据此判断 Excel 未安装；HTML 截图仅能显式传入
`--render html --non-fidelity-preview` 作为诊断预览，不能用于正式图像、PDF 版面、打印/分页
验收或论文图。OfficeCLI `validate` 或 `verify_xlsx.py` 通过也不等于 Excel 原生可打开。

## Acceptance layers

Keep these records separate:

- `STATIC_PASS`: `verify_xlsx.py`、公式/结构/源文件哈希检查。
- `LO_RENDER_PASS`: 实际执行并查看后的 LibreOffice 渲染结果；不是所有表格任务的默认要求，重算成功不等于视觉检查通过。
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
并仅在确认任务创建且 `Workbooks.Count == 0` 时退出实例。创建或编辑任务按下节完成文件检查、
必要计算和版面检查；只有任务声明需要 Excel 兼容性时才追加 `NATIVE_OPEN_PASS`。
只读查询不因这些交付检查启动写入。未运行的步骤如实标为未运行或不需要，不登记为通过。

`verify_xlsx.py` 除公式、筛选和 ZIP 完整性外，还检查 `workbook.xml` 的工作表名称、
`sheetId`、关系、可见工作表和活动页。半角禁用字符，以及名称经 NFKC 归一化后出现的禁用
字符，均为 Excel 兼容硬错误；这能在生成阶段拦住某些 OOXML schema 本身接受、但 Excel 会要求
修复的工作簿。它仍不能替代本机 Excel 原生打开复测。

## 按实际影响选择检查

- **只读查询**：只读取相关数据、公式和缓存；不保存、重算或默认生成预览。缓存缺失、过期疑点或已有错误如实说明，不用修改文件来完成查询。
- **计算未变**：文字、格式或数据修改不影响公式及其输入、引用范围、匹配条件，且已有缓存可靠时，保留公式和缓存即可，不整本重算。核对实际依赖，不能只凭“改文字”判断；例如分类文字可能参与 `SUMIF`。无法可靠判断依赖或时效时，不声称旧结果准确。
- **计算变化**：新增公式、修改计算输入或引用范围、影响条件匹配，以及缓存缺失或可能过期时，执行必要重算并核对代表性输入、结果及错误。外部链接、宏和复杂公式先核对现有引擎是否适用；不能满足时说明具体未完成项。
- **视觉变化**：新增或改变文字、样式、图表、行列布局时，查看实际渲染中的受影响区域及关联影响；仅数据处理且呈现未受影响时不强制渲染。打印或 PDF 任务检查最终全部相关页面，包括分页、裁切与内容完整性，不默认给普通任务另交 PDF。
- **保留结果**：按需使用 OOXML 定点修改，比较修改前后的公式、缓存及受保护对象。常规库保存可能清空缓存，不能把“没改公式”当作结果已保留；若保存造成丢失，换用保留缓存的方法或对当前候选正确重算。

检查计划由智能体根据当前文件决定，不另设阶段确认。沿用现有校验器接口；有非零结果时解释具体问题，不能把已有错误、缺缓存或跳过步骤改报为通过。

## 先读

1. 读取项目和上级规则，确认输入、输出、覆盖限制、允许变化和 Office 边界。
2. 完整读取 [references/general-workflow.md](references/general-workflow.md)。
3. 任务会产生文件时完整读取 [references/output-lifecycle.md](references/output-lifecycle.md)。
4. 创建或常规编辑工作簿时读取 [references/formatting-and-formulas.md](references/formatting-and-formulas.md)。
5. 复杂既有模板、严格差异或公式缓存任务，完整读取 [references/high-fidelity-workflow.md](references/high-fidelity-workflow.md)。
6. 使用定点 OOXML 补丁时读取 [references/patch-spec.md](references/patch-spec.md)。

## 路由

### 工程产品调研工作簿

- 普通产品参数或一次性多采购渠道对比直接使用本技能，按实际需要列产品、可比参数、单位、来源和必要备注；不同参数来自不同资料时保留可定位的对应关系。不强制建立过程账本、长期编号、固定身份/采购列或双工作簿。
- 资料由用户提供，或由当前智能体通过现有 `web-access` 路径收集核实，再进入表格制作；本技能负责文件、公式、样式、链接和验收，不新增调研管理或联网流程。
- 当前智能体读取请求和已有文件后，只有明确建立/持续维护产品库、更新已采用产品库契约的业务记录，或明确按该契约审计时，才结合 `product-research-workbook`。依据实际维护、跨版本编号和来源关联要求判断，不按数量、文件名或孤立关键词分类；实质歧义才询问，已有要求不重复确认。
- 已有双表产品库的业务更新继续沿用原契约；仅调整格式时仍走本技能，不因此迁移工作簿、清理历史编号或新增账本。更新既有产品库的参数、编号或来源关联时，即使只改一个单元格，也结合产品库技能维护原有过程记录。

### 只读问答或审计

- 不保存、不导出、不改源文件，不为查询启动重算；明确要求已有 PDF 检查时只读检查该文件。
- 同时读取公式和缓存值，按工作表、单元格和单位追溯答案。
- 用户问结果原因时，继续追到输入或假设，不停在中间合计。

### 新建工作簿

- 使用当前环境规定的表格作者工具；没有强制工具时使用 `openpyxl`，批量分析可配合 `pandas`。
- 将输入、公式和输出分清，保持数字、日期、百分比为真实类型。
- Excel Table 自带该表范围的筛选；不得再设置与任何 Table 范围相交的工作表级 `autoFilter`（例如 `openpyxl` 的 `ws.auto_filter.ref`）。
- 新建公式需实际重算和检查结果；无公式的值表不运行重算。按上节检查新建的可见布局或图表，纯 CSV/TSV 数据交付不制造版面预览。

### 常规编辑

- 先检查相邻值、公式、样式和既有约定。
- 只改用户要求的范围；新增行列时同步公式、表格范围、验证、条件格式和图表数据源。
- 简单工作簿可用结构化库保存为新版本，但须核对缓存及对象是否保留；按实际计算和呈现影响检查，不因保存文件就固定整本重算、整本渲染。

### 高保真编辑

以下任一条件成立，进入高保真路线：

- 工作簿含绘图、图片、批注、VML、复杂验证、计算链、外部关系或精细打印设置；
- 用户要求“只改指定单元格”“其他内容全部保持”“比较 OOXML 包”；
- LibreOffice 重算后不能接受整包重写；
- 交付必须证明公式缓存、包对象和 PDF 分页同时正确。

高保真路线使用本 skill 的 OOXML 工具，不把常规库或 LibreOffice 整包输出直接当正式件。

### 参考实例分支

当用户要求“仿照某子表/示例表/已有格式”并明确给出参考工作表或区域时，先进入参考实例分支，再选择常规或高保真实现：

- 在写入前记录参考实例的纵向/横向方向、表头和列顺序、合并范围、列宽、行高、换行与对齐、字体属性及加粗范围；不要只复制文字。
- 优先复制参考工作表或建立可追溯的样式映射，再填入目标内容；不得用默认样式或自动排版覆盖实例结构。
- 验收时做结构差异检查和渲染检查，并单独核对文本单元格的加粗范围，确认层级标题、字段标题和正文没有错加或漏加粗。
- 用户未提供参考实例时，继续使用普通模板优先流程，不把实例分支的约束强加到任务；用户说“仿照”但未指明实例时，编辑前只询问参考工作表或区域。

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
- `scripts/verify_xlsx.py`、`scripts/verify_pdf.py` 负责机器检查；需要视觉验收的任务仍须实际查看相关渲染结果。
- `scripts/publish_output.py` 负责把已验证候选发布到正式路径；其他作者工具仍只能写不存在的候选路径。

## 基本边界

- 用户原文件、任务开始前已存在的文件、已交付文件和归属不明文件默认受保护，不覆盖。
- 当前任务创建、尚未交付且未被用户接管的草稿，只有在上次记录的 SHA-256 仍匹配时，才可通过 `publish_output.py` 复用原路径。
- 文件首次在最终回复中正式链接后即为已交付；后续修正默认生成递增版本。用户提前查看、打开、编辑或接管草稿时，先转为受保护状态再链接。
- OfficeCLI、OOXML 和 `libreoffice-runner` 继续只生成不存在的候选路径，不直接覆盖任何已有文件。
- 候选、重算副本、渲染结果和中间 JSON 放入任务独占临时目录；正式文件发布并验证后保留过程材料，等待用户显式触发 ChatNote 清理。
- 未获本次明确许可，不启动、连接或控制 Excel，不使用 Office COM 或 GUI 自动化。
- 不保存以 `data_only=True` 加载的工作簿；那会把公式替换成缓存值。
- 公式结果用公式表达，不用脚本计算后硬写静态结果，除非用户明确要求静态值。
- 不把标识符误写成数字；不把数字、日期、金额或百分比预格式化成普通文本。
- 既有模板优先级高于默认风格。不全表重排、不无关改色、不随意自动列宽。
- 无来源字段保持空白。外部事实记录来源，不根据常识补填。
- 草稿不在 commentary 中链接。用户要求提前查看时，链接动作本身会结束草稿的可替换状态。

## 通用工作流

1. **识别任务**：区分只读、创建、常规编辑、高保真编辑、格式转换，复用已有决定。
2. **检查输入**：读取相关区域及其依赖，按需查看公式、缓存、样式、对象、合并和打印设置。
3. **建立约束**：列出允许变化、锁定字段、关键合计、公式和输出路径。
4. **实现**：选择常规作者工具或高保真 OOXML 路线，在任务独占临时目录生成不存在的候选文件。
5. **按需重算**：按“实际影响”判断是否重算；计算未变且缓存可靠时核对保留结果，计算变化时在适用的隔离引擎重算。高保真任务只回填经核对的缓存。
6. **数据验证**：检查公式错误、范围、合计、唯一性、类型、空白、排序和文本规则。
7. **按需视觉验证**：呈现变化时查看受影响部分，打印或 PDF 任务逐页检查；工具只能整表导出时可使用该能力，但检查和交付范围不因此扩大。
8. **发布与交付**：按 [references/output-lifecycle.md](references/output-lifecycle.md) 通过受控发布器落位；只在最终回复链接正式文件，并报告实际变化、公式检查、关键数值和仍未确认的事实。

## 公式规则

- 使用清楚、可追溯的引用；跨表引用正确处理工作表名称。
- 复制公式前确认绝对与相对引用方向。
- 范围扩展后检查首尾行、合计行、查找范围、条件格式和图表范围。
- 公式“无错误”不等于公式“正确”；抽查代表性输入和结果，核对业务合计。
- 重算工具返回成功不证明旧缓存已刷新；须核对受影响结果。仍为旧值时按 [高保真重算说明](references/high-fidelity-workflow.md#5-重算与缓存回填) 在专用计算副本处理失效缓存，再验证回填。
- `<v/>` 为空不算有效公式缓存；必须有可解释的缓存值，字符串空结果除外。
- 出现 `#REF!`、`#DIV/0!`、`#VALUE!`、`#NAME?`、`#N/A` 等错误时不交付。

## 文件格式边界

- `.xlsx/.xltx`：完整支持。
- `.xlsm`：常规库加载时保留 VBA；高保真修改不触碰 `vbaProject.bin`。数字签名会因修改失效，先说明。
- `.xls`：先在隔离路径转换为 `.xlsx` 或只读提取；不覆盖原文件。
- `.xlsb`、加密文件：默认停止并说明当前工具限制。
- 外部链接工作簿：重算可能改变或丢失链接；未验证依赖文件前不整包重算。

## 高保真命令按需组合

以下是兼有计算变化与 PDF 交付的完整示例。只做定点修改且计算未变、缓存可靠时，直接验证
`draft.xlsx` 并按任务需要检查版面；无需生成重算副本或回填文件。重算和 PDF 两组步骤分别按需启用，
后续命令使用本轮实际生成的权威候选路径，不引用被跳过步骤的输出。

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
- 公式结果有可靠缓存、错误为 0；计算未变时验证保留，发生变化时核对实际重算结果；
- 格式与模板一致，图表和关键文本完整可见；
- 高保真任务的差异只落在获准范围，受保护 OOXML 条目保持；
- 需要视觉验收的部分无重叠和裁切；打印或 PDF 任务的实际页面无空白页、窄页及内容遗漏；
- 最终报告说明输出路径、变化范围、验证结果和未确认项；首次链接后将该路径视为已交付、受保护文件；
- 发送最终回复前，正式文件已自动发布到项目根目录并复核；过程材料仍保留，等待用户显式触发 ChatNote。

必要计算或检查受阻时，完成其他独立工作并说明具体限制；不把已有问题或未核实的结果当作合格交付，也不自动扩修无关工作表。


当前用户请求已覆盖本次 Excel 原生检查、且现有守护程序能证明隔离时，可传入 `--allow-office-com` 并检查实际输出，不另设用户逐页签字。进程归属、只读副本和自有空实例退出按本技能的 Acceptance layers 执行。工具身份校验失败时停用该工具，选择可信且可满足目标的现有文件级或渲染路径；如实说明未验证项。
