Eval prompt:
把刚才关于“项目私有经验先记在当前项目里，跨项目都成立的方法再整理成 skill”的讨论整理一下。我要的是判断这些经验该写到哪里，不要直接开始改文件。

Final response:
这次在做：整理经验 / 判断写到哪里

结论：修改现有 skill

理由：
- 这次讨论里真正稳定、可复用的部分，不是某个项目里的具体经验，而是一个判断原则：`项目私有经验先记在当前项目里，跨项目都成立的方法再整理成 skill`。这条原则离开当前项目也成立。
- 这条原则正好属于 `D:\BaiduSyncdisk\.agents\agents-skills-src\duihua-jingyan-zhengli\SKILL.md` 的核心职责，也就是“把经验整理出来，并判断它该写进项目、现有 skill，还是新建 skill”。
- 所以这次不该新建 skill，也不该只写在某个项目文档里。更合适的落点，是补进现有 `duihua-jingyan-zhengli` 的判断规则里。

本地有没有类似 skill：
- 有。`D:\BaiduSyncdisk\.agents\agents-skills-src\duihua-jingyan-zhengli\` 已经在做“经验提炼 + 落点判断”这件事，和这次讨论高度重合。
- 目前它已经有“写在当前项目里 / 修改现有 skill / 整理成新 skill”的框架，但还可以把“项目私有 vs 跨项目复用”这条判断线写得更直白一点。

外面有没有类似 skill：
- 查到了相近方向，但没有完全对位的公开 skill。
- [knowledge-extractor](https://skills.sh/rysweet/amplihack/knowledge-extractor) 更偏“把会话里的知识提炼出来并沉淀”；它强调把可跨场景复用的模式抽出来，但没有把“该写在项目里还是 skill 里”这层判断讲清楚。
- [knowledge-management](https://skills.sh/anthropics/knowledge-work-plugins/knowledge-management) 更偏知识库文章维护，不是 skill 治理。
- 公开资料里常见共识是：skill 负责稳定、可复用的方法；项目文档负责项目特有约束和当前上下文。这和这次讨论方向一致，但本地现有 `duihua-jingyan-zhengli` 仍然是最该承接这条规则的地方。

如果结论是修改现有 skill，建议这样改：
- 在“结论怎么选”里明确补一条判断线：只在当前项目、当前环境、当前仓库成立的经验，先写当前项目；能跨项目复用的方法，再考虑进 skill。
- 在“工作顺序”或“先这样做”里补一句：先把对话内容拆成“项目私有经验”和“跨项目方法”，再判断落点，不要把两类内容混在一起。
- 在例子里补一个更直接的样例：同一轮讨论里既有项目内约定，也有通用方法时，前者进项目文档，后者再判断是否补到现有 skill。

审查稿：
- skill 名称：`duihua-jingyan-zhengli`
- description：从当前对话里提炼经验，先区分哪些只对当前项目成立，哪些已经形成跨项目可复用的方法，再判断应写入当前项目、现有 skill、还是新建 skill。
- 什么时候该触发：用户要求整理一段对话里的经验，并判断“该写项目里还是 skill 里”；尤其适用于同时混有项目私有做法和通用方法的讨论。
- 预期输出：明确结论、简短理由、本地/外部相近 skill 检查结果，以及如果要改现有 skill 时的审查稿。
- 拟议结构：先区分经验类型 / 再检查本地与外部相似项 / 最后判断落点并给审查稿
- scripts / references / assets：暂不需要新增
- 建议测试提示：
  - “把我们刚才关于某个仓库的发布坑整理一下，判断哪些写项目文档，哪些值得补进 skill。”
  - “这轮对话里既有 Windows 路径细节，也有通用排错方法，帮我判断该分别写到哪里。”
  - “不要改文件，先告诉我这次经验应该写当前项目、改现有 skill，还是新建 skill。”

这次先停在审查稿，不开始改文件。
