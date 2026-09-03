# humanizer-zh

这是本地中文写作流程的共同质量层，同时保留普通中文材料的直接编辑入口。

它不再对所有正式文稿统一“去 AI 味”。项目书、技术文档、调研报告、会议纪要和论文先由 `writing-router` 分类，再由文体技能处理；`humanizer-zh` 直接调用时只负责普通中文材料。

## 两份共同规则

- `references/common-quality.md`：保护事实和关系，判断材料是否充足，检查段落功能、信息推进、全文重复和停笔条件。
- `references/ai-smell-catalog.md`：列出十类候选气味。每类都写明成立条件、文体例外、阻断条件和处理方式。

关键词命中不等于问题成立。原文已经清楚时可以不改，修改数量不作为质量指标。

## 正式文稿路由

| 文稿 | 技能 |
|---|---|
| 项目书、专家答复 | `project-writing` |
| 技术方案、系统说明、测试结果分析 | `technical-writing` |
| 调研报告 | `research-report` |
| 会议纪要 | `meeting-notes` |
| 中文或英文论文 | `ieee-manuscript-edit` |

个人样稿存放在私有配置仓库的 `D:\BaiduSyncdisk\.agents\writing-profile\`。公开技能仓库不保存个人段落，也不保存由个人样稿生成的评测输出。

## 设计来源

当前版本综合参考了：

- [shuorenhua](https://github.com/MrGeDiao/shuorenhua)：事实、关系、受保护片段和修改范围。
- [human-writing](https://github.com/KKKKhazix/human-writing)：材料不足就少写、每段推进新信息、写够即停。
- [Linux.do 中文提示词讨论](https://linux.do/t/topic/2709199)：日常回复先答问题、少铺垫。
- [Waza /write](https://github.com/tw93/Waza/blob/main/skills/write/SKILL.md)：把 AI 痕迹当作气味，少改并保留作者声音。

原 `Humanizer-zh` 的长模式表仍保留在 Git 历史中。v2 将其中可复用内容收缩为十类需要人工复核的气味，不沿用英文语境的机械规则、个性注入或逐词替换。
