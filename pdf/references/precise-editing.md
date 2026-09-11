# 精确编辑与参考拼版

## Precise Edits to Existing PDFs

Use this workflow when changing prices, quantities, dates, names, or other fields in an existing PDF while the surrounding layout, technical content, signatures, stamps, and supplier information must remain unchanged.

### Inspect before editing

- Confirm the page count, classify each target region as editable text, a flattened scan, or a hybrid, and find every occurrence of the old value. A single page can contain more than one region type.
- For editable text, identify the exact text objects or content-stream operations that draw the old value. For scanned regions, inspect the raster background, table borders, stamps, and antialiased edge pixels around the old glyphs.
- Check linked fields such as unit price, quantity, total, and uppercase amount against the authorized scope. Resolve clear dependencies from the document; ask only about a genuine meaning or scope conflict.
- Record the original text spans with `page.get_text("dict")`, including `font`, `size`, and `bbox`, then inspect page font resources with `page.get_fonts(full=True)`.
- A matching family name is not proof of a visual match. For example, an original PDF resource reported as `SimSun` can rasterize differently from newly embedded `SimSun Regular` because the PDF font object, subset, metrics, or encoding differs.
- If glyph encoding, scan repair, or typography is difficult, inspect the original resources and try feasible verified methods on a copy within the existing authorization. If the required fidelity remains unattainable, describe the exact difference and pause only that part; retain the draft as such and provide replacement text or another usable next step.

### Edit a copy

- Never overwrite the source. Use a clear suffix and keep the original available for comparison.
- For editable text, remove or rewrite only the original text objects; do not cover unrelated lines or graphics with an opaque rectangle.
- For scanned regions, patch only the old-glyph area with a sampled or verified background. Extend coverage through the old glyphs' antialiased edge pixels, but keep the patch inside table-border pixels so line color and thickness remain unchanged.
- Limit masks or redactions to the exact old-text rectangles. Preserve dates, signatures, stamps, company names, and technical content outside those rectangles.
- Prefer a verified original PDF font resource when it supports the replacement glyphs. If direct content-stream insertion with a Type0 font or CMap is necessary, use only confirmed encodings; never guess character codes.
- When subsetting a replacement font with `fontTools` and existing glyph IDs must stay aligned, set `fontTools.subset.Options().retain_gids = True`. This prevents glyph remapping errors but does not prove that the subset's metrics match the original PDF font.
- Treat mixed Latin, digit, sign, and unit sequences as nonbreaking layout tokens. Keep strings such as `TDD`, `2.5Gbps`, `10GE SFP+`, frequency ranges, and parenthesized units together unless the original document visibly breaks them.
- Reinspect font resources after redaction or page rewriting because some operations can remove or replace unembedded resources.
- Update linked fields covered by the request consistently. An authorized total update is incomplete if numeric and uppercase totals disagree; flag an unresolved scope conflict without changing unrelated fields.

### Verify the edited PDF

- Extract text from the final PDF and assert that every new value is present and every old field value is absent. For scanned regions, record that text verification is unavailable and rely on rendered inspection.
- Check the complete file structure and render the affected pages with a suitable renderer; expand to all pages or another renderer when rewriting could affect them or a discrepancy needs diagnosis. Check for overlap, clipping, shifted baselines, unreadable glyphs, and font-weight or width changes.
- For surgical edits, rasterize the source or reference and the result with the same renderer and DPI. Mask only the intended edit rectangles; pixels outside those masks should be identical. Any unexplained outside difference is a failed verification, not a harmless formatting detail.
- Inspect high-resolution crops inside every edited region, using 600 dpi when small glyph or border residues are difficult to see. Check for old punctuation, partial strokes, background seams, and changed border antialiasing; an outside-region pixel diff cannot detect these failures.
- Reinspect replacement spans and font resources. Automated text, geometry, and pixel checks cannot prove that typography matches the original. An unavailable original font calls for a verified alternative, not automatic abandonment. Resolve visible font, spacing, size, or layout differences where feasible; if differences remain, label the output a draft and explain them rather than presenting it as final.

## Reference-Layout Composition

Use this workflow when a reference PDF already defines how several source pages should share one page, especially when source typography and table borders must remain unchanged.

### Recover the reference geometry

- Record the reference `MediaBox`, `CropBox`, rotation, placement order, and every destination rectangle before composing.
- Inspect image and Form XObject rectangles or transformation matrices instead of estimating slots by eye. In PyMuPDF, use APIs such as `page.get_images(full=True)`, `page.get_image_rects(xref, transform=True)`, `page.get_xobjects()`, and `page.get_drawings()` as applicable to the page structure.
- When source pages contain large outer white margins, render only to measure a conservative non-white-content bounding box. Convert that pixel box back to PDF points, retain a small deterministic padding, and use it as the `clip`; do not rasterize the source page itself. Reinspect the crop so it does not cut faint rules, stamps, signatures, or antialiased border pixels.
- If the reference geometry is unclear, investigate page boxes, resources, and rendered measurements first. Ask only when an unresolved placement choice would materially change the result; continue independent work.

### Place source pages as vector content

- Create the destination page with the reference page size and rotation. Use `show_pdf_page(destination_rect, source_doc, page_number, clip=source_clip, keep_proportion=True)` or an equivalent page-placement API.
- Keep the placement order and spacing explicit. Do not redraw table borders, recreate text, or flatten vector pages into screenshots; those shortcuts can change font metrics, line color, line width, and antialiasing.
- If a source page is already a scan, preserve its embedded page content through page placement rather than recompressing it as a new image.

### Append scanned supporting pages

- Use `insert_pdf` or an equivalent whole-page copy to append an existing scanned PDF. Preserve its page boxes, rotation, stamps, signatures, and image resources; do not rebuild the scan with ReportLab or a screenshot.
- Keep document-to-appendix pairing explicit when processing batches so a valid scan cannot be attached to the wrong product or record.

### Verify the composition

- Parse the final file with `PdfReader(path, strict=True)`. Check page count, page order, `MediaBox`, `CropBox`, rotation, and expected text or source identifiers.
- Render every composed page at high resolution, normally 180-300 dpi, and inspect placement, clipping, whitespace, border continuity, and readability.
- For copied scan pages, render the standalone source and appended page with the same renderer, DPI, RGB colorspace, background, and alpha setting at two DPIs. Require equal pixel dimensions and equal raw-pixel hashes; a PDF-file hash is not useful because object numbering and compression may change.
- Compare the result with the reference layout. Any difference outside expected source-content regions must be zero or explicitly explained.
- Automated geometry and pixel checks cannot prove that typography looks identical. Inspect the final rendered output yourself; report unresolved font, spacing or layout differences. User sign-off is required only when explicitly requested.
