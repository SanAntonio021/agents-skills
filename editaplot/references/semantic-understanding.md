# Scientific data understanding and element confirmation

Use this gate after selecting a candidate template and before creating a render plan.

## The five data dispositions

Every source column must appear exactly once:

- `render_primary`: the main evidence shown in the figure;
- `render_secondary`: background, fit, residual, reference, phase tick, or another visible aid;
- `support_only`: used for validation, filtering, weighting, coordinate choice, or layout control,
  but not drawn as a curve or mark;
- `retain_not_render`: preserved for provenance/editability and not used by the visible figure;
- `uncertain`: scientific meaning is unresolved; planning is blocked.

Do not use `ignored` as an unexplained wastebasket. Explain why each non-rendered numeric column is
support-only or retained.

## Required sequence

1. Prepare the selected template with the proposed or corrected column mapping.
2. Run `understand` using that exact mapping.
3. Record internally:
   - what kind of experiment/table this appears to be;
   - what will be drawn;
   - what is retained or used only as support;
   - what approved display helpers are proposed;
   - what the drawing layer will not calculate;
   - any focused unresolved scientific questions.
   Tell the user only what will be drawn and unresolved questions; give the full breakdown on request.
4. If an item is uncertain, check the supplied material first. Ask only if meaning remains unresolved,
   then obtain the corrected mapping and return to step 2.
5. Reuse an already explicit scientific purpose and exact choices; ask only for unresolved meaning. Record the actual request in the existing confirmation fields.
6. Pass the exact proposal hash, approved helper IDs, and ambiguity resolutions to `plan`.

A different source hash, mapping, or proposal hash invalidates the old machine payload. Rerun
inspection and `understand`, then compare the current purpose, column roles, units and authorized
transformations with the existing user decision. When the current request covers the updated data
and those choices still apply, generate a new payload with the current proposal hash and matching
helper/ambiguity IDs; retain the actual earlier authorization rather than inventing a new answer.
Ask only when a material change is unresolved. Never reuse a stale payload, edit a confirmed plan
by hand, or change the fixed external engine to bypass validation. Internal confirmation states
do not by themselves require another user question.

## Derived data

Source columns and derived helpers are separate objects. A helper requires:

- an allow-listed deterministic operation;
- complete source-item lineage;
- explicit user approval;
- a stated scientific/display purpose;
- a renderable disposition when visible.

Do not silently fit, smooth, remove outliers, calculate error bars, identify phases, calculate
background, derive band gaps, calculate SHAP, or create statistics. Simple display helpers such as
an X-axis sign transform, percentage-of-row total, or a phase-tick Y lane remain explicit and never
overwrite source values.

## GSAS/GSAS-II Rietveld example

A suitable focused question, when a source column's meaning cannot be established, is:

> 这里的 `Diff` 已经包含展示偏移了吗？这会决定是否直接按原值绘制，避免重复偏移。

If the file or existing decision already establishes a Publication `Diff`, preserve it exactly
without asking again. Keep the full column classification and any calculations in the internal
record; do not turn it into a mandatory checklist for the user to approve.

If a numeric column such as Temperature is not part of a recognized contract, do not guess. Ask
whether it is a plotted condition, support metadata, an alternative coordinate, or a column that
should be retained without display, then regenerate the proposal.

## Conversation contract

Keep the first response compact. The full JSON is audit evidence for Codex and advanced users, not
the default beginner explanation. Ask only questions that can change the scientific meaning or
visible elements.


Existing authorization applies only within the scope it specified. Scientific ambiguity and a new
meaning-changing analysis require a real decision; a byte-level change alone does not.
