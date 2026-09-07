# Fast paragraph editing

Use `scripts/edit_paragraphs.py` for ordinary body paragraphs whose character formatting is uniform.
Its strict paragraph stage edits the existing OOXML package directly without OfficeCLI, Word or
LibreOffice. Final delivery also follows [numbering and references](numbering-references.md).
Accepted prose goes into the JSON exactly as approved; do not rewrite it during Word handoff.

## Inspect and finalize

The approved high-level source interface is:

```powershell
python scripts/edit_paragraphs.py inspect source.docx --contains "Original paragraph"
python scripts/edit_paragraphs.py finalize source.docx edits.json output.docx --allow-office-com
```

`finalize` keeps two stages and two records when existing relevant fields need refresh:

1. Apply the approved edits to a new paragraph-stage `output1`, retaining its own content/style
   record. The existing exact `check_packages` equality and source protection remain unchanged.
2. Refresh all existing relevant internal fields from `output1` to a separate `output2`, using the
   common local finalizer. Its field-scoped check compares `output2` with `output1`, and its own record
   binds reference and native evidence to the saved final hash. `output2` is the requested deliverable;
   retain `output1` and its passed record as the strict intermediate.

Report the actual intermediate, deliverable and both record paths returned by the tool. Never reuse
one record for both outputs, mutate `output1` after its check, or relax `check_packages` to permit
field deltas. With no relevant fields, refresh is not applicable and no Office launch is needed.
The new interface is a source contract, not a claim that documentation changes publish the command.

## Lower-level apply and check

```powershell
python scripts/edit_paragraphs.py inspect source.docx --contains "Original paragraph"
python scripts/edit_paragraphs.py apply source.docx edits.json paragraph-stage.docx
python scripts/edit_paragraphs.py check source.docx edits.json paragraph-stage.docx
```

`inspect` returns full text and zero-based paragraph indices from the original `word/document.xml`.
Omit `--contains` to inspect all paragraphs. Indices always refer to the original, even when an earlier
operation in the same batch inserts or deletes a paragraph. `check` is read-only and emits JSON.
These commands remain the strict paragraph-only stage, not finalization when fields need refresh.

The UTF-8 JSON file is an array of edits:

```json
[
  {"op": "replace", "old": "Original paragraph", "text": "Approved replacement"},
  {"op": "insert_before", "old": "Anchor paragraph", "text": "New preceding paragraph"},
  {"op": "insert_after", "old": "Another anchor", "text": "New following paragraph"},
  {"op": "delete", "old": "Paragraph to remove"}
]
```

Each `old` must match the complete original paragraph exactly and uniquely. For repeated text, add
`"index": 12` using an index returned by `inspect`; the tool still checks `old` at that index. A stale
index or stale text fails. It never silently uses the first occurrence. New `text` is one paragraph;
use separate edits for separate paragraphs, with no newline or tab characters in the text.

Replacements retain the original paragraph and uniform character formatting. Insertions inherit
their anchor's formatting by default. To choose the anchor or a physically adjacent sibling paragraph
as the formatting source, add a `format_from` selector:

```json
[
  {
    "op": "insert_after",
    "old": "Anchor paragraph",
    "text": "Approved new paragraph",
    "format_from": {"old": "Adjacent body paragraph", "index": 13}
  }
]
```

`format_from` is only for insertions and uses the same complete-text/optional-index rules. The tool
rejects ambiguous matches, conflicting operations and unsupported targets before publishing output.
Do not combine multiple edits that compete for the same paragraph or insertion location.

## Scope and evidence

Table paragraphs and targets containing formulas, fields, hyperlinks, revisions or mixed character
formatting need the existing specialized workflow. Do not strip these structures or flatten their
text to force them through this tool. Unsupported cases return a clear failure for routing.

The output must be a new path. The entire batch is preflighted and checked before publication; a
failed match or conflict does not produce a partial deliverable. The source is preserved, style
definitions remain frozen and unrelated package parts are verified unchanged. `apply` reuses
`style_guard.py` and `document_versions.py`, writes one paragraph-stage check record by default and
accepts `--record <path>` for a different new check-record location. Existing outputs and records are
protected; reuse their passed results through `document_versions.py` instead of replacing them.

A passing paragraph-stage result establishes content, styles and file integrity, with
`layout: "not_checked"`; it does not establish completed field refresh. A standalone `check` verifies
only that strict candidate and does not render or update its record. Finalization preserves unrelated
literal references, prose, styles, OMML and media; only the existing internal fields' validated results
and permitted dirty/settings state can change globally, as specified in the shared reference.

Report content/style, reference structure, native refresh and unchecked layout separately. Failed or
unavailable native refresh leaves the candidate unfinished, not a final passed deliverable. Avoid
project-specific scripts, snapshots or PDF/PNG for these small edits; the two required records are
not an extra report collection. Update a current-version pointer only when the project already needs one.

Initial full-document creation, template or layout changes (including figure/table layout), and
explicit layout-check requests use the rendering path in `SKILL.md`. Check the affected pages and
their pagination boundaries; inspect all pages for new full documents or document-wide changes.
These conditions select rendering, not an ordinary paragraph update, field refresh or a missing
prior check record.
