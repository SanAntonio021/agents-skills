这次在做：判断经验该写到哪里

结论：**拆开写，不新建 skill。**

- **项目私有经验**：先记在当前项目里。
- **跨项目都成立的方法**：整理进现有 skill。
- **这次不该做的事**：不要把两类内容混在一个 skill 里，也不要因为提到“经验”就直接新建 skill。

理由：

- 你刚才讨论出来的核心，不是一套全新的独立流程，而是一条**经验归位规则**：什么该留在项目内，什么才值得上升成 skill。
- 这条规则本身有跨项目复用价值，但某个项目里的背景、约束、目录习惯、特殊坑点，离开当前项目后就可能失效，所以不该直接写成通用 skill。
- 现有 `D:\BaiduSyncdisk\.agents\agents-skills-src\duihua-jingyan-tiqu\SKILL.md` 本来就在负责“从对话里提炼经验，并判断该写到项目里还是写到 skill 里”，所以如果以后要正式沉淀这条方法，应该是**补强这个现有 skill**，不是另起一个新的。

本地有没有类似 skill：

- 有，最贴近的是 `D:\BaiduSyncdisk\.agents\agents-skills-src\duihua-jingyan-tiqu\SKILL.md`。它已经明确把结论分成“整理成新 skill / 修改现有 skill / 写在当前项目里 / 这次不改”四类。
- `D:\BaiduSyncdisk\.agents\agents-skills-src\skill-creator-local\SKILL.md` 只负责**已经决定要改 skill 之后**的正式落地，不负责前面的归位判断。
- `D:\BaiduSyncdisk\.agents\agents-skills-src\codex-long-term-memory\SKILL.md` 也说明了一个相近原则：**可变、运行时、场景相关的内容，不要混进通用 skill 源目录**。这和“项目私有经验先留在项目里”是同一路子。

外面有没有类似做法：

- 有相近思路，但没有看到一个比当前 `duihua-jingyan-tiqu` 更直接贴合你这个问题的现成 skill。
- 外部参考里，Acontext 提到 memory/skill 的结构可以按用途拆分，甚至可以做到“**一个项目一份文件**”，本质上也是在强调：**项目上下文应该按项目存放，只有稳定可复用的东西才适合抽成更通用的结构**。
  参考：["GitHub - memodb-io/Acontext"](https://github.com/memodb-io/Acontext)

这次整理后的判断可以直接记成一句话：

**项目私有经验，写当前项目；跨项目稳定方法，补现有 skill；不要为了“看起来完整”就把项目细节抽成通用 skill。**

如果以后要正式落文件，推荐归位是：

- **写到当前项目里**：项目专用背景、目录约定、当前工作流、只在这个项目成立的坑和处理办法。
- **补到现有 skill `duihua-jingyan-tiqu`**：判断“项目私有 vs 跨项目复用”的标准、分流原则、反例和边界。
- **不建议新建 skill**：因为你现在沉淀出来的，还更像一条现有 skill 应该补充的判断规则，不像一个全新的独立能力。
