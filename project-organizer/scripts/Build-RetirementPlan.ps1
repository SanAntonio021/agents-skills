[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Config,
    [Parameter(Mandatory = $true)][string]$OutputDir
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'ProjectOrganizer.psm1') -Force

$settings = Read-POConfig -Path $Config -RequireSources -ForExecution
$configPath = Resolve-POFullPath -Path $Config
$output = Resolve-POFullPath -Path $OutputDir
$acceptancePath = Join-Path $output 'organization-acceptance.json'
if (-not (Test-Path -LiteralPath $acceptancePath)) { throw 'Organization acceptance is missing.' }
$acceptance = Get-Content -LiteralPath $acceptancePath -Encoding UTF8 -Raw | ConvertFrom-Json
if (-not $acceptance.accepted) { throw 'Organization acceptance did not pass.' }
$planHashPath = Join-Path $output 'plan.sha256'
$planHash = (Get-Content -LiteralPath $planHashPath -Encoding UTF8 -Raw).Trim().ToUpperInvariant()
if ([string]$acceptance.plan_sha256 -ne $planHash) { throw 'Acceptance and plan hashes differ.' }
$actions = @(Import-Csv -LiteralPath (Join-Path $output 'actions.csv') -Encoding UTF8)
$executionState = Get-Content -LiteralPath (Join-Path $output 'execution-state.json') -Encoding UTF8 -Raw | ConvertFrom-Json
$gitArchivesPath = Join-Path $output 'git_archives.json'
$gitArchives = @()
if (Test-Path -LiteralPath $gitArchivesPath) { $gitArchives = @(Read-POJsonArray -Path $gitArchivesPath) }
foreach ($archive in $gitArchives) {
    if ((Get-POStableSha256 -Path ([string]$archive.bundle_path)) -ne ([string]$archive.bundle_sha256).ToUpperInvariant()) { throw "Git bundle changed: $($archive.source_id)" }
}

$actionBySource = @{}
foreach ($action in $actions) { $actionBySource[([string]$action.source_path).ToLowerInvariant()] = $action }
$retirement = New-Object Collections.Generic.List[object]
$errors = New-Object Collections.Generic.List[object]

foreach ($action in @($actions | Where-Object action -eq 'move_file_verify')) {
    $exists = [IO.File]::Exists((ConvertTo-POExtendedPath ([string]$action.source_path)))
    $retirement.Add([pscustomobject][ordered]@{
        retirement_id=''; action=if ($exists) { 'hold_changed' } else { 'already_moved' }; source_id=$action.source_id
        source_path=$action.source_path; relative_path=$action.relative_path; entry_type='file'; target_path=$action.target_path
        size_bytes=[int64]$action.size_bytes; last_write_utc=$action.last_write_utc; sha256=$action.sha256
        reason=if ($exists) { 'same_volume_move_source_reappeared' } else { 'source_removed_by_verified_move' }; state='planned'
    })
}

foreach ($source in @($settings.sources | Sort-Object { ([string]$_.id).ToLowerInvariant() })) {
    $sourceId = [string]$source.id
    $scan = Get-POSourceEntries -Root ([string]$source.path)
    foreach ($scanError in @($scan.Errors)) { $errors.Add([pscustomobject][ordered]@{ source_id=$sourceId; path=$scanError.path; stage=$scanError.stage; reason=$scanError.error }) }
    foreach ($entry in @($scan.Entries | Sort-Object { ([string]$_.relative_path).ToLowerInvariant() }, { [string]$_.relative_path })) {
        $sourcePath = [string]$entry.full_path
        $key = $sourcePath.ToLowerInvariant()
        $planned = if ($actionBySource.ContainsKey($key)) { $actionBySource[$key] } else { $null }
        $actionName=''; $target=''; $hash=''; $reason=''
        if ($entry.entry_type -eq 'directory') {
            if ($entry.is_name_surrogate -or $entry.is_cloud_placeholder) { $actionName='hold_changed'; $reason='unsupported_reparse_or_placeholder_directory' }
            elseif ($null -eq $planned) { $actionName='hold_unplanned'; $reason='directory_not_in_approved_inventory' }
            else { $actionName='remove_empty_directory'; $reason='remove_only_after_manifest_files_are_recycled' }
        }
        elseif ($entry.is_name_surrogate -or $entry.is_cloud_placeholder -or ([string]$entry.attributes -match 'Encrypted|SparseFile') -or
            [int]$entry.link_count -ne 1 -or [int]$entry.stream_count -ne 1) {
            $actionName='hold_changed'; $reason='unsupported_file_state'
        }
        elseif ($null -eq $planned) { $actionName='hold_unplanned'; $reason='file_not_in_approved_inventory' }
        else {
            $target=[string]$planned.target_path
            try { $hash=Get-POStableSha256 -Path $sourcePath }
            catch { $actionName='hold_changed'; $reason=$_.Exception.Message; $errors.Add([pscustomobject][ordered]@{ source_id=$sourceId; path=$sourcePath; stage='retirement_hash'; reason=$reason }) }
            if (-not $actionName) {
                switch ([string]$planned.action) {
                    'copy_file_verify' {
                        if ($hash -ne ([string]$planned.sha256).ToUpperInvariant() -or [int64]$entry.size_bytes -ne [int64]$planned.size_bytes -or
                            [string]$entry.last_write_utc -ne [string]$planned.last_write_utc) { $actionName='hold_changed'; $reason='source_changed_after_copy' }
                        elseif ((Get-POStableSha256 -Path $target) -ne $hash) { $actionName='hold_changed'; $reason='target_copy_not_verified' }
                        else { $actionName='recycle_verified_copy_source'; $reason='verified_cross_volume_copy' }
                    }
                    'skip_exact_duplicate' {
                        if ($hash -ne ([string]$planned.sha256).ToUpperInvariant()) { $actionName='hold_changed'; $reason='duplicate_source_changed' }
                        elseif ((Get-POStableSha256 -Path $target) -ne $hash) { $actionName='hold_changed'; $reason='selected_duplicate_target_changed' }
                        else { $actionName='recycle_exact_duplicate'; $reason='exact_sha256_duplicate' }
                    }
                    'skip_target_duplicate' {
                        if ($hash -ne ([string]$planned.sha256).ToUpperInvariant()) { $actionName='hold_changed'; $reason='duplicate_source_changed' }
                        elseif ((Get-POStableSha256 -Path $target) -ne $hash) { $actionName='hold_changed'; $reason='existing_target_duplicate_changed' }
                        else { $actionName='recycle_exact_duplicate'; $reason='target_already_has_exact_copy' }
                    }
                    'exclude_cache' {
                        $retireProperty = $settings.exclude_rules.PSObject.Properties['retire_excluded']
                        if ($null -ne $retireProperty -and [bool]$retireProperty.Value) { $actionName='recycle_cache'; $reason='explicit_cache_rule' }
                        else { $actionName='hold_unplanned'; $reason='excluded_item_retirement_not_enabled' }
                    }
                    'preserve_git_metadata' {
                        $archive = @($gitArchives | Where-Object { [string]$_.source_id -eq $sourceId })
                        if ($archive.Count -ne 1) { $actionName='hold_changed'; $reason='verified_git_bundle_missing' }
                        elseif (@($executionState.active_git).Count -eq 0 -and [string]$settings.active_repo_policy -notin @('new','target_existing')) { $actionName='hold_changed'; $reason='active_git_recovery_missing' }
                        else { $actionName='recycle_git_metadata'; $reason='verified_bundle_and_active_git_recovery' }
                    }
                    'move_file_verify' { $actionName='hold_changed'; $reason='moved_source_reappeared' }
                    default { $actionName='hold_unplanned'; $reason="unsupported_prior_action_$($planned.action)" }
                }
            }
        }
        $retirement.Add([pscustomobject][ordered]@{
            retirement_id=''; action=$actionName; source_id=$sourceId; source_path=$sourcePath; relative_path=$entry.relative_path
            entry_type=$entry.entry_type; target_path=$target; size_bytes=[int64]$entry.size_bytes; last_write_utc=$entry.last_write_utc
            sha256=$hash; reason=$reason; state='planned'
        })
    }
    $retirement.Add([pscustomobject][ordered]@{
        retirement_id=''; action='remove_empty_directory'; source_id=$sourceId; source_path=[string]$source.path; relative_path=''
        entry_type='directory'; target_path=''; size_bytes=[int64]0; last_write_utc=''; sha256=''; reason='remove_source_root_only_when_empty'; state='planned'
    })
}

$retirementPriority = @{ already_moved=5; recycle_verified_copy_source=10; recycle_exact_duplicate=10; recycle_cache=10; recycle_git_metadata=10; remove_empty_directory=50; hold_changed=90; hold_unplanned=90 }
$rows = @($retirement.ToArray() | Sort-Object { $retirementPriority[[string]$_.action] }, {
    if ([string]$_.entry_type -eq 'directory') { -([string]$_.source_path).Length } else { 0 }
}, { ([string]$_.source_path).ToLowerInvariant() }, { [string]$_.source_path })
for ($index=0; $index -lt $rows.Count; $index++) { $rows[$index].retirement_id=('R{0:D8}' -f ($index+1)) }
$errorRows = @($errors.ToArray() | Sort-Object { $_.source_id.ToLowerInvariant() }, { $_.path.ToLowerInvariant() }, { $_.stage })
$retirementPath = Join-Path $output 'retirement.csv'
$retirementErrorsPath = Join-Path $output 'retirement-errors.csv'
Write-POCsv -Path $retirementPath -Rows $rows -Columns @(
    'retirement_id','action','source_id','source_path','relative_path','entry_type','target_path','size_bytes','last_write_utc','sha256','reason','state'
)
Write-POCsv -Path $retirementErrorsPath -Rows $errorRows -Columns @('source_id','path','stage','reason')
$groups = @{}; foreach ($group in @($rows | Group-Object action)) { $groups[$group.Name]=$group.Count }
$review = @(
    '# 旧路径退役清单审查','',
    "- 已移动：$([int]$groups['already_moved'])",
    "- 已验证复制源：$([int]$groups['recycle_verified_copy_source'])",
    "- 完全重复：$([int]$groups['recycle_exact_duplicate'])",
    "- 缓存：$([int]$groups['recycle_cache'])",
    "- Git 元数据：$([int]$groups['recycle_git_metadata'])",
    "- 空目录：$([int]$groups['remove_empty_directory'])",
    "- hold_changed：$([int]$groups['hold_changed'])",
    "- hold_unplanned：$([int]$groups['hold_unplanned'])",
    "- errors：$($errorRows.Count)",'',
    '批准后只把本清单列出的文件移入回收站；不会清空整个回收站。',''
)
Write-POText -Path (Join-Path $output 'retirement-review.md') -Text (($review -join "`n") + "`n")
$bound = @($configPath,$planHashPath,$acceptancePath,$retirementPath,$retirementErrorsPath)
if (Test-Path -LiteralPath $gitArchivesPath) { $bound += $gitArchivesPath }
$retirementManifest = Join-Path $output 'retirement-files.sha256'
[void](New-POHashManifest -Paths $bound -OutputPath $retirementManifest)
$retirementHash = Get-POStableSha256 -Path $retirementManifest
Write-POText -Path (Join-Path $output 'retirement.sha256') -Text ($retirementHash + "`n")
Write-Output "Retirement SHA256: $retirementHash"
Write-Output "Errors: $($errorRows.Count); hold: $(@($rows | Where-Object { $_.action -like 'hold_*' }).Count)"
