# 科研日报与组会 PPT

从本地 Codex、Claude Code 会话、实验记录和图片整理科研进展，先确认要讲哪些工作，再生成文字和图片可分别编辑的 PPT。

首个支持环境：**Windows + Codex**。采集器也支持 Claude Code 会话；macOS/Linux 完整生成流程尚未验证。默认时间范围按 `Asia/Shanghai` 计算。

## 安装

从本仓库下载并安装以下两个目录，保持同级关系。使用 CC Switch 时，添加仓库 `SanAntonio021/agents-skills`、分支 `main`，选择这两个技能并启用 Codex。

单技能下载包只包含 `lab-report-slides`；配套的 [libreoffice-runner](https://github.com/SanAntonio021/agents-skills/tree/main/libreoffice-runner) 需另外安装。该依赖目录内的作者本机命令示例无需照抄，以本说明的 Python 与路径配置为准。

```text
<技能目录>/
  lab-report-slides/
    SKILL.md
    scripts/
    references/
  libreoffice-runner/
    SKILL.md
    scripts/libreoffice_run.py
    scripts/libreoffice_runner/
```

也可以把两个完整目录交给本机 Codex，说明“请安装这两个技能，并按 lab-report-slides 的 README 检查依赖”。保留原有同名技能，更新前先备份。

在当前技能目录中，用准备运行技能的同一个 Python 安装依赖：

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

## 中文表达和个人词表

内置 [中文表达规则与通用词表](references/chinese-style.md)，没有个人配置也会检查空话、重复和机械表达。它保留“闭环控制”“光学聚焦”“天线口径”等专业语境，不做全文盲替换。

个人词表可放在当前汇报项目的 `汇报词表.md`，或在对话中指定文件。使用“不建议、建议、例外”三列；个人偏好优先于通用措辞建议。已配置 `style-vocab` 的使用者仍可沿用原流程。不必额外安装 `writing-router`、`style-vocab` 或 `pptx` 才能使用基本工作流。

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

完整测试包含真实 LibreOffice 转换，首次运行前确认没有正在编辑的 LibreOffice 文件；不结束用户进程。测试临时图仅供软件验证，不是科研结果。测试通过不代表已在同学电脑或 PowerPoint 中验收。

更新只替换这两个技能的对应目录；私人词表留在项目内。首次分享建议先让同学运行依赖检查，再用自己的一个小项目完成“选择内容—生成—打开检查”。
