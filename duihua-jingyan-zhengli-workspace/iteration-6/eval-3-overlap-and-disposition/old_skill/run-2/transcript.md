# Eval prompt

我们刚才把一套“从对话里整理经验，再判断是新建、修改还是不动”的方法越聊越完整了。你先帮我查本地和公开生态有没有相近 skill，再告诉我这次到底该另做一个 skill，还是只是改已有的。

# Final response

这次在做：整理经验 / 判断写到哪里

结论：修改现有 skill

本地有没有类似 skill：
- 有，而且就是高重合主入口。当前会话实际可用的本地 skill 里已经有 `duihua-jingyan-zhengli`；运行时入口是 `C:\Users\SanAn\.codex\skills\duihua-jingyan-zhengli`，它再指向 `C:\Users\SanAn\.cc-switch\skills\duihua-jingyan-zhengli`。
- 这个 skill 的目标、主流程和边界，已经覆盖“从对话里提炼经验，再判断该写进项目、修改已有 skill，还是整理成新 skill”这条主链路。
- 如果后面要正式修改，推荐改的不是运行时镜像，也不是工作区快照，而是源码目录 `D:\BaiduSyncdisk\.agents\agents-skills-src\duihua-jingyan-zhengli\SKILL.md`。
- 本地确实还能看到 `D:\BaiduSyncdisk\.agents\agents-skills-src\find-skills-local\`、`D:\BaiduSyncdisk\.agents\agents-skills-src\skill-creator-local\` 这类历史或相邻入口，但它们不是这次的当前主入口，也不该被当成推荐修改目标。

外面有没有类似 skill：
- 有相近做法，但没查到一个和这次目标完全重合的公开 skill。
- [knowledge-extractor](https://skills.sh/rysweet/amplihack/knowledge-extractor) 更像“从问题和对话里提炼知识，并识别哪些重复工作值得做成 agent / skill”，和“先抽经验”这半段接近，但不负责严肃判断“改已有 skill 还是新建 skill”。
- [skill-creator](https://skills.sh/anthropics/skills/skill-creator) 覆盖“新建 / 修改 / 评测 skill”的正式建设流程，但它偏执行和评测，不替代这次前置的经验归纳与归属判断。
- 公开生态里也有偏计划整理的 skill，比如 [create-plan](https://skills.sh/openai/skills/create-plan)，但重合度更低，只能算邻近，不是同类。

理由：
- 本地已经有高重合 skill 覆盖主流程，所以这里优先应在“修改现有 skill”和“整理成新 skill”之间判断，不该退回“这次不改”。
- 这次新增的价值，不是出现了一个全新任务，而是把现有 skill 里“本地重合判断”“运行时入口和源码入口区分”“高重合时优先改已有 skill”的规则讲得更硬、更清楚。
- 公开生态虽然有邻近 skill，但没有谁完整覆盖“从对话整理经验，再判断是新建、修改还是不动”这整套判断链路；这说明现有本地 skill 方向是对的，缺的是补边界，不是另起炉灶。

如果结论是修改现有 skill，建议这样改：
- 在 `D:\BaiduSyncdisk\.agents\agents-skills-src\duihua-jingyan-zhengli\SKILL.md` 里更明确地区分三类路径：运行时入口、推荐修改目标、历史残留 / 工作区快照，避免后面把安装镜像或 eval 快照误写成主入口。
- 补一条更硬的判断规则：如果本地已经有高重合 skill 覆盖主流程，默认优先判为“修改现有 skill”；只有目标、输入输出和主流程都明显不同，才判为“整理成新 skill”。
- 补一组“公开生态里有邻近 skill，但不足以推翻本地高重合结论”的例子，明确 `find-skills`、`skill-creator`、`knowledge-extractor` 分别只覆盖哪一段。
- 在汇报模板里固定先写“本地类似 skill”，再写“公开生态相近 skill”，最后再下“新建 / 修改 / 项目内沉淀 / 这次不改”的结论，避免跳步。

如果结论是新建或修改 skill，再给审查稿：
- skill 名称：`duihua-jingyan-zhengli`
- description：从当前对话里提炼可复用经验，先核对本地和公开生态有没有高重合做法，再判断这些经验更适合写进当前项目、修改现有 skill、整理成新 skill，还是这次不改。
- 什么时候该触发：当用户要“整理这段对话里的经验”“判断该写进项目还是 skill”“判断该新建还是修改已有 skill”“先查本地和公开生态有没有类似 skill”时触发。
- 预期输出：一份明确结论，先交代本地高重合项和公开生态邻近项，再说明差异、理由，以及在需要时可直接交给 `skill-creator` 的审查稿。
- 拟议结构：先回看对话 / 再查本地和公开生态 / 最后做归属判断并给审查稿
- scripts / references / assets：暂时不需要新增；当前主要缺的是规则、边界和例子
- 建议测试提示：`我们刚才把一套“从对话里整理经验，再判断是新建、修改还是不动”的方法越聊越完整了。你先帮我查本地和公开生态有没有相近 skill，再告诉我这次到底该另做一个 skill，还是只是改已有的。` / `把这段对话整理一下。我们刚才其实是在修一套 skill 治理规则，先判断这些经验该写进项目文档里，还是改现有 skill。` / `我们已经把方法聊清楚了，但我不确定值不值得单独做成新 skill。先查本地和公开生态，再直接下结论。`

这次不建议另做一个新 skill。更直接的做法，是继续沿用 `duihua-jingyan-zhengli`，把上面这些判断边界和例子补进去。
