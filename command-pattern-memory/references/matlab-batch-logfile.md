# MATLAB Batch With Logfile

### Pattern: powershell-matlab-batch-scriptname-logfile
- scenario: Windows MATLAB batch execution with reliable log capture
- use_when: The task needs to run a repo-local MATLAB script or function from PowerShell and capture startup or runtime failures to a file.
- shell: PowerShell
- validated_shape: `Start-Process -FilePath "<MATLAB_EXE>" -ArgumentList @('-batch','<MATLAB_SCRIPT_NAME>','-logfile','<LOG_PATH>') -WorkingDirectory "<WORKDIR>" -PassThru -Wait`
- substitute_only: `<MATLAB_EXE>`, `<MATLAB_SCRIPT_NAME>`, `<LOG_PATH>`, `<WORKDIR>`
- preflight: `Get-Command "matlab"` or `Test-Path "<MATLAB_EXE>"`; `Test-Path "<WORKDIR>"`; `Test-Path (Join-Path "<WORKDIR>" "<MATLAB_SCRIPT_NAME>.m")` when calling a repo-local script; ensure the parent directory of `<LOG_PATH>` exists
- env: none
- avoid: Embedding repo-local script execution inside `-batch` text such as `cd(...) ; run(...)` when a plain script or function name will work; relying only on stdout or stderr redirection for early MATLAB startup failures; skipping `-logfile` when diagnosing MATLAB or hardware-launch issues
- success_signal: MATLAB starts, the logfile is non-empty, and the target script either completes successfully or emits a MATLAB-side stack trace in the logfile
- capture_rule: Update this entry when another stable MATLAB-specific preflight or argument shape proves reusable across repositories

### Pattern: powershell-matlab-batch-checkcode-expression
- scenario: Run MATLAB `checkcode` or another short MATLAB-side inspection from PowerShell
- use_when: The task only needs a compact MATLAB expression and does not need a dedicated logfile-backed script launch
- shell: PowerShell
- validated_shape: `matlab -batch "issues = checkcode('<ABS_FILE_PATH>','-cyc'); disp(numel(issues));"`
- substitute_only: `<ABS_FILE_PATH>`
- preflight: `Get-Command "matlab"`; `Test-Path "<ABS_FILE_PATH>"`
- env: none
- avoid: Calling `checkcode(...)` directly in PowerShell as if it were a shell command; omitting quotes around the absolute MATLAB file path; using this lightweight shape when startup diagnostics need `-logfile`
- success_signal: MATLAB starts, evaluates the `checkcode` expression, and prints the issue count instead of a PowerShell command-not-found error
- capture_rule: Reuse this shape for short MATLAB analyzer or inspection expressions that are safer to execute inside `matlab -batch` than directly in PowerShell

### Pattern: powershell-matlab-batch-cd-addpath-capture-replay
- scenario: Re-evaluate a saved MATLAB capture or replay helper from PowerShell with repo-local functions on path
- use_when: The task needs to load a `.mat` capture, add the repo's MATLAB tree, and run a helper such as `Func_Rx_Demod(...)` or `regenerate_demod_plot_from_capture_awg_ai(...)` inside `matlab -batch`
- shell: PowerShell
- validated_shape: `matlab -batch "cd('<REPO_ROOT>'); addpath(genpath('<MATLAB_ROOT>')); <MATLAB_EXPRESSION>;"`
- substitute_only: `<REPO_ROOT>`, `<MATLAB_ROOT>`, `<MATLAB_EXPRESSION>`
- preflight: `Get-Command "matlab"`; `Test-Path "<REPO_ROOT>"`; `Test-Path "<MATLAB_ROOT>"`; `Test-Path` for any capture or artifact paths interpolated into `<MATLAB_EXPRESSION>`
- env: none
- avoid: Writing a temporary `.m` file when a one-shot batch expression is sufficient; calling repo-local MATLAB helpers without first adding the repo `matlab` tree to path; assuming runtime TX files are stable when replaying a saved capture
- success_signal: MATLAB starts, resolves repo-local helpers, and prints the replay or regeneration result without a function-not-found error
- capture_rule: Prefer this shape for capture validation and offline redraw work that depends on repo-local helper functions

### Pattern: powershell-startprocess-matlab-batch-expression-logfile
- scenario: Launch a long-running MATLAB batch expression asynchronously from PowerShell and keep a logfile
- use_when: The task needs `Start-Process` so MATLAB can keep running in the background, and the `-batch` body is a compound expression such as `cd(...); addpath(...); run_scan_...;`
- shell: PowerShell
- validated_shape: `Start-Process -FilePath "<MATLAB_EXE>" -ArgumentList ('-logfile "<LOG_PATH>" -batch "<MATLAB_EXPRESSION>"') -WorkingDirectory "<WORKDIR>" -PassThru`
- substitute_only: `<MATLAB_EXE>`, `<LOG_PATH>`, `<MATLAB_EXPRESSION>`, `<WORKDIR>`
- preflight: `Test-Path "<MATLAB_EXE>"`; `Test-Path "<WORKDIR>"`; ensure the parent directory of `<LOG_PATH>` exists; verify any repo-local entrypoint referenced by `<MATLAB_EXPRESSION>` is reachable after the planned `cd(...)` and `addpath(...)`
- env: none
- avoid: Passing the complex batch expression through `-ArgumentList @('-logfile', '<LOG_PATH>', '-batch', '<MATLAB_EXPRESSION>')` because `Start-Process` can silently lose the compound expression and leave an empty logfile; assuming a repo-local function is on MATLAB's default path without an explicit `cd(...)` and `addpath(genpath(...))`
- success_signal: `Start-Process` returns a live MATLAB PID, the logfile becomes non-empty, and the expected startup lines from the batch expression appear in the log
- capture_rule: Reuse this shape whenever a background MATLAB run needs both a logfile and a multi-statement `-batch` expression

### Pattern: powershell-startprocess-matlab-desktop-script-statusfile
- scenario: Launch a repo-local MATLAB desktop script from PowerShell, let it drive hardware in desktop mode, and treat a status JSON as the completion signal
- use_when: `matlab -batch` is unstable for the workload, but the same script runs reliably in desktop MATLAB and can write a success/failure status file before exit
- shell: PowerShell
- validated_shape: `Start-Process -FilePath "<MATLAB_EXE>" -ArgumentList ('-logfile "<LOG_PATH>" -r "<MATLAB_EXPRESSION>"') -WorkingDirectory "<WORKDIR>" -PassThru`, then poll the spawned `MATLAB.exe` child and `<STATUS_JSON>` until the script reports `SUCCESS` or `FAILED`
- substitute_only: `<MATLAB_EXE>`, `<LOG_PATH>`, `<MATLAB_EXPRESSION>`, `<WORKDIR>`, `<STATUS_JSON>`
- preflight: `Test-Path "<MATLAB_EXE>"`; `Test-Path "<WORKDIR>"`; ensure the parent directories of `<LOG_PATH>` and `<STATUS_JSON>` exist; verify any repo-local script referenced by `<MATLAB_EXPRESSION>` is reachable after the planned `cd(...)`; set the required environment variables before launch if the MATLAB script reads configuration from `getenv(...)`
- env: Typically `AWG_AI_SINGLE_POINT_RESULT_ROOT`, `AWG_AI_SINGLE_POINT_STATUS_JSON`, `AWG_AI_SINGLE_POINT_SCAN_CHANNEL`, `AWG_AI_SINGLE_POINT_AMP_V` or the repo-specific equivalents consumed by the script
- avoid: Passing the complex desktop expression through `-ArgumentList @('-logfile', '<LOG_PATH>', '-r', '<MATLAB_EXPRESSION>')` because `Start-Process` can mis-handle the expression; assuming `matlab.exe` itself is the long-lived worker rather than the short-lived launcher; treating PowerShell as the root cause when the real issue is MATLAB batch-mode exit instability
- success_signal: The script writes `<STATUS_JSON>` with `status = SUCCESS` or `status = FAILED`, the logfile is non-empty, and any spawned `MATLAB.exe` child either exits on its own or can be safely closed after the status file is written
- capture_rule: Prefer this shape for unattended hardware point-runs when desktop MATLAB is measurably more stable than `-batch`, and keep the status-file contract minimal so the launcher can restart from the next point
