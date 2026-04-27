# CLI Paths

### Pattern: powershell-quoted-cli-paths
- scenario: External CLI invocation with absolute Windows paths
- use_when: The task needs a Windows CLI and any input, output, or working path may contain spaces, Chinese characters, or deep directories.
- shell: PowerShell
- validated_shape: `& "<TOOL>" <FLAGS> "<INPUT_PATH>" <MORE_FLAGS> "<OUTPUT_PATH>"`
- validated_shape_matlab_batch_here_string: `$script = @'<MATLAB_STATEMENTS>'@; & "<MATLAB_EXE>" -batch $script`
- validated_shape_matlab_batch_run_script: `$script = @'cd('D:/repo'); run('D:/repo/script.m');'@; & "<MATLAB_EXE>" -batch $script`
- validated_shape_matlab_batch_helper_run: `$script = @'addpath(genpath('<REPO_MATLAB_ROOT>')); set(0,'DefaultFigureVisible','off'); diary('<LOG_PATH>'); diary on; results = <HELPER_FUNCTION>('<INPUT_PATH>'); save('<OUTPUT_PATH>','results'); diary off;'@; & "<MATLAB_EXE>" -batch $script`
- substitute_only: `<TOOL>`, `<FLAGS>`, `<INPUT_PATH>`, `<MORE_FLAGS>`, `<OUTPUT_PATH>`
- preflight: `Get-Command "<TOOL>"`; `Test-Path "<INPUT_PATH>"`; verify parent directory of `<OUTPUT_PATH>` exists or should be created explicitly; for `matlab -batch`, add `addpath(genpath("<REPO_MATLAB_ROOT>"))` before calling repo helpers; if using a PowerShell literal here-string for MATLAB statements, keep MATLAB single quotes unescaped inside the here-string
- env: none
- avoid: Omitting the PowerShell call operator `&` when `<TOOL>` is a quoted executable path; unquoted paths; mixed slash styles within a copied command; relying on current working directory when absolute paths are known; embedding PowerShell-style `$vars` inside `matlab -batch` snippets instead of plain MATLAB variable names; defining local or nested MATLAB functions inline inside a `matlab -batch` one-liner; doubling MATLAB single quotes inside a PowerShell literal here-string unless the MATLAB code itself requires escaped quotes; writing `cd(''D:/repo'')` or `run(''D:/repo/script.m'')` inside a literal here-string when `cd('D:/repo')` and `run('D:/repo/script.m')` are the correct shapes
- success_signal: The CLI runs without path parsing errors and reads or writes the intended files
- capture_rule: Update this entry when a safer quoting or preflight shape is validated for repeated CLI use. For ad hoc `matlab -batch` diagnostics, prefer a flat statement sequence or a checked-in `.m` helper script instead of embedding local function definitions in the batch snippet. Prefer the literal here-string shape when the MATLAB batch body contains many quoted Windows paths. When a helper already exists, keep the batch body as a flat sequence such as `addpath` -> `set(0,'DefaultFigureVisible','off')` -> `diary` -> helper call -> `save`, and keep MATLAB single quotes exactly as native MATLAB syntax inside the PowerShell literal here-string.

### Pattern: powershell-direct-cmd-launcher
- scenario: Launching a validated local `.cmd` wrapper that in turn starts an external CLI such as MATLAB batch
- use_when: The repo already has a checked-in Windows launcher script like `launch_matlab_batch_script.cmd` and the task only needs to pass absolute file arguments through to that wrapper.
- shell: PowerShell
- validated_shape: `"<CMD_WRAPPER_PATH>" "<ARG1_PATH>" "<ARG2_PATH>"`
- substitute_only: `<CMD_WRAPPER_PATH>`, `<ARG1_PATH>`, `<ARG2_PATH>`
- preflight: `Test-Path "<CMD_WRAPPER_PATH>"`; `Test-Path "<ARG2_PATH>"`; if `<ARG1_PATH>` is a log file, its parent directory must already exist or be created explicitly
- env: none
- avoid: Wrapping the same call again in `cmd /c` when PowerShell can invoke the `.cmd` directly; building the call through PowerShell variables plus nested quoting when a plain direct invocation is enough; appending `Get-Content` or other follow-up steps into the same launcher command when validating the launcher shape itself
- success_signal: The wrapper returns the expected exit code and writes the requested log or output file
- capture_rule: Prefer this direct `.cmd` shape for repeated MATLAB batch backfill or verification tasks before falling back to nested `cmd /c` quoting

### Pattern: powershell-bypass-local-ps1
- scenario: Running a local PowerShell `.ps1` helper from another PowerShell session when the machine execution policy blocks direct `& "<SCRIPT>.ps1"` invocation
- use_when: A checked-in or workspace-local `.ps1` automation helper needs to run immediately and a prior direct invocation failed with `running scripts is disabled on this system`
- shell: PowerShell
- validated_shape: `Start-Process -FilePath "powershell.exe" -ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-File','<SCRIPT_PATH>',<SCRIPT_ARGS>) -WorkingDirectory "<WORKDIR>" -WindowStyle Hidden -PassThru`
- substitute_only: `<SCRIPT_PATH>`, `<SCRIPT_ARGS>`, `<WORKDIR>`
- preflight: `Test-Path "<SCRIPT_PATH>"`; `Test-Path "<WORKDIR>"`; if the helper should stay in the background, prefer `Start-Process` and capture the returned PID
- env: none
- avoid: Calling `& "<SCRIPT_PATH>"` again after an execution-policy failure; nesting the `.ps1` path into a quoted `-Command` string when `-File` is sufficient; assuming the current shell policy will allow direct script execution on another workstation
- success_signal: A new `powershell.exe` process starts, the helper script runs, and any expected state or log files begin updating
- capture_rule: Reuse this shape for watchdogs, background helpers, or repo-local PowerShell automation after an execution-policy failure blocks direct script invocation

### Pattern: powershell-browser-print-to-pdf
- scenario: Exporting a live vendor webpage to a local PDF when the site has no public datasheet PDF or the PDF link is unavailable
- use_when: The task needs an offline PDF snapshot of an official product page and a local browser executable such as Edge or Chrome is available
- shell: PowerShell
- validated_shape: `$browser='<ABS_BROWSER_EXE>'; $u='<URL>'; $o='<ABS_OUTPUT_PATH>'; & $browser '--headless' '--disable-gpu' \"--print-to-pdf=$o\" $u`
- substitute_only: `<ABS_BROWSER_EXE>`, `<URL>`, `<ABS_OUTPUT_PATH>`
- preflight: `Test-Path '<ABS_BROWSER_EXE>'`; `Test-Path (Split-Path -Parent '<ABS_OUTPUT_PATH>')`; keep both browser and output paths absolute; if the page depends on login, verify it loads anonymously first
- env: none
- avoid: Calling `msedge` or `chrome` by bare name when only the absolute executable path is known; mixing relative output paths with Chinese workspace folders; assuming a page has a downloadable PDF before checking for direct `.pdf` links
- success_signal: The browser exits without error and the target PDF file is created with non-zero length
- capture_rule: Reuse this shape for vendor product-page preservation when `Invoke-WebRequest` or site search shows no public datasheet PDF; prefer a short loop around the validated single-page shape for batch exports

### Pattern: powershell-currentuser-installer-from-local-exe
- scenario: Running a downloaded Windows installer silently for the current user after a package-manager path escalated to admin or was cancelled
- use_when: A task needs a Windows desktop or CLI dependency installed without admin rights, the installer `.exe` has already been downloaded to a known local path, and a user-scoped install directory is acceptable
- shell: PowerShell
- validated_shape: `$installer='<ABS_INSTALLER_EXE>'; $targetDir='<ABS_USER_INSTALL_DIR>'; $argList=@('/VERYSILENT','/NORESTART','/NOCANCEL','/SP-','/CURRENTUSER',('/DIR="' + $targetDir + '"')); $proc=Start-Process -FilePath $installer -ArgumentList $argList -Wait -PassThru; $proc.ExitCode`
- substitute_only: `<ABS_INSTALLER_EXE>`, `<ABS_USER_INSTALL_DIR>`
- preflight: `Test-Path '<ABS_INSTALLER_EXE>'`; create or verify the parent of `<ABS_USER_INSTALL_DIR>`; prefer a user-writable target such as `%LOCALAPPDATA%\Programs\<TOOL>`; if a first attempt via `winget` or another package manager was cancelled at admin elevation, switch command shape instead of retrying the same route
- env: none
- avoid: Repeating a package-manager install path that already triggered admin elevation when per-user install is sufficient; assuming `Program Files` is required; invoking the installer by bare file name when the exact local path is known; storing project-specific paths in the reusable pattern
- success_signal: The installer exits with code `0` and the expected executable tree exists under the user install directory
- capture_rule: Reuse this shape for Git for Windows and similar Inno Setup style installers when a first admin-elevation path fails but a current-user silent install succeeds; keep product-specific component flags optional and append them only when they are already validated

### Pattern: powershell-persist-user-cli-path-and-env
- scenario: A newly installed user-scoped Windows CLI works only in the current session or a dependent tool cannot find a helper executable in later sessions
- use_when: The tool was installed under `%LOCALAPPDATA%` or another user-writable directory, the executable tree is known, and the fix needs to persist for future terminals without admin rights
- shell: PowerShell
- validated_shape: `$cliDir='<ABS_CLI_DIR>'; $helperDir='<ABS_HELPER_DIR>'; $helperExe='<ABS_HELPER_EXE>'; [Environment]::SetEnvironmentVariable('<HELPER_ENV_NAME>', $helperExe, 'User'); $userPath=[Environment]::GetEnvironmentVariable('Path','User'); $parts=@(); if ($userPath) { $parts=$userPath -split ';' | Where-Object { $_ -and $_.Trim() } }; foreach ($p in @($cliDir,$helperDir)) { if ($parts -notcontains $p) { $parts += $p } }; [Environment]::SetEnvironmentVariable('Path', ($parts -join ';'), 'User')`
- substitute_only: `<ABS_CLI_DIR>`, `<ABS_HELPER_DIR>`, `<ABS_HELPER_EXE>`, `<HELPER_ENV_NAME>`
- preflight: `Test-Path '<ABS_CLI_DIR>'`; `Test-Path '<ABS_HELPER_DIR>'`; `Test-Path '<ABS_HELPER_EXE>'`; read the current user `Path` first and append only missing entries; after writing the user environment, test from a clean `powershell.exe -NoProfile` process
- env: writes user-scoped `Path` and one user-scoped helper environment variable
- avoid: Assuming a config file override is enough when the tool checks `PATH` or environment before loading user settings; appending duplicate path segments on every run; writing machine-scoped environment variables when user scope is enough
- success_signal: A fresh `powershell.exe -NoProfile` process can launch the CLI successfully without session-local path hacks
- capture_rule: Reuse this shape for user-scoped Git, bash, or helper-executable discovery fixes after a per-user install; prefer both the explicit helper environment variable and the user `Path` update when a downstream CLI reports missing bash or helper binaries

### Pattern: powershell-invoke-webrequest-download
- scenario: Downloading a webpage or PDF to a known local file on Windows when Python `requests` or another client times out but the native PowerShell downloader succeeds
- use_when: The task needs a local snapshot from a vendor site and the URL plus destination file path are already known
- shell: PowerShell
- validated_shape: `$u='<URL>'; $o='<ABS_OUTPUT_PATH>'; Invoke-WebRequest -Uri $u -OutFile $o -TimeoutSec <SECONDS>; Get-Item $o | Select-Object FullName,Length`
- substitute_only: `<URL>`, `<ABS_OUTPUT_PATH>`, `<SECONDS>`
- preflight: `Test-Path (Split-Path -Parent '<ABS_OUTPUT_PATH>')`; if overwriting would be risky, check `Test-Path '<ABS_OUTPUT_PATH>'` first; keep the output path absolute
- env: none
- avoid: Embedding the URL or Chinese output path inside a Python one-liner after a timeout has already shown the HTTP client is flaky; writing to a relative output path when the exact workspace destination is known; chaining additional parsing into the same download command before confirming the file landed
- success_signal: `Invoke-WebRequest` returns without error and `Get-Item` reports the expected output file with non-zero length
- capture_rule: Reuse this native PowerShell download shape for vendor HTML/PDF snapshots when Python `requests` times out but `Invoke-WebRequest -OutFile` succeeds; keep the command short and verify the landed file immediately with `Get-Item`
