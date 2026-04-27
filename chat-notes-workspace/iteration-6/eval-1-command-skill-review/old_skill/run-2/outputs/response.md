这次在做：整理经验，判断这些经验该写到哪里

结论：修改现有 skill

理由：
- 这轮对话沉淀出来的核心，不是一个新的独立流程，而是 Windows / PowerShell 命令在路径、引号和 UTF-8 编码判断上的稳定写法。
- 这类经验和现有命令类 skill 的职责直接重合，尤其是 `D:\BaiduSyncdisk\.agents\agents-skills-src\command-memory\SKILL.md`，它本来就是复用已验证的 Windows / PowerShell 命令形态，减少路径、引号、编码和外部 CLI 写错的概率。
- 这次最有价值的内容，属于“先失败、后修正、再沉淀成稳定命令骨架”的可复用纠偏经验，更适合补进现有 skill，而不是再拆一个新 skill。

本地有没有类似 skill：
- 有。最接近的是 `D:\BaiduSyncdisk\.agents\agents-skills-src\command-memory\SKILL.md`，目标、边界和这次经验高度一致，应该把它当成推荐修改目标。
- 另外还有 `D:\BaiduSyncdisk\.agents\agents-skills-src\terminal-safe\SKILL.md`，但它更偏通用终端护栏，不是这次经验的主落点。
- 如果要区分当前加载来源和推荐修改目标，这次我建议改源码目录 `D:\BaiduSyncdisk\.agents\agents-skills-src\command-memory\`，不是 `C:\Users\SanAn\.cc-switch\skills\` 下的同步产物。

外面有没有类似 skill：
- 有相近做法，但没有看到一个公开 skill 能和这次需求高重合到值得替代现有本地 skill。
- `skills.sh` 上的 `davila7/claude-code-templates` 里的 `powershell-windows`，重点在 PowerShell 常见坑和 Windows 写法模式，和这次经验接近，但它更像通用 PowerShell 规则集，不是围绕你当前这套命令纠偏流程来组织的。
- `skills.sh` 上的 `josiahsiegel/claude-plugin-marketplace` 里的 `windows-git-bash-paths`，也覆盖了 Windows 下路径和引号问题，但范围更窄，偏 Git Bash / Windows 路径转换，不等于这次要整理的 PowerShell 命令经验。
- 所以外部情况更支持“补现有 skill”，不支持“为了公开生态里没有完全同类，就新建一个 skill”。

如果结论是修改现有 skill，建议这样改：
- 把“UTF-8 / 文件编码最小判断顺序”明确补进 `command-memory` 的适用场景和回写规则，不要只停留在“编码”这个泛词。
- 把这轮对话里已经证明有效的 PowerShell 路径和引号稳定写法，沉淀到 `references/` 模式库，而不是把细节全堆进 `SKILL.md`。
- 明确它和 `terminal-safe` 的分工：`command-memory` 负责复用已验证的命令骨架，`terminal-safe` 负责静态护栏和执行安全。

如果结论是新建或修改 skill，再给审查稿：
- skill 名称：继续使用 `command-memory`
- description：复用已验证的 Windows 和 PowerShell 命令形态，减少路径、引号、UTF-8 / 文件编码判断和外部 CLI 写错的概率。Use when the task likely requires `shell_command`, PowerShell, or a Windows CLI command, especially for path quoting, encoding checks, external tool invocation, and failure-recovery patterns.
- 什么时候该触发：路径包含空格、中文或深层目录；PowerShell 引号容易写错；需要先判断文件是否 UTF-8 再决定怎么读；外部 CLI 参数在 PowerShell 下容易转义失控；命令刚经历“先失败后修正”
- 预期输出：推荐命令骨架、关键路径 / 引号 / 编码判断规则、必要前置检查、以及这次修正是否值得回写进模式库的判断
- 拟议结构：何时进入命令模式记忆 / PowerShell 路径与引号稳定模式 / UTF-8 与文件编码最小检查顺序 / 外部 CLI 混用时的回退策略 / 失败后经验何时回写
- scripts / references / assets：`scripts` 暂时不必新增；`references` 建议补一组命令模式和编码判断样例；`assets` 不需要
- 建议测试提示：`帮我在 PowerShell 里安全读取一个带空格和中文路径的文件` / `这个外部 CLI 参数里自带引号，命令该怎么写稳` / `先别猜编码，帮我判断这个文件是不是 UTF-8 再决定怎么读`

这次更适合修改现有 skill，不适合新建。现在先停在审查稿，不改文件正文。
