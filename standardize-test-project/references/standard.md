# 实验与仿真输出规范

统一以后脚本和程序的输出。一次完整执行称为一轮，固定条件重复采集和多点扫描都可以是一轮。沿用项目仪器保护与已有授权，不改变科学算法或历史结果。

## 1. 项目与运行目录

根目录采用六个主要目录：`code/`、`config/`、`simulation/`、`measurement/`、`analysis/`、`checks/`。人工入口、README 和唯一实验主记录留在根目录；代码内部沿用既有职责，不默认新增每轮 Markdown 报告或平台规则副本。

- simulation：模型计算、合成数据和离线波形生成。
- measurement：真实采集，包括硬件诊断及只读预检。
- analysis：已有数据重新处理、重绘和对比，单源与多源均建立新运行。
- checks：程序自检、纯软件验证、无硬件试跑。

`output_category` 与 `execution_mode`、单点/扫描方法分开。真正 dry-run 在创建硬件对象前短路，禁止连接、查询、写入仪器，也不探测旧收件箱、UNC、映射网络盘或测量输入的 exists/stat/open。允许记录计划路径和读取明确提供的本地配置。纯软件仿真自检可以是 category=checks、execution_mode=simulation，访问硬件的验证不能归为无硬件。

程序自动创建 `分类/YYYYMMDD_HHMMSS_实验名称/`，时间是本轮开始的本地时间。中文实验名、简单英文及专业缩写均可，完整参数写数据记录。并发同秒重名时独占创建并追加 `_02`、`_03`，不捏造未来时间。显式输出目录保持精确含义，已存在则拒绝覆盖。

```text
measurement/20260907_143025_双通道电回环/
├── overview.png
├── 001_TxPower-10dBm_Channel1_星座图.png
├── 001_TxPower-10dBm_Channel2_星座图.png
├── summary.csv
└── data/
    ├── run_info.json
    ├── run_log.txt
    ├── observations.csv
    └── 本轮原始数据、参考、配置和重绘输入
```

所有有用图片直接可见，data 内不再分层，不建 plots、参数点或重复次数子目录。无图可画的自检不制造占位总览。禁止落盘的选项约束正常和异常路径；实时观察不强制保存。

## 2. 观测与命名

序号代表一次实际采集/尝试，从 001 开始；同次采集的多个 Channel 共用序号、分别记录，重试是下一序号。计划重复和重试次数仍可保存在详细记录。采集前失败不创建空波形，但保留失败行及错误详情。

文件名采用 `序号_主要控制条件_Channel_类型`；控制条件可以省略，来自本次配置，不反推测量值。TxPower/RxPower 区分发射/接收功率；SNR、MER、EVM、BER 及单位保留常用写法。使用真实小数点、负号和设置分辨率。失败诊断可标 FAILED；失败或缺失不补成正常测量。

旧 repeatNN_attemptNN API 参数仍兼容；新增调用传 observation/observation_index 才采用逐次序号，不从重复与重试索引猜测全局顺序。

## 3. 指标、精度和记录

summary.csv 使用 UTF-8 BOM 和 CSV 转义，第一行名称、第二行单位、第三行起逐次观测；多 Channel 分行。显示必要条件、序号、Channel、方案、当前实验指标和状态，不强制所有实验采用通信指标。观测状态可沿用程序的明确名称，如 decoded、capture_failed；不与整轮运行状态的枚举混用。路径、时间、重试、错误详情放 data/observations.csv 与日志。失败行保留，缺失数值空白，实际 BER=0 保留零。

完整记录 data/observations.csv 保存所有列和原数值，Python 用浮点可回读表示，MATLAB double 用 17 位有效数字。计算与分析通过统一接口读取完整记录，旧版缺失时才回退旧 summary。显示表连续量默认两位小数、计数整数、BER/BLER/FER 三位有效数字科学计数；非零小值不得舍成零。控制参数通过 exact 或 fixed:N 显式保留设置分辨率。MATLAB SummaryFormats 按 matlab.lang.makeValidName(header) 设置，Python formats 按原表头。

data/run_info.json 使用 schema_version=2.0，包含 run_id、project_name、test_name、run_kind、output_category、retention_mode、planned_run_kind、purpose、execution_mode、status、stop_reason、stop_detail、started_at、finished_at、entry_point、code、runtime、primary_variable、parameters、inputs、instruments、counts、safety、source_runs、artifacts。artifact 相对运行目录，只允许根目录文件与 data/文件。

- purpose=formal|validation|debug；执行模式 hardware|hardware_query|dry_run|simulation|offline_replay|offline_analysis。
- status=running|completed|completed_with_failures|failed|stopped；退出后仍 running 表示未正常收尾。
- stop_reason：normal_completion、user_stop、preflight_failed、instrument_connection_failed、instrument_read_failed、instrument_write_failed、acquisition_failed、processing_failed、safety_stop、unhandled_exception。
- counts 区分计划、实际尝试、成功、失败、无效。多个 Channel 的行数不是采集数，重试可使实际尝试超过计划。
- 保存有效配置、随机种子、代码版本/脏状态、环境；Git 不适用时提供实际源码线索。未提交算法代码需对应补丁/快照或说明重跑限制，不逐轮打包仓库。
- JSON 无法无损表达的数组、复数、NaN/Inf 等用语言原生结构化数据保存，JSON 只引用。

日志格式 `ISO8601 | LEVEL | stage | message`，记录必要执行与保存异常、观测序号、来源、仪器状态及安全收尾，禁止密钥。只读读取不刷新/重写源记录。

## 4. 自动绘图与重绘

浏览图默认白底 300 dpi PNG；已有专用渲染器可以保留适合屏幕查看的分辨率，检查文字与曲线清晰度，不以恰好 300 dpi 作为通用门槛。字体 Microsoft YaHei，回退 Noto Sans CJK SC、SimHei。刻度 10 pt、轴名 11 pt、标题 12 pt、轴线 1 pt、曲线 1.5 pt，浅灰网格。物理量/单位明确，不裁切文字。推荐 #0072B2、#D55E00、#009E73、#CC79A7，结合标记区分 Channel/方案。正式投稿矢量图按明确请求导出。

- 总览默认逐次原始观测，不计算/叠加均值、最值、标准差，不跨失败/缺失连线。显式 ShowStatistics/show_statistics 才启用跨观测统计。必要 BER/MER 算法不属于禁止统计。
- 星座保留全部有效点、明显理想点、多个 Channel 相同 1:1 范围，标 N 和存在的指标。只有导出负担不可接受时才可重复均匀抽样并说明显示/实际点数，精简保存不能额外抽稀。超范围点标数量，不删除事实。
- 频谱区分 dBm 与 dBm/Hz，默认不平滑/插值。Peak、ChannelPower、MarkerBandPower 不互换。
- BER 对数图真实零可显示在 1/N_bits 并以空心三角注明位置，数据仍为零。

Python helper 保存安全 NPZ 重绘输入和版本化参数，不使用 pickle；MATLAB PNG helper 在 data 保存原生 .fig，含图形数据、轴与注记。重绘只读取保存输入，不运行仿真/DSP，在新 analysis 目录导出。PNG 存在不能替代视觉检查。

## 5. 分析、兼容与安全

单源/多源分析均新建 analysis 运行，data/sources.txt 每行一个源路径，元数据对应 run_id、实际文件/哈希与处理参数。相对路径优先，外部源可绝对路径；不移动/补写源数据，不复制整套波形。读取先 data，回退 schema 1 根目录。

历史不移动、改名、删除、压缩、重写。旧显式输出、输入收件箱和 resume 参数兼容；新默认目录不是历史迁移。可选绘图库按需加载，不破坏原本无绘图库的 CLI 导入。真实仪器模式、接线、角色与安全收尾沿用有效授权，只有未知实质变化才澄清。

## 6. 保留策略与验收

可重建普通仿真默认 compact：图片、完整逐次指标、全部无损绘图输入、有效参数/种子及必要记录。显式 full 再保存完整波形和中间数组；不可重建输入、断点续算单独保留。helper retention_mode 是策略标记，实际保存者必须据此决定 payload，不能只改元数据。

实测始终保留原始采集、必要参考、逐次配置/仪器状态；相同且不可变参考按实际数组内容核对后同轮只存一份，相对引用，不同内容分开。搬移整轮可读，缺失/损坏引用报错。正式实测与禁止保存冲突时在 I/O 前拒绝；实时观察沿用既有语义。

异常保留已取得的数据及失败现场。普通非零 BER/预期解调失败不升级 full。自检使用自有隔离目录，成功清理自有临时产物，失败保留，不清理共享目录或其他任务数据。

测试四类与模式区别、中文/同秒并发、显式路径防覆盖、多 Channel 同序号、失败重试、表头/显示/完整精度、旧读取及源不改。真正 dry-run 不探测仪器或历史收件箱；已有阶段锁/冻结使用隔离状态测试，并只读核对当前保护。

相同种子小仿真比较 compact/full 指标、全部绘图输入、实际文件数/体积；独立重绘逐图检查，采集保存与异常收尾使用模拟仪器。运行项目相关原测试，核对历史/无关工作不变，发布与本机生效分别验证。
