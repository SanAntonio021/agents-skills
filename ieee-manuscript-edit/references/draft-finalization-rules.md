# 终稿精修与规范化规则

当已有英文 SCI/IEEE 工程论文草稿进入提交前精修、导出前整理或审稿前整理时，按此文件执行。目标是减少规范性返工，同时保护实验事实、科学限定和证据边界。

## 输入与职责边界

- 终稿精修可处理本技能原有的 Markdown、Word 和 LaTeX 文稿。
- “终稿规范化”确定性审计 v1 只处理英文 Markdown 和单文件 LaTeX。
- 多文件 LaTeX、Word/PDF 解析、中文论文和图像语义自动识别不在审计脚本 v1 范围内。
- `paper-review` 负责投稿前审查门；`latex-paper` 负责模板、工程转换和编译；`style-vocab` 负责词级偏好。

## 固定处理顺序

1. 修改前记录输入文件 SHA-256，并确认引用、citation keys、数字、单位、公式和图表编号的基线。
2. 对 `.md` 或单文件 `.tex` 先运行只读审计：

   ```text
   python -X utf8 scripts/audit_manuscript_conventions.py --input <path> --format json
   ```

3. 按 `safe_findings`、`review_candidates`、`protected_qualifiers`、`unresolved` 四类处理。退出码 `1` 仅表示存在发现；退出码 `2` 才是解析错误。
4. 先修引用和数据问题，再统一术语、缩写和图注，最后压缩元话语与重复内容。
5. 所有修改完成后重新运行审计；最终报告的哈希、行号和计数只能来自修改后的文件。

## 缩写作用域

分别计算以下独立作用域：

- Abstract；
- 正文；
- 每一个 figure caption；
- 每一个 table caption。

规则如下：

1. 一个作用域里的定义不能自动供另一个作用域使用。摘要定义过的缩写，正文首次出现仍需重新定义；每个图注和表注也要自足。
2. 摘要内只出现一次的缩写直接保留全称，不引入缩写。
3. “全称 + 缩写”必须形成明确绑定，例如 `bit error rate (BER)`。只在前文出现可能的全称、后文再裸用缩写，列为人工复核。
4. `IQ multiple-input multiple-output (IQ-MIMO)` 这类只展开复合缩写一部分的写法列为人工复核，不能猜缺失部分。
5. 自动补全只允许使用同一稿件中唯一且一致的显式 `full form (ACRONYM)` 映射。存在冲突映射、部分展开或没有显式映射时，只报告，不建立第二套术语库，也不调用外部知识猜全称。
6. 单位、标准组织、文件格式、代际名称、仪器型号和通道编号使用保守白名单。不能确定 `CH1/CH2` 一类标签的真实含义时仍应报告，不擅自展开。

## 图注和表注自解释

每个图注或表注单独核对以下七项：

1. **对象**：图或表展示的系统、变量、指标或比较对象是什么。
2. **条件**：读图所需的链路状态、距离、频率、功率、数据集或实验条件。
3. **面板**：`(a)`、`(b)` 等面板分别表示什么。
4. **图例**：颜色、线型、标记、箭头、框选区域和参考线分别表示什么。
5. **单位**：关键坐标、数值或归一化量的单位是否清楚。
6. **统计元素**：箱体、中位线、whisker、误差条、阴影、样本点和置信区间的定义。
7. **主要读法**：读者应从图中读取的主要关系、趋势或阈值，不在图注里重复整段 Results 论证。

本地图片存在时，查看原图并逐项核对。审计脚本只提示可由文本稳定识别的问题，不替代图像语义判断。缺少绘图源码或统计定义时，把问题列为 `unresolved` 或待作者确认，不能猜 whisker 是极值还是 `1.5 IQR`。

图注应自解释，但不是正文结果段的复制品。正文负责分析、比较和论证；图注只保留独立读图所需的信息。正文与图注为了自解释而重复关键变量或条件，不按有害重复删除。

## 防御性用语与科学限定

以下属于改写候选：

- 无信息量的图件路标，例如只说“Fig. 2 shows the results”；
- `It should be noted that`、`It can be seen that`、`The following discussion focuses on` 等元话语；
- “本文不主张……”“贡献定位于……”这类预防性辩护；
- 能直接改成对象、条件和结果陈述的自我解释句。

改写时保留原句承担的科学内容。优先把元话语改成直接事实句，不因“去防御性”删除论证。

以下内容默认保护：

- 实验假设、适用条件和测试范围；
- 比较基准、公平比较条件和归一化口径；
- 不确定性、误差条、标准差、置信区间和样本量；
- 已知限制、未覆盖场景和证据边界；
- 防止普遍化过度的限定，例如 `under the tested conditions`。

`protected_qualifiers` 是保护证据，不代表应删除。只有底层证据发生变化时才调整这些限定。

## 否定链与间接否定

否定链审计用于发现需要作者判断的反复否定、间接否定和否定配对结构。它固定输出 `LANG_NEGATION_CHAIN`、`check=negative_construction`，只进入 `review_candidates`，不提供 `span` 或 `replacement`。科学限定可能依赖否定表达，因此所有发现均为人工复核候选，不能自动删除、反转或改成正面句式。

审计范围只包括 Abstract、正文和每个图注/表注；标题、表格、参考文献、代码、数学、注释和 verbatim 不参与。句号、问号和感叹号结束句子；没有终止标点的 caption、Markdown 列表项和 LaTeX `\item` 各自作为一个句子单元。同一句只生成一条合并发现。

Markdown 的 ATX/Setext 标题、表格、原始 HTML 的 `table`/`pre`/`code`/`h1`--`h6` 块和围栏/缩进代码均屏蔽；懒续行仍属于同一个列表项。LaTeX 的章节标题（含 `paragraph`/`subparagraph`）、表格环境（含 `sidewaystable`、`longtblr` 等）和 `\verb`、`\lstinline`、`\mintinline` 行内代码不参与审计；未闭合结构进入 `unresolved`。小数点和编号点不作为句子终止符，caption 标签可带面板后缀如 `Fig. 1(a)`。

匹配顺序固定如下，已占用字符不得重复计数：

1. **编号与配对结构**：`No.` 后允许空白并紧跟阿拉伯数字、含字母和数字的编号或大写罗马数字时，`No.` 作为编号屏蔽，例如 `No.3`、`No. A1`、`No. III`。`not only ... but also` 只屏蔽紧邻 `only` 的 `not`，内部或外部的其他否定照常计数。`neither ... nor` 合并为一个 `coordination` 单元，未配对的 `neither` 或 `nor` 各算一个原子单元；配对区间内的其他否定仍需计数。
2. **固定间接否定**：以下各算一个 `fixed_indirect` 单元：`not uncommon/infrequent/infrequently/insignificant/negligible/impossible/unreasonable/unlikely/atypical`；直接相邻的 `not without`；`cannot/can't be excluded/ruled out/ignored/discounted/overlooked`；以及不依赖后接词的 `by no means`。固定短语内部的否定词不再重复计数。
3. **原子否定**：包括 `not/no/never/without`、否定助动词、`unable to`、同一句单元内的 `fail...to`、`lack...`、`absence of`、`insufficient evidence`，以及未参与配对的 `neither/nor`。`fail...to` 只占用两端，不能吞掉中间的其他否定。单独的 `without` 只算一个原子单元，不自行触发报告；只有直接相邻的 `not without` 才是固定间接否定。`not entirely without` 等非直接相邻结构按两个原子单元处理。

存在任一 `fixed_indirect` 单元，或合并后的否定单元不少于两个时才报告。证据必须保留规范化后的完整句子，并按源顺序列出全部命中片段及 `fixed_indirect`、`coordination` 或 `atomic` 分类。单一科学否定自然不报告，例如 `not statistically significant`、`No packet loss was observed`、`cannot confirm` 和单独的 `without`。这些规则不改变独立运行的 `protected_qualifiers`；对于 `cannot be ruled out`、`cannot be excluded` 等科学限定，人工复核时优先判断它们是否准确表达证据边界，而不是追求形式上的正面句式。

## 重复内容

1. 只有同一正文段落内相邻、文本完全相同的句子，才是可确定删除的安全重复。
2. 摘要、引言、结果和结论之间的近重复只报告为候选。它们可能分别承担概括、铺垫、证据和收束功能。
3. 跨章节压缩先判断功能：Introduction 保留完整问题与机制，Results 保留证据和读数，Conclusion 保留最短结论；不要机械删除相同数字。
4. 正文与图注之间为自解释而保留的关键条件、变量和阈值不算安全重复。
5. 同义改写、功能性复述和语义相似句均不自动删除。

## 安全修复与报告

- 只有 `safe_findings` 可以带精确 `span` 和 `replacement`，并可自动采用。
- `review_candidates`、`protected_qualifiers` 和 `unresolved` 不得带自动替换建议。
- 应用安全修复时按文件末尾到开头的顺序处理 span，避免前一项修改使后一项定位漂移。
- 自动修复后必须重跑审计；不要把初次报告的行号或 SHA-256 当作最终证据。
- LaTeX 中的 `\input`、`\include`、自定义 caption 宏、未闭合环境或无法可靠解析的结构进入 `unresolved`，不得报告全文 clean。

## 通用精修规则

1. 保持原有 citation keys，并让引用留在所支撑论点和原小节附近。
2. 弱证据对应克制结论；有限测试只支持已测试条件下的结论。
3. 先确保引用和数据没有改错，再做术语统一和冗余压缩。
4. 实验结果段先收紧真正要证明的对象，再改句子。
5. 结果段优先回答“实验想证明什么、图里看到了什么、这说明了什么”；方法段只保留系统连接、关键参数、测量链路和分析指标。
6. 频率、功率、工作点、输入范围、步进和代表性谱线等参数要和图中可观测量一一对应。
7. 代表性指标交代选择依据，例如幅度最高、最稳定或能代表其余分量。
8. 区分器件整体物理作用和定量分析指标。代表性谱线可作定量读数，不能把整体结论写窄成只作用于该谱线。
9. 拟合斜率只用于比较功率增长趋势或功率依赖关系；互调来源主要由频率关系、谱线位置和实验链路支撑。
10. 中英双语场景下，英文稿按目标期刊风格二次重写。

如果用户明确要求对齐正式技术文体或英文论文风格，再按需读取 [writing-samples.md](writing-samples.md)；只借句式密度、术语分层和信息推进方式，具体内容仍以当前稿件为准。
