# Style identity audit and remap

Use this workflow when an existing DOCX must keep its original Word style names, or when parallel
AI-created styles must be consolidated into identities already present in a named template.

## Content-edit audit

Keep the pre-edit DOCX as the baseline. After changing content, run:

```powershell
python scripts/style_guard.py audit `
  --baseline C:\path\before.docx `
  --candidate C:\path\after.docx `
  --json-out C:\path\style-audit.json
```

Default behavior is strict. Exit code `1` means the edit introduced at least one unauthorized style
change. The JSON report separates:

- added, removed, or modified style definitions;
- paragraph style changes;
- paragraph/run direct-formatting drift;
- newly orphaned styles;
- new references to missing styles.

Do not use `--report-only` in a delivery gate. It is for diagnosis only. If the user explicitly
approved a formatting change, modify the existing style definition and repeat
`--allow-style-change StyleId`. Do not authorize a newly created parallel style.

## Explicit identity remap

`remap` takes layout properties from each old style, but takes the target style ID, localized name,
and UI metadata from the named template. It rewrites style references throughout Word XML parts,
sets the requested next-paragraph styles, then removes the old definitions.

```powershell
python scripts/style_guard.py remap `
  --input C:\path\input.docx `
  --template C:\path\style-source.docx `
  --output C:\path\output.docx `
  --map OldBody=TemplateBodyId `
  --map OldHeading=TemplateHeadingId `
  --next-style TemplateBodyId=TemplateBodyId `
  --next-style TemplateHeadingId=TemplateBodyId `
  --json-out C:\path\remap-report.json
```

The output path must not exist. Mappings must be one-to-one, every old style must exist in the input,
and every target style must exist in the template. The tool rejects chained mappings.

## Acceptance boundary

The remap report proves that paragraph count, body/formula text tokens, OMML structure, media,
relationships, and non-style XML structure stayed unchanged. It also reports whether numbering bytes
changed. For a job that requires numbering to remain byte-identical, treat
`numbering_unchanged=false` as a hard failure.

After structural checks, render both documents through `libreoffice-runner` and inspect every page.
If the user approved Word COM for the current task, test `NameLocal`, Enter-key inheritance, and style
count in an isolated copy through the shared COM guard. Never connect to an existing Word process.
