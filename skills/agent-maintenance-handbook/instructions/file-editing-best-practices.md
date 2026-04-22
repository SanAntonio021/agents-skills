# File Editing Best Practices

## Purpose

统一当前环境下的文本文件修改方式，减少编码问题、误改范围和工具错配。

## Default Editing Path

1. 先定位目标文件和实际内容。
2. 手工文本修改默认使用 `apply_patch`。
3. 重命名、移动、批量检查、格式化、验证这类动作使用 `shell_command`。
4. 修改后立刻复读或校验，确认结果与预期一致。

## Current Tooling Baseline

当前这套环境里，优先使用：

- `apply_patch` 做手工编辑
- `shell_command` 跑 PowerShell 命令
- `Get-ChildItem`、`Select-String`、`Get-Content -Raw`、`Test-Path` 做检查

不要继续依赖这类旧语境写法：

- `replace_file_content`
- `multi_replace_file_content`
- `view_file`
- `grep_search`

这些不再是当前维护基线。

## Windows / PowerShell Rules

- 默认按 PowerShell 语法写命令
- 路径尽量使用绝对路径
- 含空格路径始终加引号
- 修改前先确认目标文件真实存在
- 多步 PowerShell 逻辑如果开始变脆，就写短 `.ps1` 再执行

## Encoding Rules

处理中文 Markdown 或文本时，默认按 UTF-8 管理。

遇到乱码时按这个顺序处理：

1. 先区分是终端显示乱码，还是文件本身已损坏。
2. PowerShell 读取前先设定：

```powershell
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
```

3. 读取时优先使用：

```powershell
Get-Content -Raw -Encoding UTF8 "<path>"
```

4. 如果必须脚本化读写，优先用 `[System.IO.File]` 并显式指定 UTF-8。
5. 写回后立即再读一遍，不靠想当然判断是否修好。

## Scope Control

- 只改用户要求的文件和与之直接相关的最小范围
- 不顺手清理无关文件
- 不回滚用户已有改动
- 不使用 `git reset --hard`、`git checkout --` 这类破坏性命令

## Tool Boundary

- 简单文件读写不要为此启用 Python
- 小规模文本编辑不要用 shell 重定向硬写整文件
- 需要稳定批处理时，优先短脚本或现成 `scripts/`

## Verification

每次编辑后至少做一项验证：

- 重新读取关键片段
- 搜索旧字符串是否已消失
- 搜索新标题、链接或字段是否已出现
- 运行相关帮助命令、校验脚本或最小 smoke check

## Maintenance

- 如果当前工具栈变化，先更新本文件，再更新其他维护文档。
- 本文件只写通用编辑基线，不写单项目特例。
