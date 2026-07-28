# Native Word equations (OMML)

Use this reference when formulas stored as LaTeX or visible text in an existing DOCX must become
editable Word equations. The goal is structured Office Math Markup Language (OMML), preserved
surrounding text and layout, and a rendered document with no clipped formula rows.

## Required outcome

- Preserve the source file and write a new output file.
- Keep ordinary text, paragraph order, formula positions, styles, drawings, and relationships intact.
- Use structured `m:oMath` or `m:oMathPara` objects. A complex formula encoded as one `m:t` run is
  editable text inside an equation container, but it is not a properly structured Word equation.
- Limit package changes to the parts required by the task. Replacing formula text in an existing
  body normally changes only `word/document.xml`.

## Conversion workflow

### 1. Inspect and collect

Parse `word/document.xml` with a namespace-aware XML parser. Identify formula delimiters and
dedicated formula paragraphs from the actual document; do not assume every document uses the same
markers or paragraph style. Record each formula's paragraph and inline position before replacement.

Batch unique formulas with stable text markers such as `EQ0001`. This avoids calling a converter for
every occurrence and gives a deterministic mapping from source formula to generated OMML.

### 2. Generate structured OMML

Pandoc can convert a small Markdown batch containing TeX math to DOCX. Read the generated
`word/document.xml`, find each marker, and deep-copy its `m:oMath` tree into the target document.
Keep inline equations inline. Put display equations in dedicated equation paragraphs rather than
mixing them into ordinary body text.

Inspect Pandoc stderr for conversion failures. Also inspect the resulting XML: successful command
exit alone does not prove schema-valid or visually complete OMML.

### 3. Handle aligned and multiline formulas

Pandoc output for an `aligned` environment can retain visible `&` alignment markers. Rebuild such
formulas as `m:eqArr`, with one `m:e` element per row. Convert each row to structured OMML first,
then copy its math children into the corresponding array row. The final math text must not contain
the source `&` markers.

Use the same principle for matrices and piecewise functions: preserve their row and cell structure;
do not flatten them into a single text run.

### 4. Prevent formula-row clipping

An exact paragraph line height can show only one row of a matrix, piecewise function, or equation
array even when all OMML rows are present. Apply automatic line spacing directly to display-equation
paragraphs. A practical starting point is:

```xml
<w:spacing w:before="40" w:after="40" w:line="240" w:lineRule="auto"/>
```

Use a local paragraph override when only equation paragraphs need the fix; do not change the global
body or equation style without a document-wide reason. Insert `w:spacing` in valid `CT_PPr` child
order, before elements such as `w:ind`, `w:jc`, `w:rPr`, and `w:sectPr`.

## Known Pandoc OMML repairs

Run schema validation on the generated OMML. In Pandoc-generated output, check these known cases:

1. If the same `m:rPr` contains both `m:nor` and `m:sty`, keep `m:nor` and remove `m:sty`; they are
   alternate schema branches.
2. If an `m:mcPr` contains both `m:count` and `m:mcJc`, place `m:count` before `m:mcJc`.
3. If an aligned formula exposes `&`, rebuild it as `m:eqArr` rather than hiding or deleting only the
   rendered character.

Do not assume every document needs every repair. Count and report the repairs actually applied.

## Diagnose boxes and invisible spacing characters

A square-looking mark in Word can be an unsupported glyph, a literal Unicode character inside the
equation, or a nonprinting mark exposed by the current Word display settings. A screenshot alone
cannot distinguish these cases. Inspect the saved OOXML and a normal rendered page before editing.

For each suspicious occurrence, record the Unicode code point, containing `m:oMath` object, formula
number or paragraph, and surrounding `m:r` / `m:t` structure. Do not bulk-delete characters such as
`U+200B`, `U+2001`, `U+2005`, or `U+2009`: the same code point can be a redundant converter artifact
in one formula and an intentional placeholder or mathematical spacing character in another.

Remove only occurrences whose deletion preserves the formula text, OMML structure, and rendered
meaning. Delete the smallest possible node or text fragment. Preserve spaces that separate a value
from its unit, such as the space in `256 MHz`, and preserve structural placeholders that do not
produce a visible defect. If the mark exists only because Word is showing formatting marks, do not
change the document merely to hide the user-interface indicator.

After cleanup:

- compare per-code-point and per-formula occurrence counts before and after;
- replay the approved deletions in memory and confirm that the result matches the output XML;
- compare package entry sets and hashes, explaining every changed part;
- render every modified formula page and representative pages containing retained characters;
- check the normal reading view for boxes, clipping, changed spacing, or altered formula structure.

## Validation

### Package and schema

- Run `zipfile.testzip()` or an equivalent package-integrity check.
- Compare package entry sets and hashes against the source. Explain every changed part.
- Run the DOCX validator against the source:

```bash
python scripts/office/validate.py output.docx --original source.docx
```

On Windows, if the validator fails while decoding its own subprocess output, rerun with
`PYTHONUTF8=1` and `PYTHONIOENCODING=utf-8`. A console-codepage exception is not evidence of a DOCX
schema defect.

### Semantic equivalence

Build paragraph skeletons for source and target. Replace each source formula with one marker and
each target `m:oMath` object with the same marker, then compare paragraph count, ordinary text, and
marker positions. Also verify:

- expected inline and display formula counts;
- no empty `m:oMath` objects;
- no raw LaTeX delimiters or commands in visible text;
- no visible alignment `&` inside math text;
- no unexpected changes outside formula positions and approved paragraph formatting.

### Rendered pages

Render the output through the approved Office conversion path and inspect it. On Windows, use the
`libreoffice-runner` path required by the global rules; do not call `soffice` directly. Check:

- total page count and any page-limit requirement;
- blank pages and content touching page edges;
- every page containing a matrix, piecewise function, or equation array at enlarged scale;
- headings and body paragraphs before and after display equations;
- formula width, row visibility, and surrounding spacing.

Do not treat XML presence as proof of visible completeness. Multiline formulas require a rendered
page check.

## Acceptance checklist

- Source preserved; output uses a new path.
- Formula count and positions match the source markers.
- Structured OMML passes schema validation.
- Ordinary text and paragraph count are unchanged unless the task explicitly says otherwise.
- Multiline formulas show all rows after rendering.
- Page count stays within the requested limit.
- Validation evidence records formula counts, changed package parts, and rendered-page results.
