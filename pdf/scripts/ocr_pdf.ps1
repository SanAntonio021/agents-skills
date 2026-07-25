[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$InputPdf,

    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[A-Za-z0-9_]+(?:\+[A-Za-z0-9_]+)*$')]
    [string]$Languages,

    [ValidateSet('auto', 'none', 'skip', 'redo')]
    [string]$Mode = 'auto',

    [string]$OutputDirectory,

    [switch]$Deskew,

    [ValidateRange(1, 64)]
    [int]$Jobs = 1,

    [ValidateRange(30, 86400)]
    [int]$TimeoutSeconds = 1800
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$resolvedInput = (Resolve-Path -LiteralPath $InputPdf -ErrorAction Stop).Path
$python = Join-Path $env:LOCALAPPDATA 'pdf-ocr\.venv\Scripts\python.exe'
$router = Join-Path $PSScriptRoot 'ocr_pdf.py'
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw "OCR Python environment not found: $python"
}
if (-not (Test-Path -LiteralPath $router -PathType Leaf)) {
    throw "OCR router not found: $router"
}

$arguments = @(
    $router,
    '--input', $resolvedInput,
    '--languages', $Languages,
    '--mode', $Mode,
    '--jobs', $Jobs,
    '--timeout-seconds', $TimeoutSeconds
)
if ($OutputDirectory) {
    $arguments += @('--output-directory', $OutputDirectory)
}
if ($Deskew) {
    $arguments += '--deskew'
}

& $python @arguments
$exitCode = $LASTEXITCODE
if ($exitCode -ne 0) {
    exit $exitCode
}
