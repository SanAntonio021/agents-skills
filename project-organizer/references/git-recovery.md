# Git 恢复合同

## 发现

识别工作区中的 `.git` 目录、`.git` 指针文件和明确配置的 `.git-backup`。所有 Git 命令使用 `--no-optional-locks`，不得 fetch 远端或刷新来源。

记录：

- 当前分支、HEAD、所有本地/远端引用和 tag。
- stash、全部 reflog 中出现的提交。
- staged、unstaged、untracked 和 ignored 摘要。
- remote URL 只写审计文件，不自动访问。

## Bundle

每个 Git 存储使用唯一来源 ID。先在 `external_git_root` 建立临时裸仓库，再为 reflog 提交创建 `refs/archive/reflog/*` 命名引用。bundle 输出到审计归档目录。

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

bundle 是长期历史恢复依据，活动 Git 数据库是日常状态。两者职责不同，不能因为其中一个存在就跳过另一个的验收。
