# 正式修改 skill 后的收尾

如果这次已经按全局规则定位，并正式创建或修改了本机 skill 源码：

1. 先按当前可用的 `skill-creator` 对照检查名称、description、触发场景、预期输出和主体结构。
2. 检查 `evals/evals.json`、测试提示、打分预期、汇总说明是否需要补齐。
3. 如果一对照发现还没对上，先补 `SKILL.md` 和 `evals/evals.json`，再检查一遍。
4. 如果 `references/`、`scripts/` 或其他会被运行时读取的子文件修改了技能行为，必须同步在
   `SKILL.md` 写入对应的语义入口或约束。不能用空格、注释、无意义版本号等伪改动触发更新。
   只改 eval、测试数据或不影响运行行为的说明时，不为此制造 `SKILL.md` 改动。
5. 受限于当前环境或用户没有要求时，可以不跑完整子 agent 评测，但不得把未跑写成通过；评测不完整或失败会影响发布判断时，按 `report-format.md` 作为验证异常集中留档。
6. `skill-creator` 对照仍是内部必做检查：检查 `name`、`description`、触发场景、主体结构和 `evals`。正常成功不在最终汇报中强制单列“skill-creator 对照结论”；只有不符合、未完整评测或其他结果会影响发布判断时，才在中央异常报告中说明，并在聊天保留一句直白结论和必要动作。
7. 如果用户没有明确说不要提交或不要推送，先对每个拟提交文件运行
   `git -C "<文件所在目录>" rev-parse --show-toplevel`，按实际 Git 根目录分别检查分支、remote、
   `HEAD`、目标远端分支和工作区状态。父目录包含内层仓库时，不能凭当前工作目录判断文件归属。
8. 本机 `D:\BaiduSyncdisk\.agents\skills\` 是独立的 `agents-skills` 仓库；公开 skill 源码只从该仓库
   提交和推送。父目录 `D:\BaiduSyncdisk\.agents\` 属于 `agents-config`，不得从父仓库暂存或发布
   `skills/`。同一次收尾涉及多个仓库时，逐仓库确认范围并分别提交，不能把一次批准扩展到另一仓库。
9. 如果父仓库仍历史性跟踪内层仓库路径，停止从父仓库发布这些路径，保留本地文件，并把取消父仓库
   跟踪列为需要单独批准的边界修复。如果目标仓库本地分支与远端分叉，或本地历史包含未授权提交，
   不 merge、rebase、reset 或直接 push；在用户已批准发布范围时，从当前远端目标分支建立隔离提交，
   推送前用提交差异确认只含本次文件，并确认未授权提交不是远端祖先。
10. 只处理本次相关改动，不把无关文件一起提交或推送。提交前后都要复核其他仓库的 `HEAD`、工作区
   状态和本地文件，防止嵌套仓库操作改变另一仓库内容。

### 并行任务共享同一仓库的隔离发布

两个任务即使修改不同路径，只要在同一个 Git worktree 中运行，仍会共用同一个 index 和提交状态。
一个任务暂存的文件可能被另一个任务的提交带走；路径不重叠不能证明提交相互隔离。

1. 在第一次 Git 写操作前解析每个批准文件的真实仓库根，并记录 `HEAD`、当前分支、暂存文件清单和
   `git status --short`。只有当前任务列表、对话、进程或 Git 状态能够把另一个写入者定位到同一仓库时，
   才按并发写入处理；不能因为系统里还有其他任务就一律扩大隔离范围。
2. 已知另一个任务可能写入同一仓库，或出现 `COMMIT_EDITMSG` / index 占用、未经本任务操作的
   `HEAD` 变化、暂存文件增删、目标文件被意外提交等任一信号时，立即停止在共享 worktree 中执行
   `git add`、`git commit`、`commit-tree` 或 ref 更新。不得删除锁文件、清空或复用暂存区、停止未知
   进程，也不得用 `stash`、`reset`、`checkout`、`restore` 掩盖状态变化；共享暂存区从此只作证据，
   不能再作为本次提交来源。
3. 先向已知并行任务说明准确仓库和路径边界；若对方正在执行 Git 写操作，等该次操作结束，不抢锁。
   随后只读取得远端目标分支的唯一 40 位提交，从该固定基线创建本任务专用的 detached worktree。
   只在隔离 worktree 重建已批准内容，不复制共享 worktree 的 index、未批准文件或未知中间状态。
4. 在隔离 worktree 检查完整暂存差异、`diff --cached --check`、候选提交父提交和文件集合。推送前再次
   只读核对远端 tip 仍等于固定基线；变化时停止，不 rebase、merge、force push 或静默吸收并行提交。
   推送只能把已核实的候选提交快进到准确目标分支。
5. 本任务不得修改、清理或还原原共享 worktree。原工作区后来出现的变化按其他任务所有处理；变化若与
   本次批准路径重叠，或使远端基线失效，当前发布停止并按 `report-format.md` 留档。
6. 候选提交推送成功且范围复核通过后，才移除本任务 worktree。后续生产同步仍使用第 13 条规定的权威
   源码根，不把隔离副本改作 `SourceRoot`。

### 同文件混合改动的隔离发布

批准内容与其他任务的未批准内容落在同一文件时，按文件路径执行 `git add` 会越过授权边界。这类情况
不能当作普通脏工作区处理，也不能因为最终文件“看起来正确”就把整份文件提交。

1. 先保存原仓库的 `HEAD`、当前分支、目标远端分支、暂存区文件清单和工作区状态。逐项对照审查稿，
   明确每个批准改动的内容边界；无法从对话、原始差异或批准稿中准确重建时停止，不靠猜测拆分。
2. 禁止在原工作区整文件暂存目标路径，也不使用 `stash`、`reset`、`checkout`、`restore`、覆盖文件或
   清空暂存区来制造“干净状态”。原工作区已有的未批准内容和暂存状态必须保持不变。
3. `fetch` 后把目标远端分支解析为固定的 40 位基线提交，从该提交创建临时 worktree。目标分支已在
   主工作区检出时使用 detached worktree，不尝试把同一分支再次检出；临时目录及其恢复方式要在
   操作前记录。
4. 只在隔离 worktree 中重建批准内容并运行对应验证。随后让 Git 从固定基线和隔离副本自动生成精确
   patch；不要手写 hunk 行数。先运行 `git apply --cached --check`，通过后才写入隔离 worktree 的
   index。手工 patch 因 `corrupt patch`、`patch fragment without header` 或 hunk 计数错误失败后，
   不继续修补行数，直接回到隔离副本重新生成。
5. 提交前检查 `git diff --cached --name-status`、`git diff --cached --check` 和完整暂存差异，确认只含
   批准路径与批准内容；再检查原仓库的 `HEAD`、工作区和暂存区与步骤 1 一致。任一项不一致都停止，
   不提交、不推送。
6. 在隔离 worktree 创建候选提交后，用 `git diff-tree` 复核文件集合与内容。推送前重新 `fetch`；目标
   远端分支不再等于固定基线时停止，不 rebase、不 force push，也不把新远端内容静默并入本次批准。
7. 只有提交和 push 成功且原工作区复核通过后，才移除临时 worktree 和 patch。中途失败时保留隔离
   路径、基线 SHA 和恢复说明，按 `report-format.md` 记录异常。具体 Windows/PowerShell 命令骨架见
   `command-memory/references/git-on-windows.md` 的同文件混合改动模式。

11. Skill push 成功后，取得 40 位远端提交 SHA，并从提交差异中列出本次实际修改且仍存在的 Skill。
    请求集合必须与提交中的 Skill 集合完全一致，不能顺手加入未修改的 Skill；删除或合并后源码目录已消失的
    Skill 不进入自动更新，继续按第 18 条处理；新旧 Skill 名称不同的替换按下方“不同名称 Skill 的受控替换”处理。
12. 调用同步 helper 前重新读取本地 `HEAD` 和远端当前分支。若并发任务已提交并推送，使本次发布提交不再是
    当前 `HEAD`，不要把 `ExpectedRemoteCommit` 换成新的 `HEAD`，也不要 reset、rebase 或重新提交。本次提交只有在
    同时满足以下条件时才可继续：它是本地当前 `HEAD` 和远端当前分支的共同祖先；本次批准发布范围只由该单个
    提交构成；该提交实际修改的 Skill 集合与本次请求完全一致。满足时固定使用本次原始 40 位 SHA，并给 helper 增加
    `-AllowHistoricalCommit`；历史提交模式不能同时使用 `-ExpectedBaseCommit`，发布源仍是该提交中的 Git blob。
13. 同文件混合改动或分叉隔离发布使用 detached worktree 时，生产 helper 的权威源码根仍是
    `D:\BaiduSyncdisk\.agents\skills`，不得把隔离 worktree 或其他副本改作 `SourceRoot`。如果发布提交已经推送，
    远端 tip 仍精确等于本次批准的发布提交，而权威 checkout 的目标分支落后，可在以下条件全部成立时做一次受控
    快进：权威 checkout 正检出目标分支；其 `HEAD` 是远端 tip 的祖先；全仓库 tracked 和 staged 状态为空；先记录
    完整 untracked 路径集合，并确认它们与 `HEAD..远端 tip` 的变更路径不存在同路径或祖先/后代重叠。随后只允许
    `git merge --ff-only <已核实的远端引用>`；完成后必须确认本地 `HEAD`、远端 tip 和批准提交三者完全相同，tracked
    和 staged 状态仍为空，untracked 路径集合逐项不变。远端已越过本次发布提交、分支分叉、存在 tracked/staged
    改动、路径重叠或快进后复核不一致时立即停止，不 merge、rebase、reset，也不清理或搬动原有 untracked 文件。

    对齐完成或本来已经对齐后，调用 helper 前还要对本次目标 Skill 路径连续做两次有界状态读取；两次都必须没有
    tracked、staged 或 untracked 变化且结果一致，才算源码状态稳定。任一次不干净或两次结果不同都在 UI 操作前
    停止并留档，不靠等待后重试 helper 来掩盖并发写入。
14. 当前任务立即调用
    `D:\BaiduSyncdisk\.agents\automation\ccswitch-skill-sync\Invoke-CcSwitchSkillSync.ps1`，两个必填参数是
    `-Skills`（Skill 名称数组，不是 `-SkillNames`）和 `-ExpectedRemoteCommit`（40 位 SHA），例如
    `-Skills @("skill-a","skill-b") -ExpectedRemoteCommit "<40位SHA>"`。该 helper 用 UI Automation 识别页面和元素，
    通过 CC Switch WebView 的后台消息完成导航、搜索、一次“检查更新”和逐个单项“更新”；禁止“全部更新”，
    每个目标最多点击一次。不建 watcher 或计划任务，不修改 CC Switch 源码、EXE、数据库、配置或运行时目录。
    后台能力已经通过兼容性验收时直接继续，不再为“是否可以后台操作”追加用户确认；页面暂时重载或处于忙状态时，
    在既定超时内自动恢复。不得以前台激活后恢复焦点作为兜底。任务开始前已经存在“从备份中恢复”对话框、仓库管理
    遮罩或无法识别的页面布局时停止，说明实际阻塞后再和用户讨论其他办法。焦点采样用于 UI 路径变更后的兼容性验收，
    不是每次同步的固定步骤。CC Switch 未运行时由 helper 按既定方式启动，不得为此关闭或重启现有实例。
15. helper 若在任何 UI 操作前返回退出码 `11`、错误码 `sync_already_running`，说明另一个技能同步任务仍在运行。
    不结束对方进程、不抢锁，也不并行启动新同步；通过只读进程检查等待原同步结束后，才使用完全相同的提交 SHA、
    Skill 集合和历史/范围参数重新调用。只有这种在任何 UI 操作前因其他同步任务未结束而被拒绝的情况，才允许重新
    调用；这不放宽页面、扫描、单项更新或验收失败后的禁止重试规则。helper 返回 `source_skill_dirty` 时说明第 13 条
    的稳定前提已经失效，必须停止并生成中央异常报告；不得自动清理源码、改用其他 `SourceRoot` 或再次调用 helper。
16. helper 输出中的 `ui.clicked_skills`、单项 `action: updated` 或 `action: installed` 是点击尝试遥测：它们在等待
    四层对齐前就会写入，只能证明 helper 已发出并记录对应点击，不能证明 CC Switch 已接受、下载、安装或完成更新。
    `all_update_invoked: false` 也只证明 helper 没有调用“全部更新”。最终状态仍是
    `source_pushed_runtime_not_active` 时，对用户应直说“helper 记录了点击尝试，但运行时没有对齐，因此不能确认更新完成”，
    不能把这些字段改写成“CC Switch 已更新”或“系统已完成更新”。

    只有 helper 返回退出码 `0`、状态 `runtime_active`，且本次提交源码与 `.cc-switch`、`.claude`、`.codex` 的
    全部目标文件集合和 SHA-256 完全一致，才算运行时生效。页面被切走、过滤不唯一、扫描或单项更新超时、非目标
    Skill 变化或四层验收失败时，不重试点击、不改运行时。聊天只报告“源码已推送，运行时未生效”、必要用户动作和
    中央异常报告链接；JSON 中的错误码和差异证据留在报告中。需要人工恢复时，用户可在 CC Switch 手动定向更新后用
    `-VerifyOnly` 重新验收；重新验收必须复用原调用的提交 SHA、Skill 集合和 `-AllowHistoricalCommit` 或
    `-ExpectedBaseCommit` 参数。后续 `-VerifyOnly` 通过只证明人工处理后的当前运行时已经对齐，不能反推此前 helper 的
    点击已经完成更新，也不能仅凭最终对齐断定是哪一次点击使更新生效。

    已安装 Skill 的定向更新通过，只证明更新路径已经验证，不能据此声称首次安装也已实测。首次安装新 Skill 只有在
    用户确实需要该 Skill、后台安装真实执行，并且同样通过 `runtime_active` 和四层一致性验收后，才报告为已经验证；
    不为了补测试随便安装无用 Skill。
17. 同一 Skill 的后续提交可能覆盖原发布提交的运行时基线。此时原发布提交与当前版本必须分开验收和报告：
    - 原发布提交仍使用原始 SHA、Skill 集合和历史/范围参数执行 `-VerifyOnly`。它未通过时，保留该提交的
      `source_pushed_runtime_not_active` 结论和差异证据；当前版本的成功不能倒推为原提交已验收。
    - 验收当前可用版本前，先确认当前 `HEAD` 与远端为同一提交、原发布提交是其祖先，且目标 Skill 连续两次有界
      状态读取均为空且一致。当前 `HEAD` 确实修改了目标 Skill 时，按该提交实际修改的完整 Skill 集合执行
      `-VerifyOnly`；不能只请求其中一个 Skill。
    - 当前 `HEAD` 没有修改目标 Skill，或 helper 因目标不属于该提交而返回 `changed_skill_set_mismatch` 时，不把
      与目标无关的 HEAD 当作验收版本。按时间倒序检查所有修改过目标 Skill 的祖先提交，比较每个候选的
      `<skill>` 目录 tree object 与 `HEAD:<skill>`；选择最近一个整个目录内容与当前 HEAD 相同的提交，而不是只比较
      `SKILL.md` 等单个文件。随后从该提交差异取得完整 Skill 集合，并确认集合中每个 Skill 的目录 tree object 到
      当前 HEAD 均未变化、对应路径没有 tracked、staged 或 untracked 偏差。候选不是当前 HEAD 和远端的祖先、任一
      Skill 后来又变化、范围不完整或状态不稳定时停止，不靠手工哈希或缩小请求范围绕过 helper。
    - 上述候选满足条件时，以候选提交、其完整 Skill 集合和 `-AllowHistoricalCommit -VerifyOnly` 执行只读验收。
      只有该调用返回退出码 `0`、`runtime_active` 并完成四层一致性验收，才可报告目标 Skill 的当前内容已部署；
      这是独立事实，不改变原发布提交的失败结论。中央异常报告同时写清原提交状态和当前可用状态，当前版本已经可用时
      删除过期的人工操作要求，但不把整份报告标成原提交已经 `resolved`。
    - 这个分流只做只读验收，不重新扫描、点击或修改运行时。源码比较继续以 helper 指定提交的 Git blob 为准，
      不直接比较 Windows 工作树字节，避免 `core.autocrlf` 引起 CRLF/LF 假差异。
18. 删除或合并 skill（源码目录被移除）时，CC Switch 同步只做增量更新，不会删除运行时里已移除的
    skill。CC Switch 中仍有该 Skill 登记时，先取得对准确条目的单独批准，再使用 CC Switch 自身的卸载动作；
    不直接修改数据库或运行时目录。只有登记已经卸载或不存在、三处运行时仍留下孤儿副本，并且用户又批准了
    这次准确路径清理时，才手动清理：先删 `.claude\skills\` 和 `.codex\skills\` 下的软链接（用
    `Get-Item -Force` 拿到后调 `.Delete()`，不要用 `Remove-Item -Recurse`，否则会顺着软链接删掉
    `.cc-switch` 里的目标内容），再删 `.cc-switch\skills\<name>` 实体目录。清完用 `Test-Path` 四层复核
    该 skill 已全部消失，同时确认保留的 skill 未被误删（2026-08-10 合并 sentence-polish 时定型）。

### 不同名称 Skill 的受控替换

新 Skill 使用不同名称替代当前已安装的旧 Skill 时，新增入口和移除旧入口是两个独立状态。显式点名新 Skill
成功，只证明新入口本身可用；旧 Skill 仍可能匹配同一个自然请求，因此不能据此宣布自然路由已经切换。

1. 先保留旧 Skill，完成新 Skill 的源码推送、定向同步、四层一致性和双端显式点名验收。再在 Claude、Codex
   全新只读会话中分别使用真实自然请求测试共存状态。自然请求仍选中旧 Skill 时，记录为
   `coexistence_routing_conflict`；它既不是新 Skill 本体失败，也不是替换完成，不能靠增加未批准别名掩盖。
2. 只有新 Skill 本身已经可用，且用户对准确旧 Skill 条目和移除范围给出明确批准后，才进入卸载。先检查
   CC Switch 当前是否提供受支持的后台卸载入口；有则只处理该旧条目。没有后台入口时，由用户手动卸载，或在
   确有必要时使用最小 UI Automation。不得直接改 `cc-switch.db`、`.cc-switch`、`.claude` 或 `.codex`；
   自动化发出卸载点击也不等于 CC Switch 已经接受并完成卸载。
3. 卸载后先只读检查 `PRAGMA integrity_check`、新 Skill 唯一登记及预期来源/启用状态、旧 Skill 记录消失，
   并确认 `.cc-switch\skills\<old>`、`.claude\skills\<old>`、`.codex\skills\<old>` 均不存在。随后对新 Skill
   固定同一远端提交、完整 Skill 集合、历史/范围参数和本机文件声明，连续运行两次纯后台 `-VerifyOnly`；两次都
   必须退出 `0`、返回 `runtime_active`、`cc_switch_metadata.valid = true`、问题为空且四层文件集合和 SHA-256
   一致。最后在 Claude、Codex 全新只读会话中重跑自然请求，确认都选择新 Skill，才记录替换完成。
4. 卸载失败、超时、旧记录或路径仍残留、两次后台验收不一致，或任一宿主仍选择旧 Skill 时，保留新 Skill 的
   已验证状态并原样报告实际错误，停止替换结论。不得换供应商、直接修数据库或手工复制运行时文件；孤儿路径清理
   只有在重新列明准确范围并单独批准后，才按第 18 条执行。

## 多代理规则文件检查

- 多代理入口保护以全局规则"规范优先"为准；这里只做执行检查。
- 如果多份规则都存在，检查它们是否冲突。用户明确需要 Codex 和 Claude 各看各的规则时，默认同步 `AGENTS.md` 和 `CLAUDE.md`，不要只做转发文件。
- 没有 `CLAUDE.md` 且用户没有说会用 Claude 时，不要为了"完整"硬建一个。只有项目里已经有 `CLAUDE.md`、用户明确说这个项目会给 Claude 用、当前任务正在整理多代理规则，或任务本身涉及 Claude / Claude Code，才把 `CLAUDE.md` 写进审查稿。
- 全局规则文件和 skill 源码改动先给审查稿；普通项目内 README/AGENTS/CLAUDE 可以直接更新。
