这次在做：整理经验 / 判断写到哪里

结论：修改现有 skill

理由：
- 本地已经有高重合 skill，主流程已经覆盖“从当前对话提炼经验、先查本地和外部、再判断该新建还是修改已有的”这条链路，不值得再拆一个新 skill。
- 这次新增价值更像是在现有 skill 上补强边界、重合判断和落点说明，而不是换一个全新任务。

本地有没有类似 skill：
- 有，而且就是高重合主入口。当前加载来源是 `C:\Users\SanAn\.cc-switch\skills\duihua-jingyan-tiqu\SKILL.md`，它的 `name` 已经是 `chat-notes`，职责也正是“从当前对话提炼可复用经验，再判断该写进当前项目、修改现有 skill，还是整理成新 skill”。
- 如果后面要正式修改，推荐修改目标应是源码目录 `D:\BaiduSyncdisk\.agents\agents-skills-src\chat-notes\SKILL.md`，不是 `C:\Users\SanAn\.cc-switch\skills\duihua-jingyan-tiqu\` 这个同步产物目录。
- 其他本地 skill 只有邻近项，没有高重合替代：
  - `C:\Users\SanAn\.cc-switch\skills\find-skills\SKILL.md` 负责查公开生态有没有现成 skill，本身不负责“从对话提炼经验并判断该新建还是修改”。
  - `C:\Users\SanAn\.cc-switch\skills\skill-creator\SKILL.md` 负责正式创建、修改、评测 skill，属于下一阶段，不是这一步的判断器。

外面有没有类似 skill：
- 有邻近做法，但没有看到一个和这次目标完全重合的公开 skill。
- [knowledge-extractor](https://skills.sh/rysweet/amplihack/knowledge-extractor) 会从对话和问题处理中提炼知识，还会识别“哪些重复工作值得做成专门 agent / skill”。它和“从对话里抽经验”这半段很接近，但它更偏知识沉淀，不负责严格判断“改已有 skill 还是新建 skill”。
- [skill-creator](https://skills.sh/anthropics/skills/skill-creator) 明确覆盖“新建 skill / 修改已有 skill / 做评测迭代”，但它偏正式建设和评测流程，不替代这次前置的经验归纳与归属判断。
- [create-plan](https://skills.sh/openai/skills/create-plan) 这类公开 skill 只管把需求整理成计划，重合度更低。

如果结论是修改现有 skill，建议这样改：
- 在 `D:\BaiduSyncdisk\.agents\agents-skills-src\chat-notes\SKILL.md` 里更明确地区分三类路径：当前加载来源、推荐修改目标、历史残留 / 工作区快照，避免后续把安装镜像或 eval 快照误写成主入口。
- 补一条更硬的判断规则：当本地已经有高重合 skill 覆盖主流程时，默认优先判为“修改现有 skill”；只有目标、输入输出和主流程都明显不同，才判为“整理成新 skill”。
- 补一组“高重合但不等价”的公开生态例子，说明 `find-skills`、`skill-creator`、`knowledge-extractor` 各自只覆盖哪一段，避免因为外部有邻近 skill 就误判成“应该新建”或“应该不改”。
- 在汇报模板里加一句固定表述：先写“当前加载来源”，再写“推荐修改目标”，最后再写“为什么不是新建 skill”。

如果结论是新建或修改 skill，再给审查稿：
- skill 名称：`chat-notes`
- description：从当前对话提炼可复用经验，先核对本地和公开生态有没有高重合做法，再判断这些经验更适合写进当前项目、修改现有 skill、整理成新 skill，还是这次不改。
- 什么时候该触发：当用户要“整理这段对话里的经验”“判断该写进项目还是 skill”“判断该新建还是改已有 skill”“先查本地和公开生态有没有类似 skill”时触发。
- 预期输出：一份明确结论，带上本地重合项、公开生态近邻项、差异说明，以及在需要时可直接交给 `skill-creator` 的审查稿。
- 拟议结构：先回看对话 / 再查本地和公开生态 / 最后做归属判断并给审查稿
- scripts / references / assets：暂不需要新增；现阶段主要是补规则、边界和例子。
- 建议测试提示：`我们刚才把一套“从对话里整理经验，再判断是新建、修改还是不动”的方法越聊越完整了。你先帮我查本地和公开生态有没有相近 skill，再告诉我这次到底该另做一个 skill，还是只是改已有的。` / `把这段对话整理一下。我们刚才其实是在修一套 skill 治理规则，先判断这些经验该写到项目文档里还是改现有 skill。` / `我们已经把方法聊清楚了，但我不确定值不值得单独做成新 skill。先查本地和公开生态，再直接下结论。`

这次不建议另做一个新 skill。更直接的做法，是继续沿用 `chat-notes`，把上面这些判断边界和举例补进去。
