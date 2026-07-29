[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Config,
    [Parameter(Mandatory = $true)][string]$OutputDir,
    [Parameter(Mandatory = $true)][string]$ApprovedRetirementSha256,
    [switch]$Recycle,
    [switch]$Resume,
    [string]$MockRecycleRoot = ''
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'ProjectOrganizer.psm1') -Force

function Save-RetirementState {
    param($State,[string]$Path)
    $State.completed_retirement_ids=@($State.completed_retirement_ids | Sort-Object -Unique)
    Write-POJson -Path $Path -Value $State
}

function Send-POFileToRecycleBin {
    param([string]$Path,[string]$MockRoot,[string]$SourceId,[string]$RelativePath)
    if ($MockRoot) {
        $destinationRoot = Join-Path $MockRoot $SourceId
        $destination = Join-POPath -Root $destinationRoot -RelativePath $RelativePath
        [void][IO.Directory]::CreateDirectory((ConvertTo-POExtendedPath (Split-Path -Parent $destination)))
        if ([IO.File]::Exists((ConvertTo-POExtendedPath $destination))) { throw "Mock recycle target already exists: $destination" }
        if (Test-POSameVolume -First $Path -Second $destination) {
            [IO.File]::Move((ConvertTo-POExtendedPath $Path),(ConvertTo-POExtendedPath $destination))
        }
        else {
            $hash=Get-POStableSha256 -Path $Path
            [void](Copy-POFileAtomicVerified -Source $Path -Target $destination -ExpectedSha256 $hash)
            [IO.File]::Delete((ConvertTo-POExtendedPath $Path))
        }
        return
    }
    Add-Type -AssemblyName Microsoft.VisualBasic
    [Microsoft.VisualBasic.FileIO.FileSystem]::DeleteFile(
        $Path,
        [Microsoft.VisualBasic.FileIO.UIOption]::OnlyErrorDialogs,
        [Microsoft.VisualBasic.FileIO.RecycleOption]::SendToRecycleBin,
        [Microsoft.VisualBasic.FileIO.UICancelOption]::ThrowException
    )
}

if ($ApprovedRetirementSha256 -notmatch '^[0-9A-Fa-f]{64}$') { throw 'ApprovedRetirementSha256 must contain exactly 64 hexadecimal characters.' }
$approved=$ApprovedRetirementSha256.ToUpperInvariant()
$settings=Read-POConfig -Path $Config -RequireSources -ForExecution
$output=Resolve-POFullPath -Path $OutputDir
$hashPath=Join-Path $output 'retirement.sha256'
$manifest=Join-Path $output 'retirement-files.sha256'
if (-not (Test-Path -LiteralPath $hashPath) -or -not (Test-Path -LiteralPath $manifest)) { throw 'Retirement plan artifacts are missing.' }
$recorded=(Get-Content -LiteralPath $hashPath -Encoding UTF8 -Raw).Trim().ToUpperInvariant()
if ($approved -ne $recorded) { throw 'Approved retirement SHA256 does not match retirement.sha256.' }
if ((Get-POStableSha256 -Path $manifest) -ne $recorded) { throw 'retirement.sha256 is stale.' }
$manifestCheck=Test-POHashManifest -ManifestPath $manifest
if (-not $manifestCheck.Valid) { throw "Retirement plan changed: $($manifestCheck.Errors -join '; ')" }
$rows=@(Import-Csv -LiteralPath (Join-Path $output 'retirement.csv') -Encoding UTF8)
$errors=@(Import-Csv -LiteralPath (Join-Path $output 'retirement-errors.csv') -Encoding UTF8)
$holds=@($rows | Where-Object { $_.action -like 'hold_*' })
if ($errors.Count -gt 0 -or $holds.Count -gt 0) { throw "Retirement is not executable: hold=$($holds.Count), errors=$($errors.Count)." }

$gitArchivesPath=Join-Path $output 'git_archives.json'
if (Test-Path -LiteralPath $gitArchivesPath) {
    foreach ($archive in @(Read-POJsonArray -Path $gitArchivesPath)) {
        if ((Get-POStableSha256 -Path ([string]$archive.bundle_path)) -ne ([string]$archive.bundle_sha256).ToUpperInvariant()) { throw "Git bundle changed: $($archive.source_id)" }
    }
}

if ($MockRecycleRoot) {
    $mock=Resolve-POFullPath -Path $MockRecycleRoot -AllowMissing
    $temporaryRoot=Resolve-POFullPath -Path ([IO.Path]::GetTempPath()) -AllowMissing
    if (-not (Test-POPathWithin -Path $mock -Parent $temporaryRoot)) { throw 'MockRecycleRoot is test-only and must be inside the current temporary directory.' }
    [void][IO.Directory]::CreateDirectory((ConvertTo-POExtendedPath $mock))
}
else { $mock='' }

$statePath=Join-Path $output 'retirement-execution-state.json'
$logPath=Join-Path $output 'retirement-execution.jsonl'
if (Test-Path -LiteralPath $statePath) {
    if (-not $Resume) { throw 'Retirement state already exists. Use -Resume with the same approved plan.' }
    $state=Get-Content -LiteralPath $statePath -Encoding UTF8 -Raw | ConvertFrom-Json
    if ([string]$state.retirement_sha256 -ne $approved) { throw 'Resume state belongs to another retirement plan.' }
}
else {
    if ($Resume) { throw 'No retirement state exists to resume.' }
    $state=[pscustomobject][ordered]@{ schema_version='1.0'; retirement_sha256=$approved; completed_retirement_ids=@(); failed_retirement_id=''; complete=$false }
}

if (-not $Recycle) {
    foreach ($row in $rows) {
        if ([string]$row.entry_type -eq 'file' -and [string]$row.action -ne 'already_moved') {
            [void](Assert-POExpectedFile -Path ([string]$row.source_path) -SizeBytes ([int64]$row.size_bytes) -LastWriteUtc ([string]$row.last_write_utc) -Sha256 ([string]$row.sha256))
        }
    }
    Write-Output "Preflight passed for retirement $approved. No files changed because -Recycle was not supplied."
    return
}

$completed=@{}; foreach($id in @($state.completed_retirement_ids)){ $completed[[string]$id]=$true }
foreach($row in $rows){
    $id=[string]$row.retirement_id
    if($completed.ContainsKey($id)){continue}
    $sourceConfig=@($settings.sources | Where-Object { [string]$_.id -eq [string]$row.source_id })
    if($sourceConfig.Count -ne 1 -or -not (Test-POPathWithin -Path ([string]$row.source_path) -Parent ([string]$sourceConfig[0].path) -AllowEqual)){throw "Retirement path is outside confirmed source: $id"}
    Add-POJsonLine -Path $logPath -Value ([ordered]@{event='start';retirement_id=$id;action=$row.action;path=$row.source_path})
    try{
        switch([string]$row.action){
            'already_moved' {
                if([IO.File]::Exists((ConvertTo-POExtendedPath ([string]$row.source_path)))){throw 'Moved source reappeared.'}
            }
            {$_ -in @('recycle_verified_copy_source','recycle_exact_duplicate','recycle_cache','recycle_git_metadata')} {
                [void](Assert-POExpectedFile -Path ([string]$row.source_path) -SizeBytes ([int64]$row.size_bytes) -LastWriteUtc ([string]$row.last_write_utc) -Sha256 ([string]$row.sha256))
                Send-POFileToRecycleBin -Path ([string]$row.source_path) -MockRoot $mock -SourceId ([string]$row.source_id) -RelativePath ([string]$row.relative_path)
                if([IO.File]::Exists((ConvertTo-POExtendedPath ([string]$row.source_path)))){throw 'Recycle API returned but source still exists.'}
            }
            'remove_empty_directory' {
                $path=[string]$row.source_path
                if([IO.Directory]::Exists((ConvertTo-POExtendedPath $path))){
                    $remaining=@([IO.Directory]::EnumerateFileSystemEntries((ConvertTo-POExtendedPath $path)))
                    if($remaining.Count -gt 0){throw "Directory is not empty: $path"}
                    [IO.Directory]::Delete((ConvertTo-POExtendedPath $path),$false)
                }
            }
            default {throw "Unsupported retirement action: $($row.action)"}
        }
        $state.completed_retirement_ids=@($state.completed_retirement_ids)+$id
        $state.failed_retirement_id=''
        Save-RetirementState -State $state -Path $statePath
        Add-POJsonLine -Path $logPath -Value ([ordered]@{event='complete';retirement_id=$id;action=$row.action})
    }
    catch{
        $state.failed_retirement_id=$id
        Save-RetirementState -State $state -Path $statePath
        Add-POJsonLine -Path $logPath -Value ([ordered]@{event='failed';retirement_id=$id;action=$row.action;error=$_.Exception.Message})
        throw
    }
}
$state.complete=$true
Save-RetirementState -State $state -Path $statePath
Write-POJson -Path (Join-Path $output 'retirement-execution-summary.json') -Value ([ordered]@{
    schema_version='1.0';retirement_sha256=$approved;planned_actions=$rows.Count
    completed_actions=@($state.completed_retirement_ids).Count;complete=$true;recycle_adapter=if($mock){'mock'}else{'windows_shell'}
})
Write-Output "Retirement execution complete: $($rows.Count) actions. Recycle Bin was not emptied."
