[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Config,
    [Parameter(Mandatory = $true)][string]$OutputDir,
    [Parameter(Mandatory = $true)][string]$ApprovedPlanSha256,
    [switch]$Execute,
    [switch]$Resume,
    [ValidateRange(0,2147483647)][int]$StopAfterActions = 0
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'ProjectOrganizer.psm1') -Force

function Save-ExecutionState {
    param($State,[string]$Path)
    $State.completed_action_ids = @($State.completed_action_ids | Sort-Object -Unique)
    Write-POJson -Path $Path -Value $State
}

function Assert-SourceStateFresh {
    param($Recorded,$Settings)
    foreach ($source in @($Settings.sources)) {
        $state = @($Recorded | Where-Object { [string]$_.source_id -eq [string]$source.id })
        if ($state.Count -ne 1) { throw "Missing recorded source state: $($source.id)" }
        $current = Get-POFileSnapshot -Root ([string]$source.path)
        foreach ($field in @('file_count','directory_count','total_bytes','error_count')) {
            if ([int64]$current.$field -ne [int64]$state[0].after.$field) { throw "Source state changed before execution: $($source.path) ($field)" }
        }
    }
}

function Assert-SourceInventorySet {
    param([string]$RunDirectory,$Settings,$ExecutionState)
    $inventory=@(Import-Csv -LiteralPath (Join-Path $RunDirectory 'files.csv') -Encoding UTF8)
    $inventoryByPath=@{}
    foreach($row in $inventory){
        $full=Join-POPath -Root ([string]$row.source_root) -RelativePath ([string]$row.relative_path)
        $inventoryByPath[$full.ToLowerInvariant()]=$row
    }
    $actions=@(Import-Csv -LiteralPath (Join-Path $RunDirectory 'actions.csv') -Encoding UTF8)
    $completed=@{};foreach($id in @($ExecutionState.completed_action_ids)){$completed[[string]$id]=$true}
    $moved=@{}
    foreach($action in @($actions|Where-Object{$_.action -eq 'move_file_verify' -and $completed.ContainsKey([string]$_.action_id)})){
        $moved[([string]$action.source_path).ToLowerInvariant()]=$true
    }
    $current=@{}
    foreach($source in @($Settings.sources)){
        $scan=Get-POSourceEntries -Root ([string]$source.path)
        if($scan.Errors.Count -gt 0){throw "Source rescan failed: $($source.path)"}
        foreach($entry in @($scan.Entries)){
            $key=([string]$entry.full_path).ToLowerInvariant();$current[$key]=$entry
            if(-not $inventoryByPath.ContainsKey($key)){throw "Unplanned source entry appeared: $($entry.full_path)"}
            $recorded=$inventoryByPath[$key]
            if([string]$entry.entry_type -eq 'file'){
                if([int64]$entry.size_bytes -ne [int64]$recorded.size_bytes -or [string]$entry.last_write_utc -ne [string]$recorded.last_write_utc){throw "Source entry changed: $($entry.full_path)"}
                if([string]$recorded.sha256 -match '^[0-9A-Fa-f]{64}$' -and
                    (Get-POStableSha256 -Path ([string]$entry.full_path)) -ne ([string]$recorded.sha256).ToUpperInvariant()){throw "Source hash changed: $($entry.full_path)"}
            }
        }
    }
    foreach($pair in $inventoryByPath.GetEnumerator()){
        if($moved.ContainsKey($pair.Key)){
            if($current.ContainsKey($pair.Key)){throw "Completed move source reappeared: $($pair.Value.relative_path)"}
        }elseif(-not $current.ContainsKey($pair.Key)){throw "Planned source entry disappeared: $($pair.Value.relative_path)"}
    }
}

function Assert-GitArchives {
    param([string]$RunDirectory,$Settings)
    $gitStatePath = Join-Path $RunDirectory 'git_state.json'
    $states = @()
    if (Test-Path -LiteralPath $gitStatePath) { $states = @(Read-POJsonArray -Path $gitStatePath) }
    if ($states.Count -eq 0) { return @() }
    $archivePath = Join-Path $RunDirectory 'git_archives.json'
    if (-not (Test-Path -LiteralPath $archivePath)) { throw 'git_archives.json is missing.' }
    $archives = @(Read-POJsonArray -Path $archivePath)
    foreach ($state in $states) {
        $archive = @($archives | Where-Object { [string]$_.source_id -eq [string]$state.source_id })
        if ($archive.Count -ne 1) { throw "Verified Git archive missing: $($state.source_id)" }
        if ((Get-POStableSha256 -Path ([string]$archive[0].bundle_path)) -ne ([string]$archive[0].bundle_sha256).ToUpperInvariant()) {
            throw "Git archive changed: $($state.source_id)"
        }
    }
    return $archives
}

function Assert-TargetStateFresh {
    param($Settings,[string]$RunDirectory,$Actions,$Started)
    if([string]$Settings.schema_version -ne '1.1'){return}
    $original=@(Import-Csv -LiteralPath (Join-Path $RunDirectory 'target-state.csv') -Encoding UTF8)
    $expected=@{}
    foreach($row in $original){$expected[$row.relative_path.ToLowerInvariant()]=[pscustomobject]@{entry_type=$row.entry_type;sha256=$row.sha256}}
    foreach($action in $Actions){
        if(-not $Started.ContainsKey([string]$action.action_id)){continue}
        if($action.action -notin @('create_directory','move_file_verify','copy_file_verify','install_integrated_file')){continue}
        $key=(Get-PORelativePath -Root $Settings.target_root -Path $action.target_path).ToLowerInvariant()
        $expected[$key]=[pscustomobject]@{entry_type=$(if($action.action -eq 'create_directory'){'directory'}else{'file'});sha256=$action.sha256}
    }
    if(-not [IO.Directory]::Exists((ConvertTo-POExtendedPath $Settings.target_root))){if($original.Count -gt 0){throw 'Existing target disappeared.'};return}
    $scan=Get-POSourceEntries -Root $Settings.target_root -ExcludeRoot $Settings.audit_root
    if($scan.Errors.Count -gt 0){throw 'Target rescan failed.'}
    $actual=@{}
    foreach($entry in $scan.Entries){
        if(Test-POGitMetadataPath -RelativePath $entry.relative_path){continue}
        $key=$entry.relative_path.ToLowerInvariant();$actual[$key]=$true
        if(-not $expected.ContainsKey($key)){throw "Unplanned target entry appeared: $($entry.full_path)"}
        if($entry.is_name_surrogate -or $entry.is_cloud_placeholder -or $entry.reparse_tag -ne '0x00000000'){throw "Unsupported target entry: $($entry.full_path)"}
        if($expected[$key].entry_type -ne $entry.entry_type){throw "Target entry type changed: $($entry.full_path)"}
        if($entry.entry_type -eq 'file' -and (Get-POStableSha256 -Path $entry.full_path) -ne $expected[$key].sha256){
            $old=@($original|Where-Object{$_.relative_path.ToLowerInvariant() -eq $key})
            if($old.Count -ne 1 -or (Get-POStableSha256 -Path $entry.full_path) -ne $old[0].sha256){throw "Target content changed: $($entry.full_path)"}
        }
    }
    foreach($row in $original){if(-not $actual.ContainsKey($row.relative_path.ToLowerInvariant())){throw "Existing target disappeared: $($row.relative_path)"}}
}

function Install-ActiveGitStore {
    param($Settings,[string]$RunDirectory,$State)
    $results = New-Object Collections.Generic.List[object]
    $activePolicy = [string]$Settings.active_repo_policy
    $activeSources = @()
    if ([string]$Settings.mode -eq 'group') { $activeSources = @($Settings.sources) }
    elseif ($activePolicy -like 'source:*') {
        $activeId = $activePolicy.Substring(7)
        $activeSources = @($Settings.sources | Where-Object { [string]$_.id -eq $activeId })
        if ($activeSources.Count -ne 1) { throw "active_repo_policy source is invalid: $activePolicy" }
    }

    foreach ($source in $activeSources) {
        $sourceGit = Get-POGitState -Repository ([string]$source.path)
        if ($null -eq $sourceGit) { continue }
        $worktree = if ([string]$Settings.mode -eq 'group') {
            Join-POPath -Root $Settings.target_root -RelativePath ([string]$source.target_name)
        } else { [string]$Settings.target_root }
        [void][IO.Directory]::CreateDirectory((ConvertTo-POExtendedPath $worktree))
        $externalized = Test-POSyncPath -Path $worktree -SyncRoots $Settings.sync_roots
        $stableId=Get-POStableId -Value (([string]$Settings.mode)+'|'+$worktree+'|'+[string]$source.id)
        $gitDestination = if ($externalized) {
            Join-Path ([string]$Settings.external_git_root) ('active\' + [string]$source.id + '-' + $stableId + '.git')
        } else { Join-Path $worktree '.git' }
        $pointer = Join-Path $worktree '.git'
        $existing = @($State.active_git | Where-Object { [string]$_.source_id -eq [string]$source.id })
        if ($existing.Count -eq 0) {
            if (Test-Path -LiteralPath $gitDestination) { throw "Active Git destination already exists: $gitDestination" }
            if ($externalized -and (Test-Path -LiteralPath $pointer)) { throw "Git pointer path already exists: $pointer" }
            [void](Copy-PODirectoryVerified -Source ([string]$sourceGit.git_dir) -Target $gitDestination)
            if ($externalized) { Write-POText -Path $pointer -Text ('gitdir: ' + $gitDestination.Replace('\','/') + "`n") }
            [void](Invoke-POGit -Repository $worktree -Arguments @('config','core.worktree',$worktree.Replace('\','/')))
        }
        $targetGit = Get-POGitState -Repository $worktree
        if ($null -eq $targetGit -or [string]$targetGit.head -ne [string]$sourceGit.head) { throw "Active Git recovery validation failed: $worktree" }
        if ($externalized -and (Test-POSyncPath -Path ([string]$targetGit.git_dir) -SyncRoots $Settings.sync_roots)) {
            throw "Active Git database remains inside sync root: $($targetGit.git_dir)"
        }
        $results.Add([pscustomobject][ordered]@{
            source_id=[string]$source.id; worktree=$worktree; git_dir=[string]$targetGit.git_dir
            head=[string]$targetGit.head; externalized=$externalized; verified=$true
        })
    }

    if ([string]$Settings.mode -eq 'merge' -and $activePolicy -eq 'new') {
        $worktree = [string]$Settings.target_root
        [void][IO.Directory]::CreateDirectory((ConvertTo-POExtendedPath $worktree))
        $externalized = Test-POSyncPath -Path $worktree -SyncRoots $Settings.sync_roots
        $gitDestination = Join-Path ([string]$Settings.external_git_root) ('active\merged-new-' + (Get-POStableId -Value $worktree) + '.git')
        if (@($State.active_git).Count -eq 0) {
            if ($externalized) {
                if ((Test-Path -LiteralPath $gitDestination) -or (Test-Path -LiteralPath (Join-Path $worktree '.git'))) { throw 'New Git destination already exists.' }
                [void][IO.Directory]::CreateDirectory((ConvertTo-POExtendedPath (Split-Path -Parent $gitDestination)))
                $raw = @(& git --no-optional-locks init ("--separate-git-dir=$gitDestination") $worktree 2>&1)
            }
            else { $raw = @(& git --no-optional-locks init $worktree 2>&1) }
            if ($LASTEXITCODE -ne 0) { throw "git init failed: $($raw -join "`n")" }
        }
        $targetGit = Get-POGitState -Repository $worktree
        if ($null -eq $targetGit) { throw 'New active Git repository validation failed.' }
        $results.Add([pscustomobject][ordered]@{ source_id='new'; worktree=$worktree; git_dir=$targetGit.git_dir; head=$targetGit.head; externalized=$externalized; verified=$true })
    }

    if ([string]$Settings.mode -eq 'merge' -and $activePolicy -eq 'target_existing') {
        $targetGit = Get-POGitState -Repository ([string]$Settings.target_root)
        if ($null -eq $targetGit) { throw 'target_existing policy requires a Git repository at target_root.' }
        if ((Test-POSyncPath -Path $Settings.target_root -SyncRoots $Settings.sync_roots) -and
            (Test-POSyncPath -Path ([string]$targetGit.git_dir) -SyncRoots $Settings.sync_roots)) {
            throw 'Existing target Git database is inside a sync root; externalize it before this plan.'
        }
        $results.Add([pscustomobject][ordered]@{ source_id='target_existing'; worktree=$Settings.target_root; git_dir=$targetGit.git_dir; head=$targetGit.head; externalized=$true; verified=$true })
    }
    return @($results.ToArray())
}

if ($ApprovedPlanSha256 -notmatch '^[0-9A-Fa-f]{64}$') { throw 'ApprovedPlanSha256 must contain exactly 64 hexadecimal characters.' }
$approved = $ApprovedPlanSha256.ToUpperInvariant()
$settings = Read-POConfig -Path $Config -RequireSources -ForExecution
$output = Resolve-POFullPath -Path $OutputDir
Assert-POAuditPath -Config $settings -OutputDir $output
$integration=Read-POIntegrationManifest -Config $settings
$planHashPath = Join-Path $output 'plan.sha256'
$planManifest = Join-Path $output 'plan-files.sha256'
if (-not (Test-Path -LiteralPath $planHashPath) -or -not (Test-Path -LiteralPath $planManifest)) { throw 'Plan artifacts are missing.' }
$recorded = (Get-Content -LiteralPath $planHashPath -Encoding UTF8 -Raw).Trim().ToUpperInvariant()
if ($approved -ne $recorded) { throw 'Approved plan SHA256 does not match plan.sha256.' }
if ((Get-POStableSha256 -Path $planManifest) -ne $recorded) { throw 'plan.sha256 is stale.' }
$manifestCheck = Test-POHashManifest -ManifestPath $planManifest
if (-not $manifestCheck.Valid) { throw "Plan files changed: $($manifestCheck.Errors -join '; ')" }

$actions = @(Import-Csv -LiteralPath (Join-Path $output 'actions.csv') -Encoding UTF8)
$holds = @($actions | Where-Object { $_.action -like 'hold_*' })
$planErrors = @(Import-Csv -LiteralPath (Join-Path $output 'plan-errors.csv') -Encoding UTF8)
if ($holds.Count -gt 0 -or $planErrors.Count -gt 0) { throw "Plan is not executable: hold=$($holds.Count), errors=$($planErrors.Count)." }
$space = Get-Content -LiteralPath (Join-Path $output 'space.json') -Encoding UTF8 -Raw | ConvertFrom-Json
if ((Get-PODriveFreeSpace -Path $settings.target_root) -lt [int64]$space.required_free_bytes) { throw 'Current free space is below the approved requirement.' }
[void](Assert-GitArchives -RunDirectory $output -Settings $settings)

$statePath = Join-Path $output 'execution-state.json'
$logPath = Join-Path $output 'execution.jsonl'
if (Test-Path -LiteralPath $statePath) {
    if (-not $Resume) { throw 'Execution state already exists. Use -Resume with the same approved plan.' }
    $state = Get-Content -LiteralPath $statePath -Encoding UTF8 -Raw | ConvertFrom-Json
    if ([string]$state.plan_sha256 -ne $approved) { throw 'Resume state belongs to a different plan.' }
}
else {
    if ($Resume) { throw 'No execution state exists to resume.' }
    $sourceState = @(Read-POJsonArray -Path (Join-Path $output 'source_state.json'))
    Assert-SourceStateFresh -Recorded $sourceState -Settings $settings
    $state = [pscustomobject][ordered]@{ schema_version='1.0'; plan_sha256=$approved; completed_action_ids=@(); active_git=@(); failed_action_id=''; complete=$false }
}
Assert-SourceInventorySet -RunDirectory $output -Settings $settings -ExecutionState $state

$started=@{};foreach($id in @($state.completed_action_ids)){$started[[string]$id]=$true}
if($Resume -and (Test-Path -LiteralPath $logPath)){
    foreach($line in @(Get-Content -LiteralPath $logPath -Encoding UTF8)){
        $event=$line|ConvertFrom-Json
        if($event.event -in @('start','complete')){$started[[string]$event.action_id]=$true}
    }
}
Assert-TargetStateFresh -Settings $settings -RunDirectory $output -Actions $actions -Started $started
$installedPaths=@($actions|Where-Object{$_.action -eq 'install_integrated_file' -and $started.ContainsKey([string]$_.action_id)}|ForEach-Object target_path)
if($null -ne $integration){[void](Assert-POIntegrationFiles -Integration $integration -Phase Preflight -InstalledPaths $installedPaths)}

if (-not $Execute) {
    Write-Output "Preflight passed for plan $approved. No files changed because -Execute was not supplied."
    return
}

if (@($state.active_git).Count -eq 0) {
    $state.active_git = @(Install-ActiveGitStore -Settings $settings -RunDirectory $output -State $state)
    Save-ExecutionState -State $state -Path $statePath
}

$completed = @{}
foreach ($id in @($state.completed_action_ids)) { $completed[[string]$id] = $true }
$completedThisRun = 0
foreach ($action in $actions) {
    $id = [string]$action.action_id
    if ($completed.ContainsKey($id)) { continue }
    $source = [string]$action.source_path
    $target = [string]$action.target_path
    $sourceConfig = @($settings.sources | Where-Object { [string]$_.id -eq [string]$action.source_id })
    $synthetic=([string]$settings.schema_version -eq '1.1' -and (($action.action -eq 'create_directory' -and $action.source_id -eq '__layout__') -or ($action.action -eq 'install_integrated_file' -and $action.source_id -eq '__integration__')))
    if (-not $synthetic -and ($sourceConfig.Count -ne 1 -or -not (Test-POPathWithin -Path $source -Parent ([string]$sourceConfig[0].path)))) { throw "Action source is outside confirmed root: $id" }
    if ($target -and -not (Test-POPathWithin -Path $target -Parent $settings.target_root -AllowEqual)) { throw "Action target is outside target_root: $id" }
    Add-POJsonLine -Path $logPath -Value ([ordered]@{ event='start'; action_id=$id; action=$action.action; source=$source; target=$target })
    try {
        switch ([string]$action.action) {
            'install_integrated_file' {
                if($null -eq $integration -or -not $integration.OutputByPath.ContainsKey($target.ToLowerInvariant())){throw 'Integration output is not bound.'}
                $item=$integration.OutputByPath[$target.ToLowerInvariant()]
                Install-POIntegrationOutput -Output $item -Resume:($Resume -and $started.ContainsKey($id))
            }
            'integrated_input' {
                [void](Assert-POExpectedFile -Path $source -SizeBytes ([int64]$action.size_bytes) -LastWriteUtc $action.last_write_utc -Sha256 $action.sha256)
            }
            'create_directory' {
                if ([IO.File]::Exists((ConvertTo-POExtendedPath $target))) { throw "File blocks target directory: $target" }
                [void][IO.Directory]::CreateDirectory((ConvertTo-POExtendedPath $target))
            }
            'move_file_verify' {
                [void](Assert-POExpectedFile -Path $source -SizeBytes ([int64]$action.size_bytes) -LastWriteUtc $action.last_write_utc -Sha256 $action.sha256)
                [void](Move-POFileVerified -Source $source -Target $target -ExpectedSha256 $action.sha256)
            }
            'copy_file_verify' {
                [void](Assert-POExpectedFile -Path $source -SizeBytes ([int64]$action.size_bytes) -LastWriteUtc $action.last_write_utc -Sha256 $action.sha256)
                [void](Copy-POFileAtomicVerified -Source $source -Target $target -ExpectedSha256 $action.sha256)
            }
            'skip_exact_duplicate' {
                [void](Assert-POExpectedFile -Path $source -SizeBytes ([int64]$action.size_bytes) -LastWriteUtc $action.last_write_utc -Sha256 $action.sha256)
                if ((Get-POStableSha256 -Path $target) -ne ([string]$action.sha256).ToUpperInvariant()) { throw "Selected duplicate target is invalid: $target" }
            }
            'skip_target_duplicate' {
                [void](Assert-POExpectedFile -Path $source -SizeBytes ([int64]$action.size_bytes) -LastWriteUtc $action.last_write_utc -Sha256 $action.sha256)
                if ((Get-POStableSha256 -Path $target) -ne ([string]$action.sha256).ToUpperInvariant()) { throw "Existing target duplicate changed: $target" }
            }
            'exclude_cache' { }
            'preserve_git_metadata' { }
            default { throw "Unsupported action: $($action.action)" }
        }
        $state.completed_action_ids = @($state.completed_action_ids) + $id
        $state.failed_action_id = ''
        Save-ExecutionState -State $state -Path $statePath
        Add-POJsonLine -Path $logPath -Value ([ordered]@{ event='complete'; action_id=$id; action=$action.action })
        $completedThisRun++
        if ($StopAfterActions -gt 0 -and $completedThisRun -ge $StopAfterActions) { throw 'PO_TEST_STOP_AFTER_ACTIONS' }
    }
    catch {
        if ($_.Exception.Message -eq 'PO_TEST_STOP_AFTER_ACTIONS') { throw }
        $state.failed_action_id = $id
        Save-ExecutionState -State $state -Path $statePath
        Add-POJsonLine -Path $logPath -Value ([ordered]@{ event='failed'; action_id=$id; action=$action.action; error=$_.Exception.Message; rollback='automatic_only_when_move_verification_failed' })
        throw
    }
}

$state.complete = $true
Save-ExecutionState -State $state -Path $statePath
$summary = [ordered]@{
    schema_version='1.0'; plan_sha256=$approved; planned_actions=$actions.Count
    completed_actions=@($state.completed_action_ids).Count; active_git=@($state.active_git); complete=$true
}
Write-POJson -Path (Join-Path $output 'execution-summary.json') -Value $summary
Write-Output "Execution complete: $($actions.Count) actions."
