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

用户问“为什么现在没生效”时，先看目标工具实际读取的运行时，再查 cc-switch 分发层和数据库，
最后回到源码提交与远端。用户问“同步是否完整完成”时，执行下面的完整验收。

## 源码到双端运行时验收

### 1. 源码与远端

- 记录技能仓库当前分支、`HEAD` 和 `origin/<branch>`。
- 只比较目标提交中的文件，不把其他未提交改动算进验收范围。
- 源码尚未推送时，结论只能是“源码完成，运行时同步待完成”。

### 2. CC Switch 记录与启用

- 用只读方式打开 `cc-switch.db`，先运行 `PRAGMA integrity_check`。
- 核对目标技能的 `directory`、`repo_branch`、`enabled_claude` 和 `enabled_codex`。
- 数据库或面板显示启用不替代磁盘和行为验收。

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

### 4. 结构和确定性测试

Windows 上运行 Python 校验器前设置：

```powershell
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
```

否则 `Path.read_text()` 可能按 GBK 读取 UTF-8 `SKILL.md`，产生假失败。随后运行
`skill-creator/scripts/quick_validate.py` 和目标技能已有的合同测试、校验器测试。

### 5. Codex 与 Claude 行为验收

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

### 6. 失败分类与完成措辞

- 模型已输出但规则判断错误：运行时行为验收失败。
- 技能输出前出现认证、余额、预扣费、中转或模型服务错误：环境阻断，既不算通过，也不算技能失败。
- 环境恢复后必须重跑相同合成用例；成功输出后才能写“运行时验收完成”。
- 使用中转 API 时出现 `claude.ai connectors are disabled` 提示，但技能输出成功，可记录为非阻断提示。

### 7. 更新扫描超时与 UI 竞态恢复

定向同步 helper 返回 `update_scan_timeout` 时，先保留完整 JSON，并记录
`ExpectedRemoteCommit`、精确 `Skills` 集合、失败阶段和 `clicked_skills`：

- 结论固定为“更新扫描受环境阻断，运行时待验收”；不把超时判成 Skill 失败、同步失败或同步成功。
- 恢复时不得更换 commit、增删 Skill、改用“全部更新”，也不得直接修改数据库或运行时目录。
- `clicked_skills` 明确为空且失败发生在扫描阶段时，说明尚未点击任何目标 Skill 的“更新”按钮；可用
  完全相同的 commit 和 Skill 集合重新运行一次完整 helper。这是重新执行扫描流程，不是重复点击目标更新。
- `clicked_skills` 非空、字段缺失或无法确认是否已经点击时，不再触发 UI 更新。先用完全相同的参数运行
  `-VerifyOnly`；若仍未对齐，由用户在 CC Switch 手动定向更新后再运行 `-VerifyOnly`。
- 恢复记录必须同时保留首次超时证据和后续验收证据，不能用后一次成功覆盖前一次异常。

最终生效必须同时满足：定向同步 helper 退出码为 `0`、状态为 `runtime_active`；随后使用完全相同的
`ExpectedRemoteCommit` 与 `Skills` 执行 `-VerifyOnly`，退出码也为 `0`、状态也为 `runtime_active`；
两次结果中的提交身份、目标集合、四层文件集合和 SHA-256 均一致。任一条件缺失时，只能写“源码已推送，
运行时未生效”或“运行时待验收”。

## CC Switch SSOT 报错

当 CC Switch 安装 skill 时弹出 `Skill 不存在于 SSOT: <skill-name>`，不要先判断 GitHub 仓库坏了。常见原因是面板仓库索引和本地 SSOT 记录不同步，尤其是远端默认分支已切到 `main`，但 `skills.repo_branch` 里还残留 `master`。

先只读确认：

1. 查 `C:\Users\SanAn\.cc-switch\cc-switch.db`。
2. 对照 `skill_repos.branch` 和远端默认分支。
3. 对照 `skills.name`、`skills.directory`、`skills.repo_owner`、`skills.repo_name`、`skills.repo_branch`。
4. 如果界面出现重复卡片，区分正常目录和 `*-workspace\iteration-*` 这类临时目录。

如果确认是本地 SSOT 分支残留，安全处理顺序是：

1. 备份 `cc-switch.db` 和 `settings.json`。
2. 关闭 `cc-switch.exe`。
3. 只做最小数据库修复，例如把对应 `skills.repo_branch` 从旧分支改成当前真实分支，并同步修正 `readme_url`。
4. 重启 CC Switch。
5. 复查 `skills` 表和日志，确认没有新的 `Skill 不存在于 SSOT`。

实证案例：`SanAntonio021/agents-skills` 远端默认分支为 `main`，但 `chat-notes` 和 `paper-summary` 在 `skills` 表里残留 `master`；修正为 `main` 后，`chat-notes` 安装恢复正常。

## cc-switch 已知行为与坑（2026-07-06 实证）

审计时把这五条当固定检查项：

1. **本地导入会产生未启用副本**。cc-switch 的本地技能导入会把 `%USERPROFILE%\.agents\skills\` 这类目录的实体整体复制进 `C:\Users\SanAn\.cc-switch\skills\`，导入后不建运行时链接、不启用。实证：2026-07-05 22:09 一次导入复制了 24 个 lark 实体（含已裁剪的 5 个开发者向和孤儿 lark-note）。审计时对比 `.cc-switch\skills\` 与各运行时目录，找出"存在但未链接"的副本；普通清理优先走 cc-switch GUI 卸载，不要只删目录（会与 `cc-switch.db` 失配）。
2. **安装时按 app 单独勾选启用，可能只启用单侧**。实证：latex-paper 2026-07-06 安装时只勾了 Claude，`.claude\skills\` 有链接、`.codex\skills\` 没有。审计时必须同时核对 `C:\Users\SanAn\.claude\skills` 和 `C:\Users\SanAn\.codex\skills` 两侧链接是否对齐，不能只查 Codex 一侧。
3. **技能更新没有自动拉取**。`settings.json` 无技能自动更新选项（截至 2026-07-06 版本，`skillSyncMethod: symlink`），源码 push 后每台设备都要手动点一次"检查更新"。"源码已改但没生效"的第一排查项就是这个。
4. **只改子文件可能不触发更新识别**。2026-08-10 本机实测：提交 `3f967ce` 只改了 `chat-notes/references/skill-edit-followup.md` 和 `chat-notes/evals/evals.json`，两次“检查更新”均未出现 `chat-notes` 更新；提交 `c9e36c0` 增加有实际含义的 `chat-notes/SKILL.md` 入口后，日志在 12:07:32 记录 `Skill chat-notes 更新成功`。这只证明当时本机客户端和该仓库的现象，不据此断言所有版本的内部机制。会改变运行行为的 `references/`、`scripts/` 等子文件应同步在 `SKILL.md` 暴露对应语义；纯 eval 或不影响运行行为的说明不要制造空格、注释、无意义版本号等伪改动。诊断按顺序执行：确认远端提交包含目标文件；检查 `SKILL.md` 是否有对应语义变化；在日志中查本轮目标技能“更新成功”；更新后枚举提交内全部技能文件并比较 CC Switch、Claude、Codex 三层副本；最后用全新只读会话验证行为。
5. **Lark 技能以 `lark-cli skills` 为主来源**。飞书文档、云盘、日历等 Lark 操作最终调用 `lark-cli`，cc-switch 保存的 `lark-*` 只是另一份技能说明副本。用户明确要让 Lark 技能只走 `lark-cli` 时，清理顺序是：先备份 `C:\Users\SanAn\.cc-switch\cc-switch.db` 和 `settings.json`；再从 `skills` 表删除 `lark-*` 记录，并从 `skill_repos` 删除 `larksuite/cli`；再删除 `C:\Users\SanAn\.cc-switch\skills\lark-*` 目录和运行时目录里指向它们的软链接；最后验证 `PRAGMA integrity_check = ok`、cc-switch 与运行时目录里 `lark-* = 0`、`lark-cli skills list` 和 `lark-cli skills read lark-doc` 仍正常。不要删除 `%USERPROFILE%\.agents\skills\lark-*` 或 `lark-cli` 本体。

日志位置：`C:\Users\SanAn\.cc-switch\logs\cc-switch.log`（含安装/更新/导入记录，可按日期定位操作）。

## SSOT 记录残留与批量清理

如果面板显示技能“已安装”，但点击启动/同步时报 `Skill 不存在于 SSOT`，先把它和分支问题分开：

1. 根据 `settings.json` 的 `skillStorageLocation` 确定 SSOT 根目录。
2. 对每条 `skills` 记录检查 `<SSOT 根目录>/<directory>/SKILL.md`。
3. 目录或 `SKILL.md` 缺失时，这是数据库残留记录；不是 Codex 配置问题，也不能只看面板显示名判断已安装。
4. 批量处理前先列出所有残留目录并让用户确认范围。只清理确认过的 `skills` 行，保留 `skill_repos`，不要直接删除运行时目录。
5. CC Switch 无法关闭时，可用 SQLite 在线备份接口生成一致备份；随后用 `BEGIN IMMEDIATE` 执行短事务删除，提交后检查 `PRAGMA integrity_check`，再复查 SSOT 和 Codex 运行时目录。

本 skill 仍只做只读审计；以上是用户明确批准后供维护者执行的最小修复顺序。

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
