# IEEE 期刊投稿生命周期

## 状态与产物

| 状态 | 进入条件 | 主要工作 | 完成证据 |
| --- | --- | --- | --- |
| `preparation` | 已选定 IEEE 期刊，尚未开始系统投稿 | 核对文章类型、作者、声明、稿件和附件 | 准备清单完成，官方要求有访问日期 |
| `initial_submission` | 已进入投稿系统，尚未最终提交 | 逐页填写、上传、生成 Reviewer PDF | 系统确认提交或确认邮件 |
| `editorial_check` | 初投稿已提交 | 等待技术检查、范围检查、编辑分配；处理补件 | 系统状态或编辑部通知 |
| `under_review` | 系统显示审稿中或已送审 | 记录状态，不推测审稿人或结果 | 系统状态或通知 |
| `decision_received` | 收到决定信 | 保存原文，识别决定类型、截止日期和必须处理项 | 决定信已归档并形成任务清单 |
| `revision` | 决定允许修改 | 建审稿意见台账、修改稿、response letter、标注稿 | 每条意见有响应和证据 |
| `resubmission` | 返修材料进入系统 | 核对版本、逐页上传和确认 | 系统确认返修提交 |
| `accepted` | 收到正式接收通知 | 核对录用条件、生产流程入口和待交材料 | 正式录用通知 |
| `final_files` | 生产端要求最终文件 | 提交可生产 source、最终图、补充材料和元数据 | 系统确认最终文件接收 |
| `copyright_fees` | 进入版权或费用流程 | 逐项确认出版协议、OA、APC、页费和付款责任 | 协议回执、账单或系统确认 |
| `proof` | 收到校样 | 只改生产错误和允许范围内的问题，逐条留痕 | 校样提交确认 |
| `published` | IEEE Xplore 已上线 | 记录 DOI、Xplore URL、上线日期并归档 | 可访问的 Xplore 记录 |
| `rejected` | 收到拒稿决定 | 归档决定，转 `journal-selection` 评估下一站 | 拒稿信和改投决策 |
| `withdrawn` | 作者主动撤稿且期刊确认 | 单独确认原因和影响，保存确认 | 编辑部撤稿确认 |
| `transferred` | 稿件进入期刊转投流程 | 单独确认接收方、材料和作者同意 | 转投系统或接收方确认 |

## 常见转移

```text
preparation -> initial_submission -> editorial_check -> under_review
under_review -> decision_received -> revision -> resubmission -> editorial_check
decision_received -> accepted -> final_files -> copyright_fees -> proof -> published
editorial_check|under_review|decision_received -> rejected
initial_submission|editorial_check|under_review|decision_received -> withdrawn
decision_received|rejected -> transferred
```

平台可能把版权、费用和最终文件的顺序拆开或并行。按实际通知记录，不为了适配图而伪造状态。

## 决定类型

保存系统原文，不只写“返修”。至少区分：

- `minor_revision`
- `major_revision`
- `reject_and_resubmit`
- `reject`
- `accept`
- `transfer_offer`

决定类型、返修截止日期、是否允许延期、是否要求标注稿，必须来自决定信或当前页面。

## 返修台账最小字段

- 审稿人或编辑编号；
- 原始意见，保持原文；
- 分类：必须修改、需解释、事实核验、格式要求；
- 处理决定；
- 修改位置和证据；
- Response Letter 回复；
- 状态：`pending`、`drafted`、`verified`、`closed`。
