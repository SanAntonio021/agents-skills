---
name: lab-report-slides
description: >
  Generate a concise Chinese lab-work presentation from the user's Codex and Claude Code sessions.
  Use this skill whenever the user says "生成今日汇报", "生成当天汇报", "生成每日汇报",
  "生成本周组会汇报", "生成组会 PPT", or asks to turn recent AI-assisted experiments,
  code, instrument tests, plots, or results into a presentation. Read local session JSONL,
  merge child-agent work into parent tasks, filter AI boilerplate, find referenced experiment
  images, check whether the work is worth presenting to an advisor, require a short outline
  approval, and export HTML, PDF, and image-only PPTX.
  Do not use for paper-to-slides work when the source is a paper PDF or DOI; use a paper-slide skill.
compatibility: Requires Python 3.10+, `python-pptx`, and Microsoft Edge or Google Chrome for headless HTML rendering.
---

# 实验工作汇报幻灯片

该技能用于用户反复开展的日报和周组会工作流。导师需要清晰的工作与证据记录，而不是 AI 对话转写。将本地会话文件作为证据；绝不能把模型计划、推测或套话当成已完成工作。

## 触发与模式

- `生成今日汇报`、`生成当天汇报` 或 `生成每日汇报`：收集 `Asia/Shanghai` 时区对应的本地日历日。
- `生成本周组会汇报` 或 `生成组会汇报`：收集截至所请求本地日期的最近七个日历日。
- 用户指定项目时，只保留匹配的 `cwd`/项目记录和素材。否则，纳入所选时间窗口内发现的全部项目，并在提纲中显示项目名。

## 数据采集

运行随附的采集器。它只使用本地文件和 Python 标准库：

```text
python scripts/collect_sessions.py --mode today --out <brief.json>
python scripts/collect_sessions.py --mode week --out <brief.json>
```

默认来源：

- Codex：`%USERPROFILE%\.codex\sessions\**\rollout-*.jsonl`，以及 `session_index.jsonl` 条目在所选时间窗口内更新的归档 rollout。采集器按 session ID 匹配归档文件名，不会对整个归档目录执行 stat。只有用户明确要求排除归档会话时，才使用 `--no-include-archived`。
- Claude Code：`%USERPROFILE%\.claude\projects\**\*.jsonl`。

采集器把事件时间戳转换为 `Asia/Shanghai`，因此昨天开始但今天仍在继续的会话也会纳入。它记录 `sessionId`、`cwd`、`parent_thread_id`、`root_id` 和 platform。合并 `root_id` 相同的记录；子智能体会话属于辅助证据，不是独立工作项。

采集器保留用户消息和有用的智能体结果，排除 system/developer prompts、hidden reasoning、token telemetry 和 tool plumbing，并遮盖明显的 API keys、tokens、passwords 和 secrets。不得在对话中打印原始 session JSONL，也不得把它放入生成的演示文稿。

## 证据与降噪规则

只总结在所选记录或文件中有证据的工作：

- `已完成`：明确存在命令、测试、实验、文件或结果。
- `进行中`：工作仍在开展，但没有记录最终结果。
- `遇到问题`：明确记录了失败或尚未解决的差异。
- `下一步`：用户明确提出或有证据支撑的后续操作。

删除问候、重复确认、通用 AI 建议、推测性论断和自造术语。不得把 AI 计划写成结果。数字、单位、仪器名称、测试条件、文件名和错误消息必须准确保留。证据不完整时，写 `未验证` 或 `待确认`；绝不能用常识补齐缺口。

编写提纲前先统一状态。后续证据优先于早期中间结论。用户当前明确说明某项已完成时，可以覆盖早期审计中列出的未决问题。该说明只用于更新状态；不得编造缺失的技术细节。从 `遇到问题` 和 `下一步` 中删除已经解决的问题。

优先采用以下内容顺序：

1. 发生了什么变化或完成了什么。
2. 实验或测试得到什么结果。
3. 定位了什么问题，或还有什么问题尚未解决。
4. 接下来做什么。

只有代码本身就是科研结果时才展示代码。其他情况下，报告任务、方法和观测结果，不要复制代码块。

## 汇报价值检查

提出提纲前，判断所选工作对目标导师或组会听众是否有用。消息数量多不能证明取得进展。按以下顺序优先纳入：

1. 已验证的科研结果、实验数据、图件或定量测试结论。
2. 对目标导师有价值、已经完成且有可追溯文件或评审结果的科研或项目交付物。
3. 直接解除当前科研阻塞且结果已经验证的支撑工作。

常规登录修复、AI 配置、磁盘清理、一般软件维护和元技能工作通常应写入私人工作记录。常规行政表格也不纳入，除非它对该听众代表实质性项目里程碑。计入某项内容前，先判断导师是否需要它来理解当前科研进展。只有用户要求，或支撑工作直接影响所汇报的里程碑时，才将其纳入。不得用这些任务填充演示文稿来制造当天很忙的印象。

如果当天没有第一或第二优先级结果，只剩常规支撑工作，则在生成提纲前停止。直接告诉用户，现有记录缺少适合向导师汇报的实质性进展，并且只问一个问题：停止，还是改为生成私人工作记录。

## 提纲确认

汇报价值检查通过后，在对话中生成简短提纲。提纲不得超过五个页面标题，每页包含一至两个证据要点。按需使用以下默认页面职责：

1. 总览
2. 主要工作
3. 实验/测试结果
4. 问题与判断
5. 下一步

删除内容为空的页面职责；当天工作较少时压缩为两至三页。请用户确认或修正提纲。用户确认前不得渲染最终文件。

## 实验素材

采集器首先使用所选会话事件中明确引用的图片和图表文件。如果没有得到可用素材，则在所选项目目录中扫描同一日期窗口内修改的图片。跳过 `.git`、`.venv`、`node_modules`、`.codex` 和 `.claude`。回退扫描默认最多运行 5 秒、检查 2,000 个文件，避免同步盘阻塞日报。结果图片重要时，传入更窄的项目范围。

按以下优先级选择：

1. 实验对话直接引用的结果图片或图表。
2. 匹配项目下、在所选时间窗口内创建或修改的结果图片。
3. 不使用图片，并用清晰文字说明未找到结果图片。

绝不能为了填补空白区域而插入旧图片或无关图片。在 manifest 中保留文件路径，使用户能够追溯每项插入素材。

忽略 agent runtime 或 skill 目录中的图标、logo 和其他素材。它们是界面资源，不是实验证据；除非用户明确指出其中某项是结果图片。

## Deck JSON 与渲染

提纲获批后，在 skill 目录外写入一个小型 deck JSON 文件。渲染器要求以下结构：

```json
{
  "title": "今日工作汇报",
  "date": "20260715",
  "footer": "2026-07-15",
  "slides": [
    {
      "kicker": "实验进展",
      "title": "1 km 光纤链路引入低频噪声峰",
      "status": "已完成",
      "blocks": [
        {"type": "text", "heading": "观察", "text": "..."},
        {"type": "image", "path": "D:\\path\\spectrum.png", "caption": "频谱仪 CH2"}
      ]
    }
  ]
}
```

使用以下命令渲染：

```text
python scripts/render_deck.py --deck <deck.json> --output-dir "D:\\BaiduSyncdisk\\组会" --base-name <YYYYMMDD-or-YYYYMMDD组会>
```

渲染器生成：

- `<name>.html`：自包含 HTML 源文件。
- `<name>.pdf`：每页一张幻灯片。
- `<name>.pptx`：每张幻灯片都是全页 PNG，以保持视觉版式。
- `<name>_01.png`、`<name>_02.png`、...：渲染后的幻灯片图片。
- `<name>.manifest.json`：输出路径、幻灯片数量和来源记录。

使用 `D:\\BaiduSyncdisk\\组会\\20260506.pptx` 作为视觉参考：16:9、白色背景、等线/Microsoft YaHei fallback、蓝色标题强调、实验图片和克制的文字量。不得把 42 MB 模板复制到 skill 中。当前样式配置记录在 `references/template-profile.json`。

文件命名：

- 日报：`YYYYMMDD`。
- 周组会：`YYYYMMDD组会`。
- 请求的 stem 已存在时，保留它并使用 `_v2`、`_v3` 等后缀。绝不能自动覆盖早期演示文稿。

## 验证

报告成功前：

1. 确认 HTML、PDF、PPTX、PNG 和 manifest 文件存在且非空。
2. 确认 PPTX 是有效的 ZIP/Office 包，并且幻灯片数量符合预期。
3. 确认每张 PNG 均为 1600x900，每张引用图片均可正常渲染，或已标记为 `[MISSING: ...]`。
4. 检查日报不超过五页、文字在 16:9 版式下清晰可读，并且没有残留占位符或缺乏依据的论断。
5. 报告准确的输出路径和所有 `未验证` 项。

不得仅为验证纯图片演示文稿而通过 COM 启动或关闭 PowerPoint。如果已有 PowerPoint 实例处于打开状态，改用生成的 PDF/PNG 文件和包级检查。
