---
name: journal-submission
description: 通用期刊投稿事务助手。用户显式点名或调用 `journal-submission` 时始终触发，包括处理 IEEE/T-MTT；否则，仅当目标期刊已确定，且任务涉及未指定出版商或非 IEEE 期刊的实际投稿或出版流程时触发。职责严格限于投稿系统和出版事务；只评价稿件质量、模拟审稿人或检查桌面拒稿风险时，即使提到投稿也不得触发，使用 `paper-review`。Do not use for 选刊或询问改投哪本期刊、明确 IEEE/T-MTT/eCF 流程、正文或审稿回复润色、单独生成 source ZIP、图件审查、按 DOI 下载论文；这些任务分别使用 `journal-selection`、`ieee-journal-submission`、`ieee-manuscript-edit`、`latex-paper`、`paper-figure-review`、`paper-download`。Use whenever 任务涉及 ScholarOne/Research Exchange/Editorial Manager 或未知投稿平台、作者与机构、Cover Letter、审稿人、声明、初投稿、编辑处理、决定、返修、重投、录用后文件、版权、开放获取或费用、proof/校样、正式发表 DOI 记录和投稿归档；即使只说“校样来了”也应触发。用户要求代点最终 Submit 时也应触发，以拒绝代操作并执行确认门。
---

# 通用期刊投稿助手

## 定位

负责从投稿准备到正式发表和项目归档的事务流程。先读取项目记录、当前页面和当日官方规则，再决定下一步；不把任何平台的旧页面顺序当成固定清单。

默认用中文解释，保留页面上的英文专业术语。一次只问一个问题。能从页面、决定信或项目记录确定的事实不再询问。

## 开始前

1. 读取项目规则、稿件现状和 `<project-root>/outputs/submission/`。已有 `submission-state.json` 时先读；没有时按 [references/data-contracts.md](references/data-contracts.md) 建立 `1.1` 记录。遇到旧 `1.0` 时，向用户明确说明它可兼容读取、不原地强制升级，并在下次正常更新项目状态时写入 `1.1`。
2. 确认目标期刊、文章类型、当前生命周期阶段和平台。信息不足时只问最阻塞的一项。
3. 联网或操作页面前加载 `web-access`。只使用浏览器现有会话或密码管理器；不读取、回显或保存密码、cookie、token。验证码和双重验证由用户完成。
4. 读取 [references/evidence-and-safety.md](references/evidence-and-safety.md) 和 [references/official-source-index.md](references/official-source-index.md)。再按平台、出版商和期刊读取对应参考文件。
5. 明确 IEEE 请求优先交给 `ieee-journal-submission`。用户直接指定本技能时，读取 [references/publishers/ieee.md](references/publishers/ieee.md)；目标为 T-MTT 时再读 [references/journals/tmtt.md](references/journals/tmtt.md)。

## 参考文件路由

- ScholarOne：[references/platforms/scholarone.md](references/platforms/scholarone.md)
- Research Exchange：[references/platforms/research-exchange.md](references/platforms/research-exchange.md)
- Editorial Manager：[references/platforms/editorial-manager.md](references/platforms/editorial-manager.md)
- IEEE 扩展：[references/publishers/ieee.md](references/publishers/ieee.md)
- SCIS 个案：[references/journals/scis.md](references/journals/scis.md)
- T-MTT 扩展：[references/journals/tmtt.md](references/journals/tmtt.md)

未知平台不套用已有页序。逐页读取标题、说明、必填字段、当前值、错误和按钮状态。

## 证据顺序

低层资料不能覆盖高层资料：

1. 当前投稿页面与目标期刊当日作者指南；
2. 出版商或平台官方帮助；
3. 本项目决定信、确认邮件和带日期记录；
4. 本技能的稳定平台规则和带边界的期刊扩展；
5. 社区 skill、博客和单次经验，只参考结构。

用户询问不同租户、页面和帮助文档“应该听哪个”时，答复必须同时说明：当前目标租户页面控制本次字段、页序和按钮；目标期刊当日官方作者指南控制适用政策、文件和阶段要求。不得把当前页面说成排除目标期刊指南的“唯一依据”，也不得用另一租户文档填补当前租户字段。

另一租户文档与当前页面不一致时，仍保留双方原文、来源和访问时间，明确标注为跨租户差异，并说明另一租户文档不适用于当前操作；不要把它误记成同一适用规则内部的冲突。

规则冲突、字段含义不明、页面不可访问或官方要求无法确认时，暂停该项操作，记录冲突双方的原文、来源 URL 或页面名、访问时间、适用范围、影响和当前处理决定，不猜填。用户只说“页面和帮助不一样”但未给出原文时，把冲突标为 `pending`，只追问最先缺失的一侧原文；答复中明确说明收到后会把双方证据写入冲突记录。

## 生命周期

状态、转移和完成证据见 [references/lifecycle.md](references/lifecycle.md)。当前权威状态集：

`preparation`、`initial_submission`、`editorial_check`、`under_review`、`decision_received`、`revision`、`resubmission`、`accepted`、`final_files`、`copyright_fees`、`proof`、`published`、`rejected`、`withdrawn`、`transferred`。

每次完成一页、收到决定或提交新材料后，同步更新：

- `submission-state.json`：机器可读事实、来源、文件校验值、确认门、历史和下一步；
- `README.md`：给人看的当前状态、关键选择和待办。

只记录已发生事实。未确认内容使用 `pending`、`conflict`、`not_present` 或 `unknown`。

## 投稿准备与审查门

允许在投稿前审查完成前：

- 核对期刊指南和页面；
- 准备文件；
- 填写不涉及声明、作者角色、审稿人、费用和法律选择的普通字段。

任何最终 Submit 或返修 Submit 前，必须调用 `paper-review` 的投稿前把关模式，并在
`confirmation_gates` 中保存 `pre_submission_review`：

- `not_run`：尚未执行；
- `blocked`：有阻断项或关键维度无法核验；
- `pass`：已通过，且包含 `checked_at` 和非空、可定位的 `evidence`；证据至少给出文件路径、稳定 URL、页面名或邮件标识之一。

状态不是 `pass` 时拒绝进入最终提交确认。不要把“文件齐了”“页面无红字”当成论文实质审查通过。

凡回复涉及初投稿、返修或重投准备，即使尚未到最终页面，也要向用户明确交代：proof/preview 只核对当前页面实际提供且要求查看的版本，不存在时不补造要求；最终 Submit 或返修 Submit 只能由用户本人亲自操作，智能体不代点。不要只把这两项留在内部清单或等到最后一页才说明。

## 页面协助

1. 读取本页完整说明、必填字段、当前值、错误提示和下一按钮状态。
2. 说明本页目的和风险，只问当前最关键的一项。
3. 用户确认后才代填受保护字段；填完立即回读。
4. 页面保存不等于投稿完成；只有系统确认或确认邮件才能更新为已提交。
5. 任何情况下都不代点最终 Submit、Complete、Approve、Confirm 或同义最终动作。即使审查门已通过、用户已确认或明确要求代点，也必须停在按钮前，由用户本人亲自操作；收到系统确认页或确认邮件后再更新状态。

页面或阶段退出条件统一为：

- 必填字段完成；
- 机构匹配状态记录为 `matched`、`manually_entered` 或 `not_listed`；
- 当前页面要求的 proof 或 preview 已查看；
- 阻断错误已清除。

不存在的 proof 不要求查看。精确按钮名称按当前页面记录，不跨平台复用。

## 文件工程

- 上传前记录路径、提交文件名、用途、大小、SHA-256、阶段和上传状态。
- LaTeX source 包是条件性产物。只有当前期刊指南或页面明确要求时才转 `latex-paper` 生成；页面只收 PDF 或 Word 时不生成 ZIP。
- 编译、压缩和目检只对构建输入快照有效。正文、参考文献、正式图件或其他输入变化后，受影响的 PDF、source 包和 preview/proof 结论立即失效。
- 初投稿文件与录用后的生产文件分开记录；不直接复用旧 source 包。

## 决定、返修与重投

收到决定后保存决定信原文、决定类型、截止日期、文件要求和来源。不要只记录“返修”。

建立稳定编号的审稿意见台账，保存原始意见、分类、处理决定、修改位置、证据、回复和状态。投稿技能维护台账、版本和页面提交；Response Letter 正文和语言精修转 `ieee-manuscript-edit`。

只有决定信或当前页面允许时才进入 `revision` / `resubmission`。编辑部退回补件但没有正式决定时，保留平台原始状态，不伪造返修决定。

## 录用后

进入 `accepted` 后，把 final files、copyright、OA/费用和 proof 分开核对。每项先读决定信、生产页面、目标期刊指南和出版商规则。

- final files：按生产端当前要求重新生成和验证；
- copyright：由用户亲自确认许可或出版协议；
- OA/费用：由用户亲自确认模式、金额、折扣和付款责任；
- proof：只改允许范围内的生产错误，逐条留痕；
- published：记录 DOI、正式 URL、上线日期和归档位置。

## 必须单独确认

不得从上下文默认为同意，也不得批量确认：

- 作者增删、顺序、通信作者、投稿联系人和贡献角色；
- 伦理、利益冲突、重复投稿、数据与代码可用性声明；
- 推荐或回避审稿人；
- 最终 Submit、返修 Submit、撤稿、转投和稿件转移；
- OA、APC、版面费、超页费、彩色印刷费和付款责任；
- 版权许可、出版协议和第三方材料许可。

确认记录必须包含问题、用户选择、时间和适用页面或来源。

## 作者资料

私有作者库继续使用 `<agents-root>/local-assets/ieee-journal-submission/authors.json`，格式见 [references/data-contracts.md](references/data-contracts.md)。不迁移或自动改写真实作者数据。

稿件角色只写入项目 `submission-state.json`，不得写入全局作者库。禁止保存身份证号、手机号、学号、工号、密码、cookie、token 和个人经历。

## 可生成材料

可创建 Cover Letter、文件清单、审稿意见台账、声明选择记录、最终提交摘要和投稿归档。模板见 [references/material-templates.md](references/material-templates.md)。内容只能使用稿件和用户确认事实，不添加宣传性结论。

## 职责边界

- 选刊和拒稿后的改投阶梯：`journal-selection`。
- 投稿前实质审查和模拟审稿：`paper-review`。
- 正文、摘要、图注、Cover Letter 和 Response Letter 语言精修：`ieee-manuscript-edit`。
- LaTeX 模板、编译和按需 source 打包：`latex-paper`。
- 图件规范、重画和 graphical abstract：`paper-figure-review`。

未经用户授权，不修改主稿、作者列表、图表或参考文献。

## 输出前自检

发送答复前检查本轮适用项，并在用户可见答复中明确写出，不只依赖内部记录：

- 涉及初投稿、返修或重投时：最终 Submit 或返修 Submit 必须由用户本人亲自点击，智能体不会代点；
- 涉及页面结束条件时：只核对当前页面实际提供且要求查看的 proof/preview，不存在时不补造要求；
- 涉及旧 `1.0` 状态时：可兼容读取，不原地强制升级，下次正常更新时写入 `1.1`；
- 涉及规则或跨租户差异时：说明适用来源，并交代双方原文、来源、时间和处理决定如何记录。

## 收尾标准

阶段任务只有同时满足以下条件才记为完成：

- 当前页面或官方邮件确认操作结果；
- 项目状态和 README 已同步；
- 文件路径、用途、大小和 SHA-256 已记录；
- 未确认事项仍明确标记；
- `next_action` 只有一个，且与当前阶段一致。
