---
name: standardize-test-project
description: Standardize or scaffold projects whose main purpose is physical experiments, instrument measurements, parameter sweeps, hardware-free dry-runs, scientific simulations that produce run artifacts, or offline replay and cross-run analysis of those runs. Use whenever creating or reorganizing this kind of test project, adding experimental acquisition code, defining result folders and file names, or unifying constellation, spectrum, frequency-sweep, power-sweep, BER, and overview plots. Do not use for ordinary software unit or integration tests, CI test suites, generic application repositories, pure data-analysis repositories without experimental runs, documentation-only projects, or standalone historical-result migration or cleanup that does not change future run structure or code.
---

# Standardize Test Project

Apply one stable contract to experimental code, run artifacts, replay, and automatic plots. Preserve project-specific hardware safety rules and historical results.

## Workflow

1. Read the target project's `AGENTS.md`, related rules, existing entry points, result paths, and representative outputs before editing.
2. Read [references/standard.md](references/standard.md) completely. Treat it as the canonical directory, naming, metadata, table, replay, and plotting contract.
3. Classify the target as a new project or an existing project:
   - New project: run `scripts/scaffold_test_project.py` with the project path, project name, and language.
   - Existing project: inventory first. Change future defaults only. Do not move, rename, rewrite, or delete historical results.
4. Keep human-run entry scripts at project root. Put implementation under `code/` and generated runs under `results/`.
5. Reuse the deterministic helpers in `assets/project-template/code/` instead of duplicating naming, JSON, CSV, log, and plotting logic in experiment scripts.
6. Integrate one dry-run path before any hardware path. Short-circuit before creating or initializing hardware objects. Side-effect-free shared imports are allowed; imports with hardware side effects, connections, queries, and writes are not.
7. Run `scripts/validate_test_project.py <project>` and the language-specific tests. Use only isolated temporary result roots during validation.
8. Report the resulting structure, validation evidence, unchanged-history check, and any project-specific gaps.

## Required Result Contract

- One complete run creates one folder under exactly one of `results/single_point`, `scan`, `dry_run`, `simulation`, or `analysis`.
- Keep each run folder flat. Store repeats, attempts, raw data, point plots, replay files, and summaries as files, never point subfolders.
- Use real decimal points and units: `RF112.0GHz`, not `RF112p0GHz`. Use `repeat01` for planned repetition, `attempt01` for retry, and `FAILED_` for retained failed artifacts.
- Give the user `overview.png` for browsing and `summary.csv` for details. Put metric names in CSV row 1, units in row 2, and observations from row 3.
- Maintain `run_info.json` and `run_log.txt` for machine traceability. Never substitute Markdown for these records.
- Put one-run replay files back in the source run with a timestamped `replay_` or `analysis_` prefix. Put multi-run analysis in `results/analysis/<run>/` with `sources.txt`.
- Export automatic plots as readable 300 dpi PNG files with Chinese professional labels and the common paper-style settings. Do not auto-export publication vector files.

## Safety Gates

- Stop before real instrument I/O unless the user has confirmed the current hardware mode, physical wiring, role mapping, and applicable shutdown behavior.
- Never treat dry-run or synthetic data as hardware measurement.
- Never overwrite a run directory or raw artifact.
- Never migrate history as a side effect of standardizing future runs. Historical migration is a separate inventory, dry-run, and rollback task.
- If local project rules are stricter, follow them.

## Bundled Resources

- `scripts/scaffold_test_project.py`: create a new project without overwriting an existing nonempty directory.
- `scripts/validate_test_project.py`: validate structure and completed run contracts without instrument access.
- `scripts/test_skill.py`: exercise the scaffold and Python helpers in a temporary directory.
- `assets/project-template/code/result_management/`: MATLAB and Python result helpers.
- `assets/project-template/code/plotting/`: MATLAB and Python plotting helpers.
- `assets/project-template/code/tests/`: hardware-free helper tests.
- `evals/trigger-evals.json`: positive and near-miss negative trigger cases.
