# Upstream Skill Notes

本文件记录外部技能的取舍原则。外部内容作为参考来源，运行时仍以本地规则为准。

## labarba/sciwrite

链接：https://github.com/labarba/sciwrite
许可：CC BY 4.0

**当前状态（2026-05-20 更新）：** sentence-polish 已 fork 到本地 `skills/sentence-polish/`，作为独立的英文句子质量审查 skill。

**分工：**
- `ieee-manuscript-edit` 管内容层面的精修：术语校准、引用检查、IEEE 结构、中文改英文、图注、终稿整理。内置的 5 项语言质量复查（已吸收到 `manuscript-refinement-checklist.md`）是精修流程中的一个步骤，服务于完整流程。
- `sentence-polish` 是独立的纯英文句子质量审查工具：Sainani 五轮检查法（删废话→改被动→理句子结构→统一用词→核对数字引用）。用户单独想做句子级检查时用。

**已吸收到 ieee-manuscript-edit 的内容保留不动：**
- `SKILL.md` 主流程中的五项语言质量复查步骤。
- `references/manuscript-refinement-checklist.md` 中融合的具体检查项。

**原始背景：**
- 仓库规模小，维护不活跃，核心内容是基于 Sainani 课程的静态方法论提炼。
- IEEE 风格、通信硬件论文图文对应和本地术语库流程仍由 ieee-manuscript-edit 本地规则承担。

## ailabs-393/research-paper-writer

仓库：https://github.com/ailabs-393/ai-labs-claude-skills
技能页：https://skills.sh/ailabs-393/ai-labs-claude-skills/research-paper-writer

可借鉴：

- IEEE/ACM 论文结构意识。
- 关注引用、版式、图表放置和论文组成部分。

作为参考来源的原因：

- 所在仓库是多技能集合，单个 skill 质量需要单独判断。
- 更偏从零写作和论文生成，和已有稿件精修的匹配度较低。

## K-Dense-AI/scientific-agent-skills

链接：https://github.com/K-Dense-AI/scientific-agent-skills

可借鉴：

- `scientific-writing` 对论文结构、目标期刊和投稿材料的分工。
- `venue-templates` 的目标期刊/会议意识。
- `citation-management` 的引用一致性意识。
- `peer-review` 的审稿式检查框架。

吸收时保留本地边界：

- 图、graphical abstract 和外部工具只在用户明确需要时进入流程。
- 局部润色只吸收当前步骤需要的检查项。
- 通信硬件论文优先使用本领域写法。

## 本地已批准初稿收口

必须继承：

- 保持 citation keys。
- 弱证据对应克制结论。
- 实验结果段先收紧主线，再改句子。
- 图注写成正文结果的压缩版。
- 中文主线和术语定住后，再做英文终稿化。

本 skill 与它的关系：

- 已批准初稿收口已经并入 `ieee-manuscript-edit`。
- `ieee-manuscript-edit` 统一负责已有 SCI/IEEE 论文稿件的英文化、引用安全精修和投稿前整理。
