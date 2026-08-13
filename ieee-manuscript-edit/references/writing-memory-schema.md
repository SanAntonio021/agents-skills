# 受控论文写作记忆契约

## 数据位置

- 通用文风词：`D:\BaiduSyncdisk\.agents\vocab\vocab-full.md`
- 核心通用词：`D:\BaiduSyncdisk\.agents\vocab\vocab-core.md`
- 专业术语：`D:\BaiduSyncdisk\.agents\vocab\scientific-terminology-bank.md`
- 学术表达模式：`D:\BaiduSyncdisk\.agents\vocab\academic-expression-bank.md`
- 候选状态：`D:\BaiduSyncdisk\.agents\vocab\writing-memory-candidates.md`
- 结构化例外：`D:\BaiduSyncdisk\.agents\vocab\writing-memory-exceptions.md`

旧术语库的迁移映射：旧表中的 `状态`、`中文术语`、`推荐英文`、`可接受变体`、`慎用写法`、`适用领域`、`来源`、`用户审阅` 和 `最后更新` 分别映射到活数据术语库的同名字段；`章节功能`、`匹配模式` 和 `例外覆盖用户禁用` 缺失时，记录必须先标为 `待迁移`，不能根据自然语言备注自动补齐。旧表只作为兼容入口，未知字段不得自动推断为正式规则。

## 状态机

```text
候选 -> 已确认       用户明确接受
候选 -> 已拒绝       用户明确拒绝，并记录理由
已确认 -> 冲突待审   新证据与现有记录冲突
冲突待审 -> 已确认   用户裁决保留新规则
冲突待审 -> 已拒绝   用户裁决不采用新规则
```

未确认、已拒绝、待迁移记录永远不进入生成约束。用户确认候选后，必须把完整记录迁入对应活数据表：通用文风词迁入 `vocab-full.md`，专业术语迁入 `scientific-terminology-bank.md`，表达模式迁入 `academic-expression-bank.md`；候选台账必须填写类型、来源、用户确认和迁入位置。只改状态、不迁入仍属于未完成。拒绝记录保留，防止同义变体在下一轮绕过确认门。

## 优先级

1. 引用原文、参考文献、代码、URL、LaTeX 命令和 citation key 不参与词表约束。
2. 用户明确的硬禁用规则优先于普通术语建议。
3. 只有已确认、作用域匹配、用户审阅为 `是` 且显式标记 `例外覆盖用户禁用=是` 的术语或结构化例外，才能覆盖指定硬禁用；冲突必须进入待确认列表。
4. 术语、表达模式和例外均按领域、目标期刊、章节功能过滤；不匹配项不自动应用。

## 外部样本边界

从正式论文取样前先获得用户同意。只提炼术语、标准搭配或抽象语法模式；不保存完整句子、连续长片段、图注或方法描述。表达模式最多 4 个连续实词，并记录 DOI/正式链接和章节功能。一次学习会话最多提交 3 条候选，用户可逐条接受、拒绝或保留待审。

## 复扫硬门

每次写入或交付论文稿后运行 `scripts/audit_writing_memory.py`。报告必须记录输入文件 SHA-256、词表/术语库 SHA-256、审计器版本和上下文。`violations`、`unresolved` 或 `schema_errors` 非空时，状态只能是“复扫未通过”，不得声称精修完成。
