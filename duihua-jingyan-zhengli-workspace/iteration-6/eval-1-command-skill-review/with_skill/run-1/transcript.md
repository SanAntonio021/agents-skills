# Eval prompt

你负责 D:\BaiduSyncdisk\.agents\agents-skills-src\duihua-jingyan-zhengli-workspace\iteration-6\eval-1-command-skill-review\with_skill\run-1\ 的写入。你不是一个人在代码库里工作，不要改动任何源码，也不要回退别人的改动。任务：这是一次 dry-run 评测，请读取当前 skill：D:\BaiduSyncdisk\.agents\agents-skills-src\duihua-jingyan-zhengli\SKILL.md ，按这份 skill 的要求回答下面的用户提示，但不要真的修改文件、执行 git 提交或推送。用户提示：帮我把这轮对话整理一下。我们刚才一直在修 PowerShell 路径、引号和 UTF-8 编码判断，这些经验看起来更像该写进现有的命令类 skill。先别改文件，先告诉我这次更适合怎么处理，并给我一个审查稿。把最终用户可见答复保存到 D:\BaiduSyncdisk\.agents\agents-skills-src\duihua-jingyan-zhengli-workspace\iteration-6\eval-1-command-skill-review\with_skill\run-1\outputs\response.md 。再把一份简短 transcript 保存到 D:\BaiduSyncdisk\.agents\agents-skills-src\duihua-jingyan-zhengli-workspace\iteration-6\eval-1-command-skill-review\with_skill\run-1\transcript.md ，格式仿照评测目录里现有 transcript：包含 Eval prompt 和 Final response。最终请只汇报你写了哪些文件。

# Final response

这次在做：整理经验 / 判断写到哪里

结论：修改现有 skill

这次更适合补到现有命令类 skill，不适合单独新建，也不该只留在当前项目笔记里。

推荐正式修改目标：

`D:\BaiduSyncdisk\.agents\agents-skills-src\command-pattern-memory\`

当前加载来源：

`C:\Users\SanAn\.cc-switch\skills\command-pattern-memory\`

理由：

- 你这轮沉淀出来的核心经验，就是 Windows / PowerShell 命令形态纠偏：路径、引号、UTF-8 判断。这正好命中 `command-pattern-memory` 的主职责。
- 这些经验离开当前评测目录也成立，换一个 Windows 工作区、换一条 PowerShell 命令，还是会遇到同类坑，所以不该只写在当前项目里。
- 现有 skill 已经覆盖主流程，缺的是更具体的规则、边界和例子，不缺一个全新的 skill 壳子。
- 这次又是 dry-run，用户已经明确说“先别改文件”，所以现在最合适的产物就是审查稿，不是正式改动。

本地有没有类似 skill：

- 有，而且高度重合：`C:\Users\SanAn\.cc-switch\skills\command-pattern-memory\SKILL.md`
- 如果后面要正式改，应该改源码目录，不改同步产物：`D:\BaiduSyncdisk\.agents\agents-skills-src\command-pattern-memory\SKILL.md`
- 这个 skill 现有 references 已经有直接承载位：
  `D:\BaiduSyncdisk\.agents\agents-skills-src\command-pattern-memory\references\cli-paths.md`
  `D:\BaiduSyncdisk\.agents\agents-skills-src\command-pattern-memory\references\markdown-read-utf8.md`
  `D:\BaiduSyncdisk\.agents\agents-skills-src\command-pattern-memory\references\python-utf8.md`
  `D:\BaiduSyncdisk\.agents\agents-skills-src\command-pattern-memory\references\recovery-capture-checklist.md`

外面有没有类似 skill：

- 有相近做法，但更像补充参考，不是比你本地 skill 更合适的主入口。
- 公开生态里能找到一个偏 PowerShell 通用坑位清单的 skill：[`powershell-windows`](https://skills.sh/davila7/claude-code-templates/powershell-windows)。它覆盖了路径规则、ASCII/编码注意点等，但更偏通用规则清单。
- 还能找到一个偏 shell 防御式写法的 skill：[`bash-defensive-patterns`](https://skills.sh/wshobson/agents/bash-defensive-patterns)。它证明“命令易错点沉淀成 skill”这条路是成立的，但它是 Bash，不是你这次要补的 PowerShell 命令模式。
- 所以外部情况更支持这个判断：不用新建同类 skill，继续把经验沉淀进现有命令类 skill 就对了。

如果结论是修改现有 skill，建议这样改：

- 在 `D:\BaiduSyncdisk\.agents\agents-skills-src\command-pattern-memory\references\cli-paths.md` 补一条更直接的 PowerShell 调用骨架：
  外部程序路径只要带空格、中文或深目录，优先固定成 `& "<TOOL>" ...` 这种形态，不要在裸路径、变量插值和多层引号之间来回混用。
- 在 `D:\BaiduSyncdisk\.agents\agents-skills-src\command-pattern-memory\references\markdown-read-utf8.md` 补一条判断顺序：
  先区分“读取阶段乱码”还是“文件本体不是 UTF-8”，不要一看到乱码就直接归因到文件编码。
- 在 `D:\BaiduSyncdisk\.agents\agents-skills-src\command-pattern-memory\references\python-utf8.md` 补一条边界：
  如果已经证明问题在 PowerShell 传参、输出或终端显示层，就不要先怪 Python 文件内容编码。
- 在 `D:\BaiduSyncdisk\.agents\agents-skills-src\command-pattern-memory\references\recovery-capture-checklist.md` 补一条强制回写触发条件：
  同一线程里出现“先失败，后因改路径 / 引号 / 编码判断而成功”，默认要整理成最小可复用模式。

审查稿：

- skill 名称：`command-pattern-memory`
- description：复用已验证的 Windows 和 PowerShell 命令形态，重点沉淀路径、引号、编码判断，以及失败后纠偏得到的稳定写法，减少同类命令在后续任务里反复踩坑。
- 什么时候该触发：
  1. 任务要在 Windows / PowerShell 下执行命令。
  2. 路径包含空格、中文或很深的目录。
  3. 命令涉及外部 CLI、文本读取、编码判断或 Python 相关调用。
  4. 当前线程刚出现过一次命令失败，后来通过改写命令形态而成功。
- 预期输出：
  1. 先选最接近的已验证命令骨架。
  2. 明确这次该用的路径、引号和编码判断写法。
  3. 如果这次属于高价值纠偏，指出应该回写到哪个 reference 文件。
- 拟议结构：
  `SKILL.md` 继续只负责分诊和边界。
  `references/cli-paths.md` 补 PowerShell 路径调用骨架。
  `references/markdown-read-utf8.md` 补 UTF-8 读取与误判区分。
  `references/python-utf8.md` 补 PowerShell 层和 Python 文件本体的边界。
  `references/recovery-capture-checklist.md` 补 fail-then-fix 的回写触发条件。
- scripts / references / assets：
  不需要新增 `scripts/` 或 `assets/`。
  这次更适合只补 `references/` 里的规则和例子。
- 建议测试提示：
  1. “帮我在 PowerShell 里调用一个带空格和中文路径的 exe，别再把引号写炸了。”
  2. “这个 Markdown 看起来像 UTF-8，但我在 PowerShell 里读出来是乱码。先帮我判断问题出在读取还是文件本身。”
  3. “刚才那条 PowerShell 命令第一次失败，后来改了路径和引号就成功了。把这次经验整理成对现有命令 skill 的审查稿。”

这次不建议新建 skill。最直接的处理就是：把这轮对话提炼成几条可复用规则，作为对 `D:\BaiduSyncdisk\.agents\agents-skills-src\command-pattern-memory\` 的一次审查稿，等你批准后再正式改源码目录。
