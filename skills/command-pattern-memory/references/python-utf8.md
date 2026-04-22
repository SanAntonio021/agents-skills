# Python UTF-8

### Pattern: powershell-python-utf8-inline
- scenario: PowerShell plus Python one-liner with Unicode-safe output
- use_when: A command uses `python -c` or similar inline Python in PowerShell and the task may emit Chinese text, bullet characters, or other non-ASCII output.
- shell: PowerShell
- validated_shape: `$env:PYTHONIOENCODING='utf-8'; $env:PYTHONUTF8='1'; python -c "<PYTHON_CODE>"`
- substitute_only: `<PYTHON_CODE>`
- preflight: `Get-Command "python"`; keep Python code compact enough for inline execution; switch to a script file if quoting becomes fragile
- preflight: For inline Python that writes files under a Windows path containing non-ASCII characters, prefer discovering the parent with `Path.cwd()` and give the output file an ASCII-only filename; if the inline source itself shows signs of character mangling, keep workbook sheet titles ASCII too and reserve Unicode for cell contents
- preflight: For Excel or document generation tasks with many Chinese strings, prefer a UTF-8 `.py` script on disk over an inline here-string; let PowerShell invoke `python .\script.py` and keep the Unicode content inside the script file instead of inside the shell command
- preflight: For inline verification of a Chinese-named `.xlsx`, avoid hardcoding the Chinese path or Chinese worksheet title inside the here-string; instead let Python discover the target via `Path.cwd().glob('*.xlsx')`, print `wb.sheetnames` if needed, and access the sheet by index such as `wb.worksheets[2]`
- preflight: If you must open one exact Chinese-named workbook or script rather than discover it, bind the absolute path in PowerShell first and pass it as a CLI argument, for example `$p = "D:\path\中文文件.xlsx"; @'<PY>'@ | python -X utf8 - $p`; this avoids the path literal being mangled before Python receives `sys.argv[1]`
- env: `PYTHONIOENCODING=utf-8`; `PYTHONUTF8=1`
- avoid: Bare `python -c` with default Windows encoding; large multiline code embedded without checking quoting; hardcoding Chinese paths or filenames inside PowerShell-delivered inline Python when the same targets can be discovered from `Path.cwd()` or matched with ASCII-only rules; assuming UTF-8 env vars alone will protect non-ASCII workbook sheet titles or output filenames inside an inline here-string; generating a workbook with many Chinese cell values from an inline shell-delivered Python block when a UTF-8 script file would avoid mangling
- avoid: Referring to Chinese worksheet names like `wb['方案2B_拆分']` inside an inline here-string when the same workbook can be reached safely as `wb.worksheets[2]`
- avoid: Using a Python raw string that ends with a backslash inside inline PowerShell-delivered code, such as `r'\\?\';` Python treats that as an unterminated string. For Windows prefix literals like `\\?\`, prefer an ordinary escaped string such as `'\\\\?\\'`
- success_signal: Python runs without encoding errors and emits expected UTF-8 text in PowerShell
- capture_rule: Update this entry when a more reliable inline quoting or UTF-8 setup is validated across multiple tasks; if a first attempt fails because non-ASCII path literals are mangled before Python receives them, prefer a corrected shape that lets Python enumerate files in the working directory and identify targets with ASCII-safe patterns; for file-writing tasks in non-ASCII directories, a stable fallback is `Path.cwd() / "<ASCII_OUTPUT_NAME>"` plus ASCII workbook sheet titles, while leaving worksheet cell text in Unicode; when the worksheet cell text itself is large Unicode content, switch from inline Python to a UTF-8 script file and run it from PowerShell
- capture_rule: For read/verify tasks on Chinese-named workbooks, a stable fallback is `p = sorted(Path.cwd().glob('*.xlsx'), key=lambda x: x.stat().st_mtime, reverse=True)[0]` followed by `ws = wb.worksheets[index]`; then address columns by numeric position instead of Chinese header strings if the inline shell path is still at risk
- capture_rule: When discovery by glob is unsafe because multiple `.xlsx` files exist, a validated recovery shape is `PowerShell variable -> python stdin script -> sys.argv[1]`; this works better than embedding the same Chinese absolute path directly inside the inline Python block

### Recovery Addendum: exact-path-via-environment
- scenario: Inline Python needs one exact Chinese-named PDF/XLSX and both direct path literals and hardcoded Chinese worksheet names are unreliable under PowerShell.
- validated_shape: `PowerShell resolves exact path with Get-ChildItem/Test-Path -> stores it in $env:TARGET_* -> @'<PY>'@ | python -X utf8 -`, then Python reads `os.environ['TARGET_*']`
- example_shape: `$env:TARGET_PDF = (Get-ChildItem -LiteralPath . -Filter '*.pdf' | Where-Object { $_.Name -like '*北亿纤通*V3.057*' } | Select-Object -First 1 -ExpandProperty FullName); @'<PY>'@ | python -X utf8 -`
- example_shape: `$env:TARGET_XLSX = (Get-ChildItem -LiteralPath . -Filter '*RFoF*xlsx' | Sort-Object LastWriteTime -Descending | Select-Object -First 1 -ExpandProperty FullName); @'<PY>'@ | python -X utf8 -`
- use_when: Multiple workbook candidates exist, the target name contains Chinese, and inline Python must inspect or extract without creating a standalone script first.
- avoid: Embedding the same Chinese absolute path directly inside the here-string, or using Chinese worksheet names inside inline Python when `wb.worksheets[index]` is sufficient.
- success_signal: Python opens the exact target from `os.environ[...]` and completes text extraction or workbook inspection without `Invalid argument` / mangled-path errors.

### Recovery Addendum: chinese-header-columns-by-index
- scenario: Inline Python must edit an Excel workbook under PowerShell, the workbook/sheets/headers contain Chinese, and a first attempt using header-name dictionaries such as `col['品牌']` fails because the header literals are mangled in the here-string.
- validated_shape: `PowerShell env vars for source/output paths -> @'<PY>'@ | python -X utf8 -`, then Python opens the workbook from `os.environ[...]`, locates the target row using ASCII substrings in existing cells, and writes back by numeric column index instead of Chinese header names.
- use_when: The target workbook path is best passed through environment variables and the edit only touches a known small set of columns.
- avoid: Reconstructing a header-name dictionary when the same edit can be expressed with inspected numeric columns from a prior read/verify pass.
- success_signal: Python finds the intended row, writes the target cells, and saves the workbook copy without `KeyError` from mangled Chinese header strings.
