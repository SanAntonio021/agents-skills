# 按命令行检查 Windows 进程

## 典型误判

用 `Get-CimInstance Win32_Process` 搜索 `CommandLine` 时，当前 `pwsh.exe` 或 `powershell.exe` 的启动参数里也可能包含同一个搜索词。此时查询会命中自己；每次重新运行都会出现新的进程号，看起来像后台任务一直存在。

PowerShell 的自动变量 `$PID` 表示当前 PowerShell 会话的进程号。先保存它，再排除当前进程：

```powershell
$selfPid = $PID
$matchedProcesses = @(Get-CimInstance Win32_Process | Where-Object {
    $_.ProcessId -ne $selfPid -and
    $_.CommandLine -and
    $_.CommandLine -match '<TARGET_PATTERN>'
})
```

官方说明：[about_Automatic_Variables - `$PID`](https://learn.microsoft.com/powershell/module/microsoft.powershell.core/about/about_automatic_variables#pid)

## 判断要求

- 搜索词应尽量指向目标脚本的完整文件名、固定参数或可核对的可执行文件路径。
- 声称“后台任务还在运行”或“某进程持有锁”前，至少确认命中的进程号不等于 `$PID`，并核对目标脚本、可执行文件路径、启动时间或 helper / mutex 的实际状态。
- 不要因为父进程也叫 PowerShell 就一并排除；只有证据表明它也是检查器时才排除。
- 单次 `CommandLine` 命中只能证明文字匹配，不能单独证明该进程持有文件锁或互斥锁。
- 身份尚未核实时，不停止或终止命中的进程。

## 成功信号

排除 `$PID` 后结果为空，表示刚才看到的是检查命令自身；结果仍存在时，再依据目标身份和实际锁状态继续判断。
