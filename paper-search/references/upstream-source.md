# 本地化来源说明

## 来源身份

- 上游仓库：`https://github.com/K-Dense-AI/scientific-agent-skills.git`
- 上游技能路径：`skills/research-lookup`
- 接受提交：`b085e116c5de7d244fccbd666f1a9e73257999e4`
- 接受版本：`1.4`
- 原作者：K-Dense Inc.
- 许可证：MIT；完整文本见 `../LICENSE.md`

## 引用管理来源身份

- 上游仓库：`https://github.com/K-Dense-AI/scientific-agent-skills.git`
- 上游技能路径：`skills/citation-management`
- 接受提交：`1dd0fccf46fc3c9855c4a0c313a0c57fe4319883`
- 接受版本：`2.0`
- 接受目录 tree：`27852a2bf7570d4556395f12237b27f75bd91ae7`
- 该目录最近内容修改提交：`3378ecea5702801512e18ad37d52fd069e8653b0`
- 原作者：K-Dense Inc.
- 许可证：MIT；完整文本见 `../LICENSE.md`

## 已吸收

- 证据记录的保守规范化。
- DOI、PMID 和年份抽取。
- 来源类型分类、规范 URL、按标识符与题名去重。
- 可解释排序、coverage 统计、Markdown 与 BibTeX 输出。

上述逻辑由本地 `scripts/evidence_records.py` 重新整理为只处理既有记录的标准库工具。

引用管理来源中只吸收并重新实现：

- 嵌套花括号安全的 BibTeX 解析和稳定渲染思路；
- DOI、页码范围、字段顺序和 citation key 的规范化；
- DOI 优先、规范化题名辅助的条目匹配；
- 不同条目类型的字段检查和逐项问题分类。

## 明确不吸收

- 上游供应商专用检索与认证逻辑。
- 密钥、运行时配置和外部客户端依赖。
- 固定目标篇数、固定文献包和自动生成多文件的默认流程。
- 将搜索摘要直接当作已核实证据的做法。
- `requests`、`scholarly` 以及 OpenAlex、PubMed、Crossref、DataCite、arXiv 的直接客户端和凭证环境变量。
- Google Scholar 抓取、代理、固定参考文献数量、`--min-count`、Zotero 和整篇稿件引用键覆盖检查。
- 缺卷、页码或 DOI 就强制补齐，以及复杂 BibTeX 无提示静默跳过的行为。

## 更新策略

人工审查提醒。上游变化只能进入隔离候选；永不自动合并或直接覆盖本地技能。

## 本次引用能力扩展

- IEEE 格式规则依据 IEEE Author Center 的公开 `IEEE Reference Guide`：https://journals.ieeeauthorcenter.ieee.org/wp-content/uploads/sites/7/IEEE_Reference_Guide.pdf
- IEEE 文本渲染、字段冲突说明和缺失字段留空政策是本地工作流设计，不把官方格式指南登记为代码上游，也不宣称 K-Dense 上游提供 IEEE 格式能力。
- 引用管理来源的固定链接：https://github.com/K-Dense-AI/scientific-agent-skills/tree/1dd0fccf46fc3c9855c4a0c313a0c57fe4319883/skills/citation-management
