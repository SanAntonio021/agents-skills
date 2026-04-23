---
name: patent-writer-agent-local
description: 把 `vendor/PatentWriterAgent` 的专利申请写作方法接到当前 Codex 环境中。Use when the user mentions PatentWriterAgent, wants to draft patent application materials from technical disclosure, or wants to follow that upstream workflow here; prefer this over reading the vendor files directly when you need local execution guidance.
---

# 本地专利写作引导

## 作用

这个 skill 负责承接 `vendor/PatentWriterAgent`，把上游偏 `Claude Code` 的使用假设，转成当前 `Codex` 会话里可直接执行的做法。

重点不是重写上游内容，而是补这几件本地差异：

- 当前环境下该先读哪些文件
- 用户输入需要先收齐到什么程度
- 输出时怎样沿用上游主流程而不失真
- 哪些地方只能先产出草稿，不能替代正式法律审查

## 流程

1. 先读上游基线：
   - `PatentWriterAgent`
   - `PatentWriterAgent`
2. 再判断用户目标：
   - 根据技术交底材料起草专利申请草稿
   - 按上游方法拆开某个写作步骤
   - 检查或整理这个上游 skill 本身
3. 如果是起草专利，先尽量收齐这些信息：
   - 发明主题
   - 关键创新点
   - 与现有技术相比的主要区别
   - 可实施方式和可替代方案
   - 是否需要附图、流程图或示意图
4. 产出时优先沿用上游主线：
   - 理解输入材料
   - 梳理现有技术与区别点
   - 形成申请结构
   - 起草说明书、权利要求或其他所需部分

## 输入边界

如果材料还很散，先补信息，不急着写成完整申请文本。至少要让下面三件事说清：

- 发明到底解决什么问题
- 方案靠什么结构或步骤实现
- 哪些点是希望获得保护的核心内容

## 输出要求

- 默认先给可讨论、可修改的草稿，不把它说成可直接提交的正式法律文件。
- 当用户材料不足时，优先给缺口清单和追问项。
- 涉及权利要求时，尽量区分核心独立点和可下沉的从属点，但不假装替代专利代理人的最终把关。

## 边界

- 不替代正式法律审查、专利代理或专利检索结论。
- 不把普通论文写作、项目申报或产品文案误路由到这里。
- 如果任务是改上游仓库本身，先明确是在维护 `vendor/PatentWriterAgent`，不要把本地接入层当成上游正文。

## 相关文件

- 上游说明：`PatentWriterAgent`
- 上游写作 skill：`PatentWriterAgent`

## 维护

- 上游更新后，先核对主流程有没有变化，再决定这层本地说明是否需要跟着改。
- 这里保留本地接入和使用边界，不复制整段上游正文。
