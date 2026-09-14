[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$Config,
    [Parameter(Mandatory=$true)][string]$OutputDir
)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
Import-Module (Join-Path $PSScriptRoot 'ProjectOrganizer.psm1') -Force
$settings=Read-POConfig -Path $Config -RequireSources
$output=Resolve-POFullPath -Path $OutputDir
Assert-POAuditPath -Config $settings -OutputDir $output
$source=Get-PORecoveryRunRoot -Config $settings -OutputDir $output
Assert-POSafePath -Path $source
if(-not [IO.Directory]::Exists($source)){throw 'No incomplete recovery directory exists.'}
if(Test-Path -LiteralPath (Join-Path $source 'recovery.sha256')){throw 'A sealed recovery exists; do not reset or bypass its validation.'}
$destination=Join-Path (Join-Path $output 'failed-git-recovery') ([guid]::NewGuid().ToString('N'))
$destination=Resolve-POFullPath -Path $destination -AllowMissing
if(-not (Test-POPathWithin -Path $source -Parent $settings.recovery_root) -or -not (Test-POPathWithin -Path $destination -Parent $settings.audit_root)){throw 'Failure preservation path escaped its configured root.'}
Assert-POSafePath -Path $destination
if(-not (Test-POSameVolume -First $source -Second $output)){throw 'Failure preservation requires the same volume. Keep the partial directory intact and arrange a verified copy to a process location on its volume before retrying.'}
$scan=Get-POSourceEntries -Root $source
if($scan.Errors.Count){throw 'Cannot inventory the partial recovery safely.'}
$entries=@(foreach($entry in $scan.Entries){
    Assert-POSafePath -Path $entry.full_path -File:($entry.entry_type -eq 'file')
    [pscustomobject]@{relative_path=$entry.relative_path;entry_type=$entry.entry_type;sha256=$(if($entry.entry_type -eq 'file'){Get-POStableSha256 -Path $entry.full_path}else{''})}
})
$register=Join-Path $output 'failed-git-recovery.json'
$existing=@();if(Test-Path -LiteralPath $register){$existing=@(Read-POJsonArray -Path $register)}
$record=[pscustomobject]@{source_root=$source;destination_root=$destination;entries=$entries;status='unverified_git_preserved'}
[void][IO.Directory]::CreateDirectory((Split-Path -Parent $destination))
# Keep a recovery location before the atomic move; no file is overwritten or deleted.
Write-POJson -Path $register -Value @($existing + @($record))
try{[IO.Directory]::Move($source,$destination)}catch{Write-POJson -Path $register -Value $existing;throw}
$after=Get-POSourceEntries -Root $destination
if($after.Errors.Count -or $after.Entries.Count -ne $entries.Count){throw 'Preserved partial tree needs inspection; both record and files remain available.'}
foreach($entry in $entries){
    $path=Join-POPath -Root $destination -RelativePath $entry.relative_path
    if($entry.entry_type -eq 'file' -and (Get-POStableSha256 -Path $path) -ne $entry.sha256){throw 'Preserved partial file differs; do not resume.'}
}
Write-Output "Incomplete recovery preserved without Git acceptance: $destination"
Write-Output 'Fix the original failure, then rerun New-GitRecoveryBundle with the same Config and OutputDir. Rebuild and verify the organization plan before retirement.'
