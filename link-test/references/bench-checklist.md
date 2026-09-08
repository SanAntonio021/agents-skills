# 台架测试执行清单

## 测前核对

- 沿用本轮已确认的条件和项目配置，读回 AWG OFFSET、示波器插值、平均次数、增强分辨率与 OptimizeGroupDelay。
- 未指定设置时先记录现状；只有影响本轮测量含义且无法从已有要求确定做法时才询问。不自动重置成固定基线。
- 对应参数路径与可选参考设置见 [LeCroy 前处理映射](preprocessing-mapping.md)。
- 核对当前链路、仪器和通道，必要信息随本轮数据保存。

## 测试类型选择

- 只看链路通不通：单次 `SMOKE`
- 看原始质量：`AWG OFF/ON` 配对功率
- 看可解调性：功率 + full demod
- 看长期稳定性：固定工作点重复多轮

## 按测试目标选取的指标

只选本轮实际测量或计算的指标，区分功率、解调结果与采集状态；不为补齐清单虚构数值。

- `InBandNoisePower`
- `InBandOnPower`
- `OnOffRatio_dB`
- `MER`
- `BER`
- `SyncPSNR`
- `ClipFraction`
- `ActualVdivVPerDiv`

## 常见误区

- 不同 `V/div` 的 `AWG OFF` 噪声不能直接拿来做严格的开关功率比。
- 没有同量程 noise 参考时，不要把代理量硬写成 `SNR`。
- 量程还没定时，不要一上来就做长时间重复测试。
- 链路功率摸底阶段，不要过早把 `MER` 当唯一结论。
