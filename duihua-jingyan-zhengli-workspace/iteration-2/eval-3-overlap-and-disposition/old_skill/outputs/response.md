Candidate skill: `duihua-jingyan-tiqu`

Decision: 更适合扩展现有 skill

Why:
- 本地已经有一个几乎同题的 skill：`D:\BaiduSyncdisk\.agents\agents-skills-src\duihua-jingyan-tiqu\SKILL.md`，它的核心目标就是“从当前对话里提炼可复用经验，再判断是新建、改已有 skill、写进项目，还是这次不改”。
- 你这次新增的东西，不是另一个完全不同的任务，而是把这套判断流程补得更完整了，属于同一主流程里的规则细化。
- 公开生态里也能找到相近做法，但它们大多只做到“把对话经验整理成 skill”这一层，还没把你这里这种“先查本地重合、再查外部、最后判断新建/修改/不动”的本地决策口径做得这么贴合。

Duplicate check:
- Local overlap:
  - 高重合：`D:\BaiduSyncdisk\.agents\agents-skills-src\duihua-jingyan-tiqu\SKILL.md`
  - 作用接近但不是主入口：`D:\BaiduSyncdisk\.agents\agents-skills-src\find-skills-local\SKILL.md` 只负责本地查找与委托；`D:\BaiduSyncdisk\.agents\agents-skills-src\skill-creator-local\SKILL.md` 只负责确认后正式创建或修改；`D:\BaiduSyncdisk\.agents\agents-skills-src\jineng-fupan\SKILL.md` 偏周报复盘，不是当前对话经验落 skill 的判断器。
- External overlap:
  - 相近公开做法 1：OpenClaw 的 `self-improving-agent` 会把已验证、可复用的 learnings 提升成 skill，说明“从经验沉淀成 skill”这条路在公开生态里是成立的，但它更偏持续自改进，不是你现在这类人工审查式分流判断。[来源](https://github.com/openclaw/skills/blob/main/skills/pskoett/self-improving-agent/SKILL.md)
  - 相近公开做法 2：社区里的 `capture-skill` 会把当前对话中的模式、流程和知识整理成“新 skill 或已有 skill”，这和你的主题很像；但它没有你这里这么强调本地查重、外部复核和“无需落盘”的判断口径。[来源](https://gist.github.com/jediahkatz/e528631580cc42dd5b8092aa7f162851?permalink_comment_id=5968161)
  - 生态层面证据：`tech-leads-club/agent-skills` 这类公开技能仓已经把“查 skill / 读 skill / 复用 skill”做成独立能力，说明外部生态成熟，但没直接替代你这个本地经验分流 skill。[来源](https://github.com/tech-leads-club/agent-skills)

建议结论：
- 这次不要另做一个新 skill。
- 直接修改现有 `D:\BaiduSyncdisk\.agents\agents-skills-src\duihua-jingyan-tiqu\SKILL.md` 更合适。

建议补进去的点：
- 把“先看当前对话，信息不够再问，而且一次只问一个问题”写得更硬一点，避免一上来就让用户重复背景。
- 把“本地查重”的顺序写得更明确：先看当前会话已可用 skills，再看 `C:\Users\SanAn\.cc-switch\skills\`，最后才回源码目录决定真正修改目标。
- 把“历史入口、兼容包装、退役 `*-local` 变体不要当主入口”的口径写清楚，避免改错对象。
- 把最终结论固定成几类清楚选项，例如“整理成新 skill / 修改现有 skill / 写在当前项目里 / 这次不改”，这样后面更好落地。
- 把“外部查询如果没做完，要明确说明查到了什么、还缺什么”写成硬规则，避免假装已经核实完。

如果按这次判断往下走，推荐修改目标就是：
`D:\BaiduSyncdisk\.agents\agents-skills-src\duihua-jingyan-tiqu\SKILL.md`

不推荐新建的核心原因只有一句话：主问题已经被现有 skill 覆盖了，这次新增的是规则补强，不是新任务类型。
