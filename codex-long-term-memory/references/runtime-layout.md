# Runtime Layout

## Directory Roles

- Immutable upstream: `<agents-root>\skills\vendor\long-term-memory`
- Local wrapper: `<agents-root>\codex-long-term-memory`
- Runtime state root:
  - Preferred: `%CODEX_HOME%\state\long-term-memory`
  - Fallback: `%USERPROFILE%\.codex\state\long-term-memory`
- Runtime working tree: `<state-root>\runtime`

## Why This Split Exists

- `vendor/` should stay close to upstream so later diff and refresh work is cheap.
- Runtime state contains secrets and mutable user data, so it should not live under synced `skills/`.
- The upstream Python scripts expect their resources next to `scripts/`, `memories/`, and `short-term/`. Seeding a dedicated runtime working tree preserves that contract.

## Data That Must Stay In Runtime

- `.env`
- `configured.txt`
- `memories/`
- `short-term/`
- `vector_db/`

## Safe Refresh Policy

Use `scripts/ensure_runtime.ps1 -RefreshStatic` only when the upstream `vendor/long-term-memory` copy has been updated.

The refresh step should overwrite or re-seed only static resources:

- `assets/`
- `references/`
- `scripts/`
- `requirements.txt`
- `SETUP_GUIDE.md`
- `SKILL.md`

It must preserve existing runtime data and secrets.

## Example Commands

```powershell
powershell -File "<agents-root>\codex-long-term-memory\scripts\ensure_runtime.ps1"
```

```powershell
powershell -File "<agents-root>\codex-long-term-memory\scripts\ensure_runtime.ps1" -Json
```

```powershell
powershell -File "<agents-root>\codex-long-term-memory\scripts\ensure_runtime.ps1" -RefreshStatic
```

```powershell
powershell -File "<agents-root>\codex-long-term-memory\scripts\invoke_runtime_python.ps1" scripts\load_context.py --mode all
```

## Windows Encoding Note

The upstream Python scripts print emoji and Chinese text. On a default Windows `powershell` session, direct `python scripts\...` invocation may fail with a `gbk` encoding error.

Prefer the local wrapper:

- `scripts/invoke_runtime_python.ps1`

It sets `PYTHONUTF8=1` and `PYTHONIOENCODING=utf-8` before delegating to the upstream runtime script.
