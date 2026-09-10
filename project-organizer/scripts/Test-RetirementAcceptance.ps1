[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Config,
    [Parameter(Mandatory = $true)][string]$OutputDir
)

Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
Import-Module (Join-Path $PSScriptRoot 'ProjectOrganizer.psm1') -Force

$settings=Read-POConfig -Path $Config -RequireSources -ForExecution -AllowMissingSources
$output=Resolve-POFullPath -Path $OutputDir
Assert-POAuditPath -Config $settings -OutputDir $output
$integration=Read-POIntegrationManifest -Config $settings
if($null -ne $integration){[void](Assert-POIntegrationFiles -Integration $integration -Phase Retired -RequireChecks -OutputDir $output)}
$retirementHash=(Get-Content -LiteralPath (Join-Path $output 'retirement.sha256') -Encoding UTF8 -Raw).Trim().ToUpperInvariant()
$manifest=Join-Path $output 'retirement-files.sha256'
if((Get-POStableSha256 -Path $manifest) -ne $retirementHash){throw 'Retirement hash changed before final acceptance.'}
$manifestCheck=Test-POHashManifest -ManifestPath $manifest
if(-not $manifestCheck.Valid){throw "Retirement files changed before final acceptance: $($manifestCheck.Errors -join '; ')"}
$state=Get-Content -LiteralPath (Join-Path $output 'retirement-execution-state.json') -Encoding UTF8 -Raw|ConvertFrom-Json
if(-not $state.complete -or [string]$state.retirement_sha256 -ne $retirementHash){throw 'Retirement execution is incomplete or belongs to another plan.'}
$rows=@(Import-Csv -LiteralPath (Join-Path $output 'retirement.csv') -Encoding UTF8)
$actions=@(Import-Csv -LiteralPath (Join-Path $output 'actions.csv') -Encoding UTF8)
$executionState=Get-Content -LiteralPath (Join-Path $output 'execution-state.json') -Encoding UTF8 -Raw|ConvertFrom-Json
$checks=New-Object Collections.Generic.List[object]
$errors=New-Object Collections.Generic.List[object]

$plannedIds=@($rows.retirement_id|Sort-Object -Unique)
$completedIds=@($state.completed_retirement_ids|Sort-Object -Unique)
$conservation=($plannedIds.Count -eq $completedIds.Count -and @(Compare-Object $plannedIds $completedIds).Count -eq 0)
$checks.Add([pscustomobject][ordered]@{check='retirement_action_conservation';item='retirement_ids';passed=$conservation;evidence="planned=$($plannedIds.Count);completed=$($completedIds.Count)"})
if(-not $conservation){$errors.Add([pscustomobject][ordered]@{item='retirement_ids';stage='conservation';reason='planned_and_completed_differ'})}

foreach($source in @($settings.sources)){
    $absent=(-not [IO.File]::Exists((ConvertTo-POExtendedPath ([string]$source.path))) -and -not [IO.Directory]::Exists((ConvertTo-POExtendedPath ([string]$source.path))))
    $checks.Add([pscustomobject][ordered]@{check='source_retired';item=[string]$source.id;passed=$absent;evidence=if($absent){'source_path_absent'}else{'source_path_still_exists'}})
    if(-not $absent){$errors.Add([pscustomobject][ordered]@{item=[string]$source.path;stage='source_retired';reason='source_path_still_exists'})}
}

foreach($action in @($actions|Where-Object{$_.action -in @('move_file_verify','copy_file_verify','skip_exact_duplicate','skip_target_duplicate','install_integrated_file')})){
    $passed=$true;$evidence='target_hash_verified'
    try{if((Get-POStableSha256 -Path ([string]$action.target_path)) -ne ([string]$action.sha256).ToUpperInvariant()){throw 'target_hash_mismatch'}}catch{$passed=$false;$evidence=$_.Exception.Message}
    $checks.Add([pscustomobject][ordered]@{check='target_file';item=[string]$action.action_id;passed=$passed;evidence=$evidence})
    if(-not $passed){$errors.Add([pscustomobject][ordered]@{item=[string]$action.target_path;stage='target_file';reason=$evidence})}
}

if([string]$settings.schema_version -eq '1.1'){
    $treePassed=$true;$treeEvidence='final_tree_verified'
    try{
        $expected=@{}
        foreach($entry in @(Import-Csv -LiteralPath (Join-Path $output 'target-tree.csv') -Encoding UTF8)){
            $expected[([string]$entry.relative_path).ToLowerInvariant()]=$entry
        }
        $scan=Get-POSourceEntries -Root $settings.target_root -ExcludeRoot $settings.audit_root
        if(@($scan.Errors).Count){throw 'final_target_scan_failed'}
        $seen=@{}
        foreach($entry in @($scan.Entries)){
            if(Test-POGitMetadataPath -RelativePath ([string]$entry.relative_path)){continue}
            $key=([string]$entry.relative_path).ToLowerInvariant()
            if(-not $expected.ContainsKey($key)){throw "unplanned_final_path: $key"}
            if($entry.is_name_surrogate -or $entry.is_cloud_placeholder -or [string]$entry.reparse_tag -ne '0x00000000'){throw "unsupported_final_path: $key"}
            if([string]$entry.entry_type -ne [string]$expected[$key].entry_type){throw "final_path_type_changed: $key"}
            if([string]$entry.entry_type -eq 'file' -and (Get-POStableSha256 -Path $entry.full_path) -ne ([string]$expected[$key].sha256).ToUpperInvariant()){throw "final_file_changed: $key"}
            $seen[$key]=$true
        }
        foreach($key in $expected.Keys){if(-not $seen.ContainsKey($key)){throw "final_path_missing: $key"}}
    }catch{$treePassed=$false;$treeEvidence=$_.Exception.Message;$errors.Add([pscustomobject][ordered]@{item='target-tree';stage='final_tree';reason=$treeEvidence})}
    $checks.Add([pscustomobject][ordered]@{check='final_tree';item='target-tree';passed=$treePassed;evidence=$treeEvidence})
}

foreach($gitRecord in @($executionState.active_git)){
    $passed=$true;$evidence='active_git_readable'
    try{
        $git=Get-POGitState -Repository ([string]$gitRecord.worktree)
        if($null -eq $git){throw 'active_git_unreadable'}
        if([string]$gitRecord.head -and [string]$git.head -ne [string]$gitRecord.head){throw 'active_git_head_changed'}
        [void](Invoke-POGit -Repository ([string]$gitRecord.worktree) -Arguments @('fsck','--full'))
    }catch{$passed=$false;$evidence=$_.Exception.Message}
    $checks.Add([pscustomobject][ordered]@{check='active_git';item=[string]$gitRecord.source_id;passed=$passed;evidence=$evidence})
    if(-not $passed){$errors.Add([pscustomobject][ordered]@{item=[string]$gitRecord.source_id;stage='active_git';reason=$evidence})}
}

$gitArchivesPath=Join-Path $output 'git_archives.json'
if(Test-Path -LiteralPath $gitArchivesPath){
    foreach($archive in @(Read-POJsonArray -Path $gitArchivesPath)){
        $passed=$true;$evidence='bundle_hash_and_heads_readable'
        try{
            if((Get-POStableSha256 -Path ([string]$archive.bundle_path)) -ne ([string]$archive.bundle_sha256).ToUpperInvariant()){throw 'bundle_hash_mismatch'}
            $bundleOutput=@(& git --no-optional-locks bundle list-heads ([string]$archive.bundle_path) 2>&1)
            if($LASTEXITCODE -ne 0){throw "bundle_list_heads_failed: $($bundleOutput -join ' ')"}
        }catch{$passed=$false;$evidence=$_.Exception.Message}
        $checks.Add([pscustomobject][ordered]@{check='git_bundle';item=[string]$archive.source_id;passed=$passed;evidence=$evidence})
        if(-not $passed){$errors.Add([pscustomobject][ordered]@{item=[string]$archive.bundle_path;stage='git_bundle';reason=$evidence})}
    }
}

$checkRows=@($checks.ToArray());$errorRows=@($errors.ToArray())
$accepted=($errorRows.Count -eq 0 -and @($checkRows|Where-Object{-not $_.passed}).Count -eq 0)
$result=[ordered]@{
    schema_version='1.0';retirement_sha256=$retirementHash;accepted=$accepted
    checks=$checkRows;errors=$errorRows;target_free_bytes=(Get-PODriveFreeSpace -Path $settings.target_root)
    recycle_bin_emptied_by_tool=$false;manual_empty_confirmation_required=$false
}
Write-POJson -Path (Join-Path $output 'final-acceptance.json') -Value $result
Write-POCsv -Path (Join-Path $output 'final-acceptance-errors.csv') -Rows $errorRows -Columns @('item','stage','reason')
$report=@(
    '# 最终退役验收','',
    "- 结论：$(if($accepted){'通过'}else{'失败'})",
    "- 检查：$($checkRows.Count)",
    "- 错误：$($errorRows.Count)",
    "- 目标盘当前可用字节：$($result.target_free_bytes)",'',
    '旧入口退役与目标使用检查完成即可交付；无需清空回收站或等待用户最终签字。',''
)
Write-POText -Path (Join-Path $output 'final-acceptance.md') -Text (($report -join "`n")+"`n")
if(-not $accepted){throw "Final retirement acceptance failed with $($errorRows.Count) error(s)."}
Write-Output 'Final retirement acceptance passed. Recycle Bin was not emptied by this tool.'
