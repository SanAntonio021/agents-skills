# Eval prompt

你负责 D:\BaiduSyncdisk\.agents\agents-skills-src\duihua-jingyan-zhengli-workspace\iteration-6\eval-1-command-skill-review\old_skill\run-1\ 的写入。你不是一个人在代码库里工作，不要改动任何源码，也不要回退别人的改动。任务：这是一次 dry-run 评测，请读取旧版 skill 快照：D:\BaiduSyncdisk\.agents\agents-skills-src\duihua-jingyan-zhengli-workspace\skill-snapshot-iteration-6\duihua-jingyan-zhengli\SKILL.md ，按旧版 skill 的要求回答下面的用户提示，但不要真的修改文件、执行 git 提交或推送。用户提示：帮我把这轮对话整理一下。我们刚才一直在修 PowerShell 路径、引号和 UTF-8 编码判断，这些经验看起来更像该写进现有的命令类 skill。先别改文件，先告诉我这次更适合怎么处理，并给我一个审查稿。把最终用户可见答复保存到 D:\BaiduSyncdisk\.agents\agents-skills-src\duihua-jingyan-zhengli-workspace\iteration-6\eval-1-command-skill-review\old_skill\run-1\outputs\response.md 。再把一份简短 transcript 保存到 D:\BaiduSyncdisk\.agents\agents-skills-src\duihua-jingyan-zhengli-workspace\iteration-6\eval-1-command-skill-review\old_skill\run-1\transcript.md ，格式仿照评测目录里现有 transcript：包含 Eval prompt 和 Final response。最终请只汇报你写了哪些文件。

# Final response

这次在做：整理经验，判断这些经验该写到哪里

结论：修改现有 skill

理由：
- 这轮对话沉淀出来的核心，不是一个新的独立流程，而是 Windows / PowerShell 命令在实际执行时怎么把路径、引号和 UTF-8 编码判断写稳。
- 这些内容和现有 `command-pattern-memory` 的职责直接对齐。它本来就是复用已验证的 Windows / PowerShell 命令形态，减少路径、引号、编码和外部 CLI 写错的概率。
- 这次经验里最有价值的部分，是“先失败、后修正、再沉淀成稳定命令骨架”的纠偏经验，更适合补进现有命令类 skill 的模式库，不值得单独再建一个新 skill。

本地有没有类似 skill：
- 有。`C:\Users\SanAn\.cc-switch\skills\command-pattern-memory\SKILL.md` 已经覆盖 PowerShell 路径、引号、编码、外部 CLI 和失败后回写模式库这条主流程。
- 另外还有 `zhongduan-zhixing-hulan` 这类终端护栏型 skill，但它更偏通用静态规则，不是这次经验的主落点。

外面有没有类似 skill：
- 我没查到一个公开生态里高度同名、专门只做“PowerShell 路径 / 引号 / UTF-8 判断”的独立 skill。
- 公开资料里更常见的做法，是把这类高频、易错、可复用的 Windows 命令经验，沉淀进已有 skill 的 `references/`、模式库或恢复清单，而不是单独拆一个新 skill。

如果结论是修改现有 skill，建议这样改：
- 把“UTF-8 / 文件编码判断”明确补进 `command-pattern-memory` 的适用场景和回写规则。
- 把这轮对话里已经证明有效的 PowerShell 稳定写法，拆成 references，而不是把细节都堆进 `SKILL.md`。
- 明确它和 `zhongduan-zhixing-hulan` 的分工：前者负责复用命令骨架，后者负责终端静态护栏。

审查稿：
- skill 名称：继续使用 `command-pattern-memory`
- description：复用已验证的 Windows 和 PowerShell 命令形态，减少路径、引号、编码判断和外部 CLI 写错的概率。Use when the task likely requires `shell_command`, PowerShell, or a Windows CLI command, especially for path quoting, UTF-8 / file encoding checks, external tool invocation, and failure-recovery patterns.
- 什么时候该触发：路径包含空格或中文、PowerShell 引号容易写错、需要判断文件是否 UTF-8、外部 CLI 参数容易在 PowerShell 下转义失控、命令刚经历“先失败后修正”
- 预期输出：推荐使用的命令骨架、关键引号 / 路径 / 编码判断规则、必要的前置检查、是否值得把这次修正回写进模式库
- 拟议结构：何时进入命令模式记忆 / PowerShell 路径与引号稳定模式 / UTF-8 与文件编码最小检查顺序 / 外部 CLI 混用时的回退策略 / 失败后经验何时回写
- scripts / references / assets：`scripts` 暂时不必新增；`references` 建议补；`assets` 不需要
- 建议测试提示：`帮我在 PowerShell 里安全读取一个带空格和中文路径的文件` / `这个外部 CLI 参数里自带引号，命令该怎么写稳` / `先别猜编码，帮我判断这个文件是不是 UTF-8 再决定怎么读`

我这次的判断很明确：更适合补现有命令类 skill，不适合新建一个专门整理这轮对话的新 skill。现在先停在审查稿，不改文件正文。
