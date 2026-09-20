#requires -Version 7.0
Set-StrictMode -Version Latest

function Initialize-SCNative {
    if ('StorageCleanupNative' -as [type]) { return }
    Add-Type -TypeDefinition @'
using System;
using System.Text;
using System.Runtime.InteropServices;
using Microsoft.Win32.SafeHandles;
public static class StorageCleanupNative {
 [ComImport,Guid("43826d1e-e718-42ee-bc55-a1e261c37bfe"),InterfaceType(ComInterfaceType.InterfaceIsIUnknown)] interface IShellItem { void BindToHandler(); void GetParent(); void GetDisplayName(); void GetAttributes(); void Compare(); }
 [ComImport,Guid("947AAB5F-0A5C-4C13-B4D6-4BF7836FC9F8"),InterfaceType(ComInterfaceType.InterfaceIsIUnknown)] interface IFileOperation {
 void Advise(IntPtr sink,out uint cookie); void Unadvise(uint cookie); void SetOperationFlags(uint flags); void SetProgressMessage([MarshalAs(UnmanagedType.LPWStr)]string msg);void SetProgressDialog(IntPtr p);void SetProperties(IntPtr p);void SetOwnerWindow(uint hwnd);void ApplyPropertiesToItem(IShellItem i);void ApplyPropertiesToItems(IntPtr p);void RenameItem(IShellItem i,[MarshalAs(UnmanagedType.LPWStr)]string n,IntPtr s);void RenameItems(IntPtr p,[MarshalAs(UnmanagedType.LPWStr)]string n);void MoveItem(IShellItem i,IShellItem d,[MarshalAs(UnmanagedType.LPWStr)]string n,IntPtr s);void MoveItems(IntPtr p,IShellItem d);void CopyItem(IShellItem i,IShellItem d,[MarshalAs(UnmanagedType.LPWStr)]string n,IntPtr s);void CopyItems(IntPtr p,IShellItem d);void DeleteItem(IShellItem i,IntPtr s);void DeleteItems(IntPtr p);void NewItem(IShellItem d,uint a,[MarshalAs(UnmanagedType.LPWStr)]string n,[MarshalAs(UnmanagedType.LPWStr)]string t,IntPtr s);void PerformOperations();void GetAnyOperationsAborted([MarshalAs(UnmanagedType.Bool)]out bool aborted);
 }
 [DllImport("shell32.dll",CharSet=CharSet.Unicode,PreserveSig=false)] static extern void SHCreateItemFromParsingName(string path,IntPtr binding,ref Guid iid,[MarshalAs(UnmanagedType.Interface)]out IShellItem item);
 public static void Recycle(string path) { Exception error=null;var thread=new System.Threading.Thread(()=>{object obj=null;IShellItem item=null;try {obj=Activator.CreateInstance(Type.GetTypeFromCLSID(new Guid("3ad05575-8857-4850-9277-11b85bdb8e09")));var op=(IFileOperation)obj;op.SetOperationFlags(0x00080000|0x00100000|0x00000400|0x00000010|0x00000004);var id=new Guid("43826d1e-e718-42ee-bc55-a1e261c37bfe");SHCreateItemFromParsingName(path,IntPtr.Zero,ref id,out item);op.DeleteItem(item,IntPtr.Zero);op.PerformOperations();bool aborted;op.GetAnyOperationsAborted(out aborted);if(aborted)throw new InvalidOperationException("Recycle operation aborted");}catch(Exception e){error=e;}finally{if(item!=null)Marshal.FinalReleaseComObject(item);if(obj!=null)Marshal.FinalReleaseComObject(obj);}});thread.SetApartmentState(System.Threading.ApartmentState.STA);thread.Start();thread.Join();if(error!=null)throw new InvalidOperationException("Recycle failed: "+error.Message,error); }
 [StructLayout(LayoutKind.Sequential)] public struct Info { public uint Attr; public System.Runtime.InteropServices.ComTypes.FILETIME Creation,Access,Write; public uint Volume,High,Low,Links,IndexHigh,IndexLow; }
 [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true)] static extern SafeFileHandle CreateFileW(string p,uint a,uint s,IntPtr sec,uint c,uint f,IntPtr t);
 [DllImport("kernel32.dll",SetLastError=true)] static extern bool GetFileInformationByHandle(SafeFileHandle h,out Info i);
 [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true)] static extern IntPtr FindFirstFileNameW(string p,uint flags,ref uint len,StringBuilder b);
 [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true)] static extern bool FindNextFileNameW(IntPtr h,ref uint len,StringBuilder b);
 [DllImport("kernel32.dll")] static extern bool FindClose(IntPtr h);
 public static string Identity(string p) { using(var h=CreateFileW(@"\\?\"+p,0,7,IntPtr.Zero,3,0x02000000,IntPtr.Zero)) { Info i;if(h.IsInvalid||!GetFileInformationByHandle(h,out i))throw new System.ComponentModel.Win32Exception();return i.Volume+":"+i.IndexHigh+":"+i.IndexLow; } }
 public static string[] Links(string p) { var list=new System.Collections.Generic.List<string>();uint n=32768;var b=new StringBuilder((int)n);var h=FindFirstFileNameW(@"\\?\"+p,0,ref n,b);if(h==new IntPtr(-1))throw new System.ComponentModel.Win32Exception();try { list.Add(System.IO.Path.GetPathRoot(p).TrimEnd('\\')+b.ToString());while(true){n=32768;b.Clear();if(!FindNextFileNameW(h,ref n,b)){int e=Marshal.GetLastWin32Error();if(e!=38)throw new System.ComponentModel.Win32Exception(e);break;}list.Add(System.IO.Path.GetPathRoot(p).TrimEnd('\\')+b.ToString());} }finally{FindClose(h);}return list.ToArray(); }
}
'@
    Add-Type -AssemblyName Microsoft.VisualBasic
}

function Get-SCPath([string]$Path) {
    if ([string]::IsNullOrWhiteSpace($Path) -or $Path -notmatch '^[A-Za-z]:\\' -or $Path.IndexOf(':',2) -ge 0) { throw "Only absolute local drive paths are supported: $Path" }
    if ($Path -match '(?i)(^|\\)(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|\\|$)' -or $Path -match '[*?]' -or $Path -match '~[0-9]' -or $Path -match '(^|\\)\.\.?(\\|$)' -or $Path -match '[ .](\\|$)') { throw "Ambiguous path: $Path" }
    [IO.Path]::GetFullPath($Path).TrimEnd('\')
}
function Test-SCWithin([string]$Path,[string]$Root) { $Path.Equals($Root,[StringComparison]::OrdinalIgnoreCase) -or $Path.StartsWith($Root+'\',[StringComparison]::OrdinalIgnoreCase) }
function Assert-SCPlain([string]$Path) {
    $cursor=$Path
    while ($cursor -and $cursor.Length -gt 3) {
        if (Test-Path -LiteralPath $cursor) {
            $a=[IO.File]::GetAttributes($cursor)
            if (([int]$a -band (0x400 -bor 0x1000 -bor 0x40000 -bor 0x400000)) -ne 0) { throw "Reparse/offline/on-demand path is not supported: $cursor" }
        }
        $cursor=[IO.Path]::GetDirectoryName($cursor)
    }
}
function Assert-SCTarget([string]$Path,[string[]]$Roots) {
    $p=Get-SCPath $Path
    if ($p.Length -le 3 -or -not @($Roots|Where-Object {Test-SCWithin $p $_}).Count) { throw "Outside approved roots: $p" }
    $protected=@($env:windir,$env:ProgramFiles,${env:ProgramFiles(x86)},$env:ProgramData)|Where-Object {$_}
    foreach($r in $protected){if(Test-SCWithin $p (Get-SCPath $r)){throw "System or installed-application root: $p"}}
    if($p -match '(?i)^[A-Z]:\\(\$Recycle\.Bin|System Volume Information|Recovery|Windows\.old)(\\|$)' -or $p -match '(?i)^[A-Z]:\\(pagefile|swapfile|hiberfil)\.sys$'){throw "System-maintained target: $p"}
    Assert-SCPlain $p
    $p
}
function Get-SCValue($Object,[string]$Name,$Default=$null){if($Object.Contains($Name)){$Object[$Name]}else{$Default}}
function Get-SCHash([string]$Path){(Get-FileHash -LiteralPath $Path -Algorithm SHA256 -ErrorAction Stop).Hash}
function Get-SCEntries([string]$Path,[string]$Kind) {
    Assert-SCPlain $Path
    $item=Get-Item -LiteralPath $Path -Force -ErrorAction Stop
    if (($Kind -eq 'directory') -ne $item.PSIsContainer) { throw "Type changed: $Path" }
    if($Kind -eq 'file'){return ,$item}
    $stack=[Collections.Generic.Stack[string]]::new();$stack.Push($Path)
    $out=[Collections.Generic.List[object]]::new()
    while($stack.Count){foreach($e in Get-ChildItem -LiteralPath $stack.Pop() -Force -ErrorAction Stop){Assert-SCPlain $e.FullName;$out.Add($e);if($e.PSIsContainer){$stack.Push($e.FullName)}}}
    $out.ToArray()
}
function Get-SCExpected($Item,[string]$Base) {
    if($Item.kind -eq 'file'){return ,@{path=$Base;kind='file';bytes=[long]$Item.bytes;lastWriteTimeUtc=$Item.lastWriteTimeUtc;sha256=$Item.sha256}}
    foreach($m in $Item.members){
        if([IO.Path]::IsPathRooted($m.relativePath) -or $m.relativePath -match '(^|[\\/])\.\.?([\\/]|$)'){throw 'Invalid relative member'}
        $p=Get-SCPath ([IO.Path]::Combine($Base,$m.relativePath))
        if($p -eq $Base -or -not(Test-SCWithin $p $Base)){throw 'Member escapes directory'}
        @{path=$p;kind=$m.kind;bytes=[long](Get-SCValue $m bytes 0);lastWriteTimeUtc=$m.lastWriteTimeUtc;sha256=(Get-SCValue $m sha256)}
    }
}
function Assert-SCContent($Item,[string]$Path,[switch]$IgnoreRootTime,[switch]$IgnoreTimes) {
    $actual=@(Get-SCEntries $Path $Item.kind);$expected=@(Get-SCExpected $Item $Path)
    if($actual.Count -ne $expected.Count){throw "Member count changed: $Path"}
    $map=@{};foreach($e in $actual){$map[$e.FullName]=$e}
    if(!$IgnoreRootTime -and !$IgnoreTimes){$r=Get-Item -LiteralPath $Path -Force;if($r.LastWriteTimeUtc.Ticks -ne ([datetime]$Item.lastWriteTimeUtc).ToUniversalTime().Ticks){throw "Root timestamp changed: $Path"}}
    [long]$total=0
    foreach($e in $expected){
        if(!$map.ContainsKey($e.path)){throw "Missing member: $($e.path)"};$a=$map[$e.path]
        if(($e.kind -eq 'directory') -ne $a.PSIsContainer){throw 'Member type changed'}
        if(!$IgnoreTimes -and $a.LastWriteTimeUtc.Ticks -ne ([datetime]$e.lastWriteTimeUtc).ToUniversalTime().Ticks){throw "Timestamp changed: $($e.path)"}
        if($e.kind -eq 'file'){if($a.Length -ne $e.bytes -or (Get-SCHash $e.path) -ne $e.sha256){throw "Content changed: $($e.path)"};$total+=$a.Length}
    }
    if($total -ne [long]$Item.bytes){throw 'Manifest byte sum mismatch'}
}
function Get-SCBin([string]$Path){[IO.Path]::Combine([IO.Path]::GetPathRoot($Path),'$Recycle.Bin',[Security.Principal.WindowsIdentity]::GetCurrent().User.Value)}
function Get-SCBaseline([string]$Bin){$r=@{};if(Test-Path -LiteralPath $Bin){Assert-SCPlain $Bin;foreach($f in Get-ChildItem -LiteralPath $Bin -Force -ErrorAction Stop){$r[$f.Name]=@{ticks=$f.LastWriteTimeUtc.Ticks;length=$(if($f.PSIsContainer){0}else{$f.Length})}}};$r}
function Read-SCRecycleInfo([string]$Path) {
    Assert-SCPlain $Path;$b=[IO.File]::ReadAllBytes($Path)
    if($b.Length -lt 28){throw 'Invalid recycle metadata'};$v=[BitConverter]::ToInt64($b,0)
    if($v -eq 2){$n=[BitConverter]::ToInt32($b,24);if($n -lt 1 -or (28+2L*$n) -gt $b.Length){throw 'Invalid recycle name length'};$name=[Text.Encoding]::Unicode.GetString($b,28,$n*2).TrimEnd([char]0)}
    elseif($v -eq 1){$name=[Text.Encoding]::Unicode.GetString($b,24,$b.Length-24).TrimEnd([char]0)}else{throw "Unknown recycle format: $v"}
    if($name.StartsWith('\\?\')){$name=$name.Substring(4)}
    @{original=(Get-SCPath $name);bytes=[BitConverter]::ToInt64($b,8);deletedUtc=[datetime]::FromFileTimeUtc([BitConverter]::ToInt64($b,16));metadataHash=(Get-SCHash $Path)}
}
function Invoke-SCCheckpoint([string]$Name) { } # Private, mockable crash boundary; never exposed as a CLI option.
function Write-SCJournal($Context,[string]$Type,[string]$Id,$Data) {
    $record=@{type=$Type;id=$Id;data=$Data;utc=[datetime]::UtcNow.ToString('o')}
    $bytes=[Text.UTF8Encoding]::new($false).GetBytes(($record|ConvertTo-Json -Depth 30 -Compress)+"`n")
    for($attempt=0;$attempt -lt 4;$attempt++){
        $writeStarted=$false
        try{$s=[IO.FileStream]::new($Context.journal,[IO.FileMode]::Append,[IO.FileAccess]::Write,[IO.FileShare]::Read);try{$writeStarted=$true;$s.Write($bytes);$s.Flush($true)}finally{$s.Dispose()};$Context.records.Add($record);break}
        catch{if($writeStarted -or $attempt -eq 3){throw [InvalidOperationException]::new('JOURNAL_FAILURE: '+$_.Exception.Message,$_.Exception)};Start-Sleep -Milliseconds (100*($attempt+1))}
    }
    Invoke-SCCheckpoint $Type
}
function Get-SCRecord($Context,[string]$Type,[string]$Id){@($Context.records|Where-Object {$_.type -eq $Type -and $_.id -eq $Id}|Select-Object -Last 1)|Select-Object -First 1}
function Find-SCPair($Item,$Intent) {
    $candidates=@();$bin=$Intent.bin
    if(Test-Path -LiteralPath $bin){foreach($f in Get-ChildItem -LiteralPath $bin -Force -ErrorAction Stop){if($f.Name.StartsWith('$I') -and !$Intent.baseline.Contains($f.Name)){
        try{$meta=Read-SCRecycleInfo $f.FullName;if($meta.original -eq $Item.source){if($meta.bytes -ne [long]$Item.bytes){throw 'Recycle size mismatch'};if($Intent.Contains('utc') -and $meta.deletedUtc -lt ([datetime]$Intent.utc).ToUniversalTime().AddSeconds(-2)){throw 'Recycle timestamp predates intent'};$r=Join-Path $bin ('$R'+$f.Name.Substring(2));$candidates+=@{i=$f.FullName;r=$r;metadataHash=$meta.metadataHash;bin=$bin}}}catch{throw "Unrecognized new recycle metadata; preserving batch: $($f.FullName): $($_.Exception.Message)"}
    }}}
    if($candidates.Count -ne 1){throw "Recycle match is not unique ($($candidates.Count)); preserve and inspect"}
    $candidates[0]
}
function Assert-SCPair($Item,$Pair){
    foreach($p in @($Pair.i,$Pair.r)){if([IO.Path]::GetDirectoryName((Get-SCPath $p)) -ne (Get-SCPath $Pair.bin)){throw 'Recycle pair escaped bin'};Assert-SCPlain $p}
    if([IO.Path]::GetFileName($Pair.i) -cnotmatch '^\$I' -or [IO.Path]::GetFileName($Pair.r) -cne ('$R'+[IO.Path]::GetFileName($Pair.i).Substring(2))){throw 'Invalid recycle pair names'}
    $m=Read-SCRecycleInfo $Pair.i
    if($m.original -ne $Item.source -or $m.metadataHash -ne $Pair.metadataHash){throw 'Recycle metadata changed'}
}
function Invoke-SCRecycle($Item){
    [StorageCleanupNative]::Recycle($Item.source)
}
function Get-SCSpace($Roots){$r=@{};foreach($root in $Roots){$drive=[IO.Path]::GetPathRoot($root);if(!$r.ContainsKey($drive)){$r[$drive]=[IO.DriveInfo]::new($drive).AvailableFreeSpace}};$r}

function Assert-SCManifest($Manifest,[string]$StateDirectory,[string]$ManifestPath) {
    if($Manifest.schemaVersion -ne 1 -or $Manifest.batchId -notmatch '^[A-Za-z0-9_-]{1,80}$' -or !$Manifest.approvedRoots.Count -or !$Manifest.items.Count){throw 'Invalid manifest header'}
    $roots=@($Manifest.approvedRoots|ForEach-Object {Get-SCPath $_});$paths=[Collections.Generic.List[string]]::new();$ids=@{}
    foreach($i in $Manifest.items){
        if($i.id -notmatch '^[A-Za-z0-9_-]{1,80}$' -or $ids.ContainsKey($i.id)){throw 'Invalid/duplicate item id'};$ids[$i.id]=$true
        if($i.kind -notin @('file','directory') -or $i.action -notin @('recycle','recycle_then_purge','archive_then_purge') -or [long]$i.bytes -lt 0){throw 'Invalid item contract'}
        $i.source=Assert-SCTarget $i.source $roots;[void][datetime]::Parse($i.lastWriteTimeUtc)
        if($i.kind -eq 'file' -and $i.sha256 -notmatch '^[A-Fa-f0-9]{64}$'){throw 'Invalid hash'}
        $seen=@{};foreach($e in @(Get-SCExpected $i $i.source)){if($seen.ContainsKey($e.path)){throw 'Duplicate member'};$seen[$e.path]=$true;if($e.kind -notin @('file','directory')){throw 'Invalid member kind'};[void][datetime]::Parse($e.lastWriteTimeUtc);if($e.kind -eq 'file' -and $e.sha256 -notmatch '^[a-fA-F0-9]{64}$'){throw 'Invalid member hash'}}
        $paths.Add($i.source)
        if($i.action -eq 'archive_then_purge'){$i.archiveDestination=Get-SCPath $i.archiveDestination;[void](Assert-SCTarget $i.archiveDestination @($i.archiveDestination));$paths.Add($i.archiveDestination)}
    }
    if($StateDirectory){$paths.Add((Get-SCPath $StateDirectory));Assert-SCPlain $StateDirectory
        if($StateDirectory -match '(?i)(^|\\)(OneDrive[^\\]*|BaiduSyncdisk|Dropbox|Nutstore|Google Drive)(\\|$)'){throw 'State directory must be confirmed local and outside sync/backup roots'}
        foreach($v in @($env:OneDrive,$env:OneDriveCommercial,$env:OneDriveConsumer)|Where-Object {$_}){if(Test-SCWithin $StateDirectory (Get-SCPath $v)){throw 'State directory is synchronized'}}
    }
    $paths.Add((Get-SCPath $ManifestPath))
    for($a=0;$a -lt $paths.Count;$a++){for($b=$a+1;$b -lt $paths.Count;$b++){if((Test-SCWithin $paths[$a] $paths[$b]) -or (Test-SCWithin $paths[$b] $paths[$a])){throw "Overlapping managed paths: $($paths[$a]), $($paths[$b])"}}}
    foreach($i in $Manifest.items){if(Get-SCValue $i retainedCopy){$i.retainedCopy=Get-SCPath $i.retainedCopy;Assert-SCPlain $i.retainedCopy;foreach($p in $paths){if((Test-SCWithin $i.retainedCopy $p) -or (Test-SCWithin $p $i.retainedCopy)){throw 'Retained copy overlaps managed paths'}}}}
    $roots
}

function Open-SCRetained($Item) {
    $held=[Collections.Generic.List[IDisposable]]::new()
    try{
        if(Get-SCValue $Item retainedCopy){Assert-SCContent $Item $Item.retainedCopy -IgnoreTimes
            $sources=@(Get-SCExpected $Item $Item.source|Where-Object kind -eq file);$dest=@(Get-SCExpected $Item $Item.retainedCopy|Where-Object kind -eq file)
            for($n=0;$n -lt $dest.Count;$n++){$f=$dest[$n];$s=[IO.FileStream]::new($f.path,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::Read);$held.Add($s)
                if((Test-Path -LiteralPath $sources[$n].path) -and [StorageCleanupNative]::Identity($sources[$n].path) -eq [StorageCleanupNative]::Identity($f.path)){throw 'Retained copy is the same physical file'}
                if((Get-SCHash $f.path) -ne $f.sha256){throw 'Retained copy changed'}
            }
        }
        return ,$held
    }catch{foreach($h in $held){$h.Dispose()};throw}
}

function Invoke-SCArchive($Context,$Item) {
    $dest=$Item.archiveDestination;$intent=Get-SCRecord $Context archive_intent $Item.id
    if(!$intent){if(Test-Path -LiteralPath $dest){throw 'Archive destination already exists'};Write-SCJournal $Context archive_intent $Item.id @{destination=$dest}}
    if($Item.kind -eq 'directory'){
        if(!(Test-Path -LiteralPath $dest)){[void][IO.Directory]::CreateDirectory($dest)}
        foreach($e in @(Get-SCExpected $Item $dest)|Where-Object kind -eq directory|Sort-Object {$_.path.Length}){Assert-SCPlain $e.path;if(!(Test-Path -LiteralPath $e.path)){[void][IO.Directory]::CreateDirectory($e.path)}}
    }else{[void][IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($dest))}
    $source=@(Get-SCExpected $Item $Item.source|Where-Object kind -eq file);$target=@(Get-SCExpected $Item $dest|Where-Object kind -eq file)
    for($n=0;$n -lt $source.Count;$n++){
        $s=$source[$n];$t=$target[$n];Assert-SCPlain $t.path
        if(Test-Path -LiteralPath $t.path){
            $owned=@($Context.records|Where-Object {$_.type -eq 'copy_intent' -and $_.id -eq $Item.id -and $_.data.path -eq $t.path -and $_.data.source -eq $s.path})
            if(!$owned.Count -or (Get-SCHash $t.path) -ne $s.sha256){throw "Incomplete, unowned or conflicting archive preserved: $($t.path)"};continue
        }
        Write-SCJournal $Context copy_intent $Item.id @{path=$t.path;source=$s.path}
        $input=[IO.FileStream]::new($s.path,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::Read)
        try{$output=[IO.FileStream]::new($t.path,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None);try{$input.CopyTo($output);$output.Flush($true)}finally{$output.Dispose()}}finally{$input.Dispose()}
        [IO.File]::SetLastWriteTimeUtc($t.path,([datetime]$s.lastWriteTimeUtc).ToUniversalTime())
        if((Get-SCHash $t.path) -ne $s.sha256){throw 'Archive verification failed'}
        Write-SCJournal $Context copy_done $Item.id @{path=$t.path}
    }
    Assert-SCContent $Item $dest -IgnoreTimes
    Write-SCJournal $Context archive_verified $Item.id @{destination=$dest}
}

function Invoke-SCPurge($Context,$Item,$Pair) {
    $purge=Get-SCRecord $Context purge_started $Item.id
    if(!$purge){Assert-SCPair $Item $Pair;Assert-SCContent $Item $Pair.r -IgnoreRootTime;Write-SCJournal $Context purge_started $Item.id $Pair}
    if(Test-Path -LiteralPath $Pair.i){Assert-SCPair $Item $Pair}
    elseif(!(Get-SCRecord $Context metadata_delete_intent $Item.id)){throw 'Recycle metadata disappeared unexpectedly'}
    $expected=@(Get-SCExpected $Item $Pair.r)
    if($Item.kind -eq 'directory'){$expected+=@{path=$Pair.r;kind='directory';bytes=0}}
    $allowed=@{};foreach($e in $expected){$allowed[$e.path]=$e}
    if(Test-Path -LiteralPath $Pair.r){foreach($a in @(Get-SCEntries $Pair.r $Item.kind)){if(!$allowed.ContainsKey($a.FullName)){throw 'Unexpected recycled member; preserve'};if(!$a.PSIsContainer){$e=$allowed[$a.FullName];if($a.Length -ne $e.bytes -or (Get-SCHash $a.FullName) -ne $e.sha256){throw 'Recycled contents changed during purge'}}}}
    foreach($e in $expected|Sort-Object @{Expression={if($_.kind -eq 'file'){0}else{1}}},@{Expression={$_.path.Length};Descending=$true}){
        $key=$Item.id+'|'+$e.path;$prior=Get-SCRecord $Context delete_intent $key
        if(!(Test-Path -LiteralPath $e.path)){if(!$prior){throw 'Recycled member disappeared without an intent'};continue}
        Assert-SCPlain $e.path
        if(!(Test-SCWithin (Get-SCPath $e.path) (Get-SCPath $Pair.r))){throw 'Purge path escaped payload'}
        $payloadLock=$null
        try{
            if($e.kind -eq 'file'){$payloadLock=[IO.FileStream]::new($e.path,[IO.FileMode]::Open,[IO.FileAccess]::Read,([IO.FileShare]::Read -bor [IO.FileShare]::Delete));if((Get-SCHash $e.path) -ne $e.sha256){throw 'Payload changed immediately before delete'}}
            Write-SCJournal $Context delete_intent $key @{path=$e.path}
            if($e.kind -eq 'directory'){[IO.Directory]::Delete($e.path,$false)}else{[IO.File]::Delete($e.path)}
        }finally{if($payloadLock){$payloadLock.Dispose()}}
        Invoke-SCCheckpoint 'after_delete'
        if(Test-Path -LiteralPath $e.path){throw 'Delete failed'};Write-SCJournal $Context delete_done $key @{path=$e.path}
    }
    if(Test-Path -LiteralPath $Pair.i){Assert-SCPair $Item $Pair;Write-SCJournal $Context metadata_delete_intent $Item.id $Pair;[IO.File]::Delete($Pair.i);Invoke-SCCheckpoint 'after_metadata_delete'}
    if((Test-Path -LiteralPath $Pair.r) -or (Test-Path -LiteralPath $Pair.i)){throw 'Purge incomplete'}
    Write-SCJournal $Context completed $Item.id @{action=$Item.action;pair=$Pair}
}

function Invoke-StorageCleanup {
    [CmdletBinding()]param([ValidateSet('Check','Execute','Resume','Verify')][string]$Mode='Check',[Parameter(Mandatory)][string]$ManifestPath,[string]$StateDirectory)
    $ErrorActionPreference='Stop'
    if(!$IsWindows){throw 'Windows is required'};Initialize-SCNative
    $ManifestPath=Get-SCPath $ManifestPath;Assert-SCPlain $ManifestPath
    $manifestHandle=[IO.FileStream]::new($ManifestPath,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::Read)
    $lock=$null
    try{
        $mem=[IO.MemoryStream]::new();$manifestHandle.CopyTo($mem);$raw=$mem.ToArray();$mem.Dispose()
        $digest=[Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($raw));$manifest=[Text.UTF8Encoding]::new($false,$true).GetString($raw).TrimStart([char]0xFEFF)|ConvertFrom-Json -AsHashtable
        if($Mode -ne 'Check' -and !$StateDirectory){throw 'Explicit, confirmed non-synchronized StateDirectory is required'}
        if($StateDirectory){$StateDirectory=Get-SCPath $StateDirectory}
        $roots=@(Assert-SCManifest $manifest $StateDirectory $ManifestPath)
        $ctx=@{records=[Collections.Generic.List[object]]::new();journal=$(if($StateDirectory){Join-Path $StateDirectory 'journal.jsonl'}else{$null})}
        $mutating=$Mode -in @('Execute','Resume')
        if($Mode -eq 'Execute'){
            if(Test-Path -LiteralPath $StateDirectory){if(@(Get-ChildItem -LiteralPath $StateDirectory -Force).Count){throw 'Execute requires a new or empty state directory; use Resume'}}else{[void][IO.Directory]::CreateDirectory($StateDirectory)}
        }
        if($mutating){$lock=[IO.FileStream]::new((Join-Path $StateDirectory 'batch.lock'),[IO.FileMode]::OpenOrCreate,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None)}
        if($Mode -in @('Resume','Verify')){
            $b=[IO.File]::ReadAllBytes($ctx.journal);if(!$b.Length -or $b[-1] -ne 10){throw 'Incomplete journal tail preserved; manual reconciliation required'}
            foreach($line in [Text.UTF8Encoding]::new($false,$true).GetString($b).Split("`n",[StringSplitOptions]::RemoveEmptyEntries)){$ctx.records.Add(($line|ConvertFrom-Json -AsHashtable))}
            $start=Get-SCRecord $ctx batch ''
            if(!$start -or $start.data.manifestSha256 -ne $digest -or $start.data.batchId -ne $manifest.batchId){throw 'Manifest does not match immutable batch binding'}
        }
        $spaceRoots=@($roots)+@($manifest.items|Where-Object action -eq archive_then_purge|ForEach-Object {$_.archiveDestination})
        $before=Get-SCSpace $spaceRoots
        if($Mode -eq 'Execute'){Write-SCJournal $ctx batch '' @{manifestSha256=$digest;batchId=$manifest.batchId;freeSpace=$before}}
        $results=[Collections.Generic.List[object]]::new();$physical=@{};[long]$logical=0;[long]$estimate=0
        $allFiles=@{};foreach($i in $manifest.items){foreach($e in @(Get-SCExpected $i $i.source)|Where-Object kind -eq file){$allFiles[$e.path]=$i.action}}
        foreach($i in $manifest.items){$known=Get-SCRecord $ctx staged $i.id;if($known){foreach($e in @(Get-SCExpected $i $known.data.r)|Where-Object kind -eq file){$allFiles[$e.path]=$i.action}}}
        foreach($i in $manifest.items){
            Write-Verbose "$Mode item $($i.id)"
            $held=$null;$sourceLocks=[Collections.Generic.List[IDisposable]]::new()
            try{
                $done=Get-SCRecord $ctx completed $i.id;$staged=Get-SCRecord $ctx staged $i.id;$intent=Get-SCRecord $ctx recycle_intent $i.id
                if($done){
                    if(Test-Path -LiteralPath $i.source){throw 'Previously completed source reappeared; preserved'}
                    if($i.action -eq 'recycle'){Assert-SCPair $i $done.data.pair;Assert-SCContent $i $done.data.pair.r -IgnoreRootTime}
                    elseif((Test-Path -LiteralPath $done.data.pair.i) -or (Test-Path -LiteralPath $done.data.pair.r)){throw 'Completed purge payload reappeared'}
                    if($i.action -eq 'archive_then_purge'){Assert-SCContent $i $i.archiveDestination -IgnoreTimes}
                    $held=Open-SCRetained $i;$results.Add(@{id=$i.id;status='completed';bytes=$i.bytes;action=$i.action});continue
                }
                if($Mode -eq 'Verify'){throw 'Item has not completed; use Resume after inspection'}
                if(!$staged -and !(Test-Path -LiteralPath $i.source)){
                    if(!$intent){throw 'Source absent without a recycle intent'};$pair=Find-SCPair $i $intent.data;Assert-SCPair $i $pair;Assert-SCContent $i $pair.r -IgnoreRootTime
                    Write-SCJournal $ctx staged $i.id $pair;$staged=Get-SCRecord $ctx staged $i.id
                }
                if(!$staged){
                    Assert-SCContent $i $i.source;$held=Open-SCRetained $i
                    if($Mode -eq 'Check' -and $i.action -eq 'archive_then_purge' -and (Test-Path -LiteralPath $i.archiveDestination)){throw 'Archive destination already exists'}
                    foreach($e in @(Get-SCExpected $i $i.source)|Where-Object kind -eq file){
                        $identity=[StorageCleanupNative]::Identity($e.path);$links=@([StorageCleanupNative]::Links($e.path));$covered=$true;$allPurge=$true;foreach($l in $links){if(!$allFiles.ContainsKey($l)){$covered=$false};if($allFiles[$l] -eq 'recycle'){$allPurge=$false}}
                        if(!$covered){throw 'Hard-link alias is outside the explicit batch members'}
                        if(!$physical.ContainsKey($identity)){$physical[$identity]=$true;if($covered -and $allPurge){$estimate+=$e.bytes}}
                        $probe=[IO.FileStream]::new($e.path,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::None);$probe.Dispose()
                    }
                    $logical+=[long]$i.bytes
                    if($Mode -eq 'Check'){$results.Add(@{id=$i.id;status='ready';bytes=$i.bytes;action=$i.action});continue}
                    if($i.action -eq 'archive_then_purge'){Invoke-SCArchive $ctx $i;if($held){foreach($h in $held){$h.Dispose()}};$copy=$i.Clone();$copy.retainedCopy=$i.archiveDestination;$held=Open-SCRetained $copy}
                    foreach($e in @(Get-SCExpected $i $i.source)|Where-Object kind -eq file){$sourceLocks.Add([IO.FileStream]::new($e.path,[IO.FileMode]::Open,[IO.FileAccess]::Read,([IO.FileShare]::Read -bor [IO.FileShare]::Delete)))}
                    Assert-SCContent $i $i.source
                    $bin=Get-SCBin $i.source;$baseline=Get-SCBaseline $bin
                    $recycleData=@{bin=$bin;baseline=$baseline;utc=[datetime]::UtcNow.ToString('o')}
                    Write-SCJournal $ctx recycle_intent $i.id $recycleData
                    foreach($h in $sourceLocks){$h.Dispose()};$sourceLocks.Clear()
                    Invoke-SCRecycle $i;Invoke-SCCheckpoint 'after_recycle'
                    if(Test-Path -LiteralPath $i.source){throw 'Source remains after recycle'}
                    $pair=Find-SCPair $i $recycleData;Assert-SCPair $i $pair;Assert-SCContent $i $pair.r -IgnoreRootTime
                    Write-SCJournal $ctx staged $i.id $pair;$staged=Get-SCRecord $ctx staged $i.id
                }
                if(Test-Path -LiteralPath $i.source){throw 'Source reappeared; stop item'}
                foreach($e in @(Get-SCExpected $i $staged.data.r)|Where-Object kind -eq file){$allFiles[$e.path]=$i.action}
                if(!$held){$copy=$i.Clone();if($i.action -eq 'archive_then_purge'){$copy.retainedCopy=$i.archiveDestination};$held=Open-SCRetained $copy}
                if($i.action -eq 'recycle'){Assert-SCPair $i $staged.data;Assert-SCContent $i $staged.data.r -IgnoreRootTime;Write-SCJournal $ctx completed $i.id @{action=$i.action;pair=$staged.data}}
                else{Invoke-SCPurge $ctx $i $staged.data}
                $results.Add(@{id=$i.id;status='completed';bytes=$i.bytes;action=$i.action})
            }catch{
                if($_.Exception.Message -like '*JOURNAL_FAILURE*'){throw}
                $results.Add(@{id=$i.id;status='needs-attention';reason=$_.Exception.Message;action=$i.action})
            }finally{if($held){foreach($h in $held){$h.Dispose()}};foreach($h in $sourceLocks){$h.Dispose()}}
        }
        $baselineChecks=[Collections.Generic.List[object]]::new()
        foreach($r in @($ctx.records|Where-Object type -eq recycle_intent)){
            $now=Get-SCBaseline $r.data.bin
            foreach($name in $r.data.baseline.Keys){if(!$now.ContainsKey($name) -or $now[$name].ticks -ne $r.data.baseline[$name].ticks -or $now[$name].length -ne $r.data.baseline[$name].length){
                # Earlier batch payloads may intentionally have been removed; unrelated names must survive.
                $ours=@($ctx.records|Where-Object {$_.type -eq 'staged' -and ([IO.Path]::GetFileName($_.data.i) -eq $name -or [IO.Path]::GetFileName($_.data.r) -eq $name)})
                if(!$ours.Count){$baselineChecks.Add(@{bin=$r.data.bin;name=$name;status='changed-or-missing'})}
            }}
        }
        $batchRecord=Get-SCRecord $ctx batch ''; $batchBefore=if($batchRecord){$batchRecord.data.freeSpace}else{$before}; $after=Get-SCSpace $spaceRoots; $delta=@{}; foreach($drive in $after.Keys){$delta[$drive]=$after[$drive]-$batchBefore[$drive]}
        $partial=@($results|Where-Object status -eq 'needs-attention').Count -gt 0 -or $baselineChecks.Count -gt 0
        @{schemaVersion=1;batchId=$manifest.batchId;mode=$Mode;manifestSha256=$digest;outcome=$(if($partial){'partial'}elseif($Mode -eq 'Check'){'checked'}elseif($Mode -eq 'Verify'){'verified'}else{'complete'});exitCode=$(if($partial){2}else{0});items=$results.ToArray();logicalBytes=$logical;estimatedReclaimBytes=$estimate;freeSpaceBefore=$before;freeSpaceAfter=$after;batchFreeSpaceBefore=$batchBefore;freeSpaceDelta=$delta;unrelatedRecycleChanges=$baselineChecks.ToArray()}
    }finally{if($lock){$lock.Dispose()};$manifestHandle.Dispose()}
}
Export-ModuleMember -Function Invoke-StorageCleanup
