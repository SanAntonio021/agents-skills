---
name: zhongduan-zhixing-hulan
description: 为 Codex 提供 Windows 终端执行护栏，减少路径引号、shell 混用和命令构造错误。Use when running PowerShell commands or Windows CLI tools, especially when the command touches file paths, external executables, conversion tools, or archive operations.
---

# 终端执行护栏

## 作用

这个 skill 负责统一 Windows 下的命令写法，让终端任务更稳、更容易排错。

它关注的是命令形态和执行安全，不负责业务逻辑本身。

## 何时使用

- 运行 `shell_command` 前
- 命令里有文件路径、外部 CLI 或格式转换
- 路径包含空格、中文或深层目录
- 已经失败过一次，命令形态需要调整

## 核心规则

1. 默认使用 PowerShell，除非用户明确要求别的 shell。
2. 已知目标路径时，优先用绝对 Windows 路径。
3. 路径参数一律加引号。
4. 主命令前先做最小存在性检查：
   - `Test-Path`
   - `Get-ChildItem`
5. 文本编辑优先 `apply_patch`，执行优先 `shell_command`。
6. 文件操作优先 PowerShell 原生命令：
   - `Copy-Item`
   - `Move-Item`
   - `Remove-Item`
   - `Select-String`
   - `Get-ChildItem`
   - `Expand-Archive`
7. 失败一次后，要改命令形态，不盲目重试。

## 与命令模式记忆的关系

- 如果像是重复出现或高风险 Windows 命令场景，先看 [../command-pattern-memory/SKILL.md](../command-pattern-memory/SKILL.md)。
- 复用完已有命令骨架后，再回到这里套静态护栏。
- 长期可复用的命令形态放在 `command-pattern-memory`，这里保留规则层和诊断层角色。

## 常用模板

路径检查：

```powershell
Test-Path "D:\absolute\path\to\file.ext"
Get-ChildItem "D:\absolute\path\to\folder"
```

安全文件操作：

```powershell
Copy-Item "D:\source path\file.ext" "D:\dest path\file.ext"
Move-Item "D:\source path\file.ext" "D:\dest path\file.ext"
```

解压：

```powershell
Expand-Archive -LiteralPath "D:\path\archive.zip" -DestinationPath "D:\path\extract_to_folder" -Force
```

## 失败处理

1. 先判断是哪类问题：
   - 路径错误
   - 引号错误
   - 可执行文件缺失
   - shell 语法不对
   - 权限或锁定问题
2. 修一次命令形态。
3. 再失败就说明阻塞点，不来回抖动重试。
4. 如果 CLI 本身不是合适工具，就换脚本或库方案。

## 边界

- 不用它为无关的高风险命令背书。
- 不把二进制文件按文本硬读。
- 不把这里写成命令记忆库；可复用命令形态属于 [../command-pattern-memory/SKILL.md](../command-pattern-memory/SKILL.md)。

## 维护

- 例子保持 PowerShell 优先、Windows 优先。
- `shell_command` 行为、默认环境或常用 CLI 变化时，复查这里。
