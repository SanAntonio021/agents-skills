[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string]$ScriptPath,

    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$ScriptArgs
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $PSCommandPath
$ensureScript = Join-Path $scriptDir "ensure_runtime.ps1"
$runtimeDir = & $ensureScript -Quiet
$targetScript = Join-Path $runtimeDir $ScriptPath

if (-not (Test-Path -LiteralPath $targetScript -PathType Leaf)) {
    throw "Runtime script not found: $targetScript"
}

$hadPythonUtf8 = Test-Path Env:PYTHONUTF8
$previousPythonUtf8 = $null
if ($hadPythonUtf8) {
    $previousPythonUtf8 = $env:PYTHONUTF8
}

$hadPythonIoEncoding = Test-Path Env:PYTHONIOENCODING
$previousPythonIoEncoding = $null
if ($hadPythonIoEncoding) {
    $previousPythonIoEncoding = $env:PYTHONIOENCODING
}

Push-Location $runtimeDir

try {
    $env:PYTHONUTF8 = "1"
    $env:PYTHONIOENCODING = "utf-8"
    & python $ScriptPath @ScriptArgs
    $exitCode = $LASTEXITCODE
}
finally {
    Pop-Location

    if ($hadPythonUtf8) {
        $env:PYTHONUTF8 = $previousPythonUtf8
    }
    else {
        Remove-Item Env:PYTHONUTF8 -ErrorAction SilentlyContinue
    }

    if ($hadPythonIoEncoding) {
        $env:PYTHONIOENCODING = $previousPythonIoEncoding
    }
    else {
        Remove-Item Env:PYTHONIOENCODING -ErrorAction SilentlyContinue
    }
}

exit $exitCode
