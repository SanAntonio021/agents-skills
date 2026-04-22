[CmdletBinding()]
param(
    [switch]$Json,
    [switch]$Quiet,
    [switch]$RefreshStatic
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Copy-Tree {
    param(
        [Parameter(Mandatory = $true)]
        [string]$SourcePath,

        [Parameter(Mandatory = $true)]
        [string]$DestinationPath
    )

    if (Test-Path -LiteralPath $SourcePath -PathType Container) {
        New-Item -ItemType Directory -Path $DestinationPath -Force | Out-Null
        Get-ChildItem -LiteralPath $SourcePath -Force | ForEach-Object {
            Copy-Item -LiteralPath $_.FullName -Destination $DestinationPath -Recurse -Force
        }
        return
    }

    $parent = Split-Path -Parent $DestinationPath
    if ($parent) {
        New-Item -ItemType Directory -Path $parent -Force | Out-Null
    }

    Copy-Item -LiteralPath $SourcePath -Destination $DestinationPath -Force
}

$scriptDir = Split-Path -Parent $PSCommandPath
$customSkillDir = Split-Path -Parent $scriptDir
$skillsRoot = Split-Path -Parent (Split-Path -Parent $customSkillDir)
$vendorDir = Join-Path $skillsRoot "vendor\long-term-memory"

if (-not (Test-Path -LiteralPath $vendorDir -PathType Container)) {
    throw "Vendor skill not found: $vendorDir"
}

$codexHome = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $env:USERPROFILE ".codex" }
$stateRoot = Join-Path $codexHome "state\long-term-memory"
$runtimeDir = Join-Path $stateRoot "runtime"

$staticItems = @(
    "assets",
    "references",
    "scripts",
    "requirements.txt",
    "SETUP_GUIDE.md",
    "SKILL.md"
)

$seedOnlyItems = @(
    "memories",
    "short-term"
)

New-Item -ItemType Directory -Path $stateRoot -Force | Out-Null

$initialized = $false
$refreshed = $false

if (-not (Test-Path -LiteralPath $runtimeDir -PathType Container)) {
    New-Item -ItemType Directory -Path $runtimeDir -Force | Out-Null
    Get-ChildItem -LiteralPath $vendorDir -Force | ForEach-Object {
        Copy-Item -LiteralPath $_.FullName -Destination $runtimeDir -Recurse -Force
    }
    $initialized = $true
}
else {
    foreach ($item in $staticItems + $seedOnlyItems) {
        $sourcePath = Join-Path $vendorDir $item
        $destinationPath = Join-Path $runtimeDir $item

        if (-not (Test-Path -LiteralPath $destinationPath)) {
            Copy-Tree -SourcePath $sourcePath -DestinationPath $destinationPath
        }
    }
}

if ($RefreshStatic) {
    foreach ($item in $staticItems) {
        $sourcePath = Join-Path $vendorDir $item
        $destinationPath = Join-Path $runtimeDir $item
        Copy-Tree -SourcePath $sourcePath -DestinationPath $destinationPath
    }
    $refreshed = $true
}

$result = [PSCustomObject]@{
    custom_skill_dir = $customSkillDir
    vendor_dir = $vendorDir
    codex_home = $codexHome
    state_root = $stateRoot
    runtime_dir = $runtimeDir
    initialized = $initialized
    refreshed_static = $refreshed
}

if ($Json) {
    $result | ConvertTo-Json -Compress
    exit 0
}

if ($Quiet) {
    $runtimeDir
    exit 0
}

Write-Output "Long-term memory runtime is ready."
Write-Output "Vendor dir : $vendorDir"
Write-Output "State root : $stateRoot"
Write-Output "Runtime dir: $runtimeDir"
Write-Output "Initialized: $initialized"
Write-Output "Refreshed  : $refreshed"
