---
name: standardize-test-project
description: Build and modify experimental or scientific simulation programs, including result directories, retention, automatic plots, replay, and hardware-free validation. Also reuse the bundled complete MATLAB TX/RX workbench, diagnostic plots, and M8195A/LeCroy adapters when creating a workbench or integrating selected modules. Use for new experimental projects, future output changes, parameter sweeps, compact/full simulation storage, and offline run analysis. Real instrument operation belongs to link-test. Do not use for ordinary software tests, generic application repositories, standalone analysis without experimental runs, documentation-only work, or historical-result migration that does not change future code or outputs.
---

# Standardize Test Project

Build or adapt experimental programs with a consistent output contract. Reuse the complete TX/RX workbench only when the task needs it. Preserve project-specific hardware safety rules and historical results.

## Workflow

1. Read the request, target project's rules, existing entry points and relevant files. Reuse the confirmed scope and authorization. A read-only question ends with findings and suggestions; it does not authorize scaffolding, file changes or instrument access.
2. Select the necessary resources:
   - **General experimental project or output changes:** use [the output standard](references/standard.md). Read sections 1–3 for directories, observations and precision; section 4 for automatic plots/replot; section 5 for analysis, compatibility and safety; section 6 for retention and storage acceptance. Read the whole standard when implementing a complete output lifecycle. Ordinary output or plotting tasks do not load the workbench assets.
   - **Complete MATLAB TX/RX workbench:** follow [Workbench reuse](#workbench-reuse). Copy its complete dependencies, without also running the generic scaffold.
   - **Existing project, selected module or plot:** keep its architecture and integrate only the requested module and dependencies. Read the relevant standard sections, and the workbench adaptation guide only if using a workbench module. Plot-only work applies section 4 to the existing source and checks affected normal/compact exports; skip scaffolding, directory migration and unrelated lifecycle tests.
3. For a new general project, run `scripts/scaffold_test_project.py` with project path, name and language. Keep human-run entry scripts at root and use `code/`, `config/`, `simulation/`, `measurement/`, `analysis/`, `checks/`. For existing projects, change future defaults only; keep historical results in place.
4. When changing output writers, reuse compatible project helpers or `assets/project-template/code/`. New writers use timestamp-first directories, exclusive suffix allocation, visible images/display CSV and flat `data/`. Helpers expose retention mode; writers choose compact/full payloads, and plotting helpers save lossless replot inputs when the run has `data/`.
5. Apply [Validation and dry-run](#validation-and-dry-run) to the affected behavior. Report the actual changes, validation, preserved inputs/history, and remaining gaps; source reuse, mock execution and real instrument acceptance are distinct.

## Workbench Reuse

Read [the adaptation guide](assets/tx-rx-workbench/references/adaptation.md) and relevant [TX/RX previews](assets/tx-rx-workbench/assets/previews/) when choosing or adapting this implementation. It is a complete reference project, not a mandatory algorithm or UI.

- For complete reuse, run [copy_template.ps1](assets/tx-rx-workbench/scripts/copy_template.ps1) with `-Destination` pointing to a new directory. It refuses an existing destination. Keep the namespace and runtime dependencies together; the two root entry files alone are insufficient. Local reuse integrates only needed modules and dependencies into a protected current project.
- For complete reuse, run `Template_Validate('smoke')`, which includes the simulation `Template_Demo` and mock `Template_GUI_Demo`, then only additional plotting/GUI checks relevant to the adaptation. Do not repeat the two demos after a successful smoke. The original no-argument `TX_Workbench()` / `RX_Workbench()` try instrument access and are not offline demos. Local module work runs only its affected checks with isolated inputs.
- Adapt waveform, receive processing and plot groups on the copy. Preserve real units, data origins and stage meanings. The 16QAM/QPSK example, frame structure, panel count and layout are examples, not required scientific choices.
- Source hashes, device references and historical acceptance remain in [provenance](assets/tx-rx-workbench/references/provenance/). This frozen snapshot retains its existing output behavior and helper differences; it is not proof of current output-contract compliance. Apply the current standard to the new project's requested output adaptations without silently rewriting the snapshot or previously copied projects.
- Hardware operation uses [link-test](../link-test/SKILL.md) and current project protections. Device references do not supply new wiring confirmation or instrument authorization. Reuse valid current authorization; retain capacity, alignment, shared-channel, read-back and shutdown safeguards described in the adaptation guide.

## Validation and Dry-Run

Select checks by actual changes: scaffold/whole-output work uses `scripts/validate_test_project.py <project>`, applicable project tests and language helpers; a local module or plot change checks affected behavior. Use isolated temporary projects or result roots, never real instrument access as an incidental software test.

- When adding or changing a hardware execution path, integrate a dry-run that short-circuits before creating or initializing hardware objects. A plan-only dry-run may record expected input paths, but must not call `exists`, `stat`, `open`, or equivalents on a legacy inbox, UNC path, mapped drive or measurement file. Side-effect-free imports are allowed; hardware-side-effect imports, connections, queries and writes are not. Keep optional plotting/result dependencies lazy when needed by legacy CLI compatibility.
- When changing dry-run persistence or legacy-inbox handling, test malformed sentinel files in an isolated inbox fixture and verify no read or probe; run persisted dry-run twice and confirm distinct directories without overwriting.
- When changing lifecycle gates, earlier/transitional-stage tests must use one controlled state in a temporary project copy or mocks replacing every relevant manifest, freeze file and run-inventory input. Do not infer an earlier stage from live current files. Keep a separate read-only final-state test when it is a safety gate and verify blocking before run creation or model/hardware execution.

## Required Result Contract

Apply this contract to new or modified output behavior. A local plot/module task preserves unrelated writers and existing paths; read-only observation does not acquire a new persistence requirement.

- With persistence enabled, one complete run creates `category/YYYYMMDD_HHMMSS_experiment/` directly under the project. Categories are `simulation`, `measurement`, `analysis`, `checks`; single-point and scan remain methods, not directory categories. A no-write run creates nothing, including on failure.
- Keep useful images and display `summary.csv` in the run root. Put raw/derived data, full observations, configuration, sources, replot inputs, and logs in one flat `data/` directory.
- Use a capture/attempt sequence such as `001_TxPower-10dBm_Channel1_星座图.png`. Same capture across Channels shares the sequence; retries increment it and failed observations remain recorded. Conditions come from configured controls, not measured results. Chinese and familiar English/acronyms are acceptable.
- Give the user `overview.png` for browsing and `summary.csv` for details. Put metric names in CSV row 1, units in row 2, and observations from row 3.
- Maintain `data/run_info.json`, `data/run_log.txt`, and full-precision `data/observations.csv`. Display summaries contain only required conditions, Channel, metrics and status. Do not automatically calculate cross-observation statistics. Explicit requested statistics are separate from necessary DSP calculations.
- For reproducible simulations, prefer compact output preserving existing plots, metrics, effective configuration, seeds, provenance, and versioned replot data. Keep full output and no-write options; real acquisitions retain raw data. Validate equivalence and measured storage savings using section 6 of the standard.
- Create a new `analysis/` run for single-source or multi-source analysis/replot and record sources in `data/sources.txt`; never write into source runs or copy their whole raw dataset.
- Export automatic plots as readable PNG files with Chinese professional labels. Section 4's font sizes and 300 dpi setting are defaults, not fixed requirements for screen dashboards; prioritize the data area and check the actual target sizes. Do not auto-export publication vector files.

## Safety Gates

- Before real instrument I/O, apply the project's current authorized hardware mode, wiring, role mapping and shutdown policy. Reuse established authorization; clarify only unresolved changes that affect operation or safety.
- Never treat dry-run or synthetic data as hardware measurement.
- Never overwrite a run directory or raw artifact.
- Never migrate history as a side effect of standardizing future runs. Historical migration is a separate inventory, dry-run, and rollback task.
- For an existing project, preserve its explicit legacy output/resume path. Introduce the standard result root separately, and do not redirect real hardware output until measurement fields, artifact names, and shutdown behavior have been reviewed.
- If local project rules are stricter, follow them.

## Bundled Resources

- `scripts/scaffold_test_project.py`: create a new project without overwriting an existing nonempty directory.
- `scripts/validate_test_project.py`: validate structure and completed run contracts without instrument access.
- `scripts/test_skill.py`: exercise the scaffold and Python helpers in a temporary directory.
- `assets/project-template/code/result_management/`: MATLAB and Python result helpers.
- `assets/project-template/code/plotting/`: MATLAB and Python plotting helpers.
- `assets/project-template/code/tests/`: hardware-free helper tests.
- `assets/tx-rx-workbench/`: frozen complete MATLAB TX/RX reference, previews, copy tool and adaptation/provenance records; load only for workbench or module reuse.
- `evals/trigger-evals.json`: positive and near-miss negative trigger cases.
