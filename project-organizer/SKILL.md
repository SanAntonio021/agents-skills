---
name: project-organizer
description: 整理多个相关的本机项目目录、备份或旧版本，支持同项目合并、独立项目分组、迁移验收与旧路径退役。先盘点真实文件和 Git 恢复依据，按当前明确范围执行；普通单文件操作、单仓库分支整理和整盘清理使用对应能力。
compatibility: Windows PowerShell 5.1+, Git for Windows; execution supports local drive-letter paths only.
---

# Project Organizer

把多处项目内容整理成可审计、可恢复的长期工作区。先盘点再执行。发现目录不等于授权搬动；当前请求已明确包含迁移与退役时可一起复用，未包含的动作不扩展。

## 两种模式

- `merge`：多个来源属于同一个逻辑项目。文件按目标相对路径合并，完全重复只保留一个目标，同一目标的不同内容进入 `hold_conflict`。
- `group`：多个来源是独立但同类的项目。每个来源整体进入共同父目录下独立的 `target_name`，项目之间不混合。

按请求与项目事实确定模式，只有实质歧义才询问。不能仅凭目录名相似自动把独立项目合并。

## 流程

1. 读取项目规则、明确路径、现有目标和约束；只搜索与当前任务相关的根目录。显式调用 `ask-first` 时按它澄清，不自动加载。
2. 盘点来源、目标、重复、冲突、文件哈希和 Git 状态，形成可读目标树与迁移动作。可复用已明确的目录设计，无需单独先批准树才能准备计划。
3. 为涉及 Git 的来源准备并验证恢复 bundle。正式计划按共享规则互审并确认；一次准确授权可覆盖已展示的目录树、迁移和退役范围。
4. 智能体将该授权绑定工具生成的哈希，运行迁移和验收；无需用户粘贴内部哈希。出现变化时重新核实是否影响授权，不把哈希变化本身等同于新决定。
5. 只对已纳入范围并通过迁移验收的来源建立退役清单。退役按已有授权执行，未授权时再询问；不清空整个回收站。
6. 更新确有必要的现有入口说明，保留历史证据。

## 命令

所有命令使用 Windows PowerShell 5.1：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass `
  -File <script> -Config <config.json> -OutputDir <run-dir>
```

按顺序调用：

```text
Find-ProjectCandidates.ps1
Build-ProjectInventory.ps1
New-GitRecoveryBundle.ps1
Build-OrganizationPlan.ps1
Invoke-OrganizationPlan.ps1
Test-OrganizationAcceptance.ps1
Build-RetirementPlan.ps1
Invoke-RetirementPlan.ps1
Test-RetirementAcceptance.ps1
```

迁移执行必须同时提供：

```powershell
-ApprovedPlanSha256 <64-hex> -Execute
```

退役执行必须同时提供：

```powershell
-ApprovedRetirementSha256 <64-hex> -Recycle
```

没有 `-Execute` 或 `-Recycle` 时只做预检。终端或工具超时不等于子进程停止：先在不重启命令的情况下重复读取状态文件和 JSONL 日志，比较 `LastWriteTimeUtc`、完成动作数和日志行数；只要仍在变化就继续等待。确认相关进程已退出且连续两次观察均无变化后，才对原输出目录和未变化的计划增加 `-Resume`；不得手工补写状态或并行重跑。

## 目录和映射规则

- `merge` 默认把来源相对路径直接映射到目标；显式 `mapping_rules` 可做前缀替换。
- `group` 固定映射为 `<target_root>/<target_name>/<relative_path>`。
- `group` 保持每个项目内部结构，不接受 `mapping_rules`，也不自动平铺项目内容。
- 已存在目标参与盘点，禁止覆盖。哈希相同登记为目标重复；不同则 `hold_conflict`。
- 默认保持目录关系。目录重构必须先形成可读目录树，再由用户批准；`mapping_rules` 只是批准后执行该设计的表达。
- 资料型项目主动提出浅层方案：经批准的常用交付物可放目标根目录，其他日常资料原则上只保留一层短分类。不要保留仅起套壳作用的 `platform`、`shared` 等泛化层。
- 代码、独立 Git 项目、论文、实验、原始数据、结果数据和 `migration`/审计记录可以保留完成工作所需的内部层级。
- 资料型项目的可选布局参考见 [references/material-layout.md](references/material-layout.md)。它只提供设计原则和脱敏示例，不是固定模板；一级分类、语言和深度仍须按当前项目重新设计并审批。
- 搜索根、来源、目标和审计目录必须解析为绝对路径；执行阶段只允许本机盘符路径。
- 来源之间、来源与目标之间不得嵌套。路径穿越、通配符和未解析环境变量均停止。

### `merge` 目录设计确认

按 `ask-first` 一次只问一个最关键问题，确认以下事项；用户已明确的内容直接记录：

- 哪些常用文件放目标根目录。
- 一级分类的名称和语言。
- 普通资料允许的最大层级。
- 哪些代码、论文、实验或其他子项目必须保持独立。
- 多个版本全部保留，还是只保留用户批准的版本。
- 本次迁移是否包含目录重构。

`approved_selection` 只决定哪些版本处于日常位置，不授权丢弃其他唯一文件。未选作当前版本的内容仍须进入用户批准的归档路径，或保持 `hold` 等待裁决；不得从盘点和目标树中静默省略。

盘点输出 `target-tree.md`、`target-tree.csv`、`target-tree.sha256` 和 `layout-violations.csv`。哈希用于锁定实际内容；智能体依据本轮准确授权填写 `layout_decisions.approved_tree_sha256`，不要求用户复制哈希。目录组成、范围或风险实质变化时才重新询问。

完整配置和清单字段见 [references/config-and-manifests.md](references/config-and-manifests.md)。

## 文件迁移规则

- 每个稳定文件必须有 SHA256。哈希前后复查大小和 UTC 修改时间；变化则作废。
- 同盘使用“记录、移动、复验”；跨盘使用目标目录内临时文件、复验、原子改名。
- 复制需求加 20% 余量。空间不足时不执行。
- 不覆盖现有文件，不自动按修改时间选版本，不静默丢弃冲突。
- 缓存和临时文件只按显式规则分类；删除仍进入独立退役清单。
- 云端占位、未支持的重解析点、加密/稀疏文件、多硬链接和无法安全处理的特殊流进入 `hold`。

Windows 路径、回收站和云端规则见 [references/windows-safety.md](references/windows-safety.md)。

## Git 规则

- 每个来源仓库分别保存，不自动拼接历史。
- 保存本地/远端引用、tag、stash 和 reflog 提交；dirty、staged、untracked 状态写入清单。
- bundle 必须通过 `git bundle verify`，在隔离目录恢复后运行 `git fsck --full` 并检查记录的提交。
- `merge` 由配置指定一个现役来源、已有目标仓库或新仓库。
- `group` 保留各项目独立仓库。目标位于同步目录时，活动 Git 数据库必须放到 `external_git_root`，工作区只保留 `.git` 指针。
- `.git-backup` 等额外 Git 存储单独识别和归档，不能混入工作文件。

详细恢复合同见 [references/git-recovery.md](references/git-recovery.md)。

## 授权与工具参数

向用户展示来源、目标、可读目录树、动作、冲突和恢复方式。已有明确授权覆盖这些内容时继续；没有时对缺失的实际决定提问。

脚本的 `approved_tree_sha256`、`-ApprovedPlanSha256` 与 `-ApprovedRetirementSha256` 仍校验内容一致性，由智能体根据已获授权填写。三个参数不要求三次用户批准，不能凭内部哈希自行扩大授权。

## 与其他技能的边界

- 单个仓库内把本地与远端分支、worktree 和 stash 收口到默认分支时使用 git-branch-consolidation；本技能只处理多个目录或仓库之间的项目整理。
- 正式计划互审统一遵守共享规则；普通盘点和执行不额外互审。

- 新实验项目未来结构需要统一时，在迁移验收后调用 `standardize-test-project`；不得把历史迁移当作结构标准化的副作用。
- 需要进一步释放磁盘空间或检查整个回收站时调用 `windows-storage-cleanup`。
- 只更新受本次迁移影响的现有引用，不自动追加经验沉淀任务。

## 停止条件

以下条件只阻塞受影响的计划或动作；脚本要求整份计划一致时保留该计划并继续独立工作，不绕过其检查：来源未确认、目录设计未确认、目标映射不明确、读取错误、非零 `hold`、目录树与批准不符、来源变化、目标冲突、空间不足、Git 恢复失败、网络路径执行、路径越界、回收站无法确认或用户撤回批准。
