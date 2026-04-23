# Tongyong-Moren Template Profile

- Public asset: `assets/master-default-template.style-profile.json`
- Human-readable report: `references/master-default-template-profile.md`
- Builder: `scripts/build_master_template.py`

This profile is the long-term default preset for the skill under the canonical name `tongyong-moren`. If you need a concrete `.docx` template locally, regenerate it with `scripts/build_master_template.py`.

Design sources:

- Cover/title conventions come from the `gongzuo-zongjie` template family.
- Body text, heading hierarchy, captions, appendix, and references come from the `jishu-zongjie` template family.
- Sensitive cover footer text is kept as a neutral placeholder and not copied from the source sample.

Core rules:

- Page setup follows the `jishu-zongjie` margins and first-page layout.
- `Title` is used as the cover/report title style.
- `Heading 1-3` are normalized into the main heading hierarchy.
- `Master Body` is the default body style applied during formatting.
- Custom helper styles are included for cover fields, TOC title, figure/table captions, appendix title, table text, and references.
