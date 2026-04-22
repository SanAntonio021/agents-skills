# Validated Command Patterns

## Purpose

This index routes high-risk Windows command scenarios to the smallest relevant pattern file.
Read only the nearest matching reference instead of loading the whole library.

## Routing

- Path quoting and absolute Windows CLI invocation: read [cli-paths.md](cli-paths.md)
- PowerShell-native HTTP download to an exact local file: read [cli-paths.md](cli-paths.md)
- MATLAB batch script execution with reliable logging: read [matlab-batch-logfile.md](matlab-batch-logfile.md)
- MATLAB desktop script execution with logfile, child-process tracking, and status-file completion: read [matlab-batch-logfile.md](matlab-batch-logfile.md)
- PowerShell `python -c` and UTF-8 environment setup: read [python-utf8.md](python-utf8.md)
- Reading Chinese Markdown or other UTF-8 text in PowerShell: read [markdown-read-utf8.md](markdown-read-utf8.md)
- Batch CSV text repair with UTF-8 BOM preservation: read [csv-rewrite-utf8.md](csv-rewrite-utf8.md)
- Search, traversal, and text matching: read [search-and-traversal.md](search-and-traversal.md)
- Archive extraction and native file operations: read [archive-and-file-ops.md](archive-and-file-ops.md)
- Tool discovery and preflight checks: read [tool-discovery.md](tool-discovery.md)
- GitHub repo subtree download via Contents API when clone-based install fails: read [github-contents-api-download.md](github-contents-api-download.md)
- Word COM `gen_py` cache recovery for `pywin32`: read [word-com-genpy-recovery.md](word-com-genpy-recovery.md)
- Codex desktop sidebar/workspace recovery after local UI state corruption: read [codex-sidebar-recovery.md](codex-sidebar-recovery.md)
- Minimal recovery capture after a fail-then-fix success: read [recovery-capture-checklist.md](recovery-capture-checklist.md)

## Update Path

If a command shape succeeds and is worth keeping, update the nearest scenario file instead of appending logs here.
