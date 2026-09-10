---
name: project-organizer
description: 把散落在多个本机目录的同一项目整合到统一目录，合并有效内容、更新 Markdown 与真实引用、验证新入口并清理已处理的旧目录；也支持独立项目分组。先盘点当前文件，按明确范围执行；普通单文件操作、单仓库分支整理和整盘清理使用对应能力。
compatibility: Windows PowerShell 5.1+, Git for Windows; execution supports local drive-letter paths only.
---

# Project Organizer

把多处项目内容整理成一个可继续使用的工作区。完成标准是有效内容完整、新位置的说明与引用可用、已处理的旧目录退役。恢复材料集中保存，不默认再留一套日常使用的旧项目或“历史版本”目录。只读、分步确认及不清理旧目录等明确要求继续优先遵从。

## 两种模式

- `merge`：来源属于同一个逻辑项目，包括一个来源与已有目标整合。原样文件按目标相对路径迁移；需要合并内容、修改引用或更新已有目标时，先准备最终文件并登记整合清单。未解决的同目标异内容保留为 `hold_conflict`。
- `group`：多个来源是独立但同类的项目。每个来源整体进入共同父目录下独立的 `target_name`，项目之间不混合。

按请求与项目事实确定模式，只有实质歧义才询问。不能仅凭目录名相似自动把独立项目合并。

## 流程

1. 读取项目规则、明确路径、现有目标和约束；只搜索与当前任务相关的根目录。显式调用 `ask-first` 时按它澄清，不自动加载。
2. 盘点来源、已有目标、重复、冲突、引用和 Git 状态，按项目内容形成可读目标树。复用已确认结构；能够从文件与上下文判断的内容直接整合，只有实质歧义才询问。
3. 为涉及 Git 的来源准备并验证恢复 bundle。正式计划按共享规则互审并确认；一次准确授权可覆盖已展示的目录树、迁移和退役范围。
4. 在本轮过程目录准备最终内容、逐项内容去向说明及原件恢复副本，再封定计划。智能体依据已有授权填写工具哈希，无需用户粘贴；内容变化需要核实并重新封定，只有范围或重要取舍变化才重新提问。
5. 执行迁移，在新目录核验说明、链接及适用的打开、编译或无硬件试运行；为整合组记录对应最终文件版本的检查结果。检查失败或必要检查未完成时保留相关来源。
6. 重新核对来源、最终文件、恢复材料和检查结果，按已有授权退役通过验收的旧目录。不清空回收站，不等待最终签字，也不自动追加经验维护。

## 命令

所有命令使用 Windows PowerShell 5.1：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass `
  -File <script> -Config <config.json> -OutputDir <run-dir>
```

按顺序调用；使用整合清单时，在迁移执行后、组织验收前完成实际使用检查并写入 `integration-checks.json`：

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
- 已存在目标参与盘点。原样迁移不覆盖异内容；已授权修改的目标须作为整合输入，记录其当前哈希及恢复副本，按预期状态替换。
- 先展示可读目录树，复用已明确的目录决定；`mapping_rules` 表达原样迁移映射，整合清单表达最终内容及其去向，两者都随计划锁定。
- 资料型项目主动提出浅层方案：经批准的常用交付物可放目标根目录，其他日常资料原则上只保留一层短分类。不要保留仅起套壳作用的 `platform`、`shared` 等泛化层。
- 代码、独立 Git 项目、论文和实验数据保留必要内部结构。布局参考见 [references/material-layout.md](references/material-layout.md)，分类、语言和深度按项目内容确定，不套固定模板。
- 清单、恢复材料和检查记录默认集中在目标的 `过程文件/整理主题/`。仅排除这一本轮专用子树参与业务目录比较，其他任务的过程文件照常保护；显式外部过程目录保持兼容。
- 搜索根、来源、目标和审计目录必须解析为绝对路径；执行阶段只允许本机盘符路径。
- 来源之间、来源与目标之间不得嵌套。路径穿越、通配符和未解析环境变量均停止。

### 内容与引用整合

- 读取每份当前文件。Markdown 合并仍有用的说明与记录，去掉重复内容，更新新入口、路径和用法；历史记录保留当时事实，不改写成现状。
- 检查 Markdown 链接与图片、代码和配置路径、论文及其他工程资源引用，按明确映射修改，优先采用可用的相对路径。外部 URL、Zotero 标识和历史叙述不作机械替换；动态依赖通过适用工具和运行检查核实。
- 内容相同但承担不同引用用途的文件仍按各自目标保存。数据和用途不明的二进制默认原样保留，需要编辑时使用对应工具核验。
- `version_policy=integrate` 保存全部有效内容的整合结果，不默认建立旧版本副本。每份被改写输入记录原哈希、恢复位置和具体内容去向；程序验证关联与完整性，智能体逐项检查独有改动，哈希不能证明语义完整。
- 旧 `preserve_all` 与 `approved_selection` 保持原义。后者只决定日常版本，其他唯一内容仍按已确认的归档方案保留或保持 `hold`，不借升级删除。
- 已知项目外依赖需要修改但超出授权时，指出具体位置，只暂停依赖该修改的旧入口清理。

盘点输出 `target-tree.md`、`target-tree.csv`、`target-tree.sha256` 和 `layout-violations.csv`。配置 `1.1` 可将 `approved_tree_sha256` 留空，由完整计划锁定目录树；填写时必须匹配。`1.0` 保持原目录树校验。哈希由智能体绑定当前准确授权，不增加用户确认轮次。

完整配置和清单字段见 [references/config-and-manifests.md](references/config-and-manifests.md)。

## 文件迁移规则

- 每个稳定文件必须有 SHA256。哈希前后复查大小和 UTC 修改时间；变化则作废。
- 原样文件同盘使用“记录、移动、复验”；跨盘使用目标目录内临时文件、复验、原子改名。整合输出在目标盘准备临时文件后校验并替换，来源原件保留至退役。
- 复制需求加 20% 余量。空间不足时不执行。
- 部署前核对输入、准备文件、检查材料和已有目标未发生未记录变化；不覆盖用户新增修改，也不按修改时间选版本。中断后核实实际文件再续做，只有实际输出符合计划才承认动作完成。
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

脚本的 `approved_tree_sha256`（如填写）、`-ApprovedPlanSha256` 与 `-ApprovedRetirementSha256` 校验内容一致性，由智能体根据已获授权填写。它们不要求三次用户批准。需要重新整合时读取现行文件，准备新结果并更新受影响计划，保留旧记录，不重复询问原范围授权。

## 与其他技能的边界

- 单个仓库内把本地与远端分支、worktree 和 stash 收口到默认分支时使用 git-branch-consolidation；本技能只处理多个目录或仓库之间的项目整理。
- 正式计划互审统一遵守共享规则；普通盘点和执行不额外互审。

- 实验输出沿用 `standardize-test-project` 的既有规范；历史实验仅按本次明确映射迁移，不自动改写结果格式。
- 文献沿用 Zotero 管理分工，不因目录整理另建本地文献库或操作 Zotero。
- 需要进一步释放磁盘空间或检查整个回收站时调用 `windows-storage-cleanup`。
- 只更新受本次迁移影响的现有引用，不自动追加经验沉淀任务。

## 停止条件

以下条件只阻塞受影响的计划或动作；脚本要求整份计划一致时保留该计划并继续独立工作，不绕过其检查：来源未确认、目录设计未确认、目标映射不明确、读取错误、非零 `hold`、目录树与批准不符、来源变化、目标冲突、空间不足、Git 恢复失败、网络路径执行、路径越界、回收站无法确认或用户撤回批准。
