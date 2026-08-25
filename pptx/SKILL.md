---
name: pptx
description: "Use this skill any time a .pptx or .potx file is involved in any way — as input, output, or both. This includes: creating slide decks, pitch decks, or presentations; reading, parsing, or extracting text from any .pptx or .potx file (even if the extracted content will be used elsewhere, like in an email or summary); editing, modifying, or updating existing presentations; combining or splitting slide files; working with templates (.potx), layouts, speaker notes, or comments. Trigger whenever the user mentions \"deck,\" \"slides,\" \"presentation,\" or references a .pptx or .potx filename, regardless of what they plan to do with the content afterward. If a .pptx or .potx file needs to be opened, created, or touched, use this skill. For OfficeCLI-backed inspection or constrained editing, route through the shared local OfficeCLI bridge described below."
---

# PPTX creation, editing, and analysis

A `.pptx` is a ZIP archive of XML files. Choose your approach by task:

## OfficeCLI route

For ordinary `.pptx`/`.potx` inspection, text extraction, element queries, validation, and small
structural edits, use this skill's bridge so Codex and Claude call the same pinned OfficeCLI:

```powershell
python <skill-root>\scripts\officecli_bridge.py view input.pptx text
python <skill-root>\scripts\officecli_bridge.py query input.pptx '*' --compact
python <skill-root>\scripts\officecli_bridge.py validate input.pptx
python <skill-root>\scripts\officecli_bridge.py mutate input.pptx draft.pptx batch --input commands.json
```

The bridge pins OfficeCLI `1.0.144` and verifies its existence, SHA-256, and reported version before
every invocation. Normal presentation work never downloads or repairs it. To repair the default local
binary, the user must explicitly run `python <skill-root>\scripts\repair_officecli.py --repair`.
An `OFFICECLI_EXE` override is subject to the same checks and must be fixed or unset directly; the
repair script only repairs the default path.

The bridge copies `input.pptx` to new `draft.pptx` before mutation and never overwrites an existing
output. It is not a fidelity renderer. OfficeCLI `--render native --allow-native` is retained only
as an explicit diagnostic probe; its success or failure is never release evidence, and its generic
native error must not be interpreted as "PowerPoint is not installed". Use the independent native
gate below for PowerPoint acceptance. `--render html --non-fidelity-preview` is also diagnostics only.
HTML/SVG previews must not be used for final images, layout PDF, print/page QA, or publication
graphics. OfficeCLI PDF export is disabled because the pinned installation has no exporter plugin.
The bridge never quits or terminates Office.

## Acceptance layers

Keep these records separate:

- `STATIC_PASS`: `validate.py`, OOXML/package checks, typography and source-hash checks.
- `LO_RENDER_PASS`: the required LibreOffice compatibility render and visual inspection.
- `NATIVE_OPEN_PASS`: the independent gate opened an isolated copy with PowerPoint and read
  `Slides.Count`.
- `NATIVE_RENDER_PASS`: the same gate exported every slide to a new non-empty PNG.

OfficeCLI `validate` passing proves only `STATIC_PASS`; it does **not** prove that PowerPoint can
open the file. A failed OfficeCLI native probe is reported as
`officecli_native_diagnostic_failed` with the original stderr and exit code, never as
`APP_UNAVAILABLE`.

For native evidence, run the gate explicitly for the current task:

```powershell
python <skill-root>\scripts\office_native_gate.py check input.pptx `
  --format pptx --json --allow-office-com
python <skill-root>\scripts\office_native_gate.py check input.pptx `
  --format pptx --json --allow-office-com --require-render
```

The gate returns `PASS`, `FAIL_OPEN`, `FAIL_RENDER`, `APP_UNAVAILABLE`, `UNVERIFIED`, or
`UNSAFE_PROCESS`, and records the actual phase and exception. It refuses to run without
`--allow-office-com`. If `POWERPNT.EXE` already exists, the PPTX gate does not call COM, returns
`UNVERIFIED` in `preflight` with reason `powerpoint_already_running`, and its non-JSON output is
exactly `请关闭 PowerPoint 后重试。` It never attaches to, closes, or kills that process. Otherwise
it uses `DispatchEx` plus an isolated copy, checks the source SHA-256 before and after, never saves
the source, and quits only a task-created instance whose presentation collection is empty. For a
PPTX release, require `STATIC_PASS`, `LO_RENDER_PASS`, `NATIVE_OPEN_PASS`, and
`NATIVE_RENDER_PASS`; a blocked native check is not a completed delivery.

### Python runtime preflight

Before running `scripts/office/validate.py` or `scripts/typography_audit.py`, run
`scripts/python_runtime_preflight.py` with the interpreter currently selected for QA. The
preflight is standard-library-only and probes each candidate in its own process by importing
`defusedxml`, `lxml`, and `pptx` (the `python-pptx` distribution). It checks the current
`sys.executable` first, then `py -3`, PATH Python, and any explicitly supplied system-Python
candidate. Use only the first candidate for which all three imports pass; do not install or repair
packages automatically.

Keep the complete JSON report with the QA evidence. It must record every candidate, its source,
actual interpreter path, Python version, each dependency's `ok`/`version`/`error` result, and the
final `selected_executable`. If no candidate passes, stop before file validation. The report path
must be an existing QA/evidence directory; the preflight refuses `.codex`, `.cc-switch`, `.claude`,
and bundled runtime paths. The selected interpreter is the only interpreter allowed for the two
static validators, and its path plus the three dependency results belong in the `STATIC_PASS`
record.

Keep the existing OOXML/pptxgenjs paths for template-sensitive work, unsupported PowerPoint
features, and any operation where preserving package parts is the acceptance criterion. OfficeCLI
is an interface and does not replace the visual QA or source-hash checks below.

| Task | Approach |
|---|---|
| **Create** a new deck | Write a `pptxgenjs` script — see gotchas below |
| **Edit** an existing deck, or build from a template | unzip → edit `ppt/slides/slideN.xml` → zip |
| **Read** content | `markitdown deck.pptx` (one block per slide under `<!-- Slide number: N -->` markers); visual grid: `python scripts/thumbnail.py deck.pptx` |

## Scripts

Paths are relative to this skill's directory. Everything else is plain Python, `node`, or shell.

| Script | What it does |
|---|---|
| `scripts/thumbnail.py deck.pptx [prefix]` | Labeled grid of every slide, for picking template layouts. `.pptx` only. Pass `prefix` — it defaults to `thumbnails`, which overwrites the grids of any other deck done in the same directory |
| `scripts/add_slide.py unpacked/ slide2.xml [--after slideN.xml]` | Duplicate a slide (or a `slideLayoutN.xml`) with all the package bookkeeping. Also takes a `.pptx` directly with `-o out.pptx` |
| `scripts/clean.py unpacked/` | Delete slides, media, and rels no longer referenced. Run **after** `<p:sldIdLst>` is final |
| `scripts/python_runtime_preflight.py [--candidate PATH] [--json-out PATH]` | Select a verified Python runtime for static PPTX QA; import-checks `defusedxml`, `lxml`, and `python-pptx`, and never installs packages |
| `scripts/office/validate.py deck.pptx [--original src.pptx]` | Schema, relationship, content-type, chart and slide checks; each failure names its fix. Pass `--original` for any template-derived deck — it baselines the schema checks against the template, so the template's own XSD errors don't read as yours |
| `scripts/office/soffice.py --headless --convert-to pdf deck.pptx` | LibreOffice wrapper — bare `soffice` hangs in this sandbox |

On Windows, `scripts/office/soffice.py` is a thin compatibility adapter. It accepts the limited
conversion command above and delegates all LibreOffice launch, queue, profile, and process management
to the public `libreoffice-runner`; do not call `soffice` directly.

## Creating with pptxgenjs — gotchas

`pptxgenjs` is preinstalled — do not run `npm install` first; write the script and `require('pptxgenjs')` directly. Only if that require fails: `npm install pptxgenjs`. The model knows the API; these are the footguns:

- **Set `pres.layout` before adding slides.** The default canvas is `LAYOUT_16x9` = **10" × 5.625"**, not 13.3" wide. Coordinates past the edge are written, not clamped — the shape just isn't on the slide. (`LAYOUT_WIDE` is 13.3" × 7.5".)
- **Hex colors: never `#`, never 8 digits.** `color: "FF0000"`. Both `"#FF0000"` and alpha baked into the hex (`"00000020"`) **corrupt the file**. For translucency: `transparency: 0-100` on fills and images, `opacity: 0.0-1.0` on shadows — each is silently ignored on the other.
- **pptxgenjs mutates option objects in place** (converts values to EMU on first use). Never share one `shadow`/options object across two `add*` calls — build a fresh object each time.
- **Shadow `offset` must be ≥ 0** — a negative offset corrupts the file. To cast a shadow upward, use `angle: 270` with a positive offset.
- **All shape extents must be non-negative.** `pptxgenjs` writes a negative `a:ext cx/cy` when a line or shape is given reversed endpoints (for example, `h: y2 - y1` with `y2 < y1`); PowerPoint may report the file as corrupt even when LibreOffice renders it. Normalize line endpoints or use positive `w/h` plus the appropriate direction before writing.
- **`letterSpacing` is silently ignored** — the real option is `charSpacing`.
- **Lists:** `bullet: true` on each item, never a literal `•` (renders double bullets). Set `breakLine: true` on every array item except the last. Space bulleted paragraphs with `paraSpaceAfter`, not `lineSpacing` (huge gaps).
- **One `new pptxgen()` per output file** — never reuse an instance.
- **`rectRadius` only works on `ROUNDED_RECTANGLE`**, not `RECTANGLE`.
- **Gradient fills aren't supported** — use a gradient image as the background instead.
- **Text boxes have built-in internal padding** — set `margin: 0` whenever text must align with a shape, line, or icon at the same x.
- **Speaker notes go in `slide.addNotes("...")`** (plain text, once per slide), never in a text box on the slide.
- **Keep charts native.** Use `addChart()` for everything PowerPoint can chart (pass an array of `{type, data, options}` for combos). For PowerPoint-native features the library doesn't expose (trendlines, error bars), compute the extra series yourself or post-process the generated OOXML — do not fall back to a rendered image. Only chart types PowerPoint has no native form for (Sankey, network, chord) go in as images.
- **Default charts render bare** — no title, no data labels, dated palette. Set `showTitle` + `title`, `showValue: true` + `dataLabelPosition`, `chartColors: [...]` from your palette, and quiet the frame (`catAxisLabelColor`/`valAxisLabelColor`, `valGridLine: { color, size }`, `catGridLine: { style: "none" }`, `showLegend: false` for a single series).
- **On a stacked bar or column chart, `dataLabelPosition` must be `ctr`, `inEnd`, or `inBase`.** `outEnd` **corrupts the file**.
- **A combo series using `secondaryValAxis`/`secondaryCatAxis` needs both `valAxes` and `catAxes` on the chart options, two entries each.** Without them pptxgenjs writes axis *ids* it never declares, and PowerPoint **discards that chart** and reports the file as corrupt. Supplying only `valAxes` is not enough.
- **Tables need a post-write shape-ID check.** PptxGenJS 4.0.1 can give a table's `p:cNvPr@id` the same value as another object on that slide. `objectName` changes `p:cNvPr@name`; it does not reserve or replace the numeric ID. Rebuild the deck with an unused per-slide ID rather than relying on the name.
- **After `writeFile()`, run `python scripts/office/validate.py deck.pptx`.** It reports the two chart faults above, duplicate per-slide `p:cNvPr@id` values (including tables, charts, and grouped shapes), negative DrawingML extents, and the other slide-XML defects PowerPoint refuses. The diagnostics name the slide and the offending object/attribute where available. Fix them in your generator, not by hand-editing the packed XML.
- **Never reorder the children of `<p:presentation>`.** pptxgenjs writes `<p:notesMasterIdLst>` right after `<p:sldIdLst>` and points both masters at one theme part. PowerPoint reads that happily — move the element and the same deck becomes unopenable.
- **Icons:** render `react-icons` to SVG (`ReactDOMServer.renderToStaticMarkup`), rasterize with `sharp` at ≥256px, and insert via `addImage({ data: "image/png;base64," + buf.toString("base64") })` — the `image/png;base64,` prefix is required (`react-icons`, `react`, `react-dom`, and `sharp` are preinstalled — `npm install react-icons react react-dom sharp` only if a require fails).

## Editing existing decks and templates

Pick layouts first: `python scripts/thumbnail.py template.pptx template-thumbs` writes a labeled grid of every slide and prints the file(s) it created — `template-thumbs.jpg`, split into `template-thumbs-N.jpg` past 12 slides. **Always pass that second argument, named after the deck.** It defaults to `thumbnails`, so two decks thumbnailed in one directory silently overwrite each other's grids — the first deck's are simply gone (template analysis only — visual QA needs the full-resolution renders from [Converting to Images](#converting-to-images); it only accepts `.pptx`, so copy a `.potx` to a `.pptx` name first). Use it with `markitdown` to map each content section onto a template slide, and vary the layouts — don't put every section on the same title-and-bullets slide.

```bash
python3 -c "import sys,zipfile; zipfile.ZipFile(sys.argv[1]).extractall('unpacked')" deck.pptx
python scripts/add_slide.py unpacked/ slide2.xml --after slide2.xml   # duplicate a slide (or slideLayoutN.xml); prints the new slide's path
# reorder / delete slides = edit <p:sldIdLst> in ppt/presentation.xml
python scripts/clean.py unpacked/                                     # after deletions: removes orphaned slides, media, rels
# edit slide content in ppt/slides/slideN.xml
(cd unpacked && rm -f ../out.pptx && zip -Xr ../out.pptx .)           # zip from INSIDE the dir; rm first or deleted parts survive
python scripts/office/validate.py out.pptx --original deck.pptx
```

- **Do all structural work — add, delete, reorder — before editing any slide's content.** `add_slide.py` copies a slide file verbatim, so duplicating after you edit clones the edited content; and `clean.py` deletes any slide missing from `<p:sldIdLst>`, including one you just wrote.
- **Never copy a slide file by hand** — `add_slide.py` does every registration a new slide needs and reports what it made (`Created ppt/slides/slide17.xml from slide2.xml`). It also works directly on a file: `add_slide.py deck.pptx slide2.xml -o out.pptx` — **pass `-o`, or it rewrites the input deck in place.** A duplicated slide still *references* its source's chart/SmartArt/embedded-object parts rather than cloning them, so editing one slide's chart changes the other's.
- **If you use `python-pptx`**, three things it won't do: duplicate a slide (its only entry point is `add_slide(layout)`), preserve formatting through `text_frame.text = "..."` (that collapses the paragraph to a single unstyled run — assign `run.text` instead), or read the SVG/EMF most template art uses (`add_picture` raises `UnidentifiedImageError`).
- Legacy `.ppt` must be converted first: `python scripts/office/soffice.py --headless --convert-to pptx file.ppt`. `.potx` templates unpack and pack identically — keep the `.potx` extension on the output.
- To reuse a template icon or image, duplicate a slide or layout that already contains it.

When filling in a template:

- If you script an XML transform, parse with `defusedxml.minidom` — round-tripping OOXML through `xml.etree.ElementTree` rewrites namespace prefixes and corrupts the deck.
- **Template slots ≠ source items.** If the template shows 4 team members and you have 3, delete the 4th member's entire group (image + text boxes), not just its text — then check for orphaned visuals in QA.
- One `<a:p>` per list item — never concatenate items into a single paragraph. Copy the sibling `<a:pPr>` to preserve spacing, and put `b="1"` on the `<a:rPr>` of titles, section headers, and inline labels (`Status:`, `Owner:`).
- Let bullets inherit from the layout; only add `<a:buChar>`, `<a:buAutoNum>` (numbered), or `<a:buNone>` to override — never a literal `•` in the text.
- Text with leading or trailing spaces needs `xml:space="preserve"` on its `<a:t>`.

## Design Ideas

**Don't create boring slides.** Plain bullets on a white background won't impress anyone. Consider ideas from this list for each slide.

### Before Starting

- **Pick a bold, content-informed color palette**: The palette should feel designed for THIS topic. If swapping your colors into a completely different presentation would still "work," you haven't made specific enough choices.
- **Dominance over equality**: One color should dominate (60-70% visual weight), with 1-2 supporting tones and one sharp accent. Never give all colors equal weight.
- **Dark/light contrast**: Dark backgrounds for title + conclusion slides, light for content ("sandwich" structure). Or commit to dark throughout for a premium feel.
- **Commit to a visual motif**: Pick ONE distinctive element and repeat it — rounded image frames, icons in colored circles. Carry it across every slide. **Do not use a color bar or accent stripe as your motif** (see Avoid list).

### Color Palettes

Choose colors that match your topic — don't default to generic blue. Use these palettes as inspiration:

| Theme | Primary | Secondary | Accent |
|-------|---------|-----------|--------|
| **Midnight Executive** | `1E2761` (navy) | `CADCFC` (ice blue) | `FFFFFF` (white) |
| **Forest & Moss** | `2C5F2D` (forest) | `97BC62` (moss) | `F5F5F5` (cream) |
| **Coral Energy** | `F96167` (coral) | `F9E795` (gold) | `2F3C7E` (navy) |
| **Warm Terracotta** | `B85042` (terracotta) | `E7E8D1` (sand) | `A7BEAE` (sage) |
| **Ocean Gradient** | `065A82` (deep blue) | `1C7293` (teal) | `21295C` (midnight) |
| **Charcoal Minimal** | `36454F` (charcoal) | `F2F2F2` (off-white) | `212121` (black) |
| **Teal Trust** | `028090` (teal) | `00A896` (seafoam) | `02C39A` (mint) |
| **Berry & Cream** | `6D2E46` (berry) | `A26769` (dusty rose) | `ECE2D0` (cream) |
| **Sage Calm** | `84B59F` (sage) | `69A297` (eucalyptus) | `50808E` (slate) |
| **Cherry Bold** | `990011` (cherry) | `FCF6F5` (off-white) | `2F3C7E` (navy) |

### For Each Slide

**Every slide needs a visual element** — image, chart, icon, or shape. Text-only slides are forgettable.

**Layout options:**
- Two-column (text left, illustration on right)
- Icon + text rows (icon in colored circle, bold header, description below)
- 2x2 or 2x3 grid (image on one side, grid of content blocks on other)
- Half-bleed image (full left or right side) with content overlay

**Data display:**
- Large stat callouts (big numbers 60-72pt with small labels below)
- Comparison columns (before/after, pros/cons, side-by-side options)
- Timeline or process flow (numbered steps, arrows)

**Visual polish:**
- Icons in small colored circles next to section headers
- Italic accent text for key stats or taglines

### Typography

**Font names you write into the .pptx are rendered by the user's PowerPoint, not by this environment.** Your visual QA renders via LibreOffice, which substitutes fonts it doesn't have — and for some fonts the substitute has different widths, so your QA preview can show text overflow (or fit) that the real deck won't have. To keep your QA trustworthy:

- **Safe fonts** (render true-to-width in QA *and* ship with Office): **Arial, Calibri, Cambria, Times New Roman, Courier New, Bookman Old Style, Century Schoolbook**. Use these for body text and anything where fit matters.
- **Headers with personality at zero QA risk**: pair a safe-list serif header (Cambria, Bookman Old Style, Century Schoolbook) with a safe-list sans body (Calibri or Arial). You get visual contrast without giving up reliable overflow checks.
- **If the user asks for a font outside the safe list** (e.g. Georgia or Trebuchet MS): use it where the user asked, but size those containers with extra slack (~10%) and don't trust QA text-fit on those elements — the preview of that font is approximate. If the user hasn't specified, prefer safe-list fonts for body text.
- **QA-unreliable fonts** (substitute has different widths — overflow checks can be wrong): Georgia, Trebuchet MS, Impact, Arial Black, Garamond, Consolas, Palatino Linotype. Calibri Light substitution varies by environment; treat as QA-unreliable. Fine for titles/accents with slack; don't trust QA text-fit on these.
- **Never default to Aptos** — Office's post-2023 default has no metric-compatible substitute here *and* is missing from older Office installs, so it's unreliable on both ends.

| Element | Size |
|---------|------|
| Slide title | 36-44pt bold |
| Section header | 20-24pt bold |
| Other non-table visible text | 12pt minimum |
| Table cells and chart data tables, except sources/links | 12pt minimum |
| Sources, links, and footnotes | 12pt minimum, muted |

These are delivery gates, not suggestions. Table cells and native chart data tables use
the 12pt minimum. Charts, axes, legends, timelines, Gantt labels, and other reader-facing
content also use the 12pt minimum. Twelve points is a floor for collision avoidance, not
the default: use larger text when the layout has room, and reduce content or reflow it
before accepting overlaps. Titles and section headers retain their larger gates.

Give generated title, section-header, source, and footnote shapes meaningful
`objectName` values (`Title`, `SectionHeader`, `Source`, `Citation`, or `Footnote`) when
the creation library supports it. This makes the typography audit deterministic.

### Spacing

- 0.5" minimum margins
- 0.3-0.5" between content blocks
- Leave breathing room—don't fill every inch

### Avoid (Common Mistakes)

- **Don't repeat the same layout** — vary columns, cards, and callouts across slides
- **Don't center body text** — left-align paragraphs and lists; center only titles
- **Don't skimp on size contrast** — titles need 36pt+ to stand out from body text
- **Don't default to blue** — pick colors that reflect the specific topic
- **Don't mix spacing randomly** — choose 0.3" or 0.5" gaps and use consistently
- **Don't style one slide and leave the rest plain** — commit fully or keep it simple throughout
- **Don't create text-only slides** — add images, icons, charts, or visual elements; avoid plain title + bullets
- **Don't forget text box padding** — when aligning lines or shapes with text edges, set `margin: 0` on the text box or offset the shape to account for padding
- **Don't use low-contrast elements** — icons AND text need strong contrast against the background; avoid light text on light backgrounds or dark text on dark backgrounds
- **NEVER use accent lines under titles** — these are a hallmark of AI-generated slides; use whitespace or background color instead
- **NEVER add decorative color bars or accent stripes** — this includes: header/footer bars spanning the slide width, vertical sidebar stripes down one edge of the slide, thin accent stripes along one edge of a card or content block, and "single-side borders" on rectangles. These read as AI-generated filler. If you want to set a card apart, use a subtle background tint, a drop shadow, or an icon — not an edge stripe.
- **Don't default to cream/beige backgrounds** — when no background is specified, use white (`FFFFFF`) or the user's brand palette; avoid warm-neutral defaults like `F5F5DC`, `FAF0E6`, `FAEBD7`, `FFF8E1`
- **Don't ship text that overflows its shape** — if text doesn't fit, simplify, split across slides, or enlarge the container; never reduce visible text below the typography gates or leave content cut off or spilling past bounds

## QA (Required)

Your first render usually has a few real issues — overlaps, overflow, misalignment. Find and fix those, re-render only the slides you changed, and stop.

### Content QA

```bash
markitdown output.pptx
```

Check for missing content, typos, wrong order.

**When using templates, check for leftover placeholder text:**

```bash
markitdown output.pptx | grep -iE "\bx{3,}\b|lorem|ipsum|\bTODO|\[insert|this.*(page|slide).*layout"
```

If grep returns results, fix them before declaring success.

### File QA (required)

```powershell
$preflight = Join-Path "<skill-root>" "scripts/python_runtime_preflight.py"
$report = Join-Path "<qa-evidence-dir>" "python-runtime-preflight.json"
& "<current-python>" $preflight --json-out $report
if ($LASTEXITCODE -ne 0) { throw "No verified Python runtime for PPTX static QA" }
$qa_python = (Get-Content -LiteralPath $report -Raw -Encoding UTF8 | ConvertFrom-Json).selected_executable
if ([string]::IsNullOrWhiteSpace($qa_python)) { throw "Preflight did not select an interpreter" }
& $qa_python scripts/office/validate.py output.pptx                      # built from scratch
& $qa_python scripts/office/validate.py output.pptx --original src.pptx  # built from a template
& $qa_python scripts/typography_audit.py output.pptx
```

The preflight command is mandatory even when the invoking Python is expected to be complete:
record its JSON before recording `STATIC_PASS`. If the current runtime is missing a dependency,
the only permitted recovery is to rerun the validators with a candidate that the preflight itself
verified, such as `py -3` or an installed system Python. Do not run `pip install` and do not edit
runtime directories.

**If the deck came from a template, always pass `--original`.** A template may itself
contain parts the XSD rejects, so a bare run can report failures you never caused — and
a genuine regression can hide among them. `--original` baselines
the schema and slide checks against the template, suppressing errors it already had.
The structural checks — relationships, content types, charts — ignore `--original` and
report template-inherited problems either way, so read those on their own merits.
Per-slide `p:cNvPr@id` uniqueness is also structural and is never suppressed by
`--original`; PowerPoint requires those object IDs to be unique within each slide.

The typography audit is read-only and checks the entire output deck, including text in
tables, grouped shapes, and native chart text. It fails when any non-title visible text
is below 12pt, automatic shrink-to-fit reduces the effective size below its gate, or the
effective size cannot be resolved. `spAutoFit` may expand a shape but does not waive an
unresolved base font size. Fix the layout and rerun the audit; the script does not
mechanically enlarge text.

For a user-authorized exception to the 12pt visible-text gate, pass
`--exceptions exceptions.json`. Each entry must identify one slide and one shape and
include the user's reason; blanket slide/deck exceptions are rejected, and 12pt remains
the absolute floor. Do not create or use an exception file without explicit user
authorization. Use `--json` when a machine-readable audit record is useful.

pptxgenjs emits chart XML PowerPoint refuses to open, and every other tool
accepts: python-pptx opens those decks, LibreOffice renders them, the XSD
passes them. Every failure names its fix. Fix it in the generator and rebuild.

### Visual QA

Convert the slides to images (see [Converting to Images](#converting-to-images)) and inspect every one as a complete 16:9 page. Text that becomes readable only after cropping or zooming in does not pass. After staring at the generating code you tend to see what you expect rather than what rendered, so look at the images fresh (a subagent works well for this if you have one). User-visible defects to look for:

- **Text overflow or text cut off at a box or slide boundary — check this first.** It is the most common defect and always user-visible. (For a font the previewer renders unreliably per Typography, the preview is approximate: trust the ~10% slack you left, not its apparent fit.)
- Overlapping elements (text through shapes, lines through words, stacked elements)
- Source citations or footers colliding with content above
- Elements too close (< 0.3" gaps) or cards/sections nearly touching
- Uneven gaps (large empty area in one place, cramped in another)
- Insufficient margin from slide edges (< 0.5")
- Columns or similar elements not aligned consistently
- Low-contrast text (e.g., light gray text on cream-colored background)
- Template decoration mispositioned after text replacement — e.g., a title underline positioned for one line, but the replaced title wrapped to two
- Low-contrast icons (e.g., dark icons on dark backgrounds without a contrasting circle)
- Text boxes too narrow causing excessive wrapping
- Leftover placeholder content

If the user manually edits the deck after an audit, treat the edited file as a new
output: rerun content QA, file validation, typography audit, rendering, and full-page
visual inspection on that latest version.

## Converting to Images

Convert presentations to individual slide images for visual inspection:

Do not use OfficeCLI as a visual export path. Its HTML/SVG output is available only as an explicit
non-fidelity diagnostic preview (`--render html --non-fidelity-preview` for screenshots) and cannot
serve as final images or visual QA. For native acceptance, run `office_native_gate.py --require-render`;
the gate owns the isolated PowerPoint export and records `NATIVE_RENDER_PASS`. Use the existing
LibreOffice-runner adapter below for the visual compatibility render and human inspection.

```bash
python scripts/office/soffice.py --headless --convert-to pdf output.pptx
rm -f slide-*.jpg
pdftoppm -jpeg -r 150 output.pdf slide
ls -1 "$PWD"/slide-*.jpg
```

**Pass the absolute paths printed above directly to the view tool.** The `rm` clears stale images from prior runs. `pdftoppm` zero-pads based on page count: `slide-1.jpg` for decks under 10 pages, `slide-01.jpg` for 10-99, `slide-001.jpg` for 100+.

**After fixes, rerun all four commands above** — the PDF must be regenerated from the edited `.pptx` before `pdftoppm` can reflect your changes.

## Dependencies

`pptxgenjs` (npm, preinstalled — install only if `require('pptxgenjs')` fails) · `markitdown[pptx]`, `Pillow`, `defusedxml`, `lxml`, `python-pptx` (the runtime preflight checks the imports used by validation) · LibreOffice (`soffice`, auto-configured for sandboxed environments via `scripts/office/soffice.py`) · `pdftoppm` (Poppler)
