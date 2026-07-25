# 学术期刊投稿生命周期

## 状态与完成证据

| 状态 | 进入条件 | 主要工作 | 完成证据 |
| --- | --- | --- | --- |
| `preparation` | 已选定期刊，尚未进入最终提交 | 核对文章类型、作者、声明、稿件和附件 | 准备清单、当日官方要求和文件记录 |
| `initial_submission` | 已进入投稿系统，尚未最终提交 | 逐页填写、上传、查看页面要求的 preview/proof | 系统确认提交或确认邮件 |
| `editorial_check` | 初投稿或重投已提交 | 等待技术检查、范围检查、编辑分配；处理补件 | 系统原始状态或编辑部通知 |
| `under_review` | 系统明确显示已送审 | 记录状态，不推测审稿人或结果 | 系统原始状态或通知 |
| `decision_received` | 收到决定信 | 保存原文，识别决定类型、截止日期和必须处理项 | 决定信归档和任务清单 |
| `revision` | 决定允许修改 | 建意见台账、修改稿、Response Letter、标注稿 | 每条意见有处理和证据 |
| `resubmission` | 返修材料进入系统 | 核对版本、逐页上传、查看 preview/proof | 系统确认返修提交 |
| `accepted` | 收到正式接收通知 | 核对录用条件、生产入口和待交材料 | 正式接收通知 |
| `final_files` | 生产端要求最终文件 | 提交可生产 source、最终图、补充材料和元数据 | 生产系统确认接收 |
| `copyright_fees` | 进入版权、开放获取或费用流程 | 分项确认协议、OA、APC、页费和付款责任 | 协议回执、账单或系统确认 |
| `proof` | 收到校样 | 在允许范围内校对并逐条留痕 | 校样提交确认 |
| `published` | 正式版本已上线 | 记录 DOI、正式 URL、上线日期并归档 | 可访问的正式出版记录 |
| `rejected` | 收到拒稿决定 | 归档决定，转 `journal-selection` 评估下一站 | 拒稿信和改投决策 |
| `withdrawn` | 作者撤稿且期刊确认 | 单独确认原因和影响，保存确认 | 编辑部撤稿确认 |
| `transferred` | 稿件进入正式转投流程 | 单独确认接收方、材料和全体作者同意 | 转投系统或接收方确认 |

## 常见转移

```text
preparation -> initial_submission -> editorial_check -> under_review
under_review -> decision_received -> revision -> resubmission -> editorial_check
decision_received -> accepted -> final_files -> copyright_fees -> proof -> published
editorial_check|under_review|decision_received -> rejected
initial_submission|editorial_check|under_review|decision_received -> withdrawn
decision_received|rejected -> transferred
```

平台可能把最终文件、版权、费用和校样拆开、并行或调整顺序。保留平台原始状态和证据，不为了适配状态图而伪造事件。

## 提交确认后的原子更新

收到系统确认或确认邮件后，同一轮完成：

- 将生命周期切到页面证据支持的阶段；`Submitted` 或 `In Screening` 通常记录为 `editorial_check`，只有明确显示 `Under Review` 才进入 `under_review`；
- 记录确认时间和证据，冻结已上传文件的路径、大小和 SHA-256；
- 将页面原始状态、文件清单和结果写入 `operation_history`；
- `next_action` 只保留等待编辑部状态或邮件这一项；
- 本地文件后续变化另记漂移，不覆盖已提交版本。

## 决定类型

保存决定信原文，并至少区分：

- `minor_revision`
- `major_revision`
- `reject_and_resubmit`
- `reject`
- `accept`
- `transfer_offer`

截止日期、延期规则、标注稿和回复格式必须来自决定信或当前页面。

## 审稿意见台账

最小字段：来源编号、原始意见、分类、处理决定、修改位置、证据、Response Letter 回复、状态。
状态使用 `pending`、`drafted`、`verified`、`closed`。
