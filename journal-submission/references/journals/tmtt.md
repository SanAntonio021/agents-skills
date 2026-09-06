# T-MTT 期刊扩展

目标期刊：IEEE Transactions on Microwave Theory and Techniques。

官方入口：<https://mtt.org/publications/t-mtt/information-for-authors/>。最后核对：`2026-07-25`。

本文件只保存 T-MTT 阶段差异和已观察冲突。每次初投稿、返修和录用后提交前重新访问官方页面。T-MTT 请求统一由 `journal-submission` 加载本扩展。

## 初投稿冲突处理

既有项目曾出现：公开指南说明初投稿使用单个 PDF，而当次 IEEE Atypon 页面又显示 `main document LaTeX source` 文件类型。处理规则：

1. 分别记录公开指南和当前页面；
2. 当前页面只控制本次操作；
3. source 包只在本次页面明确要求时交给 `latex-paper`；
4. 不把该要求推广到下一篇稿件。

graphical abstract、Cover Letter、审稿人和资格问题均按当前页面是否出现、是否必填处理。

## 资格问题

某次页面出现过“识别相关 T-MTT 论文”一类 Qualifications 动态问题。保存完整题目、帮助文字和选项；不自行解释为固定引用数量，也不把它提升为期刊长期硬规则。

## 返修

- 保存决定信、截止日期和当前页面要求；
- 分开准备无高亮修订稿、高亮修订稿和逐条回复，具体文件以决定信为准；
- Response Letter 正文精修转 `ieee-manuscript-edit`；
- 返修 Submit 使用本次准确授权，需本人签署的声明仍由用户处理。

## 录用后

最终生产文件与初投稿文件分开。LaTeX/Word 源、完整 PDF、独立图件、补充材料、版权和费用按当前生产页面重新核对，不直接复用初投稿 source 包。


## 历史观察补充

以下来自 2026-07-14 的旧画像，仅供重新核验时定位问题，不作为当前硬规则：当时指南描述 single-anonymous peer review，初投稿单 PDF、低于 1 MB 且不接受 ZIP；真实页面曾同时要求 LaTeX source。Graphical Abstract 曾标为 strongly encouraged，ORCID、Data/Code 依当时字段解释。费用快照为 OA APC USD 2800、超过 11 页的 MTT-S/其他作者 USD 185/230 每页、前 11 页自愿页费 USD 110。进入相关阶段时重新核对当日指南、决定信和页面，不直接套用快照或替用户选择付款责任。
