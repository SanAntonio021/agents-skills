# 测试项目目录与结果规范

本文件是 `standardize-test-project` 的实施契约。项目自己的规则可以更严格，不能更宽松地绕过硬件安全、原始数据保护和结果追溯要求。

## 目录

1. 适用目标与基本原则
2. 标准目录与职责
3. 结果分类
4. 运行和参数点命名
5. 单运行复盘与跨运行分析
6. `run_info.json`
7. `summary.csv` 与日志
8. 自动绘图
9. 旧结果与无硬件验收

## 1. 适用目标与基本原则

用于仪器测试、通信实验、器件测试、参数扫描、科研仿真及其离线复盘。一次完整执行任务称为一轮运行：固定参数重复采集 10 次是一轮，112.0 GHz 到 125.0 GHz 扫频也是一轮。

- 人工直接启动的入口脚本放项目根目录。
- 内部流程、仪器控制、采集、处理、绘图和结果管理放 `code/`。
- 所有采用新规范的运行放 `results/`。
- 一轮运行只建立一个目录，目录内部保持扁平。
- 测试形态由结果分类目录区分；`formal`、`validation`、`debug` 等用途写元数据，不再建组合目录。
- 用户优先看 `overview.png` 和 `summary.csv`；程序读取 JSON、CSV、日志和原始数据。
- 文件名、表格、图片和元数据必须能相互反查。
- 原始数据不得被复盘、重绘或跨运行分析覆盖。

## 2. 标准目录与职责

```text
测试项目/
├── README.md
├── AGENTS.md
├── CLAUDE.md
├── GEMINI.md
├── .gitignore
├── 人工入口脚本.m / .py
├── code/
│   ├── experiments/{single_point,frequency_sweep,power_sweep}/
│   ├── instrument_control/
│   ├── acquisition/
│   ├── signal_processing/
│   ├── plotting/
│   ├── result_management/
│   ├── analysis/
│   ├── simulation/
│   └── tests/
├── config/
├── data/
├── docs/
├── results/{single_point,scan,dry_run,simulation,analysis}/
└── archive/
```

- `code/experiments/` 放完整实验流程，可按温度、延时等变量扩展代码子目录。
- `code/instrument_control/` 只放发现、连接、查询、写入和安全收尾。
- `code/acquisition/` 放波形、频谱和功率采集。
- `code/signal_processing/` 放解调、滤波和指标计算。
- `code/plotting/` 放自动浏览图的公共样式，不放人工挑选后的正式投稿图。
- `code/result_management/` 负责建目录、命名、JSON、CSV、日志和产物登记。
- `code/analysis/` 与 `code/simulation/` 放代码，结果仍放 `results/`。
- `config/` 不保存密码、令牌或不应提交的本机隐私配置。
- `data/` 放外部输入、参考序列、校准和样例，不放本项目运行结果。
- `archive/` 放退役代码和旧说明，不作为正式结果根目录。

## 3. 结果分类

| 目录 | 判定 |
|---|---|
| `results/single_point/` | 主要控制参数固定，可有多次计划内重复采集 |
| `results/scan/` | 至少一个物理变量按计划改变；短扫和完整扫描均在这里 |
| `results/dry_run/` | 仅计划检查；禁止连接、查询或写入仪器 |
| `results/simulation/` | 模型或合成数据，不依赖本轮真实仪器采集 |
| `results/analysis/` | 同时使用两个或更多源运行 |

离线复盘不放 `dry_run/`。用途单独写入 `purpose=formal|validation|debug`。

## 4. 运行和参数点命名

运行目录格式：

```text
主要变量或范围_主要固定条件_YYYYMMDD_HHMMSS
```

要求：

- 不重复上级已有的 `scan`、`single_point`、`dry_run` 等名称。
- 目录只保留有助人工识别的主要条件，完整参数进入 JSON。
- 时间戳固定为本地时间 `YYYYMMDD_HHMMSS`。
- 使用 ASCII 真小数点和与分辨率一致的小数位数，例如 `112.0`，不用 `112p0`。
- 单位紧跟数值，例如 `115.0GHz`、`4.0dBm`、`20.0ns`。
- 负数保留减号；范围含负数时用 `_to_`，如 `P-10.0_to_4.0dBm`。
- 不使用空格、冒号、斜杠或只靠大小写区分的名称。
- 同名目录存在时失败，不覆盖；同秒冲突应重新取时间戳。

示例：

```text
results/single_point/RF115.0GHz_P4.0dBm_20260715_151500/
results/scan/RF112.0-125.0GHz_step0.1GHz_P4.0dBm_20260715_143000/
results/scan/P-10.0_to_4.0dBm_step1.0dB_RF115.0GHz_20260715_160000/
results/dry_run/RF112.0-125.0GHz_step0.1GHz_20260715_141000/
results/simulation/SNR0.0-30.0dB_step1.0dB_20260715_170000/
```

参数点基础名：

```text
<变量><数值><单位>_repeatNN_attemptNN
```

- `repeat01` 是计划内第 1 次重复；`attempt01` 是该重复的第 1 次执行尝试。
- 重试只增加 `attempt`，不增加 `repeat`。
- 序号至少两位，从 `01` 开始，超过 99 自然扩展。
- 多变量按扫描设计顺序写，如 `RF112.0GHz_P-4.0dBm_repeat01_attempt01.mat`。
- 失败后已取得的诊断数据保留，并加 `FAILED_`。采集前失败且没有数据时不创建空原始文件，但 CSV 和日志仍记录失败。
- 运行目录禁止 `traces/`、`figures/`、`repeat01/`、参数点目录等子目录。

## 5. 单运行复盘与跨运行分析

只使用一个原始运行时，派生文件仍放源运行目录，不建子目录，不覆盖原文件：

```text
replay_YYYYMMDD_HHMMSS_run_info.json
replay_YYYYMMDD_HHMMSS_summary.csv
replay_YYYYMMDD_HHMMSS_overview.png
analysis_YYYYMMDD_HHMMSS_power_comparison.png
```

同一轮派生文件使用相同时间戳前缀。复盘 JSON 至少记录原 `run_id`、源文件、代码版本、配置变化和派生产物。

使用两个或更多运行时，新建 `results/analysis/<run>/`。目录仍扁平，并包含 `sources.txt`。`sources.txt` 为 UTF-8，每行一个源运行目录的项目相对路径，顺序等于读取顺序。外部来源可写绝对路径，但 JSON 同时保存来源文件哈希。不得修改源运行。

## 6. `run_info.json`

UTF-8，键名使用稳定英文 `snake_case`，路径优先项目相对路径。创建运行目录后立即原子写入，状态为 `running`；关键状态变化后更新；正常或异常收尾时更新完成时间和最终状态。禁止记录密钥。

必需字段：

```text
schema_version, run_id, project_name, test_name,
run_kind, planned_run_kind, purpose, execution_mode,
status, stop_reason, stop_detail, started_at, finished_at,
entry_point, code, runtime, primary_variable, parameters,
inputs, instruments, counts, safety, source_runs, artifacts
```

固定取值：

- `run_kind`: `single_point|scan|dry_run|simulation|analysis`
- `purpose`: `formal|validation|debug`
- `execution_mode`: `hardware|hardware_query|dry_run|simulation|offline_replay|offline_analysis`；`hardware_query` 仅用于只读仪器预检
- `status`: `running|completed|completed_with_failures|failed|stopped`
- `stop_reason`: 运行中为空；结束后为 `normal_completion|user_stop|preflight_failed|instrument_connection_failed|instrument_read_failed|instrument_write_failed|acquisition_failed|processing_failed|safety_stop|unhandled_exception`

`dry_run` 必须同时写 `planned_run_kind`、`execution_mode=dry_run`、空 `instruments`，日志明确说明未连接、未查询、未写入仪器。

`counts.planned/executed/succeeded/failed/invalid` 按计划重复及其最终结果计数，满足
`executed = succeeded + failed + invalid` 且 `executed <= planned`。每次实际
attempt 仍各占 `summary.csv` 一行；存在重试时增加 `attempted`、
`attempt_succeeded`、`attempt_failed`、`attempt_invalid`，避免把失败重试和最终重复结果混为一层。

最小对象结构：

```json
{
  "code": {"git_commit": null, "git_dirty": null, "entry_file_sha256": null},
  "runtime": {"name": "Python", "version": "3.x", "os": "Windows"},
  "counts": {"planned": 0, "executed": 0, "succeeded": 0, "failed": 0, "invalid": 0},
  "safety": {"preflight": "pending", "shutdown": "pending"},
  "source_runs": [],
  "artifacts": [{"file": "summary.csv", "role": "detail_table"}]
}
```

`status=running` 留到程序退出表示未正常收尾，不能解释成完成。

## 7. `summary.csv` 与日志

`summary.csv` 使用 UTF-8 with BOM 和标准 CSV 转义：

1. 第 1 行是指标名。
2. 第 2 行是单位，无单位写 `-`。
3. 第 3 行起每次实际尝试占一行，失败和成功重试都保留。

指标列放最前。固定追溯尾部为：

```text
状态,repeat,attempt,采集时间,原始数据文件,单次图片文件,错误代码,错误信息
-,-,-,-,-,-,-,-
```

行状态只用 `成功|无效|失败`。缺失数值留空，真实 `BER=0` 保留 0。失败和无效不进入均值与标准差。样本标准差仅在至少 2 个有效观测时计算；一个观测不能用 0 冒充未知波动。

`run_log.txt` 每条一行：

```text
ISO8601时间 | INFO|WARNING|ERROR|DEBUG | 阶段 | 消息
```

日志必须记录入口、用途、运行目录、每个 repeat/attempt、重试、停止、保存异常、硬件读回与安全收尾。`DEBUG` 只用于 `purpose=debug`。dry-run 必须明确记录未访问仪器。

## 8. 自动绘图

自动图片用于日常浏览、检查和筛选，默认只导出白底 300 dpi PNG。正式投稿图在选定数据后另行生成。

通用样式：

- 中文字体优先 `Microsoft YaHei`，回退 `Noto Sans CJK SC`、`SimHei`。
- 刻度 10 pt，坐标名称 11 pt，标题 12 pt，图例和注释 9 pt。
- 坐标轴 1.0 pt，主曲线 1.5 pt，误差条 1.2 pt，标记 5 至 6 pt。
- 主网格浅灰 `#D9D9D9`；不使用装饰渐变、三维效果或只靠颜色区分曲线。
- 推荐颜色：蓝 `#0072B2`、橙红 `#D55E00`、绿 `#009E73`、紫红 `#CC79A7`。
- 坐标名称使用 `物理量 (单位)`，不得裁切标题、刻度、图例或最长中文标签。

星座图：

- 多通道放一张图的左右子图，所有通道使用相同的 1:1 坐标范围。
- 接收符号使用高对比度、不透明深色点；理想点使用更大的黑色空心方框或黑色十字。
- 默认绘制全部有效符号并标 `N`。仅在导出失败或耗时、体积不可接受时使用固定间隔的可重复均匀抽样，同时标显示数和实际数并写日志；禁止随机抽样美化分布。
- 显示 `BER`、`EVM`、`MER` 和 `N`，缺失指标不伪造。超范围符号不删除，图中标超出数量。

频谱图：

- 明确区分 `功率 (dBm)` 与 `功率谱密度 (dBm/Hz)`。
- 默认保留原始采样点，不平滑、不插值。处理方法和参数必须写 JSON。
- `Peak`、`ChannelPower`、`MarkerBandPower` 不得互相替代。
- 同轮点图使用相同频率和功率范围；无效诊断图加 `FAILED_` 且不进入统计。

扫描汇总图：

- 文件固定为 `overview.png`；不同单位使用共享横轴的独立子图。
- 每个变量值画有效原始散点、均值和可用时的 `±1` 样本标准差。
- 无有效观测处留缺口，不跨缺口连线，不在图上堆失败红叉。
- 右上角动态显示 `成功采集：有效次数/计划次数`，具体失败留 CSV 和日志。
- dry-run 总览只显示计划点、阶段和计划观测数，不画伪测量值，也不显示 `成功采集：0/N`。
- BER 跨数量级时用对数轴。真实 BER 0 可画在 `1/N_bits` 并使用空心向下三角，图例说明显示位置；CSV 仍为 0。

## 9. 旧结果与无硬件验收

- 只改变未来运行默认值。旧结果不移动、不改名、不删除、不补写、不压缩、不改内部字段。
- 显式旧路径保持兼容；发现旧目录不能自动迁移或清理。
- 迁移历史前先建立清单、哈希基线、dry-run 和回滚方案。
- 无硬件测试使用隔离临时目录和合成数据，覆盖五类结果、扁平目录、JSON 解析、CSV BOM/两行表头、日志、点图、总览图、单运行复盘和跨运行 `sources.txt`。
- dry-run 测试不得建立仪器连接，也不得执行 SCPI 查询或写入。
- 验收前比较旧结果文件集合、字节数和 SHA256，确认不变。
