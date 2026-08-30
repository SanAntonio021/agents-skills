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
11. Skill push 成功后，取得 40 位远端提交 SHA，并从提交差异中列出本次实际修改且仍存在的 Skill。
    请求集合必须与提交中的 Skill 集合完全一致，不能顺手加入未修改的 Skill；删除或合并后源码目录已消失的
    Skill 不进入自动更新，继续按第 17 条处理。
12. 调用同步 helper 前重新读取本地 `HEAD` 和远端当前分支。若并发任务已提交并推送，使本次发布提交不再是
    当前 `HEAD`，不要把 `ExpectedRemoteCommit` 换成新的 `HEAD`，也不要 reset、rebase 或重新提交。本次提交只有在
    同时满足以下条件时才可继续：它是本地当前 `HEAD` 和远端当前分支的共同祖先；本次批准发布范围只由该单个
    提交构成；该提交实际修改的 Skill 集合与本次请求完全一致。满足时固定使用本次原始 40 位 SHA，并给 helper 增加
    `-AllowHistoricalCommit`；历史提交模式不能同时使用 `-ExpectedBaseCommit`，发布源仍是该提交中的 Git blob。
13. 当前任务立即调用
    `D:\BaiduSyncdisk\.agents\automation\ccswitch-skill-sync\Invoke-CcSwitchSkillSync.ps1`，两个必填参数是
    `-Skills`（Skill 名称数组，不是 `-SkillNames`）和 `-ExpectedRemoteCommit`（40 位 SHA），例如
    `-Skills @("skill-a","skill-b") -ExpectedRemoteCommit "<40位SHA>"`。该 helper 只通过 UI Automation 进入 Skills 页、执行一次“检查更新”并
    逐个过滤后点击单项“更新”；禁止“全部更新”，每个目标最多点击一次。不建 watcher 或计划任务，不修改
    CC Switch 源码、EXE、数据库、配置或运行时目录。CC Switch 未运行时由 helper 启动；优先后台操作，必要时
    可短暂前台并在结束时恢复原窗口。
14. helper 若在任何 UI 操作前返回退出码 `11`、错误码 `sync_already_running`，说明另一个技能同步任务仍在运行。
    不结束对方进程、不抢锁，也不并行启动新同步；通过只读进程检查等待原同步结束后，才使用完全相同的提交 SHA、
    Skill 集合和历史/范围参数重新调用。只有这种在任何 UI 操作前因其他同步任务未结束而被拒绝的情况，才允许重新
    调用；这不放宽页面、扫描、单项更新或验收失败后的禁止重试规则。
15. 只有 helper 返回退出码 `0`、状态 `runtime_active`，且本次提交源码与 `.cc-switch`、`.claude`、
    `.codex` 的全部目标文件集合和 SHA-256 完全一致，才算运行时生效。页面被切走、过滤不唯一、扫描或单项更新
    超时、非目标 Skill 变化或四层验收失败时，不重试点击、不改运行时。聊天只报告“源码已推送，运行时未生效”、
    必要用户动作和中央异常报告链接；JSON 中的错误码和差异证据留在报告中。需要人工恢复时，用户可在 CC Switch 手动定向更新后用 `-VerifyOnly`
    重新验收；重新验收必须复用原调用的提交 SHA、Skill 集合和 `-AllowHistoricalCommit` 或
    `-ExpectedBaseCommit` 参数。
16. 同一 Skill 的后续提交可能覆盖原发布提交的运行时基线。此时原发布提交与当前版本必须分开验收和报告：
    - 原发布提交仍使用原始 SHA、Skill 集合和历史/范围参数执行 `-VerifyOnly`。它未通过时，保留该提交的
      `source_pushed_runtime_not_active` 结论和差异证据；当前版本的成功不能倒推为原提交已验收。
    - 只有当前 `HEAD` 与远端为同一提交、原发布提交是该提交祖先、且源码没有未声明工作区偏差时，才可另外以当前
      `HEAD` 执行 `-VerifyOnly`。只有该调用返回退出码 `0`、`runtime_active` 并完成四层一致性验收，才可报告
      “当前最新版已部署”；这是一条独立事实，不改变原发布提交的结论。
    - 这个分流只做只读验收，不重新扫描、点击或修改运行时。源码比较继续以 helper 指定提交的 Git blob 为准，
      不直接比较 Windows 工作树字节，避免 `core.autocrlf` 引起 CRLF/LF 假差异。
17. 删除或合并 skill（源码目录被移除）时，CC Switch 同步只做增量更新，不会删除运行时里已移除的
    skill。用户点完同步后，源码目录已消失，但 `.cc-switch\skills\<name>`、`.claude\skills\<name>`、
    `.codex\skills\<name>` 三处仍会残留旧副本，必须手动清理。顺序：先删 `.claude\skills\` 和
    `.codex\skills\` 下的软链接（用 `Get-Item -Force` 拿到后调 `.Delete()`，不要用 `Remove-Item -Recurse`，
    否则会顺着软链接删掉 `.cc-switch` 里的目标内容），再删 `.cc-switch\skills\<name>` 实体目录。清完用
    `Test-Path` 四层复核该 skill 已全部消失，同时确认保留的 skill 未被误删（2026-08-10 合并 sentence-polish
    时定型）。

## 多代理规则文件检查

- 多代理入口保护以全局规则"规范优先"为准；这里只做执行检查。
- 如果多份规则都存在，检查它们是否冲突。用户明确需要 Codex 和 Claude 各看各的规则时，默认同步 `AGENTS.md` 和 `CLAUDE.md`，不要只做转发文件。
- 没有 `CLAUDE.md` 且用户没有说会用 Claude 时，不要为了"完整"硬建一个。只有项目里已经有 `CLAUDE.md`、用户明确说这个项目会给 Claude 用、当前任务正在整理多代理规则，或任务本身涉及 Claude / Claude Code，才把 `CLAUDE.md` 写进审查稿。
- 全局规则文件和 skill 源码改动先给审查稿；普通项目内 README/AGENTS/CLAUDE 可以直接更新。
