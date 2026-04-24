# 这次在做

整理这轮对话里的可复用经验，并判断这些经验更适合写到哪里。

## 结论

这次更适合 **修改现有 skill**，目标是：

`C:\Users\SanAn\.cc-switch\skills\command-pattern-memory\SKILL.md`

而不是新建一个新 skill，也不是只写在当前项目里。

## 为什么我会这样判断

- 这轮反复修的核心问题，正好就是 `command-pattern-memory` 已经负责的范围：Windows / PowerShell 下的 **路径、引号、编码、命令骨架复用**。
- 本地现有模式库已经明确给了这些入口，不是空白领域：
  - `C:\Users\SanAn\.cc-switch\skills\command-pattern-memory\references\cli-paths.md`
  - `C:\Users\SanAn\.cc-switch\skills\command-pattern-memory\references\python-utf8.md`
  - `C:\Users\SanAn\.cc-switch\skills\command-pattern-memory\references\markdown-read-utf8.md`
- 这说明主流程已经有了，缺的是“把这次踩坑后的更稳写法补进去”，不是另起炉灶。
- 这些经验离开当前项目也成立，明显能跨任务复用，所以也不该只记在项目文档里。

## 本地有没有类似 skill

- 有，最贴近的是：
  `C:\Users\SanAn\.cc-switch\skills\command-pattern-memory\SKILL.md`
- 它的定位就是“复用已验证的 Windows 和 PowerShell 命令形态，减少路径、引号、编码写错的概率”。
- 而且它自己的索引文件
  `C:\Users\SanAn\.cc-switch\skills\command-pattern-memory\references\validated-command-patterns.md`
  已经把这次相关主题单独列出来了。

## 外面有没有类似做法

- 有，但大多也是“更大的 Windows / PowerShell 经验包”，不是把“路径 + 引号 + UTF-8”拆成一个独立 skill。
- 我查到的公开参考里，更接近“把这些问题当成 PowerShell 命令规范来处理”：
  - Microsoft Learn 的 [about_Character_Encoding](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_character_encoding?view=powershell-7.5)
  - Microsoft Learn 的 [about_Quoting_Rules](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_quoting_rules?view=powershell-7.5)
  - Microsoft Learn 的 [about_Parsing](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_parsing?view=powershell-7.4&viewFallbackFrom=powershell-7.2)
  - skills.sh 上更宽泛的 PowerShell 技能，如 [powershell-5.1-expert](https://skills.sh/404kidwiz/claude-supercode-skills/powershell-5.1-expert) 和 [admin-windows](https://skills.sh/smithery/ai/admin-windows)
- 这些外部材料都在说明一件事：这类问题通常应该沉淀为 **命令执行规则 / 模式库**，而不是单独再造一个新 skill。

## 建议怎么处理

先不改文件的话，我建议把这次定性为：

**“给现有 `command-pattern-memory` 做一次补强审查，后续再决定是否正式回写。”**

最适合补的不是整个 `SKILL.md` 主体，而是下面几类内容：

- 在 `C:\Users\SanAn\.cc-switch\skills\command-pattern-memory\SKILL.md` 里补一条更明确的触发提醒：
  只要出现 PowerShell 中文路径、深路径、引号嵌套、UTF-8 读写判断，就优先进入这个 skill。
- 在 `C:\Users\SanAn\.cc-switch\skills\command-pattern-memory\references\cli-paths.md` 补“绝对路径 + `-LiteralPath` + 外部 CLI 调用骨架”的边界提醒。
- 在 `C:\Users\SanAn\.cc-switch\skills\command-pattern-memory\references\markdown-read-utf8.md` 补“先判断是不是编码问题，再决定是不是文件坏了”的检查顺序。
- 在 `C:\Users\SanAn\.cc-switch\skills\command-pattern-memory\references\python-utf8.md` 补“什么时候该继续用 inline Python，什么时候应该立刻切成 UTF-8 `.py` 文件”的分界线。

## 审查稿

- skill 名称：`command-pattern-memory`
- 处理类型：修改现有 skill
- 本次目标：把这轮对话里已经验证过的 PowerShell 路径、引号和 UTF-8 判断经验，补成更容易复用的规则与例子

### 建议补充的规则

- 规则 1：**先分清“路径问题、引号问题、编码问题”是哪一类，再动命令。**
  不要一上来同时改三样，不然很难知道到底是哪一步救活了命令。
- 规则 2：**只要路径里可能有空格、中文、深目录，默认走绝对路径 + `-LiteralPath`。**
  这样能少掉很多“其实文件在，但 PowerShell 解释错了”的误判。
- 规则 3：**只要输出要被上层抓取，默认同时考虑“文件编码”和“控制台输出编码”。**
  很多时候不是文件坏了，而是“读的时候没指定 UTF-8”或“终端输出不是 UTF-8”。
- 规则 4：**PowerShell 里如果 inline Python 已经开始脆弱，就不要硬撑，改成 UTF-8 脚本文件。**
  尤其是代码里同时有中文、反斜杠、引号、长字符串时，继续塞进一行命令里只会越来越不稳。
- 规则 5：**沉淀的是“成功后的命令骨架”，不是整段任务日志。**
  只保留可复用形态，不带具体项目私有路径。

### 建议补充的例子

- 例子 1：读取中文 Markdown
  从“裸 `Get-Content`”升级到“`[Console]::OutputEncoding = UTF8` + `Get-Content -LiteralPath ... -Encoding UTF8 -Raw`”。
- 例子 2：调用外部 CLI
  从“未加 `&`、路径没包好”升级到“`& "<TOOL>" "<INPUT_PATH>"`”这种稳定骨架。
- 例子 3：PowerShell 里跑 Python
  从“直接 `python -c` 硬塞中文和路径”升级到“先设 UTF-8 环境变量；再判断是否该改成 `.py` 文件执行”。
- 例子 4：编码排查顺序
  先确认文件本身编码，再确认 `Get-Content` 的 `-Encoding`，最后确认 PowerShell 输出编码，不要把乱码直接当成文件损坏。

### 建议放到哪一节

- `SKILL.md`
  补“何时触发”和“何时从普通命令构造切换到模式库”的提醒。
- `references\cli-paths.md`
  补路径和引号的稳定骨架。
- `references\markdown-read-utf8.md`
  补读取 UTF-8 文本时的判断顺序。
- `references\python-utf8.md`
  补 inline Python 与脚本文件之间的切换条件。

### 预期输出

- 让后续同类任务少走弯路。
- 看到乱码时，先想到“编码链路”，不是直接怀疑文件坏了。
- 看到中文路径和复杂引号时，优先套已验证骨架，而不是临场拼命令。

### scripts / references / assets

- `scripts`：这次不一定需要新增。
- `references`：需要，且应优先补进现有参考文件。
- `assets`：不需要。

### 建议测试提示

- “帮我在 PowerShell 里读取一个中文路径下的 Markdown，先判断是不是 UTF-8 编码问题。”
- “这条 Windows 命令因为路径里有空格和中文失败了，按稳定骨架重写。”
- “我想在 PowerShell 里跑一段带中文路径的 `python -c`，你先判断该不该改成脚本文件。”

## 一句话总结

这次最合适的处理方式不是新建 skill，而是把经验作为一次 **现有命令类 skill 的补强审查**：主 skill 不用大改，重点补规则、边界和例子到现有的命令模式库里。
