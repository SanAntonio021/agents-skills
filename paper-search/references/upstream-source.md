# 本地化来源说明

## 来源身份

- 上游仓库：`https://github.com/K-Dense-AI/scientific-agent-skills.git`
- 上游技能路径：`skills/research-lookup`
- 接受提交：`b085e116c5de7d244fccbd666f1a9e73257999e4`
- 接受版本：`1.4`
- 原作者：K-Dense Inc.
- 许可证：MIT；完整文本见 `../LICENSE.md`

## 已吸收

- 证据记录的保守规范化。
- DOI、PMID 和年份抽取。
- 来源类型分类、规范 URL、按标识符与题名去重。
- 可解释排序、coverage 统计、Markdown 与 BibTeX 输出。

上述逻辑由本地 `scripts/evidence_records.py` 重新整理为只处理既有记录的标准库工具。

## 明确不吸收

- 上游供应商专用检索与认证逻辑。
- 密钥、运行时配置和外部客户端依赖。
- 固定目标篇数、固定文献包和自动生成多文件的默认流程。
- 将搜索摘要直接当作已核实证据的做法。

## 更新策略

人工审查提醒。上游变化只能进入隔离候选；永不自动合并或直接覆盖本地技能。
