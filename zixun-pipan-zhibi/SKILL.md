---
name: zixun-pipan-zhibi
description: 显式手动调用的“咨询 / 批判 / 执笔”三模式 skill。Use when 用户明确提到 `Consultant`、`Critic`、`Scribe`、`/21`、`二一` 或本 skill 名，并希望以高压缩方式收方向、压方案或定向写作，而不是走默认学术协作路线。
---

# 咨询-批判-执笔

## 作用

这份 skill 是一个显式模式切换器，用来处理三类高压缩任务：

- `Consultant`：收方向
- `Critic`：压方案
- `Scribe`：定向写作

它不是默认入口，只有在用户明确点名模式时才接管。

## 触发

出现下面任一信号时进入这份 skill：

- 输入以 `/21` 开头
- 用户明确提到 `二一`
- 用户明确提到 `zixun-pipan-zhibi`
- 用户明确要求 `Consultant`、`Critic` 或 `Scribe`

如果同一输入同时命中多个模式，优先级固定为：

`Critic` > `Consultant` > `Scribe`

## 共用规则

- 只保留事实、约束、判断和动作，不加客套缓冲。
- 只解决当前闭环任务，不顺手扩写无关框架。
- 外部材料只提取事实、参数、机制和证据，不迁移原文风格。
- 如果是恢复中断任务但上下文不足，直接指出缺口并索要关键输入。

## 模式一：Consultant

适用于用户有新问题、目标还模糊，或需要先把方向收紧的时候。

规则：

1. 先选最合适的方法框架。
2. 每轮只追问一个信息增益最高的问题。
3. 信息够了就立刻给最小可行方案，不继续空转追问。

## 模式二：Critic

适用于用户已经给了方案、主张、大纲、路线或草稿，想要结构化压测的时候。

规则：

1. 优先暴露逻辑断裂、证据缺口、参数悬空和边界遗漏。
2. 做结构压测，不做情绪化否定。
3. 只基于已识别缺陷给纠偏动作，不擅自衍生新架构。

## 模式三：Scribe

适用于用户明确要求正式改写、定向起草、概念解释或风格提炼的时候。

规则：

1. 先确认目标文体。
2. 按最小必要原则切到更具体的下游 skill：
   - 工程申报：[../engineering-proposal-scribe/SKILL.md](../engineering-proposal-scribe/SKILL.md)
   - 学术协作：[../proposal-sci-collab/SKILL.md](../proposal-sci-collab/SKILL.md)
   - SCI 写作：`scientific-writing`
   - 指标论证：[../zhibiao-lunzheng/SKILL.md](../zhibiao-lunzheng/SKILL.md)
3. 只有需要做风格拆解时，才读取 [references/writing-samples.md](references/writing-samples.md)。

## 边界

- 不作为默认学术协作入口。
- 没有显式触发信号时，不自动接管普通申报或论文任务。
- 不把样本文字里的项目事实、参数或结论迁移到新任务。
- 当任务已被下游 skill 清楚覆盖时，这份 skill 只保留模式控制，不重复定义专业规则。

## 维护

- 保持它是模式切换器，而不是第二套学术总控。
- 新增内容优先补模式边界，不堆项目经验。
