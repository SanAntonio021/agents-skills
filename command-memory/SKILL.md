---
name: command-memory
description: Windows 命令急救卡。只在 Windows / PowerShell 命令存在明显高风险或已经失败后需要纠偏时使用：编码乱码、中文/空格路径、软链或规则文件同步、压缩/移动/删除等文件操作、目录被进程占用删不掉或删掉后又自动重生、用 CommandLine 检查进程时把当前 PowerShell 自己误认为目标进程、git 同一文件混有批准与未批准改动需要安全部分暂存、隔离发布后用户另行批准把同一补丁安全更新到含有其他改动的本地工作副本、手工 patch 出现 hunk 计数或格式错误、`git commit` 遇到 `COMMIT_EDITMSG` / index 占用或暂存文件集合异常变化且可能有并行任务共用仓库、`git fetch` 被云盘临时 ref 或 `FETCH_HEAD` 锁阻断、Git for Windows 报 `schannel` / SSL/TLS 握手失败、提交历史莫名倒退或仓库被云同步软件回滚、Codex Windows sandbox 的 `setup refresh had errors` / ACL 失败、Office COM、MATLAB batch、LibreOffice / Poppler 转换或渲染失败、外部 CLI 调用失败、照抄对话里显示的 `%USERPROFILE%` 用户目录路径后报 `EPERM` 或建出不存在的目录树、引用本机插件与运行时源码的行号前要确认磁盘上哪份版本副本真正加载、Codex 自动任务在 heartbeat 与 project cron 间迁移或经子进程传入自动任务 API 的中文名称/提示变乱码、用户要求“按上次正确方式跑”。普通只读命令如 `rg`、`Get-Content`、`git status`、简单 `Test-Path` 不要触发。
---

# Windows 命令急救卡

## 定位

这个 skill 不负责日常 shell 使用。它只在 Windows 命令容易出错、出错代价高，或已经出现“先失败、后成功”的纠偏场景时介入。

目标是少读上下文：先读这一页；只有命中具体坑位时，再读一个最相关的 reference。

## 必须触发

- PowerShell / 外部 CLI 命令已经失败，需要换命令形态继续。
- 路径含中文、空格、很深目录，且要写入、移动、复制、删除、压缩或调用外部程序。
- 出现乱码、GBK/UTF-8、BOM、PowerShell here-string、`python -c` 编码问题。
- **目录移动/删除报 “Device or resource busy” / “Permission denied” / “另一个程序正在使用此文件”**（进程占用、MCP 僵尸、IDE/Office 锁文件）。
- Codex 在 Windows 上写入时报 `windows sandbox failed`、`setup refresh had errors`、`read ACL run had errors` 或 `SetNamedSecurityInfoW failed`。
- 需要判断或修复规则文件同步、软链、旧副本。
- 要拼 `%USERPROFILE%` 下的绝对路径，尤其是把对话里显示过的用户目录路径交给 Edit/Write 或 .NET 文件 API，出现 `EPERM`、假目录树、同一条 `Test-Path` 前后结果不一致。
- 要引用本机插件或运行时源码的行号和行为，而同一份东西在磁盘上可能并存多个版本副本，先得判定哪一份真正加载。
- 需要 Office COM、MATLAB batch / desktop、用户级 CLI 安装或环境变量持久化。
- LibreOffice / Poppler 在 Windows 上转换或渲染失败，例如 helper 报 `socket.AF_UNIX`、profile URI 异常，或 `pdftoppm` / `pdfinfo` 命中了不可用包装器。
- 用 `Get-CimInstance Win32_Process` 按 `CommandLine` 搜索后台任务，却反复命中刚启动且进程号变化的 `pwsh.exe` / `powershell.exe`，需要排除检查命令自身后再判断。
- Git 同一文件同时含有本次允许提交和其他未授权改动，不能整文件暂存；或手工构造的 patch 已出现 `corrupt patch`、`patch fragment without header`、hunk 行数不匹配，需要换成隔离 worktree 纠偏。
- 已在隔离工作副本完成发布，用户随后明确要求把同一已审查补丁更新到当前本地工作副本，而本地还有必须保留的其他改动。
- `git commit` 被 `.git/COMMIT_EDITMSG` 或 index 占用阻断，或 `HEAD`、暂存文件集合在本任务未操作时发生变化，需要区分并行 Git 写入与普通同步软件锁，并隔离本次提交。
- `git fetch` 报 `bad object refs/.../*.baiduyun.uploading.cfg`，或 `.git/FETCH_HEAD: Permission denied`，需要区分短暂同步干扰与仓库回滚，并在只需核验远端分支 SHA 时改用只读命令。
- Git for Windows 或发布/验收 helper 的远端预检报 `schannel: failed to receive handshake`、`SSL/TLS connection failed`，需要区分临时网络传输中断与仓库、Skill 或证书配置故障。
- 需要将 Codex 自动任务在 `heartbeat` 与 `project cron` 间迁移，尤其归档当前 task 前；或中文、符号等非 ASCII 名称/提示经过 PowerShell、Python 等子进程传给自动任务 API 后变乱码。
- 用户明确说”按上次正确方式跑””别再试错””用之前验证过的命令”。

## 不要触发

- 普通只读探索：`rg`、`Get-Content`、`Get-ChildItem`、`git status`、`git diff`。
- 简单存在性检查：`Test-Path`、`Get-Command`。
- 不涉及 Windows 易错点的构建、测试、脚本运行。
- 单纯查看、创建或修改 Codex 自动任务，且不涉及类型迁移、跨进程非 ASCII 传输或编码异常。
- 已有更具体 skill 覆盖的业务动作；这里只管命令形态，不管业务流程。

## 最小护栏

- PowerShell 下路径优先用绝对路径；文件参数优先 `-LiteralPath`。
- .NET 文件 API（`[IO.File]::*`）只认进程启动目录，`Set-Location` 对它无效，必须传绝对路径。
- 写入、移动、删除、覆盖前先检查目标路径和父目录。
- 不跨 shell 组合破坏性文件操作。
- 第一次失败后，换命令形态；不要原样重试。
- 文本编辑优先 `apply_patch`；批量机械重写才用命令。

## Reference 路由

只读一个最相关文件：

- 路径、外部 CLI、下载、用户级安装、PATH、LibreOffice / Poppler Windows 调用失败、`%USERPROFILE%` 路径匿名化改写、插件与运行时多版本副本定位：`references/cli-paths.md`
- CSV 批量重写为 UTF-8 BOM 且要保住引号和内嵌逗号：`references/csv-rewrite-utf8.md`
- Python / inline here-string / 中文路径乱码：`references/python-utf8.md`
- 中文 Markdown 或 UTF-8 文本读取：`references/markdown-read-utf8.md`
- 搜索、遍历、匹配：`references/search-and-traversal.md`
- 按命令行检查 Windows 进程、排除当前 PowerShell 自身、核实后台任务或占用者：`references/process-inspection.md`
- git on Windows：`REF:path` 路径被 MSYS 转坏、文件被同步软件/Office 锁住导致 merge 崩、并行任务共用 worktree 引发 `COMMIT_EDITMSG` / index 占用或暂存区漂移、同一文件混合改动的隔离暂存、隔离发布后经用户另行批准把补丁安全更新到本地工作副本、手工 patch 损坏后的纠偏、云盘临时 ref 或 `FETCH_HEAD` 锁阻断 fetch、`schannel` / SSL/TLS 握手失败、云同步客户端回滚仓库（提交历史倒退/冲突文件副本/删掉的目录复活）、纯对象层解 PR 冲突：`references/git-on-windows.md`
- 压缩、复制、移动、删除：`references/archive-and-file-ops.md`
- **目录移动/删除被占用**：`mv: Device or resource busy` / Permission denied、进程 cwd 压住目录、MCP 僵尸残留、删掉的目录几秒后被重建、Office/VS Code 锁文件：`references/directory-move-locked.md`
- 规则文件同步、软链、临时复制对齐：`references/rule-file-sync-and-symlink.md`
- WindowsApps / AppX packaged app 启动锁、`0x80070020`、Claude 更新后”另一程序正在使用此文件”：`references/windows-appx-packaged-app-lock.md`
- Codex Windows sandbox、`:slash_tmp`、`C:\tmp` / `D:\tmp` ACL 刷新失败：`references/codex-windows-sandbox.md`
- Codex 自动任务在 `heartbeat` / `project cron` 间迁移，或名称、提示从 PowerShell / Python 等子进程传给自动任务 API 后出现乱码：`references/codex-automation-utf8.md`
- MATLAB batch / desktop / 写 .m 带 BOM 让 -batch 报错：`references/matlab-batch-logfile.md`
- MATLAB figure 中文显示 / 字体方框 / GUI 坑（modal→normal 销毁、batch GUI env var 旁路）：`references/matlab-figure-chinese.md`
- Office COM、PowerPoint/Word/Excel 自动化：`references/office-com.md`
- Word `gen_py` cache 报错：`references/word-com-genpy-recovery.md`
- 失败后成功，需要沉淀模式：`references/recovery-capture-checklist.md`

如果场景不在上面，按“最小护栏”构造一条简单命令，不临时加载整库。

## 回写原则

只有高价值“失败后成功”才回写：

- 不记录失败命令全文。
- 只保存成功后的可复用命令骨架。
- 用 `<INPUT_PATH>`、`<OUTPUT_PATH>`、`<TOOL>` 这类占位符。
- 优先更新最接近的现有 reference；没有承载位才新增。

不把一次性项目路径、用户私有文件名、普通报错日志写进模式库。
