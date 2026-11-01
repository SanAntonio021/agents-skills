# 英文句子质量独立审查参考（Sainani 五轮检查法）

本文件是独立英文句子质量审查的完整参考，采用 Sainani 五轮检查法，由原 `sentence-polish` 技能合并而来。

## 署名与许可

> Original work by Lorena A. Barba (labarba/sciwrite, commit 8a57fa73d541bdcf7d8501db61c018cb454e9afa).
> Licensed under CC BY 4.0.
> Local adaptation by Wang Weipeng (UESTC).
> Merged from standalone sentence-polish skill on 2026-08-10.

本轮选择改编自 Lorena A. Barba 的 [sciwrite v1.0.0](https://github.com/labarba/sciwrite/tree/v1.0.0/skills/sciwrite)（release commit `07ff1389f4394d19c21ff4ffba50ee2c0b40fb2d`），内容许可仍为 [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)。改编范围及未采用项见 [来源取舍](upstream-skill-notes.md)。本地内容更新与集中登记的接受基线分别记录，登记由维护流程回填。

## 审查模式

| 模式 | 什么时候用 | 做什么 |
|------|-----------|--------|
| **full-review** | "帮我全面检查英文""full writing review" | 对整篇文档跑 5 轮检查，出结构化报告 |
| **section-review** | "检查这段引言的英文""check the Discussion" | 对单个章节跑 5 轮检查 |
| **targeted** | "帮我改被动语态""删废话" | 只跑对应的那一轮 |
| **interactive** | "一段一段带我改" | 逐段展示修改前后对比和解释 |

以上模式服从本次 `edit_scope`；未指定整稿时不默认扩成 full-review。摘要表达审查在授权摘要内使用五轮中相关检查，并补下文的摘要检查；中文任务不加载本参考。

## 源文件与事实保护

- 引用原句与建议时保留 LaTeX/Markdown 标记、数学、宏、注释、citation keys、`\cite`、`\ref`、`\eqref` 和 `\label`。文件定位使用原始源码行号；粘贴文本使用段落号和开头短语，不能伪造文件行号。
- 引述他人的原话不作为作者语言直接改写。保持作者的英式或美式拼写；同稿混用时只报告具体不一致。
- 数字、百分比或公式相互矛盾时列出双方位置和待核实依据，不自行决定哪方正确，不直接修改数学中的数值。缺结果或引用只列缺项；明确要求草拟时可留待补位置，不能写成已有事实。
- 判断图像数据与表文是否一致，必须实际读取图像或底层数据。只有文字或图注时说明图像核验未做；可核对已有文本，不能声称看过图。
- 只审任务保持只读；修改任务遵守主入口的授权与版本保护。跨节术语和数字核对仅在授权范围及可用材料内进行。

## 严重程度

- **CRITICAL** — 会误导读者（数字错、术语不一致暗示了不同变量、被动语态隐藏了关键责任人）
- **MAJOR** — 明显影响可读性（句子结构埋得太深、大量名词化、堆砌废话）
- **MINOR** — 改了更好但不影响理解（轻微啰嗦、可选的风格优化）

---

# Sainani 五轮检查 — 详细对照表

基于 Kristin Sainani《Writing in the Sciences》方法论。这个文件是 SKILL.md 里 5 轮检查的详细展开，包含查找表和示例。

---

## 第 1 轮：删废话

### 废话短语替换表

| 废话 | 替换为 |
|------|--------|
| Due to the fact that | Because |
| A majority of | Most |
| Are of the same opinion | Agree |
| Give rise to | Cause |
| Have an effect on | Affect |
| In the event that | If |
| At the present time | Now / Currently |
| In order to | To |
| A number of | Several / Many |
| On the basis of | Based on |
| In light of the fact that | Because / Since |
| It is worth noting that | （删掉，直接说要点） |
| It is important to note that | （删掉） |
| It is interesting to note that | （删掉） |
| In terms of | （重写，说具体） |
| With regard to | About / Regarding |
| In the absence of | Without |
| Has the ability to | Can |
| Is capable of | Can |
| In a manner similar to | Like |
| Take into consideration | Consider |
| Despite the fact that | Although |

### 废话开头（标记删除）

- "As it is well known..." → 换成直接引用
- "It should be emphasized that..."
- "It can be regarded that..."
- "As it has been shown..."
- "It is noteworthy that..."
- "It goes without saying that..."

### 重复修饰（删掉多余的词）

| 重复 | 改为 |
|------|------|
| successful solutions | solutions |
| completely eliminate | eliminate |
| future plans | plans |
| unexpected surprise | surprise |
| currently underway | underway |
| basic fundamentals | fundamentals |
| final outcome | outcome |
| past history | history |
| true facts | facts |
| end result | result |
| consensus of opinion | consensus |

---

## 第 2 轮：改被动、救动词

### 名词化 → 动词对照表

| 名词化形式 | 还原为动词 |
|-----------|-----------|
| Provides a review of | Reviews |
| Offers a confirmation of | Confirms |
| Shows a peak | Peaks |
| Obtains an estimate of | Estimates |
| Conducts an assessment of | Assesses |
| Provides a description of | Describes |
| Makes an adjustment to | Adjusts |
| Performs an analysis of | Analyzes |
| Achieves a reduction in | Reduces |
| Has an influence on | Influences |
| Makes a contribution to | Contributes to |
| Provides an explanation of | Explains |
| Takes into consideration | Considers |
| Gives an indication of | Indicates |

### 被动 → 主动转换步骤

1. 找到"be + 过去分词"结构（"was observed""were analyzed""is induced"）
2. 确认动作执行者：谁做的？材料明确为作者团队时可用 "We"；执行者未知时保留被动，不从语法猜测执行者。
3. 改成"主语→动词→宾语"

示例：
- 被动: "The activation of channels is induced by the depletion of stores."
- 主动: "Depleting stores activates channels."

- 被动: "The data were analyzed using MATLAB."
- 主动: "We analyzed the data using MATLAB."

### 保留被动语态的三种情况

1. 执行者确实不重要或不明确（"The sample was collected in 2019"）
2. 期刊在 Methods 部分的惯例要求被动
3. 刻意强调承受者而非执行者

---

## 第 3 轮：句子结构

### 修饰、指代与段落关系

- 检查悬垂或错位修饰语是否改变“谁做了什么”。把修饰语移近实际对象；缺执行者证据时可改成被动方法表达，不补造 "We"。
- `This` / `These` 无名词并不自动有错。仅当存在多个可能先行项、关系不清时建议补具体名词；无法确定指代时先列歧义，不替作者选结论。
- 句子承载多项独立论点且主线难辨时再拆分，保持每项条件及限定的归属。技术名词和必要名词化不是待删废话，只在更短且含义不变时改。
- 逐段核对主线、句间衔接，以及 `However` / `Therefore` 等是否真的表达转折或因果。引言、讨论段主旨不明时可用段内既有事实建议主题句；程序步骤段不强制主题句。不按句数、句长或连接词命中机械报错，也不为形成因果关系补实验解释。

### 埋主语检查

主语与主动词间超过约 12 个词时，复核插入内容是否妨碍理解。词数只是定位线索；关系清楚且技术限定必要时保留，不按阈值自动重组。

示例：
- 埋了: "One study of 930 adults with MS receiving care in one of two managed care settings found that..."
- 改好: "One study found that, among 930 adults with MS in managed care settings, ..."

### 标点使用

| 标点 | 什么时候用 |
|------|-----------|
| 冒号（:） | 引出列表或具体解释，替代啰嗦的开头 |
| 破折号（—） | 插入强调性的补充说明，或合并两个句子 |
| 分号（;） | 连接紧密相关的独立子句，减少连接词 |

### 节奏检查

句长相近本身不是问题。仅在重复句式妨碍重点或关系理解时调整；短句可用于强调，长句可用于解释，清楚自然的段落不为节奏而改写。

---

## 第 4 轮：用词一致

### "香蕉规则"

不要把"香蕉"叫成"细长的黄色水果"来避免重复。技术术语的一致比文学性的同义词替换更重要。

### 检查步骤

1. 从 Methods 里提取所有关键词（组别名、变量名、技术名、缩写）
2. 检查 Results、Discussion、表格、图注里是否用了完全一样的词
3. 标记所有用了同义词替代的地方

### 缩写规则

- 只用公认缩写（DNA、RNA、BER、EVM、SNR、FEC 等）
- 不要为了省事自创缩写
- 摘要、正文、图注、表注分别判断缩写作用域；是否需要定义按目标读者、实际复用及已核实期刊要求处理，不机械要求每幅图重复展开。

---

## 第 5 轮：数字和引用

### 数字一致性检查

- 摘要里的 N 和表 1 的 N 是否一致
- 正文中的百分比和表格中的原始数据是否对得上
- 有效数字是否和测量精度匹配
- 图中的数据是否和对应表格的数据一致

### 引用完整性 —— "电话游戏"检查

标记所有通过二手来源（综述、教科书）引用的统计数据。常见问题："According to [Review, 2020], the prevalence is 15–62%..." —— 但这些数字背后的原始研究可能范围和条件完全不同。

建议作者核实一手来源。

---

## 英文摘要检查

- 核对研究问题、方法、实际结果及受结果支持的意义是否能辨认。只有方法或计划而没有结果时指出缺项，不把 "This study investigates" 改成未经提供的发现。
- 缩减空开头和背景前先判断是否挤占结果信息。工程摘要中的关键定量结果、实验条件、比较对象和科学限定必须保留；不以通俗化为由删除决定结论范围的参数或技术名。
- 目标期刊未知时使用通用工程论文标准，字数上限、引用政策和必需组成保持未核实；不能默认 Nature 的 200/300 词、七个 moves、固定句数或 "Here we show"。有明确模板或官方规则时才据此判断合规性。
- 摘要可用一句承担多个功能，不强制每项单独一句，也不为缺一个固定 move 判 CRITICAL。背景被动语态和自然清楚的句式可保留。
- 报告仅说明实际缺项、逻辑或表达问题及期刊规则的核实边界；不默认输出整段标注副本或全文改写。

## 审查报告

- 先用简短总评说明主要问题及未核验材料；只保留确有发现的检查栏目，无问题不凑五轮空标题。
- 同一问题重复出现时合并报告：给总数、两三个代表性原句与建议，其余位置列表。不同含义或条件不能为了合并而漏报。
- CRITICAL / MAJOR 给原始位置、准确原句、可用建议及一句理由；事实未决时给待核实项而非代造修订。MINOR 紧凑列“位置：原句 → 建议”，不重复长解释。
- 优先项只列实际值得改的内容，不凑五处；清楚、自然且含义准确的句子可直接保留。科学内容核实超出本次权限时单列待核实问题，不冒充已完成的科学审查。


## 适用边界

本参考只规范英文句子质量；术语正确性、IEEE 格式和科学内容判断不在范围内。审查时应尊重领域惯例（例如 Methods 部分采用被动语态）和作者风格。
