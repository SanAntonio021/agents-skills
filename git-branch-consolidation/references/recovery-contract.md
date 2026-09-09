# 恢复与删除合同

本文件定义全面分支收口时必须冻结、备份、演练和复核的内容。它用于破坏性执行，不是普通分支合并教程。

## Windows Git 局部排错

本节可独立读取；普通提交或查询遇到故障，只处理当前故障，不执行后文的全面收口。

- 云盘的 `*.baiduyun.uploading.cfg` 混入 refs，或 `FETCH_HEAD` 被占用，可以造成 `bad object`、`Permission denied`；这不等于仓库已经回滚。核对准确 Git 管理目录、报错路径和实际占用，不删除未知锁或强停客户端。正常单向备份运行本身不是阻塞理由。
- 只需核对远端提交时，使用 `git ls-remote --exit-code --refs <remote> <ref>` 并检查退出码与唯一返回值。它不下载对象；需要读取或合并远端内容时，仍须成功取得并核实对应对象。
- 失败后先检查是否部分完成，再决定恢复；push 返回不明时先查准确远端 ref，避免重复发布。故障只阻塞依赖它的步骤。
- 多任务共用工作树时，index、HEAD 和提交状态也共用。发现并发写入先协调，必要时使用任务自有的隔离副本；linked worktree 的管理文件仍在原仓库，原管理目录被占用时并非完全隔离。保留用户修改，不以重置、跳过 hooks 或改动无关文件来完成提交。

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
| 备份/同步状态 | 单向备份或双向同步模式、监控范围、已知写入者协调、真实回写/占用证据；仅在另获授权改变客户端状态时记录原状态和恢复时间 |

所有 Git 读取使用 --no-optional-locks，避免 index 刷新被误判为并发写入；每条命令退出 0 后才消费结果。确认已知写入者已按现有机制交接后，间隔至少 2 秒采集两份完整快照，逐项比较上表的 refs、HEAD、reflog、stash、worktree、index、文件清单/类型/模式/大小/链接目标/哈希；不是只比较 HEAD 或普通 status。封包前后再核对完整状态与哈希，删除前精确复核待删 ref 与 payload。除本流程记录的预期变化外，任何漂移都作废快照。

正常单向备份的运行、上传或暂停状态未知不是失败条件；双向覆盖风险、真实回写和并发 Git 写入只阻断受影响步骤。稳定双快照不能代替已知写入者协调，也不要求一律暂停客户端。不得强停客户端、删除未知锁或绕过 hooks。

冻结前允许一次明确的 fetch --prune。失败后在 2、5、10、20 秒后最多复查 4 次（累计 37 秒）；状态未变只观察，准确临时 ref 或占用消失且仓库状态符合预期后，才最多补一次必要的 fetch。fetch 恢复需退出 0、准确目标 SHA 和对象可解析、连接检查通过；ls-remote 不是 fetch 的替代。失败后 commit/merge/checkout 不自动重跑，删除不自动重试。

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
  links.json
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

package-manifest.sha256 覆盖包内除自身之外的每个文件，并记录 SHA-256、字节数和相对路径。两份包应从同一已封存目录复制，manifest 及所有文件字节一致。封包前后完整状态和哈希不一致时，不得以两份副本相同代替源状态稳定；两份包都须验证，并通过隔离恢复演练。

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

### 链接与外部目标

每个新恢复包的 `worktrees/<id>/links.json` 记录该工作树的链接本体，包括仓内相对路径、链接种类和原始 target。捕获和重放均不跟随 junction/symlink 去遍历、复制、哈希或删除目标目录；目标中的文件不能冒充仓库 payload。需要保全目标内容时，应作为另一个明确授权对象处理。

隔离恢复默认拒绝指向恢复工作树外的链接。只有已获授权的准确链接，才通过下列参数允许恢复链接本体：

~~~powershell
python <skill>\scripts\verify_recovery.py --source <primary-package> --mirror <mirror-package> --restore <new-isolated-restore-dir> --external-link-allowlist <external-link-allowlist.json>
~~~

allowlist 使用 `schemaVersion: 1` 和 `links` 数组；每项的 `worktree`（冻结的原工作树）、`path`（仓内相对路径）、`kind`、`target`（原始链接目标文本）须与冻结记录严格匹配，不按名称相似或解析后位置放宽。以下占位值必须从现场记录取得，不写入本机固定路径：

~~~json
{
  "schemaVersion": 1,
  "links": [
    {
      "worktree": "<original-worktree>",
      "path": "<repository-relative-link-path>",
      "kind": "<recorded-link-kind>",
      "target": "<original-target-text>"
    }
  ]
}
~~~

授权只覆盖创建所列链接本体，不覆盖读写外部目标。旧版 schemaVersion 2 恢复包缺少 `links.json` 时，沿用旧包中已有的链接记录和验证能力，不仅因新文件缺失拒绝旧包；不得推断未记录的 junction 或把未知目标当成已授权，外部链接仍默认拒绝。两份包和隔离恢复必须使用相同的准确 allowlist。


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

push 返回失败或结果不明时，先读取准确远端 ref：等于预期候选 SHA 则跳过重推；仍等于原冻结 SHA 且候选、测试和发布条件未变，才可补一次普通 push；其他 SHA 或读取失败均停止受影响步骤。Git 远端成功不代表百度备份成功。

远端辅助分支删除条件：

1. live remote 默认分支已经等于最终 SHA；
2. 每个待删 ref 仍存在且 tip 等于冻结 SHA；
3. tags 清单未变化；
4. 已知写入者协调仍有效，间隔至少 2 秒的完整双快照稳定、封包前后完整哈希相符，且没有双向覆盖风险、真实回写或并发 Git 写入；正常单向备份运行、上传或暂停状态未知不阻断；
5. 两份恢复包与隔离演练回执仍有效。

删除必须是一次 atomic push，每个分支带独立 lease。Git 官方 push 文档说明 force-with-lease 只有在期望 ref 值匹配时才允许更新；本合同把它用于保护“冻结 tip 未变化才删除”的条件，不用于默认分支：

- https://git-scm.com/docs/git-push

服务器拒绝 atomic 时保持全部远端分支，不逐项重试。删除结果不明时仅核查每个准确 ref，不自动重放删除；任何异常停止剩余删除。删除命令的 stdout、stderr、退出码和删除前后 ls-remote 均写入执行记录。

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
7. 客户端默认保持原状；只有本任务另获授权改变过状态时才按原授权恢复，随后重新检查 Git 元数据。不得把暂停状态或备份进度代替 Git 恢复验证。

两份包位于同一物理盘时，只能防单路径误删或同步污染，不能防整盘故障。把这个边界写入执行记录，不把双目录描述成异盘灾备。

## 11. 参考实现

外部 git-safety-net skill 提供了“先分析所有分支，再把有效工作收口到 main”的触发思路；本技能补上双份恢复、dirty worktree 重放、ignored 分类、atomic leases 和同步目录边界：

- https://github.com/daymade/claude-code-skills/blob/main/git-safety-net/SKILL.md
