---
name: git-branch-consolidation
description: >
  把单个 Git 仓库彻底收口到远端默认分支，并可恢复地清理本地与远端辅助分支、worktree、stash 和未提交内容。
  用户说“所有分支合到 main/master”“本地远端只留一个分支”“旧分支、worktree、stash 全部清掉”
  “把整个仓库彻底收口”时必须使用。流程覆盖冻结现场、双份恢复包、bundle 隔离重放、有效工作集成、
  带 lease 的原子远端删除和最终验收。普通单分支 merge/rebase/PR 合并不触发；多个目录或多个仓库的整理
  使用 project-organizer。
compatibility: Git 2.39+, Python 3.10+; Windows PowerShell examples require PowerShell 5.1+.
---

# Git Branch Consolidation

把一个仓库的有效工作收口到选定远端的默认分支，最后本地和该远端各只留这个分支。先保护现场并演练恢复，再按代码关系集成和测试，最后精确清理。普通 merge commit 可以保留；仅用户或项目要求时采用线性历史。

## 完成合同

默认完成状态如下：

- 根工作树检出远端默认分支，本地默认分支、远端跟踪分支和 live remote 指向同一提交。
- 本地与远端 branch heads 只剩默认分支，只保留根工作树，stash 和普通 git status 为空。
- 所有冻结时存在的 tags 原样保留。
- 冻结时默认分支是最终提交的祖先，各分支、stash 和未提交内容中的有效工作已纳入最终版本；仅留在恢复包不等于完成集成。
- 两份恢复包哈希有效，bundle 可读，所有 worktree 的 staged、unstaged、untracked 和需保存的 ignored 内容已在隔离仓库重放。

用户明确要求保留某个长期分支、worktree、stash 或本地生成物时，把它写入例外清单，并相应修改完成合同。不要把“只留一个分支”解释成删除 tags。

## 适用边界

- 本技能处理一个 Git 仓库内部的全面收口。
- 普通一两个分支的合并直接走项目常规 Git 流程。
- 两个以上目录或仓库的迁移、归组和入口整理使用 project-organizer。
- Windows 出现云盘临时 ref、FETCH_HEAD 锁或并发写入时，可直接读取 [Windows Git 局部排错](references/recovery-contract.md#windows-git-局部排错)；普通排错不触发全面收口。

执行破坏性步骤前读取 [references/recovery-contract.md](references/recovery-contract.md)。其中定义恢复包、ignored 分类、远端删除和回滚字段。

## 1. 确定默认分支并冻结写入者

1. 读取仓库及上级 AGENTS.md、项目规则和测试入口。
2. 沿用任务及项目已确定的发布远端，用 git ls-remote --symref &lt;remote&gt; HEAD 确定默认分支；不猜 main/master。多个远端归属不清且影响删除范围时才询问；未纳入的远端保持原状，完成说明写明实际范围。
3. 按现有协作方式确认已知 Git 写入者、会改工作树的任务/IDE 和自动化已结束或交接；单次进程快照不能代替协调。
4. 区分单向备份与双向同步。正常单向备份仅因客户端运行、正在上传或暂停状态未知，不阻断收口；双向覆盖风险、真实回写或并发 Git 写入则阻断受影响的封包、集成或删除步骤。记录模式、监控范围及实际干扰证据，不自动暂停或强停客户端，暂停也不是冻结的唯一门槛。
5. 检查活动 merge、rebase、cherry-pick、revert、bisect、sequencer、unmerged index，以及子模块、LFS、稀疏检出或特殊 index 标志等普通快照未必覆盖的状态。先核对其内容能否保全；不能证明时保留现场，仅阻塞依赖它的封包或清理，不擅自重置，也不为此新建一套处理引擎。
6. 按恢复合同采集快照，两次间隔至少 2 秒；比较 live remote heads/tags、全部本地 refs、HEAD、reflog、stash、worktrees、index 和受保护 payload。已确认的纯可重建 ignored 缓存只比较根元数据及重建依据，不遍历其内部文件。两次一致不能覆盖已知写入者尚未交接的事实。

冻结之后允许本流程预期的临时 backup refs 和集成 worktree 变化。其他 ref、受保护文件、index、worktree 或 remote 漂移使相关快照失效；纯忽略缓存内部变化按上述例外处理，客户端上传进度不算仓库漂移。

## 2. 明确 ignored 内容的归口

git bundle 不能单独恢复 index、工作树、stash 各层状态、配置、hooks 或未跟踪文件。对每个 worktree 运行：

~~~powershell
git -C <worktree> status --porcelain=v1 --untracked-files=normal --ignored=matching -z
~~~

所有 !! 根路径必须逐项归为：

- preserve：唯一日志、结果、旧二进制、归档、凭据外的本地配置或其他不能重建的内容；写入哈希清单并复制到恢复包。
- reproducible：已确认整根只含可重建缓存或构建产物，并有锁文件或固定命令等重建依据；记录根元数据和依据，不在备份、冻结比较或恢复验证中遍历、复制或逐文件哈希。

无法判断时按 preserve 保存并继续；只有实际无法保存或恢复时阻塞相关清理。不因 .gitignore 命中就认定可删，不临时扩大忽略范围。tracked、untracked 和不可重建数据不适用缓存例外。

## 3. 建立并演练双份恢复包

恢复路径必须不存在、彼此独立，并位于仓库及所有 worktree 之外。准备 ignored-disposition.json 后运行：

~~~powershell
python <skill>\scripts\capture_recovery.py --repo <repo> --remote <remote> --primary <primary-package> --mirror <mirror-package> --stamp <safe-unique-stamp> --ignored-disposition <ignored-disposition.json>
~~~

即使没有 ignored 内容，也可以省略最后一个参数。脚本会：

- 显式取回 live remote heads/tags，并在 refs/backup/branch-consolidation/&lt;stamp&gt;/ 下固定所有需保存对象；
- 保存二进制 staged/unstaged patch、index、tracked 当前字节、untracked payload 和需保留的 ignored payload；
- 保存 refs、reflog、stash、worktree、Git 元数据，以及受保护文件的模式和 SHA-256；纯可重建缓存只保存根记录与重建依据；
- 从明确 backup refs 创建 repository-recovery.bundle，校验后复制成字节一致的第二份包；
- 封包前后重新核对 remote、refs、reflog、stash、worktrees、index 和受保护 payload；缓存按根记录比较，除本流程预期变化外必须一致。

随后在全新路径演练：

~~~powershell
python <skill>\scripts\verify_recovery.py --source <primary-package> --mirror <mirror-package> --restore <new-isolated-restore-dir>
~~~

存在指向工作树外的 junction/symlink 时默认拒绝隔离恢复；仅按恢复合同的准确 `--external-link-allowlist` 恢复获授权链接本体，不跟随目标。旧包兼容与逐工作树 `links.json` 说明见恢复合同。

隔离重放顺序固定为 staged patch、unstaged patch、tracked 当前字节、untracked payload、需保留的 ignored payload。只有两份 package manifest、两份 bundle、所有受保护对象、每个 worktree 的状态/index/模式/哈希和 git fsck --full 全部通过，才进入集成。

## 4. 判断哪些工作需要集成

从再次核实的远端默认分支建立临时集成 worktree。结合分支提交、stash 和各工作树未提交内容判断：

1. **已是祖先**：git merge-base --is-ancestor 成功，跳过。
2. **补丁等价**：用 git cherry 和稳定 patch-id 证明等价，跳过并记录等价提交。
3. **内容已覆盖**：只有路径、语义和相关测试共同证明后续版本完整覆盖时，标为仅备份。
4. **唯一有效工作**：按依赖关系用普通合并、选择提交或应用未提交改动纳入候选；保留必要提交关系。
5. **无效或仅产物内容**：明确理由后留在恢复包；仍有效的改动不能因冲突就归为放弃。

标题、作者、日期或 tree 相似不能单独证明重复。冲突先读双方改动、调用关系和测试；能够明确处理则自主解决，仅无法自行确定的功能、数据或科研含义取舍才询问，不机械选择 ours/theirs。

## 5. 集成并测试

1. 候选从冻结后再次确认的 &lt;remote&gt;/&lt;default&gt; 创建。
2. 采用能保全有效工作的合并方式；默认允许 merge commit，线性历史仅按明确要求执行。
3. 自主解决能由代码关系和测试确定的冲突；有实质语义歧义时保留现场，只暂停相关集成和依赖它的删除，继续独立工作。
4. 有效源码、stash 和未提交改动经检查后纳入最终版本；数据与产物按用途保留，不能只为工作树干净而丢弃。辅助 worktree 中的不可重建数据在移除前还须有可直接使用的存续副本，恢复包只负责兜底。
5. 运行项目要求及改动影响范围内的测试，结合旧分支测试记录判断必要补测，不机械重跑每份历史回执。
6. 运行 git diff --check、冲突标记扫描并证明冻结默认提交是候选祖先；明确要求线性时再检查新增区间无 merge commit。

治理规则、迁移说明或其他流程性修改应作为独立提交，便于审查和回滚。

## 6. 发布默认分支

发布前重新读取 live remote。只有远端默认分支仍等于冻结 SHA 时，才把候选用普通 fast-forward push 推到默认分支：

~~~powershell
git -C <integration-worktree> push <remote> <candidate-40-sha>:refs/heads/<default>
~~~

默认分支禁止 --force 和 --force-with-lease。推送成功后立即用 ls-remote 读取准确 ref 的 live SHA。结果不明时先查远端：已等于候选 SHA 就跳过重推；仍等于原冻结 SHA，且本地候选和发布门均未变化时，最多补一次普通 push；其他 SHA 或读取失败则停止受影响步骤。commit、merge、checkout 失败不自动重跑，删除不自动重试。源码已推送只代表 Git 历史发布，不代表运行时部署、激活或百度备份完成。

## 7. 条件删除

第一个删除动作前重新检查：

- 每个待删分支、stash 和工作区中的有效改动已合入或经实际比较确认覆盖；仅有恢复包或分类标签不能放行；
- 已知写入者协调仍有效，没有双向覆盖风险、真实回写或并发 Git 写入；正常单向备份运行/上传/暂停未知不阻断；
- 两份 package manifest、bundle 和隔离恢复回执仍有效；
- 所有冻结 refs、tags、worktrees、stash、index、工作树 payload 与删除计划一致；
- live remote 的每个待删分支仍处于冻结 SHA。

在干净的候选工作区先运行下文验收命令，并增加 `--check-integration-only`；它检查当前候选的工作归并，允许尚待清理的分支和 stash 存在，不执行删除。需保留内容比较或数据存续位置时，用 `--integration-records` 接入已有分类记录，字段见恢复合同。通过后仍须核对上述现场和恢复条件。

远端临时分支必须一次原子删除，并为每个 ref 指定冻结 tip：

~~~powershell
git push --atomic --force-with-lease=refs/heads/<branch-a>:<frozen-a-40-sha> --force-with-lease=refs/heads/<branch-b>:<frozen-b-40-sha> <remote> --delete <branch-a> <branch-b>
~~~

服务器不支持 atomic、任一 lease 失败或 ref 漂移时，一个也不删，不退化为逐条删除。

远端确认只剩默认分支后，才清理本地：

1. 根工作树切到默认分支并快进到最终 SHA。
2. 每个辅助 worktree 先核对路径、HEAD、dirty 状态和恢复清单，确认有效工作已集成、不可重建数据已有可直接使用的存续副本；只移除清单中的 exact 路径，再用不带 --force 的 git worktree remove。
3. 只删除有效改动已归并且仍处于冻结 SHA 的本地分支。禁止通配符批量猜测。
4. stash 的 staged、unstaged、untracked 改动均已归并，且当前列表与冻结清单逐字一致时，按索引从大到小 drop，或一次 clear；不一致就停止。
5. 删除本次 refs/backup/branch-consolidation/&lt;stamp&gt;/ 临时 refs。保留 tags、两份恢复包和隔离恢复仓库。

## 8. 最终验收与备份状态复核

运行只读验收：

~~~powershell
python <skill>\scripts\verify_acceptance.py --repo <repo> --remote <remote> --snapshot <primary-package> --expected-commit <final-40-sha> --output <acceptance.json>
~~~

用户要求连 ignored 产物一起清空时增加 --require-no-ignored；用户或项目要求线性历史时增加 --require-linear-history。默认允许普通 merge commit，验收仍检查冻结默认提交是最终提交的祖先。所有适用检查必须为 ok=true。

保持客户端原状；只有本任务曾另获授权改变其状态时，才按该授权恢复原状态。复核 Git 公共目录是否出现临时 ref、锁或历史倒退；真实污染重现则保留恢复包并报告受影响验收未完成。正常上传本身不影响 Git 验收。清理后按项目要求复跑关键测试。

## 9. 回滚边界

删除开始后发现异常，立即停止后续删除。已经发布的远端默认分支不自动回退。

- 从有效 bundle 恢复本地 refs；远端同名 ref 仍不存在且用户原授权覆盖恢复时，才按冻结 SHA 重建。
- 同名远端 ref 被别人重建时不覆盖。
- worktree 按隔离演练的固定顺序重建 staged、unstaged、untracked 和 preserved ignored 内容。
- 根工作树原 dirty 状态恢复到独立 recovered/pre-consolidation-default worktree，避免覆盖已发布默认分支。

完成汇报区分：Git 历史发布、refs/worktree/工作区清理、测试、运行时部署和百度等备份客户端状态复核；Git 远端验证不证明百度备份完成。只报告已有证据覆盖的状态。
