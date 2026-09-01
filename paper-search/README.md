# paper-search

面向科研对话的本地论文检索技能。它通过现有 `web-access` 完成发现与来源核实，默认先返回一批可靠结果，并在“继续找”“太少”“再深入”等追问中沿用原条件扩展和去重。

## 职责

- 论文优先；按问题需要补充直接相关的标准、政策和官方数据。
- 搜索摘要只作为发现线索，最终条目保留题名、年份、来源类型、直接链接或 DOI、相关性和核实状态。
- 默认在对话中交付；只有用户指定文件类型时才生成文件。
- 已知论文下载交给 `paper-download`；全文总结交给 `paper-summary`；审稿交给 `paper-review`；成文报告交给 `research-report`；产品调研交给 `product-research-workbook`。

## 证据整理工具

`scripts/evidence_records.py` 是无网络、标准库实现，只整理已经取得的 JSON 证据记录：

```text
python scripts/evidence_records.py --input <json> --format json|markdown|bibtex [--output <path>]
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

`title`、`relevance` 以及 `url`/`doi` 中至少一个是输入校验的必需信息。年份会从结构化字段或现有文本中保守提取；找不到时保留为 `unknown`。脚本不会把 DOI 的存在自动提升为直接来源已核实。

## 来源与许可

证据规范化与去重逻辑改写自 K-Dense Inc. 的 `research-lookup` 1.4 中 `manuscript_packet.py`，接受基线为 `b085e116c5de7d244fccbd666f1a9e73257999e4`。本地保留 MIT 许可和原作者信息；供应商专用检索脚本及固定文件包流程未移植。
