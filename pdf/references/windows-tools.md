# Windows 工具与 Office 桥接兼容

## PDF 工具定位

本机 Poppler 程序位于 `%USERPROFILE%\poppler\poppler-24.08.0\Library\bin`，包括 `pdftoppm.exe`、`pdftocairo.exe`、`pdftotext.exe` 和 `pdfinfo.exe`。

调用 Poppler 时使用带 `.exe` 的程序名，或使用解析出的绝对路径。不要调用无扩展名的 `pdftoppm` 或 `pdfinfo`：Codex 运行时可能把它们解析为指向缺失 bundled `Library\bin` 的包装脚本，即使真正的 Poppler 已安装也会报路径错误。

PowerShell 解析和自检示例：

```powershell
$popplerBin = Join-Path $env:USERPROFILE 'poppler\poppler-24.08.0\Library\bin'
$pdftoppm = Join-Path $popplerBin 'pdftoppm.exe'
$pdftotext = Join-Path $popplerBin 'pdftotext.exe'
$pdfinfo = Join-Path $popplerBin 'pdfinfo.exe'

if (-not (Test-Path -LiteralPath $pdftoppm)) {
    $pdftoppm = (Get-Command pdftoppm.exe -ErrorAction Stop).Source
}
if (-not (Test-Path -LiteralPath $pdftotext)) {
    $pdftotext = (Get-Command pdftotext.exe -ErrorAction Stop).Source
}
if (-not (Test-Path -LiteralPath $pdfinfo)) {
    $pdfinfo = (Get-Command pdfinfo.exe -ErrorAction Stop).Source
}

& $pdftoppm -v
& $pdftotext -v
& $pdfinfo -v
```

`pdftoppm.exe` is the default rasterizer for page previews; use `pdftocairo.exe` when its output format or antialiasing is preferable. `pdftotext.exe` and `pdfinfo.exe` are the corresponding text and metadata utilities.


## Office source route

Word、PPT 和 Excel 源文件由对应格式技能负责读取、修改和转换。下面仅保留旧调用方需要的 PDF 本地桥接接口；已有调用仍可使用，但普通 Office 任务不因此改由 PDF 入口承担：

```powershell
python <skill-root>\scripts\officecli_bridge.py view source.pptx text
python <skill-root>\scripts\officecli_bridge.py validate source.pptx
```

桥接器固定使用 OfficeCLI `1.0.149`，每次调用都会先核对文件存在、SHA-256 和报告版本。普通
PDF/Office 文档任务不会联网下载或自动修复；当前授权覆盖修复或升级时可运行
`python <skill-root>\scripts\repair_officecli.py --repair` 修复默认本机路径。设置
`OFFICECLI_EXE` 时也必须通过相同校验，路径错误应自行修正或取消环境变量；修复脚本不会改写
覆盖路径。

桥接器会隔离输入副本并核对源文件 SHA-256。不要通过 OfficeCLI 导出 Office-to-PDF：
当前本机 OfficeCLI `1.0.149` 未安装 exporter plugin（2026-09-13 核对），bridge 会提前拒绝 `view ... pdf`。OfficeCLI
`--render native --allow-native` 只保留为诊断，失败会输出
`officecli_native_diagnostic_failed`、原始 stderr 和退出码；它不证明 Office 未安装，也不
提供发布证据。需要 Microsoft Office 原生打开/导出验证时，可沿用同构的
`office_native_gate.py`；桥接器不会关闭 Office。纯 PDF 仍按 Poppler、PyMuPDF、pypdf
和 OCR 路径处理，不把 OfficeCLI 当作 PDF 编辑器或保真渲染器。

## Acceptance layers

Office 源文件和纯 PDF 分开记录验收层：

- `STATIC_PASS`: OfficeCLI/OOXML 或 PDF 结构、文本、哈希和机器检查通过。
- `LO_RENDER_PASS`: Office 源文件通过 `libreoffice-runner` 的兼容转换/渲染；不能据此宣称 Microsoft Office 原生验证通过。
- `NATIVE_OPEN_PASS`: 按目标应用及对应格式技能确定是否需要原生检查，独立 gate 打开隔离副本。
- `NATIVE_RENDER_PASS`: PPTX/DOCX gate 的原生导出和页面栅格化通过；纯 PDF 不使用此层。

OfficeCLI `validate` 通过不等于 PowerPoint、Word 或 Excel 原生可打开。需要原生证据时，按
输入格式调用同构 gate，例如：

```powershell
python <skill-root>\scripts\office_native_gate.py check source.pptx `
  --format pptx --json --allow-office-com --require-render
python <skill-root>\scripts\office_native_gate.py check source.docx `
  --format docx --json --allow-office-com --require-render
python <skill-root>\scripts\office_native_gate.py check source.xlsx `
  --format xlsx --json --allow-office-com
```

gate 返回 `PASS`、`FAIL_OPEN`、`FAIL_RENDER`、`APP_UNAVAILABLE`、`UNVERIFIED` 或
`UNSAFE_PROCESS`，并保留真实阶段和异常。纯 PDF 的验收链不因 OfficeCLI native 状态改变；
转换工具由对应格式技能按目标应用确定；使用 LibreOffice 时通过 `libreoffice-runner`。

原生检查须由当前用户请求覆盖，并经本技能的 gate 证明实例属于本任务。已有相关 Office 进程或
归属不明时，不连接、不关闭用户实例，继续文件级或 LibreOffice 路径。原生工具只打开隔离副本，
保护源文件与用户窗口，仅关闭自己打开的文档及本任务的空实例；缺少归属或退出证据时记录未验证。
`--allow-office-com` 只表示本次操作获准，不代替隔离检查，也不要求额外口令或逐页签字。


需要 LibreOffice 时先读取 `libreoffice-runner` 并调用其隔离入口，不直接启动 `soffice`。工具身份校验失败时停用该工具，选择已核实可用的文件级或渲染路径，并如实记录未验证项。
