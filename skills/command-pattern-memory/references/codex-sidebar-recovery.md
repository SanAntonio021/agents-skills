# Codex Sidebar Recovery

### Pattern: powershell-codex-sidebar-diagnose
- scenario: Codex desktop left sidebar threads and workspace groups appear empty even though local conversation data may still exist
- use_when: The Codex desktop app loses sidebar history or workspace groups and you need to decide whether the failure is data loss or only renderer/local-state corruption
- shell: PowerShell
- validated_shape:
  ```powershell
  @'
  import json, sqlite3
  from pathlib import Path

  codex = Path(r"<CODEX_HOME>")
  conn = sqlite3.connect(codex / "state_5.sqlite")
  cur = conn.cursor()
  threads, active_threads = cur.execute(
      "select count(*), sum(case when archived = 0 then 1 else 0 end) from threads"
  ).fetchone()
  print(json.dumps({
      "threads": threads,
      "active_threads": active_threads,
      "session_index_exists": (codex / "session_index.jsonl").exists(),
      "global_state_exists": (codex / ".codex-global-state.json").exists()
  }, ensure_ascii=False))
  '@ | python -
  ```
- substitute_only: `<CODEX_HOME>`
- preflight: `Test-Path "<CODEX_HOME>\state_5.sqlite"`; `Get-Command "python"`; if desktop logs are available, prefer checking for a recent successful `thread/list` before assuming the backend is broken
- env: none
- avoid: Rebuilding or deleting `state_5.sqlite` before verifying whether the `threads` table still contains data; assuming an empty sidebar means the conversations are gone; trusting `.codex-global-state.json` as the only source of truth while Codex is still running
- success_signal: `threads` still exist in SQLite, `session_index.jsonl` is present, or logs show `thread/list` succeeded, which together indicate a UI-state problem rather than conversation loss
- capture_rule: Reuse this entry whenever the goal is to separate data-layer survival from Electron renderer/local-storage corruption before any destructive repair

### Pattern: powershell-codex-sidebar-force-repair
- scenario: Codex desktop sidebar/workspace state is repeatedly overwritten by corrupted Electron local storage or onboarding/autolaunch UI state
- use_when: SQLite and `session_index.jsonl` are intact, restoring `.codex-global-state.json` alone does not fix the UI, and the app rewrites sidebar/workspace state back to a bad one-workspace view
- shell: PowerShell
- validated_shape:
  ```powershell
  $procs = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
    $_.Name -eq 'Codex.exe' -or ($_.Name -eq 'codex.exe' -and $_.CommandLine -match 'app-server')
  }
  $procs | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction Stop }

  Copy-Item -LiteralPath "<RECOVERED_GLOBAL_STATE>" -Destination "<CODEX_HOME>\.codex-global-state.json" -Force
  Copy-Item -LiteralPath "<RECOVERED_SESSION_INDEX>" -Destination "<CODEX_HOME>\session_index.jsonl" -Force

  Remove-Item -LiteralPath "<PACKAGE_CACHE_ROOT>\Local Storage\leveldb" -Recurse -Force
  Remove-Item -LiteralPath "<PACKAGE_CACHE_ROOT>\Session Storage" -Recurse -Force
  New-Item -ItemType Directory -Path "<PACKAGE_CACHE_ROOT>\Local Storage\leveldb" -Force | Out-Null
  New-Item -ItemType Directory -Path "<PACKAGE_CACHE_ROOT>\Session Storage" -Force | Out-Null

  Start-Process explorer.exe 'shell:AppsFolder\<APP_SHELL_ID>!App'
  ```
- substitute_only: `<RECOVERED_GLOBAL_STATE>`, `<RECOVERED_SESSION_INDEX>`, `<CODEX_HOME>`, `<PACKAGE_CACHE_ROOT>`, `<APP_SHELL_ID>`
- preflight: Back up the current `.codex-global-state.json`, `session_index.jsonl`, `Local Storage\leveldb`, and `Session Storage`; confirm all Codex processes are stopped before removing package-local storage; if the recovered global state was merged from an older snapshot, prefer removing onboarding/autolaunch keys and expanding `active-workspace-roots` to the saved roots before relaunch
- env: none
- avoid: Restoring only `.codex-global-state.json` while Codex is still running; leaving `.codex-global-state.json` permanently read-only after the repair; resetting SQLite when the renderer cache is the failing layer; deleting Electron local/session storage before making a rollback snapshot
- success_signal: After relaunch, Codex shows sidebar workspaces and thread history again
- capture_rule: Reuse this pattern when Codex desktop keeps collapsing back to a single workspace, when package-local Electron storage is the layer that rewrites bad sidebar state, or when a force-stop plus cache reset succeeds after softer JSON-only restoration failed
