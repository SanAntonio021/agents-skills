建议按“**终端研发 → 三个固定点位验证**”组织建设内容，开头简短交代现有基础，不单独铺陈背景。

1. **终端研发**：说明拟在现有实验室样机基础上开展哪些研发工作。具体改进项应根据监测对象和样机现有能力确定，暂不补写通信方式、监测精度或配套平台。
2. **固定点位验证**：说明拟在园区三个固定点位验证哪些功能、采用什么方法判断是否达到要求。验证周期、指标和点位条件尚未提供，先保留为待明确内容。

全文严格区分“已有实验室样机”和“拟开展点位验证”，不写成已部署、已稳定运行或已覆盖园区。

本轮先讨论结构，暂不创建 `proposal.md`；后续分批展示正文，确认后写入。**先明确一个影响研发内容的问题：这三个点位拟监测的是环境温度，还是设备、设施的温度？**

```json
{
  "TRACE_WRITING_CONTEXT": {
    "document_type": "project",
    "mode": "proposal",
    "edit_scope": "draft",
    "language": "zh",
    "stage": "structure_discussion",
    "main_draft": "proposal.md",
    "collaboration": "先讨论结构，再分批确认正文，确认后写入",
    "fact_source": "本轮用户提供的合成案例",
    "protected_facts": [
      "拟研发园区温度监测终端",
      "目前只有实验室样机",
      "拟在三个固定点位验证，不得写成已部署"
    ],
    "loaded_refs": [
      "D:/BaiduSyncdisk/.agents/AGENTS.md",
      "D:/BaiduSyncdisk/.agents/shared-rules.md",
      "C:/Users/SanAn/.agent-rules/local.md",
      "D:/BaiduSyncdisk/.agents/global-rules/shared-rules.md",
      "D:/BaiduSyncdisk/.agents/skills/project-writing/SKILL.md",
      "D:/BaiduSyncdisk/.agents/skills/writing-router/SKILL.md",
      "D:/BaiduSyncdisk/.agents/skills/writing-router/references/collaborative-writing.md",
      "D:/BaiduSyncdisk/.agents/skills/writing-router/references/common-quality.md"
    ],
    "private_samples_loaded": false,
    "vocabulary_loaded": false,
    "files_written": []
  }
}
```
