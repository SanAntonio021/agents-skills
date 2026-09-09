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
  to PDF/PNG for inspection. Exclude non-research tool maintenance from advisor reports.
  Present verified candidate work items for user selection before making slides; reuse an
  already confirmed selection without asking again.
  Explain each selected project's motivation, approach, current progress and next steps;
  retrieve earlier context when needed and polish Chinese slide prose before rendering.
  Do not use for paper-to-slides work when the source is a paper PDF or DOI; use a paper-slide skill.
compatibility: Requires Python 3.10+, python-pptx, Pillow, the existing libreoffice-runner and Poppler. SVG input uses the existing Node.js/sharp runtime.
---

# 实验工作汇报幻灯片

该技能用于用户反复开展的日报和周组会工作流。让未参与具体工作的导师看懂每项工作为什么做、采取了什么办法、目前做到哪一步、下一步准备做什么。将本地会话与项目记录作为证据；绝不能把模型计划、推测或套话当成已完成工作。

## 触发与模式

本技能保留实验记录采集、证据筛选和简单组会模板的直接制作流程。需要确定制作工具、
复用其他模板、制作复杂场景或按页分工时，读取 `pptx` 的
[共同制作流程](../pptx/references/presentation-workflow.md)。跨技能链接若不能解析，按当前宿主
技能目录找到已安装的 `pptx` 根目录，再读取其 `references/presentation-workflow.md`，不猜私有路径。
用户指定其他制作工具或已有制作工程时，本技能可提供证据和提纲，由选定工具负责生成，
不同时运行 `render_deck.py` 再做一套稿。

普通日报、组会先确认入选内容，再沿用下文的模板配置制作；不额外要求先确认样页。
工程模板的字体、配色和构图不反向覆盖简单组会模板；跨页分工时共用本次配置和素材清单。
复杂场景的生图不能替代真实曲线、仪器截图或实验照片。

- `生成今日汇报`、`生成当天汇报` 或 `生成每日汇报`：收集 `Asia/Shanghai` 时区对应的本地日历日。
- `生成本周组会汇报` 或 `生成组会汇报`：收集截至所请求本地日期的最近七个日历日。
- 用户指定项目时，只采集匹配的 `cwd`/项目记录和素材。否则，采集所选时间窗口内发现的全部项目；采集范围不等于汇报范围，须经过科研筛选和用户选择。

## 文件存放

沿用共享规则解析项目根目录和 `过程文件/<任务>/`；续做及跨技能共用该任务目录。采集摘要、deck JSON、渲染 PDF、页面 PNG、HTML 和 manifest 均放任务过程目录，按需创建；实验原始数据和现有素材保持原位。渲染检查通过后，自动将 PPTX 无覆盖复制到项目根目录，复核可打开、大小及 SHA-256，并在过程 manifest 记录交付路径与摘要。PDF/HTML 仅在用户要求时作为成果交付；HTML 交付前确认自包含。根目录同名时沿用下文版本规则，不覆盖旧成果。普通任务结束保留过程材料，清理由用户显式触发 ChatNote。

## 数据采集

运行随附的采集器。它只使用本地文件和 Python 标准库：

```text
python scripts/collect_sessions.py --mode today --out "<project-root>/过程文件/<任务>/brief.json"
python scripts/collect_sessions.py --mode week --out "<project-root>/过程文件/<任务>/brief.json"
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
- `下一步`：用户已明确提出、确认，或项目记录已确定的后续操作。仅有助手建议时标为待讨论建议，不写成用户已经决定的计划。

删除问候、重复确认、通用 AI 建议、推测性论断和自造术语。不得把 AI 计划写成结果。数字、单位、仪器名称、测试条件、文件名和错误消息必须准确保留。证据不完整时，写 `未验证` 或 `待确认`；绝不能用常识补齐缺口。

编写提纲前先统一状态。后续证据优先于早期中间结论。用户当前明确说明某项已完成时，可以覆盖早期审计中列出的未决问题。该说明只用于更新状态；不得编造缺失的技术细节。从 `遇到问题` 和 `下一步` 中删除已经解决的问题。

每个入选项目先从相关讨论和实验记录中补齐以下关系，再组织图件：

1. 原来遇到什么问题或限制，为什么要做这项工作。
2. 这次采取了什么办法，为什么安排这组实验或比较。
3. 得到什么结果，目前能作出什么判断，尚未完成什么。
4. 下一步做什么，用来解决哪个尚未回答的问题。

按项目形成连贯叙述，可以跨页表达，不要求每页套用四个栏目。当天采集摘要不是背景的全部来源：起因不在当天记录中时，按入选项目、关联会话及引用文件定向回溯此前记录，查到足以解释当前工作即可；历史原因只作背景，不能计作当天新进展。关键动机或后续安排查不到时，只询问该缺口，继续其他已明确项目；不能从技术名称或常见用途猜原因，也不能擅自安排下一步。

只有代码本身就是科研结果时才展示代码。其他情况下，报告任务、方法和观测结果，不要复制代码块。

## 汇报价值检查

提出提纲前，判断所选工作对目标导师或组会听众是否有用。消息数量多不能证明取得进展。按以下顺序优先纳入：

1. 已验证的科研结果、实验数据、图件或定量测试结论。
2. 对目标导师有价值、已经完成且有可追溯文件或评审结果的科研或项目交付物。
3. 直接解除当前科研阻塞且结果已经验证的支撑工作。

给导师的日报和组会汇报排除科研无关内容，包括常规登录修复、AI 配置、代理设置、磁盘清理、一般软件排障和技能维护。这些内容不进入科研候选清单，也不以“工具与工作流”等页面、附录或改名后的条目进入 PPT；需要私人工作记录时另按该目标处理。常规行政表格也不纳入，除非它对该听众代表实质性项目里程碑。

科研实验自动化、数据处理和测试程序按其实际科研作用与验证结果判断，不因涉及程序就排除。只有直接服务于当前实验、结果分析或科研里程碑，且有可追溯证据的工作才可列为候选；说明具体科研进展及尚未验证的部分，不展示通用工具维护过程。不得用支撑任务填充页数。

如果当天没有第一或第二优先级结果，只剩常规支撑工作，则在生成提纲前停止。直接告诉用户，现有记录缺少适合向导师汇报的实质性进展，并且只问一个问题：停止，还是改为生成私人工作记录。

## 确认入选内容

通过汇报价值检查后，先向用户给出编号候选清单。每项写明项目或工作名称、进展状态、当期主要结果及可用图件；没有结果或图件时如实注明，不把任务标题、模型计划或旧成果写成当期完成项。清单依据实际会话和产物核实，并允许用户补充未记录的线下工作。

请用户按编号选择、删减或补充，等待明确回答后再制作 PPT。只确认听众、目标、日期、项目目录或模板，不等于确认入选内容；泛称“生成今日汇报”也不跳过此步骤。未选定前可以继续核实证据和寻找素材，但不制作页面或 PPT 文件。

用户已经明确指定要讲的具体工作，或已确认本轮候选清单时，沿用该选择，不重复询问。确认后只围绕入选内容组织页面和制作、自检；不加入未选项目。新发现的其他候选若值得补充，先单独询问，不擅自扩充。用户只改正某项状态时更新状态，不能据此推断其他候选也已入选。

## 提纲与页面

入选内容确认后，按实际材料组织简短提纲，每页围绕一个结果或问题。默认采用短篇汇报，按需使用以下页面职责：

1. 总览
2. 主要工作
3. 实验/测试结果
4. 问题与判断
5. 下一步

删除空页，素材较多时按实验拆页，不为固定页数挤小图件。入选内容确认后直接制作并自检；只有用户另外明确要求先审提纲时，才在提纲处等待，不重复确认已选范围。

先讲清入选项目的起因和进展，再匹配实际曲线、仪器截图或现场照片。每组图件回答一个具体问题：图前或相邻页面交代为何验证、各组比较什么，图后解释结果支持的判断及尚缺的工作。必要背景、当前进展和下一步要出现在可见页面，不能只放备注或依赖口头补充。保持图件清楚、文字简短，但不为图大删掉因果关系；内容较多时按项目拆页，不缩成难读小字。

## 逐页中文润色

页面内容整理后、渲染前，使用 [writing-router](../writing-router/SKILL.md) 的中文编辑流程检查逻辑和自然表达，再按 [style-vocab](../style-vocab/SKILL.md) 运行个人词表检查。两步各有目的：逐页润色检查整句与前后页是否好懂，词表检查个人用词；不能只读规则或仅凭词表无命中就声称润色完成。

像向导师说明工作一样写具体问题、行动和结果，减少“取证、核实、验证范围”等检查报告式栏目和机械状态标签；专业术语确有必要时保留，不作批量替换。影响判断的限制集中说清一次，跨页容易误解时保留必要提示。润色不改变数字、单位、比较条件、因果关系或完成状态，也不额外重复已确认的内容选择。

逐项目通读可见页面，检查未参与工作的人能否回答“为什么做、做了什么、做到哪里、接下来做什么”，并核对每组图是否承接前面的具体问题。在任务过程记录中留下逻辑与自然表达检查结果、词表检查结果及需保留的例外；有关键事实缺口时如实保留，不用顺口的句子补造。

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

提纲按当前目标确定后，在任务过程目录写入一个小型 deck JSON 文件。渲染器要求以下结构：

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
python scripts/render_deck.py --deck "<project-root>/过程文件/<任务>/deck.json" --output-dir "<project-root>/过程文件/<任务>" --base-name <YYYYMMDD-or-YYYYMMDD组会>
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
