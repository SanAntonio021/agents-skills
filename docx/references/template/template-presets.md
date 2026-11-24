# Word 模板目录

按文稿用途查目录。科研或工程项目的年度报告、课题年度进展、系统实验年度总结，优先选用下列年度进展模板。委托方指定格式或项目已有明确约定时按该约定执行。

## 项目年度进展报告

[项目年度进展报告 Word 模板](../../assets/template/project-annual-progress.dotx)随技能安装。链接相对于本目录，在新工作区也能定位。用 Word 的“基于模板新建”创建独立 `.docx`，按本项目材料替换栏目、插图与表格。Markdown 已定稿时，将正文填入新建文档，保留模板内的页脚、编号域和制表位。模板中的公式位置用于插入可编辑的 MathType 对象。

向用户介绍此模板时沿用下表的行名。即使只看格式或要求简要说明，也保留各行，每行的参数可以精简。

| 部位 | 模板格式 |
| --- | --- |
| 页面 | A4 纵向，上下页边距 2.54 cm，左右各 3.175 cm，页脚页码居中。 |
| 报告总标题（标题 1） | 黑体 15 磅，常规字重，单倍行距，段前、段后各 0.5 行。 |
| 章标题（标题 2） | 黑体 14 磅，常规字重，单倍行距，段前、段后各 1 行。 |
| 节标题（标题 3） | 宋体 12 磅，加粗，行距最小值 20.8 磅，段前、段后各 13 磅。 |
| 正文 | 宋体 12 磅，两端对齐，首行缩进 24 磅，固定行距 25 磅，段前、段后均为 0 磅。 |
| 图片 | 图段居中，与图题同页。 |
| 图题 | 位于图下，黑体 10 磅，居中。 |
| 表题 | 位于表上，黑体 10 磅，居中，与表格开头同页。 |
| 表格 | 单元格文字居中、单倍行距，表头加粗、跨页重复。 |
| 公式 | 独立公式居中，编号用全角括号、靠右，单倍行距，段前、段后各 3 磅。 |

以上三级标题均两端对齐、首行缩进为 0。标题、正文和题注的英文及数字均用 Times New Roman。图、表、公式分别使用 SEQ 域，正文引用使用 REF 域。交付前更新域、检查实际分页。

## 可通过预设代码导出的样式配置

以下 10 套模板均可通过 `-Preset`（PowerShell）或 `--preset`（Python）用于导出。
未指定模板时，按用途和读者推荐一套模板；先按[导出前的格式说明与确认](../layout-profiles.md#导出前的格式说明与确认)展示其具体设置并核实不确定项，用户确认后再导出。同一任务沿用已确认且未变化的格式。

| 中文名称 | 导出代码 | 适用用途 | 样式文件名 |
|---|---|---|---|
| 通用默认模板 | `tongyong-moren` | 适用于一般技术说明和综合报告，可作为候选推荐 | `master-default-template` |
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

兼容别名：`default`、`master-default` → `tongyong-moren`，`technical-summary` → `jishu-zongjie`，`work-summary` → `gongzuo-zongjie`。申报风格使用 `qiye-shenbao`。
