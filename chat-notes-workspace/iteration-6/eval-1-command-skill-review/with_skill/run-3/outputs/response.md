这次在做：整理经验，判断该写到哪里

结论：修改现有 skill

理由：
- 这轮经验的主轴不是新业务流程，而是已经反复验证过的 PowerShell 路径、引号和 UTF-8 编码判断，明显属于命令执行纠偏。
- 本地已经有高重合入口，主流程已经被覆盖，缺的是更细的边界、回写条件和例子，不需要再另起一个新 skill。

本地有没有类似 skill：
- 有，最贴近的是 `D:\BaiduSyncdisk\.agents\agents-skills-src\command-memory\`。它本来就负责复用已验证的 Windows 和 PowerShell 命令形态，目标正好覆盖路径、引号、编码这类稳定纠偏经验。
- 旁边还有 `D:\BaiduSyncdisk\.agents\agents-skills-src\terminal-safe\`，但它更偏静态护栏，不是这次最该承接经验的主入口。

外面有没有类似 skill：
- 公开生态里能看到 Anthropic 的通用 skills 仓库和 `skill-creator`、`find-skills` 这类基础能力，可作为写法和治理参考。
- 但我没看到一个比你本地 `command-memory` 更贴近“PowerShell 路径 / 引号 / UTF-8 纠偏回写”的现成公开 skill，所以这次没必要因为外面没有完全同类就新建。

建议修改的源码目标：
- 推荐修改 `D:\BaiduSyncdisk\.agents\agents-skills-src\command-memory\`
- 不推荐把 `C:\Users\SanAn\.cc-switch\skills\command-memory\` 当正式修改目标；那边是同步产物，不是源码主入口。

如果结论是修改现有 skill，建议这样改：
- 在 `SKILL.md` 里把“编码判断”单独写成一条高频触发条件，明确什么时候要先判断文件编码、什么时候默认 UTF-8 即可。
- 在 `references/` 里补一段 PowerShell 常见命令骨架，专门覆盖带空格路径、单引号/双引号选择、`Get-Content -Encoding UTF8`、`Set-Content -Encoding UTF8` 这类稳定写法。
- 补一条“先失败、后成功才回写”的例子，说明只沉淀成功后的命令骨架，不把整段历史命令和失败噪音一起塞进去。
- 在与 `terminal-safe` 的分工上再写清一点：命令骨架进 `command-memory`，通用执行护栏仍留在 `terminal-safe`。

审查稿：
- skill 名称：`command-memory`
- description：复用已验证的 Windows 和 PowerShell 命令骨架，重点减少路径、引号、编码和外部 CLI 调用时的重复出错；当用户在修 Windows 命令、路径写法、编码判断或重复命令形态失败时都应触发。
- 什么时候该触发：PowerShell 路径带空格或中文；需要判断文本编码；同类命令刚失败过一次并已出现修正线索；用户明确要求按之前验证过的命令形态执行。
- 预期输出：给出可直接复用的命令骨架、适用条件、替换占位符方式，以及是否值得回写进模式库的判断。
- 拟议结构：触发判断 / 命令骨架选择 / 编码判断规则 / 回写条件与边界
- scripts / references / assets：优先补 `references/`，暂时不需要 `assets/`；只有当编码判断需要稳定脚本化检查时再补 `scripts/`
- 建议测试提示：`刚才这条 PowerShell 命令因为路径里有空格炸了，按上次正确的写法帮我重组一下` / `这个规则文件读出来像乱码，先判断编码再给我稳妥的读取命令` / `我们刚修好一条带 UTF-8 编码的 PowerShell 命令，看看值不值得回写进现有命令 skill`
