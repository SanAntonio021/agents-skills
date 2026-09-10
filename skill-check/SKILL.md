---
name: skill-check
description: 承接明确的上游参考发现、技能市场搜索和候选内容比较；普通业务请求不自动搜索技能。检查本地技能目录和历史使用证据，确认 Claude/Codex 实际读取或调用过哪些技能，发现长期未见使用、疑似漏用、可能冗余、目录结构问题、重复或可合并技能、插件与本地技能重叠、名字不一致、链接失效、空技能或源码与运行时未同步。Use when 用户要监测本地技能触发情况、查哪些 skill 一直没触发或可能该触发却没触发、区分 Claude 真正的 Skill 调用与启动时候选加载、确认当前加载了哪些 skill、查同名冲突、判断技能是否该合并、判断应停用整个插件还是只停用其中的重复技能、检查目录名和 `name:` 是否一致、分清源码、lark 实体层、cc-switch 与 Claude/Codex 运行时、排查 `Skill 不存在于 SSOT` 或“已经改了为什么没生效”；prefer this over `agent-rules` when 目标是执行一次具体审计。
---

# Skill 目录检查

## 检查范围与授权

- 单个技能未生效、名称不一致或引用失效时，只检查该技能及必要的源码、分发、运行副本和元数据，不默认扫描全库或会话历史。
- 明确要求目录健康、全库盘点或历史使用统计时，才运行对应审计。既有周检继续按已确认的窗口与范围执行。
- 日志或元数据表明同仓库其他条目影响当前更新时，可以只读扩大关联检查并说明原因；关联条目不自动纳入修复授权。
- 只要求检查时给结论与建议。明确要求修复时，复用准确授权完成对应源码修改、后台修复和核验；接口不支持时只暂停相关项，说明具体缺口。
- 源码改写结合 `skill-creator`，定向发布遵循 [agent-rules](../agent-rules/SKILL.md)。CC Switch 变更只走受支持后台接口，不控制界面、强关应用、手工修改数据库或删除运行目录。

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

插件与本地技能重叠时，先把插件包、插件内各技能和连接工具分开盘点。只要插件还提供本地技能没有的能力，
就保留插件，仅考虑按**当前版本的精确绝对 `SKILL.md` 路径**停用重复技能；不能因为主题相同就关闭整个
插件。写入前必须用一次性配置覆盖证明技能目录只少目标身份，连接工具和保留技能仍在；无法证明就停止，
不能退化为整插件禁用。完整判据、真实能力 canary 和上下文差值口径见
[references/skill-hygiene.md](references/skill-hygiene.md) 的“插件技能重叠的选择性处理”。

## 流程

1. 先判断用户到底想查哪一层：
   - 查“哪些技能真正用过 / 一直没触发 / 是否存在漏触发”时，执行下方“历史使用审计”，不要拿目录存在或启动时候选加载代替使用证据。
   - 查“当前真的加载了哪些 skill”时，优先看 Codex 实际读取的技能目录。
   - 查“面板里更新了，为什么没生效”时，再看 cc-switch 同步出来的目录和 `cc-switch.db`。
   - 查 CC Switch 安装红框 `Skill 不存在于 SSOT` 时，在 `cc-switch.db` 里对照 `skill_repos.branch`、`skills.repo_branch`、`skills.directory` 和远端默认分支；详细步骤见 [references/skill-hygiene.md](references/skill-hygiene.md)。
   - 单个已安装技能的文件仍在，但来源或启用元数据陈旧时，只读定位具体字段及本机私有文件，再按已有准确授权使用受支持后台接口。更新不一定能修复元数据；接口缺少能力或无法保护私有文件时保留该项，不转入界面重装或数据库兜底。
   - 目标技能已经指向当前分支，但日志仍请求同仓库旧分支压缩包时，只读检查该仓库相关已安装技能的 `repo_branch` 和 `readme_url`。完整列出实际阻断条目；修复沿用已明确范围，新增范围才需要用户决定。
   - 如果技能条目显示“已安装”但启动/同步时报 `Skill 不存在于 SSOT`，还要核对 SSOT 下 `<directory>\SKILL.md` 是否真实存在；这通常是数据库残留记录，不要直接改 Codex 运行时目录。
   - 查“源码已经改了 / Claude 改完了 / 为什么运行时还是旧行为”时，同时比较源码、cc-switch 分发目录、Claude 运行时和 Codex 运行时的已提交 Git blob 或关键行。目录内容一致但行为仍可疑时，再用全新只读会话验证。
   - 查“远端已推送，但 CC Switch 检查更新没有提示”时，先看提交是否只改了 `references/`、`scripts/` 或 `evals/` 等子文件。会改变运行行为的子文件必须在 `SKILL.md` 有对应语义入口；纯 eval 或不影响运行行为的说明不制造无意义入口。实证和诊断顺序见 [references/skill-hygiene.md](references/skill-hygiene.md)。
   - 查“CC Switch 同步后现在是否完整生效”时，按 [references/skill-hygiene.md](references/skill-hygiene.md) 的“源码到双端运行时验收”逐层检查；不能只看面板、软链接或单个 `SKILL.md`。
   - 查“以后该改哪一份”时，最后再回到源文件目录。
2. 用户要求目录健康或全库盘点时，扫描指定根目录；局部诊断直接读取目标文件与记录，不为复用脚本而扫描整个根：

```powershell
python scripts/audit_skill_tree.py scan --root <target-root> --reports-root <reports-root> --date <YYYY-MM-DD>
```

3. 使用上述扫描后读取本轮产物；不以历史报告冒充当前检查：
   - `manifests/<date>/summary.json`
   - `weekly/<date>.md`
4. 如果还要查市场安装清单、残留目录或全局安装情况，再调用补充脚本；不要把这一步默认塞进每次审计。
5. 全库报告按以下类别呈现；局部问题只报告检查范围、结论、必要依据和下一步：
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

仅在历史使用审计中，默认数据源为 Codex 的 `sessions`、`archived_sessions`，Claude 的 `projects` 和
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
  指已提交源码已经更新，但 cc-switch 分发目录、Claude 运行时或 Codex 运行时仍是旧版本。结论写明哪一层落后；只读任务给定向同步建议，已有修复授权则按 `agent-rules` 后台发布和验证，不手工修改运行副本。
- `链接或路径失效`
  指绝对路径、相对链接、Related Skills 链接或工作流引用失效。
- `空技能或坏技能`
  指缺 `SKILL.md`、文件开头配置为空、正文为空，或关键结构损坏。

## 源码到双端运行时验收

用户要确认“同步完成”或“现在应该生效”时，不能把目录存在当成验收完成。读取
[references/skill-hygiene.md](references/skill-hygiene.md)，依次核对：

1. 源码提交与远端目标分支一致；
2. cc-switch 数据库完整，目标仓库的 `branch`/`enabled` 及目标技能的来源、目录和 Claude/Codex 启用状态一致；有仓库级阻断线索或现有 helper 要求时，只读核对关联条目，不扩大更新集合；
3. 技能仓库提交中的全部目标文件与 cc-switch、Claude、Codex 三个运行时副本一致；
4. 结构校验按目标运行时分开判断：Agent Skills / OpenAI 通用格式与 Claude Code 扩展分别验收；
   严格通用校验器拒绝已确认的 Claude 扩展时，不能把整个 Skill 直接判为无效，也不能把 Claude
   扩展的效果外推给 Codex；相关确定性测试通过；
5. 用合成数据在 Codex、Claude 全新只读会话分别验证路由和关键安全边界。
6. 定向同步返回退出码 `0` 和 `runtime_active` 后，再以完全相同的 `ExpectedRemoteCommit` 与
   `Skills` 运行一次 `-VerifyOnly`；两次结果都必须显示 `cc_switch_metadata.valid == true` 且没有
   元数据问题，第二次也返回退出码 `0`、`runtime_active`，四层文件集合和 SHA-256 仍一致，才写
   “运行时已生效”。

用户只要求核验、或已明确自行完成恢复时，固定提交、目标集合和本机文件声明，使用后台 `-VerifyOnly`；不为了获得更新回执再执行写入。通过只证明当前状态与目标提交一致，不反推是哪次历史操作使其生效。检查失败或实际状态发生变化后再针对性复核。

工作区 SHA-256 不同不等于运行时陈旧。Windows 工作区可能是 CRLF，提交 blob 和运行时副本可能是
LF；先比较已提交 Git blob 与运行时文件字节，或明确归一化换行后再判断。

运行时若有经过确认的本机私有文件，只能通过同步 helper 的 `ExpectedRuntimeLocalFiles` 逐文件声明；
路径必须属于本次 Skill、不能被目标提交跟踪，也不能使用通配符或目录。完整同步与后续
`-VerifyOnly` 必须复用同一声明；未声明的额外文件仍按漂移失败。具体判据见
[references/skill-hygiene.md](references/skill-hygiene.md) 的“合法本机文件的精确声明”。

认证、余额、中转或模型服务错误若发生在技能输出前，状态只能记为“运行时验收受环境阻断”。
环境恢复后重跑同一用例；不得把这种错误记成技能失败，也不得在未重跑时记成通过。

后台同步失败或超时后保留原回执、提交、目标集合和失败阶段，先按相同参数只读核验实际状态。临时故障恢复后可在原授权内按 `agent-rules` 的发布流程重试；已对齐目标只核验，源码变化、登记错误或文件冲突先处理具体问题。同错先诊断，不无限重跑或重复批准。旧 `clicked_skills` 仅作历史线索，不据此重启界面流程；无法确认时保留“运行时待验收”。具体见 [后台恢复与验收](references/skill-hygiene.md#8-后台恢复与验收)。

## 触发分层判断

审计每个技能时问一句：**用户实际怎么调用它**。

- 用户只在 Claude Code 点名调用（`/技能名`）→ 可建议加 `disable-model-invocation: true`，让 description
  不进入 Claude 的常驻上下文；这个结论只适用于 Claude Code。
- 同一 Skill 还供 Codex 使用时，必须单独验证 Codex 的发现和调用行为；不能凭 Claude 专用字段宣称
  Codex 也隐藏 description、禁止自动调用或实现了“仅用户点名”。
- 用户靠描述任务自动触发 → 保持默认，**不管它看起来多低频**。2026-07-06 实证：agent-rules 和 skill-check 看似点名场景，实际用户靠描述触发，降级会直接失效。
- 判断依据只能来自用户的真实使用习惯，不能从技能主题倒推；拿不准时问用户，不要默认降级。

cc-switch 的本地导入副本、单侧启用、更新链路等已知行为坑，见 [references/skill-hygiene.md](references/skill-hygiene.md)。

## 定向寻找上游参考

用户明确要求“找上游参考、看看技能市场、比较其他技能”，或本次审计发现具体能力缺口时，按 [市场发现与内容比较](../agent-rules/references/skill-upstream-maintenance.md#市场发现与内容比较) 执行。比较候选的实际内容与现有技能，分点说明缺口、增量、可借鉴内容和引入成本；市场与原始仓库按同一来源去重。

普通业务任务不自动转入搜索或安装；单次定向搜索不强制运行完整目录审计或周检。发现候选、批准吸收和安装分别按现有流程处理，复用已有准确授权。

## 融合本地技能周检

需要把上游、目录健康、历史使用和疑似漏用合并成每周逐项问答时，使用
[references/weekly-review.md](references/weekly-review.md) 和
`scripts/run_weekly_skill_review.py`。它复用本 skill 的三个审计入口，不另建职责重叠的技能。

```powershell
python scripts/run_weekly_skill_review.py scan --date <YYYY-MM-DD> --json
python scripts/run_weekly_skill_review.py next-question --json
```

周检覆盖公开、私有维护源码，以 `public:<name>` / `private:<name>` 隔离同名身份。
明确用户反馈、评测缺口或来源待查可用 `scan --discovery-input <JSON>` 纳入定向研究：
每周最多三个技能，每技能最多两个候选，未入选持久顺延；零收益或受阻结论保留到出现新证据。
本地内容变化后，对登记的已吸收能力只生成待人工复核项，不用字符匹配断言行为退化。
候选来源、收益和复核结论复用现有状态与问题队列，不自动登记或改写；输入示例、私有报告位置及
复核关闭方法见上述参考文件。

周检状态写入 `<reports-root>/weekly-review-state.json`，采用跨进程锁、临时文件和原子替换。
状态损坏、未知 `schema_version` 或锁冲突只报告严重问题，保留原文件，不自动重建。finding ID
按“类型、技能、独立修改目的”稳定生成；证据、方案和源码基线 fingerprint 未变时不重复问，
变化后旧批准和相关执行批次自动失效。

每次 `next-question` 只返回一项。证据不足最多追问两条事实，随后必须关闭、形成建议或转为等待新证据。
“历史内未见使用”只有连续四个相邻、完整、同口径周窗才进入队列；扫描失败、报告无效、证据无法
关联用户请求、周窗中断、统计口径升级或该技能的激活宿主范围变化会重置连续计数。同一周重跑不会
重复累加。周窗固定为上海时区前一周六 14:00（含）到本周六 14:00（不含）。
严重问题可插队，每周最多新增三条中低优先级问题。全部逐项决定后，`prepare-execution` 只生成一次
兼容执行批次；已有准确授权时由智能体填写现有 approve 参数继续，不另问最终确认。没有批准项不创建空批次。详细的自然语言映射、隔离候选、副本哈希、精确暂存、推送和
双端同步验收见上述参考文件。

失败重试若发生在源码已提交、运行时尚未同步的阶段，只能在目标目录干净、记录提交和远端 SHA
都可验证且目标从记录提交到当前 HEAD 未再变化时，把源码 fingerprint 推进到已提交结果；否则继续
按源码漂移阻断，不能把当前目录无条件当作新基线。
执行确认绑定的同步 helper 身份同时哈希入口脚本和实现模块；文件变化使旧批次失效；先核实新工具来源与实际影响，原授权仍覆盖时内部重建，不机械地再次询问用户。

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

- 检查请求默认只读，不自动移动、归档、删除或改写任何 `SKILL.md`；明确修复请求按准确范围执行，普通审计程序本身仍只读。
- 不把源文件目录直接当成“当前已加载技能列表”。
- 不把 cc-switch 面板显示名直接当成磁盘目录名。
- 不再按旧的分层目录判断技能来源；如果发现旧目录，只当作需要人工复核的历史残留。
- 不无目标地跑市场搜索；周检只按明确缺口定向研究。也不替代 [../agent-rules/SKILL.md](../agent-rules/SKILL.md) 的规则说明角色。
- 不替代 `skill-creator` 的创建和改写工作。
- 这里保留市场安装检查脚本，但不把自己改成“自动更新器”；默认仍以只读审计为主。
- 历史使用审计不启动 daemon、实时 watcher 或常驻 dashboard 服务，不联网，不修改 transcript、技能或运行时目录；
  周检只生成可直接打开的离线 dashboard 文件。
- 不根据一次低频或无记录结论自动降级、合并、归档或删除技能。
- 周检脚本只维护观察、决定和执行批次状态；它不替用户批准、修改、提交、推送或同步技能。

## 输出

目录审计程序固定输出到 `<reports-root>`；局部诊断不强制生成全库报告。新增过程材料沿用共享规则的 `过程文件/任务主题/`，已有周检输出位置保持兼容：

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
