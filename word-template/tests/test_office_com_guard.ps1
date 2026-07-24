$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$skillRoot = Split-Path -Parent $scriptRoot
$modulePath = Join-Path $skillRoot "scripts\OfficeComGuard.psm1"
$mainScriptPath = Join-Path $skillRoot "scripts\export_markdown_to_word.ps1"
Import-Module $modulePath -Force

$testsRun = 0

function Assert-True {
    param(
        [Parameter(Mandatory = $true)][bool]$Condition,
        [Parameter(Mandatory = $true)][string]$Message
    )
    if (-not $Condition) {
        throw $Message
    }
}

function Invoke-GuardTest {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][scriptblock]$Body
    )

    & $Body
    $script:testsRun += 1
    Write-Output "PASS: $Name"
}

Invoke-GuardTest "no permission rejects before process probe" {
    $state = [PSCustomObject]@{ ProbeCalls = 0 }
    $probe = { $state.ProbeCalls += 1; return $false }.GetNewClosure()
    $threw = $false
    try {
        Assert-WordComPermission `
            -AllowOfficeCom:$false `
            -WordProcessProbe $probe
    }
    catch {
        $threw = $true
    }
    Assert-True $threw "Expected missing permission to fail."
    Assert-True ($state.ProbeCalls -eq 0) "Process probe ran before permission gate."
}

Invoke-GuardTest "existing Word rejects" {
    $threw = $false
    try {
        Assert-WordComPermission `
            -AllowOfficeCom `
            -WordProcessProbe { $true }
    }
    catch {
        $threw = $true
    }
    Assert-True $threw "Expected an existing Word process to fail."
}

Invoke-GuardTest "probe failure rejects" {
    $threw = $false
    try {
        Assert-WordComPermission `
            -AllowOfficeCom `
            -WordProcessProbe { throw "fake probe failure" }
    }
    catch {
        $threw = $true
    }
    Assert-True $threw "Expected a failed process probe to fail closed."
}

Invoke-GuardTest "explicit permission with no Word passes" {
    $state = [PSCustomObject]@{ ProbeCalls = 0 }
    $probe = { $state.ProbeCalls += 1; return $false }.GetNewClosure()
    Assert-WordComPermission `
        -AllowOfficeCom `
        -WordProcessProbe $probe
    Assert-True ($state.ProbeCalls -eq 1) "Expected one process probe."
}

foreach ($path in @($modulePath, $mainScriptPath)) {
    $tokens = $null
    $parseErrors = $null
    [System.Management.Automation.Language.Parser]::ParseFile(
        $path,
        [ref]$tokens,
        [ref]$parseErrors
    ) | Out-Null
    Assert-True ($parseErrors.Count -eq 0) "PowerShell parse errors in $path."
}

$mainSource = Get-Content -LiteralPath $mainScriptPath -Raw -Encoding UTF8
Assert-True ($mainSource -notmatch 'New-Object\s+-ComObject') "PowerShell entrypoint still creates COM directly."
Assert-True ($mainSource -notmatch '\.Quit\s*\(') "PowerShell entrypoint still quits Word directly."
Assert-True ($mainSource -match 'apply-native-template') "Native template mode is not delegated to Python."

Write-Output "PASS: PowerShell AST and delegation contract"
Write-Output "PowerShell guard tests passed: $testsRun"
