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
| 图不显示/位置乱跳 | 浮动体参数或拥堵 | 见下节"浮动体落页核对与治理" |

## 浮动体落页核对与治理

用户抱怨"图离引用太远""图跑到参考文献后面"时按本节处理（2026-07-07 由 115 GHz 论文实战沉淀，即：从一次真实排版返工里总结出来的做法）。

两条硬规则：

1. 图表实体所在页 ≥ 首次引用所在页（同页最好，晚一页可接受，早于引用是违例）。
2. 任何图表不得出现在参考文献之后。

### 第一步：先核对，不要凭感觉调

编译后用 pymupdf 扫 PDF，逐个图表对比"首次引用页 vs 实体页"，一次看全，不要在源码里逐个猜：

```python
import fitz, re
doc = fitz.open('main.pdf')
caps, refs = {}, {}
for i in range(len(doc)):
    t = doc[i].get_text()
    for m in re.finditer(r'Fig\.\s*(\d)\.', t):          # 图题（IEEEtran 格式）
        caps.setdefault('Fig ' + m.group(1), i + 1)
    for m in re.finditer(r'TABLE\s+(X?[IV]+)\n', t):     # 表题
        caps.setdefault('Tab ' + m.group(1), i + 1)
    for m in re.finditer(r'图\s*(\d)', t):               # 正文引用（中文稿；英文稿匹配 Fig.~\d）
        refs.setdefault('Fig ' + m.group(1), i + 1)
    for m in re.finditer(r'表\s*(X?[IV]+)\b', t):
        refs.setdefault('Tab ' + m.group(1), i + 1)
for k in sorted(set(caps) | set(refs)):
    print(f'{k}: 引用页 {refs.get(k, "-")}  实体页 {caps.get(k, "-")}')
```

### 第二步：三层治理，按顺序用

1. **统一放置选项 + 放宽浮动参数**。全部浮动体统一 `[!t]`（单栏高图可 `[!tbp]`），preamble 放宽默认限制：

   ```latex
   \setcounter{topnumber}{4}
   \setcounter{dbltopnumber}{3}
   \renewcommand{\topfraction}{0.95}
   \renewcommand{\dbltopfraction}{0.95}
   \renewcommand{\textfraction}{0.05}
   \renewcommand{\floatpagefraction}{0.75}
   \renewcommand{\dblfloatpagefraction}{0.75}
   ```

2. **浮动体源码前置占位**。浮动体源码块不占正文空间，把它前移到更早的正文流位置（甚至上一小节内），它就能上浮到更早的页顶；正文文字分页不受影响，`\ref` 编号也不变（同类浮动体保持源码先后顺序即可）。前置的源码块加注释注明"仅为排版占位，逻辑位置属 X 节"，防止后人困惑。反向操作同理：表格抢在首次引用之前的页出现时，把源码块移回首次引用之后。

3. **参考文献前保底**。`\bibliographystyle` 之前加 `\clearpage`，强制清空浮动队列，杜绝图表被甩到参考文献之后。代价是文献从新页开始，草稿阶段可接受。

### 判断极限，别硬调

浮动体总数接近正文页数时（例如 12 个浮动体挤 11 页），拥堵是物理空间不足：跨栏大图每页页顶只放得下一个，同类浮动体又必须按编号顺序出现，参数放宽也无济于事。此时接受"晚 1–2 页"，把重排留给改版/翻译后的下一轮；对审稿草稿如此解释即可，不要为中间版本反复精调。

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
