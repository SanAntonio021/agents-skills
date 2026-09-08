---
name: lab-report-slides
description: >
  Generate a concise Chinese lab-work presentation from the user's Codex and Claude Code sessions.
  Use this skill whenever the user says "生成今日汇报", "生成当天汇报", "生成每日汇报",
  "生成本周组会汇报", "生成组会 PPT", or asks to turn recent AI-assisted experiments,
  code, instrument tests, plots, or results into a presentation. Read local session JSONL,
  merge child-agent work into parent tasks, filter AI boilerplate, find referenced experiment
  images and relevant platform photos, check whether the work is worth presenting to an advisor,
  and create an image-led PPTX with editable text and independent pictures. Render the actual PPTX
  to PDF/PNG for inspection. Reuse a clear audience and goal; wait for an outline decision only
  when the user explicitly asks to review the outline first.
  Do not use for paper-to-slides work when the source is a paper PDF or DOI; use a paper-slide skill.
compatibility: Requires Python 3.10+, python-pptx, Pillow, the existing libreoffice-runner and Poppler. SVG input uses the existing Node.js/sharp runtime.
---

# 实验工作汇报幻灯片

该技能用于用户反复开展的日报和周组会工作流。导师需要清晰的工作与证据记录，而不是 AI 对话转写。将本地会话文件作为证据；绝不能把模型计划、推测或套话当成已完成工作。

## 触发与模式

本技能保留实验记录采集、证据筛选和简单组会模板的直接制作流程。需要确定制作工具、
复用其他模板、制作复杂场景或按页分工时，读取 `pptx` 的
[共同制作流程](../pptx/references/presentation-workflow.md)。跨技能链接若不能解析，按当前宿主
技能目录找到已安装的 `pptx` 根目录，再读取其 `references/presentation-workflow.md`，不猜私有路径。
用户指定其他制作工具或已有制作工程时，本技能可提供证据和提纲，由选定工具负责生成，
不同时运行 `render_deck.py` 再做一套稿。

普通日报、组会沿用下文的模板配置和目标明确后直接生成规则，不额外要求先确认样页。
工程模板的字体、配色和构图不反向覆盖简单组会模板；跨页分工时共用本次配置和素材清单。
复杂场景的生图不能替代真实曲线、仪器截图或实验照片。

- `生成今日汇报`、`生成当天汇报` 或 `生成每日汇报`：收集 `Asia/Shanghai` 时区对应的本地日历日。
- `生成本周组会汇报` 或 `生成组会汇报`：收集截至所请求本地日期的最近七个日历日。
- 用户指定项目时，只保留匹配的 `cwd`/项目记录和素材。否则，纳入所选时间窗口内发现的全部项目，并在提纲中显示项目名。

## 数据采集

运行随附的采集器。它只使用本地文件和 Python 标准库：

```text
python scripts/collect_sessions.py --mode today --out <brief.json>
python scripts/collect_sessions.py --mode week --out <brief.json>
```

指定项目时加 `--project-root <project>`，包含其子目录，不混入名称前缀相似的其他项目。
素材在其他已知目录时加可重复的 `--asset-root <directory>`；已知台架照片可用
`--context-image <photo>` 明确提供。优先自行从项目记录确定这些路径，不要求用户每次重新指定。

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

## 提纲与页面

汇报价值检查通过后，按实际材料组织简短提纲，每页围绕一个结果或问题。默认采用短篇汇报，按需使用以下页面职责：

1. 总览
2. 主要工作
3. 实验/测试结果
4. 问题与判断
5. 下一步

删除空页，素材较多时按实验拆页，不为固定页数挤小图件。已有目标和听众明确时直接生成并自检；用户明确要求先看提纲时才等待其决定。

先为每项实验匹配实际曲线、仪器截图或现场照片，再写页面文字。图件占主要空间，文字只说明关键条件、数值和结论；单图配短说明，对比图并排展示。文字过多时整理或拆页，不缩成难读小字。

## 实验素材

采集器先读取会话引用，再按项目有界补充扫描；找到一张图不会跳过其他项目或实验。默认将 5 秒、2,000 个文件的预算分配给各目录，排除代码依赖、技能资源和符号链接。扫描不足时缩小到已知产物目录，不默认遍历整个同步盘。

`assets` 中的 `role`、`period` 只是候选分类，`status=unverified` 表示尚未核对内容。逐张查看并结合任务记录确定用途：近期文件不自动等于新实验结果；较早的台架照片可作为背景，但需确认仍对应本次装置。旧曲线仅用于明确标注的历史对照，不写成当前成果。

图片若嵌在既有 PPT、PDF 或实验报告中，使用相应文档技能提取，并保留原文件、页码或幻灯片来源。缺少必要图件时先定位材料，明确缺哪项；不以长段文字或虚构图片代替实验素材。

按以下优先级选择：

1. 实验对话直接引用的结果图片或图表。
2. 匹配项目下、在所选时间窗口内创建或修改的结果图片。
3. 对应当前装置的台架照片，或标注来源和时期的历史对照材料。

每张图必须服务于当前页的问题，不用无关图片填空。在 manifest 中保留文件路径、内容哈希、角色及来源，便于复查。

忽略 agent runtime 或 skill 目录中的图标、logo 和其他素材。它们是界面资源，不是实验证据；除非用户明确指出其中某项是结果图片。

## Deck JSON 与渲染

提纲按当前目标确定后，在 skill 目录外写入一个小型 deck JSON 文件。渲染器要求以下结构：

```json
{
  "title": "今日工作汇报",
  "date": "20260715",
  "footer": "2026-07-15",
  "slides": [
    {
      "kicker": "实验进展",
      "title": "1 km 光纤链路引入低频噪声峰",
      "type": "result",
      "status": "已完成",
      "blocks": [
        {"type": "text", "heading": "观察", "text": "..."},
        {"type": "image", "path": "<IMAGE_PATH>", "caption": "频谱仪 CH2", "role": "result", "period": "current", "source": "<RUN_OR_DOCUMENT_REFERENCE>"}
      ]
    }
  ]
}
```

使用以下命令渲染：

```text
python scripts/render_deck.py --deck <deck.json> --output-dir "D:\\BaiduSyncdisk\\组会" --base-name <YYYYMMDD-or-YYYYMMDD组会>
```

`type=result/setup/comparison` 的页面必须有真实图片。每页支持一至六张图片，按可读性决定是否拆页。`section`（兼容 `kicker`）为章节标题，`title` 为实验副标题，`subtitle` 可显式覆盖副标题，`summary` 为页底结论。`layout=wide-strip` 将首图放上方、其余照片放下方；`layout=stacked-left` 将三张图排为左侧上下两图、右侧大图；其他情况使用单图或网格。旧文字块在有图页进入结论区，过长时报错，应精简或拆页。来源、日期与状态写入备注，历史示例仍须在可见文字中标明。只有用户明确要求纯文字汇报时，才设置 `allow_text_only=true`；缺图和空材料会报错，不生成占位成品。

渲染器生成：

- `<name>.pptx`：文字为原生文本框，曲线图和照片为独立图片，可分别移动、缩放、替换。图片内部的数据和文字仍是像素，不宣称可编辑图表数据。
- `<name>.pdf`：由实际 PPTX 经隔离 LibreOffice 渲染。
- `<name>_01.png`、`<name>_02.png`、...：从该 PDF 生成的页面图片。
- `<name>.html`：使用这些页面图片的自包含预览，不另做一套版式。
- `<name>.manifest.json`：输出路径、图片来源与哈希、幻灯片数量及可编辑对象说明。

默认采用 `D:\\BaiduSyncdisk\\组会\\20260715近期进展.pptx` 第 3、4、8 页提取的样式：16:9、白底、微软雅黑、左上黑色大标题、深色分隔带、粉底居中实验副标题、大面积图件及页底加粗结论。渲染器实际读取 `references/template-profile.json` 的尺寸、坐标、字体与颜色；deck 可用绝对 `profile_path` 选择其他配置。这里复用样式参数，不复制原文件的母版、业务文字和私有实验图片。manifest 记录样式来源及配置哈希。

文件命名：

- 日报：`YYYYMMDD`。
- 周组会：`YYYYMMDD组会`。
- 请求的 stem 已存在时，保留它并使用 `_v2`、`_v3` 等后缀。绝不能自动覆盖早期演示文稿。

## 验证

报告成功前：

1. 确认 HTML、PDF、PPTX、PNG 和 manifest 文件存在且非空。
2. 确认 PPTX 是有效的 ZIP/Office 包，并且幻灯片数量符合预期。
3. 确认每张 PNG 均为 1600x900，每张引用图片均正常显示；缺图必须补齐或调整页面内容后再交付。
4. 逐页检查实际 PPTX 的渲染：图件够大、曲线和照片与文字对应、无裁切和重叠、无缺图占位符；页数符合本次要求。
5. 报告准确的输出路径和所有 `未验证` 项。
6. 用 `pptx` 的可编辑性检查确认有原生文字及独立图片，不能以整页截图充当可编辑交付。

原生 PowerPoint 验证使用 `pptx` 的既有守护程序和隔离副本，保留实际打开与导出结果；不能接管或关闭用户实例。应用被占用时先交付可检查的候选并说明原生验证范围，不把 LibreOffice 渲染冒充 PowerPoint 原生结果。
