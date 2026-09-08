---
name: docx
description: "Use this skill whenever the user wants to create, read, edit, repair, or format Microsoft Word documents or templates (.docx, .dotx, .dotm). Triggers include Word documents, reports, memos, letters, tracked changes, comments, equations, captions, style inheritance, Normal.dotm, reusing a reference document's Chinese styles, applying a Word template or preset, and exporting Markdown or text into a polished Word deliverable. For existing-document content edits, preserve the document's original style identities; use the template workflow only for new documents or an explicitly requested whole-document template replacement. Do NOT use for PDFs, spreadsheets, Google Docs, or coding tasks unrelated to Word deliverables."
---

# DOCX creation, editing, and analysis

A `.docx` is a ZIP archive of XML files. Choose your approach by task:
Use `$docx` as the sole explicit Word skill entrypoint.

## 文件存放与交付

- 项目根目录只放正式成果；候选、脚本、预览、核验记录和工具内部工程统一放在 `项目/过程文件/任务主题/`。同一任务续做及跨技能协作复用该目录；独立同名任务追加 `_YYYYMMDD`，仍重名追加 `_02`。只创建实际需要的目录，不搬动已有项目文件。
- 沿用项目命名习惯；没有约定时用 `内容主题_v01.扩展名`，同名递增版本。生成并通过必要检查后，由智能体在最终回复前自动复制正式成果到根目录，复核复制后的哈希、可打开性及必要依赖，并给出正式路径链接。需要用户挑选时，选定后再交付；不另设确认环节。
- 使用工具的显式输出参数或将工作目录设到任务过程目录，保留工具所需内部结构；正文命令中的相对输出路径均以该目录为基准，技能脚本及输入路径使用绝对路径。不修改上游插件缓存。可编辑源、正式工程及原始数据保留其用途，不一律当作临时文件。
- 普通任务结束后保留过程材料，只有用户显式触发 ChatNote（`chat-notes`）才进入可恢复清理；不自动清空过程目录。工具用于进程隔离、安全回滚的内部暂存清理不等于任务清场，仍遵守原有保护门。

## OfficeCLI route

For ordinary paragraph inspection and edits, use the fast paragraph workflow below. Its strict
paragraph stage needs neither OfficeCLI nor Office; field finalization is separate. For other text
extraction, element queries, validation and small structural edits, this skill's bridge gives Codex
and Claude the same pinned OfficeCLI:

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

## Content and layout checks

For new prose or substantive content changes, use [writing-router](../writing-router/SKILL.md)
before document creation. Small text edits and formatting-only work keep the existing direct route.
For prose handoff, read [Markdown to Word handoff](../writing-router/references/markdown-docx-contract.md).
Use the current source, specified template and requested output. Do not rewrite reviewed prose or
repeat a general writing pass. Existing `loaded_refs` records describe only references actually read.
用户要求导出即复用本轮授权；格式阶段不自行改写正文。
Reuse rules, templates and scripts already read in this task when they have no relevant changes;
do not reload the entire workflow for each accepted paragraph.

Check the OOXML/package, styles, affected content and unchanged source. Read
[Numbering and cross-references](references/numbering-references.md) for the common finalizer:
whole generation establishes `SEQ`/`REF` for intended numbered figures, tables and equations;
local edits refresh all existing relevant internal fields without converting unrelated literal refs.
Do not number unnumbered objects. That reference defines the approved source CLI, not runtime publication.
Ordinary paragraph updates use the strict paragraph stage followed by field finalization, without
rendering or PDF/PNG by default. No relevant fields means no Office launch. Record content/style,
reference and native-refresh results separately, with "layout not checked". Render for initial
full-document creation, template or layout changes (including figure/table layout), or an explicit
layout-check request. Inspect the affected pages and their pagination boundaries; inspect the whole
document for a new full document or changes with document-wide impact. When the affected scope
cannot be established, expand inspection to the complete relevant content. Use one renderer suited
to the target application and the [Word checklist](references/word-acceptance-checklist.md).
No mandatory second renderer, approved raster baseline, fixed confirmation phrase, delivery state
machine or user per-page signature is required.

When rendering is required and Word is the target, prefer the guarded Word gate:

```powershell
python <skill-root>\scripts\document_versions.py run-check input.docx `
  --record input.docx.check.json --kind word-native -- `
  python <skill-root>\scripts\office_native_gate.py check input.docx `
  --format docx --json --allow-office-com --require-render
```

Use [document version checks](references/document-version-checks.md) before resuming a Word delivery
or reusing a previous check. The export wrapper records the actual source, template/profile, images
and generated Word; `run-check` binds the existing checker's JSON result to those versions. Only a
successful result for unchanged files and the same check command is reused. Source changes require
an updated output; hand-edited Word is checked as it is, never silently regenerated. Without a valid
record, check the current document again using the applicable fast or layout path. Version equality
is not a new content or visual inspection. Maintain the document's check record and any necessary
current-version pointer; do not automatically create full snapshots, page images or multiple reports
for a small update.

Pass `--allow-office-com` for the Word operation covered by the current user request, only when the
existing guard proves isolation. It refuses existing `WINWORD.EXE`, uses `DispatchEx`, opens an isolated read-only
copy, checks the source hash, and quits only its own empty instance. Keep all these protections.
When rendering, Word, PDF and PNG page counts must match. Missing PID, exit or cleanup evidence is `UNVERIFIED`.
Never attach to or end a user's instance. The common reference finalizer has a narrowly scoped
writable temporary-copy exception described in [Office security](references/office-security-boundary.md).
If isolation is unavailable, continue file-level checks or suitable `libreoffice-runner` layout work;
LibreOffice cannot substitute for native field refresh, which remains unfinished.

Record actual evidence: static validation does not establish rendering; LibreOffice rendering does
not establish Word-native behavior. A failed OfficeCLI native diagnostic does not establish that
Word is absent. If the user specifically requires native validation, report any unfinished item
as unverified while delivering the completed work.

Default to a new output and protect the current source and prior deliverables. Figure-heavy
documents use [figure reference checks](references/figure-integration-gate.md) and, when a project
manifest already exists, `scripts/validate_figure_references.py`.

For explicitly requested Office MCP trials only, see [Office MCP trial](references/office-mcp-trial.md).
Trials do not change production dependencies or substitute for actual document checks.

Existing OOXML/template and guarded Word-COM tools still handle tracked changes, comments,
style identity, equations and template application. A failed pinned OfficeCLI check disables that
tool; use a trustworthy available file library or existing tool instead of blocking document work.

| Task | Approach |
|---|---|
| **Create** a new document | Write a `docx` (npm) script — see gotchas below |
| **Edit** ordinary paragraphs | Use `scripts/edit_paragraphs.py` (`inspect`, `finalize`); `apply`/`check` are strict lower-level stages; no render by default |
| **Edit** complex existing content | Freeze style identities and use the existing specialized OOXML tool |
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

For ordinary paragraph updates, complete the paragraph and reference finalization checks below. When rendering
is required by the content and layout rules above, render and inspect the affected scope:

```bash
python scripts/office/soffice.py --headless --convert-to pdf output.docx
pdftoppm -r 150 -png -aa yes -aaVector yes output.pdf page
ls page-*.png   # inspect affected pages; all pages for a new full document
```

On Windows, `scripts/office/soffice.py` is a thin compatibility adapter. It accepts the limited
conversion command above and delegates all LibreOffice launch, queue, profile, and process management
to the public `libreoffice-runner`; do not call `soffice` directly.

For comparable evidence, Word and LibreOffice renders use the existing Poppler
command (`pdftoppm -r 150 -png -aa yes -aaVector yes`) and PNG output. Do not
switch to JPEG, a different DPI, or default anti-aliasing for release evidence.
`pdftoppm` zero-pads page numbers to the width of the page count (`page-01.png`…`page-12.png`).

## Optional delivery QA

Only when the task explicitly involves accessibility, privacy/redaction, or document metadata,
read [references/delivery-qa-checklist.md](references/delivery-qa-checklist.md). It supplements the
checks selected above and does not replace style, OOXML, or required visual validation.

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
# Inspect or extract a template/profile for the current request with proven isolation.
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

Always pass `-OutputPath` and `-CheckRecordPath` inside `项目/过程文件/任务主题/` to the export wrapper; its intermediate DOCX and adjacent records therefore stay together. After checks pass, copy the selected DOCX to the project root and verify the delivered bytes. Preserve the original check record as evidence for the identical source hash; perform any new path-bound check against the delivered path and write its record back into the process directory. Do not rewrite old evidence to pretend it checked another path.

The export wrapper creates `<output>.check.json`, or uses an explicit `-CheckRecordPath`. This is
the corresponding document's check record, not an approval workflow. The approved export integration
runs the common reference finalizer after formatting and before final generation/hash recording;
see [Numbering and cross-references](references/numbering-references.md) for completion evidence.
Generation alone is `UNCHECKED`.
Default output-name collisions select a new numbered file; an existing explicit `-OutputPath` is
refused unless `-OverwriteExisting` was explicitly authorized. Inputs and templates are protected
even with that switch.

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

### Fast paragraph updates

Use the fixed `scripts/edit_paragraphs.py` tool for whole-paragraph replacement, insertion before or
after an existing paragraph, and deletion. `inspect` lists complete text and stable source paragraph
indices. The high-level `finalize source edits output --allow-office-com` retains a strict paragraph
output/record, then creates a separately refreshed deliverable/record. Lower-level `apply` accepts
the original DOCX, a UTF-8 JSON edit list and a new output path; `check` verifies that strict stage
against the original and the same edit list, not the later field-refreshed output. See
[Paragraph editing](references/paragraph-editing.md) for the exact commands and JSON format.

Match complete original text uniquely. If it occurs more than once, use the paragraph index returned
by `inspect` and validate the original text again; never choose the first match silently. Retain the
target's paragraph style and run formatting. Insertions inherit the specified adjacent paragraph's
formatting. Formula, field, hyperlink, revision and mixed-character-formatting targets require an
existing specialized tool; do not flatten them into plain text.

The tool validates the entire batch before publishing a new output, then reuses `style_guard.py`
and `document_versions.py` to check text, unchanged parts and source preservation. Match failures,
unsupported targets and conflicting edits produce no partial deliverable. The check record explicitly
distinguishes passed content/style checks from layout not checked. Existing fields require the
separate common finalization stage before final passed delivery. Do not write a project-specific
script, regenerate the full document or create a snapshot/report collection for these small edits.
Only guarded native field finalization needs Word; accepted text is inserted exactly as approved.

### Preserve style identity by default

Content editing and template replacement are different operations. For an existing DOCX content
edit, freeze `word/styles.xml`: reuse style IDs already present in the document, including for newly
inserted or rewritten paragraphs. Do not create a second body, heading, caption, equation, or
reference style just to reproduce formatting. If formatting itself must change, update the existing
style definition and authorize that exact style ID in the audit.

Retain the original and capture its hash before editing. The fast paragraph tool includes the strict
style audit; other editing paths run it after the edit:

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

For package-level repair and remap, all writes to `word/styles.xml` go through
`scripts/styles_normalizer.py`; generic OOXML repair paths deliberately skip that part. The boundary
validates package-wide style references, preserves the root declaration/outer bytes and
markup-compatibility structure, and rejects unsafe style remaps whose source or template definition
is nested below `w:styles`. Check for unregistered direct writers before a release with
`python scripts/styles_normalizer.py`.

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

### Numbering and reference finalization

For full generation, local edits or explicit reference repair, use
[Numbering and cross-references](references/numbering-references.md). It defines construction,
all-story native refresh, protected writeback, CLI and saved-output evidence. Manual `Ctrl+A` + `F9`
is fallback advice when native refresh is unfinished, never proof of completion. For caption identity,
image selection and wording checks also read [Figure integration](references/figure-integration-gate.md).

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
