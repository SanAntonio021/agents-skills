[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$CliArgs
)

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$OutputEncoding = [Text.Encoding]::UTF8
$bootstrap = Join-Path $PSScriptRoot 'bootstrap.ps1'
$statusText = & $bootstrap
if ($LASTEXITCODE -ne 0) {
    [Console]::Out.WriteLine($statusText)
    exit $LASTEXITCODE
}
$statusLine = @($statusText) | Select-Object -Last 1
$status = $statusLine | ConvertFrom-Json
$python = [string]$status.python
$scriptsRoot = Split-Path $PSScriptRoot -Parent
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONDONTWRITEBYTECODE = '1'
$previousPythonPath = $env:PYTHONPATH
if ([string]::IsNullOrWhiteSpace($previousPythonPath)) {
    $env:PYTHONPATH = $scriptsRoot
} else {
    $env:PYTHONPATH = $scriptsRoot + [IO.Path]::PathSeparator + $previousPythonPath
}
try {
    & $python -m institutional_access @CliArgs
    exit $LASTEXITCODE
}
finally {
    $env:PYTHONPATH = $previousPythonPath
}
