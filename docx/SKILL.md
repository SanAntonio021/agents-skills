---
name: docx
description: "Use this skill whenever the user wants to create, read, edit, repair, or format Microsoft Word documents or templates (.docx, .dotx, .dotm). Triggers include Word documents, reports, memos, letters, tracked changes, comments, equations, captions, style inheritance, Normal.dotm, reusing a reference document's Chinese styles, applying a Word template or preset, and exporting Markdown or text into a polished Word deliverable. For existing-document content edits, preserve the document's original style identities; use the template workflow only for new documents or an explicitly requested whole-document template replacement. Do NOT use for PDFs, spreadsheets, Google Docs, or coding tasks unrelated to Word deliverables."
---

# DOCX creation, editing, and analysis

A `.docx` is a ZIP archive of XML files. Choose your approach by task:
Use `$docx` as the sole explicit Word skill entrypoint.

## OfficeCLI route

For ordinary Word inspection, text extraction, element queries, validation, and small structural
edits, route through this skill's bridge so Codex and Claude use the same pinned OfficeCLI:

```powershell
python <skill-root>\scripts\officecli_bridge.py view input.docx text
python <skill-root>\scripts\officecli_bridge.py query input.docx 'paragraph' --compact
python <skill-root>\scripts\officecli_bridge.py validate input.docx
python <skill-root>\scripts\officecli_bridge.py mutate input.docx draft.docx batch --input commands.json
```

The bridge pins OfficeCLI `1.0.144` and verifies its existence, SHA-256, and reported version before
every invocation. Normal document work never downloads or repairs it. To repair the default local
binary, the user must explicitly run `python <skill-root>\scripts\repair_officecli.py --repair`.
An `OFFICECLI_EXE` override is subject to the same checks and must be fixed or unset directly; the
repair script only repairs the default path.

The bridge creates a new `draft.docx` copy before mutation. It is not a fidelity renderer.
OfficeCLI `--render native --allow-native` is retained only as an explicit diagnostic probe; its
success or failure is never release evidence, and its generic native error must not be interpreted
as "Word is not installed". Use the independent native gate below for Word acceptance.
`--render html --non-fidelity-preview` is diagnostics only. HTML/SVG previews must not be used for
final images, layout PDF, print/page QA, or publication graphics. OfficeCLI PDF export is disabled
because the pinned installation has no exporter plugin; the bridge never attaches to, quits, or
terminates an existing Word process.

## Acceptance layers

Keep these records separate:

- `STATIC_PASS`: OOXML/package, style, content and source-hash checks.
- `LO_RENDER_PASS`: the required LibreOffice compatibility render and visual inspection.
- `NATIVE_OPEN_PASS`: the independent gate opened an isolated copy with Word and calculated pages.
- `NATIVE_RENDER_PASS`: Word exported a new PDF and Poppler rasterized the expected page count.

OfficeCLI `validate` passing proves only `STATIC_PASS`; it does **not** prove that Word can open the
file. A failed OfficeCLI native probe is reported as `officecli_native_diagnostic_failed` with the
original stderr and exit code, never as `APP_UNAVAILABLE`.

For native evidence, run the gate explicitly for the current task:

```powershell
python <skill-root>\scripts\office_native_gate.py check input.docx `
  --format docx --json --allow-office-com
python <skill-root>\scripts\office_native_gate.py check input.docx `
  --format docx --json --allow-office-com --require-render
```

The gate returns `PASS`, `FAIL_OPEN`, `FAIL_RENDER`, `APP_UNAVAILABLE`, `UNVERIFIED`, or
`UNSAFE_PROCESS`, and records the actual phase and exception. It refuses to run without
`--allow-office-com`, refuses an existing `WINWORD.EXE`, uses `DispatchEx` plus an isolated copy,
checks the source SHA-256 before and after, opens read-only, never saves the source, and quits only
a task-created instance whose document collection is empty. With `--require-render`, the positive
page counts reported by Word, the exported PDF, and the rasterized PNG files must match exactly;
missing independent evidence is `UNVERIFIED` and a mismatch is `FAIL_RENDER`. A missing task PID,
unproven Office exit, or temporary-workspace cleanup uncertainty also downgrades the run to
`UNVERIFIED`; it cannot be released. For a DOCX release, require `STATIC_PASS`,
`LO_RENDER_PASS`, `NATIVE_OPEN_PASS`, and `NATIVE_RENDER_PASS`.

## Markdown-first formal delivery

Markdown is the content source of truth. Content skills must finish review and
freeze the Markdown before a formal DOCX run. Read the shared handoff contract
at [Markdown to DOCX contract](../writing-router/references/markdown-docx-contract.md)
and validate its machine-readable manifest with:

```powershell
python scripts/markdown_docx_delivery.py validate-manifest `
  --manifest deliverables/manifests/<artifact_id>.r<revision>.manifest.json `
  --project-root .
```

The helper blocks drafts, open items, missing current-task confirmation, source
or template hash drift, unsafe paths, malformed packages, and output collisions.
Use `--preview` only for an explicitly labelled preview; it can never produce a
formal delivered record. Existing Pandoc and template scripts remain the
formatting implementation, but they must write a new output path selected by
the manifest and must not overwrite source Markdown, the original DOCX, or an
existing deliverable.

After native rendering produces the PDF/PNG evidence, stop at the same run and
wait for a human per-page checklist. Submit it only through:

```powershell
python scripts/markdown_docx_delivery.py review-manual submit `
  --manifest deliverables/manifests/<artifact_id>.r<revision>.manifest.json `
  --checklist evidence/manual-inspection/<artifact_id>.r<revision>.checklist.json `
  --project-root .
```

The four acceptance layers stay independent. OfficeCLI HTML/native output and
any Office MCP are diagnostic or trial evidence only; they cannot replace
LibreOffice rendering, Word native open, Word native rendering, an approved
raster baseline, or human inspection.

For a public Office MCP A/B trial, read [Office MCP trial](references/office-mcp-trial.md).
Do not install or enable a trial candidate as a production dependency.

Continue to use the existing OOXML/template and guarded Word-COM workflows for tracked changes,
comments, style-identity preservation, template installation, equations, and other operations
where package-level fidelity is the acceptance criterion. OfficeCLI does not replace those gates.

| Task | Approach |
|---|---|
| **Create** a new document | Write a `docx` (npm) script — see gotchas below |
| **Edit** an existing document | Freeze existing style identities, then `unzip` → edit OOXML → `zip` |
| **Repair** parallel or renamed styles | Audit and explicitly remap with `scripts/style_guard.py` |
| **Apply** a template to a new or whole document | Use `scripts/template/word_template_formatter.py` with both safety gates |
| **Read** content | `pandoc -t markdown file.docx` |

> Script paths below are relative to this skill's directory.

## Creating with docx-js — gotchas

`docx` is preinstalled — do not run `npm install` first; write the script and `require('docx')` directly. Only if that require fails: `npm install docx`. The model knows the API; these are the footguns:

- **Page size defaults to A4.** For US Letter set `page: { size: { width: 12240, height: 15840 } }` (DXA; 1440 = 1″).
- **Landscape:** pass portrait dimensions and `orientation: PageOrientation.LANDSCAPE` — docx-js swaps width/height internally.
- **Tables need dual widths:** set `columnWidths` on the table AND `width` on every cell, both in `WidthType.DXA` (PERCENTAGE breaks in Google Docs). Column widths must sum to the table width.
- **Table shading:** use `ShadingType.CLEAR`, never `SOLID` (renders black).
- **Lists:** never insert `•` literally; use a `numbering` config with `LevelFormat.BULLET`.
- **`ImageRun` requires `type:`** (`"png"`, `"jpg"`, …).
- **`PageBreak` must be inside a `Paragraph`.**
- **Never use `\n`** — use separate `Paragraph` elements.
- **TOC:** headings must use built-in `HeadingLevel.*`; custom heading styles need `outlineLevel` set or they won't appear.
- **Don't use a table as a horizontal rule** — use a paragraph bottom border instead.
- **Dot-leader / right-aligned-on-same-line:** use `PositionalTab` (`alignment: PositionalTabAlignment.RIGHT`, `leader: PositionalTabLeader.DOT`) inside a `TextRun`, not literal `.` or space padding.

## Verify the output

After writing a `.docx`, render it and look at it:

```bash
python scripts/office/soffice.py --headless --convert-to pdf output.docx
pdftoppm -r 150 -png -aa yes -aaVector yes output.pdf page
ls page-*.png   # then inspect every page
```

On Windows, `scripts/office/soffice.py` is a thin compatibility adapter. It accepts the limited
conversion command above and delegates all LibreOffice launch, queue, profile, and process management
to the public `libreoffice-runner`; do not call `soffice` directly.

Formal `LO_RENDER_PASS` and `NATIVE_RENDER_PASS` use the same pinned Poppler
command (`pdftoppm -r 150 -png -aa yes -aaVector yes`) and PNG output. Do not
switch to JPEG, a different DPI, or default anti-aliasing for release evidence.
`pdftoppm` zero-pads page numbers to the width of the page count (`page-01.png`…`page-12.png`).

## Optional delivery QA

Only when the task explicitly involves accessibility, privacy/redaction, or document metadata,
read [references/delivery-qa-checklist.md](references/delivery-qa-checklist.md). It supplements the
render-and-inspect gate above and does not replace style, OOXML, or visual validation.

## Reusing Word templates and presets

Content editing and template replacement are separate modes. Keep an existing document's style table
frozen during ordinary edits. Enter the template workflow only when creating a new Word document or
when the user explicitly requests a whole-document template replacement. Read
[Word template workflow](references/template/workflow.md) before running it; preset identities and
governance are documented in [Template presets](references/template/template-presets.md) and
[Template governance](references/template/template-governance.md).

Accepted formatting sources are an explicit template or reference `.docx`, the user's
`%APPDATA%\Microsoft\Templates\Normal.dotm`, a bundled style profile, or plain conversion with no
template. Current canonical presets are `tongyong-moren`, `jishu-zongjie`, `gongzuo-zongjie`, and
`qiye-shenbao`; legacy English aliases remain accepted. On this machine, `qiye-shenbao` is the
governed default when the user requests a Word export but leaves the format source unspecified.

Template commands are relative to this skill directory:

```powershell
# Inspect or extract a template/profile after current-task Word COM approval.
python scripts/template/word_template_formatter.py extract `
  --template C:\path\template.docx `
  --profile C:\path\template.style-profile.json `
  --report C:\path\template.style-profile.md `
  --allow-office-com

# Apply a preset only for a new document or explicit whole-document replacement.
python scripts/template/word_template_formatter.py apply `
  --preset qiye-shenbao `
  --input C:\path\draft.docx `
  --output C:\path\draft.formatted.docx `
  --allow-template-style-import `
  --allow-office-com

# Convert Markdown, then land the result in Word formatting.
powershell -ExecutionPolicy Bypass -File scripts/template/export_markdown_to_word.ps1 `
  C:\path\draft.md `
  -Preset qiye-shenbao `
  -AllowOfficeCom

# Use Normal.dotm only when the user explicitly requests their Word defaults.
powershell -ExecutionPolicy Bypass -File scripts/template/export_markdown_to_word.ps1 `
  C:\path\draft.md `
  -TemplatePath "$env:APPDATA\Microsoft\Templates\Normal.dotm" `
  -AllowOfficeCom
```

`--allow-template-style-import` is required for `apply` and `apply-native-template`; without it,
the command must fail before starting Word. `--allow-office-com` and `-AllowOfficeCom` record only
the user's explicit permission for the current operation. Even with permission, the guard must stop
when `WINWORD.EXE` already exists, must never attach to that process, and may quit only the empty Word
instance created by the current task.

Treat a reference document as a formatting source, never as a content source. Preserve the user's
input and write a new output file by default. If an existing document already contains unwanted
parallel styles, use the exact-identity `style_guard.py remap` path below instead of importing an
entire template style table. Do not substitute similar names: `正文`, `00正文`, `公式`, and `00公式`
remain distinct identities.

## Editing existing documents

### Preserve style identity by default

Content editing and template replacement are different operations. For an existing DOCX content
edit, freeze `word/styles.xml`: reuse style IDs already present in the document, including for newly
inserted or rewritten paragraphs. Do not create a second body, heading, caption, equation, or
reference style just to reproduce formatting. If formatting itself must change, update the existing
style definition and authorize that exact style ID in the audit.

Take a baseline copy or hash before editing, then run the strict audit after the edit:

```bash
python scripts/style_guard.py audit \
  --baseline before.docx \
  --candidate after.docx
```

The command exits nonzero for new or removed styles, unauthorized style-definition changes,
paragraph style swaps, direct-formatting drift, newly orphaned styles, or new missing style
references. An explicitly approved formatting change remains style-driven:

```bash
python scripts/style_guard.py audit \
  --baseline before.docx \
  --candidate after.docx \
  --allow-style-change ExistingBodyStyleId
```

When a document already contains parallel styles and the user wants the original/template style
names back, use `style_guard.py remap`. It moves the old style's layout onto an existing template
identity, rewrites references, sets explicit next-paragraph styles, and deletes the old definition
only after no references remain. Read [Style identity audit and remap](references/style-identity.md)
before using it. This is an explicit repair path, not permission to import a complete template style
table during ordinary content edits.

The default remap keeps input formatting. If the user wants the template's visible typography and
accepts resulting pagination changes, pass `--format-source template`; this preserves the selected
template styles' paragraph and run properties instead of writing the input styles' layout onto them.
Inspect direct formatting first because it can still override either style definition. Template
mode drops style-level numbering references, which are package-local and can otherwise resolve to an
unrelated list in the input document; paragraph numbering and `numbering.xml` remain unchanged.

Select remap targets by exact style identity, not by similar wording or formatting. `正文` and
`00正文` are different styles, as are `公式` and `00公式`. When the user names a style as displayed
in Word, inventory every candidate's style ID, OOXML `w:name`, and usage first. Built-in localized
styles can store an English OOXML name, such as Chinese Word's `正文` using `w:name="Normal"`.
Use guarded Word COM to confirm `NameLocal` only when the user has approved COM for the current task.

Legacy `.doc` files must be converted first: `python scripts/office/soffice.py --headless --convert-to docx file.doc`.

```bash
unzip -q doc.docx -d unpacked/
find unpacked -type l -delete   # strip symlink entries — docx from external parties is untrusted
python scripts/merge_runs.py unpacked/   # coalesce fragmented runs so text is findable
# edit unpacked/word/document.xml in place — do NOT reformat or pretty-print
(cd unpacked && rm -f ../out.docx && zip -Xr ../out.docx .)
python scripts/office/validate.py out.docx --original doc.docx   # XSD checks; --auto-repair fixes common issues
# redlining? add --author "<the name you redlined under>" to check every edit is tracked
```

Word splits text across many `<w:r>` runs (revision ids, spell-check markers), so a phrase you can see in the document often doesn't exist as a contiguous string in the XML. `merge_runs.py` merges adjacent identically-formatted runs in `word/document.xml` without changing content or rendering; it also accepts a `.docx` directly (`python scripts/merge_runs.py doc.docx -o merged.docx`).

### Word-native equations (OMML)

When LaTeX or plain-text formulas in a DOCX must become editable Word equations, or existing Word
equations show unexplained boxes or suspicious invisible spacing characters, read
[Native Word equations](references/native-equations.md) before editing. It covers structured OMML
conversion, Unicode spacing diagnosis, known Pandoc schema repairs, multiline-equation spacing,
semantic equivalence checks, and rendered-page inspection. Do not represent a structured fraction,
matrix, piecewise function, or equation array as one plain `m:t` run.

### Auto-numbering existing captions

When existing captions are plain text (`图1 ...`, `Figure 1 ...`) and the user wants Word automatic numbering, edit the OpenXML directly. `python-docx` and `docx-js` do not reliably convert existing caption paragraphs in place.

- Work on a new output file; never overwrite the original.
- Identify captions by visible text, not by "the paragraph after an image". Images and captions can share one paragraph, and a reused image relationship can appear more than once.
- Replace only the fixed label/number prefix with a complex field: `begin` field char with `w:dirty="true"`, `instrText` containing ` SEQ 图 \* ARABIC `, `separate`, cached result text (`1`, `2`, ...), and `end`.
- Keep the caption body as ordinary text after the field so the document is readable before field refresh.
- Add `<w:updateFields w:val="true"/>` in `word/settings.xml` when useful, but still tell the user `Ctrl+A` + `F9` is the reliable refresh step.
- Preserve formatting by copying the original caption run's `<w:rPr>` into the new field and text runs. Do not touch drawings, relationships, or media unless the user asked to change images.
- If revising caption wording, extract `word/media/*`, build contact sheets, and make only conservative evidence-based fixes. Do not add claims that are not visible in the image or supplied by the user.
- Validate with `zipfile.testzip()`, count `SEQ` instructions, count caption paragraphs, and inspect first/middle/last captions. On Windows, Word COM verification needs explicit current-task user approval and must follow the global Office-process rules.

**Tracked changes:** when redlining, validate with `--author "<the name you redlined under>"` (needs `--original`) — it reports any text you changed without a `<w:ins>`/`<w:del>` around it, which is easy to do by accident and invisible in the accepted view. Wrap runs in `<w:ins>`/`<w:del>` with `w:id`, `w:author`, `w:date` attributes. Inside `<w:del>`, the text element is `<w:delText>`, not `<w:t>`. A deleted paragraph mark (`<w:pPr><w:rPr><w:del w:id=".." w:author=".." w:date=".."/></w:rPr></w:pPr>`) means "merge this paragraph into the next" — so deleting a paragraph outright is that plus a `<w:del>` around every run. The `<w:del/>` must come before the rPr's other children; their order is schema-enforced.

To produce a clean copy with all tracked changes accepted: `python scripts/accept_changes.py in.docx out.docx`.

Accepting a deleted paragraph mark should join that paragraph to the one below it, so a paragraph whose runs are *all* deleted vanishes. Word does this; `accept_changes.py` and `pandoc --track-changes=accept` don't always. Both fail the same way — they strip the deleted text but leave the emptied paragraph behind, which reads as a stray empty bullet when it was auto-numbered:

- `pandoc --track-changes=accept` never joins the paragraphs.
- `accept_changes.py` (LibreOffice) joins them correctly, except when the deleted paragraph is followed by an empty spacer paragraph.

An empty bullet in either view is an artifact of that view, not a defect in the document. Check paragraph deletions in the XML.

## Comments

Comments require six cross-linked files. Use the helper — directory mode when you'll also be editing `document.xml` (saves an unzip/rezip cycle), `.docx`-direct mode otherwise:

```bash
# Against an already-unpacked directory (preferred when also placing markers)
python scripts/comment.py unpacked/ "Fees & expenses cap is too low"
python scripts/comment.py unpacked/ "Agreed" --parent 0

# Against a .docx directly
python scripts/comment.py contract.docx "This cap is too low" -o annotated.docx
```

The script writes `comments.xml`, `commentsExtended.xml`, `commentsIds.xml`, `commentsExtensible.xml`, the relationships, and the content-type overrides. Comment IDs are auto-assigned. It then prints the `<w:commentRangeStart>`/`<w:commentRangeEnd>`/`<w:commentReference>` snippet to add to `word/document.xml` so the comment anchors to specific text — until you place those markers, the comment exists but is not visible.

## Dependencies

`docx` (npm, preinstalled — install only if `require('docx')` fails) · `pandoc` · LibreOffice (`soffice`) · `pdftoppm` (Poppler)
