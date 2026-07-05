# Markdown → LaTeX 映射规则

pandoc 能做结构转换，但论文投稿级别的 tex 需要在它的输出上逐类修正。没有 pandoc 时直接按本表手工转。

## 结构映射

| Markdown | LaTeX（IEEEtran） | 注意 |
|---|---|---|
| `# 标题` | 论文题目进 `\title{}`，不是 `\section` | md 首个 H1 通常是题目 |
| `## 一级节` | `\section{}` | IEEE 节名用 Title Case 或全大写按模板样例 |
| `### 二级节` | `\subsection{}` | |
| `**粗体**` | 视语义定：术语首次定义用正体+缩写 `(THz)`，强调慎用 `\emph{}` | 论文里大部分 md 粗体应该删格式保留文字 |
| `- 列表` | `\begin{itemize}` | IEEE 正文少用列表，考虑改成行文 |
| 脚注 `[^1]` | `\footnote{}` | |
| 超链接 | 正文引用改 `\cite`；纯 URL 用 `\url{}` 且尽量移入参考文献 | |

## 公式

| Markdown | LaTeX | 注意 |
|---|---|---|
| `$...$` 行内 | 保持 `$...$` | |
| `$$...$$` 独立 | `\begin{equation}\label{eq:xxx}...\end{equation}` | 全部编号加 label；确实不需编号才用 `equation*` |
| 多行推导 | `align` 环境 | 对齐符 `&` 放关系符前 |
| 正体单位/缩写混进斜体 | `\mathrm{}` 或 siunitx | SNR、BER 这类缩写在数学环境里用 `\mathrm{SNR}` |

## 图

```latex
\begin{figure}[!t]
\centering
\includegraphics[width=\columnwidth]{figures/fig-setup.pdf}
\caption{Experimental setup of the 300-GHz link.}
\label{fig:setup}
\end{figure}
```

- 单栏 `\columnwidth`，通栏用 `figure*` + `\textwidth`。
- 图源优先 PDF/EPS 矢量；位图最低 600 dpi（曲线图）/ 300 dpi（照片），与 paper-figure-fix 的导出约定一致。
- md 的 `![caption](path)` 里 caption 往往过短，转换时对照正文补成完整图注（这一步如涉及内容措辞，列清单转 sci-paper-edit）。

## 表

- md 管道表转 booktabs 风格：`\toprule/\midrule/\bottomrule`，不用竖线。
- IEEE 表标题在表上方：`\caption` 放 `\begin{table}` 之后、tabular 之前。
- 过宽的表用 `table*` 通栏或 `\resizebox` 兜底，先试调列内容。

## 常见残留清单（转换后必查）

逐项 grep 检查，这些是 pandoc 和手工转换都容易漏的：

| 残留 | 修正 |
|---|---|
| `×` `·` | `\times` `\cdot`（数学环境内） |
| `–` `—` | `--`（数字范围）`---`（破折号） |
| `℃` `°` | `\SI{25}{\celsius}`、`\ang{45}` 或 `$^\circ$` |
| `μ` `π` 等裸希腊字母 | `$\mu$`、`$\pi$`，注意 µ(U+00B5) 和 μ(U+03BC) 两种编码都要查 |
| 中文标点 `，。（）：、"”` | 全文不应残留任何全角字符，`rg "[^\x00-\x7F]"` 扫一遍 |
| `%` `&` `_` `#` 未转义 | `\%` `\&` `\_` `\#`（正文中） |
| `"straight quotes"` | `` `` ... '' `` |
| 裸编号引用 `[12]` | `\cite{key}` |
| `Fig. 3` 手写编号 | `Fig.~\ref{fig:xxx}`；注意 `~` 防断行 |
| md 代码块 | 论文一般不保留；确需算法用 `algorithmic` 环境 |
