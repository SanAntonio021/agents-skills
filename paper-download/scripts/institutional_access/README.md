# Institutional access downloader

This optional module supports IEEE Xplore and Optica Publishing Group article
pages on Windows. It reuses a browser session that the user has already
authenticated through their institution.

The module does not capture, return, log, or store school passwords, browser
passwords, cookies, or authorization headers. A short-lived CDP task token is
kept in Windows Credential Manager only so the same browser task can be resumed
after the user completes login or MFA.

Run through the PowerShell wrapper:

```powershell
.\run.ps1 acquire --session SESSION --url ARTICLE_URL --doi DOI --output PDF
.\run.ps1 status --session SESSION
.\run.ps1 resume --session SESSION --doi DOI --output PDF
.\run.ps1 complete --session SESSION
```

`run.ps1` requires Python 3.10 or newer and creates a private Python environment under
`%LOCALAPPDATA%\PaperDownload\venv` and installs the pinned `pypdf` version
when needed. It requires the sibling `web-access` skill and Node.js 22 or
newer.

Institutional downloads use the `web-access` managed Edge Broker only.
They do not use the daily Edge or Chrome `existing` mode. The Broker creates
an independent Profile at
`%LOCALAPPDATA%\web-access\managed-edge-profile`, with CDP `9222` and
Proxy `3456`; the first browser task starts it on demand and later tasks
reuse it. The preflight command is:

```powershell
node <web-access>\scripts\check-deps.mjs --browser edge --mode managed --json
```

`ready:true`, `browserMode:"managed"` and a passed control probe are required
before creating a task. Broker errors such as `managed_profile_busy`,
`managed_cdp_port_conflict`, `proxy_version_mismatch`, `control_probe_failed`
and `task_capacity_reached` stay distinct from school login, MFA, publisher
challenge and subscription denial.

When a publisher page needs institutional authentication, the command returns
`user_login_required` and activates the same tab for the user. After the user
answers that login is complete, call `resume`. The tool then re-reads the same
publisher page and verifies actual PDF access; the user's statement alone is
not treated as proof.

Each invocation gets its own task, token and tab. `complete` uses
`keep:false` to close only those pages; it does not stop the Proxy or Edge and
does not close pages owned by other conversations.

If the Proxy returns `UNKNOWN_RESULT` while creating the first tab, the module
checks the same task's owned tabs before doing anything else. It adopts one
blank tab and navigates it to the requested article, or stops on ambiguity. It
never creates a second task to guess at the timed-out operation.

If the browser has already filled a uniquely identifiable HTTPS login form,
the module may submit that form once without returning any field value. It
hands the page to the user for ambiguous forms, required confirmations, MFA,
CAPTCHA, failed submits, or unknown submit results.

This tool only reuses access that the user legitimately has. It does not grant
a subscription and does not bypass publisher access controls.
