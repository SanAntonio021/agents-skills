# Windows and WizTree Operations

## Read-Only Capacity Snapshot

Use CIM for stable byte counts:

```powershell
Get-CimInstance Win32_LogicalDisk -Filter "DeviceID='C:' OR DeviceID='D:'" |
    Select-Object DeviceID, Size, FreeSpace
```

Record the timestamp. Capacity changes while applications are running.

## WizTree Export Validation

WizTree CLI details can vary by version and license. Discover the local CLI syntax rather than assuming it. After an
export, validate the artifact itself:

1. Wait for the WizTree process to finish or the export file to become stable.
2. Verify the file exists and has nonzero length.
3. Read the generated-version line and CSV header.
4. Parse a small sample before processing the full export.
5. Keep scan time and drive in the audit record.

Do not trust `$LASTEXITCODE` alone. WizTree 4.31 has produced a valid CSV while returning exit code `1` on this
machine.

For large exports, use `../scripts/Summarize-WizTreeCsv.ps1` instead of loading the complete file with `Import-Csv`
or printing every match. The helper validates the banner and required columns, streams the rows with a structured CSV
parser, selects only direct children of explicitly supplied roots, and caps each root at `-Top` results. Directory rows
already contain WizTree's aggregate size, so descendants below a selected direct child must not be added again.

## Windows Cleanup Order

Prefer supported mechanisms:

1. Settings > System > Storage > Cleanup recommendations or Temporary files.
2. Application cache controls or registered uninstallers.
3. Disk Cleanup where applicable.
4. Documented DISM component cleanup for Windows component-store maintenance.

Official references:

- [Free up drive space in Windows](https://support.microsoft.com/en-us/windows/free-up-drive-space-in-windows-85529ccb-c365-490d-b548-831022bc9b32)
- [Clean up the WinSxS folder](https://learn.microsoft.com/en-us/windows-hardware/manufacture/desktop/clean-up-the-winsxs-folder)
- [Determine the appropriate page file size](https://learn.microsoft.com/en-us/troubleshoot/windows-client/performance/how-to-determine-the-appropriate-page-file-size-for-64-bit-versions-of-windows)
- [Windows memory dump file options](https://learn.microsoft.com/en-us/troubleshoot/windows-server/performance/memory-dump-file-options)

## Recycle Bin Staging

For approved personal files, use the Windows shell-backed Recycle Bin instead of `Remove-Item`. One PowerShell
option is `Microsoft.VisualBasic.FileIO.FileSystem` with `RecycleOption.SendToRecycleBin`.

Before moving anything:

- resolve and validate the absolute target path;
- reject reparse points unless explicitly understood;
- recheck expected size/hash;
- record the retained copy and recovery method;
- handle each approved item independently so one failure does not broaden the action.

Emptying the Recycle Bin is a separate, potentially broad action. Obtain separate approval or leave it to the user.

### Reporting One Drive's Recycle Bin State

When a cleanup or report is scoped to one drive, resolve that drive's `$Recycle.Bin\<SID>` directory and inventory its
`$I` metadata and `$R` payload pairs. Exclude `desktop.ini` and other non-entry control files, count one `$I`/`$R` pair
as one logical item, and calculate occupied bytes from the matching payload.

`Shell.Application.Namespace(10).Items()` is a combined view across drives. It can support a clearly labeled global
inventory, but its item count must never be used to claim that a particular drive's Recycle Bin is empty or nonempty.
If an entry resolves to another drive, exclude it from the target-drive status instead of treating it as an unrelated
entry on the target drive.

### Permanently Removing One Staged Candidate

Approval to stage an item in the Recycle Bin does not approve permanent deletion. When the user later approves only
one staged candidate, preserve every unrelated Recycle Bin entry:

1. Resolve the candidate's drive-specific `$Recycle.Bin\<SID>` directory and enumerate its metadata without changing
   it.
2. Identify one exact `$I` metadata record whose decoded original path and original byte count match the approved
   path. Use deletion time to disambiguate repeated entries for the same original path.
3. Pair it only with the `$R` payload that has the identical suffix. For a directory, also verify the current payload
   file count and total bytes against the staged audit; for a file, verify the payload byte count.
4. Snapshot the names and sizes of unrelated Recycle Bin entries, then permanently delete only those two exact
   literal paths. Do not use wildcards, suffix-prefix matching, or `Clear-RecycleBin` for a single-candidate approval.
5. Verify that the original path and exact `$I`/`$R` pair are absent, unrelated entries are unchanged, and actual free
   space changed by a plausible amount. Record any partial deletion as a failure instead of broadening the cleanup.

If the metadata path, size, suffix pair, file count, or staged audit does not match exactly, stop. A request to empty
the entire Recycle Bin is a separate broad approval and must not be inferred from approval of one candidate.

## Pagefile Inspection

```powershell
$automatic = (Get-CimInstance Win32_ComputerSystem).AutomaticManagedPagefile
$settings = Get-CimInstance Win32_PageFileSetting |
    Select-Object Name, InitialSize, MaximumSize
$usage = Get-CimInstance Win32_PageFileUsage |
    Select-Object Name, AllocatedBaseSize, CurrentUsage, PeakUsage
```

Also inspect RAM, system commit behavior, crash-dump mode, and drive free space. A tiny boot-volume pagefile can meet
some dump requirements, but that minimum is not a universal performance recommendation. System-managed sizing on a
roomier drive is often the conservative choice; decide from live evidence.

Never remove `pagefile.sys` as a normal file. State whether a full Windows reboot is required for the new layout to
become active, then verify both settings and usage after reboot.
