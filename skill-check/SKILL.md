---
name: skill-check
description: 检查本地技能目录，确认 Claude/Codex 实际读取哪些技能，发现目录结构问题、重复或可合并技能、名字不一致、链接失效、空技能或坏技能，以及源码已改但 cc-switch/运行时目录还没同步的问题。Use when 用户要确认当前加载了哪些 skill、查同名冲突（含 Codex 内置 .system 技能与 cc-switch 版重名）、判断技能是否该合并、检查目录名和 `name:` 是否一致、分清 GitHub 源码、lark 实体层、cc-switch 同步目录和 Claude/Codex 实际读取的技能目录、排查 CC Switch 安装报 `Skill 不存在于 SSOT`、确认“已经改了为什么没生效”，或做只读盘点；prefer this over `agent-rules` when 目标是执行一次具体审计，而不是阅读维护规则。
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
   - 查“当前真的加载了哪些 skill”时，优先看 Codex 实际读取的技能目录。
   - 查“面板里更新了，为什么没生效”时，再看 cc-switch 同步出来的目录和 `cc-switch.db`。
   - 查 CC Switch 安装红框 `Skill 不存在于 SSOT` 时，在 `cc-switch.db` 里对照 `skill_repos.branch`、`skills.repo_branch`、`skills.directory` 和远端默认分支；详细步骤见 [references/skill-hygiene.md](references/skill-hygiene.md)。
   - 如果技能条目显示“已安装”但启动/同步时报 `Skill 不存在于 SSOT`，还要核对 SSOT 下 `<directory>\SKILL.md` 是否真实存在；这通常是数据库残留记录，不要直接改 Codex 运行时目录。
   - 查“源码已经改了 / Claude 改完了 / 为什么 Codex 还是旧行为”时，同时比较源码、cc-switch 目录和 Codex 运行时目录的 `SKILL.md` hash 或关键行。
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
  指 `D:\BaiduSyncdisk\.agents\skills\<skill-name>\SKILL.md` 已经更新，但 `C:\Users\SanAn\.cc-switch\skills\<skill-name>\SKILL.md` 或 `C:\Users\SanAn\.codex\skills\<skill-name>\SKILL.md` 仍是旧版本。遇到这种情况，结论写成“源码已修，当前 Codex 仍未加载新版本”，并提醒用户通过 cc-switch 检查更新，不要直接改 `.cc-switch` 或 `.codex`。
- `链接或路径失效`
  指绝对路径、相对链接、Related Skills 链接或工作流引用失效。
- `空技能或坏技能`
  指缺 `SKILL.md`、文件开头配置为空、正文为空，或关键结构损坏。

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
- [scripts/manage_market_skills.ps1](scripts/manage_market_skills.ps1)
- [scripts/run_codex_skill_ecosystem_audit.py](scripts/run_codex_skill_ecosystem_audit.py)

## 边界

- 只读审计，不自动移动、归档、删除或改写任何 `SKILL.md`。
- 不把源文件目录直接当成“当前已加载技能列表”。
- 不把 cc-switch 面板显示名直接当成磁盘目录名。
- 不再按旧的分层目录判断技能来源；如果发现旧目录，只当作需要人工复核的历史残留。
- 不自动跑市场搜索，也不替代 [../agent-rules/SKILL.md](../agent-rules/SKILL.md) 的规则说明角色。
- 不替代 `skill-creator` 的创建和改写工作。
- 这里保留市场安装检查脚本，但不把自己改成“自动更新器”；默认仍以只读审计为主。

## 输出

固定输出到 `<reports-root>`：

- `manifests/<date>/summary.json`
- `weekly/<date>.md`

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
