# Markdown Read UTF-8

### Pattern: powershell-markdown-read-utf8
- scenario: Read Markdown or other plain-text files that may contain Chinese or other non-ASCII text
- use_when: The task needs to read a `.md`, `.txt`, or similar text file in PowerShell and either the path or the contents may contain Chinese, or a default first read has already shown encoding risk or mojibake
- shell: PowerShell
- validated_shape: `[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; $OutputEncoding = [Console]::OutputEncoding; Get-Content -LiteralPath "<INPUT_PATH>" -Encoding UTF8 -Raw`
- numbered_review_shape: `[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; $OutputEncoding = [Console]::OutputEncoding; $i=1; Get-Content -LiteralPath "<INPUT_PATH>" -Encoding UTF8 | ForEach-Object { '{0,4}: {1}' -f $i, $_; $i++ }`
- substitute_only: `<INPUT_PATH>`
- preflight: `Test-Path "<INPUT_PATH>"`; confirm the target is a text file rather than a binary export
- env: Set PowerShell stdout to UTF-8 in the same command when the file contents will be captured by `shell_command`
- avoid: Bare `Get-Content "<INPUT_PATH>"` or bare `Get-Content -Raw "<INPUT_PATH>"`; assuming quoted Chinese paths are sufficient without `-LiteralPath`; relying on default encoding for Chinese Markdown; using `-Encoding UTF8` without also fixing PowerShell stdout when captured output already showed mojibake; reading by path expansion when `-LiteralPath` is available
- success_signal: The file contents are returned without encoding errors or garbling in captured shell output, with full text preserved for inspection
- capture_rule: If a first read failed or produced mojibake and the corrected explicit-UTF-8 read with UTF-8 stdout succeeded, update this entry or the nearest sibling text-read pattern instead of leaving the fix only in the thread

遇到需要再转到 Python 的场景时，先读取 [python-utf8.md](python-utf8.md) 里的 UTF-8 环境变量模式，再决定是否切换工具；不要在 PowerShell 已能稳定读取时无谓切到 `python -c`。
