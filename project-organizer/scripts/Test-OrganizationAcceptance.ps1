[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Config,
    [Parameter(Mandatory = $true)][string]$OutputDir
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'ProjectOrganizer.psm1') -Force

$settings = Read-POConfig -Path $Config -RequireSources -ForExecution
$output = Resolve-POFullPath -Path $OutputDir
$planHash = (Get-Content -LiteralPath (Join-Path $output 'plan.sha256') -Encoding UTF8 -Raw).Trim().ToUpperInvariant()
$manifest = Join-Path $output 'plan-files.sha256'
if ((Get-POStableSha256 -Path $manifest) -ne $planHash) { throw 'Plan hash changed before acceptance.' }
$manifestCheck = Test-POHashManifest -ManifestPath $manifest
if (-not $manifestCheck.Valid) { throw "Plan files changed before acceptance: $($manifestCheck.Errors -join '; ')" }
$state = Get-Content -LiteralPath (Join-Path $output 'execution-state.json') -Encoding UTF8 -Raw | ConvertFrom-Json
if (-not $state.complete -or [string]$state.plan_sha256 -ne $planHash) { throw 'Execution is incomplete or belongs to another plan.' }
$actions = @(Import-Csv -LiteralPath (Join-Path $output 'actions.csv') -Encoding UTF8)

$checks = New-Object Collections.Generic.List[object]
$errors = New-Object Collections.Generic.List[object]
foreach ($action in $actions) {
    $passed = $true
    $evidence = ''
    try {
        switch ([string]$action.action) {
            'create_directory' {
                $passed = [IO.Directory]::Exists((ConvertTo-POExtendedPath ([string]$action.target_path)))
                $evidence = if ($passed) { 'target_directory_exists' } else { 'target_directory_missing' }
            }
            'move_file_verify' {
                if ([IO.File]::Exists((ConvertTo-POExtendedPath ([string]$action.source_path)))) { throw 'source_still_exists_after_move' }
                if ((Get-POStableSha256 -Path ([string]$action.target_path)) -ne ([string]$action.sha256).ToUpperInvariant()) { throw 'target_hash_mismatch' }
                $evidence='source_absent_target_hash_verified'
            }
            'copy_file_verify' {
                [void](Assert-POExpectedFile -Path ([string]$action.source_path) -SizeBytes ([int64]$action.size_bytes) -LastWriteUtc ([string]$action.last_write_utc) -Sha256 ([string]$action.sha256))
                if ((Get-POStableSha256 -Path ([string]$action.target_path)) -ne ([string]$action.sha256).ToUpperInvariant()) { throw 'target_hash_mismatch' }
                $evidence='source_and_target_hash_verified'
            }
            'skip_exact_duplicate' {
                [void](Assert-POExpectedFile -Path ([string]$action.source_path) -SizeBytes ([int64]$action.size_bytes) -LastWriteUtc ([string]$action.last_write_utc) -Sha256 ([string]$action.sha256))
                if ((Get-POStableSha256 -Path ([string]$action.target_path)) -ne ([string]$action.sha256).ToUpperInvariant()) { throw 'duplicate_target_hash_mismatch' }
                $evidence='duplicate_source_and_selected_target_verified'
            }
            'skip_target_duplicate' {
                [void](Assert-POExpectedFile -Path ([string]$action.source_path) -SizeBytes ([int64]$action.size_bytes) -LastWriteUtc ([string]$action.last_write_utc) -Sha256 ([string]$action.sha256))
                if ((Get-POStableSha256 -Path ([string]$action.target_path)) -ne ([string]$action.sha256).ToUpperInvariant()) { throw 'existing_target_hash_mismatch' }
                $evidence='source_and_existing_target_verified'
            }
            'exclude_cache' {
                $passed = ([IO.File]::Exists((ConvertTo-POExtendedPath ([string]$action.source_path))) -or [IO.Directory]::Exists((ConvertTo-POExtendedPath ([string]$action.source_path))))
                $evidence=if ($passed) { 'excluded_source_retained' } else { 'excluded_source_missing' }
            }
            'preserve_git_metadata' {
                $passed = ([IO.File]::Exists((ConvertTo-POExtendedPath ([string]$action.source_path))) -or [IO.Directory]::Exists((ConvertTo-POExtendedPath ([string]$action.source_path))))
                $evidence=if ($passed) { 'source_git_metadata_retained' } else { 'source_git_metadata_missing' }
            }
            default { throw "unexpected_action_$($action.action)" }
        }
    }
    catch { $passed=$false; $evidence=$_.Exception.Message }
    $checks.Add([pscustomobject][ordered]@{ check_type='action'; item=$action.action_id; passed=$passed; evidence=$evidence })
    if (-not $passed) { $errors.Add([pscustomobject][ordered]@{ item=$action.action_id; stage='action_acceptance'; reason=$evidence }) }
}

$completedIds = @($state.completed_action_ids | Sort-Object -Unique)
$plannedIds = @($actions.action_id | Sort-Object -Unique)
$conservation = ($completedIds.Count -eq $plannedIds.Count -and (@(Compare-Object $plannedIds $completedIds).Count -eq 0))
$checks.Add([pscustomobject][ordered]@{ check_type='conservation'; item='action_ids'; passed=$conservation; evidence="planned=$($plannedIds.Count);completed=$($completedIds.Count)" })
if (-not $conservation) { $errors.Add([pscustomobject][ordered]@{ item='action_ids'; stage='conservation'; reason='planned_and_completed_actions_differ' }) }

foreach ($gitRecord in @($state.active_git)) {
    $passed=$true; $evidence=''
    try {
        $git = Get-POGitState -Repository ([string]$gitRecord.worktree)
        if ($null -eq $git) { throw 'active_git_unreadable' }
        if ([string]$git.git_dir -ne [string]$gitRecord.git_dir) { throw 'active_git_dir_changed' }
        if ([string]$gitRecord.head -and [string]$git.head -ne [string]$gitRecord.head) { throw 'active_git_head_changed' }
        if ($gitRecord.externalized -and (Test-POSyncPath -Path ([string]$git.git_dir) -SyncRoots $settings.sync_roots)) { throw 'active_git_inside_sync_root' }
        [void](Invoke-POGit -Repository ([string]$gitRecord.worktree) -Arguments @('fsck','--full'))
        $evidence='git_dir_head_and_fsck_verified'
    }
    catch { $passed=$false; $evidence=$_.Exception.Message }
    $checks.Add([pscustomobject][ordered]@{ check_type='active_git'; item=$gitRecord.source_id; passed=$passed; evidence=$evidence })
    if (-not $passed) { $errors.Add([pscustomobject][ordered]@{ item=$gitRecord.source_id; stage='active_git'; reason=$evidence }) }
}

$treePassed=$true;$treeEvidence=''
try{
    $treePath=Join-Path $output 'target-tree.csv';$treeHashPath=Join-Path $output 'target-tree.sha256'
    $treeHash=(Get-Content -LiteralPath $treeHashPath -Encoding UTF8 -Raw).Trim().ToUpperInvariant()
    if((Get-POStableSha256 -Path $treePath) -ne $treeHash){throw 'approved_target_tree_hash_changed'}
    if([string]$settings.mode -eq 'merge' -and ([string]$settings.layout_decisions.approved_tree_sha256).ToUpperInvariant() -ne $treeHash){throw 'approved_target_tree_no_longer_matches_config'}
    $expectedRows=@(Import-Csv -LiteralPath $treePath -Encoding UTF8)
    if(@($expectedRows|Where-Object{[string]$_.state -like 'hold*'}).Count -gt 0){throw 'approved_target_tree_contains_hold_entries'}
    $expected=@{};foreach($row in $expectedRows){$expected[([string]$row.relative_path).ToLowerInvariant()]=$row}
    $actualScan=Get-POSourceEntries -Root $settings.target_root
    foreach($scanError in @($actualScan.Errors)){$errors.Add([pscustomobject][ordered]@{item=$scanError.path;stage='target_tree_scan';reason=$scanError.error});$treePassed=$false}
    $actual=@{}
    foreach($entry in @($actualScan.Entries)){
        $relative=[string]$entry.relative_path
        if(Test-POGitMetadataPath -RelativePath $relative){continue}
        if($entry.is_name_surrogate -or $entry.is_cloud_placeholder -or [string]$entry.reparse_tag -ne '0x00000000'){
            $errors.Add([pscustomobject][ordered]@{item=$relative;stage='target_tree';reason='unsupported_actual_entry'});$treePassed=$false;continue
        }
        $hash=''
        if([string]$entry.entry_type -eq 'file'){$hash=Get-POStableSha256 -Path $entry.full_path}
        $actual[$relative.ToLowerInvariant()]=[pscustomobject]@{relative_path=$relative;entry_type=$entry.entry_type;sha256=$hash}
    }
    foreach($key in $expected.Keys){
        if(-not $actual.ContainsKey($key)){$errors.Add([pscustomobject][ordered]@{item=$expected[$key].relative_path;stage='target_tree';reason='approved_path_missing'});$treePassed=$false;continue}
        if([string]$actual[$key].entry_type -ne [string]$expected[$key].entry_type){$errors.Add([pscustomobject][ordered]@{item=$expected[$key].relative_path;stage='target_tree';reason='approved_path_type_mismatch'});$treePassed=$false;continue}
        if([string]$expected[$key].entry_type -eq 'file' -and [string]$expected[$key].sha256 -and [string]$actual[$key].sha256 -ne ([string]$expected[$key].sha256).ToUpperInvariant()){
            $errors.Add([pscustomobject][ordered]@{item=$expected[$key].relative_path;stage='target_tree';reason='approved_file_hash_mismatch'});$treePassed=$false
        }
    }
    foreach($key in $actual.Keys){if(-not $expected.ContainsKey($key)){$errors.Add([pscustomobject][ordered]@{item=$actual[$key].relative_path;stage='target_tree';reason='unapproved_extra_path'});$treePassed=$false}}
    if([string]$settings.mode -eq 'merge'){
        foreach($value in @($settings.layout_decisions.forbidden_target_paths)){
            $prefix=(ConvertTo-PORelativePath ([string]$value)).ToLowerInvariant()
            if(@($actual.Keys|Where-Object{$_ -eq $prefix -or $_.StartsWith($prefix+'/')}).Count -gt 0){
                $errors.Add([pscustomobject][ordered]@{item=$value;stage='target_tree';reason='forbidden_wrapper_or_directory_present'});$treePassed=$false
            }
        }
    }
    $treeEvidence="expected=$($expected.Count);actual=$($actual.Count);sha256=$treeHash"
}
catch{$treePassed=$false;$treeEvidence=$_.Exception.Message;$errors.Add([pscustomobject][ordered]@{item='target-tree';stage='target_tree';reason=$treeEvidence})}
$checks.Add([pscustomobject][ordered]@{check_type='target_tree';item='approved_layout';passed=$treePassed;evidence=$treeEvidence})

$checkRows = @($checks.ToArray())
$errorRows = @($errors.ToArray())
$accepted = ($errorRows.Count -eq 0 -and @($checkRows | Where-Object { -not $_.passed }).Count -eq 0)
$result = [ordered]@{
    schema_version='1.0'; plan_sha256=$planHash; accepted=$accepted
    planned_actions=$actions.Count; completed_actions=$completedIds.Count; checks=$checkRows; errors=$errorRows
}
Write-POJson -Path (Join-Path $output 'organization-acceptance.json') -Value $result
Write-POCsv -Path (Join-Path $output 'acceptance-errors.csv') -Rows $errorRows -Columns @('item','stage','reason')
$report = @(
    '# 迁移验收','',
    "- 结论：$(if ($accepted) { '通过' } else { '失败' })",
    "- 计划动作：$($actions.Count)",
    "- 完成动作：$($completedIds.Count)",
    "- 检查：$($checkRows.Count)",
    "- 错误：$($errorRows.Count)",'',
    '通过只表示新目标和现役 Git 已验收，不代表旧路径获准退役。',''
)
Write-POText -Path (Join-Path $output 'acceptance.md') -Text (($report -join "`n") + "`n")
if (-not $accepted) { throw "Organization acceptance failed with $($errorRows.Count) error(s)." }
Write-Output 'Organization acceptance passed.'
