---
name: sciwrite
description: >
  英文句子质量审查。用户说"帮我检查英文句子""删废话""改被动语态""句子太长了""精简表达"
  "这段英文太啰嗦""太冗余""句子质量""check my English writing""improve clarity"
  "clean up the prose""tighten the writing""reduce wordiness"时触发。
  按 Sainani《科学写作》方法论做 5 轮检查：删废话→改被动→理句子结构→统一用词→核对数字和引用。
  只管英文句子质量，不管内容对不对、术语准不准、格式合不合 IEEE 规范。
  不管的事：中文改英文、术语校准、IEEE 结构/图注检查 → 找 sci-paper-edit；
  判断稿子该不该继续改 → 找 paper-review；去掉 AI 写作痕迹 → 找 Humanizer-zh。
---

# 英文句子质量审查（Sainani 五轮检查法）

基于 Kristin Sainani 的《Writing in the Sciences》方法论。只改表达方式，不动科学内容。

## 审查模式

| 模式 | 什么时候用 | 做什么 |
|------|-----------|--------|
| **full-review** | "帮我全面检查英文""full writing review" | 对整篇文档跑 5 轮检查，出结构化报告 |
| **section-review** | "检查这段引言的英文""check the Discussion" | 对单个章节跑 5 轮检查 |
| **targeted** | "帮我改被动语态""删废话" | 只跑对应的那一轮 |
| **interactive** | "一段一段带我改" | 逐段展示修改前后对比和解释 |

分不清用哪个就默认 full-review。

## 5 轮检查

按顺序做，每一轮只关注一个维度。详细的对照表和示例见 `references/sainani-five-pass-checklist.md`。

### 第 1 轮：删废话

把每个句子压到最精简。找出并替换：
- 废话短语（"Due to the fact that" → "Because"，"In order to" → "To"）
- 废话开头（"It is worth noting that" → 直接说要点）
- 重复修饰（"completely eliminate" → "eliminate"，"future plans" → "plans"）

### 第 2 轮：改被动、救动词

科学写作要说清楚"谁做了什么"。
- 被动 → 主动：找到"be + 过去分词"，确认动作执行者，改成"主语→动词→宾语"
- 名词化 → 动词："provides a description of" → "describes"

被动语态在三种情况下可以保留：执行者确实不重要、执行者不明、期刊在 Methods 部分要求被动。

### 第 3 轮：理句子结构

- 主语和动词之间超过约 12 个词 → 句子结构需要重排
- 用冒号引出列表、用破折号插入强调、用分号连接紧密相关的独立子句
- 一段内如果所有句子长度差不多 → 建议长短交替，制造节奏感

### 第 4 轮：用词一致

同一个概念全文必须用同一个词，不要为了"不重复"换同义词。
- Methods 里叫"obese group"，Results 里就不能换成"heavier group"
- 缩写只用公认的（DNA、BER、EVM 等），不要为了省事自创缩写
- 每个缩写在摘要和正文中都要首次定义

### 第 5 轮：数字和引用一致

- 摘要里的样本量和表 1 是否一致
- 正文百分比和表格原始数据是否对得上
- 有效数字是否和测量精度匹配
- 引用的统计数据是否来自一手来源（不是从综述里转引的）

## 输出格式

full-review 和 section-review 输出结构化报告，每一轮列出问题、原文、修改建议和原因，最后给"最值得改的 5 处"。interactive 模式逐段对比。targeted 模式只报告对应轮次。

每个问题标严重程度：
- **CRITICAL** — 会误导读者（数字错、术语不一致暗示了不同变量、被动语态隐藏了关键责任人）
- **MAJOR** — 明显影响可读性（句子结构埋得太深、大量名词化、堆砌废话）
- **MINOR** — 改了更好但不影响理解（轻微啰嗦、可选的风格优化）

## 这个 skill 不管的事

- **不改科学内容。** 如果某个论断看起来有问题，标一个"内容备注"但不改。
- **不管术语对不对。** 术语校准是 sci-paper-edit 的事。
- **不管 IEEE 格式。** 图注、引用格式、模板合规是 sci-paper-edit 的事。
- **不判断稿子该不该继续改。** 这是 paper-review 的事。
- **尊重领域惯例。** 有些领域的 Methods 习惯用被动语态，不强改。
- **保留作者风格。** 目标是清晰，不是统一成一种腔调。
