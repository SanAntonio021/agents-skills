这次在做：整理经验 / 判断写到哪里

结论：更适合修改现有 skill，不适合新建 skill。

理由：
- 这轮对话里反复修的是 PowerShell 命令形态问题，不是一个全新的工作流。核心都是“路径怎么写更稳、引号怎么包不炸、什么时候要显式按 UTF-8 处理”。
- 本地现有 skill `D:\BaiduSyncdisk\.agents\agents-skills-src\command-pattern-memory\` 已经覆盖了这类场景，而且它下面已经有对应参考文件：`cli-paths.md`、`python-utf8.md`、`markdown-read-utf8.md`。
- 真正缺的不是新 skill，而是把这次“先失败、后修正、最后稳定”的经验补成更明确的模式和例子，方便下次直接复用。
- 如果现在另起一个新 skill，边界会和 `command-pattern-memory` 重叠，后面更容易分散、重复、维护不稳。

本地有没有类似 skill：
- 有。最贴近的是 `D:\BaiduSyncdisk\.agents\agents-skills-src\command-pattern-memory\`。
- 它的定位本来就是“复用已验证的 Windows 和 PowerShell 命令形态”，而你这次整理的经验正好就是这个范围。
- 结合本地已安装镜像看，它已经把相关问题拆进了参考文件：
  - 路径与引号：`C:\Users\SanAn\.cc-switch\skills\command-pattern-memory\references\cli-paths.md`
  - `python -c` 和 UTF-8：`C:\Users\SanAn\.cc-switch\skills\command-pattern-memory\references\python-utf8.md`
  - 读取中文 Markdown / 文本：`C:\Users\SanAn\.cc-switch\skills\command-pattern-memory\references\markdown-read-utf8.md`

外面有没有类似 skill：
- 有相近的，但不够贴合。
- `powershell-windows`：更像通用 PowerShell 书写注意事项，能提供背景参考，但不是“把验证过的命令骨架沉淀成模式库”的路线。
  参考：[skills.sh 上的 powershell-windows](https://skills.sh/davila7/claude-code-templates/powershell-windows)
- `powershell-5.1-expert`：更偏 Windows PowerShell 5.1 专家知识，也不是你这次这种命令纠偏记忆库。
  参考：[skills.sh 上的 powershell-5.1-expert](https://skills.sh/404kidwiz/claude-supercode-skills/powershell-5.1-expert)

更适合怎么处理：
- 不新建 skill。
- 也不建议先往 `SKILL.md` 主体里堆很多细节，因为这个 skill 现在的设计就是“主文件只做路由和边界，细节放 references”。
- 更合适的做法是：后续如果要正式改，就优先改 `D:\BaiduSyncdisk\.agents\agents-skills-src\command-pattern-memory\references\` 下面最贴近的模式文件，把这轮经验补成更清晰的“何时用、怎么写、不要怎么写、成功信号、何时回写”。

最该先做的一步：
- 先把这轮经验拆成 3 组，再决定分别补到哪个 reference 文件：
  - PowerShell 路径和引号骨架
  - `python -c` / here-string 的 UTF-8 与中文路径处理
  - “第一次读文件乱码后，如何判断并切换到显式 UTF-8”的判断规则

审查稿：
- skill 名称：`command-pattern-memory`
- 推荐修改的源码目录：`D:\BaiduSyncdisk\.agents\agents-skills-src\command-pattern-memory\`
- 结论类型：修改现有 skill
- description 审查建议：
  - 复用已验证的 Windows 和 PowerShell 命令骨架，重点覆盖路径、引号、编码、搜索遍历和外部 CLI 调用，减少在真实工作区里反复踩同一类命令形态坑。
- 什么时候该触发：
  - 路径里可能有空格、中文、深目录
  - PowerShell 下需要调用外部 CLI 或 `python -c`
  - 已经出现一次命令失败，后来通过改路径写法、引号写法或 UTF-8 设置修好了
  - 需要把这次修好的命令形态沉淀成下次可复用的稳定骨架
- 预期输出：
  - 给出最小可复用命令骨架
  - 说明前置检查项
  - 点明哪些写法不要再用
  - 当这次属于“先失败后成功”时，提醒回写到最近的 reference 文件
- 拟议结构：
  - `SKILL.md` 继续只保留路由、边界、回写规则
  - 把新增经验优先补进 `references\cli-paths.md`
  - 把 UTF-8 判断和 `python -c` 经验补进 `references\python-utf8.md`
  - 把中文 Markdown / 文本读取经验补进 `references\markdown-read-utf8.md`
  - 如果这轮对话里“失败后如何收口并回写”的动作很典型，再补 `references\recovery-capture-checklist.md`
- scripts / references / assets：
  - `scripts`：这次看起来不需要新增
  - `references`：需要，是这次最主要的落点
  - `assets`：不需要
- 建议测试提示：
  - “帮我在 PowerShell 里调用一个绝对路径的 Windows CLI，输入输出路径都带空格和中文，先给我稳定命令骨架。”
  - “我需要在 PowerShell 里跑 `python -c` 读取一个中文路径下的文件并输出中文，按不容易乱码的方式写。”
  - “刚才 `Get-Content` 读中文 Markdown 出现乱码，帮我按稳定方式重写命令，并告诉我这次经验该回写到哪个 reference 文件。”

一句话判断：
- 这次不是“要不要做新 skill”的问题，而是“把现有命令类 skill 的 reference 层补得更像实战记忆库”。
