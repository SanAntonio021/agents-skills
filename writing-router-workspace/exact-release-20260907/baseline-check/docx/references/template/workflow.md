# Workflow Notes

## Intended use

Use this workflow inside `docx` when the user wants Word formatting reuse. For semantic edits to an
existing document, stay in the main `docx` editing workflow and preserve the original style IDs.

## Why this skill uses Word COM

- Word COM 可以从真实模板文档复制样式；公开仓只有 style profile 时，脚本会先临时合成一个模板再复制样式。
- It exposes page setup values such as margins, paper size, header distance, and footer distance.
- It is more faithful than `python-docx` for style transfer tasks on Windows.

## Suggested operating pattern

1. Keep the user's template document unchanged.
2. Before Word COM, confirm the operation is covered by the current document request and follow [Office Security Boundary](../office-security-boundary.md). The existing guard must prove an exclusive task-owned instance and no impact on user documents. Otherwise continue file-level work and ask only if the remaining native action needs a user decision.
3. Pass `--allow-office-com` or `-AllowOfficeCom` under that proven isolation and existing authorization. If `WINWORD.EXE` already exists, stop without connecting to or closing it.
4. Write the extracted profile next to the template for auditability.
5. Save formatted output into a new file.
   The Markdown exporter selects a new numbered default output when a file already exists and
   refuses an existing explicit output without `-OverwriteExisting`. It captures actual input
   versions before conversion and writes an `UNCHECKED` document record after generation;
   [version checks](../document-version-checks.md) bind subsequent checks to these files.
6. With proven instance isolation, inspect the rendered output:
   - title
   - Heading 1 and Heading 2
   - normal body paragraph
   - page size and margins

The PowerShell wrapper does not create or quit Word directly; it delegates all Word automation, including native `.dot`, `.dotm`, and `.dotx` templates, to the Python guard. The guard uses `DispatchEx`, requires an initially empty instance, and only calls `Application.Quit()` for the instance created by the current task after `Documents.Count` returns to zero. If cleanup cannot prove that condition, it refuses to quit and preserves the primary error.

Canonical entrypoints live under `scripts/template/`. Template profiles live under
`assets/template/`; generated profile reports and governance notes live under
`references/template/`.

## Heuristics used by the apply command

- Copy all styles from the template into the target document；如果公开仓未附带原始模板，则先根据 style profile 临时合成模板。
- Copy the first template section's page setup to the target's first section or all sections.
- Reassign heading paragraphs by existing heading style or outline level.
- Reassign the first body-like paragraph to `Title` only when the chosen title mode allows it.
- Reassign body text conservatively, skipping obvious non-body styles such as TOC, captions, headers/footers, and footnotes.

## Cases that may need manual follow-up

- The source document uses manual font/spacing overrides everywhere.
- The template depends on custom multilevel numbering definitions.
- The document contains many captions, quotations, or custom body variants that should not all collapse into one body style.
