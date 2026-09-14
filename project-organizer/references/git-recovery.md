# Git 恢复合同

## 发现

识别工作区中的 `.git` 目录、`.git` 指针文件和明确配置的 `.git-backup`。所有 Git 命令使用 `--no-optional-locks`，不得 fetch 远端或刷新来源。

记录：

- 当前分支、HEAD、所有本地/远端引用和 tag。
- stash、全部 reflog 中出现的提交。
- staged、unstaged、untracked 和 ignored 摘要。
- remote URL 只写审计文件，不自动访问。

## Bundle

每个 Git 存储使用唯一来源 ID。先在 `external_git_root` 建立临时裸仓库，再为 reflog 提交创建 `refs/archive/reflog/*` 命名引用。bundle 输出到正式 `<recovery_root>/<run-id>/git-bundles/`；恢复支持文件与独立映射一并保留，不依赖过程目录。

验收同时满足：

1. bundle SHA256 已记录。
2. `git bundle verify` 返回成功。
3. 隔离恢复仓库 `git fsck --full` 返回成功。
4. 每个记录的引用和 reflog 提交可由 `git cat-file -e <sha>^{commit}` 读取。
5. 恢复引用与归档清单一致。

## 现役仓库

- `merge/source:<id>`：指定来源作为目标基线，其他来源内容合入后通常显示为新增或修改文件。
- `merge/target_existing`：保留目标已有仓库，来源仓库只留 bundle。
- `merge/new`：迁移验收后新建仓库，不导入来源提交。
- `group/preserve_each`：每个项目保持自己的 Git 数据库和工作区状态。

当目标位于 `sync_roots` 中，活动 Git 数据库放在 `external_git_root/active/<stable-id>.git`，工作区根仅保留文本 `.git` 指针。复制或移动 Git 数据库必须逐文件复验；失败时保留来源并停止退役。

## 旧包归位与显式收尾

旧 `git_archives.json` 仍按记录的实际路径读取，不静默迁移。清理旧过程目录前，复制仍必要的 bundle、支持文件和整合原件到正式恢复位置；逐项核对原哈希、重新执行 bundle verify 和隔离恢复/fsck。更新恢复清单中的路径和哈希清单，保留来源、提交、原件到正式成果的必要映射。正式恢复记录不能依赖准备稿、临时检查报告或旧过程路径。

进行中的迁移若改动整合清单或配置，应重新封定计划并复验，不能沿用旧哈希批准继续退役。已完成迁移的收尾只保留独立恢复映射及必要证据，不复制整套过程日志。确认正式成果可用、恢复可用后，由 `chat-notes` 按明确收尾范围清空过程目录；失败则保留相关材料并说明未完成。不要改写其他任务的恢复记录。

bundle 是长期历史恢复依据，活动 Git 数据库是日常状态。两者职责不同，不能因为其中一个存在就跳过另一个的验收。

## 恢复包生成中断后重试

若正式运行子树已经产生、但尚无 `recovery.sha256`，不要伪造通过清单或覆盖其中内容。先读取 `git-errors.csv` 确定并修复原始故障，再执行 `Move-FailedGitRecovery.ps1 -Config <原配置> -OutputDir <原运行目录>`：程序记录完整文件哈希，并将整个未完成子树原子移入本轮过程目录的 `failed-git-recovery/<attempt-id>/`；明确标记为未经 Git 验收的失败材料，不把文件一致性当成恢复成功。

随后使用同一配置和运行目录重新执行 `New-GitRecoveryBundle.ps1`，重新生成、验证并封定计划。失败材料逐次保留，不覆盖前一次记录，显式收尾时再按过程材料处理。已存在正式总清单（包括损坏的清单）时不能用该程序跳过验证。跨卷时程序保留原目录并停止移动，应先安排同卷过程位置；不自动删除原件。

整合原件可放在 `recovery_root/整合原件/任务名/` 并在盘点前准备好，作为正常正式内容参加目录树与哈希验收。只有 Git 程序管理的 `<run-id>` 子树采用单独验收并排除业务比较，不把整个恢复根排除。新整合示例使用正式原件位置；旧过程路径仍按兼容规则读取。
