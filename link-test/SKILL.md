---
name: link-test
description: 面向高速链路台架的 AWG、示波器、DUT 和 LeCroy 前处理控制工作流，覆盖 `SMOKE/FULL`、`AWG OFF/ON` 配对、单次与重复测试、超时分级、收尾保护、中文测试报告、链路台账，以及 `Interpolation`、`Averaging`、`Enhance Resolution`、`Optimize` 等示波器 Pre-processing 项。Use when 用户要运行、续跑、排查或汇总台架测试，例如“先跑 smoke”“测一轮功率加解调”“做 AWG OFF/ON 配对”“确认示波器 linear/sinx/x”“检查 averaging/enhance resolution”“生成测试报告”或“补台账”。
---

# 高速链路台架测试

## 作用

这份 skill 把高速链路台架测试、LeCroy 前处理控制、结果汇总和台账补录收成一个稳定流程，减少每轮都从头决定“怎么测、怎么记、怎么报告”。

默认目标是先拿到可解释的功率、底噪和解调结果，再决定要不要进入更长的扫描。

## 流程

1. 先确认本轮测试类型：
   - 单点 `SMOKE`
   - 多点扫描
   - `AWG OFF/ON` 配对功率
   - 功率加解调联合验证
   - 仅调整或确认 LeCroy `Pre-processing`
2. 测前固定基线：
   - `OFFSET = 0 mV`
   - `Interpolation = Linear`
   - `AverageSweeps = 1`
   - `EnhanceResType = None`
   - `OptimizeGroupDelay = Flatness`
3. 如果用户要改示波器前处理项，先判断目标属于哪一类：
   - `Interpolation`
   - `Averaging`
   - 降噪或增强分辨率
   - `PulseResponse / Flatness`
4. 示波器前处理默认优先用已验证的 VBS 路径；修改后至少做一项读回验证。
5. 如果某个前处理项无法稳定读回，只能降级成 best-effort，并说明它不应作为最终性能基线。
6. 目标是看原始质量对比时，优先做 `AWG OFF/ON` 配对，而不是只看 `MER`。
7. 目标只是快速确认链路通不通时，优先单次 `SMOKE`，不默认多轮重试。
8. 记录结果时，优先抽取：
   - `noise_table.csv`
   - `signal_sweep.csv`
   - `validation_summary.csv`
   - 对应图片路径
9. 需要汇总时，生成中文 Markdown 报告，至少包含测试条件、链路描述、关键功率结果、解调结果和对比结论。
10. 需要补台账时，先查现有台账；有精确条目就引用精确条目，没有精确条目时才写“最近似”，仍不确定就标成待人工确认。
11. 结束时默认关闭 `AWG`，除非用户明确要求保持输出开启。

## 判断规则

- 功率摸底优先于调参。
- 单点链路检查时，优先固定量程，不在同一轮里自动扫多个 `V/div`。
- 只有目标是找最优示波器量程时，才做局部 `±1 step` 微扫。
- `timeout` 要分级：
  - 只读回状态的短超时：记 warning，不立刻停
  - 控制命令或采集挂死：fail-fast，不做长时间空等
- 不把不同量程下的 `AWG OFF` 底噪直接混成一列“开关功率比”。
- `SampleRateHz ≥ 800 GSa/s` 时，常见是 `sinx/x` 插值，不应误判成硬件采样率异常。
- `EnhanceResType` 会用带宽换噪声，不应作为默认性能基线。
- `OptimizeGroupDelay` 才是 `PulseResponse / Flatness` 对应的可用控制量。

## 报告与台账

- 默认产物是中文 `.md`，不是只留一堆 CSV。
- 报告里要区分“原始功率”和“解调指标”。
- 没有同量程 noise 参考时，不硬写严格 `On/Off Ratio`。
- 报告文件名优先中文，链路描述尽量写全。
- 不伪造缺失数据。
- 不把未经核对的器件型号直接补进台账。
- 不把单次实验结论写成永久规范。
- 字段清单见 [references/report-and-ledger-checklist.md](references/report-and-ledger-checklist.md)。

## 边界

- 不负责决定 DUT 最终工作点，只负责把测试过程跑干净。
- 不把某次实验里的最佳 `AWG` 幅度或最佳 `V/div` 固化成永久规则。
- 不把前面板残留状态当默认可信；每次测试前都显式写关键信息。
- 不把 `Averaging` 纳入默认高速链路性能基线。
- 不把 `EnhanceResType != None` 纳入默认高速链路性能基线。
- 对无法稳定读回的旧路径，不再假定它已经生效。
- 不把测试后报告或台账补录拆成独立 skill；它们是本流程的收尾阶段。

## 参考文件

- 执行护栏与常用判断：[references/bench-checklist.md](references/bench-checklist.md)
- 报告与台账字段清单：[references/report-and-ledger-checklist.md](references/report-and-ledger-checklist.md)
- LeCroy 前处理变量映射：[references/preprocessing-mapping.md](references/preprocessing-mapping.md)

## 维护

- 如果台架默认配置变化，优先更新 `references/bench-checklist.md`，不要不断往正文堆例外。
- 新增结果表字段时，优先更新 `references/report-and-ledger-checklist.md`。
- 新增或证伪 LeCroy 前处理变量时，优先更新 `references/preprocessing-mapping.md`，并写清最后验证日期和失效现象。
- 新增测试模式时，先补“什么情况下用它”的判断，不先写长背景。
