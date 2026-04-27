---
name: link-test
description: 面向高速链路台架的 AWG、示波器和 DUT 测试执行工作流，覆盖 `SMOKE/FULL`、`AWG OFF/ON` 配对、单次与重复测试、超时分级和收尾保护。Use when 用户要运行、续跑或排查台架测试，例如“先跑 smoke”“测一轮功率加解调”“做 AWG OFF/ON 配对”或“按当前链路重跑”。
---

# 高速链路台架测试

## 作用

这份 skill 把高速链路台架测试收成稳定流程，减少每轮都从头决定“怎么测”。

默认目标是先拿到可解释的功率、底噪和解调结果，再决定要不要进入更长的扫描。

## 流程

1. 先确认本轮测试类型：
   - 单点 `SMOKE`
   - 多点扫描
   - `AWG OFF/ON` 配对功率
   - 功率加解调联合验证
2. 测前固定基线：
   - `OFFSET = 0 mV`
   - `Interpolation = Linear`
   - `AverageSweeps = 1`
   - `EnhanceResType = None`
   - `OptimizeGroupDelay = Flatness`
3. 目标是看原始质量对比时，优先做 `AWG OFF/ON` 配对，而不是只看 `MER`。
4. 目标只是快速确认链路通不通时，优先单次 `SMOKE`，不默认多轮重试。
5. 记录结果时，优先抽取：
   - `noise_table.csv`
   - `signal_sweep.csv`
   - `validation_summary.csv`
6. 结束时默认关闭 `AWG`，除非用户明确要求保持输出开启。

## 判断规则

- 功率摸底优先于调参。
- 单点链路检查时，优先固定量程，不在同一轮里自动扫多个 `V/div`。
- 只有目标是找最优示波器量程时，才做局部 `±1 step` 微扫。
- `timeout` 要分级：
  - 只读回状态的短超时：记 warning，不立刻停
  - 控制命令或采集挂死：fail-fast，不做长时间空等
- 不把不同量程下的 `AWG OFF` 底噪直接混成一列“开关功率比”。

## 边界

- 不负责决定 DUT 最终工作点，只负责把测试过程跑干净。
- 不把某次实验里的最佳 `AWG` 幅度或最佳 `V/div` 固化成永久规则。
- 不把前面板残留状态当默认可信；每次测试前都显式写关键信息。

## 参考文件

- 执行护栏与常用判断：[references/bench-checklist.md](references/bench-checklist.md)
- 前面板预处理控制：[../lecroy-data/SKILL.md](../lecroy-data/SKILL.md)
- 报告与台账补录：[../test-report-log/SKILL.md](../test-report-log/SKILL.md)

## 维护

- 如果台架默认配置变化，优先更新 `references/bench-checklist.md`，不要不断往正文堆例外。
- 新增测试模式时，先补“什么情况下用它”的判断，不先写长背景。
