---
name: research-report
description: 将已完成取证的行业、市场、技术、竞品或政策材料写成证据型报告、决策建议报告，或做终稿审校。Use when 用户要写、重构或审查调研报告；先区分 evidence_report、decision_report、final_audit。持续取样与补证据转 baseline-research，单篇论文总结转 paper-summary，单纯 Word 排版转 docx。
---

# 调研报告

审计脚本仅依赖 Python 3.11+ 标准库；联网取证需同时使用 `web-access`。

## 入口

从 [writing-router](../writing-router/SKILL.md) 接收：

- `document_type=research_report`
- `mode=evidence_report|decision_report|final_audit`
- `edit_scope`、`language`、`loaded_refs`

读取 [共同质量规则](../humanizer-zh/references/common-quality.md)。完整草稿、结构重写、终稿审校和 `audit_only` 再读取 [AI 气味目录](../humanizer-zh/references/ai-smell-catalog.md)。

再按 [工作模式](references/modes.md) 读取最少参考文件。私有样稿入口为 `D:\BaiduSyncdisk\.agents\writing-profile\index.md`；只有 `research_report` 样稿获批时才加载。

## 正式报告与内部台账

正式报告面向读者，只写已闭合的问题。内部台账记录检索过程、来源冲突、缺失字段和待取证事项。两类工件分开保存。

写正文前建立“读者问题—来源—论点—章节功能”关系：

| 项目 | 要求 |
|---|---|
| 读者问题 | 报告必须回答什么 |
| 来源 | 真实、可回查，含版本、地区和时间 |
| 论点 | 来源事实或由多条事实支持的判断 |
| 章节功能 | 范围、事实、比较、判断或建议 |

资料不足时不把未闭合问题写进正式报告，也不静默缩小用户要求。交付内部台账，指出缺哪条证据。

## `evidence_report`

正文只承担三类职责：

1. 定义与研究范围；
2. 有真实引用支撑的来源事实；
3. 基于已写事实形成的综合判断。

不生成行动建议。原稿中的建议转入内部映射表，除非用户将模式改为 `decision_report`。摘要最后写，只概括对象、主要发现和结论，不展示检索过程、资料缺口或内部编号。

详细内容边界见 [报告内容契约](references/report-contract.md)。

## `decision_report`

先完成与证据型报告相同的事实和判断，再根据用户需要写建议。建议必须：

- 明确针对哪个决策对象；
- 能回指前文事实和判断；
- 写清适用条件、代价、风险或触发条件；
- 区分“建议采用”“建议验证”“暂缓决定”等不同强度；
- 不把建议写成已经批准、已经实施或已经取得效果。

建议可以单列，也可以放在对应判断后，但不要与来源事实混在同一段。具体规则见 [决策报告](references/decision-report.md)。

## `final_audit`

先做“论点—证据—章节功能”表，再核对：

- 每个关键数字、参数和结论能否回到真实来源；
- 来源事实、作者判断和建议是否分开；
- 摘要是否只是拼接各节首句；
- 同一结论是否跨节换说法重复；
- 报告模式是否与建议内容一致；
- 是否残留内部来源号、待补状态或虚构元数据；
- 结论和建议是否超过证据适用范围。

跨节事实矛盾、虚构数据或引用、整段无理由重复、状态升级直接判 `fail`。

## 写法

- 标题写具体对象或结论，不用“核心洞察”“关键抓手”等空标签。
- 一个段落只承担范围、事实、判断或建议中的一个主要功能。
- 定义只解释到读者能理解后文，避免在每个章节重复。
- 表格用于参数、来源和同条件比较；推理写成段落。
- 引用紧跟所支撑的句子。转载同一原始资料不算多条独立证据。
- 计算结果引用输入和方法，不写成来源直接发布的数据。

## 审计脚本

Markdown 或纯文本可运行：

```text
python scripts/audit_report.py report.md --mode evidence-report --json
python scripts/audit_report.py report.md --mode decision-report --json
python scripts/audit_report.py research-ledger.md --mode internal-ledger --json
```

脚本只提供候选问题。关键词命中、行动词或句式整齐都需结合当前模式人工判断。

## 文件边界

实际写入 `.md` 或 `.tex` 前执行 [文稿版本保护](../writing-router/references/document-version-protection.md)。Markdown 正文按 [Markdown 到 DOCX 交接契约](../writing-router/references/markdown-docx-contract.md) 完成审校、冻结并确认后再交给 `docx`；导出阶段不重新改写内容。

## 完成条件

- 用户要求回答的问题已经闭合，或明确留在内部台账；
- 关键事实和数字可回查；
- 事实、判断和建议的身份清楚；
- `evidence_report` 没有行动建议，`decision_report` 的建议有证据和适用条件；
- 没有内部编号、无理由重复或虚假完成状态；
- `loaded_refs` 与实际读取一致。
