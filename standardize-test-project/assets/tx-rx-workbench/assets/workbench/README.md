# 收发工作台参考工程

这是一份可独立复制并适配的 TX/RX 模板。现有复数 I/Q 和单路实数中频链路可以复用；任意单 DAC 发送算法不在本版实现范围。

在新 MATLAB 会话中进入本目录执行：

```matlab
Template_Demo                      % 默认 I/Q 长帧模拟
Template_Demo('real_if')            % 单路实数中频生成、下变频和完整解调
Template_GUI_Demo                  % TX/RX 模拟面板
Template_Validate('smoke')         % 上述两条路径、GUI 和容量预检
Template_Validate('rx_workflows')  % 日常采集、单路中频、量程与设置专项
```

正常 `TX_Workbench()`、`RX_Workbench()` 默认模拟，不自动连接仪器。Template 入口增加主进程仪器构造拒绝保护；异步子进程须使用显式模拟工厂，不能依靠主进程保护自动继承。

完整依赖保留在 `code/`，示例配置在 `config/`。中频板及六子带为可选适配，普通 I/Q 模拟无需配置板卡。参数只作示例，不是设备能力声明。包内不提供本机地址、串口、个人偏好和 `instruments.local.json`；实测需另行配置并核对设备、通道、占用及授权。受限短帧矩阵和外部仪器驱动不分发，默认演示使用标准长帧。

本版验证目标为 R2023b，实际状态以所属技能 `references/provenance/validation.json` 为准；本说明不声明验收完成。R2023a 历史堆损坏未解决，真实高 DPI 与实机验证另列待验。

来源快照、文件哈希和模板适配分别记录在所属技能 references；新增模板入口以 `Template_` 和 `template_support/` 标识。已有项目只按需整合模块，新模板不会自动覆盖已有工程。仅查询或审查时不需要复制工程、启动 MATLAB 或连接设备。

TX 实测 GUI 须显式提供 `backend_options`（包含实际设备配置）及 `board_options`（板卡使用时指定实测来源与配置）；默认只提供模拟后端且不自动连接。显式传入的后端选项保持调用方语义，不会被模板悄悄改为模拟。
