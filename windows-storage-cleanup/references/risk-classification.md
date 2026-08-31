# Risk Classification

Classify by recoverability, reproducibility, ownership, and current use. File extension alone is not enough.

## Official Cleanup Only

Do not delete these paths or file types directly:

- `C:\Windows\WinSxS`
- `C:\Windows\Installer`
- Windows driver store and servicing directories
- `pagefile.sys`, `hiberfil.sys`, swap files, and crash-dump configuration
- Docker, WSL, Hyper-V, or application VHD/VHDX files
- WindowsApps and packaged-app internals

Use documented Windows cleanup, application settings, or the registered uninstaller.

## Low Risk After Preapproval

Candidates can be handled in a delegated batch only when reproducible and inactive:

- package-manager download caches such as npm, pip, Bun, or uv;
- stale installer download caches whose owning application documents them as disposable;
- completed crash dumps and diagnostic output no longer under investigation;
- residual files left after a verified official uninstall;
- clearly obsolete retained application versions when one working current version remains.

Cache directories can regenerate. Explain this before cleanup when recurrence matters to the user.

## Verified Uninstall Residuals

Treat a directory as an uninstall residual only after evidence shows that the owning application is gone and the
directory is not shared with another installed application. Check all applicable ownership surfaces:

1. Machine-wide and per-user uninstall registrations, including 32-bit and 64-bit registry views.
2. AppX/MSIX package registration and package-manager records.
3. Expected installation directories under Program Files, ProgramData, LocalAppData, and Roaming AppData.
4. Running processes, Windows services, drivers, startup entries, and scheduled tasks.
5. Start-menu and desktop shortcuts, protocol handlers, shell integration, and file associations.
6. Application recovery, autosave, templates, profiles, and user-created documents that may be stored beside program
   files.

The absence of an uninstall entry or active process is only one signal. A vendor directory remains protected when an
installed or running product from the same vendor still owns files inside it. Likewise, a shared runtime remains
protected when another installed application declares or contains a dependency on it, even if no runtime process is
currently active. Inspect application manifests, package metadata, configuration files such as
`*.runtimeconfig.json`, bundled launchers, and documented runtime requirements before recommending removal.

Examples of the decision boundary:

- A directory with no uninstall registration, package, process, program files, recovery material, or user documents
  can become a residual candidate after its contents and ownership are verified.
- A vendor directory containing files used by a currently running companion application is active application data,
  not an uninstall residual.
- An inactive shared runtime referenced by another application's runtime configuration is a dependency and must be
  kept. “No process is using it now” is not sufficient evidence.

Use the registered uninstaller when the application is still installed. Only the leftover directory enters the
recoverable Recycle Bin workflow after uninstall verification and explicit approval.

## Confirm as a Group

Group by source and purpose, then ask:

- installers, ISO images, and extracted installation media;
- old presentations, rendered videos, raw media, and project exports;
- chat attachments, downloads, and received archives;
- duplicate archives and duplicated project outputs;
- model weights, offline maps, speech models, and other optional assets;
- old application versions whose rollback value is uncertain.

## Protected by Default

- original experiment data and instrument captures;
- source repositories, uncommitted work, and environment definitions;
- unique project archives, PCB/CAD source, and editable Office originals;
- session history, research notes, and user-created recordings;
- active application data and locked files;
- the only local working copy, even when a cloud backup exists.

`Paper`, research paths under `Program`/`ProgramFile`, and active VS Code or Claude data remain protected unless
explicitly reviewed. Resolve their actual roots from local rules instead of hardcoding a private machine path.

## Decision Test

Before labeling a target low risk, answer all five questions:

1. Can the data be reproduced or restored?
2. Has the retained copy been verified beyond name and size?
3. Is the owning application inactive?
4. Is the action recoverable?
5. Does the user-approved group include this exact source and purpose?

Any uncertain answer raises the item to confirmation or protected status.
