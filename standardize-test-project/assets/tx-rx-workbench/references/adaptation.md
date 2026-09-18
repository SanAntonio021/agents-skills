# 使用与适配

## 在实验程序技能中使用

本目录是 `standardize-test-project` 按需使用的完整工作台资源，不是独立技能。通用输出或局部自动绘图修改不需要读取、复制本模板。

新建完整工作台时，使用 [复制脚本](../scripts/copy_template.ps1) 的 `-Destination` 指定新目录，保留全部运行依赖；不再向同一目录叠加通用脚手架。已有项目仅复用局部模块时，先读现有接口并保护修改，只整合所需模块和依赖，验证受影响功能；不默认复制整套工程或运行整套 GUI 验收。已复制出去的工程独立维护。复制脚本补齐本地 README/AGENTS；正式代码、实验数据和必要记录按用途保存，临时材料按共享规范收尾。交付前检查声明入口、重绘数据及依赖不指向待清理目录，执行所需 Template 离线验证；复制时只生成基础说明，不覆盖已有项目。模板版本更新不自动同步到已复制的工程。

本版从来源工程提取必要依赖，并单独记录模板入口与脱敏适配。默认演示目录、文件格式和本版验收状态以随包说明为准，不沿用旧快照或来源工程的通过结论。新任务需要适配输出时读取 [当前实验规范](../../../references/standard.md)，按实际范围修改项目副本；模板演示通过不代表其历史输出已满足当前全部规范。通用工具与本快照中的同名工具分别属于各自工程，不混用 MATLAB 路径或直接互相覆盖。

只要求查询或审查时直接说明，不复制工程、不启动 MATLAB。只有明确复用完整工作台时才运行下方完整演示；相关条件与授权已清楚时继续完成，不增加逐阶段确认。

## 环境与入口

本版独立软件验收目标为 Windows MATLAB R2023b；实际结果及退出状态见下方验收记录，未完成项不得视为已通过。生成和接收需要 Communications Toolbox、Signal Processing Toolbox；完整验证依赖扫描还识别 Control System Toolbox、Statistics and Machine Learning Toolbox、Instrument Control Toolbox。真实 VISA 控制需要厂商 VISA 环境；原始 LeCroy 采集路径不使用 MDD，旧 `full` 会话路径依赖外部 `lecroy_8600a.mdd`，模板不分发该第三方驱动。短帧矩阵属于外部授权依赖，不随包复制，默认例子使用标准长帧。

复制工程后在新的MATLAB会话中进入其目录执行，避免旧项目的同名 `msiq` 包或类仍处于加载状态：

```matlab
Template_Demo                         % 默认 I/Q 长帧模拟生成、解调和图件
Template_Demo('iq')                   % 同上
Template_Demo('real_if')              % 单路实数中频、数字下变频及完整解调
Template_GUI_Demo                    % TX/RX 模拟工作台预览
Template_Validate('smoke')           % 两条信号路径、GUI 和容量预检
Template_Validate('rx_workflows')    % 模拟、单路中频、计算量程和采集设置专项
Template_Validate('rx_plots')        % RX 图组专项
Template_Validate('plot_export')     % 导出专项
Template_Validate('tx_gui')          % TX 交互专项
Template_Validate('rx_gui')          % RX 交互专项
```

演示输出放在新的 `analysis/` 目录，新生成图来自合成数据，不冒充实测。`assets/previews/accepted_RX_*` 是历史布局参考；其他预览是否属于本版，以验收记录为准，不能把旧图当本轮截图。

本版分发入口 `TX_Workbench()`、`RX_Workbench()` 默认模拟，不自动连接设备；实测需明确配置和操作。Template 演示入口提供额外的常用仪器构造函数拒绝保护，退出后恢复。复制脚本不运行 MATLAB、不连接设备。

构造函数拒绝保护仅覆盖当前 MATLAB 进程；异步工作子进程必须显式使用模拟工厂并独立核验，不能假定继承主进程保护。`run_v2_validation('all')` 保留接口，但部分历史用例需要未分发夹具或授权依赖；不要将其当作无条件可运行的独立模板验收。Template 入口也只有实际完成的本版专项才能报告通过。

## 代码与数据接口

| 要改的内容 | 对应入口/输入 |
|---|---|
| TX操作与GUI | `TX_Workbench.m`、`msiq.tx_workbench_app`、`msiq.traditional_tx` |
| RX操作与GUI | `RX_Workbench.m`、`msiq.rx_workbench_app`、`msiq.traditional_rx` |
| 波形与帧 | `msiq.generate_waveforms(cfg,seed)` 返回 `waveforms,tx_ref` |
| 接收算法 | `msiq.decode_capture(raw,tx_ref,cfg)`；参考业务仅用于指标 |
| 单路实数中频 | `msiq.dsp.real_if_frontend`；按测量位置先数字下变频，再接已有解调链 |
| TX绘图 | `msiq.plotting.tx_dashboard(path,plan,execution)`；`plan` 由 `preview_plan` 生成，含 `cfg,tx_ref,waveforms,download,desired,memory_capacity` |
| RX绘图 | `msiq.plotting.rx_dashboard(path,raw,validation,context,result)` |
| 设备与路由 | `code/+msiq/+instruments/`、`config/awg_routes.json` |
| 输出与重绘 | `msiq.plot_archive`、`msiq.replot_run`、`code/result_management/` |

RX绘图的 `raw.channels` 各含通道名、实际样点、时间轴和采样率；`context` 含cfg、tx_ref、scope_status及plot_options.figure_size；`result.pairs.decoded` 为解调输出，包含同步、训练、各业务星座阶段、跟踪和最终指标。缺失阶段应明确缺失，不能拿其他阶段冒充。`Template_Demo.m` 展示完整组装过程，可作为新算法适配起点。

已有复数 I/Q 和单路实数中频路径可直接适配；单路实数采集不等于任意单 DAC 发送。新增发送形式需一起处理波形生成、参考身份、通道数量、接收算法和图表，本版未实现所有单 DAC 算法。

中频板和固定六子带是可选实验模块，普通 I/Q 模拟不需要板卡。子带频率、调制方式、默认占格、图号和布局都是配置或示例，不能据此认定其他设备的能力。端口阻抗与采样设置以实际可信状态为准，不将示例回退值当作实机回读。

更换调制方式时，先处理 `msiq.build_config` 中的16QAM配置校验（`msiq:config:ModulationLocked`），再核对bits_per_symbol、FEC映射、完整码块长度、训练/导频规则及星座参考点。现有TX预览有modulation_order覆盖入口，不代表所有配置和接收路径天然支持64QAM；不能只改JSON或图题就宣布适配完成。

## 设备参考与安全

连接参考使用占位配置，不包含可直接用于本机的设备地址、串口或个人偏好，也不会自动生成 `instruments.local.json`。真实测试应配置实际设备身份、通道和地址，保留本轮已确认的接线及授权；历史实验通道不自动成为新实验物理映射。

M8195A容量规则保留已有模块：FOUR+INT每通道262144点，RDIV不改变INT容量；EXT按选件、RDIV、拓扑检查。检查使用最终128点对齐的下载数组，失败不写仪器、不修改已有输出。连接参考不是下次实验的公共状态写入许可。

容量不足时不截断波形、不自行改变采样率或切换路由，不改变其他使用者的输出。真实运行由 [link-test](../../../../link-test/SKILL.md) 和项目现有保护承接，沿用本轮有效授权并核对设备身份、接线、通道占用和实际状态；历史连接参考不替代当前条件。

LeCroy原始波形路径保留当前观察/正式采集区别、回读字段、时间轴、量程和STOP后的TRMD AUTO恢复。每次采集的真实回读优先于历史参考。

## 验证与来源

`references/provenance/source-files.json` 记录原文件哈希；`source.json` 记录提交、捕获时间、工作区脏状态；`tracked-changes.patch` 保存所复制已跟踪文件相对提交的差异。未跟踪依赖的完整内容已在快照中，其哈希也在清单中。模板新增演示文件独立标识，不覆盖来源源码。

`run_v2_validation.m` 保留原完整入口；只将本次实际运行的专项算作通过。运行时生成的CSV/MAT/PNG是验证证据，不反写到模板源码。模板通过软件验证不等于真实仪器验收。GUI截图检查与控件交互断言都需要完成。

本版[验收状态](provenance/validation.json)须由新的独立复制目录、新 MATLAB 进程验证后填写。未完成时保持待验，不使用来源工程通过记录代替。目标覆盖 I/Q、单路实数中频、正常 GUI、受影响流程和两种实际窗口尺寸，并分别记录首次失败、复验、退出状态及主/子进程仪器访问证据。

R2023a 历史问题仍未解决：此前专项断言通过后出现 `0xc0000374` 堆损坏，大尺寸 GUI 曾被压缩。即使本版 R2023b 通过也不能宣称解决 R2023a 兼容性；真实高 DPI 和实机控制、细调匹配仍需另验。软件验收与安装发布分开记录，准确提交、定向同步及同参数 VerifyOnly 结果以本次发布回执为准。

TX 实测 GUI 须显式提供 `backend_options`（包含实际设备配置）及 `board_options`（板卡使用时指定实测来源与配置）；默认只提供模拟后端且不自动连接。显式传入的后端选项保持调用方语义，不会被模板悄悄改为模拟。
