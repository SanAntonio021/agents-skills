---
name: project-organizer
description: 新建普通项目目录并建立 README、AGENTS，或建立长期资料主档并补齐项目级 README 入口；按用途组织正式内容和临时过程文件。也把散落在多个本机目录的同一项目整合到统一目录，合并有效内容、更新 Markdown 与真实引用、验证新入口并清理已处理的旧目录；也支持独立项目分组。先盘点当前文件，按明确范围执行；普通单文件操作、单仓库分支整理和整盘清理使用对应能力。
compatibility: Windows PowerShell 5.1+, Git for Windows; execution supports local drive-letter paths only.
---

# Project Organizer

本技能负责把一个或多个项目目录整理成可以继续使用的工作区。完成标准是有效内容完整、新位置的说明和引用可用、已处理的旧目录退役，恢复材料集中保存。

涉及 Markdown 入口、专题说明或引用整合时，按 [Markdown 文档维护规范](../../docs/markdown-maintenance.md) 判断职责、历史归位、重复处理和引用验收；目录迁移、Git 恢复和退役仍按本技能的专门规则执行。单个仓库内的分支、worktree 和 stash 收口使用 `git-branch-consolidation`。

## 适用场景

本技能处理新建普通项目、长期资料主档、多个目录或仓库之间的同一项目整合，以及独立项目分组。单个仓库内的分支、worktree 和 stash 收口使用 `git-branch-consolidation`；普通单文件操作、整盘清理和释放磁盘空间使用对应技能。

新建项目时，按用户指定位置、项目已有结构、专业技能约定的顺序确定正式位置。正式内容与过程文件是两种性质，不强制建立两套目录，也不预建无内容的分类。README、AGENTS 和 Markdown 文档的写法按 `markdown-maintenance` 处理。

`merge` 用于同一逻辑项目或一个来源与已有目标整合，未解决的异内容保留为 `hold_conflict`。`group` 用于多个独立但同类项目，各自进入共同父目录下独立的 `target_name`；不能仅凭目录名相似自动合并。

资料库归集或成果回收时，读取[资料库登记衔接](references/material-libraries.md)（如存在）或 `references/material-library.md`，复用已确认的分类、扁平程度和登记方式。

## 准备

读取项目规则、明确路径、现有目标和约束；只搜索当前任务相关目录。盘点来源、目标、重复、冲突、引用和 Git 状态，形成可读目标树。以完整材料包或工程为迁移单元，先检查必要依赖；无法整体处理的单元暂缓并记录原因，其他独立单元继续。

确认来源、目标、目录设计、恢复方式和已有成果；存在实质歧义时询问，已有准确授权时继续。路径必须为绝对路径，来源之间、来源与目标之间不嵌套；执行阶段只允许本机盘符路径。为涉及 Git 的来源准备并验证恢复 bundle；一次准确授权覆盖已经展示的目录树、迁移和退役范围。复制需求预留 20% 空间，空间不足时不执行。

## 执行

目录映射：`merge` 默认把来源相对路径直接映射到目标，显式 `mapping_rules` 可按前缀替换。`group` 固定映射为 `<target_root>/<target_name>/<relative_path>`，保持项目内部结构，不接受 `mapping_rules`，也不自动平铺项目内容。已存在目标参与盘点；先展示可读目录树，复用已经明确的目录决定，`mapping_rules` 和整合清单随计划锁定。

内容合并：按 [Markdown 文档维护规范](../../docs/markdown-maintenance.md) 合并仍有用的说明、记录和引用，更新新入口、路径和用法；历史记录保留当时事实。检查 Markdown 链接与图片、代码和配置路径、论文及其他工程资源引用，按明确映射修改，优先使用可用的相对路径；外部 URL、Zotero 标识和历史叙述不作机械替换。内容相同但用途不同的文件分别保存，用途不明的二进制原样保留。

版本与清单：`version_policy=integrate` 保存全部有效内容，不默认建立旧版本副本。每份改写输入记录原哈希、恢复位置和内容去向。

旧 `preserve_all`、`approved_selection` 保持原义，后者只决定日常版本；其他唯一内容仍按已确认归档方案保留或保持 `hold`。盘点输出 `target-tree.md`、`target-tree.csv`、`target-tree.sha256` 和 `layout-violations.csv`；配置和清单字段见[配置与清单](references/config-and-manifests.md)。

文件迁移：原样文件同盘使用“记录、移动、复验”；跨盘使用目标目录内临时文件、复验、原子改名。每个稳定文件保留 SHA256，部署前后核对大小、修改时间和已有目标状态；复制需求预留 20% 余量，空间不足时不执行。

部署前核对输入、准备文件、检查材料和目标没有未记录变化，不按修改时间选版本；中断后核实实际文件再续做。缓存和临时文件按显式规则分类，删除进入独立退役清单；云端占位、未支持的重解析点、加密或稀疏文件、多硬链接和无法安全处理的特殊流进入 `hold`。Windows 路径、回收站和云端规则见[Windows 安全规则](references/windows-safety.md)。

Git 恢复：每个来源仓库分别保存，不自动拼接历史；保存本地和远端引用、tag、stash 和 reflog 提交，dirty、staged、untracked 状态写入清单。bundle 通过 `git bundle verify`，在隔离目录恢复后运行 `git fsck --full` 并检查记录的提交。

`merge` 由配置指定现役来源、已有目标仓库或新仓库；`group` 保留各项目独立仓库。目标位于同步目录时，活动 Git 数据库放到 `external_git_root`，工作区只保留 `.git` 指针；`.git-backup` 等额外存储单独归档。详细合同见[Git 恢复合同](references/git-recovery.md)。

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

迁移执行需要同时提供：

```powershell
-ApprovedPlanSha256 <64-hex> -Execute
```

退役执行需要同时提供：

```powershell
-ApprovedRetirementSha256 <64-hex> -Recycle
```

恢复包生成中断且尚未封定时，按[恢复合同](references/git-recovery.md)使用 `Move-FailedGitRecovery.ps1` 保留完整失败材料，再在原运行目录重试；不手工补写通过清单。没有 `-Execute` 或 `-Recycle` 时只做预检。

终端或工具超时不等于子进程停止：先不重启命令，重复读取状态文件和 JSONL 日志，比较 `LastWriteTimeUtc`、完成动作数和日志行数；仍在变化就继续等待。确认相关进程已退出且连续两次观察无变化后，才对原输出目录和未变化的计划增加 `-Resume`；不手工补写状态，也不并行重跑。

## 验收

在新位置回读入口、链接、必要依赖及适用的打开、编译或无硬件试运行结果。为整合组记录对应最终文件版本的检查结果；检查失败或必要检查未完成时保留相关来源。

确认新入口可用、必要恢复材料已保存、旧目录内容已经处理完毕后，按已有授权退役旧目录，回收已搬空目录，只保留新入口。同一单元不拆成新旧两处长期维护；执行中断时按恢复流程继续或回滚，不把部分迁移报告为完成。不清空回收站，不等待最终签字，也不自动追加经验维护。

## 停止时

来源未确认、目录设计未确认、目标映射不明确、读取错误、非零 `hold`、目录树与批准不符、来源变化、目标冲突、空间不足、Git 恢复失败、网络路径执行、路径越界、回收站无法确认或用户撤回批准时，只停止受影响的计划或动作，其他独立工作继续。停止时保留现场、失败材料和恢复依据，说明未完成范围及下一步。

## 与其他技能的边界

单个仓库内的分支、worktree 和 stash 收口使用 `git-branch-consolidation`；本技能负责新建普通项目及多个目录或仓库之间的项目整理。正式计划互审遵守共享规则，普通盘点和执行不额外互审。

实验输出沿用 `standardize-test-project`；历史实验只按明确映射迁移。文献沿用 Zotero 管理分工。需要检查整个回收站或释放磁盘空间时调用 `windows-storage-cleanup`。只更新受本次迁移影响的现有引用，不自动追加经验沉淀任务。
