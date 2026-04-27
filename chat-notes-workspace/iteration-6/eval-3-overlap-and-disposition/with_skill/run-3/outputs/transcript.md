Eval prompt

我们刚才把一套“从对话里整理经验，再判断是新建、修改还是不动”的方法越聊越完整了。你先帮我查本地和公开生态有没有相近 skill，再告诉我这次到底该另做一个 skill，还是只是改已有的。

Final response

这次在做：判断这套方法该新建、修改还是不动

结论：修改现有 skill

理由：
- 本地已经有高重合主入口：`D:\BaiduSyncdisk\.agents\agents-skills-src\chat-notes\` 的目标、流程和边界，已经覆盖了“从对话里整理经验，再判断是新建、修改还是不动”的主流程。
- 这次新增的不是一套完全不同的工作流，而是一些更细的判断标准，比如运行时入口和源码入口怎么区分、什么时候优先落到项目文档、正式改完后怎样按 `skill-creator` 做收尾。
- 在这种情况下，继续修改现有 skill 比另做一个新 skill 更直接，也更不容易把边界拆散。

本地有没有类似 skill：
- 有，当前最贴近的就是 `D:\BaiduSyncdisk\.agents\agents-skills-src\chat-notes\`。
- 运行时当前加载来源是 `C:\Users\SanAn\.cc-switch\skills\chat-notes\`，但正式修改目标仍应是源码目录 `D:\BaiduSyncdisk\.agents\agents-skills-src\chat-notes\`。
- `D:\BaiduSyncdisk\.agents\agents-skills-src\skill-creator-local\` 和 `D:\BaiduSyncdisk\.agents\agents-skills-src\find-skills-local\` 只是相邻或历史入口，不是这次主结论里的推荐修改目标。

外面有没有类似 skill：
- 公开生态里有 Anthropic 官方的 `skill-creator`，负责新建、修改、评测和打磨 skill。
- 也有 `find-skills`，负责在公开生态里查找相近 skill。
- 但我没看到一个现成公开 skill，完整覆盖“从当前对话抽经验、判断该落项目还是 skill、再给审查稿和收尾分流”这条流程，所以公开生态更像参考来源，不是替代目标。

如果结论是修改现有 skill，建议这样改：
- 强化“当前加载来源”和“推荐修改目标”的区分，避免把同步产物路径写成正式修改入口。
- 把“项目私有经验优先写项目文档，跨项目稳定方法再考虑写 skill”的判断规则前置，减少一上来就新建 skill 的倾向。
- 把“正式改完后的收尾”写得更硬一点：先按 `skill-creator` 对照，再找真正承载改动的仓库检查分支、remote 和工作区，满足条件才推送。

审查稿：
- skill 名称：`chat-notes`
- description：从当前对话提炼可复用经验，判断这些经验更适合写进当前项目、用于修改现有 skill，还是整理成新 skill；只要用户想整理这轮对话、判断经验该写到哪里、或比较新建与修改，就应触发。
- 什么时候该触发：用户提到“把这段对话整理一下”“值不值得做成 skill”“该写项目里还是 skill 里”“到底该新建还是改已有”。
- 预期输出：明确结论、理由、本地和外部相近 skill 情况、推荐落点，以及必要时可直接交给 `skill-creator` 的审查稿。
- 拟议结构：对话回看 / 本地相近 skill / 公开生态比对 / 结论与落点 / 正式修改后的收尾
- scripts / references / assets：暂时不需要 `assets/`；如果后面外部检索步骤变复杂，可考虑补 `references/` 记录检索口径
- 建议测试提示：`我们刚把一套经验整理流程聊完整，先查本地和公开生态，再告诉我该新建还是改已有` / `这段对话里既有项目私有规则也有通用方法，帮我判断分别该落哪里` / `这个 skill 已经改完了，接下来该按什么顺序收尾和推送`
