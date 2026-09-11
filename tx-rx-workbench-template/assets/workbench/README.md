# 收发工作台参考工程

先运行 `Template_Demo`：确定种子的TX波形生成、RX解调和两尺寸总览图。
运行 `Template_GUI_Demo` 查看两个工作台的mock预览；运行 `Template_Validate('smoke')` 完成演示及容量预检验证。

以上入口不访问真实仪器。原始 `TX_Workbench()`、`RX_Workbench()` 会尝试连接仪器，不作为演示入口。

完整依赖保留在 `code/`，配置示例在 `config/`。默认不携带 `instruments.local.json`；真实设备连接需单独配置并核对接线、占用和授权。

原始来源为 multistream_iq_SC 工作区快照；详细适配、数据接口、设备参考和来源清单见所属技能的 references。模板新增文件以 `Template_` 和 `template_support/` 标识，原始工程文件保持快照内容。
