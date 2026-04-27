# Upstream Skill Notes

本文件记录外部技能的取舍原则。外部内容只作为参考，不作为运行时依赖，不直接复制大段规则。

## labarba/sciwrite

链接：https://github.com/labarba/sciwrite

可借鉴：

- 面向 scientific/engineering manuscript 的语言精修定位。
- 不改变科学内容，只改善表达、清晰度、术语一致性和数字/引用完整性。
- 多轮检查：冗余、语态、句子结构、术语、数字和引用。

不直接依赖的原因：

- 仓库规模小，维护活跃度有限。
- 更适合作为语言精修框架，不足以覆盖 IEEE 风格和通信硬件论文的图文对应。

## ailabs-393/research-paper-writer

仓库：https://github.com/ailabs-393/ai-labs-claude-skills
技能页：https://skills.sh/ailabs-393/ai-labs-claude-skills/research-paper-writer

可借鉴：

- IEEE/ACM 论文结构意识。
- 关注引用、版式、图表放置和论文组成部分。

不直接依赖的原因：

- 所在仓库是多技能集合，单个 skill 质量需要单独判断。
- 更偏从零写作和论文生成，不完全适合已有稿件精修。

## K-Dense-AI/scientific-agent-skills

链接：https://github.com/K-Dense-AI/scientific-agent-skills

可借鉴：

- `scientific-writing` 对论文结构、目标期刊和投稿材料的分工。
- `venue-templates` 的目标期刊/会议意识。
- `citation-management` 的引用一致性意识。
- `peer-review` 的审稿式检查框架。

需要压住的倾向：

- 不默认生成图、graphical abstract 或调用外部工具。
- 不把科研全流程能力引入一次局部润色。
- 不让生物、化学、医学等领域模板污染通信硬件论文写法。

## 本地 draft-edit

路径：[../../draft-edit/SKILL.md](../../draft-edit/SKILL.md)

必须继承：

- 不改 citation keys。
- 不把弱证据润色成强结论。
- 实验结果段先收紧主线，再改句子。
- 图注写成正文结果的压缩版。
- 中文主线和术语未定住时，不硬做英文终稿化。

本 skill 与它的关系：

- `draft-edit` 继续负责一般初稿精修。
- `sci-paper-edit` 负责已有 SCI/IEEE 论文稿件的英文化、精修和投稿前整理。
