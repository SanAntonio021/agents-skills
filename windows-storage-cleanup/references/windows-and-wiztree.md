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
