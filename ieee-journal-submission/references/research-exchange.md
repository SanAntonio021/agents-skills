# Research Exchange 逐页协助

本文件记录已验证的页面结构和通用操作方法。页面会更新，当前页面始终优先。

官方帮助入口见 [official-source-index.md](official-source-index.md)。

## 已验证的初投稿页序列

T-MTT 实例中出现过以下页面或功能：

1. Article Type / Qualifications：文章类型、资格与前置声明。
2. Upload Manuscript：主 PDF、主要文档 LaTeX source、graphical abstract 等按期刊配置的独立文件类型上传。
3. Title / Abstract：题名和摘要。
4. Authors / Affiliations / Author Details：作者顺序、邮箱、单位、国家/地区、ORCID 和系统联络人。
5. Match Organizations：单位匹配。
6. Additional Information：期刊动态配置的问题，包括可能出现的数据、代码、利益相关声明和审稿人字段。
7. Cover Letter：期刊启用时的文本输入或系统生成文件。
8. Final Review：返回修改、Reviewer PDF（期刊启用时）、文件列表和最终确认。

这不是所有 IEEE 期刊的固定顺序。缺页、增页或字段变化时按页面重新识别。

## 每页操作

1. 提取页面标题、说明、必填项、当前值、错误和下一按钮状态。
2. 对照目标期刊当日指南，说明本页需要决定什么。
3. 一次只问一个问题。作者角色、声明、审稿人和费用类字段单独确认。
4. 代填后重新读取页面值，并更新项目状态的 `operation_history`。
5. 页面保存不等于最终提交。平台官方帮助中的最终动作名为 `Complete my submission`；仍以当前按钮文字为准。只有系统确认或邮件才把投稿记为已提交。

## 作者与动态字段

- Author Details 的平台通用要求包括有效邮箱、单位和国家/地区。
- Research Exchange 平台联络人只能选择一位。它不等于稿件正文中只能有一位 corresponding author；两者分开记录。
- CRediT 只在期刊启用时出现；出现后按页面规则为每位作者分配角色。
- Additional Information 由期刊配置。某次没有 recommended reviewers 字段，不代表其他稿件也没有。
- 如果当前稿件没有 `Recommended Reviewers` 字段，记录为 `not_present`，不要据此推断所有稿件都不要求推荐审稿人。除非当前页面或目标期刊明确要求，也不要把自行准备的名单塞进 Cover Letter。

### Qualifications 动态字段

`Article Type / Qualifications` 中的资格问题属于期刊配置的动态字段。T-MTT 本次流程曾出现“已识别 3-5 篇相关 T-MTT 论文”一类问题；处理时保存完整题目、帮助文字和当前选项，不把它自动解释为必须引用固定数量的论文。只有在用户确认实际相关论文和页面含义后，才勾选并记录证据。

## 文件上传

- 不从文件名猜文件类型；读取下拉项或字段说明。
- 主稿 PDF、LaTeX source、graphical abstract 和补充文件按页面要求分别上传。
- “主要文档的 LaTeX”通常应转交 `latex-paper` 生成可编译 source 包；本 skill 记录上传类型和结果。
- graphical abstract 是否必需以当前页面和目标期刊指南为准。不能因为系统允许上传就判断为必需。

## Reviewer PDF

Reviewer PDF 只在期刊启用时出现；生成和查看不是平台统一强制要求，页面可能允许把它排除出投稿包。

提交前检查：

- 页数、文件大小、是否加密；
- 元数据、Cover Letter、文件列表、正文和 graphical abstract 是否重复或缺失；
- 正文起始页、图表可读性、匿名或非匿名要求；
- 是否残留测试字符串；
- 页面上的“排除 Reviewer PDF”类选项含义。

系统生成格式看起来不美观，不等于审稿人会收到错误文件。先判断内容是否完整、顺序是否正确、页面是否明确说明其用途。

## 投稿后

- `Submitted`、`In Screening` 和 `Under Review` 是平台可出现的状态；实际状态原文写入项目记录。
- 只有决定允许时才使用 `Start resubmission`。
- 编辑部退回但未作决定时使用 `Resume Submission`，不要记成返修决定。
- 录用后若状态为 `Accepted, Updates Requested`，按 `Update submission` 页面补件；锁定文件不可自行替换。

## 其他平台

ScholarOne、Editorial Manager 或未知平台：

- 不套用 Research Exchange 的页名和按钮；
- 逐页提取字段和说明；
- 使用同一证据顺序、安全门和项目记录；
- 无法访问页面时让用户提供截图或页面文字，只问当前一项。
