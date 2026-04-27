# GitHub Contents API Download

### Pattern: powershell-python-github-contents-recursive-download
- scenario: Materialize a GitHub-hosted skill or small repo subtree locally when `git clone` or `npx skills add` cannot reach `github.com` but the GitHub Contents API still responds
- use_when: A Windows task needs files from a known `<OWNER_REPO>` and optional `<REPO_SUBPATH>`, the clone-based install path already failed for connectivity reasons, and the target can be installed by copying a small subtree rather than a full git checkout
- shell: PowerShell
- validated_shape: `@'` newline `import urllib.request, json, base64` newline `from pathlib import Path` newline `def fetch_json(url): ...` newline `def write_file_from_api(file_url, dest): ...` newline `def download_path("<OWNER_REPO>", "<REPO_SUBPATH>", Path(r"<ABS_DEST_PATH>")): ...` newline `download_path("<OWNER_REPO>", "<REPO_SUBPATH>", Path(r"<ABS_DEST_PATH>"))` newline `'@ | python -`
- substitute_only: `<OWNER_REPO>`, `<REPO_SUBPATH>`, `<ABS_DEST_PATH>`
- preflight: `Get-Command "python"`; `Test-Path (Split-Path -Parent "<ABS_DEST_PATH>")`; verify the Contents API root `https://api.github.com/repos/<OWNER_REPO>/contents/<REPO_SUBPATH>?ref=main` returns JSON before starting recursive writes; after download, verify `Test-Path "<ABS_DEST_PATH>\\SKILL.md"` when installing a skill
- env: none
- avoid: Retrying the same `git clone` or `npx skills add` shape unchanged after a confirmed `github.com` connectivity failure; relying on flaky `raw.githubusercontent.com` fetches for every file when the Contents API can return base64 file content; copying a repo subtree into a skill destination without checking that the source subtree itself is the skill root
- success_signal: The target subtree is written locally and the expected entry file such as `SKILL.md` exists at the destination
- capture_rule: Reuse this fallback when GitHub-hosted skills or small support trees must be installed on Windows and clone-based acquisition failed, then update this file instead of adding another ad hoc downloader pattern
