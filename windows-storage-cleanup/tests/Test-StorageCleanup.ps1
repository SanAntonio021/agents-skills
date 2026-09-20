#requires -Version 7.0
[CmdletBinding()]
param([string]$ModulePath = (Join-Path $PSScriptRoot '../scripts/StorageCleanup.psm1'), [string]$CrossVolumeRoot)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
if (-not $IsWindows) { throw 'These integration tests require Windows.' }
Import-Module $ModulePath -Force
$testId = [guid]::NewGuid().ToString('N')
$tempBase = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
$sandbox = Join-Path $tempBase ('storage-cleanup-tests-' + $testId)
$null = [IO.Directory]::CreateDirectory($sandbox)
$results = [Collections.Generic.List[object]]::new()
$externalSandbox = $null
if ($CrossVolumeRoot) {
    $crossBase = (Get-Item -LiteralPath $CrossVolumeRoot -ErrorAction Stop).FullName
    if ([IO.Path]::GetPathRoot($crossBase) -eq [IO.Path]::GetPathRoot($sandbox)) { throw 'CrossVolumeRoot must use another drive.' }
    $externalSandbox = Join-Path $crossBase ('storage-cleanup-tests-' + $testId)
    $null = [IO.Directory]::CreateDirectory($externalSandbox)
}
function Assert([bool]$Condition, [string]$Message) { if (-not $Condition) { throw $Message } }
function WriteSample([string]$Path, [string]$Content = 'independent test data') {
    $null = [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($Path))
    [IO.File]::WriteAllText($Path, $Content, [Text.UTF8Encoding]::new($false))
}
function Member([IO.FileSystemInfo]$File, [string]$RelativePath) {
    $m = [ordered]@{ relativePath=$RelativePath; kind=$(if ($File.PSIsContainer) {'directory'} else {'file'}); bytes=0L; lastWriteTimeUtc=$File.LastWriteTimeUtc.ToString('o') }
    if (-not $File.PSIsContainer) { $m.bytes=$File.Length; $m.sha256=(Get-FileHash -LiteralPath $File.FullName -Algorithm SHA256).Hash }
    return $m
}
function Item([string]$Source, [string]$Action='recycle_then_purge', [string]$Retained='', [string]$Archive='') {
    $f=Get-Item -LiteralPath $Source
    $i=[ordered]@{id=[guid]::NewGuid().ToString('N'); source=$f.FullName; kind=$(if($f.PSIsContainer){'directory'}else{'file'});action=$Action;bytes=0L;lastWriteTimeUtc=$f.LastWriteTimeUtc.ToString('o')}
    if ($f.PSIsContainer) {
        $i.members=@(Get-ChildItem -LiteralPath $f.FullName -Recurse -Force | ForEach-Object { Member $_ ([IO.Path]::GetRelativePath($f.FullName,$_.FullName)) })
        foreach($member in $i.members){$i.bytes += [long]$member.bytes}
    } else { $i.bytes=$f.Length; $i.sha256=(Get-FileHash -LiteralPath $Source -Algorithm SHA256).Hash }
    if($Retained){$i.retainedCopy=$Retained}; if($Archive){$i.archiveDestination=$Archive}
    return $i
}
function Fixture([string]$Name) {
    $root=Join-Path $sandbox $Name
    foreach($n in 'source','kept','control'){ $null=[IO.Directory]::CreateDirectory((Join-Path $root $n)) }
    return @{root=$root;source=(Join-Path $root 'source');kept=(Join-Path $root 'kept');manifest=(Join-Path $root 'control/manifest.json');state=(Join-Path $root 'state')}
}
function SaveManifest($F, [object[]]$Items) {
    $roots=@($F.source,$F.kept)
    if($externalSandbox){$roots+=@($externalSandbox)}
    $m=[ordered]@{schemaVersion=1;batchId=[guid]::NewGuid().ToString('N');approvedRoots=$roots;items=@($Items)}
    [IO.File]::WriteAllText($F.manifest,($m|ConvertTo-Json -Depth 20),[Text.UTF8Encoding]::new($false))
}
function Run($F,[string]$Mode) { $r=Invoke-StorageCleanup -Mode $Mode -ManifestPath $F.manifest -StateDirectory $F.state;if($r.exitCode -ne 0){throw ($r|ConvertTo-Json -Depth 12 -Compress)};return $r }
function Attempt($F,[string]$Mode='Execute'){ try { $null=Run $F $Mode } catch { } }
function Fault([string]$At,[string]$Message='TEST_INTERRUPTION') {
    $module=Get-Module StorageCleanup
    & $module {param($At,$Message) $script:testFaultAt=$At;$script:testFaultMessage=$Message
        function script:Invoke-SCCheckpoint([string]$Name){if($Name -eq $script:testFaultAt){throw $script:testFaultMessage}}
    } $At $Message
}
function ResetFault { & (Get-Module StorageCleanup) {if(Get-Variable testJournalLock -Scope Script -ErrorAction SilentlyContinue){if($script:testJournalLock){$script:testJournalLock.Dispose();$script:testJournalLock=$null}};function script:Invoke-SCCheckpoint([string]$Name){}} }
function LockJournalAfterStage($F) {
    & (Get-Module StorageCleanup) {param($Path) $script:testJournalPath=$Path
        function script:Invoke-SCCheckpoint([string]$Name){if($Name -eq 'staged'){$script:testJournalLock=[IO.File]::Open($script:testJournalPath,'Open','Read','Read')}}
    } (Join-Path $F.state 'journal.jsonl')
}
function Records($F){@(Get-Content -LiteralPath (Join-Path $F.state 'journal.jsonl')|ForEach-Object{$_|ConvertFrom-Json})}
function Test([string]$Name,[scriptblock]$Body){
    try { & $Body; $results.Add([pscustomobject]@{name=$Name;status='PASS';detail='' }); Write-Host "PASS $Name" }
    catch { $status=if($_.Exception.Message.StartsWith('SKIP:')){'SKIP'}else{'FAIL'};$results.Add([pscustomobject]@{name=$Name;status=$status;detail=$_.Exception.Message }); Write-Host "$status $Name : $($_.Exception.Message)" }
}
function BinSnapshot {
    $sid=[Security.Principal.WindowsIdentity]::GetCurrent().User.Value
    $map=@{}
    $drives=@([IO.Path]::GetPathRoot($sandbox));if($externalSandbox){$drives+=@([IO.Path]::GetPathRoot($externalSandbox))}
    foreach($drive in $drives){
        $bin=Join-Path $drive ('$Recycle.Bin\'+$sid)
        if(Test-Path -LiteralPath $bin){foreach($f in Get-ChildItem -LiteralPath $bin -Force){$length=if($f.PSIsContainer){0L}else{$f.Length};$map[$f.FullName]="${length}:$($f.LastWriteTimeUtc.Ticks)"}}
    }
    return $map
}
$baseline=BinSnapshot
$sentinelPairs=@()
Test 'Check and Verify never create state or mutate source' {
    $f=Fixture 'readonly';$p=Join-Path $f.source 'clip.mp4';WriteSample $p 'video extension regression';SaveManifest $f @((Item $p))
    $before=(Get-FileHash -LiteralPath $p).Hash
    $null=Run $f Check;Attempt $f Verify
    Assert (-not(Test-Path -LiteralPath $f.state)) 'Read-only mode wrote state.'
    Assert ((Get-FileHash -LiteralPath $p).Hash -eq $before) 'Read-only mode changed source.'
}
Test 'Recycle sentinel remains recoverable' {
    $f=Fixture 'sentinel';$p=Join-Path $f.source 'sentinel.txt';WriteSample $p 'unrelated sentinel';SaveManifest $f @((Item $p 'recycle'))
    $null=Run $f Execute
    Assert (-not(Test-Path -LiteralPath $p)) 'Recycle did not remove source.'
    $after=BinSnapshot
    $owned=@($after.Keys|Where-Object {
        if($baseline.ContainsKey($_) -or [IO.Path]::GetFileName($_) -notlike '$I*'){return $false}
        $raw=[IO.File]::ReadAllBytes($_);if($raw.Length -lt 28){return $false}
        $version=[BitConverter]::ToInt64($raw,0);$offset=if($version -eq 1){24}elseif($version -eq 2){28}else{return $false}
        $original=[Text.Encoding]::Unicode.GetString($raw,$offset,$raw.Length-$offset).TrimEnd([char]0)
        return $original -eq $p
    })
    Assert ($owned.Count -eq 1) 'Exact sentinel metadata not found.'
    $script:sentinelPairs=@($owned[0],(Join-Path ([IO.Path]::GetDirectoryName($owned[0])) ([IO.Path]::GetFileName($owned[0]).Replace('$I','$R'))))
    Assert ($sentinelPairs.Count -eq 2) 'Sentinel did not produce exactly one recycle pair.'
    $null=Run $f Resume;$null=Run $f Resume;$null=Run $f Verify
    foreach($pair in $sentinelPairs){Assert (Test-Path -LiteralPath $pair) 'Resume removed recycled sentinel.'}
}
Test 'Permanent removal preserves unrelated recycle entries and retained copy' {
    $f=Fixture 'purge';$p=Join-Path $f.source '研究视频.mp4';$k=Join-Path $f.kept 'video.mp4'
    WriteSample $p 'duplicate content';WriteSample $k 'duplicate content';SaveManifest $f @((Item $p 'recycle_then_purge' $k))
    $null=Run $f Execute;$null=Run $f Resume;$null=Run $f Resume;$null=Run $f Verify
    Assert (-not(Test-Path -LiteralPath $p)) 'Purge did not remove source.'
    Assert ([IO.File]::ReadAllText($k) -eq 'duplicate content') 'Retained copy changed.'
    foreach($pair in $sentinelPairs){Assert (Test-Path -LiteralPath $pair) 'Purge removed unrelated sentinel.'}
}
Test 'Archive complete directory including empty member and video' {
    if(-not $externalSandbox){throw 'SKIP: Cross-volume test requires -CrossVolumeRoot.'}
    $f=Fixture 'archive';$p=Join-Path $f.source 'collection';WriteSample (Join-Path $p 'sub/图像视频.mp4') 'archive video';WriteSample (Join-Path $p 'a.txt') 'archive text'
    $null=[IO.Directory]::CreateDirectory((Join-Path $p 'empty'))
    $dest=if($externalSandbox){Join-Path $externalSandbox 'collection'}else{Join-Path $f.kept 'collection'}
    SaveManifest $f @((Item $p 'archive_then_purge' '' $dest));$null=Run $f Execute;$null=Run $f Resume;$null=Run $f Verify
    Assert (-not(Test-Path -LiteralPath $p)) 'Archived source remains.'
    Assert ([IO.File]::ReadAllText((Join-Path $dest 'sub/图像视频.mp4')) -eq 'archive video') 'Archive video missing or changed.'
    Assert (Test-Path -LiteralPath (Join-Path $dest 'empty') -PathType Container) 'Empty directory missing.'
}
Test 'Changed source and retained copy are protected' {
    foreach($which in 'source','retained'){
        $f=Fixture ('changed-'+$which);$p=Join-Path $f.source 'a';$k=Join-Path $f.kept 'a';WriteSample $p 'same';WriteSample $k 'same'
        SaveManifest $f @((Item $p 'recycle_then_purge' $k));WriteSample $(if($which -eq 'source'){$p}else{$k}) 'changed';Attempt $f
        Assert (Test-Path -LiteralPath $p) "Changed $which was accepted."
    }
}
Test 'Archive collision never overwrites' {
    if(-not $externalSandbox){throw 'SKIP: Cross-volume test requires -CrossVolumeRoot.'}
    $f=Fixture 'collision';$p=Join-Path $f.source 'a';$dest=Join-Path $externalSandbox 'collision-a';WriteSample $p 'source';WriteSample $dest 'existing'
    SaveManifest $f @((Item $p 'archive_then_purge' '' $dest));Attempt $f
    Assert ((Test-Path -LiteralPath $p) -and [IO.File]::ReadAllText($dest) -eq 'existing') 'Archive collision lost content.'
}
Test 'Verify detects changed archived content' {
    if(-not $externalSandbox){throw 'SKIP: Cross-volume test requires -CrossVolumeRoot.'}
    $f=Fixture 'archive-changed';$p=Join-Path $f.source 'a';$dest=Join-Path $externalSandbox 'changed-a';WriteSample $p 'original archive'
    SaveManifest $f @((Item $p 'archive_then_purge' '' $dest));$null=Run $f Execute;WriteSample $dest 'changed archive'
    $rejected=$false;try{$r=Run $f Verify;$rejected=($r.exitCode -ne 0)}catch{$rejected=$true}
    Assert $rejected 'Verify accepted changed archive.'
}
Test 'Locked source is retained' {
    $f=Fixture 'busy';$p=Join-Path $f.source 'a';WriteSample $p;SaveManifest $f @((Item $p))
    $lock=[IO.File]::Open($p,'Open','ReadWrite','None')
    try {Attempt $f;Assert (Test-Path -LiteralPath $p) 'Busy file removed.'}finally{$lock.Dispose()}
}
Test 'Manifest byte mutation cannot reuse batch state' {
    $f=Fixture 'manifest';$p=Join-Path $f.source 'a';WriteSample $p;SaveManifest $f @((Item $p 'recycle'))
    $null=Run $f Execute;[IO.File]::AppendAllText($f.manifest,"`n")
    $rejected=$false;try{$null=Run $f Resume}catch{$rejected=$true};Assert $rejected 'Changed manifest bytes accepted.'
}
Test 'Missing source does not become successful completion' {
    $f=Fixture 'missing';$p=Join-Path $f.source 'a';WriteSample $p;SaveManifest $f @((Item $p));[IO.File]::Delete($p)
    $rejected=$false;try{$r=Run $f Execute;$rejected=$r.exitCode -ne 0}catch{$rejected=$true}
    Assert $rejected 'Missing source reported no visible failure.'
}
Test 'Ancestor overlap and source outside approval are rejected' {
    $f=Fixture 'overlap';$dir=Join-Path $f.source 'parent';$p=Join-Path $dir 'a';WriteSample $p;SaveManifest $f @((Item $dir),(Item $p));Attempt $f
    Assert (Test-Path -LiteralPath $p) 'Nested targets were accepted.'
    SaveManifest $f @((Item $p));$m=Get-Content -LiteralPath $f.manifest -Raw|ConvertFrom-Json;$m.approvedRoots=@($f.kept);$m|ConvertTo-Json -Depth 20|Set-Content -LiteralPath $f.manifest -Encoding UTF8;Attempt $f
    Assert (Test-Path -LiteralPath $p) 'Out-of-root source was accepted.'
}
Test 'Drive root and system directory rejected in read-only Check' {
    foreach($target in @([IO.Path]::GetPathRoot($env:windir),$env:windir)){
        $f=Fixture ('protected-'+[guid]::NewGuid().ToString('N'))
        $fake=[ordered]@{id='protected';source=$target;kind='directory';action='recycle_then_purge';bytes=0L;lastWriteTimeUtc=[DateTime]::UtcNow.ToString('o');members=@()}
        SaveManifest $f @($fake);$m=Get-Content -LiteralPath $f.manifest -Raw|ConvertFrom-Json;$m.approvedRoots=@($target);$m|ConvertTo-Json -Depth 20|Set-Content -LiteralPath $f.manifest -Encoding UTF8
        $rejected=$false;try{$r=Run $f Check;$rejected=($r.exitCode -ne 0)}catch{$rejected=$true};Assert $rejected 'Protected target accepted.'
    }
}
Test 'Junction ancestor is rejected without touching target content' {
    $f=Fixture 'junction';$real=Join-Path $f.kept 'target';$p=Join-Path $real 'a';WriteSample $p 'protected synthetic target'
    $junction=Join-Path $f.source 'alias';$null=New-Item -ItemType Junction -Path $junction -Target $real
    $alias=Join-Path $junction 'a';SaveManifest $f @((Item $alias));Attempt $f
    Assert ((Test-Path -LiteralPath $alias) -and [IO.File]::ReadAllText($p) -eq 'protected synthetic target') 'Junction target was changed.'
}
Test 'Unicode long path remains within explicit root' {
    $f=Fixture 'long';$p=$f.source;foreach($n in 1..5){$p=Join-Path $p (('中文资料'+('x'*35))+$n)};$p=Join-Path $p '视频.mp4';WriteSample $p
    SaveManifest $f @((Item $p));$null=Run $f Execute;Assert (-not(Test-Path -LiteralPath $p)) 'Supported long path was not processed.'
}
Test 'Hardlink outside listed targets prevents destructive processing' {
    $f=Fixture 'hardlink';$p=Join-Path $f.source 'a';$alias=Join-Path $f.kept 'alias';WriteSample $p
    $null=New-Item -ItemType HardLink -Path $alias -Target $p
    SaveManifest $f @((Item $p));Attempt $f
    Assert ((Test-Path -LiteralPath $p) -and (Test-Path -LiteralPath $alias)) 'Unlisted hardlink alias was accepted.'
}
Test 'Listed hardlinks count once and mixed retained recycle counts zero' {
    foreach($mixed in $false,$true){
        $f=Fixture ('listed-links-'+$mixed);$p=Join-Path $f.source 'a';$alias=Join-Path $f.source 'b';WriteSample $p 'hardlink data'
        $null=New-Item -ItemType HardLink -Path $alias -Target $p
        $action=if($mixed){'recycle'}else{'recycle_then_purge'}
        SaveManifest $f @((Item $p),(Item $alias $action));$r=Run $f Check
        $expected=if($mixed){0L}else{(Get-Item -LiteralPath $p).Length}
        Assert ($r.estimatedReclaimBytes -eq $expected) 'Hardlink estimate counted retained/shared data incorrectly.'
        $null=Run $f Execute;$null=Run $f Resume;$null=Run $f Verify
        Assert (-not(Test-Path -LiteralPath $p) -and -not(Test-Path -LiteralPath $alias)) 'Listed hardlinks incomplete.'
    }
}
Test 'Archive resumes copy and verification boundaries' {
    if(-not $externalSandbox){throw 'SKIP: Cross-volume test requires -CrossVolumeRoot.'}
    foreach($point in 'copy_intent','copy_done','archive_verified'){
        $f=Fixture ('archive-'+$point);$p=Join-Path $f.source 'a';$dest=Join-Path $externalSandbox $point;WriteSample $p 'boundary archive'
        SaveManifest $f @((Item $p 'archive_then_purge' '' $dest))
        try{Fault $point;Attempt $f}finally{ResetFault}
        $null=Run $f Resume;$null=Run $f Resume;$null=Run $f Verify
        Assert ([IO.File]::ReadAllText($dest) -eq 'boundary archive') "Archive failed after $point."
    }
}
Test 'Archive intent cannot claim externally created identical destination' {
    if(-not $externalSandbox){throw 'SKIP: Cross-volume test requires -CrossVolumeRoot.'}
    $f=Fixture 'archive-ownership';$p=Join-Path $f.source 'a';$dest=Join-Path $externalSandbox 'foreign';WriteSample $p 'same bytes'
    SaveManifest $f @((Item $p 'archive_then_purge' '' $dest))
    try{Fault 'archive_intent';Attempt $f}finally{ResetFault}
    WriteSample $dest 'same bytes';Attempt $f Resume
    Assert (Test-Path -LiteralPath $p) 'Archive claimed an externally created destination.'
}
Test 'Resume reconciles payload removed before metadata deletion' {
    $f=Fixture 'partial-purge';$p=Join-Path $f.source 'a';WriteSample $p;SaveManifest $f @((Item $p))
    try{Fault 'after_delete';Attempt $f}finally{ResetFault}
    $staged=@(Records $f|Where-Object type -eq staged)[-1].data
    Assert ((Test-Path -LiteralPath $staged.i) -and -not(Test-Path -LiteralPath $staged.r)) 'Expected metadata-only interrupted state not reached.'
    $r=Run $f Resume;Assert ($r.exitCode -eq 0) 'Resume failed after payload deletion.'
    $r=Run $f Resume;Assert ($r.exitCode -eq 0) 'Repeated Resume failed.'
    $r=Run $f Verify;Assert ($r.exitCode -eq 0) 'Verify failed after interrupted purge recovery.'
}
Test 'Resume handles interruption before and after recycle and metadata removal' {
    foreach($point in 'recycle_intent','after_recycle','purge_started','delete_intent','metadata_delete_intent','after_metadata_delete'){
        $f=Fixture ('boundary-'+$point);$p=Join-Path $f.source 'a';WriteSample $p;SaveManifest $f @((Item $p))
        try{Fault $point;Attempt $f}finally{ResetFault}
        $r=Run $f Resume;Assert ($r.exitCode -eq 0) "Resume failed at $point."
        $r=Run $f Resume;Assert ($r.exitCode -eq 0) "Repeated Resume failed at $point."
        $r=Run $f Verify;Assert ($r.exitCode -eq 0) "Verify failed at $point."
        Assert (-not(Test-Path -LiteralPath $p)) "Source remains at $point."
    }
}
Test 'Persistent journal failure stops batch before purge' {
    $f=Fixture 'journal-failure';$p=Join-Path $f.source 'first';$q=Join-Path $f.source 'later';WriteSample $p;WriteSample $q;SaveManifest $f @((Item $p),(Item $q))
    try{LockJournalAfterStage $f;Attempt $f}finally{ResetFault}
    $staged=@(Records $f|Where-Object type -eq staged)[-1].data
    Assert ((Test-Path -LiteralPath $staged.i) -and (Test-Path -LiteralPath $staged.r)) 'Journal failure allowed purge.'
    Assert (Test-Path -LiteralPath $q) 'Journal failure did not stop later destructive action.'
    $r=Run $f Resume;Assert ($r.exitCode -eq 0) 'Journal failure recovery failed.'
}
Test 'Incomplete journal tail preserved and rejected' {
    $f=Fixture 'journal-tail';$p=Join-Path $f.source 'a';WriteSample $p;SaveManifest $f @((Item $p 'recycle'))
    $null=Run $f Execute;$journal=Join-Path $f.state 'journal.jsonl';[IO.File]::AppendAllText($journal,'{"partial":')
    $hash=(Get-FileHash -LiteralPath $journal).Hash;$rejected=$false;try{$null=Run $f Resume}catch{$rejected=$true}
    Assert $rejected 'Incomplete journal tail accepted.';Assert ((Get-FileHash -LiteralPath $journal).Hash -eq $hash) 'Incomplete journal evidence rewritten.'
}
Test 'Preexisting recycle entries unchanged' {
    $now=BinSnapshot
    foreach($key in $baseline.Keys){Assert ($now.ContainsKey($key) -and $now[$key] -eq $baseline[$key]) "Unrelated recycle entry changed: $key"}
}
$report=[ordered]@{sandbox=$sandbox;crossVolumeSandbox=$externalSandbox;passed=@($results|Where-Object status -eq PASS).Count;failed=@($results|Where-Object status -eq FAIL).Count;skipped=@($results|Where-Object status -eq SKIP).Count;tests=@($results);note='Generated samples and their recycle entries are retained for inspection. Never empty the whole recycle bin.'}
$report|ConvertTo-Json -Depth 10
if($report.failed){throw "$($report.failed) integration tests failed; samples retained at $sandbox"}
