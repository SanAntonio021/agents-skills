# Upstream Skill Notes

本文件记录外部技能的取舍原则。外部内容作为参考来源，运行时仍以本地规则为准。

## labarba/sciwrite

链接：https://github.com/labarba/sciwrite
许可：CC BY 4.0

可借鉴：

- 面向 scientific/engineering manuscript 的语言精修定位。
- 保持科学内容，只改善表达、清晰度、术语一致性和数字/引用完整性。
- 五项语言检查：删空话和重复句，改顺主语和动词，拆开太绕的长句，固定术语，核对数字、单位和引用。

已吸收：

- `SKILL.md` 主流程已加入五项语言质量复查。
- `references/manuscript-refinement-checklist.md` 已融合具体检查项。

作为参考来源的原因：

- 仓库规模小，当前 GitHub 页面显示提交数少、仍有 open issues，维护强度有限。
- 它更适合作为语言质量检查框架；IEEE 风格、通信硬件论文图文对应和本地术语库流程仍由本地规则承担。
- 因此只吸收可复用检查项并保留来源说明。

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

- 已批准初稿收口已经并入 `sci-paper-edit`。
- `sci-paper-edit` 统一负责已有 SCI/IEEE 论文稿件的英文化、引用安全精修和投稿前整理。
