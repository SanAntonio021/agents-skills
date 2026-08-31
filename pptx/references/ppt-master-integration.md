# PPT Master integration

## Purpose

Use the official `ppt-master` as the upstream presentation authoring and visual-design engine while
keeping the local `pptx` skill responsible for deterministic file operations, local safety policy,
and final acceptance. These are two cooperating skills, not two copies to merge.

The host loads the active `ppt-master` skill by name. Do not copy its workflow into `pptx`, edit its
installed directory, or execute the zero-exposure Git mirror as a runtime skill.

## Routing decision

Apply the first matching rule:

1. If the user explicitly names or invokes `ppt-master`, route to the active official skill.
2. Route new-deck authoring, substantial redesign or beautification, image-to-PPTX reconstruction,
   Brand/Style/Layout/Deck workspace creation, native template filling or enhancement, and
   presentation narration, animation, or self-running video work to `ppt-master`.
3. Keep content reading and extraction, element inspection, structural validation, combining or
   splitting files, and small deterministic edits in local `pptx`.
4. For a mixed task, let `ppt-master` complete the authoring route first, then use local `pptx` only
   for acceptance and formal release packaging. Never run two competing generation pipelines.

## Handoff to the official skill

Pass the official route the user's actual source files, output location, audience, presentation goal,
content constraints, brand or template assets, editability requirements, and any explicit Quick or
quality preference. Use absolute paths and preserve the source files.

After loading `ppt-master`:

1. Follow its mandatory load order from its own `SKILL.md`.
2. Run its attribution or integrity guard exactly as documented.
3. Let its routing authority select one top-level route and active profile.
4. Honor every blocking confirmation. The local wrapper does not pre-approve an upstream gate.
5. Keep its project workspace and intermediate authorities intact until the route reaches its final
   candidate.

The expected return is the candidate PPTX plus the upstream workspace or source artifacts needed to
revise it. Record the exact candidate path and the active `ppt-master` version when available.

## Local acceptance after handoff

Once the upstream route has completed, treat the returned PPTX as a candidate, not as a finished local
release. Apply the local `pptx` acceptance policy:

- run Python runtime preflight before the static validators;
- record `STATIC_PASS` independently;
- use `libreoffice-runner` for `LO_RENDER_PASS` and inspect the full-slide render;
- obtain the task-specific Office authorization required by the global rules before running the native
  gate;
- keep `NATIVE_OPEN_PASS` and `NATIVE_RENDER_PASS` separate;
- use the formal release bundle workflow when the user calls the output final or formal.

Do not edit an upstream workspace merely to make a local gate appear green. Repair the owning source,
regenerate the candidate, and rerun the affected acceptance layers.

## Failure behavior

If the official skill is absent, not enabled for the current client, cannot resolve its root, or fails
its integrity guard, report the exact blocker and preserve all inputs. An explicit `ppt-master` request
fails closed. For an implicit route, ask whether the user accepts the narrower local `pptx` pipeline;
do not silently fall back.

Do not substitute a bundled or system presentation skill. Do not load or execute
`D:/BaiduSyncdisk/.agents/upstream/hugohe3-ppt-master`; that directory exists only for source review
and update detection.

## Ownership and updates

- `ppt-master`: official repository content and its internal authoring workflow. CC Switch should manage
  its GitHub origin, version checks, installation, and enablement for Codex and Claude.
- `pptx`: local routing, deterministic operations, acceptance gates, and release policy. It remains
  maintained and distributed from the local skills repository.
- `hugohe3-ppt-master` mirror: zero-exposure review evidence only. Weekly maintenance may compare it
  with the accepted upstream baseline, but it never overwrites either runtime skill automatically.

Never modify `.cc-switch`, `.codex`, or `.claude` runtime copies directly. A source release and a
runtime activation are separate gates and must be reported separately.
