[CmdletBinding()]
param([switch]$KeepWorkspace)

Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false)
$OutputEncoding=[Text.UTF8Encoding]::new($false)
Import-Module (Join-Path $PSScriptRoot 'ProjectOrganizer.psm1') -Force
$testRoot=Join-Path ([IO.Path]::GetTempPath()) ('project-integration-test-'+[guid]::NewGuid().ToString('N'))
$results=New-Object Collections.Generic.List[object]
$success=$false

function Write-FixtureText([string]$Path,[string]$Text){
    [void][IO.Directory]::CreateDirectory((Split-Path -Parent $Path))
    [IO.File]::WriteAllText($Path,$Text,[Text.UTF8Encoding]::new($false))
}
function Assert-Test([bool]$Condition,[string]$Name){
    $results.Add([pscustomobject]@{name=$Name;passed=$Condition})
    if(-not $Condition){throw "TEST_FAILED: $Name"}
}
function Invoke-Step([string]$Name,[object]$Fixture,[string[]]$Extra=@(),[switch]$Fail){
    $old=$ErrorActionPreference;$ErrorActionPreference='Continue'
    try{
        $lines=@(& powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot $Name) -Config $Fixture.Config -OutputDir $Fixture.Run @Extra 2>&1 | ForEach-Object{[string]$_})
        $code=$LASTEXITCODE
    }finally{$ErrorActionPreference=$old}
    if($Fail){if($code -eq 0){throw "Expected refusal from $Name"}}
    elseif($code -ne 0){throw "$Name failed ($code): $($lines -join "`n")"}
    return [pscustomobject]@{Code=$code;Text=($lines -join "`n")}
}
function New-IntegrationFixture([string]$Name,[switch]$SingleSource,[switch]$ExternalAudit){
    $root=Join-Path $testRoot $Name;$a=Join-Path $root 'old-a';$b=Join-Path $root 'old-b';$target=Join-Path $root 'project'
    $run=if($ExternalAudit){Join-Path $root 'audit'}else{Join-Path $target '过程文件/本轮整合'}
    $config=Join-Path $root 'config.json'
    Write-FixtureText (Join-Path $a 'README.md') "# Source A`nMethod: sum all observed values.`n"
    Write-FixtureText (Join-Path $target 'README.md') "# Current project`nUser note: keep calibrated units.`n"
    Write-FixtureText (Join-Path $target '过程文件/其他任务/notes.md') 'Unrelated process material must survive.'
    Write-FixtureText (Join-Path $a 'code/run.ps1') ('# Original data: '+(Join-Path $b 'data/values.csv')+"`nfunction Get-Total { param(`$Rows) (`$Rows | Measure-Object Value -Sum).Sum }`n")
    $dataSource=if($SingleSource){$a}else{$b}
    Write-FixtureText (Join-Path $dataSource 'data/values.csv') "Value`n1`n2`n3`n"
    $png=[Convert]::FromBase64String('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jA1sAAAAASUVORK5CYII=')
    foreach($pair in @(@($a,'figures/overview.png'),@($dataSource,'figures/detail.png'))){
        $p=Join-Path $pair[0] $pair[1];[void][IO.Directory]::CreateDirectory((Split-Path -Parent $p));[IO.File]::WriteAllBytes($p,$png)
    }
    $sources=@([pscustomobject]@{id='a';path=$a;role='canonical';target_name='a'})
    if($SingleSource){
        [IO.File]::AppendAllText((Join-Path $a 'README.md'),"Result: double the total for the second method.`n",[Text.UTF8Encoding]::new($false))
        [IO.File]::AppendAllText((Join-Path $a 'code/run.ps1'),'function Get-Double { param($Total) $Total * 2 }',[Text.UTF8Encoding]::new($false))
    }
    if(-not $SingleSource){
        Write-FixtureText (Join-Path $b 'README.md') "# Source B`nResult: double the total for the second method.`n"
        Write-FixtureText (Join-Path $b 'code/run.ps1') 'function Get-Double { param($Total) $Total * 2 }'
        $sources+= [pscustomobject]@{id='b';path=$b;role='legacy';target_name='b'}
    }
    $preparedReadme=Join-Path $run 'prepared/README.md'
    Write-FixtureText $preparedReadme "# Unified project`nMethod: sum all observed values.`nResult: double the total for the second method.`nUser note: keep calibrated units.`nRun [code](code/run.ps1) with [data](data/values.csv).`n![Overview](figures/overview.png)`n![Detail](figures/detail.png)`n"
    $preparedCode=Join-Path $run 'prepared/run.ps1'
    Write-FixtureText $preparedCode @'
function Get-Total { param($Rows) ($Rows | Measure-Object Value -Sum).Sum }
function Get-Double { param($Total) $Total * 2 }
$rows=Import-Csv -LiteralPath (Join-Path (Split-Path -Parent $PSScriptRoot) 'data/values.csv')
$sum=Get-Total $rows
[pscustomobject]@{sum=$sum;double=(Get-Double $sum)} | ConvertTo-Json -Compress
'@
    $groups=New-Object Collections.Generic.List[object]
    foreach($spec in @(@{id='docs';relative='README.md';prepared=$preparedReadme;targetInput=$true},@{id='code';relative='code/run.ps1';prepared=$preparedCode;targetInput=$false})){
        $inputs=New-Object Collections.Generic.List[object]
        foreach($source in $sources){
            $p=Join-Path $source.path $spec.relative
            if(Test-Path -LiteralPath $p){
                $backup=Join-Path $run ('originals/'+$source.id+'/'+$spec.relative)
                [void][IO.Directory]::CreateDirectory((Split-Path -Parent $backup));[IO.File]::Copy($p,$backup,$false)
                $inputs.Add([pscustomobject]@{source_id=$source.id;relative_path=$spec.relative;sha256=(Get-POStableSha256 $p);recovery_path=$backup})
            }
        }
        $expected='absent'
        if($spec.targetInput){
            $p=Join-Path $target $spec.relative;$expected=Get-POStableSha256 $p;$backup=Join-Path $run ('originals/target/'+$spec.relative)
            [void][IO.Directory]::CreateDirectory((Split-Path -Parent $backup));[IO.File]::Copy($p,$backup,$false)
            $inputs.Add([pscustomobject]@{source_id='__target__';relative_path=$spec.relative;sha256=$expected;recovery_path=$backup})
        }
        $coverage=Join-Path $run ('coverage/'+$spec.id+'.md')
        $coverageRows=@($inputs | ForEach-Object{[pscustomobject]@{source_id=$_.source_id;relative_path=$_.relative_path;destination_paths=@($spec.relative);reason=if($spec.id -eq 'docs'){'Preserved source method, result and current user calibration note; updated links.'}else{'Preserved sum and double functions; data input now resolves from the project root.'}}})
        Write-FixtureText $coverage (($coverageRows | ConvertTo-Json -Depth 10)+"`n")
        $groups.Add([pscustomobject]@{id=$spec.id;inputs=@($inputs.ToArray());outputs=@([pscustomobject]@{relative_path=$spec.relative;prepared_path=$spec.prepared;sha256=(Get-POStableSha256 $spec.prepared);expected_target_sha256=$expected});coverage=[pscustomobject]@{path=$coverage;sha256=(Get-POStableSha256 $coverage);inputs=$coverageRows};required_checks=@($(if($spec.id -eq 'docs'){'links'}else{'run'}))})
    }
    $manifest=Join-Path $run 'integration.json'
    Write-POJson $manifest ([ordered]@{schema_version='1.0';groups=@($groups.ToArray())})
    Write-POJson $config ([ordered]@{
        schema_version='1.1';mode='merge';search_roots=@($root);candidate_hints=@('old');max_discovery_depth=2;sources=$sources
        target_root=$target;audit_root=$run;integration_manifest=$manifest;canonical_source_id='a';mapping_rules=@()
        active_repo_policy='new';sync_roots=@($target);external_git_root=(Join-Path $root 'external-git');protected_paths=@()
        exclude_rules=[ordered]@{directory_names=@();relative_prefixes=@();extensions=@();retire_excluded=$false}
        layout_decisions=[ordered]@{restructure_in_scope=$true;root_files=@('README.md');category_language='preserve';max_general_depth=4;deep_structure_prefixes=@('code','data','figures','过程文件');independent_subprojects=@();version_policy='integrate';keep_empty_directories=@();forbidden_target_paths=@();exceptions=@();approved_tree_sha256=''}
    })
    return [pscustomobject]@{Root=$root;A=$a;B=$b;Target=$target;Run=$run;Config=$config;Manifest=$manifest;Groups=@($groups.ToArray());Sources=$sources}
}
function Build-FixturePlan($Fixture){
    Invoke-Step 'Build-ProjectInventory.ps1' $Fixture | Out-Null
    Invoke-Step 'Build-OrganizationPlan.ps1' $Fixture | Out-Null
    return (Get-Content -LiteralPath (Join-Path $Fixture.Run 'plan.sha256') -Encoding UTF8 -Raw).Trim()
}
function Write-ActualChecks($Fixture,[switch]$VerifyOnly){
    $readme=[IO.File]::ReadAllText((Join-Path $Fixture.Target 'README.md'))
    $links=@([regex]::Matches($readme,'\]\(([^)]+)\)') | ForEach-Object{$_.Groups[1].Value})
    foreach($link in $links){if(-not(Test-Path -LiteralPath (Join-Path $Fixture.Target $link) -PathType Leaf)){throw "Broken sample link: $link"}}
    if($links.Count -ne 4){throw 'Expected four actual file links.'}
    foreach($text in @('sum all observed values','double the total','keep calibrated units')){if(-not $readme.Contains($text)){throw "Lost content: $text"}}
    $code=Join-Path $Fixture.Target 'code/run.ps1'
    $runOutput=& powershell -NoProfile -ExecutionPolicy Bypass -File $code
    if($LASTEXITCODE -ne 0){throw 'Prepared sample code failed.'}
    $value=$runOutput | ConvertFrom-Json
    if($value.sum -ne 6 -or $value.double -ne 12){throw 'Integrated code changed expected sample calculations.'}
    if($VerifyOnly){return}
    $checks=New-Object Collections.Generic.List[object]
    foreach($group in $Fixture.Groups){
        $id=[string]$group.required_checks[0];$report=Join-Path $Fixture.Run ('checks/'+$id+'.json')
        Write-POJson $report ([ordered]@{links=$links;observed_sum=$value.sum;observed_double=$value.double;checked_content=@('method','result','user_note')})
        $checks.Add([pscustomobject]@{group_id=$group.id;id=$id;status='passed';checked_at=[datetime]::UtcNow.ToString('o');outputs=@($group.outputs|ForEach-Object{[pscustomobject]@{relative_path=$_.relative_path;sha256=(Get-POStableSha256 (Join-Path $Fixture.Target $_.relative_path))}});report_path=$report;report_sha256=(Get-POStableSha256 $report)})
    }
    Write-POJson (Join-Path $Fixture.Run 'integration-checks.json') ([ordered]@{schema_version='1.0';manifest_sha256=(Get-POStableSha256 $Fixture.Manifest);checks=@($checks.ToArray())})
}
function Test-FileMutation($Fixture,[string]$Path,[string]$Name,[scriptblock]$Check){
    $bytes=[IO.File]::ReadAllBytes($Path);$time=[IO.File]::GetLastWriteTimeUtc($Path)
    try{
        [IO.File]::AppendAllText($Path,"`nUNPLANNED CHANGE",[Text.UTF8Encoding]::new($false))
        & $Check
        Assert-Test (([IO.File]::ReadAllText($Path)).Contains('UNPLANNED CHANGE')) ($Name+'_preserved')
        foreach($source in $Fixture.Sources){Assert-Test (Test-Path -LiteralPath $source.path) ($Name+'_source_'+$source.id+'_retained')}
        $missing=@($Fixture.Groups | ForEach-Object{$_.inputs} | Where-Object source_id -ne '__target__' | Where-Object{
            $inputRecord=$_;$source=@($Fixture.Sources|Where-Object id -eq $inputRecord.source_id)[0]
            -not(Test-Path -LiteralPath (Join-Path $source.path $inputRecord.relative_path) -PathType Leaf)
        })
        Assert-Test ($missing.Count -eq 0) ($Name+'_all_integrated_source_files_retained')
    }finally{[IO.File]::WriteAllBytes($Path,$bytes);[IO.File]::SetLastWriteTimeUtc($Path,$time)}
}
function Assert-ManifestRefusal($Fixture,[string]$Name,[scriptblock]$Change){
    $bytes=[IO.File]::ReadAllBytes($Fixture.Manifest)
    try{
        $value=Get-Content -LiteralPath $Fixture.Manifest -Raw -Encoding UTF8 | ConvertFrom-Json
        & $Change $value
        Write-POJson $Fixture.Manifest $value
        $refused=$false
        try{Read-POIntegrationManifest -Config (Read-POConfig -Path $Fixture.Config -RequireSources) | Out-Null}catch{$refused=$true}
        Assert-Test $refused $Name
    }finally{[IO.File]::WriteAllBytes($Fixture.Manifest,$bytes)}
}

[void][IO.Directory]::CreateDirectory($testRoot)
try{
    $f=New-IntegrationFixture '完整整合'
    $settings=Read-POConfig $f.Config -RequireSources
    $integration=Read-POIntegrationManifest -Config $settings
    Assert-Test ($integration.Groups.Count -eq 2) 'manifest_two_groups_and_target_input'
    Assert-ManifestRefusal $f 'reject_duplicate_group' {param($v) $v.groups+=@($v.groups[0])}
    Assert-ManifestRefusal $f 'reject_duplicate_input' {param($v) $v.groups[0].inputs+=@($v.groups[0].inputs[0])}
    Assert-ManifestRefusal $f 'reject_duplicate_output' {param($v) $v.groups[1].outputs[0].relative_path='README.md'}
    Assert-ManifestRefusal $f 'reject_output_traversal' {param($v) $v.groups[0].outputs[0].relative_path='../escape.md'}
    Assert-ManifestRefusal $f 'reject_output_inside_audit' {param($v) $v.groups[0].outputs[0].relative_path='过程文件/本轮整合/business.md'}
    Assert-ManifestRefusal $f 'reject_missing_input_coverage' {param($v) $v.groups[0].coverage.inputs=@($v.groups[0].coverage.inputs[0])}
    Assert-ManifestRefusal $f 'reject_unrelated_coverage_destination' {param($v) $v.groups[0].coverage.inputs[0].destination_paths=@('unrelated.md')}
    Assert-ManifestRefusal $f 'reject_target_without_input' {param($v) $v.groups[0].inputs=@($v.groups[0].inputs|Where-Object source_id -ne '__target__')}
    Assert-ManifestRefusal $f 'reject_recovery_outside_audit' {param($v) $v.groups[0].inputs[0].recovery_path=(Join-Path $f.A 'README.md')}
    Assert-ManifestRefusal $f 'reject_prepared_outside_audit' {param($v) $v.groups[0].outputs[0].prepared_path=(Join-Path $f.A 'README.md')}
    $configBytes=[IO.File]::ReadAllBytes($f.Config)
    foreach($badAudit in @($f.Target,(Join-Path $f.A 'audit'))){
        try{
            $bad=Get-Content -LiteralPath $f.Config -Encoding UTF8 -Raw | ConvertFrom-Json;$bad.audit_root=$badAudit;Write-POJson $f.Config $bad
            $refused=$false;try{Read-POConfig $f.Config -RequireSources | Out-Null}catch{$refused=$true}
            Assert-Test $refused ('reject_audit_overlap_'+[IO.Path]::GetFileName($badAudit))
        }finally{[IO.File]::WriteAllBytes($f.Config,$configBytes)}
    }
    $auditLink=Join-Path $f.Root 'linked-audit'
    [void](New-Item -ItemType Junction -Path $auditLink -Target $f.Run)
    try{
        $bad=Get-Content -LiteralPath $f.Config -Encoding UTF8 -Raw | ConvertFrom-Json;$bad.audit_root=$auditLink;Write-POJson $f.Config $bad
        $refused=$false;try{Read-POConfig $f.Config -RequireSources | Out-Null}catch{$refused=$true}
        Assert-Test $refused 'reject_audit_junction'
    }finally{[IO.File]::WriteAllBytes($f.Config,$configBytes);[IO.Directory]::Delete($auditLink,$false)}
    $hiddenBusiness=Join-Path $f.Run 'business.txt';Write-FixtureText $hiddenBusiness 'Existing business content must not disappear from inventory.'
    try{
        Invoke-Step 'Build-ProjectInventory.ps1' $f -Fail | Out-Null
        Assert-Test (Test-Path $hiddenBusiness) 'reject_existing_business_hidden_in_audit'
    }finally{[IO.File]::Delete($hiddenBusiness)}
    $plan=Build-FixturePlan $f
    $rows=@(Import-Csv -LiteralPath (Join-Path $f.Run 'actions.csv') -Encoding UTF8)
    Assert-Test (@($rows|Where-Object action -eq 'install_integrated_file').Count -eq 2) 'outputs_installed_once_for_many_inputs'
    $tree=@(Import-Csv -LiteralPath (Join-Path $f.Run 'target-tree.csv') -Encoding UTF8)
    Assert-Test (@($tree|Where-Object relative_path -eq 'README.md').Count -eq 1) 'final_tree_one_readme'
    Assert-Test (@($tree|Where-Object relative_path -like '过程文件/本轮整合*').Count -eq 0) 'only_current_audit_subtree_excluded'
    Assert-Test (@($tree|Where-Object relative_path -eq '过程文件/其他任务/notes.md').Count -eq 1) 'other_task_material_in_inventory'
    foreach($item in @(
        @{name='source';path=(Join-Path $f.A 'README.md')},@{name='target';path=(Join-Path $f.Target 'README.md')},
        @{name='prepared';path=$f.Groups[0].outputs[0].prepared_path},@{name='recovery';path=$f.Groups[0].inputs[0].recovery_path},
        @{name='coverage';path=$f.Groups[0].coverage.path}
    )){
        Test-FileMutation $f $item.path ('preflight_'+$item.name) {Invoke-Step 'Invoke-OrganizationPlan.ps1' $f @('-ApprovedPlanSha256',$plan,'-Execute') -Fail | Out-Null}
    }
    $unplanned=Join-Path $f.A 'new-user-note.md';Write-FixtureText $unplanned 'New user work.'
    try{Invoke-Step 'Invoke-OrganizationPlan.ps1' $f @('-ApprovedPlanSha256',$plan,'-Execute') -Fail | Out-Null;Assert-Test (Test-Path $unplanned) 'new_source_file_retained'}finally{[IO.File]::Delete($unplanned)}
    Write-FixtureText (Join-Path $f.Run 'execution.jsonl') "{`"event`":`"fixture_progress`"}`n"
    Invoke-Step 'Invoke-OrganizationPlan.ps1' $f @('-ApprovedPlanSha256',$plan,'-Execute','-StopAfterActions','1') -Fail | Out-Null
    Assert-Test (Test-Path (Join-Path $f.Run 'execution-state.json')) 'integration_interruption_state_saved'
    Invoke-Step 'Invoke-OrganizationPlan.ps1' $f @('-ApprovedPlanSha256',$plan,'-Execute','-Resume') | Out-Null
    Invoke-Step 'Test-OrganizationAcceptance.ps1' $f -Fail | Out-Null
    Assert-Test (Test-Path (Join-Path $f.A 'README.md')) 'unchecked_integration_keeps_old_sources'
    Write-ActualChecks $f
    Assert-Test ((Get-POStableSha256 (Join-Path $f.Target 'figures/overview.png')) -eq (Get-POStableSha256 (Join-Path $f.Target 'figures/detail.png'))) 'same_bytes_distinct_reference_roles_preserved'
    Assert-Test ([IO.File]::ReadAllText((Join-Path $f.Target '过程文件/其他任务/notes.md')) -eq 'Unrelated process material must survive.') 'unrelated_target_content_preserved'
    Invoke-Step 'Test-OrganizationAcceptance.ps1' $f | Out-Null
    foreach($item in @(@{name='output';path=(Join-Path $f.Target 'README.md')},@{name='recovery';path=$f.Groups[0].inputs[0].recovery_path},@{name='report';path=(Join-Path $f.Run 'checks/links.json')})){
        Test-FileMutation $f $item.path ('before_retirement_plan_'+$item.name) {Invoke-Step 'Build-RetirementPlan.ps1' $f -Fail | Out-Null}
    }
    Invoke-Step 'Build-RetirementPlan.ps1' $f | Out-Null
    $retirement=(Get-Content -LiteralPath (Join-Path $f.Run 'retirement.sha256') -Raw -Encoding UTF8).Trim()
    foreach($item in @(@{name='output';path=(Join-Path $f.Target 'README.md')},@{name='recovery';path=$f.Groups[0].inputs[0].recovery_path},@{name='source';path=(Join-Path $f.A 'README.md')},@{name='report';path=(Join-Path $f.Run 'checks/links.json')})){
        Test-FileMutation $f $item.path ('before_retirement_execute_'+$item.name) {Invoke-Step 'Invoke-RetirementPlan.ps1' $f @('-ApprovedRetirementSha256',$retirement,'-Recycle','-MockRecycleRoot',(Join-Path $f.Root 'recycled')) -Fail | Out-Null}
    }
    $lateSource=Join-Path $f.A 'later-user-work.md';Write-FixtureText $lateSource 'New work after retirement was planned.'
    try{
        Invoke-Step 'Invoke-RetirementPlan.ps1' $f @('-ApprovedRetirementSha256',$retirement,'-Recycle','-MockRecycleRoot',(Join-Path $f.Root 'recycled')) -Fail | Out-Null
        Assert-Test (Test-Path $lateSource) 'retirement_rejects_new_unplanned_source_file'
        Assert-Test (Test-Path (Join-Path $f.A 'code/run.ps1')) 'unplanned_source_detected_before_first_recycle'
    }finally{[IO.File]::Delete($lateSource)}
    $retireRows=@(Import-Csv -LiteralPath (Join-Path $f.Run 'retirement.csv') -Encoding UTF8)
    $first=@($retireRows|Where-Object action -eq 'recycle_integrated_source')[0]
    $recycle=Join-Path $f.Root 'recycled';$obstacle=Join-Path (Join-Path $recycle $first.source_id) $first.relative_path
    Write-FixtureText $obstacle 'Mock recycle interruption only.'
    Invoke-Step 'Invoke-RetirementPlan.ps1' $f @('-ApprovedRetirementSha256',$retirement,'-Recycle','-MockRecycleRoot',$recycle) -Fail | Out-Null
    Assert-Test (Test-Path -LiteralPath $first.source_path) 'failed_mock_recycle_preserves_source'
    [IO.File]::Delete($obstacle)
    Invoke-Step 'Invoke-RetirementPlan.ps1' $f @('-ApprovedRetirementSha256',$retirement,'-Recycle','-MockRecycleRoot',$recycle,'-Resume') | Out-Null
    Invoke-Step 'Test-RetirementAcceptance.ps1' $f | Out-Null
    Assert-Test (-not(Test-Path $f.A) -and -not(Test-Path $f.B)) 'all_integrated_old_roots_retired'
    Write-ActualChecks $f -VerifyOnly
    Assert-Test (Test-Path (Join-Path $f.Target 'README.md')) 'new_project_usable_after_old_roots_removed'
    $otherNote=Join-Path $f.Target '过程文件/其他任务/notes.md';$otherBytes=[IO.File]::ReadAllBytes($otherNote);$otherTime=[IO.File]::GetLastWriteTimeUtc($otherNote)
    try{
        [IO.File]::AppendAllText($otherNote,'User later edit.',[Text.UTF8Encoding]::new($false))
        Invoke-Step 'Test-RetirementAcceptance.ps1' $f -Fail | Out-Null
        Assert-Test ([IO.File]::ReadAllText($otherNote).Contains('User later edit.')) 'final_acceptance_detects_and_preserves_other_target_change'
    }finally{[IO.File]::WriteAllBytes($otherNote,$otherBytes);[IO.File]::SetLastWriteTimeUtc($otherNote,$otherTime)}
    $extra=Join-Path $f.Target 'unexpected.txt';Write-FixtureText $extra 'New unrelated content.'
    try{Invoke-Step 'Test-RetirementAcceptance.ps1' $f -Fail | Out-Null;Assert-Test (Test-Path $extra) 'final_acceptance_detects_extra_target_file'}finally{[IO.File]::Delete($extra)}
    Invoke-Step 'Test-RetirementAcceptance.ps1' $f | Out-Null

    $single=New-IntegrationFixture 'single-source' -SingleSource -ExternalAudit
    $singlePlan=Build-FixturePlan $single
    Invoke-Step 'Invoke-OrganizationPlan.ps1' $single @('-ApprovedPlanSha256',$singlePlan,'-Execute') | Out-Null
    Write-ActualChecks $single
    Invoke-Step 'Test-OrganizationAcceptance.ps1' $single | Out-Null
    Assert-Test (@((Read-POConfig $single.Config -RequireSources).sources).Count -eq 1) 'single_source_plus_existing_target_supported'
    Assert-Test (Test-Path (Join-Path $single.Target 'code/run.ps1')) 'external_audit_supported_with_integration'
    $conflict=New-IntegrationFixture 'unresolved-conflict'
    Write-FixtureText (Join-Path $conflict.A 'code/unresolved.ps1') 'function Get-Unknown { 1 }'
    Write-FixtureText (Join-Path $conflict.B 'code/unresolved.ps1') 'function Get-Unknown { 2 }'
    Invoke-Step 'Build-ProjectInventory.ps1' $conflict | Out-Null
    $conflictRows=@(Import-Csv -LiteralPath (Join-Path $conflict.Run 'conflicts.csv') -Encoding UTF8)
    Assert-Test (@($conflictRows|Where-Object reason -eq 'same_target_different_sha256').Count -eq 2) 'uncovered_conflicting_inputs_remain_held'
    Invoke-Step 'Build-OrganizationPlan.ps1' $conflict -Fail | Out-Null
    Assert-Test ([IO.File]::ReadAllText((Join-Path $conflict.A 'code/unresolved.ps1')) -eq 'function Get-Unknown { 1 }') 'unresolved_first_variant_preserved'
    Assert-Test ([IO.File]::ReadAllText((Join-Path $conflict.B 'code/unresolved.ps1')) -eq 'function Get-Unknown { 2 }') 'unresolved_second_variant_preserved'
    $success=$true
}finally{
    Write-POJson (Join-Path $testRoot 'test-results.json') ([ordered]@{complete=$success;total=$results.Count;passed=@($results|Where-Object passed).Count;tests=@($results.ToArray())})
    Write-Output "Integration test workspace: $testRoot"
    if($success){Write-Output "Project integration tests passed: $($results.Count)/$($results.Count)"}
    if($success -and -not $KeepWorkspace){
        $resolved=[IO.Path]::GetFullPath($testRoot);$temporary=[IO.Path]::GetFullPath([IO.Path]::GetTempPath())
        if(-not $resolved.StartsWith($temporary,[StringComparison]::OrdinalIgnoreCase) -or [IO.Path]::GetFileName($resolved) -notmatch '^project-integration-test-[0-9a-f]{32}$'){throw 'Unsafe test cleanup target.'}
        Remove-Item -LiteralPath $resolved -Recurse -Force
    }
}
