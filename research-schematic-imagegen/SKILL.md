---
name: research-schematic-imagegen
description: 为自然科学基金、工程申报、科研汇报和答辩 PPT 设计、生成、编辑高技术密度科研示意图。用户提到科研示意图、关键技术图、机理图、技术路线图、系统框图、申报 PPT 配图、统一系列配图、英文图中文化、线条/箭头/光束局部修改、GPT Image 2 生图或改图、图中文字纠错时必须使用。只负责图件，不代写申报书正文，也不修改 PPT 文件，除非用户另行明确授权。
compatibility: Node.js 18+ for direct OpenAI-compatible image API scripts; Node.js 22+ for CC Switch provider discovery; Windows PowerShell or PowerShell 7 for deterministic label correction.
---

# 科研示意图生成与编辑

## 目标

把已经确认的技术方案转成可用于基金、工程申报和科研汇报的高技术密度示意图。技术含义优先于画面效果，最终目录只保留用户真正应使用的版本。

本 skill 基于 `ConardLi/garden-skills` 的 `gpt-image-2@1.0.4` MIT 核心脚本改写。来源、基准和上游维护方式见：

- [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)
- [references/upstream-maintenance.md](references/upstream-maintenance.md)

## 边界

- 本 skill 负责科研示意图的技术约束、视觉设计、生图、改图、中文化、检查和版本整理。
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

按以下顺序选择后端：

1. 用户明确指定并已配置 OpenAI 兼容图像接口时，使用本地脚本直接调用该接口。
2. 用户选择 `RESEARCH_IMAGE_BACKEND=ccswitch` 时，只读发现 CC Switch 中的候选并探测图像模型。
3. 没有可用本地接口且宿主提供原生图像工具时，使用宿主原生工具。
4. 两者都不可用时，只输出提示词并报告原因。

本地 OpenAI 兼容接口先运行：

```powershell
node <skill-dir>/scripts/check-mode.js --json
```

规则：

- `ENABLE_RESEARCH_IMAGEGEN=1` 且存在 API key 才允许本地脚本发起付费或计费请求。
- API key 只通过当前进程环境变量传入，不写进 skill、项目文件、命令行参数或输出日志。
- 用户未明确确认前，不启用付费本地接口；不切换 CC Switch 当前 provider。
- `/models` 只说明模型名可见，不能证明 `/images/generations` 或 `/images/edits` 可用。
- 需要判断渠道时，以用户确认后的真实小规模生成或编辑调用为准。
- 认证、配额、超时、运行时或渠道错误按原文简短报告，不静默换路。

密钥只通过当前进程环境读取。技能会自动发现以下用户私有配置文件（按顺序，显式 `RESEARCH_IMAGE_ENV_FILE` 优先）：

- `~/.config/research-schematic-imagegen/image-api.env`
- `~/.config/research-schematic-imagegen/hangzhale.env`（兼容既有配置）

配置文件不属于技能源码、项目文件或 Git 交付物。其内容只在本地进程中加载，不回显到日志。

支持的环境变量：

| 变量 | 作用 |
| --- | --- |
| `ENABLE_RESEARCH_IMAGEGEN` | `1/true/yes/on` 时允许本地 API 调用 |
| `RESEARCH_IMAGE_API_KEY` | 图像接口 API key；也兼容 `OPENAI_API_KEY` |
| `RESEARCH_IMAGE_BASE_URL` | OpenAI 兼容接口根地址；也兼容 `OPENAI_BASE_URL` |
| `RESEARCH_IMAGE_MODEL` | 默认 `gpt-image-2`；也兼容 `OPENAI_IMAGE_MODEL` |
| `RESEARCH_IMAGE_ENV_FILE` | 显式指定私有 env 文件；优先于自动发现路径 |
| `RESEARCH_IMAGE_CONFIG_DIR` | 覆盖默认用户配置目录 |
| `RESEARCH_IMAGE_BACKEND` | `direct` 或 `ccswitch`；默认 `direct` |
| `RESEARCH_IMAGE_CCSWITCH_DB` | CC Switch DB 路径；默认 `~/.cc-switch/cc-switch.db` |
| `RESEARCH_IMAGE_CC_SWITCH_PROVIDER_ID` | 指定 CC Switch provider ID；优先于自动选择 |
| `RESEARCH_IMAGE_CC_SWITCH_PROVIDER_NAME` | 指定 CC Switch provider 名称；同名多条记录仍需消歧 |
| `RESEARCH_IMAGE_OUTPUT_ROOT` | 默认输出根目录 `research-schematic-imagegen` |

CC Switch 发现规则：

- 只读 `providers` 表的结构化配置，不修改 CC Switch DB，不切换当前聊天 provider。
- 解析 provider 的基址和 key 后，自动补齐 `/v1`，逐个调用 `/models`。
- 只把返回图像模型的 provider 视为候选；相同基址与相同 key 的重复记录合并。
- 候选唯一时自动使用；多个候选时停止并列出名称和 ID，要求通过 `RESEARCH_IMAGE_CC_SWITCH_PROVIDER_ID` 或名称指定。
- `/models` 只是候选筛选，正式使用前仍需一次真实小规模生图确认 `/images/generations`。

手动查看候选：

```powershell
node <skill-dir>/scripts/discover-ccswitch-image-providers.js --json
```

### 2. 建立技术表达合同

读取 [references/technical-contract.md](references/technical-contract.md)，为每张图列清：

- 必须表达的对象、模块、信号流和因果关系
- 可以简化的内容
- 禁止出现的旧方案、越界功能和未经确认的数值
- 图内允许使用的短标签
- 仍待确认的技术问题

系列图先建立一份共同视觉合同，再分别建立每张图的技术合同。

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
node <skill-dir>/scripts/generate.js --promptfile <prompt.md> --image <working.png> --size 1536x1024 --quality high
```

基于原图编辑：

```powershell
node <skill-dir>/scripts/edit.js --image <source.png> --promptfile <edit-prompt.md> --output <working.png> --input-fidelity high
```

带遮罩局部编辑：

```powershell
node <skill-dir>/scripts/edit.js --image <source.png> --mask <mask.png> --promptfile <edit-prompt.md> --output <working.png> --input-fidelity high
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

只要技术方案后来变化，就重新核对图片。文件名含 `final` 不能替代技术复核。

### 8. 整理最终输出

默认目录：

```text
research-schematic-imagegen/
├── prompt/       最终使用的生成和编辑提示词
├── working/      原图、版本图、遮罩和诊断裁剪
├── final/        当前选定、可交付的图片
└── record.md     文件映射、技术边界、已知问题和生成路径
```

最终检查：

```powershell
node <skill-dir>/scripts/verify-output.js --dir <final-dir> --expected-count 4 --width 1536 --height 1024 --json
```

`final/` 必须恰好包含用户要求的数量。过程版本和被否定版本留在 `working/` 或可恢复归档区，不要和最终图并列造成选择混乱。

## 上游更新检查

用户问“上游有没有更新”“本地专属技能要不要跟进”时，读取 [references/upstream-maintenance.md](references/upstream-maintenance.md)。先检查零暴露镜像，再运行差异脚本。上游变化只作为评审输入，不自动覆盖本地 skill。

## 交付说明

最终回复只需说明：

- 当前应使用的最终目录和图片数量
- 已完成的技术、文字和尺寸检查
- 仍存在的技术含义风险
- 实际使用的图像路径或渠道，不回显凭据
