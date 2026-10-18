# Word numbering and cross-references

This is the shared contract for figure, table and equation numbering, reference refresh and final
delivery. Verify the available source/runtime before execution; a source change does not establish
publication to installed skills. Missing commands leave finalization unfinished, not implicitly passed.

## Scope

- Whole-document creation/export uses native `SEQ` numbering and bookmark-backed `REF` references
  for all intended numbered figures, tables and equations, even when an older Word version exists.
- Local edits change only approved prose, then refresh all existing relevant internal numbering and
  cross-reference fields throughout the document. Report unrelated literal references without
  converting them. Explicit whole-document reference repair may convert all intended literal refs.
- Do not add numbering to unnumbered objects, including inline or display math. Never infer a label
  from numbers inside a formula. Preserve OMML and the visible reference presentation.
- Cover body paragraphs and tables, headers/footers, footnotes/endnotes and text boxes. Do not
  evaluate external links or unrelated fields.

## Common CLI

Paths below are relative to the `docx` skill. Every output is a new path; preserve sources, prior
deliverables and passed records. `source` is a DOCX; Markdown first uses the existing structured
Pandoc conversion, never raw-text reference rewriting.

```text
python scripts/reference_fields.py inspect source
python scripts/reference_fields.py prepare source output --mode full [--mapping mapping.json]
python scripts/reference_fields.py refresh source output --allow-office-com
python scripts/reference_fields.py check baseline candidate
python scripts/reference_fields.py finalize source output --mode full|local --allow-office-com [--record path] [--mapping path]
```

Brackets and `full|local` denote optional arguments and a mode choice, not literal shell syntax.

`inspect` supplies stable-in-that-input locations such as `main:p2:c6` and target keys such as
`main:p4`. A mapping has `references: {"main:p2:c6": "main:p4"}` for explicit target selection and
`ignore: ["main:p8:c5"]` for user-confirmed external/non-object mentions. Stale keys are rejected.
Fully labelled range endpoints are preserved. Abbreviated ranges/lists require explicit endpoint
labels before conversion; ambiguous chapter schemes require a specialized numbering design, not guessing.

| Command | Responsibility |
|---|---|
| `inspect` | Read-only inventory of objects, fields, bookmarks, literal refs and unresolved locations across all stories. No Office launch. |
| `prepare --mode full` | Build missing intended `SEQ`/bookmark/`REF` structures in a new package, preserving valid existing structures. Cached values and `updateFields` are preparation, not refreshed results. |
| `refresh` | Evaluate existing relevant internal fields in guarded native Word, save/reopen, and write only validated field results to a new output. No literal conversion. |
| `check` | Pure OOXML baseline/candidate check of the field-scoped writeback below. No mutation or COM; not proof of native evaluation. |
| `finalize` | Common delivery chain: full mode prepares then refreshes; local mode refreshes only. Check the saved output and bind evidence to its final hash. Mapping supports authorized full preparation, not expansion of local scope. |

All standalone Word creation/edit paths use this finalizer. Export wrappers invoke it after
conversion and template/profile formatting, before final generation/hash recording. Keep the
original input fingerprints, verify them unchanged, and record the final saved deliverable, not a
pre-refresh draft. Never mutate an already-checked output in place or refresh inside `run-check`.
For approved ordinary paragraph edits use the two-stage high-level command in
[paragraph editing](paragraph-editing.md); its strict intermediate is not the field-refreshed final.

## Build and bind

Parse OOXML with namespaces, handling simple, complex, split and nested fields. Use separate `SEQ`
categories for figures, tables and equations. Preserve valid field codes, existing bookmark
identities, chapter/appendix sequences and formatting. New bookmarks have stable unique identities,
stay inside one paragraph and wrap only the number span; they must not protect unrelated adjacent
paragraphs from later prose edits. Keep caption wording outside the number field, with readable
cached results and copied run formatting.

Bind each reference to an unambiguous source object identity. Duplicate labels, missing/deleted
targets and unresolved range endpoints fail with locations; never choose the first match or silently
retarget. Use an explicit mapping when it resolves the intended identity. A mapping cannot invent a
missing object or justify guessing. Preserve reference prefixes, suffixes, parentheses and range
presentation; resolve each intended endpoint. Keep unnumbered objects untouched on repeated runs.
Check package integrity, intended caption/label and `SEQ` counts, bookmark/reference coverage, and
representative first/middle/last captions after preparation; counts alone do not establish correct binding.

## Native refresh

Use Windows with Microsoft Word and the current operation's `--allow-office-com`, subject to
[Office security](office-security-boundary.md). Reuse `owned_application`; leave the native gate's
read-only checker unchanged. Only the refresh helper opens a writable isolated temporary copy.

1. Traverse and deduplicate all relevant stories. Evaluate only numbering dependencies, then `SEQ`,
   then internal `REF`/`PAGEREF`, repaginating when necessary. Never call blanket `Fields.Update` on
   a document or story, and never use an arbitrary field update loop.
2. Require stable results within at most five passes. Locked/unsupported relevant fields, broken
   targets, update errors or non-convergence are non-pass; do not unlock fields or guess values.
3. Save and reopen the temporary Word copy to verify persistence. Read result text from that saved
   package's OOXML, not COM `Result.Text`, avoiding string coercion and locale changes.
4. Transplant only validated textual field results and permitted dirty state into the protected
   candidate package. Save to a new output, check the writeback and verify that delivered file
   separately with the read-only native gate.

Match OOXML and COM fields through independently built composite identities: story identifier,
zero-based field-begin ordinal in that story's OOXML order, and normalized instruction text. Require
a total bijection, never positional pairing alone. For text boxes in `mc:AlternateContent`, use
`mc:Choice` as canonical and apply the same result to its `mc:Fallback` twin; Word exposes that story
once, so do not count the twin as unmatched. Count differences, instruction mismatches, nested-field
ordinal ambiguity, unmapped fields or unsupported result structures abort the entire transplant.

The refresh baseline is the prepared full document or the exact paragraph-stage output, not the
original before authorized structural/prose edits. The field-scoped checker permits only textual
result runs between `separate` and `end` (or the corresponding simple-field result), field `w:dirty`
state and the settings `updateFields` flag. Preserve all other bytes of package parts, including
non-field prose, field codes, bookmarks, styles, OMML, relationships and media. Unsupported structures
must fail instead of widening this allowance. Do not loosen paragraph `check_packages` equality.

## Evidence and incomplete outcomes

Use `document_versions.py` records with separate content/style, reference-structure and native-refresh
results. `reference_fields.py check` emits exactly one JSON object; a pass has `ok: true`,
`status: "PASS"` and no `error`. Any `source`/`file` and `source_sha256*` fields identify the checked
candidate and its current hash, not the baseline. This checker is pure OOXML; if later made to launch
Word, it must also enter `run_check`'s `office_entrypoints` so Office timeout/cleanup protection applies.

Record delivered-file native evidence separately under `word-native` (no render flag for refresh):

```powershell
python scripts/document_versions.py run-check output.docx `
  --record output.docx.check.json --kind word-native -- `
  python scripts/reference_word.py check output.docx --allow-office-com
```

Use the actual final record path returned by the finalizer, or the explicit `--record` path. A
temporary-copy save/reopen proves convergence, not native acceptance of the delivered output.
The wrapper calls the unchanged read-only native gate, using new-instance late-bound COM to avoid
dependence on user-generated wrapper caches. Registration must identify Microsoft WINWORD.EXE;
WPS compatibility registration is rejected before activation. No registry/cache repair is attempted.
Static field checks or merely setting `updateFields` do not prove refresh. Final passed delivery
requires all applicable checks on the final saved hash; retain paragraph-stage evidence separately.

No relevant fields means refresh is not applicable and no Office launch is needed. Otherwise Word
absent/unavailable, an existing user Word process (`UNSAFE_PROCESS`), missing COM consent, unresolved
mapping, locked fields, update or cleanup failure leave native refresh non-pass. Preserve the
candidate where possible, with its constructed fields/cached values, and state the unfinished items;
do not call it a final passed deliverable. Never substitute LibreOffice as the field evaluator.
`Ctrl+A` + `F9` is fallback user advice only, not claimed completion or evidence that every story was
refreshed. Do not attach to or close a user's Word process to make the operation pass.

Refresh alone does not require PDF/PNG or rendering. Keep the existing render requirements for full
creation, template/layout changes and explicit layout checks. Report output/intermediate and record
paths, actual checks, and any pending native refresh or layout evidence separately.
