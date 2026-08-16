---
name: product-research-workbook
description: 为工程技术产品调研、产品库、设备/竞品参数对比、采购渠道清单和既有产品调研工作簿规范化，建立 sample-first 的过程账本、分类正式 XLSX 和可执行验收。用户提到卫星地面站、调制解调设备、相控阵、射频/光电/测试设备等产品调研并需要参数表、产品库、采购渠道或统一编号时，即使没有直接点名工作簿也应使用本技能。不要用于普通 XLSX 单元格处理、财务表、排期表、人员表、实验结果统计、论文文献表、纯调研报告写作或一次性事实查询。
---

# 工程产品调研工作簿

把产品研究过程和面向比较、询价的正式工作簿分开，避免不同产品形态被硬塞进同一张参数表，也避免研究过程字段泄漏到交付表。

## 职责边界

- `baseline-research`：任务池、设计单、真实样本取样、证据闭环和用户确认关口。
- 本技能：过程/正式工作簿契约、产品编号生命周期、确定性生成、业务校验和审计。
- `xlsx`：通用 XLSX/OOXML、超链接关系、包级检查和视觉验收。
- `web-access`：研究阶段验证页面可访问性；离线校验器不访问网络。
- `libreoffice-runner`：正式表需要转换 PDF 或视觉验收时的唯一 LibreOffice 入口。

读取 [references/workbook-contract.md](references/workbook-contract.md) 后执行。发布或运行时同步前，再读取 [references/acceptance-and-release.md](references/acceptance-and-release.md)。

## 工作流

1. 先读取项目规则、现有工作簿和输出版本。保护用户原文件，不覆盖过程表或正式表；过程工作簿与正式工作簿各自递增版本。
2. 先净化历史人工前缀列，再写任何新文件：它只是源行定位控制列。对含历史编号列的源表，先生成净化样本清单，后续 sample-first 分析只读该清单；不要用会把整张表逐格打印出来的通用提取命令，也不要自行导出源表 JSON/CSV：

```powershell
python <skill-root>\scripts\inspect_product_samples.py <source.xlsx> <staging-directory>\sample-inventory.json --identifier-header <source-id-column>
```

该清单直接跳过编号列的值，只保留源工作表与行/单元格位置。不要把该列放入中间数据对象、候选摘要、渠道摘要或文件名。需要候选键时只能重新生成 `CAND-0001` 起的键；尚未创建过程账本时，直接用源表行/单元格描述，不额外发明分类前缀候选键。
3. 调用 `baseline-research` 建立任务池、设计单和 sample-first 取样。不同产品形态先用真实样本决定各自字段；组件、分系统、整机分表，不预设全品类参数总表。按工程形态和专用指标把不同组件类型拆成各自子表，只有字段结构相同的同类组件才可共用一个子表。确认分类中含整机参数表时，在`字段设计`把它的`工作表顺序`设为 `1`，组件和分系统使用后续不同序号；没有整机时仍从 `1` 开始。分类来自样本和用户确认，不凭工作表名称猜测。
4. 用生成器创建过程账本。sample-first 期间只填写候选字段、候选产品和证据，不分配正式编号、不生成正式表：

```powershell
python <skill-root>\scripts\build_product_workbooks.py init-process <new-process.xlsx>
```

5. 样本完成后暂停，向用户确认产品分类、每类已确认字段、单位口径和证据标准。未经这一步确认，不能把字段改为`已确认`、不能分配正式编号、不能生成正式表。
6. 确认后，为初版正式产品分配全局数字 `1..N`；更新版保留已发布的候选账本和全局数字产品编号，旧号不重排、不复用，新产品从旧最大号加一。未知品牌、厂家、联系方式或其他来源未写明事实留空，不填占位词。
7. 先校验过程账本，再建立正式表。已有正式版本时必须传入上一版：

```powershell
python <skill-root>\scripts\validate_product_workbooks.py <process.xlsx> --json-out <new-process-report.json>
python <skill-root>\scripts\build_product_workbooks.py build-formal <process.xlsx> <new-formal.xlsx> --previous-formal <previous-formal.xlsx>
python <skill-root>\scripts\validate_product_workbooks.py <process.xlsx> --formal <new-formal.xlsx> --previous-formal <previous-formal.xlsx> --json-out <new-formal-report.json>
```

初版省略 `--previous-formal`，但仍必须通过 `1..N` 连续编号检查。所有输出路径必须不存在，命令拒绝覆盖。

8. 正式表通过本技能业务校验后，交给 `xlsx` 做 `verify_xlsx.py` 包级检查、公式数为 `0` 的检查和逐表视觉验收。无公式时不重算。需要 PDF 时只通过 `libreoffice-runner` 的隔离 runner，不直接运行 `soffice`，不启动或控制 Microsoft Office。
9. 对历史表派生的任何新建文件先在独立版本化暂存目录完成值级复查，再发布。用下面的扫描器从历史编号列提取标记、扫描暂存目录；JSON 只报告数量和泄漏文件，绝不回显具体旧值。扫描退出码不是 `0` 时，弃用该暂存版本并重新生成，不能覆盖已存在文件；扫描完成前不要把暂存文件交给用户或评测器：

```powershell
python <skill-root>\scripts\scan_legacy_identifiers.py <source.xlsx> <staging-directory> --identifier-header <source-id-column> --json-out <new-legacy-scan-report.json>
```

`<source-id-column>` 是列标题，例如 `产品编号`，不是旧编号文本。然后汇报过程/正式版本路径、编号范围、产品/渠道数量、校验 JSON、OOXML 超链接和视觉验收结论。不要把证据摘录、判定依据、访问日期或采购流程状态带入正式表。

## 确认门与数据规则

- 过程表是用户可审计的机器账本；正式表仅用于参数比较和采购询价。
- `字段设计` 中候选字段可以继续存在，但生成器只使用`已确认`字段。
- 一个产品可有多条采购渠道；每个正式产品至少有一条已确认且正式采用的关联记录，即使公开联系方式为空。
- 参数主证据按“候选编号 + 字段名称”唯一。除内部生成的产品编号外，每个非空正式单元格与一条主证据双向对应。
- 正式参数表第一行字段名、第二行单位，数据从第 3 行开始。混合单位保留原文，单位行留空。
- 收发频段、G/T、EIRP、接口、典型/平均功耗、峰值功耗等按工程含义拆开；没有来源不要推断成熟度、用途或可采购性。
- 采购渠道表固定 14 列，使用 Table 自带筛选；不得叠加与 Table 相交的工作表级筛选。
- 产品页、规格书/手册、采购链接必须是 OOXML 可解析的外部 HTTP(S) 超链接。页面是否可访问只在研究阶段确认。

## 工具与退出码

`validate_product_workbooks.py` 输出固定 JSON。退出码 `0` 表示契约通过，`2` 表示契约错误，`1` 表示参数、I/O 或解析错误。校验器不修改输入，也不发起网络请求。

脚本已按 `openpyxl 3.1.5` 验证；不要用数据只读模式重新保存工作簿，也不要为每个任务另写临时生成器绕过这里的合同。

## 既有工作簿

审计既有产品表时保持只读，先记录 SHA-256，再报告与契约的差异。除非用户明确授权迁移，不修改、另存或把历史工作簿作为可写测试夹具。

历史表中的人工前缀序号（以及其他项目或类别前缀）只是源表行标识，不是厂家型号、候选编号或正式产品编号。把它当作导入时即丢弃的控制列，而不是可追溯业务数据。读取历史表时先排除该列，再做样本字段分析；只用“源工作表 + 行/单元格”描述这一发现，不引用具体旧值。审计结束后直接丢弃，不把旧号复制到新过程账本、正式表、样本依据、复核备注、模板示例或内部工作记录，也不生成旧号到候选号、正式编号或厂家型号的映射表、映射示例、CSV 或 JSON 键。任何新建候选表、候选摘要或渠道摘要的候选键都必须满足 `CAND-0001` 格式；没有过程账本时不应输出候选键。正式表只使用数值型全局产品编号 `1..N`。厂家型号应来自 `产品型号` 字段；如果来源只有历史行号而没有厂家型号，型号留空。

把具体旧值视为不能写入新文件的敏感值：即使解释禁令、写扫描模式、给反例、列命令、写断言或汇报自检结论，也不能复述它。只写“历史人工前缀”“源编号列”或源表行/单元格。交付前对所有新建报告、过程表、正式表、样本依据、复核备注和内部辅助文件执行扫描器；任何泄漏或“旧号 -> 新号”关系都必须在暂存版本中消除后再交付。
