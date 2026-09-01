---
name: skill-check
description: 检查本地技能目录和历史使用证据，确认 Claude/Codex 实际读取或调用过哪些技能，发现长期未见使用、疑似漏用、可能冗余、目录结构问题、重复或可合并技能、名字不一致、链接失效、空技能或源码与运行时未同步。Use when 用户要监测本地技能触发情况、查哪些 skill 一直没触发或可能该触发却没触发、区分 Claude 真正的 Skill 调用与启动时候选加载、确认当前加载了哪些 skill、查同名冲突、判断技能是否该合并、检查目录名和 `name:` 是否一致、分清源码、lark 实体层、cc-switch 与 Claude/Codex 运行时、排查 `Skill 不存在于 SSOT` 或“已经改了为什么没生效”；prefer this over `agent-rules` when 目标是执行一次具体审计。
---

# Skill 目录检查

## 作用

这份 skill 用来查清本地技能目录，重点看这些问题：

- 当前实际会用到哪些技能
- 目录结构问题
- 真的重复技能
- 名字不一致
- 职责相近但不该直接合并
- 源码和运行时目录没有同步
- 链接或路径失效
- 空技能或坏技能
- 触发分层是否合理（该点名的没降级、不该降级的被降级）
- cc-switch 未启用副本、双侧启用不对齐
- Codex/Claude 历史里哪些技能有实际使用证据、哪些长期未见使用
- 哪些用户请求疑似应该触发某个技能但未见对应调用证据

## 本地目录方案

这台机器现在不再按旧的分层目录分类。

源文件目录采用一层平铺的方式：

```text
D:\BaiduSyncdisk\.agents\skills\<skill-name>\SKILL.md
```

判断规则很简单：

- 顶层目录里有 `SKILL.md`，就算一个源技能。
- 顶层目录里没有 `SKILL.md`，不算技能。
- `*-workspace`、`rescued-skill-materials` 这类目录只当作工作材料或历史材料，不算当前技能。
- 目录名必须和 `SKILL.md` 里的 `name:` 一致。

## 先分清六层目录（2026-07-11 审计实测）

在这台机器上，排查技能问题时先分清这六层：

1. 自建源码：`D:\BaiduSyncdisk\.agents\skills`（独立 git 仓库 agents-skills，真正该改的地方）
2. lark 实体层：`C:\Users\SanAn\.agents\skills`（lark-cli 从飞书 well-known 源安装，`.skill-lock.json` 记账；新版 codex-cli 直接读取这一层）
3. cc-switch 分发：`C:\Users\SanAn\.cc-switch\skills`（自建技能的同步产物 + 第三方技能的安装体）
4. Claude 运行时：`C:\Users\SanAn\.claude\skills`（symlink→cc-switch，lark 技能是 junction→实体层）
5. Codex 运行时：`C:\Users\SanAn\.codex\skills`（symlink→cc-switch）＋ `.system\` 内置技能（skill-creator/skill-installer 等，带 `.codex-system-skills.marker`，与 cc-switch 版可能重名双入口）
6. Codex plugins bundled 技能层：`C:\Users\SanAn\.codex\plugins\cache\...`（插件自带技能，如 bundled pdf）

用户问“现在到底加载了什么”时，看对应工具的运行时层：Claude 看第 4 层，Codex 看第 5＋6 层再叠加第 2 层（直读）；不要把源文件目录当成当前已加载列表。

停用某个技能用 `~\.codex\config.toml` 的 `[[skills.config]]`（`name`/`path` + `enabled = false`）。注意：config.toml 是 cc-switch 按 DB 快照渲染的产物，直接改会在 provider 切换时被冲回，持久化要进 cc-switch 的配置快照。

## 流程

1. 先判断用户到底想查哪一层：
   - 查“哪些技能真正用过 / 一直没触发 / 是否存在漏触发”时，执行下方“历史使用审计”，不要拿目录存在或启动时候选加载代替使用证据。
   - 查“当前真的加载了哪些 skill”时，优先看 Codex 实际读取的技能目录。
   - 查“面板里更新了，为什么没生效”时，再看 cc-switch 同步出来的目录和 `cc-switch.db`。
   - 查 CC Switch 安装红框 `Skill 不存在于 SSOT` 时，在 `cc-switch.db` 里对照 `skill_repos.branch`、`skills.repo_branch`、`skills.directory` 和远端默认分支；详细步骤见 [references/skill-hygiene.md](references/skill-hygiene.md)。
   - 单个已安装技能的文件仍在，但 `repo_branch`、`readme_url` 或双端启用元数据残留在旧状态时，先完成只读定位；获得批准后，优先在 CC Switch 中只卸载并重新安装该技能，从当前真实分支恢复来源元数据并启用 Claude/Codex。存在未处理的本机私有文件、重装未能修复或 GUI 无法完成时，才进入最小数据库修复。由本任务执行恢复时，用同一远端 SHA 和 Skill 集合重跑完整同步与 `-VerifyOnly`；用户明确自行完成恢复且不授权 UI 自动化时，改走下方“两次后台 `-VerifyOnly`”验收。
   - 目标技能本身已经指向当前分支，但 CC Switch 日志仍请求同仓库旧分支压缩包时，检查该仓库下全部已安装技能的 `repo_branch` 和 `readme_url`。CC Switch 的更新扫描以仓库为单位，任一兄弟技能残留旧分支都可能阻断目标更新；这类多技能范围先完整列出，再单独批准修复。
   - 如果技能条目显示“已安装”但启动/同步时报 `Skill 不存在于 SSOT`，还要核对 SSOT 下 `<directory>\SKILL.md` 是否真实存在；这通常是数据库残留记录，不要直接改 Codex 运行时目录。
   - 查“源码已经改了 / Claude 改完了 / 为什么运行时还是旧行为”时，同时比较源码、cc-switch 分发目录、Claude 运行时和 Codex 运行时的已提交 Git blob 或关键行。目录内容一致但行为仍可疑时，再用全新只读会话验证。
   - 查“远端已推送，但 CC Switch 检查更新没有提示”时，先看提交是否只改了 `references/`、`scripts/` 或 `evals/` 等子文件。会改变运行行为的子文件必须在 `SKILL.md` 有对应语义入口；纯 eval 或不影响运行行为的说明不制造无意义入口。实证和诊断顺序见 [references/skill-hygiene.md](references/skill-hygiene.md)。
   - 查“CC Switch 同步后现在是否完整生效”时，按 [references/skill-hygiene.md](references/skill-hygiene.md) 的“源码到双端运行时验收”逐层检查；不能只看面板、软链接或单个 `SKILL.md`。
   - 查“以后该改哪一份”时，最后再回到源文件目录。
2. 扫描目标根目录：

```powershell
python scripts/audit_skill_tree.py scan --root <target-root> --reports-root <reports-root> --date <YYYY-MM-DD>
```

3. 再读取本轮产物：
   - `manifests/<date>/summary.json`
   - `weekly/<date>.md`
4. 如果还要查市场安装清单、残留目录或全局安装情况，再调用补充脚本；不要把这一步默认塞进每次审计。
5. 汇报时先给出：
   - 当前实际会用到的技能
   - 目录结构问题
   - 真的重复技能
   - 名字不一致
   - 链接或路径失效
   - 空技能或坏技能
6. 优先看严重问题、建议动作和链接失效，再决定是否把具体修补工作交给 `skill-creator`。

## 历史使用审计

用户要监测技能触发、找长期未用技能或检查触发条件时，先读取
[references/usage-audit.md](references/usage-audit.md)，再运行：

用户进一步要判断保留、停用、归档、删除，或是否为一组低频技能增加路由时，也先按该 reference
的“保留价值复核”执行；不得把零调用、技能包文件总字数，或“CLI 已可读取这些说明”直接当成精简依据。

```powershell
python scripts/audit_skill_usage.py --reports-root <reports-root> --date <YYYY-MM-DD> `
  --window-start <ISO-8601> --window-end <ISO-8601> --timezone Asia/Shanghai
```

默认只读扫描全部可用历史：Codex 的 `sessions`、`archived_sessions`，Claude 的 `projects` 和
`telemetry`；技能清单覆盖源码、Codex/Claude 运行时、lark 实体层和 Codex 插件缓存。需要隔离测试或
限定范围时，可重复传入 `--skills-root`、`--codex-sessions-root`、`--claude-projects-root` 和
`--claude-telemetry-root`；一旦传入某一类自定义根，该类默认根就不再扫描。

固定证据口径：

- 计数单位是用户请求；同一宿主、同一请求、同一技能无论出现多少条证据，最多计一次。
- Claude 仅把 `assistant.message.content[].name == "Skill"`、`input.skill` 非空且能沿
  `parentUuid` 关联到用户请求的事件计为实际调用；无法关联的事件只报警，不计数。
- Claude `tengu_skill_loaded` 只是启动时候选加载，绝不计为使用。
- Codex 统计真实用户记录里的 `$skill-name`、`/skill-name`、技能 `SKILL.md` 链接，以及能映射到
  `turn_id`、执行成功且读取已知 `SKILL.md` 的命令；显式点名和读取证据在同一请求内合并。
- Codex 仍没有覆盖全部隐式路由的稳定事件，因此计数是可观察下界；报告必须写明“未见记录不等于实际未使用”。
- 纯图片或附件、没有可扫描文本的 Codex 用户记录单独计数，不作为目标字段缺失，避免永久阻断完整周次。
- `疑似漏用` 只由技能名和 `description` 的确定性规则筛选，不调用模型，也不自动改技能。
- `可能冗余` 只有在传入 `--hygiene-summary` 后，才把“历史内未见使用”与已有 duplicate/overlap
  finding 求交；它仍是人工复核候选，不是删除建议。

报告固定输出到：

- `<reports-root>/usage/manifests/<date>/summary.json`
- `<reports-root>/usage/weekly/<date>.md`
- 周检另维护 `<reports-root>/usage/dashboard/index.html`，这是内嵌最近 12 周聚合数据的离线页面，
  不需要启动本地服务或联网。

默认片段先脱敏再截到 240 字符；敏感场景传 `--no-excerpt`。真实 transcript 不复制进报告目录、技能
仓库或评测夹具，报告证据源只保存配置根代号、POSIX 相对路径和行号。

## 结果类型

- `当前实际会用到的技能`
  指本次扫描目录里，实际会参与当前路由或加载判断的技能。
- `目录结构问题`
  指技能放在不该放的位置，或工作区、历史材料、说明材料里混入了 `SKILL.md`。
- `真的重复技能`
  指当前会用到的技能里，`name:` 归一化后冲突，或 `SKILL.md` 正文高度相似且职责也重合。
- `名字不一致`
  指目录名、数据库里的 `directory`、数据库里的显示名，和 `SKILL.md` 里的 `name:` 对不上。
- `职责相近但不该直接合并`
  指描述和正文相似，但职责没有完全重合，不能直接当重复。
- `源码和运行时目录没有同步`
  指已提交源码已经更新，但 cc-switch 分发目录、Claude 运行时或 Codex 运行时仍是旧版本。结论要写明哪一层落后，例如“源码已修，当前 Claude/Codex 仍未加载新版本”，并提醒用户通过 cc-switch 检查更新；不要直接改 `.cc-switch`、`.claude` 或 `.codex`。
- `链接或路径失效`
  指绝对路径、相对链接、Related Skills 链接或工作流引用失效。
- `空技能或坏技能`
  指缺 `SKILL.md`、文件开头配置为空、正文为空，或关键结构损坏。

## 源码到双端运行时验收

用户要确认“同步完成”或“现在应该生效”时，不能把目录存在当成验收完成。读取
[references/skill-hygiene.md](references/skill-hygiene.md)，依次核对：

1. 源码提交与远端目标分支一致；
2. cc-switch 数据库完整，目标仓库的 `branch`/`enabled`、同仓库全部已安装技能的
   `repo_branch`/`readme_url`，以及目标技能的目录、仓库归属和 Claude/Codex 启用状态均与预期源码一致；
3. 技能仓库提交中的全部目标文件与 cc-switch、Claude、Codex 三个运行时副本一致；
4. 结构校验按目标运行时分开判断：Agent Skills / OpenAI 通用格式与 Claude Code 扩展分别验收；
   严格通用校验器拒绝已确认的 Claude 扩展时，不能把整个 Skill 直接判为无效，也不能把 Claude
   扩展的效果外推给 Codex；相关确定性测试通过；
5. 用合成数据在 Codex、Claude 全新只读会话分别验证路由和关键安全边界。
6. 定向同步返回退出码 `0` 和 `runtime_active` 后，再以完全相同的 `ExpectedRemoteCommit` 与
   `Skills` 运行一次 `-VerifyOnly`；两次结果都必须显示 `cc_switch_metadata.valid == true` 且没有
   元数据问题，第二次也返回退出码 `0`、`runtime_active`，四层文件集合和 SHA-256 仍一致，才写
   “运行时已生效”。

当用户明确选择自己在 CC Switch 完成卸载、重装或定向更新，并明确不授权本任务控制鼠标或执行 UI
自动化时，不再运行会进入界面的完整同步 helper。用户报告手动操作完成后，以完全相同的
`ExpectedRemoteCommit`、`Skills`、历史/范围参数和本机文件声明，连续运行两次纯后台
`-VerifyOnly`。两次都必须退出 `0`、返回 `runtime_active`，且 `cc_switch_metadata.valid == true`、
元数据问题为空、四层文件集合和 SHA-256 一致；任何在运行时核验前因网络或预检失败而中止的调用都
不计入这两次验收。该分流只证明手动操作后的当前运行时已经稳定对齐，不反推具体哪次手动操作使其生效。

工作区 SHA-256 不同不等于运行时陈旧。Windows 工作区可能是 CRLF，提交 blob 和运行时副本可能是
LF；先比较已提交 Git blob 与运行时文件字节，或明确归一化换行后再判断。

运行时若有经过确认的本机私有文件，只能通过同步 helper 的 `ExpectedRuntimeLocalFiles` 逐文件声明；
路径必须属于本次 Skill、不能被目标提交跟踪，也不能使用通配符或目录。完整同步与后续
`-VerifyOnly` 必须复用同一声明；未声明的额外文件仍按漂移失败。具体判据见
[references/skill-hygiene.md](references/skill-hygiene.md) 的“合法本机文件的精确声明”。

认证、余额、中转或模型服务错误若发生在技能输出前，状态只能记为“运行时验收受环境阻断”。
环境恢复后重跑同一用例；不得把这种错误记成技能失败，也不得在未重跑时记成通过。

CC Switch 定向同步返回 `update_scan_timeout` 时，记录原始 JSON、目标 commit、Skill 集合和
`clicked_skills`，状态写“更新扫描受环境阻断，运行时待验收”，不写成技能失败或同步成功。只有
`clicked_skills` 明确为空、确认尚未点击任何目标 Skill 的“更新”按钮时，才允许用同一 commit 和
同一 Skill 集合重新运行完整 helper；如果已经点击或无法确认，则不再触发 UI 更新，只做
`-VerifyOnly`，或等待用户手动定向更新后按上述两次后台 `-VerifyOnly` 分流验收。完整判据见
[references/skill-hygiene.md](references/skill-hygiene.md) 的“更新扫描超时与 UI 竞态恢复”。

若 helper 返回 `skills_page_blocked_by_restore`，结论是“从备份中恢复”窗口阻塞了 Skills 页面，
不能再归为网络错误或导航超时，也不能继续重试同步。不是当前流程打开的窗口只报告并停止；任何主动
打开弹窗或覆盖层的诊断流程都必须在 `finally` 中关闭它，并确认回到操作前页面。

## 触发分层判断

审计每个技能时问一句：**用户实际怎么调用它**。

- 用户只在 Claude Code 点名调用（`/技能名`）→ 可建议加 `disable-model-invocation: true`，让 description
  不进入 Claude 的常驻上下文；这个结论只适用于 Claude Code。
- 同一 Skill 还供 Codex 使用时，必须单独验证 Codex 的发现和调用行为；不能凭 Claude 专用字段宣称
  Codex 也隐藏 description、禁止自动调用或实现了“仅用户点名”。
- 用户靠描述任务自动触发 → 保持默认，**不管它看起来多低频**。2026-07-06 实证：agent-rules 和 skill-check 看似点名场景，实际用户靠描述触发，降级会直接失效。
- 判断依据只能来自用户的真实使用习惯，不能从技能主题倒推；拿不准时问用户，不要默认降级。

cc-switch 的本地导入副本、单侧启用、更新链路等已知行为坑，见 [references/skill-hygiene.md](references/skill-hygiene.md)。

## 融合本地技能周检

需要把上游、目录健康、历史使用和疑似漏用合并成每周逐项问答时，使用
[references/weekly-review.md](references/weekly-review.md) 和
`scripts/run_weekly_skill_review.py`。它复用本 skill 的三个审计入口，不另建职责重叠的技能。

```powershell
python scripts/run_weekly_skill_review.py scan --date <YYYY-MM-DD> --json
python scripts/run_weekly_skill_review.py next-question --json
```

周检状态写入 `<reports-root>/weekly-review-state.json`，采用跨进程锁、临时文件和原子替换。
状态损坏、未知 `schema_version` 或锁冲突只报告严重问题，保留原文件，不自动重建。finding ID
按“类型、技能、独立修改目的”稳定生成；证据、方案和源码基线 fingerprint 未变时不重复问，
变化后旧批准和相关执行批次自动失效。

每次 `next-question` 只返回一项。证据不足最多追问两条事实，随后必须关闭、形成建议或转为等待新证据。
“历史内未见使用”只有连续四个相邻、完整、同口径周窗才进入队列；扫描失败、报告无效、证据无法
关联用户请求、周窗中断、统计口径升级或该技能的激活宿主范围变化会重置连续计数。同一周重跑不会
重复累加。周窗固定为上海时区前一周六 14:00（含）到本周六 14:00（不含）。
严重问题可插队，每周最多新增三条中低优先级问题。全部逐项决定后，`prepare-execution` 只生成一次
最终执行确认；没有批准项不创建空批次。详细的自然语言映射、隔离候选、副本哈希、精确暂存、推送和
双端同步验收见上述参考文件。

失败重试若发生在源码已提交、运行时尚未同步的阶段，只能在目标目录干净、记录提交和远端 SHA
都可验证且目标从记录提交到当前 HEAD 未再变化时，把源码 fingerprint 推进到已提交结果；否则继续
按源码漂移阻断，不能把当前目录无条件当作新基线。
执行确认绑定的同步 helper 身份同时哈希入口脚本和实现模块；任一文件变化都必须使旧批次失效并重新确认。

## 合并候选判断

判断两个 skill 是否该合并时，不只看主题是否相近。

只有目标、输入、输出产物、执行方式和触发场景都高度重合，才标为 `合并候选`。

如果只是同属一个大主题，但产物或执行方式不同，标为 `职责相近但不该直接合并` 或 `保留`。例如：

- 论文文本精修和论文图件重画都属于论文工作，但一个处理文本，一个处理图件，不应直接合并。
- 台架测试和实验记录都属于实验工作，但一个执行测试，一个同步记录，不应直接合并。
- 指标论证和工程申报都可能服务同一项目，但一个判断指标是否站得住，一个写申报正文，不应直接合并。

`合并候选` 只用于两件事明显重复、合并后又不会伤害触发准确性的情况。

详细分级和报告模板见：

- [references/finding-severity.md](references/finding-severity.md)
- [references/report-template.md](references/report-template.md)
- [references/skill-hygiene.md](references/skill-hygiene.md)
- [references/usage-audit.md](references/usage-audit.md)
- [scripts/manage_market_skills.ps1](scripts/manage_market_skills.ps1)
- [scripts/run_codex_skill_ecosystem_audit.py](scripts/run_codex_skill_ecosystem_audit.py)
- [scripts/audit_skill_usage.py](scripts/audit_skill_usage.py)

## 边界

- 只读审计，不自动移动、归档、删除或改写任何 `SKILL.md`。
- 不把源文件目录直接当成“当前已加载技能列表”。
- 不把 cc-switch 面板显示名直接当成磁盘目录名。
- 不再按旧的分层目录判断技能来源；如果发现旧目录，只当作需要人工复核的历史残留。
- 不自动跑市场搜索，也不替代 [../agent-rules/SKILL.md](../agent-rules/SKILL.md) 的规则说明角色。
- 不替代 `skill-creator` 的创建和改写工作。
- 这里保留市场安装检查脚本，但不把自己改成“自动更新器”；默认仍以只读审计为主。
- 不启动 daemon、实时 watcher 或常驻 dashboard 服务，不联网，不修改 transcript、技能或运行时目录；
  周检只生成可直接打开的离线 dashboard 文件。
- 不根据一次低频或无记录结论自动降级、合并、归档或删除技能。
- 周检脚本只维护观察、决定和执行批次状态；它不替用户批准、修改、提交、推送或同步技能。

## 输出

固定输出到 `<reports-root>`：

- `manifests/<date>/summary.json`
- `weekly/<date>.md`

历史使用审计另输出到 `usage/` 子目录，使用 `已用`、`历史内未见使用`、`疑似漏用`、`可能冗余`
四个面向用户的分类；不要把内部事件名直接当结论标题。

融合周检还输出 `usage/dashboard/data/<date>.json` 和稳定入口 `usage/dashboard/index.html`。dashboard
只含技能名、宿主、聚合请求次数、连续零周数、状态、证据类型和覆盖警告，不含提示词片段、session
来源路径或本机绝对路径。

默认汇报顺序是：

- 扫描范围
- 当前实际会用到的技能
- 目录结构问题
- 真的重复技能
- 名字不一致
- 源码和运行时目录没有同步
- 链接或路径失效
- 空技能或坏技能
- 建议动作

建议动作只使用这些标签：

- `保留`
- `补边界`
- `补引用`
- `归档候选`
- `合并候选`
- `降级点名`
- `人工复核`

## 维护

- 如果路径、同步方式或启用链路变化，先更新 [references/skill-hygiene.md](references/skill-hygiene.md) 和脚本，再同步这里。
- 如果本地目录方案变化，先改脚本和参考文件，再同步这里。
- 如果以后接 automation，优先复用现有 CLI 入口，不把调度信息写进 `SKILL.md`。
- 周检自动任务应回到当前任务执行 `scan`、`next-question` 和逐条决定，不另建独立周报任务。
