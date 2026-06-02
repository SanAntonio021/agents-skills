# WindowsApps / AppX Packaged App Lock

适用：Windows 上 Microsoft Store / MSIX / WindowsApps 打包应用更新后启动失败，提示“另一程序正在使用此文件”，或事件日志出现 `0x80070020`。

典型例子：Claude 更新后，从开始菜单启动只拉起 `CoworkVMService` / `cowork-svc.exe`，主 `Claude.exe` 起不来。

## 判断信号

- 弹窗：`另一程序正在使用此文件。`
- AppX 事件日志：
  - `Microsoft-Windows-AppModel-Runtime/Admin`
  - `0x80070020: Cannot create the process for package ...`
  - `Cannot create the Desktop AppX container ... because an error was encountered converting the job`
- `Get-AppxPackage` 显示包状态 `Ok`，但开始菜单启动仍失败。

## 最小排查

先找当前包路径，不写死版本号：

```powershell
$pkg = Get-AppxPackage |
  Where-Object { $_.Name -eq "<APP_NAME>" -or $_.PackageFullName -like "<APP_NAME>_*" } |
  Select-Object -First 1

$pkg | Select-Object Name, PackageFullName, InstallLocation, Status | Format-List
```

查最近 AppModel 错误：

```powershell
$since = (Get-Date).AddMinutes(-30)
Get-WinEvent -FilterHashtable @{
  LogName = "Microsoft-Windows-AppModel-Runtime/Admin"
  StartTime = $since
} -ErrorAction SilentlyContinue |
  Where-Object {
    $_.Message -like "*$($pkg.PackageFullName)*" -or
    $_.Message -like "*0x80070020*"
  } |
  Select-Object TimeCreated, Id, LevelDisplayName, Message |
  Format-List
```

查残留打包服务或进程：

```powershell
Get-CimInstance Win32_Service |
  Where-Object {
    $_.PathName -like "*$($pkg.InstallLocation)*" -or
    $_.Name -like "*<APP_OR_SERVICE_KEYWORD>*" -or
    $_.DisplayName -like "*<APP_OR_SERVICE_KEYWORD>*"
  } |
  Select-Object Name, DisplayName, State, StartMode, PathName, ProcessId |
  Format-List

Get-CimInstance Win32_Process |
  Where-Object {
    $_.ExecutablePath -like "$($pkg.InstallLocation)*" -or
    $_.CommandLine -like "*$($pkg.InstallLocation)*"
  } |
  Select-Object ProcessId, Name, ExecutablePath, CommandLine |
  Format-List
```

## Claude 已验证绕过

Claude 的已验证锁源：

- 服务名：`CoworkVMService`
- 进程名：`cowork-svc.exe`
- 主程序：`app\Claude.exe`

最稳做法：停掉打包服务和残留进程后，直接启动当前包内的 `Claude.exe`，绕过开始菜单 AppX shell 激活。

```powershell
$pkg = Get-AppxPackage |
  Where-Object { $_.Name -eq "Claude" -or $_.PackageFullName -like "Claude_*" } |
  Select-Object -First 1

if (-not $pkg) {
  throw "Claude package not found."
}

$claudeExe = Join-Path $pkg.InstallLocation "app\Claude.exe"
if (-not (Test-Path -LiteralPath $claudeExe)) {
  throw "Claude.exe not found: $claudeExe"
}

Stop-Service -Name "CoworkVMService" -Force -ErrorAction SilentlyContinue

Get-Process -Name "cowork-svc","Claude" -ErrorAction SilentlyContinue |
  Stop-Process -Force -ErrorAction SilentlyContinue

Start-Sleep -Seconds 2

Start-Process -FilePath $claudeExe -WorkingDirectory (Split-Path -LiteralPath $claudeExe)
```

验证：

```powershell
Get-Process -Name "Claude" -ErrorAction SilentlyContinue |
  Select-Object Id, ProcessName, Path
```

## 不要做

- 不要删除 `C:\Users\<USER>\AppData\Roaming\<APP>`，这是用户配置和登录状态。
- 不要写死 WindowsApps 版本目录，例如 `Claude_1.9659.4.0_...`；每次更新版本号会变。
- 不要把 `sc.exe config <service> start= disabled` 当默认修复；打包服务可能是应用功能需要的服务，禁用会引入新问题。
- 不要默认杀 `RuntimeBroker`、`ApplicationFrameHost`、`StartMenuExperienceHost`、`ShellExperienceHost`、`SearchHost` 或 `explorer.exe`。这些是用户态 shell / AppX 启动链路，误杀后可能导致开始菜单、任务栏、桌面快捷方式或其它应用点击启动失效。
- 不要用 `git reset`、删除 WindowsApps 目录、修改 `AppxManifest.xml` 这类扩大破坏面的做法。

## 如果误伤后其它应用点不开

如果为了排查 AppX 锁而停止过 shell 相关进程，随后 Chrome 等其它应用从开始菜单、任务栏或桌面点击不启动，先恢复用户态 shell，不要立刻重启整台机器。

先确认应用本体能否直接启动。以 Chrome 为例：

```powershell
$chrome = "C:\Program Files\Google\Chrome\Application\chrome.exe"
if (Test-Path -LiteralPath $chrome) {
  Start-Process -FilePath $chrome -ArgumentList "--new-window","about:blank"
}
```

如果直接启动可行，问题多半在 shell / 快捷方式激活链路。重启这些用户态组件：

```powershell
Get-Process -Name `
  "StartMenuExperienceHost",`
  "ShellExperienceHost",`
  "SearchHost",`
  "ApplicationFrameHost",`
  "RuntimeBroker" `
  -ErrorAction SilentlyContinue |
  Stop-Process -Force

Start-Sleep -Seconds 1

Get-Process -Name "explorer" -ErrorAction SilentlyContinue |
  Stop-Process -Force

Start-Sleep -Seconds 2
Start-Process explorer.exe
```

验证：

```powershell
Get-Process -Name `
  "explorer",`
  "StartMenuExperienceHost",`
  "ShellExperienceHost",`
  "SearchHost",`
  "RuntimeBroker",`
  "ApplicationFrameHost" `
  -ErrorAction SilentlyContinue |
  Select-Object Id, ProcessName, Path
```

## 如果直接启动也失败

再尝试轻量重注册，不清用户配置：

```powershell
$manifest = Join-Path $pkg.InstallLocation "AppxManifest.xml"
Add-AppxPackage -DisableDevelopmentMode -Register $manifest
```

如果重注册后仍是 `0x80070020`，优先继续找占用者；不要立刻让用户重启整台机器。只有无法停掉系统级占用或包状态损坏时，再建议重启或重装。
