这次在做：整理经验 / 判断写到哪里

结论：修改现有 skill

理由：
- “项目私有经验先记在当前项目里，跨项目都成立的方法再整理成 skill” 本身是跨项目可复用的判断规则，不是只对某一个项目成立的临时说法。
- 但它解决的仍然是“经验该落在哪一层”的归类问题，和现有 skill `duihua-jingyan-zhengli` 的主流程高度重合，还没到需要拆成新 skill 的程度。
- 只对当前项目有用的经验，应该继续写在当前项目里，比如当前项目特有的目录结构、命名约定、历史包袱、协作边界、只在这个工作区成立的坑。
- 跨项目也成立的经验，才适合补进现有 skill，比如先区分“项目私有”还是“跨项目通用”、没有形成稳定流程前不要升格成 skill、先落项目文档再观察是否反复复用。

本地有没有类似 skill：
- [D:\BaiduSyncdisk\.agents\agents-skills-src\duihua-jingyan-zhengli](D:\BaiduSyncdisk\.agents\agents-skills-src\duihua-jingyan-zhengli) 已经高重合。它本来就负责从对话里提炼经验，并判断这些经验更适合写进当前项目、用于修改现有 skill，还是整理成新 skill。
- 当前会话里可用的 `skill-creator` 更偏正式创建、补齐和评测 skill，不是这一步“先判断该写哪里”的主入口。

外面有没有类似 skill：
- 我查到公开生态里有偏“记忆沉淀”或“经验提升”的做法，比如 [session-memory](https://skills.sh/romiluz13/cc10x/session-memory) 和 [self-improvement](https://skills.sh/moltbot/skills/self-improvement) 这类，会把 learnings 归档到项目记忆或可复用模式里。
- 但没查到一个高重合的公开 skill，专门负责“先判断这些经验只对当前项目有效，还是跨项目通用，再决定写项目文档还是写 skill”。
- 所以外部生态能借鉴的是“分层沉淀”的方向，不足以替代当前这个 skill。

如果结论是修改现有 skill，建议这样改：
- 在 [D:\BaiduSyncdisk\.agents\agents-skills-src\duihua-jingyan-zhengli\SKILL.md](D:\BaiduSyncdisk\.agents\agents-skills-src\duihua-jingyan-zhengli\SKILL.md) 的“工作顺序”或“结论怎么选”里明确加一条：项目私有经验优先写当前项目，跨项目通用方法再考虑升格为 skill。
- 增补一组正反例，明确哪些算“当前项目专属经验”，哪些算“跨项目通用方法”，避免以后一提“经验整理”就过早往 skill 上收。
- 在汇报模板里单列“只对当前项目有用的经验”和“跨项目也成立的经验”两段，要求先分类，再给四选一结论。

如果结论是新建或修改 skill，再给审查稿：
- skill 名称：duihua-jingyan-zhengli
- description：从当前对话提炼可复用经验，先区分项目私有经验和跨项目通用方法，再判断这些内容更适合写在当前项目、修改现有 skill、整理成新 skill，还是这次不改。
- 什么时候该触发：用户要“整理这段对话里的经验”“判断这些经验该写项目里还是写 skill 里”“区分哪些只对当前项目有效、哪些可以抽成通用规则”时触发。
- 预期输出：先列出项目专属经验与跨项目通用经验，再给出四个结论之一；如果结论是修改现有 skill 或整理成新 skill，再附审查稿，不直接改文件。
- 拟议结构：先这样做 / 工作顺序 / 结论怎么选 / 汇报模板 / 例子 / 边界
- scripts / references / assets：暂时不需要
- 建议测试提示：把这段关于当前仓库目录命名和发布流程的讨论整理一下，判断哪些该写在项目里，哪些值得补进 skill。 / 我们刚才总结出一套跨多个项目都适用的经验沉淀方法，你先查本地和公开生态有没有类似 skill，再判断这次该新建还是改已有。 / 刚才那轮讨论里既有这个项目特有的坑，也有通用方法，先帮我分开，再告诉我这些内容各该落在哪里。
