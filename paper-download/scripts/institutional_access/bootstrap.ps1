[CmdletBinding()]
param(
    [switch]$Check
)

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$OutputEncoding = [Text.Encoding]::UTF8

function Write-Status {
    param(
        [string]$Status,
        [bool]$Ready,
        [string]$Venv,
        [string]$Python,
        [string]$Pypdf,
        [string]$Reason = $null
    )
    [pscustomobject]@{
        status = $Status
        ready = $Ready
        venv = $Venv
        python = $Python
        pypdf = $Pypdf
        reason = $Reason
    } | ConvertTo-Json -Compress
}

$localAppData = $env:LOCALAPPDATA
if ([string]::IsNullOrWhiteSpace($localAppData) -or -not [IO.Path]::IsPathRooted($localAppData)) {
    Write-Status -Status 'environment_failure' -Ready $false -Venv '' -Python '' -Pypdf '' -Reason 'LOCALAPPDATA is unavailable'
    exit 1
}

$stateRoot = Join-Path $localAppData 'PaperDownload'
$venv = Join-Path $stateRoot 'venv'
$venvPython = Join-Path $venv 'Scripts\python.exe'
$requirements = Join-Path $PSScriptRoot 'requirements.txt'

function Test-Pypdf {
    if (-not (Test-Path -LiteralPath $venvPython -PathType Leaf)) {
        return $null
    }
    $value = & $venvPython -c "import pypdf; print(pypdf.__version__)" 2>$null
    if ($LASTEXITCODE -ne 0) {
        return $null
    }
    return [string]$value
}

$pypdf = Test-Pypdf
if ($null -ne $pypdf) {
    Write-Status -Status 'ready' -Ready $true -Venv $venv -Python $venvPython -Pypdf $pypdf
    exit 0
}

if ($Check) {
    Write-Status -Status 'setup_required' -Ready $false -Venv $venv -Python $venvPython -Pypdf '' -Reason 'dedicated Python environment or pypdf is missing'
    exit 1
}

$basePython = $env:PAPER_DOWNLOAD_BASE_PYTHON
if ([string]::IsNullOrWhiteSpace($basePython)) {
    $pyLauncher = Get-Command py -ErrorAction SilentlyContinue
    if ($pyLauncher) {
        $candidate = & $pyLauncher.Source -3 -c "import sys; print(sys.executable)" 2>$null
        if ($LASTEXITCODE -eq 0) {
            $basePython = [string]$candidate
        }
    }
}
if ([string]::IsNullOrWhiteSpace($basePython)) {
    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if ($pythonCommand) {
        $basePython = $pythonCommand.Source
    }
}
if ([string]::IsNullOrWhiteSpace($basePython) -or -not (Test-Path -LiteralPath $basePython -PathType Leaf)) {
    Write-Status -Status 'environment_failure' -Ready $false -Venv $venv -Python $venvPython -Pypdf '' -Reason 'Python 3 was not found'
    exit 1
}
$versionText = & $basePython -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
if ($LASTEXITCODE -ne 0 -or [version]$versionText -lt [version]'3.10') {
    Write-Status -Status 'environment_failure' -Ready $false -Venv $venv -Python $venvPython -Pypdf '' -Reason 'Python 3.10 or newer is required'
    exit 1
}

if (-not (Test-Path -LiteralPath $venvPython -PathType Leaf)) {
    New-Item -ItemType Directory -Path $stateRoot -Force | Out-Null
    & $basePython -m venv $venv *> $null
    if ($LASTEXITCODE -ne 0) {
        Write-Status -Status 'environment_failure' -Ready $false -Venv $venv -Python $venvPython -Pypdf '' -Reason 'virtual environment creation failed'
        exit 1
    }
}

$env:PIP_DISABLE_PIP_VERSION_CHECK = '1'
$installOutput = & $venvPython -m pip install --disable-pip-version-check -r $requirements 2>&1
if ($LASTEXITCODE -ne 0) {
    [pscustomobject]@{
        status = 'environment_failure'
        ready = $false
        venv = $venv
        python = $venvPython
        pypdf = ''
        reason = 'pypdf installation failed'
        detail = (($installOutput | Select-Object -Last 8) -join "`n")
    } | ConvertTo-Json -Compress
    exit 1
}

$pypdf = Test-Pypdf
if ($null -eq $pypdf) {
    Write-Status -Status 'environment_failure' -Ready $false -Venv $venv -Python $venvPython -Pypdf '' -Reason 'pypdf import check failed'
    exit 1
}

Write-Status -Status 'ready' -Ready $true -Venv $venv -Python $venvPython -Pypdf $pypdf
