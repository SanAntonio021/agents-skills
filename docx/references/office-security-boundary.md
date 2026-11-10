# Office Security Boundary

- LibreOffice headless operations run through `libreoffice-runner` with a unique `UserInstallation`. Direct launch of `soffice`, `soffice.exe`, or `soffice.com` is forbidden.
- Word COM operations must be covered by the current document request and use the existing guard to prove ownership and isolation. Use an exclusive task-owned instance and read-only input copy for native checks; the limited refresh exception is below. Permission flags do not replace these checks, and no fixed user phrase is required.
- An existing `WINWORD.EXE` blocks Word COM automation; existing WPS background, preview or automation processes are recorded but do not block activation. Do not connect to, close, save, or alter any existing Office instance. Continue safe file-level work unless a newly observed provider is proven to be task-owned and empty.
- For Word, the newly observed task-owned process must be `WINWORD.EXE`; its readable executable path, COM `Application.Path`-derived executable, and registered `WINWORD.EXE` path must agree. If the process path cannot be read or does not match, fail closed before opening the document.
- For a background-only fallback, `scripts/word_nativeom.py` runs its worker and Word on a private non-input desktop, never switching desktops. It connects through the documented `_WwG` document window and refuses the input desktop. Only a generated blank bootstrap opens before ownership checks; `Word.Window.Hwnd`, actual process path and COM path must agree. The shared gate then invokes the paired bootstrap preparation callback, releases that window reference, verifies that Documents is empty, and applies its usual hidden/macro-disabled settings before opening the isolated input. Never use an existing Word window or treat this fallback as proof that the system COM entry has been repaired.
- If WPS has hijacked `Word.Application`, the guarded `scripts/native_word_ui_refresh.py --allow-office-ui` route may launch the registered `WINWORD.EXE` directly. It must observe exactly the new Word PID, verify its executable path, operate on a disposable copy, close only that task-owned window normally, and leave all pre-existing WPS processes untouched. A missing Word PID or a path resolving to WPS is non-pass.
- Keep gate temporary files under `%TEMP%/codex-docx-gates` or `%TEMP%/office-mcp-trials`. Reject symbolic links and path traversal in gate-managed temporary workspaces.
- Protect source Markdown, templates and existing deliverables. Clean up only owned files and the current task's empty instance, proving exit before temporary-workspace cleanup.

## Activation and registry-view mismatch

Use this branch when the registered Word path and actual activation disagree, or activation still
fails after a registration repair. It is not a prerequisite for ordinary document work. Packaged
clients can present a virtualized registry view; check for a view difference rather than assuming
that every timeout is a WPS takeover or stale COM cache.

1. **Capture the mismatch read-only.** Record the caller's user identity, registry bitness, effective
   Word CLSID, `LocalServer32` values (including the default command and `ServerExecutable`), and
   any observed new process image/command line. For the same CLSID, distinguish the user override
   in `HKCU\Software\Classes`, the machine entry in `HKLM\Software\Classes`, and merged `HKCR`.
   A correct executable value, application caption or Word-like version alone is insufficient.
2. **Compare the real Windows user context.** Read the same keys and relevant 64/32-bit views through
   a verified system-side route under the same user. A temporary, demand-start-only Task Scheduler
   worker is one option: use least privilege for reads, run only the targeted registry snapshot,
   launch no Office application, and remove only that task after completion. Verify the worker's
   identity and script/version receipt so its result cannot be confused with an earlier run.
   A normal or elevated child of the client can inherit its registry view; administrator status or
   a missing package-identity result does not prove an independent view. If the system-side read is
   unavailable, retain that boundary and continue safe document work rather than claiming a cause.
3. **Locate the effective conflict.** Compare the two snapshots before repeating repair commands.
   A hidden user-level WPS override can combine its launch command with a machine-level Word
   executable. Different results establish a view mismatch; diagnose the particular active entry
   from the evidence. Do not unload/reset client hives or require a reboot on that evidence alone.
4. **Repair only within the existing authorization.** Document-edit permission alone does not grant
   system-configuration changes. When those changes are authorized, back up the actual affected
   entries and file-association choices, use the installed vendor's supported configuration route
   where available, and apply the change in the context where the conflict was observed. Preserve
   WPS, user windows and unrelated settings when that is the requested scope. Read back the real
   effective configuration and association choices; success inside the client alone is insufficient.
5. **Verify the standard entry in both contexts.** After repair, test ordinary `Word.Application`
   activation from a fresh client in the real Windows user context and from the task's client.
   Keep the existing ownership/isolation checks and background-only constraint: use a private
   non-input desktop, no user documents, only an empty owned instance or disposable bootstrap,
   and normal exit. Verify the actual Word executable, COM path, new PID, launch command and exit;
   retain current-desktop observations. A direct native-model fallback can complete document QA
   but does not prove standard activation is repaired. Report an unavailable or failed context as
   unverified; a 32-bit registry read does not establish a successful 32-bit activation test.

Keep targeted snapshots, repair backups and verification receipts in the task's existing process
directory. Do not copy client hives or unrelated registry contents into project or public skill files.

## Writable field-refresh copy

The [common reference finalizer](numbering-references.md) may evaluate and save fields only in its
isolated temporary copy, with the current operation's `--allow-office-com`. Reuse
`office_native_gate.py`'s `owned_application` and its ownership/cleanup protections; do not change
the native gate's read-only checker or reuse its read-only `_open_docx` for this write operation.
The refresh helper supplies its own `Documents.Open` with `ReadOnly=False`, `AddToRecentFiles=False`,
`Visible=False`, `ConfirmConversions=False`, `OpenAndRepair=False` and empty password arguments.

`owned_application` already forces `Visible=False`, `DisplayAlerts=0`, `ScreenUpdating=False` and
Word `AutomationSecurity=3`. Within that owned context, the refresh helper reads the prior values
of `Options.UpdateFieldsAtPrint`, `Options.UpdateLinksAtOpen` and
`Options.WarnBeforeSavingPrintingSendingMarkup`, disables them during the operation, then restores
them before leaving the context. Failure to read, set or restore any option must be reported as
non-pass, not silently ignored. Do not enable external-link updates or blanket `Fields.Update`.

The saved temporary package is only an evaluation source. Transplant field-scoped results into a
new protected output under the shared contract, never replace the deliverable with Word's broadly
rewritten temporary package. In the local two-stage chain, preserve the exact paragraph output and
its record; refreshed delivery uses another output and record. Verify that delivered file through
the unchanged read-only native gate. No native refresh or failed cleanup means non-pass; LibreOffice
is not a substitute field evaluator. No relevant fields means no Office launch.
