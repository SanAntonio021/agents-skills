这次在做：整理经验 / 判断写到哪里

结论：修改现有 skill

理由：
- 本地已经有高重合主入口：`D:\BaiduSyncdisk\.agents\agents-skills-src\duihua-jingyan-tiqu\`。它的主流程已经覆盖“从当前对话提炼经验 -> 先查本地有没有类似 skill -> 再查外面有没有类似做法 -> 在新建 / 修改 / 写项目 / 不改之间做判断”。
- 这次新补出来的价值，主要不是一套全新流程，而是把现有流程又收紧了一层：更明确地区分“当前主入口”和“历史过渡壳”，更明确要求先说本地情况、再说公开生态情况、最后直接给处置结论。
- 公开生态里能找到相近方向，但没有一个和你现在这套方法完全对齐。它们更像“对话经验沉淀成 skill”或“skill 创建器”，而不是“先查重、再判断去向、并且把本地主入口与历史壳分开”的本地化决策 skill。

本地有没有类似 skill：
- 有，最高重合的是 `D:\BaiduSyncdisk\.agents\agents-skills-src\duihua-jingyan-tiqu\`。它已经把这次任务的主目标、主步骤、结论选项和汇报格式都写进去了，所以这次不该另做一个新 skill。
- 相邻但不该作为主结论目标的有两个：
  - `C:\Users\SanAn\.cc-switch\skills\find-skills\`：负责查公开 skill 生态，适合“去找有没有 skill”，不负责从当前对话里提炼经验并判断写到哪里。
  - `C:\Users\SanAn\.cc-switch\skills\skill-creator\`：负责正式创建和迭代 skill，适合在结论已经明确之后接手，不适合承担这一步“先判断该不该改、该改谁”。
- 另外，`D:\BaiduSyncdisk\.agents\agents-skills-src\find-skills-local\` 和 `D:\BaiduSyncdisk\.agents\agents-skills-src\skill-creator-local\` 明确把自己写成“过渡壳”或“本地补充”，不应当作为这次主结论里的推荐修改目标。

外面有没有类似 skill：
- 有两类相近做法。
- 第一类是“找 skill”的通用 skill，例如 [vercel-labs/skills 的 `find-skills`](https://skills.sh/vercel-labs/skills/find-skills)。它解决的是“公开生态里有没有现成 skill”，和你这次流程里的“外部复核”这一步接近，但它不负责整理当前对话经验，也不负责判断该新建还是改已有。
- 第二类是“把对话沉淀成 skill”的 skill，例如 [sanjeed5/capture-skill 的 `capture-skill`](https://skills.sh/sanjeed5/capture-skill/capture-skill)。它会从对话里提炼 workflow，并在“新建还是更新现有 skill”之间做选择，这和你的方向最接近。
- 但它和你这次需求还有明显差别：它更偏“把 learnings 保存成 skill”，而不是“先核对本地主入口、再查公开生态、最后给出四选一处置结论，并排除历史过渡壳”。所以它证明这条方向在公开生态里是成立的，但还不足以替代你本地这份 skill。
- 公开生态里的 [Anthropic `skill-creator`](https://skills.sh/anthropics/skills/skill-creator) 也相关，但它定位是“正式创建、测试、迭代 skill”，不是这一步的“经验归档与去向判断”。

如果结论是修改现有 skill，建议这样改：
- 修改目标：`D:\BaiduSyncdisk\.agents\agents-skills-src\duihua-jingyan-tiqu\`
- 在“先查本地有没有类似 skill”那一节再收紧一句：先把当前默认可用 skill 和源码目录里的主入口对齐，再把 `*-local`、兼容壳、同步镜像明确降级为背景信息，不进入主结论推荐位。
- 在“再查外面有没有类似 skill”那一节补一句：公开生态里的相近项要区分成“通用找 skill”“正式造 skill”“从对话捕获经验”三类，避免因为看到相近名字就误判成该新建。
- 在“结论怎么选”里补一个更硬的判定句：只要本地已有 skill 覆盖主流程，这次新增内容又主要是规则、边界、例子或处置口径，就优先落到“修改现有 skill”。
- 在例子里补一个和这次几乎同型的样例：用户明确要求“先查本地和公开生态，再告诉我是新建还是修改”，输出必须先讲本地，再讲公开生态，最后直接下结论，不能只给模糊建议。

审查稿：
- skill 名称：`duihua-jingyan-tiqu`
- description：从当前对话里提炼可复用经验，先核对本地现有 skill 和公开生态里的相近做法，再判断这些经验更适合修改现有 skill、整理成新 skill、写进当前项目，还是这次不改。用户一旦在问“这段对话值不值得做成 skill”“该新建还是改已有”“先查有没有重合再决定”，就优先使用。
- 什么时候该触发：用户想把这轮对话沉淀下来；用户明确要求判断“新建 / 修改 / 不改”；用户提到“先查本地有没有类似，再看外面有没有”。
- 预期输出：一份审查稿，先说本地重合情况，再说公开生态相近做法，最后给出四选一结论；若结论是修改或新建，再补可直接交给 `skill-creator` 的草案。
- 拟议结构：回看当前对话 / 本地重合检查 / 公开生态复核 / 结论判定 / 修改建议与审查稿
- scripts / references / assets：目前不需要额外加；这类任务更像判断与汇报，不是重复性脚本任务。
- 建议测试提示：
  - “把我们刚才这轮对话整理一下。先看本地有没有类似 skill，再看公开生态，最后直接告诉我是新建还是改已有。”
  - “我们刚才讨论出一套稳定方法了，但我不确定该写进项目文档还是 skill。你先查重，再给结论。”
  - “别直接改文件。先判断这段经验值不值得沉淀，以及该落到哪个现有 skill。”
