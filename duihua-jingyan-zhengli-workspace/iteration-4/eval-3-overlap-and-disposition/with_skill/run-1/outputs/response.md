这次在做：整理经验 / 判断写到哪里

结论：修改现有 skill

理由：
- 你现在这套方法的主问题，不是“有没有一个全新的任务类型”，而是“如何把从对话里整理经验，再判断该新建、改已有、写项目里还是不动”这条判断链说得更稳、更可执行。这个主流程，现有 `D:\BaiduSyncdisk\.agents\agents-skills-src\duihua-jingyan-zhengli\SKILL.md` 已经覆盖了。
- 这次新补出来的价值，主要是判定更细了：先查本地，再查公开生态；不只看名字，要看目标、流程、边界；如果用户明确在问“新建还是改已有”，又已经找到高重合 skill，就优先落到“修改现有 skill”或“整理成新 skill”，不要轻易退回“这次不改”。这些都属于现有 skill 的增强，不是新 skill 的独立主流程。
- 如果现在另做一个新 skill，很容易和现有 `duihua-jingyan-zhengli` 形成高重合：都在回看对话、查相近 skill、判断归属、给审查稿。这样会让触发边界变乱，后面反而更难维护。

本地有没有类似 skill：
- 有，最高重合的是 `D:\BaiduSyncdisk\.agents\agents-skills-src\duihua-jingyan-zhengli\SKILL.md`。它已经明确要求：先回看对话，再查本地，再查外面，然后在“整理成新 skill / 修改现有 skill / 写在当前项目里 / 这次不改”之间下结论。
- `D:\BaiduSyncdisk\.agents\agents-skills-src\find-skills-local\SKILL.md` 有部分重合，但它更偏“帮你找本地或上游 skill，并放回 cc-switch 管理语境里判断”，不是专门做“从当前对话提炼经验，再决定该写到哪里”。
- `D:\BaiduSyncdisk\.agents\agents-skills-src\skill-creator-local\SKILL.md` 是后续正式创建或修改 skill 时用的，不负责前面的归类判断。
- `D:\BaiduSyncdisk\.agents\agents-skills-src\jineng-fupan\SKILL.md` 更偏“周内 transcript 复盘与跨项目观察”，不是当前这类单次对话经验归档与处置判断。
- `D:\BaiduSyncdisk\.agents\agents-skills-src\codex-skill-ecosystem-audit\SKILL.md` 是生态周检，不是单轮对话经验去向判断。

外面有没有类似 skill：
- 有相近做法，但没有一个把“从当前对话提炼经验”与“判断该新建、改已有、写项目里还是不动”这四选一处置，做得像你这个本地 skill 这么贴合。
- 官方 `find-skills` 强调先看 `skills.sh` 热门项，再搜索并核对来源质量，适合作为你这份 skill 里“先查外面”的方法依据，而不是替代品。来源：[`find-skills` on GitHub](https://github.com/vercel-labs/skills/blob/main/skills/find-skills/SKILL.md?plain=1)，[`skills.sh` 页面](https://skills.sh/skills/skills/find-skills)。
- 官方/生态里的 `skill-creator` 更偏“创建或迭代 skill”的全流程，包含测试、评估、修改旧 skill，不负责先做这次这种归属判断。来源：[`anthropics/skills` 的 `skill-creator`](https://skills.sh/anthropics/skills/skill-creator)。
- 公开生态里最接近的是 `skill-capture`、`capture-skill` 这类“把对话经验直接沉淀成 skill”的做法。它们会检查是否该更新现有 skill，但默认目标更偏“落成 skill 文件”，而不是像你这里这样先严肃区分“新建 / 修改 / 项目内记录 / 不改”。来源：[`skill-capture`](https://skills.sh/shipshitdev/library/skill-capture)，[`capture-skill`](https://skills.sh/sanjeed5/capture-skill/capture-skill)。

如果结论是修改现有 skill，建议这样改：
- 推荐修改的源码目录：`D:\BaiduSyncdisk\.agents\agents-skills-src\duihua-jingyan-zhengli\`
- 在“工作顺序”里再强调一次判定顺序：`先查当前会话默认可用 skill -> 再查本地源码/同步产物 -> 再查公开生态 -> 最后做处置判断`。这样更不容易漏掉“本地已有高重合 skill”。
- 在“结论怎么选”里把“修改现有 skill”的触发条件写得更硬一点：只要已有 skill 覆盖主流程，本轮新增内容只是补规则、边界、例子、收尾或路由判断，就优先修改，不另起新 skill。
- 单独补一个“高重合但不应新建”的例子。比如：用户把“从对话中提炼经验，再判断去向”的步骤聊得更完整了，这通常不是新 skill，而是给现有 skill 补判断标准和输出模板。
- 在“外部查询”部分补一句边界：公开生态里即使有相近 `skill-capture` 类 skill，也只能证明这个方向有通用需求；不能仅因为外面有类似名字，就判定本地应该新建。
- 在“汇报格式”里补一行“推荐修改目标：<skill 路径>”，让输出更适合直接交给 `skill-creator`。

如果结论是新建或修改 skill，再给审查稿：
- skill 名称：`duihua-jingyan-zhengli`
- description：从当前对话里提炼可复用经验，先查本地和公开生态有没有高重合 skill，再判断这些经验更适合修改现有 skill、整理成新 skill、写在当前项目里，还是这次不改；在用户批准前，只交付审查稿，不直接改 skill。
- 什么时候该触发：用户说“把这段对话整理一下”“看看值不值得做成 skill”“判断该写到项目里还是 skill 里”“先查有没有类似 skill，再告诉我是新建还是改已有”；或者当前对话里已经形成了稳定流程，但还没决定该沉淀到哪里。
- 预期输出：给出一个明确处置结论；说明本地和公开生态的重合情况；如果建议修改现有 skill，明确写出源码目录、建议改动点、建议放入的章节；如果建议新建或修改，再补到可交给 `skill-creator` 的审查稿程度。
- 拟议结构：先这样做 / 工作顺序 / 结论怎么选 / 汇报格式 / 例子 / 边界 / 维护
- scripts / references / assets：默认不需要新增；这类 skill 主要靠规则和例子。如果后面发现公开生态检索经常重复，再考虑补一个只读搜索辅助脚本。
- 建议测试提示：`我们刚才把一套“从对话里整理经验，再判断是新建、修改还是不动”的方法越聊越完整了。你先帮我查本地和公开生态有没有相近 skill，再告诉我这次到底该另做一个 skill，还是只是改已有的。`
- 建议测试提示：`把这轮对话整理一下。重点不是直接做成新 skill，而是判断这些经验该写进现有 skill、项目文档，还是先不动。`
- 建议测试提示：`我们刚才补出来的是几个边界规则，不是整套新流程。你先查本地有没有高重合 skill，再判断这次是不是只该改原来的。`

这次不建议另做一个新 skill。最直接的做法，就是后续把这轮新增的判定规则、例子和输出模板，补进 `D:\BaiduSyncdisk\.agents\agents-skills-src\duihua-jingyan-zhengli\SKILL.md`。
