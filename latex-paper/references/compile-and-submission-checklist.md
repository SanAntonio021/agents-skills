# 编译排错与投稿打包清单

## 编译链

Windows 本机优先 `latexmk -pdf main.tex`（TeX Live / MiKTeX 均自带）。没有 latexmk：

```
pdflatex main.tex
bibtex main
pdflatex main.tex
pdflatex main.tex
```

正文只有英文时用 pdflatex；需要中文致谢或中文图注（罕见）才换 xelatex，并注意 IEEEtran 与 xelatex 的字体兼容。

## 常见报错对照

| 报错 | 常见原因 | 处理 |
|---|---|---|
| `Undefined control sequence` | 残留 md 语法或缺宏包 | 看报错行；siunitx/booktabs/graphicx 是否已 `\usepackage` |
| `Missing $ inserted` | 正文里裸 `_` `^` 或希腊字母没进数学环境 | 按残留清单 grep |
| `! LaTeX Error: File 'xxx.sty' not found` | 本机 TeX 发行版缺包 | MiKTeX 允许自动装；TeX Live 用 `tlmgr install` |
| `Citation 'xxx' undefined` | bib key 拼错或没跑 bibtex | 核对 refs.bib；完整跑一遍编译链 |
| `Multiply defined labels` | 复制粘贴节/图后 label 重复 | label 全文唯一，前缀区分 `sec:/fig:/tab:/eq:` |
| Overfull \hbox | 长 URL、长公式、大表 | >10 pt 逐条处理：断行、缩写、resizebox |
| 图不显示/位置乱跳 | 浮动体参数 | 用 `[!t]`，接受 LaTeX 的浮动决策，不追求"图在提到它的段落旁边" |

## 投稿前自查

- [ ] 零 error；undefined/multiply defined/citation 警告清零
- [ ] 每个 figure/table/equation 都在正文被 `\ref` 引用过
- [ ] 参考文献无重复条目、无预印本冒充正式版（存疑的转 `paper-download` 核对）
- [ ] 页数符合期刊限制（超页费页数也确认）
- [ ] 双盲期刊删作者信息与致谢；普通期刊核对 ORCID 和资助号
- [ ] PDF 字体全部内嵌（Acrobat 属性或 `pdffonts` 检查，IEEE PDF eXpress 会卡这个）

## 打包

各刊要求不同，以投稿系统页面为准，通用结构：

```
submission.zip
├── main.tex            # 去掉大段注释和被注释掉的旧稿
├── refs.bib 或 main.bbl # 有的系统要 bbl 不要 bib，看要求
├── cls/bst             # 非标准模板文件随包
└── figures/            # 与 tex 引用文件名一一对应，无多余文件
```

- Overleaf 协作时直接把整个工程 zip 上传新建项目即可，模板 cls 已随工程。
- 投稿版和自留版分开打包；自留版保留注释和被删段落。
