# 这次在做

整理刚才那条判断规则，明确这些经验该写到当前项目里，还是该进入 skill。

## 结论

**这次的主结论不是“新建 skill”，也不是“全写进项目里”，而是分两类处理：**

- **项目私有经验**：先写在当前项目里。
- **跨项目都成立的判断方法**：更适合补到现有 skill `D:\BaiduSyncdisk\.agents\agents-skills-src\duihua-jingyan-tiqu\` 的审查稿里，后续如果你批准，再正式修改。

换句话说，你们刚才讨论出来的那句：

> 项目私有经验先记在当前项目里，跨项目都成立的方法再整理成 skill

本身更像一条**通用分流规则**，不只是当前项目临时可用，所以它**更适合归到现有的“对话经验整理 / 判断写到哪里”这个 skill 里**，而不是只埋在某一个项目文档里。

## 理由

- 这条规则说的不是某个项目的目录、命名、接口、部署方式，而是在教人**怎么判断经验该放哪里**。
- 只要以后还会遇到“这段经验该留在项目里，还是抽成 skill”这种问题，这条规则就还能继续用。
- `D:\BaiduSyncdisk\.agents\agents-skills-src\duihua-jingyan-tiqu\SKILL.md` 现在本来就在负责这件事：提炼经验、判断该写到哪里、决定是新建 skill、修改 skill，还是只写项目里。
- 所以这次更像是给现有 skill **补一条更清楚的判断标准**，不是另起炉灶。

## 本地有没有类似 skill

- **有，而且已经很贴近。**
- `D:\BaiduSyncdisk\.agents\agents-skills-src\duihua-jingyan-tiqu\SKILL.md` 已经明确写了四种结论：`整理成新 skill`、`修改现有 skill`、`写在当前项目里`、`这次不改`。
- 它也已经包含一句核心判断：**“哪些内容只对当前项目有用，哪些内容换个项目也成立。”**
- 这说明你们刚才讨论出来的规则，**不是一个全新主题**，而是对现有 skill 的判断标准做进一步明确。

## 外面有没有类似做法

- **有，外部资料也普遍是分层放置，而不是全塞进同一处。**
- Microsoft 的 Agent Skills 资料把可复用 workflow 当成 skill，并区分团队仓库内的 skill 和个人全局 skill，说明“复用范围不同，放置位置也不同”。  
  参考：[https://microsoft.github.io/skills/](https://microsoft.github.io/skills/)  
  参考：[https://dev.to/pwd9000/github-copilot-skills-reusable-ai-workflows-for-devops-and-sres-caf](https://dev.to/pwd9000/github-copilot-skills-reusable-ai-workflows-for-devops-and-sres-caf)
- 一篇 2026 年论文甚至直接用了两层结构：**Global Skills** 放跨项目可复用流程，**Project Skills** 放项目特有流程和约束。  
  参考：[https://d197for5662m48.cloudfront.net/documents/publicationstatus/309332/preprint_pdf/1f64711628ebdd55a71d760b2ad65832.pdf](https://d197for5662m48.cloudfront.net/documents/publicationstatus/309332/preprint_pdf/1f64711628ebdd55a71d760b2ad65832.pdf)
- 社区 skill 仓库里也普遍把 skill 定义成**可重复调用的稳定流程**，而不是一次性的项目随手记录。  
  参考：[https://github.com/iliaal/ai-skills](https://github.com/iliaal/ai-skills)

## 所以这次该写到哪里

可以直接按下面这条简单判断来落：

- 如果这条经验**离开当前项目就不一定成立**，写当前项目。
- 如果这条经验是在说**怎么判断、怎么整理、怎么复用**，而且换项目还成立，优先作为 skill 规则。

套回你这次这句话：

- “项目私有经验先记在当前项目里”这一半，是在定义**项目经验的归档原则**。
- “跨项目都成立的方法再整理成 skill”这一半，是在定义**什么时候该升格成 skill**。

因此，**整句话作为规则，更适合进入现有 skill 的审查稿**；  
而以后真正整理具体内容时，再把具体项目坑点、目录约定、临时限制，继续留在各自项目里。

## 这次建议

**建议归类为：修改现有 skill。**

不是现在就改文件，而是先把下面这个方向作为审查意见记住：

- 在 `D:\BaiduSyncdisk\.agents\agents-skills-src\duihua-jingyan-tiqu\SKILL.md` 里，把“项目私有经验 vs 跨项目方法”的分流标准写得更直白一点。
- 最好再补一个例子，专门说明：
  - 某项目专属目录结构、命名习惯、历史坑点，写项目里。
  - 能跨项目复用的判断框架、整理流程、提炼方法，才进入 skill。

如果你现在只要一句最短结论，那就是：

**具体项目经验写项目里；这条“先项目、后 skill”的判断规则本身，应该归到现有 `duihua-jingyan-tiqu` skill 的审查稿里。**
