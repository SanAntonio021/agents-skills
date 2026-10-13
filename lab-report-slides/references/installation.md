# 安装、配置与环境检查

首次安装、迁移或依赖异常时读取；日常制作无需重复加载。

## 安装范围

本文件由执行安装的 Codex 读取；用户入口见 [README](../README.md)。安装命令从实际 `lab-report-slides` 目录运行。

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

4. **配置可持续使用的实际路径。** 定位真实 `python.exe`、`soffice.com`/`soffice.exe` 和 `pdftoppm.exe`，不使用示例中的占位符或作者路径。优先沿用已有 PATH；需要补充时只追加必要的用户级路径，保留原值，并更新当前进程。非默认位置也可使用下文环境变量，同时设置当前进程与用户级值；先保存旧值，不覆盖无关配置。用户级写入被拒绝时，不把软件已安装判成全部失败：由执行安装的 Codex 保存下文项目配置文件，后续检查和生成明确传入其绝对路径。仅设置本次终端的临时变量不算持久配置完成。记录实际使用的 Python 路径，确保后续命令使用装有依赖的同一解释器。PNG/JPG 安装验收不要求 Node.js/sharp。

5. **检查并修复缺项。** 在主技能目录用选定的 Python 运行 `scripts/check_dependencies.py`。对 JSON 中的 `missing` 逐项处理，再运行检查；随后运行下文完整测试。转换通过 `libreoffice-runner` 进行，不直接启动裸 LibreOffice 命令，不关闭用户正在编辑的文件。有未解决错误就报告失败原因，不把文件已下载或预检成功称为安装完成。

6. **验证一次实际使用并交付。** 使用单独临时目录中的合成材料，生成标有“安装测试，非科研结果”的小型 PPT；这是明确允许的纯文字安装样例，可设置 `allow_text_only=true`。沿用 [制作参考](rendering.md#deck-json-与渲染) 的 deck JSON 与渲染命令，按制作参考完成文件和逐页视觉验收。不读取私人会话或实验资料。确认 Codex 可以发现四个技能，并实际读取 `writing-router` 的 `references/common-quality.md`、`references/ai-smell-catalog.md` 和 PPT 随附中文规则。用合成文字核对副标题包含对象、多余操作提醒被删除、必要比较条件仍保留；再检查完整生成样例。未发现技能时核对安装位置，确需重启时提示用户完成后复查。个人词表未配置时跳过个人审计，仍执行通用润色；不能声称通过个人词表审计。有词表时使用上述独立脚本及实际词表目录完成审计。最终报告技能位置、依赖检查、测试、样例文件和首条使用命令。PowerPoint 原生打开与导出若未做，单列为未验证，不影响如实报告已通过的 LibreOffice 渲染结果。

## 安装命令与配置参考

使用 CC Switch 时，添加仓库 `SanAntonio021/agents-skills`、分支 `main`，选择这四个技能并启用 Codex。若管理器只能跟随分支、不能固定提交，安装后逐项核对实际文件与目标提交一致；不一致时不能宣称完成本发布版本安装。

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

无法持久写入用户环境变量时，Codex 可在当前汇报项目保存 `lab-report.local.json`。这是一项安装操作，不是检查脚本自动安装或写配置；已有同名文件先保留并合并必要项。示例中的路径必须替换为实际值，使用默认发现的项目可以省略：

```json
{
  "lo_runner": "<实际技能目录>/libreoffice-runner/scripts/libreoffice_run.py",
  "soffice": "<实际LibreOffice目录>/program/soffice.com",
  "pdftoppm": "<实际Poppler目录>/pdftoppm.exe",
  "work_root": "过程文件/日报运行/work",
  "diagnostics_root": "过程文件/日报运行/diagnostics"
}
```

相对路径基于配置文件所在目录解析。优先级为已有 `LAB_REPORT_*` 环境变量、项目配置、自动发现；配置的程序路径必须存在，明确的错误路径不会被其他发现结果掩盖。目录配置分别对应 `LAB_REPORT_WORK_ROOT` 和 `LAB_REPORT_DIAGNOSTICS_ROOT`，目录可以尚未创建，运行时再创建。配置只保存在项目本机，不提交公开仓库。

```powershell
python scripts/check_dependencies.py --config '<项目配置绝对路径>'
python scripts/render_deck.py --deck '<deck JSON绝对路径>' --output-dir '<过程目录绝对路径>' --base-name '<新文件名>' --config '<项目配置绝对路径>'
```

未传 `--config` 时，依赖检查仅查看当前目录，生成入口仅查看 deck JSON 同目录，不搜索父目录。使用安装回退配置后，后续始终显式传入其绝对路径。检查结果分别列出实际 Python、有效程序路径、来源、当前进程值、项目文件值和用户级持久值；用户级读取被拒绝时标为不可读取，不将其解释为已保存或不存在。所有 JSON 输出采用 UTF-8，不修改系统代码页。

受限 Windows 环境可通过上述工作目录保存临时文件、独立用户配置与诊断；runner 也提供 `--work-root`、`--diagnostics-root`。共享并发锁保持统一位置，所有项目共用两个容量槽位；锁访问被拒绝时 LibreOffice 不启动，应在获准访问该锁的环境中重试，不能为每个项目另建锁以绕开限制。

未配置 `work_root` 时保留系统临时目录默认值。LibreOffice 在深目录中可能因内部缓存路径过长而崩溃；runner 对工作根绝对路径进行长度预检，超过 63 个 UTF-16 单元时返回 `work_root_too_long`。此时由智能体在项目允许范围内选更浅的过程目录，写入本机项目配置后重试；不移动共享锁、不修改原稿。诊断目录不受这项 LibreOffice 工作根限制。

PNG/JPG 不需要 Node.js。只有输入 SVG 时才额外需要 Node.js 和 sharp；也可先从原绘图工具导出 PNG。已安装 sharp 但无法解析模块时，可用 `SHARP_MODULE` 指定其实际模块目录。

## 验证与更新

只测试采集逻辑（使用临时合成会话，不读取个人历史）：

```powershell
python -m unittest discover -s tests -p test_collect_sessions.py -v
```

依赖全部就绪后运行完整测试：

```powershell
python -m unittest discover -s tests -p 'test_*.py' -v
```

完整测试包含真实 LibreOffice 转换，使用 runner 的独立进程和新输出目录；保留用户打开的文件，不结束用户进程。测试临时图仅供软件验证，不是科研结果。默认测试检查 PPTX、PDF、PNG 和 manifest；HTML 只在显式开启预览场景时检查。测试通过不代表已在同学电脑或 PowerPoint 中验收。

更新只处理这四个技能的对应目录并保留本机修改；私人词表留在项目内。首次分享建议先让同学运行依赖检查，再用自己的一个小项目完成“选择内容—讨论并确认总览—整套生成—打开检查”。
