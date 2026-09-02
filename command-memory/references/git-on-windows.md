# Git on Windows 命令坑

## 这份说明管什么

在 Windows（PowerShell / git bash / MSYS2）上跑 git 时，有七类坑会让命令失败或越过提交范围：

1. **路径被 MSYS 自动转换**：命令里带 `/` 或 `:` 的 git 引用（如 `origin/master:file`）被改写成 `\` 和 `;`，git 报 `ambiguous argument`。
2. **文件被同步软件或编辑器锁住**：百度网盘 / OneDrive / PowerPoint 锁着某个文件或 `.git/index`，git 任何要写它的操作报 `unable to unlink old` 或 `unable to write .git/index`，merge / checkout 直接崩。
3. **同步客户端用云端旧快照回滚整个仓库**：双向同步的云盘把几天前的 `.git` 和工作区覆盖回来，提交历史倒退、已删目录复活。
4. **同一文件混有批准与未批准改动**：整文件暂存会把未授权内容带入提交，手工编写 patch 又容易因 hunk 行数错误损坏。
5. **云盘临时文件进入 Git 元数据**：上传临时 ref 会让 Git 报 `bad object`，`FETCH_HEAD` 被占用会让 `fetch` 报 `Permission denied`。
6. **并行任务共用同一 worktree**：即使修改路径不同，也会共用 index 和提交状态；`COMMIT_EDITMSG` / index 占用、`HEAD` 或暂存文件集合漂移都可能把另一任务的内容带入本次提交。
7. **工作树已等于远端但快进仍被阻断**：远端继续推进后，本地相关文件已经逐项等于新 tip，Git 仍因它们相对旧 `HEAD` 显示为修改而拒绝普通快进。

按对应 pattern 处理。第 4、6、7 类不一定是 Git 故障，但在非交互式 Windows 任务里容易因共享状态或命令形态选错而造成范围越界。

## 目录

- [坑 1：MSYS 引用路径转换](#pitfall-1)
- [坑 2：文件或 index 被锁](#pitfall-2)
- [坑 3：云同步回滚仓库](#pitfall-3)
- [坑 4：同一文件混合改动](#pitfall-4)
- [坑 5：临时 ref 或 FETCH_HEAD 锁](#pitfall-5)
- [坑 6：并行任务共享 worktree](#pitfall-6)
- [坑 7：工作树已等于远端但快进仍被阻断](#pitfall-7)

<a id="pitfall-1"></a>

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

<a id="pitfall-2"></a>

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

### Pattern: git-commit-pure-object-layer
- scenario: 已按允许清单完成 `git add`，但 `git commit` 因同步软件锁住 `.git/index` 报 `unable to write new index file`；已经排除并行 Git 写入，仍需创建一个单父提交
- use_when: 报错准确指向 index 重写，已确认没有其他任务或 Git 进程写同一 worktree，且两次只读检查的 `HEAD` 和完整暂存文件集合一致；当前不在 merge / rebase / cherry-pick 状态，且本次提交不依赖必须运行的 commit hook。只绕过稳定 index 的重写，不绕过内容审查
- shell: PowerShell 或 bash；下面的变量写法为 PowerShell
- validated_shape:
  ```powershell
  $head = (git rev-parse HEAD).Trim()
  git diff --cached --name-status
  git diff --cached --check
  if (git ls-files -u) { throw "Unmerged index entries are present" }
  $tree = (git write-tree).Trim()
  $commit = (git commit-tree $tree -p $head -m "<MESSAGE>").Trim()
  git cat-file -p $commit
  git diff-tree --no-commit-id --name-status -r $commit
  # 仅当候选提交的父提交和文件清单都符合预期时才更新分支
  git update-ref -m "commit: <MESSAGE>" refs/heads/<BRANCH> $commit $head
  git status --short --branch
  git push origin <BRANCH>
  ```
- substitute_only: `<MESSAGE>`, `<BRANCH>`；提交文件清单必须沿用此前核验过的明确路径，不从工作区重新猜测
- preflight: `git rev-parse --show-toplevel` 确认实际仓库根；连续两次读取 `HEAD`、`git status --short`、`git diff --cached --name-status` 和 `git diff --cached --check`，结果必须稳定且只含批准范围；`git ls-files -u` 必须为空；确认当前分支和远端目标未分叉，并排除已知并行写入者
- candidate_check: `git cat-file -p $commit` 的 `parent` 必须等于 `$head`；`git diff-tree --no-commit-id --name-status -r $commit` 必须只列允许文件；候选不正确时不执行 `update-ref`
- avoid: `COMMIT_EDITMSG` 被占用、存在已知并行写入者、`HEAD` / 暂存集合发生漂移时，禁止从共享 index 执行 `write-tree` 或 `commit-tree`，改走坑 6；不要删除 `index.lock`、停止同步客户端、`reset` / `checkout` 工作区或用 `git add .` 扩大范围；`git commit-tree` 不运行 hooks，若需要签名、`pre-commit` 或 `commit-msg` 校验就停止并先恢复正常 `git commit`
- success_signal: 分支通过带旧值校验的 `update-ref` 前进一个提交，`git status` 中目标文件干净、无关改动仍保留，随后远端 push 为 fast-forward
- capture_rule: 单提交的对象层回退是已核验暂存区的窄范围应急路径；先验证 tree/commit/差异，再原子更新 ref，不能把它当作普通提交的默认替代

## 为什么不直接修工作区

被同步软件锁的文件，你没法稳定地 unlink / checkout；CRLF 噪声会让几十个文件显示 `modified`、反复挡路。对象层操作（cat-file / merge-tree / commit-tree / update-ref）只读写 `.git/objects` 和 ref，绕开整个工作区，是这种环境下最稳的路子。前提：每一步都先验证（rev-parse 出 hash、ls-tree 抽查、cat-file 查冲突标记），再推进。

<a id="pitfall-3"></a>

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

<a id="pitfall-4"></a>

## 坑 4：同一文件混合改动，手工 patch 又已损坏

同一文件同时包含本次允许提交的改动和其他任务的未授权改动时，`git add <file>` 会扩大提交范围。
`git add -p` 依赖交互选择，也不适合作为自动化任务的唯一保护。若手工 patch 已报 hunk 行数或格式错误，
继续修改 `@@ -a,b +c,d @@` 计数会把内容审查变成脆弱的文本记账。更稳的做法是从固定远端基线建立
detached worktree，只重建批准内容，再让 Git 自动生成和检查 patch。

### Pattern: git-stage-approved-same-file-changes-via-detached-worktree
- scenario: 原工作区的同一文件混有批准与未批准改动，需要非交互式地只提交批准内容，同时保持原工作区和暂存区不变
- use_when: 整文件暂存会越权；或手工 patch 已报 `corrupt patch`、`patch fragment without header`、hunk 行数不匹配
- shell: PowerShell + Git for Windows
- validated_shape:
  ```powershell
  $repoRoot = "<REPO_ROOT>"
  $branch = "<BRANCH>"
  $approvedPaths = @("<PATH_1>", "<PATH_2>")

  git -C $repoRoot fetch origin
  if ($LASTEXITCODE -ne 0) { throw "fetch failed" }
  $base = (git -C $repoRoot rev-parse "refs/remotes/origin/$branch").Trim()
  if ($base -notmatch '^[0-9a-f]{40}$') { throw "remote baseline is not a full commit id" }

  $tempRoot = Join-Path ([IO.Path]::GetTempPath()) ("git-approved-" + [guid]::NewGuid().ToString("N"))
  $isolatedTree = Join-Path $tempRoot "worktree"
  $patchPath = Join-Path $tempRoot "approved.patch"
  New-Item -ItemType Directory -Path $tempRoot -ErrorAction Stop | Out-Null
  git -C $repoRoot worktree add --detach $isolatedTree $base
  if ($LASTEXITCODE -ne 0) { throw "detached worktree creation failed" }

  # 只在 $isolatedTree 中重建已经批准的内容，并完成该 skill / 项目的验证。
  git -C $isolatedTree diff --check -- $approvedPaths
  if ($LASTEXITCODE -ne 0) { throw "reconstructed changes failed diff check" }
  git -C $isolatedTree diff --binary --full-index "--output=$patchPath" -- $approvedPaths
  if ($LASTEXITCODE -ne 0) { throw "Git failed to generate the patch" }

  git -C $isolatedTree apply --cached --check -- $patchPath
  if ($LASTEXITCODE -ne 0) { throw "generated patch does not apply to the clean index" }
  git -C $isolatedTree apply --cached -- $patchPath
  if ($LASTEXITCODE -ne 0) { throw "staging generated patch failed" }
  git -C $isolatedTree diff --cached --name-status
  git -C $isolatedTree diff --cached --check
  git -C $isolatedTree diff --cached -- $approvedPaths
  ```
- substitute_only: `<REPO_ROOT>`, `<BRANCH>`, `<PATH_1>...`；`approvedPaths` 必须来自已确认允许清单，不从当前工作区文件名猜测
- preflight: 记录原仓库 `HEAD`、分支、`git status --short` 和 `git diff --cached --name-status`；确认远端目标分支是允许的发布基线；目标分支已在原工作区检出时必须保持 `--detach`
- candidate_check: 暂存文件集合和完整差异只能包含批准内容；候选提交创建后再用 `git diff-tree --no-commit-id --name-status -r <COMMIT>` 和 `git show --stat --oneline <COMMIT>` 复核；推送前重新 `fetch`，远端分支必须仍等于 `$base`
- cleanup: 只有候选提交已接受、需要的 push 已成功且原工作区复核无变化后，才运行 `git -C $repoRoot worktree remove $isolatedTree` 并删除本次 `$tempRoot`；失败时保留路径、`$base` 和恢复说明
- optional_tool: `git-hunk` 只能在已经安装时辅助枚举和规划 hunk；不自动安装、不形成默认依赖，也不能替代暂存后的完整差异复核
- avoid: 不在原工作区执行整文件 `git add`、`stash`、`reset`、`checkout`、`restore` 或覆盖目标文件；不把原工作区未批准内容复制进隔离副本；手工 patch 第一次确认是 hunk 计数或格式损坏后，不继续修改 header 计数；不 force push
- success_signal: 隔离 worktree 的暂存差异只含批准内容，候选提交基于固定远端提交，原工作区 `HEAD`、暂存区和未提交内容保持不变
- capture_rule: 同文件混合改动先隔离重建，再由 Git 生成 patch 并执行 `--cached --check`；内容范围不清或远端基线变化时失败关闭

### Pattern: git-align-authorized-local-worktree-after-isolated-release
- scenario: 批准内容已经在 detached worktree 中提交并发布，用户随后明确要求把同一补丁更新到原本地工作副本；原工作副本仍有必须保留的其他改动，甚至与批准改动位于同一文件
- use_when: 发布提交及其唯一父提交已固定；这次“更新本地工作副本”取得了发布之后的单独明确授权；可以准确列出会改变行为的目标文件、仅含说明文字的混合文件以及批准 hunk
- shell: PowerShell + Git for Windows；文本修改使用 `apply_patch`
- preflight: 先确认已知并行写入者当前的 Git 写操作已经结束，记录本地 `HEAD`、分支、`git status --short` 和完整暂存清单；对这些状态做两次有界只读检查，只有两次一致才继续。发布批准本身不等于本地修改授权，缺少用户后续明确要求时停止
- parent_match: 对每个会改变执行行为的目标文件，用 `git hash-object --path=<RELATIVE_PATH> -- <RELATIVE_PATH>` 计算当前工作树经 Git 过滤后的 blob，并与 `<RELEASE_COMMIT>^:<RELATIVE_PATH>` 比较；全部相等才说明本地文件仍处于发布补丁的准确起点。任何一个不相等都停止，不覆盖、不整文件复制
- apply_rule: 只用 `apply_patch` 应用已经审查过的准确 hunk。行为文件可以应用完整批准差异；含有其他任务改动的文档只应用获批的文字 hunk，不能用 checkout、restore、整文件复制或从隔离副本覆盖
- candidate_check: 修改后，每个行为目标的过滤后 blob 必须等于 `<RELEASE_COMMIT>:<RELATIVE_PATH>`；完整暂存清单必须与修改前一致；逐项确认同文件内原有的未批准 hunk 仍在。随后运行相关完整测试，不以单个冒烟测试代替已有完整套件
- publication_boundary: 本地对齐不再生成提交或再次推送；远端发布已经完成，本步骤只让用户当前工作副本取得同一批准改动。若发布后远端又有新提交，不把这些新内容顺带带入本地
- avoid: 不把“源码已推送”解释成可以改原工作副本；不在并行写入未结束或两次状态不一致时继续；不 stash、reset、checkout、restore、清空暂存区、覆盖整文件、重放未知工作树差异或再次提交推送
- success_signal: 行为目标的 blob 与发布提交一致，暂存集合未变，原有未批准 hunk 完整保留，相关完整测试通过；汇报应明确说出哪些本地脚本或模块已经可直接使用
- capture_rule: 隔离发布和本地启用是两次授权；本地启用只在准确父版本、稳定现场和逐 hunk 保留其他改动的条件下进行

<a id="pitfall-5"></a>

## 坑 5：云盘临时 ref 或 FETCH_HEAD 锁挡住 fetch

同步客户端可能在 `.git/refs/heads/` 短暂生成 `*.baiduyun.uploading.cfg`，Git 会把它当作分支引用并报
`fatal: bad object refs/heads/<name>.baiduyun.uploading.cfg`。也可能只有 `.git/FETCH_HEAD` 正被占用，
使 `git fetch` 报 `cannot open '.git/FETCH_HEAD': Permission denied`。单独出现其中一项，只证明 Git
元数据正受外部写入或锁影响，不足以按“坑 3”判定整个仓库已被旧快照回滚。

### Pattern: git-verify-remote-tip-when-fetch-metadata-is-blocked
- scenario: `fetch` 被临时 ref 或 `FETCH_HEAD` 锁阻断，但当前步骤只需要确认远端分支是否等于预期提交
- use_when: 已取得明确的 `bad object refs/...uploading.cfg` 或 `FETCH_HEAD: Permission denied`；没有 merge、rebase、checkout 或下载远端对象的需求
- shell: PowerShell + Git for Windows
- validated_shape:
  ```powershell
  $repoRoot = "<REPO_ROOT>"
  $branch = "<BRANCH>"

  $gitDirText = (git -C $repoRoot rev-parse --git-dir).Trim()
  if ($LASTEXITCODE -ne 0) { throw "cannot resolve git dir" }
  if ([IO.Path]::IsPathRooted($gitDirText)) {
      $gitDir = [IO.Path]::GetFullPath($gitDirText)
  } else {
      $gitDir = [IO.Path]::GetFullPath((Join-Path $repoRoot $gitDirText))
  }
  Get-ChildItem -LiteralPath (Join-Path $gitDir "refs\heads") -Force -ErrorAction SilentlyContinue |
      Where-Object Name -like "*.baiduyun.uploading.cfg" |
      Select-Object FullName, Length, LastWriteTime
  Get-Item -LiteralPath (Join-Path $gitDir "FETCH_HEAD") -Force -ErrorAction SilentlyContinue |
      Select-Object FullName, Length, LastWriteTime, Attributes

  $localHead = (git -C $repoRoot rev-parse HEAD).Trim()
  $remoteLines = @(git -C $repoRoot ls-remote --exit-code --refs origin "refs/heads/$branch")
  if ($LASTEXITCODE -ne 0 -or $remoteLines.Count -ne 1) { throw "remote branch lookup failed or was ambiguous" }
  $remoteHead = ($remoteLines[0] -split '\s+')[0].Trim()
  if ($localHead -notmatch '^[0-9a-f]{40}$' -or $remoteHead -notmatch '^[0-9a-f]{40}$') {
      throw "local or remote commit is not a full SHA"
  }
  [pscustomobject]@{ LocalHead = $localHead; RemoteHead = $remoteHead; Equal = ($localHead -eq $remoteHead) }
  ```
- substitute_only: `<REPO_ROOT>`, `<BRANCH>`；远端名不是 `origin` 时必须使用已核实的实际 remote，不从报错文本猜
- diagnosis: 先检查报错指向的准确临时 ref 或 `FETCH_HEAD`，再核对真实 `HEAD`、目标远端 SHA 和当前 Git 状态；临时 ref 消失后可运行 `git fsck --no-reflogs --connectivity-only`，只有 dangling 对象不等于损坏，出现 missing/bad object 才停止并升级排查；只有同时出现历史倒退、冲突副本、旧目录复活等“坑 3”迹象时，才升级为云同步回滚处理
- retry_boundary: 临时 ref 已自行消失或锁状态已经变化，且后续确实需要远端对象时，可以重新执行一次 `fetch`；同一状态下不原样重试，第二次仍失败就停止
- scope_limit: `ls-remote` 只读取服务器端 ref，不更新本地 `origin/<BRANCH>`、不写 `FETCH_HEAD`、不下载对象；它只适合 push 后确认远端 tip、发布 helper 前核对 SHA 等只读门槛，不能替代 merge、rebase、checkout 或对象完整性检查前的 `fetch`
- avoid: 不因单个临时文件就停止同步客户端、删除 `.git` 内文件、清理 refs、reset 仓库或宣称发生回滚；不把 `ls-remote` 的成功说成本地远端跟踪分支已更新；不在未知并发 Git 操作仍运行时继续写仓库
- success_signal: 唯一远端分支返回完整 40 位 SHA，只读核验结论明确，本地 Git 元数据未被该命令修改；若任务需要对象，则等阻断状态改变后正常 `fetch` 成功再继续
- capture_rule: fetch 元数据被临时 ref 或锁阻断时，先缩小诊断范围；只读核验用 `ls-remote`，需要对象仍必须等到 `fetch` 恢复

### Pattern: git-recover-transient-schannel-tls-preflight
- scenario: Git for Windows 或发布/验收 helper 在任何仓库写入、UI 更新或运行时核验前，远端预检报 `schannel: failed to receive handshake` 或 `SSL/TLS connection failed`
- use_when: 已确认报错发生在访问准确远端和分支的 TLS 建连阶段；当前只需判断连接是否恢复，并决定能否重新运行原验收
- shell: PowerShell + Git for Windows
- validated_shape:
  ```powershell
  $repoRoot = "<REPO_ROOT>"
  $remoteName = "<REMOTE>"
  $branchName = "<BRANCH>"

  $remoteLines = @(git -C $repoRoot ls-remote --exit-code --refs $remoteName "refs/heads/$branchName")
  if ($LASTEXITCODE -ne 0 -or $remoteLines.Count -ne 1) {
      throw "remote TLS/read probe failed or branch result was ambiguous"
  }
  $remoteCommit = (($remoteLines[0] -split '\s+')[0]).Trim()
  if ($remoteCommit -notmatch '^[0-9a-f]{40}$') { throw "remote commit is not a full SHA" }
  $remoteCommit
  ```
- substitute_only: `<REPO_ROOT>`, `<REMOTE>`, `<BRANCH>`；使用任务已经核实的远端和分支，不因 TLS 报错改写 remote URL、协议或目标分支
- diagnosis: `schannel` 是 Git for Windows 使用的 Windows TLS 后端；握手失败只证明当次加密传输没有建立完成，常见于临时网络、代理链路或远端连接中断。它本身不证明仓库损坏、Skill 失败、远端分支不存在或本机证书配置损坏
- retry_boundary: 只执行一次上述窄范围只读探针；探针成功后可用原提交、原 Skill 集合和原范围参数重新运行一次原验收。探针失败或原验收再次出现同类 TLS 错误时停止并报告网络阻断，不循环重试
- acceptance_count: 在运行时核验开始前因 TLS 或远端预检中止的调用不计入“完整同步 + `-VerifyOnly`”或“两次后台 `-VerifyOnly`”的验收轮次；连接恢复后从第一次完整有效调用重新计数
- scope_limit: `ls-remote` 成功只证明该远端分支此刻可读取，并返回唯一 40 位 SHA；它不下载对象、不更新本地远端跟踪分支，也不能单独证明发布、同步或运行时验收成功
- avoid: 不把第一次 TLS 失败记成仓库、Skill 或证书故障；不先关闭 `http.sslVerify`、切换 `http.sslBackend`、替换 CA、凭据或 remote URL；不修改仓库、CC Switch 数据库或运行时目录来绕过网络错误
- success_signal: 只读探针返回唯一完整 SHA，随后原验收从头执行并按其自身全部判据通过；完成结论来自原验收，不来自 `ls-remote`
- capture_rule: TLS 预检失败先缩小为一次只读远端探针；网络恢复后重跑原验收，预检中断不占用正式验收轮次

<a id="pitfall-6"></a>

## 坑 6：并行任务共用同一 worktree，提交状态相互污染

同一 worktree 只有一份 index。一个任务暂存的文件会进入另一个任务看到的提交候选；另一个任务执行
`git commit` 时，也可能更新共同的 `HEAD` 或占用 `COMMIT_EDITMSG`。Git 的 linked worktree 会共享对象和
refs，但 `HEAD`、index 等状态按 worktree 分开，因此适合给并行任务建立独立提交环境
（[Git 官方说明](https://git-scm.com/docs/git-worktree.html)）。

### Pattern: git-isolate-after-shared-worktree-concurrency
- scenario: `git commit` 被 `COMMIT_EDITMSG` / index 占用阻断，或本任务未操作时 `HEAD`、暂存文件集合、目标文件提交归属发生变化，且存在另一个可能写入同一仓库的任务
- use_when: 已有具体证据把另一写入者定位到同一 Git 仓库；双方即使修改不同路径也适用。只有其他任务处于 active 状态、但仓库无关时不触发
- shell: PowerShell + Git for Windows
- validated_shape:
  ```powershell
  $repoRoot = "<REPO_ROOT>"
  $branch = "<BRANCH>"
  $approvedPaths = @("<PATH_1>", "<PATH_2>")

  # 只读保存共享 worktree 现场；这些暂存内容不再作为本次提交来源。
  $sharedHead = (git -C $repoRoot rev-parse HEAD).Trim()
  $sharedStage = @(git -C $repoRoot diff --cached --name-status)
  $gitDir = (git -C $repoRoot rev-parse --absolute-git-dir).Trim()
  $commitMessagePath = Join-Path $gitDir "COMMIT_EDITMSG"
  Get-Item -LiteralPath $commitMessagePath -Force -ErrorAction SilentlyContinue |
      Select-Object FullName, Length, LastWriteTime, Attributes

  # 向已知任务说明准确仓库和路径边界；若其正在执行 Git 写操作，先等该次操作结束，不抢锁。
  $remoteLines = @(git -C $repoRoot ls-remote --exit-code --refs origin "refs/heads/$branch")
  if ($LASTEXITCODE -ne 0 -or $remoteLines.Count -ne 1) { throw "remote branch lookup failed" }
  $base = ($remoteLines[0] -split '\s+')[0].Trim()
  if ($base -notmatch '^[0-9a-f]{40}$') { throw "remote baseline is not a full commit id" }
  git -C $repoRoot cat-file -e "$base^{commit}"
  if ($LASTEXITCODE -ne 0) { throw "remote baseline object is not available locally" }

  $taskRoot = Join-Path ([IO.Path]::GetTempPath()) ("git-concurrent-" + [guid]::NewGuid().ToString("N"))
  $isolatedTree = Join-Path $taskRoot "worktree"
  New-Item -ItemType Directory -Path $taskRoot -ErrorAction Stop | Out-Null
  git -C $repoRoot worktree add --detach $isolatedTree $base
  if ($LASTEXITCODE -ne 0) { throw "detached worktree creation failed" }

  # 只在 $isolatedTree 中重建批准内容，不复制共享 index 或未知中间文件。
  git -C $isolatedTree diff --check -- $approvedPaths
  if ($LASTEXITCODE -ne 0) { throw "reconstructed changes failed diff check" }
  git -C $isolatedTree add -- $approvedPaths
  if ($LASTEXITCODE -ne 0) { throw "staging approved paths failed" }
  git -C $isolatedTree diff --cached --name-status
  git -C $isolatedTree diff --cached --check
  if ($LASTEXITCODE -ne 0) { throw "staged changes failed diff check" }
  git -C $isolatedTree diff --cached -- $approvedPaths
  git -C $isolatedTree commit -m "<MESSAGE>"
  if ($LASTEXITCODE -ne 0) { throw "isolated commit failed" }
  $candidate = (git -C $isolatedTree rev-parse HEAD).Trim()
  $candidateParent = (git -C $isolatedTree rev-parse "$candidate^").Trim()
  if ($candidateParent -ne $base) { throw "candidate parent is not the fixed baseline" }
  git -C $isolatedTree diff-tree --no-commit-id --name-status -r $candidate

  $remoteAfter = @(git -C $repoRoot ls-remote --exit-code --refs origin "refs/heads/$branch")
  if ($LASTEXITCODE -ne 0 -or $remoteAfter.Count -ne 1) { throw "remote recheck failed" }
  if ((($remoteAfter[0] -split '\s+')[0].Trim()) -ne $base) { throw "remote baseline moved" }
  git -C $isolatedTree push origin "$candidate`:refs/heads/$branch"
  ```
- substitute_only: `<REPO_ROOT>`, `<BRANCH>`, `<PATH_1>...`, `<MESSAGE>`；批准路径来自已确认范围，不从共享暂存区或另一个任务的文件名猜测
- preflight: 记录共享 worktree 的 `HEAD`、分支、状态和完整暂存清单；把并行写入证据定位到准确仓库；已知 Git 写操作结束后再顺序创建 worktree，不结束进程、不抢锁
- candidate_check: 隔离提交只能有固定基线这一个父提交，完整 `git diff-tree` 只能包含批准路径；推送前远端 tip 必须仍等于基线；当前任务没有对原共享 worktree 执行任何写入、清理或还原
- cleanup: 只有候选提交通过范围检查并成功推送后，才用 `git worktree remove` 移除准确隔离 worktree；失败时保留路径、基线 SHA 和恢复说明
- avoid: 不删除 `COMMIT_EDITMSG`、`index.lock` 或其他 Git 元数据，不停止未知进程，不在共享 index 上运行 `commit-tree`，不清空、取消暂存或复用共享暂存区，不用 `stash`、`reset`、`checkout`、`restore` 伪造干净状态，不因一个锁就宣称云盘回滚
- success_signal: 本次候选提交基于固定远端提交且只含批准路径，远端仅发生一次 fast-forward；原共享 worktree 的文件、index 和 `HEAD` 未被本任务改动
- capture_rule: 并行任务只要共用同一 worktree，就不能靠“文件路径不同”判断提交隔离；出现提交锁或状态漂移后，保存现场、放弃共享 index，并在独立 worktree 重建本次批准提交

<a id="pitfall-7"></a>

## 坑 7：工作树已等于远端，普通快进仍被本地修改阻断

远端在并行任务后继续推进时，本地工作树可能已经以未提交修改的形式包含了同样内容。此时
`git merge --ff-only` 会为保护本地文件而拒绝更新，即使最终文件逐项等于远端。只有完整 tree 可以证明一致；
少量文件肉眼相同或测试通过都不够。下面的模式基于 Git 官方的
[`update-index --cacheinfo`](https://git-scm.com/docs/git-update-index.html) 和
[`update-ref <ref> <new> <old>`](https://git-scm.com/docs/git-update-ref.html)，只校准 index 和分支 ref，
不改写工作树文件。

### Pattern: git-align-index-and-ref-when-worktree-equals-remote
- scenario: 当前分支落后于远端且可快进；普通快进因本地修改被拒绝，但完整核对证明工作树中的全部远端变化已经等于准确远端 tip
- use_when: 用户已经另外批准校准当前仓库的 Git 记录；旧 `HEAD`、准确远端 tip、完整变化路径和其余 untracked 路径都已固定；暂存集合为空且没有并行 Git 写入者或锁
- shell: PowerShell + Git for Windows
- validated_shape:
  ```powershell
  $repoRoot = "<REPO_ROOT>"
  $branchName = "<BRANCH>"
  $remoteName = "<REMOTE>"
  $oldHead = "<OLD_HEAD_40_SHA>"
  $remoteCommit = "<REMOTE_TIP_40_SHA>"
  $alignmentPaths = @("<RELATIVE_PATH_1>", "<RELATIVE_PATH_2>")

  if ($env:GIT_INDEX_FILE) { throw "a pre-existing alternate Git index is active" }
  if ($oldHead -notmatch '^[0-9a-f]{40}$' -or $remoteCommit -notmatch '^[0-9a-f]{40}$') {
      throw "both commits must be full SHA values"
  }
  if ((git -C $repoRoot rev-parse HEAD).Trim() -ne $oldHead) { throw "local HEAD changed" }
  if ((git -C $repoRoot symbolic-ref --quiet HEAD).Trim() -ne "refs/heads/$branchName") {
      throw "the expected branch is not checked out"
  }
  if (@(git -C $repoRoot diff --cached --name-only).Count -ne 0) { throw "staged set is not empty" }
  git -C $repoRoot cat-file -e "$remoteCommit`^{commit}"
  if ($LASTEXITCODE -ne 0) { throw "the remote target object is not available locally" }
  git -C $repoRoot merge-base --is-ancestor $oldHead $remoteCommit
  if ($LASTEXITCODE -ne 0) { throw "local HEAD is not an ancestor of the remote target" }

  $remotePaths = @(git -C $repoRoot diff --name-only --no-renames $oldHead $remoteCommit)
  if (@(Compare-Object ($remotePaths | Sort-Object -Unique) ($alignmentPaths | Sort-Object -Unique)).Count -ne 0) {
      throw "approved alignment paths do not equal the complete remote change set"
  }
  $trackedPaths = @(git -C $repoRoot diff --name-only)
  $untrackedPaths = @(git -C $repoRoot ls-files --others --exclude-standard)
  $localRelevant = @($trackedPaths + @($untrackedPaths | Where-Object { $alignmentPaths -contains $_ })) |
      Sort-Object -Unique
  if (@(Compare-Object $localRelevant ($alignmentPaths | Sort-Object -Unique)).Count -ne 0) {
      throw "local changes do not exactly cover the remote change set"
  }

  $targetEntries = [ordered]@{}
  foreach ($path in $alignmentPaths) {
      $treeLine = @(git -C $repoRoot ls-tree $remoteCommit -- $path)
      if ($treeLine.Count -eq 0) {
          if (Test-Path -LiteralPath (Join-Path $repoRoot $path)) { throw "remote deletion still exists locally: $path" }
          $targetEntries[$path] = $null
          continue
      }
      if ($treeLine.Count -ne 1) { throw "remote path lookup is ambiguous: $path" }
      $tab = $treeLine[0].IndexOf("`t")
      if ($tab -lt 0) { throw "unexpected ls-tree output: $path" }
      $meta = $treeLine[0].Substring(0, $tab) -split ' '
      if ($meta.Count -ne 3 -or $meta[1] -ne 'blob' -or $meta[0] -notin @('100644', '100755')) {
          throw "unsupported tree entry; stop instead of aligning it: $path"
      }
      $workOid = (git -C $repoRoot hash-object "--path=$path" -- $path).Trim()
      if ($LASTEXITCODE -ne 0 -or $workOid -ne $meta[2]) { throw "working file differs from remote: $path" }
      $targetEntries[$path] = [pscustomobject]@{ Mode = $meta[0]; Oid = $meta[2] }
  }

  $tempIndex = Join-Path ([IO.Path]::GetTempPath()) ("git-align-index-" + [guid]::NewGuid().ToString('N'))
  try {
      $env:GIT_INDEX_FILE = $tempIndex
      git -C $repoRoot read-tree $oldHead
      foreach ($path in $alignmentPaths) {
          $entry = $targetEntries[$path]
          if ($null -eq $entry) { git -C $repoRoot update-index --remove -- $path }
          else { git -C $repoRoot update-index --add --cacheinfo $entry.Mode $entry.Oid $path }
          if ($LASTEXITCODE -ne 0) { throw "temporary index update failed: $path" }
      }
      $candidateTree = (git -C $repoRoot write-tree).Trim()
  } finally {
      $env:GIT_INDEX_FILE = $null
      Remove-Item -LiteralPath $tempIndex -Force -ErrorAction SilentlyContinue
  }
  $remoteTree = (git -C $repoRoot rev-parse "$remoteCommit`^{tree}").Trim()
  if ($candidateTree -ne $remoteTree) { throw "candidate index tree does not equal the remote tree" }

  $remoteLines = @(git -C $repoRoot ls-remote --exit-code --refs $remoteName "refs/heads/$branchName")
  if ($LASTEXITCODE -ne 0 -or $remoteLines.Count -ne 1 -or
      (($remoteLines[0] -split '\s+')[0]).Trim() -ne $remoteCommit) { throw "remote tip changed" }

  try {
      foreach ($path in $alignmentPaths) {
          $entry = $targetEntries[$path]
          if ($null -eq $entry) { git -C $repoRoot update-index --remove -- $path }
          else { git -C $repoRoot update-index --add --cacheinfo $entry.Mode $entry.Oid $path }
          if ($LASTEXITCODE -ne 0) { throw "real index update failed: $path" }
      }
      if ((git -C $repoRoot write-tree).Trim() -ne $remoteTree) { throw "real index tree does not equal remote" }
      git -C $repoRoot update-ref -m "align: verified worktree equals $remoteName/$branchName" "refs/heads/$branchName" $remoteCommit $oldHead
      if ($LASTEXITCODE -ne 0) { throw "guarded branch update failed" }
  } catch {
      if ((git -C $repoRoot rev-parse HEAD).Trim() -eq $oldHead) { git -C $repoRoot read-tree $oldHead }
      throw
  }
  ```
- substitute_only: 仓库、分支、远端、两个 40 位提交和完整相对路径集合；路径集合必须由 `旧 HEAD..远端 tip` 的完整差异产生，不能手填一个方便的子集
- preflight: 连续两次读取 `HEAD`、唯一远端 tip、`git status --short`、完整暂存清单和 untracked 清单，结果必须一致；确认普通快进只被这些本地修改阻断；保存其余 untracked 路径，并检查与 alignment paths 不存在同路径或祖先、后代重叠；`git ls-files -u` 必须为空，`GIT_INDEX_FILE` 必须未设置，index 中不能有无法完整恢复的 intent-to-add、skip-worktree 或 assume-unchanged 状态
- scope_limit: 上述骨架只处理普通 blob 和删除。symlink、gitlink、目录/文件类型变化、带换行文件名、属性过滤结果不稳定或无法一一核对时停止，改用隔离 worktree；不把这个模式用作普通 pull、merge 或清理脏工作区
- candidate_check: 临时 index 与真实 index 的 `write-tree` 都必须等于远端提交的完整 tree；更新 ref 前再次读取唯一远端 tip；`update-ref` 必须传旧 `HEAD` 作为保护值
- recovery: 如果真实 index 已开始更新但带旧值 ref 更新尚未成功，只在当前 `HEAD` 仍等于 `$oldHead`、原暂存集合为空且没有并行写入证据时，用 `git read-tree $oldHead` 恢复 index；条件不完整时保留现场并停止
- avoid: 不使用 `stash`、`reset`、`checkout`、`restore`、整文件复制或覆盖工作树；不因几个文件哈希相同就推进分支；不清理其余 untracked 文件；不在远端再次推进后自动追赶
- success_signal: `HEAD` 等于复核过的远端 tip，tracked 和 staged 状态为空，其余 untracked 路径集合逐项不变，相关验证通过；任何一项不成立都不报告已经对齐
- capture_rule: 只有“完整远端变化路径都已在工作树中准确实现”才能把内容一致转换成 Git 记录一致；先用临时 index 证明完整 tree，再精确更新真实 index，并以旧值保护 ref 更新
