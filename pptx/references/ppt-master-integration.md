# PPT Master integration

## Purpose and trust boundary

Use the official `ppt-master` author workflow through the audited CC Switch distribution at
`SanAntonio021/ppt-master:ccswitch`. The Fork changes only the distribution layer: loose icon assets
are stored in deterministic local shards, and runtime access remains offline. The local `pptx` skill
owns routing, the external pin, deterministic file operations, and final acceptance.

These are cooperating skills, not two authoring implementations. Do not copy the upstream workflow
into `pptx`, edit an installed runtime directory, or execute a source-review mirror as a skill. The
bundled/system presentation skills are outside this route and are never a silent fallback.

## External pin before handoff

The authoritative pin is [ppt-master-pin.json](ppt-master-pin.json). It has three fail-closed states:

- `bootstrap`: accept exactly one first-install candidate;
- `transition`: accept the old stable distribution and one upgrade candidate;
- `stable`: accept exactly one stable distribution.

Resolve the actual `ppt-master` root loaded by the current client, then run:

```powershell
python <pptx-skill-root>\scripts\verify_ppt_master_pin.py `
  --skill-root <active-ppt-master-root> --json-out <task-evidence>\ppt-master-pin.json
```

The verifier requires the trusted Fork repository and `ccswitch` branch in the pin, validates state
cardinality, matches the installed `distribution.manifest.json` to an accepted release, and verifies
every protected file using relative path, raw size, and raw SHA-256. It rejects symlinks/reparse
points, unsafe or case-colliding paths, missing files, and residual files. Python bytecode under
`__pycache__` is the only ignored transient. It also checks that `ccswitch.provenance.json` matches
the pinned upstream version, commit, release tag, and Fork identity.

`--pin-only` proves only that the pin state is internally valid. It does not prove an installed tree.
Do not read or execute the upstream `SKILL.md` or attribution guard until installation verification
returns `status=PASS`. Keep the full JSON report as task evidence.

## Routing decision

Apply the first matching rule:

1. If the user explicitly names or invokes `ppt-master`, verify the pin and route to the active skill.
2. Route new-deck authoring, substantial redesign or beautification, image-to-PPTX reconstruction,
   Brand/Style/Layout/Deck workspace creation, native template filling or enhancement, and
   presentation narration, animation, or self-running video work to `ppt-master`.
3. Keep content reading and extraction, element inspection, structural validation, combining or
   splitting files, and small deterministic edits in local `pptx`.
4. For a mixed task, let `ppt-master` complete the authoring route first, then use local `pptx` only
   for acceptance and formal release packaging. Never run two competing generation pipelines.

## Handoff to the author workflow

Pass the user's actual source files, output location, audience, presentation goal, content
constraints, brand or template assets, editability requirements, and any explicit Quick or quality
preference. Use absolute paths and preserve the source files.

After the external pin passes:

1. Follow the verified skill's mandatory load order from its own `SKILL.md`.
2. Run its attribution or integrity guard exactly as documented.
3. Let its routing authority select one top-level route and active profile.
4. Honor every blocking confirmation. The local route does not pre-approve an upstream gate.
5. Keep its project workspace and intermediate authorities intact until the route reaches its final
   candidate.

The expected return is the candidate PPTX plus the upstream workspace or source artifacts needed to
revise it. Record the candidate path, external-pin report, Fork commit, release tag, and official
upstream version.

## Local acceptance after handoff

Treat the returned PPTX as a candidate, not as a finished local release. Apply the local `pptx`
acceptance policy:

- run Python runtime preflight before the static validators;
- record `STATIC_PASS` independently;
- use `libreoffice-runner` for `LO_RENDER_PASS` and inspect the full-slide render;
- obtain task-specific Office authorization before running the native gate;
- keep `NATIVE_OPEN_PASS` and `NATIVE_RENDER_PASS` separate;
- use the formal release bundle workflow when the user calls the output final or formal.

Do not edit an upstream workspace merely to make a local gate appear green. Repair the owning source,
regenerate the candidate, and rerun the affected acceptance layers.

## Failure behavior

Stop and report the exact blocker when the trusted distribution is absent, disabled for the current
client, cannot resolve its root, fails the external pin, or fails its own integrity guard. Preserve
all inputs. An explicit `ppt-master` request always fails closed. For an implicit route, ask whether
the user accepts the narrower local `pptx` pipeline; never switch silently.

Do not substitute a bundled/system presentation skill, an ad hoc generator, or
`D:/BaiduSyncdisk/.agents/upstream/hugohe3-ppt-master`. The mirror is source-review evidence only.

## Ownership and updates

- Official `hugohe3/ppt-master`: author workflow and upstream release source.
- `SanAntonio021/ppt-master:main`: sync-only view of the official repository.
- `SanAntonio021/ppt-master:ccswitch`: installable, manifest-protected distribution tracked by CC
  Switch. Tags are immutable release evidence; CC Switch follows the branch head.
- Local `pptx`: routing, external pin, deterministic operations, acceptance gates, and release policy.
- Review mirror: zero-exposure comparison evidence only; never a runtime source.

Never modify `.cc-switch`, `.codex`, or `.claude` runtime copies directly. Fork publication, local
pin publication, CC Switch installation, and per-client runtime activation are separate gates.
