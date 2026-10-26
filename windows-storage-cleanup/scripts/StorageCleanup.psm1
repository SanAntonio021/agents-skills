#requires -Version 7.0
Set-StrictMode -Version Latest
$script:SCProgressMemberThreshold = 1000
$script:SCProgressIntervalSeconds = 5

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
function Add-SCRecordIndex($Context,$Record) {
    if(-not $Context.ContainsKey('recordIndex')){$Context.recordIndex=@{}}
    $byId=$Context.recordIndex[$Record.type]
    if(!$byId){$byId=@{};$Context.recordIndex[$Record.type]=$byId}
    $byId[$Record.id]=$Record
}
function Get-SCItemMemberCount($Item) {
    if($Item.kind -eq 'file'){return 1}
    @($Item.members).Count
}
function Get-SCHardLinkPaths([string]$Path) {
    @([StorageCleanupNative]::Links($Path) | ForEach-Object { Get-SCPath $_ })
}
function Get-SCHardLinkedPathSet($AllFiles) {
    $hard=@{}
    foreach($path in @($AllFiles.Keys)){
        if(-not (Test-Path -LiteralPath $path)){continue}
        $links=@(Get-SCHardLinkPaths $path)
        if($links.Count -gt 1){foreach($alias in $links){$hard[$alias]=$true}}
    }
    $hard
}
function Assert-SCHardLinkScope($AllFiles) {
    $hard=Get-SCHardLinkedPathSet $AllFiles
    foreach($path in @($hard.Keys)){if(-not $AllFiles.ContainsKey($path)){throw "Hard-link alias is outside the explicit batch members: $path"}}
}
function Get-SCItemFileIdentities($Item,$Context=$null) {
    $identities=[Collections.Generic.List[string]]::new();$seen=@{}
    $basePath=$Item.source
    if($Context){$staged=Get-SCRecord $Context 'staged' $Item.id;if($staged){$basePath=$staged.data.r}}
    foreach($entry in @(Get-SCExpected $Item $basePath | Where-Object kind -eq file)){
        $identity=[StorageCleanupNative]::Identity($entry.path)
        if($seen.ContainsKey($identity)){continue}
        $seen[$identity]=$true;$identities.Add($identity)
    }
    $identities.ToArray()
}
function Assert-SCAliasOriginalScope($Context,$CurrentFiles) {
    $record=Get-SCRecord $Context 'alias_plan_map' ''
    $originals=@()
    if($record){$originals=@(Get-SCValue $record.data 'originalFiles' @())}
    else{
        $batch=Get-SCRecord $Context 'batch' ''
        if($batch -and $batch.data.Contains('aliasPlan')){$originals=@(Get-SCValue $batch.data.aliasPlan 'originalFiles' @())}
    }
    if(-not $originals.Count){return}
    $originalSet=@{};foreach($entry in $originals){$originalSet[[string]$entry.path]=$true}
    $currentHard=Get-SCHardLinkedPathSet $CurrentFiles
    foreach($path in @($currentHard.Keys)){if(-not $originalSet.ContainsKey($path)){throw "Hard-link member was added outside the frozen batch: $path"}}
}
function Get-SCAliasPlanMap($Manifest,$AllFiles,$Context=$null) {
    Assert-SCHardLinkScope $AllFiles
    if($Context){Assert-SCAliasOriginalScope $Context $AllFiles}
    $actions=@{};$order=@{};foreach($i in $Manifest.items){$actions[$i.id]=$i.action;$order[$i.id]=$order.Count}
    $firstOwner=@{};$plans=[Collections.Generic.List[object]]::new()
    foreach($i in $Manifest.items){
        if($i.action -notin @('recycle','recycle_then_purge') -or (Get-SCValue $i retainedCopy) -or (Get-SCValue $i archiveDestination)){continue}
        try{$identities=@(Get-SCItemFileIdentities $i $Context)}catch{continue}
        if(-not $identities.Count){continue}
        $covered=[Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
        $fullyCovered=$true
        foreach($identity in $identities){
            if(-not $firstOwner.ContainsKey($identity)){$firstOwner[$identity]=$i.id;$fullyCovered=$false}
            else{[void]$covered.Add([string]$firstOwner[$identity])}
        }
        if(-not $fullyCovered -or -not $covered.Count){continue}
        $coveredBy=@($covered | Sort-Object { $order[[string]$_] })
        $sameAction=$true
        foreach($coverId in $coveredBy){if($actions[[string]$coverId] -ne $i.action){$sameAction=$false;break}}
        if($sameAction){$plans.Add([ordered]@{id=$i.id;action=$i.action;coveredBy=$coveredBy})}
    }
    $plans.ToArray()
}
function Get-SCAliasPlanEntry($Context,[string]$ItemId) {
    $record=Get-SCRecord $Context 'alias_plan_map' ''
    if($record){
        foreach($plan in @($record.data.plans)){if([string]$plan.id -eq $ItemId){return $plan}}
        return $null
    }
    $batch=Get-SCRecord $Context 'batch' ''
    if($batch -and $batch.data.Contains('aliasPlan')){
        foreach($plan in @($batch.data.aliasPlan.plans)){if([string]$plan.id -eq $ItemId){return $plan}}
    }
    return $null
}
function Test-SCAliasCoverage($Context,$Item,$Plan) {
    if(-not $Plan -or [string]$Plan.action -ne [string]$Item.action){return $false}
    $coveredBy=@($Plan.coveredBy)
    if(-not $coveredBy.Count){return $false}
    if((Get-SCRecord $Context 'recycle_intent' $Item.id) -or (Get-SCRecord $Context 'staged' $Item.id) -or (Get-SCRecord $Context 'purge_started' $Item.id)){return $false}
    foreach($coverId in $coveredBy){
        $cover=Get-SCRecord $Context 'completed' ([string]$coverId)
        if(-not $cover -or [string](Get-SCValue $cover.data 'completionMode' 'direct') -eq 'alias' -or [string]$cover.data.action -ne [string]$Item.action){return $false}
    }
    return $true
}
function Initialize-SCProgress($Manifest,[string]$Mode,$Context) {
    if($Mode -notin @('Execute','Resume')){return $null}
    $totalMembers=0;$totalBytes=[long]0;$memberMap=@{};$itemMap=@{}
    foreach($i in $Manifest.items){
        $itemMap[$i.id]=$true
        $totalMembers+=(Get-SCItemMemberCount $i);$totalBytes+=[long]$i.bytes
        if($i.kind -eq 'file'){$memberMap[$i.source]=@{bytes=[long]$i.bytes;itemId=$i.id}}
        else{
            foreach($m in @($i.members|Where-Object kind -eq 'file')){
                $path=Get-SCPath ([IO.Path]::Combine($i.source,$m.relativePath))
                $memberMap[$path]=@{bytes=[long]$m.bytes;itemId=$i.id}
            }
        }
    }
    if($totalMembers -le $script:SCProgressMemberThreshold){return @{enabled=$false}}
    $payloadRoots=@{}
    foreach($i in $Manifest.items){
        $staged=Get-SCRecord $Context 'staged' $i.id
        if($staged){$payloadRoots[$i.id]=$staged.data.r}
    }
    $deleted=@{};foreach($record in $Context.records){if($record.type -eq 'delete_done'){$deleted[$record.id]=$record}}
    $completed=@{};foreach($i in $Manifest.items){if(-not $itemMap.ContainsKey($i.id)){continue};if(Get-SCRecord $Context 'completed' $i.id){$completed[$i.id]=$true}}
    $partialMembers=@{};$partialBytes=@{}
    foreach($key in $deleted.Keys){
        $separator=$key.IndexOf('|');if($separator -lt 1){continue}
        $itemId=$key.Substring(0,$separator);if($completed.ContainsKey($itemId)){continue}
        if(-not $partialMembers.ContainsKey($itemId)){$partialMembers[$itemId]=0L;$partialBytes[$itemId]=[long]0}
        $path=$key.Substring($separator+1)
        if($payloadRoots.ContainsKey($itemId) -and $path -eq $payloadRoots[$itemId]){continue}
        $partialMembers[$itemId]++
        if($memberMap.ContainsKey($path)){$partialBytes[$itemId]+=[long]$memberMap[$path].bytes}
    }
    $membersDone=[long]0;$bytesDone=[long]0
    foreach($i in $Manifest.items){
        if(-not $itemMap.ContainsKey($i.id)){continue}
        if($completed.ContainsKey($i.id)){$membersDone+=(Get-SCItemMemberCount $i);$bytesDone+=[long]$i.bytes}
        elseif($partialMembers.ContainsKey($i.id)){$membersDone+=$partialMembers[$i.id];$bytesDone+=$partialBytes[$i.id]}
    }
    @{
        enabled=$true;mode=$Mode;itemsTotal=$itemMap.Count;membersTotal=[long]$totalMembers;bytesTotal=$totalBytes
        itemsCompleted=$completed.Count;membersDone=$membersDone;bytesDone=$bytesDone
        itemIndex=0;itemId='';itemMembersTotal=0L;itemBytesTotal=0L;itemMembersDone=0L;itemBytesDone=0L
        partialMembers=$partialMembers;partialBytes=$partialBytes;lastEmitUtc=[datetime]::MinValue
    }
}
function Set-SCCurrentProgress($Progress,$Item,[int]$Index) {
    if(-not $Progress -or -not $Progress.enabled){return}
    $Progress.itemIndex=$Index;$Progress.itemId=$Item.id
    $Progress.itemMembersTotal=[long](Get-SCItemMemberCount $Item);$Progress.itemBytesTotal=[long]$Item.bytes
    $Progress.itemMembersDone=if($Progress.partialMembers.ContainsKey($Item.id)){[long]$Progress.partialMembers[$Item.id]}else{[long]0}
    $Progress.itemBytesDone=if($Progress.partialBytes.ContainsKey($Item.id)){[long]$Progress.partialBytes[$Item.id]}else{[long]0}
}
function Write-SCProgress($Progress,[string]$Phase,[switch]$Force) {
    if(-not $Progress -or -not $Progress.enabled){return}
    $now=[datetime]::UtcNow
    if(-not $Force -and ($now-$Progress.lastEmitUtc).TotalSeconds -lt $script:SCProgressIntervalSeconds){return}
    $record=[ordered]@{
        event='progress';mode=$Progress.mode;phase=$Phase
        itemsCompleted=$Progress.itemsCompleted;itemsTotal=$Progress.itemsTotal;itemIndex=$Progress.itemIndex;itemId=$Progress.itemId
        itemMembersDone=$Progress.itemMembersDone;itemMembersTotal=$Progress.itemMembersTotal
        membersDone=$Progress.membersDone;membersTotal=$Progress.membersTotal
        bytesDone=$Progress.bytesDone;bytesTotal=$Progress.bytesTotal
    }
    [Console]::Error.WriteLine(($record|ConvertTo-Json -Compress))
    $Progress.lastEmitUtc=$now
}
function Record-SCProgressDelete($Progress,$Item,$Entry) {
    if(-not $Progress -or -not $Progress.enabled){return}
    $Progress.itemMembersDone++
    $Progress.membersDone++
    if($Entry.kind -eq 'file'){$Progress.itemBytesDone+=[long]$Entry.bytes;$Progress.bytesDone+=[long]$Entry.bytes}
    Write-SCProgress $Progress 'purging'
}
function Complete-SCProgressItem($Progress,$Item) {
    if(-not $Progress -or -not $Progress.enabled){return}
    $missingMembers=[long]$Progress.itemMembersTotal-$Progress.itemMembersDone
    if($missingMembers -gt 0){$Progress.itemMembersDone+=$missingMembers;$Progress.membersDone+=$missingMembers}
    $missingBytes=[long]$Progress.itemBytesTotal-$Progress.itemBytesDone
    if($missingBytes -gt 0){$Progress.itemBytesDone+=$missingBytes;$Progress.bytesDone+=$missingBytes}
    $Progress.itemsCompleted++
    Write-SCProgress $Progress 'completed'
}
function Test-SCStatusPath([string]$Path) {
    try{[void][IO.File]::GetAttributes($Path);return $true}
    catch{
        $exception=$_.Exception
        while($exception.InnerException){$exception=$exception.InnerException}
        if($exception -is [IO.FileNotFoundException] -or $exception -is [IO.DirectoryNotFoundException]){return $false}
        return $null
    }
}
function Get-SCStatusResult($Manifest,$Context,$Digest) {
    $itemIds=@{};foreach($i in $Manifest.items){$itemIds[$i.id]=$true}
    $lastEvent=@{};$deleteDone=@{}
    foreach($record in $Context.records){
        if($record.type -eq 'delete_done'){$deleteDone[$record.id]=$record}
        $rootId=[string]$record.id;$separator=$rootId.IndexOf('|');if($separator -ge 1){$rootId=$rootId.Substring(0,$separator)}
        if($itemIds.ContainsKey($rootId)){
            if(-not $lastEvent.ContainsKey($rootId) -or [datetime]$record.utc -gt [datetime]$lastEvent[$rootId]){$lastEvent[$rootId]=$record.utc}
        }
    }
    $payloadRoots=@{}
    foreach($i in $Manifest.items){
        $staged=Get-SCRecord $Context 'staged' $i.id
        if($staged){$payloadRoots[$i.id]=$staged.data.r}
    }
    $memberMap=@{}
    foreach($i in $Manifest.items){
        if($i.kind -eq 'file'){$memberMap[$i.source]=@{bytes=[long]$i.bytes;itemId=$i.id}}
        else{foreach($m in @($i.members|Where-Object kind -eq 'file')){$path=Get-SCPath ([IO.Path]::Combine($i.source,$m.relativePath));$memberMap[$path]=@{bytes=[long]$m.bytes;itemId=$i.id}}}
    }
    $doneMembers=@{};$doneBytes=@{}
    foreach($key in $deleteDone.Keys){
        $separator=$key.IndexOf('|');if($separator -lt 1){continue}
        $itemId=$key.Substring(0,$separator)
        if(-not $doneMembers.ContainsKey($itemId)){$doneMembers[$itemId]=0L;$doneBytes[$itemId]=[long]0}
        $path=$key.Substring($separator+1)
        if($payloadRoots.ContainsKey($itemId) -and $path -eq $payloadRoots[$itemId]){continue}
        $doneMembers[$itemId]++
        if($memberMap.ContainsKey($path)){$doneBytes[$itemId]+=[long]$memberMap[$path].bytes}
    }
    $items=[Collections.Generic.List[object]]::new()
    foreach($i in $Manifest.items){
        $complete=Get-SCRecord $Context 'completed' $i.id
        $staged=Get-SCRecord $Context 'staged' $i.id
        $purge=Get-SCRecord $Context 'purge_started' $i.id
        $intent=Get-SCRecord $Context 'recycle_intent' $i.id
        $sourceExists=Test-SCStatusPath $i.source
        $metadataExists=$null;$payloadExists=$null
        if($staged){
            $metadataExists=Test-SCStatusPath $staged.data.i;$payloadPathExists=Test-SCStatusPath $staged.data.r
            $payloadExists=$payloadPathExists
        }
        $completionMode=$null;$coveredBy=$null
        if($complete){
            $completionMode=if(Get-SCValue $complete.data 'completionMode'){[string]$complete.data.completionMode}else{'direct'}
            $coveredBy=@(Get-SCValue $complete.data 'coveredBy' @())
        }else{
        }
        $status=if($complete -and $completionMode -eq 'alias'){
            if($sourceExists -ne $false){'attention'}
            elseif(-not @($coveredBy).Count){'attention'}
            else{
                $coverValid=$true
                foreach($coverId in $coveredBy){
                    $cover=Get-SCRecord $Context 'completed' ([string]$coverId)
                    if(-not $cover -or [string](Get-SCValue $cover.data 'completionMode' 'direct') -eq 'alias' -or [string]$cover.data.action -ne [string]$i.action){$coverValid=$false;break}
                }
                if($coverValid){'completed'}else{'attention'}
            }
        }elseif(!$complete){
            $planned=Get-SCAliasPlanEntry $Context $i.id
            $covered=if($planned -and $sourceExists -eq $false -and (Test-SCAliasCoverage $Context $i $planned)){$true}else{$false}
            if($covered){$completionMode='alias';$coveredBy=@($planned.coveredBy);'completed'}
            elseif($purge){if($metadataExists -eq $false -and $payloadExists -eq $false){'attention'}else{'purging'}}
            elseif($staged){if($metadataExists -eq $false -or $payloadExists -eq $false){'attention'}else{'staged'}}
            elseif($intent){if($sourceExists -eq $false){'recycling'}else{'attention'}}
            elseif($sourceExists){'not_started'}else{'attention'}
        }else{
            if($sourceExists -ne $false){'attention'}
            elseif($i.action -eq 'recycle'){
                if($metadataExists -eq $true -and $payloadExists -eq $true){'completed'}else{'attention'}
            }elseif($metadataExists -eq $false -and $payloadExists -eq $false){'completed'}
            else{'attention'}
        }
        $membersDone=if($status -eq 'completed'){(Get-SCItemMemberCount $i)}elseif($doneMembers.ContainsKey($i.id)){$doneMembers[$i.id]}else{0L}
        $bytesDone=if($status -eq 'completed'){[long]$i.bytes}elseif($doneBytes.ContainsKey($i.id)){$doneBytes[$i.id]}else{0L}
        $items.Add([ordered]@{
            id=$i.id;status=$status;sourceExists=$sourceExists;recycleMetadataExists=$metadataExists;recyclePayloadExists=$payloadExists
            completionMode=$completionMode;coveredBy=$coveredBy
            membersDone=$membersDone;membersTotal=(Get-SCItemMemberCount $i);bytesDone=$bytesDone;bytesTotal=[long]$i.bytes
            lastEventUtc=$(if($lastEvent.ContainsKey($i.id)){$lastEvent[$i.id]}else{$null})
        })
    }
    @{
        schemaVersion=1;batchId=$Manifest.batchId;mode='Status';manifestSha256=$Digest
        outcome='status';exitCode=$(if(@($items|Where-Object status -eq 'attention').Count){2}else{0})
        items=$items.ToArray()
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
        try{$s=[IO.FileStream]::new($Context.journal,[IO.FileMode]::Append,[IO.FileAccess]::Write,[IO.FileShare]::Read);try{$writeStarted=$true;$s.Write($bytes);$s.Flush($true)}finally{$s.Dispose()};$Context.records.Add($record);Add-SCRecordIndex $Context $record;break}
        catch{if($writeStarted -or $attempt -eq 3){throw [InvalidOperationException]::new('JOURNAL_FAILURE: '+$_.Exception.Message,$_.Exception)};Start-Sleep -Milliseconds (100*($attempt+1))}
    }
    Invoke-SCCheckpoint $Type $record
}
function Get-SCRecord($Context,[string]$Type,[string]$Id){
    if(-not $Context.ContainsKey('recordIndex')){
        $Context.recordIndex=@{}
        foreach($record in $Context.records){Add-SCRecordIndex $Context $record}
    }
    $byId=$Context.recordIndex[$Type]
    if($byId -and $byId.ContainsKey($Id)){return $byId[$Id]}
    return $null
}
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
function Assert-SCObjectFields($Object,[string[]]$Allowed,[string]$Context) {
    foreach($key in $Object.Keys){if($Allowed -notcontains $key){throw "Unknown $Context field: $key"}}
}

function Test-SCFormalPath([string]$Path,[string[]]$PreferredRoots,$Depth) {
    foreach($root in @($PreferredRoots)){if(Test-SCWithin $Path $root){return $true}}
    $parts=@($Path.Substring(3).Split([char[]]@('\','/'),[StringSplitOptions]::RemoveEmptyEntries))
    if($Depth -le 2 -and $parts.Count -le 4){return $true}
    if($Path -match '(?i)\\(Documents|Desktop|Papers?|Projects?|Research|Archive|正式|论文|项目|归档)(\\|$)'){return $true}
    if($Path -match '(?i)(\|/)(backups?|copy|copies|temp|tmp|cache|downloads?|备份|副本|缓存|临时|下载)(\|/)'){return $false}
    return $Depth -le 3
}
function Get-SCFormalNameScore([string]$Path) {
    $name=[IO.Path]::GetFileName($Path);$score=0
    if($name -match '(?i)(^|[\s._-])(copy|副本|backup|bak)([\s._-]|$)'){$score-=2}
    if($name -match '(?i)(~1|\.tmp$|\.temp$)'){$score-=2}
    if($name -match '^[\p{L}\p{N}][\p{L}\p{N} ._()\[\]+\-]*\.[A-Za-z0-9]{1,10}$'){$score+=1}
    $score
}
function Sort-SCDuplicateObjectPaths([string[]]$Paths,[string[]]$PreferredRoots) {
    $ranked=@()
    foreach($p in $Paths){
        $depth=@($p.Substring(3).Split([char[]]@('\','/'),[StringSplitOptions]::RemoveEmptyEntries)).Count
        $info=[IO.FileInfo]::new($p)
        try{$modified=$info.LastWriteTimeUtc.Ticks}catch{$modified=0}
        $ranked+=[pscustomobject]@{path=$p;formal=(Test-SCFormalPath $p $PreferredRoots $depth);modified=$modified;depth=$depth;nameScore=(Get-SCFormalNameScore $p)}
    }
    @($ranked|Sort-Object @{Expression='formal';Descending=$true},@{Expression='modified';Descending=$true},@{Expression='depth'},@{Expression='nameScore';Descending=$true},@{Expression='path'})
}
function New-StorageCleanupDuplicateScan {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string[]]$Roots,
        [string[]]$PreferredRoots=@(),
        [string]$OutputPath,
        [long]$MinBytes=1
    )
    Initialize-SCNative
    if($Roots.Count -lt 1){throw 'At least one explicit scan root is required'}
    $normalized=[Collections.Generic.List[string]]::new();$seenRoots=@{}
    foreach($root in $Roots){
        $p=Get-SCPath $root
        if(-not (Test-Path -LiteralPath $p -PathType Container)){throw "Scan root is not an existing directory: $p"}
        Assert-SCPlain $p
        if($p.Length -le 3){throw "Drive root cannot be scanned: $p"}
        if($seenRoots.ContainsKey($p)){continue};$seenRoots[$p]=$true;$normalized.Add($p)
    }
    for($a=0;$a -lt $normalized.Count;$a++){for($b=$a+1;$b -lt $normalized.Count;$b++){if((Test-SCWithin $normalized[$a] $normalized[$b]) -or (Test-SCWithin $normalized[$b] $normalized[$a])){throw "Scan roots must not overlap: $($normalized[$a]), $($normalized[$b])"}}}
    $preferred=[Collections.Generic.List[string]]::new();foreach($p in @($PreferredRoots)){if([string]::IsNullOrWhiteSpace($p)){continue};$preferred.Add((Get-SCPath $p))}
    if($OutputPath){$OutputPath=Get-SCPath $OutputPath;Assert-SCPlain $OutputPath;foreach($root in $normalized){if((Test-SCWithin $OutputPath $root) -or (Test-SCWithin $root $OutputPath)){throw 'Duplicate scan report must be outside scanned roots'}};if(Test-Path -LiteralPath $OutputPath){throw "Duplicate scan output already exists: $OutputPath"}}
    $files=[Collections.Generic.List[object]]::new();$skipped=[Collections.Generic.List[object]]::new();$directories=0
    foreach($root in $normalized){
        $stack=[Collections.Generic.Stack[string]]::new();$stack.Push($root)
        while($stack.Count){
            $current=$stack.Pop()
            try{$children=@(Get-ChildItem -LiteralPath $current -Force -ErrorAction Stop)}catch{$skipped.Add([ordered]@{path=$current;outcome='unreadable';reason=$_.Exception.Message});continue}
            foreach($entry in $children){
                try{
                    $attributes=[IO.File]::GetAttributes($entry.FullName)
                    if(($attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0){$skipped.Add([ordered]@{path=$entry.FullName;outcome='skipped';reason='reparse-point'});continue}
                    if($entry.PSIsContainer){$directories++;$stack.Push($entry.FullName);continue}
                    if([long]$entry.Length -lt $MinBytes){$skipped.Add([ordered]@{path=$entry.FullName;outcome='skipped';reason='below-minimum-size';bytes=[long]$entry.Length});continue}
                    $identity=[StorageCleanupNative]::Identity($entry.FullName)
                    $links=@(Get-SCHardLinkPaths $entry.FullName)
                    $files.Add([pscustomobject]@{path=$entry.FullName;bytes=[long]$entry.Length;identity=$identity;links=$links;modified=$entry.LastWriteTimeUtc.Ticks;deviationReason=$null})
                }catch{$skipped.Add([ordered]@{path=$entry.FullName;outcome='skipped';reason=$_.Exception.Message})}
            }
        }
    }
    $objects=@($files|Group-Object identity|ForEach-Object{
        $members=@($_.Group|Sort-Object path)
        [pscustomobject]@{identity=$_.Name;paths=@($members.path);bytes=[long]$members[0].bytes;modified=$members[0].modified;hash=$null;readable=$true}
    })
    $sizeGroups=@($objects|Group-Object bytes|Where-Object Count -gt 1)
    $hashCache=@{}
    foreach($group in $sizeGroups){
        foreach($object in $group.Group){
            try{
                $hash=$null
                foreach($path in $object.paths){if((Test-Path -LiteralPath $path) -and [StorageCleanupNative]::Identity($path) -eq $object.identity){$hash=Get-SCHash $path;break}}
                if(-not $hash){throw 'No readable path for physical object'}
                $object.hash=$hash
            }catch{$object.readable=$false;$skipped.Add([ordered]@{path=($object.paths -join '; ');outcome='unreadable';reason=$_.Exception.Message;bytes=$object.bytes})}
        }
    }
    $duplicateGroups=[Collections.Generic.List[object]]::new()
    foreach($group in $sizeGroups){
        foreach($h in @($group.Group|Where-Object {$_.readable -and $_.hash}|Group-Object hash)){
            $objectsInGroup=@($h.Group);if($objectsInGroup.Count -lt 2){continue}
            $first=$objectsInGroup[0]
            $candidatePaths=@($objectsInGroup|ForEach-Object {$_.paths}|ForEach-Object {$_})
            $pathRank=Sort-SCDuplicateObjectPaths $candidatePaths $preferred
            $objectRank=@($pathRank|ForEach-Object {$rank=$_;$obj=$objectsInGroup|Where-Object {$_.paths -contains $rank.path}|Select-Object -First 1;if(-not $obj){throw 'Duplicate object could not be resolved'};[pscustomobject]@{path=$rank.path;formal=$rank.formal;modified=$obj.modified;depth=$rank.depth;nameScore=$rank.nameScore;object=$obj}})
            $keepChoice=$objectRank[0];$keepPath=$keepChoice.path;$keepObject=$keepChoice.object
            $deleteItems=[Collections.Generic.List[object]]::new()
            foreach($object in $objectsInGroup){
                if($object.identity -eq $keepObject.identity){continue}
                foreach($path in $object.paths){$deleteItems.Add([ordered]@{path=$path;bytes=$object.bytes;physicalObject=$object.identity});}
            }
            $reasonParts=[Collections.Generic.List[string]]::new()
            $keepInfo=$objectRank[0]
            $hasFormal=@($objectRank|Where-Object formal).Count -gt 0
            if($keepInfo.formal){$reasonParts.Add('优先保留正式目录或正式文件名的副本')}
            $eligible=if($hasFormal){@($objectRank|Where-Object formal)}else{@($objectRank)}
            $newest=($eligible|Sort-Object modified -Descending|Select-Object -First 1).modified
            if($keepInfo.modified -eq $newest){$reasonParts.Add('正式程度相同时保留修改时间较新的副本')}
            if($reasonParts.Count -eq 0){$reasonParts.Add('正式程度和修改时间相同时保留路径较浅且文件名更完整的副本')}
            $deleteArray=@($deleteItems|ForEach-Object {[pscustomobject][ordered]@{path=$_.path;bytes=$_.bytes;physicalObject=$_.physicalObject}})
            $duplicateGroups.Add([pscustomobject][ordered]@{
                id=('duplicate-{0:D3}' -f ($duplicateGroups.Count+1));bytes=$first.bytes;sha256=$h.Name;copies=$objectsInGroup.Count
                keepPath=$keepPath;keepIdentity=$keepObject.identity;keepReason=($reasonParts -join '；')
                deleteItems=$deleteArray;reclaimBytes=([long]$first.bytes*[long]($objectsInGroup.Count-1));deleteCopies=$objectsInGroup.Count-1
            })
        }
    }
    $sorted=@($duplicateGroups|Sort-Object @{Expression={[long]$_.reclaimBytes};Descending=$true},@{Expression={[long]$_.bytes};Descending=$true},@{Expression={[string]$_.keepPath}})
    [long]$totalReclaim=0;foreach($d in $sorted){$totalReclaim+=[long]$d.reclaimBytes}
    $result=[pscustomobject][ordered]@{
        schemaVersion=1;mode='DuplicateScan';outcome='scanned';exitCode=0
        roots=$normalized.ToArray();fileCount=$files.Count;physicalObjectCount=$objects.Count;directoryCount=$directories
        duplicates=@($sorted);totalReclaimBytes=$totalReclaim;skipped=@($skipped|Sort-Object path)
        note='Read-only scan. Review the groups; only an explicitly approved selection may proceed to manifest Check, Execute, Resume, and Verify.'
    }
    if($OutputPath){
        $parent=[IO.Path]::GetDirectoryName($OutputPath);if(-not(Test-Path -LiteralPath $parent)){[void][IO.Directory]::CreateDirectory($parent)}
        $result | Add-Member -NotePropertyName outputPath -NotePropertyValue $OutputPath -Force
        $bytes=([Text.UTF8Encoding]::new($false)).GetBytes(($result|ConvertTo-Json -Depth 20))
        $result | Add-Member -NotePropertyName outputSha256 -NotePropertyValue ([Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($bytes))) -Force
        [IO.File]::WriteAllBytes($OutputPath,([Text.UTF8Encoding]::new($false)).GetBytes(($result|ConvertTo-Json -Depth 20)))
    }
    $result
}

function New-StorageCleanupDuplicateSelection {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$ScanPath,
        [Parameter(Mandatory)][string]$OutputPath,
        [string[]]$GroupIds=@()
    )
    $ScanPath=Get-SCPath $ScanPath;Assert-SCPlain $ScanPath
    $OutputPath=Get-SCPath $OutputPath
    if(Test-Path -LiteralPath $OutputPath){throw "Duplicate selection output already exists: $OutputPath"}
    $scan=Get-Content -LiteralPath $ScanPath -Raw -Encoding utf8|ConvertFrom-Json -AsHashtable
    if($scan.schemaVersion -ne 1 -or $scan.mode -ne 'DuplicateScan' -or -not @($scan.duplicates).Count){throw 'Invalid or empty duplicate scan'}
    $groups=@($scan.duplicates)
    if($GroupIds.Count){$groups=@($groups|Where-Object {$GroupIds -contains [string]$_.id});if($groups.Count -ne $GroupIds.Count){throw 'Requested duplicate group is missing'}}
    $items=[Collections.Generic.List[object]]::new();[long]$deleteBytes=0
    foreach($group in $groups){
        if([string]::IsNullOrWhiteSpace([string]$group.keepPath) -or -not (Test-Path -LiteralPath $group.keepPath)){throw "Retained duplicate is unavailable: $($group.keepPath)"}
        foreach($path in @($group.deleteItems|ForEach-Object {[string]$_.path})){
            if([string]::IsNullOrWhiteSpace($path) -or $path -eq [string]$group.keepPath){throw 'Invalid duplicate delete path'}
            if(-not (Test-Path -LiteralPath $path)){throw "Duplicate delete path is unavailable: $path"}
            $items.Add([ordered]@{source=$path;action='recycle_then_purge';retainedCopy=$group.keepPath})
        }
        $deleteBytes+=[long]$group.reclaimBytes
    }
    if(-not $items.Count){throw 'No duplicate delete candidates selected'}
    $roots=@($items|ForEach-Object {[string]$_.source}|ForEach-Object {[IO.Path]::GetDirectoryName($_)}|Sort-Object -Unique)
    $approved=[Collections.Generic.List[string]]::new();foreach($root in $roots){$covered=$false;foreach($existing in $approved){if(Test-SCWithin $root $existing){$covered=$true;break}};if(-not $covered){$approved.Add($root)}}
    $selection=[ordered]@{schemaVersion=1;batchId=('duplicates-'+[datetime]::UtcNow.ToString('yyyyMMddHHmmss')+'-'+[guid]::NewGuid().ToString('N').Substring(0,8));approvedRoots=$approved.ToArray();items=$items.ToArray()}
    $parent=[IO.Path]::GetDirectoryName($OutputPath);if(-not(Test-Path -LiteralPath $parent)){[void][IO.Directory]::CreateDirectory($parent)}
    $bytes=[Text.UTF8Encoding]::new($false).GetBytes(($selection|ConvertTo-Json -Depth 20))
    [IO.File]::WriteAllBytes($OutputPath,$bytes)
    [ordered]@{schemaVersion=1;mode='DuplicateSelection';outcome='created';exitCode=0;selectionPath=$OutputPath;groups=$groups.Count;items=$items.Count;deleteBytes=$deleteBytes}
}
function New-StorageCleanupManifest {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$SelectionPath,
        [Parameter(Mandatory)][string]$OutputPath
    )
    Initialize-SCNative
    $SelectionPath=Get-SCPath $SelectionPath;Assert-SCPlain $SelectionPath
    $OutputPath=Get-SCPath $OutputPath
    $OutputPath=Assert-SCTarget $OutputPath @([IO.Path]::GetPathRoot($OutputPath).TrimEnd('\'))
    if(Test-Path -LiteralPath $OutputPath){throw "Output manifest already exists: $OutputPath"}
    $raw=[IO.File]::ReadAllBytes($SelectionPath)
    $selection=[Text.UTF8Encoding]::new($false,$true).GetString($raw).TrimStart([char]0xFEFF)|ConvertFrom-Json -AsHashtable
    Assert-SCObjectFields $selection @('schemaVersion','batchId','approvedRoots','items') 'selection'
    if($selection.schemaVersion -ne 1 -or [string]$selection.batchId -notmatch '^[A-Za-z0-9_-]{1,80}$'){throw 'Invalid selection header'}
    $approvedRoots=@($selection.approvedRoots)
    if(-not $approvedRoots.Count){throw 'Selection approvedRoots must not be empty'}
    $approvedRoots=@($approvedRoots|ForEach-Object {Get-SCPath $_})
    $selectionItems=@($selection.items)
    if(-not $selectionItems.Count){throw 'Selection items must not be empty'}
    $items=[Collections.Generic.List[object]]::new()
    $fileCount=0;$directoryCount=0;$logicalBytes=[long]0
    for($index=0;$index -lt $selectionItems.Count;$index++){
        $selected=$selectionItems[$index]
        Assert-SCObjectFields $selected @('source','action','retainedCopy','archiveDestination') 'selection item'
        if(-not (Get-SCValue $selected 'source')){throw 'Selection item source is required'}
        $source=Assert-SCTarget (Get-SCValue $selected 'source') $approvedRoots
        $action=[string](Get-SCValue $selected 'action')
        if($action -notin @('recycle','recycle_then_purge','archive_then_purge')){throw "Invalid selection action: $action"}
        $archiveDestination=Get-SCValue $selected 'archiveDestination'
        $retainedCopy=Get-SCValue $selected 'retainedCopy'
        if($action -eq 'archive_then_purge'){
            if(-not $archiveDestination){throw 'archive_then_purge requires archiveDestination'}
            if($retainedCopy){throw 'archive_then_purge cannot also specify retainedCopy'}
        }elseif($archiveDestination){throw 'archiveDestination is only valid for archive_then_purge'}
        if($retainedCopy){
            $retainedCopy=Get-SCPath $retainedCopy
            Assert-SCPlain $retainedCopy
            if(-not (Test-Path -LiteralPath $retainedCopy)){throw "Retained copy does not exist: $retainedCopy"}
        }
        $sourceItem=Get-Item -LiteralPath $source -Force -ErrorAction Stop
        $item=[ordered]@{
            id=('item-{0:D3}' -f ($index+1));source=$source
            kind=$(if($sourceItem.PSIsContainer){'directory'}else{'file'})
            action=$action;bytes=[long]0;lastWriteTimeUtc=$sourceItem.LastWriteTimeUtc.ToString('o')
        }
        if($sourceItem.PSIsContainer){
            $directoryCount++
            $members=[Collections.Generic.List[object]]::new()
            foreach($entry in @(Get-SCEntries $source 'directory')){
                $relative=[IO.Path]::GetRelativePath($source,$entry.FullName)
                $member=[ordered]@{
                    relativePath=$relative;kind=$(if($entry.PSIsContainer){'directory'}else{'file'})
                    bytes=[long]$(if($entry.PSIsContainer){0}else{$entry.Length})
                    lastWriteTimeUtc=$entry.LastWriteTimeUtc.ToString('o')
                }
                if(-not $entry.PSIsContainer){
                    $member.sha256=Get-SCHash $entry.FullName;$fileCount++;$item.bytes+=[long]$entry.Length
                }
                $members.Add($member)
            }
            $item.members=$members.ToArray()
        }else{
            $fileCount++;$item.bytes=[long]$sourceItem.Length;$item.sha256=Get-SCHash $source
        }
        $logicalBytes+=[long]$item.bytes
        if($retainedCopy){$item.retainedCopy=$retainedCopy}
        if($archiveDestination){$item.archiveDestination=Get-SCPath $archiveDestination}
        $items.Add($item)
    }
    $manifest=[ordered]@{
        schemaVersion=1;batchId=[string]$selection.batchId;approvedRoots=$approvedRoots;items=$items.ToArray()
    }
    [void](Assert-SCManifest $manifest $null $OutputPath)
    $explicitFiles=@{}
    foreach($i in $manifest.items){foreach($e in @(Get-SCExpected $i $i.source)|Where-Object kind -eq file){$explicitFiles[$e.path]=$i.action}}
    Assert-SCHardLinkScope $explicitFiles
    $parent=[IO.Path]::GetDirectoryName($OutputPath)
    if(-not (Test-Path -LiteralPath $parent -PathType Container)){[void][IO.Directory]::CreateDirectory($parent)}
    $bytes=[Text.UTF8Encoding]::new($false).GetBytes(($manifest|ConvertTo-Json -Depth 20 -Compress))
    $digest=[Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($bytes))
    $temporary=Join-Path $parent ('.'+[IO.Path]::GetFileName($OutputPath)+'.tmp-'+[guid]::NewGuid().ToString('N'))
    try{
        $stream=[IO.FileStream]::new($temporary,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
        try{$stream.Write($bytes);$stream.Flush($true)}finally{$stream.Dispose()}
        if(Test-Path -LiteralPath $OutputPath){throw "Output manifest appeared during generation: $OutputPath"}
        [IO.File]::Move($temporary,$OutputPath)
    }finally{if(Test-Path -LiteralPath $temporary){[IO.File]::Delete($temporary)}}
    @{
        schemaVersion=1;batchId=$manifest.batchId;mode='Manifest';outcome='created';exitCode=0
        manifestPath=$OutputPath;manifestSha256=$digest;approvedRoots=$approvedRoots
        items=$manifest.items.Count;files=$fileCount;directories=$directoryCount;logicalBytes=$logicalBytes
    }
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
            if($e.kind -eq 'file'){
                $attributes=[IO.File]::GetAttributes($e.path)
                if(($attributes -band [IO.FileAttributes]::ReadOnly) -ne 0){
                    [IO.File]::SetAttributes($e.path,($attributes -band (-bnot [IO.FileAttributes]::ReadOnly)))
                }
            }
            if($e.kind -eq 'directory'){[IO.Directory]::Delete($e.path,$false)}else{[IO.File]::Delete($e.path)}
        }finally{if($payloadLock){$payloadLock.Dispose()}}
        Invoke-SCCheckpoint 'after_delete' $e
        if(Test-Path -LiteralPath $e.path){throw 'Delete failed'};Write-SCJournal $Context delete_done $key @{path=$e.path}
        if($e.path -ne $Pair.r -and $Context.ContainsKey('progress')){Record-SCProgressDelete $Context.progress $Item $e}
    }
    if(Test-Path -LiteralPath $Pair.i){Assert-SCPair $Item $Pair;Write-SCJournal $Context metadata_delete_intent $Item.id $Pair;[IO.File]::Delete($Pair.i);Invoke-SCCheckpoint 'after_metadata_delete'}
    if((Test-Path -LiteralPath $Pair.r) -or (Test-Path -LiteralPath $Pair.i)){throw 'Purge incomplete'}
    Write-SCJournal $Context completed $Item.id @{action=$Item.action;pair=$Pair}
}

function Invoke-StorageCleanup {
    [CmdletBinding()]param([ValidateSet('Check','Execute','Resume','Status','Verify')][string]$Mode='Check',[Parameter(Mandatory)][string]$ManifestPath,[string]$StateDirectory)
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
        $journalBytes=$null;$journalHash=$null
        if($Mode -in @('Resume','Status','Verify')){
            if(Test-Path -LiteralPath $ctx.journal){
                $b=[IO.File]::ReadAllBytes($ctx.journal);$journalBytes=[byte[]]$b.Clone();$journalHash=[Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($b));if(!$b.Length -or $b[-1] -ne 10){throw 'Incomplete journal tail preserved; manual reconciliation required'}
                foreach($line in [Text.UTF8Encoding]::new($false,$true).GetString($b).Split("`n",[StringSplitOptions]::RemoveEmptyEntries)){
                    $record=$line|ConvertFrom-Json -AsHashtable
                    $ctx.records.Add($record);Add-SCRecordIndex $ctx $record
                }
                $start=Get-SCRecord $ctx batch ''
                if(!$start -or $start.data.manifestSha256 -ne $digest -or $start.data.batchId -ne $manifest.batchId){throw 'Manifest does not match immutable batch binding'}
            }elseif($Mode -ne 'Status'){throw 'State journal is required'}
        }
        if($Mode -eq 'Status'){
            $result=Get-SCStatusResult $manifest $ctx $digest
            if($null -ne $journalBytes){[byte[]]$current=[IO.File]::ReadAllBytes($ctx.journal);if([Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($current)) -ne $journalHash){throw 'Status modified the journal'}}
            return $result
        }
        $spaceRoots=@($roots)+@($manifest.items|Where-Object action -eq archive_then_purge|ForEach-Object {$_.archiveDestination})
        $before=Get-SCSpace $spaceRoots
        $allFiles=@{};foreach($i in $manifest.items){foreach($e in @(Get-SCExpected $i $i.source)|Where-Object kind -eq file){$allFiles[$e.path]=$i.action}}
        $frozenFiles=@{};foreach($path in $allFiles.Keys){$frozenFiles[$path]=$allFiles[$path]}
        $ctx.frozenFiles=$frozenFiles
        if($Mode -eq 'Execute'){
            $plans=@(Get-SCAliasPlanMap $manifest $frozenFiles $ctx)
            $hardFiles=Get-SCHardLinkedPathSet $frozenFiles
            $originalFiles=@($hardFiles.Keys|Sort-Object|ForEach-Object {[ordered]@{path=$_;action=[string]$frozenFiles[$_]}})
            Write-SCJournal $ctx batch '' @{manifestSha256=$digest;batchId=$manifest.batchId;freeSpace=$before;aliasPlan=@{plans=$plans;originalFiles=$originalFiles}}
        }
        $results=[Collections.Generic.List[object]]::new();$physical=@{};[long]$logical=0;[long]$estimate=0
        $replayMode=$Mode -in @('Resume','Verify')
        foreach($i in $manifest.items){$known=Get-SCRecord $ctx staged $i.id;if($known){foreach($e in @(Get-SCExpected $i $known.data.r)|Where-Object kind -eq file){$allFiles[$e.path]=$i.action}}}
        if($Mode -in @('Resume','Verify')){Assert-SCAliasOriginalScope $ctx $frozenFiles}
        $ctx.progress=Initialize-SCProgress $manifest $Mode $ctx
        $itemIndex=0
        foreach($i in $manifest.items){
            $itemIndex++
            Write-Verbose "$Mode item $($i.id)"
            $held=$null;$sourceLocks=[Collections.Generic.List[IDisposable]]::new()
            try{
                $done=Get-SCRecord $ctx completed $i.id;$staged=Get-SCRecord $ctx staged $i.id;$intent=Get-SCRecord $ctx recycle_intent $i.id
                $aliasPlan=Get-SCAliasPlanEntry $ctx $i.id
                $sourceForAlias=Test-SCStatusPath $i.source
                if(-not $done -and $aliasPlan -and $sourceForAlias -eq $false -and (Test-SCAliasCoverage $ctx $i $aliasPlan)){
                    $data=@{action=$i.action;completionMode='alias';coveredBy=@($aliasPlan.coveredBy)}
                    Write-SCJournal $ctx completed $i.id $data
                    Complete-SCProgressItem $ctx.progress $i
                    $results.Add(@{id=$i.id;status='completed';completionMode='alias';coveredBy=@($aliasPlan.coveredBy);bytes=0;action=$i.action});continue
                }
                if($done){
                    if(Test-Path -LiteralPath $i.source){throw 'Previously completed source reappeared; preserved'}
                    if([string](Get-SCValue $done.data 'completionMode') -eq 'alias'){
                        $coveredBy=@(Get-SCValue $done.data 'coveredBy' @())
                        if(-not $coveredBy.Count){throw 'Alias completion has no covering item'}
                        $aliasCheck=[ordered]@{id=$i.id;action=$i.action;coveredBy=$coveredBy}
                        if(-not (Test-SCAliasCoverage $ctx $i $aliasCheck)){throw 'Alias completion is no longer covered'}
                        $results.Add(@{id=$i.id;status='completed';completionMode='alias';coveredBy=$coveredBy;bytes=0;action=$i.action});continue
                    }
                    if($i.action -eq 'recycle'){Assert-SCPair $i $done.data.pair;Assert-SCContent $i $done.data.pair.r -IgnoreRootTime}
                    elseif((Test-Path -LiteralPath $done.data.pair.i) -or (Test-Path -LiteralPath $done.data.pair.r)){throw 'Completed purge payload reappeared'}
                    if($i.action -eq 'archive_then_purge'){Assert-SCContent $i $i.archiveDestination -IgnoreTimes}
                    $held=Open-SCRetained $i;$results.Add(@{id=$i.id;status='completed';bytes=$i.bytes;action=$i.action});continue
                }
                Set-SCCurrentProgress $ctx.progress $i $itemIndex
                Write-SCProgress $ctx.progress 'starting'
                if($Mode -eq 'Verify'){throw 'Item has not completed; use Resume after inspection'}
                if(!$staged -and !(Test-Path -LiteralPath $i.source)){
                    if(!$intent){throw 'Source absent without a recycle intent'};$pair=Find-SCPair $i $intent.data;Assert-SCPair $i $pair;Assert-SCContent $i $pair.r -IgnoreRootTime
                    Write-SCJournal $ctx staged $i.id $pair;$staged=Get-SCRecord $ctx staged $i.id
                }
                if(!$staged -and $replayMode -and !(Test-Path -LiteralPath $i.source) -and !$intent){throw 'Source absent without completed evidence'}
                if(!$staged){
                    Assert-SCContent $i $i.source;$held=Open-SCRetained $i
                    if($Mode -eq 'Check' -and $i.action -eq 'archive_then_purge' -and (Test-Path -LiteralPath $i.archiveDestination)){throw 'Archive destination already exists'}
                    foreach($e in @(Get-SCExpected $i $i.source)|Where-Object kind -eq file){
                        $identity=[StorageCleanupNative]::Identity($e.path);$links=@([StorageCleanupNative]::Links($e.path)|ForEach-Object {Get-SCPath $_});$covered=$true;$allPurge=$true;foreach($l in $links){if(!$allFiles.ContainsKey($l)){$covered=$false}elseif($allFiles[$l] -eq 'recycle'){$allPurge=$false}}
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
                    Invoke-SCRecycle $i;Invoke-SCCheckpoint 'after_recycle' $i
                    if(Test-Path -LiteralPath $i.source){throw 'Source remains after recycle'}
                    $pair=Find-SCPair $i $recycleData;Assert-SCPair $i $pair;Assert-SCContent $i $pair.r -IgnoreRootTime
                    Write-SCJournal $ctx staged $i.id $pair;$staged=Get-SCRecord $ctx staged $i.id
                }
                if(Test-Path -LiteralPath $i.source){throw 'Source reappeared; stop item'}
                foreach($e in @(Get-SCExpected $i $staged.data.r)|Where-Object kind -eq file){$allFiles[$e.path]=$i.action}
                if(!$held){$copy=$i.Clone();if($i.action -eq 'archive_then_purge'){$copy.retainedCopy=$i.archiveDestination};$held=Open-SCRetained $copy}
                if($i.action -eq 'recycle'){Assert-SCPair $i $staged.data;Assert-SCContent $i $staged.data.r -IgnoreRootTime;Write-SCJournal $ctx completed $i.id @{action=$i.action;pair=$staged.data}}
                else{Invoke-SCPurge $ctx $i $staged.data}
                Complete-SCProgressItem $ctx.progress $i
                $results.Add(@{id=$i.id;status='completed';bytes=$i.bytes;action=$i.action})
            }catch{
                if($_.Exception.Message -like '*JOURNAL_FAILURE*'){throw}
                $results.Add(@{id=$i.id;status='needs-attention';reason=$_.Exception.Message;action=$i.action})
            }finally{if($held){foreach($h in $held){$h.Dispose()}};foreach($h in $sourceLocks){$h.Dispose()}}
        }
        if($Mode -eq 'Verify'){
            $partial=@($results|Where-Object status -eq 'needs-attention').Count -gt 0
            return @{schemaVersion=1;batchId=$manifest.batchId;mode='Verify';manifestSha256=$digest;outcome=$(if($partial){'partial'}else{'verified'});exitCode=$(if($partial){2}else{0});items=$results.ToArray()}
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
Export-ModuleMember -Function Invoke-StorageCleanup,New-StorageCleanupManifest,New-StorageCleanupDuplicateScan,New-StorageCleanupDuplicateSelection
