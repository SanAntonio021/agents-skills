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
- preflight: 检查 CLI/helper 目录和 exe；写入前读取用户 `Path`；写后用新 `powershell.exe -NoProfile` 验证。用户级 PATH 只自动进入新进程，已经运行的终端、Codex 或桌面应用需要重启后才能继承。
- avoid: 重复追加 PATH；写 machine scope；只做当前会话 `$env:Path`；在旧进程里验证后误判持久化失败。

## LibreOffice 和 Poppler

### Pattern: windows-libreoffice-direct-profile
- use_when: Windows 上 DOCX 等 Office 文件转换失败，`soffice` 不在 PATH，或第三方 helper 尚未启动 LibreOffice 就报错。
- shape: `$soffice='<ABS_LIBREOFFICE_PROGRAM_DIR>\soffice.com'; $profilePath='<ABS_ISOLATED_PROFILE_DIR>'; $profileUri=([Uri]$profilePath).AbsoluteUri; & $soffice ('-env:UserInstallation=' + $profileUri) --headless --convert-to pdf --outdir '<ABS_OUTPUT_DIR>' '<ABS_INPUT_FILE>'`
- preflight: `Test-Path -LiteralPath $soffice`; 检查输入文件、输出目录和隔离 profile 父目录；确认 `$profileUri` 形如 `file:///C:/...`；转换后检查退出码和目标文件。
- avoid: 依赖裸命令 `soffice`；把 Windows 路径直接拼成 `file://C:\...`；多个任务共用同一 profile；需要控制台诊断时绕过 `soffice.com` 去调 GUI 入口。

### Pattern: detect-af-unix-helper
- use_when: Python helper 在 Windows 上报 `AttributeError: module 'socket' has no attribute 'AF_UNIX'`，需要判断是 helper 不兼容还是 LibreOffice 安装问题。
- shape: `& '<PYTHON_EXE>' -c "import socket; print(hasattr(socket, 'AF_UNIX'))"; rg -n "AF_UNIX|soffice" '<HELPER_SCRIPT>'`
- preflight: 用 helper 实际使用的 Python 运行时执行检查；确认异常发生在外部进程启动前。
- avoid: 反复重装 LibreOffice；原样重试不兼容 helper；在文档任务中直接修改第三方运行时副本。检查结果为 `False` 且 helper 无条件访问 `AF_UNIX` 时，改走 `windows-libreoffice-direct-profile`。

### Pattern: windows-poppler-direct-exe
- use_when: PDF 信息读取或渲染失败，PATH 中的 `pdftoppm` / `pdfinfo` 不可用，或命中了无扩展名包装器而不是真正的 Poppler 二进制文件。
- shape: `$popplerBin='<ABS_POPPLER_BIN_DIR>'; $pdfinfo=Join-Path $popplerBin 'pdfinfo.exe'; $pdftoppm=Join-Path $popplerBin 'pdftoppm.exe'; & $pdfinfo '<ABS_INPUT_PDF>'; & $pdftoppm -png -r <DPI> '<ABS_INPUT_PDF>' '<ABS_OUTPUT_PREFIX>'`
- preflight: `Test-Path -LiteralPath $pdfinfo`; `Test-Path -LiteralPath $pdftoppm`; 检查输入 PDF 和输出前缀的父目录；必要时用 `Get-Command pdftoppm -All` / `Get-Command pdfinfo -All` 查看 PATH 实际解析结果。
- avoid: 未确认解析来源就调用裸命令；调用无扩展名的 `pdftoppm` / `pdfinfo` 包装器；把输出前缀误当成输出目录。优先直调已验证的 `.exe` 绝对路径。

## MATLAB 提示

MATLAB 复杂场景不要塞在本文件。转读 [matlab-batch-logfile.md](matlab-batch-logfile.md)。

这里只保留一个最小提示：PowerShell literal here-string 里写 MATLAB 代码时，MATLAB 单引号按 MATLAB 原样写，不要改成双层 `''`，例如 `cd('D:/repo')`。
