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
| ignored | 根路径及 preserve/reproducible 分类；preserve 保存内容哈希，确认纯可重建根仅记录身份、类型及重建依据 |
| Git 健康 | active operations、unmerged index、fsck --full、log --all |
| 备份/同步状态 | 单向备份或双向同步模式、监控范围、已知写入者协调、真实回写/占用证据；仅在另获授权改变客户端状态时记录原状态和恢复时间 |

所有 Git 读取使用 --no-optional-locks，避免 index 刷新被误判为并发写入；命令成功后才消费结果。已知写入者交接后，间隔至少 2 秒采集两份快照，比较 refs、HEAD、reflog、stash、worktree、index 和受保护文件的类型、模式、大小、链接目标及哈希；不是只比较 HEAD 或普通 status。纯可重建缓存按下文 v2 根记录比较，不遍历内部。封包前后核对同一范围，删除前精确复核待删 ref 与 payload；未预期的漂移使相关快照失效。

活动 Git 操作、子模块、LFS、稀疏检出和特殊 index 标志等不能仅凭普通 status 判为已保全。检测到后先保留现场并核对现有恢复能力；尚未覆盖的内容阻塞依赖它的封包或删除，其余只读与独立集成继续，不自动重置或新增专用恢复引擎。

正常单向备份的运行、上传或暂停状态未知不是失败条件；双向覆盖风险、真实回写和并发 Git 写入只阻断受影响步骤。稳定双快照不能代替已知写入者协调，也不要求一律暂停客户端。不得强停客户端、删除未知锁或绕过 hooks。

冻结前允许一次明确的 fetch --prune。失败后在 2、5、10、20 秒后最多复查 4 次（累计 37 秒）；状态未变只观察，准确临时 ref 或占用消失且仓库状态符合预期后，才最多补一次必要的 fetch。fetch 恢复需退出 0、准确目标 SHA 和对象可解析、连接检查通过；ls-remote 不是 fetch 的替代。失败后 commit/merge/checkout 不自动重跑，删除不自动重试。

## 2. ignored disposition

capture_recovery.py 接受以下 JSON：

~~~json
{
  "schemaVersion": 2,
  "worktrees": {
    "D:\\Repos\\demo": {
      "preserve": [
        "local-results",
        "vendor-archive.zip"
      ],
      "reproducible": [
        "node_modules",
        "dist"
      ],
      "rebuild": {
        "node_modules": "npm ci，使用当前 package-lock.json",
        "dist": "npm run build，使用当前已保存源码及锁文件"
      }
    },
    "D:\\Worktrees\\demo-feature": {
      "preserve": [],
      "reproducible": [
        ".pytest_cache"
      ],
      "rebuild": {
        ".pytest_cache": "pytest 会重新生成缓存；测试输入已作为受保护内容保存"
      }
    }
  }
}
~~~

规则：

- worktree key 必须解析为已注册 worktree 的准确绝对路径。
- 值必须是 git status --ignored=matching 返回的根路径；不能写其任意子项来规避整根分类。
- 每个 ignored 根路径必须且只能出现一次。
- preserve 复制 payload；reproducible 仅适用于已确认整根纯可重建内容，`rebuild` 中每个准确根路径对应非空重建命令或充分依据。
- v2 保存根及祖先的类型、身份、模式、链接目标与重建依据，不遍历、复制或逐文件哈希缓存内部；根被替换、链接逃逸、分类变化或保护路径与缓存混合时不能用缓存例外放行。
- 路径不得为绝对路径、空路径、点路径或包含 ..。
- 无法确定用途的根按 preserve 分类继续；分类文件缺漏或实际保存失败时阻塞相关封包，不因目录名称猜测可删。

tracked 和 untracked 内容没有可重建例外，全部按原保护路径保存；缓存根中出现受保护文件时不能跳过。v1 disposition 继续使用旧版完整缓存清单，不静默按 v2 降低保护。凭据和密钥不得为方便而写入仓库；恢复包含敏感本地配置时，应保存在用户批准的受控本地路径。

每次双快照和封包前后都重新运行 Git 的 index/status/非忽略 untracked 枚举，复核分类文件、忽略规则和缓存根至工作树根的身份及类型。Git 识别保护路径所需的枚举仍执行；备份程序才跳过缓存内部。取反规则引入保护文件、根或祖先被替换、分类变化均阻塞相关步骤，只有纯忽略内容的内部变化不使快照失效。

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
  ignored-reproducible-roots.json
git-metadata/git-metadata.tar
~~~

新捕获使用 snapshot schemaVersion 3。v2 disposition 的 `ignored-reproducible-roots.json` 记录 `path`、`kind`、`mode`、`device`、`inode`、`linkTarget`、根至父级的 `ancestors` 身份和 `rebuild`；v1 disposition 仍生成 `ignored-reproducible-manifest.json` 完整清单，旧 v1/v2 记录按原保护语义读取。

旧 snapshot v2 只按包内原 v1 分类和完整清单验证；snapshot v3 接受 v1 完整清单或 v2 根记录。缺重建依据、两种表示混用或未知版本拒绝读取，不通过外部新分类改变旧包含义。v3 同时记录双包位置，供验收排除“把备份当正常数据存续位置”的情况。

package-manifest.sha256 覆盖包内除自身之外的每个文件，记录 SHA-256、字节数和相对路径。两份包从同一封存目录复制，manifest 及所有字节一致。双包相同不能替代源状态稳定；两份包均须验证并通过隔离恢复演练。

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

reproducible ignored 内容不在恢复工作树创建；v2 核对根记录与重建依据，v1 继续核对完整冻结清单。隔离 bare repo 最后运行 fsck --full。受保护内容恢复失败时不能开始依赖它的删除。

恢复只验证包内记录和实际还原内容，不要求原工作树仍存在，不执行重建说明。轻量缓存内部链接不会被读取或重建；根级链接仍按准确链接授权检查。缓存是否确实可重建由分类时核对的项目流程保证，非空文字本身不能证明可重建。

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
| action | 实际采用的跳过、合并、选择提交、改动应用、仅备份或暂缓方式 |
| resulting_sha | 集成后的目标 SHA，未集成则为空 |

稳定 patch-id 可以辅助判断等价，但不能证明项目语义完整。content-covered 要有具体路径、实现关系和相关测试依据。冲突先检查双方意图并自主解决明确部分；仅无法自行确定的功能或科学含义取舍才询问。有效工作只在恢复包中可找回不代表已集成，无效或被覆盖的工作才可说明理由后仅备份。

`verify_acceptance.py --check-integration-only` 在删除前检查候选，最终验收再次检查同一归并结果。默认自动核对分支祖先或非 merge 提交的补丁等价、stash 各层与工作区补丁、未跟踪文件的已提交内容；含独有 merge commit 时不靠 `git cherry` 放行。

需要语义比较时，`--integration-records <现有分类记录.json>` 读取数组：沿用 `source_ref`、`source_sha`、`classification`、`evidence`、`action`、`resulting_sha`。接受的分类为 `content-covered` 或 `patch-equivalent`，动作是 `skip`、`merge`、`rebase` 或 `cherry-pick`；`evidence` 指向已有非空比较材料，`resulting_sha` 绑定当前完整候选 SHA。验收回执明确标为已记录的内容比较，不冒充机器证明了语义一致。

来源标识和摘要由首次归并检查的失败项直接取得：分支用原 ref（远端加 `remote:`），stash 用 `stash:<SHA>:working/index`，工作区补丁用 `worktree:<三位序号>:staged/unstaged`，payload 用 `worktree:<三位序号>:untracked/ignored-preserved`。补丁摘要为原始字节 SHA-256，payload 为按键排序、保留中文的 JSON 清单 SHA-256；无须用户手工填写。ignored-preserved 另存时在对应记录加 `destination`，程序实际比较该目录下相同相对路径的内容；恢复包及待移除工作区不能作为目的地。

## 7. 远端发布与删除

默认分支发布条件：

1. live remote 默认分支仍等于冻结 SHA；
2. 候选以冻结 SHA 为祖先；
3. 有效工作已集成，用户或项目明确要求线性历史时才限制新区间无 merge commit；
4. 所有测试通过；
5. 普通 fast-forward push，不带任何 force 选项。

push 返回失败或结果不明时，先读取准确远端 ref：等于预期候选 SHA 则跳过重推；仍等于原冻结 SHA 且候选、测试和发布条件未变，才可补一次普通 push；其他 SHA 或读取失败均停止受影响步骤。Git 远端成功不代表百度备份成功。

远端辅助分支删除条件：

1. live remote 默认分支已经等于最终 SHA；
2. 每个待删 ref 仍存在且 tip 等于冻结 SHA；
3. tags 清单未变化；
4. 已知写入者协调仍有效，间隔至少 2 秒的完整双快照稳定、封包前后完整哈希相符，且没有双向覆盖风险、真实回写或并发 Git 写入；正常单向备份运行、上传或暂停状态未知不阻断；
5. 两份恢复包与隔离演练回执仍有效。

上述条件之外，每个待删分支和 stash 均须有归并检查结果；任何未归并内容保留其分支、工作区或 stash。辅助工作区仍占用旧分支且不能移除时，报告未完成，不能仅为分支数量合格而删除。

删除必须是一次 atomic push，每个分支带独立 lease。Git 官方 push 文档说明 force-with-lease 只有在期望 ref 值匹配时才允许更新；本合同把它用于保护“冻结 tip 未变化才删除”的条件，不用于默认分支：

- https://git-scm.com/docs/git-push

服务器拒绝 atomic 时保持全部远端分支，不逐项重试。删除结果不明时仅核查每个准确 ref，不自动重放删除；任何异常停止剩余删除。删除命令的 stdout、stderr、退出码和删除前后 ls-remote 均写入执行记录。

## 8. 本地清理

本地删除顺序固定为：

1. 再次拉取或只读证明 live remote 最终状态；
2. 根工作树检出默认分支并对齐最终 SHA；
3. 对辅助 worktree 逐项验证 frozen HEAD、branch、status、index 和 payload；
4. 有效源码、stash 和未提交改动已集成；辅助 worktree 中的不可重建数据有可直接使用的存续副本并核对内容，不以双恢复包替代正常数据交付，再移除冻结清单内的 exact roots；
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
- new-history-is-linear（仅传入 --require-linear-history 时要求）
- recovery-package-manifest
- recovery-bundle-hash
- recovery-bundle-verify
- git-fsck-full
- git-log-all-readable

默认允许普通 merge commit，仍检查冻结默认提交是最终提交祖先。任何适用检查失败都表示本次验收未完成。receipt、最终 commit 和恢复包路径写入已有任务记录。

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
