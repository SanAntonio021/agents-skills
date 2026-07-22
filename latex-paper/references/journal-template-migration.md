# 已投稿稿件的期刊模板迁移

本清单适用于：论文已有提交源包、已确认版本或冻结工作副本，现在需要换用另一家期刊模板。目标是完成投稿工程转换，不改变科学内容。

## 1. 冻结科学内容基线

1. 明确唯一基线来源：已提交的 source 压缩包或用户明确指定的提交快照。不要默认把后来工作区里的 `main.tex` 当成基线。
2. 记录源包以及关键 `main.tex`、参考文献和图件目录的 SHA256；保留原始工程，不在原目录上套新模板。
3. 将标题、作者顺序、摘要、关键词、正文、公式、表格、图注、结论和固定技术口径列为默认锁定项。模板迁移发现的科学或措辞问题只列出，转交内容编辑流程。

## 2. 建立目标期刊副本

- 在独立目录中复制基线，例如 `paper-<venue>-en/`；目标期刊的 `cls`、`bst`、宏、前置命令、致谢位置和编译脚本只放在该目录。
- 先核对目标期刊官方模板版本和作者指南，再决定版式适配；不要把目标模板文件反向复制到基线工程。
- 修改范围按“模板必需适配”和“用户明确授权的投稿元数据”分开记录。任何超出范围的正文变化先停下报告。

## 3. 保留原图并建立目标图件版本

- 从基线复制的 `figures/` 视为只读，不覆盖或删除其中的图。
- 目标期刊图件放在独立目录，如 `figures-<venue>/`；裁剪、拼版或高分辨率替换的源文件放在 `figure-sources-<venue>/`。
- 每个变体使用新文件名和版本号，并在 manifest 中记录：源文件、版式/目标宽度、是否重绘数据、SHA256 和目标用途。
- 图件版式可以适配单栏/双栏或目标模板的正文宽度，但不能借版式变化改变数据、图注口径或技术含义。

## 4. 隔离编译和输出

- 默认执行 `pdflatex → bibtex → pdflatex → pdflatex`（或等价的 `latexmk`），并对最终日志做错误和未解析引用检查。
- 如果 `main.pdf` 或辅助文件被 PDF 阅读器、同步程序或其他进程占用，不关闭相关进程，也不覆盖用户可能正在查看的 PDF。改用本机临时目录作为 `-output-directory`，并使用唯一、版本化的 `-jobname`。
- BibTeX 在临时目录运行时，将源码目录加入 `BIBINPUTS` 和 `BSTINPUTS`，同时保留原搜索路径，使 `.bib`、`.bst` 和系统样式都能被找到。随后执行两次同参数的 pdfLaTeX。
- 编译成功后先确认目标同级文件名不存在，再把临时 PDF 复制回源码目录；最终文件名应可追溯，例如 `main_<venue>_submission_final_v02.pdf`。旧版即使作废也保留，明确标注“仅本地审计，不上传”，不得静默覆盖。

Windows/MiKTeX 示例（从源码目录运行）：

```powershell
$sourceDir = (Resolve-Path -LiteralPath '.').Path
$buildDir = Join-Path $env:TEMP ('latex-build-' + [guid]::NewGuid())
$jobName = 'main_venue_submission_final_v02'
$destination = Join-Path $sourceDir ($jobName + '.pdf')
New-Item -ItemType Directory -Path $buildDir | Out-Null

pdflatex -interaction=nonstopmode -halt-on-error "-output-directory=$buildDir" "-jobname=$jobName" .\main.tex

$oldBibInputs = $env:BIBINPUTS
$oldBstInputs = $env:BSTINPUTS
try {
    $env:BIBINPUTS = $sourceDir + ';' + $oldBibInputs
    $env:BSTINPUTS = $sourceDir + ';' + $oldBstInputs
    Push-Location -LiteralPath $buildDir
    try {
        bibtex $jobName
    } finally {
        Pop-Location
    }
} finally {
    $env:BIBINPUTS = $oldBibInputs
    $env:BSTINPUTS = $oldBstInputs
}

pdflatex -interaction=nonstopmode -halt-on-error "-output-directory=$buildDir" "-jobname=$jobName" .\main.tex
pdflatex -interaction=nonstopmode -halt-on-error "-output-directory=$buildDir" "-jobname=$jobName" .\main.tex

if (Test-Path -LiteralPath $destination) {
    throw "Refusing to overwrite existing PDF: $destination"
}
Copy-Item -LiteralPath (Join-Path $buildDir ($jobName + '.pdf')) -Destination $destination
```

## 5. 元数据修改的证据链

1. 修改前保存源码快照或哈希，修改后检查 diff；元数据任务的 diff 应只包含已授权字段。
2. 摘要需要逐字核对时，把 LaTeX 公式、范围符号和转义字符还原为投稿字段纯文本，再按约定规则计词；不要只依赖 PDF 的断行文本。
3. 标题、作者、通讯作者标记、单位、关键词和摘要分别核对，不能用“编译成功”替代字段验收。

## 6. 最终验收

- PDF 页数符合当前作者指南；若不同官方来源存在冲突，报告各来源和提交日复核要求，不擅自取最宽口径。
- 日志无 LaTeX error、未解析 citation/reference、缺失图件或重复 label；非致命版式警告逐项记录。
- 渲染首页、摘要页和所有关键图所在页，检查裁切、重叠、空白图、字体可读性和页码。
- 用 `pdfinfo`/等价工具确认页数、页面尺寸、加密状态，并记录最终 PDF SHA256。
- 报告实际改动文件、验证命令、警告和仍需用户判断的内容；不登录投稿系统、不上传、不点击 Submit，除非用户另行授权。
