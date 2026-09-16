# Word 模板目录

以下 10 套模板均可通过 `-Preset`（PowerShell）或 `--preset`（Python）用于导出。
首次导出尚未确认模板时，按文稿用途和读者推荐一套，简短说明理由并询问格式需求，等待用户确认或提出调整要求后再导出。同一任务沿用已确认模板。

| 中文名称 | 导出代码 | 适用用途 | 样式文件名 |
|---|---|---|---|
| 通用报告 | `tongyong-moren` | 一般技术说明、老师审阅稿和综合报告 | `master-default-template` |
| 技术总结 | `jishu-zongjie` | 技术总结、研制及验收报告，使用 `GF报告…` 样式体系 | `default-template` |
| 工作总结 | `gongzuo-zongjie` | 阶段工作总结、工作汇报 | `work-summary-template` |
| 申报风格 | `qiye-shenbao` | 一般项目申报材料 | `qiye-shenbao-template` |
| 经费使用报告 | `funding-usage-report` | 经费使用情况说明 | `funding-usage-report` |
| 节点验收意见 | `node-eval-opinion` | 阶段节点验收意见 | `node-eval-opinion` |
| 技术总结自评 | `technical-summary-self-eval` | 技术总结和自评材料 | `technical-summary-self-eval` |
| 测试大纲评审意见 | `test-outline-review-opinion` | 测试大纲的评审意见 | `test-outline-review-opinion` |
| 第三方专家意见 | `third-party-test-opinion-expert` | 第三方测试专家意见 | `third-party-test-opinion-expert` |
| 第三方机构意见 | `third-party-test-opinion-org` | 第三方测试机构意见 | `third-party-test-opinion-org` |

样式文件位于 `assets/template/`，扩展名为 `.style-profile.json`，保存字体、段落样式和页面设置。导出时据此生成临时 Word 模板；原始样例文件不随技能发布，也不从样例补入正文或固定表单。申报风格不代表特定企业的申报要求。

现有 10 套模板的字体颜色统一为明确的黑色。以后新增或用户提供的模板保留自身颜色。模板只处理排版，不擅自添加版本、日期、说明等内容。

兼容旧代码：`master-default` → `tongyong-moren`、`technical-summary` → `jishu-zongjie`、`work-summary` → `gongzuo-zongjie`、`default` → `qiye-shenbao`。这些别名均需显式传入，不表示自动选择模板。
