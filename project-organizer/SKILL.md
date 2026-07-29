---
name: project-organizer
description: >
  当用户涉及两个或以上相关的本机项目目录、工作区、备份副本或旧版本时，第一步必须调用
  project-organizer 技能；即使本轮只要求只读发现、文件盘点、SHA256 去重、Git 历史比较、
  最终目录树设计或迁移计划，也必须触发，禁止先用 Agent、Read、Glob、Bash 或 PowerShell
  代做。适用任务包括：把同一项目的散落内容合并为统一入口；把多个独立同类项目归入共同父目录
  且保持彼此独立；迁移验收后退役旧路径。用户说“这几个目录”“这些项目”“两个仓库”
  “旧电脑备份”“散落各处”而没有点名技能时同样触发。不得用于单个项目内部整理、普通磁盘或
  缓存清理、扫描整盘自动分类、数据库迁移、Git 分支合并、单文件移动、新建单个项目或论文返修
  工作区、代码托管平台迁移、GitHub Project 看板归档。
compatibility: Windows PowerShell 5.1+, Git for Windows; execution supports local drive-letter paths only.
---

# Project Organizer

把多处项目内容整理成可审计、可恢复的长期工作区。默认只读。发现相关目录不等于授权搬动，批准迁移也不等于授权退役旧目录。

## 两种模式

- `merge`：多个来源属于同一个逻辑项目。文件按目标相对路径合并，完全重复只保留一个目标，同一目标的不同内容进入 `hold_conflict`。
- `group`：多个来源是独立但同类的项目。每个来源整体进入共同父目录下独立的 `target_name`，项目之间不混合。

每次先确认模式。不能仅凭目录名相似自动把独立项目合并。

## 固定流程

1. 阅读项目规则和用户给出的路径。每次真实整理都使用 `ask-first`，一次只确认一个会改变目录结构、范围或风险的选择；材料已经回答的事项不重复问。
2. 用户提供限定的 `search_roots`。运行候选发现；不得扫描未批准的整块磁盘。
3. 展示候选证据，由用户确认 `sources`、`target_root`、模式和现役 Git 策略。
4. `merge` 模式先完成目录设计确认，再把设计表达为 `layout_decisions` 和 `mapping_rules`。映射规则不能替代用户对最终目录组成的确认。
5. 运行盘点，生成稳定 SHA256 清单、重复项、冲突、源状态、Git 状态、错误和 `target-tree.md`。
6. 向用户展示可读的最终目录树。只有用户明确批准该树后，才把 `target-tree.sha256` 写入 `layout_decisions.approved_tree_sha256` 并重新盘点。
7. 对每个 Git 来源生成独立 bundle，验证 bundle、`git fsck`、隔离恢复和引用可读性。
8. 生成正式迁移计划。用户检查 `review.md` 后，批准 `plan.sha256` 才可执行。
9. 执行迁移并验收。任何 `error`、`hold`、来源变化、目录树变化或计划哈希变化都停止。
10. 重新扫描来源，生成独立退役清单。批准 `retirement.sha256` 后，只把清单内内容移入回收站。
11. 技能不得清空整个回收站。用户手动清空后，只读复核空间、来源、目标和恢复包。
12. 更新现有 README 和代理规则中的当前状态；历史审计清单不覆盖。

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

没有 `-Execute` 或 `-Recycle` 时只做预检。中断后只对原输出目录和未变化的计划增加 `-Resume`。

## 目录和映射规则

- `merge` 默认把来源相对路径直接映射到目标；显式 `mapping_rules` 可做前缀替换。
- `group` 固定映射为 `<target_root>/<target_name>/<relative_path>`。
- `group` 保持每个项目内部结构，不接受 `mapping_rules`，也不自动平铺项目内容。
- 已存在目标参与盘点，禁止覆盖。哈希相同登记为目标重复；不同则 `hold_conflict`。
- 默认保持目录关系。目录重构必须先形成可读目录树，再由用户批准；`mapping_rules` 只是批准后执行该设计的表达。
- 资料型项目主动提出浅层方案：经批准的常用交付物可放目标根目录，其他日常资料原则上只保留一层短分类。不要保留仅起套壳作用的 `platform`、`shared` 等泛化层。
- 代码、独立 Git 项目、论文、实验、原始数据、结果数据和 `migration`/审计记录可以保留完成工作所需的内部层级。
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

首次回复在提出单个问题前，先用短句说明固定合同：当前只读；`target-tree.sha256` 是正式计划前的独立批准；`mapping_rules` 仅表达获批设计；目录树、映射和例外由 `plan.sha256` 绑定；验收逐项拒绝旧套壳目录和额外空目录。随后只问当前最高影响问题，不一次列出所有待确认项。

盘点输出 `target-tree.md`、`target-tree.csv`、`target-tree.sha256` 和 `layout-violations.csv`。目录树批准是正式计划之前的独立审批门。批准后的目录树、映射、例外和版本策略都由 `plan.sha256` 绑定；任何一项变化都要重新批准。

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

## 审批门

`merge` 先查看 `target-tree.md`：最终目录、根目录文件、分类层级、独立子项目、版本策略、例外和目录树 SHA256。目录树没有明确批准时，不生成正式计划。

目录树批准后再查看 `review.md`：来源与目标、模式、文件/字节数、重复、冲突、`hold`、Git 恢复包、空间估算和拟执行动作。

审批必须引用工具输出的完整 SHA256。聊天中的“继续”“同意迁移”不能替代目录树、计划或退役哈希批准；三个批准互不替代，退役批准也不能替代用户手动清空回收站。

## 与其他技能的边界

- 新实验项目未来结构需要统一时，在迁移验收后调用 `standardize-test-project`；不得把历史迁移当作结构标准化的副作用。
- 需要进一步释放磁盘空间或检查整个回收站时调用 `windows-storage-cleanup`。
- 完成后用 `chat-notes` 检查 README、AGENTS、CLAUDE、GEMINI 是否仍描述旧状态。

## 停止条件

以下任一条件出现即停止，不扩大范围：来源未确认、目录设计未确认、目标映射不明确、读取错误、非零 `hold`、目录树与批准不符、来源变化、目标冲突、空间不足、Git 恢复失败、网络路径执行、路径越界、回收站无法确认或用户撤回批准。
