# Workflow Notes

## Intended use

Use this skill when the user wants Word formatting reuse, not when they want to edit document text semantically.

## Why this skill uses Word COM

- Word COM 可以从真实模板文档复制样式；公开仓只有 style profile 时，脚本会先临时合成一个模板再复制样式。
- It exposes page setup values such as margins, paper size, header distance, and footer distance.
- It is more faithful than `python-docx` for style transfer tasks on Windows.

## Suggested operating pattern

1. Keep the user's template document unchanged.
2. Before any Word COM call, obtain explicit permission for this operation and confirm that no Word document needs protection.
3. Pass `--allow-office-com` or `-AllowOfficeCom` only after that confirmation. If `WINWORD.EXE` already exists, stop without connecting to or closing it.
4. Write the extracted profile next to the template for auditability.
5. Save formatted output into a new file.
6. Only with separate permission to open Word, spot-check the output once:
   - title
   - Heading 1 and Heading 2
   - normal body paragraph
   - page size and margins

The PowerShell wrapper does not create or quit Word directly; it delegates all Word automation, including native `.dot`, `.dotm`, and `.dotx` templates, to the Python guard. The guard uses `DispatchEx`, requires an initially empty instance, and only calls `Application.Quit()` for the instance created by the current task after `Documents.Count` returns to zero. If cleanup cannot prove that condition, it refuses to quit and preserves the primary error.

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
