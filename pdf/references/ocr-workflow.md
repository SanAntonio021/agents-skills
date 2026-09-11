# OCR 加工与全文提取

Do not decide that a PDF is digital or scanned from `page.get_text()` alone. A page number, watermark, header, or damaged OCR layer can produce a few characters while the body remains an image.

When searchable output or reliable full-document text is needed, resolve `scripts/ocr_pdf.ps1` relative to the parent skill directory and use the wrapper:

```powershell
& $ocrWrapper `
    -InputPdf 'C:\path\document.pdf' `
    -OutputDirectory 'C:\项目\过程文件\文档识别' `
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

The wrapper never overwrites the input or an existing output. It stages work in a unique directory and publishes only after SHA-256, page count, dimensions, rotation, PyMuPDF rendering, Poppler rendering, `pdfinfo`, and strict pypdf checks pass. Always pass `-OutputDirectory` inside the task process directory. Successful process outputs are:

- `<name>_ocr.pdf`
- `<name>_ocr.txt`, extracted from the completed PDF with `pdftotext -layout`; OCRmyPDF sidecar text is not the full document
- `<name>_ocr.log`
- `<name>_ocr.status.json`

After validation, automatically copy the requested PDF and/or full text to versioned project-root filenames and verify their hashes; logs, status records and render diagnostics stay in the process directory. On failure, no successful output names are created. Diagnostics remain in the reported `.pdf-ocr-run-*` directory on both success and failure, until explicit ChatNote cleanup.

For visual reading or review of tables, formulas, stamps, handwriting, and complex layouts, render representative pages even after OCR. OCR preserves the page image in the PDF but plain text does not preserve table structure or formula semantics. Use Poppler or PyMuPDF:

```python
import fitz, os, tempfile

doc = fitz.open('scanned.pdf')
out_dir = os.path.join(task_process_dir, 'pdf-pages')  # task_process_dir is the resolved task directory
os.makedirs(out_dir, exist_ok=True)

page_indices = [0]  # zero-based; select pages relevant to the question, expand when needed
for i in page_indices:
    pix = doc[i].get_pixmap(dpi=120)
    pix.save(os.path.join(out_dir, f'p{i+1:02d}.png'))
```

Current machine paths, pinned versions, installer hash, and language-model hashes are recorded in [ocr-runtime.md](ocr-runtime.md).


## 读取与参数边界

普通查询先使用现有文字层或相关原页图像；需要 OCR 才进入识别。位置未知时可扩大范围直至全文，辅助识别结果留在过程目录，不自动交付新 PDF。包装器处理整份输入，不提供页码或页码范围参数；如需先抽取页面，使用现有 PDF 工具生成过程副本并保留原页对应关系。

包装器现有参数为 `InputPdf`、`Languages`、`Mode`、`OutputDirectory`、`Deskew`、`Jobs`、`TimeoutSeconds`。本说明不改变接口和程序的完整验证链。
