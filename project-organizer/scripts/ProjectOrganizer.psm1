Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if (-not ('ProjectOrganizer.NativeFile' -as [type])) {
    Add-Type -TypeDefinition @'
using System;
using System.IO;
using System.Runtime.InteropServices;
using Microsoft.Win32.SafeHandles;

namespace ProjectOrganizer {
    public static class NativeFile {
        [StructLayout(LayoutKind.Sequential)]
        private struct BY_HANDLE_FILE_INFORMATION {
            public uint FileAttributes;
            public System.Runtime.InteropServices.ComTypes.FILETIME CreationTime;
            public System.Runtime.InteropServices.ComTypes.FILETIME LastAccessTime;
            public System.Runtime.InteropServices.ComTypes.FILETIME LastWriteTime;
            public uint VolumeSerialNumber;
            public uint FileSizeHigh;
            public uint FileSizeLow;
            public uint NumberOfLinks;
            public uint FileIndexHigh;
            public uint FileIndexLow;
        }

        [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        private static extern SafeFileHandle CreateFileW(
            string fileName, uint desiredAccess, uint shareMode, IntPtr securityAttributes,
            uint creationDisposition, uint flagsAndAttributes, IntPtr templateFile);

        [DllImport("kernel32.dll", SetLastError = true)]
        private static extern bool DeviceIoControl(
            SafeFileHandle device, uint ioControlCode, IntPtr inBuffer, int inBufferSize,
            byte[] outBuffer, int outBufferSize, out int bytesReturned, IntPtr overlapped);

        [DllImport("kernel32.dll", SetLastError = true)]
        private static extern bool GetFileInformationByHandle(
            SafeFileHandle handle, out BY_HANDLE_FILE_INFORMATION information);

        private const uint OPEN_EXISTING = 3;
        private const uint FILE_FLAG_BACKUP_SEMANTICS = 0x02000000;
        private const uint FILE_FLAG_OPEN_REPARSE_POINT = 0x00200000;
        private const uint FSCTL_GET_REPARSE_POINT = 0x000900A8;

        public static UInt32 GetReparseTag(string path) {
            using (SafeFileHandle handle = CreateFileW(
                path, 0, 7, IntPtr.Zero, OPEN_EXISTING,
                FILE_FLAG_BACKUP_SEMANTICS | FILE_FLAG_OPEN_REPARSE_POINT, IntPtr.Zero)) {
                if (handle.IsInvalid) return 0;
                byte[] buffer = new byte[16384];
                int returned;
                if (!DeviceIoControl(handle, FSCTL_GET_REPARSE_POINT, IntPtr.Zero, 0,
                    buffer, buffer.Length, out returned, IntPtr.Zero) || returned < 4) return 0;
                return BitConverter.ToUInt32(buffer, 0);
            }
        }

        public static UInt32 GetLinkCount(string path) {
            using (SafeFileHandle handle = CreateFileW(path, 0, 7, IntPtr.Zero, OPEN_EXISTING, 0, IntPtr.Zero)) {
                if (handle.IsInvalid) return 0;
                BY_HANDLE_FILE_INFORMATION information;
                if (!GetFileInformationByHandle(handle, out information)) return 0;
                return information.NumberOfLinks;
            }
        }
    }
}
'@
}

function ConvertTo-POExtendedPath {
    param([Parameter(Mandatory = $true)][string]$Path)
    if ($Path.StartsWith('\\?\')) { return $Path }
    if ($Path.StartsWith('\\')) { return '\\?\UNC\' + $Path.TrimStart('\') }
    return '\\?\' + $Path
}

function ConvertFrom-POExtendedPath {
    param([Parameter(Mandatory = $true)][string]$Path)
    if ($Path.StartsWith('\\?\UNC\')) { return '\\' + $Path.Substring(8) }
    if ($Path.StartsWith('\\?\')) { return $Path.Substring(4) }
    return $Path
}

function Resolve-POFullPath {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [switch]$AllowNetwork,
        [switch]$AllowMissing
    )
    if ([string]::IsNullOrWhiteSpace($Path)) { throw 'Path is empty.' }
    if ($Path.IndexOfAny([char[]]'*?') -ge 0) { throw "Wildcards are not allowed: $Path" }
    if ($Path -match '(^|[\\/])\.\.([\\/]|$)') { throw "Parent traversal is not allowed: $Path" }
    if ($Path -match '%[^%]+%') { throw "Unexpanded environment variable is not allowed: $Path" }
    $expanded = [Environment]::ExpandEnvironmentVariables($Path)
    if (-not [IO.Path]::IsPathRooted($expanded)) { throw "Path must be absolute: $Path" }
    $full = [IO.Path]::GetFullPath($expanded)
    $root = [IO.Path]::GetPathRoot($full)
    if ($full -ne $root) { $full = $full.TrimEnd('\', '/') }
    if (-not $AllowNetwork -and $full -notmatch '^[A-Za-z]:\\') {
        throw "Execution path must use a local drive letter: $full"
    }
    if (-not $AllowNetwork) {
        $drive = New-Object IO.DriveInfo([IO.Path]::GetPathRoot($full))
        if ($drive.DriveType -eq [IO.DriveType]::Network) { throw "Network drive execution is prohibited: $full" }
    }
    if (-not $AllowMissing -and -not ([IO.File]::Exists((ConvertTo-POExtendedPath $full))) -and
        -not ([IO.Directory]::Exists((ConvertTo-POExtendedPath $full)))) {
        throw "Path does not exist: $full"
    }
    return $full
}

function Test-POPathWithin {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Parent,
        [switch]$AllowEqual
    )
    $pathFull = Resolve-POFullPath -Path $Path -AllowNetwork -AllowMissing
    $parentFull = Resolve-POFullPath -Path $Parent -AllowNetwork -AllowMissing
    if ($pathFull.Equals($parentFull, [StringComparison]::OrdinalIgnoreCase)) { return [bool]$AllowEqual }
    $prefix = $parentFull
    if (-not $prefix.EndsWith('\')) { $prefix += '\' }
    return $pathFull.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)
}

function ConvertTo-PORelativePath {
    param([Parameter(Mandatory = $true)][AllowEmptyString()][string]$Path)
    $value = $Path.Replace('\', '/').TrimStart('/')
    $parts = @($value.Split('/') | Where-Object { $_ -ne '' -and $_ -ne '.' })
    if (@($parts | Where-Object { $_ -eq '..' }).Count -gt 0) { throw "Relative path escapes its root: $Path" }
    return ($parts -join '/')
}

function Get-PORelativePath {
    param(
        [Parameter(Mandatory = $true)][string]$Root,
        [Parameter(Mandatory = $true)][string]$Path
    )
    $rootFull = Resolve-POFullPath -Path $Root -AllowNetwork -AllowMissing
    $pathFull = Resolve-POFullPath -Path $Path -AllowNetwork -AllowMissing
    if (-not (Test-POPathWithin -Path $pathFull -Parent $rootFull -AllowEqual)) {
        throw "Path is outside source root: $pathFull"
    }
    if ($pathFull.Equals($rootFull, [StringComparison]::OrdinalIgnoreCase)) { return '' }
    return ConvertTo-PORelativePath -Path $pathFull.Substring($rootFull.Length).TrimStart('\', '/')
}

function Join-POPath {
    param(
        [Parameter(Mandatory = $true)][string]$Root,
        [Parameter(Mandatory = $true)][AllowEmptyString()][string]$RelativePath
    )
    $rootFull = Resolve-POFullPath -Path $Root -AllowNetwork -AllowMissing
    $relative = ConvertTo-PORelativePath -Path $RelativePath
    $joined = if ($relative) { [IO.Path]::GetFullPath((Join-Path $rootFull $relative.Replace('/', '\'))) } else { $rootFull }
    if (-not (Test-POPathWithin -Path $joined -Parent $rootFull -AllowEqual)) { throw "Joined path escaped root: $joined" }
    return $joined
}

function Write-POText {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [AllowEmptyString()][string]$Text
    )
    $parent = Split-Path -Parent $Path
    if ($parent -and -not (Test-Path -LiteralPath $parent)) { [void](New-Item -ItemType Directory -Path $parent -Force) }
    $temporary = $Path + '.tmp.' + [Guid]::NewGuid().ToString('N')
    [IO.File]::WriteAllText($temporary, $Text, (New-Object Text.UTF8Encoding($false)))
    if (Test-Path -LiteralPath $Path) {
        $backup = $Path + '.bak.' + [Guid]::NewGuid().ToString('N')
        try { [IO.File]::Replace($temporary, $Path, $backup) }
        finally { if ([IO.File]::Exists($backup)) { [IO.File]::Delete($backup) } }
    }
    else { [IO.File]::Move($temporary, $Path) }
}

function Write-POJson {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][AllowEmptyCollection()]$Value
    )
    Write-POText -Path $Path -Text (($Value | ConvertTo-Json -Depth 30) + "`n")
}

function Read-POJsonArray {
    param([Parameter(Mandatory = $true)][string]$Path)
    $full = Resolve-POFullPath -Path $Path -AllowNetwork
    $parsed = Get-Content -LiteralPath $full -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($null -eq $parsed) { return }
    foreach ($item in @($parsed)) { Write-Output $item }
}

function Get-POStableId {
    param([Parameter(Mandatory = $true)][string]$Value,[ValidateRange(8,64)][int]$Length=12)
    $algorithm=[Security.Cryptography.SHA256]::Create()
    try{$bytes=[Text.Encoding]::UTF8.GetBytes($Value.ToLowerInvariant());$hash=$algorithm.ComputeHash($bytes)}
    finally{$algorithm.Dispose()}
    return ([BitConverter]::ToString($hash).Replace('-','').ToLowerInvariant().Substring(0,$Length))
}

function Write-POCsv {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][AllowEmptyCollection()][object[]]$Rows,
        [string[]]$Columns
    )
    $parent = Split-Path -Parent $Path
    if ($parent -and -not (Test-Path -LiteralPath $parent)) { [void](New-Item -ItemType Directory -Path $parent -Force) }
    $temporary = $Path + '.tmp.' + [Guid]::NewGuid().ToString('N')
    if ($Rows.Count -gt 0) {
        $Rows | Select-Object -Property $Columns | Export-Csv -LiteralPath $temporary -NoTypeInformation -Encoding UTF8
    }
    else {
        $header = ($Columns | ForEach-Object { '"' + $_.Replace('"', '""') + '"' }) -join ','
        [IO.File]::WriteAllText($temporary, $header + "`r`n", (New-Object Text.UTF8Encoding($true)))
    }
    if (Test-Path -LiteralPath $Path) {
        $backup = $Path + '.bak.' + [Guid]::NewGuid().ToString('N')
        try { [IO.File]::Replace($temporary, $Path, $backup) }
        finally { if ([IO.File]::Exists($backup)) { [IO.File]::Delete($backup) } }
    }
    else { [IO.File]::Move($temporary, $Path) }
}

function Add-POJsonLine {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)]$Value
    )
    $parent = Split-Path -Parent $Path
    if ($parent -and -not (Test-Path -LiteralPath $parent)) { [void](New-Item -ItemType Directory -Path $parent -Force) }
    $line = ($Value | ConvertTo-Json -Compress -Depth 20) + "`n"
    [IO.File]::AppendAllText($Path, $line, (New-Object Text.UTF8Encoding($false)))
}

function Get-POStableSha256 {
    param([Parameter(Mandatory = $true)][string]$Path)
    $full = Resolve-POFullPath -Path $Path -AllowNetwork
    $extended = ConvertTo-POExtendedPath $full
    $before = New-Object IO.FileInfo($extended)
    $before.Refresh()
    if (-not $before.Exists) { throw "File does not exist: $full" }
    $beforeLength = [int64]$before.Length
    $beforeWrite = $before.LastWriteTimeUtc.Ticks
    $algorithm = [Security.Cryptography.SHA256]::Create()
    try {
        $stream = New-Object IO.FileStream($extended, [IO.FileMode]::Open, [IO.FileAccess]::Read,
            ([IO.FileShare]::ReadWrite -bor [IO.FileShare]::Delete), 1048576, [IO.FileOptions]::SequentialScan)
        try { $hash = $algorithm.ComputeHash($stream) }
        finally { $stream.Dispose() }
    }
    finally { $algorithm.Dispose() }
    $after = New-Object IO.FileInfo($extended)
    $after.Refresh()
    if (-not $after.Exists -or $after.Length -ne $beforeLength -or $after.LastWriteTimeUtc.Ticks -ne $beforeWrite) {
        throw "PO_SOURCE_CHANGED: $full"
    }
    return ([BitConverter]::ToString($hash).Replace('-', '').ToUpperInvariant())
}

function Get-POReparseInfo {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][IO.FileAttributes]$Attributes,
        [switch]$File
    )
    $extended = ConvertTo-POExtendedPath $Path
    $tag = [uint32]0
    if (($Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
        $tag = [ProjectOrganizer.NativeFile]::GetReparseTag($extended)
    }
    $attributeBits = [uint32][int]$Attributes
    $offlineMask = [uint32](0x00001000 -bor 0x00040000 -bor 0x00400000)
    $linkCount = [uint32]0
    if ($File -and $tag -eq 0) { $linkCount = [ProjectOrganizer.NativeFile]::GetLinkCount($extended) }
    return [pscustomobject][ordered]@{
        tag = ('0x{0:X8}' -f $tag)
        tag_value = $tag
        is_name_surrogate = (($tag -band [uint32]0x20000000) -ne 0)
        is_cloud_placeholder = (($attributeBits -band $offlineMask) -ne 0)
        link_count = $linkCount
    }
}

function Get-POAlternateStreamCount {
    param([Parameter(Mandatory = $true)][string]$Path)
    try {
        $streams = @(Get-Item -LiteralPath $Path -Stream * -ErrorAction Stop)
        return [int]$streams.Count
    }
    catch { return -1 }
}

function Get-POFileSnapshot {
    param([Parameter(Mandatory = $true)][string]$Root,[string]$ExcludeRoot)
    $scan = Get-POSourceEntries -Root $Root -ExcludeRoot $ExcludeRoot
    $files = @($scan.Entries | Where-Object { $_.entry_type -eq 'file' })
    return [pscustomobject][ordered]@{
        file_count = [int64]$files.Count
        directory_count = [int64]@($scan.Entries | Where-Object { $_.entry_type -eq 'directory' }).Count
        total_bytes = [int64](($files | Measure-Object -Property size_bytes -Sum).Sum)
        error_count = [int64]$scan.Errors.Count
    }
}

function Get-POPathVolume {
    param([Parameter(Mandatory = $true)][string]$Path)
    $full = Resolve-POFullPath -Path $Path -AllowMissing
    return ([IO.Path]::GetPathRoot($full)).TrimEnd('\\').ToUpperInvariant()
}

function Test-POSameVolume {
    param(
        [Parameter(Mandatory = $true)][string]$First,
        [Parameter(Mandatory = $true)][string]$Second
    )
    return (Get-POPathVolume -Path $First).Equals((Get-POPathVolume -Path $Second), [StringComparison]::OrdinalIgnoreCase)
}

function Test-POSyncPath {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        $SyncRoots
    )
    foreach ($root in @($SyncRoots)) {
        if ([string]::IsNullOrWhiteSpace([string]$root)) { continue }
        if (Test-POPathWithin -Path $Path -Parent ([string]$root) -AllowEqual) { return $true }
    }
    return $false
}

function Test-POHashManifest {
    param([Parameter(Mandatory = $true)][string]$ManifestPath)
    $manifest = Resolve-POFullPath -Path $ManifestPath -AllowNetwork
    $base = Split-Path -Parent $manifest
    $errors = New-Object Collections.Generic.List[string]
    foreach ($line in @(Get-Content -LiteralPath $manifest -Encoding UTF8)) {
        if ([string]::IsNullOrWhiteSpace($line)) { continue }
        if ($line -notmatch '^([0-9A-Fa-f]{64})  (.+)$') {
            $errors.Add("Invalid manifest line: $line")
            continue
        }
        $expected = $Matches[1].ToUpperInvariant()
        $listed = $Matches[2].Replace('/', '\\')
        $candidate = if ([IO.Path]::IsPathRooted($listed)) { $listed } else { Join-Path $base $listed }
        try {
            $actual = Get-POStableSha256 -Path $candidate
            if ($actual -ne $expected) { $errors.Add("Hash mismatch: $candidate") }
        }
        catch { $errors.Add("Manifest check failed: $candidate : $($_.Exception.Message)") }
    }
    return [pscustomobject]@{ Valid=($errors.Count -eq 0); Errors=@($errors.ToArray()) }
}

function Assert-POExpectedFile {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][int64]$SizeBytes,
        [Parameter(Mandatory = $true)][string]$LastWriteUtc,
        [Parameter(Mandatory = $true)][string]$Sha256
    )
    $full = Resolve-POFullPath -Path $Path
    $info = New-Object IO.FileInfo((ConvertTo-POExtendedPath $full))
    $info.Refresh()
    if ([int64]$info.Length -ne $SizeBytes) { throw "PO_SOURCE_SIZE_CHANGED: $full" }
    if ($LastWriteUtc -and $info.LastWriteTimeUtc.ToString('o') -ne $LastWriteUtc) { throw "PO_SOURCE_TIME_CHANGED: $full" }
    $actual = Get-POStableSha256 -Path $full
    if ($actual -ne $Sha256.ToUpperInvariant()) { throw "PO_SOURCE_HASH_CHANGED: $full" }
    return $full
}

function Copy-POFileAtomicVerified {
    param(
        [Parameter(Mandatory = $true)][string]$Source,
        [Parameter(Mandatory = $true)][string]$Target,
        [Parameter(Mandatory = $true)][string]$ExpectedSha256
    )
    $sourceFull = Resolve-POFullPath -Path $Source
    $targetFull = Resolve-POFullPath -Path $Target -AllowMissing
    if ([IO.File]::Exists((ConvertTo-POExtendedPath $targetFull)) -or [IO.Directory]::Exists((ConvertTo-POExtendedPath $targetFull))) {
        throw "Target already exists: $targetFull"
    }
    $parent = Split-Path -Parent $targetFull
    [void][IO.Directory]::CreateDirectory((ConvertTo-POExtendedPath $parent))
    $temporary = $targetFull + '.po-partial-' + [Guid]::NewGuid().ToString('N')
    try {
        [IO.File]::Copy((ConvertTo-POExtendedPath $sourceFull), (ConvertTo-POExtendedPath $temporary), $false)
        $temporaryHash = Get-POStableSha256 -Path $temporary
        if ($temporaryHash -ne $ExpectedSha256.ToUpperInvariant()) { throw "Copied file hash mismatch: $targetFull" }
        [IO.File]::Move((ConvertTo-POExtendedPath $temporary), (ConvertTo-POExtendedPath $targetFull))
        $targetHash = Get-POStableSha256 -Path $targetFull
        if ($targetHash -ne $ExpectedSha256.ToUpperInvariant()) { throw "Final target hash mismatch: $targetFull" }
    }
    finally {
        if ([IO.File]::Exists((ConvertTo-POExtendedPath $temporary))) {
            [IO.File]::Delete((ConvertTo-POExtendedPath $temporary))
        }
    }
    return $targetFull
}

function Move-POFileVerified {
    param(
        [Parameter(Mandatory = $true)][string]$Source,
        [Parameter(Mandatory = $true)][string]$Target,
        [Parameter(Mandatory = $true)][string]$ExpectedSha256
    )
    $sourceFull = Resolve-POFullPath -Path $Source
    $targetFull = Resolve-POFullPath -Path $Target -AllowMissing
    if (-not (Test-POSameVolume -First $sourceFull -Second $targetFull)) { throw 'Move-POFileVerified requires one volume.' }
    if ([IO.File]::Exists((ConvertTo-POExtendedPath $targetFull)) -or [IO.Directory]::Exists((ConvertTo-POExtendedPath $targetFull))) {
        throw "Target already exists: $targetFull"
    }
    [void][IO.Directory]::CreateDirectory((ConvertTo-POExtendedPath (Split-Path -Parent $targetFull)))
    [IO.File]::Move((ConvertTo-POExtendedPath $sourceFull), (ConvertTo-POExtendedPath $targetFull))
    try {
        $targetHash = Get-POStableSha256 -Path $targetFull
        if ($targetHash -ne $ExpectedSha256.ToUpperInvariant()) { throw "Moved file hash mismatch: $targetFull" }
    }
    catch {
        if (-not [IO.File]::Exists((ConvertTo-POExtendedPath $sourceFull)) -and
            [IO.File]::Exists((ConvertTo-POExtendedPath $targetFull))) {
            [IO.File]::Move((ConvertTo-POExtendedPath $targetFull), (ConvertTo-POExtendedPath $sourceFull))
        }
        throw
    }
    return $targetFull
}

function Copy-PODirectoryVerified {
    param(
        [Parameter(Mandatory = $true)][string]$Source,
        [Parameter(Mandatory = $true)][string]$Target
    )
    $sourceFull = Resolve-POFullPath -Path $Source
    $targetFull = Resolve-POFullPath -Path $Target -AllowMissing
    if ([IO.File]::Exists((ConvertTo-POExtendedPath $targetFull)) -or [IO.Directory]::Exists((ConvertTo-POExtendedPath $targetFull))) {
        throw "Target already exists: $targetFull"
    }
    $temporary = $targetFull + '.po-partial-' + [Guid]::NewGuid().ToString('N')
    $scan = Get-POSourceEntries -Root $sourceFull
    if ($scan.Errors.Count -gt 0) { throw "Directory scan failed: $sourceFull" }
    foreach ($entry in @($scan.Entries)) {
        if ($entry.is_name_surrogate -or $entry.is_cloud_placeholder -or $entry.link_count -gt 1 -or $entry.stream_count -gt 1 -or $entry.stream_count -lt 0) {
            throw "Unsupported directory entry: $($entry.full_path)"
        }
    }
    try {
        [void][IO.Directory]::CreateDirectory((ConvertTo-POExtendedPath $temporary))
        foreach ($directory in @($scan.Entries | Where-Object { $_.entry_type -eq 'directory' } |
            Sort-Object { ([string]$_.relative_path).Length }, { ([string]$_.relative_path).ToLowerInvariant() }, { [string]$_.relative_path })) {
            [void][IO.Directory]::CreateDirectory((ConvertTo-POExtendedPath (Join-POPath -Root $temporary -RelativePath $directory.relative_path)))
        }
        foreach ($file in @($scan.Entries | Where-Object { $_.entry_type -eq 'file' } |
            Sort-Object { ([string]$_.relative_path).ToLowerInvariant() }, { [string]$_.relative_path })) {
            $destination = Join-POPath -Root $temporary -RelativePath $file.relative_path
            [void][IO.Directory]::CreateDirectory((ConvertTo-POExtendedPath (Split-Path -Parent $destination)))
            $hash = Get-POStableSha256 -Path $file.full_path
            [IO.File]::Copy((ConvertTo-POExtendedPath $file.full_path), (ConvertTo-POExtendedPath $destination), $false)
            if ((Get-POStableSha256 -Path $destination) -ne $hash) { throw "Directory copy hash mismatch: $($file.full_path)" }
        }
        [void][IO.Directory]::CreateDirectory((ConvertTo-POExtendedPath (Split-Path -Parent $targetFull)))
        [IO.Directory]::Move((ConvertTo-POExtendedPath $temporary), (ConvertTo-POExtendedPath $targetFull))
    }
    catch {
        if ([IO.Directory]::Exists((ConvertTo-POExtendedPath $temporary))) {
            [IO.Directory]::Delete((ConvertTo-POExtendedPath $temporary), $true)
        }
        throw
    }
    return $targetFull
}

function Get-POSourceEntries {
    param([Parameter(Mandatory = $true)][string]$Root,[string]$ExcludeRoot)
    $rootFull = Resolve-POFullPath -Path $Root -AllowNetwork
    $excluded = ''
    if ($ExcludeRoot -and (Test-POPathWithin -Path $ExcludeRoot -Parent $rootFull -AllowEqual)) {
        $excluded = Resolve-POFullPath -Path $ExcludeRoot -AllowMissing
        if ($excluded.Equals($rootFull,[StringComparison]::OrdinalIgnoreCase)) { throw 'Cannot exclude the scan root.' }
        Assert-POSafePath -Path $excluded
    }
    $entries = New-Object Collections.Generic.List[object]
    $errors = New-Object Collections.Generic.List[object]
    $pending = New-Object Collections.Generic.Stack[string]
    $pending.Push($rootFull)
    while ($pending.Count -gt 0) {
        $directory = $pending.Pop()
        try {
            $children = @([IO.Directory]::EnumerateFileSystemEntries((ConvertTo-POExtendedPath $directory)) |
                ForEach-Object { ConvertFrom-POExtendedPath $_ } | Sort-Object { $_.ToLowerInvariant() }, { $_ })
        }
        catch {
            $errors.Add([pscustomobject][ordered]@{ path=$directory; stage='enumerate'; error=$_.Exception.Message })
            continue
        }
        foreach ($child in $children) {
            try {
                if ($excluded -and (Test-POPathWithin -Path $child -Parent $excluded -AllowEqual)) { continue }
                $attributes = [IO.File]::GetAttributes((ConvertTo-POExtendedPath $child))
                $isDirectory = (($attributes -band [IO.FileAttributes]::Directory) -ne 0)
                $reparse = Get-POReparseInfo -Path $child -Attributes $attributes -File:(-not $isDirectory)
                $relative = Get-PORelativePath -Root $rootFull -Path $child
                if ($isDirectory) {
                    $info = New-Object IO.DirectoryInfo((ConvertTo-POExtendedPath $child))
                    $entries.Add([pscustomobject][ordered]@{
                        full_path=$child; relative_path=$relative; entry_type='directory'; size_bytes=[int64]0
                        last_write_utc=$info.LastWriteTimeUtc.ToString('o'); attributes=[string]$attributes
                        reparse_tag=$reparse.tag; is_name_surrogate=$reparse.is_name_surrogate
                        is_cloud_placeholder=$reparse.is_cloud_placeholder; link_count=[int]0; stream_count=[int]0
                    })
                    if (-not $reparse.is_name_surrogate) { $pending.Push($child) }
                }
                else {
                    $info = New-Object IO.FileInfo((ConvertTo-POExtendedPath $child))
                    $entries.Add([pscustomobject][ordered]@{
                        full_path=$child; relative_path=$relative; entry_type='file'; size_bytes=[int64]$info.Length
                        last_write_utc=$info.LastWriteTimeUtc.ToString('o'); attributes=[string]$attributes
                        reparse_tag=$reparse.tag; is_name_surrogate=$reparse.is_name_surrogate
                        is_cloud_placeholder=$reparse.is_cloud_placeholder; link_count=[int]$reparse.link_count
                        stream_count=(Get-POAlternateStreamCount -Path $child)
                    })
                }
            }
            catch {
                $errors.Add([pscustomobject][ordered]@{ path=$child; stage='metadata'; error=$_.Exception.Message })
            }
        }
    }
    # Do not count otherwise-empty ancestors introduced only by this run's audit subtree.
    if ($excluded) {
        foreach ($entry in @($entries.ToArray() | Where-Object { $_.entry_type -eq 'directory' } | Sort-Object { $_.full_path.Length } -Descending)) {
            if ((Test-POPathWithin -Path $excluded -Parent $entry.full_path) -and
                @($entries.ToArray() | Where-Object { Test-POPathWithin -Path $_.full_path -Parent $entry.full_path }).Count -eq 0) {
                [void]$entries.Remove($entry)
            }
        }
    }
    return [pscustomobject]@{ Entries=@($entries.ToArray()); Errors=@($errors.ToArray()) }
}

function Test-POGitMetadataPath {
    param([Parameter(Mandatory = $true)][string]$RelativePath)
    $relative = (ConvertTo-PORelativePath $RelativePath).ToLowerInvariant()
    foreach ($part in @($relative.Split('/'))) {
        if ($part -in @('.git','.git-backup')) { return $true }
    }
    return $false
}

function Test-POExcludedPath {
    param(
        [Parameter(Mandatory = $true)][string]$RelativePath,
        $Rules
    )
    if ($null -eq $Rules) { return $false }
    $relative = ConvertTo-PORelativePath $RelativePath
    $lower = $relative.ToLowerInvariant()
    foreach ($name in @($Rules.directory_names)) {
        $needle = ([string]$name).ToLowerInvariant()
        if (@($lower.Split('/') | Where-Object { $_ -eq $needle }).Count -gt 0) { return $true }
    }
    foreach ($prefix in @($Rules.relative_prefixes)) {
        $normalized = (ConvertTo-PORelativePath ([string]$prefix)).ToLowerInvariant()
        if ($lower -eq $normalized -or $lower.StartsWith($normalized + '/')) { return $true }
    }
    foreach ($extension in @($Rules.extensions)) {
        if ($lower.EndsWith(([string]$extension).ToLowerInvariant())) { return $true }
    }
    return $false
}

function Get-POProposedRelativePath {
    param(
        [Parameter(Mandatory = $true)]$Config,
        [Parameter(Mandatory = $true)]$Source,
        [Parameter(Mandatory = $true)][string]$RelativePath
    )
    $relative = ConvertTo-PORelativePath $RelativePath
    if ([string]$Config.mode -eq 'group') {
        return ConvertTo-PORelativePath (([string]$Source.target_name).Trim('/') + '/' + $relative)
    }
    foreach ($rule in @($Config.mapping_rules)) {
        if ([string]$rule.source_id -and [string]$rule.source_id -ne [string]$Source.id) { continue }
        $from = ConvertTo-PORelativePath ([string]$rule.from_prefix)
        $to = ConvertTo-PORelativePath ([string]$rule.to_prefix)
        if ($relative.Equals($from, [StringComparison]::OrdinalIgnoreCase)) { return $to }
        if ($from -and $relative.StartsWith($from + '/', [StringComparison]::OrdinalIgnoreCase)) {
            return ConvertTo-PORelativePath ($to.TrimEnd('/') + '/' + $relative.Substring($from.Length + 1))
        }
    }
    return $relative
}

function Read-POConfig {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [switch]$RequireSources,
        [switch]$ForExecution,
        [switch]$AllowMissingSources
    )
    $configPath = Resolve-POFullPath -Path $Path -AllowNetwork
    $config = Get-Content -LiteralPath $configPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ([string]$config.schema_version -notin @('1.0','1.1')) { throw 'Unsupported schema_version.' }
    if ([string]$config.mode -notin @('merge','group')) { throw 'mode must be merge or group.' }
    foreach ($required in @('search_roots','target_root','audit_root','external_git_root','sync_roots','active_repo_policy')) {
        if ($null -eq $config.PSObject.Properties[$required] -or [string]::IsNullOrWhiteSpace([string]$config.$required)) {
            throw "Missing config field: $required"
        }
    }
    if (@($config.search_roots).Count -eq 0) { throw 'At least one bounded search_root is required.' }
    foreach ($root in @($config.search_roots)) { [void](Resolve-POFullPath -Path ([string]$root) -AllowNetwork) }
    $config.target_root = Resolve-POFullPath -Path ([string]$config.target_root) -AllowNetwork -AllowMissing
    $config.audit_root = Resolve-POFullPath -Path ([string]$config.audit_root) -AllowNetwork -AllowMissing
    $config.external_git_root = Resolve-POFullPath -Path ([string]$config.external_git_root) -AllowMissing
    foreach($syncRootValue in @($config.sync_roots)){
        $syncRoot=Resolve-POFullPath -Path ([string]$syncRootValue) -AllowNetwork -AllowMissing
        if(Test-POPathWithin -Path $config.external_git_root -Parent $syncRoot -AllowEqual){throw "external_git_root is inside a sync_root: $syncRoot"}
    }
    if((Test-POPathWithin -Path $config.external_git_root -Parent $config.target_root -AllowEqual) -or
        (Test-POPathWithin -Path $config.target_root -Parent $config.external_git_root -AllowEqual)){throw 'external_git_root overlaps target_root.'}
    if ([string]$config.schema_version -eq '1.0') {
        if((Test-POPathWithin -Path $config.audit_root -Parent $config.target_root -AllowEqual) -or
            (Test-POPathWithin -Path $config.target_root -Parent $config.audit_root -AllowEqual)){throw 'audit_root overlaps target_root.'}
    }
    if ($ForExecution) {
        [void](Resolve-POFullPath -Path $config.target_root -AllowMissing)
        [void](Resolve-POFullPath -Path $config.audit_root -AllowMissing)
    }
    $minimumSources = if ([string]$config.schema_version -eq '1.1') { 1 } else { 2 }
    if ($RequireSources -and @($config.sources).Count -lt $minimumSources) { throw "At least $minimumSources confirmed sources are required." }
    $ids = @{}
    $sourcePaths = New-Object Collections.Generic.List[string]
    foreach ($source in @($config.sources)) {
        $id = [string]$source.id
        if ([string]$config.schema_version -eq '1.1' -and $id -eq '__target__') { throw '__target__ is reserved for existing target inputs.' }
        if ($id -notmatch '^[A-Za-z0-9._-]+$') { throw "Invalid source id: $id" }
        if ($ids.ContainsKey($id.ToLowerInvariant())) { throw "Duplicate source id: $id" }
        $ids[$id.ToLowerInvariant()] = $true
        $source.path = Resolve-POFullPath -Path ([string]$source.path) -AllowNetwork -AllowMissing:$AllowMissingSources
        if ($ForExecution -and -not $AllowMissingSources) { [void](Resolve-POFullPath -Path ([string]$source.path)) }
        if(-not $AllowMissingSources){
            $sourceAttributes=[IO.File]::GetAttributes((ConvertTo-POExtendedPath ([string]$source.path)))
            $sourceReparse=Get-POReparseInfo -Path ([string]$source.path) -Attributes $sourceAttributes
            if($sourceReparse.is_name_surrogate){throw "Source root cannot be a junction or symbolic link: $($source.path)"}
        }
        if ([string]$config.mode -eq 'group' -and [string]$source.target_name -notmatch '^[A-Za-z0-9._-]+$') {
            throw "group source requires a safe target_name: $id"
        }
        $sourcePaths.Add([string]$source.path)
    }
    if([string]$config.mode -eq 'group'){
        if([string]$config.active_repo_policy -ne 'preserve_each'){throw 'group mode requires active_repo_policy preserve_each.'}
        if(@($config.mapping_rules).Count -gt 0){throw 'group mode preserves each project structure and does not accept mapping_rules.'}
        $targetNames=@($config.sources|ForEach-Object{([string]$_.target_name).ToLowerInvariant()})
        if(@($targetNames|Sort-Object -Unique).Count -ne $targetNames.Count){throw 'group target_name values must be unique.'}
    }elseif([string]$config.active_repo_policy -notin @('target_existing','new') -and [string]$config.active_repo_policy -notlike 'source:*'){
        throw 'Unsupported merge active_repo_policy.'
    }
    if([string]$config.mode -eq 'merge'){
        if($null -eq $config.PSObject.Properties['layout_decisions']){throw 'merge mode requires layout_decisions.'}
        $layout=$config.layout_decisions
        foreach($field in @('restructure_in_scope','root_files','category_language','max_general_depth','deep_structure_prefixes',
            'independent_subprojects','version_policy','keep_empty_directories','forbidden_target_paths','exceptions','approved_tree_sha256')){
            if($null -eq $layout.PSObject.Properties[$field]){throw "Missing layout_decisions field: $field"}
        }
        if(@($config.mapping_rules).Count -gt 0 -and -not [bool]$layout.restructure_in_scope){
            throw 'mapping_rules require layout_decisions.restructure_in_scope=true.'
        }
        if([string]$layout.category_language -notin @('en','zh','preserve')){throw 'category_language must be en, zh, or preserve.'}
        if([int]$layout.max_general_depth -lt 0){throw 'max_general_depth must be zero or greater.'}
        $versionPolicies = @('preserve_all','approved_selection')
        if ([string]$config.schema_version -eq '1.1') { $versionPolicies += 'integrate' }
        if([string]$layout.version_policy -notin $versionPolicies){throw 'Unsupported version_policy.'}
        $approvedTree=[string]$layout.approved_tree_sha256
        if($approvedTree -and $approvedTree -notmatch '^[0-9A-Fa-f]{64}$'){throw 'approved_tree_sha256 must be empty or contain 64 hexadecimal characters.'}
        foreach($rootFile in @($layout.root_files)){
            $normalized=ConvertTo-PORelativePath ([string]$rootFile)
            if(-not $normalized -or $normalized.Contains('/')){throw "root_files must contain root-level file names: $rootFile"}
        }
        foreach($listName in @('deep_structure_prefixes','independent_subprojects','keep_empty_directories','forbidden_target_paths')){
            foreach($value in @($layout.$listName)){
                $normalized=ConvertTo-PORelativePath ([string]$value)
                if(-not $normalized){throw "$listName cannot contain an empty path."}
            }
        }
        foreach($exception in @($layout.exceptions)){
            $normalized=ConvertTo-PORelativePath ([string]$exception.path)
            if(-not $normalized -or [string]::IsNullOrWhiteSpace([string]$exception.reason)){throw 'Each layout exception requires a path and reason.'}
        }
        foreach($rule in @($config.mapping_rules)){
            $ruleSource=[string]$rule.source_id
            if($ruleSource -and -not $ids.ContainsKey($ruleSource.ToLowerInvariant())){throw "mapping_rules references an unknown source: $ruleSource"}
            $from=ConvertTo-PORelativePath ([string]$rule.from_prefix)
            [void](ConvertTo-PORelativePath ([string]$rule.to_prefix))
            if(-not $from){throw 'mapping_rules.from_prefix cannot be empty.'}
        }
    }
    for ($i = 0; $i -lt $sourcePaths.Count; $i++) {
        for ($j = $i + 1; $j -lt $sourcePaths.Count; $j++) {
            if ((Test-POPathWithin -Path $sourcePaths[$i] -Parent $sourcePaths[$j] -AllowEqual) -or
                (Test-POPathWithin -Path $sourcePaths[$j] -Parent $sourcePaths[$i] -AllowEqual)) {
                throw "Source roots overlap: $($sourcePaths[$i]) ; $($sourcePaths[$j])"
            }
        }
        if ((Test-POPathWithin -Path $config.target_root -Parent $sourcePaths[$i] -AllowEqual) -or
            (Test-POPathWithin -Path $sourcePaths[$i] -Parent $config.target_root -AllowEqual)) {
            throw "Source and target overlap: $($sourcePaths[$i]) ; $($config.target_root)"
        }
        if (Test-POPathWithin -Path $config.audit_root -Parent $sourcePaths[$i] -AllowEqual) {
            throw "Audit root is inside a source: $($config.audit_root)"
        }
        if ((Test-POPathWithin -Path $config.external_git_root -Parent $sourcePaths[$i] -AllowEqual) -or
            (Test-POPathWithin -Path $sourcePaths[$i] -Parent $config.external_git_root -AllowEqual)) {
            throw "external_git_root overlaps source: $($sourcePaths[$i])"
        }
    }
    foreach ($protected in @($config.protected_paths)) {
        $protectedFull = Resolve-POFullPath -Path ([string]$protected) -AllowNetwork -AllowMissing
        if ((Test-POPathWithin -Path $config.target_root -Parent $protectedFull -AllowEqual) -or
            (Test-POPathWithin -Path $protectedFull -Parent $config.target_root -AllowEqual)) {
            throw "Target overlaps protected path: $protectedFull"
        }
        foreach($sourcePath in $sourcePaths){
            if((Test-POPathWithin -Path $sourcePath -Parent $protectedFull -AllowEqual) -or
                (Test-POPathWithin -Path $protectedFull -Parent $sourcePath -AllowEqual)){throw "Source overlaps protected path: $protectedFull"}
        }
    }
    if ([string]$config.mode -eq 'merge' -and [string]$config.active_repo_policy -like 'source:*') {
        $canonical = [string]$config.canonical_source_id
        if (-not $ids.ContainsKey($canonical.ToLowerInvariant())) { throw 'canonical_source_id is not a confirmed source.' }
        if([string]$config.active_repo_policy -ne ('source:'+$canonical)){throw 'active_repo_policy source must match canonical_source_id.'}
    }
    if ([string]$config.schema_version -eq '1.1') {
        Assert-POAuditPath -Config $config
        if ($null -ne $config.PSObject.Properties['integration_manifest'] -and $config.integration_manifest) {
            if ([string]$config.mode -ne 'merge' -or [string]$config.layout_decisions.version_policy -ne 'integrate') {
                throw 'integration_manifest requires merge mode and version_policy integrate.'
            }
            $config.integration_manifest = Resolve-POFullPath -Path ([string]$config.integration_manifest)
            if (-not (Test-POPathWithin -Path $config.integration_manifest -Parent $config.audit_root)) { throw 'integration_manifest must be inside audit_root.' }
        }
    }
    elseif ($null -ne $config.PSObject.Properties['integration_manifest'] -and $config.integration_manifest) {
        throw 'integration_manifest requires config schema_version 1.1.'
    }
    return $config
}

function Assert-POSafePath {
    param([Parameter(Mandatory = $true)][string]$Path,[switch]$File)
    $full = Resolve-POFullPath -Path $Path -AllowMissing
    $cursor = $full
    while ($cursor) {
        if ([IO.File]::Exists((ConvertTo-POExtendedPath $cursor)) -or [IO.Directory]::Exists((ConvertTo-POExtendedPath $cursor))) {
            $attributes = [IO.File]::GetAttributes((ConvertTo-POExtendedPath $cursor))
            $isFile = ($attributes -band [IO.FileAttributes]::Directory) -eq 0
            $info = Get-POReparseInfo -Path $cursor -Attributes $attributes -File:$isFile
            if ($info.is_name_surrogate -or $info.is_cloud_placeholder -or
                ($attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw "Unsafe path component: $cursor" }
            if ($isFile -and (-not $cursor.Equals($full,[StringComparison]::OrdinalIgnoreCase) -or $info.link_count -gt 1)) {
                throw "Unsafe file or ancestor: $cursor"
            }
        }
        $parent = [IO.Path]::GetDirectoryName($cursor)
        if ($parent -eq $cursor) { break }
        $cursor = $parent
    }
    if ($File) {
        if (-not [IO.File]::Exists((ConvertTo-POExtendedPath $full))) { throw "Expected regular file: $full" }
        if ((Get-POAlternateStreamCount -Path $full) -ne 1) { throw "Unsupported file streams: $full" }
    }
}

function Assert-POAuditPath {
    param([Parameter(Mandatory = $true)]$Config,[string]$OutputDir)
    if ([string]$Config.schema_version -ne '1.1') { return }
    $audit = Resolve-POFullPath -Path ([string]$Config.audit_root) -AllowMissing
    if (Test-POPathWithin -Path ([string]$Config.target_root) -Parent $audit -AllowEqual) { throw 'audit_root cannot equal or contain target_root.' }
    foreach ($source in @($Config.sources)) {
        if ((Test-POPathWithin -Path $audit -Parent ([string]$source.path) -AllowEqual) -or
            (Test-POPathWithin -Path ([string]$source.path) -Parent $audit -AllowEqual)) { throw 'audit_root overlaps a source.' }
    }
    Assert-POSafePath -Path $audit
    if ($OutputDir) {
        if (-not (Test-POPathWithin -Path $OutputDir -Parent $audit -AllowEqual)) { throw 'OutputDir must belong to audit_root.' }
        Assert-POSafePath -Path $OutputDir
    }
}

function Assert-POAuditContents {
    param([Parameter(Mandatory = $true)]$Config,[Parameter(Mandatory = $true)][string]$OutputDir,
        [Parameter(Mandatory = $true)][string]$ConfigPath,$Integration)
    if ([string]$Config.schema_version -ne '1.1' -or
        -not (Test-POPathWithin -Path ([string]$Config.audit_root) -Parent ([string]$Config.target_root))) { return }
    Assert-POAuditPath -Config $Config -OutputDir $OutputDir
    if (-not [IO.Directory]::Exists((ConvertTo-POExtendedPath ([string]$Config.audit_root)))) { return }
    $allowed = @{}
    $allowed[(Resolve-POFullPath -Path $ConfigPath).ToLowerInvariant()] = $true
    if ($null -ne $Integration) {
        foreach ($path in @($Integration.BoundPaths)) { $allowed[([string]$path).ToLowerInvariant()] = $true }
    }
    # Exact files owned by the existing workflow. No directory is trusted recursively.
    $artifactNames = @(
        'candidates.csv','candidate_evidence.json','files.csv','duplicates.csv','conflicts.csv','errors.csv',
        'source_state.json','git_state.json','target-state.csv','target-state.json','layout-violations.csv','target-tree.csv',
        'target-tree.md','target-tree.sha256','summary.md','inventory-files.sha256','inventory.sha256',
        'git_archives.json','git-errors.csv','git-review.md','actions.csv','space.json','plan-errors.csv',
        'review.md','plan-files.sha256','plan.sha256','execution-state.json','execution.jsonl','execution-summary.json',
        'organization-acceptance.json','acceptance-errors.csv','acceptance.md','retirement.csv',
        'retirement-errors.csv','retirement-review.md','retirement-files.sha256','retirement.sha256',
        'retirement-execution-state.json','retirement-execution.jsonl','retirement-execution-summary.json',
        'final-acceptance.json','final-acceptance-errors.csv','final-acceptance.md','integration-checks.json'
    )
    foreach ($name in $artifactNames) { $allowed[(Join-Path $OutputDir $name).ToLowerInvariant()] = $true }
    $repositoryIds = New-Object Collections.Generic.List[string]
    foreach ($source in @($Config.sources)) {
        $repositoryIds.Add([string]$source.id)
        if ($null -ne $source.PSObject.Properties['git_paths']) {
            for ($i=1;$i -le @($source.git_paths).Count;$i++) { $repositoryIds.Add(([string]$source.id)+'-extra-'+$i) }
        }
    }
    foreach ($id in $repositoryIds) {
        $allowed[(Join-Path $OutputDir ('git-bundles/'+$id+'.bundle')).ToLowerInvariant()] = $true
        foreach ($name in @('source-fsck.txt','working-tree.diff','index.diff','untracked.txt','ignored.txt',
            'git-state.json','bundle-verify.txt','restore-fsck.txt','recovery-files.sha256')) {
            $allowed[(Join-Path $OutputDir ('git-recovery/'+$id+'/'+$name)).ToLowerInvariant()] = $true
        }
    }
    $receiptPath = Join-Path $OutputDir 'integration-checks.json'
    if ($null -ne $Integration -and [IO.File]::Exists((ConvertTo-POExtendedPath $receiptPath))) {
        Assert-POSafePath -Path $receiptPath -File
        $receipt = Get-Content -LiteralPath $receiptPath -Raw -Encoding UTF8 | ConvertFrom-Json
        if ([string]$receipt.schema_version -ne '1.0' -or [string]$receipt.manifest_sha256 -ne $Integration.ManifestSha256) { throw 'Audit check receipt belongs to another integration.' }
        foreach ($check in @($receipt.checks)) {
            $reportPath = Resolve-POFullPath -Path ([string]$check.report_path)
            if (-not (Test-POPathWithin -Path $reportPath -Parent ([string]$Config.audit_root))) { throw 'Audit check report is outside audit_root.' }
            Assert-POSafePath -Path $reportPath -File
            Assert-POIntegrationHash -Hash ([string]$check.report_sha256) -Label 'audit check report'
            if ((Get-POStableSha256 -Path $reportPath) -ne [string]$check.report_sha256) { throw 'Audit check report changed.' }
            $allowed[$reportPath.ToLowerInvariant()] = $true
        }
    }
    $scan = Get-POSourceEntries -Root ([string]$Config.audit_root)
    if ($scan.Errors.Count -gt 0) { throw 'Cannot inventory existing audit contents safely.' }
    foreach ($entry in @($scan.Entries)) {
        Assert-POSafePath -Path ([string]$entry.full_path) -File:([string]$entry.entry_type -eq 'file')
        if ([string]$entry.entry_type -eq 'file') {
            if (-not $allowed.ContainsKey(([string]$entry.full_path).ToLowerInvariant())) { throw "Audit root contains unrecognized existing content: $($entry.full_path)" }
        }
        elseif (@($allowed.Keys | Where-Object { Test-POPathWithin -Path $_ -Parent ([string]$entry.full_path) }).Count -eq 0) {
            throw "Audit root contains an unrecognized directory: $($entry.full_path)"
        }
    }
}

function ConvertTo-POIntegrationRelativePath {
    param([Parameter(Mandatory = $true)][string]$Path)
    if ([IO.Path]::IsPathRooted($Path) -or $Path -match '[:*?"<>|]' -or $Path -match '(^|[\\/])\.\.?([\\/]|$)') {
        throw "Invalid integration relative path: $Path"
    }
    $relative = ConvertTo-PORelativePath $Path
    if (-not $relative) { throw 'Integration file path cannot be empty.' }
    foreach ($part in $relative.Split('/')) {
        if ($part.EndsWith('.') -or $part.EndsWith(' ') -or $part -match '^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(\.|$)') {
            throw "Ambiguous integration path component: $part"
        }
    }
    if (Test-POGitMetadataPath -RelativePath $relative) { throw 'Integration cannot rewrite Git metadata.' }
    return $relative
}

function Assert-POIntegrationHash {
    param([string]$Hash,[string]$Label)
    if ($Hash -notmatch '^[0-9A-Fa-f]{64}$') { throw "Invalid SHA256 for $Label" }
}

function Read-POIntegrationManifest {
    param([Parameter(Mandatory = $true)]$Config)
    if ($null -eq $Config.PSObject.Properties['integration_manifest'] -or -not $Config.integration_manifest) { return $null }
    if ([string]$Config.schema_version -ne '1.1' -or [string]$Config.mode -ne 'merge' -or
        [string]$Config.layout_decisions.version_policy -ne 'integrate') { throw 'Integration requires merge config 1.1 and version_policy integrate.' }
    Assert-POAuditPath -Config $Config
    $manifestPath = Resolve-POFullPath -Path ([string]$Config.integration_manifest)
    if (-not (Test-POPathWithin -Path $manifestPath -Parent ([string]$Config.audit_root))) { throw 'Manifest must belong to audit_root.' }
    Assert-POSafePath -Path $manifestPath -File
    $manifestHash = Get-POStableSha256 -Path $manifestPath
    $manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ([string]$manifest.schema_version -ne '1.0' -or @($manifest.groups).Count -eq 0) { throw 'Invalid or empty integration manifest.' }
    $groups = New-Object Collections.Generic.List[object]
    $inputMap = @{}; $outputMap = @{}; $ids = @{}; $bound = @{}
    $bound[$manifestPath] = $manifestHash
    foreach ($group in @($manifest.groups)) {
        $id = [string]$group.id
        if ($id -notmatch '^[A-Za-z0-9._-]+$' -or $ids.ContainsKey($id)) { throw "Invalid or duplicate integration group: $id" }
        $ids[$id] = $true
        if (@($group.inputs).Count -eq 0 -or @($group.outputs).Count -eq 0 -or @($group.required_checks).Count -eq 0) {
            throw "Integration group requires inputs, outputs and checks: $id"
        }
        $checkIds = @{}
        foreach ($checkIdValue in @($group.required_checks)) {
            $checkId = [string]$checkIdValue
            if ($checkId -notmatch '^[A-Za-z0-9._-]+$' -or $checkIds.ContainsKey($checkId)) { throw "Invalid or duplicate required check: $id/$checkId" }
            $checkIds[$checkId] = $true
        }
        $inputs = New-Object Collections.Generic.List[object]
        foreach ($inputItem in @($group.inputs)) {
            $sourceId = [string]$inputItem.source_id
            $relative = ConvertTo-POIntegrationRelativePath -Path ([string]$inputItem.relative_path)
            $inputHash = ([string]$inputItem.sha256).ToUpperInvariant()
            Assert-POIntegrationHash -Hash $inputHash -Label "$id input"
            if ($sourceId -eq '__target__') { $sourceRoot = [string]$Config.target_root }
            else {
                $sources = @($Config.sources | Where-Object { [string]$_.id -eq $sourceId })
                if ($sources.Count -ne 1) { throw "Unknown integration source: $sourceId" }
                $sourceRoot = [string]$sources[0].path
            }
            $sourcePath = Join-POPath -Root $sourceRoot -RelativePath $relative
            Assert-POSafePath -Path $sourcePath
            if (Test-POPathWithin -Path $sourcePath -Parent ([string]$Config.audit_root) -AllowEqual) { throw 'Integration input overlaps audit_root.' }
            $key = $sourcePath.ToLowerInvariant()
            if ($inputMap.ContainsKey($key)) { throw "Integration input is used more than once: $sourcePath" }
            $recovery = Resolve-POFullPath -Path ([string]$inputItem.recovery_path)
            if (-not (Test-POPathWithin -Path $recovery -Parent ([string]$Config.audit_root))) { throw 'Recovery copy must belong to audit_root.' }
            Assert-POSafePath -Path $recovery -File
            if ((Get-POStableSha256 -Path $recovery) -ne $inputHash) { throw "Recovery copy differs from input: $sourcePath" }
            if ($bound.ContainsKey($recovery) -and $bound[$recovery] -ne $inputHash) { throw 'Conflicting bound hashes.' }
            $bound[$recovery] = $inputHash
            $inputNormalized = [pscustomobject][ordered]@{group_id=$id;source_id=$sourceId;relative_path=$relative;source_path=$sourcePath;sha256=$inputHash;recovery_path=$recovery}
            $inputs.Add($inputNormalized); $inputMap[$key] = $inputNormalized
        }
        $outputs = New-Object Collections.Generic.List[object]
        foreach ($outputItem in @($group.outputs)) {
            $relative = ConvertTo-POIntegrationRelativePath -Path ([string]$outputItem.relative_path)
            $target = Join-POPath -Root ([string]$Config.target_root) -RelativePath $relative
            Assert-POSafePath -Path $target
            if ((Test-POPathWithin -Path $target -Parent ([string]$Config.audit_root) -AllowEqual) -or
                (Test-POPathWithin -Path ([string]$Config.audit_root) -Parent $target -AllowEqual)) { throw 'Integration output overlaps audit_root.' }
            $key = $target.ToLowerInvariant()
            if ($outputMap.ContainsKey($key)) { throw "Multiple integration writers for target: $target" }
            foreach ($other in $outputMap.Values) {
                if ((Test-POPathWithin -Path $target -Parent $other.target_path) -or (Test-POPathWithin -Path $other.target_path -Parent $target)) {
                    throw 'Integration outputs have file/ancestor conflicts.'
                }
            }
            $outputHash = ([string]$outputItem.sha256).ToUpperInvariant()
            Assert-POIntegrationHash -Hash $outputHash -Label "$id output"
            $expected = [string]$outputItem.expected_target_sha256
            if ($expected -ne 'absent') { Assert-POIntegrationHash -Hash $expected -Label "$id expected target"; $expected = $expected.ToUpperInvariant() }
            $prepared = Resolve-POFullPath -Path ([string]$outputItem.prepared_path)
            if (-not (Test-POPathWithin -Path $prepared -Parent ([string]$Config.audit_root))) { throw 'Prepared output must belong to audit_root.' }
            Assert-POSafePath -Path $prepared -File
            if ((Get-POStableSha256 -Path $prepared) -ne $outputHash) { throw "Prepared output changed: $prepared" }
            if ($bound.ContainsKey($prepared) -and $bound[$prepared] -ne $outputHash) { throw 'Conflicting bound hashes.' }
            $bound[$prepared] = $outputHash
            $recovery = ''
            if ($expected -ne 'absent') {
                $oldTarget = @($inputs.ToArray() | Where-Object { $_.source_id -eq '__target__' -and $_.source_path -eq $target })
                if ($oldTarget.Count -ne 1 -or $oldTarget[0].sha256 -ne $expected) { throw "Existing target needs matching protected input: $target" }
                $recovery = [string]$oldTarget[0].recovery_path
            }
            $outputNormalized = [pscustomobject][ordered]@{group_id=$id;relative_path=$relative;target_path=$target;prepared_path=$prepared;sha256=$outputHash;expected_target_sha256=$expected;recovery_path=$recovery}
            $outputs.Add($outputNormalized); $outputMap[$key] = $outputNormalized
        }
        foreach ($inputNormalized in @($inputs.ToArray() | Where-Object { $_.source_id -eq '__target__' })) {
            if (@($outputs.ToArray() | Where-Object { $_.target_path -eq $inputNormalized.source_path -and $_.expected_target_sha256 -eq $inputNormalized.sha256 }).Count -ne 1) {
                throw 'Existing target input must have an output at the same path.'
            }
        }
        $coveragePath = Resolve-POFullPath -Path ([string]$group.coverage.path)
        $coverageHash = ([string]$group.coverage.sha256).ToUpperInvariant()
        Assert-POIntegrationHash -Hash $coverageHash -Label "$id coverage"
        if (-not (Test-POPathWithin -Path $coveragePath -Parent ([string]$Config.audit_root))) { throw 'Coverage report must belong to audit_root.' }
        Assert-POSafePath -Path $coveragePath -File
        if ((Get-Item -LiteralPath $coveragePath).Length -eq 0 -or (Get-POStableSha256 -Path $coveragePath) -ne $coverageHash) { throw 'Coverage report missing, empty or changed.' }
        $covered = @{}
        foreach ($coverageItem in @($group.coverage.inputs)) {
            $coverageKey = ([string]$coverageItem.source_id) + '|' + (ConvertTo-POIntegrationRelativePath ([string]$coverageItem.relative_path))
            if ($covered.ContainsKey($coverageKey) -or [string]::IsNullOrWhiteSpace([string]$coverageItem.reason)) { throw 'Duplicate or unexplained coverage input.' }
            if (@($inputs.ToArray() | Where-Object { ($_.source_id + '|' + $_.relative_path) -eq $coverageKey }).Count -ne 1) { throw 'Coverage names an unknown input.' }
            if (@($coverageItem.destination_paths).Count -eq 0) { throw 'Coverage requires an output destination.' }
            foreach ($destination in @($coverageItem.destination_paths)) {
                $destinationRelative = ConvertTo-POIntegrationRelativePath ([string]$destination)
                if (@($outputs.ToArray() | Where-Object { $_.relative_path -eq $destinationRelative }).Count -ne 1) { throw 'Coverage destination is not a group output.' }
            }
            $covered[$coverageKey] = $true
        }
        if ($covered.Count -ne $inputs.Count) { throw "Coverage omits an input: $id" }
        if ($bound.ContainsKey($coveragePath) -and $bound[$coveragePath] -ne $coverageHash) { throw 'Conflicting bound hashes.' }
        $bound[$coveragePath] = $coverageHash
        $groups.Add([pscustomobject][ordered]@{id=$id;inputs=@($inputs.ToArray());outputs=@($outputs.ToArray());coverage=$group.coverage;required_checks=@($group.required_checks)})
    }
    if ((Get-POStableSha256 -Path $manifestPath) -ne $manifestHash) { throw 'Integration manifest changed while being read.' }
    return [pscustomobject][ordered]@{SchemaVersion='1.0';ManifestPath=$manifestPath;ManifestSha256=$manifestHash;Groups=@($groups.ToArray());InputByPath=$inputMap;OutputByPath=$outputMap;BoundPaths=@($bound.Keys | Sort-Object);BoundHashes=$bound;AuditRoot=[string]$Config.audit_root}
}

function Assert-POIntegrationFiles {
    param([Parameter(Mandatory = $true)]$Integration,
        [ValidateSet('Preflight','Installed','Retired')][string]$Phase='Preflight',
        [switch]$RequireChecks,[string]$OutputDir,[string[]]$InstalledPaths=@())
    $checkBound = @{}
    $installed = @{}
    foreach ($path in $InstalledPaths) {
        $key = (Resolve-POFullPath -Path $path -AllowMissing).ToLowerInvariant()
        if (-not $Integration.OutputByPath.ContainsKey($key)) { throw 'Resume path is not an integration output.' }
        $installed[$key] = $true
    }
    foreach ($path in @($Integration.BoundPaths)) {
        Assert-POSafePath -Path $path -File
        if ((Get-POStableSha256 -Path $path) -ne [string]$Integration.BoundHashes[$path]) { throw "Integration bound file changed: $path" }
    }
    foreach ($group in @($Integration.Groups)) {
        foreach ($inputItem in @($group.inputs)) {
            if ($Phase -eq 'Retired' -or ($Phase -eq 'Installed' -and $inputItem.source_id -eq '__target__')) { continue }
            Assert-POSafePath -Path $inputItem.source_path -File
            $actual = Get-POStableSha256 -Path $inputItem.source_path
            $key = $inputItem.source_path.ToLowerInvariant()
            if ($Phase -eq 'Preflight' -and $inputItem.source_id -eq '__target__' -and $installed.ContainsKey($key) -and
                $actual -eq $Integration.OutputByPath[$key].sha256) { continue }
            if ($actual -ne $inputItem.sha256) { throw "Integration input changed: $($inputItem.source_path)" }
        }
        foreach ($outputItem in @($group.outputs)) {
            Assert-POSafePath -Path $outputItem.target_path
            if ($Phase -eq 'Preflight' -and $installed.ContainsKey($outputItem.target_path.ToLowerInvariant()) -and
                [IO.File]::Exists((ConvertTo-POExtendedPath $outputItem.target_path)) -and
                (Get-POStableSha256 -Path $outputItem.target_path) -eq $outputItem.sha256) { continue }
            if ($Phase -eq 'Preflight' -and $outputItem.expected_target_sha256 -eq 'absent') {
                if (Test-Path -LiteralPath $outputItem.target_path) { throw "Unexpected integration target: $($outputItem.target_path)" }
            }
            else {
                $expected = if ($Phase -eq 'Preflight') { $outputItem.expected_target_sha256 } else { $outputItem.sha256 }
                Assert-POSafePath -Path $outputItem.target_path -File
                if ((Get-POStableSha256 -Path $outputItem.target_path) -ne $expected) { throw "Integration target changed: $($outputItem.target_path)" }
            }
        }
    }
    if ($RequireChecks) {
        if ($Phase -eq 'Preflight') { throw 'Post-installation checks cannot satisfy preflight.' }
        if (-not $OutputDir -or -not (Test-POPathWithin -Path $OutputDir -Parent $Integration.AuditRoot -AllowEqual)) { throw 'Checks OutputDir must belong to audit_root.' }
        $receiptPath = Join-Path $OutputDir 'integration-checks.json'
        Assert-POSafePath -Path $receiptPath -File
        $receiptHash = Get-POStableSha256 -Path $receiptPath
        $receipt = Get-Content -LiteralPath $receiptPath -Raw -Encoding UTF8 | ConvertFrom-Json
        if ([string]$receipt.schema_version -ne '1.0' -or [string]$receipt.manifest_sha256 -ne $Integration.ManifestSha256) { throw 'Integration check receipt belongs to another manifest.' }
        foreach ($group in @($Integration.Groups)) {
            foreach ($id in @($group.required_checks)) {
                $checks = @($receipt.checks | Where-Object { [string]$_.group_id -eq $group.id -and [string]$_.id -eq $id })
                if ($checks.Count -ne 1 -or [string]$checks[0].status -ne 'passed') { throw "Required check not passed: $($group.id)/$id" }
                $check = $checks[0]; $checkedAt = [DateTimeOffset]::MinValue
                if (-not [DateTimeOffset]::TryParse([string]$check.checked_at,[ref]$checkedAt)) { throw 'Check timestamp is missing or invalid.' }
                if (@($check.outputs).Count -ne @($group.outputs).Count) { throw 'Check receipt must cover every group output.' }
                foreach ($outputItem in @($group.outputs)) {
                    $checkedOutput = @($check.outputs | Where-Object { [string]$_.relative_path -eq $outputItem.relative_path -and [string]$_.sha256 -eq $outputItem.sha256 })
                    if ($checkedOutput.Count -ne 1) { throw 'Check receipt output hash is outdated or missing.' }
                }
                $reportPath = Resolve-POFullPath -Path ([string]$check.report_path)
                if (-not (Test-POPathWithin -Path $reportPath -Parent $Integration.AuditRoot)) { throw 'Check report must belong to audit_root.' }
                Assert-POSafePath -Path $reportPath -File
                $reportHash = ([string]$check.report_sha256).ToUpperInvariant()
                Assert-POIntegrationHash -Hash $reportHash -Label 'check report'
                if ((Get-Item -LiteralPath $reportPath).Length -eq 0 -or (Get-POStableSha256 -Path $reportPath) -ne $reportHash) { throw 'Check report missing, empty or changed.' }
                $checkBound[$reportPath] = $reportHash
            }
        }
        if ((Get-POStableSha256 -Path $receiptPath) -ne $receiptHash) { throw 'Check receipt changed while reading.' }
        $checkBound[$receiptPath] = $receiptHash
    }
    if ($RequireChecks) { return [pscustomobject]@{Valid=$true;BoundPaths=@($checkBound.Keys | Sort-Object);BoundHashes=$checkBound} }
}

function Install-POIntegrationOutput {
    param([Parameter(Mandatory = $true)]$Output,[switch]$Resume)
    Assert-POSafePath -Path ([string]$Output.prepared_path) -File
    if ((Get-POStableSha256 -Path $Output.prepared_path) -ne $Output.sha256) { throw 'Prepared integration output changed.' }
    $target = Resolve-POFullPath -Path ([string]$Output.target_path) -AllowMissing
    Assert-POSafePath -Path $target
    if ($Output.expected_target_sha256 -ne 'absent') {
        Assert-POSafePath -Path ([string]$Output.recovery_path) -File
        if ((Get-POStableSha256 -Path $Output.recovery_path) -ne $Output.expected_target_sha256) { throw 'Target recovery copy changed.' }
    }
    if ($Resume -and [IO.File]::Exists((ConvertTo-POExtendedPath $target)) -and (Get-POStableSha256 -Path $target) -eq $Output.sha256) { return $target }
    if ($Output.expected_target_sha256 -eq 'absent') {
        return Copy-POFileAtomicVerified -Source $Output.prepared_path -Target $target -ExpectedSha256 $Output.sha256
    }
    Assert-POSafePath -Path $target -File
    if ((Get-POStableSha256 -Path $target) -ne $Output.expected_target_sha256) { throw 'Existing target changed before integration.' }
    $temporary = $target + '.po-partial-' + [Guid]::NewGuid().ToString('N')
    $rollback = $target + '.po-replaced-' + [Guid]::NewGuid().ToString('N')
    try {
        [void](Copy-POFileAtomicVerified -Source $Output.prepared_path -Target $temporary -ExpectedSha256 $Output.sha256)
        Assert-POSafePath -Path $target -File
        if ((Get-POStableSha256 -Path $target) -ne $Output.expected_target_sha256) { throw 'Existing target changed before replacement.' }
        [IO.File]::Replace((ConvertTo-POExtendedPath $temporary),(ConvertTo-POExtendedPath $target),(ConvertTo-POExtendedPath $rollback))
        if ((Get-POStableSha256 -Path $rollback) -ne $Output.expected_target_sha256) {
            if ((Get-POStableSha256 -Path $target) -eq $Output.sha256) {
                $displaced = $target + '.po-displaced-' + [Guid]::NewGuid().ToString('N')
                [IO.File]::Replace((ConvertTo-POExtendedPath $rollback),(ConvertTo-POExtendedPath $target),(ConvertTo-POExtendedPath $displaced))
                # Retain the displaced copy for diagnosis; do not delete a concurrent writer's content.
            }
            throw "Concurrent target change detected; recovery artifacts retained near $target"
        }
        if ((Get-POStableSha256 -Path $target) -ne $Output.sha256) { throw 'Installed integration target changed; captured original retained.' }
        [IO.File]::Delete((ConvertTo-POExtendedPath $rollback))
    }
    finally {
        if ([IO.File]::Exists((ConvertTo-POExtendedPath $temporary))) { [IO.File]::Delete((ConvertTo-POExtendedPath $temporary)) }
    }
    return $target
}

function Invoke-POGit {
    param(
        [Parameter(Mandatory = $true)][string]$Repository,
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [switch]$AllowFailure
    )
    $oldPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $output = @(& git --no-optional-locks -C $Repository @Arguments 2>&1)
        $code = $LASTEXITCODE
    }
    finally { $ErrorActionPreference = $oldPreference }
    if ($code -ne 0 -and -not $AllowFailure) { throw "git failed ($code): git -C $Repository $($Arguments -join ' ')`n$($output -join "`n")" }
    return [pscustomobject]@{ ExitCode=$code; Output=$output }
}

function Get-POGitState {
    param([Parameter(Mandatory = $true)][string]$Repository)
    $probe = Invoke-POGit -Repository $Repository -Arguments @('rev-parse','--is-inside-work-tree') -AllowFailure
    if ($probe.ExitCode -ne 0 -or ($probe.Output -join '').Trim() -ne 'true') { return $null }
    $head = Invoke-POGit -Repository $Repository -Arguments @('rev-parse','HEAD') -AllowFailure
    $branch = Invoke-POGit -Repository $Repository -Arguments @('symbolic-ref','--short','-q','HEAD') -AllowFailure
    $gitDir = Invoke-POGit -Repository $Repository -Arguments @('rev-parse','--absolute-git-dir')
    $refs = Invoke-POGit -Repository $Repository -Arguments @('for-each-ref','--format=%(refname)%09%(objectname)')
    $reflog = Invoke-POGit -Repository $Repository -Arguments @('reflog','--all','--format=%H') -AllowFailure
    $status = Invoke-POGit -Repository $Repository -Arguments @('status','--porcelain=v2','--branch','--untracked-files=all')
    $remotes = Invoke-POGit -Repository $Repository -Arguments @('remote','-v') -AllowFailure
    $statusLines = @($status.Output | ForEach-Object { [string]$_ })
    return [pscustomobject][ordered]@{
        repository=$Repository
        git_dir=($gitDir.Output -join "`n").Trim()
        head=if ($head.ExitCode -eq 0) { ($head.Output -join '').Trim() } else { '' }
        branch=if ($branch.ExitCode -eq 0) { ($branch.Output -join '').Trim() } else { '' }
        refs=@($refs.Output | ForEach-Object { [string]$_ } | Sort-Object)
        reflog_commits=@($reflog.Output | ForEach-Object { ([string]$_).Trim() } | Where-Object { $_ -match '^[0-9a-fA-F]{40,64}$' } | Sort-Object -Unique)
        remotes=@($remotes.Output | ForEach-Object { [string]$_ } | Sort-Object)
        status=$statusLines
        dirty=@($statusLines | Where-Object { $_ -notmatch '^#' }).Count -gt 0
        staged=@($statusLines | Where-Object { $_ -match '^1 [^. ]' -or $_ -match '^2 [^. ]' }).Count
        untracked=@($statusLines | Where-Object { $_ -like '? *' }).Count
    }
}

function New-POHashManifest {
    param(
        [Parameter(Mandatory = $true)][string[]]$Paths,
        [Parameter(Mandatory = $true)][string]$OutputPath
    )
    $base = Split-Path -Parent $OutputPath
    $lines = New-Object Collections.Generic.List[string]
    foreach ($path in @($Paths | Sort-Object { $_.ToLowerInvariant() }, { $_ })) {
        $full = Resolve-POFullPath -Path $path -AllowNetwork
        $hash = Get-POStableSha256 -Path $full
        $relative = if ($base -and (Test-POPathWithin -Path $full -Parent $base -AllowEqual)) { Get-PORelativePath -Root $base -Path $full } else { $full }
        $lines.Add("$hash  $($relative.Replace('\','/'))")
    }
    Write-POText -Path $OutputPath -Text (($lines.ToArray() -join "`n") + "`n")
    return Get-POStableSha256 -Path $OutputPath
}

function Get-PODriveFreeSpace {
    param([Parameter(Mandatory = $true)][string]$Path)
    $full = Resolve-POFullPath -Path $Path -AllowMissing
    $root = [IO.Path]::GetPathRoot($full)
    $drive = New-Object IO.DriveInfo($root)
    return [int64]$drive.AvailableFreeSpace
}

Export-ModuleMember -Function @(
    'ConvertTo-POExtendedPath','ConvertFrom-POExtendedPath','Resolve-POFullPath','Test-POPathWithin',
    'ConvertTo-PORelativePath','Get-PORelativePath','Join-POPath','Write-POText','Write-POJson','Read-POJsonArray','Get-POStableId','Write-POCsv',
    'Add-POJsonLine','Get-POStableSha256','Get-POReparseInfo','Get-POSourceEntries','Test-POGitMetadataPath',
    'Test-POExcludedPath','Get-POProposedRelativePath','Read-POConfig','Invoke-POGit','Get-POGitState',
    'New-POHashManifest','Get-PODriveFreeSpace','Get-POFileSnapshot','Get-POPathVolume','Test-POSameVolume',
    'Test-POSyncPath','Test-POHashManifest','Assert-POExpectedFile','Copy-POFileAtomicVerified',
    'Move-POFileVerified','Copy-PODirectoryVerified','Assert-POSafePath','Assert-POAuditPath',
    'Read-POIntegrationManifest','Assert-POIntegrationFiles','Install-POIntegrationOutput','Assert-POAuditContents'
)
