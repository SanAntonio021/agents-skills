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

```powershell
python scripts/audit_skill_usage.py --reports-root <reports-root> --date <YYYY-MM-DD>
```

默认只读扫描全部可用历史：Codex 的 `sessions`、`archived_sessions`，Claude 的 `projects` 和
`telemetry`；技能清单覆盖源码、Codex/Claude 运行时、lark 实体层和 Codex 插件缓存。需要隔离测试或
限定范围时，可重复传入 `--skills-root`、`--codex-sessions-root`、`--claude-projects-root` 和
`--claude-telemetry-root`；一旦传入某一类自定义根，该类默认根就不再扫描。

固定证据口径：

- Claude 仅把 `assistant.message.content[].name == "Skill"` 且 `input.skill` 非空计为实际调用。
- Claude `tengu_skill_loaded` 只是启动时候选加载，绝不计为使用。
- Codex 仅从真实用户记录里的 `$skill-name`、`/skill-name` 或技能 `SKILL.md` 链接识别显式点名。
- Codex 当前没有稳定的隐式 Skill 调用事件；报告必须写明“未见记录不等于实际未使用”。
- `疑似漏用` 只由技能名和 `description` 的确定性规则筛选，不调用模型，也不自动改技能。
- `可能冗余` 只有在传入 `--hygiene-summary` 后，才把“历史内未见使用”与已有 duplicate/overlap
  finding 求交；它仍是人工复核候选，不是删除建议。

报告固定输出到：

- `<reports-root>/usage/manifests/<date>/summary.json`
- `<reports-root>/usage/weekly/<date>.md`

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
2. cc-switch 数据库完整，目标技能在 Claude 和 Codex 两侧均已启用；
3. 技能仓库提交中的全部目标文件与 cc-switch、Claude、Codex 三个运行时副本一致；
4. 结构校验和相关确定性测试通过；
5. 用合成数据在 Codex、Claude 全新只读会话分别验证路由和关键安全边界。
6. 定向同步返回退出码 `0` 和 `runtime_active` 后，再以完全相同的 `ExpectedRemoteCommit` 与
   `Skills` 运行一次 `-VerifyOnly`；第二次也返回退出码 `0`、`runtime_active`，且四层文件集合和
   SHA-256 仍一致，才写“运行时已生效”。

工作区 SHA-256 不同不等于运行时陈旧。Windows 工作区可能是 CRLF，提交 blob 和运行时副本可能是
LF；先比较已提交 Git blob 与运行时文件字节，或明确归一化换行后再判断。

认证、余额、中转或模型服务错误若发生在技能输出前，状态只能记为“运行时验收受环境阻断”。
环境恢复后重跑同一用例；不得把这种错误记成技能失败，也不得在未重跑时记成通过。

CC Switch 定向同步返回 `update_scan_timeout` 时，记录原始 JSON、目标 commit、Skill 集合和
`clicked_skills`，状态写“更新扫描受环境阻断，运行时待验收”，不写成技能失败或同步成功。只有
`clicked_skills` 明确为空、确认尚未点击任何目标 Skill 的“更新”按钮时，才允许用同一 commit 和
同一 Skill 集合重新运行完整 helper；如果已经点击或无法确认，则不再触发 UI 更新，只做
`-VerifyOnly`，或等待用户手动定向更新后再验收。完整判据见
[references/skill-hygiene.md](references/skill-hygiene.md) 的“更新扫描超时与 UI 竞态恢复”。

## 触发分层判断

审计每个技能时问一句：**用户实际怎么调用它**。

- 用户只点名调用（`/技能名`）→ 建议加 `disable-model-invocation: true`，description 移出常驻上下文。
- 用户靠描述任务自动触发 → 保持默认，**不管它看起来多低频**。2026-07-06 实证：agent-rules 和 skill-check 看似点名场景，实际用户靠描述触发，降级会直接失效。
- 判断依据只能来自用户的真实使用习惯，不能从技能主题倒推；拿不准时问用户，不要默认降级。

cc-switch 的本地导入副本、单侧启用、更新链路等已知行为坑，见 [references/skill-hygiene.md](references/skill-hygiene.md)。

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
- 不启动 daemon、实时 watcher 或 dashboard，不联网，不修改 transcript、技能或运行时目录。
- 不根据一次低频或无记录结论自动降级、合并、归档或删除技能。

## 输出

固定输出到 `<reports-root>`：

- `manifests/<date>/summary.json`
- `weekly/<date>.md`

历史使用审计另输出到 `usage/` 子目录，使用 `已用`、`历史内未见使用`、`疑似漏用`、`可能冗余`
四个面向用户的分类；不要把内部事件名直接当结论标题。

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
