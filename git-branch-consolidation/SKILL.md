---
name: git-branch-consolidation
description: >
  把单个 Git 仓库彻底收口到远端默认分支，并可恢复地清理本地与远端辅助分支、worktree、stash 和未提交内容。
  用户说“所有分支合到 main/master”“本地远端只留一个分支”“旧分支、worktree、stash 全部清掉”
  “把整个仓库彻底收口”时必须使用。流程覆盖冻结现场、双份恢复包、bundle 隔离重放、提交判重、线性集成、
  带 lease 的原子远端删除和最终验收。普通单分支 merge/rebase/PR 合并不触发；多个目录或多个仓库的整理
  使用 project-organizer。
compatibility: Git 2.39+, Python 3.10+; Windows PowerShell examples require PowerShell 5.1+.
---

# Git Branch Consolidation

把一个仓库收口到它的远端默认分支。先证明所有状态可恢复，再形成线性历史，最后按冻结清单删除。任何现场漂移、冲突、恢复失败或测试失败都会停止删除。

## 完成合同

默认完成状态如下：

- 根工作树检出远端默认分支，本地默认分支、远端跟踪分支和 live remote 指向同一提交。
- 本地与远端 branch heads 只剩默认分支，只保留根工作树，stash 和普通 git status 为空。
- 所有冻结时存在的 tags 原样保留。
- 冻结时默认分支是最终提交的祖先，新增区间没有 merge commit。
- 两份恢复包哈希有效，bundle 可读，所有 worktree 的 staged、unstaged、untracked 和需保存的 ignored 内容已在隔离仓库重放。

用户明确要求保留某个长期分支、worktree、stash 或本地生成物时，把它写入例外清单，并相应修改完成合同。不要把“只留一个分支”解释成删除 tags。

## 适用边界

- 本技能处理一个 Git 仓库内部的全面收口。
- 普通一两个分支的合并直接走项目常规 Git 流程。
- 两个以上目录或仓库的迁移、归组和入口整理使用 project-organizer。
- Windows 出现 FETCH_HEAD 锁、*.baiduyun.uploading.cfg、长路径或 worktree 半删除时，读取 command-memory/references/git-on-windows.md，不要在本技能重复发明修复命令。

执行破坏性步骤前读取 [references/recovery-contract.md](references/recovery-contract.md)。其中定义恢复包、ignored 分类、远端删除和回滚字段。

## 1. 确定默认分支并冻结写入者

1. 读取仓库及上级 AGENTS.md、项目规则和测试入口。
2. 用 git ls-remote --symref &lt;remote&gt; HEAD 确定默认分支；不要凭 main、master 或当前分支名猜测。
3. 列出正在写这个仓库的任务、进程、IDE 和同步程序。等待已知写入者结束。
4. 仓库位于百度网盘、OneDrive、Dropbox 等同步目录时，记录同步程序原状态并暂停它。无法确认已暂停就停止。
5. 检查每个 worktree 是否存在 merge、rebase、cherry-pick、revert、bisect、sequencer 或 unmerged index。任一存在就停止。
6. 记录 live remote heads/tags、全部本地 refs、HEAD、reflog、stash、worktrees 和各工作树状态。连续两次读取不一致时，现场未冻结。

冻结之后只允许本流程预期的临时 backup refs 和集成 worktree 变化。其他 ref、文件、index、worktree、remote 或同步状态变化会使恢复包失效。

## 2. 明确 ignored 内容的归口

git bundle 不包含 index、工作树、stash、配置、hooks 或未跟踪文件。对每个 worktree 运行：

~~~powershell
git -C <worktree> status --porcelain=v1 --untracked-files=normal --ignored=matching -z
~~~

所有 !! 根路径必须逐项归为：

- preserve：唯一日志、结果、旧二进制、归档、凭据外的本地配置或其他不能重建的内容；写入哈希清单并复制到恢复包。
- reproducible：依赖缓存、构建目录和可由锁文件或固定命令重建的内容；只记录完整哈希清单和重建依据。

无法判断就停止。不要因为路径被 .gitignore 命中便认定可以删除，也不要临时扩大 .gitignore。

## 3. 建立并演练双份恢复包

恢复路径必须不存在、彼此独立，并位于仓库及所有 worktree 之外。准备 ignored-disposition.json 后运行：

~~~powershell
python <skill>\scripts\capture_recovery.py --repo <repo> --remote <remote> --primary <primary-package> --mirror <mirror-package> --stamp <safe-unique-stamp> --ignored-disposition <ignored-disposition.json>
~~~

即使没有 ignored 内容，也可以省略最后一个参数。脚本会：

- 显式取回 live remote heads/tags，并在 refs/backup/branch-consolidation/&lt;stamp&gt;/ 下固定所有需保存对象；
- 保存二进制 staged/unstaged patch、index、tracked 当前字节、untracked payload 和需保留的 ignored payload；
- 保存 refs、reflog、stash、worktree、Git 元数据、文件模式和 SHA-256；
- 从明确 backup refs 创建 repository-recovery.bundle，校验后复制成字节一致的第二份包；
- 封包前重新核对 remote、refs、reflog、stash、worktrees、index、状态和所有 payload。

随后在全新路径演练：

~~~powershell
python <skill>\scripts\verify_recovery.py --source <primary-package> --mirror <mirror-package> --restore <new-isolated-restore-dir>
~~~

隔离重放顺序固定为 staged patch、unstaged patch、tracked 当前字节、untracked payload、需保留的 ignored payload。只有两份 package manifest、两份 bundle、所有受保护对象、每个 worktree 的状态/index/模式/哈希和 git fsck --full 全部通过，才进入集成。

## 4. 对分支提交分类

从执行时最新的远端默认分支建立唯一临时集成 worktree。对每个非默认分支按原提交顺序分类：

1. **已是祖先**：git merge-base --is-ancestor 成功，跳过。
2. **补丁等价**：用 git cherry 和稳定 patch-id 证明等价，跳过并记录等价提交。
3. **内容已覆盖**：只有路径、语义和相关测试共同证明后续版本完整覆盖时，标为仅备份。
4. **唯一有效提交**：按拓扑与原顺序进入候选 cherry-pick 队列。
5. **冲突、失败或产物类内容**：只保留在恢复包，等待用户或项目规则决定。

标题相同、作者相同、日期相近或最终 tree 相似都不能单独证明重复。不要自动选择冲突一侧，不整体 squash，不制造 merge commit。

## 5. 线性集成并测试

1. 候选从冻结后再次确认的 &lt;remote&gt;/&lt;default&gt; 创建。
2. 按记录顺序逐个 cherry-pick 唯一有效提交。
3. 每次遇到冲突立即 cherry-pick --abort，保留证据并停止；不要自行选 ours/theirs。
4. 新出现的未跟踪项只能成为通过测试的规范源码提交，或进入恢复包后从候选移除。
5. 运行项目全部必需测试，以及各被收口分支回执中声明的测试。
6. 运行 git diff --check、冲突标记扫描，并证明冻结默认提交是候选祖先、冻结区间没有 merge commit。

治理规则、迁移说明或其他流程性修改应作为独立提交，便于审查和回滚。

## 6. 发布默认分支

发布前重新读取 live remote。只有远端默认分支仍等于冻结 SHA 时，才把候选用普通 fast-forward push 推到默认分支：

~~~powershell
git -C <integration-worktree> push <remote> <candidate-40-sha>:refs/heads/<default>
~~~

默认分支禁止 --force 和 --force-with-lease。推送成功后立即用 ls-remote 读取 live SHA；源码已推送只代表历史发布，不代表运行时部署或激活。

## 7. 条件删除

第一个删除动作前重新检查：

- 同步程序仍暂停，Git 元数据没有新污染；
- 两份 package manifest、bundle 和隔离恢复回执仍有效；
- 所有冻结 refs、tags、worktrees、stash、index、工作树 payload 与删除计划一致；
- live remote 的每个待删分支仍处于冻结 SHA。

远端临时分支必须一次原子删除，并为每个 ref 指定冻结 tip：

~~~powershell
git push --atomic --force-with-lease=refs/heads/<branch-a>:<frozen-a-40-sha> --force-with-lease=refs/heads/<branch-b>:<frozen-b-40-sha> <remote> --delete <branch-a> <branch-b>
~~~

服务器不支持 atomic、任一 lease 失败或 ref 漂移时，一个也不删，不退化为逐条删除。

远端确认只剩默认分支后，才清理本地：

1. 根工作树切到默认分支并快进到最终 SHA。
2. 每个辅助 worktree 先核对路径、HEAD、dirty 状态和恢复清单；只移除清单中的 exact 路径，再用不带 --force 的 git worktree remove。
3. 只删除已备份、已分类且仍处于冻结 SHA 的本地分支。禁止通配符批量猜测。
4. stash 当前列表与冻结清单逐字一致时，按索引从大到小 drop，或一次 clear；不一致就停止。
5. 删除本次 refs/backup/branch-consolidation/&lt;stamp&gt;/ 临时 refs。保留 tags、两份恢复包和隔离恢复仓库。

## 8. 最终验收与同步恢复

运行只读验收：

~~~powershell
python <skill>\scripts\verify_acceptance.py --repo <repo> --remote <remote> --snapshot <primary-package> --expected-commit <final-40-sha> --output <acceptance.json>
~~~

用户要求连 ignored 产物一起清空时增加 --require-no-ignored。验收必须全部为 ok=true。

恢复同步程序原运行状态，再观察 Git 公共目录是否出现临时 ref、锁或历史倒退。污染重现就保留恢复包并报告验收未完成。清理后按项目要求复跑关键测试。

## 9. 回滚边界

删除开始后发现异常，立即停止后续删除。已经发布的远端默认分支不自动回退。

- 从有效 bundle 恢复本地 refs；远端同名 ref 仍不存在且用户原授权覆盖恢复时，才按冻结 SHA 重建。
- 同名远端 ref 被别人重建时不覆盖。
- worktree 按隔离演练的固定顺序重建 staged、unstaged、untracked 和 preserved ignored 内容。
- 根工作树原 dirty 状态恢复到独立 recovered/pre-consolidation-default worktree，避免覆盖已发布默认分支。

完成汇报区分：Git 历史发布、refs/worktree/工作区清理、测试、运行时部署和同步程序复核。只报告已有证据覆盖的状态。
