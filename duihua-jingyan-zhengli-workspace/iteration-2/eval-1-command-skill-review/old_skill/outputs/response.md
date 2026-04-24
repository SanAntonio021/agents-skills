这次更适合按“扩展现有命令类 skill”处理，不适合新建一个独立 skill。

原因很直接：你们这轮沉淀下来的不是一个新任务流，而是一组已经反复验证过的 Windows / PowerShell 命令稳定写法，核心就是三类高风险问题怎么避免再踩坑：

- 路径怎么传才不炸
- 引号怎么包才不被 PowerShell 或外部 CLI 吃掉
- UTF-8 和 Python/PowerShell 的编码边界怎么判断才不乱码

这三类内容，和 `D:\BaiduSyncdisk\.agents\agents-skills-src\command-pattern-memory\SKILL.md` 的职责是正对上的；而 `D:\BaiduSyncdisk\.agents\agents-skills-src\zhongduan-zhixing-hulan\SKILL.md` 本来就把自己定位成“静态护栏层”，长期可复用的命令形态应该沉淀到 `command-pattern-memory`，不是再拆一个新 skill。

我先给结论，再给审查稿。

## 审查结论

Candidate skill: `D:\BaiduSyncdisk\.agents\agents-skills-src\command-pattern-memory`

Decision: 更适合扩展现有 skill

Why:
- 本轮经验和现有 skill 的目标高度重合，都是“减少 Windows / PowerShell 下路径、引号、编码、外部 CLI 写错的概率”。
- 现有模式库里已经有直接承载位，不需要再发明一个新 skill 名字来装同一类东西。
- 这次经验更像“补模式”和“补 recovery capture 规则”，不是形成了一条新的独立工作流。
- 如果现在新建一个 PowerShell 路径/引号/编码专门 skill，和现有 `command-pattern-memory`、`zhongduan-zhixing-hulan` 的边界会打架，后面更难路由。

Duplicate check:
- Local overlap: 很高。`D:\BaiduSyncdisk\.agents\agents-skills-src\command-pattern-memory\references\cli-paths.md` 已覆盖路径与外部 CLI 引号骨架；`D:\BaiduSyncdisk\.agents\agents-skills-src\command-pattern-memory\references\python-utf8.md` 已覆盖 PowerShell 下 `python -c` 的 UTF-8 环境与恢复写法；`D:\BaiduSyncdisk\.agents\agents-skills-src\command-pattern-memory\references\recovery-capture-checklist.md` 已明确要求对“先失败、后成功”的高风险命令做最小回写。
- External overlap: 外部公开资料里，这类问题也主要被当成同一类 PowerShell 命令稳定性问题处理，而不是单独拆成一个新能力域。我查到的官方资料重点也是引号规则、字符编码、Python UTF-8 模式这几块基础规则；GitHub 侧没有搜到一个明显值得对标的新独立 skill 形态。这部分结论是基于公开资料后的判断，不是官方明说。

Proposed triggers:
- `PowerShell 路径老出错`
- `PowerShell 引号总炸`
- `PowerShell UTF-8 乱码`
- `Windows 命令先失败后修好了`
- `把这次命令修正沉淀一下`
- `按上次那个稳定命令形态来`

Proposed frontmatter description:
复用已验证的 Windows 和 PowerShell 命令形态，减少路径、引号、编码和外部 CLI 写错的概率。尤其用于绝对路径传参、PowerShell 与外部 CLI 的引号边界、以及 UTF-8 / Python 相关命令在 Windows 下的稳定执行与恢复回写。

Proposed sections:
- 保持 `SKILL.md` 主体不扩张，只补一句更明确的适用边界：PowerShell 路径、引号、UTF-8 判断属于优先命中场景。
- 优先更新 `D:\BaiduSyncdisk\.agents\agents-skills-src\command-pattern-memory\references\cli-paths.md`，补“绝对路径 + 引号 + 调用操作符/参数边界”的稳定骨架或 `avoid` 说明。
- 优先更新 `D:\BaiduSyncdisk\.agents\agents-skills-src\command-pattern-memory\references\python-utf8.md`，补“PowerShell 负责传路径，Python 负责读参数/环境变量，不在 inline 代码里硬塞脆弱中文路径”的稳定写法。
- 如本轮主要价值在“如何判断该回写”，再补 `D:\BaiduSyncdisk\.agents\agents-skills-src\command-pattern-memory\references\recovery-capture-checklist.md` 或 `pattern-library-maintenance.md`，而不是新开 skill。

Resources:
- scripts: 不需要
- references: 需要，且应优先落到现有 `references\` 文件
- assets: 不需要

## 更适合怎么落

这次更像“给现有 skill 补齿”，建议按下面这个口径处理：

1. 不新建 skill。
2. 把经验拆成两层：
   - 规则层继续留在 `D:\BaiduSyncdisk\.agents\agents-skills-src\zhongduan-zhixing-hulan\SKILL.md`
   - 可复用命令骨架、失败后修正出来的稳定形态，沉淀到 `D:\BaiduSyncdisk\.agents\agents-skills-src\command-pattern-memory\references\...`
3. 本轮如果最终要正式落盘，优先判断是“更新已有条目”还是“在现有 references 下新增一个很窄的条目”，不要先起新 skill。

## 这次可提炼出的经验类型

如果把这轮对话压成可复用经验，我建议只保留下面这种“能复用、能替换参数、能跨任务用”的东西：

- PowerShell 调外部 CLI 时，绝对路径、引号和 `&` 的稳定骨架
- 路径里有空格、中文、深目录时，优先走变量传参或参数位传递，不把复杂路径直接硬嵌进脆弱的一行命令
- `python -c` 或 here-string 一旦同时掺杂中文路径、中文表头、复杂引号，就要尽快切到“PowerShell 传参 / 环境变量，Python 从 `sys.argv` 或环境变量读”
- 编码问题要分清是“控制台显示层”“PowerShell 管道层”“文件读写层”“Python 解释器层”，不要混成一句“UTF-8 没开”
- 满足“先失败、后成功”的高风险命令时，应该优先回写到现有模式库，而不是只在当前对话里修完就算

## 外部依据

下面这些资料支持“这是一类现有命令稳定性问题，应补进命令模式库，而不是另起 skill”的判断：

- PowerShell 官方引号规则：`about_Quoting_Rules`
  https://learn.microsoft.com/zh-cn/powershell/module/microsoft.powershell.core/about/about_quoting_rules?view=powershell-7.5
- PowerShell 官方编码说明：`about_Character_Encoding`
  https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_character_encoding?view=powershell-7.5
- Python 官方命令行与环境变量文档，包含 `PYTHONUTF8`、`PYTHONIOENCODING`
  https://docs.python.org/3/using/cmdline.html
- PowerShell 社区关于控制台 UTF-8 边界问题的长期讨论，可作为“这不是一次性偶发坑”的旁证
  https://github.com/PowerShell/PowerShell/issues/7233

如果你要一句最短判断，就是这句：

这次不该新建 skill，应该把经验作为 `D:\BaiduSyncdisk\.agents\agents-skills-src\command-pattern-memory` 的增补审查稿处理，重点更新它现有的 `cli-paths.md`、`python-utf8.md` 和必要的 recovery 规则。
