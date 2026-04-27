这次在做：整理经验 / 判断写到哪里

结论：修改现有 skill

理由：
- 这轮经验的核心不是新增业务流程，而是把已经反复出现的 Windows / PowerShell 命令纠偏经验补进现有命令类 skill，尤其是路径、引号和 UTF-8 编码判断。
- 本地已经有高度重合的命令类 skill，主流程已覆盖“Windows 命令形态复用”和“终端护栏”，缺的是更具体的编码判断和纠偏示例，不值得再拆一个新 skill。

本地有没有类似 skill：
- 有。当前会话里已经有 `command-memory`，目标就是“复用已验证的 Windows 和 PowerShell 命令形态，减少路径、引号、编码和外部 CLI 写错的概率”。
- 还有 `terminal-safe` 负责 Windows 终端执行护栏，但它更偏通用规则层；这次经验更贴近 `command-memory` 的模式库与回写规则。
- 如果后面要正式修改，推荐修改目标是源码目录 `D:\BaiduSyncdisk\.agents\agents-skills-src\command-memory\`，不是同步产物目录 `C:\Users\SanAn\.cc-switch\skills\command-memory\`。

外面有没有类似 skill：
- 有公开生态里的相近做法，但都是通用 PowerShell / Windows pattern skill，不是你这次这类“基于对话纠偏后沉淀回本地命令模式库”的场景。
- `agent-skills.md` 上的 `xenitV1/claude-code-maestro/powershell-windows` 明确是 “PowerShell Windows patterns. Critical pitfalls, operator syntax, error handling.”：<https://agent-skills.md/skills/xenitV1/claude-code-maestro/powershell-windows>
- `SkillsMP` 上的 `powershell` skill 也明确强调 `-Encoding utf8NoBOM`、`Join-Path $PSScriptRoot`、不要假设工作目录等规则：<https://skillsmp.com/skills/dstreefkerk-claude-skills-plugins-powershell-skills-powershell-skill-md>
- 这些外部例子能证明“PowerShell 路径 / 引号 / 编码规则值得沉淀成 skill”，但不构成新建你自己 skill 的理由，反而更支持补强现有命令类 skill。

如果结论是修改现有 skill，建议这样改：
- 在 `D:\BaiduSyncdisk\.agents\agents-skills-src\command-memory\SKILL.md` 的“何时使用”或“流程”里，单列一条“遇到 UTF-8 / BOM / PowerShell 5.1 与 7+ 编码差异时，必须先判断再写文件”的触发与分诊规则。
- 在 `D:\BaiduSyncdisk\.agents\agents-skills-src\command-memory\references\` 里补一组专门的 Windows 命令模式，至少覆盖：绝对路径 + `-LiteralPath`、单引号/双引号选择、`Get-Content` / `Set-Content` / `Out-File` 的 UTF-8 明示写法、读取前先做存在性检查。
- 把“先失败、后成功”的典型纠偏例子补进去，明确哪些内容该作为命令骨架沉淀，哪些只属于一次性任务上下文，避免把失败日志原样堆进模式库。
- 在 `command-memory` 与 `terminal-safe` 的分工上再写清一层：前者负责可复用命令骨架和纠偏记忆，后者负责执行前的静态护栏，避免以后同类经验落点混乱。

审查稿：
- skill 名称：`command-memory`
- description：复用已验证的 Windows 和 PowerShell 命令形态，重点覆盖路径、引号、编码判断和外部 CLI 调用，减少在 `shell_command` 中重复踩坑。
- 什么时候该触发：路径包含空格/中文/深层目录；PowerShell 命令第一次失败后需要改写形态；涉及 `Get-Content`、`Set-Content`、`Out-File`、压缩解压、搜索、外部 CLI；出现 PS5.1 与 PS7+ 编码差异风险时。
- 预期输出：先定位当前问题属于路径、引号、编码还是 shell 混用；再给出已经验证过的命令骨架；必要时指出应该回退到 `terminal-safe` 的哪条静态护栏。
- 拟议结构：触发与分诊 / 已验证命令骨架 / UTF-8 与编码判断 / 回写规则与边界
- scripts / references / assets：不需要新增 `scripts/` 或 `assets/`；建议补 `references/`，把编码判断、路径引号和外部 CLI 模式拆成独立参考页
- 建议测试提示：
  - “刚才这条 PowerShell 命令因为路径里有空格失败了，按已经验证过的方式帮我重写，不要换 shell。”
  - “这个文件读出来像乱码，帮我先判断是不是编码问题，再给我稳妥的 PowerShell 读写方式。”
  - “我在 Windows 下要调用外部 CLI 处理一个中文路径文件，先按现有命令模式库给我最稳的命令骨架。”
