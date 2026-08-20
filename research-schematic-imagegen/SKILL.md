---
name: research-schematic-imagegen
description: 为自然科学基金、工程申报、科研汇报和答辩 PPT 设计、生成、编辑高技术密度科研示意图。用户提到科研示意图、关键技术图、机理图、技术路线图、系统框图、端到端全流程图、业务/控制/运维流、申报 PPT 配图、统一系列配图、英文图中文化、线条/箭头/光束局部修改、GPT Image 2 生图或改图、图中文字纠错时必须使用。只负责图件，不代写申报书正文，也不修改 PPT 文件，除非用户另行明确授权。
metadata:
  compatibility: Node.js 18+ for direct OpenAI-compatible image API scripts; Node.js 22+ for CC Switch provider discovery; Windows PowerShell or PowerShell 7 for deterministic label correction.
---

# 科研示意图生成与编辑

## 目标

把已经确认的技术方案转成可用于基金、工程申报和科研汇报的高技术密度示意图。技术含义优先于画面效果，本轮交付清单只包含用户真正应使用的版本；不据此整理任务开始前已存在的文件。

本 skill 基于 `ConardLi/garden-skills` 的 `gpt-image-2@1.0.4` MIT 核心脚本改写。来源、基准和上游维护方式见：

- [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)
- [references/upstream-maintenance.md](references/upstream-maintenance.md)

## 边界

- 本 skill 负责科研示意图的技术约束、视觉设计、生图、改图、中文化、检查和本轮生成版本的整理。
- 不代写申报书、论文或技术报告正文。
- 不修改 PPTX、DOCX 或其他 Office 文件，除非用户对该文件另行明确授权。
- 用户要 IEEE 投稿数据图、可编辑矢量系统图或论文图审查时，优先使用 `paper-figure-review`。
- 用户要海报、商品图、头像、UI 样机等通用图像任务时，使用上游 `gpt-image-2` 或宿主原生图像工具。

## 必须先确定的三件事

1. **图的用途**：基金申报、工程申报、答辩 PPT、论文概念图，还是内部讨论。
2. **技术依据**：哪份本地文件或用户确认内容是当前权威版本。
3. **生成路径**：宿主原生图像工具、用户已确认的 OpenAI 兼容图像接口，还是只输出提示词。

如果技术依据互相冲突，先列出冲突并问一个最关键的问题。不要先生成一张视觉上漂亮、技术上错误的图。

## 工作流

### 1. 确定图像后端

本 skill 的图像请求与 Codex/Claude 聊天 provider 解耦。不要为了生图切换 CC Switch 当前聊天 provider；只支持 `/images/generations` 或 `/images/edits` 的中转站不能承担聊天请求。

默认后端是 Cici Switch 私有注册表，而不是独立 API key。每次生成或编辑都必须由用户指定一个已登记 alias；未指定时停止并只列出已登记 alias，向用户询问选择。不得扫描全部 CC Switch 记录后自动选择，也不得自动切换、重试或故障转移。

```powershell
node <skill-dir>/scripts/check-mode.js --provider <alias> --json
```

规则：

- 用户的生图/改图请求加上其渠道选择，只授权该渠道的一次计费调用；失败后必须报告，不能改用其他渠道。
- `/models` 仅证明模型可见；每个新渠道仍需在用户授权后做一次最小真实 `/images/generations` 验证。它不证明 `/images/edits` 可用。
- `gpt-image-2` 是登记时的默认模型。`gpt-image-2-cf` 仅在用户明确指定，且该渠道当前 `/models` 返回它时使用。
- API key 只从 CC Switch 数据库读取到当前进程内存，不写进 skill、项目、注册表、命令行参数或日志；不切换当前聊天 provider。
- 认证、配额、超时或渠道错误按原文简短报告；不静默换路。

私有注册表位于 `~/.config/research-schematic-imagegen/providers.json`，不属于技能源码或 Git 交付物。每条记录只含 `alias`、`provider_id`、`app_type`、`expected_name` 和 `default_model`，不含 API key。正常路径会核验 provider ID、名称、类型和所选模型，任一漂移即停止。

新增渠道流程：先对用户指定的候选 ID 运行 `/models` 检查，展示安全的名称、ID 与可用图像模型；取得用户确认后，才手动登记该渠道：

```powershell
node <skill-dir>/scripts/register-ccswitch-image-provider.js --alias <alias> --provider-id <id> --default-model gpt-image-2 --json
```

`--replace` 才允许更新已有 alias 或 provider ID。候选检查可使用：

```powershell
node <skill-dir>/scripts/discover-ccswitch-image-providers.js --provider-id <id> --json
```

独立接口只保留为显式兼容路径：传入 `--backend direct` 或设置 `RESEARCH_IMAGE_BACKEND=direct`。该模式才会读取显式 `RESEARCH_IMAGE_ENV_FILE` 或 `~/.config/research-schematic-imagegen/image-api.env`；普通路径绝不自动读取 `hangzhale.env`。

支持的环境变量：

| 变量 | 作用 |
| --- | --- |
| `RESEARCH_IMAGE_BACKEND` | `ccswitch`（默认）或显式兼容的 `direct` |
| `RESEARCH_IMAGE_PROVIDER` | 已登记 alias；CLI 的 `--provider` 可指定本次渠道 |
| `RESEARCH_IMAGE_PROVIDER_REGISTRY` | 覆盖私有 `providers.json` 路径 |
| `RESEARCH_IMAGE_CONFIG_DIR` | 覆盖私有配置目录 |
| `RESEARCH_IMAGE_CCSWITCH_DB` | CC Switch DB 路径；默认 `~/.cc-switch/cc-switch.db` |
| `RESEARCH_IMAGE_MODEL` | 指定模型；Cici Switch 路径会验证其当前可用性 |
| `RESEARCH_IMAGE_ENV_FILE` | 仅 `direct` 模式使用的私有 env 文件 |
| `RESEARCH_IMAGE_API_KEY`、`RESEARCH_IMAGE_BASE_URL` | 仅 `direct` 模式使用的 OpenAI 兼容接口配置 |
| `ENABLE_RESEARCH_IMAGEGEN` | `direct` 模式中启用本地 API 调用；Cici Switch 在已选 alias 后由脚本在进程内设置 |
| `RESEARCH_IMAGE_OUTPUT_ROOT` | 默认输出根目录 `research-schematic-imagegen` |

### 2. 建立技术表达合同

读取 [references/technical-contract.md](references/technical-contract.md)，为每张图列清：

- 必须表达的对象、模块、信号流和因果关系
- 可以简化的内容
- 禁止出现的旧方案、越界功能和未经确认的数值
- 图内允许使用的短标签
- 仍待确认的技术问题

系列图先建立一份共同视觉合同，再分别建立每张图的技术合同。

#### 全流程系统图

一张图同时表达端到端主路径、运行保障/控制关系或可选机制时，除技术合同外，读取 [references/full-flow-system-diagram.md](references/full-flow-system-diagram.md)。先把节点、分区、连线和视觉语义写成台账，再让模型出图；不要用一串看似合理的箭头代替已确认的系统关系。

- 主业务路径应是首要阅读线，箭头端点逐段对应台账中的源节点和目标节点。
- 控制、运维、反馈和可选机制必须与主业务路径使用可区分的线型/颜色，并在图例中说明；可选关系不能被画成业务必经路径。
- 控制或保障节点默认靠近其受管对象，避免用跨图绕线代替清晰的逻辑关系。图中要区分逻辑管理关系和实际物理通信链路，不能无依据地把其中一种暗示成另一种。
- 面向汇报或跨专业讨论时，首次出现的陌生缩写使用已确认的中文全称或括号内短解释；这些解释仍必须进入准确标签清单，不能由模型临场改写。

### 3. 先做一张风格基准图

系列任务不要一开始生成全部图片。先选信息结构最典型的一张作为基准，确认：

- 白底、蓝灰主色、强调色数量
- 模块形态、箭头、线宽、字体和留白
- 信息密度与文字量
- 画幅和输出尺寸

基准图通过后再生成其余图片，减少系列风格漂移。

### 4. 编写提示词

按 [references/scientific-schematic.md](references/scientific-schematic.md) 选择最接近的结构。提示词必须同时包含：

- 画什么
- 技术关系如何连接
- 必须出现什么
- 禁止出现什么
- 视觉风格和尺寸
- 允许出现的准确标签

全流程系统图还必须逐条复述连线台账的源节点、目标节点、关系类型和图例语义；不要只写“清晰连接”或“合理布局”。

图像模型不负责决定技术方案。禁止让模型自行补全关键技术路线、定量指标或系统能力。

### 5. 生成与编辑

#### 编辑范围控制

用户只要求修改一条线、一个箭头、一束光、一个标签或一个局部对象时，把原图的其余构图视为锁定内容。“更现代”“更好看”只约束目标局部，不自动授权重画背景、对象、比例或整体风格。

- 先用紧贴目标区域的遮罩做克制版本，尽量保持遮罩外内容不变。
- 整图重画只用于原构图无法表达当前技术含义，或用户明确要求重新设计；重画结果另存为候选版本，不能覆盖克制版本。
- 对线条、箭头、光束和规则边框，模型编辑若出现边缘模糊、双边、线宽漂移、过强光晕或端点错位，最多再做一次针对性编辑；仍不清晰就停止生成。
- 模型不适合稳定绘制简单几何元素时，改用确定性覆盖。最终载体是 PPTX 且用户明确授权修改该文件时，优先使用 PowerPoint 原生矢量线条和发光效果；没有 PPTX 修改授权时，只处理位图或给出可复现的线宽、颜色、透明度和发光参数。

文本生图：

```powershell
node <skill-dir>/scripts/generate.js --provider <alias> --promptfile <prompt.md> --image <working.png> --size 1536x1024 --quality high
```

基于原图编辑：

```powershell
node <skill-dir>/scripts/edit.js --provider <alias> --image <source.png> --promptfile <edit-prompt.md> --output <working.png> --input-fidelity high
```

带遮罩局部编辑：

```powershell
node <skill-dir>/scripts/edit.js --provider <alias> --image <source.png> --mask <mask.png> --promptfile <edit-prompt.md> --output <working.png> --input-fidelity high
```

所有生成和编辑结果先进入工作目录，不直接写入 `final/`。

### 6. 中文化和文字纠错

先读 [references/chinese-localization.md](references/chinese-localization.md)。默认顺序：

1. 先确认原图构图和技术含义。
2. 再用编辑接口替换为短中文标签。
3. 逐项核对文字，不凭缩略图判断。
4. 同一局部连续两次模型编辑仍错误时，停止继续消耗生成调用。
5. 对规则色块内的文字使用 `fix-label.ps1` 做确定性覆盖，并检查局部裁剪。

确定性覆盖示例：

```powershell
& <skill-dir>/scripts/fix-label.ps1 -InputPath <source.png> -OutputPath <fixed.png> -Text '自适应调制编码' -X 100 -Y 200 -Width 360 -Height 70 -FontSize 28 -BackgroundColor '#FFFFFF' -TextColor '#16324F'
```

### 7. 技术和视觉双重检查

每张图至少检查：

- 技术对象、信号方向、阶段顺序是否符合技术合同
- 是否混入旧方案、越界职责、虚构参数或错误术语
- 中文标签是否逐字正确，缩放到 PPT 使用尺寸后是否可读
- 系列图的画幅、颜色、线条、标题层级和信息密度是否一致
- 图内文字是否少而必要
- 是否存在遮挡、裁切、重复元素或无意义装饰
- 局部编辑后，遮罩外内容是否与原图一致；不应出现未经请求的背景、对象或构图变化
- 按 PPT 实际显示尺寸检查边缘清晰度；细线、光束、文字和对象轮廓不能出现局部模糊、双边或不均匀光晕

全流程系统图按 [references/full-flow-system-diagram.md](references/full-flow-system-diagram.md) 的整图和分区验收执行。文字重叠、裁切、悬空箭头、端点错误、图例与实际线型不一致，或控制/可选关系越界时，不能交付为最终图。局部问题优先做定向修正，并锁定已通过的主路径和无关区域；只有构图已无法表达技术关系时才重画整图。

只要技术方案后来变化，就重新核对图片。文件名含 `final` 不能替代技术复核。

### 8. 整理最终输出

先读 [references/output-ownership.md](references/output-ownership.md)。科研图目录常混有历史定稿和其他课题图；目录名是 `final` 不表示当前任务拥有其中所有文件。

- 写入前只读列出目标目录已有文件。任务开始前已存在的文件一律视为用户资产。
- 未经用户明确授权，不移动、删除、重命名、覆盖或归档既有文件。
- 可直接整理到 `working/` 的内容只限本轮生成的过程图、遮罩、诊断图和被用户否定的本轮候选。
- “用户要求 N 张图”约束本轮交付清单，不约束一个已存在目录中的历史文件总数。
- 发现目录中有非本轮文件时，保留原位并在检查结果中报告；需要物理隔离时，新建任务级子目录，或先征得用户同意。

默认目录：

```text
research-schematic-imagegen/
├── prompt/       最终使用的生成和编辑提示词
├── working/      原图、版本图、遮罩和诊断裁剪
├── final/        当前选定、可交付的图片
└── record.md     文件映射、技术边界、已知问题和生成路径
```

在 `record.md` 中记录本轮文件映射，并生成独立 JSON manifest 供验证脚本读取；验证只覆盖 manifest 中的图片：

```powershell
node <skill-dir>/scripts/verify-output.js --dir <final-dir> --manifest <manifest.json> --expected-count 4 --width 1536 --height 1024 --json
```

`verify-output.js` 在 manifest 模式下把其他 PNG 报告为 `extra_files`，但不移动它们，也不把它们计入本轮交付数量。只有用户明确要求清理目录时，才可以在列明文件和目标路径并获得确认后执行移动。

## 上游更新检查

用户问“上游有没有更新”“本地专属技能要不要跟进”时，读取 [references/upstream-maintenance.md](references/upstream-maintenance.md)。先检查零暴露镜像，再运行差异脚本。上游变化只作为评审输入，不自动覆盖本地 skill。

## 交付说明

最终回复只需说明：

- 当前应使用的最终目录和图片数量
- 已完成的技术、文字和尺寸检查
- 仍存在的技术含义风险
- 实际使用的图像路径或渠道，不回显凭据
