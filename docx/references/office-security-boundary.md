# Office Security Boundary

- LibreOffice headless operations run through `libreoffice-runner` with a unique `UserInstallation`. Direct launch of `soffice`, `soffice.exe`, or `soffice.com` is forbidden.
- Word COM operations must be covered by the current document request and use the existing guard to prove ownership and isolation. Use an exclusive task-owned instance and read-only input copy; permission flags do not replace these checks, and no fixed user phrase is required.
- An existing `WINWORD.EXE` causes `UNSAFE_OFFICE_PROCESS`; do not connect to, close, save, or alter an existing instance. Continue safe file-level work.
- Keep gate temporary files under `%TEMP%/codex-docx-gates` or `%TEMP%/office-mcp-trials`. Reject symbolic links and path traversal in gate-managed temporary workspaces.
- Protect source Markdown, templates and existing deliverables. Clean up only owned files and the current task's empty instance, proving exit before temporary-workspace cleanup.
