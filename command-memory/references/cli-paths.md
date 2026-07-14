# CLI Paths

用途：Windows 下外部 CLI、绝对路径、下载、用户级安装、PATH/env 持久化的命令骨架。只在这些场景有风险或已失败时读取。

## 通用骨架

### Pattern: quoted-external-cli
- use_when: 外部程序路径或输入/输出路径含空格、中文或深目录。
- shape: `& "<TOOL>" <FLAGS> "<INPUT_PATH>" <MORE_FLAGS> "<OUTPUT_PATH>"`
- preflight: `Get-Command "<TOOL>"` 或 `Test-Path "<TOOL>"`; `Test-Path "<INPUT_PATH>"`; 检查 `<OUTPUT_PATH>` 父目录。
- avoid: 省略 PowerShell call operator `&`; 未加引号路径；依赖当前目录。

### Pattern: direct-cmd-wrapper
- use_when: 仓库已有 `.cmd` 包装脚本，任务只需传绝对路径参数。
- shape: `"<CMD_WRAPPER_PATH>" "<ARG1_PATH>" "<ARG2_PATH>"`
- preflight: `Test-Path "<CMD_WRAPPER_PATH>"`; 检查每个输入路径和日志父目录。
- avoid: 再套一层 `cmd /c`; 把后续读取日志命令拼进同一条。

### Pattern: npx-cmd-when-ps1-blocked
- use_when: PowerShell 调用 `npx` 时命中 `npx.ps1` 的 execution policy 限制。
- shape: `& (Get-Command npx.cmd).Source <FLAGS> <ARGS>`
- preflight: `Get-Command npx.cmd`; 确认目标命令只是查询或已获用户授权的安装动作。
- avoid: 原样重试 `npx`、修改系统 execution policy，或为了调用 `npx` 直接绕过整台机器的安全策略。

### Pattern: bypass-local-ps1-policy
- use_when: 本地 `.ps1` 因 execution policy 报 `running scripts is disabled on this system`。
- shape: `Start-Process -FilePath "powershell.exe" -ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-File','<SCRIPT_PATH>',<SCRIPT_ARGS>) -WorkingDirectory "<WORKDIR>" -WindowStyle Hidden -PassThru`
- preflight: `Test-Path "<SCRIPT_PATH>"`; `Test-Path "<WORKDIR>"`。
- avoid: 失败后继续直接 `& "<SCRIPT_PATH>"`。

### Pattern: dotnet-io-absolute-path
- use_when: PowerShell 里调用 .NET 文件 API（`[IO.File]::ReadAllText/WriteAllText/ReadAllBytes` 等）做读写或批量替换。
- shape: `$f = Join-Path "<ABS_ROOT>" "<REL_PATH>"; [IO.File]::WriteAllText($f, $text, (New-Object Text.UTF8Encoding($hasBom)))`
- preflight: 每个传给 .NET API 的路径都必须是绝对路径；批量循环先 `Test-Path` 抽查第一个。
- avoid: 先 `Set-Location` 再给 .NET API 传相对路径——**.NET 只认进程启动目录，不认 PowerShell 的当前位置**，相对路径会静默读写到错误目录（实测事故：批量替换写进了另一个仓库，靠 git checkout 恢复）。

## 下载和网页导出

### Pattern: invoke-webrequest-download
- use_when: URL 和输出路径已知，需要落地网页/PDF；Python `requests` 超时或不稳。
- shape: `$u='<URL>'; $o='<ABS_OUTPUT_PATH>'; Invoke-WebRequest -Uri $u -OutFile $o -TimeoutSec <SECONDS>; Get-Item $o | Select-Object FullName,Length`
- preflight: `Test-Path (Split-Path -Parent '<ABS_OUTPUT_PATH>')`; 覆盖前检查目标是否已存在。
- avoid: 下载和解析塞进同一条命令；相对输出路径。

### Pattern: browser-print-to-pdf
- use_when: 官方网页没有可下载 PDF，但需要本地 PDF 快照。
- shape: `$browser='<ABS_BROWSER_EXE>'; $u='<URL>'; $o='<ABS_OUTPUT_PATH>'; & $browser '--headless' '--disable-gpu' "--print-to-pdf=$o" $u`
- preflight: `Test-Path '<ABS_BROWSER_EXE>'`; `Test-Path (Split-Path -Parent '<ABS_OUTPUT_PATH>')`。
- avoid: 裸调 `msedge`/`chrome`; 未确认页面匿名可访问。

## 用户级安装和 PATH

### Pattern: currentuser-installer
- use_when: 包管理器触发管理员权限，但当前用户安装已足够。
- shape: `$installer='<ABS_INSTALLER_EXE>'; $targetDir='<ABS_USER_INSTALL_DIR>'; $argList=@('/VERYSILENT','/NORESTART','/NOCANCEL','/SP-','/CURRENTUSER',('/DIR="' + $targetDir + '"')); $proc=Start-Process -FilePath $installer -ArgumentList $argList -Wait -PassThru; $proc.ExitCode`
- preflight: `Test-Path '<ABS_INSTALLER_EXE>'`; 检查用户可写安装目录。
- avoid: 已取消管理员提权后继续重复包管理器路径。

### Pattern: persist-user-path-env
- use_when: 用户目录安装的 CLI 当前会话可用，新终端不可用，或依赖工具找不到 helper。
- shape: `$cliDir='<ABS_CLI_DIR>'; $helperDir='<ABS_HELPER_DIR>'; $helperExe='<ABS_HELPER_EXE>'; [Environment]::SetEnvironmentVariable('<HELPER_ENV_NAME>', $helperExe, 'User'); $userPath=[Environment]::GetEnvironmentVariable('Path','User'); $parts=@(); if ($userPath) { $parts=$userPath -split ';' | Where-Object { $_ -and $_.Trim() } }; foreach ($p in @($cliDir,$helperDir)) { if ($parts -notcontains $p) { $parts += $p } }; [Environment]::SetEnvironmentVariable('Path', ($parts -join ';'), 'User')`
- preflight: 检查 CLI/helper 目录和 exe；写入前读取用户 `Path`；写后用新 `powershell.exe -NoProfile` 验证。
- avoid: 重复追加 PATH；写 machine scope；只做当前会话 `$env:Path`。

## MATLAB 提示

MATLAB 复杂场景不要塞在本文件。转读 [matlab-batch-logfile.md](matlab-batch-logfile.md)。

这里只保留一个最小提示：PowerShell literal here-string 里写 MATLAB 代码时，MATLAB 单引号按 MATLAB 原样写，不要改成双层 `''`，例如 `cd('D:/repo')`。
