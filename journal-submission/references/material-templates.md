# 投稿材料模板

## Cover Letter

```text
Dear Editor-in-Chief,

[SUBMISSION SENTENCE. Include "On behalf of all authors" only after the user's authority to represent all authors is separately confirmed.]

[Problem and scope]
[Contribution and evidence supported by the manuscript]
[Fit with the journal]

[ORIGINALITY, EXCLUSIVE-SUBMISSION, AND AUTHOR-APPROVAL DECLARATIONS. Include each statement only after separate user confirmation.]

Sincerely,
[CONFIRMED SIGNATORY NAME]
[CONFIRMED ROLE; include "on behalf of all authors" only if separately confirmed]
```

署名人、角色和声明必须由用户确认。系统没有指定提交人时，可代表全体作者写 `we` / `our`；署名人和角色必须由用户确认。

如果页面给出 500 words、字符数或其他长度上限，先记录单位和完整字段说明。上限是最大值，不是应达到的目标；Cover Letter 应保持简洁完整，不为凑字数添加空话、重复结果或未经稿件支持的宣传性表述。

## 文件清单

| 本地路径 | 提交文件名 | 用途 | 阶段 | 大小 | SHA-256 | 新鲜度 | 上传状态 |
| --- | --- | --- | --- | --- | --- | --- | --- |

初投稿和录用后最终文件使用不同清单。

## 审稿意见台账

机读台账逐条记录，一行一条意见：

| ID | 来源 | 原始意见 | 分类 | 处理决定 | 修改位置 | 证据 | 回复 | 状态 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |

原始意见保持原文。

### 稳定编号

ID 用 `Rn-m`：`n` 为第几位审稿人，`m` 为该审稿人第几条意见（如 `R1-4` 为审稿人 1 第 4 条）。编号一经确定不随增删条目变动；正文和 Response Letter 的交叉引用都用同一编号。标题不把编号和全角竖线黏在一起（避免 `R1-01｜标题` 这类写法），编号与标题之间用空格。

### 逐条对应体例

写给编辑部的 Response Letter 按审稿人分组、每条意见独立成段，先列原始意见再紧跟回复，使审稿人能逐条核对：

- 一条意见含多个并列小问时，把回复拆成对应的小标题逐问作答，不用“第一、第二”笼统分点；每个小标题对应审稿人该条里的一个具体关注点。
- 意见为单一诉求时，回复按处理动作分点即可，小标题形式与逐问体例保持一致。
- 承诺的稿件修改单独列出（“修改内容”），指明改动位置，与台账的“修改位置”“证据”列对应。

精简示例（一条含多小问的意见）：

```markdown
### R1-2 载波频率的选择依据

**审稿意见（中文）**

> （审稿人原文，保持原样）

**中文回复：**

感谢审稿人的意见。下面按意见中的问题逐条回复。

**（1）选择依据：** ……
**（2）是否合适：** ……
**（3）对性能的影响：** ……
**（4）修改内容：** 我们将在修改稿中……
```

Response Letter 正文和语言精修转 `ieee-manuscript-edit`，LaTeX 和版本文件转 `latex-paper`。

## 最终提交摘要

```text
期刊 / 文章类型：
当前稿件编号：
作者顺序 / 通信作者 / 投稿联系人：
提交文件及 SHA-256：
声明选择：
推荐 / 回避审稿人：
机构匹配状态：
当前页面要求的 proof / preview：
已有内容审查（可选）：实际状态 / 适用版本 / checked_at / evidence / 未决问题
费用 / OA / 版权：不适用、未到阶段或已单独确认
阻断错误：无
仍待确认：
```

摘要用于核对当前提交内容；复用准确的提交授权，本人签署事项仍交用户完成。
