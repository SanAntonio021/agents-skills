# Template Governance

Use this note when deciding whether a newly provided Word sample should become a preset or replace the current default preset.

## Promotion rules

- On this machine, the current governed default is `qiye-shenbao` because the user prefers the company project-proposal format whenever no other format source is specified.
- Keep `tongyong-moren` available as the general-report preset rather than the current default.
- Add a source document as a separate preset when it has a recognizable house style but is not suitable as the universal default.
- A project-proposal sample such as `qiye-shenbao` may become the current default when the user's standing preference is to default all unspecified Word exports to the company proposal format.
- Rebuild `tongyong-moren` only when the new evidence improves the long-term common format, not just one document family.

## What makes a template reusable

- Real Word styles are used consistently for title, heading hierarchy, body text, captions, appendix, and references.
- Page setup is explicit and stable: paper size, margins, gutter, header/footer distance, first-page behavior.
- Direct formatting is limited. Small exceptions are acceptable; widespread manual overrides are a warning sign.
- The file does not embed sensitive or one-off text that should not leak into a reusable asset.

## Warning signs

- The visual result depends mostly on manual font/spacing overrides instead of style definitions.
- Only one narrow document type is covered, such as an opinion form or a single review sheet.
- Key layers are missing, for example no stable body style, no caption style, or no reference style.
- Cover text includes organization-specific wording that should be replaced by placeholders.

## Lessons from current presets

- `jishu-zongjie` is the strongest body-style source because its `GF-report` style family covers headings, body, captions, appendix, and references.
- `gongzuo-zongjie` is useful for cover conventions and common report feel, but it is not clean enough to serve as the only long-term default because many paragraphs rely on direct formatting.
- Opinion-style templates and single-purpose review forms should stay separate candidates or future narrow presets, not the universal default.

## Maintenance rules

- Prefer changing `custom/word-template` rather than patching `vendor` skills.
- Regenerate the master asset with `scripts/build_master_template.py` when changing the synthesized default.
- Re-extract the profile after any template change and review `references/master-default-template-profile.md`.
- Run `scripts/validate_master_default.py` after changing the default preset or the master builder.

Legacy English aliases remain accepted for compatibility, but governance notes should use `tongyong-moren`, `jishu-zongjie`, `gongzuo-zongjie`, and `qiye-shenbao` as the canonical labels.
