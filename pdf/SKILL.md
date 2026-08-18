---
name: pdf
description: Use this skill whenever the user wants to read, create, inspect, convert, OCR, repair, or otherwise process PDF files on this Windows machine. Trigger it for native digital PDFs, scanned or image-only PDFs, mixed PDFs, damaged or garbled text layers, searchable-PDF creation, full-text extraction, merging, splitting, rotation, watermarks, encryption, image extraction, precise field edits, reference-layout composition, and Office-to-PDF conversion. PDF form filling is not covered (upstream forms.md and scripts excluded for license reasons).
---

# PDF Processing Guide

本地维护的 PDF 处理技能，针对 Windows 环境做了适配。当前机器已安装 Poppler 24.08.0、隔离的 OCRmyPDF/PyMuPDF 环境和 Tesseract 中文/英文语言包。扫描检测、OCR 路由、全文提取和结果验证统一由 `scripts/ocr_pdf.ps1` 完成。

## Office source route

当输入实际是 `.pptx`、`.docx` 或 `.xlsx`，且目标是读取、结构检查或受限新副本编辑时，先经
本 skill 内的 OfficeCLI bridge：

```powershell
python <skill-root>\scripts\officecli_bridge.py view source.pptx text
python <skill-root>\scripts\officecli_bridge.py validate source.pptx
```

桥接器固定使用 OfficeCLI `1.0.144`，每次调用都会先核对文件存在、SHA-256 和报告版本。普通
PDF/Office 文档任务不会联网下载或自动修复；只有用户明确运行
`python <skill-root>\scripts\repair_officecli.py --repair` 才会修复默认本机路径。设置
`OFFICECLI_EXE` 时也必须通过相同校验，路径错误应自行修正或取消环境变量；修复脚本不会改写
覆盖路径。

桥接器会隔离输入副本并核对源文件 SHA-256。不要通过 OfficeCLI 导出 Office-to-PDF：固定的
OfficeCLI `1.0.144` 没有 exporter plugin，bridge 会提前拒绝 `view ... pdf`。OfficeCLI
`--render native --allow-native` 只保留为诊断，失败会输出
`officecli_native_diagnostic_failed`、原始 stderr 和退出码；它不证明 Office 未安装，也不
提供发布证据。需要 Microsoft Office 原生打开/导出证据时，使用四个 Office 技能同构的
`office_native_gate.py`；桥接器不会关闭 Office。纯 PDF 仍按下面的 Poppler、PyMuPDF、pypdf
和 OCR 路径处理，不把 OfficeCLI 当作 PDF 编辑器或保真渲染器。

## Acceptance layers

Office 源文件和纯 PDF 分开记录验收层：

- `STATIC_PASS`: OfficeCLI/OOXML 或 PDF 结构、文本、哈希和机器检查通过。
- `LO_RENDER_PASS`: Office 源文件通过 `libreoffice-runner` 的兼容转换/渲染；这是默认的
  Office-to-PDF 路径。
- `NATIVE_OPEN_PASS`: 只有任务明确要求原生 Office 兼容性时，独立 gate 打开隔离副本。
- `NATIVE_RENDER_PASS`: PPTX/DOCX gate 的原生导出和页面栅格化通过；纯 PDF 不使用此层。

OfficeCLI `validate` 通过不等于 PowerPoint、Word 或 Excel 原生可打开。需要原生证据时，按
输入格式调用同构 gate，例如：

```powershell
python <skill-root>\scripts\office_native_gate.py check source.pptx `
  --format pptx --json --allow-office-com --require-render
python <skill-root>\scripts\office_native_gate.py check source.docx `
  --format docx --json --allow-office-com --require-render
python <skill-root>\scripts\office_native_gate.py check source.xlsx `
  --format xlsx --json --allow-office-com
```

gate 返回 `PASS`、`FAIL_OPEN`、`FAIL_RENDER`、`APP_UNAVAILABLE`、`UNVERIFIED` 或
`UNSAFE_PROCESS`，并保留真实阶段和异常。纯 PDF 的验收链不因 OfficeCLI native 状态改变；
Office 转 PDF 继续以 `libreoffice-runner` 为主。

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

对于 Office 源文件，不通过 OfficeCLI 导出 PDF。需要无界面兼容转换时，Windows 上所有
LibreOffice 转换必须使用已安装的 `libreoffice-runner` skill。先读取该 skill 的 `SKILL.md`
和调用契约，再解析其 `scripts/libreoffice_run.py` 绝对路径：

```powershell
& 'C:\Python313\python.exe' $libreOfficeRunner pdf $inputDocument $outputPdf `
    --json-out $reportJson
```

Do not run `soffice`, `soffice.exe`, or `soffice.com` directly. Do not use bundled helpers that start LibreOffice themselves. The runner serializes access, gives each call an isolated profile, refuses to overwrite an existing output, and returns JSON on stdout. After conversion, rasterize with the explicit Poppler `.exe` paths above.

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

### Scanned, mixed, and damaged-text PDFs

Do not decide that a PDF is digital or scanned from `page.get_text()` alone. A page number, watermark, header, or damaged OCR layer can produce a few characters while the body remains an image.

When searchable output or reliable full-document text is needed, resolve `scripts/ocr_pdf.ps1` relative to this `SKILL.md` and use the wrapper:

```powershell
& $ocrWrapper `
    -InputPdf 'C:\path\document.pdf' `
    -Languages 'chi_sim' `
    -Mode auto
```

`-Languages` is mandatory because Tesseract cannot reliably choose the document language:

- English-only material: `eng`
- Simplified Chinese or Chinese-first mixed material: start with `chi_sim`
- Traditional Chinese or Chinese-first mixed material: start with `chi_tra`
- Add `+eng` or combine `chi_sim+chi_tra` only after a one-page A/B test. On the generated local canary, `chi_sim` recognized Chinese materially better than `chi_sim+eng` while still recognizing the English line.

Automatic routing uses page text quality and image coverage:

- Native digital PDF or a sound existing OCR layer: no OCR; copy the input to a new output and extract full text.
- Pure scan or document-level mixture of digital and image-only pages: OCRmyPDF `--mode skip`.
- Same-page sparse text plus a large scan, or an obviously damaged text layer: OCRmyPDF `--mode redo`.

Use `-Deskew` only when the user requests it or a rendered page shows clear skew. Deskew changes page pixels and requires stronger visual comparison. Override `-Mode` only when the automatic decision is known to be wrong and record why.

The wrapper never overwrites the input or an existing output. It stages work in a unique directory and publishes only after SHA-256, page count, dimensions, rotation, PyMuPDF rendering, Poppler rendering, `pdfinfo`, and strict pypdf checks pass. Successful outputs are:

- `<name>_ocr.pdf`
- `<name>_ocr.txt`, extracted from the completed PDF with `pdftotext -layout`; OCRmyPDF sidecar text is not the full document
- `<name>_ocr.log`
- `<name>_ocr.status.json`

On failure, no official output names are created. Diagnostic files remain in the reported `.pdf-ocr-run-*` directory.

For visual reading or review of tables, formulas, stamps, handwriting, and complex layouts, render representative pages even after OCR. OCR preserves the page image in the PDF but plain text does not preserve table structure or formula semantics. Use Poppler or PyMuPDF:

```python
import fitz, os

doc = fitz.open('scanned.pdf')
out_dir = r'C:\Users\SanAn\AppData\Local\Temp\pages'
os.makedirs(out_dir, exist_ok=True)

for i in range(len(doc)):
    pix = doc[i].get_pixmap(dpi=120)
    pix.save(os.path.join(out_dir, f'p{i+1:02d}.png'))
```

Current machine paths, pinned versions, installer hash, and language-model hashes are recorded in [references/ocr-runtime.md](references/ocr-runtime.md).

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

## Quick Reference

| Task | Best Tool | Command/Code |
|------|-----------|--------------|
| OCR scanned/mixed PDF | `scripts/ocr_pdf.ps1` | Explicit languages, automatic `none`/`skip`/`redo`, validated outputs |
| Review tables/formulas/stamps | PyMuPDF or Poppler + visual read | Render representative pages after OCR |
| Render PDF pages | Poppler `pdftoppm.exe` | `& $pdftoppm -png -r 120 input.pdf page` |
| Convert Office document to PDF | `libreoffice-runner` skill | Use its queued `libreoffice_run.py pdf` command |
| Merge PDFs | pypdf | `writer.add_page(page)` |
| Split PDFs | pypdf | One page per file |
| Extract text | pdfplumber | `page.extract_text()` |
| Extract tables | pdfplumber | `page.extract_tables()` |
| Create PDFs | reportlab | Canvas or Platypus |
| Precise field edits | PyMuPDF + verified font resource | Classify each region; edit a copy; inspect text, pixels, residues, and typography |
| Reference-layout composition | PyMuPDF `show_pdf_page` + `insert_pdf` | Recover slot geometry, preserve vector pages, append scans, and verify at multiple DPIs |

## Provenance

Derived from the upstream `anthropics/skills` pdf skill (last upstream content update ~2025-10). Local adaptations: explicit Poppler 24.08.0 executable paths, queued Office-to-PDF conversion through `libreoffice-runner`, deterministic OCRmyPDF/Tesseract routing for scanned, mixed, and damaged-text PDFs, complete post-OCR text extraction, input/output hashes and multi-engine validation, scanned PDF reading via fitz render-to-PNG, precise existing-PDF edits with original-font checks, high-resolution residue checks, a user visual-acceptance gate, vector multi-source composition with reference-geometry recovery, whole-page scan attachment, multi-DPI rendered-hash verification, and Windows path conventions. Upstream Proprietary files (LICENSE.txt, forms.md, reference.md, scripts/) are not included; refer to the upstream skill if those features are needed.
