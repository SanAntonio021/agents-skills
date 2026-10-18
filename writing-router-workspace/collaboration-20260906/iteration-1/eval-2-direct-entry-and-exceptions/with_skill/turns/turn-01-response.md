原稿明确了 **1秒采集间隔、记录电脑保存为 CSV、测试时长待定**。建议按以下结构重排，目前尚未修改主稿：

1. **目的**：说明温度采集与记录保存的用途，并引出对采集、保存过程的验证。
2. **已有条件**：集中保留采集器、1秒间隔、记录电脑及 CSV 保存方式，不增加设备能力或已测试结论。
3. **待定参数**：保留测试时长待定；测试允许的时间偏差、记录缺失判据作为建议补充项，不自行定值。

**测试思路**：建议先验证采集间隔和 CSV 保存，再检查记录是否缺失、重复。温度测量精度需要参考温度和误差要求，现有材料不足以展开。

测试先限定为“采集与保存功能验证”，暂不加入温度精度测试，可以吗？

```json
{
  "writing_context": {
    "document_type": "technical",
    "mode": "technical_scheme",
    "edit_scope": "structural",
    "language": "zh",
    "loaded_refs": [
      "D:/BaiduSyncdisk/.agents/AGENTS.md",
      "D:/BaiduSyncdisk/.agents/shared-rules.md",
      "C:/Users/SanAn/.agent-rules/local.md",
      "D:/BaiduSyncdisk/.agents/global-rules/shared-rules.md",
      "D:/BaiduSyncdisk/.agents/skills/technical-writing/SKILL.md",
      "D:/BaiduSyncdisk/.agents/skills/writing-router/SKILL.md",
      "D:/BaiduSyncdisk/.agents/skills/writing-router/references/collaborative-writing.md",
      "D:/BaiduSyncdisk/.agents/skills/writing-router/references/common-quality.md",
      "D:/BaiduSyncdisk/.agents/skills/writing-router/references/ai-smell-catalog.md"
    ]
  }
}
```
