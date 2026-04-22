# Word COM `gen_py` Cache Recovery

### Pattern: powershell-python-clear-word-genpy-then-rerun
- scenario: `pywin32`-backed Word automation fails because the generated `win32com.gen_py` cache is corrupted
- use_when: A Python or wrapper command that automates Microsoft Word fails with errors like missing `CLSIDToClassMap` or `MinorVersion` under `win32com.gen_py`, then needs one repair step before rerun
- shell: PowerShell
- validated_shape:
  ```powershell
  @'
  import pathlib, shutil
  import win32com.client.gencache as g
  path = pathlib.Path(g.GetGeneratePath())
  shutil.rmtree(path, ignore_errors=True)
  path.mkdir(parents=True, exist_ok=True)
  print(path)
  '@ | python -
  <RERUN_ORIGINAL_WORD_AUTOMATION_COMMAND>
  ```
- substitute_only: `<RERUN_ORIGINAL_WORD_AUTOMATION_COMMAND>`
- preflight: `python -c "import win32com.client.gencache as g; print(g.GetGeneratePath())"`; confirm the rerun uses the same Python installation as the failing Word automation command
- avoid: Retrying the same Word automation command without clearing the corrupted cache first; hard-coding user-specific cache paths when `g.GetGeneratePath()` can discover them; storing the original failing command text verbatim in the pattern library
- success_signal: The Word automation command rebuilds `gen_py` and completes after the cache reset
- capture_rule: Reuse this pattern for Word automation wrappers such as `word_template_formatter.py apply` or `export_markdown_to_word.ps1` when the failure signature points to `win32com.gen_py`
