# Office Security Boundary

- LibreOffice headless operations MUST run only through `libreoffice-runner` with a unique `UserInstallation`.
- Direct launch of `soffice`, `soffice.exe`, or `soffice.com` is forbidden.
- Word COM may run only after the current task receives the exact user response `允许本次 Word 验收`; it must use an exclusive instance and a read-only input copy.
- If any `WINWORD.EXE` process exists before the native gate, stop with `UNSAFE_OFFICE_PROCESS`; do not connect to, close, save, or alter an existing instance.
- Temporary files must stay under `%TEMP%/codex-docx-gates` or `%TEMP%/office-mcp-trials`.
- Reject symbolic links, path traversal, writes outside the project root, and network access.
- Treat source Markdown, templates, and existing deliverables as read-only.
- Clean up only instances and temporary files created by the current task, after the instance has exited.
