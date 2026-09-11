# 科研日报与组会 PPT

从本地 Codex、Claude Code 会话、实验记录和图片整理科研进展，先确认要讲哪些工作，再生成文字和图片可分别编辑的 PPT。

首个支持环境：**Windows + Codex**。采集器也支持 Claude Code 会话；macOS/Linux 完整生成流程尚未验证。默认时间范围按 `Asia/Shanghai` 计算。

## 把这个页面交给 Codex

在 **Windows 本机的 Codex** 中发送本发布页链接，并说“请按页面流程完成安装”即可。下面是给执行安装的 Codex 的完整步骤；使用者无需另外下载目录、安装 CC Switch 或复制多段命令。

### 默认安装：PPT + 完整中文润色

把本页交给 Codex 安装，默认同时安装以下四个技能，不要求使用者逐个点名：

| 技能 | 用途 |
|---|---|
| `lab-report-slides` | 科研内容整理、页面组织与 PPT 生成 |
| `libreoffice-runner` | 转换及渲染检查，基本生成流程所需 |
| `writing-router` | 完整中文质量规则与去 AI 味检查 |
| `style-vocab` | 个人词表加载与用词检查；词表由使用者提供 |

只有用户明确选择精简安装时，才只装前两个并使用 PPT 自带的基础润色。默认完整安装不额外安装英文 `humanizer`、整套文体技能或整个仓库。

### Codex 安装流程

用户要求按本页安装后，连续完成以下步骤；不要只返回教程或缺项清单。默认安装上表四个技能及缺少的必要软件，已有可用依赖直接复用。遇到管理员授权、网络访问限制或已有同名文件冲突时，说明具体问题，再请用户配合。

1. **确认本机环境和安装位置。** 确认任务在 Windows 本机执行，能够访问网络和运行命令；不要装进远端 Linux 或 WSL 后声称 Windows 已安装。解析启动用户的实际主目录。已有技能管理器时沿用其受支持安装入口；否则优先使用可用的 `skill-installer`，或将完整技能目录安装到该用户的 `.agents/skills`。先检查同名技能，保留已有修改，不把整个仓库安装成技能。目录发现方式见 [Codex 官方说明](https://learn.chatgpt.com/docs/build-skills)。

2. **取得四个技能。** 从同一仓库 `SanAntonio021/agents-skills` 的 `main` 解析一次当前提交 SHA，或沿用发布页指定的固定提交；从该提交取得 `lab-report-slides`、`libreoffice-runner`、`writing-router`、`style-vocab` 四个完整目录。可以下载该提交归档后只取这四项，不把整个仓库安装成技能，不混用旧附件与新依赖。记录提交和实际安装目录；使用技能管理器时沿用其受支持入口。另从同一提交取得 `ieee-manuscript-edit/scripts/audit_writing_memory.py`，保存到实际 `style-vocab/tools/audit_writing_memory.py`，记录来源与文件校验值；该脚本仅使用 Python 标准库，无需安装论文技能。个人词表审计时用此实际脚本路径和用户自己的 `--vocab-root`，覆盖技能文档中的作者路径示例。四个目录保持同级；目录不同时按实际安装位置解析共用参考文件，并配置 `LAB_REPORT_LO_RUNNER`。全部下载与依赖安装由 Codex 执行，不要求用户手工补齐。

3. **补齐软件和 Python 库。** 先发现并复用已有的 Python、LibreOffice 和 `pdftoppm`。Python 需 3.10+；缺失时可选 Python 3.13 的稳定补丁版本。优先使用本机已有的软件包管理器，先查询并核对软件名称、发布者及安装来源，再安装缺项；没有包管理器时，从 [Python 官方 Windows 下载页](https://www.python.org/downloads/windows/)、[LibreOffice 官网](https://www.libreoffice.org/download/) 和 [Poppler Windows 构建发布页](https://github.com/oschwartz10612/poppler-windows/releases) 获取与本机架构匹配的安装包。Poppler 链接是社区 Windows 构建。不要安装预发布版本或把包管理器当成额外必装依赖。使用实际选定的同一个 Python 执行下文 `pip install -r requirements.txt`。

4. **配置可持续使用的实际路径。** 定位真实 `python.exe`、`soffice.com`/`soffice.exe` 和 `pdftoppm.exe`，不使用示例中的占位符或作者路径。优先沿用已有 PATH；需要补充时只追加必要的用户级路径，保留原值，并更新当前进程。非默认位置也可使用下文环境变量：同时设置当前进程与用户级值，供以后启动的 Codex 使用；先保存旧值，不覆盖与本任务无关的配置。仅设置本次终端的临时变量不算完成。记录实际使用的 Python 路径，确保后续命令使用装有依赖的同一解释器。PNG/JPG 安装验收不要求 Node.js/sharp。

5. **检查并修复缺项。** 在主技能目录用选定的 Python 运行 `scripts/check_dependencies.py`。对 JSON 中的 `missing` 逐项处理，再运行检查；随后运行下文完整测试。转换通过 `libreoffice-runner` 进行，不直接启动裸 LibreOffice 命令，不关闭用户正在编辑的文件。有未解决错误就报告失败原因，不把文件已下载或预检成功称为安装完成。

6. **验证一次实际使用并交付。** 使用单独临时目录中的合成材料，生成标有“安装测试，非科研结果”的小型 PPT；这是明确允许的纯文字安装样例，可设置 `allow_text_only=true`。沿用 SKILL.md 的 deck JSON 与渲染命令，检查 PPTX、PDF、PNG、HTML 和 manifest，查看逐页预览并确认原生文字可编辑。不读取私人会话或实验资料。确认 Codex 可以发现四个技能，并实际读取 `writing-router` 的 `references/common-quality.md`、`references/ai-smell-catalog.md` 和 PPT 随附中文规则。用合成文字核对副标题包含对象、多余操作提醒被删除、必要比较条件仍保留；再检查完整生成样例。未发现技能时核对安装位置，确需重启时提示用户完成后复查。个人词表未配置时跳过个人审计，仍执行通用润色；不能声称通过个人词表审计。有词表时使用上述独立脚本及实际词表目录完成审计。最终报告技能位置、依赖检查、测试、样例文件和首条使用命令。PowerPoint 原生打开与导出若未做，单列为未验证，不影响如实报告已通过的 LibreOffice 渲染结果。

完成后，使用者可以说：“生成今日汇报，先列出可汇报的科研进展让我选择。”

## 安装命令与配置参考

从本仓库下载并安装以下四个目录，保持同级关系。使用 CC Switch 时，添加仓库 `SanAntonio021/agents-skills`、分支 `main`，选择这四个技能并启用 Codex。若管理器只能跟随分支、不能固定提交，安装后逐项核对实际文件与目标提交一致；不一致时不能宣称完成本发布版本安装。

旧单技能下载包只包含当时版本的 `lab-report-slides`，不代表当前完整配置。默认按上方流程从同一提交安装四项。依赖技能中的作者本机路径仅作作者环境记录，使用时按本机实际配置解析，不创建作者同名目录。

```text
<技能目录>/
  lab-report-slides/
    SKILL.md
    scripts/
    references/
  writing-router/
    SKILL.md
    references/
  style-vocab/
    SKILL.md
    tools/audit_writing_memory.py  # 安装时从同版本取得的独立脚本
  libreoffice-runner/
    SKILL.md
    scripts/libreoffice_run.py
    scripts/libreoffice_runner/
```

采用上面的 Codex 安装流程时，这些下载与目录整理都由 Codex 执行。已有同名技能先备份，保留用户修改。

以下安装及测试命令均先进入实际的 `lab-report-slides` 目录，用准备运行技能的同一个 Python 执行：

```powershell
python -m pip install -r requirements.txt
python scripts/check_dependencies.py
```

需要 Python 3.10 或更新版本、LibreOffice，以及 Poppler 中的 `pdftoppm`。检查脚本只报告是否找到依赖，不自动下载软件或修改系统。`requirements.txt` 含 Windows 时区数据库和 runner 所需的 Python 库；不需要把 Python 安装到作者的固定目录。

LibreOffice 可采用 Windows 默认安装位置，或将其程序目录加入 PATH。Poppler 的程序目录需在 PATH 中。非默认安装可在当前会话指定：

```powershell
$env:LAB_REPORT_LO_RUNNER = '<实际技能目录>\libreoffice-runner\scripts\libreoffice_run.py'
$env:LAB_REPORT_SOFFICE = '<LibreOffice安装目录>\program\soffice.com'
$env:LAB_REPORT_PDFTOPPM = '<Poppler程序目录>\pdftoppm.exe'
```

以上值是占位符，须替换成实际已存在的路径。默认同级安装时不需要设置 `LAB_REPORT_LO_RUNNER`。预检通过只说明依赖可定位，首次生成仍须检查实际 PPT、PDF 和逐页图片。

PNG/JPG 不需要 Node.js。只有输入 SVG 时才额外需要 Node.js 和 sharp；也可先从原绘图工具导出 PNG。已安装 sharp 但无法解析模块时，可用 `SHARP_MODULE` 指定其实际模块目录。

## 开始使用

可以直接对 Codex 说：

- “生成今日汇报，只看这个实验项目。先列出今天可汇报的科研进展让我选择。”
- “生成本周组会汇报，曲线在 results 目录；先让我选择内容，下一步只写我已经确认的安排。”
- “把候选 1、3 做成 PPT，不写 2。使用项目里的汇报词表.md。”

若没有可读取的本地会话，直接提供实验记录与图件；不要把空采集结果理解为没有做过科研。自定义会话位置可使用采集器的 `--codex-root`、`--claude-root`；不自动查找其他账号的记录。

无论从哪种来源采集，先核实事实并确认入选内容。普通账号、代理、软件维护不自动写成科研成果；没有实质进展时不凑页数。

每个进展页用同一行的“项目名称 + 三个 ASCII 空格 + 本页主题”标明归属：项目大标题保留字号并加粗，小标题按 PowerPoint 字号档缩小两次、不加粗，例如 36 → 32 → 28 pt。项目名以实际项目及用户确认的名称为准；最后的“下一步工作”总页保留单标题。新稿在 deck JSON 中分别提供 `project` 和 `title`，旧的单 `title` 稿仍兼容。

## 更换自己的模板

项目首次使用且尚未指定模板时，Codex 会主动询问：“使用内置模板，还是提供你自己的本地 PPT 模板？已有汇报也可以。”选择后在当前项目记住，后续直接沿用并提醒可以更换；已经在请求里指定模板时不重复询问。

直接把本地 `.pptx`、带样页的 `.potx` 或以前做过的汇报路径交给 Codex，说：“以后按这份模板生成每日汇报。”Codex 会检查样页，复用页面尺寸、母版、Logo、字体和图文布局，替换旧报告内容，并在当前项目记住模板。

原模板保持不动；原稿中的实验图和结论不会当作新成果。首次会生成一份适配样例检查效果，之后沿用项目配置。你不需要自己填对象编号或 JSON。具体执行见 [本地模板流程](references/local-template.md)；复杂图表、SmartArt、动画或纯空白母版可能需要先补充适用样页。

## 中文表达和个人词表

内置 [中文表达规则与通用词表](references/chinese-style.md)，没有个人配置也会检查空话、重复和机械表达。它保留“闭环控制”“光学聚焦”“天线口径”等专业语境，不做全文盲替换。

结果句准确写明仿真、离线测试或实测状态后，不再补“尚未连接真实仪器”“不代表实测通过”等重复防御性说明。已确定的后续实机安排放最后一页；影响结论的实际测量条件、解释限制和数据状态仍保留。

每次生成还会主动检查多余的术语释义、图中标签解释和读图提示：删除不影响理解、图文对应和结论的补充，有口头讲解价值时放备注；防止误读所必需的解释留在页面，无需每次单独提醒。

个人词表可放在当前汇报项目的 `汇报词表.md`，或在对话中指定文件。使用“不建议、建议、例外”三列；个人偏好优先于通用措辞建议。默认安装已包含 `writing-router` 和 `style-vocab`，生成时自动调用，无需另发润色指令。没有个人词表时仍执行共用规则与随附基础用词检查，不凭空生成个人偏好。精简安装可完成基本工作流，不强制安装 `pptx`。

## 本机个性化配置

模板、项目名称、交付目录和个人词表不随公开技能分发。安装时使用用户提供的配置；没有模板则按首次使用流程选择，没有交付目录则沿用当前汇报项目目录，没有个人词表则用通用规则。不要复制作者的用户名、磁盘路径、私人样稿或词表；`writing-router` 中的私人样稿路径不可用时跳过该增强，不阻断 PPT 流程。四个技能齐全代表检查能力配置齐全，不保证未经本机验证的字体、模板和输出与作者电脑逐像素相同。

## 产物与资料保护

- 默认交付 PPTX，过程目录保留 PDF、逐页 PNG、自包含 HTML 和来源清单。
- PPT 文字是原生文本框，图件是独立图片；图片内部的曲线数据和标签仍是像素。
- 使用样式参数，不读取作者的原始 PPT，也不附带私人会话或实验图片。微软雅黑未安装时，先选择本机已有的中文字体。
- 采集脚本不联网；Codex 本身如何处理材料取决于所用服务和账号设置。不要把“本地采集”理解为模型完全离线运行。
- 采集摘要和来源清单包含本地内容及路径，仅用于本次任务，不提交到公开仓库。密钥遮盖只能识别部分常见格式，不能代替人工检查。
- 实际 PPT 经 LibreOffice 渲染检查；PowerPoint 原生打开、字体替换和导出应另外验证，没有验证就明确说明。

## 验证与更新

只测试采集逻辑（使用临时合成会话，不读取个人历史）：

```powershell
python -m unittest discover -s tests -p test_collect_sessions.py -v
```

依赖全部就绪后运行完整测试：

```powershell
python -m unittest discover -s tests -p 'test_*.py' -v
```

完整测试包含真实 LibreOffice 转换，使用 runner 的独立进程和新输出目录；保留用户打开的文件，不结束用户进程。测试临时图仅供软件验证，不是科研结果。测试通过不代表已在同学电脑或 PowerPoint 中验收。

更新只处理这四个技能的对应目录并保留本机修改；私人词表留在项目内。首次分享建议先让同学运行依赖检查，再用自己的一个小项目完成“选择内容—生成—打开检查”。
