# 台架测试执行清单

## 测前固定项

- `AWG OFFSET = 0 mV`
- `Scope Interpolation = Linear`
- `AverageSweeps = 1`
- `EnhanceResType = None`
- `OptimizeGroupDelay = Flatness`
- 记录当前链路文字描述

## 测试类型选择

- 只看链路通不通：单次 `SMOKE`
- 看原始质量：`AWG OFF/ON` 配对功率
- 看可解调性：功率 + full demod
- 看长期稳定性：固定工作点重复多轮

## 必记结果

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
