---
name: product-research-workbook
description: 为工程技术产品调研、产品库、设备/竞品参数对比、采购渠道清单和既有产品调研工作簿规范化，建立 sample-first 的过程账本、分类正式 XLSX 和可执行验收。用户提到卫星地面站、调制解调设备、相控阵、射频/光电/测试设备等产品调研并需要参数表、产品库、采购渠道或统一编号时，即使没有直接点名工作簿也应使用本技能。不要用于普通 XLSX 单元格处理、财务表、排期表、人员表、实验结果统计、论文文献表、纯调研报告写作或一次性事实查询。
---

# 工程产品调研工作簿

把产品研究过程和面向比较、询价的正式工作簿分开，避免不同产品形态被硬塞进同一张参数表，也避免研究过程字段泄漏到交付表。

## 职责边界

- `baseline-research`：任务池、设计单、真实样本取样、证据闭环和实质口径澄清。
- 本技能：过程/正式工作簿契约、产品编号生命周期、确定性生成、业务校验和审计。
- `xlsx`：通用 XLSX/OOXML、超链接关系、包级检查和视觉验收。
- `web-access`：研究阶段验证页面可访问性；离线校验器不访问网络。
- `libreoffice-runner`：正式表需要转换 PDF 或视觉验收时的唯一 LibreOffice 入口。

读取 [references/workbook-contract.md](references/workbook-contract.md) 后执行。发布或运行时同步前，再读取 [references/acceptance-and-release.md](references/acceptance-and-release.md)。

## 工作流

1. 先读取项目规则、现有工作簿和输出版本。保护用户原文件，不覆盖过程表或正式表；过程工作簿与正式工作簿各自递增版本。
2. 读取当前源表。仅在本项目明确要求丢弃历史人工编号时，使用 `inspect_product_samples.py` 生成净化样本清单；普通项目不把旧编号一概视为敏感值。区分行标识和厂家型号，不凭旧行号虚构型号。

3. 调用 `baseline-research` 建立任务池、设计单和 sample-first 取样。不同产品形态先用真实样本决定各自字段；组件、分系统、整机分表，不预设全品类参数总表。按工程形态和专用指标把不同组件类型拆成各自子表，只有字段结构相同的同类组件才可共用一个子表。确认分类中含整机参数表时，在`字段设计`把它的`工作表顺序`设为 `1`，组件和分系统使用后续不同序号；没有整机时仍从 `1` 开始。分类来自样本与本次已明确口径，不凭工作表名称猜测。已有任务说明和字段足够时无需重复建立调研文件。
4. 用生成器创建过程账本。sample-first 期间只填写候选字段、候选产品和证据，不分配正式编号、不生成正式表：

```powershell
python <skill-root>\scripts\build_product_workbooks.py init-process <new-process.xlsx>
```

5. 样本完成后核对分类、字段、单位和证据标准。沿用本次已有明确决定；仅实际歧义才询问。`已确认` 表示依据本次要求和样本核实可采用，不要求额外一轮用户批准。
6. 确认后，为初版正式产品分配全局数字 `1..N`；更新版保留已发布的候选账本和全局数字产品编号，旧号不重排、不复用，新产品从旧最大号加一。未知品牌、厂家、联系方式或其他来源未写明事实留空，不填占位词。
7. 先校验过程账本，再建立正式表。已有正式版本时必须传入上一版：

```powershell
python <skill-root>\scripts\validate_product_workbooks.py <process.xlsx> --json-out <new-process-report.json>
python <skill-root>\scripts\build_product_workbooks.py build-formal <process.xlsx> <new-formal.xlsx> --previous-formal <previous-formal.xlsx>
python <skill-root>\scripts\validate_product_workbooks.py <process.xlsx> --formal <new-formal.xlsx> --previous-formal <previous-formal.xlsx> --json-out <new-formal-report.json>
```

初版省略 `--previous-formal`，但仍必须通过 `1..N` 连续编号检查。所有输出路径必须不存在，命令拒绝覆盖。

8. 正式表通过本技能业务校验后，交给 `xlsx` 做 `verify_xlsx.py` 包级检查、公式数为 `0` 的检查和逐表视觉验收。无公式时不重算。需要 PDF 时只通过 `libreoffice-runner` 的隔离 runner，不直接运行 `soffice`，需要 Excel 原生检查时按共享 Office 隔离规则执行。
9. 若本项目明确要求删除历史编号，使用 `scan_legacy_identifiers.py` 对新输出检查；不把该特殊净化流程套到普通产品表。汇报当前工作簿、校验和实际视觉检查结果。

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

历史行标识与厂家型号分开。已有编号的保留或转换遵循当前项目要求；只有明确要求净化历史标识的任务才使用净化脚本和泄漏扫描，不在普通项目自动删除溯源关系。
