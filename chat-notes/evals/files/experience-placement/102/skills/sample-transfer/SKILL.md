---
name: sample-transfer
description: 上传文件并核对结果。
---
# 文件上传

## 超时处理

超时不能直接判定失败，也不能盲目重复写入。设备支持任务查询时，先按任务编号核对结果；缺少查询接口时依照对应设备说明确认实际状态。设备方法见 references/devices。
