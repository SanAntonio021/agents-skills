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

按 [内容同步与排版保留](../SKILL.md#5-内容同步与排版保留)选择编译时机。正式编译若仍提示交叉引用需重跑，继续有界重跑至引用稳定；根据最终日志和文件判断结果。

## 常见报错对照

| 报错 | 常见原因 | 处理 |
|---|---|---|
| `Undefined control sequence` | 残留 md 语法或缺宏包 | 看报错行；siunitx/booktabs/graphicx 是否已 `\usepackage` |
| `Missing $ inserted` | 正文里裸 `_` `^` 或希腊字母没进数学环境 | 按残留清单 grep |
| `! LaTeX Error: File 'xxx.sty' not found` | 本机 TeX 发行版缺包 | MiKTeX 允许自动装；TeX Live 用 `tlmgr install` |
| `Citation 'xxx' undefined` | bib key 拼错或没跑 bibtex | 核对 refs.bib；完整跑一遍编译链 |
| `Multiply defined labels` | 复制粘贴节/图后 label 重复 | label 全文唯一，前缀区分 `sec:/fig:/tab:/eq:` |
| Overfull \hbox | 长 URL、长公式、大表 | 定位并查看渲染；优先合法断行、列宽和单双栏调整，不随意缩写专业名称或缩字号。超过 10 pt 逐条处理，小于该值也不能据此断言没有重叠或截断 |
| 图不显示/位置乱跳 | 浮动体参数或拥堵 | 见下节"浮动体落页核对与治理" |

## 浮动体落页核对与治理

默认将图表安排在首次引用和相关解释附近，并保持合理的阅读顺序。具体位置遵循目标模板；调整时结合图表尺寸、单双栏布局和浮动体顺序，编译后检查实际落页、正文衔接及页面留白。

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

### 第二步：按问题选择调整方法

以下是可选手段，不要求依次全部执行。每次调整后检查实际页面效果。

1. **调整放置选项和浮动参数**。依据模板和图表类型选择 `[!t]`、`[!tbp]` 等选项。需要放宽限制时可参考下例，参数按实际页面调整：

   ```latex
   \setcounter{topnumber}{4}
   \setcounter{dbltopnumber}{3}
   \renewcommand{\topfraction}{0.95}
   \renewcommand{\dbltopfraction}{0.95}
   \renewcommand{\textfraction}{0.05}
   \renewcommand{\floatpagefraction}{0.75}
   \renewcommand{\dblfloatpagefraction}{0.75}
   ```

2. **调整浮动体入队位置**。双栏浮动体可能被延后排出；可在保持同类图表顺序及标签的前提下，将源码块适当前移，让它更早进入队列，必要时注明逻辑所属章节。移动可能改变正文分页、其他浮动体位置和交叉引用，须重新编译核对，不能承诺正文不受影响。若图表提前后脱离解释，则调回更合适位置。

3. **必要时排空队列**。在相关章节末使用合适的浮动屏障或 `\clearpage`；参考文献前排空仅是兜底。先检查是否产生大块空白、图表独占页或无谓增页，不能为位置接近而破坏整体排版。

### 判断极限，别硬调

浮动队列能否排下取决于图表实际高度、单双栏类型、可用位置、顺序和相邻正文，不能仅凭图表数量接近页数就断言空间不足。确有版面限制时，比较适当延后、调整图表尺寸或单双栏、增加页面等方案；保留可读性和相关解释，不硬塞到指定页，也不为尚未定稿的中间版本反复精调。

## 首页与交付核验

- 用户质疑作者单位或标题区留白时，先核对当前 PDF、文档类选项和相关宏。IEEEtran 的普通期刊与会议模式不同，不能把会议式作者单位排列直接套入期刊；对特殊期刊按其官方模板核实。
- 区分模板默认间距和额外插入的空行、`\vspace` 或标题补丁。没有格式要求或异常依据时保留模板默认，不为“更紧凑”任意塞入负间距，也不把其他稿件的毫米数当标准。
- 最终交付同时检查源码差异与 PDF 渲染。局部调整可比较发生变化的页面并核实其他页未变；正文改动引起重排时检查全部受影响页面。日志无错误不等于无视觉问题，文字提取也不能替代看图表。
- 有已确认的术语修改时，按修改清单回读生成 PDF，核对新词并扫描旧词及连字符变体；图片内文字无法提取时目视检查。
- 用户指定正式 PDF 路径时，核实该路径仍为当前交付目标，并回读该文件。若它由另一编译输出复制生成，更新后核对两者 SHA-256；仅检查临时 main.pdf 不能证明指定正式文件已更新。
- 交付时说明本次实际更新的文件及尚未完成的相关环节；只处理源稿时说明 PDF 是否待更新。投稿压缩包和系统上传件仅在本次授权涉及它们时处理、核对。
- PDF 被占用时不关闭用户应用或强改权限；在可用临时构建目录完成编译后，以新的明确文件名交付，并更新现用入口。说明旧文件未更新，避免用户反复打开旧版。必要编辑源及构建依赖保持在正式工程内。

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
