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
