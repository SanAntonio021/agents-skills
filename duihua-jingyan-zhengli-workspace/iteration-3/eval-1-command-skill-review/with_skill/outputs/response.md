这次在做：整理经验 / 判断写到哪里

结论：修改现有 skill

更具体地说，这次更适合补到源码目录 `D:\BaiduSyncdisk\.agents\agents-skills-src\command-pattern-memory\`，先不要新建 skill，也不要去改 `D:\BaiduSyncdisk\.agents\agents-skills-src\duihua-jingyan-tiqu\`。

理由：

- 你这轮沉淀出来的核心，不是一个新任务流程，而是 Windows / PowerShell 命令在“路径、引号、UTF-8 编码判断”上的稳定写法。这个范围已经被 `command-pattern-memory` 明确覆盖了。
- 现有 `command-pattern-memory` 的 `description`、`何时使用`、`回写规则` 已经写了路径、引号、编码、先失败后成功再回写，这说明主流程是对的，缺的是更细的模式和触发说明，不缺一个新 skill。
- 这次经验是“命令形态纠偏经验”，不是“经验提取方法论”。所以它不该继续堆进 `duihua-jingyan-tiqu`，后者负责判断写到哪里，不负责承载命令细节。
- 外部公开生态里也有相近东西，但更像通用 PowerShell 规则，不是你现在这种“在 Windows 环境里把路径、引号、编码诊断收口成可复用命令骨架”的本地工作流，所以更像补强现有 skill，而不是另起炉灶。

本地有没有类似 skill：

- 有，最接近的是 `D:\BaiduSyncdisk\.agents\agents-skills-src\command-pattern-memory\SKILL.md`。
- 它已经覆盖：
  - 路径包含空格、中文或深目录
  - PowerShell / Windows CLI 高风险命令
  - 先失败、后成功后的模式回写
  - 编码、引号、路径这几类高价值问题
- 它现有参考文件里也已经有承载位：
  - `D:\BaiduSyncdisk\.agents\agents-skills-src\command-pattern-memory\references\cli-paths.md`
  - `D:\BaiduSyncdisk\.agents\agents-skills-src\command-pattern-memory\references\markdown-read-utf8.md`
  - `D:\BaiduSyncdisk\.agents\agents-skills-src\command-pattern-memory\references\python-utf8.md`
  - `D:\BaiduSyncdisk\.agents\agents-skills-src\command-pattern-memory\references\validated-command-patterns.md`
  - `D:\BaiduSyncdisk\.agents\agents-skills-src\command-pattern-memory\references\recovery-capture-checklist.md`

外面有没有类似 skill：

- 有相近公开 skill，例如 [powershell-windows](https://skills.sh/davila7/claude-code-templates/powershell-windows)，它说明公开生态里确实有人把 PowerShell 易错点单独整理。
- 但它更偏通用 PowerShell 语法和脚本模板，不是你这里这种“命令骨架复用 + 失败后回写 + Windows 本地路径/编码坑位”的组织方式。
- 另外，公开问题里也能看到这类坑是反复出现的，而不是一次性偶发：
  - [Codex Windows 下脆弱引号与 shell 混淆问题](https://github.com/openai/codex/issues/9581)
  - [PowerShell UTF-8 / 中文输出乱码问题](https://github.com/openai/codex/issues/4498)
- 这进一步说明：该补的是现有命令类 skill 的模式库，不是单独再造一个“对话经验 skill”分支。

如果结论是修改现有 skill，建议这样改：

- 修改目标先锁定源码目录：`D:\BaiduSyncdisk\.agents\agents-skills-src\command-pattern-memory\`
- `SKILL.md` 里补一条更明确的触发说明：当问题集中在 PowerShell 路径引用、参数引号、UTF-8 判定或编码环境时，优先进入这个 skill，而不是临场拼命令。
- `references\validated-command-patterns.md` 里补一条更明确的路由，例如“PowerShell 路径/引号/UTF-8 联合诊断”。
- 优先补现有参考文件，不急着新建文件：
  - 路径和引号骨架补到 `references\cli-paths.md`
  - 读取 UTF-8 文本、判断乱码来源补到 `references\markdown-read-utf8.md`
  - 涉及 PowerShell 下 Python 或环境变量联动时，再补 `references\python-utf8.md`
- `references\recovery-capture-checklist.md` 可以补一句更具体的提示：如果同一线程里连续在“路径写法 -> 引号写法 -> 编码判定”上反复纠偏，默认视为同一个高价值模式收口机会，而不是三条零散经验。

为什么现有内容还不够：

- 现在的总入口已经说了“路径、引号、编码”，但还不够像“拿来就能套”的规则。
- 它更像分类说明，缺少你这次对话里最有价值的东西：先检查什么，再判断什么，再决定改引号、改路径表达、还是先确认编码。
- 换句话说，现在缺的是“顺手就能复用的窄模式”，不是缺一个新 skill 名字。

审查稿：

- skill 名称：`command-pattern-memory`
- 处理方式：修改现有 skill，不新建
- 推荐修改源码目录：`D:\BaiduSyncdisk\.agents\agents-skills-src\command-pattern-memory\`
- description：
  复用已验证的 Windows 和 PowerShell 命令形态，减少路径、引号、UTF-8 编码判断和外部 CLI 调用中的高频错误；当同一线程里出现先失败后成功的命令纠偏时，优先把成功骨架收口到最近的模式文件。
- 什么时候该触发：
  - PowerShell 命令涉及中文、空格、深目录或绝对路径
  - 多词参数、嵌套引号、`-LiteralPath`、`-Encoding` 这类写法容易出错
  - 需要先判断“是路径问题、引号问题，还是 UTF-8 / 代码页问题”
  - 同一线程刚出现过一次失败，后面靠改命令形态修好了
- 预期输出：
  - 给出最稳的命令骨架
  - 明确该替换哪些占位符
  - 明确先做哪些前置检查
  - 明确该避开什么失败形态
  - 必要时把成功形态回写到最近的参考文件
- 拟议结构：
  - `SKILL.md`：补触发说明和“路径 / 引号 / UTF-8 联合诊断”入口
  - `references\validated-command-patterns.md`：补新的路由项
  - `references\cli-paths.md`：补 PowerShell 路径与引号的稳定骨架
  - `references\markdown-read-utf8.md`：补 UTF-8 判定和读取的稳定骨架
  - `references\recovery-capture-checklist.md`：补这类连续纠偏的收口规则
- scripts / references / assets：
  - `scripts`：这次不需要
  - `references`：需要，且优先补现有文件
  - `assets`：不需要
- 建议测试提示：
  - “把这个带中文和空格的 Windows 路径传给 PowerShell，别再因为引号炸掉。”
  - “读取一个中文 Markdown，先判断是不是 UTF-8，再给稳定命令。”
  - “这条 PowerShell 命令第一次失败了，第二次靠改 `-LiteralPath`、引号和编码成功，帮我沉淀成可复用模式。”

一句话收口：这次不是“再做一个新 skill”，而是把已经证明有复用价值的 Windows 命令纠偏经验，补进现有 `command-pattern-memory` 的源码和参考模式里。
