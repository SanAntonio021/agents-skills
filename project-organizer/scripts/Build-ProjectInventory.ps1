[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Config,
    [Parameter(Mandatory = $true)][string]$OutputDir,
    [switch]$Resume
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'ProjectOrganizer.psm1') -Force

$settings = Read-POConfig -Path $Config -RequireSources
$configPath = Resolve-POFullPath -Path $Config -AllowNetwork
$output = Resolve-POFullPath -Path $OutputDir -AllowMissing
[void][IO.Directory]::CreateDirectory((ConvertTo-POExtendedPath $output))
$previous = @{}
$previousPath = Join-Path $output 'files.csv'
if ($Resume -and (Test-Path -LiteralPath $previousPath)) {
    foreach ($row in @(Import-Csv -LiteralPath $previousPath -Encoding UTF8)) {
        $key = ([string]$row.source_id).ToLowerInvariant() + '|' + ([string]$row.relative_path).ToLowerInvariant()
        $previous[$key] = $row
    }
}

$fileRows = New-Object Collections.Generic.List[object]
$errorRows = New-Object Collections.Generic.List[object]
$sourceStates = New-Object Collections.Generic.List[object]
$gitStates = New-Object Collections.Generic.List[object]
$targetRows = New-Object Collections.Generic.List[object]
$layoutViolationRows = New-Object Collections.Generic.List[object]

foreach ($source in @($settings.sources | Sort-Object { ([string]$_.id).ToLowerInvariant() }, { [string]$_.id })) {
    $sourceId = [string]$source.id
    $root = [string]$source.path
    $scan = Get-POSourceEntries -Root $root
    $beforeFiles = @($scan.Entries | Where-Object { $_.entry_type -eq 'file' })
    $before = [ordered]@{
        file_count=[int64]$beforeFiles.Count
        directory_count=[int64]@($scan.Entries | Where-Object { $_.entry_type -eq 'directory' }).Count
        total_bytes=[int64](($beforeFiles | Measure-Object -Property size_bytes -Sum).Sum)
        error_count=[int64]$scan.Errors.Count
    }
    foreach ($scanError in @($scan.Errors)) {
        $errorRows.Add([pscustomobject][ordered]@{ source_id=$sourceId; path=$scanError.path; stage=$scanError.stage; reason=$scanError.error })
    }

    foreach ($entry in @($scan.Entries | Sort-Object { ([string]$_.relative_path).ToLowerInvariant() }, { [string]$_.relative_path })) {
        $relative = [string]$entry.relative_path
        $proposed = Get-POProposedRelativePath -Config $settings -Source $source -RelativePath $relative
        $target = Join-POPath -Root $settings.target_root -RelativePath $proposed
        $status = if ($entry.entry_type -eq 'directory') { 'directory' } else { 'pending_hash' }
        $reason = ''
        $hash = ''
        $targetStatus = 'absent'

        if ($entry.entry_type -eq 'directory') {
            if ($entry.is_name_surrogate) { $status='hold'; $reason='name_surrogate_reparse_point' }
            elseif ($entry.is_cloud_placeholder) { $status='hold'; $reason='cloud_placeholder_directory' }
            elseif ([string]$entry.reparse_tag -ne '0x00000000') { $status='hold'; $reason='unsupported_reparse_point' }
            elseif (Test-POGitMetadataPath -RelativePath $relative) { $status='preserve_git_metadata'; $reason='git_metadata' }
            elseif (Test-POExcludedPath -RelativePath $relative -Rules $settings.exclude_rules) { $status='excluded'; $reason='explicit_exclude_rule' }
            $targetStatus = if ([IO.Directory]::Exists((ConvertTo-POExtendedPath $target))) { 'directory_exists' }
                elseif ([IO.File]::Exists((ConvertTo-POExtendedPath $target))) { 'target_type_conflict' } else { 'absent' }
        }
        elseif (Test-POGitMetadataPath -RelativePath $relative) { $status='preserve_git_metadata'; $reason='git_metadata' }
        elseif (Test-POExcludedPath -RelativePath $relative -Rules $settings.exclude_rules) { $status='excluded'; $reason='explicit_exclude_rule' }
        elseif ($entry.is_name_surrogate) { $status='hold'; $reason='name_surrogate_reparse_point' }
        elseif ($entry.is_cloud_placeholder) { $status='hold'; $reason='cloud_placeholder_file' }
        elseif ([string]$entry.reparse_tag -ne '0x00000000') { $status='hold'; $reason='unsupported_reparse_point' }
        elseif (([string]$entry.attributes -match 'Encrypted|SparseFile')) { $status='hold'; $reason='encrypted_or_sparse_file' }
        elseif ([int]$entry.link_count -ne 1) { $status='hold'; $reason='unknown_or_multiple_hard_links' }
        elseif ([int]$entry.stream_count -ne 1) { $status='hold'; $reason='unknown_or_extra_data_streams' }
        elseif ($target.Length -ge 32760) { $status='hold'; $reason='target_path_too_long' }
        else {
            try {
                $key = $sourceId.ToLowerInvariant() + '|' + $relative.ToLowerInvariant()
                $old = if ($previous.ContainsKey($key)) { $previous[$key] } else { $null }
                if ($null -ne $old -and [string]$old.size_bytes -eq [string]$entry.size_bytes -and
                    [string]$old.last_write_utc -eq [string]$entry.last_write_utc -and [string]$old.sha256 -match '^[0-9A-Fa-f]{64}$') {
                    $hash = ([string]$old.sha256).ToUpperInvariant()
                }
                else { $hash = Get-POStableSha256 -Path $entry.full_path }
                $status = 'stable'
                if ([IO.Directory]::Exists((ConvertTo-POExtendedPath $target))) {
                    $targetStatus='target_type_conflict'; $status='hold'; $reason='target_is_directory'
                }
                elseif ([IO.File]::Exists((ConvertTo-POExtendedPath $target))) {
                    $targetHash = Get-POStableSha256 -Path $target
                    if ($targetHash -eq $hash) { $targetStatus='exact_duplicate'; $status='target_duplicate'; $reason='target_sha256_matches' }
                    else { $targetStatus='hash_conflict'; $status='hold'; $reason='target_sha256_differs' }
                }
            }
            catch {
                $status='error'; $reason=$_.Exception.Message; $hash=''
                $errorRows.Add([pscustomobject][ordered]@{ source_id=$sourceId; path=$entry.full_path; stage='hash'; reason=$reason })
            }
        }

        $fileRows.Add([pscustomobject][ordered]@{
            source_id=$sourceId; source_root=$root; relative_path=$relative; entry_type=$entry.entry_type
            size_bytes=[int64]$entry.size_bytes; last_write_utc=$entry.last_write_utc; attributes=$entry.attributes
            reparse_tag=$entry.reparse_tag; link_count=[int]$entry.link_count; sha256=$hash; scan_status=$status; reason=$reason
            proposed_relative_path=$proposed; proposed_target_path=$target; target_status=$targetStatus
        })
    }

    try {
        $git = Get-POGitState -Repository $root
        if ($null -ne $git) {
            $git | Add-Member -NotePropertyName source_id -NotePropertyValue $sourceId
            $gitStates.Add($git)
        }
    }
    catch { $errorRows.Add([pscustomobject][ordered]@{ source_id=$sourceId; path=$root; stage='git_state'; reason=$_.Exception.Message }) }

    $after = Get-POFileSnapshot -Root $root
    $changed = ($before.file_count -ne $after.file_count -or $before.directory_count -ne $after.directory_count -or
        $before.total_bytes -ne $after.total_bytes -or $before.error_count -ne $after.error_count)
    if ($changed) { $errorRows.Add([pscustomobject][ordered]@{ source_id=$sourceId; path=$root; stage='source_state'; reason='source_changed_during_inventory' }) }
    $sourceStates.Add([pscustomobject][ordered]@{ source_id=$sourceId; source_root=$root; before=[pscustomobject]$before; after=$after; changed=$changed })
}

$targetState = [ordered]@{ target_root=$settings.target_root; exists=$false; before=$null; after=$null; changed=$false }
if ([IO.Directory]::Exists((ConvertTo-POExtendedPath $settings.target_root))) {
    $targetState.exists = $true
    $targetScan = Get-POSourceEntries -Root $settings.target_root
    $targetFiles = @($targetScan.Entries | Where-Object entry_type -eq 'file')
    $targetBefore = [ordered]@{
        file_count=[int64]$targetFiles.Count
        directory_count=[int64]@($targetScan.Entries | Where-Object entry_type -eq 'directory').Count
        total_bytes=[int64](($targetFiles | Measure-Object size_bytes -Sum).Sum)
        error_count=[int64]$targetScan.Errors.Count
    }
    $targetState.before = [pscustomobject]$targetBefore
    foreach ($scanError in @($targetScan.Errors)) {
        $errorRows.Add([pscustomobject][ordered]@{ source_id='__target__'; path=$scanError.path; stage=$scanError.stage; reason=$scanError.error })
    }
    foreach ($entry in @($targetScan.Entries | Sort-Object { ([string]$_.relative_path).ToLowerInvariant() }, { [string]$_.relative_path })) {
        $relative=[string]$entry.relative_path
        if (Test-POGitMetadataPath -RelativePath $relative) { continue }
        $status='stable';$reason='';$hash=''
        if ($entry.is_name_surrogate) { $status='hold';$reason='name_surrogate_reparse_point' }
        elseif ($entry.is_cloud_placeholder) { $status='hold';$reason='cloud_placeholder' }
        elseif ([string]$entry.reparse_tag -ne '0x00000000') { $status='hold';$reason='unsupported_reparse_point' }
        elseif ([string]$entry.entry_type -eq 'file' -and ([string]$entry.attributes -match 'Encrypted|SparseFile')) { $status='hold';$reason='encrypted_or_sparse_file' }
        elseif ([string]$entry.entry_type -eq 'file' -and [int]$entry.link_count -ne 1) { $status='hold';$reason='unknown_or_multiple_hard_links' }
        elseif ([string]$entry.entry_type -eq 'file' -and [int]$entry.stream_count -ne 1) { $status='hold';$reason='unknown_or_extra_data_streams' }
        elseif ([string]$entry.entry_type -eq 'file') {
            try { $hash=Get-POStableSha256 -Path $entry.full_path }
            catch { $status='error';$reason=$_.Exception.Message;$errorRows.Add([pscustomobject][ordered]@{ source_id='__target__'; path=$entry.full_path; stage='target_hash'; reason=$reason }) }
        }
        $targetRows.Add([pscustomobject][ordered]@{
            relative_path=$relative;entry_type=$entry.entry_type;size_bytes=[int64]$entry.size_bytes
            last_write_utc=$entry.last_write_utc;sha256=$hash;scan_status=$status;reason=$reason
        })
    }
    $targetAfter=Get-POFileSnapshot -Root $settings.target_root
    $targetState.after=$targetAfter
    $targetState.changed=($targetBefore.file_count -ne $targetAfter.file_count -or $targetBefore.directory_count -ne $targetAfter.directory_count -or
        $targetBefore.total_bytes -ne $targetAfter.total_bytes -or $targetBefore.error_count -ne $targetAfter.error_count)
    if($targetState.changed){$errorRows.Add([pscustomobject][ordered]@{source_id='__target__';path=$settings.target_root;stage='target_state';reason='target_changed_during_inventory'})}
}

$files = @($fileRows.ToArray() | Sort-Object { $_.source_id.ToLowerInvariant() }, { $_.relative_path.ToLowerInvariant() }, { $_.relative_path })
$duplicateRows = New-Object Collections.Generic.List[object]
$duplicateIndex = 0
foreach ($group in @($files | Where-Object { $_.entry_type -eq 'file' -and $_.sha256 -match '^[0-9A-F]{64}$' } | Group-Object sha256 | Where-Object Count -gt 1 | Sort-Object Name)) {
    $duplicateIndex++
    $members = @($group.Group | Sort-Object {
        if ([string]$settings.mode -eq 'merge' -and [string]$_.source_id -eq [string]$settings.canonical_source_id) { 0 } else { 1 }
    }, { $_.proposed_target_path.ToLowerInvariant() }, { $_.source_id.ToLowerInvariant() }, { $_.relative_path.ToLowerInvariant() })
    $selectedTarget = if ([string]$settings.mode -eq 'merge') { [string]$members[0].proposed_target_path } else { '' }
    foreach ($member in $members) {
        $duplicateRows.Add([pscustomobject][ordered]@{
            duplicate_group_id=('D{0:D6}' -f $duplicateIndex); sha256=$group.Name; source_id=$member.source_id
            relative_path=$member.relative_path; proposed_target_path=$member.proposed_target_path
            selected_target_path=$selectedTarget; selected=([string]$settings.mode -eq 'merge' -and $member -eq $members[0])
            dedup_scope=if ([string]$settings.mode -eq 'merge') { 'merge' } else { 'evidence_only_group' }
        })
    }
}

$conflictRows = New-Object Collections.Generic.List[object]
$conflictIndex = 0
foreach ($group in @($files | Where-Object { $_.entry_type -eq 'file' -and $_.sha256 } | Group-Object { $_.proposed_target_path.ToLowerInvariant() } |
    Where-Object { @($_.Group.sha256 | Sort-Object -Unique).Count -gt 1 } | Sort-Object Name)) {
    $conflictIndex++
    foreach ($member in @($group.Group | Sort-Object { $_.source_id.ToLowerInvariant() }, { $_.relative_path.ToLowerInvariant() })) {
        $conflictRows.Add([pscustomobject][ordered]@{
            conflict_group_id=('C{0:D6}' -f $conflictIndex); proposed_target_path=$member.proposed_target_path
            source_id=$member.source_id; relative_path=$member.relative_path; sha256=$member.sha256; reason='same_target_different_sha256'
        })
    }
}
foreach($member in @($files|Where-Object{$_.entry_type -eq 'file' -and $_.target_status -eq 'hash_conflict'})){
    $conflictIndex++
    $conflictRows.Add([pscustomobject][ordered]@{
        conflict_group_id=('C{0:D6}' -f $conflictIndex);proposed_target_path=$member.proposed_target_path
        source_id=$member.source_id;relative_path=$member.relative_path;sha256=$member.sha256;reason='existing_target_different_sha256'
    })
}

$conflictTargets=@{}
foreach($row in @($conflictRows.ToArray())){$conflictTargets[([string]$row.proposed_target_path).ToLowerInvariant()]=$true}
$selectedByHash=@{}
if([string]$settings.mode -eq 'merge'){
    foreach($row in @($duplicateRows.ToArray()|Where-Object{[string]$_.selected -eq 'True'})){$selectedByHash[[string]$row.sha256]=$row}
}
$treeIndex=@{}
function Add-TargetTreeEntry {
    param([string]$RelativePath,[string]$EntryType,[string]$Origin,[string]$State,[string]$Sha256,[string]$SourceId)
    $relative=ConvertTo-PORelativePath $RelativePath
    if(-not $relative){return}
    $key=$relative.ToLowerInvariant()
    if($treeIndex.ContainsKey($key)){
        $existing=$treeIndex[$key]
        if([string]$existing.entry_type -ne $EntryType){
            $existing.state='hold_conflict'
            $layoutViolationRows.Add([pscustomobject][ordered]@{relative_path=$relative;rule='tree_type_conflict';reason='file_and_directory_share_target_path'})
            return
        }
        if($EntryType -eq 'file' -and $existing.sha256 -and $Sha256 -and [string]$existing.sha256 -ne $Sha256){$existing.state='hold_conflict'}
        if($State -like 'hold*'){$existing.state=$State}
        $existing.source_ids=(@(([string]$existing.source_ids).Split(';')+@($SourceId)|Where-Object{$_}|Sort-Object -Unique)-join ';')
        $existing.origin=(@(([string]$existing.origin).Split(';')+@($Origin)|Where-Object{$_}|Sort-Object -Unique)-join ';')
        return
    }
    $treeIndex[$key]=[pscustomobject][ordered]@{
        relative_path=$relative;entry_type=$EntryType;origin=$Origin;state=$State;source_ids=$SourceId
        sha256=$Sha256;exception_reason=''
    }
}

foreach($row in @($targetRows.ToArray())){
    Add-TargetTreeEntry -RelativePath $row.relative_path -EntryType $row.entry_type -Origin 'target_existing' `
        -State $(if([string]$row.scan_status -in @('hold','error')){'hold_unsupported'}else{'target_existing'}) -Sha256 $row.sha256 -SourceId '__target__'
}
foreach($row in $files){
    $status=[string]$row.scan_status
    if($status -in @('excluded','preserve_git_metadata')){continue}
    $targetPath=[string]$row.proposed_target_path
    $treeState=if($status -in @('hold','error')){'hold_unsupported'}elseif($conflictTargets.ContainsKey($targetPath.ToLowerInvariant())){'hold_conflict'}else{'planned'}
    if([string]$row.entry_type -eq 'file' -and [string]$settings.mode -eq 'merge' -and $selectedByHash.ContainsKey([string]$row.sha256)){
        $selected=$selectedByHash[[string]$row.sha256]
        $isSelected=([string]$selected.source_id -eq [string]$row.source_id -and [string]$selected.relative_path -eq [string]$row.relative_path)
        if(-not $isSelected){continue}
    }
    Add-TargetTreeEntry -RelativePath $row.proposed_relative_path -EntryType $row.entry_type -Origin 'source_mapping' `
        -State $treeState -Sha256 $row.sha256 -SourceId $row.source_id
}

foreach($entry in @($treeIndex.Values)){
    $parts=@(([string]$entry.relative_path).Split('/'))
    for($index=1;$index -lt $parts.Count;$index++){
        Add-TargetTreeEntry -RelativePath (($parts[0..($index-1)]) -join '/') -EntryType 'directory' -Origin 'parent' -State 'planned' -Sha256 '' -SourceId ''
    }
}

if([string]$settings.mode -eq 'merge'){
    $layout=$settings.layout_decisions
    $rootFiles=@{};foreach($value in @($layout.root_files)){$rootFiles[(ConvertTo-PORelativePath ([string]$value)).ToLowerInvariant()]=$true}
    $deepPrefixes=@((@($layout.deep_structure_prefixes)+@($layout.independent_subprojects))|ForEach-Object{(ConvertTo-PORelativePath ([string]$_)).ToLowerInvariant()}|Sort-Object -Unique)
    $keepEmpty=@{};foreach($value in @($layout.keep_empty_directories)){$keepEmpty[(ConvertTo-PORelativePath ([string]$value)).ToLowerInvariant()]=$true}
    $forbidden=@($layout.forbidden_target_paths|ForEach-Object{(ConvertTo-PORelativePath ([string]$_)).ToLowerInvariant()})
    $exceptions=@($layout.exceptions|ForEach-Object{[pscustomobject]@{path=(ConvertTo-PORelativePath ([string]$_.path)).ToLowerInvariant();reason=[string]$_.reason}})
    function Get-LayoutExceptionReason {
        param([string]$RelativePath)
        $key=$RelativePath.ToLowerInvariant()
        foreach($exception in $exceptions){if($key -eq $exception.path -or $key.StartsWith($exception.path+'/')){return $exception.reason}}
        return ''
    }
    function Add-LayoutViolation {
        param([string]$RelativePath,[string]$Rule,[string]$Reason)
        $exceptionReason=Get-LayoutExceptionReason $RelativePath
        if($exceptionReason){if($treeIndex.ContainsKey($RelativePath.ToLowerInvariant())){$treeIndex[$RelativePath.ToLowerInvariant()].exception_reason=$exceptionReason};return}
        $layoutViolationRows.Add([pscustomobject][ordered]@{relative_path=$RelativePath;rule=$Rule;reason=$Reason})
    }
    foreach($entry in @($treeIndex.Values)){
        $relative=[string]$entry.relative_path;$key=$relative.ToLowerInvariant()
        if([string]$entry.state -like 'hold*'){Add-LayoutViolation $relative 'unresolved_tree_entry' ([string]$entry.state)}
        foreach($prefix in $forbidden){if($key -eq $prefix -or $key.StartsWith($prefix+'/')){Add-LayoutViolation $relative 'forbidden_target_path' "path_is_under_$prefix"}}
        if([string]$entry.entry_type -ne 'file'){continue}
        $parts=@($relative.Split('/'))
        if($parts.Count -eq 1){if(-not $rootFiles.ContainsKey($key)){Add-LayoutViolation $relative 'root_file_not_approved' 'root-level file is not listed in layout_decisions.root_files'};continue}
        $isDeep=$false;foreach($prefix in $deepPrefixes){if($key -eq $prefix -or $key.StartsWith($prefix+'/')){$isDeep=$true;break}}
        if(-not $isDeep -and ($parts.Count-1) -gt [int]$layout.max_general_depth){
            Add-LayoutViolation $relative 'general_depth_exceeded' "parent depth $($parts.Count-1) exceeds $($layout.max_general_depth)"
        }
    }
    $fileEntries=@($treeIndex.Values|Where-Object entry_type -eq 'file')
    foreach($directory in @($treeIndex.Values|Where-Object entry_type -eq 'directory')){
        $key=([string]$directory.relative_path).ToLowerInvariant()
        $hasFile=@($fileEntries|Where-Object{([string]$_.relative_path).ToLowerInvariant().StartsWith($key+'/')}).Count -gt 0
        if(-not $hasFile -and -not $keepEmpty.ContainsKey($key)){Add-LayoutViolation $directory.relative_path 'empty_directory_not_approved' 'empty directory is not listed in keep_empty_directories'}
    }
}

$treeRows=@($treeIndex.Values|Sort-Object {([string]$_.relative_path).ToLowerInvariant()},{[string]$_.relative_path},{[string]$_.entry_type})

$duplicates = @($duplicateRows.ToArray())
$conflicts = @($conflictRows.ToArray())
$errors = @($errorRows.ToArray() | Sort-Object { $_.source_id.ToLowerInvariant() }, { $_.path.ToLowerInvariant() }, { $_.stage }, { $_.reason })
Write-POCsv -Path (Join-Path $output 'files.csv') -Rows $files -Columns @(
    'source_id','source_root','relative_path','entry_type','size_bytes','last_write_utc','attributes','reparse_tag',
    'link_count','sha256','scan_status','reason','proposed_relative_path','proposed_target_path','target_status'
)
Write-POCsv -Path (Join-Path $output 'duplicates.csv') -Rows $duplicates -Columns @(
    'duplicate_group_id','sha256','source_id','relative_path','proposed_target_path','selected_target_path','selected','dedup_scope'
)
Write-POCsv -Path (Join-Path $output 'conflicts.csv') -Rows $conflicts -Columns @(
    'conflict_group_id','proposed_target_path','source_id','relative_path','sha256','reason'
)
$targetStateRows=@($targetRows.ToArray()|Sort-Object{([string]$_.relative_path).ToLowerInvariant()},{[string]$_.relative_path})
$layoutViolations=@($layoutViolationRows.ToArray()|Sort-Object{([string]$_.relative_path).ToLowerInvariant()},{[string]$_.rule},{[string]$_.reason} -Unique)
Write-POCsv -Path (Join-Path $output 'target-state.csv') -Rows $targetStateRows -Columns @(
    'relative_path','entry_type','size_bytes','last_write_utc','sha256','scan_status','reason'
)
Write-POJson -Path (Join-Path $output 'target-state.json') -Value $targetState
Write-POCsv -Path (Join-Path $output 'layout-violations.csv') -Rows $layoutViolations -Columns @('relative_path','rule','reason')
$targetTreePath=Join-Path $output 'target-tree.csv'
Write-POCsv -Path $targetTreePath -Rows $treeRows -Columns @('relative_path','entry_type','origin','state','source_ids','sha256','exception_reason')
$targetTreeHash=Get-POStableSha256 -Path $targetTreePath
Write-POText -Path (Join-Path $output 'target-tree.sha256') -Text ($targetTreeHash+"`n")
$approvedTree='';if([string]$settings.mode -eq 'merge'){$approvedTree=[string]$settings.layout_decisions.approved_tree_sha256}
$treeApproved=([string]$settings.mode -eq 'merge' -and $approvedTree -and $approvedTree.ToUpperInvariant() -eq $targetTreeHash)
$approvalStatus=if([string]$settings.mode -eq 'group'){'不适用（保持各项目内部结构）'}elseif($treeApproved){'已匹配'}else{'未批准或已变化'}
$treeLines=@(
    '# 最终目标目录树','',
    "- 目标：$($settings.target_root)",
    "- 模式：$($settings.mode)",
    "- 目录树 SHA256：$targetTreeHash",
    "- 当前批准：$approvalStatus",
    "- 布局问题：$($layoutViolations.Count)",'',
    '```text','.'
)
foreach($entry in $treeRows){
    $parts=@(([string]$entry.relative_path).Split('/'));$indent='  '*$parts.Count;$name=$parts[-1]
    if([string]$entry.entry_type -eq 'directory'){$name+='\'}
    $suffix=if([string]$entry.state -like 'hold*'){" [$($entry.state)]"}else{''}
    $treeLines+=$indent+'- '+$name+$suffix
}
$treeLines+=@('```','')
if([string]$settings.mode -eq 'merge'){
    $treeLines+=@(
        "- 根目录文件：$(@($settings.layout_decisions.root_files)-join ', ')",
        "- 普通资料最大分类层级：$($settings.layout_decisions.max_general_depth)",
        "- 深层结构例外：$(@($settings.layout_decisions.deep_structure_prefixes)-join ', ')",
        "- 独立子项目：$(@($settings.layout_decisions.independent_subprojects)-join ', ')",
        "- 版本策略：$($settings.layout_decisions.version_policy)",''
    )
    if($treeApproved){$treeLines+=@('目录树批准记录与当前哈希一致，可以进入 Git 恢复归档和正式迁移计划阶段。','')}
    else{$treeLines+=@('用户确认目录树后，把上面的 SHA256 写入 layout_decisions.approved_tree_sha256，重新盘点，再生成正式迁移计划。','')}
}
Write-POText -Path (Join-Path $output 'target-tree.md') -Text (($treeLines-join "`n")+"`n")
Write-POCsv -Path (Join-Path $output 'errors.csv') -Rows $errors -Columns @('source_id','path','stage','reason')
Write-POJson -Path (Join-Path $output 'source_state.json') -Value @($sourceStates.ToArray())
Write-POJson -Path (Join-Path $output 'git_state.json') -Value @($gitStates.ToArray() | Sort-Object { $_.source_id.ToLowerInvariant() })

$summary = @(
    '# 项目文件盘点','',
    "- 模式：$($settings.mode)",
    "- 来源：$(@($settings.sources).Count)",
    "- 文件：$(@($files | Where-Object entry_type -eq 'file').Count)",
    "- 字节：$((@($files | Where-Object entry_type -eq 'file') | Measure-Object size_bytes -Sum).Sum)",
    "- 重复记录：$($duplicates.Count)",
    "- 冲突记录：$($conflicts.Count)",
    "- hold：$(@($files | Where-Object scan_status -eq 'hold').Count)",
    "- 目标目录树 SHA256：$targetTreeHash",
    "- 布局问题：$($layoutViolations.Count)",
    "- errors：$($errors.Count)",'',
    '任何 hold、布局问题或 errors 非零都禁止生成可执行迁移。',''
)
Write-POText -Path (Join-Path $output 'summary.md') -Text (($summary -join "`n") + "`n")
$manifestPath = Join-Path $output 'inventory-files.sha256'
[void](New-POHashManifest -Paths @(
    $configPath,(Join-Path $output 'files.csv'),(Join-Path $output 'duplicates.csv'),(Join-Path $output 'conflicts.csv'),
    (Join-Path $output 'source_state.json'),(Join-Path $output 'git_state.json'),(Join-Path $output 'target-state.csv'),
    (Join-Path $output 'target-state.json'),$targetTreePath,(Join-Path $output 'target-tree.sha256'),
    (Join-Path $output 'target-tree.md'),(Join-Path $output 'layout-violations.csv'),(Join-Path $output 'errors.csv')
) -OutputPath $manifestPath)
$inventoryHash = Get-POStableSha256 -Path $manifestPath
Write-POText -Path (Join-Path $output 'inventory.sha256') -Text ($inventoryHash + "`n")

Write-Output "Inventory SHA256: $inventoryHash"
Write-Output "Files: $(@($files | Where-Object entry_type -eq 'file').Count); errors: $($errors.Count); hold: $(@($files | Where-Object scan_status -eq 'hold').Count); layout: $($layoutViolations.Count)"
