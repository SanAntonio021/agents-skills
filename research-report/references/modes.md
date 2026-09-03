# 工作模式

`mode` 决定报告承担什么职责，`edit_scope` 决定本轮能改多大范围。两者不能混用。

## 模式

| `mode` | 适用情况 | 正文可包含 |
|---|---|---|
| `evidence_report` | 读者要了解事实、比较和研究结论 | 范围、来源事实、综合判断 |
| `decision_report` | 读者要据此选择方案或安排验证 | 范围、来源事实、综合判断、证据支持的建议 |
| `final_audit` | 已有完整报告，准备冻结或交付 | 审计结果；只有用户要求修改时才改正文 |

## 与 `edit_scope` 的组合

- `draft`：从已闭合证据生成新稿。
- `structural`：先做内容清单和旧段落映射，再重排。
- `bounded`：只处理指定章节。
- `in_place`：保持章节，只压缩重复、修复混写和表达问题。
- `audit_only`：保持只读，输出“论点—证据—章节功能”表和问题位置。

只有主题、读者或研究问题而没有闭合证据时，不生成正式报告。先建立 [内部调研台账](research-ledger.md)，持续取样转 `baseline-research`。

## 最小参考文件

| 任务 | 读取 |
|---|---|
| `evidence_report` | [report-contract.md](report-contract.md)、[research-ledger.md](research-ledger.md) |
| `decision_report` | 上述两份 + [decision-report.md](decision-report.md) |
| 结构重写 | 再读 [restructure-existing.md](restructure-existing.md) |
| `final_audit` | 只读与当前报告模式对应的文件 |

## 读者测试

报告接近完成时，用正文回答四个问题：

1. 报告研究什么对象和范围？
2. 最可靠的发现是什么？
3. 哪些是来源事实，哪些是作者判断？
4. 若为决策报告，每项建议依据什么、在什么条件下成立？

必须靠口头补充才能回答时，先补证据或重写正文，不用更长摘要掩盖问题。
