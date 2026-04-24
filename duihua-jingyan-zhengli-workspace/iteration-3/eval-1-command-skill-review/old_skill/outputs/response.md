# 这次更适合怎么处理

这次更适合**扩展现有的命令类 skill**，不适合单独再新建一个“PowerShell 路径 / 引号 / UTF-8” skill。

原因很直接：

- 你们这轮沉淀下来的经验，核心不是一个新任务类型，而是**Windows / PowerShell 命令在执行层怎么写才稳**。
- 现有 `command-pattern-memory` 已经明确覆盖这类问题，描述里就直接写了：`Windows`、`PowerShell`、`path handling`、`encoding`。
- 这个 skill 下面也已经有现成承载位：
  - `cli-paths.md`：放路径和引号骨架
  - `markdown-read-utf8.md`：放 PowerShell 读 UTF-8 文本
  - `python-utf8.md`：放 PowerShell 下 Python 和 UTF-8 的组合
  - `recovery-capture-checklist.md`：专门处理“先失败、后成功”的命令纠偏回写

所以，这次最合适的处理方式不是“再起一个新 skill 名字”，而是：

1. 把这轮经验按问题类型拆开。
2. 分别补进 `command-pattern-memory` 现有的对应 reference。
3. 如果现有 reference 放不下，再考虑在这个 skill 下面新增一个更窄的 reference 文件，而不是新建平级 skill。

# 审查稿

**Candidate skill:** `command-pattern-memory`（扩展现有 skill，不新建）

**Decision:** 更适合扩展现有 skill

**Why:**

- 本轮经验是“命令构造与纠偏规则”，不是独立的新工作流。
- 现有 skill 已覆盖主流程，只缺更细的 PowerShell 路径、引号、UTF-8 判断细则。
- 这类经验天然应该跟“已验证命令骨架”放在一起，后续复用成本最低。

**Duplicate check:**

- Local overlap: 已存在 `C:\Users\SanAn\.cc-switch\skills\command-pattern-memory\SKILL.md`，且其 `references/validated-command-patterns.md` 已把“路径引号”“UTF-8 读取”“Python UTF-8”“失败后回写”都列为承载位。
- External overlap: 没看到值得单独拆成一门独立 skill 的公开稳定范式；公开资料里，这类问题更多被当作**命令执行可靠性**问题处理，而不是新 skill 类型。
  - 参考：[openai/codex issue #9581](https://github.com/openai/codex/issues/9581)
  - 参考：[PowerShell issue #24037](https://github.com/PowerShell/PowerShell/issues/24037)

**Proposed triggers:**

- `PowerShell 路径老出错`
- `PowerShell 引号又炸了`
- `UTF-8 编码判断`
- `按上次那个稳定命令形态来`
- `先失败后成功的命令回写`

**Proposed frontmatter description:**

复用已验证的 Windows 和 PowerShell 命令形态，减少路径、引号、编码和外部 CLI 写错的概率。特别适用于绝对路径、中文路径、UTF-8 文本读取、PowerShell 内联 Python，以及“先失败后成功”的命令纠偏回写场景。

**Proposed sections:**

- 何时判定这是“命令形态问题”而不是业务问题
- PowerShell 路径、引号、`-LiteralPath` 的稳定写法
- UTF-8 判断与读取的最小闭环
- PowerShell 下内联 Python 的编码与传参边界
- “先失败、后成功”后的最小回写规则

**Resources:**

- scripts: 暂不需要
- references: 需要，优先增补现有 `references/` 文件
- assets: 不需要

# 一句话判断

这次最好的做法是：**不新建 skill，直接把经验并回现有 `command-pattern-memory` 的 references。**
