---
name: journal-submission
description: 处理期刊选择、改投建议、投稿格式与材料合规检查及投稿出版事务。用户问“这篇投哪”“TTST 还是 TMTT”、分区口径或拒稿后投哪时，按需读取选刊资料并给出比较建议；准备投稿、检查目标期刊格式要求、作者与声明、返修、录用后文件、版权/OA/费用和校样按当前请求处理。支持 IEEE、T-MTT、Research Exchange、ScholarOne、Editorial Manager 和 Optica Prism。正文精修用 ieee-manuscript-edit，全文内容审查用 paper-review，格式修改按需转对应工具技能。
---

# 期刊选择与投稿

## 定位

负责选刊建议，以及从投稿准备到正式发表和项目归档的事务流程。先按当前请求选择分支，再读取相关材料；平台操作以当前页面和当日官方规则为准。

默认用中文解释，保留页面上的英文专业术语。一次只问一个问题。能从页面、决定信或项目记录确定的事实不再询问。

## 任务分流

- **选刊与改投建议**：读取 [选刊流程](references/journal-selection.md)，需要时再读 [期刊画像](references/journal-profiles.md)。只交付当前要求的比较、建议或选刊材料；不进入下方投稿操作流程，不初始化 `submission-state.json`、索取作者声明或启动投稿前审查。
- **投稿合规与出版操作**：准备投稿、检查格式时，默认核对目标期刊的模板、篇幅、文件格式、匿名要求和必需材料；平台操作、返修提交和录用后事项按当前请求处理。只读检查给出问题和建议，明确授权修改则完成对应修改。选刊或材料检查本身不构成实际投稿授权。
- **相邻任务**：全文技术内容、论证与结论审查或模拟审稿使用 `paper-review`；正文起草、修改和终稿文字审校使用 `ieee-manuscript-edit`。LaTeX、Word 和图件格式修改分别使用 `latex-paper`、`docx`、`paper-figure-review`，由本技能提供适用的投稿要求，共用当前稿件和已有授权。文献检索使用 `paper-search`。同时要求内容与格式检查时完成两项；仅在上下文仍有实质歧义时询问，不因“投稿”一词自动扩大成全文审稿。

## 开始前

1. 读取项目规则、稿件现状及该投稿任务已有状态；兼容读取原 `<project-root>/outputs/submission/`，已有状态沿用原位置，不搬动、不另建双份。持续投稿操作需要新建状态时，按 [references/data-contracts.md](references/data-contracts.md) 建立 `1.1` 记录；状态、截图和过程材料放 `<project-root>/过程文件/<投稿任务>/`，续做及跨技能共用。只读格式或材料检查不新建、更新投稿记录。已有 `submission-state.json` 时先读；旧 `1.0` 可兼容读取，下次已授权的正常更新时再写入 `1.1`，不为升级增加写入。
2. 确认目标期刊、文章类型、当前生命周期阶段和平台。信息不足时只问最阻塞的一项。
3. 联网或操作页面前加载 `web-access`。只使用浏览器现有会话或密码管理器；不读取、回显或保存密码、cookie、token。验证码和双重验证由用户完成。
4. 读取 [references/evidence-and-safety.md](references/evidence-and-safety.md) 和 [references/official-source-index.md](references/official-source-index.md)。再按平台、出版商和期刊读取对应参考文件。
5. 当前平台为 Optica Prism 时，读取 [references/platforms/prism-optica.md](references/platforms/prism-optica.md)；账户资料页、稿件字段和最终提交页分别以当前页面为准。
6. IEEE 请求读取 [references/publishers/ieee.md](references/publishers/ieee.md)；目标为 T-MTT 时再读 [references/journals/tmtt.md](references/journals/tmtt.md)。

投稿稿件、回复信和用户要求的其他正式文件，完成必要检查后自动无覆盖交付到项目根目录，沿用项目命名、同名递增版本，并复核文件及依赖可用；状态中的路径指向实际交付文件。LaTeX 工程、原始稿件和文献库保持原有位置。不额外生成根目录索引或归档副本；普通任务结束保留过程材料，用户触发 ChatNote 后再清理，保护投稿状态和必要证据。

## 参考文件路由

- ScholarOne：[references/platforms/scholarone.md](references/platforms/scholarone.md)
- Research Exchange：[references/platforms/research-exchange.md](references/platforms/research-exchange.md)
- Editorial Manager：[references/platforms/editorial-manager.md](references/platforms/editorial-manager.md)
- Optica Prism：[references/platforms/prism-optica.md](references/platforms/prism-optica.md)
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

持续投稿任务在状态、决定或材料发生变化时更新现有记录：

- `submission-state.json`：机器可读事实、来源、文件校验值、确认门、历史和下一步；
- 已有项目说明需要时同步当前状态；不为每页操作另建 README。

只记录已发生事实。未确认内容使用 `pending`、`conflict`、`not_present` 或 `unknown`。

## 投稿合规与内容审查

默认按当前期刊指南和页面检查格式、材料与字段。发现明显内容问题时指出并保留具体问题；用户要求全文内容审查时再调用 `paper-review`，不自动启动完整模拟审稿。

`confirmation_gates` 中的 `pre_submission_review` 是可选的内容审查记录，兼容保留已有条目：

- `not_run`：尚未执行；
- `blocked`：有阻断项或关键维度无法核验；
- `pass`：已通过，且包含 `checked_at` 和非空、可定位的 `evidence`；证据至少给出文件路径、稳定 URL、页面名或邮件标识之一。

缺失或 `not_run` 不自动阻止已准确授权的提交，也不表示内容审查通过。已有 `blocked` 问题如实保留并说明影响，按具体问题处理；不为通过校验删除问题或改写成 `pass`。不要把“文件齐了”“页面无红字”当成论文实质审查通过。

整稿审查已完成且稿件未变时复用结果；后续小改检查受影响部分，方法、数据、主要结论或整体结构发生实质变化时再评估是否需要整稿重审。仅做过局部修改和检查，不宣称整稿已审查。

只核对当前页面实际提供且要求查看的 proof/preview，不为不存在的功能补造要求。提交前核对当前稿件、作者、文件、声明、费用与投稿合规；有内容审查记录时核对其适用版本和未决问题。已有准确提交授权可复用。

## 页面协助

1. 读取本页完整说明、必填字段、当前值、错误提示和下一按钮状态。
2. 自行查明页面事实；只有尚未决定且实质影响结果的选项才询问。
3. 受保护字段复用当前稿件已有准确授权；缺少选择时才询问，填完立即回读。
4. 页面保存不等于投稿完成；只有系统确认或确认邮件才能更新为已提交。
5. 最终 Submit、Complete、Approve、Confirm 按准确授权执行；需用户本人确认或签署的声明交用户处理。缺少提交授权时，先准备核对摘要再询问。只有系统确认页或确认邮件证明提交成功。

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

## 需要真实选择的事项

下列事项不得猜填；复用当前稿件和实际选项的已有明确选择，不重复逐项询问。新选项、实质变化或平台要求本人签署时才交用户处理：

- 作者增删、顺序、通信作者、投稿联系人和贡献角色；
- 伦理、利益冲突、重复投稿、数据与代码可用性声明；
- 推荐或回避审稿人；
- 最终 Submit、返修 Submit、撤稿、转投和稿件转移；
- OA、APC、版面费、超页费、彩色印刷费和付款责任；
- 版权许可、出版协议和第三方材料许可。

确认记录保存实际问题或请求、用户选择、时间和适用页面或来源。可记录最初请求提供的授权，不伪造后续用户确认。

## 作者资料

私有作者库继续使用 `<agents-root>/local-assets/ieee-journal-submission/authors.json`，格式见 [references/data-contracts.md](references/data-contracts.md)。不迁移或自动改写真实作者数据。

稿件角色只写入项目 `submission-state.json`，不得写入全局作者库。禁止保存身份证号、手机号、学号、工号、密码、cookie、token 和个人经历。

## 可生成材料

可创建 Cover Letter、文件清单、审稿意见台账、声明选择记录、最终提交摘要和投稿归档。模板见 [references/material-templates.md](references/material-templates.md)。内容只能使用稿件和用户确认事实，不添加宣传性结论。

## 职责边界

- 选刊和拒稿后的改投建议：[选刊流程](references/journal-selection.md)。
- 用户要求的全文内容审查和模拟审稿：`paper-review`。
- 正文、摘要、图注、Cover Letter 和 Response Letter 语言精修：`ieee-manuscript-edit`。
- LaTeX 模板、编译和按需 source 打包：`latex-paper`。
- Word 排版和格式修改：`docx`。
- 图件规范、重画和 graphical abstract：`paper-figure-review`。

未经用户授权，不修改主稿、作者列表、图表或参考文献。

## 输出前自检

核对本轮要求的 proof/preview、记录兼容性、文件新鲜度与规则适用范围。只说明当前需要用户知道的结果或限制，不在每页重复提交警告。

## 收尾标准

按当前请求判断完成；实际平台操作与材料准备分别报告：

- 实际提交或页面操作以平台回执为准；只准备材料的任务完成自检即可交付；
- 需要持续追踪的投稿任务已更新项目现有状态；没有必要不另建 README；
- 文件路径、用途、大小和 SHA-256 已记录；
- 未确认事项仍明确标记；
- 未完成事项准确记录，不把用户后续提交或最终反馈当成本轮材料交付的结束条件。
