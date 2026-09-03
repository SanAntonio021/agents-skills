# CLI Paths

用途：Windows 下外部 CLI、PowerShell 命令形态、绝对路径、下载、用户级安装、PATH/env 持久化的命令骨架。只在这些场景有风险或已失败时读取。

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

### Pattern: child-powershell-preserve-inner-variables
- use_when: 当前 PowerShell 通过 `powershell.exe` 或 `pwsh` 的 `-Command` 启动子进程，内层命令含 `$result`、`$LASTEXITCODE` 等变量；外层双引号会先展开这些变量，使赋值或失败判断在传入子进程前已经损坏。
- preferred_shape: 多步测试或校验写入一份短小、可检查的 UTF-8 `.ps1`，再用 `powershell.exe -NoLogo -NoProfile -NonInteractive -File "<SCRIPT_PATH>" <ARGS>`；减少两层 PowerShell 同时解析同一段代码。
- short_shape: 确需 `-Command` 时，外层使用单引号原样传递完整脚本块，内层路径改用双引号，例如 `powershell.exe -NoLogo -NoProfile -NonInteractive -Command '& { $result = Invoke-Pester "<TEST_PATH>" -PassThru; Write-Output ("passed={0} failed={1}" -f $result.PassedCount,$result.FailedCount); if ($result.FailedCount -gt 0) { exit 1 } }'`。
- acceptance: 子进程输出必须证明目标测试实际运行，并给出通过数和失败数；调用方再检查子进程退出码。只有退出码 `0` 而没有有效测试汇总，不能算通过。
- avoid: 用外层双引号包住含 `$变量` 的整段 `-Command`；看到 `= is not recognized`、`.FailedCount is not recognized` 等内层命令损坏迹象后仍把父进程退出码 `0` 当作成功。

### Pattern: powershell-caller-normalize-command-output
- use_when: PowerShell 函数包装一个可能输出零行、一行或多行的外部命令，调用端随后要读取 `.Count`、按索引取值或调用字符串方法；单行结果处出现 `System.Char` 没有 `Trim` 等类型错误。
- shape: `function Invoke-ToolLines { param([string[]]$Arguments) $output = @(& "<TOOL>" @Arguments); if ($LASTEXITCODE -ne 0) { throw "tool failed: $($Arguments -join ' ')" }; $output }; $lines = @(Invoke-ToolLines -Arguments @('<ARG1>','<ARG2>')); if ($lines.Count -ne 1) { throw "expected one line, got $($lines.Count)" }; $first = ([string]$lines[0]).Trim()`
- reason: PowerShell 会枚举函数写入成功输出流的集合；即使函数里写了 `return @($output)`，调用表达式只有一个对象时仍可能在赋值处退化为标量。需要稳定集合语义时，由消费结果的调用端用 `@(...)` 固定形状。
- preflight: 包装器在输出结果前立即检查外部命令的 `$LASTEXITCODE`；调用端先验证行数，再把准确元素转成预期类型。对会复用的包装器分别探测零行、一行和多行结果。
- acceptance: 单行时 `$lines` 仍是数组、`Count` 为 `1`，`$lines[0]` 是完整字符串；零行或多行会被显式分流，不会因为字符索引、空值或隐式标量化继续后续写操作。
- avoid: `$first = (Invoke-ToolLines ...)[0].Trim()`；依赖函数内部的 `return @($output)` 保证调用方拿到数组；不检查行数就消费首项。

### Pattern: powershell-avoid-matches-automatic-variable-collision
- use_when: 脚本把普通结果、筛选集合或布尔状态命名为 `$matches`（任意大小写），随后又执行 `-match`、`-notmatch` 或 `switch -Regex`，原值意外变成哈希表或读取到上一次正则捕获。
- shape: 普通业务结果改名为 `$matchedRows`、`$matchResults` 或更具体的名称；正则命中后立即把需要的捕获复制到业务变量，例如 `if ($text -match '<REGEX>') { $capturedValue = [string]$Matches[1] }`，后续只使用 `$capturedValue`。
- reason: PowerShell 变量名不区分大小写，所以 `$matches` 与自动变量 `$Matches` 是同一个变量。标量 `-match` / `-notmatch` 和 `switch -Regex` 会填充该哈希表；后续未命中的 `-match` 也不会自动清空旧值。
- preflight: 在失败脚本中同时查找普通 `$matches` 赋值和正则操作，确认类型变化发生在相同作用域；把业务变量重命名后，从脚本入口重跑，而不是只在出错行前强制转型。
- acceptance: 普通结果集合跨越全部正则操作后类型、数量和内容保持不变；正则捕获只从紧邻的成功匹配复制，未命中分支不会误用旧捕获。
- avoid: 把 `$matches` 的大小写变体当普通变量；依赖一次未命中的 `-match` 清空 `$Matches`；用 `@($matches)` 或强制转型掩盖自动变量已经覆盖业务状态。

### Pattern: pester-version-aware-invocation
- use_when: `Invoke-Pester` 在测试开始前报某个输出控制参数不存在，例如 Windows PowerShell 5.1 自带 Pester 3.4 不接受从新版命令复制来的 `-Show None`；当前任务不能为适配一条命令而升级测试框架。
- shape: `$module = Get-Module -ListAvailable Pester | Sort-Object Version -Descending | Select-Object -First 1; if (-not $module) { throw 'Pester is unavailable' }; Import-Module $module.Path -Force; $command = Get-Command Invoke-Pester -Module Pester; $pesterParams = @{ Script = '<TEST_PATH>'; PassThru = $true }; if ($command.Parameters.ContainsKey('Show')) { $pesterParams.Show = 'None' } elseif ($command.Parameters.ContainsKey('Quiet')) { $pesterParams.Quiet = $true }; $result = Invoke-Pester @pesterParams; if ($null -eq $result -or $null -eq $result.FailedCount) { throw 'Pester did not return a test summary' }; Write-Output ("passed={0} failed={1}" -f $result.PassedCount,$result.FailedCount); if ([int]$result.FailedCount -ne 0) { throw 'Pester tests failed' }`
- preflight: 先固定实际要运行的 PowerShell 版本，再查看该进程能加载的 Pester 模块和实际 `Invoke-Pester` 的 `Parameters`；以命令参数表决定可选的静默参数，不只凭记忆或主版本号拼命令。测试路径必须存在。
- acceptance: 输出包含目标测试的真实通过数和失败数，失败数为 `0`，并且承载测试的 PowerShell 进程退出码为 `0`。参数绑定失败发生在测试执行前，既不是测试失败，也不能算测试通过。
- avoid: 把 Pester 4/5 的 `-Show None` 或更新版的 `-Output None` 无条件传给 Pester 3.4；为让命令可用而临时安装或升级模块；删除不兼容参数后只看进程退出码、不再核对测试汇总。

### Pattern: dotnet-io-absolute-path
- use_when: PowerShell 里调用 .NET 文件 API（`[IO.File]::ReadAllText/WriteAllText/ReadAllBytes` 等）做读写或批量替换。
- shape: `$f = Join-Path "<ABS_ROOT>" "<REL_PATH>"; [IO.File]::WriteAllText($f, $text, (New-Object Text.UTF8Encoding($hasBom)))`
- preflight: 每个传给 .NET API 的路径都必须是绝对路径；批量循环先 `Test-Path` 抽查第一个。
- avoid: 先 `Set-Location` 再给 .NET API 传相对路径——**.NET 只认进程启动目录，不认 PowerShell 的当前位置**，相对路径会静默读写到错误目录（实测事故：批量替换写进了另一个仓库，靠 git checkout 恢复）。

### Pattern: userprofile-path-anonymization
- use_when: 拼 `%USERPROFILE%` 下的绝对路径（`.claude\`、`.codex\`、`AppData\` 等），尤其是要交给 Edit/Write 或 .NET 文件 API 的路径。
- shape: `$p = Join-Path $env:USERPROFILE '.codex\sessions'; Test-Path -LiteralPath $p`
- preflight: 存疑时 `Get-ChildItem C:\Users -Directory` 核对真实用户名；同一条 `Test-Path` 字面量前后返回不一致，就是命中本条。
- avoid: 照抄对话里显示的 `C:\Users\<name>\...` 字面量——**宿主会对路径做匿名化改写**（真实用户名被替换成 `User`，盘符和目录段被打散重排，见 anthropics/claude-code#57141），照抄得到的路径可能根本不存在，Edit/Write 会在假路径下建出整棵目录树或直接报 `EPERM`。非用户目录的路径（如 `D:\...`）写真实绝对路径即可，不受影响。

### Pattern: installed-plugin-version-authority
- use_when: 引用 Claude Code 插件源码的行号或行为（`.claude\plugins\cache\<repo>\<plugin>\<version>\`），判断某 flag 是值参数还是布尔、某分支是否可达。
- shape: `$ip = Join-Path $env:USERPROFILE '.claude\plugins\installed_plugins.json'; (Get-Content -LiteralPath $ip -Raw | ConvertFrom-Json).plugins.'<plugin>@<repo>'[0].installPath`
- preflight: 先用 `installed_plugins.json` 的 `installPath` 定版本，再读那一份；`find`/`Get-ChildItem -Recurse` 找到多份时不要 `head -1`、不要按字典序取，先列全并逐份记录字节数或 SHA256。多份 SHA256 相同时可一并作结论（升级不改行为）。
- avoid: 假定 cache 下只有一个版本目录——**同一插件的多个版本副本会长期并存，路径里的版本号看起来都合法**，读到未加载的旧副本会得到一整套偏移的错误行号（实测：1.0.6 有 1073 行、已装的 1.0.7-sidebar.1 有 1115 行，同一处 `booleanOptions` 分别在 `:765` 和 `:807`）。拿错行号去更正别人时错误会继续传播。

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

### Pattern: windows-libreoffice-runner
- use_when: Windows 上 DOCX 等 Office 文件转换失败，`soffice` 不在 PATH，或第三方 helper 尚未启动 LibreOffice 就报错。
- shape: `$python='C:\Python313\python.exe'; $runner='<ABS_LIBREOFFICE_RUNNER_SCRIPTS>\libreoffice_run.py'; & $python $runner pdf '<ABS_INPUT_FILE>' '<ABS_OUTPUT_FILE>' --run-timeout 120`
- preflight: `Test-Path -LiteralPath $python`; `Test-Path -LiteralPath $runner`; 检查输入文件、输出路径不存在；读取 runner JSON 的 `ok`、`error`、`stdout`、`stderr` 和 `diagnostics`。
- avoid: 直接运行 `soffice`、`soffice.exe` 或 `soffice.com`；手工拼 `UserInstallation` URI；多个任务共用 profile；按进程名结束 LibreOffice；绕过 runner 调用 GUI 入口。

### Pattern: detect-af-unix-helper
- use_when: Python helper 在 Windows 上报 `AttributeError: module 'socket' has no attribute 'AF_UNIX'`，需要判断是 helper 不兼容还是 LibreOffice 安装问题。
- shape: `& '<PYTHON_EXE>' -c "import socket; print(hasattr(socket, 'AF_UNIX'))"; rg -n "AF_UNIX|soffice" '<HELPER_SCRIPT>'`
- preflight: 用 helper 实际使用的 Python 运行时执行检查；确认异常发生在外部进程启动前。
- avoid: 反复重装 LibreOffice；原样重试不兼容 helper；在文档任务中直接修改第三方运行时副本。检查结果为 `False` 且 helper 无条件访问 `AF_UNIX` 时，改走 `windows-libreoffice-runner`。

### Pattern: windows-poppler-direct-exe
- use_when: PDF 信息读取或渲染失败，PATH 中的 `pdftoppm` / `pdfinfo` 不可用，或命中了无扩展名包装器而不是真正的 Poppler 二进制文件。
- shape: `$popplerBin='<ABS_POPPLER_BIN_DIR>'; $pdfinfo=Join-Path $popplerBin 'pdfinfo.exe'; $pdftoppm=Join-Path $popplerBin 'pdftoppm.exe'; & $pdfinfo '<ABS_INPUT_PDF>'; & $pdftoppm -png -r <DPI> '<ABS_INPUT_PDF>' '<ABS_OUTPUT_PREFIX>'`
- preflight: `Test-Path -LiteralPath $pdfinfo`; `Test-Path -LiteralPath $pdftoppm`; 检查输入 PDF 和输出前缀的父目录；必要时用 `Get-Command pdftoppm -All` / `Get-Command pdfinfo -All` 查看 PATH 实际解析结果。
- avoid: 未确认解析来源就调用裸命令；调用无扩展名的 `pdftoppm` / `pdfinfo` 包装器；把输出前缀误当成输出目录。优先直调已验证的 `.exe` 绝对路径。

## MATLAB 提示

MATLAB 复杂场景不要塞在本文件。转读 [matlab-batch-logfile.md](matlab-batch-logfile.md)。

这里只保留一个最小提示：PowerShell literal here-string 里写 MATLAB 代码时，MATLAB 单引号按 MATLAB 原样写，不要改成双层 `''`，例如 `cd('D:/repo')`。
