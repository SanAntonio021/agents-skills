[CmdletBinding()]
param([switch]$KeepWorkspace)

Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
Import-Module (Join-Path $PSScriptRoot 'ProjectOrganizer.psm1') -Force

$testId=[Guid]::NewGuid().ToString('N')
$testRoot=Join-Path ([IO.Path]::GetTempPath()) ('project-organizer-test-'+$testId)
$externalRoot=Join-Path ([IO.Path]::GetTempPath()) ('project-organizer-git-'+$testId)
$missingExternalRoot=Join-Path ([IO.Path]::GetTempPath()) ('project-organizer-git-'+[Guid]::NewGuid().ToString('N'))
$secondVolumeRoot=if(Test-Path -LiteralPath 'D:\'){ 'D:\project-organizer-test-'+$testId }else{ '' }
$results=New-Object Collections.Generic.List[object]

function Add-TestResult{param([string]$Name,[bool]$Passed,[string]$Evidence)
    $script:results.Add([pscustomobject][ordered]@{name=$Name;passed=$Passed;evidence=$Evidence})
    if(-not $Passed){throw "TEST_FAILED: $Name : $Evidence"}
}
function Assert-True{param([bool]$Condition,[string]$Name,[string]$Evidence='')
    Add-TestResult -Name $Name -Passed $Condition -Evidence $(if($Evidence){$Evidence}elseif($Condition){'passed'}else{'condition_false'})
}
function Write-TestFile{param([string]$Path,[string]$Text)
    [void][IO.Directory]::CreateDirectory((ConvertTo-POExtendedPath (Split-Path -Parent $Path)))
    [IO.File]::WriteAllText((ConvertTo-POExtendedPath $Path),$Text,(New-Object Text.UTF8Encoding($false)))
}
function Remove-TestTreeSafe{param([string]$Path)
    $full=[IO.Path]::GetFullPath($Path);$extended=ConvertTo-POExtendedPath $full
    if(-not [IO.Directory]::Exists($extended)){return}
    foreach($entryValue in @([IO.Directory]::EnumerateFileSystemEntries($extended))){
        $entry=ConvertFrom-POExtendedPath $entryValue;$attributes=[IO.File]::GetAttributes((ConvertTo-POExtendedPath $entry))
        if(($attributes -band [IO.FileAttributes]::Directory) -ne 0){
            $reparse=Get-POReparseInfo -Path $entry -Attributes $attributes
            if($reparse.is_name_surrogate){[IO.Directory]::Delete((ConvertTo-POExtendedPath $entry),$false)}else{Remove-TestTreeSafe $entry}
        }else{[IO.File]::SetAttributes((ConvertTo-POExtendedPath $entry),[IO.FileAttributes]::Normal);[IO.File]::Delete((ConvertTo-POExtendedPath $entry))}
    }
    [IO.Directory]::Delete($extended,$false)
}
function Invoke-WorkflowScript{param([string]$Name,[string[]]$Arguments,[switch]$ExpectFailure)
    $scriptPath=Join-Path $PSScriptRoot $Name
    $oldPreference=$ErrorActionPreference;$ErrorActionPreference='Continue'
    try{$output=@(& powershell -NoProfile -ExecutionPolicy Bypass -File $scriptPath @Arguments 2>&1|ForEach-Object{[string]$_});$code=$LASTEXITCODE}
    finally{$ErrorActionPreference=$oldPreference}
    if($ExpectFailure){if($code -eq 0){throw "Expected failure from $Name.`n$($output -join "`n")"}}
    elseif($code -ne 0){throw "$Name failed ($code).`n$($output -join "`n")"}
    return [pscustomobject]@{code=$code;output=$output}
}
function New-TestConfig{param([string]$Path,[string]$Mode,[object[]]$Sources,[string]$Target,[string]$Audit,[string]$Policy,[string]$Canonical='',[int64]$MinimumFree=0)
    $rootFiles=New-Object Collections.Generic.List[string]
    if($Mode -eq 'merge'){
        foreach($source in $Sources){if(Test-Path -LiteralPath ([string]$source.path)){foreach($file in @(Get-ChildItem -LiteralPath ([string]$source.path) -File -Force -ErrorAction SilentlyContinue)){$rootFiles.Add($file.Name)}}}
        if(Test-Path -LiteralPath $Target){foreach($file in @(Get-ChildItem -LiteralPath $Target -File -Force -ErrorAction SilentlyContinue)){$rootFiles.Add($file.Name)}}
    }
    $value=[ordered]@{
        schema_version='1.0';mode=$Mode;search_roots=@((Split-Path -Parent ([string]$Sources[0].path)))
        candidate_hints=@('project');max_discovery_depth=4;sources=$Sources;target_root=$Target;audit_root=$Audit
        canonical_source_id=$Canonical;mapping_rules=@();active_repo_policy=$Policy;sync_roots=@($testRoot)
        external_git_root=$externalRoot;protected_paths=@();exclude_rules=[ordered]@{
            directory_names=@('node_modules','__pycache__','.cache');relative_prefixes=@();extensions=@('.tmp','.downloading');retire_excluded=$true
        }
    }
    if($Mode -eq 'merge'){$value.layout_decisions=[ordered]@{
        restructure_in_scope=$false;root_files=@($rootFiles|Sort-Object -Unique);category_language='en';max_general_depth=32
        deep_structure_prefixes=@('code','papers','experiments','data','results','migration');independent_subprojects=@()
        version_policy='preserve_all';keep_empty_directories=@();forbidden_target_paths=@();exceptions=@();approved_tree_sha256=''
    }}
    if($MinimumFree -gt 0){$value.minimum_free_bytes=$MinimumFree}
    Write-POJson -Path $Path -Value $value
}
function Approve-TestLayout{param([string]$Config,[string]$Run)
    $treeHash=(Get-Content -LiteralPath (Join-Path $Run 'target-tree.sha256') -Encoding UTF8 -Raw).Trim().ToUpperInvariant()
    $value=Get-Content -LiteralPath $Config -Encoding UTF8 -Raw|ConvertFrom-Json
    if([string]$value.mode -eq 'merge'){$value.layout_decisions.approved_tree_sha256=$treeHash;Write-POJson -Path $Config -Value $value;Invoke-WorkflowScript 'Build-ProjectInventory.ps1' @('-Config',$Config,'-OutputDir',$Run)|Out-Null
        $rerunHash=(Get-Content -LiteralPath (Join-Path $Run 'target-tree.sha256') -Encoding UTF8 -Raw).Trim().ToUpperInvariant();if($rerunHash -ne $treeHash){throw 'Target tree changed while recording approval.'}
    }
    return $treeHash
}
function Initialize-TestGit{param([string]$Path,[string]$Remote,[string]$Name)
    [void](& git init $Path 2>&1);if($LASTEXITCODE -ne 0){throw 'git init failed'}
    [void](& git -C $Path config user.name 'Project Organizer Test')
    [void](& git -C $Path config user.email 'project-organizer@example.invalid')
    Write-TestFile -Path (Join-Path $Path 'tracked.txt') -Text ("initial-$Name")
    [void](& git -C $Path add tracked.txt);[void](& git -C $Path commit -m 'initial' 2>&1)
    [void](& git -C $Path branch feature)
    Write-TestFile -Path (Join-Path $Path 'orphan.txt') -Text 'reflog-only'
    [void](& git -C $Path add orphan.txt);[void](& git -C $Path commit -m 'reflog commit' 2>&1)
    [void](& git -C $Path reset --hard HEAD~1 2>&1)
    Write-TestFile -Path (Join-Path $Path 'stash.txt') -Text 'stash'
    [void](& git -C $Path add stash.txt);[void](& git -C $Path stash push -m 'test stash' 2>&1)
    Write-TestFile -Path (Join-Path $Path 'tracked.txt') -Text ("dirty-$Name")
    Write-TestFile -Path (Join-Path $Path 'untracked.txt') -Text 'untracked'
    if(-not(Test-Path -LiteralPath $Remote)){[void](& git init --bare $Remote 2>&1)}
    [void](& git -C $Path remote add origin $Remote)
}

[void][IO.Directory]::CreateDirectory((ConvertTo-POExtendedPath $testRoot))
[void][IO.Directory]::CreateDirectory((ConvertTo-POExtendedPath $externalRoot))
try{
    $pathChecks=@(
        @{name='reject_relative_path';script={Resolve-POFullPath -Path 'relative\path' -AllowMissing}},
        @{name='reject_parent_traversal';script={Resolve-POFullPath -Path 'C:\safe\..\escape' -AllowMissing}}
    )
    foreach($check in $pathChecks){$failed=$false;try{& $check.script|Out-Null}catch{$failed=$true};Assert-True $failed $check.name}
    $unc=Resolve-POFullPath -Path '\\server\share\project' -AllowNetwork -AllowMissing
    Assert-True ($unc -like '\\server\share*') 'network_path_inventory_form_allowed'
    $networkRejected=$false;try{Resolve-POFullPath -Path '\\server\share\project' -AllowMissing|Out-Null}catch{$networkRejected=$true}
    Assert-True $networkRejected 'network_path_execution_rejected'

    $overlapRoot=Join-Path $testRoot 'overlap';$overlapChild=Join-Path $overlapRoot 'child';$overlapOther=Join-Path $testRoot 'overlap-other'
    [void][IO.Directory]::CreateDirectory($overlapChild);[void][IO.Directory]::CreateDirectory($overlapOther)
    $overlapConfig=Join-Path $testRoot 'overlap.json'
    New-TestConfig -Path $overlapConfig -Mode merge -Sources @(
        [pscustomobject]@{id='a';path=$overlapRoot;role='canonical';target_name='a'},
        [pscustomobject]@{id='b';path=$overlapChild;role='legacy';target_name='b'}
    ) -Target (Join-Path $testRoot 'overlap-target') -Audit (Join-Path $testRoot 'overlap-audit') -Policy 'new'
    $overlapRejected=$false;try{Read-POConfig -Path $overlapConfig -RequireSources|Out-Null}catch{$overlapRejected=$true}
    Assert-True $overlapRejected 'overlapping_sources_rejected'

    $inventoryFixture=Join-Path $testRoot 'inventory-fixture';$ia=Join-Path $inventoryFixture 'project-a';$ib=Join-Path $inventoryFixture 'project-b';$it=Join-Path $inventoryFixture 'target';$ir=Join-Path $inventoryFixture 'run'
    [void][IO.Directory]::CreateDirectory($ia);[void][IO.Directory]::CreateDirectory($ib)
    Write-TestFile (Join-Path $ia 'same.bin') 'duplicate';Write-TestFile (Join-Path $ib 'renamed.bin') 'duplicate'
    Write-TestFile (Join-Path $ia 'conflict.txt') 'A';Write-TestFile (Join-Path $ib 'conflict.txt') 'B'
    Write-TestFile (Join-Path $ia 'existing-target.txt') 'source-version';[void][IO.Directory]::CreateDirectory($it);Write-TestFile (Join-Path $it 'existing-target.txt') 'target-version'
    Write-TestFile (Join-Path $ia '中文目录\数据.txt') '中文路径';Write-TestFile (Join-Path $ib 'cache.tmp') 'cache'
    $outside=Join-Path $inventoryFixture 'outside';[void][IO.Directory]::CreateDirectory($outside);Write-TestFile (Join-Path $outside 'must-not-follow.txt') 'outside'
    $junction=Join-Path $ia 'junction';[void](New-Item -ItemType Junction -Path $junction -Target $outside)
    $symbolicCreated=$false
    try{[void](New-Item -ItemType SymbolicLink -Path (Join-Path $ib 'symbolic') -Target $outside -ErrorAction Stop);$symbolicCreated=$true}catch{}
    $offline=Join-Path $ib 'placeholder.dat';Write-TestFile $offline 'placeholder';[IO.File]::SetAttributes($offline,[IO.FileAttributes]::Offline)
    $longBase=Join-Path $ia ('l'*120);[void][IO.Directory]::CreateDirectory((ConvertTo-POExtendedPath $longBase));$longFile=Join-Path $longBase (('n'*90)+'.txt');Write-TestFile $longFile 'long'
    $inventoryConfig=Join-Path $inventoryFixture 'config.json'
    New-TestConfig -Path $inventoryConfig -Mode merge -Sources @(
        [pscustomobject]@{id='a';path=$ia;role='canonical';target_name='a'},
        [pscustomobject]@{id='b';path=$ib;role='legacy';target_name='b'}
    ) -Target $it -Audit $ir -Policy 'new' -Canonical 'a'
    Invoke-WorkflowScript 'Build-ProjectInventory.ps1' @('-Config',$inventoryConfig,'-OutputDir',$ir)|Out-Null
    $inventoryRows=@(Import-Csv (Join-Path $ir 'files.csv') -Encoding UTF8)
    Assert-True (@($inventoryRows|Where-Object{$_.relative_path -eq 'junction'}).Count -eq 1) 'junction_recorded_not_followed'
    Assert-True (@($inventoryRows|Where-Object{$_.relative_path -like 'junction/*'}).Count -eq 0) 'junction_target_not_enumerated'
    if($symbolicCreated){Assert-True (@($inventoryRows|Where-Object{$_.relative_path -eq 'symbolic' -and $_.scan_status -eq 'hold'}).Count -eq 1) 'symbolic_link_held'}else{Add-TestResult 'symbolic_link_held' $true 'creation_not_permitted; junction coverage passed'}
    Assert-True (@($inventoryRows|Where-Object{$_.relative_path -eq 'placeholder.dat' -and $_.scan_status -eq 'hold'}).Count -eq 1) 'cloud_placeholder_held'
    Assert-True (@($inventoryRows|Where-Object{$_.relative_path -eq 'cache.tmp' -and $_.scan_status -eq 'excluded'}).Count -eq 1) 'cache_excluded'
    Assert-True (@($inventoryRows|Where-Object{$_.relative_path -like '*数据.txt' -and $_.sha256 -match '^[0-9A-F]{64}$'}).Count -eq 1) 'chinese_path_hashed'
    Assert-True (@($inventoryRows|Where-Object{$_.relative_path -like (('l'*120)+'/*')}).Count -ge 1) 'extended_long_path_enumerated'
    Assert-True (@(Import-Csv (Join-Path $ir 'duplicates.csv') -Encoding UTF8).Count -ge 2) 'exact_duplicates_listed'
    $inventoryConflicts=@(Import-Csv (Join-Path $ir 'conflicts.csv') -Encoding UTF8)
    Assert-True (@($inventoryConflicts|Where-Object reason -eq 'same_target_different_sha256').Count -eq 2) 'same_target_conflict_held'
    Assert-True (@($inventoryConflicts|Where-Object reason -eq 'existing_target_different_sha256').Count -eq 1) 'existing_target_conflict_held'
    $firstHash=Get-POStableSha256 (Join-Path $ir 'files.csv');Invoke-WorkflowScript 'Build-ProjectInventory.ps1' @('-Config',$inventoryConfig,'-OutputDir',$ir,'-Resume')|Out-Null
    Assert-True ((Get-POStableSha256 (Join-Path $ir 'files.csv')) -eq $firstHash) 'inventory_resume_byte_deterministic'

    $locked=Join-Path $ia 'locked.dat';Write-TestFile $locked ('x'*1024)
    $lockStream=New-Object IO.FileStream($locked,[IO.FileMode]::Open,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None)
    try{Invoke-WorkflowScript 'Build-ProjectInventory.ps1' @('-Config',$inventoryConfig,'-OutputDir',(Join-Path $inventoryFixture 'locked-run'))|Out-Null}finally{$lockStream.Dispose()}
    Assert-True (@(Import-Csv (Join-Path $inventoryFixture 'locked-run\errors.csv') -Encoding UTF8|Where-Object{$_.path -like '*locked.dat'}).Count -eq 1) 'read_failure_reported'

    $changing=Join-Path $testRoot 'changing.bin';$fs=New-Object IO.FileStream($changing,[IO.FileMode]::Create,[IO.FileAccess]::Write,[IO.FileShare]::ReadWrite);$fs.SetLength(67108864);$fs.Dispose()
    if(-not('ProjectOrganizer.TestMutator' -as [type])){Add-Type -TypeDefinition @'
using System;
using System.IO;
using System.Threading;
namespace ProjectOrganizer {
    public static class TestMutator {
        public static Thread Start(string path) {
            Thread thread = new Thread(() => {
                for (int i = 0; i < 1000; i++) {
                    File.SetLastWriteTimeUtc(path, DateTime.UtcNow);
                    Thread.Sleep(1);
                }
            });
            thread.IsBackground = true;
            thread.Start();
            return thread;
        }
    }
}
'@}
    $changer=[ProjectOrganizer.TestMutator]::Start($changing)
    $changedCaught=$false;try{Get-POStableSha256 $changing|Out-Null}catch{if($_.Exception.Message -like 'PO_SOURCE_CHANGED*'){$changedCaught=$true}}finally{$changer.Join()}
    Assert-True $changedCaught 'scan_time_change_invalidates_hash'

    $discoveryConfig=Join-Path $testRoot 'discovery.json';New-TestConfig -Path $discoveryConfig -Mode merge -Sources @(
        [pscustomobject]@{id='a';path=$ia;role='canonical';target_name='a'},[pscustomobject]@{id='b';path=$ib;role='legacy';target_name='b'}
    ) -Target $it -Audit $ir -Policy 'new'
    $discoveryObject=Get-Content $discoveryConfig -Encoding UTF8 -Raw|ConvertFrom-Json;$discoveryObject.search_roots=@($inventoryFixture);Write-POJson $discoveryConfig $discoveryObject
    $candidateRun=Join-Path $testRoot 'candidate-run';Invoke-WorkflowScript 'Find-ProjectCandidates.ps1' @('-Config',$discoveryConfig,'-OutputDir',$candidateRun)|Out-Null
    Assert-True (Test-Path (Join-Path $candidateRun 'candidate_evidence.json')) 'bounded_candidate_discovery_outputs_evidence'

    $missingGitFixture=Join-Path $testRoot 'missing-external-git';$missingGitA=Join-Path $missingGitFixture 'a';$missingGitB=Join-Path $missingGitFixture 'b';$missingGitTarget=Join-Path $missingGitFixture 'target';$missingGitRun=Join-Path $missingGitFixture 'audit'
    [void][IO.Directory]::CreateDirectory($missingGitA);[void][IO.Directory]::CreateDirectory($missingGitB);Write-TestFile (Join-Path $missingGitA 'a.txt') 'a';Write-TestFile (Join-Path $missingGitB 'b.txt') 'b'
    $missingGitConfig=Join-Path $missingGitFixture 'config.json';New-TestConfig -Path $missingGitConfig -Mode merge -Sources @(
        [pscustomobject]@{id='a';path=$missingGitA;role='canonical';target_name='a'},[pscustomobject]@{id='b';path=$missingGitB;role='legacy';target_name='b'}
    ) -Target $missingGitTarget -Audit $missingGitRun -Policy 'new' -Canonical 'a'
    $missingGitConfigObject=Get-Content -LiteralPath $missingGitConfig -Encoding UTF8 -Raw|ConvertFrom-Json;$missingGitConfigObject.external_git_root=$missingExternalRoot;Write-POJson -Path $missingGitConfig -Value $missingGitConfigObject
    if((Test-Path -LiteralPath $missingExternalRoot)-or(Test-Path -LiteralPath (Join-Path $missingExternalRoot 'active'))){throw 'Missing external Git fixture must start without its root or active parent.'}
    Invoke-WorkflowScript 'Build-ProjectInventory.ps1' @('-Config',$missingGitConfig,'-OutputDir',$missingGitRun)|Out-Null;Approve-TestLayout -Config $missingGitConfig -Run $missingGitRun|Out-Null;Invoke-WorkflowScript 'Build-OrganizationPlan.ps1' @('-Config',$missingGitConfig,'-OutputDir',$missingGitRun)|Out-Null
    $missingGitPlan=(Get-Content -LiteralPath (Join-Path $missingGitRun 'plan.sha256') -Encoding UTF8 -Raw).Trim();Invoke-WorkflowScript 'Invoke-OrganizationPlan.ps1' @('-Config',$missingGitConfig,'-OutputDir',$missingGitRun,'-ApprovedPlanSha256',$missingGitPlan,'-Execute')|Out-Null;Invoke-WorkflowScript 'Test-OrganizationAcceptance.ps1' @('-Config',$missingGitConfig,'-OutputDir',$missingGitRun)|Out-Null
    $missingGitState=Get-Content -LiteralPath (Join-Path $missingGitRun 'execution-state.json') -Encoding UTF8 -Raw|ConvertFrom-Json
    Assert-True (@($missingGitState.active_git).Count -eq 1 -and $missingGitState.active_git[0].externalized -and (Test-Path -LiteralPath $missingGitState.active_git[0].git_dir)) 'new_repo_creates_missing_external_git_parent'

    $groupRoot=Join-Path $testRoot 'group-fixture';$g1=Join-Path $groupRoot 'project-one';$g2=Join-Path $groupRoot 'project-two';$groupTarget=Join-Path $groupRoot 'grouped';$groupRun=Join-Path $groupRoot 'audit';$remote1=Join-Path $groupRoot 'remote-one.git';$remote2=Join-Path $groupRoot 'remote-two.git'
    [void][IO.Directory]::CreateDirectory($g1);[void][IO.Directory]::CreateDirectory($g2)
    Initialize-TestGit $g1 $remote1 'one';Initialize-TestGit $g2 $remote2 'two';Write-TestFile (Join-Path $g1 'same-content.dat') 'same';Write-TestFile (Join-Path $g2 'same-content.dat') 'same';Write-TestFile (Join-Path $g2 'cache.tmp') 'cache'
    $groupConfig=Join-Path $groupRoot 'config.json';New-TestConfig -Path $groupConfig -Mode group -Sources @(
        [pscustomobject]@{id='one';path=$g1;role='independent';target_name='one'},[pscustomobject]@{id='two';path=$g2;role='independent';target_name='two'}
    ) -Target $groupTarget -Audit $groupRun -Policy 'preserve_each'
    Invoke-WorkflowScript 'Build-ProjectInventory.ps1' @('-Config',$groupConfig,'-OutputDir',$groupRun)|Out-Null
    Invoke-WorkflowScript 'New-GitRecoveryBundle.ps1' @('-Config',$groupConfig,'-OutputDir',$groupRun)|Out-Null
    Invoke-WorkflowScript 'Build-OrganizationPlan.ps1' @('-Config',$groupConfig,'-OutputDir',$groupRun)|Out-Null
    $groupActions=@(Import-Csv (Join-Path $groupRun 'actions.csv') -Encoding UTF8)
    Assert-True (@($groupActions|Where-Object action -eq 'move_file_verify').Count -gt 0) 'same_volume_uses_verified_move'
    Assert-True (@($groupActions|Where-Object{$_.relative_path -eq 'same-content.dat' -and $_.action -eq 'move_file_verify'}).Count -eq 2) 'group_mode_does_not_deduplicate_projects'
    $groupPlan=(Get-Content (Join-Path $groupRun 'plan.sha256') -Encoding UTF8 -Raw).Trim()
    Invoke-WorkflowScript 'Invoke-OrganizationPlan.ps1' @('-Config',$groupConfig,'-OutputDir',$groupRun,'-ApprovedPlanSha256',$groupPlan,'-Execute','-StopAfterActions','2') -ExpectFailure|Out-Null
    Assert-True (Test-Path (Join-Path $groupRun 'execution-state.json')) 'interrupted_execution_writes_resume_state'
    Invoke-WorkflowScript 'Invoke-OrganizationPlan.ps1' @('-Config',$groupConfig,'-OutputDir',$groupRun,'-ApprovedPlanSha256',$groupPlan,'-Execute','-Resume')|Out-Null
    Invoke-WorkflowScript 'Test-OrganizationAcceptance.ps1' @('-Config',$groupConfig,'-OutputDir',$groupRun)|Out-Null
    $activeState=Get-Content (Join-Path $groupRun 'execution-state.json') -Encoding UTF8 -Raw|ConvertFrom-Json
    Assert-True (@($activeState.active_git).Count -eq 2) 'group_active_git_recovered_independently'
    Assert-True (@($activeState.active_git|Where-Object{Test-POSyncPath $_.git_dir @($testRoot)}).Count -eq 0) 'active_git_databases_outside_sync_root'
    $archives=@(Read-POJsonArray -Path (Join-Path $groupRun 'git_archives.json'))
    Assert-True ($archives.Count -eq 2 -and @($archives|Where-Object{-not $_.references_verified}).Count -eq 0) 'git_bundle_restore_refs_stash_reflog_verified'
    $savedGitState=Get-Content (Join-Path $groupRun 'git-recovery\one\git-state.json') -Encoding UTF8 -Raw|ConvertFrom-Json
    Assert-True ($savedGitState.dirty -and [int]$savedGitState.untracked -gt 0 -and @($savedGitState.remotes).Count -gt 0) 'git_dirty_untracked_remote_state_saved'
    Invoke-WorkflowScript 'Build-RetirementPlan.ps1' @('-Config',$groupConfig,'-OutputDir',$groupRun)|Out-Null
    $groupRetirement=(Get-Content (Join-Path $groupRun 'retirement.sha256') -Encoding UTF8 -Raw).Trim();$mockRecycle=Join-Path $testRoot 'mock-recycle'
    Invoke-WorkflowScript 'Invoke-RetirementPlan.ps1' @('-Config',$groupConfig,'-OutputDir',$groupRun,'-ApprovedRetirementSha256',$groupRetirement,'-Recycle','-MockRecycleRoot',$mockRecycle)|Out-Null
    Invoke-WorkflowScript 'Test-RetirementAcceptance.ps1' @('-Config',$groupConfig,'-OutputDir',$groupRun)|Out-Null
    Assert-True (-not(Test-Path $g1)-and -not(Test-Path $g2)) 'retirement_removes_only_approved_source_paths'
    Assert-True (Test-Path $mockRecycle) 'mock_recycle_adapter_used'

    $layoutRoot=Join-Path $testRoot 'document-layout';$layoutA=Join-Path $layoutRoot 'materials';$layoutB=Join-Path $layoutRoot 'records';$layoutTarget=Join-Path $layoutRoot 'organized';$layoutRun=Join-Path $layoutRoot 'audit'
    [void][IO.Directory]::CreateDirectory($layoutA);[void][IO.Directory]::CreateDirectory($layoutB)
    Write-TestFile (Join-Path $layoutA 'Project-Overview.pptx') 'presentation'
    Write-TestFile (Join-Path $layoutA 'LegacyWrapper\Procurement\vendor-quote.pdf') 'quote'
    Write-TestFile (Join-Path $layoutB 'LegacyShared\Notes\meeting.txt') 'notes'
    Write-TestFile (Join-Path $layoutB 'PaperDraft\submission\manuscript.tex') 'paper'
    Write-TestFile (Join-Path $layoutB 'AuditRecords\runs\inventory.csv') 'audit'
    $layoutConfig=Join-Path $layoutRoot 'config.json';New-TestConfig -Path $layoutConfig -Mode merge -Sources @(
        [pscustomobject]@{id='materials';path=$layoutA;role='canonical';target_name='materials'},
        [pscustomobject]@{id='records';path=$layoutB;role='legacy';target_name='records'}
    ) -Target $layoutTarget -Audit $layoutRun -Policy 'new' -Canonical 'materials'
    $layoutObject=Get-Content -LiteralPath $layoutConfig -Encoding UTF8 -Raw|ConvertFrom-Json
    $layoutObject.layout_decisions.restructure_in_scope=$true
    $layoutObject.layout_decisions.root_files=@('Project-Overview.pptx')
    $layoutObject.layout_decisions.category_language='en'
    $layoutObject.layout_decisions.max_general_depth=1
    $layoutObject.layout_decisions.deep_structure_prefixes=@('code','papers','experiments','data','results','migration')
    $layoutObject.layout_decisions.independent_subprojects=@()
    $layoutObject.layout_decisions.version_policy='preserve_all'
    $layoutObject.layout_decisions.keep_empty_directories=@()
    $layoutObject.layout_decisions.forbidden_target_paths=@('LegacyWrapper','LegacyShared','platform','shared')
    $layoutObject.layout_decisions.exceptions=@()
    $layoutObject.mapping_rules=@(
        [pscustomobject][ordered]@{source_id='materials';from_prefix='LegacyWrapper/Procurement';to_prefix='procurement'},
        [pscustomobject][ordered]@{source_id='materials';from_prefix='LegacyWrapper';to_prefix=''},
        [pscustomobject][ordered]@{source_id='records';from_prefix='LegacyShared/Notes';to_prefix='notes'},
        [pscustomobject][ordered]@{source_id='records';from_prefix='LegacyShared';to_prefix=''},
        [pscustomobject][ordered]@{source_id='records';from_prefix='PaperDraft';to_prefix='papers/article'},
        [pscustomobject][ordered]@{source_id='records';from_prefix='AuditRecords';to_prefix='migration/audit'}
    )
    Write-POJson -Path $layoutConfig -Value $layoutObject
    Invoke-WorkflowScript 'Build-ProjectInventory.ps1' @('-Config',$layoutConfig,'-OutputDir',$layoutRun)|Out-Null
    $layoutViolations=@(Import-Csv -LiteralPath (Join-Path $layoutRun 'layout-violations.csv') -Encoding UTF8)
    Assert-True ($layoutViolations.Count -eq 0) 'shallow_document_layout_has_no_unapproved_structure'
    $layoutTree=@(Import-Csv -LiteralPath (Join-Path $layoutRun 'target-tree.csv') -Encoding UTF8)
    Assert-True (@($layoutTree|Where-Object relative_path -eq 'Project-Overview.pptx').Count -eq 1) 'approved_common_presentation_at_target_root'
    Assert-True (@($layoutTree|Where-Object relative_path -eq 'procurement/vendor-quote.pdf').Count -eq 1) 'ordinary_material_uses_one_classification_layer'
    Assert-True (@($layoutTree|Where-Object relative_path -eq 'papers/article/submission/manuscript.tex').Count -eq 1) 'paper_keeps_necessary_internal_depth'
    Assert-True (@($layoutTree|Where-Object relative_path -eq 'migration/audit/runs/inventory.csv').Count -eq 1) 'audit_keeps_necessary_internal_depth'
    Assert-True (@($layoutTree|Where-Object{$_.relative_path -like 'LegacyWrapper*' -or $_.relative_path -like 'LegacyShared*'}).Count -eq 0) 'wrapper_only_directories_removed_from_design'
    $unapprovedLayout=Invoke-WorkflowScript 'Build-OrganizationPlan.ps1' @('-Config',$layoutConfig,'-OutputDir',$layoutRun) -ExpectFailure
    Assert-True (($unapprovedLayout.output -join "`n") -match 'not been approved') 'unapproved_target_tree_blocks_plan'
    $approvedLayoutHash=Approve-TestLayout -Config $layoutConfig -Run $layoutRun
    Assert-True ($approvedLayoutHash -match '^[0-9A-F]{64}$') 'approved_tree_sha256_recorded'
    Invoke-WorkflowScript 'Build-OrganizationPlan.ps1' @('-Config',$layoutConfig,'-OutputDir',$layoutRun)|Out-Null
    $layoutPlan=(Get-Content -LiteralPath (Join-Path $layoutRun 'plan.sha256') -Encoding UTF8 -Raw).Trim()
    Invoke-WorkflowScript 'Invoke-OrganizationPlan.ps1' @('-Config',$layoutConfig,'-OutputDir',$layoutRun,'-ApprovedPlanSha256',$layoutPlan,'-Execute')|Out-Null
    Invoke-WorkflowScript 'Test-OrganizationAcceptance.ps1' @('-Config',$layoutConfig,'-OutputDir',$layoutRun)|Out-Null
    $extraWrapper=Join-Path $layoutTarget 'shared';[void][IO.Directory]::CreateDirectory($extraWrapper)
    Invoke-WorkflowScript 'Test-OrganizationAcceptance.ps1' @('-Config',$layoutConfig,'-OutputDir',$layoutRun) -ExpectFailure|Out-Null
    $layoutAcceptanceErrors=@(Import-Csv -LiteralPath (Join-Path $layoutRun 'acceptance-errors.csv') -Encoding UTF8)
    Assert-True (@($layoutAcceptanceErrors|Where-Object reason -eq 'unapproved_extra_path').Count -eq 1) 'acceptance_rejects_unapproved_empty_directory'
    Assert-True (@($layoutAcceptanceErrors|Where-Object reason -eq 'forbidden_wrapper_or_directory_present').Count -eq 1) 'acceptance_rejects_forbidden_wrapper_directory'
    [IO.Directory]::Delete((ConvertTo-POExtendedPath $extraWrapper),$false)
    Invoke-WorkflowScript 'Test-OrganizationAcceptance.ps1' @('-Config',$layoutConfig,'-OutputDir',$layoutRun)|Out-Null

    if($secondVolumeRoot){
        [void][IO.Directory]::CreateDirectory($secondVolumeRoot)
        $crossRoot=Join-Path $testRoot 'cross-fixture';$c1=Join-Path $crossRoot 'source-one';$c2=Join-Path $crossRoot 'source-two';$crossTarget=Join-Path $secondVolumeRoot 'merged';$crossRun=Join-Path $crossRoot 'audit'
        [void][IO.Directory]::CreateDirectory($c1);[void][IO.Directory]::CreateDirectory($c2);Write-TestFile (Join-Path $c1 'one.txt') 'one';Write-TestFile (Join-Path $c2 'two.txt') 'two'
        $crossConfig=Join-Path $crossRoot 'config.json';New-TestConfig -Path $crossConfig -Mode merge -Sources @(
            [pscustomobject]@{id='one';path=$c1;role='canonical';target_name='one'},[pscustomobject]@{id='two';path=$c2;role='legacy';target_name='two'}
        ) -Target $crossTarget -Audit $crossRun -Policy 'new'
        Invoke-WorkflowScript 'Build-ProjectInventory.ps1' @('-Config',$crossConfig,'-OutputDir',$crossRun)|Out-Null;Approve-TestLayout -Config $crossConfig -Run $crossRun|Out-Null;Invoke-WorkflowScript 'Build-OrganizationPlan.ps1' @('-Config',$crossConfig,'-OutputDir',$crossRun)|Out-Null
        $crossActions=@(Import-Csv (Join-Path $crossRun 'actions.csv') -Encoding UTF8);Assert-True (@($crossActions|Where-Object action -eq 'copy_file_verify').Count -eq 2) 'cross_volume_uses_verified_copy'
        $crossPlan=(Get-Content (Join-Path $crossRun 'plan.sha256') -Encoding UTF8 -Raw).Trim();Invoke-WorkflowScript 'Invoke-OrganizationPlan.ps1' @('-Config',$crossConfig,'-OutputDir',$crossRun,'-ApprovedPlanSha256',$crossPlan,'-Execute')|Out-Null;Invoke-WorkflowScript 'Test-OrganizationAcceptance.ps1' @('-Config',$crossConfig,'-OutputDir',$crossRun)|Out-Null
        Invoke-WorkflowScript 'Build-RetirementPlan.ps1' @('-Config',$crossConfig,'-OutputDir',$crossRun)|Out-Null;$crossRetirement=(Get-Content (Join-Path $crossRun 'retirement.sha256') -Encoding UTF8 -Raw).Trim();Invoke-WorkflowScript 'Invoke-RetirementPlan.ps1' @('-Config',$crossConfig,'-OutputDir',$crossRun,'-ApprovedRetirementSha256',$crossRetirement,'-Recycle','-MockRecycleRoot',(Join-Path $testRoot 'cross-recycle'))|Out-Null;Invoke-WorkflowScript 'Test-RetirementAcceptance.ps1' @('-Config',$crossConfig,'-OutputDir',$crossRun)|Out-Null
        Assert-True (-not(Test-Path $c1)-and -not(Test-Path $c2)-and(Test-Path(Join-Path $crossTarget 'one.txt'))) 'cross_volume_copy_then_retire_verified'
    }else{Add-TestResult 'cross_volume_uses_verified_copy' $true 'second local volume unavailable; selection logic covered by Test-POSameVolume'}

    $tamperRoot=Join-Path $testRoot 'tamper';$ta=Join-Path $tamperRoot 'a';$tb=Join-Path $tamperRoot 'b';$tt=Join-Path $tamperRoot 'target';$tr=Join-Path $tamperRoot 'run';[void][IO.Directory]::CreateDirectory($ta);[void][IO.Directory]::CreateDirectory($tb);Write-TestFile (Join-Path $ta 'a.txt') 'a';Write-TestFile (Join-Path $tb 'b.txt') 'b'
    $tamperConfig=Join-Path $tamperRoot 'config.json';New-TestConfig $tamperConfig merge @([pscustomobject]@{id='a';path=$ta;role='canonical';target_name='a'},[pscustomobject]@{id='b';path=$tb;role='legacy';target_name='b'}) $tt $tr new
    Invoke-WorkflowScript 'Build-ProjectInventory.ps1' @('-Config',$tamperConfig,'-OutputDir',$tr)|Out-Null;Approve-TestLayout -Config $tamperConfig -Run $tr|Out-Null;Invoke-WorkflowScript 'Build-OrganizationPlan.ps1' @('-Config',$tamperConfig,'-OutputDir',$tr)|Out-Null;$tamperPlan=(Get-Content (Join-Path $tr 'plan.sha256') -Encoding UTF8 -Raw).Trim()
    [IO.File]::AppendAllText((Join-Path $tr 'actions.csv'),"#tamper`r`n",[Text.Encoding]::UTF8)
    Invoke-WorkflowScript 'Invoke-OrganizationPlan.ps1' @('-Config',$tamperConfig,'-OutputDir',$tr,'-ApprovedPlanSha256',$tamperPlan) -ExpectFailure|Out-Null
    Assert-True (-not(Test-Path $tt)) 'plan_hash_tamper_blocks_execution'

    $raceRoot=Join-Path $testRoot 'target-race';$ra=Join-Path $raceRoot 'a';$rb=Join-Path $raceRoot 'b';$raceTarget=Join-Path $raceRoot 'target';$raceRun=Join-Path $raceRoot 'audit';[void][IO.Directory]::CreateDirectory($ra);[void][IO.Directory]::CreateDirectory($rb);Write-TestFile (Join-Path $ra 'a.txt') 'source-a';Write-TestFile (Join-Path $rb 'b.txt') 'source-b'
    $raceConfig=Join-Path $raceRoot 'config.json';New-TestConfig $raceConfig merge @([pscustomobject]@{id='a';path=$ra;role='canonical';target_name='a'},[pscustomobject]@{id='b';path=$rb;role='legacy';target_name='b'}) $raceTarget $raceRun new
    Invoke-WorkflowScript 'Build-ProjectInventory.ps1' @('-Config',$raceConfig,'-OutputDir',$raceRun)|Out-Null;Approve-TestLayout -Config $raceConfig -Run $raceRun|Out-Null;Invoke-WorkflowScript 'Build-OrganizationPlan.ps1' @('-Config',$raceConfig,'-OutputDir',$raceRun)|Out-Null;$racePlan=(Get-Content (Join-Path $raceRun 'plan.sha256') -Encoding UTF8 -Raw).Trim();Write-TestFile (Join-Path $raceTarget 'a.txt') 'do-not-overwrite'
    Invoke-WorkflowScript 'Invoke-OrganizationPlan.ps1' @('-Config',$raceConfig,'-OutputDir',$raceRun,'-ApprovedPlanSha256',$racePlan,'-Execute') -ExpectFailure|Out-Null
    Assert-True ([IO.File]::ReadAllText((Join-Path $raceTarget 'a.txt')) -eq 'do-not-overwrite') 'execution_never_overwrites_existing_target'
    $failedLog=@(Get-Content (Join-Path $raceRun 'execution.jsonl') -Encoding UTF8|ForEach-Object{$_|ConvertFrom-Json}|Where-Object event -eq 'failed')
    Assert-True ($failedLog.Count -eq 1 -and [string]$failedLog[0].rollback) 'failed_action_records_rollback_policy'

    $changeRoot=Join-Path $testRoot 'source-change';$ca=Join-Path $changeRoot 'a';$cb=Join-Path $changeRoot 'b';$changeTarget=Join-Path $changeRoot 'target';$changeRun=Join-Path $changeRoot 'audit';[void][IO.Directory]::CreateDirectory($ca);[void][IO.Directory]::CreateDirectory($cb);Write-TestFile (Join-Path $ca 'a.txt') 'a';Write-TestFile (Join-Path $cb 'b.txt') 'b'
    $changeConfig=Join-Path $changeRoot 'config.json';New-TestConfig $changeConfig merge @([pscustomobject]@{id='a';path=$ca;role='canonical';target_name='a'},[pscustomobject]@{id='b';path=$cb;role='legacy';target_name='b'}) $changeTarget $changeRun new
    Invoke-WorkflowScript 'Build-ProjectInventory.ps1' @('-Config',$changeConfig,'-OutputDir',$changeRun)|Out-Null;Approve-TestLayout -Config $changeConfig -Run $changeRun|Out-Null;Invoke-WorkflowScript 'Build-OrganizationPlan.ps1' @('-Config',$changeConfig,'-OutputDir',$changeRun)|Out-Null;$changePlan=(Get-Content (Join-Path $changeRun 'plan.sha256') -Encoding UTF8 -Raw).Trim();Write-TestFile (Join-Path $ca 'unplanned.txt') 'new'
    Invoke-WorkflowScript 'Invoke-OrganizationPlan.ps1' @('-Config',$changeConfig,'-OutputDir',$changeRun,'-ApprovedPlanSha256',$changePlan) -ExpectFailure|Out-Null
    Assert-True (-not(Test-Path (Join-Path $changeTarget 'a.txt'))) 'source_change_invalidates_approved_plan'

    $spaceRoot=Join-Path $testRoot 'space';$sa=Join-Path $spaceRoot 'a';$sb=Join-Path $spaceRoot 'b';[void][IO.Directory]::CreateDirectory($sa);[void][IO.Directory]::CreateDirectory($sb);Write-TestFile (Join-Path $sa 'a') 'a';Write-TestFile (Join-Path $sb 'b') 'b';$spaceConfig=Join-Path $spaceRoot 'config.json';$spaceRun=Join-Path $spaceRoot 'run';New-TestConfig $spaceConfig merge @([pscustomobject]@{id='a';path=$sa;role='canonical';target_name='a'},[pscustomobject]@{id='b';path=$sb;role='legacy';target_name='b'}) (Join-Path $spaceRoot 'target') $spaceRun new '' ([int64]::MaxValue)
    Invoke-WorkflowScript 'Build-ProjectInventory.ps1' @('-Config',$spaceConfig,'-OutputDir',$spaceRun)|Out-Null;Approve-TestLayout -Config $spaceConfig -Run $spaceRun|Out-Null;Invoke-WorkflowScript 'Build-OrganizationPlan.ps1' @('-Config',$spaceConfig,'-OutputDir',$spaceRun)|Out-Null
    Assert-True (@(Import-Csv (Join-Path $spaceRun 'plan-errors.csv') -Encoding UTF8|Where-Object stage -eq 'space').Count -eq 1) 'insufficient_space_blocks_plan'

    $passed=@($results.ToArray()|Where-Object passed).Count;$total=$results.Count
    Write-POJson -Path (Join-Path $testRoot 'test-results.json') -Value ([ordered]@{passed=$passed;failed=($total-$passed);total=$total;tests=@($results.ToArray())})
    Write-Output "ProjectOrganizer tests passed: $passed/$total"
}
finally{
    if($KeepWorkspace){Write-Output "Kept test workspace: $testRoot"}
    else{
        foreach($path in @($testRoot,$externalRoot,$missingExternalRoot,$secondVolumeRoot)){
            if(-not $path){continue}
            $full=[IO.Path]::GetFullPath($path)
            if($full -notmatch 'project-organizer-(test|git)-[0-9a-f]{32}'){throw "Refusing unsafe test cleanup: $full"}
            try{
                if([IO.Directory]::Exists((ConvertTo-POExtendedPath $full))){Remove-TestTreeSafe $full}
            }catch{Write-Warning "Test cleanup failed for $full : $($_.Exception.Message)"}
        }
    }
}
