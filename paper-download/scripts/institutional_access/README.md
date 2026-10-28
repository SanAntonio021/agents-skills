# Institutional access downloader

This optional module supports IEEE Xplore and Optica Publishing Group article
pages on Windows. `web-access` is the only browser execution layer; this module
handles publication identification, PDF identity/version validation and the
compatible `acquire`, `status`, `resume` and `complete` CLI workflow. Zotero
import follows the parent skill's shared storage workflow.

The module does not capture, return, log or store school passwords, browser
passwords, cookies or authorization headers, and does not copy browser profiles.
Existing sessions stay inside the running Edge. A short-lived Broker task token
is kept in Windows Credential Manager to resume the same task; it is not a
publisher login token.

Run through the PowerShell wrapper:

```powershell
.\run.ps1 acquire --session SESSION --url ARTICLE_URL --doi DOI --output PDF
.\run.ps1 status --session SESSION
.\run.ps1 resume --session SESSION --doi DOI --output PDF
.\run.ps1 complete --session SESSION
```

`run.ps1` requires Python 3.10 or newer, creates a private Python environment under
`%LOCALAPPDATA%\PaperDownload\venv` and installs the pinned `pypdf` when needed.
The sibling `web-access` skill and Node.js 22 or newer are required.

## Browser execution contract

The default is the currently running Edge (`existing`), using its existing
sessions. `web-access` discovers the current CDP endpoint from
`DevToolsActivePort`; no CDP port is hard-coded. Its Edge HTTP Broker normally
uses `127.0.0.1:3456`. The preflight command is:

```powershell
node <web-access>\scripts\check-deps.mjs --browser edge --mode existing --json
```

Require `ready:true`, the requested browser mode, Edge identity and a passed
control probe before creating a task. An HTTP `/json/version` 404 alone does not
mean CDP is unavailable: `web-access` verifies the WebSocket and background-tab
control. `managed` is an explicit isolation option only, not a default or an
automatic recovery path. This module never launches, repairs or reconnects a
browser itself.

Each session has its own Broker task, token and new background tab. Do not
navigate, close or adopt user-owned tabs. `complete` closes only task-owned pages;
it does not stop the Broker or Edge. For `UNKNOWN_RESULT` during tab creation,
inspect the same task's owned tabs before retrying; do not create a second task
to guess whether the first operation succeeded.

PDF bytes come only from `POST /v2/tabs/{targetId}/download`, with `url`,
`timeoutMs` and `maxBytes`; cross-origin PDF hosts must already be confirmed.
Validate the complete returned bytes, length and SHA-256, then publication
identity/version before saving or importing. Do not implement a second CDP,
page-fetch/Base64 download or browser-startup path here. HTML, truncated files
and identity mismatches are not successful downloads.

## Access and verification ownership

The new access contract is `POST /v2/tabs/{targetId}/access`, returning sanitized
`state`, `failureCode`, `handoffRequired` and `interactionRequired`. This is a
contract for the runtime change, not a claim of completed integration or live
acceptance; check Broker capabilities before using it. A missing endpoint is an
environment/capability gap, not a subscription denial or permission to recreate
login logic in Python.

The Broker owns routine saved-account autofill and authorized login submission.
`web-access` handles graphical/slider challenges through page actions and email
codes through an authorized mail tool; availability and success must be checked,
not promised. `interactionRequired` does not by itself require user handoff.
Actual SMS, dynamic-token, face or system-level verification requires handoff;
a tool restriction or unresolved capability gap must be reported separately.
While handed off, do not read or modify the page. After the user completes the
required step, `resume` re-observes the same task and verifies actual access;
the user's statement alone is not evidence of a valid PDF.

Preserve existing CLI statuses and add a specific failure code without replacing
them. Browser/control failure, site authentication or challenge, institutional
permission and file validation remain distinct. Bound retries for 401/403/429/418
and challenge pages; leave recovery to `web-access`, without copying credentials
or switching to a separate browser. This tool reuses legitimate access only and
does not grant subscriptions or bypass publisher access controls.
