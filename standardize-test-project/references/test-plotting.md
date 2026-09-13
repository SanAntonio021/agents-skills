# MATLAB 公共测试绘图规范

本规范用于实验程序自动生成的观察图和解调诊断图。新增测试先复用公共 helper，再适配数据和选择面板，不为每次测试创建新的频谱计算或绘图实现。真实采集、同步、均衡、解调与指标算法由实验程序负责；绘图程序不会连接仪器或补做 DSP。

## 1. 图组与显示

| 图组 | 默认内容 |
|---|---|
| 单通道观察 | 原始电压波形、单边 PSD；显示物理通道、有效值与峰峰值 |
| IQ 观察 | I、Q 两行，每行左波形、右频谱；I 蓝 `#0072B2`、Q 橙 `#D55E00`，同时标物理通道 |
| 解调结果 | 复用采集基础图，按实际阶段补充复基带频谱、同步/均衡/跟踪曲线与星座 |

观察频谱默认完整可信频段。解调总览有可信信号频段时聚焦信号及邻近带外区域，缺少依据则保留完整频段，不猜中心或带宽。两者显示范围可不同，相同输入和计算参数得到相同数值结果。

波形保留原始电压、直流偏置和时间。已知示波器设置时沿用真实范围，横向十格、纵向八格；缺少设置时按数据适配并注明。所有统计与 PSD 使用完整输入，按像素抽样仅是临时显示优化。

星座保持 I/Q 等比例，不额外归一化或拉伸；同一业务符号集且幅度基准相同的可比较阶段共用坐标范围。训练与业务分开，只显示输入提供的理想点和已有指标，不根据调制名称猜出新的测量结果。显示点数与实际点数不同时注明。面板按真实流程产生，每页最多十二个逻辑面板，超过分页，不固定某个算法的图数。

采用白底、中文专业标签、浅灰网格及随窗口调整的字体。布局、遮挡与两种窗口尺寸验收沿用 [输出规范第4节](standard.md#4-自动绘图与重绘)。界面缩放或裁切不得改变频段统计，图内应保留单位、来源阶段及必要幅度基准。

## 2. 统一计算口径

- 采样率使用实际均匀时间间隔，或有来源说明的可信 `fs_hz`。时间轴非有限、不递增、不均匀，或输入值无效时记录失败，不静默删除样点以便继续算图。时间与采样率冲突不能静默选择一个。
- PSD 默认 periodic Hann 窗，50% 重叠；窗口长度为不超过 `min(N,65536)` 的最大二次幂，FFT 长度等于窗口长度。从全部候选段中等距选择最多八段平均。允许显式修改窗口长度、段数和去均值选项；保存实际窗口、选段位置、FFT 长度、采样率、频率间隔和去均值状态。输入太短而无法形成有效窗时标为不可用。
- 线性 PSD 按 `abs(FFT(x .* w)).^2 / (fs * sum(w.^2))` 计算后按实际段平均。实通道单边谱只将非 DC、非 Nyquist 频点翻倍；复信号使用居中双边谱。零补点不能标成更高实际频率分辨率。
- 原始电压通道保留线性电压 PSD。阻抗来源可信且为正值时可换算 dBm/Hz；否则使用电压谱密度单位。不能把 PSD、频点功率和带内功率混写。数字归一化复谱使用其数字幅度基准，不标绝对 RF 功率。
- 带内功率使用请求闭区间中的频点线性功率求和，即 `sum(PSD(mask)) * df`；记录请求边界、实际纳入频点范围、点数和 `df`。请求区间部分超出有效域或没有频点时结果不可用，不截断请求后冒充原范围。显示缩放不改变这项计算。
- 有效值、峰峰值与整段统计来自完整原始样点，PSD 去均值不改变保存的原波形及原波形统计。

原始 I/Q 合成复信号必须同时满足两路 `sync_verified=true`、样本数量一致及时间网格一致；否则保留原始 I/Q 面板并返回失败原因，不能调用合成分支。仅相同 `fs_hz` 不构成同步确认。已有 DSP 对齐后的复信号走单独的复信号输入分支，必须带明确阶段来源与幅度基准；该接口不会自行重采样或校准 I/Q。

## 3. 公共接口与数据契约

公共源码位于 `assets/project-template/code/plotting/`。新接口 options 使用 `lower_snake_case` 字段；具体可选字段以函数头及示例为准。旧 `Test_Project_Plot_Spectrum`、`Test_Project_Plot_Constellation` 保留既有大写字段接口，作为兼容包装调用公共实现。

| 接口 | 职责 |
|---|---|
| `Test_Project_Analyze_Capture(channels, options)` | 完整采集波形、统计与每通道 PSD；不合成未经确认的 I/Q |
| `Test_Project_Compute_PSD` | 统一线性 PSD，供采集分析和复谱接口复用；带内功率由 Analyze 计算 |
| `Test_Project_Complex_Spectrum` | 有同步检查的原始 I/Q 或有阶段来源的 DSP 复信号频谱 |
| `Test_Project_Make_Plot_Data(analysis, profile, panels, source, view)` | 组装采集基础图和实际处理阶段，形成版本化数值输入 |
| `Test_Project_Draw_Waveform(ax, waveform, options)` / `Draw_Spectrum(ax, spectrum, options)` | 在传入坐标轴中绘制或更新波形/频谱，不重复分析 |
| `Test_Project_Draw_Constellation(ax, data, options)` / `Draw_Curve(ax, data, options)` | 绘制输入提供的星座或诊断曲线，不计算解调指标 |
| `Test_Project_Plot_Test(outputPath, plotData, options)` | 同一渲染器组合总览或按面板 ID 导出独立图 |
| `Test_Project_Save_Plot_Data(path, plotData)` / `Load_Plot_Data(path)` | 保存、校验并加载数值契约；拒绝未知主版本 |
| `Test_Project_Replot_Test(sourcePath, projectRoot, options)` | 只读数值归档，在新的分析轮次导出 |

`channels` 每项必含 `id`、`role`、原始电压列向量 `samples`，以及 `time_s` 或有来源说明的 `fs_hz`。物理通道标签、阻抗及其来源、示波器量程、时间范围、可信带宽为可选元数据；`sync_verified` 默认 false。`analysis.channels` 保存完整波形、有效值、峰峰值、完整线性 PSD、实际计算参数及各自状态，不用像素抽样值替换这些数据。

`plotData` 固定包含 `schema_name`、`schema_version=1`、`profile`、`source`、`analysis`、`panels`、`view`。来源能区分实测、合成与离线数据，并可关联采集帧。每个面板有唯一 ID、类型、标题、`status`、`reason`、上游依赖，并引用公共分析结果或保存完整阶段曲线/星座数据。仅 `ok / failed / skipped` 三种面板状态；失败保留标题和原因，依赖失败的后续面板标 `skipped`，算法本来不存在的步骤不创建面板。

图形句柄、按像素缩减的显示数组等仅在临时缓存中。实时程序保留最近一次完成渲染的不可变分析数据及帧标识；保存动作使用该帧数据，不能重新采集或使用已排队的下一帧。总览、独立图和实时观察都接受同一份分析，不因显示选择另算一份频谱。

## 4. 接入、保存与兼容

1. 读取目标程序，定位采集后的原始通道数据、真实 DSP 阶段及现有保存入口。已有单图/实时界面只合并必要 helper 与依赖；没有必要时不复制工作台或运行通用脚手架。
2. 调用 `Test_Project_Analyze_Capture` 一次，把分析传入实时绘制或 `Test_Project_Make_Plot_Data`。解调程序只添加本算法实际输出的阶段数据；共享图元与 PSD 算法继续使用公共源码。
3. 默认导出总览及 `data/test_plot_data.mat`，其中变量名为 `plotData`。独立图按需导出。已有工程的 `plot_data.mat` 可加入独立子结构，保持外层格式和原读取器；这种接入由适配代码明确完成，不自动批量转换旧包。
4. 重绘写到新的 `analysis/` 轮次并记录来源，禁止回写来源数据、重采集或重新解调。未知主版本报不支持；历史包缺少独立图数值时明确不可用，不从 PNG 补造。

先运行 `Run_Test_Project_Plot_Demos(outputRoot)` 查看单通道、IQ 观察、解调三类合成示例，再沿用示例的数据适配方式。示例与 helper 测试无仪器访问，只能证明对应软件行为。运行实际项目原有 mock 检查用于验证其显示更新与保存接入，不能以公共示例替代项目实机验收。

源程序按模块选择性合并到项目现有目录，保护用户修改并保留许可和来源。通用修复应在维护源码中完成，再通过受支持流程发布并核对运行副本。发布技能不会迁移冻结工作台、已复制工程或现役仪器入口；历史结果保持原位。

## 5. 验证范围

- 数值覆盖常量、单音、噪声、复信号正负频率、已知/未知阻抗、频段闭区间/越界/空频点、无效样点及时间轴。与同窗同段的独立 FFT 参考比较，double 默认相对容差 `1e-10`，零参考值用明确的绝对容差。
- 验证同输入同参数的实时/总览/独立图数值一致，缩放不改功率；同步未确认或网格不一致时不发生原始 I/Q 合成。检查实际显示帧保存、句柄复用及旧接口/旧归档的兼容边界。
- 导出并实际查看 1920×1080、1440×810 两种尺寸，覆盖单通道、IQ、不同调制与解调中途失败。记录至少两种记录长度下的计算/绘制耗时，不承诺未经实机验证的帧率。
- 技能行为用独立上下文实际试跑单通道与 IQ 解调接入，检查产物是否复用公共代码。直接指定加载与普通请求自动触发分开记录；用例定义、静态检查或调用成功不等于触发已通过。


## 6. 最小接入示例与字段

在自己的测试项目中只复制 `assets/project-template/code/plotting/` 的公共文件；需要自动新建重绘轮次时再加入相邻 `result_management/`。把这些项目内目录加到 MATLAB path，不依赖技能运行目录作为实验的永久代码路径。

```matlab
% samples_v、time_s 来自本次完整采集；这里不访问仪器。
channel = struct('id','C1','role','signal','samples',samples_v(:), ...
    'time_s',time_s(:),'impedance_ohm',50, ...
    'voltage_limits_v',[-0.4 0.4],'sync_verified',false);
analysis = Test_Project_Analyze_Capture(channel, ...
    struct('power_band_hz',[0 2e9]));
plotData = Test_Project_Make_Plot_Data(analysis,'single_channel', ...
    struct([]),struct('kind','measurement','frame_id','capture_001'),struct());
result = Test_Project_Plot_Test(fullfile(run_dir,'overview.png'),plotData);
% 按需另存单图，仍用同帧、同参数的数据；不会覆盖已有文件。
result = Test_Project_Plot_Test(fullfile(run_dir,'spectrum.png'),plotData, ...
    struct('panel_ids',{{'C1_spectrum'}}));
% project_root 是接收新 analysis/ 轮次的项目根目录。
result = Test_Project_Replot_Test(run_dir,project_root, ...
    struct('panel_ids',{{'C1_spectrum'}}));
```

上例的阻抗和量程仅示范字段位置，实际值必须来自本次已确认配置或回读；未知时省略。IQ 输入为一个 I 和一个 Q 的 channel 数组，profile 取 `iq_observation`；解调 profile 取 `demodulation`，通过 panels 增加实际阶段。

- 通道必填 `id`（唯一文本）、`role`（`signal/I/Q`）、`samples`（实电压数值列向量）。`time_s` 或正标量 `fs_hz` 与非空 `fs_source` 至少一组；两者同时提供时须一致。可选 `impedance_ohm`、`bandwidth_hz` 默认未知，`voltage_limits_v`、`time_limits_s` 默认空，`sync_verified` 默认 false。
- Analyze options：`window_length=[]`、`overlap_fraction=0.5`、`max_segments=8`（`Inf` 表示全部候选段）、`remove_mean=false`、`power_band_hz=[]`。空频段不报告带内功率；保存实际窗口、选段与频点，不把八段估计描述为遍历全部采样段。
- Plot options：`panel_ids={}`（空为总览）、`target_size_px=[1920 1080]`、`visible=false`、`save_data=true`，以及显式显示范围 `frequency_limits_hz`。`view.title` 控制总标题；`view.signal_band_hz` 为解调近带视图提供物理频段依据。
- 追加面板最少给 `id/kind/title/data`；Make 补齐 `status='ok'`、`reason=''`、`depends_on={}`、`data_ref=struct()`、`options=struct()`。`kind` 仅为 `waveform/spectrum/constellation/curve`。依赖 ID 必须位于本面板之前。
- 曲线 `data` 提供 `x/y/x_unit/y_unit`；星座提供 `symbols`、可选 `ideal_symbols/metrics`。同一批业务符号且幅度基准相同的阶段，把 `panel.options.comparison_group` 设成相同文本；训练图另组或不设置。独立导出仍按完整数据包计算该组公共坐标。
- 复谱通过 `Test_Project_Complex_Spectrum(input,options)` 生成：raw 分支 `input.channels` 含已确认同步的 I/Q；DSP 分支给 `samples/fs_hz/alignment_basis='dsp_aligned'/stage_id/amplitude_unit`，幅度单位仅 `V` 或 `dimensionless`。把返回值直接作为 spectrum 面板的 `data`，不要手工伪造同步依据。
- 引用基础数据时 `data_ref=struct('channel_id','C1','field','waveform')` 或 `field='spectrum'`，不能同时给非空 `data`。完整数值只存一份；渲染返回的 `display_indices/handle` 留在调用者临时状态。

v1 顶层字段、上述通道与面板结构共同构成接口契约。`Load` 遇到原有格式明确交回原项目读取器，不拦截或改写原读取入口。向一个新生成的 `plot_data.mat` 增加公共包时，`Save` 仅在不存在 `test_plot_data` 时追加该变量，原外层变量不变；已有公共包或其他同名 MAT 拒绝覆盖。历史结果不因这项能力自动追加字段。

IQ 物理通道总览共用 PSD 纵轴；任一路阻抗未知时，两路都使用电压谱密度以便比较。可用 `view.psd_y_limits` 显式固定纵轴。每次导出另在 `data/<输出名>_view.json` 记录所选面板、像素尺寸与显示范围，数值归档保持不变。
