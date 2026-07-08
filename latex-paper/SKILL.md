---
name: latex-paper
description: 把已有 Markdown 或 Word 论文稿转成可投稿的 IEEE LaTeX 工程，并负责 LaTeX 工程层的全部事务：模板选择与套用（IEEEtran、期刊 cls）、md 转 tex 结构映射、公式/图/表环境、BibTeX 参考文献、交叉引用、浮动体落页治理、编译排错、投稿打包。Use when 用户说"转 LaTeX""md 转 tex""IEEEtran""套期刊模板""LaTeX 编译报错""Overleaf""BibTeX""引用编号""交叉引用坏了"，或抱怨"图离引用太远""图表位置乱跳""图跑到参考文献后面"这类浮动体落页问题，或要把现有论文稿变成投稿版 LaTeX。只管格式与工程：内容润色找 ieee-manuscript-edit，英文句子质量找 sentence-polish，图件本身找 paper-figure-review，Word 版式找 word-template。
---

# Markdown 转 LaTeX 投稿工程

## 定位

这份 skill 管"从现有稿子到能编译、能投稿的 LaTeX 工程"这一段，不动科学内容。转换中发现内容层面的疑问（术语不一致、引用缺失、结论表述问题），列成清单交给用户或转给对应技能，不要自行改写。

## 工作流

### 1. 确认目标模板

先问清或确认目标期刊。IEEE 常用模板本仓已有缓存，优先直接用，不要重新下载：

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

- md 里的引用逐条落进 `refs.bib`；有 DOI 的用 DOI 反查 BibTeX 并核对字段，没有 DOI 的按 `paper_index.md`（paper-download 维护）或原文核对。
- BibTeX 条目统一小写 key 约定 `firstauthor-year-keyword`，页码、卷期、月份补全；IEEE 风格由 `IEEEtran.bst` 负责，不要手工排引用格式。
- 引用元数据可疑（预印本当正式版、会议/期刊混淆）时标注出来，需要正式版 PDF 证据时转 `paper-download`。

### 5. 编译验证

- 默认 `latexmk -pdf main.tex`；没有 latexmk 用 pdflatex → bibtex → pdflatex ×2。
- 通过标准：零 error；warning 里 undefined references、multiply defined labels、citation undefined 必须清零；overfull hbox 超过 10 pt 的逐条处理。
- 常见报错对照和处理见 [references/compile-and-submission-checklist.md](references/compile-and-submission-checklist.md)。

### 6. 投稿打包

按目标期刊投稿要求执行 [references/compile-and-submission-checklist.md](references/compile-and-submission-checklist.md) 的打包清单：去注释、图源文件与 PDF 对应、字体内嵌检查、单 zip 结构。

## 边界

- 内容精修（术语、图注文字、结论强度、中改英）：[../ieee-manuscript-edit/SKILL.md](../ieee-manuscript-edit/SKILL.md)
- 纯英文句子质量：[../sentence-polish/SKILL.md](../sentence-polish/SKILL.md)
- 图件绘制与 IEEE 图规范：[../paper-figure-review/SKILL.md](../paper-figure-review/SKILL.md)
- Word 版式交付：[../word-template/SKILL.md](../word-template/SKILL.md)
- 论文 PDF 获取与索引：[../paper-download/SKILL.md](../paper-download/SKILL.md)
- 一个请求同时涉及转换和内容修改时，先完成转换得到可编译工程，再把内容问题清单转给 ieee-manuscript-edit，不要边转边改内容。
