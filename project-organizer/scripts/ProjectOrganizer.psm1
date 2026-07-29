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
    param([Parameter(Mandatory = $true)][string]$Root)
    $scan = Get-POSourceEntries -Root $Root
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
    param([Parameter(Mandatory = $true)][string]$Root)
    $rootFull = Resolve-POFullPath -Path $Root -AllowNetwork
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
    if ([string]$config.schema_version -ne '1.0') { throw 'Unsupported schema_version.' }
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
    if((Test-POPathWithin -Path $config.audit_root -Parent $config.target_root -AllowEqual) -or
        (Test-POPathWithin -Path $config.target_root -Parent $config.audit_root -AllowEqual)){throw 'audit_root overlaps target_root.'}
    if ($ForExecution) {
        [void](Resolve-POFullPath -Path $config.target_root -AllowMissing)
        [void](Resolve-POFullPath -Path $config.audit_root -AllowMissing)
    }
    if ($RequireSources -and @($config.sources).Count -lt 2) { throw 'At least two confirmed sources are required.' }
    $ids = @{}
    $sourcePaths = New-Object Collections.Generic.List[string]
    foreach ($source in @($config.sources)) {
        $id = [string]$source.id
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
        if([string]$layout.version_policy -notin @('preserve_all','approved_selection')){throw 'Unsupported version_policy.'}
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
    return $config
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
    'Move-POFileVerified','Copy-PODirectoryVerified'
)
