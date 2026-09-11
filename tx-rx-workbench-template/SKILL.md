---
name: tx-rx-workbench-template
description: 复用完整 MATLAB TX/RX 收发实验工作台、自动诊断图和 Keysight M8195A / LeCroy 设备适配。用户要以现有收发工作台建立新实验、复制发射接收绘图、替换算法后调整工作台或复用同一套 AWG/示波器控制时使用。单纯修改诊断图先用 standardize-test-project；论文排版、独立科研图和实际上机操作分别交给对应绘图技能或 link-test。
---

# 收发实验工作台模板

这是可复制后修改的完整参考工程，不是所有实验必须采用的算法或界面。

## 使用步骤

1. 读目标项目规则和现有入口，确认用户要复用绘图、工作台还是完整工程。已有项目只补需要的部分，不整仓覆盖。
2. 读取 [适配说明](references/adaptation.md)，查看 `assets/previews/` 的 TX/RX 参考图。通用绘图要求读取相邻 `standardize-test-project/references/standard.md` 第4节；该技能缺失时明确说明，不能声称已加载。
3. 使用 [复制脚本](scripts/copy_template.ps1) 将 `assets/workbench/` 复制到新的空目录。完整保留命名空间与运行依赖；不要只拿两个入口文件。已有项目手工整合前保护原改动。
4. 首先运行 `Template_Demo` 和 `Template_GUI_Demo`，这两个入口只使用仿真或 mock。原有 `TX_Workbench()` / `RX_Workbench()` 无参数入口会尝试访问仪器，不用于无硬件演示。
5. 按新算法修改模板副本的数据生成、接收处理和图组。保留真实单位、数据来源和各阶段含义；不要为了凑图复制过时指标。当前16QAM、QPSK训练、帧结构、4/11面板和默认布局只是实例。
6. 运行 `Template_Validate('smoke')` 和相关原专项测试。实际检查正常、紧凑尺寸预览。用例PASS、进程退出、真实仪器验证分别记录。

## 设备复用

保留 M8195A 容量、128点对齐、路由、只读回读、共享通道保护以及 LeCroy 原始波形解析和异常恢复。连接参考见 `references/provenance/device-reference.json`；它不被程序自动加载，也不继承上次接线确认或上机授权。

真实运行前核对设备身份、地址、接线、通道占用和公共状态。容量不足不得截波形、改变采样率或自动换路由；不得改变其他使用者的输出。正式采集沿用项目安全门及已有有效授权。

## 维护

源码快照、提交与哈希见 `references/provenance/`。项目和模板独立维护，更新模板须重新冻结来源并验证。保存用户需要的设备配置参考，但不打包凭据、本机偏好、海量历史数据或第三方授权工具箱。

配套内容：`assets/workbench/` 为完整代码；`assets/previews/` 为合成示例图；`scripts/` 为复制工具；`references/adaptation.md` 集中说明环境、接口和验证边界。不要为同一事项新建多份人工报告。
