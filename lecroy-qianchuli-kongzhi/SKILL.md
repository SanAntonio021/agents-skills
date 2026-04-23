---
name: lecroy-qianchuli-kongzhi
description: 管理 LeCroy 示波器前面板 Pre-processing 相关控制项，覆盖 `Interpolation`、`Averaging`、`Enhance Resolution` 和 `Optimize` 模式，并区分可验证路径与高风险假指令。Use when 用户要修改或确认这些前面板预处理项，例如“切到 linear”“确认 averaging”“看 pulse/flatness”或“检查 sinx/x”。
---

# LeCroy 前处理控制

## 作用

这份 skill 把 LeCroy 前面板 `Pre-processing` 项映射到真正可用、可读回、可验证的自动化变量，避免再走无效的 SCPI 或 VBS 路径。

## 流程

1. 先识别用户要改哪一类：
   - `Interpolation`
   - `Averaging`
   - 降噪或增强分辨率
   - `PulseResponse / Flatness`
2. 默认优先用已验证的 VBS 路径。
3. 修改后至少做一项读回验证。
4. 如果某项无法稳定读回，只能降级成 best-effort，并明确说明风险。

## 稳定判断

- `SampleRateHz ≥ 800 GSa/s` 时，常见是 `sinx/x` 插值，不应误判成硬件采样率异常。
- `EnhanceResType` 会用带宽换噪声，不应作为默认性能基线。
- `OptimizeGroupDelay` 才是 `PulseResponse / Flatness` 对应的可用控制量。

## 边界

- 不把 `Averaging` 纳入默认高速链路性能基线。
- 不把 `EnhanceResType != None` 纳入默认性能基线。
- 对无法稳定读回的旧路径，不再假定它已经生效。

## 参考文件

- 变量映射与风险说明：[references/preprocessing-mapping.md](references/preprocessing-mapping.md)
- 基线测试流程：[../gaosu-lianlu-taijia-ceshi/SKILL.md](../gaosu-lianlu-taijia-ceshi/SKILL.md)

## 维护

- 以后发现新的可读写变量时，优先更新映射表，不往正文堆试错记录。
- 某项在固件升级后失效时，把“最后验证日期”和“失效现象”补进参考文件。
