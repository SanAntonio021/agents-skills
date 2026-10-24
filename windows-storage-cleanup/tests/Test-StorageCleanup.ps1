#requires -Version 7.0
[CmdletBinding()]
param([string]$ModulePath = (Join-Path $PSScriptRoot '../scripts/StorageCleanup.psm1'), [string]$CrossVolumeRoot, [switch]$LargeBenchmark)
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
    return @{root=$root;source=(Join-Path $root 'source');kept=(Join-Path $root 'kept');control=(Join-Path $root 'control');manifest=(Join-Path $root 'control/manifest.json');state=(Join-Path $root 'state')}
}
function SaveManifest($F, [object[]]$Items) {
    $roots=@($F.source,$F.kept)
    if($externalSandbox){$roots+=@($externalSandbox)}
    $m=[ordered]@{schemaVersion=1;batchId=[guid]::NewGuid().ToString('N');approvedRoots=$roots;items=@($Items)}
    [IO.File]::WriteAllText($F.manifest,($m|ConvertTo-Json -Depth 20),[Text.UTF8Encoding]::new($false))
}
function SaveSelection($F, [object[]]$Items, [string[]]$Roots=@($F.source,$F.kept)) {
    $p=Join-Path $F.control 'selection.json'
    $m=[ordered]@{schemaVersion=1;batchId=[guid]::NewGuid().ToString('N');approvedRoots=@($Roots);items=@($Items)}
    [IO.File]::WriteAllText($p,($m|ConvertTo-Json -Depth 20),[Text.UTF8Encoding]::new($false))
    return $p
}
function Selected([string]$Source, [string]$Action='recycle_then_purge', [string]$Retained='', [string]$Archive='') {
    $i=[ordered]@{source=$Source;action=$Action}
    if($Retained){$i.retainedCopy=$Retained}
    if($Archive){$i.archiveDestination=$Archive}
    return $i
}
function Run($F,[string]$Mode) { $r=Invoke-StorageCleanup -Mode $Mode -ManifestPath $F.manifest -StateDirectory $F.state;if($r.exitCode -ne 0){throw ($r|ConvertTo-Json -Depth 12 -Compress)};return $r }
function Status($F) { Invoke-StorageCleanup -Mode Status -ManifestPath $F.manifest -StateDirectory $F.state }
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
Test 'Manifest generator captures files, directories, empty members and actions' {
    $f=Fixture 'manifest-generate'
    $file=Join-Path $f.source '资料/视频.mp4';WriteSample $file 'generated file'
    $directory=Join-Path $f.source '缓存';WriteSample (Join-Path $directory '子目录/工具.bin') 'generated member'
    $null=[IO.Directory]::CreateDirectory((Join-Path $directory '空目录'))
    $archiveSource=Join-Path $f.source '归档目录';WriteSample (Join-Path $archiveSource '待归档.txt') 'archive member'
    $retained=Join-Path $f.kept '视频.mp4';WriteSample $retained 'generated file'
    $archive=Join-Path $f.kept '缓存归档'
    $selection=SaveSelection $f @(
        (Selected $file 'recycle' $retained),
        (Selected $directory 'recycle_then_purge'),
        (Selected $archiveSource 'archive_then_purge' '' $archive)
    )
    $output=Join-Path $f.control 'manifest.json'
    $result=New-StorageCleanupManifest -SelectionPath $selection -OutputPath $output
    Assert ($result.exitCode -eq 0 -and (Test-Path -LiteralPath $output)) 'Manifest generator did not create output.'
    $manifest=Get-Content -LiteralPath $output -Raw|ConvertFrom-Json
    Assert (@($manifest.items).Count -eq 3) 'Manifest item count changed.'
    Assert (@($manifest.items.id) -join ',' -eq 'item-001,item-002,item-003') 'Manifest item IDs are not stable.'
    $generatedFile=@($manifest.items|Where-Object id -eq 'item-001')[0]
    Assert ($generatedFile.sha256 -eq (Get-FileHash -LiteralPath $file).Hash) 'Generated file hash mismatch.'
    $generatedDirectory=@($manifest.items|Where-Object id -eq 'item-002')[0]
    Assert (@($generatedDirectory.members|Where-Object {$_.kind -eq 'directory' -and $_.relativePath -eq '空目录'}).Count -eq 1) 'Empty directory was not captured.'
    Assert ($result.files -ge 2 -and $result.directories -ge 2) 'Generator summary omitted members.'
    $f.manifest=$output
    $check=Run $f Check
    Assert ($check.exitCode -eq 0 -and @($check.items).Count -eq 3) 'Generated manifest did not pass Check.'
}
Test 'Manifest generator rejects unsafe or ambiguous selections' {
    $f=Fixture 'manifest-reject';$file=Join-Path $f.source 'a.txt';WriteSample $file 'safe sample';$output=Join-Path $f.control 'manifest.json'
    $cases=[Collections.Generic.List[object]]::new()
    $cases.Add(@{items=@((Selected (Join-Path $f.source '*') 'recycle'));roots=@($f.source);label='wildcard'})
    $unknown=Selected $file 'recycle';$unknown.unknownField='x';$cases.Add(@{items=@($unknown);roots=@($f.source);label='unknown field'})
    $parent=Join-Path $f.source 'parent';WriteSample (Join-Path $parent 'child.txt');$cases.Add(@{items=@((Selected $parent),(Selected (Join-Path $parent 'child.txt')));roots=@($f.source);label='overlap'})
    $junction=Join-Path $f.source 'junction';$junctionTarget=Join-Path $f.kept 'junction-target';WriteSample (Join-Path $junctionTarget 'item.txt');$null=New-Item -ItemType Junction -Path $junction -Target $junctionTarget
    $cases.Add(@{items=@((Selected $junction));roots=@($f.source);label='junction'})
    $hardSource=Join-Path $f.source 'hard-source.txt';$hardAlias=Join-Path $f.kept 'hard-alias.txt';WriteSample $hardSource 'hard-link sample';$null=New-Item -ItemType HardLink -Path $hardAlias -Target $hardSource
    $cases.Add(@{items=@((Selected $hardSource 'recycle'));roots=@($f.source,$f.kept);label='hardlink'})
    $hardDirectory=Join-Path $f.source 'hard-directory';$hardMember=Join-Path $hardDirectory 'member.txt';$hardDirectoryAlias=Join-Path $f.kept 'directory-member-alias.txt';WriteSample $hardMember 'directory hard-link sample';$null=New-Item -ItemType HardLink -Path $hardDirectoryAlias -Target $hardMember
    $cases.Add(@{items=@((Selected $hardDirectory 'recycle'));roots=@($f.source,$f.kept);label='directory hardlink'})
    $cases.Add(@{items=@((Selected $env:windir 'recycle'));roots=@($env:windir);label='system path'})
    foreach($case in $cases){
        $selection=SaveSelection $f $case.items $case.roots
        $rejected=$false;try{$null=New-StorageCleanupManifest -SelectionPath $selection -OutputPath $output}catch{$rejected=$true}
        Assert $rejected "Generator accepted $($case.label)."
        Assert (-not(Test-Path -LiteralPath $output)) "Generator left output after $($case.label)."
    }
    $safeSelection=SaveSelection $f @((Selected $file 'recycle'))
    $targetDirectory=Join-Path $f.source 'output-target';WriteSample (Join-Path $targetDirectory 'child.txt')
    $targetSelection=SaveSelection $f @((Selected $targetDirectory 'recycle'))
    $insideTarget=Join-Path $targetDirectory 'manifest.json'
    $rejected=$false;try{$null=New-StorageCleanupManifest -SelectionPath $targetSelection -OutputPath $insideTarget}catch{$rejected=$true}
    Assert ($rejected -and -not(Test-Path -LiteralPath $insideTarget)) 'Generator wrote its manifest inside a cleanup target.'
    $protectedOutputs=@(
        [IO.Path]::GetPathRoot($f.source),
        (Join-Path $env:windir 'cc-switch-manifest-should-not-exist.json'),
        (Join-Path $env:ProgramFiles 'cc-switch-manifest-should-not-exist.json'),
        (Join-Path $env:ProgramData 'cc-switch-manifest-should-not-exist.json'),
        'C:\$Recycle.Bin\cc-switch-manifest-should-not-exist.json'
    )
    foreach($protectedOutput in $protectedOutputs){
        $rejected=$false;try{$null=New-StorageCleanupManifest -SelectionPath $safeSelection -OutputPath $protectedOutput}catch{$rejected=$true}
        Assert $rejected "Generator accepted protected output path: $protectedOutput"
    }
    $null=New-StorageCleanupManifest -SelectionPath $safeSelection -OutputPath $output
    $rejected=$false;try{$null=New-StorageCleanupManifest -SelectionPath $safeSelection -OutputPath $output}catch{$rejected=$true}
    Assert $rejected 'Generator overwrote an existing manifest.'
}
Test 'Recycle sentinel remains recoverable' {
    $f=Fixture 'sentinel';$p=Join-Path $f.source 'sentinel.txt';WriteSample $p 'unrelated sentinel';SaveManifest $f @((Item $p 'recycle'))
    $null=Run $f Execute
    Assert (-not(Test-Path -LiteralPath $p)) 'Recycle did not remove source.'
    Assert ((Status $f).items[0].status -eq 'completed') 'Status treated a completed recycle as attention.'
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
Test 'Verified recycled payload clears read-only before permanent deletion' {
    $f=Fixture 'readonly-purge';$p=Join-Path $f.source 'readonly.txt';WriteSample $p 'readonly payload'
    (Get-Item -LiteralPath $p).IsReadOnly=$true
    SaveManifest $f @((Item $p 'recycle_then_purge'))
    $null=Run $f Execute
    $r=Run $f Resume
    Assert ($r.exitCode -eq 0 -and -not(Test-Path -LiteralPath $p)) 'Read-only recycled payload was not purged.'
    $null=Run $f Verify
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
Test 'Journal record index returns the last record after append' {
    $f=Fixture 'record-index';$journal=Join-Path $f.control 'index-journal.jsonl'
    $result=& (Get-Module StorageCleanup) {
        param($JournalPath)
        $context=@{records=[Collections.Generic.List[object]]::new();journal=$JournalPath}
        Write-SCJournal $context 'staged' 'same-id' @{value=1}
        Write-SCJournal $context 'staged' 'same-id' @{value=2}
        $indexed=Get-SCRecord $context 'staged' 'same-id'
        $lazyContext=@{records=[Collections.Generic.List[object]]::new();journal=$null}
        $lazyContext.records.Add(@{type='completed';id='lazy';data=@{value=1}})
        $lazyContext.records.Add(@{type='completed';id='lazy';data=@{value=2}})
        $lazy=Get-SCRecord $lazyContext 'completed' 'lazy'
        [pscustomobject]@{indexed=$indexed.data.value;lazy=$lazy.data.value;hasIndex=$lazyContext.ContainsKey('recordIndex')}
    } $journal
    Assert ($result.indexed -eq 2 -and $result.lazy -eq 2 -and $result.hasIndex) 'Record lookup did not preserve last-record semantics.'
}
Test 'Progress emits aggregate JSON to stderr only when enabled' {
    $writer=[IO.StringWriter]::new();$oldError=[Console]::Error
    try{
        [Console]::SetError($writer)
        $result=& (Get-Module StorageCleanup) {
            $manifest=@{items=@(@{id='item-001';kind='directory';source='C:\Synthetic';action='recycle';bytes=1;members=@(1..1001|ForEach-Object{@{relativePath="d$_";kind='directory';bytes=0}})})}
            $context=@{records=[Collections.Generic.List[object]]::new()}
            $progress=Initialize-SCProgress $manifest 'Execute' $context
            Set-SCCurrentProgress $progress $manifest.items[0] 1
            Write-SCProgress $progress 'starting' -Force
            [pscustomobject]@{enabled=$progress.enabled;members=$progress.membersTotal}
        }
    }finally{[Console]::SetError($oldError)}
    $line=($writer.ToString().Trim()|ConvertFrom-Json)
    Assert ($result.enabled -and $result.members -eq 1001) 'Progress did not enable above the member threshold.'
    Assert ($line.event -eq 'progress' -and $line.membersTotal -eq 1001 -and $line.PSObject.Properties.Name -notcontains 'source') 'Progress JSON omitted aggregate fields or leaked a path.'
}
Test 'Progress accounts file completion and respects the interval' {
    $writer=[IO.StringWriter]::new();$oldError=[Console]::Error
    try{
        [Console]::SetError($writer)
        $result=& (Get-Module StorageCleanup) {
            $file=@{id='item-001';kind='file';source='C:\Synthetic\a';action='recycle_then_purge';bytes=7;members=@()}
            $other=@{id='item-002';kind='directory';source='C:\Synthetic\b';action='recycle';bytes=0;members=@(1..1000|ForEach-Object{@{relativePath="d$_";kind='directory';bytes=0}})}
            $context=@{records=[Collections.Generic.List[object]]::new()}
            $progress=Initialize-SCProgress @{items=@($file,$other)} 'Execute' $context
            Set-SCCurrentProgress $progress $file 1
            foreach($n in 1..10){Write-SCProgress $progress 'starting'}
            $progress.lastEmitUtc=[datetime]::UtcNow.AddSeconds(-6)
            Complete-SCProgressItem $progress $file
            [pscustomobject]@{itemMembersDone=$progress.itemMembersDone;membersDone=$progress.membersDone;itemBytesDone=$progress.itemBytesDone;bytesDone=$progress.bytesDone}
        }
    }finally{[Console]::SetError($oldError)}
    $events=@($writer.ToString().Trim().Split("`n",[StringSplitOptions]::RemoveEmptyEntries))
    Assert ($result.itemMembersDone -eq 1 -and $result.membersDone -eq 1 -and $result.itemBytesDone -eq 7 -and $result.bytesDone -eq 7) 'Progress did not account a completed file item.'
    $completedEvent=$events[-1]|ConvertFrom-Json
    Assert ($events.Count -eq 2 -and $completedEvent.phase -eq 'completed' -and $completedEvent.itemMembersDone -eq 1 -and $completedEvent.bytesDone -eq 7) 'Progress ignored the interval or omitted visible completion counts.'
}
Test 'Automatic large-batch progress preserves the final result object' {
    $f=Fixture 'progress-batch';$source=Join-Path $f.source 'large';$null=[IO.Directory]::CreateDirectory($source)
    for($n=1;$n -le 1001;$n++){$null=[IO.Directory]::CreateDirectory((Join-Path $source ('d'+$n)))}
    SaveManifest $f @((Item $source))
    $writer=[IO.StringWriter]::new();$oldError=[Console]::Error
    try{
        [Console]::SetError($writer)
        $result=Invoke-StorageCleanup -Mode Execute -ManifestPath $f.manifest -StateDirectory $f.state
    }finally{[Console]::SetError($oldError)}
    $events=@($writer.ToString().Trim().Split("`n",[StringSplitOptions]::RemoveEmptyEntries)|ForEach-Object{$_|ConvertFrom-Json})
    Assert ($events.Count -gt 0 -and @($events|Where-Object event -ne 'progress').Count -eq 0) 'Automatic progress emitted a malformed event.'
    Assert ($events.Count -lt 1001) 'Automatic progress emitted one event per item instead of rate limiting.'
    Assert ($result.exitCode -eq 0 -and $result.items[0].status -eq 'completed') 'Progress capture changed the final cleanup result.'
    Assert (-not(Test-Path -LiteralPath $source)) 'Large progress fixture was not cleaned.'
}
Test 'Status reports durable phases without mutating state' {
    $cases=@(
        @{name='not-started';fault=$null;expected='not_started'},
        @{name='recycling';fault='after_recycle';expected='recycling'},
        @{name='staged';fault='staged';expected='staged'},
        @{name='purging';fault='after_delete';expected='purging'}
    )
    foreach($case in $cases){
        $f=Fixture ('status-'+$case.name);$p=Join-Path $f.source 'a';WriteSample $p;SaveManifest $f @((Item $p))
        if($case.fault){try{Fault $case.fault;Attempt $f}finally{ResetFault}}
        $before=@(Get-ChildItem -LiteralPath $f.root -Recurse -File -Force|ForEach-Object{$_.FullName+':'+$_.Length+':'+$_.LastWriteTimeUtc.Ticks})
        $status=Status $f
        $after=@(Get-ChildItem -LiteralPath $f.root -Recurse -File -Force|ForEach-Object{$_.FullName+':'+$_.Length+':'+$_.LastWriteTimeUtc.Ticks})
        Assert ($status.items[0].status -eq $case.expected) "Status misreported $($case.name)."
        Assert (($before -join '|') -eq ($after -join '|')) 'Status changed the fixture.'
    }
    $completed=Fixture 'status-completed';$p=Join-Path $completed.source 'a';WriteSample $p;SaveManifest $completed @((Item $p));$null=Run $completed Execute
    Assert ((Status $completed).items[0].status -eq 'completed') 'Status did not report completion.'
    $attention=Fixture 'status-attention';$p=Join-Path $attention.source 'a';WriteSample $p;SaveManifest $attention @((Item $p));[IO.File]::Delete($p)
    Assert ((Status $attention).items[0].status -eq 'attention') 'Status did not flag missing evidence.'
    $blocked=Fixture 'status-blocked-path';$p=Join-Path $blocked.source 'a';WriteSample $p;SaveManifest $blocked @((Item $p))
    try{Fault 'after_delete';Attempt $blocked}finally{ResetFault}
    $module=Get-Module StorageCleanup
    & $module {$script:originalStatusPath=(Get-Command Test-SCStatusPath).ScriptBlock;Set-Item Function:\Test-SCStatusPath -Value {param([string]$Path)return $null}}
    try{$blockedStatus=Status $blocked}finally{& $module {Set-Item Function:\Test-SCStatusPath -Value $script:originalStatusPath;Remove-Variable originalStatusPath -Scope Script}}
    Assert ($blockedStatus.items[0].status -eq 'purging' -and $null -eq $blockedStatus.items[0].recyclePayloadExists) 'Status did not survive inaccessible recycle paths.'
    $metadataOnly=& $module {
        $script:statusSource='C:\Synthetic\source';$script:statusMetadata='C:\Synthetic\metadata';$script:statusPayload='C:\Synthetic\payload'
        $item=@{id='item-001';kind='file';source=$script:statusSource;action='recycle';bytes=1;members=@()}
        $context=@{records=[Collections.Generic.List[object]]::new()}
        $pair=@{i=$script:statusMetadata;r=$script:statusPayload}
        $context.records.Add(@{type='staged';id='item-001';data=$pair;utc=[datetime]::UtcNow.AddSeconds(-2).ToString('o')})
        $context.records.Add(@{type='completed';id='item-001';data=@{action='recycle';pair=$pair};utc=[datetime]::UtcNow.AddSeconds(-1).ToString('o')})
        $script:originalStatusPath=(Get-Command Test-SCStatusPath).ScriptBlock
        Set-Item Function:\Test-SCStatusPath -Value {
            param([string]$Path)
            if($Path -eq $script:statusSource){return $false}
            if($Path -eq $script:statusMetadata){return $true}
            if($Path -eq $script:statusPayload){return $false}
            return $null
        }
        try{Get-SCStatusResult @{batchId='batch';items=@($item)} $context 'digest'}
        finally{
            Set-Item Function:\Test-SCStatusPath -Value $script:originalStatusPath
            Remove-Variable originalStatusPath,statusSource,statusMetadata,statusPayload -Scope Script -ErrorAction SilentlyContinue
        }
    }
    Assert ($metadataOnly.items[0].status -eq 'attention' -and $metadataOnly.items[0].recycleMetadataExists -eq $true -and $metadataOnly.items[0].recyclePayloadExists -eq $false) 'Status treated metadata without its payload as completed recycle.'
    $noHash=Fixture 'status-no-hash';$p=Join-Path $noHash.source 'a';WriteSample $p;SaveManifest $noHash @((Item $p))
    & $module {$script:originalGetHash=(Get-Command Get-SCHash).ScriptBlock;Set-Item Function:\Get-SCHash -Value {param([string]$Path)throw 'HASH_CALLED_DURING_STATUS'}}
    try{$noHashStatus=Status $noHash}finally{& $module {Set-Item Function:\Get-SCHash -Value $script:originalGetHash;Remove-Variable originalGetHash -Scope Script}}
    Assert ($noHashStatus.items[0].status -eq 'not_started') 'Status recalculated source hashes.'
    $shortId=& $module {
        $item=@{id='a';kind='file';source='C:\Synthetic\source';action='recycle';bytes=1;members=@()}
        $eventUtc=[datetime]::UtcNow.ToString('o')
        $context=@{records=[Collections.Generic.List[object]]::new()}
        $context.records.Add(@{type='delete_done';id='a|C:\Synthetic\payload';data=@{};utc=$eventUtc})
        $script:originalStatusPath=(Get-Command Test-SCStatusPath).ScriptBlock
        Set-Item Function:\Test-SCStatusPath -Value {param([string]$Path)return $false}
        try{Get-SCStatusResult @{batchId='batch';items=@($item)} $context 'digest'}
        finally{Set-Item Function:\Test-SCStatusPath -Value $script:originalStatusPath;Remove-Variable originalStatusPath -Scope Script}
    }
    Assert ($shortId.items[0].membersDone -eq 1 -and -not [string]::IsNullOrWhiteSpace([string]$shortId.items[0].lastEventUtc)) 'Status lost last-event evidence for a single-character item ID.'
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
if($LargeBenchmark){
    Test 'Large journal index benchmark completes within ten seconds' {
        $result=& (Get-Module StorageCleanup) {
            $context=@{records=[Collections.Generic.List[object]]::new();recordIndex=@{}}
            for($n=0;$n -lt 100000;$n++){
                $record=@{type=('type'+($n%10));id=('id'+$n);data=@{value=$n}}
                $context.records.Add($record);Add-SCRecordIndex $context $record
            }
            $watch=[Diagnostics.Stopwatch]::StartNew()
            $valid=$true
            for($n=0;$n -lt 20000;$n++){
                $id='id'+($n*5);$record=Get-SCRecord $context ('type'+(($n*5)%10)) $id
                if(!$record -or $record.data.value -ne ($n*5)){$valid=$false;break}
            }
            $watch.Stop()
            [pscustomobject]@{valid=$valid;seconds=$watch.Elapsed.TotalSeconds}
        }
        Write-Host ('BENCH large-journal lookup {0:N3}s' -f $result.seconds)
        Assert $result.valid 'Large journal benchmark returned incorrect records.'
        Assert ($result.seconds -lt 10) 'Large journal benchmark exceeded ten seconds.'
    }
    Test 'Large Status benchmark completes within ten seconds' {
        $result=& (Get-Module StorageCleanup) {
            $items=[Collections.Generic.List[object]]::new();$context=@{records=[Collections.Generic.List[object]]::new();recordIndex=@{}}
            for($n=1;$n -le 20000;$n++){
                $id=('item-{0:D5}' -f $n)
                $items.Add(@{id=$id;kind='file';source=('C:\Synthetic\a'+$n);action='recycle';bytes=1;members=@()})
                $record=@{type='delete_done';id=($id+'|C:\Synthetic\payload'+$n);data=@{};utc=[datetime]::UtcNow.ToString('o')}
                $context.records.Add($record);Add-SCRecordIndex $context $record
            }
            $script:originalStatusPath=(Get-Command Test-SCStatusPath).ScriptBlock
            Set-Item Function:\Test-SCStatusPath -Value {param([string]$Path)return $false}
            $watch=[Diagnostics.Stopwatch]::StartNew()
            try{$status=Get-SCStatusResult @{batchId='benchmark';items=$items.ToArray()} $context 'digest'}
            finally{Set-Item Function:\Test-SCStatusPath -Value $script:originalStatusPath;Remove-Variable originalStatusPath -Scope Script}
            $watch.Stop()
            [pscustomobject]@{items=$status.items.Count;seconds=$watch.Elapsed.TotalSeconds}
        }
        Write-Host ('BENCH large-status {0:N3}s' -f $result.seconds)
        Assert ($result.items -eq 20000 -and $result.seconds -lt 10) 'Large Status benchmark regressed.'
    }
}
Test 'Preexisting recycle entries unchanged' {
    $now=BinSnapshot
    foreach($key in $baseline.Keys){Assert ($now.ContainsKey($key) -and $now[$key] -eq $baseline[$key]) "Unrelated recycle entry changed: $key"}
}
$report=[ordered]@{sandbox=$sandbox;crossVolumeSandbox=$externalSandbox;passed=@($results|Where-Object status -eq PASS).Count;failed=@($results|Where-Object status -eq FAIL).Count;skipped=@($results|Where-Object status -eq SKIP).Count;tests=@($results);note='Generated samples and their recycle entries are retained for inspection. Never empty the whole recycle bin.'}
$report|ConvertTo-Json -Depth 10
if($report.failed){throw "$($report.failed) integration tests failed; samples retained at $sandbox"}
