# 恢复与删除合同

本文件定义全面分支收口时必须冻结、备份、演练和复核的内容。它用于破坏性执行，不是普通分支合并教程。

## 1. 冻结快照

冻结记录至少包含：

| 对象 | 必须记录的证据 |
|---|---|
| live remote | remote 名、symbolic HEAD、所有 heads/tags 及 40 位 SHA |
| 本地 refs | 所有 refs、heads、remote tracking refs、tags |
| 根 HEAD | symbolic ref 和 40 位 SHA |
| worktrees | porcelain 清单、路径、HEAD、branch、locked/prunable 状态 |
| stash | selector、commit SHA、subject，保持原顺序 |
| reflog | commit SHA、完整 selector、subject |
| index | ls-files --stage 的 NUL 输出、staged binary patch |
| 工作树 | unstaged binary patch、当前 tracked 字节、untracked payload |
| ignored | 根路径、preserve/reproducible 分类、逐项大小、模式和 SHA-256 |
| Git 健康 | active operations、unmerged index、fsck --full、log --all |
| 同步状态 | 同步进程名称、PID、原状态、暂停证据和恢复时间 |

所有 Git 读取使用 --no-optional-locks，避免 index 刷新被误判为并发写入。冻结前允许一次明确的 fetch --prune；冻结后任何非预期变化都作废快照。

## 2. ignored disposition

capture_recovery.py 接受以下 JSON：

~~~json
{
  "schemaVersion": 1,
  "worktrees": {
    "D:\\Repos\\demo": {
      "preserve": [
        "local-results",
        "vendor-archive.zip"
      ],
      "reproducible": [
        "node_modules",
        "dist"
      ]
    },
    "D:\\Worktrees\\demo-feature": {
      "preserve": [],
      "reproducible": [
        ".pytest_cache"
      ]
    }
  }
}
~~~

规则：

- worktree key 必须解析为已注册 worktree 的准确绝对路径。
- 值必须是 git status --ignored=matching 返回的根路径；不能写其任意子项来规避整根分类。
- 每个 ignored 根路径必须且只能出现一次。
- preserve 必须复制 payload；reproducible 只记录完整清单，另外在执行记录中写明固定重建命令或依据。
- 路径不得为绝对路径、空路径、点路径或包含 ..。
- 无法完整分类时 capture 必须失败。

untracked 内容没有可重建例外，全部进入 payload。凭据和密钥不得为方便而写入仓库；恢复包含敏感本地配置时，应保存在用户批准的受控本地路径。

## 3. 恢复包结构

每份包至少包含：

~~~text
package-manifest.sha256
repository-recovery.bundle
snapshot-summary.json
snapshot/
  backup-refs.json
  protected-objects.json
  live-remote-before-pin.json
  worktrees.porcelain.z
  stash.tsv
  reflog.tsv
  fsck-result.json
worktrees/000/
  metadata.json
  status-v2-no-branch.z
  ls-files-stage.z
  staged.patch
  unstaged.patch
  tracked-current.tar
  untracked-payload.tar
  ignored-preserved-payload.tar
  ignored-reproducible-manifest.json
git-metadata/git-metadata.tar
~~~

package-manifest.sha256 覆盖包内除自身之外的每个文件，并记录 SHA-256、字节数和相对路径。两份包应从同一已封存目录复制，manifest 及所有文件字节一致。

Git 官方文档说明 bundle 只打包可达 Git 对象和 refs，不包含工作树、index、stash 的工作区语义、配置或 hooks。因此 bundle 不能替代 patch、payload 和状态清单：

- https://git-scm.com/docs/git-bundle
- https://git-scm.com/docs/git-worktree

## 4. backup refs

临时 refs 固定在：

~~~text
refs/backup/branch-consolidation/<stamp>/
~~~

至少保护：

- 冻结时存在的所有本地 refs；
- live remote 的所有 heads 和 tags；
- 每个 detached 或 attached worktree 的 HEAD；
- 每个 stash commit；
- 每个仍可读的 reflog commit。

远端对象用准确 refspec 单独 fetch 到临时 ref，不使用受损的 --all，也不把远端 branch 直接映射成可误推送的本地 branch。创建 bundle 时从 backup-refs.json 中的明确 ref 列表通过 --stdin 输入。

bundle verify、bundle list-heads 与 backup-refs.json 必须一致。隔离 mirror clone 后，每个受保护 object/commit 必须可由 cat-file 读取。

## 5. worktree 重放

每个 worktree 从冻结 HEAD 建立 detached 恢复工作树，严格按此顺序：

1. git apply --index --binary staged.patch
2. git apply --binary unstaged.patch
3. 覆盖 tracked-current.tar 中的当前字节，以消除 checkout 的 EOL 转换差异
4. 解包 untracked-payload.tar
5. 解包 ignored-preserved-payload.tar

随后逐字比较：

- status --porcelain=v2 --untracked-files=all -z
- ls-files --stage -z
- tracked、untracked、preserved ignored 的路径、类型、模式、大小、链接目标和 SHA-256

reproducible ignored 内容不在恢复工作树创建，只核对其冻结清单仍存在于包内。隔离 bare repo 最后运行 fsck --full。任一步失败都不允许开始删除。

## 6. 提交判重记录

每个待判断提交应有一条记录：

| 字段 | 含义 |
|---|---|
| source_ref | 冻结分支 ref |
| source_sha | 原提交 40 位 SHA |
| order | 在该分支上的原顺序 |
| classification | ancestor、patch-equivalent、content-covered、unique、conflict、artifact |
| evidence | merge-base、git cherry、stable patch-id、路径 diff、测试或冲突证据 |
| action | skip、cherry-pick、backup-only、stop |
| resulting_sha | cherry-pick 后的新 SHA，未集成则为空 |

稳定 patch-id 可以辅助判断提交等价，但不能证明项目语义仍完整。content-covered 必须有具体路径与测试证据。conflict 一律 stop，不自动选择内容。

## 7. 远端发布与删除

默认分支发布条件：

1. live remote 默认分支仍等于冻结 SHA；
2. 候选以冻结 SHA 为祖先；
3. 新区间无 merge commit；
4. 所有测试通过；
5. 普通 fast-forward push，不带任何 force 选项。

远端辅助分支删除条件：

1. live remote 默认分支已经等于最终 SHA；
2. 每个待删 ref 仍存在且 tip 等于冻结 SHA；
3. tags 清单未变化；
4. 同步程序仍暂停；
5. 两份恢复包与隔离演练回执仍有效。

删除必须是一次 atomic push，每个分支带独立 lease。Git 官方 push 文档说明 force-with-lease 只有在期望 ref 值匹配时才允许更新；本合同把它用于保护“冻结 tip 未变化才删除”的条件，不用于默认分支：

- https://git-scm.com/docs/git-push

服务器拒绝 atomic 时保持全部远端分支，不逐项重试。删除命令的 stdout、stderr、退出码和删除前后 ls-remote 均写入执行记录。

## 8. 本地清理

本地删除顺序固定为：

1. 再次拉取或只读证明 live remote 最终状态；
2. 根工作树检出默认分支并对齐最终 SHA；
3. 对辅助 worktree 逐项验证 frozen HEAD、branch、status、index 和 payload；
4. 只移除冻结清单中的 untracked/ignored exact roots，必要的 dirty tracked 内容已进入最终历史或恢复包；
5. 使用不带 --force 的 worktree remove；
6. 删除已验证 tip 的本地辅助 branches；
7. stash 列表与冻结快照一致时从大索引到小索引 drop，或一次 clear；
8. 删除当前 stamp 的 backup refs；
9. 保留所有 tags、双份恢复包和隔离恢复仓库。

递归删除或移动前先把每个目标解析成绝对路径，并证明它位于预期 worktree 或任务自有恢复目录内。禁止把枚举结果跨 shell 拼接到删除命令。

## 9. 最终验收字段

verify_acceptance.py 检查：

- repository-root
- root-symbolic-head
- root-head-sha
- local-heads-only-default
- remote-tracking-default
- remote-symbolic-head
- remote-heads-only-default
- local-tags-preserved
- remote-tags-preserved
- single-default-worktree
- stash-empty
- working-tree-clean
- ignored-content-policy
- temporary-backup-refs-removed
- no-cloud-sync-ref-pollution
- no-active-git-operation
- no-unmerged-index
- working-diff-check
- new-range-diff-check
- no-tracked-conflict-markers
- frozen-default-is-ancestor
- new-history-is-linear
- recovery-package-manifest
- recovery-bundle-hash
- recovery-bundle-verify
- git-fsck-full
- git-log-all-readable

任何一项失败都表示本次验收未完成。输出 receipt 的路径、最终 commit 和恢复包路径应写入任务记录。

## 10. 回滚

开始删除后失败：

1. 停止剩余删除，记录 live refs 和当前本地状态。
2. 不自动回退已经发布的默认分支。
3. 从已验证 bundle 取回 backup refs，并按 backup-refs.json 重建本地 refs。
4. 远端同名 ref 不存在且原授权覆盖恢复时，以普通 create push 重建；名字已被他人使用时停止。
5. 用隔离演练目录中的恢复顺序重建 worktrees。
6. 原根工作树 dirty 状态恢复到独立 recovered/pre-consolidation-default worktree。
7. 同步程序只恢复到冻结时记录的原状态，随后重新检查 Git 元数据。

两份包位于同一物理盘时，只能防单路径误删或同步污染，不能防整盘故障。把这个边界写入执行记录，不把双目录描述成异盘灾备。

## 11. 参考实现

外部 git-safety-net skill 提供了“先分析所有分支，再把有效工作收口到 main”的触发思路；本技能补上双份恢复、dirty worktree 重放、ignored 分类、atomic leases 和同步目录边界：

- https://github.com/daymade/claude-code-skills/blob/main/git-safety-net/SKILL.md
