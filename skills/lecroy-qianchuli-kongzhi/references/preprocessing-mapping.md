# LeCroy 前处理映射

## 已验证可用

- `Interpolation`
  - 变量：`app.Acquisition.<Ch>.InterpolateType`
  - 常用值：`Linear`、`Sinxx`
  - 现象：`Sinxx` 时结果表中常见 `SampleRateHz ≈ 800 GSa/s`

- `Averaging`
  - 变量：`app.Acquisition.<Ch>.AverageSweeps`
  - 默认基线：`1`

- `Enhance Resolution`
  - 变量：`app.Acquisition.<Ch>.EnhanceResType`
  - 默认基线：`None`
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

## 默认性能基线

- `InterpolateType = Linear`
- `AverageSweeps = 1`
- `EnhanceResType = None`
- `OptimizeGroupDelay = Flatness`
