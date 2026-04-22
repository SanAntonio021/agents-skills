# Tool Discovery

### Pattern: powershell-tool-discovery-then-run
- scenario: Windows external tool execution with explicit discovery
- use_when: The task depends on a non-builtin tool such as `pandoc`, `ffmpeg`, or another CLI that may be missing, shadowed, or version-dependent.
- shell: PowerShell
- validated_shape: `Get-Command "<TOOL>"; <TOOL> <FLAGS> "<INPUT_PATH>" <MORE_FLAGS>`
- substitute_only: `<TOOL>`, `<FLAGS>`, `<INPUT_PATH>`, `<MORE_FLAGS>`
- preflight: `Get-Command "<TOOL>"`; `Test-Path "<INPUT_PATH>"`; if the tool writes files, verify output directory handling explicitly
- env: none
- avoid: Assuming PATH contains the tool; retrying the same failing invocation without checking tool availability first
- success_signal: The tool is discoverable and the command completes without executable-not-found or quoting errors
- capture_rule: Update this entry when a tool-specific preflight becomes stable enough to reuse beyond a single project

### Pattern: powershell-npx-skills-with-cache-override
- scenario: Running `npx skills` from PowerShell when the default npm cache can raise `EPERM` or when `npm warn exec` on stderr is incorrectly promoted to a terminating error
- use_when: A task needs `npx skills ...` on Windows and the first attempt fails because `C:\Users\<USER>\AppData\Local\npm-cache` is not writable or PowerShell aborts while the CLI itself is still usable
- shell: PowerShell
- validated_shape: `$cacheDir = "<CACHE_DIR>"; New-Item -ItemType Directory -Force -Path $cacheDir | Out-Null; $env:npm_config_cache = $cacheDir; $env:NPM_CONFIG_CACHE = $cacheDir; Set-ExecutionPolicy -Scope Process Bypass -Force; $PSNativeCommandUseErrorActionPreference = $false; & "<SCRIPT_PATH>" <SCRIPT_FLAGS>`
- substitute_only: `<CACHE_DIR>`, `<SCRIPT_PATH>`, `<SCRIPT_FLAGS>`
- preflight: `Get-Command "npx"`; `Test-Path "<SCRIPT_PATH>"`; create `<CACHE_DIR>` explicitly before invoking the script; prefer a repo-owned temp cache directory instead of the default user npm cache when the default path already failed once
- env: `npm_config_cache`, `NPM_CONFIG_CACHE`, `ExecutionPolicy Bypass`, `$PSNativeCommandUseErrorActionPreference = $false`
- avoid: Retrying the same `npx skills` command against the default npm cache after an `EPERM`; nesting another `powershell -File ...` layer when same-session invocation is enough; treating `npm warn exec` on stderr as proof that the underlying script logic failed
- success_signal: The wrapper script returns JSON or normal CLI output and `npx skills` completes with the intended exit code while using the override cache directory
- capture_rule: Reuse this shape for repeated `npx skills` maintenance tasks on the same Windows machine once cache-permission or stderr-promotion failures have been observed
