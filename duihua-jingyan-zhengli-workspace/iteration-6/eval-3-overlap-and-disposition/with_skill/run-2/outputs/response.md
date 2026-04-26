这次在做：整理经验 / 判断写到哪里

本地有没有类似 skill：
- `D:\BaiduSyncdisk\.agents\agents-skills-src\duihua-jingyan-zhengli\SKILL.md`：高重合，已经覆盖这次主流程，包括“从当前对话提炼经验 -> 先查本地和公开生态有没有相近 skill -> 在新建 / 修改 / 写在当前项目里 / 这次不改之间给结论 -> 用户批准前只交审查稿”。
- 当前机器上的运行时入口是 `C:\Users\SanAn\.codex\skills\duihua-jingyan-zhengli`，它指向 `C:\Users\SanAn\.cc-switch\skills\duihua-jingyan-zhengli`。这说明本地安装态也已经有同类能力，但正式推荐修改目标仍应是源码目录 `D:\BaiduSyncdisk\.agents\agents-skills-src\duihua-jingyan-zhengli\`，不是安装态目录。
- `D:\BaiduSyncdisk\.agents\agents-skills-src\find-skills-local\SKILL.md`：只负责查本地和公开生态有没有 skill、该装还是该改，不负责“从当前对话提炼经验并判断最后写到哪里”。
- `D:\BaiduSyncdisk\.agents\agents-skills-src\skill-creator-local\SKILL.md`：只负责已经决定要新建或修改 skill 之后的正式整理，不负责这一步前置分流判断。

外面有没有类似 skill：
- 公开生态里能查到相近的是 `find-skills`，它解决的是“去哪里找 skill、怎么比较 skill”，不是这次这种“先从对话里抽经验，再判断该新建、改已有、写项目里还是不动”的完整分流。
- 公开生态里还能查到 `skill-creator` 这类能力，它解决的是“已经决定要建或改 skill 后怎么正式落地、测试和迭代”，也不是这一步前置判断。
- 我没有查到一个比本地这份 `duihua-jingyan-zhengli` 更贴合的公开 skill，能把“对话经验整理 + 本地优先重合检查 + 四选一去向判断”完整打包成主流程。

结论：修改现有 skill

理由：
- 本地已经有高重合 skill 覆盖主流程，这种情况下优先应该在 `修改现有 skill` 和 `整理成新 skill` 之间判断，不该退回 `这次不改`。
- 这次新增的价值主要是把判定规则补得更稳，比如“运行时入口、源码入口、历史残留目录要分开说”“用户明确在问新建还是修改时，如果本地已有高重合 skill，默认优先判修改现有 skill”。这些都属于现有 skill 的规则补强，不是一个全新的任务类型。
- 如果再另做一个 skill，会和 `duihua-jingyan-zhengli` 在目标、输入、输出和触发场景上大面积重叠，后面更容易出现职责分裂和触发冲突。

如果结论是修改现有 skill，建议这样改：
- 继续把唯一推荐修改目标写死为源码目录 `D:\BaiduSyncdisk\.agents\agents-skills-src\duihua-jingyan-zhengli\`，不要把 `skill-creator-local`、`find-skills-local`，也不要把 `C:\Users\SanAn\.cc-switch\skills\duihua-jingyan-zhengli` 这种安装态入口写成主修改目标。
- 在“先查本地有没有类似 skill”那一节前置一条硬规则：用户如果直接问“该新建还是改已有”，且本地已有高重合主流程 skill，默认先判 `修改现有 skill`，只有目标、输入输出和边界明显变化时才转成 `整理成新 skill`。
- 把“运行时入口 / 源码入口 / 历史残留目录”的区分往前提，避免汇报时把安装态目录、源码目录和工作区快照混写。
- 补一个例子：公开生态有近邻能力，但本地已经有高重合 skill，所以最终仍落到 `修改现有 skill`。

如果结论是新建或修改 skill，再给审查稿：
- skill 名称：`duihua-jingyan-zhengli`
- description：从当前对话里提炼可复用经验，先查本地和公开生态有没有相近 skill，再判断这些经验更适合修改现有 skill、整理成新 skill、写在当前项目里，还是这次不改；用户批准前只交付审查稿，不直接改 skill。
- 什么时候该触发：用户提到“把这段对话整理一下”“看看值不值得做成 skill”“判断该写到项目里还是 skill 里”“先查本地和公开生态，再判断该新建还是改已有”这类需求时触发。
- 预期输出：明确结论、本地重合判断、公开生态对照、推荐修改目标，以及可直接交给 `skill-creator` 的审查稿。
- 拟议结构：先这样做 / 工作顺序 / 结论怎么选 / 汇报格式 / 例子 / 边界
- `scripts / references / assets`：这次看起来都不需要，正文规则已经足够承载。
- 建议测试提示：
  - `我们刚才把一套“从对话里整理经验，再判断是新建、修改还是不动”的方法越聊越完整了。你先帮我查本地和公开生态有没有相近 skill，再告诉我这次到底该另做一个 skill，还是只是改已有的。`
  - `把这段对话整理一下。我们刚才讨论的是一套只在这个仓库成立的规则，帮我判断该写进项目文档，还是该做成 skill。`
  - `我们已经形成了一套稳定流程，但我拿不准要不要新建 skill。先看本地有没有高重合的，再看公开生态，最后给我审查稿，不要直接改文件。`
