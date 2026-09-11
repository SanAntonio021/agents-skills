# 使用与适配

## 环境与入口

来源工程使用 Windows MATLAB R2023a；本次软件验收在 Windows MATLAB R2023b Update 6（23.2.0.2485118）完成。生成和接收需要 Communications Toolbox、Signal Processing Toolbox；完整验证依赖扫描还识别 Control System Toolbox、Statistics and Machine Learning Toolbox、Instrument Control Toolbox。真实 VISA 控制需要厂商 VISA 环境；原始 LeCroy 采集路径不使用 MDD，旧 `full` 会话路径依赖外部 `lecroy_8600a.mdd`，模板不分发该第三方驱动。短帧矩阵属于外部授权依赖，不随包复制，默认例子使用标准长帧。

复制工程后在新的MATLAB会话中进入其目录执行，避免旧项目的同名 `msiq` 包或类仍处于加载状态：

```matlab
Template_Demo                          % 确定种子的TX生成、RX真实DSP仿真及两尺寸图
Template_GUI_Demo                     % TX/RX mock工作台，两尺寸预览
Template_Validate('smoke')            % 上述演示加容量安全专项
Template_Validate('rx_plots')         % 原RX图组专项
Template_Validate('plot_export')      % 原导出专项
Template_Validate('tx_gui')           % 原TX工作台交互专项
Template_Validate('rx_gui')           % 原RX工作台交互专项
```

演示输出放在新的 `analysis/` 目录，新生成图来自合成数据，不冒充实测。`assets/previews/accepted_RX_*` 是用户此前认可的历史RX参考图，`TX_*`、`RX_*` 为本次合成或mock示例，两者不能混作同一轮验证。无参数原工作台是硬件入口；仅演示时始终使用 Template 入口。演示设置mock、禁用真实自动连接，并对常用仪器构造函数设置拒绝保护，保护在退出时恢复。复制脚本不运行 MATLAB、不连接设备。

构造函数拒绝保护只覆盖当前MATLAB进程。原RX异步专项启动的子进程使用显式mock工厂隔离，不声称其继承了主进程的路径保护。原 `run_v2_validation('all')` 及历史回放入口含未打包的历史夹具路径，执行它们需另行提供数据和授权依赖；独立运行保证限定为Template入口和本次实际通过的专项。

## 代码与数据接口

| 要改的内容 | 对应入口/输入 |
|---|---|
| TX操作与GUI | `TX_Workbench.m`、`msiq.tx_workbench_app`、`msiq.traditional_tx` |
| RX操作与GUI | `RX_Workbench.m`、`msiq.rx_workbench_app`、`msiq.traditional_rx` |
| 波形与帧 | `msiq.generate_waveforms(cfg,seed)` 返回 `waveforms,tx_ref` |
| 接收算法 | `msiq.decode_capture(raw,tx_ref,cfg)`；参考业务仅用于指标 |
| TX绘图 | `msiq.plotting.tx_dashboard(path,plan,execution)`；`plan` 由 `preview_plan` 生成，含 `cfg,tx_ref,waveforms,download,desired,memory_capacity` |
| RX绘图 | `msiq.plotting.rx_dashboard(path,raw,validation,context,result)` |
| 设备与路由 | `code/+msiq/+instruments/`、`config/awg_routes.json` |
| 输出与重绘 | `msiq.plot_archive`、`msiq.replot_run`、`code/result_management/` |

RX绘图的 `raw.channels` 各含通道名、实际样点、时间轴和采样率；`context` 含cfg、tx_ref、scope_status及plot_options.figure_size；`result.pairs.decoded` 为解调输出，包含同步、训练、各业务星座阶段、跟踪和最终指标。缺失阶段应明确缺失，不能拿其他阶段冒充。`Template_Demo.m` 展示完整组装过程，可作为新算法适配起点。

TX独立导出保留原版正方形画布；横屏两尺寸示例通过源码已有的 `target_axes` 接口排版，不拉伸已有PNG。RX总览原生支持两尺寸。图号、布局、调制方式均允许修改，不能将本例50Ω回退规则默认为其他实验的已回读阻抗。

更换调制方式时，先处理 `msiq.build_config` 中的16QAM配置校验（`msiq:config:ModulationLocked`），再核对bits_per_symbol、FEC映射、完整码块长度、训练/导频规则及星座参考点。现有TX预览有modulation_order覆盖入口，不代表所有配置和接收路径天然支持64QAM；不能只改JSON或图题就宣布适配完成。

## 设备参考与安全

连接参考文件保存提取时本机配置：AWG localhost、示波器192.168.1.123，以及配置中的C1/C2。此前C3/C4实验也是有效案例，但不能据此替换当前文件内容或宣称现场已确认。本机配置参考不会自动成为 `instruments.local.json`；按下一次实验实际接线复制必要字段，重新记录确认。

M8195A容量规则保留已有模块：FOUR+INT每通道262144点，RDIV不改变INT容量；EXT按选件、RDIV、拓扑检查。检查使用最终128点对齐的下载数组，失败不写仪器、不修改已有输出。连接参考不是下次实验的公共状态写入许可。

LeCroy原始波形路径保留当前观察/正式采集区别、回读字段、时间轴、量程和STOP后的TRMD AUTO恢复。每次采集的真实回读优先于历史参考。

## 验证与来源

`references/provenance/source-files.json` 记录原文件哈希；`source.json` 记录提交、捕获时间、工作区脏状态；`tracked-changes.patch` 保存所复制已跟踪文件相对提交的差异。未跟踪依赖的完整内容已在快照中，其哈希也在清单中。模板新增演示文件独立标识，不覆盖来源源码。

`run_v2_validation.m` 保留原完整入口；只将本次实际运行的专项算作通过。运行时生成的CSV/MAT/PNG是验证证据，不反写到模板源码。模板通过软件验证不等于真实仪器验收。GUI截图检查与控件交互断言都需要完成。

本次[验收状态](provenance/validation.json)为 R2023b 软件验收通过：通用 Python 自检验证10个运行，MATLAB helper 19项通过；最终 smoke、RX绘图、导出几何及TX/RX完整GUI专项均通过，独立验收进程退出码全部为0。TX/RX GUI的1100×700和1500×900实际尺寸回读及截图目视检查通过，合成总览的1920×1080和1440×810导出也已检查。RX异步专项另由外层保留进程句柄读取工作子进程退出码，全部为0，无遗留MATLAB子进程。全部验证使用仿真或mock，未连接真实仪器。

原电脑R2023a的历史记录完整保留在验收文件的 historical_candidate_r2023a 中：专项断言通过后仍报0xc0000374堆损坏，大尺寸GUI曾被压缩。本机R2023b通过不代表R2023a问题已经解决。软件验收与安装发布分开记录；具体提交、定向同步及同参数VerifyOnly结果以本次发布回执为准。
