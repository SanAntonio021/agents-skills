---
name: windows-storage-cleanup
description: >
  Safely inspect and reclaim Windows disk space using WizTree or native tools, with risk classification,
  active-process protection, duplicate and backup verification, Recycle Bin staging, and post-cleanup checks.
  Use whenever the user says a Windows drive is full, asks what can be deleted, wants C/D drive cleanup,
  mentions WizTree or large files, asks whether local/cloud duplicates are safe to remove, or needs pagefile
  space advice. Trigger even when the user only asks to review candidates before deleting anything.
---

# Windows Storage Cleanup

Treat cleanup as an evidence and approval workflow. Free-space targets are soft goals; never delete valuable
data merely to reach a number.

## Operating Contract

1. Inspect local rules, current disk state, active processes, and available audit artifacts before proposing actions.
2. Ask one question at a time until the protection boundaries and desired outcome are clear. Skip further questions
   only when the user explicitly says to proceed directly.
3. Start read-only. Do not delete, move, uninstall, stop services, or change system settings during discovery.
4. Protect active work, source code, user history, original experiment data, and unique project archives by default.
5. Group confirmation items by the same source and purpose. State size, reason, risk, and recovery method.
6. Execute only approved groups. Low-risk automatic handling is allowed only when the user explicitly delegates it.
7. Prefer official cleanup or uninstall mechanisms for system and application data. Move approved personal files to
   the Recycle Bin instead of permanently deleting them.
8. Stop broad cleanup when the user says the result is sufficient. Do not continue with small files after that point.

## Workflow

### 1. Establish Scope

Confirm the drives, urgency, protected roots, active applications, and whether the user wants review only or actual
cleanup. Separate the immediate goal from an aspirational free-space target.

Resolve the user's actual research roots from local rules and the current filesystem. Treat paths such as these as
protected until explicitly reviewed:

- `<research-root>\Paper`
- experiment or raw-data paths under `<research-root>\Program` and `<research-root>\ProgramFile`
- active VS Code, Claude, Office, Docker, browser, and research-tool data

### 2. Collect Evidence

Capture current capacity and free space first. Prefer WizTree when available for hotspot discovery, then use narrow
native queries to investigate specific candidates.

When exporting from WizTree:

- Record WizTree version, scan time, drive, and export path.
- Treat process exit code as advisory. A successful-looking exit code is not proof, and WizTree 4.31 has returned
  exit code `1` even when an export succeeded.
- Verify that the CSV exists, is non-empty, has the expected header, and parses before using it.
- Avoid unrestricted recursive searches that create huge output. Start from the largest folders and narrow down.

Read [references/windows-and-wiztree.md](references/windows-and-wiztree.md) for scan, official cleanup, Recycle Bin,
and pagefile rules.

### 3. Classify Candidates

Assign every candidate to one of four classes before acting:

- `official-cleanup-only`: Windows components, installers, drivers, package stores, pagefiles, and virtual disks.
- `low-risk-after-preapproval`: reproducible caches, completed crash dumps, and small uninstall remnants.
- `confirm-as-a-group`: installers, old application versions, media, downloads, chat attachments, and duplicates.
- `protected`: original experiment data, source repositories, unique archives, active application data, and history.

Use [references/risk-classification.md](references/risk-classification.md) for boundaries and examples.

### 4. Verify Duplicates and Backups

Do not treat matching names or sizes as duplicate proof. For a deletion candidate:

1. Inspect the file type or archive contents.
2. Locate the intended retained copy or cloud record.
3. Compare size and SHA-256; for archives or folder copies, verify every required member.
4. Confirm the retained copy is readable and belongs to the expected project/version.
5. Confirm cloud behavior: backup, synchronization, and local placeholder are different semantics.
6. Preserve a local working copy when the cloud copy is the only other copy or restoration has not been tested.

Read [references/backup-verification.md](references/backup-verification.md) when personal or research files are involved.

### 5. Present the Review List

Use this compact table:

| Group | Path or source | Size | Evidence | Risk | Proposed action |
| --- | --- | ---: | --- | --- | --- |
| `<purpose>` | `<path>` | `<size>` | `<why it is safe or uncertain>` | low/medium/high | keep/recycle/official cleanup |

Ask for one decision at a time when risk is medium or high. After the user delegates low-risk actions, execute only
items whose retained copy and recovery path are already verified.

### 6. Execute Safely

Immediately before each action:

- Recheck path, type, size, modification time, hash when relevant, and whether the item still exists.
- Resolve the absolute path and verify it remains under the approved root.
- Check whether a related application or service is active.
- Refuse path traversal, reparse-point surprises, changed hashes, missing retained copies, or changed file counts.

For personal files, use Windows Recycle Bin APIs. Do not implement permanent deletion unless the user explicitly
requests it and the governing rules allow it. Do not empty the entire Recycle Bin without separate approval.

For applications, run the registered uninstaller first, verify uninstall records, then recycle only residual files.
For Windows components, use Settings Storage recommendations, Disk Cleanup, or documented DISM commands.

Write an action manifest containing original path, action, bytes, evidence, retained copy, hash when used, timestamp,
result, and recovery method.

### 7. Verify Outcome

After each approved batch:

- Confirm moved items appear in the Recycle Bin or official cleanup completed successfully.
- Recheck free space. Recycle Bin moves do not reclaim physical space until the bin is emptied.
- Report expected versus realized space and any skipped items.
- Keep failures isolated; do not broaden cleanup to compensate for a failed target.

## Pagefile Questions

Treat pagefile sizing as system configuration, not file deletion.

1. Read live `Win32_PageFileSetting`, `Win32_PageFileUsage`, `AutomaticManagedPagefile`, RAM, commit behavior,
   `CrashDumpEnabled`, and free space.
2. Separate minimum crash-dump requirements from conservative operating headroom.
3. Do not claim a C-drive pagefile improves startup performance. Relevant reasons are crash-dump support and commit
   limit behavior.
4. Give one internally consistent recommendation and label machine-specific numbers as such.
5. Never delete `pagefile.sys` directly. Apply supported settings and say clearly when a full Windows reboot is needed.

## Safety Stop Conditions

Stop and ask the user when:

- the candidate may be original data, source code, history, or the only local project copy;
- backup evidence is only a matching filename or cloud listing;
- an application is active or a file is locked;
- a system path, pagefile, VHDX, package store, or driver directory is involved;
- the candidate changed after review;
- the action would become permanent rather than recoverable.

## Expected Final Report

Report:

- space before and after, with timestamp;
- actions completed and bytes affected;
- items skipped and the reason;
- Recycle Bin state and whether space is already reclaimed;
- backup/hash evidence for personal or project data;
- any restart or user action still required.
