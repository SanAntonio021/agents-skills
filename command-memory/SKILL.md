---
name: command-memory
description: Windows 命令急救卡。只在 Windows / PowerShell 命令存在明显高风险或已经失败后需要纠偏时使用：编码乱码、中文/空格路径、软链或规则文件同步、压缩/移动/删除等文件操作、Office COM、MATLAB batch、外部 CLI 调用失败、用户要求“按上次正确方式跑”。普通只读命令如 `rg`、`Get-Content`、`git status`、简单 `Test-Path` 不要触发。
---

# Windows 命令急救卡

## 定位

这个 skill 不负责日常 shell 使用。它只在 Windows 命令容易出错、出错代价高，或已经出现“先失败、后成功”的纠偏场景时介入。

目标是少读上下文：先读这一页；只有命中具体坑位时，再读一个最相关的 reference。

## 必须触发

- PowerShell / 外部 CLI 命令已经失败，需要换命令形态继续。
- 路径含中文、空格、很深目录，且要写入、移动、复制、删除、压缩或调用外部程序。
- 出现乱码、GBK/UTF-8、BOM、PowerShell here-string、`python -c` 编码问题。
- 需要判断或修复规则文件同步、软链、旧副本。
- 需要 Office COM、MATLAB batch / desktop、用户级 CLI 安装或环境变量持久化。
- 用户明确说“按上次正确方式跑”“别再试错”“用之前验证过的命令”。

## 不要触发

- 普通只读探索：`rg`、`Get-Content`、`Get-ChildItem`、`git status`、`git diff`。
- 简单存在性检查：`Test-Path`、`Get-Command`。
- 不涉及 Windows 易错点的构建、测试、脚本运行。
- 已有更具体 skill 覆盖的业务动作；这里只管命令形态，不管业务流程。

## 最小护栏

- PowerShell 下路径优先用绝对路径；文件参数优先 `-LiteralPath`。
- 写入、移动、删除、覆盖前先检查目标路径和父目录。
- 不跨 shell 组合破坏性文件操作。
- 第一次失败后，换命令形态；不要原样重试。
- 文本编辑优先 `apply_patch`；批量机械重写才用命令。

## Reference 路由

只读一个最相关文件：

- 路径、外部 CLI、下载、用户级安装、PATH：`references/cli-paths.md`
- Python / inline here-string / 中文路径乱码：`references/python-utf8.md`
- 中文 Markdown 或 UTF-8 文本读取：`references/markdown-read-utf8.md`
- 搜索、遍历、匹配：`references/search-and-traversal.md`
- git on Windows：`REF:path` 路径被 MSYS 转坏、文件被同步软件/Office 锁住导致 merge 崩、纯对象层解 PR 冲突：`references/git-on-windows.md`
- 压缩、复制、移动、删除：`references/archive-and-file-ops.md`
- 规则文件同步、软链、临时复制对齐：`references/rule-file-sync-and-symlink.md`
- WindowsApps / AppX packaged app 启动锁、`0x80070020`、Claude 更新后“另一程序正在使用此文件”：`references/windows-appx-packaged-app-lock.md`
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
