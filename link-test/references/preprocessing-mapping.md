# LeCroy 前处理映射

## 已验证可用

- `Interpolation`
  - 变量：`app.Acquisition.<Ch>.InterpolateType`
  - 常用值：`Linear`、`Sinxx`
  - 现象：`Sinxx` 时结果表中常见 `SampleRateHz ≈ 800 GSa/s`

- `Averaging`
  - 变量：`app.Acquisition.<Ch>.AverageSweeps`
  - 未平均的参考值：`1`

- `Enhance Resolution`
  - 变量：`app.Acquisition.<Ch>.EnhanceResType`
  - 未增强的参考值：`None`
  - 风险：会牺牲有效带宽

- `PulseResponse / Flatness`
  - 变量：`app.Acquisition.<Ch>.OptimizeGroupDelay`
  - 常用值：`PulseResponse`、`Flatness`

## 已证伪或不可靠

- `INTE?`
  - 不能作为稳定读回路径

- `app.Acquisition.<Ch>.OptimalFilterSetup`
  - 在当前机型/固件上不支持或不稳定

- `C<Ch>:OPTIMAL_FILTER_SETUP ...`
  - 曾表现为发送不报错，但仪器并未真正接受

## 未处理性能的参考设置

以下用于判断设置含义或按已确认目标配置，不是每次测试都要写入的固定值。沿用本轮已确认条件；未指定时先读回现状，实质歧义再询问。AWG 零偏置参考值为 `OFFSET = 0 mV`，同样不覆盖已确认偏置。

- `InterpolateType = Linear`
- `AverageSweeps = 1`
- `EnhanceResType = None`
- `OptimizeGroupDelay = Flatness`
