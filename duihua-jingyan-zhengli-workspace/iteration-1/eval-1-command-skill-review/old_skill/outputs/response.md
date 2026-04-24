# 这次更适合怎么处理

这次我更建议按“**扩展现有命令类 skill**”处理，而不是新建一个新的 skill。

原因用大白话说，就是我们这轮沉淀出来的东西，核心不是“多了一个新任务”，而是“同一类 Windows / PowerShell 命令以后该怎么写才更稳”。你们刚才反复修的是这几类老问题：

- 路径里有空格、中文、层级深，命令容易写炸
- 引号在 PowerShell 里看着对，实际一跑就被拆坏
- UTF-8 / 中文输出到底是不是编码问题，判断口径需要固定

这些都正好落在现有 `command-pattern-memory` 的职责里。它本来就是用来记“Windows 命令骨架怎么写更稳”的，而且它现有索引里已经覆盖了：

- 路径与命令行调用
- `python -c` 和 UTF-8 环境
- 中文 Markdown / UTF-8 文本读取
- “先失败、后成功”之后把可复用修正回写进去

所以这次更像是：**给现有命令类 skill 补一组更明确的 PowerShell 路径 / 引号 / UTF-8 判断规则**，而不是再开一个新 skill。

## 审查稿

Candidate skill: `command-pattern-memory`（扩展现有 skill，不新建）

Decision: 更适合扩展现有 skill

Why:
- 本轮经验解决的是“命令形态怎么写稳”，不是一个新的独立任务流。
- 本地已有 skill 的主流程、边界和回写机制已经直接覆盖这类问题。
- 如果另起一个新 skill，会和现有命令类 skill 高度重复，后面维护时也容易分叉。

Duplicate check:
- Local overlap: `C:\Users\SanAn\.cc-switch\skills\command-pattern-memory\SKILL.md` 与本轮经验高度重合，尤其是路径、引号、编码、失败后回写这几块。
- External overlap: 外部公开生态里能找到通用 Windows / PowerShell skill，例如 [powershell-windows](https://skills.sh/davila7/claude-code-templates/powershell-windows)、[admin-windows](https://skills.sh/smithery/ai/admin-windows)，也能看到真实社区问题长期集中在 PowerShell 引号和编码稳定性上，例如 [OpenAI Codex 的 Windows 引号问题讨论](https://github.com/openai/codex/issues/9581) 和 [PowerShell 中文乱码问题讨论](https://github.com/openai/codex/issues/4498)。这说明它更像“命令模式库补强”，不像值得单拆的新 skill。

Proposed triggers:
- `PowerShell 路径总出错`
- `引号老是写炸`
- `UTF-8 怎么判断`
- `按上次正确命令方式来`
- `Windows 命令先失败后修好了`

Proposed frontmatter description:
复用已验证的 Windows 和 PowerShell 命令形态，重点沉淀路径、引号、UTF-8 编码判断与失败后纠偏回写规则，减少命令在本地环境下反复写错。Use when the task repeatedly hits Windows / PowerShell command-shape problems such as path quoting, shell-safe argument passing, UTF-8 diagnosis, or fail-then-fix recovery capture.

Proposed sections:
- PowerShell 路径与引号的稳定写法
- UTF-8 / 中文乱码的最小判断口径
- 失败后成功时，哪些经验要回写，写到哪里

Resources:
- scripts: no
- references: needed
- assets: no

## 我建议的落地方向

如果后面你要真的动手改，我建议优先是“补现有 references”，不是先改 `SKILL.md` 主体路由。

更具体地说，可以按这个顺序：

1. 把“路径 + 引号”的稳定骨架补进最接近的现有模式文件。
2. 把“UTF-8 到底怎么判断，不要一上来就猜”的判断口径补进编码相关模式文件。
3. 在 recovery checklist 里补一句，明确这类“先失败后成功”的命令修正应回写到命令模式库，而不是只留在当前对话里。

如果你要我给下一步版本，我会建议目标不是“新建 skill 草案”，而是“现有 `command-pattern-memory` 的扩展审查稿”。
