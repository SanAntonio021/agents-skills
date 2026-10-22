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

Supported browser backends are Edge and Chrome through the existing
`web-access` CDP proxy. The selected browser comes from
`PAPER_DOWNLOAD_BROWSER`, then the normal `web-access` preference, and
defaults to Edge on a fresh machine.

When a publisher page needs institutional authentication, the command returns
`user_login_required` and activates the same tab for the user. After the user
answers that login is complete, call `resume`. The tool then re-reads the same
publisher page and verifies actual PDF access; the user's statement alone is
not treated as proof.

If the browser has already filled a uniquely identifiable HTTPS login form,
the module may submit that form once without returning any field value. It
hands the page to the user for ambiguous forms, required confirmations, MFA,
CAPTCHA, failed submits, or unknown submit results.

This tool only reuses access that the user legitimately has. It does not grant
a subscription and does not bypass publisher access controls.
