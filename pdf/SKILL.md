---
name: pdf
description: Use this skill whenever the user wants to do anything with PDF files, or needs a Word/DOCX/Office document rendered to PDF for visual inspection on this Windows machine. This includes reading or extracting text/tables from PDFs (including scanned PDFs via fitz rendering), combining or merging multiple PDFs into one, splitting PDFs apart, rotating pages, adding watermarks, creating new PDFs, encrypting/decrypting PDFs, extracting images, and background Office-to-PDF conversion through LibreOffice. PDF form filling is not covered by this skill.
---

# PDF Processing Guide

本地维护的 PDF 处理技能，针对 Windows 环境做了适配。当前机器已安装 Poppler 24.08.0；同时保留 PyMuPDF `fitz` 作为扫描件和页面检查的 Python 兜底。

## Windows Toolchain

本机 Poppler 程序位于 `%USERPROFILE%\poppler\poppler-24.08.0\Library\bin`，包括 `pdftoppm.exe`、`pdftocairo.exe`、`pdftotext.exe` 和 `pdfinfo.exe`。

调用 Poppler 时使用带 `.exe` 的程序名，或使用解析出的绝对路径。不要调用无扩展名的 `pdftoppm` 或 `pdfinfo`：Codex 运行时可能把它们解析为指向缺失 bundled `Library\bin` 的包装脚本，即使真正的 Poppler 已安装也会报路径错误。

PowerShell 解析和自检示例：

```powershell
$popplerBin = Join-Path $env:USERPROFILE 'poppler\poppler-24.08.0\Library\bin'
$pdftoppm = Join-Path $popplerBin 'pdftoppm.exe'
$pdftotext = Join-Path $popplerBin 'pdftotext.exe'
$pdfinfo = Join-Path $popplerBin 'pdfinfo.exe'

if (-not (Test-Path -LiteralPath $pdftoppm)) {
    $pdftoppm = (Get-Command pdftoppm.exe -ErrorAction Stop).Source
}
if (-not (Test-Path -LiteralPath $pdftotext)) {
    $pdftotext = (Get-Command pdftotext.exe -ErrorAction Stop).Source
}
if (-not (Test-Path -LiteralPath $pdfinfo)) {
    $pdfinfo = (Get-Command pdfinfo.exe -ErrorAction Stop).Source
}

& $pdftoppm -v
& $pdftotext -v
& $pdfinfo -v
```

`pdftoppm.exe` is the default rasterizer for page previews; use `pdftocairo.exe` when its output format or antialiasing is preferable. `pdftotext.exe` and `pdfinfo.exe` are the corresponding text and metadata utilities.

### Office documents to PDF

LibreOffice 26.2.4.2 is installed at `C:\Program Files\LibreOffice`. On Windows, call `soffice.com` directly so console output and exit status remain available. Use an isolated user profile with a proper file URI:

```powershell
$soffice = 'C:\Program Files\LibreOffice\program\soffice.com'
$inputDocument = 'C:\path\input.docx'
$outputDirectory = 'C:\path\rendered'
$profile = Join-Path $outputDirectory ('.lo-profile-' + [guid]::NewGuid())

New-Item -ItemType Directory -Path $outputDirectory,$profile -Force | Out-Null
$profileUri = ([System.Uri](Resolve-Path -LiteralPath $profile).Path).AbsoluteUri

& $soffice "-env:UserInstallation=$profileUri" `
    --headless --nologo --nodefault --nolockcheck --nofirststartwizard `
    --convert-to pdf --outdir $outputDirectory $inputDocument

if ($LASTEXITCODE -ne 0) {
    throw "LibreOffice conversion failed with exit code $LASTEXITCODE"
}
```

Do not use the installed `docx/scripts/office/soffice.py` on this machine. Both available Windows Python runtimes lack `socket.AF_UNIX`, so that helper fails before LibreOffice starts. Also avoid the bundled `documents/render_docx.py` conversion path until its Windows profile-URI handling is verified; bundle 26.715.12143 concatenates `file://` with a raw Windows path and can leave LibreOffice waiting. After direct PDF conversion, rasterize with the explicit Poppler `.exe` paths above.

## Quick Start

```python
from pypdf import PdfReader, PdfWriter

# Read a PDF
reader = PdfReader("document.pdf")
print(f"Pages: {len(reader.pages)}")

# Extract text
text = ""
for page in reader.pages:
    text += page.extract_text()
```

## Python Libraries

### pypdf - Basic Operations

#### Merge PDFs
```python
from pypdf import PdfWriter, PdfReader

writer = PdfWriter()
for pdf_file in ["doc1.pdf", "doc2.pdf", "doc3.pdf"]:
    reader = PdfReader(pdf_file)
    for page in reader.pages:
        writer.add_page(page)

with open("merged.pdf", "wb") as output:
    writer.write(output)
```

#### Split PDF
```python
reader = PdfReader("input.pdf")
for i, page in enumerate(reader.pages):
    writer = PdfWriter()
    writer.add_page(page)
    with open(f"page_{i+1}.pdf", "wb") as output:
        writer.write(output)
```

#### Extract Metadata
```python
reader = PdfReader("document.pdf")
meta = reader.metadata
print(f"Title: {meta.title}")
print(f"Author: {meta.author}")
print(f"Subject: {meta.subject}")
print(f"Creator: {meta.creator}")
```

#### Rotate Pages
```python
reader = PdfReader("input.pdf")
writer = PdfWriter()

page = reader.pages[0]
page.rotate(90)  # Rotate 90 degrees clockwise
writer.add_page(page)

with open("rotated.pdf", "wb") as output:
    writer.write(output)
```

### pdfplumber - Text and Table Extraction

#### Extract Text with Layout
```python
import pdfplumber

with pdfplumber.open("document.pdf") as pdf:
    for page in pdf.pages:
        text = page.extract_text()
        print(text)
```

#### Extract Tables
```python
with pdfplumber.open("document.pdf") as pdf:
    for i, page in enumerate(pdf.pages):
        tables = page.extract_tables()
        for j, table in enumerate(tables):
            print(f"Table {j+1} on page {i+1}:")
            for row in table:
                print(row)
```

#### Advanced Table Extraction
```python
import pandas as pd

with pdfplumber.open("document.pdf") as pdf:
    all_tables = []
    for page in pdf.pages:
        tables = page.extract_tables()
        for table in tables:
            if table:  # Check if table is not empty
                df = pd.DataFrame(table[1:], columns=table[0])
                all_tables.append(df)

# Combine all tables
if all_tables:
    combined_df = pd.concat(all_tables, ignore_index=True)
    combined_df.to_excel("extracted_tables.xlsx", index=False)
```

### reportlab - Create PDFs

#### Basic PDF Creation
```python
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

c = canvas.Canvas("hello.pdf", pagesize=letter)
width, height = letter

# Add text
c.drawString(100, height - 100, "Hello World!")
c.drawString(100, height - 120, "This is a PDF created with reportlab")

# Add a line
c.line(100, height - 140, 400, height - 140)

# Save
c.save()
```

#### Create PDF with Multiple Pages
```python
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
from reportlab.lib.styles import getSampleStyleSheet

doc = SimpleDocTemplate("report.pdf", pagesize=letter)
styles = getSampleStyleSheet()
story = []

# Add content
title = Paragraph("Report Title", styles['Title'])
story.append(title)
story.append(Spacer(1, 12))

body = Paragraph("This is the body of the report. " * 20, styles['Normal'])
story.append(body)
story.append(PageBreak())

# Page 2
story.append(Paragraph("Page 2", styles['Heading1']))
story.append(Paragraph("Content for page 2", styles['Normal']))

# Build PDF
doc.build(story)
```

#### Subscripts and Superscripts

**IMPORTANT**: Never use Unicode subscript/superscript characters (₀₁₂₃₄₅₆₇₈₉, ⁰¹²³⁴⁵⁶⁷⁸⁹) in ReportLab PDFs. The built-in fonts do not include these glyphs, causing them to render as solid black boxes.

Instead, use ReportLab's XML markup tags in Paragraph objects:
```python
from reportlab.platypus import Paragraph
from reportlab.lib.styles import getSampleStyleSheet

styles = getSampleStyleSheet()

# Subscripts: use <sub> tag
chemical = Paragraph("H<sub>2</sub>O", styles['Normal'])

# Superscripts: use <super> tag
squared = Paragraph("x<super>2</super> + y<super>2</super>", styles['Normal'])
```

For canvas-drawn text (not Paragraph objects), manually adjust font the size and position rather than using Unicode subscripts/superscripts.

## Common Tasks

### Read Scanned PDFs (Local-adapted, primary method)

Poppler is available for command-line rasterization. PyMuPDF (`fitz`) remains the preferred Python path when page-level inspection, blank-page filtering, or a self-contained renderer is more convenient. When `page.get_text()` returns 0 characters, the PDF is a scan. Render pages to PNG and read them visually (Claude Read tool) instead of OCR:

```python
# PYTHONIOENCODING=utf-8 for Chinese output on Windows
import fitz, os

doc = fitz.open('scanned.pdf')
out_dir = r'C:\Users\SanAn\AppData\Local\Temp\pages'
os.makedirs(out_dir, exist_ok=True)

for i in range(len(doc)):
    pix = doc[i].get_pixmap(dpi=120)   # 120 dpi is enough for A4 text
    pix.save(os.path.join(out_dir, f'p{i+1:02d}.png'))
```

Then filter blank pages by PNG file size before reading (< ~25KB at 120dpi is blank), and Read only the content-bearing pages. This avoids OCR entirely and preserves stamps/signatures/layout that OCR loses.

### OCR Alternative (requires poppler + tesseract)

Poppler is available on this machine; Tesseract is not currently installed. If OCR is explicitly required after Tesseract is installed, use:

```python
# Requires: pip install pytesseract pdf2image
import pytesseract
from pdf2image import convert_from_path

# Convert PDF to images
images = convert_from_path('scanned.pdf')

# OCR each page
text = ""
for i, image in enumerate(images):
    text += f"Page {i+1}:\n"
    text += pytesseract.image_to_string(image)
    text += "\n\n"

print(text)
```

### Precise Edits to Existing PDFs

Use this workflow when changing prices, quantities, dates, names, or other fields in an existing PDF while the surrounding layout, technical content, signatures, stamps, and supplier information must remain unchanged.

#### Inspect before editing

- Confirm the page count, classify each target region as editable text, a flattened scan, or a hybrid, and find every occurrence of the old value. A single page can contain more than one region type.
- For editable text, identify the exact text objects or content-stream operations that draw the old value. For scanned regions, inspect the raster background, table borders, stamps, and antialiased edge pixels around the old glyphs.
- Check all linked fields such as unit price, quantity, total, and uppercase amount before deciding the edit scope.
- Record the original text spans with `page.get_text("dict")`, including `font`, `size`, and `bbox`, then inspect page font resources with `page.get_fonts(full=True)`.
- A matching family name is not proof of a visual match. For example, an original PDF resource reported as `SimSun` can rasterize differently from newly embedded `SimSun Regular` because the PDF font object, subset, metrics, or encoding differs.
- If the needed glyph cannot be encoded reliably, the scan background cannot be repaired without changing protected graphics, or the replacement typography cannot reproduce the original layout, stop instead of synthesizing uncertain text. Provide copyable replacement text for a manual editor when that is the safer completion path.

#### Edit a copy

- Never overwrite the source. Use a clear suffix and keep the original available for comparison.
- For editable text, remove or rewrite only the original text objects; do not cover unrelated lines or graphics with an opaque rectangle.
- For scanned regions, patch only the old-glyph area with a sampled or verified background. Extend coverage through the old glyphs' antialiased edge pixels, but keep the patch inside table-border pixels so line color and thickness remain unchanged.
- Limit masks or redactions to the exact old-text rectangles. Preserve dates, signatures, stamps, company names, and technical content outside those rectangles.
- Prefer a verified original PDF font resource when it supports the replacement glyphs. If direct content-stream insertion with a Type0 font or CMap is necessary, use only confirmed encodings; never guess character codes.
- When subsetting a replacement font with `fontTools` and existing glyph IDs must stay aligned, set `fontTools.subset.Options().retain_gids = True`. This prevents glyph remapping errors but does not prove that the subset's metrics match the original PDF font.
- Treat mixed Latin, digit, sign, and unit sequences as nonbreaking layout tokens. Keep strings such as `TDD`, `2.5Gbps`, `10GE SFP+`, frequency ranges, and parenthesized units together unless the original document visibly breaks them.
- Reinspect font resources after redaction or page rewriting because some operations can remove or replace unembedded resources.
- Update every linked field consistently. A change is incomplete if one of the unit price, quantity, numeric total, or uppercase total still reflects the old value.

#### Verify the edited PDF

- Extract text from the final PDF and assert that every new value is present and every old field value is absent. For scanned regions, record that text verification is unavailable and rely on rendered inspection.
- Render every page with Poppler and open or render again with PyMuPDF. Check for overlap, clipping, shifted baselines, unreadable glyphs, and font-weight or width changes.
- For surgical edits, rasterize the source or reference and the result with the same renderer and DPI. Mask only the intended edit rectangles; pixels outside those masks should be identical. Any unexplained outside difference is a failed verification, not a harmless formatting detail.
- Inspect high-resolution crops inside every edited region, using 600 dpi when small glyph or border residues are difficult to see. Check for old punctuation, partial strokes, background seams, and changed border antialiasing; an outside-region pixel diff cannot detect these failures.
- Reinspect replacement spans and font resources. Automated text, geometry, and pixel checks cannot prove that typography matches the original. If the original font resource is unavailable, adjacent text differs visibly, or the user rejects the font, spacing, size, or overall layout, label the output experimental and do not present it as a final deliverable. Supply the replacement text for manual editing in WPS or another suitable PDF editor.

### Reference-Layout Composition

Use this workflow when a reference PDF already defines how several source pages should share one page, especially when source typography and table borders must remain unchanged.

#### Recover the reference geometry

- Record the reference `MediaBox`, `CropBox`, rotation, placement order, and every destination rectangle before composing.
- Inspect image and Form XObject rectangles or transformation matrices instead of estimating slots by eye. In PyMuPDF, use APIs such as `page.get_images(full=True)`, `page.get_image_rects(xref, transform=True)`, `page.get_xobjects()`, and `page.get_drawings()` as applicable to the page structure.
- When source pages contain large outer white margins, render only to measure a conservative non-white-content bounding box. Convert that pixel box back to PDF points, retain a small deterministic padding, and use it as the `clip`; do not rasterize the source page itself. Reinspect the crop so it does not cut faint rules, stamps, signatures, or antialiased border pixels.
- If the reference geometry cannot be recovered reliably, stop and request a layout decision rather than inventing placement coordinates.

#### Place source pages as vector content

- Create the destination page with the reference page size and rotation. Use `show_pdf_page(destination_rect, source_doc, page_number, clip=source_clip, keep_proportion=True)` or an equivalent page-placement API.
- Keep the placement order and spacing explicit. Do not redraw table borders, recreate text, or flatten vector pages into screenshots; those shortcuts can change font metrics, line color, line width, and antialiasing.
- If a source page is already a scan, preserve its embedded page content through page placement rather than recompressing it as a new image.

#### Append scanned supporting pages

- Use `insert_pdf` or an equivalent whole-page copy to append an existing scanned PDF. Preserve its page boxes, rotation, stamps, signatures, and image resources; do not rebuild the scan with ReportLab or a screenshot.
- Keep document-to-appendix pairing explicit when processing batches so a valid scan cannot be attached to the wrong product or record.

#### Verify the composition

- Parse the final file with `PdfReader(path, strict=True)`. Check page count, page order, `MediaBox`, `CropBox`, rotation, and expected text or source identifiers.
- Render every composed page at high resolution, normally 180-300 dpi, and inspect placement, clipping, whitespace, border continuity, and readability.
- For copied scan pages, render the standalone source and appended page with the same renderer, DPI, RGB colorspace, background, and alpha setting at two DPIs. Require equal pixel dimensions and equal raw-pixel hashes; a PDF-file hash is not useful because object numbering and compression may change.
- Compare the result with the reference layout. Any difference outside expected source-content regions must be zero or explicitly explained.
- Automated geometry and pixel checks cannot prove that typography looks identical. Keep the output provisional when the user has not accepted font, spacing, and overall layout.

### Add Watermark
```python
from pypdf import PdfReader, PdfWriter

# Create watermark (or load existing)
watermark = PdfReader("watermark.pdf").pages[0]

# Apply to all pages
reader = PdfReader("document.pdf")
writer = PdfWriter()

for page in reader.pages:
    page.merge_page(watermark)
    writer.add_page(page)

with open("watermarked.pdf", "wb") as output:
    writer.write(output)
```

### Password Protection
```python
from pypdf import PdfReader, PdfWriter

reader = PdfReader("input.pdf")
writer = PdfWriter()

for page in reader.pages:
    writer.add_page(page)

# Add password
writer.encrypt("userpassword", "ownerpassword")

with open("encrypted.pdf", "wb") as output:
    writer.write(output)
```

## Command-Line Tools

### Poppler

Use the resolved `.exe` paths from the Windows Toolchain section. For example:

```powershell
& $pdftoppm -png -r 120 input.pdf page
& $pdftotext input.pdf output.txt
& $pdfinfo input.pdf
```

### qpdf
```bash
# Merge PDFs
qpdf --empty --pages file1.pdf file2.pdf -- merged.pdf

# Split pages
qpdf input.pdf --pages . 1-5 -- pages1-5.pdf
qpdf input.pdf --pages . 6-10 -- pages6-10.pdf

# Rotate pages
qpdf input.pdf output.pdf --rotate=+90:1  # Rotate page 1 by 90 degrees

# Remove password
qpdf --password=mypassword --decrypt encrypted.pdf decrypted.pdf
```

## Quick Reference

| Task | Best Tool | Command/Code |
|------|-----------|--------------|
| Read scanned PDF | fitz + Read | Render to PNG, visual read |
| Render PDF pages | Poppler `pdftoppm.exe` | `& $pdftoppm -png -r 120 input.pdf page` |
| Convert Office document to PDF | LibreOffice `soffice.com` | Direct headless command with isolated file-URI profile |
| Merge PDFs | pypdf | `writer.add_page(page)` |
| Split PDFs | pypdf | One page per file |
| Extract text | pdfplumber | `page.extract_text()` |
| Extract tables | pdfplumber | `page.extract_tables()` |
| Create PDFs | reportlab | Canvas or Platypus |
| Precise field edits | PyMuPDF + verified font resource | Classify each region; edit a copy; inspect text, pixels, residues, and typography |
| Reference-layout composition | PyMuPDF `show_pdf_page` + `insert_pdf` | Recover slot geometry, preserve vector pages, append scans, and verify at multiple DPIs |
| Command line merge | qpdf | `qpdf --empty --pages ...` |

## Maintenance

本技能由用户针对本机 Windows 环境（Python 3.13 + Poppler 24.08.0 + LibreOffice 26.2.4.2）自行编写和维护。涉及的 Python 库（pypdf、pdfplumber、reportlab、PyMuPDF）均为公开开源项目，用法示例基于各自官方文档。精确编辑、参考版面拼版、多 DPI 验证等工作流为本机实践总结。
