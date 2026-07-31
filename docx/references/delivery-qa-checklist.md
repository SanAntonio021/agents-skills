# Word delivery QA checklist

Use this checklist only when the requested deliverable needs accessibility review, privacy or
redaction, or metadata cleanup. It is an optional final pass, not a second document-generation flow.

## Accessibility

- Confirm heading levels form a readable hierarchy and are not used only for visual size.
- Confirm tables have meaningful header rows and no information is conveyed by color alone.
- Confirm images have useful alt text or are marked decorative when they carry no information.
- Confirm reading order, language metadata, and sufficient contrast where the target viewer supports
  those checks.

## Privacy and redaction

- Search the visible text, headers, footers, comments, tracked changes, document properties, and
  embedded files for names, contact details, local paths, credentials, and other user data.
- Treat redaction as removal from the package, not white text or a black rectangle over the original.
- Reopen the resulting package and search its unzipped XML and relationships after redaction.
- Preserve a separate original and record what was removed; do not overwrite the source by default.

## Metadata and handoff

- Remove or normalize author, company, template, revision, and custom properties only when the user
  requested metadata cleanup or the delivery policy requires it.
- Check comments, tracked changes, hidden text, and unused embedded objects before release.
- Render the final output again after cleanup and verify the filename, page count, and requested output
  format.
- Report any check that could not be performed instead of claiming a clean delivery.
