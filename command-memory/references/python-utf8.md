# Python UTF-8

用途：PowerShell 调 Python 时处理 UTF-8、中文路径、here-string、Excel/PDF 文件名乱码。只在出现编码风险或已有失败时读取。

## 首选判断

- 简单 Python 一行：用 UTF-8 环境变量。
- 多行代码或大量中文字符串：写成 UTF-8 `.py` 脚本，再由 PowerShell 调用。
- 内容含反斜杠序列（LaTeX 命令、正则、路径字面量）：不走 inline / heredoc，直接写脚本文件，写后验证关键标记。
- 中文文件名/路径：优先让 PowerShell 找到路径，再用参数或环境变量传给 Python。
- 中文 worksheet/header：能用索引就用索引，别把中文表头塞进 PowerShell here-string。

## 常用骨架

### Pattern: inline-python-utf8
- use_when: `python -c` 或 stdin 脚本会输出中文、符号或非 ASCII。
- shape: `$env:PYTHONIOENCODING='utf-8'; $env:PYTHONUTF8='1'; python -c "<PYTHON_CODE>"`
- preflight: `Get-Command "python"`; 代码保持短；复杂就切脚本文件。
- avoid: 裸 `python -c`; 大段多行代码塞进命令行。

### Pattern: stdin-script-with-arg
- use_when: 必须打开一个精确中文路径文件，直接把路径写进 Python 代码不稳。
- shape: `$p = "<ABS_INPUT_PATH>"; @'<PY>'@ | python -X utf8 - $p`
- Python: `from pathlib import Path; import sys; p = Path(sys.argv[1])`
- preflight: PowerShell 先 `Test-Path -LiteralPath $p`。
- avoid: 在 here-string 里硬编码同一个中文绝对路径。

### Pattern: exact-path-via-env
- use_when: 目标文件名中文且需要 PowerShell 先筛选，例如多个 PDF/XLSX 候选。
- shape: `$env:TARGET_FILE = (Get-ChildItem -LiteralPath . -Filter '*.xlsx' | Sort-Object LastWriteTime -Descending | Select-Object -First 1 -ExpandProperty FullName); @'<PY>'@ | python -X utf8 -`
- Python: `import os; from pathlib import Path; p = Path(os.environ['TARGET_FILE'])`
- preflight: 确认筛选结果非空且唯一；必要时先打印候选。
- avoid: 用中文文件名直接拼进 Python 字符串。

### Pattern: backslash-content-via-script-file
- use_when: 要用 Python 写入或替换含反斜杠序列的文本（LaTeX 命令、正则、Windows 路径字面量），尤其混有中文时；或 bash heredoc / `python -c` 已出现 `SyntaxWarning: invalid escape` 乃至内容静默损坏。
- failure_class: 多层转义（工具调用层→shell→heredoc→Python 字符串）各吃一层反斜杠：`\times` 中的 `\t` 被解析成 TAB 写进文件（渲染成 `2imes2`），`\m` 报 invalid escape 却继续跑——命令成功、内容已坏，属静默损坏。
- shape: 用编辑器落地 UTF-8 `.py` 脚本再 `python -X utf8 <SCRIPT>.py`；脚本内反斜杠用 `chr(92)`、制表符判断用 `chr(9)` 拼接，彻底避开字符串转义；写后立刻计数验证关键标记。
- success_signal: 写入后 grep/count 确认标记数量符合预期（如 `\times` 恢复 N 处、TAB 残留 0）。
- avoid: 把含 `\` 的多行文本塞进 bash heredoc 或 `python -c`；跑通了不验证内容。

### Pattern: chinese-excel-by-index
- use_when: workbook、sheet、header 含中文，inline Python 读取或编辑失败。
- shape: 用 env/argv 传 workbook 路径；`ws = wb.worksheets[<INDEX>]`; 按数字列写入。
- avoid: `wb['中文sheet']`; `col['中文表头']`；在 here-string 里写大量中文 key。
- success_signal: Python 成功打开目标，按预期读写并保存，不出现 mangled path、`KeyError`、`Invalid argument`。

## 文件生成建议

- 输出文件名尽量 ASCII，例如 `result.xlsx`、`extracted.txt`。
- worksheet 名称可先用 ASCII；单元格内容可以保留中文。
- 中文内容很多时，创建临时 `.py` 文件比 inline here-string 更稳。
- Windows 前缀 `\\?\` 不要写成 raw string 结尾；用普通转义字符串：`'\\\\?\\'`。

## 回写

只有出现“编码/路径相关失败后，换形态成功”才更新本文件。记录成功骨架和失败类别，不记录真实用户路径。
