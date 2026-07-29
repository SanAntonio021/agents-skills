[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Config,
    [Parameter(Mandatory = $true)][string]$OutputDir
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'ProjectOrganizer.psm1') -Force

$settings = Read-POConfig -Path $Config -RequireSources
$configPath = Resolve-POFullPath -Path $Config -AllowNetwork
$output = Resolve-POFullPath -Path $OutputDir
$inventoryManifest = Join-Path $output 'inventory-files.sha256'
$inventoryHashPath = Join-Path $output 'inventory.sha256'
if (-not (Test-Path -LiteralPath $inventoryManifest) -or -not (Test-Path -LiteralPath $inventoryHashPath)) { throw 'Inventory artifacts are missing.' }
$inventoryCheck = Test-POHashManifest -ManifestPath $inventoryManifest
if (-not $inventoryCheck.Valid) { throw "Inventory manifest is invalid: $($inventoryCheck.Errors -join '; ')" }
$recordedInventoryHash = (Get-Content -LiteralPath $inventoryHashPath -Encoding UTF8 -Raw).Trim().ToUpperInvariant()
if ((Get-POStableSha256 -Path $inventoryManifest) -ne $recordedInventoryHash) { throw 'inventory.sha256 does not match inventory-files.sha256.' }

$files = @(Import-Csv -LiteralPath (Join-Path $output 'files.csv') -Encoding UTF8)
$duplicates = @(Import-Csv -LiteralPath (Join-Path $output 'duplicates.csv') -Encoding UTF8)
$conflicts = @(Import-Csv -LiteralPath (Join-Path $output 'conflicts.csv') -Encoding UTF8)
$inventoryErrors = @(Import-Csv -LiteralPath (Join-Path $output 'errors.csv') -Encoding UTF8)
$gitStates = @(Read-POJsonArray -Path (Join-Path $output 'git_state.json'))
$targetTreePath=Join-Path $output 'target-tree.csv'
$targetTreeHashPath=Join-Path $output 'target-tree.sha256'
$targetTreeReviewPath=Join-Path $output 'target-tree.md'
$layoutViolationsPath=Join-Path $output 'layout-violations.csv'
if(-not(Test-Path -LiteralPath $targetTreePath)-or -not(Test-Path -LiteralPath $targetTreeHashPath)-or
    -not(Test-Path -LiteralPath $targetTreeReviewPath)-or -not(Test-Path -LiteralPath $layoutViolationsPath)){
    throw 'Target layout artifacts are missing.'
}
$targetTreeHash=(Get-Content -LiteralPath $targetTreeHashPath -Encoding UTF8 -Raw).Trim().ToUpperInvariant()
if((Get-POStableSha256 -Path $targetTreePath) -ne $targetTreeHash){throw 'target-tree.sha256 does not match target-tree.csv.'}
$layoutViolations=@(Import-Csv -LiteralPath $layoutViolationsPath -Encoding UTF8)
if($layoutViolations.Count -gt 0){throw "Target layout has unresolved violations: $($layoutViolations.Count)"}
if([string]$settings.mode -eq 'merge'){
    $approvedTree=([string]$settings.layout_decisions.approved_tree_sha256).ToUpperInvariant()
    if(-not $approvedTree -or $approvedTree -ne $targetTreeHash){throw 'The readable target tree has not been approved, or its SHA256 changed.'}
}
$gitArchivesPath = Join-Path $output 'git_archives.json'
$gitArchives = @()
if (Test-Path -LiteralPath $gitArchivesPath) { $gitArchives = @(Read-POJsonArray -Path $gitArchivesPath) }
$gitErrorPath = Join-Path $output 'git-errors.csv'
$gitErrors = @()
if (Test-Path -LiteralPath $gitErrorPath) { $gitErrors = @(Import-Csv -LiteralPath $gitErrorPath -Encoding UTF8) }
if ($gitStates.Count -gt 0 -and $gitArchives.Count -lt $gitStates.Count) { throw 'Not every discovered Git repository has a verified recovery bundle.' }
if ($gitErrors.Count -gt 0) { throw 'Git recovery errors prohibit plan creation.' }
foreach ($archive in $gitArchives) {
    if (-not $archive.bundle_verified -or -not $archive.restore_fsck_verified -or -not $archive.references_verified) { throw "Unverified Git archive: $($archive.source_id)" }
    if ((Get-POStableSha256 -Path ([string]$archive.bundle_path)) -ne ([string]$archive.bundle_sha256).ToUpperInvariant()) { throw "Git bundle hash mismatch: $($archive.source_id)" }
}

$conflictTargets = @{}
foreach ($row in $conflicts) { $conflictTargets[([string]$row.proposed_target_path).ToLowerInvariant()] = $true }
$selectedByHash = @{}
if ([string]$settings.mode -eq 'merge') {
    foreach ($row in @($duplicates | Where-Object { [string]$_.selected -eq 'True' })) { $selectedByHash[[string]$row.sha256] = $row }
}

$draftActions = New-Object Collections.Generic.List[object]
$directoryTargets = @{}
foreach ($row in $files) {
    $sourcePath = Join-POPath -Root ([string]$row.source_root) -RelativePath ([string]$row.relative_path)
    $targetPath = [string]$row.proposed_target_path
    $status = [string]$row.scan_status
    $action = ''
    $reason = [string]$row.reason
    if ([string]$row.entry_type -eq 'directory') {
        if ($status -eq 'preserve_git_metadata') { $action='preserve_git_metadata' }
        elseif ($status -eq 'excluded') { $action='exclude_cache' }
        elseif ($status -eq 'hold' -or [string]$row.target_status -eq 'target_type_conflict') { $action='hold_unsupported' }
        else {
            $targetKey = $targetPath.ToLowerInvariant()
            if ($directoryTargets.ContainsKey($targetKey)) { continue }
            $directoryTargets[$targetKey] = $true
            $action='create_directory'
        }
    }
    elseif ($conflictTargets.ContainsKey($targetPath.ToLowerInvariant())) { $action='hold_conflict'; $reason='same_target_different_sha256' }
    elseif ($status -eq 'hold' -or $status -eq 'error') { $action='hold_unsupported' }
    elseif ($status -eq 'preserve_git_metadata') { $action='preserve_git_metadata' }
    elseif ($status -eq 'excluded') { $action='exclude_cache' }
    elseif ($status -eq 'target_duplicate') { $action='skip_target_duplicate' }
    elseif ([string]$settings.mode -eq 'merge' -and $selectedByHash.ContainsKey([string]$row.sha256)) {
        $selected = $selectedByHash[[string]$row.sha256]
        $isSelected = ([string]$selected.source_id -eq [string]$row.source_id -and [string]$selected.relative_path -eq [string]$row.relative_path)
        if (-not $isSelected) { $action='skip_exact_duplicate'; $targetPath=[string]$selected.selected_target_path; $reason='merge_sha256_duplicate' }
    }
    if (-not $action) {
        $action = if (Test-POSameVolume -First $sourcePath -Second $targetPath) { 'move_file_verify' } else { 'copy_file_verify' }
    }
    $draftActions.Add([pscustomobject][ordered]@{
        action_id=''; action=$action; source_id=$row.source_id; source_path=$sourcePath; relative_path=$row.relative_path
        target_path=$targetPath; size_bytes=[int64]$row.size_bytes; last_write_utc=$row.last_write_utc
        sha256=$row.sha256; reason=$reason; state='planned'
    })
}

$priority = @{ create_directory=10; move_file_verify=20; copy_file_verify=20; skip_exact_duplicate=30; skip_target_duplicate=30; exclude_cache=40; preserve_git_metadata=50; hold_conflict=90; hold_unsupported=90 }
$orderedActions = @($draftActions.ToArray() | Sort-Object { $priority[[string]$_.action] }, { $_.target_path.ToLowerInvariant() }, { $_.source_id.ToLowerInvariant() }, { $_.relative_path.ToLowerInvariant() })
for ($index=0; $index -lt $orderedActions.Count; $index++) { $orderedActions[$index].action_id = ('A{0:D8}' -f ($index + 1)) }

$copyBytes = [int64]0
foreach ($copyAction in @($orderedActions | Where-Object action -eq 'copy_file_verify')) { $copyBytes += [int64]$copyAction.size_bytes }
$requiredBytes = [int64][Math]::Ceiling($copyBytes * 1.2)
$minimumProperty = $settings.PSObject.Properties['minimum_free_bytes']
if ($null -ne $minimumProperty -and [int64]$minimumProperty.Value -gt $requiredBytes) { $requiredBytes = [int64]$minimumProperty.Value }
$availableBytes = Get-PODriveFreeSpace -Path $settings.target_root
$space = [ordered]@{
    unique_cross_volume_copy_bytes=$copyBytes; safety_margin_percent=20
    required_free_bytes=$requiredBytes; available_free_bytes=$availableBytes; sufficient=($availableBytes -ge $requiredBytes)
}
$planErrors = New-Object Collections.Generic.List[object]
foreach ($row in $inventoryErrors) { $planErrors.Add([pscustomobject][ordered]@{ stage='inventory'; item=$row.path; reason=$row.reason }) }
if (-not $space.sufficient) { $planErrors.Add([pscustomobject][ordered]@{ stage='space'; item=$settings.target_root; reason='insufficient_free_space' }) }

$actionsPath = Join-Path $output 'actions.csv'
$spacePath = Join-Path $output 'space.json'
$planErrorsPath = Join-Path $output 'plan-errors.csv'
Write-POCsv -Path $actionsPath -Rows $orderedActions -Columns @(
    'action_id','action','source_id','source_path','relative_path','target_path','size_bytes','last_write_utc','sha256','reason','state'
)
Write-POJson -Path $spacePath -Value $space
Write-POCsv -Path $planErrorsPath -Rows @($planErrors.ToArray()) -Columns @('stage','item','reason')

$counts = @{}
foreach ($group in @($orderedActions | Group-Object action)) { $counts[$group.Name] = $group.Count }
$review = @(
    '# 项目迁移计划审查','',
    "- 模式：$($settings.mode)",
    "- 来源：$(@($settings.sources).Count)",
    "- 目标：$($settings.target_root)",
    "- 同盘移动：$([int]$counts['move_file_verify'])",
    "- 跨盘复制：$([int]$counts['copy_file_verify'])",
    "- 完全重复跳过：$([int]$counts['skip_exact_duplicate'])",
    "- 目标已有副本：$([int]$counts['skip_target_duplicate'])",
    "- 缓存排除：$([int]$counts['exclude_cache'])",
    "- Git 元数据保留：$([int]$counts['preserve_git_metadata'])",
    "- 冲突 hold：$([int]$counts['hold_conflict'])",
    "- 不支持项 hold：$([int]$counts['hold_unsupported'])",
    "- 已批准目录树 SHA256：$targetTreeHash",
    "- 跨盘唯一字节：$copyBytes",
    "- 含 20% 余量需求：$requiredBytes",
    "- 当前可用空间：$availableBytes",
    "- 错误：$($planErrors.Count)",'',
    '只有 errors 和 hold 都为零时才可批准完整计划 SHA256。迁移批准不包含旧路径退役。',''
)
Write-POText -Path (Join-Path $output 'review.md') -Text (($review -join "`n") + "`n")

$boundPaths = @($configPath,$inventoryManifest,$inventoryHashPath,$targetTreePath,$targetTreeHashPath,$targetTreeReviewPath,$layoutViolationsPath,$actionsPath,$spacePath,$planErrorsPath,(Join-Path $output 'review.md'))
if (Test-Path -LiteralPath $gitArchivesPath) { $boundPaths += $gitArchivesPath }
$planManifest = Join-Path $output 'plan-files.sha256'
[void](New-POHashManifest -Paths $boundPaths -OutputPath $planManifest)
$planHash = Get-POStableSha256 -Path $planManifest
Write-POText -Path (Join-Path $output 'plan.sha256') -Text ($planHash + "`n")
Write-Output "Plan SHA256: $planHash"
Write-Output "Errors: $($planErrors.Count); hold: $(@($orderedActions | Where-Object { $_.action -like 'hold_*' }).Count)"
