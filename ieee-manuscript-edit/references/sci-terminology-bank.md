# SCI Terminology Bank

这份文件是 `ieee-manuscript-edit` 的全局术语库模板。它用于长期保存用户审过的专业术语，减少每次 SCI 润色时的重复纠结。

## 使用规则

- 润色前先查本表，再查当前稿件和外部来源。
- 已审术语默认沿用；目标期刊或高相关正式论文给出另一种明确用法时，标为“冲突待审”交给用户。
- 新增术语、冲突术语、待判定术语必须带来源，交给用户审过后才能标为“已确认”。
- `ScienceDirect Topics` 可以作为定义入口和辅助来源；最终依据优先取正式论文或官方来源。
- 每条术语都要写清适用领域。
- 只保存可复用术语、缩写、状态名、指标名和必要备注。

## 术语表

| 状态 | 中文术语 | 推荐英文 | 可接受变体 | 慎用写法 | 适用领域 | 来源 | 用户审阅 | 最后更新 | 备注 |
|---|---|---|---|---|---|---|---|---|---|
| 已确认 | 杂散分量 | spurious component | spur; spurious component(s) | 杂散信号 | THz communication; RF/microwave spectrum analysis | https://www.analog.com/en/resources/app-notes/an-835.html; https://www.rohde-schwarz.com/us/applications/interaction-of-intermodulation-products-between-dut-and-spectrum-analyzer-application-note_56280-29700.html; D:\BaiduSyncdisk\Paper\202604_IEEE_isolator | 是 | 2026-05-01 | 用户确认中文正文优先使用“杂散分量”；“三阶互调杂散分量”“1.999 GHz 杂散分量”等作为组合表达处理。 |

## 字段说明

- `状态`：`已确认`、`待审`、`冲突待审`、`待判定`、`弃用`。
- `中文术语`：用户稿件中常见的中文表达。
- `推荐英文`：润色时默认使用的英文表达。
- `可接受变体`：目标期刊或特定语境下也可接受的写法。
- `慎用写法`：容易误导、太泛、和本领域匹配度低或用户已经否定过的写法。
- `适用领域`：例如 `THz communication`、`photonics`、`microwave device`、`signal processing`。
- `来源`：优先写 DOI、正式论文链接、目标期刊文章链接或官方页面；可补充 ScienceDirect Topics 链接。
- `用户审阅`：用户明确审过后写 `是`；否则写 `否`。
- `最后更新`：使用 `YYYY-MM-DD`。
- `备注`：只写短说明，例如“本文定义用法”“只用于状态名”“优先于 device”。
