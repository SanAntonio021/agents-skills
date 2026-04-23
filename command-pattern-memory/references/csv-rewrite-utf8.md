# CSV Rewrite UTF-8

### Pattern: powershell-csv-rewrite-utf8-bom
- scenario: Batch repair or normalization of CSV files while preserving CSV quoting rules
- use_when: The task needs to recurse through Windows CSV files, parse them safely, rewrite them as UTF-8 with BOM, and optionally clean placeholder values in text columns without breaking embedded commas or quotes
- shell: PowerShell
- validated_shape: `[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; $OutputEncoding = [Console]::OutputEncoding; Add-Type -AssemblyName Microsoft.VisualBasic; Get-ChildItem -LiteralPath "<ROOT_PATH>" -Recurse -Filter "*.csv" -File | ForEach-Object { $path = $_.FullName; $reader = [System.IO.StreamReader]::new($path, [System.Text.Encoding]::UTF8, $true); $parser = [Microsoft.VisualBasic.FileIO.TextFieldParser]::new($reader); $parser.TextFieldType = 'Delimited'; $parser.SetDelimiters(','); $parser.HasFieldsEnclosedInQuotes = $true; $rows = New-Object System.Collections.Generic.List[object[]]; while (-not $parser.EndOfData) { $rows.Add($parser.ReadFields()) | Out-Null }; $parser.Close(); $reader.Close(); $utf8Bom = [System.Text.UTF8Encoding]::new($true); $writer = [System.IO.StreamWriter]::new($path, $false, $utf8Bom); foreach ($fields in $rows) { $escaped = foreach ($field in $fields) { $text = if ($null -eq $field) { '' } else { [string]$field }; '"{0}"' -f $text.Replace('"', '""') }; $writer.WriteLine(($escaped -join ',')) }; $writer.Close() }`
- substitute_only: `<ROOT_PATH>`
- preflight: `Test-Path "<ROOT_PATH>"`; confirm the target files are CSV text files; if rewriting in place, close Excel or WPS first; if cleanup is selective, identify text-like headers before replacing placeholder strings such as `NaN` or `<missing>`
- env: Set PowerShell stdout to UTF-8 in the same command when Chinese paths or content may appear in captured output
- avoid: Reading and writing the same file handle without closing the parser and reader first; using naive `-split ','` parsing; dropping BOM on rewritten files when Windows spreadsheet tools are expected; replacing `NaN` blindly in numeric columns; writing primary CSV and `_zh.csv` companions with different encodings
- success_signal: The rewritten CSVs open in Excel or WPS without Chinese mojibake, quoted fields remain structurally valid, and placeholder cleanup affects only the intended text columns
- capture_rule: Update this entry when a safer in-place CSV normalization shape is validated again, especially around file-lock handling, placeholder cleanup scope, or BOM-preserving rewrite behavior
