# Research Exchange / Atypon 租户边界

最后核对：`2026-07-25`。官方入口见 [../official-source-index.md](../official-source-index.md)。

## 先识别租户

Research Exchange 页面可能由不同出版组织使用。先记录主机名、出版组织、目标期刊和当前页面。

- `rex-docs.atypon.com/wiley-rex/` 文档直接描述 Wiley 租户。
- T-MTT 官方作者页指向 `ieee.atyponrex.com`，证明 IEEE 使用 Atypon Research Exchange 租户。
- 同属 Atypon 平台族不表示字段、页序、Reviewer PDF、Cover Letter 或最终按钮完全一致。

Wiley 文档只能作为 Wiley 租户规则，或作为 IEEE 当前页面的比较线索；不跨租户推断字段、页序、proof 或按钮，也不能替代 IEEE 当前页面和期刊指南。

## Wiley 文档已确认事项

- Match Organizations 使用规范机构匹配；找不到时允许 `Organization is not listed` 路径。
- Reviewer PDF 对多数 Wiley 期刊可能不可用，官方明确不要求生成或查看。
- Final Review 的最终动作名可为 `Complete my submission`。

这些按钮和要求不能直接推广到 IEEE 租户。

## IEEE Atypon 租户

- 逐页读取当前页面标题、字段、帮助文字、错误和按钮。
- T-MTT 已观察到的页序和动态问题只放在 [../journals/tmtt.md](../journals/tmtt.md)。
- 当前页面缺少某字段时记录 `not_present`，不推断所有 IEEE 期刊都没有该字段。
- Reviewer PDF、Cover Letter、source 和 graphical abstract 都是条件项，以当前页面为准。

## 统一操作

1. 记录当前租户和页面证据。
2. 对照目标期刊当日指南。
3. 填写后回读值，并更新 `operation_history`。
4. 机构状态记录为 `matched`、`manually_entered` 或 `not_listed`。
5. 只查看当前页面要求的 proof/preview。
6. 清除阻断错误后停在最终动作前，由用户亲自提交。
