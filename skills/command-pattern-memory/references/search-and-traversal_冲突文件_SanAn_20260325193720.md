# Search And Traversal

### Pattern: powershell-search-and-traversal
- scenario: File search and content search on Windows
- use_when: The task needs to search by file name, traverse directories, or inspect text content from PowerShell.
- shell: PowerShell
- validated_shape: `Get-ChildItem -LiteralPath "<ROOT_PATH>" -Recurse -Filter "<FILE_FILTER>" -File`
- validated_shape_alt: `Select-String -Path "<INPUT_PATH>" -Pattern "<PATTERN>" -Encoding UTF8`
- validated_shape_alt2: `Get-ChildItem -Path "<ROOT_PATH>" -Filter "<FILE_FILTER>" -Recurse | Select-Object -ExpandProperty FullName`
- substitute_only: `<ROOT_PATH>`, `<FILE_FILTER>`, `<FILTERS>`, `<INPUT_PATH>`, `<PATTERN>`
- preflight: `Test-Path "<ROOT_PATH>"` or `Test-Path "<INPUT_PATH>"`; confirm whether the task is file-name search, direct file content search, or recursive content search before choosing between `-Filter`, `Select-String`, or a traversal pipeline
- env: none
- avoid: Reading binary files as text; assuming `rg` is usable without verification; retrying `rg` after a PowerShell permission or execution failure instead of falling back to the validated PowerShell shape; retrying `rg --files -g "<FILE_FILTER>" "<ROOT_PATH>"` after `rg.exe` access-denied or execution failure instead of switching to `Get-ChildItem`; omitting quotes around `<ROOT_PATH>`; omitting `-Encoding UTF8` when matching Chinese Markdown or other UTF-8 text; using a content-search pipeline when only file-name traversal is needed
- success_signal: The command returns only the intended files or matching lines without shell syntax errors
- capture_rule: Update this entry when a clearer split between direct-path content search, recursive traversal search, and `rg`-failure fallback traversal is validated repeatedly
