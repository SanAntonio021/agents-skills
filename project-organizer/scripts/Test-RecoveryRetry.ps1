[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$WorkspaceRoot)
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
Import-Module (Join-Path $PSScriptRoot 'ProjectOrganizer.psm1') -Force
$root=Join-Path $WorkspaceRoot ('r-'+[guid]::NewGuid().ToString('N').Substring(0,8))
$source=Join-Path $root 's';$target=Join-Path $root 't';$run=Join-Path $target '过程文件/run';$config=Join-Path $root 'config.json'
[void][IO.Directory]::CreateDirectory($source)
$results=New-Object Collections.Generic.List[object]
function Check([bool]$Value,[string]$Name){$results.Add([pscustomobject]@{name=$Name;passed=$Value});if(-not $Value){throw $Name}}
function Step([string]$Name,[switch]$Fail){
    $old=$ErrorActionPreference;$ErrorActionPreference='Continue'
    try{$lines=@(& powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot $Name) -Config $config -OutputDir $run 2>&1);$code=$LASTEXITCODE}finally{$ErrorActionPreference=$old}
    if($Fail){Check ($code -ne 0) ($Name+'_refused')}elseif($code -ne 0){throw ($lines -join "`n")}
    return ($lines -join "`n")
}
& git init --quiet $source
if($LASTEXITCODE){throw 'git init failed'}
$settings=[ordered]@{schema_version='1.1';mode='group';mapping_rules=@();search_roots=@($root);sources=@([ordered]@{id='s';path=$source;role='primary';target_name='one'});target_root=$target;audit_root=$run;active_repo_policy='preserve_each';sync_roots=@($target);external_git_root=(Join-Path $root 'e');protected_paths=@();exclude_rules=@{directory_names=@();relative_prefixes=@();extensions=@()}}
Write-POJson -Path $config -Value $settings
try{
    Step 'New-GitRecoveryBundle.ps1' -Fail | Out-Null
    $parsed=Read-POConfig -Path $config
    $formal=Get-PORecoveryRunRoot -Config $parsed -OutputDir $run
    Check ((Test-Path -LiteralPath $formal) -and -not (Test-Path -LiteralPath (Join-Path $formal 'recovery.sha256'))) 'actual_empty_git_failure_left_partial_directory'
    $before=@((Get-POSourceEntries -Root $formal).Entries | Where-Object entry_type -eq 'file' | ForEach-Object {[pscustomobject]@{relative_path=$_.relative_path;sha256=(Get-POStableSha256 -Path $_.full_path)}})
    $again=Step 'New-GitRecoveryBundle.ps1' -Fail
    Check ($again -match 'recovery.sha256') 'ordinary_retry_does_not_trust_partial_files'
    Write-POText -Path (Join-Path $source 'README.md') -Text 'repair empty repository fixture'
    & git -C $source add README.md
    & git -C $source -c user.name=Fixture -c user.email=fixture@example.invalid commit --quiet -m initial
    if($LASTEXITCODE){throw 'fixture commit failed'}
    Step 'Move-FailedGitRecovery.ps1' | Out-Null
    Check (-not (Test-Path -LiteralPath $formal)) 'partial_formal_location_freed_without_deleting_contents'
    $records=@(Read-POJsonArray -Path (Join-Path $run 'failed-git-recovery.json'))
    $parked=[string]$records[0].destination_root
    foreach($item in $before){Check ((Get-POStableSha256 -Path (Join-POPath -Root $parked -RelativePath $item.relative_path)) -eq $item.sha256) ('preserved_'+$item.relative_path)}
    Check ($records[0].status -eq 'unverified_git_preserved') 'failed_materials_are_not_accepted_as_git_recovery'
    Step 'New-GitRecoveryBundle.ps1' | Out-Null
    Assert-PORecoveryContents -Config $parsed -OutputDir $run
    Check (Test-Path -LiteralPath (Join-Path $formal 'recovery.sha256')) 'same_output_retry_succeeds_after_real_git_fix'
    Assert-POAuditContents -Config $parsed -OutputDir $run -ConfigPath $config
    Check $true 'preserved_failures_pass_explicit_process_inventory'
    Step 'Move-FailedGitRecovery.ps1' -Fail | Out-Null
    Check (Test-Path -LiteralPath (Join-Path $formal 'recovery.sha256')) 'sealed_recovery_cannot_be_reset'
    $file=Join-Path $parked $before[0].relative_path;$bytes=[IO.File]::ReadAllBytes($file)
    Write-POText -Path $file -Text 'tampered'
    $refused=$false;try{Assert-POAuditContents -Config $parsed -OutputDir $run -ConfigPath $config}catch{$refused=$true}
    Check $refused 'tampered_preserved_failure_blocks_audit'
    [IO.File]::WriteAllBytes($file,$bytes)
}finally{
    Write-POJson -Path (Join-Path $root 'retry-results.json') -Value ([ordered]@{total=$results.Count;passed=@($results | Where-Object passed).Count;tests=@($results.ToArray())})
    Write-Output "Recovery retry test evidence: $root"
}
