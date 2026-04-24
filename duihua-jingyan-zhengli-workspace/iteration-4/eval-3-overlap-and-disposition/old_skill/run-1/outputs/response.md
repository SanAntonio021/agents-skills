Candidate skill: duihua-jingyan-zhengli
Decision: 更适合扩展现有 skill

Why:
- 本地已经有 `D:\BaiduSyncdisk\.agents\agents-skills-src\duihua-jingyan-zhengli\SKILL.md`，目标和主流程都高度重合：都是先从当前对话提炼可复用经验，再查本地和外部有没有相近 skill，最后判断是新建、修改还是不动。
- 这次新补出来的方法，核心还是在细化同一条工作流，不是换了一个全新任务。它更像给现有 skill 补判定口径、边界和输出模板，而不是另起一个 skill。
- 公开生态里能找到的是邻近能力，不是同一能力：`find-skills` 负责找 skill，`skill-creator` 负责创建 skill，`specstory-session-summary` 更像会话摘要，`AutoSkill` 是从对话中自动抽取技能的研究/框架，不是这类“先审查再决定写到哪里”的人工整理 skill。

Duplicate check:
- Local overlap: `D:\BaiduSyncdisk\.agents\agents-skills-src\duihua-jingyan-zhengli\SKILL.md` 已覆盖主流程；`D:\BaiduSyncdisk\.agents\agents-skills-src\find-skills-local\SKILL.md` 是外部复核配套，不是替代品。
- External overlap: 公开生态有相邻 skill，但没有一个同时覆盖“从对话提炼经验 + 本地查重 + 外部复核 + 判断新建/修改/不动”这一整套流程，所以没有必要为这次再单开一个新 skill。

Proposed triggers:
- 把这段对话整理成经验
- 看看值不值得做成 skill
- 判断该新建 skill 还是改已有的
- 先查本地和公开生态，再决定写到哪里

Proposed frontmatter description:
从当前对话里提炼可复用经验，先查本地和公开生态有没有高重合 skill，再判断这些经验更适合修改现有 skill、整理成新 skill、写进当前项目，还是这次不改；在用户批准前只交付审查稿，不直接动文件。

Proposed sections:
- 从当前对话抽取最小事实集
- 本地重合检查与主入口判断
- 外部生态复核与相邻 skill 区分
- 新建 / 修改 / 项目内沉淀 / 不改 的决策口径
- 审查稿输出模板与批准前暂停规则

Resources:
- scripts: no
- references: no
- assets: no

结论直接说：
这次不要另做一个 skill，改现有的更对。因为本地已经有高重合 skill，差的是细则，不是能力类型。
