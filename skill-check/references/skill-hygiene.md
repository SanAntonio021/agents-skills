# Skill Hygiene

## Purpose

维护本地 skill 环境的一致性，避免把“源文件目录”“cc-switch 同步出来的目录”“Codex 实际读取的技能目录”混成一层，最后查不清到底哪里出了问题。

## 本地目录方案

当前本地源文件目录用一层平铺的方式存放技能：

```text
D:\BaiduSyncdisk\.agents\skills\<skill-name>\SKILL.md
```

判断规则：

- 顶层目录里有 `SKILL.md`，就算一个源技能。
- 顶层目录里没有 `SKILL.md`，不算技能。
- `*-workspace`、`rescued-skill-materials` 这类目录只当作工作材料或历史材料。
- 目录名必须和 `SKILL.md` 里的 `name:` 一致。

## 要分清的六层

在这台机器上，排查 skill 问题时默认分清六层：

1. `D:\BaiduSyncdisk\.agents\skills`
   自建技能源码仓库。真正应该修改和提交的地方，但不是当前已加载列表。
2. `C:\Users\SanAn\.agents\skills`
   Lark 技能实体层；新版 Codex CLI 还会直接读取这一层。
3. `C:\Users\SanAn\.cc-switch\skills`
   CC Switch 的分发层。这里更新不代表 Claude、Codex 两侧都已启用。
4. `C:\Users\SanAn\.claude\skills`
   Claude 运行时入口，多数自建技能链接到 CC Switch 分发层。
5. `C:\Users\SanAn\.codex\skills`
   Codex 运行时入口；还要区分 `.system` 内置技能。
6. `C:\Users\SanAn\.codex\plugins\cache`
   Codex 插件自带技能层，可能与用户技能出现同名入口。

`C:\Users\SanAn\.cc-switch\cc-switch.db` 是记录层，不单独算技能目录，但必须核对
`directory`、仓库分支和各运行时的启用状态。

## 什么算当前已加载

- 查 Claude 时，以 `C:\Users\SanAn\.claude\skills` 的实际入口为准。
- 查 Codex 时，同时看 `C:\Users\SanAn\.codex\skills`、`.system`、插件缓存和直读的 Lark 实体层。
- 源码目录和 cc-switch 分发目录只是证据，不能直接拿来报“当前已加载”或“当前冲突”。
- cc-switch 面板显示名不等于磁盘目录名；已分发但单侧未启用时，另一侧运行时可能没有入口。

## 插件技能重叠的选择性处理

插件是能力包，不等于其中任意一个 `SKILL.md`。发现插件技能与本地技能同题或同名时，按以下顺序处理：

1. 分开列出插件内的技能、连接工具、MCP、hooks 和其他能力，并标明哪些能力在本地技能中没有替代项。
2. 根据触发范围、输入对象、执行方式和产物判断是否真正重叠；只处理职责重复的入口，不因同属一种文件格式或主题就认定整包重复。
3. 对当前插件版本先做一次性配置覆盖，并用 `codex debug prompt-input` 比较基线和对照。停用目标必须是版本化的精确绝对 `...\skills\<name>\SKILL.md` 路径；基线与目录路径、通配符等负对照的技能身份集合必须一致，精确对照必须严格等于基线只删除目标身份。
4. 插件仍提供独有的实时控制或连接工具时，保持插件启用，只停用已证明重复的技能。无法证明精确停用后独有能力仍在时，返回延期状态并零写入；不得退化为关闭或卸载整个插件。
5. 保留配置所有权。CC Switch 管理 Common Config 和 provider 时，通过对应所有者保存目标；不直接写生成的 `.codex/config.toml`、插件缓存、运行时技能目录或数据库。启用 Common 且没有本地目标的 provider 继续继承；未启用 Common 或已有本地覆盖的 provider 才维护自身目标。
6. 精确路径随插件版本变化。版本更新后重新发现路径、重做正负能力探针并迁移受管条目；仅清理由台账证明是本流程新增的条目，来源不明或预先存在的配置不动。
7. 完成状态至少分开记录配置、目录、运行时和保留能力。只看到配置写入成功、界面开关正确或提示目录变化，都不能替代真实能力 canary；保留能力对任务重要时，必须在隔离、可回滚的真实对象上完成最小 canary 并清理。
8. 记录本轮提示输入的实际字符或 token 差值，但不承诺固定节省。目录删去一个技能后可能重新分配描述截断预算，主要收益也可能只是减少路由竞争。
9. 变更命令超时后先只读检查目标状态，再决定是否重试；已经生效的写操作不能因回执超时而重复执行。

表格案例：本地 `xlsx` 处理独立 XLSX/CSV 文件，官方 `excel-live-control` 处理已打开的 Excel、当前选区和连接会话。若官方通用表格技能与本地 `xlsx` 重复，应保留官方插件、live-control 和连接文档工具，只精确停用当前插件版本内的通用表格 `SKILL.md`；最后用真实 Excel 会话验证写入、公式读回、格式、清理和不保存关闭。

## 主要问题类型

- `真冲突`
  两个或多个当前会用到的技能里，`SKILL.md` 的 `name:` 一样或归一化后一样。
- `名字不一致`
  目录名、数据库里的 `directory`、数据库里的显示名，和 `SKILL.md` 里的 `name:` 对不上。
- `链接或路径失效`
  文本里的本地路径或相对引用已经失效。
- `目录结构问题`
  skill 放在不该放的位置，或工作区、历史材料、说明材料里混入了 `SKILL.md`。
- `空技能或坏技能`
  缺 `SKILL.md`、文件开头配置为空、正文为空。

## 检查顺序

用户问单个技能“为什么现在没生效”时，先看目标工具实际读取的运行时，再查该技能的 CC Switch 分发、必要元数据和源码提交。局部诊断直接读取目标材料，不默认运行全库目录、全部会话历史或上游扫描。用户明确要求目录健康或历史统计时才使用对应审计；既有周检的范围与输出不变。

日志或元数据提示仓库级影响时，可只读检查关联条目并说明扩查原因；读取关联信息不增加修复授权。只读请求交付结论与建议；已有准确修复授权时，通过受支持后台接口继续。源码修改与发布复用 [agent-rules](../../agent-rules/SKILL.md) 的当前流程，不复制界面、数据库或运行目录修复处方。

用户问“同步是否完整完成”时，对准确目标执行下面的完整验收。

## 源码到双端运行时验收

### 1. 源码与远端

- 记录技能仓库当前分支、`HEAD` 和 `origin/<branch>`。
- 只比较目标提交中的文件，不把其他未提交改动算进验收范围。
- 源码尚未推送时，结论只能是“源码完成，运行时同步待完成”。

### 2. CC Switch 记录与启用

- 用只读方式打开 `cc-switch.db`，先运行 `PRAGMA integrity_check`。
- 核对目标仓库在 `skill_repos` 中只有一条有效记录，`branch` 与远端目标分支一致且 `enabled = 1`。
- 有仓库级阻断线索、或现有定向 helper 为完整验收检查仓库一致性时，只读核对同仓库关联记录的 `repo_branch` 和 `readme_url`。历史上兄弟技能旧分支曾导致错误压缩包请求；按当前日志核实，保持精确更新集合。
- 核对每个目标技能在 `skills` 中只有一条记录；`name`、`directory`、`repo_owner`、`repo_name`、
  `repo_branch`、`readme_url`、`enabled_claude` 和 `enabled_codex` 都必须与预期源码和目标分支一致。
- 文件已经对齐只证明当前副本相同。旧分支、旧 `readme_url` 或错误启用状态会破坏后续更新，仍属于
  元数据验收失败；数据库或面板显示启用也不替代磁盘和行为验收。

### 3. 比较全部已提交文件

逐个读取 `git ls-tree -r --name-only HEAD -- <skill-name>` 的结果，并把提交 blob 与三个
分发/运行时根目录下的对应文件比较：

- `C:\Users\SanAn\.cc-switch\skills`
- `C:\Users\SanAn\.claude\skills`
- `C:\Users\SanAn\.codex\skills`

Git blob 比较可使用：

```powershell
$expected = git -C $repo rev-parse "HEAD:$relativePath"
$actual = git hash-object --no-filters -- $runtimeFile
```

不要只比较工作区 SHA-256。Windows 工作区可能保存为 CRLF，Git 提交和运行时副本可能是 LF；
这会造成工作区哈希不同，但提交 blob 与运行时文件完全一致。先排除换行差异，再判断同步是否漂移。

### 4. 合法本机文件的精确声明

只有同时满足以下条件，才把运行时额外文件认定为合法本机文件：

- 它是该 Skill 明确需要、且按设计不进入 Git 的本机私有配置或状态文件；
- 已核对目标提交没有跟踪该路径，文件也不属于应发布的源码；
- 路径精确到单个文件并属于本次请求的 Skill，不使用通配符、目录或跨 Skill 路径。

调用定向同步 helper 时，通过 `-ExpectedRuntimeLocalFiles "web-access/config.env"` 逐项声明。
声明只把该路径从运行时文件集合比较中排除；helper 不读取、散列、复制或修改文件内容，并会拒绝
目标提交已经跟踪的路径。完整同步与后续 `-VerifyOnly` 必须使用完全相同的声明。任何未声明的额外
文件仍然是漂移，不能因为某个 Skill 有一处合法本机配置就忽略它的全部额外文件。

### 5. 结构和确定性测试

Windows 上运行 Python 校验器前设置：

```powershell
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
```

否则 `Path.read_text()` 可能按 GBK 读取 UTF-8 `SKILL.md`，产生假失败。随后先列明目标 Skill 实际面向
哪些运行时，再把 frontmatter 分成通用字段和目标运行时扩展，分别验收：

1. `skill-creator/scripts/quick_validate.py` 继续作为 Agent Skills / OpenAI 通用格式的严格检查。`name`、
   `description` 等通用字段不合格时直接阻断；不要为了通过检查而修改上游校验器。
2. 如果严格检查唯一拒绝的是目标运行时官方文档明确支持的扩展字段，分别报告“通用格式不兼容”和
   “目标运行时扩展有效”，不能把它们合并成“整个 Skill 无效”，也不能删掉扩展字段制造假通过。
3. `disable-model-invocation` 是 Claude Code 的调用控制字段，只能据此判断 Claude 的发现和调用行为。
   同一 Skill 供 Codex 使用时，必须在全新 Codex 会话中单独验证；没有 Codex 证据时不能声称它会隐藏
   description、禁止自动调用或实现“仅用户点名”。若成功标准要求 Claude、Codex 都只能由用户点名，
   Codex 侧未验证就仍是未完成。
4. 不在目标运行时官方文档中的未知字段仍按结构失败处理，不能套用“运行时扩展”名义放行。

判据以 [Agent Skills 规范](https://github.com/agentskills/agentskills/blob/main/docs/specification.mdx)、
[OpenAI skill-creator](https://github.com/openai/skills/blob/main/skills/.system/skill-creator/SKILL.md) 和
[Claude Code Skills 文档](https://code.claude.com/docs/en/skills) 为准；目标技能已有的合同测试、校验器
测试仍要运行。最终报告至少把“通用格式”“Claude”“Codex”三项状态分开，不用一项结果替代另外两项。

### 6. Codex 与 Claude 行为验收

只使用合成数据，不登录、不上传、不发送、不点击最终动作、不修改项目文件。每个场景使用全新会话：

```powershell
codex exec --ephemeral --sandbox read-only -C <trusted-root> -
claude -p --no-session-persistence --permission-mode plan --no-chrome
```

至少验证：

- 自动路由选择正确技能；
- 用户显式点名入口时不被另一入口覆盖；
- 旧兼容入口能独立完成自己的流程；
- 人工确认门和禁止代点最终动作仍生效。

### 7. 失败分类与完成措辞

- 模型已输出但规则判断错误：运行时行为验收失败。
- 技能输出前出现认证、余额、预扣费、中转或模型服务错误：环境阻断，既不算通过，也不算技能失败。
- 环境恢复后必须重跑相同合成用例；成功输出后才能写“运行时验收完成”。
- 使用中转 API 时出现 `claude.ai connectors are disabled` 提示，但技能输出成功，可记录为非阻断提示。

### 8. 后台恢复与验收

后台入口、备份、重试与恢复以 [agent-rules 的定向发布流程](../../agent-rules/references/skill-upstream-maintenance.md) 为准。保持同一提交、精确 Skill 集合和本机文件声明；失败时先保留 JSON 回执和阶段信息，再只读核验实际状态，不为追求成功而扩大更新范围。

按该流程执行的后台更新与随后 `-VerifyOnly` 均须退出 `0`、返回 `runtime_active`，且 `cc_switch_metadata.valid = true`、问题为空，目标文件集合、哈希、来源和启用状态一致。缺少核验时报告具体未完成部分，不把单步成功当作完整生效。

只要求核验，或用户已明确自行完成恢复时，固定参数直接运行 `-VerifyOnly`，不额外执行更新写入。有效核验通过后结束，有失败、变化或未解决问题再复查。核验只能确认当前状态，不能推断具体哪次历史操作使其生效。

旧回执的 `update_scan_timeout`、`clicked_skills` 和 `skills_page_blocked_by_restore` 描述当时 UI 流程的超时或窗口阻挡，保留为历史事实，不再作为点击、关闭弹窗或重跑旧界面的依据。当前后台能力不足时说明缺口，只暂停该项；不强关 CC Switch、不手工写数据库或修改运行目录。

## CC Switch SSOT 报错与单技能元数据残留

当 CC Switch 安装 skill 时弹出 `Skill 不存在于 SSOT: <skill-name>`，不要先判断 GitHub 仓库坏了。常见原因是面板仓库索引和本地 SSOT 记录不同步，尤其是远端默认分支已切到 `main`，但 `skills.repo_branch` 里还残留 `master`。

先只读确认：

1. 查 `C:\Users\SanAn\.cc-switch\cc-switch.db`。
2. 对照 `skill_repos.branch` 和远端默认分支。
3. 对照 `skills.name`、`skills.directory`、`skills.repo_owner`、`skills.repo_name`、`skills.repo_branch`。
4. 如果界面出现重复卡片，区分正常目录和 `*-workspace\iteration-*` 这类临时目录。
5. 如果目标技能已经是当前分支，但日志仍请求同仓库旧分支的 ZIP，按 `repo_owner` 和 `repo_name` 枚举全部兄弟技能；不要只复查目标行。

如果确认已安装技能的来源或启用元数据残留，按以下顺序处理：

1. 记录目标技能、预期仓库、真实分支、远端提交和双端启用状态；只读核对目标运行副本的本机私有文件及恢复要求。
2. 只检查的任务交付发现和建议。已有准确修复授权时，核实当前受支持后台接口能否完成对应字段或条目操作，以及备份与非目标保护。
3. 能完成时通过该接口定向修复，并按上述流程验证。不能完成、私有文件保护不足或发生并发变化时保留该项，说明具体限制，不把“更新成功”当作元数据必然修复。
4. 不以手工数据库变更、强关应用、界面重装或手工删运行目录兜底；用户后续自行处理后可只读核验当前状态。

多个技能、重复仓库记录、SSOT 文件缺失或行归属不清时，先列出完整关联范围。修复复用准确授权；未覆盖的新增条目只读报告。仓库级阻断未解除时如实保留未完成状态，不把只修当前目标表述为整仓已恢复。

实证案例：`SanAntonio021/agents-skills` 远端默认分支为 `main`，但 `chat-notes` 和 `paper-summary` 在 `skills` 表里残留 `master`；修正为 `main` 后，`chat-notes` 安装恢复正常。后续单技能案例进一步确认：在文件副本已经一致、目标记录仍残留旧分支时，定向卸载并从真实分支重新安装可以同时恢复分支、`readme_url` 和双端启用元数据；完成结论仍以重装后的完整只读验收为准。

## cc-switch 已知行为与坑（2026-07-06 实证）

以下是历史观察，按当前问题选取相关项核实，不固定扩大每次检查：

1. **本地导入曾产生未启用副本**。2026-07-05 22:09 一次导入从 `%USERPROFILE%\.agents\skills\` 复制了 24 个 lark 实体到 CC Switch（含当时已裁剪的 5 个开发者向和孤儿 lark-note），未建立运行时链接或启用。相关诊断应对照分发与运行目录；准确授权下只用受支持后台接口处理条目，不手工删除目录。
2. **安装时按 app 单独勾选启用，可能只启用单侧**。实证：latex-paper 2026-07-06 安装时只勾了 Claude，`.claude\skills\` 有链接、`.codex\skills\` 没有。审计时必须同时核对 `C:\Users\SanAn\.claude\skills` 和 `C:\Users\SanAn\.codex\skills` 两侧链接是否对齐，不能只查 Codex 一侧。
3. **当时源码推送未触发自动更新**。2026-07-06 版本的 `settings.json` 未见技能自动更新选项，采用 `skillSyncMethod: symlink`；当时通过手动检查更新激活。现行流程使用后台定向发布，各设备是否生效按实际核验结果说明。
4. **只改子文件可能不触发更新识别**。2026-08-10 本机实测：提交 `3f967ce` 只改了 `chat-notes/references/skill-edit-followup.md` 和 `chat-notes/evals/evals.json`，两次“检查更新”均未出现 `chat-notes` 更新；提交 `c9e36c0` 增加有实际含义的 `chat-notes/SKILL.md` 入口后，日志在 12:07:32 记录 `Skill chat-notes 更新成功`。这只证明当时本机客户端和该仓库的现象，不据此断言所有版本的内部机制。会改变运行行为的 `references/`、`scripts/` 等子文件应同步在 `SKILL.md` 暴露对应语义；纯 eval 或不影响运行行为的说明不要制造空格、注释、无意义版本号等伪改动。诊断按顺序执行：确认远端提交包含目标文件；检查 `SKILL.md` 是否有对应语义变化；在日志中查本轮目标技能“更新成功”；更新后枚举提交内全部技能文件并比较 CC Switch、Claude、Codex 三层副本；最后用全新只读会话验证行为。
5. **Lark 技能以 `lark-cli skills` 为主要能力包，但本地条目不是自动冗余**。飞书文档、云盘、日历等操作最终由 `lark-cli` 执行；各 `lark-*` 条目同时承担宿主发现、触发边界和操作说明。2026-09-01 用户已决定整包保留 27 个 Lark 技能，不增加本地路由，也不停用、卸载或删除；连续四周未见调用不能单独重开这个决定。只有用户以后明确改为“只保留 CLI”、宿主出现技能省略警告，或实测发生触发退化时，才重新复核。后续若明确授权调整，先核对当前安装归属与后台接口，保留 Lark 实体和 CLI 独有能力；不沿用手工删数据库记录及运行目录的旧处方。

日志位置：`C:\Users\SanAn\.cc-switch\logs\cc-switch.log`（含安装/更新/导入记录，可按日期定位操作）。

## SSOT 记录残留与批量清理

如果面板显示技能“已安装”，但点击启动/同步时报 `Skill 不存在于 SSOT`，先把它和分支问题分开：

1. 根据 `settings.json` 的 `skillStorageLocation` 确定 SSOT 根目录。
2. 对每条 `skills` 记录检查 `<SSOT 根目录>/<directory>/SKILL.md`。
3. 目录或 `SKILL.md` 缺失时，这是数据库残留记录；不是 Codex 配置问题，也不能只看面板显示名判断已安装。
4. 只读列出实际残留及影响范围，修复沿用准确授权，未覆盖条目不自动处理。
5. 通过受支持后台接口备份并操作精确条目，保留非目标仓库记录、技能和私有文件；随后核对完整性、元数据、SSOT 与目标运行副本。接口不支持该类残留修复时报告受阻，不绕过接口改数据库或删目录。

审计保持只读；用户明确要求修复时按上述范围完成支持的后台操作。不能完成的部分单独说明，不阻塞独立事项。

## 常见错误

- 把源文件目录当成当前已加载 skill 列表
- 把 cc-switch 面板显示名当成磁盘目录名
- 看到 cc-switch 同步出来的目录更新了，就以为 Codex 已经会用
- 把“名字不一致”直接说成“运行时冲突”
- 没先看 Codex 实际读取的技能目录，就开始猜 GitHub 没更新
- 看到 CC Switch 面板能搜到 skill，就忽略 `cc-switch.db` 里旧分支或旧目录残留

## 汇报顺序

汇报时优先按这个顺序说：

- 当前实际会用到的技能
- 真冲突
- 名字不一致
- 链接或路径失效
- 空技能或坏技能
- 建议动作

## 维护

- 本文件只定义“怎么排查 skill 层级和同步链路”，不定义单个 skill 的业务规则。
- 如果路径、同步方式或启用链路变了，先更新这份文件和脚本，再改 `SKILL.md`。
