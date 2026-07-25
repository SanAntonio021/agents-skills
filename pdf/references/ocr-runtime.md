# Local OCR Runtime Record

Recorded: 2026-07-24

This file records the verified local installation used by `scripts/ocr_pdf.ps1`.
It is a machine-specific record, not a portable installer.

## Runtime

- Isolated Python: `C:\Users\SanAn\AppData\Local\pdf-ocr\.venv\Scripts\python.exe`
- Base interpreter: `C:\Python313\python.exe`, CPython 3.13.1
- uv: 0.9.26
- OCRmyPDF: 17.8.1
- PyMuPDF: 1.27.1
- pypdf: 6.10.0
- pypdfium2: 5.12.1
- Poppler: 24.08.0 at `C:\Users\SanAn\poppler\poppler-24.08.0\Library\bin`

## Tesseract

- Executable: `C:\Users\SanAn\AppData\Local\Programs\Tesseract-OCR\tesseract.exe`
- Version: 5.4.0.20240606
- tessdata: `C:\Users\SanAn\AppData\Local\Programs\Tesseract-OCR\tessdata`
- Available languages: `eng`, `chi_sim`, `chi_tra`, `osd`
- No global `PATH` or `TESSDATA_PREFIX` value was added. The wrapper sets required
  values only for its child process.

The UB-Mannheim installer was downloaded from:

`https://github.com/UB-Mannheim/tesseract/releases/download/v5.4.0.20240606/tesseract-ocr-w64-setup-5.4.0.20240606.exe`

- Installer SHA-256: `C885FFF6998E0608BA4BB8AB51436E1C6775C2BAFC2559A19B423E18678B60C9`
- This matches the SHA-256 published by WinGet for `UB-Mannheim.TesseractOCR`
  5.4.0.20240606.
- The installed `eng` and `osd` data came from the installer.
- `chi_sim` and `chi_tra` were fetched from the same `tessdata_fast` source used
  by the installer, pinned to commit
  `87416418657359cb625c412a48b6e1d6d41c29bd`.

| File | SHA-256 |
|---|---|
| `eng.traineddata` | `7D4322BD2A7749724879683FC3912CB542F19906C83BCC1A52132556427170B2` |
| `chi_sim.traineddata` | `A5FCB6F0DB1E1D6D8522F39DB4E848F05984669172E584E8D76B6B3141E1F730` |
| `chi_tra.traineddata` | `529C5B5797D64B126065CD55F2BB4C7FD7B15790798091B1FF259941A829330B` |
| `osd.traineddata` | `9CF5D576FCC47564F11265841E5CA839001E7E6F38FF7F7AACF46D15A96B00FF` |

## Optional Tools

Ghostscript and qpdf command-line executables were not installed. OCRmyPDF
17.8.1 completed the `--output-type pdf` canary with pypdfium2, so neither is
required for the current searchable-PDF pipeline. Re-evaluate Ghostscript only
if a future task requires PDF/A output.

## Generated Canary

The generated one-page image-only PDF completed without Ghostscript. Input and
output page count, point dimensions, rotation, and 150 dpi rendered-pixel
SHA-256 were identical. The input SHA-256 was
`DFDAAB4DCE03E635429E4F1D62D1D8546D1307707E81DF090E71649145E275E3`.

Language A/B on the same page found that `chi_sim` preserved the Chinese
keywords materially better than `chi_sim+eng` while still reading the English
line. This is only a generated canary, not a claim that real-document Chinese
accuracy has passed. Use a representative one-page A/B before a large job.
