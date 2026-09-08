---
name: link-test
description: 操作和排查高速链路台架的 AWG、示波器与 DUT，负责 SMOKE/FULL、AWG OFF/ON 配对、单次与重复测试、LeCroy 前处理控制、读回验证、超时处理和安全收尾。用户要实际运行、续跑或诊断台架测试时使用。补链路器件台账时仅核对资料，不进入测试流程。仅整理已有实验记录或编写报告时不触发；边测边记时结合 lab-notebook。
---

# 高速链路台架测试

## 作用

负责仪器怎么操作、测试怎么执行、结果怎么判断，以及异常怎么收尾。人工实验记录由 `lab-notebook` 负责。

默认目标是先拿到可解释的功率、底噪和解调结果，再决定要不要进入更长的扫描。

仅补链路器件台账时，直接按 [台架结果与台账核对](references/report-and-ledger-checklist.md) 核对已有资料；不执行下方测试流程、不连接仪器，也不改变 AWG 输出。

## 流程

1. 根据本轮目标和已有决定选择测试类型，要求已明确时直接继续：
   - 单点 `SMOKE`
   - 多点扫描
   - `AWG OFF/ON` 配对功率
   - 功率加解调联合验证
   - 仅调整或确认 LeCroy `Pre-processing`
2. 测前沿用本轮已确认的条件和项目配置，并读回实际状态。两者都未指定时，先读回并记录现状；设置会实质影响本轮测量含义、且不能从已有要求判断如何处理时，再询问是否调整。设置与已确认条件不一致时，在已有授权范围内纠正并验证，不重复确认。
3. 如果用户要改示波器前处理项，先判断目标属于哪一类：
   - `Interpolation`
   - `Averaging`
   - 降噪或增强分辨率
   - `PulseResponse / Flatness`
4. 示波器前处理默认优先用已验证的 VBS 路径；修改后至少做一项读回验证。
5. 如果某个前处理项无法稳定读回，只能降级成 best-effort，并说明它不应作为最终性能基线。
6. 目标是看原始质量对比时，优先做 `AWG OFF/ON` 配对，而不是只看 `MER`。
7. 目标只是快速确认链路通不通时，优先单次 `SMOKE`，不默认多轮重试。
8. 保存实际采集、必要配置和读回状态，检查本轮相关的功率、底噪与解调指标，保留失败结果。指标选取见 [台架结果与台账核对](references/report-and-ledger-checklist.md)。
9. 结束时默认关闭 `AWG`，除非用户明确要求保持输出开启；按项目已有保护完成异常收尾。

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

## 输出与协作

- 数据目录、逐次指标表和图片沿用项目已采用的 [standardize-test-project](../standardize-test-project/SKILL.md) 规范；不再指定另一套 CSV 文件名，也不迁移历史结果。需要修改保存程序时才加载其实现说明。
- 用户要求边测边记，或当前任务已约定维护记录时，使用 [lab-notebook](../lab-notebook/SKILL.md) 续写同一份人工主记录，不另生成一份测试日志或默认报告。只整理旧记录时使用 `lab-notebook`，不进入仪器操作流程。
- 测试完成后直接说明关键结果与产物位置。正式报告仅按用户请求生成，复用已有数据与记录；报告不是每轮测试结束的前提。
- 仪器、线缆、模块和 DUT 台账只在用户要求补录时核对更新；具体字段和识别规则见 [台架结果与台账核对](references/report-and-ledger-checklist.md)。

## 边界

- 不负责决定 DUT 最终工作点，只负责把测试过程跑干净。
- 不把某次实验里的最佳 `AWG` 幅度或最佳 `V/div` 固化成永久规则。
- 读回并记录实际状态，不把前面板残留设置当成本轮已确认条件，也不为套用默认值覆盖实验设置。
- 使用 `Averaging` 或 `EnhanceResType != None` 时说明对噪声、带宽和可比性的影响，不把处理后的结果当作未处理的原始性能；用户已明确要求的对比实验可以保留这些设置。
- 对无法稳定读回的旧路径，不再假定它已经生效。
- 不伪造缺失数据，不把单次最佳设置或结论固化成永久规范。

## 参考文件

- 执行护栏与常用判断：[references/bench-checklist.md](references/bench-checklist.md)
- 台架结果与台账核对：[references/report-and-ledger-checklist.md](references/report-and-ledger-checklist.md)
- LeCroy 前处理变量映射：[references/preprocessing-mapping.md](references/preprocessing-mapping.md)

## 维护

- 如果台架默认配置变化，优先更新 `references/bench-checklist.md`，不要不断往正文堆例外。
- 台架指标含义变化时，更新 `references/report-and-ledger-checklist.md`；通用输出与记录要求维护在承接技能中。
- 新增或证伪 LeCroy 前处理变量时，优先更新 `references/preprocessing-mapping.md`，并写清最后验证日期和失效现象。
- 新增测试模式时，先补“什么情况下用它”的判断，不先写长背景。
