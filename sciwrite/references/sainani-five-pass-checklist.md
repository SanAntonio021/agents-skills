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
2. 确认动作执行者：谁做的？如果是作者团队，用 "We"
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

### 埋主语检查

数主语到主动词之间的词数。超过约 12 个词就需要重组。

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

一段内如果所有句子长度差不多（±5 个词以内），标记需要调整。建议：短句用于强调，长句用于解释。

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
- 每个缩写在摘要和正文中都要分别首次定义
- 每个表格和图注中也要独立定义（读者不一定从头读）

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

## 输出模板（full-review 模式）

```
## 英文写作质量审查：[文档/章节标题]

### 总评
[2-3 句总体评价：主要问题集中在哪里、整体清晰度]

### 第 1 轮：废话 — [N 处问题]
[每处：段落/行号、原文、修改建议、原因]

### 第 2 轮：语态和动词 — [N 处问题]
[同上]

### 第 3 轮：句子结构 — [N 处问题]
[同上]

### 第 4 轮：用词一致 — [N 处问题]
[同上]

### 第 5 轮：数字和引用 — [N 处问题]
[同上]

### 最值得改的 5 处
[按影响大小排序，每处说清楚改什么、为什么重要]
```
