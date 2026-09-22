---
name: standardize-test-project
description: 实验规范：新建或修改实验/科研仿真程序，统一单通道波形与频谱、IQ 观察、解调图组及结果保存；用户说“按实验规范来做”“用实验规范”时使用。Build and modify experimental or scientific simulation programs, including reusable MATLAB single-channel waveform/spectrum, IQ observation and demodulation diagnostic plots, result directories, retention, replay, and hardware-free validation. Use for new tests, unified test plotting, future output changes, parameter sweeps, compact/full simulation storage, and offline run analysis. Also reuse the complete MATLAB TX/RX workbench and M8195A/LeCroy adapters when needed. Real instrument operation belongs to link-test. Do not use for ordinary software tests, standalone publication figures or analysis without experimental runs, documentation-only work, or historical-result migration that does not change future code or outputs.
---

# 实验规范（Standardize Test Project）

中文调用名为“实验规范”。在本技能适用任务中，“按实验规范来做”或“用实验规范”表示加载本技能；内部标识仍为 `standardize-test-project`。

Build or adapt experimental programs with a consistent output contract. Reuse the complete TX/RX workbench only when the task needs it. Preserve project-specific hardware safety rules and historical results.

## Workflow

1. Read the request, target project's rules, existing entry points and relevant files. Reuse the confirmed scope and authorization. A read-only question ends with findings and suggestions; it does not authorize scaffolding, file changes or instrument access.
2. Select the necessary resources:
   - **General experimental project or output changes:** use [the output standard](references/standard.md). Read sections 1–3 for directories, observations and precision; section 4 for automatic plots/replot; section 5 for analysis, compatibility and safety; section 6 for retention and storage acceptance. Read the whole standard when implementing a complete output lifecycle. Ordinary output or plotting tasks do not load the workbench assets.
   - **Complete MATLAB TX/RX workbench:** follow [Workbench reuse](#workbench-reuse). Copy its complete dependencies, without also running the generic scaffold.
   - **Existing project, selected module or plot:** keep its architecture and integrate only the requested module and dependencies. Read the relevant standard sections, and the workbench adaptation guide only if using a workbench module. Plot-only work applies section 4 to the existing source and checks affected normal/compact exports; skip scaffolding, directory migration and unrelated lifecycle tests.
   - **MATLAB single-channel/IQ observation or demodulation plots:** read [the shared test-plotting contract](references/test-plotting.md) and reuse `assets/project-template/code/plotting/`. Adapt input data and select panels; do not create another private PSD calculation or waveform/spectrum renderer for each new test. An existing plot-only task needs only the selected helpers and dependencies, not a whole project copy. Python helpers retain their existing interfaces; this shared numeric contract is MATLAB-first.
3. For a new general project, run `scripts/scaffold_test_project.py` with project path, name and language. Generate README.md and AGENTS.md by default. Keep human-run entry scripts at root and use `code/`, `config/`, `simulation/`, `measurement/`, `analysis/`, `checks/`. For existing projects, change future defaults only; keep historical results in place.
4. When changing output writers, reuse compatible project helpers or `assets/project-template/code/`. New writers use timestamp-first directories, exclusive suffix allocation, visible images/display CSV and flat `data/`. Helpers expose retention mode; writers choose compact/full payloads, and plotting helpers save lossless replot inputs when the run has `data/`.
5. Apply [Validation and dry-run](#validation-and-dry-run) to the affected behavior. Report the actual changes, validation, preserved inputs/history, and remaining gaps; source reuse, mock execution and real instrument acceptance are distinct.

Formal project content follows the shared global file policy: the six professional directories retain code, raw data, replot inputs and necessary run records. Agent-created drafts, temporary scripts and previews belong in `过程文件/任务主题/`. Explicit cleanup promotes adopted content and its dependencies into formal locations, updates references and verifies them before clearing only that task directory; ordinary completion does not clear it. Do not require a separate output directory.

指标表按 [实验指标表](references/experiment-tables.md) 命名并分开名称与单位；显示精度按设置或测量依据选择。主表逐次记录，跨观测统计需已有实验设计或后续讨论依据。整轮总览在具体实验时设计，不将单次解调图组当作整轮固定模板。

## 界面文案检查

新建或修改 MATLAB 上位机、实验工作台或其他实验 GUI 时，生成可见文字前读取 [writing-router](../writing-router/SKILL.md) 的“界面文案”分支，按该分支实际加载 `style-vocab` 和适用词表。已有任务加载记录可复用；仅提到技能名不算完成调用。只改算法、数据保存或科研图数值且未涉及界面文字时，不增加 GUI 文案流程。

界面交付分别核验：①可见文字的含义、术语一致性、必要性和操作指向；②目标窗口尺寸下的实际截图，包括文字截断、可读性、信息分组、分隔符使用及当前步骤和下一操作；③受影响的功能行为。实验前面板应精简解释性文字，同时保留设备名称、IP、连接状态、当前动作和错误等必要反馈；优先通过布局、字段组和分组区域组织这些信息，避免把多项内容串成一长段。功能测试或词表无命中均不能替代前两项。无法运行窗口时可以完成源码文案检查，但明确窗口视觉检查未验证，不宣称界面已验收。仅润色既有文字时不重建布局或扩大硬件测试。

## 工作台交互与状态

新建或修改带仪器控制、异步采集或结果浏览的实验工作台时，读取 [工作台交互与状态检查](references/workbench-interaction.md)，只应用受影响的条目。简单脚本、独立图件或无相关行为的 GUI 不需要补齐整套工作台功能。

## Shared MATLAB Test Plotting

- Single-channel observation uses raw voltage waveform plus one-sided PSD. IQ observation uses I/Q rows with waveform/spectrum columns. Demodulation reuses those capture panels and adds actual processing stages, centered complex spectra and constellations; there is no fixed algorithm or panel count.
- For demodulation, preserve an existing user-approved dashboard's stage order, panel proportions and comparison layout. Use the grouped receive-chain example in the plotting contract as the reference: acquisition/synchronization above, training/tracking in the middle, comparable payload constellations below. A flat equal-tile gallery is only a fallback when no reference layout exists. Keep already accepted single-channel and IQ observation layouts intact when adapting demodulation.
- Keep analysis, single-panel rendering, composition and save/replot separate. Use `Test_Project_Analyze_Capture`, the `Test_Project_Draw_*` helpers and `Test_Project_Plot_Test`; use `Test_Project_Make_Plot_Data` to assemble the versioned input. The detailed reference owns calculation defaults, units, synchronization guards and the data contract.
- Real-time and exported plots consume the same analyzed frame and parameters. Display thinning and zoom never replace full samples, PSD arrays or band-power calculation. Save the frame actually displayed, not a new acquisition.
- Default persistence is overview PNG plus `data/test_plot_data.mat` containing numeric `plotData` schema v1. Export independent panels on request using the same renderer. Existing archives and APIs retain their readers/wrappers; do not infer missing stage data from PNG files.
- Merge needed helpers from the maintained skill source into the target project's existing structure, preserving user edits and licenses. Change shared behavior in the maintained source and validate selective project integration; never edit CC Switch/Claude/Codex runtime copies as source. Updating this skill does not migrate frozen workbench assets, existing project entry points or instrument code.

## Workbench Reuse

Read [the adaptation guide](assets/tx-rx-workbench/references/adaptation.md) and relevant [TX/RX previews](assets/tx-rx-workbench/assets/previews/) when choosing or adapting this implementation. It is a complete reference project, not a mandatory algorithm or UI.

- For complete reuse, run [copy_template.ps1](assets/tx-rx-workbench/scripts/copy_template.ps1) with `-Destination` pointing to a new directory. It refuses an existing destination. Keep the namespace and runtime dependencies together; the two root entry files alone are insufficient. Local reuse integrates only needed modules and dependencies into a protected current project.
- For complete reuse, run `Template_Validate('smoke')`, which includes `Template_Demo('iq')`, `Template_Demo('real_if')` and mock `Template_GUI_Demo`, then only additional plotting/GUI checks relevant to the adaptation. Do not repeat these demos after a successful smoke. The distributed template defaults to simulation; real instrument access still requires explicit configuration and action. Verify both the main process and asynchronous workers; do not assume a child inherits the parent hardware guard. Local module work runs only its affected checks with isolated inputs.
- Keep instrument adapters, signal forms and optional experiment modules separate when adapting. A single acquired real IF channel is not a new single-DAC transmit algorithm: changing signal form must cover generation, reference, channel mapping, processing and plots together. IF-board control and fixed subband examples remain optional configuration.
- Adapt waveform, receive processing and plot groups on the copy. Preserve real units, data origins and stage meanings. The 16QAM/QPSK example, frame structure, panel count and layout are examples, not required scientific choices.
- New or changed single-channel/IQ plots on the copy use [the shared plotting contract](references/test-plotting.md) and common helpers above. Keep the versioned workbench snapshot separate from selective integrations into existing projects; updating the skill does not update those projects.
- Source hashes, device references and historical acceptance remain in [provenance](assets/tx-rx-workbench/references/provenance/). Use this version’s independent acceptance record, not historical source-project results, to establish template behavior. The snapshot retains documented output behavior and helper differences; it is not proof of full current output-contract compliance. Apply the current standard to the new project's requested output adaptations without silently rewriting the snapshot or previously copied projects.
- Hardware operation uses [link-test](../link-test/SKILL.md) and current project protections. Device references do not supply new wiring confirmation or instrument authorization. Reuse valid current authorization; retain capacity, alignment, shared-channel, read-back and shutdown safeguards described in the adaptation guide.

## Validation and Dry-Run

Select checks by actual changes: scaffold/whole-output work uses `scripts/validate_test_project.py <project>`, applicable project tests and language helpers; a local module or plot change checks affected behavior. Use isolated temporary projects or result roots, never real instrument access as an incidental software test.

- For delivery/cleanup, optionally run `scripts/validate_test_project.py <project> --delivery-manifest <json>`; declare formal entry points and dependencies as described in section 5 of the standard. This checks declared local paths and analysis source references, not arbitrary code or MAT internals; also perform the actual open/replot/build check. External formal sources are permitted.
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
- `references/test-plotting.md`: shared MATLAB waveform/PSD/IQ/stage contract and integration example.
- `assets/project-template/Run_Test_Project_Plot_Demos.m`: synthetic single-channel, IQ observation and demodulation examples; no instrument access.
- `assets/project-template/code/tests/`: hardware-free helper tests.
- `assets/tx-rx-workbench/`: frozen complete MATLAB TX/RX reference, previews, copy tool and adaptation/provenance records; load only for workbench or module reuse.
- `evals/trigger-evals.json`: positive and near-miss negative trigger cases.
