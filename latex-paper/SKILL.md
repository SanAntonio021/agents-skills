---
name: latex-paper
description: 把已有 Markdown 或 Word 论文稿转成可投稿的 LaTeX 工程，负责模板、公式图表、BibTeX 接入、交叉引用、浮动体、编译排错及按投稿要求打包。Use when 用户说“转 LaTeX”“md 转 tex”“IEEEtran”“套期刊模板”“迁移投稿模板”“LaTeX 编译报错”“Overleaf”“BibTeX”“引用编号”“交叉引用坏了”或要求调整图表位置。文字修改结合 `ieee-manuscript-edit`，文献核实交给 `paper-search`，投稿事务交给 `journal-submission`，图件交给 `paper-figure-review`，Word 版式交给 `docx`。
---

# Markdown 转 LaTeX 投稿工程

## 本地文稿版本保护

实际写入本地 `.md` 或 `.tex` 前，读取并执行 [../writing-router/references/document-version-protection.md](../writing-router/references/document-version-protection.md)，核对当前文件、项目目录和已有改动。已有 Git 按项目约定使用；Git 不适用时通过新副本或已有备份继续，不默认提交或增加 baseline、WIP 确认。只读排错和方案说明保持只读。

如果输入是已经投稿、已经打包或明确冻结的稿件，先读取并执行
[references/journal-template-migration.md](references/journal-template-migration.md)。保留原始提交版本，在独立目标工程中适配模板、制作图件版本并实施已授权的文字修改；新发现的科学内容疑问单独讨论。

## 定位

这份 skill 管"从现有稿子到能编译、能投稿的 LaTeX 工程"这一段。纯转换保留科学内容；用户同时授权改文时，结合 `ieee-manuscript-edit` 一并完成，复用已确认的修改要求。新出现且无法自行查明的科学含义歧义单独讨论，只暂停依赖该问题的修改。

它只在当前期刊指南或当前投稿页面明确要求时生成并验证 source 包。页面只要求 PDF 或 Word 时，不额外生成 ZIP。投稿系统的文件类型、表单和提交事务交给 `journal-submission`。

## 工作流

### 1. 确认目标模板

先读取当前任务、已有工程和项目约定，复用已确定的目标期刊与模板；仅影响模板选择的信息缺失、冲突且无法自行查明时询问。以该期刊当前官方模板为准。明确 IEEE 时，优先使用本仓已有缓存：

- IEEE Transactions / Letters（IEEEtran.cls + bare_jrnl 样例）：`../ieee-manuscript-edit/assets/ieee-official-templates/transactions-journals-letters/latex-extracted/`
- IEEE Access：`../ieee-manuscript-edit/assets/ieee-official-templates/ieee-access/latex-extracted/`
- IEEE Journal of Microwaves（IEEEjmw.cls）：`../ieee-manuscript-edit/assets/ieee-official-templates/ieee-journal-of-microwaves/latex-extracted/`

缓存里没有的期刊，先到期刊官方作者页取最新模板，核对 cls 版本和年份，再开工。运行时找不到缓存路径时（同步目录下相对路径可能不同），退回官方下载。

### 2. 搭工程骨架

在论文工作目录新建独立 LaTeX 工程，不要混在 md 草稿目录里：

```
paper-tex/
├── main.tex          # 主文件，从模板样例改
├── refs.bib
├── figures/          # 复制或链接 paper-figure-review 的成品图
├── IEEEtran.cls      # 模板文件随工程走，保证可移植（Overleaf 直接可用）
└── IEEEtran.bst
```

sections/ 拆分只在稿子超长或多人协作时用；单人单稿默认单文件，减少交叉引用维护成本。

### 3. md 转 tex

有 pandoc 时先 `pandoc draft.md -o body.tex --top-level-division=section` 得到底稿，再按 [references/md-to-latex-conversion.md](references/md-to-latex-conversion.md) 的映射表逐类修正；没有 pandoc 就直接按映射表手工转。无论哪种方式，转换后必须过一遍该文件末尾的"常见残留清单"——pandoc 处理不了的 Unicode 符号、中文标点、图表环境细节是返工的主要来源。

转换原则：

- 章节、公式、图、表全部加 `\label`，从一开始就用 `\ref`/`\eqref`/`\cite`，不留裸编号。
- 数值和单位统一用 siunitx（`\SI{300}{\GHz}`、`\SI{20}{Gbit/s}`）；模板与 siunitx 冲突时退回 `$300\,\mathrm{GHz}$` 风格并全文统一。
- 图先用 paper-figure-review 的可投稿版本；没有成品图时插占位并记入待办，不阻塞正文转换。

### 4. 参考文献

- 将稿件引用和已核实的文献条目接入 `refs.bib`；缺失或可疑的元数据、DOI 及版本核实交给 `paper-search`，复用其结果。
- 保留已有 BibTeX key，新增条目沿用工程约定；无约定时使用 `firstauthor-year-keyword`。引用样式遵循目标模板，IEEEtran 工程使用 `IEEEtran.bst`。
- 检查正文引用与条目对应、样式及编译结果；需要取得原文时由 `paper-search` 协调 `paper-download`。

### 5. 双源同步校验

当 Markdown 阅读稿与 LaTeX 投稿工程并存时，复用当前任务或有效项目约定已确定的主稿和同步方向，并读取当前文件。文件时间戳或编译成功不足以决定主稿；实际内容冲突且主稿关系无法查明时才询问。将 PDF 称为 final 前，按已确认修改清单逐项进行语义核对，至少覆盖术语、数值、图表标题、论断和结论。

- 已确认修改造成的差异，按声明的权威关系同步源稿或派生稿后，再执行编译。
- 差异涉及尚未解决的科学含义歧义时，只暂停相关同步并讨论，继续独立的工程工作；已授权的文字修改结合 `ieee-manuscript-edit` 完成。
- 编译通过只说明 LaTeX 工程可生成 PDF，不能证明双源已经同步。例如，Markdown 写作 `digital signal processing (DSP)`，而 `main.tex` 仍写作 `DSP`；两份文件都可通过编译，但该 PDF 不能称为已同步的最终版本。

### 6. 编译验证

- 默认 `latexmk -pdf main.tex`；没有 latexmk 用 pdflatex → bibtex → pdflatex ×2。
- 通过标准：零 error；warning 里 undefined references、multiply defined labels、citation undefined 必须清零；overfull hbox 超过 10 pt 的逐条处理。
- 常见报错对照和处理见 [references/compile-and-submission-checklist.md](references/compile-and-submission-checklist.md)。

### 7. 条件性投稿打包

只有目标期刊指南或当前页面明确要求 source 包时，才执行 [references/compile-and-submission-checklist.md](references/compile-and-submission-checklist.md) 的打包清单。页面只收 PDF 或 Word 时，本步骤记录为 `not_required`，不生成 ZIP。

## 边界

- 内容精修（术语、图注文字、结论强度、中改英）：[../ieee-manuscript-edit/SKILL.md](../ieee-manuscript-edit/SKILL.md)
- 图件绘制与 IEEE 图规范：[../paper-figure-review/SKILL.md](../paper-figure-review/SKILL.md)
- Word 版式交付：[../docx/SKILL.md](../docx/SKILL.md)
- 论文 PDF 获取与索引：[../paper-download/SKILL.md](../paper-download/SKILL.md)
- 文献检索与元数据核实：[../paper-search/SKILL.md](../paper-search/SKILL.md)
- 投稿页面、文件类型和生命周期记录：[../journal-submission/SKILL.md](../journal-submission/SKILL.md)
