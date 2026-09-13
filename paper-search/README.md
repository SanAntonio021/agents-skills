# paper-search

面向科研对话的本地论文检索与引用核验技能。它通过现有 `web-access` 完成发现与来源核实，默认先返回一批可靠结果，并在“继续找”“太少”“再深入”等追问中沿用原条件扩展和去重。正式引用生成、出版元数据核验和纠错核实相关条目，复用可定位且未变化的结果；具体疑点只核相关条目。仅 BibTeX 语法、样式、引用键对应或编译交给 `latex-paper`，不因关键词重查全库。

## 职责

- 为明确的文章或持续调研复用一个 Zotero 任务分类：先找库内文献，再向外补缺口；同一条目可加入多个任务，保留原分类和附件。普通一次性查询不自动写库。
- 文献通用阅读笔记留在 Zotero；当前文章的引用用途和待核问题留在工作区已有提纲、主稿或记录，不默认新建账本或状态子分类。

- 论文优先；按问题需要补充直接相关的标准、政策和官方数据。
- 搜索摘要只作为发现线索，最终条目保留题名、年份、来源类型、直接链接或 DOI、相关性和核实状态。
- 默认在对话中交付；只有用户指定文件类型时才生成文件。
- 正式引用模式核对正式版本、作者、刊名或会议名、卷期、页码或文章号、日期和标识符；缺的信息留空，并直接说明没查到什么。
- 支持 IEEE 引用输出、BibTeX 对照和已有引用清单纠错；修正清单时保持原编号和输入顺序。
- 已知论文下载交给 `paper-download`；全文总结按请求整理，Zotero 笔记读写使用现有 Zotero 插件；原文核对和审稿交给 `paper-review`；成文报告交给 `research-report`；普通参数或多渠道比较表交给 `xlsx`，明确持续产品库或库契约审计交给 `product-research-workbook`。
- 整篇稿件的漏引、错引和正文编号覆盖检查交给相应论文编辑或审查技能；飞书写回按实际载体交给 `lark-doc` 或 `lark-base`，本技能只提供核验结果。

## 证据整理工具

`scripts/evidence_records.py` 是无网络、标准库实现，只整理已经取得的 JSON 证据记录：

```text
python scripts/evidence_records.py --input <json> --format json|markdown|bibtex|ieee [--order ranked|input] [--bibtex-input <bib>] [--output <path>]
```

输入可为数组，也可为：

```json
{
  "query": "research question",
  "records": [
    {
      "title": "Paper title",
      "year": 2025,
      "source_type": "journal-article",
      "url": "https://example.org/article",
      "doi": "10.1234/example",
      "relevance": "Directly evaluates the requested system condition.",
      "verification_status": "primary-source-verified"
    }
  ]
}
```

`title`、`relevance` 以及 `url`/`doi` 中至少一个是输入校验的必需信息。v2 记录还可包含完整作者列表、期刊/会议名、卷、期、页码、文章号、出版者、出版日期、访问日期、ISBN、arXiv ID、字段来源、原引用和逐条问题；旧 v1 输入继续可读。年份会从结构化字段或现有文本中保守提取；找不到时保留为空并在问题中说明。脚本不会把 DOI 的存在自动提升为直接来源已核实，也不会自行联网补字段。

`--order ranked` 保留普通检索的相关度排序；`--order input` 用于核对已有参考文献，保持用户原编号顺序。`--bibtex-input` 传入要与核实记录逐项对照的现有 `.bib` 文件。正式引用字段和 BibTeX 对照规则见 `references/citation-workflow.md`。

## 来源与许可

证据规范化与去重逻辑改写自 K-Dense Inc. 的 `research-lookup` 1.4，接受提交为 `b085e116c5de7d244fccbd666f1a9e73257999e4`。BibTeX 解析、规范化和一致性检查思路参考同仓库的 `citation-management` 2.0，接受提交为 `1dd0fccf46fc3c9855c4a0c313a0c57fe4319883`。本地保留 MIT 许可和原作者信息；供应商检索客户端、凭证、固定数量门槛和整篇稿件检查未移植。IEEE 格式规则单独依据 IEEE Author Center 的公开 Reference Guide，不宣称由 K-Dense 上游提供。
