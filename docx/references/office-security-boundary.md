# Office Security Boundary

- LibreOffice headless operations run through `libreoffice-runner` with a unique `UserInstallation`. Direct launch of `soffice`, `soffice.exe`, or `soffice.com` is forbidden.
- Word COM operations must be covered by the current document request and use the existing guard to prove ownership and isolation. Use an exclusive task-owned instance and read-only input copy for native checks; the limited refresh exception is below. Permission flags do not replace these checks, and no fixed user phrase is required.
- An existing `WINWORD.EXE` blocks Word COM automation; existing WPS background, preview or automation processes are recorded but do not block activation. Do not connect to, close, save, or alter any existing Office instance. Continue safe file-level work unless a newly observed provider is proven to be task-owned and empty.
- For Word, the newly observed task-owned process must be `WINWORD.EXE`; its readable executable path, COM `Application.Path`-derived executable, and registered `WINWORD.EXE` path must agree. If the process path cannot be read or does not match, fail closed before opening the document.
- If WPS has hijacked `Word.Application`, the guarded `scripts/native_word_ui_refresh.py --allow-office-ui` route may launch the registered `WINWORD.EXE` directly. It must observe exactly the new Word PID, verify its executable path, operate on a disposable copy, close only that task-owned window normally, and leave all pre-existing WPS processes untouched. A missing Word PID or a path resolving to WPS is non-pass.
- Keep gate temporary files under `%TEMP%/codex-docx-gates` or `%TEMP%/office-mcp-trials`. Reject symbolic links and path traversal in gate-managed temporary workspaces.
- Protect source Markdown, templates and existing deliverables. Clean up only owned files and the current task's empty instance, proving exit before temporary-workspace cleanup.

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
