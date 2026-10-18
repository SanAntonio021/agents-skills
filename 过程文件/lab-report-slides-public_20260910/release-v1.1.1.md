# 科研日报与组会 PPT：首次主动选择模板

适用于 Windows 本机 Codex。把本页链接交给 Codex，说“请按页面流程完成安装”。

项目首次使用且尚未指定模板时，会主动询问使用内置模板还是提供本地 PPT；已有汇报也可以。已选模板在当前项目沿用并提醒可更换；本轮明确指定时不重复询问。安装合成测试不会增加模板询问。

本版本仅更新交互规则与使用说明，已核对首次使用、沿用、更换及安装流程的一致性；渲染程序未变。自定义模板仍需首次适配检查。

### Codex 安装流程

用户要求按本页安装后，连续完成以下步骤；不要只返回教程或缺项清单。只安装本技能、配套转换技能和缺少的必要软件。遇到管理员授权、网络访问限制或已有同名文件冲突时，说明具体问题，再请用户配合。

1. **确认本机环境和安装位置。** 确认任务在 Windows 本机执行，能够访问网络和运行命令；不要装进远端 Linux 或 WSL 后声称 Windows 已安装。解析启动用户的实际主目录。已有技能管理器时沿用其受支持安装入口；否则优先使用可用的 `skill-installer`，或将完整技能目录安装到该用户的 `.agents/skills`。先检查同名技能，保留已有修改，不把整个仓库安装成技能。目录发现方式见 [Codex 官方说明](https://learn.chatgpt.com/docs/build-skills)。

2. **取得两个技能。** 从本发布页下载 `lab-report-slides` 压缩包，核对页面给出的 SHA-256 后解压；从同仓库的 [已验证版本](https://github.com/SanAntonio021/agents-skills/tree/5e5c988a6e02c91d1ceb6fb4f9647694af67fa80/libreoffice-runner) 取得完整 `libreoffice-runner` 目录，包含其整个 `scripts` 子目录。可下载该固定提交的仓库归档到临时目录，再只取需要的目录。两个技能保持同级；若使用管理器导致实际路径不同，按下文配置 `LAB_REPORT_LO_RUNNER`。不要求用户手工下载依赖技能。

3. **补齐软件和 Python 库。** 先发现并复用已有的 Python、LibreOffice 和 `pdftoppm`。Python 需 3.10+；缺失时可选 Python 3.13 的稳定补丁版本。优先使用本机已有的软件包管理器，先查询并核对软件名称、发布者及安装来源，再安装缺项；没有包管理器时，从 [Python 官方 Windows 下载页](https://www.python.org/downloads/windows/)、[LibreOffice 官网](https://www.libreoffice.org/download/) 和 [Poppler Windows 构建发布页](https://github.com/oschwartz10612/poppler-windows/releases) 获取与本机架构匹配的安装包。Poppler 链接是社区 Windows 构建。不要安装预发布版本或把包管理器当成额外必装依赖。使用实际选定的同一个 Python 执行下文 `pip install -r requirements.txt`。

4. **配置可持续使用的实际路径。** 定位真实 `python.exe`、`soffice.com`/`soffice.exe` 和 `pdftoppm.exe`，不使用示例中的占位符或作者路径。优先沿用已有 PATH；需要补充时只追加必要的用户级路径，保留原值，并更新当前进程。非默认位置也可使用下文环境变量：同时设置当前进程与用户级值，供以后启动的 Codex 使用；先保存旧值，不覆盖与本任务无关的配置。仅设置本次终端的临时变量不算完成。记录实际使用的 Python 路径，确保后续命令使用装有依赖的同一解释器。PNG/JPG 安装验收不要求 Node.js/sharp。

5. **检查并修复缺项。** 在主技能目录用选定的 Python 运行 `scripts/check_dependencies.py`。对 JSON 中的 `missing` 逐项处理，再运行检查；随后运行下文完整测试。转换通过 `libreoffice-runner` 进行，不直接启动裸 LibreOffice 命令，不关闭用户正在编辑的文件。有未解决错误就报告失败原因，不把文件已下载或预检成功称为安装完成。

6. **验证一次实际使用并交付。** 使用单独临时目录中的合成材料，生成标有“安装测试，非科研结果”的小型 PPT；这是明确允许的纯文字安装样例，可设置 `allow_text_only=true`。沿用 SKILL.md 的 deck JSON 与渲染命令，检查 PPTX、PDF、PNG、HTML 和 manifest，查看逐页预览并确认原生文字可编辑。不读取私人会话或实验资料。确认 Codex 可以发现 `lab-report-slides`；未发现时核对安装位置，确需重启时提示用户完成后复查。最终报告技能位置、依赖检查、测试、样例文件和首条使用命令。PowerPoint 原生打开与导出若未做，单列为未验证，不影响如实报告已通过的 LibreOffice 渲染结果。

完成后，使用者可以说：“生成今日汇报，先列出可汇报的科研进展让我选择。”

## 下载与校验

附件：`lab-report-slides-windows-v1.1.1.zip`，包含主技能及完整安装说明；配套转换技能由 Codex 按上述流程取得。

SHA-256：`c62a4e1634266ef965358f7f32ea45750cde5523ab8885af7ab5d29222793d74`。
