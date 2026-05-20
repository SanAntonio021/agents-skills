# 上游来源记录

## 原始来源

- **仓库：** labarba/sciwrite（GitHub，原名 manuscript-writing-review）
- **作者：** Lorena A. Barba，George Washington University (GWU)
- **许可证：** CC BY 4.0
- **方法论基础：** Kristin Sainani《Writing in the Sciences》（Stanford/Coursera 课程），30 节课程讲座通过 NotebookLM 转写后由 Claude 整理为 skill

## 本地改了什么

1. **范围限定：** 原版 description 中包含"edit for journal submission""prepare a manuscript for submission"，这些可能和 sci-paper-edit 冲突。本地版明确限定为"纯英文句子质量审查"，不涉及术语校准、IEEE 格式、图注检查、中改英。
2. **description 改中文：** 触发词加了中文表达（"删废话""改被动""精简表达"等）。
3. **详细表格拆分：** 原版把废话短语表、名词化对照表、输出模板全写在 SKILL.md 里（约 10KB），本地版拆到 `references/sainani-five-pass-checklist.md`，SKILL.md 只保留每轮检查的简述和关键规则。
4. **加了分工说明：** 明确写了什么情况不归这个 skill 管，该找哪个 skill。

## 上游维护情况

- 原仓库维护不活跃，核心内容是基于 Sainani 课程讲座的静态方法论提炼，不会频繁变化
- 5 轮检查方法论（删废话、改被动、理句子、统一用词、核对数字引用）已经是成熟的学术写作教学框架
- 除非 Sainani 课程本身大幅更新，否则上游内容不会有实质变化

## 和 sci-paper-edit 的关系

sci-paper-edit 的 `references/manuscript-refinement-checklist.md` 也包含 5 项语言检查，是从 labarba/sciwrite 吸收的。那是 sci-paper-edit 9 步精修流程中内置的一个步骤，服务于"中改英 + 术语 + 终稿"的完整流程。本地 sciwrite 是独立的完整版英文句子审查工具，用户单独想做句子级检查时用。两边各自保留，不冲突。
