# Git on Windows 命令坑

## 这份说明管什么

在 Windows（git bash / MSYS2）上跑 git 时，有三类坑会让命令莫名失败：

1. **路径被 MSYS 自动转换**：命令里带 `/` 或 `:` 的 git 引用（如 `origin/master:file`）被改写成 `\` 和 `;`，git 报 `ambiguous argument`。
2. **文件被同步软件或编辑器锁住**：百度网盘 / OneDrive / PowerPoint 锁着某个文件或 `.git/index`，git 任何要写它的操作报 `unable to unlink old` 或 `unable to write .git/index`，merge / checkout 直接崩。
3. **同步客户端用云端旧快照回滚整个仓库**：双向同步的云盘把几天前的 `.git` 和工作区覆盖回来，提交历史倒退、已删目录复活。

这三类都不是 git 本身的错，是 Windows 环境问题，按对应 pattern 处理。

## 坑 1：MSYS 把 `REF:path` 里的 `/` `:` 转坏

`git show origin/master:.gitignore` 在 git bash 下可能报：

```
fatal: ambiguous argument 'origin\master;.gitignore': unknown revision or path
```

注意 `origin\master;.gitignore`——`/`→`\`、`:`→`;` 被 MSYS 路径转换搞坏了。

### Pattern: git-read-file-at-ref-via-catfile
- scenario: 读任意提交 / 分支下某个文件的内容，绕过 MSYS 对 `REF:path` 的路径转换
- use_when: `git show <REF>:<file>` 报 `ambiguous argument`，引用里的 `/` 或 `:` 被改写
- shell: bash (git bash / MSYS2)
- validated_shape:
  ```bash
  rev=$(git rev-parse <REF>)
  git cat-file -p "${rev}:<RELATIVE_PATH>"
  ```
- substitute_only: `<REF>`（如 `origin/master`）, `<RELATIVE_PATH>`（仓库内相对路径）
- preflight: `git rev-parse <REF>`（先确认引用能解析成 40 位 hash）
- env: none
- avoid: 反复给 `git show origin/master:file` 加引号——加引号没用，MSYS 在更早层转换；不要把 `:` 换成别的符号猜
- success_signal: 文件内容正常打印，没有 `ambiguous argument`
- capture_rule: 凡是 git bash 下 `<REF>:<path>` 形态报路径歧义，就先 `rev-parse` 再 `cat-file -p`

## 坑 2：文件被锁时仍要完成 merge / 解 PR 冲突

百度网盘 / OneDrive / Office 锁着某文件（如 `figure.pptx`）或 `.git/index`，导致：

```
error: unable to unlink old 'figure.pptx': Invalid argument
fatal: unable to write .git/index
```

merge / checkout 碰到被锁文件就崩。两种绕法，按需要选。

### Pattern: git-bypass-locked-file-assume-unchanged
- scenario: 某个被锁文件挡住 merge / checkout，但它在两个分支内容相同、根本不需要被改动
- use_when: `unable to unlink old <file>`，且确认该文件在 HEAD 和目标分支是同一个 blob（merge 不会真改它）
- shell: bash 或 PowerShell
- validated_shape:
  ```bash
  # 先确认两边是同一 blob（输出两个相同 hash 才安全）
  git rev-parse HEAD:<file>
  git rev-parse <TARGET_REF>:<file>
  # 让 git 假装它没变，跳过对它的检查
  git update-index --assume-unchanged <file>
  # ...完成 merge / 其它操作...
  # 事后务必撤销，否则以后该文件真变了 git 也看不到
  git update-index --no-assume-unchanged <file>
  ```
- substitute_only: `<file>`, `<TARGET_REF>`
- preflight: 两个 `rev-parse` 必须输出相同 hash；不同就不能用这招（说明 merge 真要改它）
- env: none
- avoid: 用完忘记 `--no-assume-unchanged`（会让该文件永久从 git 视野消失）；在两边 blob 不同时用它（会丢改动）
- success_signal: `git status` 里该文件消失，merge 能继续
- capture_rule: 被锁文件 + 两边同 blob + 只是挡路，就 assume-unchanged 临时绕过，事后立刻撤销

### Pattern: git-merge-pure-object-layer
- scenario: 工作区脏（CRLF 噪声 / 被锁文件 / 同步软件污染）但仍要完成一次 merge 并 push，完全不碰工作区文件
- use_when: 常规 `git merge` 因工作区脏或文件锁反复失败，而你只需要在对象层产出一个正确的 merge commit（典型：解一个 PR 的 `.gitignore` 类小冲突）
- shell: bash (git 2.38+，需 `merge-tree --write-tree`)
- validated_shape:
  ```bash
  head=$(git rev-parse HEAD)
  other=$(git rev-parse <OTHER_REF>)
  # 1. 内存里做三方合并，输出合并树 oid + 冲突清单（stage 1/2/3）
  git merge-tree --write-tree "$head" "$other"
  # 若有冲突文件，手动定其内容：把要用的版本 blob 写进 index 再 write-tree
  git read-tree <CONFLICTED_TREE_OID>
  git update-index --cacheinfo 100644 <CHOSEN_BLOB_OID> <CONFLICTED_PATH>
  clean_tree=$(git write-tree)
  # 2. 用干净树造 merge commit（两个父）
  mc=$(git commit-tree "$clean_tree" -p "$head" -p "$other" -m "Merge <OTHER_REF>")
  # 3. 验证合并树内容对（两边文件都在、无冲突标记）后，移动分支指针并 push
  git ls-tree -r "$mc" --name-only | grep <SANITY_PATTERN>
  git update-ref refs/heads/<BRANCH> "$mc"
  git push origin <BRANCH>
  ```
- substitute_only: `<OTHER_REF>`, `<CONFLICTED_TREE_OID>`, `<CHOSEN_BLOB_OID>`, `<CONFLICTED_PATH>`, `<BRANCH>`, `<SANITY_PATTERN>`
- preflight: `git --version`（确认支持 `merge-tree --write-tree`）；造完 `mc` 后先 `git ls-tree -r "$mc"` 抽查两边关键文件都在、`git cat-file -p "$mc:<file>"` 确认无 `<<<<<<<` 残留，再 `update-ref`
- env: none
- avoid: 直接 `git merge` 硬上（被锁文件 / CRLF 会反复崩）；`read-tree` 会动 index，但只要不 `checkout` 就不碰工作区文件；没验证合并树就 `update-ref` push
- success_signal: 远端分支更新成功，PR 状态变 MERGEABLE / CLEAN，工作区文件一个没动
- capture_rule: 工作区被同步软件 / CRLF 污染、又必须完成 merge 时，走纯对象层（merge-tree → commit-tree → update-ref），不碰工作区

## 为什么不直接修工作区

被同步软件锁的文件，你没法稳定地 unlink / checkout；CRLF 噪声会让几十个文件显示 `modified`、反复挡路。对象层操作（cat-file / merge-tree / commit-tree / update-ref）只读写 `.git/objects` 和 ref，绕开整个工作区，是这种环境下最稳的路子。前提：每一步都先验证（rev-parse 出 hash、ls-tree 抽查、cat-file 查冲突标记），再推进。

## 坑 3：同步客户端用云端旧快照回滚整个仓库

双向同步的云盘（百度网盘"同步空间"、OneDrive、Dropbox、坚果云）把云端滞后的旧快照当"新状态"下发，整个仓库——包括 `.git`——被覆盖回几天前。这不是锁文件那种"挡路"，是数据被静默改写，比坑 2 致命。

### Pattern: git-recover-from-cloud-sync-rollback
- scenario: 云同步客户端把仓库（含 `.git`）回滚成云端旧快照，需要识别症状并恢复到真实最新状态
- use_when: 出现"回滚四联征"中任意两条：
  1. 提交历史倒退——`git log` 的 HEAD 落后于记忆/远端，`git push` 报 non-fast-forward，说本地 "behind its remote counterpart"（明明刚提交过）
  2. 出现冲突副本文件——中文客户端形如 `<名字>_冲突文件_<用户>_<时间戳>.<ext>`，英文客户端形如 `<name> (conflicted copy).<ext>`
  3. 早已删除/改名的旧目录整棵复活（内容是旧布局）
  4. `.git/objects/` 里出现同步临时文件（`*.baiduyun.uploading.cfg`、`*.tmp.driveupload`）——`git fsck` 报 `bad sha1 file` / `garbage`，本身无害但证明同步客户端在写 `.git` 内部
- shell: bash + PowerShell
- validated_shape:
  ```bash
  # 0. 止血：先杀同步客户端，防止恢复过程中再次被覆盖
  #    PowerShell: Get-Process | Where-Object { $_.ProcessName -match '<SYNC_CLIENT_PATTERN>' } | Stop-Process -Force
  # 1. 确认远端是完整基准（分叉点 + 远端领先的提交都认识 = 远端完整）
  git fetch origin
  git log --oneline -5 origin/<BRANCH>
  git merge-base HEAD origin/<BRANCH>
  # 2. 抢救：reset 前把未推送的本地新内容（冲突副本里可能有）另存
  # 3. 恢复到远端最新
  git reset --hard origin/<BRANCH>
  # 4. 残留清理：冲突副本、复活的旧目录移入归档区（不直接删），
  #    移动被 Permission denied 挡住时按 directory-move-locked.md 扫进程 cwd
  # 5. 根因必须消除：把同步模式改成单向备份，或把仓库移出同步范围；
  #    否则客户端重启后必然复发
  ```
- substitute_only: `<BRANCH>`, `<SYNC_CLIENT_PATTERN>`（如 `baidu`、`onedrive`、`dropbox`、`nutstore`）
- preflight: 恢复基准必须是**远端**（GitHub 等），不能用本地 reflog——`.git` 整个被旧快照覆盖时 reflog 也是旧的；远端若也不完整，先从冲突副本和归档抢内容再说
- env: none
- avoid: 先修工作区文件再管 `.git`（历史不对，改了也会乱）；直接删冲突副本（里面可能有未推送的独有内容，先 diff 再归档）；恢复后不改同步模式（100% 复发）；把 `.git` 留在任何双向同步目录里
- success_signal: `git log` 回到最新提交、`git status` 干净、`git push` 正常 fast-forward；再无新冲突副本生成
- capture_rule: 2026-07-10 百度网盘实战沉淀（回滚 18 个提交，reset --hard origin/main 全量恢复）。新确认的同步客户端症状形态（临时文件后缀、冲突副本命名）补进四联征清单

